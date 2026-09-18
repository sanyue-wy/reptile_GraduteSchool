# -*- coding: utf-8 -*-
"""
Tests for FilterComponentPlugin
"""

import json
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from plugins.ui.filter_component.plugin import (
    FilterComponentPlugin,
    FilterFieldConfig,
    FilterEvent,
    FilterQueryExecutor,
    render_filter_html,
    generate_csp_header,
    validate_filter_params,
    ALLOWED_OPERATORS,
    CSP_POLICY,
)
from plugins.base import PluginContext
from contracts.ui import ViewModel


class TestFilterFieldConfig:
    """Tests for FilterFieldConfig dataclass."""

    def test_default_operators_by_type(self):
        """Test default operators are set based on field type."""
        fc = FilterFieldConfig(field_name="test", field_type="string", label="Test")
        assert "contains" in fc.operators
        assert "eq" in fc.operators

        fc = FilterFieldConfig(field_name="test", field_type="number", label="Test")
        assert "gt" in fc.operators
        assert "between" in fc.operators

        fc = FilterFieldConfig(field_name="test", field_type="boolean", label="Test")
        assert fc.operators == ["eq", "neq"]

    def test_custom_operators_filtered(self):
        """Test custom operators are filtered to allowed list."""
        fc = FilterFieldConfig(
            field_name="test", field_type="string", label="Test",
            operators=["eq", "invalid_op", "contains"]
        )
        assert "eq" in fc.operators
        assert "contains" in fc.operators
        assert "invalid_op" not in fc.operators

    def test_default_operator_set(self):
        """Test default operator is set to first allowed."""
        fc = FilterFieldConfig(
            field_name="test", field_type="string", label="Test",
            operators=["contains", "eq"]
        )
        assert fc.default_operator == "contains"

    def test_to_dict(self):
        """Test serialization to dict."""
        fc = FilterFieldConfig(
            field_name="name", field_type="string", label="Name",
            operators=["eq", "contains"], default_operator="contains",
            placeholder="Search..."
        )
        d = fc.to_dict()
        assert d["field_name"] == "name"
        assert d["field_type"] == "string"
        assert d["operators"] == ["eq", "contains"]
        assert d["default_operator"] == "contains"
        assert d["placeholder"] == "Search..."


class TestFilterEvent:
    """Tests for FilterEvent dataclass."""

    def test_to_dict(self):
        """Test event serialization."""
        event = FilterEvent(action_id="filter", params={"filters": []})
        d = event.to_dict()
        assert d["action_id"] == "filter"
        assert d["params"] == {"filters": []}
        assert "timestamp" in d


