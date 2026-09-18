"""CSV Presenter Plugin.

Renders PresentationRequest records as CSV (Comma-Separated Values) output.
Supports column selection via OutputSpec.field_selection.
"""

import csv
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4
from datetime import datetime

from contracts.output import PresentationRequest, RenderedOutputDTO
from plugins.base import PresenterPlugin, PluginContext

logger = logging.getLogger(__name__)


class CsvPresenterPlugin(PresenterPlugin):
    """Presenter plugin that outputs records in CSV format.

    Supports column selection via OutputSpec.field_selection (whitelist of field names).
    Writes standard CSV with headers as the first row.
    """

    name = "csv_presenter"
    version = "1.0.0"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def __init__(self):
        super().__init__()
        self._config: dict[str, Any] = {}
        self._workspace: Path | None = None

    def setup(self, context: PluginContext) -> None:
        """Initialize presenter with context and configuration."""
        plugin_config = context.config_snapshot.get("plugins", {}).get("csv_presenter", {})
        self._config = plugin_config

        if context.storage and hasattr(context.storage, "workspace"):
            self._workspace = context.storage.workspace
        logger.info("CSV presenter initialized with config: %s", self._config)

    def render(self, request: PresentationRequest, context: PluginContext) -> RenderedOutputDTO | str:
        """Render records to CSV file.

        Args:
            request: PresentationRequest containing records and output_spec
            context: PluginContext with workspace and allowed paths

        Returns:
            RenderedOutputDTO with path to generated CSV file
        """
        # Resolve output path
        output_path = self._resolve_output_path(request, context)

        # Prepare records with column selection
        records, fieldnames = self._prepare_records(request)

        # Write CSV
        written = self._write_csv(records, fieldnames, output_path, request)

        logger.info("CSV presenter wrote %d records to %s", written, output_path)

        return RenderedOutputDTO(
            output_id=uuid4().hex,
            output_format="csv",
            path=str(output_path),
            metadata={
                "record_count": written,
                "field_count": len(fieldnames),
                "fields": fieldnames,
                "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
            },
        )

    def _resolve_output_path(self, request: PresentationRequest, context: PluginContext) -> Path:
        """Resolve output file path based on request and context."""
        output_dir = self._config.get("output_dir")

        if output_dir:
            base = Path(output_dir)
        elif self._workspace:
            base = self._workspace.get_store_path(request.dataset, ".csv").parent
        else:
            base = Path("data/output/presenter")

        base.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{request.dataset}_{timestamp}.csv"
        return base / filename

    def _prepare_records(self, request: PresentationRequest) -> tuple[list[dict], list[str]]:
        """Prepare records for CSV output based on output_spec.field_selection.

        Args:
            request: PresentationRequest with records and output_spec

        Returns:
            Tuple of (filtered_records, fieldnames)
        """
        records = request.records
        output_spec = request.output_spec or {}

        # Get field selection from output_spec
        field_selection = output_spec.get("field_selection")

        if not records:
            return [], []

        # If field_selection is specified, use it as whitelist
        if field_selection and isinstance(field_selection, list):
            fieldnames = [f for f in field_selection if f]
            # Filter records to only include selected fields
            filtered = []
            for rec in records:
                filtered_rec = {k: v for k, v in rec.items() if k in fieldnames}
                filtered.append(filtered_rec)
            return filtered, fieldnames

        # Otherwise, use all fields from first record (preserving order)
        fieldnames = list(records[0].keys()) if records else []
        return records, fieldnames

    def _write_csv(
        self,
        records: list[dict],
        fieldnames: list[str],
        output_path: Path,
        request: PresentationRequest,
    ) -> int:
        """Write records to CSV file using atomic I/O.

        Args:
            records: List of record dictionaries
            fieldnames: Ordered list of column names
            output_path: Target file path
            request: Original request for metadata

        Returns:
            Number of records written
        """
        from infra.storage.atomic_io import atomic_writer

        output_path.parent.mkdir(parents=True, exist_ok=True)

        written = 0
        with atomic_writer(output_path) as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for record in records:
                # Convert all values to strings for CSV
                row = {k: self._csv_value(v) for k, v in record.items()}
                writer.writerow(row)
                written += 1

        return written

    def _csv_value(self, value: Any) -> str:
        """Convert a value to CSV-safe string."""
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            import json
            return json.dumps(value, ensure_ascii=False)
        if hasattr(value, "isoformat"):  # datetime/date
            return value.isoformat()
        return str(value)

    def close(self) -> None:
        """Cleanup resources."""
        pass