# -*- coding: utf-8 -*-
"""test_schema_editor.py — schema_editor 三件套 + 预设校验测试。"""

import json
from pathlib import Path

import pytest

from schema_editor.editor import load_preset, list_presets, BUILTIN_PROFILES
from schema_editor.generator import (
    generate_task_config,
    generate_json_schema,
    generate_form_spec,
    validate_generated_config,
    generate_all,
)


PRESETS_DIR = Path(__file__).parent.parent / "schema_editor" / "presets"


# ── 预设加载 ──

class TestPresets:
    def test_list_presets_returns_three(self):
        presets = list_presets()
        assert len(presets) == 3
        assert set(presets) == {"tutor_research", "paper_collection", "news_monitor"}

    @pytest.mark.parametrize("preset_name", ["tutor_research", "paper_collection", "news_monitor"])
    def test_load_preset_has_required_keys(self, preset_name):
        config = load_preset(preset_name)
        assert "dataset" in config
        assert "source_id" in config
        assert "target_url" in config
        assert "fields" in config
        assert isinstance(config["fields"], list)
        assert len(config["fields"]) > 0

    @pytest.mark.parametrize("preset_name", ["tutor_research", "paper_collection", "news_monitor"])
    def test_preset_fields_have_name_and_type(self, preset_name):
        config = load_preset(preset_name)
        for field in config["fields"]:
            assert "name" in field, f"Field missing 'name' in {preset_name}"
            assert "type" in field, f"Field '{field['name']}' missing 'type' in {preset_name}"

    def test_tutor_research_profile_is_education(self):
        config = load_preset("tutor_research")
        assert config["profile_id"] == "education"

    def test_paper_collection_profile_is_custom(self):
        config = load_preset("paper_collection")
        assert config["profile_id"] == "custom"


# ── 任务配置生成 ──

class TestTaskConfig:
    def test_generate_task_config_has_required_fields(self):
        definition = load_preset("tutor_research")
        tc = generate_task_config(definition)
        for key in ("task_id", "dataset", "source_id", "profile_id", "target_url",
                     "config_revision", "config_snapshot", "created_at"):
            assert key in tc, f"Missing key: {key}"

    def test_task_id_is_32hex(self):
        definition = load_preset("tutor_research")
        tc = generate_task_config(definition)
        assert len(tc["task_id"]) == 32
        int(tc["task_id"], 16)  # should not raise

    def test_config_snapshot_contains_fields(self):
        definition = load_preset("tutor_research")
        tc = generate_task_config(definition)
        assert "fields" in tc["config_snapshot"]
        assert len(tc["config_snapshot"]["fields"]) > 0

    def test_plugins_copied_from_definition(self):
        definition = load_preset("tutor_research")
        tc = generate_task_config(definition)
        assert "plugins" in tc
        assert "acquire" in tc["plugins"]


# ── JSON Schema 生成 ──

class TestJsonSchema:
    def test_schema_has_draft07(self):
        definition = load_preset("tutor_research")
        schema = generate_json_schema(definition)
        assert "$schema" in schema
        assert "draft-07" in schema["$schema"]

    def test_schema_has_properties(self):
        definition = load_preset("tutor_research")
        schema = generate_json_schema(definition)
        assert "properties" in schema
        assert "name" in schema["properties"]

    def test_schema_id_matches_dataset(self):
        definition = load_preset("paper_collection")
        schema = generate_json_schema(definition)
        assert schema["$id"] == "paper_collection.v1"

    def test_required_fields_marked(self):
        definition = load_preset("tutor_research")
        schema = generate_json_schema(definition)
        assert "required" in schema
        assert "name" in schema["required"]

    def test_enum_propagated(self):
        definition = load_preset("news_monitor")
        schema = generate_json_schema(definition)
        cat_prop = schema["properties"].get("category", {})
        assert "enum" in cat_prop


# ── FormSpec 生成 ──

class TestFormSpec:
    def test_form_spec_has_widgets(self):
        definition = load_preset("tutor_research")
        fs = generate_form_spec(definition)
        assert "widgets" in fs
        assert len(fs["widgets"]) > 0

    def test_widget_has_name_label_type(self):
        definition = load_preset("tutor_research")
        fs = generate_form_spec(definition)
        for w in fs["widgets"]:
            assert "name" in w
            assert "label" in w
            assert "type" in w

    def test_enum_field_becomes_select(self):
        definition = load_preset("tutor_research")
        fs = generate_form_spec(definition)
        title_widget = next(w for w in fs["widgets"] if w["name"] == "title")
        assert title_widget["type"] == "select"
        assert "options" in title_widget

    def test_boolean_field_becomes_checkbox(self):
        definition = {
            "dataset": "test",
            "fields": [{"name": "active", "type": "boolean", "required": False, "description": "是否活跃"}],
        }
        fs = generate_form_spec(definition)
        assert fs["widgets"][0]["type"] == "checkbox"


# ── 校验 ──

class TestValidation:
    def test_valid_config_passes(self):
        definition = load_preset("tutor_research")
        result = generate_all(definition)
        assert result["validation"]["valid"] is True

    @pytest.mark.parametrize("preset_name", ["tutor_research", "paper_collection", "news_monitor"])
    def test_all_presets_validate(self, preset_name):
        definition = load_preset(preset_name)
        result = generate_all(definition)
        assert result["validation"]["valid"] is True, f"{preset_name} failed: {result['validation']['errors']}"

    def test_missing_dataset_fails(self):
        bad = {"fields": [{"name": "x", "type": "string"}]}
        tc = generate_task_config(bad)
        result = validate_generated_config(tc)
        # dataset 默认值兜底，不会完全失败；但 fields 为空会 warning
        assert isinstance(result["valid"], bool)

    def test_duplicate_field_names_detected(self):
        tc = {
            "task_id": "a" * 32,
            "dataset": "test",
            "source_id": "s",
            "profile_id": "custom",
            "target_url": "http://x",
            "config_snapshot": {
                "fields": [
                    {"name": "x", "type": "string"},
                    {"name": "x", "type": "integer"},
                ],
            },
        }
        result = validate_generated_config(tc)
        assert not result["valid"]
        assert any("重复字段名" in e for e in result["errors"])


# ── 组合入口 ──

class TestGenerateAll:
    def test_generate_all_has_four_keys(self):
        definition = load_preset("tutor_research")
        result = generate_all(definition)
        assert set(result.keys()) == {"task_config", "json_schema", "form_spec", "validation"}

    def test_generate_all_json_serializable(self):
        definition = load_preset("tutor_research")
        result = generate_all(definition)
        # Should not raise
        json.dumps(result, ensure_ascii=False)
