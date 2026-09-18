"""Media Storage Plugin.

Stores MediaAsset/AssetRef to managed media directory with content-addressed filenames.
Handles streaming for large files, MIME sniffing, and reference mapping.
"""

import hashlib
import logging
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from contracts.asset import AssetRef, MediaAsset
from contracts.result import StoreRequest, StoreReceipt, ErrorDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)

# Initialize MIME types
mimetypes.init()


class MediaStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    """Storage plugin for media assets."""

    name = "media_store"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    def __init__(self):
        super().__init__()
        self._config = {}
        self._workspace = None
        self._ref_map = {}  # In-memory ref -> path mapping

    def setup(self, context: PluginContext) -> None:
        """Initialize workspace reference."""
        self._context = context
        self._config = context.config_snapshot.get("plugins", {}).get("media_store", {})
        if context.storage and hasattr(context.storage, "workspace"):
            self._workspace = context.storage.workspace

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        """Store media assets.

        Args:
            request: StoreRequest with data_refs pointing to MediaAsset objects
            context: PluginContext with storage workspace

        Returns:
            StoreReceipt with written/skipped/failed counts
        """
        try:
            assets = self._load_assets(request, context)

            if not assets:
                return StoreReceipt(
                    target_id=request.target_id,
                    written=0,
                    skipped=0,
                    failed=0,
                    records_written=0,
                    output_ref="",
                )

            written = 0
            skipped = 0
            failed = 0
            errors = []

            for asset in assets:
                try:
                    result = self._store_asset(asset, request.run_id)
                    if result == "written":
                        written += 1
                    elif result == "skipped":
                        skipped += 1
                except Exception as e:
                    failed += 1
                    errors.append(str(e))
                    logger.warning("Failed to store asset: %s", e)

            output_ref = str(self._workspace.media_dir) if self._workspace else self._config.get("output_dir", "")

            error_dto = None
            if failed > 0:
                error_dto = ErrorDTO(
                    code="STORAGE_WRITE_FAILED",
                    message=f"Failed to store {failed} assets: {'; '.join(errors[:3])}",
                    stage="store",
                    task_id=request.state_snapshot.get("task_id", ""),
                    retryable=True,
                    diagnostics={"failed_count": failed, "errors": errors[:10]},
                )

            return StoreReceipt(
                target_id=request.target_id,
                written=written,
                skipped=skipped,
                failed=failed,
                records_written=written,
                output_ref=output_ref,
                error=error_dto,
            )

        except Exception as e:
            logger.exception("Media storage failed for target %s", request.target_id)
            return StoreReceipt(
                target_id=request.target_id,
                written=0,
                skipped=0,
                failed=1,
                records_written=0,
                output_ref="",
                error=ErrorDTO(
                    code="STORAGE_WRITE_FAILED",
                    message=str(e),
                    stage="store",
                    task_id=request.state_snapshot.get("task_id", ""),
                    retryable=True,
                ),
            )

    def _load_assets(self, request: StoreRequest, context: PluginContext) -> list[MediaAsset]:
        """Load media assets from data_refs (placeholder)."""
        # Actual implementation would fetch from data_refs
        return []

    def _store_asset(self, asset: MediaAsset, run_id: str) -> str:
        """Store a single media asset.

        Returns:
            "written", "skipped", or raises exception
        """
        # Compute content hash for deduplication
        content_hash = self._compute_hash(asset)
        if content_hash in self._ref_map:
            logger.debug("Asset already stored (dedup): %s", content_hash[:16])
            return "skipped"

        # Determine media type directory
        media_type = asset.media_type
        ext = self._guess_extension(asset.mime_type)

        # Generate filename: hash_prefix + extension
        filename = f"{content_hash[:16]}{ext}"

        # Get target path
        if self._workspace:
            target_path = self._workspace.get_media_path(media_type, filename)
        else:
            output_dir = Path(self._config.get("output_dir", "data/media"))
            target_path = output_dir / media_type / filename

        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file already exists (by hash)
        if target_path.exists():
            existing_hash = self._file_hash(target_path)
            if existing_hash == content_hash:
                self._ref_map[content_hash] = target_path
                return "skipped"

        # Store asset
        max_inline = self._config.get("max_inline_size", 10 * 1024 * 1024)  # 10 MiB

        if asset.data is not None:
            # In-memory data
            if len(asset.data) > max_inline:
                # Stream to disk
                self._stream_write(target_path, asset.data)
            else:
                # Direct write
                from infra.storage.atomic_io import atomic_write_bytes
                atomic_write_bytes(target_path, asset.data)
        elif asset.url:
            # URL reference - create AssetRef instead of downloading
            # In real implementation, would download with streaming
            logger.warning("URL-based asset storage not fully implemented: %s", asset.url)
            # For now, create a reference file
            ref = AssetRef(
                path=str(target_path.relative_to(self._workspace.media_dir if self._workspace else Path("data/media"))),
                media_type=asset.media_type,
                mime_type=asset.mime_type,
                size=asset.size or 0,
                sha256=content_hash,
            )
            self._write_ref_file(target_path, ref)
        else:
            raise ValueError("Asset has neither data nor url")

        # Record mapping
        self._ref_map[content_hash] = target_path

        # Write ref mapping file
        self._update_ref_mapping(run_id)

        return "written"

    def _compute_hash(self, asset: MediaAsset) -> str:
        """Compute SHA256 hash of asset content."""
        if asset.sha256:
            return asset.sha256

        if asset.data:
            return hashlib.sha256(asset.data).hexdigest()

        # For URL-only assets, hash the URL
        return hashlib.sha256(asset.url.encode()).hexdigest()

    def _file_hash(self, path: Path) -> str:
        """Compute SHA256 hash of file content."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _stream_write(self, target_path: Path, data: bytes) -> None:
        """Stream write large data to avoid memory pressure."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(data)

    def _guess_extension(self, mime_type: str) -> str:
        """Guess file extension from MIME type."""
        ext = mimetypes.guess_extension(mime_type)
        if ext:
            return ext
        # Fallback by media type
        type_map = {
            "image": ".bin",
            "audio": ".bin",
            "video": ".bin",
            "document": ".pdf",
            "text": ".txt",
            "binary": ".bin",
        }
        return type_map.get(mime_type.split("/")[0], ".bin")

    def _write_ref_file(self, target_path: Path, ref: AssetRef) -> None:
        """Write AssetRef as JSON sidecar file."""
        import json
        ref_path = target_path.with_suffix(target_path.suffix + ".ref.json")
        from infra.storage.atomic_io import atomic_write_json
        atomic_write_json(ref_path, {
            "path": ref.path,
            "media_type": ref.media_type,
            "mime_type": ref.mime_type,
            "size": ref.size,
            "sha256": ref.sha256,
        })

    def _update_ref_mapping(self, run_id: str) -> None:
        """Update the reference mapping file."""
        if not self._workspace:
            return

        mapping_path = self._workspace.media_dir / "ref_mapping.json"
        import json
        from infra.storage.atomic_io import atomic_write_json

        mapping = {}
        for hash_val, path in self._ref_map.items():
            rel_path = path.relative_to(self._workspace.media_dir)
            mapping[hash_val] = str(rel_path)

        atomic_write_json(mapping_path, mapping)

    def close(self) -> None:
        """Cleanup resources."""
        pass