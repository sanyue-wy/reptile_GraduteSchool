"""HTML Presenter Plugin.

Renders PresentationRequest into a standalone HTML package that can be
opened directly via file:// without a running server.

Features:
- Loads templates from templates/ registry
- Resolves UI component renderers (table/chart/card/filter)
- Embeds ThemeSwitcher for client-side theme cycling
- Two modes: standalone (inline everything) / hosted (API data refs)
- CSP-safe: all user data escaped, no arbitrary script injection
"""

import html as html_mod
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from contracts.output import PresentationRequest, RenderedOutputDTO
from contracts.ui import UIComponentDTO
from plugins.base import PresenterPlugin, PluginContext
from plugins.presenters.base_presenter import BasePresenterHelper

logger = logging.getLogger(__name__)

# Built-in renderer implementations keyed by renderer_id
_RENDERER_REGISTRY: dict[str, Any] = {}


def register_renderer(renderer_id: str, impl: Any) -> None:
    """Register a UI renderer implementation for HTML composition."""
    _RENDERER_REGISTRY[renderer_id] = impl


def get_renderer(renderer_id: str) -> Any | None:
    """Get a registered renderer by ID."""
    return _RENDERER_REGISTRY.get(renderer_id)


def list_renderers() -> dict[str, Any]:
    """Return all registered renderers."""
    return dict(_RENDERER_REGISTRY)


def _escape(text: Any) -> str:
    """HTML-escape any value for safe insertion."""
    return html_mod.escape(str(text)) if text is not None else ""


