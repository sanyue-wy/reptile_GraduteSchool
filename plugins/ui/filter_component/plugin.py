# -*- coding: utf-8 -*-
"""
Filter Component UI Plugin
==========================
Provides a declarative filter component for querying dataset records via
authorized API endpoints. Supports field-based filtering with configurable
operators, safe event handling, and CSP-compliant HTML rendering.

Key behaviors:
- "Start crawl" action triggers request_converter (recrawl)
- Normal filter actions do NOT trigger recrawl
- All HTML output is sanitized with CSP headers
- No arbitrary script URLs allowed
"""

import html
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from plugins.base import BasePlugin, PluginContext
from contracts.ui import ViewModel, UIComponentDTO, validate_ui_component

logger = logging.getLogger(__name__)


# ─── Allowed Operators per Field Type ───
ALLOWED_OPERATORS = {
    "string": ["eq", "neq", "contains", "not_contains", "starts_with", "ends_with", "in", "not_in"],
    "number": ["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "between"],
    "date": ["eq", "neq", "gt", "gte", "lt", "lte", "between"],
    "boolean": ["eq", "neq"],
    "enum": ["eq", "neq", "in", "not_in"],
}

# ─── CSP Policy for Filter Component ───
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "  # unsafe-inline only for inline event handlers, no external scripts
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "  # Only same-origin API calls
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


@dataclass
class FilterFieldConfig:
    """Configuration for a single filter field."""
    field_name: str
    field_type: str  # string, number, date, boolean, enum
    label: str
    operators: list[str] = field(default_factory=list)
    default_operator: str = ""
    enum_values: list[str] = field(default_factory=list)
    placeholder: str = ""
    required: bool = False

    def __post_init__(self):
        # Validate and default operators
        allowed = ALLOWED_OPERATORS.get(self.field_type, [])
        if not self.operators:
            self.operators = allowed
        else:
            # Only keep allowed operators
            self.operators = [op for op in self.operators if op in allowed]
        if not self.default_operator and self.operators:
            self.default_operator = self.operators[0]

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_name": self.field_name,
            "field_type": self.field_type,
            "label": self.label,
            "operators": self.operators,
            "default_operator": self.default_operator,
            "enum_values": self.enum_values,
            "placeholder": self.placeholder,
            "required": self.required,
        }


@dataclass
class FilterEvent:
    """Event emitted by filter component."""
    action_id: str  # "filter", "start_crawl", "reset", "export"
    params: dict[str, Any]  # Validated filter parameters
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "params": self.params,
            "timestamp": self.timestamp,
        }