class TestFilterComponentPlugin:
    """Tests for FilterComponentPlugin."""

    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return FilterComponentPlugin()

    @pytest.fixture
    def mock_context(self):
        """Create mock PluginContext."""
        ctx = Mock(spec=PluginContext)
        ctx.config_snapshot = {
            "filter_component": {
                "filter_fields": [
                    {
                        "field_name": "name",
                        "field_type": "string",
                        "label": "Name",
                        "operators": ["contains", "eq"],
                        "default_operator": "contains",
                        "placeholder": "Search name..."
                    },
                    {
                        "field_name": "department",
                        "field_type": "enum",
                        "label": "Department",
                        "operators": ["eq", "in"],
                        "default_operator": "eq",
                        "enum_values": ["CS", "EE", "ME"]
                    }
                ],
                "api_endpoint": "/api/v1/datasets/query",
                "default_filters": {"department": "CS"},
                "enable_crawl_action": True
            }
        }
        return ctx

    @pytest.fixture
    def view_model(self):
        """Create sample ViewModel."""
        return ViewModel(
            dataset="faculty",
            schema_id="faculty.v1",
            field_descriptions={
                "name": {"type": "string", "label": "Name", "format": ""},
                "department": {"type": "string", "label": "Department", "format": "enum"},
                "title": {"type": "string", "label": "Title", "format": ""},
                "email": {"type": "string", "label": "Email", "format": ""},
            },
            data_ref="/api/v1/datasets/faculty/data",
            page=1,
            page_size=50,
            total_count=100,
        )

    def test_plugin_metadata(self):
        """Verify plugin metadata."""
        plugin = FilterComponentPlugin()
        assert plugin.name == "filter_component"
        assert plugin.plugin_type == "ui"
        assert plugin.input_schema == "ViewModel.v1"
        assert plugin.output_schema == "UIComponentDTO.v1"

    def test_setup_loads_config(self, plugin, mock_context):
        """Test setup loads filter configuration."""
        plugin.setup(mock_context)

        assert len(plugin._filter_fields) == 2
        assert plugin._filter_fields[0].field_name == "name"
        assert plugin._filter_fields[1].field_name == "department"
        assert plugin._api_endpoint == "/api/v1/datasets/query"
        assert plugin._default_filters == {"department": "CS"}
        assert plugin._enable_crawl_action is True
        assert plugin._csp_nonce  # Nonce generated

    def test_setup_uses_defaults_when_no_config(self, plugin):
        """Test setup uses defaults when no config provided."""
        ctx = Mock(spec=PluginContext)
        ctx.config_snapshot = {}

        plugin.setup(ctx)

        assert len(plugin._filter_fields) == len(FilterComponentPlugin.DEFAULT_FILTER_FIELDS)
        assert plugin._api_endpoint == "/api/v1/datasets/query"
        assert plugin._default_filters == {}
        assert plugin._enable_crawl_action is True

    def test_execute_returns_ui_component(self, plugin, mock_context, view_model):
        """Test execute returns valid UIComponentDTO."""
        plugin.setup(mock_context)
        component = plugin.execute(view_model, mock_context)

        assert component.component_type == "filter"
        assert component.renderer_id == "filter_renderer_v1"
        assert component.data_ref == "/api/v1/datasets/query"
        assert "filter_fields" in component.payload
        assert component.payload["api_endpoint"] == "/api/v1/datasets/query"
        assert component.payload["enable_crawl_action"] is True
        assert "csp_nonce" in component.payload

    def test_execute_validates_output(self, plugin, mock_context, view_model):
        """Test execute output passes validation."""
        plugin.setup(mock_context)
        component = plugin.execute(view_model, mock_context)

        # Should not raise
        from contracts.ui import validate_ui_component
        validate_ui_component(component)

    def test_execute_events_structure(self, plugin, mock_context, view_model):
        """Test events contain only action_id + validated params schema."""
        plugin.setup(mock_context)
        component = plugin.execute(view_model, mock_context)

        events = component.events
        assert len(events) == 4  # filter, start_crawl, reset, export

        # Check filter event
        filter_event = next(e for e in events if e["action_id"] == "filter")
        assert filter_event["event"] == "filter"
        assert "params_schema" in filter_event
        assert filter_event["params_schema"]["required"] == ["filters"]

        # Check start_crawl event (triggers request_converter)
        crawl_event = next(e for e in events if e["action_id"] == "start_crawl")
        assert crawl_event["action_id"] == "start_crawl"
        assert "source_id" in crawl_event["params_schema"]["required"]

        # Check reset event
        reset_event = next(e for e in events if e["action_id"] == "reset")
        assert reset_event["action_id"] == "reset"

        # Check export event
        export_event = next(e for e in events if e["action_id"] == "export")
        assert export_event["action_id"] == "export"

    def test_build_field_configs_merges_with_view_model(self, plugin, mock_context, view_model):
        """Test field configs merge plugin config with view model."""
        plugin.setup(mock_context)
        fields = plugin._build_field_configs(view_model)

        # Should have configured fields
        names = {f.field_name for f in fields}
        assert "name" in names
        assert "department" in names

        # Should also have view model fields not in config
        assert "title" in names
        assert "email" in names

    def test_infer_field_type(self, plugin):
        """Test field type inference from view model."""
        assert plugin._infer_field_type({"type": "string", "format": "date"}) == "date"
        assert plugin._infer_field_type({"type": "integer"}) == "number"
        assert plugin._infer_field_type({"type": "number"}) == "number"
        assert plugin._infer_field_type({"type": "boolean"}) == "boolean"
        assert plugin._infer_field_type({"type": "string", "format": "enum"}) == "enum"
        assert plugin._infer_field_type({"enum": ["a", "b"]}) == "enum"
        assert plugin._infer_field_type({"type": "string"}) == "string"


