# -*- coding: utf-8 -*-
"""
Tests for UI Component Plugins (W7)
=====================================
Covers all 4 UI component plugins:
  - table_component
  - chart_component
  - card_component
  - filter_component

Each component: normal execute, payload validation, field inference,
renderer manifest, empty ViewModel.
"""

import json
from unittest.mock import Mock, MagicMock
from uuid import uuid4

import pytest

from contracts.ui import ViewModel, UIComponentDTO


# ─── Fixtures ─────────────────────────────────────────────────────────────


def _make_view_model(
    dataset="test_dataset",
    schema_id="education.tutor.v1",
    field_descriptions=None,
    data_ref="/api/data/test_dataset",
    total_count=10,
):
    if field_descriptions is None:
        field_descriptions = {
            "name": {"type": "string", "label": "Name"},
            "title": {"type": "string", "label": "Title"},
            "university": {"type": "string", "label": "University"},
            "year": {"type": "integer", "label": "Year"},
            "count": {"type": "number", "label": "Count"},
        }
    return ViewModel(
        dataset=dataset,
        schema_id=schema_id,
        field_descriptions=field_descriptions,
        data_ref=data_ref,
        total_count=total_count,
        page=1,
        page_size=50,
    )


class MockContext:
    def __init__(self):
        self.config_snapshot = {"plugins": {}}
        self.logger = Mock()


@pytest.fixture
def mock_ctx():
    return MockContext()


# ─── Table Component ─────────────────────────────────────────────────────


class TestTableComponent:
    def test_basic_execute(self, mock_ctx):
        from plugins.ui.table_component.plugin import TableComponentPlugin

        p = TableComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        assert isinstance(result, UIComponentDTO)
        assert result.component_type == "table"
        assert result.renderer_id == "table_renderer_v1"
        assert len(result.payload["columns"]) >= 2
        assert result.payload["pagination"] is True

    def test_custom_columns(self, mock_ctx):
        from plugins.ui.table_component.plugin import TableComponentPlugin

        mock_ctx.config_snapshot["plugins"]["table_component"] = {
            "columns": ["name", "title"],
        }
        p = TableComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        col_fields = [c["field"] for c in result.payload["columns"]]
        assert "name" in col_fields
        assert "title" in col_fields
        assert "university" not in col_fields

    def test_empty_field_descriptions(self, mock_ctx):
        from plugins.ui.table_component.plugin import TableComponentPlugin

        p = TableComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model(field_descriptions={})
        result = p.execute(vm, mock_ctx)

        assert result.component_type == "table"
        assert len(result.payload["columns"]) > 0

    def test_events_declared(self, mock_ctx):
        from plugins.ui.table_component.plugin import TableComponentPlugin

        p = TableComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        event_types = [e["event"] for e in result.events]
        assert "sort" in event_types
        assert "page_change" in event_types

    def test_renderer_manifest(self):
        from plugins.ui.table_component.plugin import TABLE_RENDERER_MANIFEST

        assert TABLE_RENDERER_MANIFEST["renderer_id"] == "table_renderer_v1"
        assert TABLE_RENDERER_MANIFEST["component_type"] == "table"
        assert TABLE_RENDERER_MANIFEST["approved"] is True
        assert "sort" in TABLE_RENDERER_MANIFEST["capabilities"]


# ─── Chart Component ─────────────────────────────────────────────────────


