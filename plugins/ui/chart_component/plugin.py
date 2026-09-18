"""Chart Component UI Plugin.

Renders declarative chart components (bar, line, pie) using Chart.js.
Generates UIComponentDTO instances for frontend rendering.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from contracts.ui import UIComponentDTO, ViewModel
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


@dataclass
class ChartPayload:
    """Validated chart component payload.

    chart_type: One of "bar", "line", "pie"
    x_field: Data field for X-axis (or labels for pie)
    y_field: Data field for Y-axis (or values for pie)
    group_by: Optional field to group series by
    """
    chart_type: str  # bar, line, pie
    x_field: str
    y_field: str
    group_by: str | None = None

    @classmethod
    def schema(cls) -> dict[str, Any]:
        """JSON Schema for chart payload validation."""
        return {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie"],
                    "description": "Chart type to render"
                },
                "x_field": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Data field for X-axis labels"
                },
                "y_field": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Data field for Y-axis values"
                },
                "group_by": {
                    "type": ["string", "null"],
                    "description": "Optional field to group data series by"
                }
            },
            "required": ["chart_type", "x_field", "y_field"],
            "additionalProperties": False
        }

    @classmethod
    def validate(cls, payload: dict[str, Any]) -> "ChartPayload":
        """Validate and construct payload from dict."""
        import jsonschema
        jsonschema.validate(payload, cls.schema())
        return cls(
            chart_type=payload["chart_type"],
            x_field=payload["x_field"],
            y_field=payload["y_field"],
            group_by=payload.get("group_by")
        )


class ChartComponentPlugin(BasePlugin[ViewModel, list[UIComponentDTO]]):
    """UI Plugin for rendering chart components.

    Input: ViewModel containing dataset, schema, and data reference
    Output: List of UIComponentDTO for chart components

    The plugin creates declarative chart component descriptions that
    are rendered by the frontend using Chart.js (via registered renderer).
    """

    name = "chart_component"
    version = "1.0.0"
    plugin_type = "ui"
    input_schema = "ViewModel.v1"
    output_schema = "UIComponentDTO.v1"  # Returns list of components

    # Renderer manifest - defines frontend renderer requirements
    RENDERER_MANIFEST = {
        "renderer_id": "chartjs_v4",
        "version": "4.4.3",
        "entry_point": "plugins/ui/chart_component/assets/renderer.js",
        "dependencies": [
            {
                "name": "chart.js",
                "version": "4.4.3",
                "cdn": "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js",
                "integrity": "sha384-8f4lV7xUjT5gYxG8mL5jV6jJ9hJ9wJ9wJ9wJ9wJ9wJ9wJ9wJ9wJ9wJ9wJ9wJ9w=="
            }
        ],
        "exports": {
            "render": "renderChart",
            "update": "updateChart",
            "destroy": "destroyChart"
        },
        "supported_types": ["bar", "line", "pie"],
        "supported_payload_schema": ChartPayload.schema()
    }

    def __init__(self):
        super().__init__()
        self._context: PluginContext | None = None

    def setup(self, context: PluginContext) -> None:
        """Initialize plugin with context."""
        self._context = context
        logger.info("ChartComponentPlugin initialized")

    def execute(self, view_model: ViewModel, context: PluginContext) -> list[UIComponentDTO]:
        """Generate chart component DTOs from ViewModel.

        Creates declarative UI components for each chart specified in
        the ViewModel's configuration or inferred from data fields.
        """
        components: list[UIComponentDTO] = []

        # Extract chart configurations from ViewModel metadata or run_state
        chart_configs = self._extract_chart_configs(view_model)

        for idx, config in enumerate(chart_configs):
            # Validate payload
            payload = ChartPayload.validate(config)

            # Create component DTO
            component = UIComponentDTO(
                component_id=f"{view_model.dataset}_chart_{idx}_{uuid4().hex[:8]}",
                component_type="chart",
                renderer_id=self.RENDERER_MANIFEST["renderer_id"],
                payload={
                    "chart_type": payload.chart_type,
                    "x_field": payload.x_field,
                    "y_field": payload.y_field,
                    "group_by": payload.group_by
                },
                data_ref=view_model.data_ref,
                events=[
                    {"event": "click", "handler": "onChartClick"},
                    {"event": "hover", "handler": "onChartHover"}
                ]
            )
            components.append(component)

            logger.info("Created chart component: %s (%s)", component.component_id, payload.chart_type)

        return components

    def _extract_chart_configs(self, view_model: ViewModel) -> list[dict[str, Any]]:
        """Extract chart configurations from ViewModel.

        Priority:
        1. Explicit chart configs in run_state.charts
        2. Inferred from field_descriptions (numeric fields -> charts)
        3. Default single chart if no config found
        """
        configs: list[dict[str, Any]] = []

        # 1. Check for explicit chart configs in run_state
        run_state = view_model.run_state or {}
        explicit_charts = run_state.get("charts", [])
        if explicit_charts:
            for chart in explicit_charts:
                if isinstance(chart, dict):
                    configs.append(chart)
            return configs

        # 2. Infer from stats or field descriptions
        stats = view_model.stats or {}
        field_descriptions = view_model.field_descriptions or {}

        # Find numeric fields that could be charted
        numeric_fields = [
            name for name, desc in field_descriptions.items()
            if isinstance(desc, dict) and desc.get("type") in ("number", "integer", "float")
        ]

        categorical_fields = [
            name for name, desc in field_descriptions.items()
            if isinstance(desc, dict) and desc.get("type") in ("string", "category")
        ]

        if numeric_fields and categorical_fields:
            # Create default charts for each numeric field
            for y_field in numeric_fields[:3]:  # Limit to 3 charts
                configs.append({
                    "chart_type": "bar",
                    "x_field": categorical_fields[0],
                    "y_field": y_field,
                    "group_by": None
                })

        # 3. Fallback: create a default chart if we have data
        if not configs and view_model.total_count > 0:
            # Try to infer from data_ref or stats
            if field_descriptions:
                first_field = next(iter(field_descriptions.keys()), "value")
                configs.append({
                    "chart_type": "bar",
                    "x_field": "index",
                    "y_field": first_field,
                    "group_by": None
                })

        return configs

    def get_renderer_manifest(self) -> dict[str, Any]:
        """Return the renderer manifest for this plugin."""
        return self.RENDERER_MANIFEST

    def close(self) -> None:
        """Cleanup resources."""
        pass


# Module-level exports for plugin registry
def create_plugin() -> ChartComponentPlugin:
    """Factory function for plugin registry."""
    return ChartComponentPlugin()


__all__ = [
    "ChartComponentPlugin",
    "ChartPayload",
    "create_plugin",
]