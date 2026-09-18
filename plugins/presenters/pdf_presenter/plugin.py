# -*- coding: utf-8 -*-
"""
PDF Presenter Plugin
====================
Renders PresentationRequest records as PDF output using WeasyPrint.

Optional dependency: weasyprint
- If WeasyPrint not installed, plugin reports "依赖缺失" in precheck
- Test environment without WeasyPrint: test cases explicitly skip

Output format: pdf
"""

import html as html_mod
import logging
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4
from datetime import datetime

from contracts.output import PresentationRequest, RenderedOutputDTO
from plugins.base import PresenterPlugin, PluginContext

logger = logging.getLogger(__name__)

# Track WeasyPrint availability
_WEASYPRINT_AVAILABLE = False
_WEASYPRINT_IMPORT_ERROR = None

try:
    from weasyprint import HTML, CSS
    from weasyprint.text.fonts import FontConfiguration
    _WEASYPRINT_AVAILABLE = True
except (ImportError, OSError) as e:
    _WEASYPRINT_IMPORT_ERROR = str(e)
    logger.info("WeasyPrint not available: %s", e)


class PdfPresenterPlugin(PresenterPlugin):
    """Presenter plugin that renders records as PDF using WeasyPrint.

    Input: PresentationRequest with records and output_spec
    Output: RenderedOutputDTO with path to generated PDF file

    Configuration via config_snapshot["plugins"]["pdf_presenter"]:
    - output_dir: Optional output directory
    - template: HTML template name (default: "default")
    - page_size: Page size (default: "A4") - A4, Letter, Legal, etc.
    - margin: Page margins (default: "2cm")
    - include_header: Include header with dataset info (default: true)
    - include_footer: Include footer with page numbers (default: true)
    """

    name = "pdf_presenter"
    version = "1.0.0"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    class DependencyError(RuntimeError):
        """Raised when WeasyPrint is not available."""
        pass

    def __init__(self):
        super().__init__()
        self._config: dict[str, Any] = {}
        self._workspace: Path | None = None
        self._font_config: Any = None

    def setup(self, context: PluginContext) -> None:
        """Initialize workspace reference and config."""
        # Read config from context.config_snapshot
        plugin_config = context.config_snapshot.get("plugins", {}).get("pdf_presenter", {})
        self._config = plugin_config

        # Get workspace from context.storage if available
        if context.storage and hasattr(context.storage, "workspace"):
            self._workspace = context.storage.workspace

        # Initialize font configuration for WeasyPrint
        if _WEASYPRINT_AVAILABLE:
            self._font_config = FontConfiguration()

        logger.info("PDF presenter initialized with config: %s", self._config)

    def precheck(self) -> tuple[bool, Optional[str]]:
        """Check if WeasyPrint dependency is available.

        Returns:
            (ok, error_message) - ok=True if ready, False with error message if dependency missing
        """
        if not _WEASYPRINT_AVAILABLE:
            return False, f"依赖缺失: WeasyPrint not installed ({_WEASYPRINT_IMPORT_ERROR})"
        return True, None

    def render(self, request: PresentationRequest, context: PluginContext) -> RenderedOutputDTO | str:
        """Render records as PDF file.

        Args:
            request: PresentationRequest containing records and output spec
            context: PluginContext with storage workspace

        Returns:
            RenderedOutputDTO or path string to output file

        Raises:
            DependencyError: If WeasyPrint is not available
        """
        # Precheck at execution time too
        ok, err = self.precheck()
        if not ok:
            raise self.DependencyError(err)

        # Determine output path
        output_path = self._resolve_output_path(request, context)

        # Generate HTML content
        html_content = self._generate_html(request)

        # Convert HTML to PDF
        written = self._write_pdf(html_content, output_path, request)

        logger.info("PDF presenter wrote %d records to %s", len(request.records), output_path)

        return RenderedOutputDTO(
            output_id=uuid4().hex,
            output_format="pdf",
            path=str(output_path),
            metadata={
                "record_count": len(request.records),
                "page_size": self._config.get("page_size", "A4"),
                "size_bytes": output_path.stat().st_size if output_path.exists() else 0,
            },
        )

    def _resolve_output_path(self, request: PresentationRequest, context: PluginContext) -> Path:
        """Resolve output file path based on request and context."""
        # Check for output_dir in config
        output_dir = self._config.get("output_dir")

        if output_dir:
            base = Path(output_dir)
        elif self._workspace:
            base = self._workspace.get_store_path(request.dataset, ".pdf").parent
        else:
            # Fallback to default location
            base = Path("data/output/presenter")

        base.mkdir(parents=True, exist_ok=True)

        # Include dataset and timestamp in filename for uniqueness
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{request.dataset}_{timestamp}.pdf"
        return base / filename

    def _generate_html(self, request: PresentationRequest) -> str:
        """Generate HTML content from records using template.

        Args:
            request: PresentationRequest with records and output_spec

        Returns:
            HTML string ready for PDF conversion
        """
        template_name = self._config.get("template", "default")
        include_header = self._config.get("include_header", True)
        include_footer = self._config.get("include_footer", True)

        if template_name == "default":
            return self._generate_default_html(request, include_header, include_footer)
        else:
            # Could support custom templates from files
            return self._generate_default_html(request, include_header, include_footer)

    def _generate_default_html(
        self,
        request: PresentationRequest,
        include_header: bool,
        include_footer: bool
    ) -> str:
        """Generate default HTML table representation."""
        records = request.records
        output_spec = request.output_spec or {}

        # Determine fields to display
        if records:
            all_fields = list(records[0].keys())
        else:
            all_fields = []

        include_fields = output_spec.get("include_fields")
        exclude_fields = output_spec.get("exclude_fields")

        if include_fields:
            fields = [f for f in all_fields if f in include_fields]
        elif exclude_fields:
            fields = [f for f in all_fields if f not in exclude_fields]
        else:
            fields = all_fields

        # Build HTML
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang=\"zh-CN\">",
            "<head>",
            "    <meta charset=\"UTF-8\">",
            "    <title>{dataset}</title>".format(dataset=request.dataset),
            "    <style>",
            self._get_default_css(),
            "    </style>",
            "</head>",
            "<body>",
        ]

        # Header section
        if include_header:
            html_parts.extend([
                "    <header class=\"pdf-header\">",
                "        <h1>{dataset}</h1>".format(dataset=request.dataset),
                "        <div class=\"meta\">",
                "            <span>Schema: {schema}</span>".format(schema=request.schema_id),
                "            <span>Records: {count}</span>".format(count=len(records)),
                "            <span>Generated: {time}</span>".format(time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "        </div>",
                "    </header>",
            ])

        # Table
        if records:
            html_parts.append("    <table class=\"pdf-table\">")
            # Header row
            html_parts.append("        <thead>")
            html_parts.append("            <tr>")
            for field in fields:
                html_parts.append("                <th>{field}</th>".format(field=html_mod.escape(field)))
            html_parts.append("            </tr>")
            html_parts.append("        </thead>")
            # Body rows
            html_parts.append("        <tbody>")
            for record in records:
                html_parts.append("            <tr>")
                for field in fields:
                    value = str(record.get(field, ""))
                    # Escape HTML entities (& < > " ')
                    value = html_mod.escape(value, quote=True)
                    html_parts.append("                <td>{value}</td>".format(value=value))
                html_parts.append("            </tr>")
            html_parts.append("        </tbody>")
            html_parts.append("    </table>")
        else:
            html_parts.append("    <div class=\"no-data\">No records to display</div>")

        # Footer section
        if include_footer:
            html_parts.extend([
                "    <footer class=\"pdf-footer\">",
                "        <div class=\"page-number\">Page <span class=\"page\"></span> of <span class=\"pages\"></span></div>",
                "    </footer>",
            ])

        html_parts.extend(["</body>", "</html>"])

        return "\n".join(html_parts)

    def _get_default_css(self) -> str:
        """Get default CSS for PDF styling."""
        page_size = self._config.get("page_size", "A4")
        margin = self._config.get("margin", "2cm")

        return f"""
        @page {{
            size: {page_size};
            margin: {margin};
            @top-center {{
                content: element(header);
            }}
            @bottom-center {{
                content: element(footer);
            }}
        }}

        body {{
            font-family: "DejaVu Sans", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
            font-size: 10pt;
            line-height: 1.4;
            color: #333;
        }}

        .pdf-header {{
            position: running(header);
            text-align: center;
            padding-bottom: 10px;
            border-bottom: 1px solid #ccc;
            margin-bottom: 20px;
        }}

        .pdf-header h1 {{
            margin: 0;
            font-size: 16pt;
            color: #2c3e50;
        }}

        .pdf-header .meta {{
            font-size: 8pt;
            color: #666;
            margin-top: 5px;
        }}

        .pdf-header .meta span {{
            margin: 0 10px;
        }}

        .pdf-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
            table-layout: fixed;
        }}

        .pdf-table th {{
            background-color: #2c3e50;
            color: white;
            padding: 8px 6px;
            text-align: left;
            font-weight: bold;
            font-size: 9pt;
            border: 1px solid #ddd;
            word-wrap: break-word;
        }}

        .pdf-table td {{
            padding: 6px;
            border: 1px solid #ddd;
            font-size: 9pt;
            word-wrap: break-word;
        }}

        .pdf-table tbody tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}

        .pdf-table tbody tr:hover {{
            background-color: #f0f0f0;
        }}

        .no-data {{
            text-align: center;
            padding: 40px;
            color: #999;
            font-style: italic;
        }}

        .pdf-footer {{
            position: running(footer);
            text-align: center;
            font-size: 8pt;
            color: #999;
            border-top: 1px solid #ccc;
            padding-top: 5px;
        }}

        .page-number {{
            margin: 0;
        }}
        """

    def _write_pdf(self, html_content: str, output_path: Path, request: PresentationRequest) -> int:
        """Convert HTML to PDF using WeasyPrint.

        Args:
            html_content: HTML string to convert
            output_path: Target PDF file path
            request: Original request for metadata

        Returns:
            Number of records written (for logging)
        """
        from weasyprint import HTML, CSS

        # Create PDF
        html_doc = HTML(string=html_content, base_url=".")
        css_doc = CSS(string=self._get_default_css(), font_config=self._font_config)

        # Write to file
        html_doc.write_pdf(
            str(output_path),
            stylesheets=[css_doc],
            font_config=self._font_config,
        )

        return len(request.records)

    def close(self) -> None:
        """Cleanup resources."""
        pass


# For backward compatibility and direct imports
__all__ = ["PdfPresenterPlugin"]