class HtmlPresenterPlugin(PresenterPlugin):
    """Presenter plugin that generates standalone HTML output.

    Composes UI component descriptions into a themed HTML page using
    templates from the template registry. Output is a self-contained
    HTML file (or directory with assets) viewable at file://.
    """

    name = "html_presenter"
    version = "1.0.0"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def __init__(self):
        super().__init__()
        self._config: dict[str, Any] = {}
        self._template_dir: Path | None = None
        self._helper = BasePresenterHelper()

    def setup(self, context: PluginContext) -> None:
        """Initialize presenter with context and template registry."""
        plugin_config = context.config_snapshot.get("plugins", {}).get("html_presenter", {})
        self._config = plugin_config

        # Locate templates directory relative to project root
        candidates = [
            Path("templates"),
            Path(__file__).resolve().parents[2] / "templates",
        ]
        for c in candidates:
            if c.is_dir():
                self._template_dir = c
                break

        if not self._template_dir:
            logger.warning("Templates directory not found; will use built-in minimal template")

        logger.info("HTML presenter initialized with config: %s", self._config)

    def render(self, request: PresentationRequest, context: PluginContext) -> RenderedOutputDTO:
        """Render PresentationRequest into standalone HTML.

        Steps:
        1. Resolve template (from output_spec.template or default minimal-light)
        2. Build component HTML from UI component descriptions
        3. Compose final page with theme switcher
        4. Write to output directory
        """
        output_spec = request.output_spec or {}
        template_name = output_spec.get("template", self._config.get("template", "minimal-light"))
        mode = self._config.get("mode", "standalone")  # standalone | hosted

        # Load template assets
        layout_html, style_css, variables = self._load_template(template_name)

        # Build component sections
        components_html = self._build_components_html(request, output_spec)

        # Build theme switcher script
        theme_switcher_js = self._get_theme_switcher_js()

        # Compose final HTML
        page_title = _escape(f"{request.dataset} - {request.schema_id}")
        full_html = self._compose_html(
            title=page_title,
            layout=layout_html,
            style=style_css,
            variables=variables,
            components=components_html,
            theme_switcher_js=theme_switcher_js,
            request=request,
            mode=mode,
        )

        # Write output
        output_dir = self._helper.resolve_output_dir(self._config, context, request, ".html")
        output_path = self._helper.make_output_path(
            output_dir, request.dataset, ".html", request.request_id
        )

        bytes_written = self._helper.atomic_write_text(output_path, full_html)

        logger.info("HTML presenter wrote %d bytes to %s", bytes_written, output_path)

        return self._helper.make_rendered_output(
            output_format="html",
            path=output_path,
            metadata={
                "template": template_name,
                "mode": mode,
                "record_count": len(request.records),
                "size_bytes": bytes_written,
                "components": list(output_spec.get("components", [])),
            },
        )

    def _load_template(self, template_name: str) -> tuple[str, str, dict]:
        """Load template files from the templates/ registry.

        Returns (layout_html, style_css, variables_dict).
        Falls back to built-in minimal template if not found.
        """
        if self._template_dir:
            tmpl_dir = self._template_dir / template_name
            if tmpl_dir.is_dir():
                layout_path = tmpl_dir / "layout.html"
                style_path = tmpl_dir / "style.css"
                vars_path = tmpl_dir / "variables.json"

                layout = layout_path.read_text(encoding="utf-8") if layout_path.exists() else ""
                style = style_path.read_text(encoding="utf-8") if style_path.exists() else ""
                variables = {}
                if vars_path.exists():
                    variables = json.loads(vars_path.read_text(encoding="utf-8"))

                return layout, style, variables

        # Built-in minimal fallback
        return self._builtin_layout(), self._builtin_style(), self._builtin_variables()

    def _build_components_html(self, request: PresentationRequest, output_spec: dict) -> str:
        """Build HTML sections for each UI component in the output spec.

        Uses registered renderers to generate component HTML.
        Unknown renderers get a placeholder with diagnostic info.
        """
        component_specs = output_spec.get("components", [])
        if not component_specs:
            # Default: render records as a simple table
            return self._render_simple_table(request)

        parts = []
        for comp_spec in component_specs:
            if isinstance(comp_spec, str):
                # Simple component type reference
                comp_html = self._render_component_by_type(comp_spec, request)
            elif isinstance(comp_spec, dict):
                renderer_id = comp_spec.get("renderer_id", comp_spec.get("type", "table"))
                comp_html = self._render_with_renderer(renderer_id, comp_spec, request)
            else:
                comp_html = f'<div class="component-unknown">Unknown component spec</div>'
            parts.append(comp_html)

        return "\n".join(parts)

    def _render_simple_table(self, request: PresentationRequest) -> str:
        """Render records as a basic HTML table (default when no components specified)."""
        records, fieldnames = self._helper.prepare_records(request)

        if not records:
            return '<div class="no-data">No records to display.</div>'

        rows = []
        for rec in records:
            cells = "".join(f"<td>{_escape(rec.get(f, ''))}</td>" for f in fieldnames)
            rows.append(f"<tr>{cells}</tr>")

        thead = "".join(f"<th>{_escape(f)}</th>" for f in fieldnames)
        tbody = "\n".join(rows)

        return f"""<div class="component-table">
<table class="data-table">
  <thead><tr>{thead}</tr></thead>
  <tbody>
{tbody}
  </tbody>
</table>
</div>"""

    def _render_component_by_type(self, component_type: str, request: PresentationRequest) -> str:
        """Render a component by type name using default renderer."""
        renderer_id = f"{component_type}_renderer_v1"
        renderer = get_renderer(renderer_id)

        if renderer and callable(renderer):
            try:
                return renderer(request)
            except Exception as e:
                logger.warning("Renderer %s failed: %s", renderer_id, e)
                return self._render_placeholder(component_type, str(e))

        # No registered renderer: render basic version
        if component_type == "table":
            return self._render_simple_table(request)
        elif component_type == "chart":
            return self._render_chart_placeholder(request)
        elif component_type == "card":
            return self._render_card_placeholder(request)
        elif component_type == "filter":
            return self._render_filter_placeholder(request)
        else:
            return self._render_placeholder(component_type, "No renderer registered")

    def _render_with_renderer(self, renderer_id: str, spec: dict, request: PresentationRequest) -> str:
        """Render using a specific registered renderer."""
        renderer = get_renderer(renderer_id)
        if renderer and callable(renderer):
            try:
                return renderer(request, spec)
            except Exception as e:
                logger.warning("Renderer %s failed: %s", renderer_id, e)
                return self._render_placeholder(renderer_id, str(e))

        # Fallback: component-type-based default rendering
        comp_type = spec.get("type", "table")
        return self._render_component_by_type(comp_type, request)

    def _render_chart_placeholder(self, request: PresentationRequest) -> str:
        """Render a placeholder for chart component."""
        return '<div class="component-chart placeholder"><p>Chart component (requires Chart.js runtime)</p></div>'

    def _render_card_placeholder(self, request: PresentationRequest) -> str:
        """Render records as simple cards."""
        records, fieldnames = self._helper.prepare_records(request)
        if not records:
            return '<div class="no-data">No records to display.</div>'

        cards = []
        for rec in records[:50]:  # Limit for standalone mode
            fields_html = "".join(
                f'<div class="card-field"><span class="card-label">{_escape(f)}</span>'
                f'<span class="card-value">{_escape(rec.get(f, ""))}</span></div>'
                for f in fieldnames
            )
            title = _escape(rec.get(fieldnames[0], "")) if fieldnames else ""
            cards.append(f'<div class="card"><h3 class="card-title">{title}</h3>{fields_html}</div>')

        return f'<div class="component-card card-grid">{"".join(cards)}</div>'

    def _render_filter_placeholder(self, request: PresentationRequest) -> str:
        """Render a static filter display (non-functional in standalone mode)."""
        return '<div class="component-filter placeholder"><p>Filter component (interactive in hosted mode)</p></div>'

    def _render_placeholder(self, name: str, detail: str) -> str:
        """Render a diagnostic placeholder for unknown/failed components."""
        return (
            f'<div class="component-unknown">'
            f'<p>Component: {_escape(name)}</p>'
            f'<p class="diagnostic">{_escape(detail)}</p>'
            f'</div>'
        )

    def _get_theme_switcher_js(self) -> str:
        """Get the ThemeSwitcher JavaScript code."""
        from plugins.presenters.html_presenter.theme_switcher import THEME_SWITCHER_JS
        return THEME_SWITCHER_JS

    def _compose_html(
        self,
        title: str,
        layout: str,
        style: str,
        variables: dict,
        components: str,
        theme_switcher_js: str,
        request: PresentationRequest,
        mode: str,
    ) -> str:
        """Compose the final HTML page from template parts."""
        # Build CSS custom properties from variables
        css_vars = self._build_css_variables(variables)

        # Header info
        header_html = (
            f'<header class="report-header">'
            f'<h1>{_escape(request.dataset)}</h1>'
            f'<p class="meta">Schema: {_escape(request.schema_id)} | '
            f'Records: {len(request.records)} | '
            f'Generated: {_escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</p>'
            f'</header>'
        )

        # Stats section if available
        stats_html = ""
        if request.stats:
            stats_items = "".join(
                f'<span class="stat"><strong>{_escape(k)}</strong>: {_escape(v)}</span>'
                for k, v in request.stats.items()
            )
            stats_html = f'<div class="stats-bar">{stats_items}</div>'

        # Use layout template if it contains placeholders, otherwise use default
        if "{{ content }}" in layout or "{{components}}" in layout:
            page_content = layout.replace("{{ content }}", components)
            page_content = page_content.replace("{{components}}", components)
            page_content = page_content.replace("{{ header }}", header_html)
            page_content = page_content.replace("{{header}}", header_html)
            page_content = page_content.replace("{{ stats }}", stats_html)
            page_content = page_content.replace("{{stats}}", stats_html)
            page_content = page_content.replace("{{ title }}", title)
            page_content = page_content.replace("{{title}}", title)
        else:
            page_content = f"{header_html}\n{stats_html}\n<main class='content'>{components}</main>"

        # Compose full page
        return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'none'; frame-ancestors 'none';">
    <title>{title}</title>
    <style>
    :root {{
{css_vars}
    }}
{style}
{_builtin_base_style()}
    </style>
