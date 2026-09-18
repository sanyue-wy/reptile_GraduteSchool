"""JSONL Storage Plugin.

Wraps storage/jsonl_store.py functionality with V3.0 plugin interface.
Supports legacy_education_v1 and generic_record formats.
"""

import json
import logging
from pathlib import Path
from typing import Any

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

    def setup(self, context: PluginContext) -> None:
        """Initialize workspace reference and config."""
        self._context = context
        # Read config from context.config_snapshot
        plugin_config = context.config_snapshot.get("plugins", {}).get("jsonl_store", {})
        self._config = plugin_config
        # Get workspace from context.storage if available
        if context.storage and hasattr(context.storage, "workspace"):
            self._workspace = context.storage.workspace

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        """Execute JSONL storage.

        Args:
            request: StoreRequest with dataset, run_id, target_id, format_id, data_refs
            context: PluginContext with storage workspace

        Returns:
            StoreReceipt with written/skipped/failed counts and output_ref
        """
        try:
            # Determine output path
            output_path = self._resolve_output_path(request, context)

            # Read data from references (simplified - in real impl, would fetch from data_refs)
            # For now, assume data_refs contains the actual records or we load from a known location
            records = self._load_records(request, context)

            # Write based on format
            format_id = request.format_id
            if format_id == "legacy_education_v1":
                written = self._write_legacy_format(records, output_path)
            elif format_id == "generic_record":
                written = self._write_generic_format(records, output_path)
            else:
                raise ValueError(f"Unknown format_id: {format_id}")

            return StoreReceipt(
                target_id=request.target_id,
                written=written,
                skipped=0,
                failed=0,
                records_written=written,
                output_ref=str(output_path),
            )

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
                    retryable=True,
                ),
            )

    def _resolve_output_path(self, request: StoreRequest, context: PluginContext) -> Path:
        """Resolve output file path based on request and context."""
        # Check for output_dir in config
        config = getattr(self, "_config", {})
        output_dir = config.get("output_dir")

        if output_dir:
            base = Path(output_dir)
        elif self._workspace:
            base = self._workspace.get_store_path(request.target_id, ".jsonl").parent
        else:
            # Fallback to default location
            base = Path("data/output")

        base.mkdir(parents=True, exist_ok=True)
        return base / f"{request.target_id}.jsonl"

    def _load_records(self, request: StoreRequest, context: PluginContext) -> list[dict]:
        """Load records from data_refs or context.

        In a real implementation, this would fetch data from the references
        (which could be paths to RecordBatch files, in-memory data, etc.)
        For now, we return empty list - the actual data flow is handled by the pipeline.
        """
        # This is a placeholder - actual data loading would be implemented
        # when integrated with the pipeline's storage_converter
        return []

    def _write_legacy_format(self, records: list[dict], output_path: Path) -> int:
        """Write records in legacy education format (compatible with V2.2 output).

        Groups by university_college and writes separate JSONL files.
        """
        if not records:
            # Create empty file for idempotency
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("", encoding="utf-8")
            return 0

        # Group by university and college
        groups: dict[str, list[dict]] = {}
        for rec in records:
            key = f"{rec.get('university', '未知')}_{rec.get('college', '未知')}"
            groups.setdefault(key, []).append(rec)

        total_written = 0
        for key, group_records in groups.items():
            safe_key = key.replace("/", "_").replace("\\", "_")
            group_path = output_path.parent / f"{safe_key}.jsonl"

            # Atomic write
            from infra.storage.atomic_io import atomic_writer
            with atomic_writer(group_path) as stream:
                for record in group_records:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")

            total_written += len(group_records)
            logger.info("Wrote %d records to %s", len(group_records), group_path)

        return total_written

    def _write_generic_format(self, records: list[dict], output_path: Path) -> int:
        """Write records in generic format (full NormalizedRecordDTO fields)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        from infra.storage.atomic_io import atomic_writer
        with atomic_writer(output_path) as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

        logger.info("Wrote %d records to %s", len(records), output_path)
        return len(records)

    def close(self) -> None:
        """Cleanup resources."""
        pass