"""JSONL Presenter Plugin.

Renders PresentationRequest records as JSONL (JSON Lines) output.
Shares serialization logic with jsonl_store for consistency.
"""

import json
import logging
from pathlib import Path
from typing import Any

from contracts.output import PresentationRequest, RenderedOutputDTO
from plugins.base import PresenterPlugin, PluginContext
from uuid import uuid4
from datetime import datetime

logger = logging.getLogger(__name__)


class JsonlPresenterPlugin(PresenterPlugin):
    """Presenter plugin that outputs records in JSONL format.

    Each record is written as a single JSON line.
    Supports both full records and simplified views based on output_spec.
    """

    name = "jsonl_presenter"
    version = "1.0.0"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def __init__(self):
        super().__init__()
        self._context: PluginContext | None = None
        self._config: dict[str, Any] = {}

    def setup(self, context: PluginContext) -> None:
        """Initialize presenter with context and configuration."""
        self._context = context
        plugin_config = context.config_snapshot.get("plugins", {}).get("jsonl_presenter", {})
        self._config = plugin_config
        logger.info("JSONL presenter initialized with config: %s", self._config)

    def render(self, request: PresentationRequest, context: PluginContext) -> str:
        """Render records to JSONL file.

        Args:
            request: PresentationRequest containing records and metadata
            context: PluginContext with workspace and allowed paths

        Returns:
            Absolute path to the generated JSONL file
        """
        # Determine output path
        output_path = self._resolve_output_path(request, context)

        # Get records to output
        records = self._prepare_records(request)

        # Write JSONL
        written = self._write_jsonl(records, output_path, request)

        logger.info("JSONL presenter wrote %d records to %s", written, output_path)
        return str(output_path)

    def _resolve_output_path(self, request: PresentationRequest, context: PluginContext) -> Path:
        """Resolve output file path based on request and context."""
        config = getattr(self, "_config", {})
        output_dir = config.get("output_dir")

        if output_dir:
            base = Path(output_dir)
        elif context.storage and hasattr(context.storage, "workspace"):
            base = context.storage.workspace.get_store_path("jsonl_presenter", ".jsonl").parent
        else:
            # Fallback to default location
            base = Path("data/output/present")

        base.mkdir(parents=True, exist_ok=True)

        # Include dataset and timestamp in filename for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{request.dataset}_{timestamp}.jsonl"
        return base / filename

    def _prepare_records(self, request: PresentationRequest) -> list[dict]:
        """Prepare records for output based on output_spec.

        Args:
            request: PresentationRequest with records and output_spec

        Returns:
            List of record dictionaries ready for JSONL serialization
        """
        records = request.records
        output_spec = request.output_spec or {}

        # If fields are specified in output_spec, filter records
        include_fields = output_spec.get("include_fields")
        if include_fields:
            filtered = []
            for rec in records:
                filtered_rec = {k: v for k, v in rec.items() if k in include_fields}
                filtered.append(filtered_rec)
            return filtered

        # If exclude_fields specified, remove those
        exclude_fields = output_spec.get("exclude_fields")
        if exclude_fields:
            filtered = []
            for rec in records:
                filtered_rec = {k: v for k, v in rec.items() if k not in exclude_fields}
                filtered.append(filtered_rec)
            return filtered

        # Return as-is
        return records

    def _write_jsonl(self, records: list[dict], output_path: Path, request: PresentationRequest) -> int:
        """Write records to JSONL file using atomic I/O.

        Args:
            records: List of record dictionaries
            output_path: Target file path
            request: Original request for metadata

        Returns:
            Number of records written
        """
        from infra.storage.atomic_io import atomic_writer

        output_path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        with atomic_writer(output_path) as stream:
            for record in records:
                # Ensure record is JSON serializable
                line = json.dumps(record, ensure_ascii=False, default=self._json_default)
                stream.write(line + "\n")
                written += 1

        return written

    def _json_default(self, obj: Any) -> Any:
        """JSON serializer for non-standard types."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    def close(self) -> None:
        """Cleanup resources."""
        pass