</head>
<body>
    <div id="theme-switcher-container"></div>
    {page_content}
    <footer class="report-footer">
        <p>Generated by GraduteSchool V3.0 &mdash; {_escape(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))}</p>
    </footer>
    <script>
{theme_switcher_js}
    </script>
</body>
</html>"""

    def _build_css_variables(self, variables: dict) -> str:
        """Build CSS custom property declarations from variables dict."""
        if not variables:
            return _builtin_css_variables()

        lines = []
        for key, val in variables.items():
            if isinstance(val, dict):
                value = val.get("default", val.get("value", ""))
            else:
                value = val
            lines.append(f"        --{key}: {value};")
        return "\n".join(lines)

    @staticmethod
    def _builtin_layout() -> str:
        return "{{ header }}\n{{ stats }}\n<main class='content'>{{ content }}</main>"

    @staticmethod
    def _builtin_style() -> str:
        return ""

    @staticmethod
    def _builtin_variables() -> dict:
        return {
            "color-primary": {"type": "color", "default": "#2c3e50"},
            "color-secondary": {"type": "color", "default": "#3498db"},
            "bg-primary": {"type": "color", "default": "#ffffff"},
            "bg-secondary": {"type": "color", "default": "#f8f9fa"},
            "text-primary": {"type": "color", "default": "#333333"},
            "text-secondary": {"type": "color", "default": "#666666"},
            "border-color": {"type": "color", "default": "#dee2e6"},
            "font-family": {"type": "font", "default": "system-ui, -apple-system, sans-serif"},
        }


def _builtin_base_style() -> str:
    """Built-in base stylesheet for standalone HTML output."""
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: var(--font-family);
        color: var(--text-primary);
        background: var(--bg-primary);
        line-height: 1.6;
        padding: 2rem;
        max-width: 1200px;
        margin: 0 auto;
    }
    .report-header { margin-bottom: 1.5rem; padding-bottom: 1rem; border-bottom: 2px solid var(--color-primary); }
    .report-header h1 { color: var(--color-primary); font-size: 1.8rem; }
    .report-header .meta { color: var(--text-secondary); font-size: 0.9rem; margin-top: 0.3rem; }
    .stats-bar { display: flex; gap: 1.5rem; flex-wrap: wrap; padding: 0.75rem 1rem; background: var(--bg-secondary); border-radius: 6px; margin-bottom: 1.5rem; }
    .stat { font-size: 0.85rem; }
    .content { margin-bottom: 2rem; }
    .data-table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
    .data-table th { background: var(--color-primary); color: #fff; padding: 0.6rem 0.75rem; text-align: left; font-weight: 600; font-size: 0.85rem; }
    .data-table td { padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border-color); font-size: 0.85rem; }
    .data-table tr:nth-child(even) { background: var(--bg-secondary); }
    .data-table tr:hover { background: rgba(0,0,0,0.03); }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
    .card { background: var(--bg-primary); border: 1px solid var(--border-color); border-radius: 8px; padding: 1rem; }
    .card-title { font-size: 1rem; color: var(--color-primary); margin-bottom: 0.5rem; }
    .card-field { display: flex; gap: 0.5rem; font-size: 0.85rem; margin-bottom: 0.25rem; }
    .card-label { color: var(--text-secondary); min-width: 80px; }
    .no-data { text-align: center; padding: 3rem; color: var(--text-secondary); }
    .component-unknown { border: 2px dashed var(--border-color); padding: 1rem; border-radius: 6px; color: var(--text-secondary); }
    .diagnostic { font-size: 0.8rem; color: #999; }
    .placeholder { opacity: 0.7; }
    .report-footer { margin-top: 2rem; padding-top: 1rem; border-top: 1px solid var(--border-color); text-align: center; color: var(--text-secondary); font-size: 0.8rem; }
    #theme-switcher-container { position: fixed; top: 1rem; right: 1rem; z-index: 1000; }
    """


def _builtin_css_variables() -> str:
    """Default CSS custom properties."""
    return """        --color-primary: #2c3e50;
        --color-secondary: #3498db;
        --bg-primary: #ffffff;
        --bg-secondary: #f8f9fa;
        --text-primary: #333333;
        --text-secondary: #666666;
        --border-color: #dee2e6;
        --font-family: system-ui, -apple-system, sans-serif;"""
