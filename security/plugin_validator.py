# -*- coding: utf-8 -*-
"""插件源码静态校验。

仅提取既有 AST 检查范围，不导入或执行插件。通过检查不代表插件可信，
该检查不是安全沙箱。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

# 单向依赖：config.plugins 重导出这些常量，本模块不依赖插件加载器。
PLUGIN_INTERFACES = {
    "source": "describe",
    "fetcher": "fetch",
    "parser": "parse",
    "processor": "process",
    "exporter": "export",
    "presenter": "render",
    "utility": "setup",
}
PLUGIN_META_FIELDS = ("name", "kind", "version", "author", "description")
BLOCKED_MODULES = {"os", "subprocess", "shutil", "socket", "ctypes", "sys"}
BLOCKED_CALLS = {"eval", "exec", "compile", "input", "__import__"}


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _check_import_safety(tree: ast.AST) -> list[str]:
    """沿用原有 import、from-import 和调用名称检查规则。"""
    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_MODULES:
                    issues.append(f"插件引入了受限模块 {root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BLOCKED_MODULES:
                issues.append(f"插件引入了受限模块 {root}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in BLOCKED_CALLS:
                issues.append(f"插件调用了受限函数 {name}")
    return issues


def _extract_plugin_meta(tree: ast.Module):
    """只读取字面量；与旧实现一致，使用最后一次顶层 META 赋值。"""
    meta_node = None
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(target, ast.Name) and target.id == "PLUGIN_META" for target in targets):
                meta_node = node.value
    return ast.literal_eval(meta_node) if meta_node is not None else None


def validate_plugin_source(source: str, kind: str = "", filename: str = "") -> ValidationResult:
    """检查源码；指定 kind 时同时检查 META 和顶层接口函数。

    受限导入/调用同时列入 errors 和诊断 warnings，始终使 ok=False。
    不指定 kind 时仅检查语法及受限导入/调用，不推断插件类型。
    """
    try:
        tree = ast.parse(source, filename=filename or "<unknown>")
    except SyntaxError as exc:
        return ValidationResult(ok=False, errors=[f"插件 Python 语法错误: {exc.msg}"])

    safety_issues = _check_import_safety(tree)
    if safety_issues:
        return ValidationResult(ok=False, errors=safety_issues, warnings=list(safety_issues))
    if not kind:
        return ValidationResult(ok=True)

    try:
        meta = _extract_plugin_meta(tree)
    except (ValueError, TypeError):
        return ValidationResult(ok=False, errors=["PLUGIN_META 必须是字面量字典"])
    if not isinstance(meta, dict):
        return ValidationResult(ok=False, errors=["插件缺少 PLUGIN_META"])

    errors: list[str] = []
    missing = [name for name in PLUGIN_META_FIELDS if not meta.get(name)]
    if missing:
        errors.append(f"PLUGIN_META 缺少字段: {', '.join(missing)}")
    if meta.get("kind") != kind:
        errors.append(f"PLUGIN_META.kind 必须是 {kind!r}")
    interface = PLUGIN_INTERFACES.get(kind, "")
    if not any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == interface
        for node in tree.body
    ):
        errors.append(f"插件必须实现 {interface}()")
    return ValidationResult(ok=not errors, errors=errors)


def validate_plugin_file(path) -> ValidationResult:
    """读取 UTF-8 文件做语法及受限导入/调用检查，不执行插件或推断 kind。"""
    try:
        source = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        return ValidationResult(ok=False, errors=[f"无法读取文件: {exc}"])
    return validate_plugin_source(source, filename=str(path))