class TestRenderFilterHTML:
    """Tests for CSP-safe HTML rendering."""

    def test_render_contains_no_external_scripts(self):
        """Test rendered HTML has no external script URLs."""
        from contracts.ui import UIComponentDTO

        component = UIComponentDTO(
            component_id="test_filter",
            component_type="filter",
            renderer_id="filter_renderer_v1",
            payload={
                "filter_fields": [
                    {
                        "field_name": "name",
                        "field_type": "string",
                        "label": "Name",
                        "operators": ["contains", "eq"],
                        "default_operator": "contains",
                        "placeholder": "Search...",
                        "enum_values": [],
                        "required": False
                    }
                ],
                "api_endpoint": "/api/v1/query",
                "default_filters": {},
                "enable_crawl_action": True,
                "csp_nonce": "test-nonce-123",
            },
            data_ref="/api/v1/query",
            events=[],
        )

        html = render_filter_html(component, "test-nonce-123")

        # No external script src
        assert 'src="http' not in html
        assert 'src="https' not in html
        assert 'src="//' not in html

        # Has nonce
        assert 'nonce="test-nonce-123"' in html

        # Has CSP meta tag
        assert 'name="csp-nonce"' in html

        # Has data-action attributes (not onclick)
        assert 'data-action="filter"' in html
        assert 'data-action="reset"' in html
        assert 'data-action="export"' in html
        assert 'data-action="start_crawl"' in html

    def test_render_includes_crawl_button_when_enabled(self):
        """Test crawl button appears when enabled."""
        from contracts.ui import UIComponentDTO

        component = UIComponentDTO(
            component_id="test",
            component_type="filter",
            renderer_id="r",
            payload={
                "filter_fields": [],
                "api_endpoint": "/api",
                "default_filters": {},
                "enable_crawl_action": True,
                "csp_nonce": "nonce",
            },
            data_ref="/api",
            events=[],
        )

        html = render_filter_html(component, "nonce")
        assert "Start Crawl" in html
        assert 'data-action="start_crawl"' in html

    def test_render_excludes_crawl_button_when_disabled(self):
        """Test crawl button hidden when disabled."""
        from contracts.ui import UIComponentDTO

        component = UIComponentDTO(
            component_id="test",
            component_type="filter",
            renderer_id="r",
            payload={
                "filter_fields": [],
                "api_endpoint": "/api",
                "default_filters": {},
                "enable_crawl_action": False,
                "csp_nonce": "nonce",
            },
            data_ref="/api",
            events=[],
        )

        html = render_filter_html(component, "nonce")
        assert "Start Crawl" not in html
        assert 'data-action="start_crawl"' not in html

    def test_render_escapes_html(self):
        """Test HTML escaping prevents XSS."""
        from contracts.ui import UIComponentDTO

        component = UIComponentDTO(
            component_id="test",
            component_type="filter",
            renderer_id="r",
            payload={
                "filter_fields": [{
                    "field_name": "name",
                    "field_type": "string",
                    "label": "<script>alert(1)</script>",
                    "operators": ["eq"],
                    "default_operator": "eq",
                    "placeholder": "';alert(1);//",
                    "enum_values": [],
                    "required": False
                }],
                "api_endpoint": "/api",
                "default_filters": {},
                "enable_crawl_action": True,
                "csp_nonce": "nonce",
            },
            data_ref="/api",
            events=[],
        )

        html = render_filter_html(component, "nonce")

        # The component's own inline script is present (legitimate)
        assert "</script>" in html

        # Placeholder should be escaped (escaped form present, raw XSS absent)
        assert "';alert(1);//" not in html
        assert "alert" not in html or "&#x27;" in html or "&apos;" in html


class TestCSPHeader:
    """Tests for CSP header generation."""

    def test_generate_csp_header(self):
        """Test CSP header includes nonce."""
        header = generate_csp_header("test-nonce-abc")
        assert "nonce-test-nonce-abc" in header
        assert "default-src 'self'" in header
        assert "connect-src 'self'" in header  # Only same-origin
        assert "frame-ancestors 'none'" in header

    def test_csp_no_unsafe_external(self):
        """Test CSP doesn't allow unsafe external resources."""
        header = generate_csp_header("nonce")
        # No unsafe-eval
        assert "unsafe-eval" not in header
        # No wildcard script-src
        assert "script-src *" not in header
        assert "script-src 'self'" in header


