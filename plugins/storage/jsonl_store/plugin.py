"""JSONL Storage Plugin.

Wraps storage/jsonl_store.py functionality with V3.0 plugin interface.
Supports legacy_education_v1 and generic_record formats.
"""

import json
import logging
from pathlib import Path

from contracts.result import StoreRequest, StoreReceipt, ErrorDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


class JsonlStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    """Storage plugin for JSONL output."""

    name = "jsonl_store"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    def __init__(self):
        super().__init__()
        self._workspace = None
        self._config = {}

    def setup(self, context: PluginContext) -> None:
        self._context = context
        self._config = context.config_snapshot.get("plugins", {}).get("jsonl_store", {})
        if context.storage and hasattr(context.storage, "workspace"):
            self._workspace = context.storage.workspace

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        try:
            from infra.storage import check_and_reserve, commit as idem_commit
            from converters.storage_converter import (
                records_from_data_refs, records_to_legacy_format,
            )
            from infra.storage.atomic_io import atomic_writer, path_lock

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

            output_path = self._resolve_output_path(request, context)
            raw_records = records_from_data_refs(request.data_refs)

            if request.format_id == "legacy_education_v1":
                records = records_to_legacy_format(raw_records)
                written = self._write_legacy_format(records, output_path)
            elif request.format_id == "generic_record":
                written = self._write_generic_format(raw_records, output_path)
            else:
                raise ValueError(f"Unknown format_id: {request.format_id}")

            receipt = StoreReceipt(
                target_id=request.target_id,
                written=written,
                skipped=0,
                failed=0,
                records_written=written,
                output_ref=str(output_path),
            )

            # Commit idempotency key
            idem_commit(base_dir, request.run_id, request.idempotency_key, {
                "target_id": receipt.target_id,
                "records_written": receipt.records_written,
                "output_ref": receipt.output_ref,
            })

            return receipt

        except Exception as e:
            logger.exception("JSONL storage failed for target %s", request.target_id)
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

    def _resolve_output_path(self, request: StoreRequest, context: PluginContext) -> Path:
        output_dir = self._config.get("output_dir")
        if output_dir:
            base = Path(output_dir)
        elif self._workspace:
            base = self._workspace.get_store_path(request.target_id, ".jsonl").parent
        else:
            base = Path("data/output")
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{request.target_id}.jsonl"

    def _write_legacy_format(self, records: list[dict], output_path: Path) -> int:
        """Write records in legacy education format (compatible with V2.2 output)."""
        if not records:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            from infra.storage.atomic_io import atomic_write_bytes
            atomic_write_bytes(output_path, b"")
            return 0

        groups: dict[str, list[dict]] = {}
        for rec in records:
            key = f"{rec.get('university', '未知')}_{rec.get('college', '未知')}"
            groups.setdefault(key, []).append(rec)

        total_written = 0
        for key, group_records in groups.items():
            safe_key = key.replace("/", "_").replace("\\", "_")
            group_path = output_path.parent / f"{safe_key}.jsonl"
            from infra.storage.atomic_io import atomic_writer
            with atomic_writer(group_path) as stream:
                for record in group_records:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            total_written += len(group_records)
            logger.info("Wrote %d records to %s", len(group_records), group_path)

        return total_written

    def _write_generic_format(self, records: list[dict], output_path: Path) -> int:
        """Write records in generic format (full NormalizedRecordDTO fields)."""
        from infra.storage.atomic_io import atomic_writer
        with atomic_writer(output_path) as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("Wrote %d records to %s", len(records), output_path)
        return len(records)

    def close(self) -> None:
        pass