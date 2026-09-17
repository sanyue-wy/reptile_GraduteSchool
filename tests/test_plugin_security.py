"""Defensive AST validation only: never execute prohibited plugin source."""
import pytest

from security.plugin_validator import ValidationResult, validate_plugin_file, validate_plugin_source


META = 'PLUGIN_META = {"name":"test", "kind":"processor", "version":"1", "author":"test", "description":"test"}\n'
SAFE = META + 'def process(records, ctx):\n    return records\n'


def test_safe_source_and_independent_results():
    result = validate_plugin_source(SAFE, kind="processor", filename="safe.py")
    assert result == ValidationResult(ok=True, errors=[], warnings=[])
    result.errors.append("test-only")
    assert validate_plugin_source(SAFE, kind="processor").errors == []
    assert validate_plugin_source("import json\nx = 1").ok


@pytest.mark.parametrize("module", ["os", "subprocess", "shutil", "socket", "ctypes", "sys"])
@pytest.mark.parametrize("form", ["import {module}", "from {module} import harmless_name"])
def test_restricted_imports_are_errors_not_only_warnings(module, form):
    result = validate_plugin_source(form.format(module=module) + "\n" + SAFE, kind="processor")
    assert result.ok is False
    assert any(module in error for error in result.errors)


@pytest.mark.parametrize("name", ["eval", "exec", "compile", "input", "__import__"])
def test_prohibited_calls_rejected_without_execution(name):
    # Parsed as text only; no arguments, payload, dynamic import or exploitation.
    result = validate_plugin_source(SAFE + f"\ndef never_run():\n    {name}()\n", kind="processor")
    assert not result.ok
    assert any(name in error for error in result.errors)


@pytest.mark.parametrize("source,fragment", [
    ("def broken(:", "语法"),
    ("x = 1", "PLUGIN_META"),
    ("PLUGIN_META = dict(name='x')", "字面量"),
    ("PLUGIN_META = {}", "字段"),
    (META, "process"),
    (SAFE.replace('"processor"', '"exporter"'), "kind"),
])
def test_invalid_structure(source, fragment):
    result = validate_plugin_source(source, kind="processor")
    assert not result.ok
    assert any(fragment in message for message in result.errors)


def test_annotated_meta_and_async_interface():
    source = SAFE.replace("PLUGIN_META =", "PLUGIN_META: dict =").replace("def process", "async def process")
    assert validate_plugin_source(source, kind="processor").ok


def test_file_validation_safe_blocked_missing_and_bad_encoding(tmp_path):
    file = tmp_path / "plugin.py"
    file.write_text(SAFE, encoding="utf-8")
    assert validate_plugin_file(file).ok
    file.write_text("import os\n" + SAFE, encoding="utf-8")
    result = validate_plugin_file(file)
    assert not result.ok and result.errors
    assert not validate_plugin_file(tmp_path / "missing.py").ok
    file.write_bytes(b"\xff\xfe\x00")
    assert not validate_plugin_file(file).ok


def test_upload_rejects_dangerous_import_before_saving(isolated_workspace):
    from config.plugins import upload_plugin
    with pytest.raises(ValueError, match="os"):
        upload_plugin("processor", "rejected.py", "import os\n" + SAFE)
    assert not list((isolated_workspace / "plugins_ext").rglob("rejected.py"))
