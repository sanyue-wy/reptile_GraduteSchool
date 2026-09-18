"""Progress Store Plugin.

Exports ProgressTracker current state as a snapshot file.
This is for export only - runtime progress management is handled by infra.progress.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from contracts.result import StoreRequest, StoreReceipt, ErrorDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


class ProgressStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    """Storage plugin for progress snapshot export."""

    name = "progress_store"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    def __init__(self):
        super().__init__()
        self._config = {}

    def setup(self, context: PluginContext) -> None:
        self._context = context
        self._config = context.config_snapshot.get("plugins", {}).get("progress_store", {})

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        try:
            if not self._config.get("enabled", True):
                return StoreReceipt(
                    target_id=request.target_id,
                    written=0,
                    skipped=1,
                    failed=0,
                    records_written=0,
                    output_ref="disabled",
                )

            from infra.storage import check_and_reserve, commit as idem_commit

            # Idempotency check
            base_dir = Path("data")
            if context.storage and hasattr(context.storage, "workspace"):
                base_dir = context.storage.workspace.base_dir
            cached = check_and_reserve(base_dir, request.run_id, request.idempotency_key)
            if cached is not None:
                return StoreReceipt(
                    target_id=cached.get("target_id", request.target_id),
                    written=0,
                    skipped=1,
                    failed=0,
                    records_written=0,
                    output_ref=cached.get("output_ref", ""),
                )

            progress_data = self._get_progress_data(request, context)
            output_path = self._resolve_output_path(request)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            from infra.storage.atomic_io import atomic_write_json
            atomic_write_json(output_path, progress_data)

            receipt = StoreReceipt(
                target_id=request.target_id,
                written=1,
                skipped=0,
                failed=0,
                records_written=1,
                output_ref=str(output_path),
            )

            idem_commit(base_dir, request.run_id, request.idempotency_key, {
                "target_id": receipt.target_id,
                "records_written": receipt.records_written,
                "output_ref": receipt.output_ref,
            })

            return receipt

        except Exception as e:
            logger.exception("Progress snapshot export failed for target %s", request.target_id)
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

    def _get_progress_data(self, request: StoreRequest, context: PluginContext) -> dict:
        if request.state_snapshot:
            data = dict(request.state_snapshot)
            data["exported_at"] = datetime.now().isoformat()
            return data

        if context.progress and hasattr(context.progress, "_read_raw"):
            data = context.progress._read_raw()
            data["exported_at"] = datetime.now().isoformat()
            return data

        return {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "exported_at": datetime.now().isoformat(),
            "schools": {},
            "pipelines": {
                "source_a": {"completed": 0, "total": 147},
                "source_b": {"completed": 0, "total": 147},
                "merged": {"completed": 0, "total": 147},
            },
            "source_breakdown": {
                "matched": 0,
                "notice_only": 0,
                "faculty_only": 0,
                "unmatched": 0,
            },
        }

    def _resolve_output_path(self, request: StoreRequest) -> Path:
        output_dir = self._config.get("output_dir", "data/output")
        base = Path(output_dir)
        base.mkdir(parents=True, exist_ok=True)
        return base / f"progress_{request.run_id[:8]}.json"

    def close(self) -> None:
        pass