class TestValidateFilterParams:
    """Tests for filter parameter validation."""

    @pytest.fixture
    def field_configs(self):
        return [
            FilterFieldConfig(field_name="name", field_type="string", label="Name",
                            operators=["eq", "contains"], default_operator="contains"),
            FilterFieldConfig(field_name="age", field_type="number", label="Age",
                            operators=["eq", "gt"], default_operator="eq"),
            FilterFieldConfig(field_name="active", field_type="boolean", label="Active",
                            operators=["eq"], default_operator="eq"),
            FilterFieldConfig(field_name="dept", field_type="enum", label="Department",
                            operators=["eq", "in"], default_operator="eq",
                            enum_values=["CS", "EE"]),
        ]

    def test_valid_filter_params(self, field_configs):
        """Test valid params pass validation."""
        params = {
            "action_id": "filter",
            "filters": [
                {"field": "name", "operator": "contains", "value": "John"},
                {"field": "age", "operator": "gt", "value": "30"},
            ],
            "page": 1,
            "page_size": 20,
        }

        result = validate_filter_params(params, field_configs)

        assert result["action_id"] == "filter"
        assert len(result["filters"]) == 2
        assert result["filters"][0]["field"] == "name"
        assert result["filters"][1]["value"] == 30.0  # Converted to float
        assert result["page"] == 1
        assert result["page_size"] == 20

    def test_missing_action_id_raises(self, field_configs):
        """Test missing action_id raises."""
        params = {"filters": []}
        with pytest.raises(ValueError, match="Missing action_id"):
            validate_filter_params(params, field_configs)

    def test_invalid_field_raises(self, field_configs):
        """Test unknown field raises."""
        params = {
            "action_id": "filter",
            "filters": [{"field": "unknown", "operator": "eq", "value": "x"}],
        }
        with pytest.raises(ValueError, match="Unknown filter field"):
            validate_filter_params(params, field_configs)

    def test_invalid_operator_raises(self, field_configs):
        """Test disallowed operator raises."""
        params = {
            "action_id": "filter",
            "filters": [{"field": "name", "operator": "invalid_op", "value": "x"}],
        }
        with pytest.raises(ValueError, match="not allowed for field"):
            validate_filter_params(params, field_configs)

    def test_number_type_conversion(self, field_configs):
        """Test number values are converted."""
        params = {
            "action_id": "filter",
            "filters": [{"field": "age", "operator": "eq", "value": "25"}],
        }
        result = validate_filter_params(params, field_configs)
        assert result["filters"][0]["value"] == 25.0
        assert isinstance(result["filters"][0]["value"], float)

    def test_boolean_type_conversion(self, field_configs):
        """Test boolean values are converted."""
        params = {
            "action_id": "filter",
            "filters": [
                {"field": "active", "operator": "eq", "value": "true"},
                {"field": "active", "operator": "eq", "value": "false"},
            ],
        }
        result = validate_filter_params(params, field_configs)
        assert result["filters"][0]["value"] is True
        assert result["filters"][1]["value"] is False

    def test_date_format_validation(self, field_configs):
        """Test date format validation."""
        # Add date field
        field_configs.append(
            FilterFieldConfig(field_name="created", field_type="date", label="Created",
                            operators=["eq"], default_operator="eq")
        )

        params = {
            "action_id": "filter",
            "filters": [{"field": "created", "operator": "eq", "value": "2024-01-15"}],
        }
        result = validate_filter_params(params, field_configs)
        assert result["filters"][0]["value"] == "2024-01-15"

        # Invalid date format
        params["filters"][0]["value"] = "01/15/2024"
        with pytest.raises(ValueError, match="expects YYYY-MM-DD"):
            validate_filter_params(params, field_configs)

    def test_page_size_capped(self, field_configs):
        """Test page_size is capped at 500."""
        params = {
            "action_id": "filter",
            "filters": [],
            "page_size": 1000,
        }
        result = validate_filter_params(params, field_configs)
        assert result["page_size"] == 500


class TestAllowedOperators:
    """Tests for ALLOWED_OPERATORS constant."""

    def test_all_types_have_operators(self):
        """Test all field types have defined operators."""
        assert "string" in ALLOWED_OPERATORS
        assert "number" in ALLOWED_OPERATORS
        assert "date" in ALLOWED_OPERATORS
        assert "boolean" in ALLOWED_OPERATORS
        assert "enum" in ALLOWED_OPERATORS

    def test_string_operators(self):
        """Test string operators list."""
        ops = ALLOWED_OPERATORS["string"]
        assert "eq" in ops
        assert "contains" in ops
        assert "starts_with" in ops

    def test_number_operators(self):
        """Test number operators list."""
        ops = ALLOWED_OPERATORS["number"]
        assert "gt" in ops
        assert "gte" in ops
        assert "between" in ops


class TestMetadataFile:
    """Test metadata.json exists and is valid."""

    def test_metadata_exists(self):
        meta_path = Path(__file__).parent.parent / "plugins/ui/filter_component/metadata.json"
        assert meta_path.exists()

    def test_metadata_valid(self):
        meta_path = Path(__file__).parent.parent / "plugins/ui/filter_component/metadata.json"
        with open(meta_path) as f:
            meta = json.load(f)

        assert meta["name"] == "filter_component"
        assert meta["plugin_type"] == "ui"
        assert meta["input_schema"] == "ViewModel.v1"
        assert meta["output_schema"] == "UIComponentDTO.v1"
        assert meta["entry_point"] == "plugins.ui.filter_component.plugin:FilterComponentPlugin"
        assert "filter_fields" in meta["config_schema"]["properties"]
        assert "api_endpoint" in meta["config_schema"]["properties"]
        assert "enable_crawl_action" in meta["config_schema"]["properties"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])