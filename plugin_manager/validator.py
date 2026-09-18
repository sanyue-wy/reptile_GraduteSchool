# -*- coding: utf-8 -*-
"""插件结构/版本/依赖/schema 校验。

复用 security/plugin_validator.py 的 BLOCKED_* 常量与 AST 提取逻辑，
扩展：新类接口校验（BasePlugin 子类）与旧顶层函数校验分开适配。
schema 名称从受控注册表解析，禁止 eval 任意字符串。
"""

from __future__ import annotations

import ast
import importlib.util
import json
import logging
import re
from pathlib import Path
from typing import Any

from packaging.version import Version

from security.plugin_validator import (
    BLOCKED_CALLS,
    BLOCKED_MODULES,
    PLUGIN_INTERFACES,
    ValidationResult,
    _check_import_safety,
    _extract_plugin_meta,
    validate_plugin_source as _validate_legacy_source,
)

logger = logging.getLogger(__name__)

# V3.0 五组插件类型 → 预期的基类名
PLUGIN_BASE_CLASSES = {
    "spider": "SpiderPlugin",
    "processor": "ParserPlugin",  # 或 RecordProcessorPlugin
    "storage": "StoragePlugin",
    "presenter": "PresenterPlugin",
    "ui": "UIPlugin",
}

# 受控 Schema ID 注册表（INTERFACES.md §7）
KNOWN_SCHEMA_IDS: set[str] = {
    "TaskConfigDTO.v1",
    "TaskRunState.v1",
    "OutputSpec.v1",
    "RawDataDTO.v1",
    "RawDataBatch.v1",
    "NormalizedRecordDTO.v1",
    "RecordBatch.v1",
    "PresentationRequest.v1",
    "RenderedOutputDTO.v1",
    "ViewModel.v1",
    "UIComponentDTO.v1",
    "StoreRequest.v1",
    "StoreReceipt.v1",
    "StageResult.v1",
    "RunResult.v1",
    "ErrorDTO.v1",
    "MediaAsset.v1",
    "AssetRef.v1",
    "education.tutor.v1",
    "education.major.v1",
}

# entry_point 格式：module.path:ClassName
_ENTRY_POINT_RE = re.compile(
    r"^([a-zA-Z_][a-zA-Z0-9_.]*):([a-zA-Z_][a-zA-Z0-9_]*)$"
)


def validate_entry_point(entry_point: str, base_dir: Path | None = None) -> ValidationResult:
    """校验 entry_point 格式和包路径可达性。"""
    match = _ENTRY_POINT_RE.match(entry_point)
    if not match:
        return ValidationResult(
            ok=False,
            errors=[f"entry_point 格式无效 (应为 module.path:ClassName): {entry_point!r}"],
        )

    module_path_str = match.group(1)
    class_name = match.group(2)

    # 格式校验通过后，检查文件可达性
    parts = module_path_str.split(".")
    entry_filename = parts[-1] + ".py"

    if base_dir is not None and base_dir.is_dir():
        # 检查 entry 文件是否在包目录中
        entry_file = base_dir / entry_filename
        if not entry_file.exists():
            # 也检查 package 子目录
            pkg_init = base_dir / parts[-1] / "__init__.py"
            if not pkg_init.exists():
                return ValidationResult(
                    ok=False,
                    errors=[f"entry_point 入口文件不可达: {entry_filename}"],
                    warnings=[f"检查路径: {entry_file}"],
                )

    return ValidationResult(ok=True)


def validate_schema_ids(
    input_schema: str,
    output_schema: str,
    plugin_type: str,
) -> ValidationResult:
    """校验 schema ID 是否在受控注册表中。"""
    errors: list[str] = []

    if input_schema not in KNOWN_SCHEMA_IDS:
        errors.append(
            f"input_schema {input_schema!r} 不在受控注册表中；"
            "新 schema 必须先在 INTERFACES.md 注册"
        )

    if output_schema not in KNOWN_SCHEMA_IDS:
        errors.append(
            f"output_schema {output_schema!r} 不在受控注册表中；"
            "新 schema 必须先在 INTERFACES.md 注册"
        )

    return ValidationResult(ok=not errors, errors=errors)


def validate_metadata(
    data: dict[str, Any],
    metadata_path: Path | None = None,
) -> ValidationResult:
    """完整校验 metadata.json：字段、版本、schema、entry_point。"""
    from plugin_manager.loader import REQUIRED_METADATA_FIELDS, PLUGIN_TYPES, MetadataError
    from packaging.version import InvalidVersion

    errors: list[str] = []
    warnings: list[str] = []
    label = str(metadata_path) if metadata_path else "<metadata>"

    # 必须字段
    missing = [f for f in REQUIRED_METADATA_FIELDS if f not in data]
    if missing:
        errors.append(f"{label}: 缺少必须字段: {', '.join(missing)}")
        return ValidationResult(ok=False, errors=errors)

    # plugin_type
    if data["plugin_type"] not in PLUGIN_TYPES:
        errors.append(f"{label}: plugin_type 必须是 {PLUGIN_TYPES} 之一")

    # version
    try:
        ver = Version(data["version"])
    except InvalidVersion:
        errors.append(f"{label}: version 无效: {data['version']!r}")
        ver = None

    # min_core_version
    min_core = data.get("min_core_version", "3.0.0")
    try:
        Version(min_core)
    except InvalidVersion:
        errors.append(f"{label}: min_core_version 无效: {min_core!r}")

    # schema IDs
    schema_result = validate_schema_ids(
        data["input_schema"], data["output_schema"], data["plugin_type"]
    )
    errors.extend(schema_result.errors)

    # config_schema additionalProperties
    config_schema = data.get("config_schema", {})
    if config_schema and config_schema.get("additionalProperties") is not False:
        warnings.append(
            f"{label}: config_schema 应设置 additionalProperties=false 收紧参数"
        )

    return ValidationResult(ok=not errors, errors=errors, warnings=warnings)