class TestChartComponent:
    def test_basic_execute(self, mock_ctx):
        from plugins.ui.chart_component.plugin import ChartComponentPlugin

        p = ChartComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        assert isinstance(result, list)
        assert len(result) > 0
        comp = result[0]
        assert isinstance(comp, UIComponentDTO)
        assert comp.component_type == "chart"
        assert comp.renderer_id == "chartjs_v4"

    def test_explicit_chart_config(self, mock_ctx):
        from plugins.ui.chart_component.plugin import ChartComponentPlugin

        p = ChartComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        vm.run_state = {
            "charts": [
                {"chart_type": "pie", "x_field": "university", "y_field": "count"}
            ]
        }
        result = p.execute(vm, mock_ctx)

        assert len(result) == 1
        assert result[0].payload["chart_type"] == "pie"

    def test_chart_payload_validation(self):
        from plugins.ui.chart_component.plugin import ChartPayload

        payload = ChartPayload.validate({
            "chart_type": "bar",
            "x_field": "name",
            "y_field": "count",
        })
        assert payload.chart_type == "bar"
        assert payload.x_field == "name"

    def test_invalid_chart_type(self):
        from plugins.ui.chart_component.plugin import ChartPayload

        with pytest.raises(Exception):
            ChartPayload.validate({
                "chart_type": "invalid",
                "x_field": "name",
                "y_field": "count",
            })

    def test_no_numeric_fields(self, mock_ctx):
        from plugins.ui.chart_component.plugin import ChartComponentPlugin

        p = ChartComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model(field_descriptions={
            "name": {"type": "string", "label": "Name"},
            "title": {"type": "string", "label": "Title"},
        })
        result = p.execute(vm, mock_ctx)
        # May return empty list or a default chart
        assert isinstance(result, list)

    def test_renderer_manifest(self):
        from plugins.ui.chart_component.plugin import ChartComponentPlugin

        p = ChartComponentPlugin()
        manifest = p.get_renderer_manifest()
        assert manifest["renderer_id"] == "chartjs_v4"
        assert "bar" in manifest["supported_types"]


# ─── Card Component ──────────────────────────────────────────────────────


class TestCardComponent:
    def test_basic_execute(self, mock_ctx):
        from plugins.ui.card_component.plugin import CardComponentPlugin

        mock_ctx.config_snapshot["plugins"]["card_component"] = {
            "card_fields": ["name", "title", "university"],
        }
        p = CardComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        assert isinstance(result, UIComponentDTO)
        assert result.component_type == "card"
        assert result.renderer_id == "plain_js_template"
        assert result.payload["card_fields"] == ["name", "title", "university"]

    def test_inferred_card_fields(self, mock_ctx):
        from plugins.ui.card_component.plugin import CardComponentPlugin

        p = CardComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        assert len(result.payload["card_fields"]) > 0

    def test_payload_schema_validation(self):
        from plugins.ui.card_component.plugin import CardComponentPayload, CARD_COMPONENT_PAYLOAD_SCHEMA
        import jsonschema

        payload = CardComponentPayload(card_fields=["name", "title"])
        jsonschema.validate(payload.to_dict(), CARD_COMPONENT_PAYLOAD_SCHEMA)

    def test_card_layout_options(self, mock_ctx):
        from plugins.ui.card_component.plugin import CardComponentPlugin

        mock_ctx.config_snapshot["plugins"]["card_component"] = {
            "card_fields": ["name"],
            "card_layout": "horizontal",
        }
        p = CardComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        assert result.payload["card_layout"] == "horizontal"

    def test_renderer_manifest(self):
        from plugins.ui.card_component.plugin import CARD_RENDERER_MANIFEST

        assert CARD_RENDERER_MANIFEST["renderer_id"] == "plain_js_template"
        assert CARD_RENDERER_MANIFEST["component_type"] == "card"
        assert "registerRenderer" in CARD_RENDERER_MANIFEST["template"]


# ─── Filter Component ────────────────────────────────────────────────────


