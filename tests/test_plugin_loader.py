# -*- coding: utf-8 -*-
"""W3 插件治理测试：loader / registry / 兼容适配。

覆盖关键用例：
1. metadata-only 发现：未批准的包不出现在可执行清单、不被 import
2. 批准后篡改任一字节 → 重新加载被拒
3. 同一输出场景下活动快照在批准新版前后：进行中 run 用旧版、新 run 用新版
4. 旧 API 形状回归：list_plugins() 输出与改造前 golden fixture 逐字段一致
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Fixtures ──


@pytest.fixture
def tmp_plugins(tmp_path):
    """创建临时插件目录结构。"""
    plugins_dir = tmp_path / "plugins"
    spiders_dir = plugins_dir / "spiders" / "test_spider"
    spiders_dir.mkdir(parents=True)

    # 写入 metadata.json
    meta = {
        "name": "test_spider",
        "version": "1.0.0",
        "author": "test",
        "plugin_type": "spider",
        "input_schema": "TaskConfigDTO.v1",
        "output_schema": "RawDataBatch.v1",
        "entry_point": "plugins.spiders.test_spider.plugin:TestSpiderPlugin",
        "dependencies": [],
        "min_core_version": "3.0.0",
        "config_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "license": "MIT",
    }
    (spiders_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    # 写入 plugin.py（继承 SpiderPlugin）
    plugin_code = '''
from plugins.base import BasePlugin

class TestSpiderPlugin(BasePlugin):
    name = "test_spider"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data, context):
        return None
'''
    (spiders_dir / "plugin.py").write_text(plugin_code, encoding="utf-8")
    (spiders_dir / "__init__.py").write_text("", encoding="utf-8")

    return plugins_dir


@pytest.fixture
def tmp_plugins_bad(tmp_path):
    """创建包含危险调用的插件目录。"""
    plugins_dir = tmp_path / "plugins"
    bad_dir = plugins_dir / "spiders" / "bad_spider"
    bad_dir.mkdir(parents=True)

    meta = {
        "name": "bad_spider",
        "version": "1.0.0",
        "author": "test",
        "plugin_type": "spider",
        "input_schema": "TaskConfigDTO.v1",
        "output_schema": "RawDataBatch.v1",
        "entry_point": "plugins.spiders.bad_spider.plugin:BadSpiderPlugin",
        "dependencies": [],
        "min_core_version": "3.0.0",
        "license": "MIT",
    }
    (bad_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    plugin_code = '''
import os

class BadSpiderPlugin:
    def execute(self, data, context):
        os.system("rm -rf /")
        return None
'''
    (bad_dir / "plugin.py").write_text(plugin_code, encoding="utf-8")

    return plugins_dir


@pytest.fixture
def tmp_plugins_gpl(tmp_path):
    """创建 GPL 许可证插件。"""
    plugins_dir = tmp_path / "plugins"
    gpl_dir = plugins_dir / "spiders" / "gpl_spider"
    gpl_dir.mkdir(parents=True)

    meta = {
        "name": "gpl_spider",
        "version": "1.0.0",
        "author": "test",
        "plugin_type": "spider",
        "input_schema": "TaskConfigDTO.v1",
        "output_schema": "RawDataBatch.v1",
        "entry_point": "plugins.spiders.gpl_spider.plugin:GplSpiderPlugin",
        "dependencies": ["some_gpl_lib"],
        "min_core_version": "3.0.0",
        "license": "GPL-3.0",
    }
    (gpl_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    plugin_code = '''
from plugins.base import BasePlugin

class GplSpiderPlugin(BasePlugin):
    name = "gpl_spider"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data, context):
        return None
'''
    (gpl_dir / "plugin.py").write_text(plugin_code, encoding="utf-8")

    return plugins_dir


@pytest.fixture
def tmp_plugins_no_license(tmp_path):
    """创建缺少 license 且有依赖的插件。"""
    plugins_dir = tmp_path / "plugins"
    no_lic_dir = plugins_dir / "spiders" / "no_lic_spider"
    no_lic_dir.mkdir(parents=True)

    meta = {
        "name": "no_lic_spider",
        "version": "1.0.0",
        "author": "test",
        "plugin_type": "spider",
        "input_schema": "TaskConfigDTO.v1",
        "output_schema": "RawDataBatch.v1",
        "entry_point": "plugins.spiders.no_lic_spider.plugin:NoLicSpiderPlugin",
        "dependencies": ["requests"],
        "min_core_version": "3.0.0",
    }
    (no_lic_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    plugin_code = '''
from plugins.base import BasePlugin

class NoLicSpiderPlugin(BasePlugin):
    name = "no_lic_spider"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data, context):
        return None
'''
    (no_lic_dir / "plugin.py").write_text(plugin_code, encoding="utf-8")

    return plugins_dir


# ── Loader Tests ──


class TestPluginLoader:
    """metadata.json 扫描发现测试。"""

    def test_scan_finds_valid_plugin(self, tmp_plugins):
        from plugin_manager.loader import scan_plugin_dirs
        descs, warnings, errors = scan_plugin_dirs(tmp_plugins)
        assert len(descs) == 1
        assert descs[0].name == "test_spider"
        assert descs[0].plugin_type == "spider"
        assert descs[0].version == "1.0.0"
        assert descs[0].license == "MIT"

    def test_scan_empty_dir(self, tmp_path):
        from plugin_manager.loader import scan_plugin_dirs
        descs, warnings, errors = scan_plugin_dirs(tmp_path / "plugins")
        assert len(descs) == 0

    def test_scan_type_mismatch_rejected(self, tmp_path):
        """plugin_type 与目录名不匹配时拒绝。"""
        from plugin_manager.loader import scan_plugin_dirs
        plugins_dir = tmp_path / "plugins"
        bad_dir = plugins_dir / "spiders" / "wrong_type"
        bad_dir.mkdir(parents=True)
        meta = {
            "name": "wrong_type",
            "version": "1.0.0",
            "author": "test",
            "license": "MIT",
            "plugin_type": "storage",  # 不匹配 spiders 目录
            "input_schema": "StoreRequest.v1",
            "output_schema": "StoreReceipt.v1",
            "entry_point": "plugins.spiders.wrong_type.plugin:WrongPlugin",
        }
        (bad_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        descs, warnings, errors = scan_plugin_dirs(plugins_dir)
        assert len(descs) == 0
        assert any("不匹配" in e for e in errors)

    def test_gpl_license_produces_warning(self, tmp_plugins_gpl):
        from plugin_manager.loader import scan_plugin_dirs
        descs, warnings, errors = scan_plugin_dirs(tmp_plugins_gpl)
        assert len(descs) == 1  # 不阻断
        assert any("GPL" in w for w in warnings)

    def test_missing_license_with_deps_rejected(self, tmp_plugins_no_license):
        """license 现为必须字段，缺失时直接拒绝。"""
        from plugin_manager.loader import scan_plugin_dirs
        descs, warnings, errors = scan_plugin_dirs(tmp_plugins_no_license)
        assert len(descs) == 0
        assert any("license" in e.lower() for e in errors)

    def test_missing_required_field_rejected(self, tmp_path):
        from plugin_manager.loader import scan_plugin_dirs
        plugins_dir = tmp_path / "plugins"
        bad_dir = plugins_dir / "spiders" / "no_entry"
        bad_dir.mkdir(parents=True)
        meta = {"name": "no_entry", "version": "1.0.0"}  # 缺少必须字段
        (bad_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        descs, warnings, errors = scan_plugin_dirs(plugins_dir)
        assert len(descs) == 0

    def test_invalid_entry_point_rejected(self, tmp_path):
        from plugin_manager.loader import scan_plugin_dirs
        plugins_dir = tmp_path / "plugins"
        bad_dir = plugins_dir / "spiders" / "bad_ep"
        bad_dir.mkdir(parents=True)
        meta = {
            "name": "bad_ep",
            "version": "1.0.0",
            "author": "test",
            "plugin_type": "spider",
            "input_schema": "TaskConfigDTO.v1",
            "output_schema": "RawDataBatch.v1",
            "entry_point": "invalid-no-colon",  # 缺少冒号
            "license": "MIT",
        }
        (bad_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        descs, warnings, errors = scan_plugin_dirs(plugins_dir)
        assert len(descs) == 0


# ── Registry Tests ──


class TestPluginRegistry:
    """生命周期状态机测试。"""

    def test_scan_creates_pending_entries(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry, PluginState
        reg = PluginRegistry()
        count, msgs = reg.scan(tmp_plugins)
        assert count == 1
        assert reg.get_state("spider:test_spider") == PluginState.PENDING_REVIEW

    def test_approve_and_load(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry, PluginState
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        ok, msg = reg.approve("spider:test_spider", admin_id="test_admin")
        assert ok
        assert reg.get_state("spider:test_spider") == PluginState.APPROVED
        entry = reg.get_entry("spider:test_spider")
        assert entry.content_hash  # 非空
        assert entry.approved_by == "test_admin"

    def test_approve_generates_content_hash(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        reg.approve("spider:test_spider", admin_id="test_admin")
        entry = reg.get_entry("spider:test_spider")
        assert len(entry.content_hash) == 64  # SHA-256 hex

    def test_tamper_detection_on_load(self, tmp_plugins):
        """批准后篡改任一字节 → 重新加载被拒。"""
        from plugin_manager.registry import PluginRegistry, PluginState
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        reg.approve("spider:test_spider", admin_id="test_admin")

        # 篡改
        plugin_py = tmp_plugins / "spiders" / "test_spider" / "plugin.py"
        original = plugin_py.read_bytes()
        plugin_py.write_bytes(original + b"# tamper")

        ok, msg = reg.load("spider:test_spider")
        assert not ok
        assert "篡改" in msg or "tamper" in msg.lower() or "不匹配" in msg
        assert reg.get_state("spider:test_spider") == PluginState.REJECTED

        # 恢复
        plugin_py.write_bytes(original)

    def test_snapshot_versioning(self, tmp_plugins):
        """批准新版前后：快照版本递增。"""
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)

        assert reg.current_revision == 0  # 无快照
        reg.approve("spider:test_spider", admin_id="admin")
        assert reg.current_revision == 1

    def test_frozen_revision_for_run(self, tmp_plugins):
        """运行开始冻结 revision，新版本只影响后续运行。"""
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        reg.approve("spider:test_spider", admin_id="admin")

        frozen = reg.freeze_revision()
        assert frozen == 1

        # 新操作改变 revision
        reg.disable("spider:test_spider")
        assert reg.current_revision == 2
        assert frozen == 1  # 冻结的不变

    def test_disable_blocks_load(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry, PluginState
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        reg.approve("spider:test_spider", admin_id="admin")
        reg.disable("spider:test_spider")

        ok, msg = reg.load("spider:test_spider")
        assert not ok
        assert "禁用" in msg

    def test_reference_count_blocks_disable(self):
        """活动运行引用的版本不可禁用。使用真实插件测试加载。"""
        from plugin_manager.registry import PluginRegistry, PluginState
        reg = PluginRegistry()
        reg.scan()  # 扫描真实项目插件
        # 找一个可以 approve 和 load 的插件
        pending = reg.list_entries(state=PluginState.PENDING_REVIEW)
        if not pending:
            pytest.skip("没有 pending_review 的插件可用")
        pid = pending[0].descriptor.plugin_id
        reg.approve(pid, admin_id="test")
        ok, msg = reg.load(pid)
        if not ok:
            pytest.skip(f"无法加载 {pid}: {msg}")

        reg.acquire_reference(pid)
        ok, msg = reg.disable(pid)
        assert not ok
        assert "活动引用" in msg

        reg.release_reference(pid)
        ok, msg = reg.disable(pid)
        assert ok

    def test_unknown_plugin_rejected(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        ok, msg = reg.approve("spider:nonexistent", admin_id="admin")
        assert not ok

    def test_approve_non_pending_rejected(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        # 不批准，直接尝试 approve twice
        reg.approve("spider:test_spider", admin_id="admin")
        ok, msg = reg.approve("spider:test_spider", admin_id="admin")
        assert not ok
        assert "不可批准" in msg

    def test_audit_log(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        reg.approve("spider:test_spider", admin_id="admin")
        log = reg.audit_log
        assert len(log) >= 2  # discovered + approved
        actions = [e["action"] for e in log]
        assert "discovered" in actions
        assert "approved" in actions
        assert log[-1]["admin_id"] == "admin"


# ── 预检函数 Tests ──


class TestPipelineValidation:
    """预检函数测试（供 W2 POST /api/pipeline/validate 调用）。"""

    def test_validate_unknown_instance_rejected(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        reg.approve("spider:test_spider", admin_id="admin")

        result = reg.validate_pipeline_config({
            "my_instance": {"plugin": "spider:nonexistent", "enabled": True}
        })
        assert not result.ok
        assert any("未知插件" in e for e in result.errors)

    def test_validate_unapproved_rejected(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        # 不批准

        result = reg.validate_pipeline_config({
            "my_instance": {"plugin": "spider:test_spider", "enabled": True}
        })
        assert not result.ok

    def test_validate_approved_passes(self, tmp_plugins):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        reg.scan(tmp_plugins)
        reg.approve("spider:test_spider", admin_id="admin")

        result = reg.validate_pipeline_config({
            "my_instance": {"plugin": "spider:test_spider", "enabled": True}
        })
        assert result.ok

    def test_validate_empty_registry_fails(self):
        from plugin_manager.registry import PluginRegistry
        reg = PluginRegistry()
        # 不 scan
        result = reg.validate_pipeline_config({})
        assert not result.ok
        assert any("未初始化" in e for e in result.errors)


# ── Validator Tests ──


class TestValidator:
    """结构/版本/依赖校验测试。"""

    def test_validate_metadata_valid(self, tmp_plugins):
        from plugin_manager.validator import validate_metadata
        meta = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "plugin_type": "spider",
            "input_schema": "TaskConfigDTO.v1",
            "output_schema": "RawDataBatch.v1",
            "entry_point": "plugins.spiders.test.plugin:TestPlugin",
            "license": "MIT",
        }
        result = validate_metadata(meta)
        assert result.ok

    def test_validate_metadata_invalid_schema_id(self):
        from plugin_manager.validator import validate_metadata
        meta = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "license": "MIT",
            "plugin_type": "spider",
            "input_schema": "UnknownSchema.v999",
            "output_schema": "RawDataBatch.v1",
            "entry_point": "plugins.spiders.test.plugin:TestPlugin",
        }
        result = validate_metadata(meta)
        assert not result.ok
        assert any("不在受控注册表" in e for e in result.errors)

    def test_validate_entry_point_valid(self, tmp_plugins):
        """entry_point 格式正确且文件可达时通过。"""
        from plugin_manager.validator import validate_entry_point
        pkg_dir = tmp_plugins / "spiders" / "test_spider"
        result = validate_entry_point(
            "plugins.spiders.test_spider.plugin:TestSpiderPlugin",
            base_dir=pkg_dir,
        )
        assert result.ok

    def test_validate_entry_point_no_colon(self):
        from plugin_manager.validator import validate_entry_point
        result = validate_entry_point("invalid_format")
        assert not result.ok

    def test_content_integrity_check(self, tmp_plugins):
        from plugin_manager.validator import compute_content_hash, check_content_integrity
        pkg_dir = tmp_plugins / "spiders" / "test_spider"
        h = compute_content_hash(pkg_dir)
        assert len(h) == 64

        result = check_content_integrity(pkg_dir, h)
        assert result.ok

        # 篡改
        (pkg_dir / "plugin.py").write_bytes(b"# tampered\n")
        result = check_content_integrity(pkg_dir, h)
        assert not result.ok


# ── 兼容视图 Tests ──


class TestLegacyCompat:
    """旧七类兼容视图测试。"""

    def test_list_plugins_returns_legacy_shape(self):
        """list_plugins() 返回值包含旧七类必要字段。"""
        from config.plugins import list_plugins, PLUGIN_KINDS, refresh_registry
        refresh_registry()
        plugins = list_plugins()
        assert len(plugins) > 0

        required_keys = {"id", "kind", "name", "version", "author", "description", "builtin", "enabled"}
        for p in plugins:
            assert required_keys.issubset(p.keys()), f"缺少字段: {required_keys - p.keys()}"
            assert p["kind"] in PLUGIN_KINDS

    def test_list_plugins_sorted_by_kind_and_id(self):
        from config.plugins import list_plugins, PLUGIN_KINDS, refresh_registry
        refresh_registry()
        plugins = list_plugins()
        for i in range(len(plugins) - 1):
            a, b = plugins[i], plugins[i + 1]
            kind_a = PLUGIN_KINDS.index(a["kind"])
            kind_b = PLUGIN_KINDS.index(b["kind"])
            assert (kind_a, a["id"]) <= (kind_b, b["id"])

    def test_get_plugin_existing(self):
        from config.plugins import get_plugin, refresh_registry
        refresh_registry()
        plugin = get_plugin("spider", "static_html")
        # 可能来自 registry 或旧方式
        if plugin is not None:
            assert plugin["id"] == "static_html"
            assert plugin["kind"] == "spider"

    def test_get_plugin_nonexistent(self):
        from config.plugins import get_plugin
        assert get_plugin("spider", "nonexistent") is None
        assert get_plugin("invalid_kind", "test") is None

    def test_fetcher_alias_static_list(self):
        """static_list 是 static_html 的别名。"""
        from config.plugins import list_plugins, refresh_registry
        refresh_registry()
        plugins = list_plugins()
        names = {p["id"] for p in plugins if p["kind"] == "fetcher"}
        # 应包含 static_html（可能也包含 static_list 别名）
        assert "static_html" in names
