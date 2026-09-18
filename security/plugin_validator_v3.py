# -*- coding: utf-8 -*-
"""V3.0 插件源码校验层。

不修改原 security/plugin_validator.py（W2 等仍 import 它）。
复用 BLOCKED_* 常量，扩展 BasePlugin 子类接口校验。
AST 检查是门禁不是沙箱。

V3.0 安全策略：允许导入 os/sys 等模块（插件需要 os.path/os.replace），
但阻止危险的顶层函数调用（os.system/subprocess.run/eval/exec 等）。
"""

from __future__ import annotations

import ast
from pathlib import Path

from security.plugin_validator import (
    BLOCKED_CALLS,
    BLOCKED_MODULES,
    ValidationResult,
    _extract_plugin_meta,
)

# V3.0 BasePlugin 子类名称（AST 匹配用）
_V3_BASE_CLASSES = frozenset({
    "BasePlugin",
    "SpiderPlugin",
    "ParserPlugin",
    "RecordProcessorPlugin",
    "StoragePlugin",
    "PresenterPlugin",
    "UIPlugin",
})

# V3.0 五组 plugin_type → 可接受的基类
_TYPE_BASE_MAP = {
    "spider": {"BasePlugin", "SpiderPlugin"},
    "processor": {"BasePlugin", "ParserPlugin", "RecordProcessorPlugin"},
    "storage": {"BasePlugin", "StoragePlugin"},
    "presenter": {"BasePlugin", "PresenterPlugin"},
    "ui": {"BasePlugin", "UIPlugin"},
}

# 危险调用：模块.属性 形式（AST 匹配用）
_BLOCKED_ATTR_CALLS: set[tuple[str, str]] = {
    ("os", "system"),
    ("os", "popen"),
    ("os", "exec"),
    ("os", "execv"),
    ("os", "execve"),
    ("subprocess", "run"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("subprocess", "Popen"),
    ("shutil", "which"),
}


def _check_v3_safety(tree: ast.AST) -> list[str]:
    """V3.0 安全检查：阻止危险调用，允许模块导入。

    与 V2.2 的 _check_import_safety 不同：
    - V2.2 阻止整个 os/subprocess 模块的 import
    - V3.0 允许 import，但阻止 os.system()/subprocess.run() 等危险调用
    - eval/exec/compile 等顶层函数仍被阻止
    """
    issues: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func

            # 顶层函数调用：eval(), exec(), compile(), input(), __import__()
            if isinstance(func, ast.Name) and func.id in BLOCKED_CALLS:
                issues.append(f"调用了受限函数 {func.id}()")

            # 属性调用：os.system(), subprocess.run(), etc.
            if isinstance(func, ast.Attribute):
                attr = func.attr
                if isinstance(func.value, ast.Name):
                    module = func.value.id
                    if (module, attr) in _BLOCKED_ATTR_CALLS:
                        issues.append(f"调用了受限方法 {module}.{attr}()")

    return issues


def _find_class_bases(tree: ast.Module) -> dict[str, set[str]]:
    """提取所有类定义及其基类名称。"""
    result: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases: set[str] = set()
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.add(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.add(base.attr)
                # Subscript like BasePlugin[T, U] - base.func is the class name
                elif isinstance(base, ast.Subscript):
                    if isinstance(base.value, ast.Name):
                        bases.add(base.value.id)
                    elif isinstance(base.value, ast.Attribute):
                        bases.add(base.value.attr)
            result[node.name] = bases
    return result


def validate_v3_plugin(
    source: str,
    metadata: dict | None = None,
    plugin_type: str = "",
    filename: str = "",
) -> ValidationResult:
    """V3.0 插件源码校验：AST 安全检查 + BasePlugin 子类检测。

    Args:
        source: 插件 Python 源码
        metadata: metadata.json 解析结果（可选，用于交叉校验）
        plugin_type: 期望的 plugin_type
        filename: 源文件名（用于错误消息）

    Returns:
        ValidationResult
    """
    # 语法检查
    try:
        tree = ast.parse(source, filename=filename or "<unknown>")
    except SyntaxError as exc:
        return ValidationResult(ok=False, errors=[f"语法错误: {exc.msg}"])

    # V3.0 安全检查（允许 import，阻止危险调用）
    safety_issues = _check_v3_safety(tree)
    if safety_issues:
        return ValidationResult(ok=False, errors=safety_issues, warnings=list(safety_issues))

    errors: list[str] = []
    warnings: list[str] = []

    if plugin_type:
        expected_bases = _TYPE_BASE_MAP.get(plugin_type, set())
        class_bases = _find_class_bases(tree)

        # 检查是否有符合要求的子类
        has_valid_subclass = False
        for cls_name, bases in class_bases.items():
            if bases & (expected_bases | _V3_BASE_CLASSES):
                has_valid_subclass = True
                break

        if not has_valid_subclass:
            errors.append(
                f"插件必须定义继承 BasePlugin 子类的类；"
                f"plugin_type={plugin_type!r} 期望基类: {expected_bases}"
            )

    # 交叉校验 metadata 与源码
    if metadata:
        entry_point = metadata.get("entry_point", "")
        if ":" in entry_point:
            class_name = entry_point.split(":")[-1]
            class_bases = _find_class_bases(tree)
            if class_name not in class_bases:
                errors.append(
                    f"entry_point 引用的类 {class_name!r} 未在源码中定义"
                )

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


def validate_v3_plugin_file(
    path: str | Path,
    metadata: dict | None = None,
    plugin_type: str = "",
) -> ValidationResult:
    """读取文件并执行 V3.0 校验。"""
    try:
        source = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        return ValidationResult(ok=False, errors=[f"无法读取文件: {exc}"])
    return validate_v3_plugin(source, metadata, plugin_type, str(path))


__all__ = [
    "validate_v3_plugin",
    "validate_v3_plugin_file",
    "_check_v3_safety",
]