def validate_plugin_source_v3(
    source: str,
    metadata: dict[str, Any] | None = None,
    plugin_type: str = "",
    filename: str = "",
) -> ValidationResult:
    """V3.0 插件源码校验：AST 黑名单 + 类接口检测。

    复用旧校验器的 AST 提取逻辑，扩展 BasePlugin 子类检测。
    """
    try:
        tree = ast.parse(source, filename=filename or "<unknown>")
    except SyntaxError as exc:
        return ValidationResult(ok=False, errors=[f"语法错误: {exc.msg}"])

    # AST 黑名单（与 V2.2 一致）
    safety_issues = _check_import_safety(tree)
    if safety_issues:
        return ValidationResult(ok=False, errors=safety_issues, warnings=list(safety_issues))

    errors: list[str] = []

    if plugin_type:
        # 检查是否继承 BasePlugin（V3.0 新类方式）
        has_base_plugin_subclass = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    base_name = ""
                    if isinstance(base, ast.Name):
                        base_name = base.id
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                    if base_name in ("BasePlugin", "SpiderPlugin", "ParserPlugin",
                                     "RecordProcessorPlugin", "StoragePlugin",
                                     "PresenterPlugin", "UIPlugin"):
                        has_base_plugin_subclass = True
                        break

        if not has_base_plugin_subclass:
            # 兼容旧方式：检查顶层函数
            interface = PLUGIN_INTERFACES.get(plugin_type, "")
            has_legacy_function = any(
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == interface
                for node in tree.body
            )
            if not has_legacy_function:
                errors.append(
                    f"插件必须继承 BasePlugin 子类或实现 {interface}() 顶层函数"
                )

    return ValidationResult(ok=not errors, errors=errors)


def check_content_integrity(
    package_dir: Path,
    expected_hash: str,
) -> ValidationResult:
    """校验批准后包内容摘要是否匹配。

    读取包目录下所有文件计算 SHA-256，与批准时记录的摘要比对。
    """
    import hashlib

    if not package_dir.is_dir():
        return ValidationResult(ok=False, errors=[f"包目录不存在: {package_dir}"])

    hasher = hashlib.sha256()
    file_count = 0

    for file_path in sorted(package_dir.rglob("*")):
        if not file_path.is_file():
            continue
        # 跳过 __pycache__ 和 .pyc
        if "__pycache__" in str(file_path) or file_path.suffix == ".pyc":
            continue
        rel = file_path.relative_to(package_dir)
        hasher.update(str(rel).encode("utf-8"))
        hasher.update(file_path.read_bytes())
        file_count += 1

    actual_hash = hasher.hexdigest()

    if actual_hash != expected_hash:
        return ValidationResult(
            ok=False,
            errors=[
                f"内容摘要不匹配：批准后包内容被篡改。"
                f"期望 {expected_hash[:16]}...，实际 {actual_hash[:16]}..."
            ],
        )

    return ValidationResult(ok=True)


def compute_content_hash(package_dir: Path) -> str:
    """计算包目录的内容摘要（SHA-256）。"""
    import hashlib

    hasher = hashlib.sha256()

    for file_path in sorted(package_dir.rglob("*")):
        if not file_path.is_file():
            continue
        if "__pycache__" in str(file_path) or file_path.suffix == ".pyc":
            continue
        rel = file_path.relative_to(package_dir)
        hasher.update(str(rel).encode("utf-8"))
        hasher.update(file_path.read_bytes())

    return hasher.hexdigest()


__all__ = [
    "KNOWN_SCHEMA_IDS",
    "PLUGIN_BASE_CLASSES",
    "validate_all_metadata",
    "validate_entry_point",
    "validate_schema_ids",
    "validate_metadata",
    "validate_plugin_source_v3",
    "check_content_integrity",
    "compute_content_hash",
]


def validate_all_metadata(plugins_root: Path | None = None) -> list[dict[str, Any]]:
    """扫描所有 metadata.json 并校验，返回缺失字段清单。

    返回格式: [{"path": str, "plugin_id": str, "missing_fields": [str]}]
    仅包含有缺失字段的条目；空列表表示全部通过。
    """
    from plugin_manager.loader import REQUIRED_METADATA_FIELDS, scan_plugin_dirs

    if plugins_root is None:
        plugins_root = Path("plugins")

    descriptors, warnings, errors = scan_plugin_dirs(plugins_root)
    missing_list: list[dict[str, Any]] = []

    for desc in descriptors:
        if not desc.metadata_path.exists():
            continue
        try:
            data = json.loads(desc.metadata_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        missing_fields = [f for f in REQUIRED_METADATA_FIELDS if f not in data or not data[f]]
        if missing_fields:
            missing_list.append({
                "path": str(desc.metadata_path),
                "plugin_id": data.get("id", data.get("name", "(unknown)")),
                "missing_fields": missing_fields,
            })

    return missing_list
