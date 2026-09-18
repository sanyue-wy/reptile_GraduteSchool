# -*- coding: utf-8 -*-
"""test_scaffolds.py — 脚手架 CLI 六类生成物测试。"""

import json
from pathlib import Path

import pytest

from scaffolds.generator import (
    generate_plugin,
    validate_scaffold,
    VALID_KINDS,
    _to_class_name,
)
from scaffolds.loader_protocol import REQUIRED_METADATA_FIELDS


# ── 类名转换 ──

class TestClassName:
    def test_simple(self):
        assert _to_class_name("my_plugin") == "MyPlugin"

    def test_single_word(self):
        assert _to_class_name("spider") == "SpiderPlugin"

    def test_multi_word(self):
        assert _to_class_name("jsonl_store") == "JsonlStorePlugin"


# ── 六类生成物各跑一次 ──

@pytest.mark.parametrize("kind", ["spider", "processor", "storage", "presenter", "ui"])
class TestGeneratePlugin:
    def test_generates_files(self, kind, tmp_path):
        result = generate_plugin(kind, f"test_{kind}", output_dir=str(tmp_path / kind))
        assert "output_dir" in result
        assert "files" in result
        assert "metadata.json" in result["files"]
        assert "plugin.py" in result["files"]
        assert "test_plugin.py" in result["files"]

    def test_metadata_has_required_fields(self, kind, tmp_path):
        generate_plugin(kind, f"test_{kind}", output_dir=str(tmp_path / kind))
        meta = json.loads((tmp_path / kind / "metadata.json").read_text(encoding="utf-8"))
        for field in REQUIRED_METADATA_FIELDS:
            assert field in meta, f"Missing {field} in {kind} metadata"

    def test_metadata_plugin_type_matches(self, kind, tmp_path):
        generate_plugin(kind, f"test_{kind}", output_dir=str(tmp_path / kind))
        meta = json.loads((tmp_path / kind / "metadata.json").read_text(encoding="utf-8"))
        assert meta["plugin_type"] == kind

    def test_entry_point_format(self, kind, tmp_path):
        generate_plugin(kind, f"test_{kind}", output_dir=str(tmp_path / kind))
        meta = json.loads((tmp_path / kind / "metadata.json").read_text(encoding="utf-8"))
        ep = meta["entry_point"]
        assert ":" in ep
        module_path, class_name = ep.split(":")
        assert module_path.endswith(".plugin")

    def test_validator_passes(self, kind, tmp_path):
        generate_plugin(kind, f"test_{kind}", output_dir=str(tmp_path / kind))
        result = validate_scaffold(str(tmp_path / kind))
        assert result["valid"], f"Validation failed for {kind}: {result['errors']}"


class TestGenerateTemplate:
    def test_generates_template_files(self, tmp_path):
        result = generate_plugin("template", "my_template", output_dir=str(tmp_path / "tmpl"))
        assert "layout.html" in result["files"]
        assert "style.css" in result["files"]
        assert "variables.json" in result["files"]

    def test_template_variables_json_valid(self, tmp_path):
        generate_plugin("template", "my_template", output_dir=str(tmp_path / "tmpl"))
        variables = json.loads((tmp_path / "tmpl" / "variables.json").read_text(encoding="utf-8"))
        assert variables["name"] == "my_template"
        assert "variables" in variables


# ── 验证器 ──

class TestValidator:
    def test_missing_metadata_json(self, tmp_path):
        result = validate_scaffold(str(tmp_path))
        assert not result["valid"]
        assert any("metadata.json 不存在" in e for e in result["errors"])

    def test_invalid_json(self, tmp_path):
        (tmp_path / "metadata.json").write_text("not json", encoding="utf-8")
        result = validate_scaffold(str(tmp_path))
        assert not result["valid"]

    def test_missing_required_field(self, tmp_path):
        (tmp_path / "metadata.json").write_text(
            json.dumps({"name": "test", "version": "1.0.0"}),
            encoding="utf-8",
        )
        result = validate_scaffold(str(tmp_path))
        assert not result["valid"]

    def test_invalid_plugin_type(self, tmp_path):
        meta = {f: "x" for f in REQUIRED_METADATA_FIELDS}
        meta["plugin_type"] = "invalid_type"
        meta["entry_point"] = "x.y:Z"
        (tmp_path / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        result = validate_scaffold(str(tmp_path))
        assert not result["valid"]
        assert any("plugin_type" in e for e in result["errors"])


# ── CLI ──

class TestCLI:
    def test_cli_new_spider(self, tmp_path):
        from scaffolds.cli import main
        exit_code = main(["new", "spider", "cli_test", "-o", str(tmp_path / "cli_spider")])
        assert exit_code == 0
        assert (tmp_path / "cli_spider" / "metadata.json").exists()

    def test_cli_invalid_kind(self, tmp_path):
        from scaffolds.cli import main
        with pytest.raises(SystemExit):
            main(["new", "invalid_kind", "test"])

    def test_cli_no_args(self):
        from scaffolds.cli import main
        exit_code = main([])
        assert exit_code == 1


# ── 业务代码行数检查 ──

@pytest.mark.parametrize("kind", ["spider", "processor", "storage", "presenter", "ui"])
def test_plugin_py_business_lines_under_30(kind, tmp_path):
    """生成的 plugin.py 中 execute 方法的业务代码 ≤30 行。"""
    generate_plugin(kind, f"line_check_{kind}", output_dir=str(tmp_path / kind))
    content = (tmp_path / kind / "plugin.py").read_text(encoding="utf-8")

    # Count lines in the execute method (between def execute and next def/class)
    in_execute = False
    biz_lines = 0
    for line in content.split("\n"):
        if "def execute(" in line:
            in_execute = True
            continue
        if in_execute:
            if line.strip().startswith("def ") or line.strip().startswith("class "):
                break
            if line.strip() and not line.strip().startswith("#"):
                biz_lines += 1

    assert biz_lines <= 30, f"{kind} execute has {biz_lines} business lines (limit: 30)"


# ── 默认输出目录测试 ──

def test_default_output_dir(tmp_path, monkeypatch):
    """验证默认输出目录为 tests/fixtures/generated_plugin/<name>。"""
    monkeypatch.chdir(tmp_path)
    result = generate_plugin("spider", "default_dir_test")
    assert "generated_plugin" in result["output_dir"]
    assert "default_dir_test" in result["output_dir"]
