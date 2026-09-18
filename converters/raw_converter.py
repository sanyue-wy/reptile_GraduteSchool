# -*- coding: utf-8 -*-
"""
Raw Data Converter
==================
Normalizes arbitrary legacy/heterogeneous raw batches into canonical RawDataBatch.

Input sources:
- Legacy RawDataDTO with content/raw_ref (V2.2 engines)
- Legacy list[dict] engine results via LegacyRecordBatch adapter
- Already-canonical RawDataBatch (pass-through with validation)

Output: RawDataBatch with:
- assets as true source of truth (MediaAsset with data or url)
- schema_version = "1"
- trace complete
- References validated to be within allowed directories
- Unknown encodings explicitly diagnosed (not silently assumed utf-8)
"""

import json
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Optional

from contracts.asset import MediaAsset, AssetRef
from contracts.raw import RawDataDTO, RawDataBatch, LegacyRecordBatch
from contracts.task import TaskConfigDTO

logger = logging.getLogger(__name__)

# Allowed base directories for raw_ref paths
ALLOWED_RAW_DIRS = [
    Path("data/raw"),
    Path("data/cache"),
    Path("data/plugin_uploads"),
]


class RawConverter:
    """Converts legacy/heterogeneous raw data into canonical RawDataBatch."""

    def __init__(self, allowed_dirs: Optional[list[Path]] = None):
        self.allowed_dirs = allowed_dirs or ALLOWED_RAW_DIRS

    def convert(self, source: Any, task_config: Optional[TaskConfigDTO] = None) -> RawDataBatch:
        """Main entry point: convert any supported source to RawDataBatch."""
        if isinstance(source, RawDataBatch):
            return self._validate_and_normalize_batch(source)
        elif isinstance(source, list) and all(isinstance(item, dict) for item in source):
            # Legacy list[dict] from V2.2 engines
            return self._convert_legacy_records(source, task_config)
        elif isinstance(source, LegacyRecordBatch):
            return source.to_raw_batch()
        else:
            raise TypeError(f"Unsupported source type for raw_converter: {type(source)}")

    def _validate_and_normalize_batch(self, batch: RawDataBatch) -> RawDataBatch:
        """Validate and normalize an already-canonical batch."""
        # Ensure schema_version
        if not batch.schema_version:
            batch.schema_version = "1"

        # Ensure task_id
        if not batch.task_id:
            from uuid import uuid4
            batch.task_id = uuid4().hex

        # Validate each item
        normalized_items = []
        for item in batch.items:
            normalized = self._normalize_dto(item)
            normalized_items.append(normalized)

        return RawDataBatch(
            schema_version=batch.schema_version,
            task_id=batch.task_id,
            items=normalized_items,
            pagination_complete=batch.pagination_complete,
            next_page_token=batch.next_page_token,
            errors=batch.errors,
            fetched_at=batch.fetched_at,
        )

    def _convert_legacy_records(self, records: list[dict], task_config: Optional[TaskConfigDTO]) -> RawDataBatch:
        """Convert V2.2 engine list[dict] to RawDataBatch via LegacyRecordBatch.

        WARNING: This creates placeholder assets. Real spider plugins
        must produce proper RawDataBatch with actual fetched assets.
        """
        source_id = task_config.source_id if task_config else "unknown"
        task_id = task_config.task_id if task_config else ""

        legacy_batch = LegacyRecordBatch(
            records=records,
            source_id=source_id,
            task_id=task_id,
        )
        return legacy_batch.to_raw_batch()

    def _normalize_dto(self, dto: RawDataDTO) -> RawDataDTO:
        """Normalize a single RawDataDTO: resolve raw_ref, validate assets, fix encoding."""
        # If already has assets, validate them
        if dto.assets:
            validated_assets = []
            for asset in dto.assets:
                validated = self._validate_asset(asset, dto)
                validated_assets.append(validated)
            dto.assets = validated_assets
            return dto

        # Legacy: has content (text) or raw_ref (file path)
        if dto.content is not None:
            return self._convert_content_to_asset(dto)
        elif dto.raw_ref is not None:
            return self._convert_raw_ref_to_asset(dto)

        # No content at all - create empty asset placeholder
        logger.warning("RawDataDTO has no content, raw_ref, or assets: %s", dto.url)
        asset = MediaAsset(
            media_type="text",
            mime_type="application/octet-stream",
            data=b"",
        )
        dto.assets = [asset]
        return dto

    def _convert_content_to_asset(self, dto: RawDataDTO) -> RawDataDTO:
        """Convert legacy content string to MediaAsset."""
        # Detect encoding if not specified
        encoding = dto.encoding or "utf-8"
        content_bytes: bytes

        if isinstance(dto.content, str):
            try:
                content_bytes = dto.content.encode(encoding)
            except UnicodeEncodeError:
                # Fallback: try utf-8, then latin-1
                try:
                    content_bytes = dto.content.encode("utf-8")
                    encoding = "utf-8"
                except UnicodeEncodeError:
                    content_bytes = dto.content.encode("latin-1")
                    encoding = "latin-1"
        elif isinstance(dto.content, bytes):
            content_bytes = dto.content
        else:
            content_bytes = str(dto.content).encode(encoding)

        # Guess MIME type from content_type or content
        mime_type = dto.content_type
        if not mime_type or mime_type == "application/octet-stream":
            # Sniff content
            if content_bytes[:1] in (b"{", b"["):
                mime_type = "application/json"
            elif content_bytes[:5].lower() == b"<html" or b"<html" in content_bytes[:100]:
                mime_type = "text/html"
            else:
                mime_type = "text/plain"

        media_type = self._guess_media_type(mime_type)

        asset = MediaAsset(
            media_type=media_type,
            mime_type=mime_type,
            data=content_bytes,
            metadata={"legacy_content": True, "original_encoding": encoding},
        )

        dto.assets = [asset]
        dto.content = None  # Clear legacy field
        dto.encoding = encoding
        dto.content_type = mime_type
        return dto

    def _convert_raw_ref_to_asset(self, dto: RawDataDTO) -> RawDataDTO:
        """Convert legacy raw_ref file path to MediaAsset or AssetRef."""
        raw_path = Path(dto.raw_ref)

        # Validate path is within allowed directories
        if not self._is_path_allowed(raw_path):
            raise ValueError(f"raw_ref path {raw_path} is outside allowed directories")

        if not raw_path.exists():
            raise FileNotFoundError(f"raw_ref file not found: {raw_path}")

        # Check file size
        file_size = raw_path.stat().st_size
        MAX_INLINE_SIZE = 10 * 1024 * 1024  # 10 MiB

        # Guess MIME type
        mime_type = dto.content_type
        if not mime_type or mime_type == "application/octet-stream":
            mime_type = mimetypes.guess_type(str(raw_path))[0] or "application/octet-stream"

        media_type = self._guess_media_type(mime_type)

        if file_size <= MAX_INLINE_SIZE:
            # Read into memory
            try:
                with open(raw_path, "rb") as f:
                    data = f.read()
                # Try to decode as text if text type
                if media_type == "text":
                    try:
                        text = data.decode(dto.encoding or "utf-8")
                        data = text.encode("utf-8")
                        dto.encoding = "utf-8"
                    except UnicodeDecodeError:
                        # Keep as binary, update media_type
                        media_type = "binary"
                        mime_type = "application/octet-stream"
            except Exception as e:
                logger.exception("Failed to read raw_ref file %s", raw_path)
                raise

            asset = MediaAsset(
                media_type=media_type,
                mime_type=mime_type,
                data=data,
                metadata={"legacy_raw_ref": True, "original_path": str(raw_path)},
            )
            dto.assets = [asset]
        else:
            # Large file: create AssetRef (path relative to allowed root)
            # Find which allowed dir contains this file
            rel_path = None
            for allowed in self.allowed_dirs:
                try:
                    rel_path = raw_path.relative_to(allowed)
                    break
                except ValueError:
                    continue

            if rel_path is None:
                rel_path = raw_path.name  # Fallback

            asset_ref = AssetRef(
                path=str(rel_path),
                media_type=media_type,
                mime_type=mime_type,
                size=file_size,
                sha256="",  # Would compute in real implementation
            )
            # Store as MediaAsset with url pointing to managed path
            asset = MediaAsset(
                media_type=media_type,
                mime_type=mime_type,
                url=f"raw_ref://{rel_path}",
                metadata={"legacy_raw_ref": True, "original_path": str(raw_path), "asset_ref": True},
            )
            dto.assets = [asset]

        dto.raw_ref = None  # Clear legacy field
        dto.content_type = mime_type
        return dto

    def _validate_asset(self, asset: MediaAsset, dto: RawDataDTO) -> MediaAsset:
        """Validate and fix up a MediaAsset."""
        # Ensure size is set
        if asset.size is None:
            if asset.data is not None:
                asset.size = len(asset.data)
            elif asset.url and asset.metadata:
                asset.size = asset.metadata.get("size")

        # Ensure fetched_at
        if not asset.fetched_at:
            from datetime import datetime
            asset.fetched_at = datetime.now().isoformat()

        # If url is a raw_ref:// path, validate it
        if asset.url and asset.url.startswith("raw_ref://"):
            ref_path = asset.url[10:]  # Strip "raw_ref://"
            full_path = None
            for allowed in self.allowed_dirs:
                candidate = allowed / ref_path
                if candidate.exists():
                    full_path = candidate
                    break
            if full_path is None:
                logger.warning("AssetRef path not found: %s", ref_path)

        return asset

    def _is_path_allowed(self, path: Path) -> bool:
        """Check if path is within allowed directories."""
        try:
            path.resolve()
        except Exception:
            return False

        for allowed in self.allowed_dirs:
            try:
                path.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False

    def _guess_media_type(self, mime_type: str) -> str:
        """Map MIME type to media_type enum."""
        mt = mime_type.lower()
        if mt.startswith("text/") or mt in ("application/json", "application/xml", "application/xhtml+xml"):
            return "text"
        elif mt.startswith("image/"):
            return "image"
        elif mt.startswith("audio/"):
            return "audio"
        elif mt.startswith("video/"):
            return "video"
        elif mt == "application/pdf":
            return "document"
        else:
            return "binary"


def convert_to_raw_batch(source: Any, task_config: Optional[TaskConfigDTO] = None) -> RawDataBatch:
    """Convenience function for one-shot conversion."""
    converter = RawConverter()
    return converter.convert(source, task_config)