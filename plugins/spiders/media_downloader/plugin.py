# -*- coding: utf-8 -*-
"""
Media Downloader Spider Plugin
==============================
NEW example plugin for controlled direct media URL downloads.

Downloads images/audio/video/binary directly as MediaAsset with:
- Size limits (default 10 MiB, oversized streamed to disk as AssetRef)
- MIME type sniffing via Content-Type header
- URL domain whitelist checking
- Streaming download to avoid loading entire file into memory

This is the first consumer of the multimedia contract and serves as
reference implementation for future media spider plugins.
"""

import hashlib
import logging
import mimetypes
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from plugins.base import PluginContext
from plugins.spiders import (
    SpiderPlugin, make_error,
    ERROR_HTTP_BLOCKED, ERROR_HTTP_TIMEOUT, ERROR_PIPELINE_CANCELLED,
    ERROR_PLUGIN_EXECUTE_FAILED,
)
from utils.http import BlockedError

logger = logging.getLogger(__name__)

DEFAULT_MAX_SIZE = 10 * 1024 * 1024  # 10 MiB

MIME_TO_MEDIA_TYPE = {
    "image/": "image",
    "audio/": "audio",
    "video/": "video",
    "application/pdf": "document",
    "application/": "binary",
}


class MediaDownloaderSpiderPlugin(SpiderPlugin):
    """Spider plugin for controlled direct media URL downloads.

    Input: TaskConfigDTO with config_snapshot containing urls[], max_size_mb, allowed_domains, allowed_mime_types.
    Output: RawDataBatch containing RawDataDTO items with MediaAsset (in-memory or url for large files).
    """

    name = "media_downloader"
    version = "1.0.0"

    def execute(self, task_config: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        session = context.http
        cancel_token = context.cancel_token

        if not session:
            raise RuntimeError("PoliteSession not injected via context")

        cfg = task_config.config_snapshot
        urls = cfg.get("urls", [])
        max_size_mb = cfg.get("max_size_mb", 10)
        allowed_domains = cfg.get("allowed_domains", [])
        allowed_mime_types = cfg.get("allowed_mime_types", ["image/*", "audio/*", "video/*", "application/pdf", "application/octet-stream"])

        if not urls:
            raise ValueError("urls array is required in config_snapshot")

        max_size = max_size_mb * 1024 * 1024
        allowed_mime_prefixes = [mt.replace("*", "") for mt in allowed_mime_types]

        items: list[RawDataDTO] = []
        errors: list[dict] = []

        # Determine allowed output directory for large files
        output_dir = None
        if context.allowed_paths:
            output_dir = Path(context.allowed_paths[0]) / "media"
            output_dir.mkdir(parents=True, exist_ok=True)

        for idx, url in enumerate(urls):
            if cancel_token and cancel_token.is_set():
                errors.append(make_error(
                    ERROR_PIPELINE_CANCELLED,
                    "Crawl cancelled by user",
                    task_id=task_config.task_id,
                    source_id=task_config.source_id,
                ))
                break

            if allowed_domains:
                parsed = urlparse(url)
                if parsed.netloc not in allowed_domains:
                    errors.append(make_error(
                        ERROR_PLUGIN_EXECUTE_FAILED,
                        f"Domain {parsed.netloc} not in allowed list",
                        task_id=task_config.task_id,
                        source_id=task_config.source_id,
                        retryable=False,
                        diagnostics={"url": url, "domain": parsed.netloc},
                    ))
                    continue

            dto, error = self._download_media(url, task_config, f"media_{idx}", session, max_size, allowed_mime_prefixes, output_dir)
            if error:
                errors.append(error)
                continue
            if dto:
                items.append(dto)

        return RawDataBatch(
            schema_version="1",
            task_id=task_config.task_id,
            items=items,
            pagination_complete=True,
            errors=errors,
        )

    def _download_media(self, url, task_config, trace_label, session, max_size, allowed_mime_prefixes, output_dir):
        try:
            def _do_fetch():
                return session.get(url, stream=True, timeout=60)

            resp = _do_fetch()

            content_length = resp.headers.get("Content-Length")
            if content_length:
                try:
                    cl = int(content_length)
                    if cl > max_size:
                        return self._stream_to_disk(resp, url, task_config, trace_label, max_size, allowed_mime_prefixes, output_dir)
                except ValueError:
                    pass

            content_type = resp.headers.get("Content-Type", "")
            if not content_type:
                content_type = mimetypes.guess_type(url)[0] or "application/octet-stream"

            if not self._is_mime_allowed(content_type, allowed_mime_prefixes):
                resp.close()
                return None, make_error(
                    ERROR_PLUGIN_EXECUTE_FAILED,
                    f"MIME type {content_type} not allowed",
                    task_id=task_config.task_id,
                    source_id=task_config.source_id,
                    retryable=False,
                    diagnostics={"url": url, "mime": content_type},
                )

            chunks = []
            total_size = 0
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    total_size += len(chunk)
                    if total_size > max_size:
                        return self._stream_remainder(resp, chunks, url, task_config, trace_label, max_size, output_dir, content_type)
                    chunks.append(chunk)

            resp.close()
            data = b"".join(chunks)
            media_type = self._guess_media_type(content_type)

            asset = MediaAsset(
                media_type=media_type,
                mime_type=content_type,
                data=data,
                metadata={"source_url": url, "trace_label": trace_label, "downloaded_size": len(data)},
            )
            return RawDataDTO(
                source_id=task_config.source_id,
                url=url,
                content_type=content_type,
                encoding="binary",
                fetched_at=datetime.now().isoformat(),
                trace={"trace_label": trace_label, "task_id": task_config.task_id, "downloaded_size": len(data)},
                assets=[asset],
            ), None

        except BlockedError as e:
            return None, make_error(ERROR_HTTP_BLOCKED, str(e), task_id=task_config.task_id, source_id=task_config.source_id)
        except Exception as e:
            logger.exception("Media download failed for %s", url)
            code = ERROR_HTTP_TIMEOUT if "timeout" in str(e).lower() else ERROR_PLUGIN_EXECUTE_FAILED
            return None, make_error(code, str(e), task_id=task_config.task_id, source_id=task_config.source_id)

    def _stream_to_disk(self, resp, url, task_config, trace_label, max_size, allowed_mime_prefixes, output_dir):
        """Stream an oversized response to disk, returning a url-referenced MediaAsset."""
        content_type = resp.headers.get("Content-Type", "") or mimetypes.guess_type(url)[0] or "application/octet-stream"

        if not self._is_mime_allowed(content_type, allowed_mime_prefixes):
            resp.close()
            return None, make_error(
                ERROR_PLUGIN_EXECUTE_FAILED,
                f"MIME type {content_type} not allowed",
                task_id=task_config.task_id,
                source_id=task_config.source_id,
                retryable=False,
                diagnostics={"url": url, "mime": content_type},
            )

        media_type = self._guess_media_type(content_type)

        if output_dir is None:
            # No output dir available — fall back to error
            resp.close()
            return None, make_error(
                ERROR_PLUGIN_EXECUTE_FAILED,
                f"File exceeds {max_size} bytes and no output directory available for streaming",
                task_id=task_config.task_id,
                source_id=task_config.source_id,
                retryable=False,
                diagnostics={"url": url, "limit": max_size},
            )

        # Stream to temp file, then atomic move
        sha256_hash = hashlib.sha256()
        total_size = 0
        fd, tmp_path = tempfile.mkstemp(dir=str(output_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        sha256_hash.update(chunk)
                        total_size += len(chunk)
            resp.close()

            # Determine final filename from URL
            parsed = urlparse(url)
            base_name = Path(parsed.path).name or "media"
            final_path = output_dir / f"{sha256_hash.hexdigest()[:16]}_{base_name}"
            os.replace(tmp_path, str(final_path))
            tmp_path = None  # prevent cleanup

            asset = MediaAsset(
                media_type=media_type,
                mime_type=content_type,
                url=str(final_path),
                size=total_size,
                sha256=sha256_hash.hexdigest(),
                metadata={"source_url": url, "trace_label": trace_label, "streamed_to_disk": True},
            )
            return RawDataDTO(
                source_id=task_config.source_id,
                url=url,
                content_type=content_type,
                encoding="binary",
                fetched_at=datetime.now().isoformat(),
                trace={"trace_label": trace_label, "task_id": task_config.task_id, "streamed_to_disk": True, "size": total_size},
                assets=[asset],
            ), None

        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _stream_remainder(self, resp, chunks_so_far, url, task_config, trace_label, max_size, output_dir, content_type):
        """Already exceeded limit mid-stream — flush accumulated + remainder to disk."""
        media_type = self._guess_media_type(content_type)

        if output_dir is None:
            resp.close()
            return None, make_error(
                ERROR_PLUGIN_EXECUTE_FAILED,
                f"File exceeds {max_size} bytes and no output directory available",
                task_id=task_config.task_id,
                source_id=task_config.source_id,
                retryable=False,
                diagnostics={"url": url, "limit": max_size},
            )

        sha256_hash = hashlib.sha256()
        total_size = 0
        fd, tmp_path = tempfile.mkstemp(dir=str(output_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                for chunk in chunks_so_far:
                    f.write(chunk)
                    sha256_hash.update(chunk)
                    total_size += len(chunk)
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        sha256_hash.update(chunk)
                        total_size += len(chunk)
            resp.close()

            parsed = urlparse(url)
            base_name = Path(parsed.path).name or "media"
            final_path = output_dir / f"{sha256_hash.hexdigest()[:16]}_{base_name}"
            os.replace(tmp_path, str(final_path))
            tmp_path = None

            asset = MediaAsset(
                media_type=media_type,
                mime_type=content_type,
                url=str(final_path),
                size=total_size,
                sha256=sha256_hash.hexdigest(),
                metadata={"source_url": url, "trace_label": trace_label, "streamed_to_disk": True},
            )
            return RawDataDTO(
                source_id=task_config.source_id,
                url=url,
                content_type=content_type,
                encoding="binary",
                fetched_at=datetime.now().isoformat(),
                trace={"trace_label": trace_label, "task_id": task_config.task_id, "streamed_to_disk": True, "size": total_size},
                assets=[asset],
            ), None

        finally:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    def _is_mime_allowed(self, content_type, allowed_prefixes):
        ct = content_type.lower()
        for prefix in allowed_prefixes:
            if ct.startswith(prefix.lower()):
                return True
        return False

    def _guess_media_type(self, content_type):
        ct = content_type.lower()
        for prefix, media_type in MIME_TO_MEDIA_TYPE.items():
            if ct.startswith(prefix):
                return media_type
        return "binary"
