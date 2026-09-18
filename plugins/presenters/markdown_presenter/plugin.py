"""Markdown Presenter Plugin.

Renders RecordBatch data as structured Markdown (table or list mode).
Uses BasePresenterHelper for output path resolution and atomic writes.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts.output import PresentationRequest, RenderedOutputDTO
from plugins.base import PresenterPlugin, PluginContext
from plugins.presenters.base_presenter import BasePresenterHelper

logger = logging.getLogger(__name__)


class MarkdownPresenterPlugin(PresenterPlugin):
    """Presenter that renders records as Markdown files.

    Modes:
    - "table": Markdown table (default)
    - "list":  Each record as a headed section with key-value pairs
    """

    name = "markdown_presenter"
    version = "1.0.0"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def __init__(self):
        super().__init__()
        self._config: dict[str, Any] = {}

    def setup(self, context: PluginContext) -> None:
        self._config = (
            context.config_snapshot.get("plugins", {}).get("markdown_presenter", {})
        )

    def render(self, request: PresentationRequest, context: PluginContext) -> RenderedOutputDTO:
        mode = self._config.get("mode", "table").lower()
        h = BasePresenterHelper

        records, fieldnames = h.prepare_records(request)
        base_dir = h.resolve_output_dir(self._config, context, request, ".md")
        path = h.make_output_path(base_dir, request.dataset, ".md", request.request_id)

        if mode == "list":
            content = self._render_list(request, records, fieldnames)
        else:
            content = self._render_table(request, records, fieldnames)

        size = h.atomic_write_text(path, content)
        logger.info("Rendered %d records as markdown (%s) to %s", len(records), mode, path)

        return h.make_rendered_output(
            output_format="markdown",
            path=path,
            metadata={
                "mode": mode,
                "record_count": len(records),
                "size_bytes": size,
            },
        )

    # ------------------------------------------------------------------
    # Mode renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_table(
        request: PresentationRequest,
        records: list[dict],
        fieldnames: list[str],
    ) -> str:
        lines: list[str] = []
        lines.append(f"# {request.dataset}\n")
        lines.append(f"**Schema:** `{request.schema_id}`  ")
        lines.append(f"**Records:** {len(records)}  ")
        lines.append(f"**Generated:** {datetime.now().isoformat()}\n")

        if not records:
            lines.append("_No records._\n")
            return "\n".join(lines)

        # Header
        lines.append("| " + " | ".join(fieldnames) + " |")
        lines.append("| " + " | ".join("---" for _ in fieldnames) + " |")

        # Rows — pipe-escape every cell value
        for rec in records:
            cells = []
            for f in fieldnames:
                v = str(rec.get(f, ""))
                v = v.replace("|", "\\|").replace("\n", " ")
                cells.append(v)
            lines.append("| " + " | ".join(cells) + " |")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_list(
        request: PresentationRequest,
        records: list[dict],
        fieldnames: list[str],
    ) -> str:
        lines: list[str] = []
        lines.append(f"# {request.dataset}\n")
        lines.append(f"**Schema:** `{request.schema_id}`  ")
        lines.append(f"**Records:** {len(records)}  ")
        lines.append(f"**Generated:** {datetime.now().isoformat()}\n")

        if not records:
            lines.append("_No records._\n")
            return "\n".join(lines)

        for idx, rec in enumerate(records, start=1):
            lines.append(f"## Record {idx}\n")
            for f in fieldnames:
                lines.append(f"- **{f}:** {rec.get(f, '')}")
            lines.append("")

        return "\n".join(lines)

    @property
    def output_format(self) -> str:
        return "markdown"

    def close(self) -> None:
        pass