class FilterComponentPlugin(BasePlugin):
    """
    UI Plugin for filter component.

    Input: ViewModel (dataset + schema + field descriptions)
    Output: UIComponentDTO (filter component declaration + events)

    Payload schema:
    - filter_fields: list of field configs (name, type, operators, etc.)
    - api_endpoint: authorized endpoint for query filtering
    - default_filters: optional initial filter values
    - enable_crawl_action: whether to show "Start crawl" button
    """

    name = "filter_component"
    version = "1.0.0"
    plugin_type = "ui"
    input_schema = "ViewModel.v1"
    output_schema = "UIComponentDTO.v1"

    # Default filter field configuration
    DEFAULT_FILTER_FIELDS = [
        FilterFieldConfig(
            field_name="name",
            field_type="string",
            label="Name",
            operators=["eq", "contains", "starts_with"],
            default_operator="contains",
            placeholder="Search by name...",
        ),
        FilterFieldConfig(
            field_name="department",
            field_type="enum",
            label="Department",
            operators=["eq", "in"],
            default_operator="eq",
            enum_values=["CS", "EE", "ME", "CE", "Math", "Physics"],
        ),
        FilterFieldConfig(
            field_name="title",
            field_type="enum",
            label="Title",
            operators=["eq", "in"],
            default_operator="eq",
            enum_values=["Professor", "Associate Professor", "Assistant Professor", "Lecturer", "Researcher"],
        ),
        FilterFieldConfig(
            field_name="research_area",
            field_type="string",
            label="Research Area",
            operators=["contains", "eq"],
            default_operator="contains",
            placeholder="e.g., Machine Learning",
        ),
        FilterFieldConfig(
            field_name="email",
            field_type="string",
            label="Email",
            operators=["contains", "ends_with"],
            default_operator="ends_with",
            placeholder="Filter by email domain...",
        ),
    ]

    def __init__(self):
        super().__init__()
        self._filter_fields: list[FilterFieldConfig] = []
        self._api_endpoint: str = ""
        self._default_filters: dict[str, Any] = {}
        self._enable_crawl_action: bool = True
        self._csp_nonce: str = ""

    def setup(self, context: PluginContext) -> None:
        """Initialize plugin with configuration from context."""
        super().setup(context)

        # Extract filter configuration from config_snapshot
        config = context.config_snapshot.get("filter_component", {})

        # Parse filter fields
        fields_config = config.get("filter_fields", [])
        if fields_config:
            self._filter_fields = [FilterFieldConfig(**fc) for fc in fields_config]
        else:
            self._filter_fields = self.DEFAULT_FILTER_FIELDS

        # API endpoint for query filtering (must be authorized)
        self._api_endpoint = config.get("api_endpoint", "/api/v1/datasets/query")

        # Default filters
        self._default_filters = config.get("default_filters", {})

        # Crawl action toggle
        self._enable_crawl_action = config.get("enable_crawl_action", True)

        # Generate CSP nonce for this session
        import secrets
        self._csp_nonce = secrets.token_urlsafe(16)

        logger.info(
            "FilterComponentPlugin initialized: fields=%d, endpoint=%s, crawl_action=%s",
            len(self._filter_fields), self._api_endpoint, self._enable_crawl_action
        )

    def execute(self, view_model: ViewModel, context: PluginContext) -> UIComponentDTO:
        """
        Build and return the filter component declaration.

        The component is rendered by approved frontend renderers.
        Events contain only action_id + validated params.
        """
        # Validate input
        if not isinstance(view_model, ViewModel):
            raise TypeError(f"Expected ViewModel, got {type(view_model)}")

        # Build field configurations from view model schema + plugin config
        field_configs = self._build_field_configs(view_model)

        # Build payload for filter component renderer
        payload = {
            "filter_fields": [fc.to_dict() for fc in field_configs],
            "api_endpoint": self._api_endpoint,
            "default_filters": self._default_filters,
            "enable_crawl_action": self._enable_crawl_action,
            "csp_nonce": self._csp_nonce,
            "dataset": view_model.dataset,
            "schema_id": view_model.schema_id,
        }

        # Declare event handlers - ONLY action_id + validated params passed
        events = [
            {
                "event": "filter",
                "action_id": "filter",
                "description": "Apply filter query to dataset",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "filters": {"type": "array", "items": {"type": "object"}},
                        "page": {"type": "integer", "minimum": 1, "default": 1},
                        "page_size": {"type": "integer", "minimum": 1, "maximum": 500, "default": 50},
                    },
                    "required": ["filters"],
                    "additionalProperties": False,
                },
            },
            {
                "event": "start_crawl",
                "action_id": "start_crawl",
                "description": "Trigger new crawl with current filters (invokes request_converter)",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "filters": {"type": "array", "items": {"type": "object"}},
                        "source_id": {"type": "string"},
                        "force_refresh": {"type": "boolean", "default": False},
                    },
                    "required": ["filters", "source_id"],
                    "additionalProperties": False,
                },
            },
            {
                "event": "reset",
                "action_id": "reset",
                "description": "Reset filters to defaults",
                "params_schema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
            {
                "event": "export",
                "action_id": "export",
                "description": "Export filtered results",
                "params_schema": {
                    "type": "object",
                    "properties": {
                        "format": {"type": "string", "enum": ["jsonl", "csv", "xlsx"]},
                        "filters": {"type": "array", "items": {"type": "object"}},
                    },
                    "required": ["format", "filters"],
                    "additionalProperties": False,
                },
            },
        ]

        # Create component DTO
        component = UIComponentDTO(
            component_id=f"filter_{view_model.dataset}_{uuid4().hex[:8]}",
            component_type="filter",
            renderer_id="filter_renderer_v1",
            payload=payload,
            data_ref=self._api_endpoint,
            events=events,
        )

        # Validate output
        validate_ui_component(component)

        logger.info(
            "Filter component created: component_id=%s, fields=%d, events=%d",
            component.component_id, len(field_configs), len(events)
        )

        return component

    def _build_field_configs(self, view_model: ViewModel) -> list[FilterFieldConfig]:
        """Merge plugin field config with view model field descriptions."""
        field_descriptions = view_model.field_descriptions or {}
        result = []

        # Start with configured fields
        for fc in self._filter_fields:
            # Enrich with view model metadata if available
            if fc.field_name in field_descriptions:
                vm_field = field_descriptions[fc.field_name]
                # Could add format, description, etc. from view model
                pass
            result.append(fc)

        # Add any additional fields from view model that aren't in config
        configured_names = {fc.field_name for fc in self._filter_fields}
        for field_name, field_info in field_descriptions.items():
            if field_name not in configured_names:
                field_type = self._infer_field_type(field_info)
                result.append(FilterFieldConfig(
                    field_name=field_name,
                    field_type=field_type,
                    label=field_info.get("label", field_name.replace("_", " ").title()),
                    operators=ALLOWED_OPERATORS.get(field_type, ["eq"]),
                    default_operator=ALLOWED_OPERATORS.get(field_type, ["eq"])[0],
                ))

        return result

    def _infer_field_type(self, field_info: dict[str, Any]) -> str:
        """Infer filter field type from view model field description."""
        fmt = field_info.get("format", "").lower()
        type_ = field_info.get("type", "").lower()

        if fmt in ("date", "date-time", "time"):
            return "date"
        if type_ in ("integer", "number", "float"):
            return "number"
        if type_ == "boolean":
            return "boolean"
        if "enum" in field_info or fmt == "enum":
            return "enum"
        return "string"

    def close(self) -> None:
        """Cleanup resources."""
        pass


