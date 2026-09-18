# -*- coding: utf-8 -*-
"""metadata.json 扫描发现器。

扫描 plugins/ 及 data/plugin_uploads/ 下的 metadata.json，
不 import 任何插件代码。metadata.json 是 V3.0 唯一真值源。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion, Version

logger = logging.getLogger(__name__)

PLUGIN_TYPES = ("spider", "processor", "storage", "presenter", "ui")

REQUIRED_METADATA_FIELDS = (
    "name",
    "version",
    "author",
    "license",
    "plugin_type",
    "input_schema",
    "output_schema",
    "entry_point",
)

OPTIONAL_METADATA_FIELDS = (
    "dependencies",
    "min_core_version",
    "config_schema",
    "description",
)

VALID_ENTRY_POINT_RE = re.compile(
    r"^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$"
)

GPL_LICENSE_PATTERNS = re.compile(r"\b(AGPL|GPL|LGPL)\b", re.IGNORECASE)

DEFAULT_MIN_CORE_VERSION = "3.0.0"

# 插件目录名 → plugin_type 映射
_DIR_TO_TYPE = {
    "spiders": "spider",
    "processors": "processor",
    "storage": "storage",
    "presenters": "presenter",
    "ui": "ui",
}


class MetadataError(Exception):
    """metadata.json 校验失败。"""


class PluginDescriptor:
    """扫描阶段发现的插件描述，不持有模块引用。"""

    __slots__ = (
        "name",
        "version",
        "author",
        "plugin_type",
        "input_schema",
        "output_schema",
        "entry_point",
        "dependencies",
        "min_core_version",
        "config_schema",
        "license",
        "description",
        "metadata_path",
        "package_dir",
    )

    def __init__(
        self,
        name: str,
        version: str,
        author: str,
        plugin_type: str,
        input_schema: str,
        output_schema: str,
        entry_point: str,
        dependencies: list[str] | None = None,
        min_core_version: str = DEFAULT_MIN_CORE_VERSION,
        config_schema: dict[str, Any] | None = None,
        license: str = "",
        description: str = "",
        metadata_path: Path | None = None,
        package_dir: Path | None = None,
    ):
        self.name = name
        self.version = version
        self.author = author
        self.plugin_type = plugin_type
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.entry_point = entry_point
        self.dependencies = dependencies or []
        self.min_core_version = min_core_version
        self.config_schema = config_schema or {}
        self.license = license
        self.description = description
        self.metadata_path = metadata_path
        self.package_dir = package_dir

    @property
    def plugin_id(self) -> str:
        return f"{self.plugin_type}:{self.name}"

    def core_version_compatible(self, core_version: str = "3.0.0") -> bool:
        try:
            return Version(core_version) >= Version(self.min_core_version)
        except InvalidVersion:
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "plugin_type": self.plugin_type,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "entry_point": self.entry_point,
            "dependencies": self.dependencies,
            "min_core_version": self.min_core_version,
            "config_schema": self.config_schema,
            "license": self.license,
            "description": self.description,
        }


def _parse_metadata_json(path: Path) -> dict[str, Any]:
    """读取并解析 metadata.json，返回原始 dict。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise MetadataError(f"无法读取 {path}: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MetadataError(f"JSON 解析失败 {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise MetadataError(f"metadata.json 必须是对象: {path}")
    return data


def validate_metadata_fields(data: dict[str, Any], path: Path) -> None:
    """校验 metadata.json 必须字段和基本约束。"""
    missing = [f for f in REQUIRED_METADATA_FIELDS if f not in data]
    if missing:
        raise MetadataError(f"{path}: 缺少必须字段: {', '.join(missing)}")

    if data["plugin_type"] not in PLUGIN_TYPES:
        raise MetadataError(
            f"{path}: plugin_type 必须是 {PLUGIN_TYPES} 之一，"
            f"实际为 {data['plugin_type']!r}"
        )

    if not VALID_ENTRY_POINT_RE.match(data["entry_point"]):
        raise MetadataError(
            f"{path}: entry_point 格式无效 (应为 module.path:ClassName): "
            f"{data['entry_point']!r}"
        )

    try:
        Version(data["version"])
    except InvalidVersion as exc:
        raise MetadataError(f"{path}: version 无效: {exc}") from exc

    min_core = data.get("min_core_version", DEFAULT_MIN_CORE_VERSION)
    try:
        Version(min_core)
    except InvalidVersion as exc:
        raise MetadataError(f"{path}: min_core_version 无效: {exc}") from exc


def _check_license_policy(data: dict[str, Any], path: Path) -> list[str]:
    """检查许可证策略，返回告警列表（不阻断）。

    缺 license 且 dependencies 非空：对内置插件降级为警告，
    对外部/上传插件由 registry 在审批阶段拦截。
    """
    warnings: list[str] = []
    license_val = data.get("license", "")
    dependencies = data.get("dependencies", [])

    if GPL_LICENSE_PATTERNS.search(license_val):
        warnings.append(
            f"{path}: 许可证声明含 GPL 类 ({license_val})，加载时将告警"
        )

    if not license_val and dependencies:
        # 降级为警告：由审批阶段拦截未经许可声明的外部插件
        warnings.append(
            f"{path}: 缺少 license 字段且有依赖声明 ({', '.join(dependencies)})，"
            "建议补充许可证声明"
        )

    return warnings


def scan_metadata(metadata_path: Path) -> tuple[PluginDescriptor, list[str]]:
    """扫描单个 metadata.json，返回描述符和告警。"""
    data = _parse_metadata_json(metadata_path)
    validate_metadata_fields(data, metadata_path)
    warnings = _check_license_policy(data, metadata_path)

    descriptor = PluginDescriptor(
        name=data["name"],
        version=data["version"],
        author=data["author"],
        plugin_type=data["plugin_type"],
        input_schema=data["input_schema"],
        output_schema=data["output_schema"],
        entry_point=data["entry_point"],
        dependencies=data.get("dependencies", []),
        min_core_version=data.get("min_core_version", DEFAULT_MIN_CORE_VERSION),
        config_schema=data.get("config_schema", {}),
        license=data.get("license", ""),
        description=data.get("description", ""),
        metadata_path=metadata_path,
        package_dir=metadata_path.parent,
    )
    return descriptor, warnings


def scan_plugin_dirs(
    plugins_root: Path | None = None,
    upload_root: Path | None = None,
) -> tuple[list[PluginDescriptor], list[str], list[str]]:
    """扫描 plugins/ 和可选的待审区，返回 (描述符列表, 告警, 错误)。"""
    from config.plugins import EXT_PLUGIN_DIR, PLUGIN_CONFIG_PATH

    if plugins_root is None:
        plugins_root = Path("plugins")
    if upload_root is None:
        upload_root = Path("data/plugin_uploads")

    descriptors: list[PluginDescriptor] = []
    all_warnings: list[str] = []
    all_errors: list[str] = []

    # 扫描正式插件目录
    if plugins_root.exists():
        for type_dir in sorted(plugins_root.iterdir()):
            if not type_dir.is_dir() or type_dir.name.startswith("_"):
                continue
            expected_type = _DIR_TO_TYPE.get(type_dir.name)
            if expected_type is None:
                continue
            for pkg_dir in sorted(type_dir.iterdir()):
                if not pkg_dir.is_dir() or pkg_dir.name.startswith("_"):
                    continue
                meta_path = pkg_dir / "metadata.json"
                if not meta_path.exists():
                    continue
                try:
                    desc, warns = scan_metadata(meta_path)
                    if desc.plugin_type != expected_type:
                        all_errors.append(
                            f"{meta_path}: plugin_type={desc.plugin_type!r} "
                            f"与目录 {type_dir.name!r} 不匹配"
                        )
                        continue
                    descriptors.append(desc)
                    all_warnings.extend(warns)
                except MetadataError as exc:
                    all_errors.append(str(exc))

    # 扫描待审区（不参与可执行发现，仅用于审批流程）
    if upload_root.exists():
        for pkg_dir in sorted(upload_root.iterdir()):
            if not pkg_dir.is_dir() or pkg_dir.name.startswith("_"):
                continue
            meta_path = pkg_dir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                desc, warns = scan_metadata(meta_path)
                # 待审区的标记为 pending，不加入可执行描述符
                all_warnings.append(
                    f"待审区发现: {desc.plugin_id} (v{desc.version})，"
                    "需管理员批准后方可加载"
                )
                all_warnings.extend(warns)
            except MetadataError as exc:
                all_errors.append(f"[待审] {exc}")

    return descriptors, all_warnings, all_errors
