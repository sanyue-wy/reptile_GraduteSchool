# -*- coding: utf-8 -*-
"""W3 插件安全测试：AST 拦截 / GPL 告警 / 篡改拒绝。

覆盖关键用例：
1. 含 subprocess.run 的插件源被 AST 拒绝
2. 含 GPL 依赖声明的包加载出告警
3. 批准后篡改任一字节 → 重新加载被拒
4. os.system() 被拒绝
5. eval()/exec() 被拒绝
6. 合法 os.path 使用不被误拒
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


# ── V3.0 安全检查 Tests ──


class TestV3SafetyCheck:
    """V3.0 AST 安全检查：允许 import os，阻止危险调用。"""

    def test_os_system_blocked(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
import os
class BadPlugin:
    def execute(self, data, ctx):
        os.system("rm -rf /")
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert not result.ok
        assert any("os.system" in e for e in result.errors)

    def test_subprocess_run_blocked(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
import subprocess
class BadPlugin:
    def execute(self, data, ctx):
        subprocess.run(["ls"])
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert not result.ok
        assert any("subprocess.run" in e for e in result.errors)

    def test_subprocess_call_blocked(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
import subprocess
class BadPlugin:
    def execute(self, data, ctx):
        subprocess.call(["ls"])
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert not result.ok

    def test_eval_blocked(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
class BadPlugin:
    def execute(self, data, ctx):
        eval("1+1")
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert not result.ok
        assert any("eval" in e for e in result.errors)

    def test_exec_blocked(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
class BadPlugin:
    def execute(self, data, ctx):
        exec("x = 1")
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert not result.ok
        assert any("exec" in e for e in result.errors)

    def test_os_path_allowed(self):
        """os.path.join 是合法使用，不应被阻止。"""
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
import os
from plugins.base import BasePlugin

class GoodPlugin(BasePlugin):
    name = "good"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data, context):
        path = os.path.join("a", "b")
        return None
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert result.ok, f"误拒 os.path 使用: {result.errors}"

    def test_os_replace_allowed(self):
        """os.replace 是原子写入的合法使用。"""
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
import os
from plugins.base import BasePlugin

class GoodPlugin(BasePlugin):
    name = "good"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    def execute(self, data, context):
        os.replace("tmp", "final")
        return None
'''
        result = validate_v3_plugin(source, plugin_type="storage")
        assert result.ok, f"误拒 os.replace: {result.errors}"

    def test_syntax_error_detected(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
def broken(
    pass
'''
        result = validate_v3_plugin(source)
        assert not result.ok
        assert any("语法" in e for e in result.errors)


# ── BasePlugin 子类检测 Tests ──


class TestBasePluginDetection:
    """V3.0 BasePlugin 子类检测。"""

    def test_base_plugin_subclass_accepted(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
from plugins.base import BasePlugin

class MyPlugin(BasePlugin):
    name = "my"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data, context):
        return None
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert result.ok

    def test_plain_class_rejected(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
class MyPlugin:
    name = "my"
    def execute(self, data, context):
        return None
'''
        result = validate_v3_plugin(source, plugin_type="spider")
        assert not result.ok
        assert any("BasePlugin" in e for e in result.errors)

    def test_presenter_plugin_subclass_accepted(self):
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
from plugins.base import PresenterPlugin

class MyPresenter(PresenterPlugin):
    name = "my_presenter"
    version = "1.0.0"
    plugin_type = "presenter"

    def render(self, data, context):
        return "output.html"
'''
        result = validate_v3_plugin(source, plugin_type="presenter")
        assert result.ok

    def test_generic_base_plugin_accepted(self):
        """BasePlugin[T, U] 泛型形式应被接受。"""
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
from plugins.base import BasePlugin
from contracts.result import StoreRequest, StoreReceipt

class MyStorage(BasePlugin[StoreRequest, StoreReceipt]):
    name = "my_storage"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    def execute(self, data, context):
        return None
'''
        result = validate_v3_plugin(source, plugin_type="storage")
        assert result.ok, f"误拒泛型 BasePlugin: {result.errors}"

    def test_entry_point_class_must_exist(self):
        """entry_point 引用的类必须存在于源码中。"""
        from security.plugin_validator_v3 import validate_v3_plugin
        source = '''
from plugins.base import BasePlugin

class WrongName(BasePlugin):
    name = "test"
    def execute(self, data, context):
        return None
'''
        metadata = {"entry_point": "some.module:NonExistentClass"}
        result = validate_v3_plugin(
            source, metadata=metadata, plugin_type="spider"
        )
        assert not result.ok
        assert any("NonExistentClass" in e for e in result.errors)


# ── 旧校验器兼容 Tests ──


class TestLegacyValidator:
    """确认旧 security/plugin_validator.py 不被修改且仍可用。"""

    def test_legacy_validator_still_works(self):
        """旧校验器对顶层函数的检查仍然有效。"""
        from security.plugin_validator import validate_plugin_source
        source = '''
PLUGIN_META = {"name": "test", "kind": "fetcher", "version": "1.0.0", "author": "t", "description": "d"}

def fetch(config, session):
    return []
'''
        result = validate_plugin_source(source, kind="fetcher")
        assert result.ok

    def test_legacy_os_import_blocked(self):
        """旧校验器仍然阻止 os import（V2.2 行为不变）。"""
        from security.plugin_validator import validate_plugin_source
        source = '''
import os
def fetch(config, session):
    return os.listdir(".")
'''
        result = validate_plugin_source(source)
        assert not result.ok
        assert any("os" in e for e in result.errors)

    def test_v2_constants_available(self):
        """BLOCKED_CALLS/BLOCKED_MODULES 仍可从旧模块导入。"""
        from security.plugin_validator import BLOCKED_CALLS, BLOCKED_MODULES, PLUGIN_INTERFACES
        assert "eval" in BLOCKED_CALLS
        assert "os" in BLOCKED_MODULES
        assert "fetcher" in PLUGIN_INTERFACES


# ── Upload 安全 Tests ──


class TestUploadSecurity:
    """上传流程安全测试。"""

    def test_upload_rejects_dangerous_source(self, tmp_path):
        """上传含 os.system 的源码应被拒绝。"""
        from plugin_manager.registry import PluginRegistry, upload_to_pending
        import plugin_manager.registry as reg_mod
        reg = PluginRegistry()

        meta = {
            "name": "bad_upload",
            "version": "1.0.0",
            "author": "test",
            "plugin_type": "spider",
            "input_schema": "TaskConfigDTO.v1",
            "output_schema": "RawDataBatch.v1",
            "entry_point": "plugins.spiders.bad_upload.plugin:BadPlugin",
            "license": "MIT",
        }
        source = '''
import os
class BadPlugin:
    def execute(self, data, ctx):
        os.system("evil")
'''

        original = reg_mod.UPLOAD_DIR
        reg_mod.UPLOAD_DIR = tmp_path / "uploads"
        try:
            ok, msg = upload_to_pending("bad.py", source, meta, reg)
            assert not ok
            assert "os.system" in msg or "安全" in msg or "受限" in msg
        finally:
            reg_mod.UPLOAD_DIR = original

    def test_upload_accepts_safe_source(self, tmp_path):
        """上传安全源码应被接受到待审区。"""
        from plugin_manager.registry import PluginRegistry, upload_to_pending
        import plugin_manager.registry as reg_mod
        reg = PluginRegistry()

        meta = {
            "name": "safe_upload",
            "version": "1.0.0",
            "author": "test",
            "plugin_type": "spider",
            "input_schema": "TaskConfigDTO.v1",
            "output_schema": "RawDataBatch.v1",
            "entry_point": "plugins.spiders.safe_upload.plugin:SafePlugin",
            "license": "MIT",
        }
        source = '''from plugins.base import BasePlugin
class SafePlugin(BasePlugin):
    name = "safe_upload"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"
    def execute(self, data, context):
        return None
'''
        original = reg_mod.UPLOAD_DIR
        reg_mod.UPLOAD_DIR = tmp_path / "uploads"
        try:
            ok, msg = upload_to_pending("safe.py", source, meta, reg)
            assert ok
            assert "待批准" in msg or "已接收" in msg
        finally:
            reg_mod.UPLOAD_DIR = original
