"""Table Component UI Plugin.

Declarative UI component plugin that generates a table component description
from a ViewModel. Produces UIComponentDTO with component_type="table"
for frontend rendering via registered table renderer.
"""

import logging
from typing import Any
from uuid import uuid4
from datetime import datetime

from contracts.ui import ViewModel, UIComponentDTO, validate_ui_component
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)


class TableComponentPlugin(BasePlugin[ViewModel, UIComponentDTO]):
    """UI Plugin that creates a table component from ViewModel.

    Input: ViewModel (dataset, schema, paginated data reference, field descriptions)
    Output: UIComponentDTO with component_type="table" and validated payload

    Payload schema:
        - columns: list of column definitions (field name, label, sortable, formatter)
        - sortable: bool (default: True) - enable column sorting
        - pagination: bool (default: True) - enable pagination controls
        - page_size: int (default: 50) - rows per page
        - striped: bool (default: True) - zebra striping
        - hoverable: bool (default: True) - row hover effect
        - bordered: bool (default: False) - show cell borders
    """

    name = "table_component"
    version = "1.0.0"
    plugin_type = "ui"
    input_schema = "ViewModel.v1"
    output_schema = "UIComponentDTO.v1"

    def __init__(self):
        super().__init__()
        self._context: PluginContext | None = None
        self._config: dict[str, Any] = {}

    def setup(self, context: PluginContext) -> None:
        """Initialize plugin with context and configuration."""
        self._context = context
        plugin_config = context.config_snapshot.get("plugins", {}).get("table_component", {})
        self._config = plugin_config
        logger.info("TableComponentPlugin initialized with config: %s", self._config)

    def execute(self, view_model: ViewModel, context: PluginContext) -> UIComponentDTO:
        """Generate table component DTO from ViewModel.

        Args:
            view_model: ViewModel containing dataset, schema, field descriptions, and data reference
            context: PluginContext with runtime services

        Returns:
            UIComponentDTO describing a table component ready for frontend rendering
        """
        # Extract field descriptions to build column definitions
        field_descriptions = view_model.field_descriptions or {}

        # Build columns from field_descriptions or use default from config
        columns = self._build_columns(field_descriptions, view_model)

        # Build payload with configurable options
        payload = {
            "columns": columns,
            "sortable": self._config.get("sortable", True),
            "pagination": self._config.get("pagination", True),
            "page_size": self._config.get("page_size", view_model.page_size or 50),
            "striped": self._config.get("striped", True),
            "hoverable": self._config.get("hoverable", True),
            "bordered": self._config.get("bordered", False),
        }

        # Create component DTO
        component = UIComponentDTO(
            component_id=f"table_{view_model.dataset}_{uuid4().hex[:8]}",
            component_type="table",
            renderer_id="table_renderer_v1",
            payload=payload,
            data_ref=view_model.data_ref or f"/api/data/{view_model.dataset}?page=1&page_size={payload['page_size']}",
            events=[
                {"event": "sort", "action": "sort_column", "params": ["column", "direction"]},
                {"event": "page_change", "action": "change_page", "params": ["page"]},
                {"event": "page_size_change", "action": "change_page_size", "params": ["page_size"]},
                {"event": "row_click", "action": "select_row", "params": ["row_index", "row_data"]},
            ],
        )

        # Validate against schema
        validate_ui_component(component)

        logger.info(
            "TableComponentPlugin generated component %s with %d columns for dataset %s",
            component.component_id,
            len(columns),
            view_model.dataset,
        )

        return component

    def _build_columns(
        self, field_descriptions: dict[str, Any], view_model: ViewModel
    ) -> list[dict[str, Any]]:
        """Build column definitions from field descriptions.

        Args:
            field_descriptions: Mapping of field name to {type, label, format}
            view_model: ViewModel for context

        Returns:
            List of column definition dictionaries
        """
        # Check if explicit columns configured
        configured_columns = self._config.get("columns")
        if configured_columns:
            # Validate and use configured columns
            return self._normalize_configured_columns(configured_columns, field_descriptions)

        # Auto-generate columns from field_descriptions
        columns = []
        for field_name, field_info in field_descriptions.items():
            if not isinstance(field_info, dict):
                field_info = {"type": "string", "label": field_name}

            col = {
                "field": field_name,
                "label": field_info.get("label", field_name.replace("_", " ").title()),
                "type": field_info.get("type", "string"),
                "sortable": field_info.get("sortable", True),
                "formatter": field_info.get("formatter"),
                "align": field_info.get("align", "left"),
                "width": field_info.get("width"),
            }
            columns.append(col)

        # If no field descriptions, create minimal columns from schema_id hint
        if not columns:
            columns = self._get_default_columns(view_model.schema_id)

        return columns

    def _normalize_configured_columns(
        self, configured: list[dict[str, Any]], field_descriptions: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Normalize and validate user-configured columns."""
        normalized = []
        for col in configured:
            if isinstance(col, str):
                # Simple field name string
                field_name = col
                field_info = field_descriptions.get(field_name, {})
                normalized.append({
                    "field": field_name,
                    "label": field_info.get("label", field_name.replace("_", " ").title()),
                    "type": field_info.get("type", "string"),
                    "sortable": True,
                    "formatter": None,
                    "align": "left",
                    "width": None,
                })
            elif isinstance(col, dict):
                # Full column definition
                field_name = col.get("field")
                if not field_name:
                    continue
                field_info = field_descriptions.get(field_name, {})
                normalized.append({
                    "field": field_name,
                    "label": col.get("label", field_info.get("label", field_name.replace("_", " ").title())),
                    "type": col.get("type", field_info.get("type", "string")),
                    "sortable": col.get("sortable", field_info.get("sortable", True)),
                    "formatter": col.get("formatter", field_info.get("formatter")),
                    "align": col.get("align", "left"),
                    "width": col.get("width"),
                })
        return normalized

    def _get_default_columns(self, schema_id: str) -> list[dict[str, Any]]:
        """Get default columns for known education schemas."""
        if "tutor" in schema_id.lower():
            return [
                {"field": "name", "label": "姓名", "type": "string", "sortable": True, "align": "left"},
                {"field": "title", "label": "职称", "type": "string", "sortable": True, "align": "left"},
                {"field": "university", "label": "高校", "type": "string", "sortable": True, "align": "left"},
                {"field": "college", "label": "学院", "type": "string", "sortable": True, "align": "left"},
                {"field": "category", "label": "学科门类", "type": "string", "sortable": True, "align": "left"},
                {"field": "year", "label": "年份", "type": "integer", "sortable": True, "align": "center"},
                {"field": "source_type", "label": "来源类型", "type": "string", "sortable": True, "align": "left"},
            ]
        elif "major" in schema_id.lower():
            return [
                {"field": "major_code", "label": "专业代码", "type": "string", "sortable": True, "align": "center"},
                {"field": "major_name", "label": "专业名称", "type": "string", "sortable": True, "align": "left"},
                {"field": "discipline", "label": "学科门类", "type": "string", "sortable": True, "align": "left"},
                {"field": "degree_level", "label": "学位层次", "type": "string", "sortable": True, "align": "center"},
                {"field": "duration", "label": "学制", "type": "string", "sortable": True, "align": "center"},
            ]
        # Generic fallback
        return [
            {"field": "id", "label": "ID", "type": "string", "sortable": True, "align": "left"},
            {"field": "name", "label": "名称", "type": "string", "sortable": True, "align": "left"},
        ]

    def close(self) -> None:
        """Cleanup resources."""
        pass


# Renderer manifest for the table component
TABLE_RENDERER_MANIFEST = {
    "renderer_id": "table_renderer_v1",
    "version": "1.0.0",
    "component_type": "table",
    "description": "Plain HTML table renderer with sorting, pagination, and row selection",
    "entry_point": "plugins.ui.table_component.assets.renderer",
    "assets": {
        "js": ["renderer.js"],
        "css": ["renderer.css"],
    },
    "payload_schema": {
        "type": "object",
        "properties": {
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "field": {"type": "string", "minLength": 1},
                        "label": {"type": "string", "minLength": 1},
                        "type": {"type": "string", "enum": ["string", "integer", "number", "boolean", "date", "datetime"]},
                        "sortable": {"type": "boolean", "default": True},
                        "formatter": {"type": ["string", "null"]},
                        "align": {"type": "string", "enum": ["left", "center", "right"], "default": "left"},
                        "width": {"type": ["integer", "string", "null"]},
                    },
                    "required": ["field", "label"],
                    "additionalProperties": False,
                },
                "minItems": 1,
            },
            "sortable": {"type": "boolean", "default": True},
            "pagination": {"type": "boolean", "default": True},
            "page_size": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
            "striped": {"type": "boolean", "default": True},
            "hoverable": {"type": "boolean", "default": True},
            "bordered": {"type": "boolean", "default": False},
        },
        "required": ["columns"],
        "additionalProperties": False,
    },
    "capabilities": [
        "sort",
        "pagination",
        "row_selection",
        "responsive",
        "accessible",
    ],
    "approved": True,
    "approved_at": "2026-09-18",
    "approved_by": "system",
}

__all__ = ["TableComponentPlugin", "TABLE_RENDERER_MANIFEST"]