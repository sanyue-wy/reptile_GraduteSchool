# -*- coding: utf-8 -*-
"""
Text Presenter Plugin
=====================
Renders RecordBatch data as plain text or markdown table.

Supports two modes via config:
- "text": Plain text with aligned columns
- "markdown": Markdown table format
"""

import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4
from datetime import datetime

from contracts.output import PresentationRequest, RenderedOutputDTO
from plugins.base import PresenterPlugin, PluginContext

logger = logging.getLogger(__name__)


class TextPresenterPlugin(PresenterPlugin):
    """Presenter plugin that renders records as plain text or markdown.

    Input: PresentationRequest with records and output_spec
    Output: RenderedOutputDTO with path to rendered file
    """

    name = "text_presenter"
    version = "1.0.0"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def __init__(self):
        super().__init__()
        self._config: dict[str, Any] = {}
        self._workspace: Path | None = None

    def setup(self, context: PluginContext) -> None:
        """Initialize workspace reference and config."""
        # Read config from context.config_snapshot
        plugin_config = context.config_snapshot.get("plugins", {}).get("text_presenter", {})
        self._config = plugin_config

        # Get workspace from context.storage if available
        if context.storage and hasattr(context.storage, "workspace"):
            self._workspace = context.storage.workspace

    def render(self, request: PresentationRequest, context: PluginContext) -> RenderedOutputDTO | str:
        """Render records as plain text or markdown table.

        Args:
            request: PresentationRequest containing records and output spec
            context: PluginContext with storage workspace

        Returns:
            RenderedOutputDTO or path string to output file
        """
        # Get mode from config (default: "text")
        mode = self._config.get("mode", "text").lower()

        # Determine output format
        if mode == "markdown":
            output_format = "markdown"
            ext = ".md"
        else:
            output_format = "text"
            ext = ".txt"

        # Resolve output path
        output_path = self._resolve_output_path(request, context, ext)

        # Render records based on mode
        if mode == "markdown":
            content = self._render_markdown(request)
        else:
            content = self._render_text(request)

        # Write output file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

        logger.info("Rendered %d records as %s to %s", len(request.records), mode, output_path)

        return RenderedOutputDTO(
            output_id=uuid4().hex,
            output_format=output_format,
            path=str(output_path),
            metadata={
                "mode": mode,
                "record_count": len(request.records),
                "size_bytes": len(content.encode("utf-8")),
            },
        )

    @property
    def output_format(self) -> str:
        """Output format identifier based on configured mode."""
        mode = self._config.get("mode", "text").lower()
        return "markdown" if mode == "markdown" else "text"

    def _resolve_output_path(
        self, request: PresentationRequest, context: PluginContext, ext: str
    ) -> Path:
        """Resolve output file path based on request and context."""
        # Check for output_dir in config
        output_dir = self._config.get("output_dir")

        if output_dir:
            base = Path(output_dir)
        elif self._workspace:
            store_path = self._workspace.get_store_path(request.dataset, ext)
            base = Path(store_path).parent if isinstance(store_path, str) else store_path.parent
        else:
            # Fallback to default location
            base = Path("data/output/presenter")

        return base / f"{request.dataset}_{request.request_id[:8]}{ext}"

    def _render_text(self, request: PresentationRequest) -> str:
        """Render records as plain text with aligned columns.

        Args:
            request: PresentationRequest with records

        Returns:
            Plain text string
        """
        if not request.records:
            return f"Dataset: {request.dataset}\nSchema: {request.schema_id}\n\nNo records to display.\n"

        # Extract field names from first record
        fields = list(request.records[0].keys()) if request.records else []

        # Calculate column widths
        col_widths = {field: len(field) for field in fields}
        for record in request.records:
            for field in fields:
                value = str(record.get(field, ""))
                col_widths[field] = max(col_widths[field], len(value))

        # Build header
        lines = []
        lines.append(f"Dataset: {request.dataset}")
        lines.append(f"Schema: {request.schema_id}")
        lines.append(f"Records: {len(request.records)}")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append("")

        # Header row
        header = " | ".join(field.ljust(col_widths[field]) for field in fields)
        lines.append(header)

        # Separator
        separator = "-+-".join("-" * col_widths[field] for field in fields)
        lines.append(separator)

        # Data rows
        for record in request.records:
            row = " | ".join(
                str(record.get(field, "")).ljust(col_widths[field]) for field in fields
            )
            lines.append(row)

        return "\n".join(lines)

    def _render_markdown(self, request: PresentationRequest) -> str:
        """Render records as markdown table.

        Args:
            request: PresentationRequest with records

        Returns:
            Markdown string
        """
        if not request.records:
            return f"# {request.dataset}\n\n**Schema:** {request.schema_id}\n\nNo records to display.\n"

        fields = list(request.records[0].keys()) if request.records else []

        lines = []
        lines.append(f"# {request.dataset}")
        lines.append("")
        lines.append(f"**Schema:** `{request.schema_id}`")
        lines.append(f"**Records:** {len(request.records)}")
        lines.append(f"**Generated:** {datetime.now().isoformat()}")
        lines.append("")

        # Table header
        lines.append("| " + " | ".join(fields) + " |")
        lines.append("| " + " | ".join("---" for _ in fields) + " |")

        # Data rows
        for record in request.records:
            row = "| " + " | ".join(str(record.get(field, "")) for field in fields) + " |"
            lines.append(row)

        return "\n".join(lines)

    def close(self) -> None:
        """Cleanup resources."""
        pass