# ─── Server-Side Filter Execution (for API endpoint) ───

class FilterQueryExecutor:
    """
    Executes filter queries against the dataset via authorized API.
    This would typically run in the backend API service, not in the UI plugin.
    Included here for reference and testing.
    """

    def __init__(self, api_client: Any, allowed_endpoints: list[str] = None):
        self._api_client = api_client
        self._allowed_endpoints = allowed_endpoints or ["/api/v1/datasets/query"]

    def execute_filter(
        self,
        dataset: str,
        filters: list[dict[str, Any]],
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """
        Execute filter query via authorized API endpoint.

        Args:
            dataset: Dataset identifier
            filters: List of filter conditions [{field, operator, value}]
            page: Page number (1-indexed)
            page_size: Items per page

        Returns:
            Paginated results with metadata
        """
        # Validate endpoint is allowed
        if not any(self._api_endpoint.startswith(e) for e in self._allowed_endpoints):
            raise ValueError(f"Endpoint {self._api_endpoint} not in allowed list")

        # Validate filters
        validated_filters = self._validate_filters(filters)

        # Build query payload
        payload = {
            "dataset": dataset,
            "filters": validated_filters,
            "page": page,
            "page_size": min(page_size, 500),
        }

        # Execute via authorized API client
        response = self._api_client.post(self._api_endpoint, json=payload)
        response.raise_for_status()

        return response.json()

    def _validate_filters(self, filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Validate filter conditions against allowed operators."""
        validated = []
        for f in filters:
            field = f.get("field")
            operator = f.get("operator")
            value = f.get("value")

            if not field or not operator:
                raise ValueError("Filter must have 'field' and 'operator'")

            # TODO: Look up field type from schema registry
            # For now, allow all string operators as fallback
            allowed = ALLOWED_OPERATORS.get("string", [])
            if operator not in allowed:
                raise ValueError(f"Operator '{operator}' not allowed for field '{field}'")

            validated.append({"field": field, "operator": operator, "value": value})

        return validated


# ─── HTML Rendering Helpers (CSP-Safe) ───

def render_filter_html(component: UIComponentDTO, csp_nonce: str = "") -> str:
    """
    Generate CSP-compliant HTML for filter component.

    NO arbitrary script URLs - only inline scripts with nonce.
    All event handlers use data-action attributes, not onclick.
    """
    payload = component.payload
    filter_fields = payload.get("filter_fields", [])
    api_endpoint = html.escape(payload.get("api_endpoint", ""))
    default_filters = payload.get("default_filters", {})
    enable_crawl = payload.get("enable_crawl_action", True)

    nonce_attr = f' nonce="{csp_nonce}"' if csp_nonce else ""

    # Build filter fields HTML
    fields_html = []
    for fc in filter_fields:
        field_name = html.escape(fc["field_name"])
        label = html.escape(fc["label"])
        field_type = fc["field_type"]
        operators = fc["operators"]
        default_op = fc["default_operator"]
        placeholder = html.escape(fc.get("placeholder", ""))
        enum_values = fc.get("enum_values", [])
        required = fc.get("required", False)

        # Operator select
        ops_html = "".join(
            f'<option value="{html.escape(op)}"{" selected" if op == default_op else ""}>'
            f'{_operator_label(op)}</option>'
            for op in operators
        )

        # Value input based on field type
        default_val = html.escape(str(default_filters.get(field_name, "")))

        if field_type == "enum" and enum_values:
            # Enum uses select
            vals_html = "".join(
                f'<option value="{html.escape(v)}"{" selected" if v == default_val else ""}>'
                f'{html.escape(v)}</option>'
                for v in enum_values
            )
            value_html = (
                f'<select name="value" class="filter-value" data-field="{field_name}" '
                f'data-type="{field_type}">{vals_html}</select>'
            )
        elif field_type == "boolean":
            value_html = (
                f'<select name="value" class="filter-value" data-field="{field_name}" data-type="boolean">'
                f'<option value="true"{" selected" if default_val == "true" else ""}>Yes</option>'
                f'<option value="false"{" selected" if default_val == "false" else ""}>No</option>'
                f'</select>'
            )
        elif field_type == "date":
            value_html = (
                f'<input type="date" name="value" class="filter-value" '
                f'data-field="{field_name}" data-type="date" value="{default_val}" '
                f'placeholder="{placeholder}">'
            )
        elif field_type == "number":
            value_html = (
                f'<input type="number" name="value" class="filter-value" '
                f'data-field="{field_name}" data-type="number" value="{default_val}" '
                f'placeholder="{placeholder}" step="any">'
            )
        else:
            value_html = (
                f'<input type="text" name="value" class="filter-value" '
                f'data-field="{field_name}" data-type="string" value="{default_val}" '
                f'placeholder="{placeholder}">'
            )

        field_html = f'''
        <div class="filter-field" data-field="{field_name}" data-type="{field_type}">
            <label for="filter-op-{field_name}">{label}</label>
            <select name="operator" id="filter-op-{field_name}" class="filter-operator" data-field="{field_name}">
                {ops_html}
            </select>
            {value_html}
            <button type="button" class="filter-remove" data-field="{field_name}" aria-label="Remove filter">×</button>
        </div>
        '''
        fields_html.append(field_html)

    fields_html_str = "\n".join(fields_html)

    # Action buttons
    crawl_btn = ""
    if enable_crawl:
        crawl_btn = '''
        <button type="button" class="filter-action filter-crawl" data-action="start_crawl">
            Start Crawl
        </button>
        '''

    html_template = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="csp-nonce" content="{html.escape(csp_nonce)}">
    <title>Filter Component</title>
    <style nonce="{html.escape(csp_nonce)}">
        .filter-component {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 1rem; }}
        .filter-fields {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }}
        .filter-field {{ display: flex; align-items: center; gap: 0.375rem; flex: 1; min-width: 200px; }}
        .filter-field label {{ font-weight: 500; white-space: nowrap; }}
        .filter-field select, .filter-field input {{ padding: 0.375rem 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 0.875rem; }}
        .filter-field select.filter-operator {{ width: 120px; }}
        .filter-field input.filter-value {{ flex: 1; min-width: 120px; }}
        .filter-field .filter-remove {{ padding: 0.375rem 0.5rem; background: #fee; border: 1px solid #fcc; border-radius: 4px; cursor: pointer; }}
        .filter-actions {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
        .filter-action {{ padding: 0.5rem 1rem; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 0.875rem; }}
        .filter-action.filter-crawl {{ background: #0066cc; color: #fff; border-color: #0055aa; }}
        .filter-action.filter-crawl:hover {{ background: #0055aa; }}
        .filter-action:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    </style>
</head>
<body>
    <div class="filter-component" data-component-id="{html.escape(component.component_id)}" data-api-endpoint="{api_endpoint}">
        <div class="filter-fields" id="filter-fields-container">
            {fields_html_str}
        </div>
        <div class="filter-actions">
            <button type="button" class="filter-action" data-action="filter">Apply Filter</button>
            <button type="button" class="filter-action" data-action="reset">Reset</button>
            <button type="button" class="filter-action" data-action="export">Export</button>
            {crawl_btn}
        </div>
    </div>
    <script{nonce_attr}>
        (function() {{
            const component = document.querySelector('.filter-component');
            const apiEndpoint = component.dataset.apiEndpoint;

            function collectFilters() {{
                const filters = [];
                document.querySelectorAll('.filter-field').forEach(field => {{
                    const fieldName = field.dataset.field;
                    const operator = field.querySelector('.filter-operator').value;
                    const valueEl = field.querySelector('.filter-value');
                    if (!valueEl) return;
                    const value = valueEl.value;
                    if (value === '' && valueEl.type !== 'checkbox') return;
                    filters.push({{ field: fieldName, operator, value }});
                }});
                return filters;
            }}

            function emitEvent(actionId, params) {{
                // In real implementation, this would call the registered event handler
                // For now, we log and could post to the API endpoint
                console.log('Filter event:', actionId, params);

                if (actionId === 'filter') {{
                    fetch(apiEndpoint, {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        credentials: 'same-origin',
                        body: JSON.stringify({{
                            dataset: component.dataset,
                            filters: params.filters,
                            page: params.page || 1,
                            page_size: params.page_size || 50
                        }})
                    }}).then(r => r.json()).then(data => {{
                        console.log('Filter results:', data);
                        // Trigger table update via custom event
                        window.dispatchEvent(new CustomEvent('filter-results', {{ detail: data }}));
                    }}).catch(err => console.error('Filter error:', err));
                }} else if (actionId === 'start_crawl') {{
                    // Triggers request_converter - recrawl
                    fetch('/api/v1/crawl/start', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        credentials: 'same-origin',
                        body: JSON.stringify({{
                            source_id: params.source_id,
                            filters: params.filters,
                            force_refresh: params.force_refresh || false
                        }})
                    }}).then(r => r.json()).then(data => {{
                        console.log('Crawl started:', data);
                    }}).catch(err => console.error('Crawl error:', err));
                }}
            }}

            // Event delegation for action buttons
            component.addEventListener('click', (e) => {{
                const btn = e.target.closest('[data-action]');
                if (!btn) return;

                const action = btn.dataset.action;
                const filters = collectFilters();

                if (action === 'filter') {{
                    emitEvent('filter', {{ filters, page: 1, page_size: 50 }});
                }} else if (action === 'reset') {{
                    document.querySelectorAll('.filter-value').forEach(el => el.value = '');
                    emitEvent('reset', {{}});
                }} else if (action === 'export') {{
                    emitEvent('export', {{ format: 'jsonl', filters }});
                }} else if (action === 'start_crawl') {{
                    // Source ID would come from context
                    emitEvent('start_crawl', {{ filters, source_id: 'default', force_refresh: false }});
                }}
            }});
        }})();
    </script>
</body>
</html>'''

    return html_template


def _operator_label(op: str) -> str:
    """Get human-readable label for operator."""
    labels = {
        "eq": "Equals",
        "neq": "Not Equals",
        "contains": "Contains",
        "not_contains": "Not Contains",
        "starts_with": "Starts With",
        "ends_with": "Ends With",
        "gt": "Greater Than",
        "gte": "Greater Than or Equal",
        "lt": "Less Than",
        "lte": "Less Than or Equal",
        "in": "In",
        "not_in": "Not In",
        "between": "Between",
    }
    return labels.get(op, op)


def generate_csp_header(nonce: str) -> str:
    """Generate CSP header with nonce for inline scripts."""
    return CSP_POLICY.replace("'unsafe-inline'", f"'nonce-{nonce}'")


def validate_filter_params(params: dict[str, Any], field_configs: list[FilterFieldConfig]) -> dict[str, Any]:
    """
    Validate filter parameters from client.

    Returns validated params dict or raises ValueError.
    """
    action_id = params.get("action_id")
    if not action_id:
        raise ValueError("Missing action_id")

    # Validate filters array
    filters = params.get("filters", [])
    if not isinstance(filters, list):
        raise ValueError("filters must be an array")

    field_map = {fc.field_name: fc for fc in field_configs}
    validated_filters = []

    for f in filters:
        field = f.get("field")
        operator = f.get("operator")
        value = f.get("value")

        if not field or not operator:
            raise ValueError("Each filter must have 'field' and 'operator'")

        if field not in field_map:
            raise ValueError(f"Unknown filter field: {field}")

        fc = field_map[field]
        if operator not in fc.operators:
            raise ValueError(f"Operator '{operator}' not allowed for field '{field}'")

        # Type-specific validation
        if fc.field_type == "number":
            try:
                value = float(value)
            except (TypeError, ValueError):
                raise ValueError(f"Field '{field}' expects a number")
        elif fc.field_type == "boolean":
            if isinstance(value, str):
                value = value.lower() in ("true", "1", "yes")
            elif not isinstance(value, bool):
                raise ValueError(f"Field '{field}' expects a boolean")
        elif fc.field_type == "date":
            if isinstance(value, str):
                # Validate ISO date format
                if not re.match(r"^\d{4}-\d{2}-\d{2}$", value):
                    raise ValueError(f"Field '{field}' expects YYYY-MM-DD format")

        validated_filters.append({"field": field, "operator": operator, "value": value})

    return {
        "action_id": action_id,
        "filters": validated_filters,
        "page": params.get("page", 1),
        "page_size": min(params.get("page_size", 50), 500),
        "source_id": params.get("source_id"),
        "force_refresh": params.get("force_refresh", False),
        "format": params.get("format", "jsonl"),
    }


# ─── Export for Plugin Registry ───

__all__ = [
    "FilterComponentPlugin",
    "FilterFieldConfig",
    "FilterEvent",
    "FilterQueryExecutor",
    "render_filter_html",
    "generate_csp_header",
    "validate_filter_params",
    "ALLOWED_OPERATORS",
    "CSP_POLICY",
]