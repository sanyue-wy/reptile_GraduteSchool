"""XLSX Storage Plugin.

Wraps Excel export functionality with V3.0 plugin interface.
"""

import logging
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from contracts.result import StoreRequest, StoreReceipt, ErrorDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


class XlsxStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    """Storage plugin for XLSX output."""

    name = "xlsx_store"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    # Column definitions matching V2.2 export
    HEADERS = ["学校", "学院", "姓名", "职称", "招生状态", "招生方向", "研究方向", "来源链接"]
    COLUMN_WIDTHS = [18, 18, 12, 10, 10, 40, 40, 50]

    def __init__(self):
        super().__init__()
        self._config = {}

    def setup(self, context: PluginContext) -> None:
        """Initialize configuration from context."""
        self._context = context
        # Read config from context.config_snapshot
        plugin_config = context.config_snapshot.get("plugins", {}).get("xlsx_store", {})
        self._config = plugin_config

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        """Execute XLSX storage.

        Args:
            request: StoreRequest with dataset, run_id, target_id, format_id, data_refs
            context: PluginContext with storage workspace

        Returns:
            StoreReceipt with written/skipped/failed counts and output_ref
        """
        try:
            # Get output path
            output_path = self._resolve_output_path(request, context)

            # Load records (placeholder - actual implementation loads from data_refs)
            records = self._load_records(request, context)

            if not records:
                # Create empty workbook for idempotency
                self._create_empty_workbook(output_path)
                return StoreReceipt(
                    target_id=request.target_id,
                    written=0,
                    skipped=0,
                    failed=0,
                    records_written=0,
                    output_ref=str(output_path),
                )

            # Write records to Excel
            written = self._write_xlsx(records, output_path)

            return StoreReceipt(
                target_id=request.target_id,
                written=written,
                skipped=0,
                failed=0,
                records_written=written,
                output_ref=str(output_path),
            )

        except Exception as e:
            logger.exception("XLSX storage failed for target %s", request.target_id)
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
        """Resolve output file path."""
        output_dir = self._config.get("output_dir", "data/output")
        filename = self._config.get("filename", "summary.xlsx")

        base = Path(output_dir)
        base.mkdir(parents=True, exist_ok=True)
        return base / filename

    def _load_records(self, request: StoreRequest, context: PluginContext) -> list[dict]:
        """Load records from data_refs (placeholder)."""
        # Actual implementation would fetch from data_refs
        return []

    def _create_empty_workbook(self, output_path: Path) -> None:
        """Create an empty workbook with headers only."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = self._config.get("sheet_name", "导师汇总")
        ws.append(self.HEADERS)
        self._style_header(ws)
        self._style_columns(ws)

        from infra.storage.atomic_io import atomic_write_bytes
        from io import BytesIO
        bio = BytesIO()
        wb.save(bio)
        atomic_write_bytes(output_path, bio.getvalue())

    def _write_xlsx(self, records: list[dict], output_path: Path) -> int:
        """Write records to XLSX file."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = self._config.get("sheet_name", "导师汇总")

        # Headers
        ws.append(self.HEADERS)
        self._style_header(ws)

        # Data rows
        row_idx = 2
        for rec in records:
            row_data = self._record_to_row(rec)
            ws.append(row_data)
            # Apply wrap text alignment
            for col_idx in range(1, len(self.HEADERS) + 1):
                ws.cell(row=row_idx, column=col_idx).alignment = Alignment(wrap_text=True, vertical="top")
            row_idx += 1

        # Style columns
        self._style_columns(ws)
        ws.freeze_panes = "A2"

        # Atomic write
        from infra.storage.atomic_io import atomic_write_bytes
        from io import BytesIO
        bio = BytesIO()
        wb.save(bio)
        atomic_write_bytes(output_path, bio.getvalue())

        logger.info("Wrote %d records to %s", len(records), output_path)
        return len(records)

    def _record_to_row(self, rec: dict) -> list[str]:
        """Convert a record dict to Excel row data."""
        return [
            rec.get("university", ""),
            rec.get("college", ""),
            rec.get("name", ""),
            rec.get("title", ""),
            rec.get("advisor_status", ""),
            rec.get("research_areas_str", rec.get("research_areas", "")),
            rec.get("research_areas_str", rec.get("research_areas", "")),
            rec.get("source_url", ""),
        ]

    def _style_header(self, ws) -> None:
        """Apply header styling."""
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
        for col_idx, header in enumerate(self.HEADERS, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def _style_columns(self, ws) -> None:
        """Set column widths."""
        for i, width in enumerate(self.COLUMN_WIDTHS, 1):
            ws.column_dimensions[get_column_letter(i)].width = width

    def close(self) -> None:
        """Cleanup resources."""
        pass