class TestFilterComponent:
    def test_basic_execute(self, mock_ctx):
        from plugins.ui.filter_component.plugin import FilterComponentPlugin

        p = FilterComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        assert isinstance(result, UIComponentDTO)
        assert result.component_type == "filter"
        assert result.renderer_id == "filter_renderer_v1"
        assert "filter_fields" in result.payload
        assert len(result.payload["filter_fields"]) > 0

    def test_events_declared(self, mock_ctx):
        from plugins.ui.filter_component.plugin import FilterComponentPlugin

        p = FilterComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        event_ids = [e["action_id"] for e in result.events]
        assert "filter" in event_ids
        assert "reset" in event_ids

    def test_crawl_action_enabled(self, mock_ctx):
        from plugins.ui.filter_component.plugin import FilterComponentPlugin

        p = FilterComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        event_ids = [e["action_id"] for e in result.events]
        assert "start_crawl" in event_ids

    def test_crawl_action_disabled(self, mock_ctx):
        from plugins.ui.filter_component.plugin import FilterComponentPlugin

        mock_ctx.config_snapshot["filter_component"] = {"enable_crawl_action": False}
        p = FilterComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        # crawl action still in events list (component declares all possible events)
        # but the payload flag disables it in UI
        assert result.payload.get("enable_crawl_action") is False

    def test_custom_filter_fields(self, mock_ctx):
        from plugins.ui.filter_component.plugin import FilterComponentPlugin

        mock_ctx.config_snapshot["filter_component"] = {
            "filter_fields": [
                {"field_name": "name", "field_type": "string", "label": "Name"},
            ]
        }
        p = FilterComponentPlugin()
        p.setup(mock_ctx)
        vm = _make_view_model()
        result = p.execute(vm, mock_ctx)

        # Configured field is included, plus ViewModel-derived fields are merged
        field_names = [f["field_name"] for f in result.payload["filter_fields"]]
        assert "name" in field_names
        # "name" field should use the custom config, not a duplicate
        name_fields = [f for f in result.payload["filter_fields"] if f["field_name"] == "name"]
        assert len(name_fields) == 1

    def test_allowed_operators(self):
        from plugins.ui.filter_component.plugin import ALLOWED_OPERATORS

        assert "contains" in ALLOWED_OPERATORS["string"]
        assert "gt" in ALLOWED_OPERATORS["number"]
        assert "between" in ALLOWED_OPERATORS["date"]
        assert "eq" in ALLOWED_OPERATORS["boolean"]

    def test_validate_filter_params(self):
        from plugins.ui.filter_component.plugin import (
            FilterFieldConfig,
            validate_filter_params,
        )

        field_configs = [
            FilterFieldConfig(field_name="name", field_type="string", label="Name"),
        ]
        result = validate_filter_params(
            {"action_id": "filter", "filters": [{"field": "name", "operator": "contains", "value": "test"}]},
            field_configs,
        )
        assert result["action_id"] == "filter"
        assert len(result["filters"]) == 1

    def test_invalid_filter_operator(self):
        from plugins.ui.filter_component.plugin import (
            FilterFieldConfig,
            validate_filter_params,
        )

        field_configs = [
            FilterFieldConfig(field_name="name", field_type="string", label="Name"),
        ]
        with pytest.raises(ValueError, match="not allowed"):
            validate_filter_params(
                {"action_id": "filter", "filters": [{"field": "name", "operator": "invalid_op", "value": "x"}]},
                field_configs,
            )

    def test_csp_header(self):
        from plugins.ui.filter_component.plugin import generate_csp_header

        header = generate_csp_header("test-nonce")
        assert "nonce-test-nonce" in header
        assert "default-src 'self'" in header
        assert "unsafe-eval" not in header


# ─── All UI plugin attributes ────────────────────────────────────────────


class TestUIPluginAttributes:
    @pytest.mark.parametrize(
        "module_path,class_name",
        [
            ("plugins.ui.table_component.plugin", "TableComponentPlugin"),
            ("plugins.ui.chart_component.plugin", "ChartComponentPlugin"),
            ("plugins.ui.card_component.plugin", "CardComponentPlugin"),
            ("plugins.ui.filter_component.plugin", "FilterComponentPlugin"),
        ],
    )
    def test_plugin_attributes(self, module_path, class_name):
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        p = cls()
        assert p.plugin_type == "ui"
        assert p.input_schema == "ViewModel.v1"
        assert p.output_schema == "UIComponentDTO.v1"
        assert p.name
        assert p.version
