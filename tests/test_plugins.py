# -*- coding: utf-8 -*-
"""插件注册表、配置和外部加载测试"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def plugin_env(monkeypatch, tmp_path):
    import config.plugins as plugins

    config_path = tmp_path / "plugins.json"
    ext_dir = tmp_path / "plugins_ext"
    monkeypatch.setattr(plugins, "PLUGIN_CONFIG_PATH", config_path)
    monkeypatch.setattr(plugins, "EXT_PLUGIN_DIR", ext_dir)
    plugins._EXTERNAL_CACHE.clear()
    yield plugins
    plugins._EXTERNAL_CACHE.clear()
    for module_name in list(__import__("sys").modules):
        if module_name.startswith("plugins_ext."):
            __import__("sys").modules.pop(module_name, None)


def processor_source(description="外部处理器"):
    return f'''PLUGIN_META = {{
    "name": "sample",
    "kind": "processor",
    "version": "1.0.0",
    "author": "测试",
    "description": {description!r},
}}

def process(records, ctx):
    return records
'''


class TestPluginManager:
    def test_list_plugins_includes_builtin_and_external(self, plugin_env):
        plugins = plugin_env
        plugin = plugins.upload_plugin("processor", "sample.py", processor_source())

        assert plugin["builtin"] is False
        assert plugin["interface"] == "process"
        items = plugins.list_plugins()
        kinds = {item["kind"] for item in items}
        assert kinds == {"source", "fetcher", "parser", "processor", "exporter", "presenter", "utility"}
        assert any(item["id"] == "sample" and item["kind"] == "processor" for item in items)
        assert {"jsonl", "xlsx"}.issubset({item["id"] for item in items if item["kind"] == "exporter"})

    def test_update_pipeline_filters_unknown_plugins(self, plugin_env):
        plugins = plugin_env
        result = plugins.update_pipeline("processors", {"merge": 10, "unknown": 99, "invalid": "x"})

        assert result == {"merge": 10}
        saved = json.loads(plugins.PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
        assert saved["pipeline"]["processors"] == {"merge": 10}
        assert plugins.update_pipeline("presenters", {"overview": 1}) is None

    def test_update_plugin_override_and_disable(self, plugin_env):
        plugins = plugin_env
        plugin = plugins.update_plugin("processor", "merge", {"enabled": False, "config": {"mode": "strict"}})

        assert plugin["enabled"] is False
        assert plugin["config"] == {"mode": "strict"}
        assert plugins.is_enabled("processor", "merge") is False
        saved = json.loads(plugins.PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
        assert saved["overrides"]["processor:merge"] == {"enabled": False, "config": {"mode": "strict"}}

    def test_upload_rejects_unsafe_import(self, plugin_env):
        plugins = plugin_env
        source = '''import os\nPLUGIN_META = {"name": "bad", "kind": "processor", "version": "1", "author": "T", "description": "bad"}\ndef process(records, ctx):\n    return records\n'''
        with pytest.raises(ValueError, match="受限模块"):
            plugins.upload_plugin("processor", "bad.py", source)
        assert not (plugins.EXT_PLUGIN_DIR / "processor" / "bad.py").exists()

    def test_external_plugin_hot_reload(self, plugin_env):
        plugins = plugin_env
        path = plugins.EXT_PLUGIN_DIR / "processor" / "sample.py"
        path.parent.mkdir(parents=True)
        path.write_text(processor_source("first"), encoding="utf-8")
        assert plugins.reload_external_plugins()["processor:sample"]["meta"]["description"] == "first"

        path.write_text(processor_source("second"), encoding="utf-8")
        plugin = plugins.reload_plugin("processor", "sample")
        assert plugin["description"] == "second"

    def test_delete_external_plugin(self, plugin_env):
        plugins = plugin_env
        plugins.upload_plugin("processor", "sample.py", processor_source())
        assert plugins.delete_plugin("processor", "sample") is True
        assert not (plugins.EXT_PLUGIN_DIR / "processor" / "sample.py").exists()
        assert plugins.get_plugin("processor", "sample") is None


class TestPluginPipelines:
    def test_processor_pipeline_orders_by_weight_and_skips_disabled(self, monkeypatch):
        import main

        calls = []
        monkeypatch.setattr(main, "load_plugin_config", lambda: {
            "pipeline": {"processors": {"first": 300, "second": 100, "disabled": 200}}
        })
        monkeypatch.setattr(main, "is_enabled", lambda kind, name: name != "disabled")
        monkeypatch.setattr(main, "plugin_config", lambda kind, name: {"name": name})
        def dispatch(name, records, ctx):
            calls.append((name, ctx))
            return records + [name]

        monkeypatch.setattr(main, "dispatch_processor", dispatch)
        result = main.run_processor_pipeline(["start"], {"university": "测试大学"})

        assert result == ["start", "second", "first"]
        assert [call[0] for call in calls] == ["second", "first"]
        assert calls[0][1]["plugin_config"] == {"name": "second"}
        assert calls[0][1]["university"] == "测试大学"

    def test_export_pipeline_orders_by_weight(self, monkeypatch):
        import main

        calls = []
        monkeypatch.setattr(main, "load_plugin_config", lambda: {
            "pipeline": {"exporters": {"jsonl": 300, "xlsx": 100}}
        })
        monkeypatch.setattr(main, "is_enabled", lambda kind, name: True)
        def dispatch(name, records, output_dir):
            calls.append((name, records, output_dir))
            return {"name": name}

        monkeypatch.setattr(main, "dispatch_exporter", dispatch)
        output_dir = Path("data/output")
        assert main.run_export_pipeline([{"name": "张三"}], output_dir) == {"xlsx": {"name": "xlsx"}, "jsonl": {"name": "jsonl"}}
        assert [call[0] for call in calls] == ["xlsx", "jsonl"]
        assert all(call[1] == [{"name": "张三"}] and call[2] == output_dir for call in calls)
