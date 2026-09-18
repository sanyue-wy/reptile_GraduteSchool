"""Media Storage Plugin.

Stores MediaAsset/AssetRef to managed media directory with content-addressed filenames.
Handles streaming for large files, MIME sniffing, and reference mapping.
"""

import hashlib
import logging
import mimetypes
from pathlib import Path

from contracts.asset import AssetRef, MediaAsset
from contracts.result import StoreRequest, StoreReceipt, ErrorDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)
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
        self._ref_map = {}
        self._allowed_paths: list[str] = []

    def setup(self, context: PluginContext) -> None:
        self._context = context
        self._config = context.config_snapshot.get("plugins", {}).get("media_store", {})
        if context.storage and hasattr(context.storage, "workspace"):
            self._workspace = context.storage.workspace
        self._allowed_paths = context.allowed_paths or []

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        try:
            from infra.storage import check_and_reserve, commit as idem_commit

            # Idempotency check
            base_dir = self._workspace.base_dir if self._workspace else Path("data")
            cached = check_and_reserve(base_dir, request.run_id, request.idempotency_key)
            if cached is not None:
                return StoreReceipt(
                    target_id=cached.get("target_id", request.target_id),
                    written=0,
                    skipped=cached.get("records_written", 0),
                    failed=0,
                    records_written=0,
                    output_ref=cached.get("output_ref", ""),
                )

            assets = self._load_assets(request, context)

            if not assets:
                receipt = StoreReceipt(
                    target_id=request.target_id,
                    written=0,
                    skipped=0,
                    failed=0,
                    records_written=0,
                    output_ref="",
                )
            else:
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
                        diagnostics={"failed_count": failed, "errors": errors[:10]},
                    )

                receipt = StoreReceipt(
                    target_id=request.target_id,
                    written=written,
                    skipped=skipped,
                    failed=failed,
                    records_written=written,
                    output_ref=output_ref,
                    error=error_dto,
                )

            idem_commit(base_dir, request.run_id, request.idempotency_key, {
                "target_id": receipt.target_id,
                "records_written": receipt.records_written,
                "output_ref": receipt.output_ref,
            })

            return receipt

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
                ),
            )

    def _load_assets(self, request: StoreRequest, context: PluginContext) -> list[MediaAsset]:
        """Load media assets from data_refs.

        data_refs may point to JSON files containing serialized MediaAsset dicts.
        """
        from converters.storage_converter import records_from_data_refs
        raw = records_from_data_refs(request.data_refs)
        assets = []
        for item in raw:
            try:
                if isinstance(item, dict) and "media_type" in item and "mime_type" in item:
                    assets.append(MediaAsset.from_dict(item))
            except (ValueError, TypeError) as e:
                logger.warning("Skipping invalid asset: %s", e)
        return assets

    def _store_asset(self, asset: MediaAsset, run_id: str) -> str:
        content_hash = self._compute_hash(asset)
        if content_hash in self._ref_map:
            logger.debug("Asset already stored (dedup): %s", content_hash[:16])
            return "skipped"

        media_type = asset.media_type
        ext = self._guess_extension(asset.mime_type)
        filename = f"{content_hash[:16]}{ext}"

        if self._workspace:
            target_path = self._workspace.get_media_path(media_type, filename)
        else:
            output_dir = Path(self._config.get("output_dir", "data/media"))
            target_path = output_dir / media_type / filename

        # Path safety: verify target is within allowed directories
        self._validate_path_safe(target_path)

        target_path.parent.mkdir(parents=True, exist_ok=True)

        # Check if file already exists (by hash)
        if target_path.exists():
            existing_hash = self._file_hash(target_path)
            if existing_hash == content_hash:
                self._ref_map[content_hash] = target_path
                return "skipped"

        # Store asset
        max_inline = self._config.get("max_inline_size", 10 * 1024 * 1024)

        if asset.data is not None:
            if len(asset.data) > max_inline:
                self._stream_write(target_path, asset.data)
            else:
                from infra.storage.atomic_io import atomic_write_bytes
                atomic_write_bytes(target_path, asset.data)
        elif asset.url:
            logger.warning("URL-based asset storage not fully implemented: %s", asset.url)
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

        self._ref_map[content_hash] = target_path
        self._update_ref_mapping(run_id)

        return "written"

    def _validate_path_safe(self, target_path: Path) -> None:
        """Ensure target path is within allowed directories."""
        if self._allowed_paths:
            from infra.storage.workspace import resolve_safe_path
            resolve_safe_path(str(target_path), self._allowed_paths)

    def _compute_hash(self, asset: MediaAsset) -> str:
        if asset.sha256:
            return asset.sha256
        if asset.data:
            return hashlib.sha256(asset.data).hexdigest()
        return hashlib.sha256(asset.url.encode()).hexdigest()

    def _file_hash(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _stream_write(self, target_path: Path, data: bytes) -> None:
        """Stream write large data using atomic binary writer."""
        from infra.storage.atomic_io import atomic_write_bytes
        atomic_write_bytes(target_path, data)

    def _guess_extension(self, mime_type: str) -> str:
        ext = mimetypes.guess_extension(mime_type)
        if ext:
            return ext
        type_map = {
            "image": ".bin", "audio": ".bin", "video": ".bin",
            "document": ".pdf", "text": ".txt", "binary": ".bin",
        }
        return type_map.get(mime_type.split("/")[0], ".bin")

    def _write_ref_file(self, target_path: Path, ref: AssetRef) -> None:
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
        if not self._workspace:
            return
        mapping_path = self._workspace.media_dir / "ref_mapping.json"
        from infra.storage.atomic_io import atomic_write_json
        mapping = {}
        for hash_val, path in self._ref_map.items():
            rel_path = path.relative_to(self._workspace.media_dir)
            mapping[hash_val] = str(rel_path)
        atomic_write_json(mapping_path, mapping)

    def close(self) -> None:
        pass