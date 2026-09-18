"""Progress Store Plugin.

Exports ProgressTracker current state as a snapshot file.
This is for export only - runtime progress management is handled by infra.progress.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

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
        """Initialize configuration."""
        self._context = context
        self._config = context.config_snapshot.get("plugins", {}).get("progress_store", {})

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        """Export progress snapshot.

        Args:
            request: StoreRequest with state_snapshot containing TaskRunState
            context: PluginContext with progress tracker

        Returns:
            StoreReceipt with export result
        """
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

            # Get progress data from state_snapshot or context.progress
            progress_data = self._get_progress_data(request, context)

            # Determine output path
            output_path = self._resolve_output_path(request)

            # Write snapshot atomically
            output_path.parent.mkdir(parents=True, exist_ok=True)
            from infra.storage.atomic_io import atomic_write_json
            atomic_write_json(output_path, progress_data)

            return StoreReceipt(
                target_id=request.target_id,
                written=1,
                skipped=0,
                failed=0,
                records_written=1,
                output_ref=str(output_path),
            )

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
                    retryable=True,
                ),
            )

    def _get_progress_data(self, request: StoreRequest, context: PluginContext) -> dict:
        """Get progress data from state_snapshot or context.progress."""
        # Priority 1: state_snapshot from request (TaskRunState)
        if request.state_snapshot:
            data = dict(request.state_snapshot)  # Copy to avoid modifying original
            data["exported_at"] = datetime.now().isoformat()
            return data

        # Priority 2: context.progress (ProgressTracker)
        if context.progress and hasattr(context.progress, "_read_raw"):
            data = context.progress._read_raw()
            data["exported_at"] = datetime.now().isoformat()
            return data

        # Priority 3: Empty structure
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
        """Resolve output file path."""
        output_dir = self._config.get("output_dir", "data/output")
        base = Path(output_dir)
        base.mkdir(parents=True, exist_ok=True)
        # Use run_id in filename for traceability
        return base / f"progress_{request.run_id[:8]}.json"

    def close(self) -> None:
        """Cleanup resources."""
        pass