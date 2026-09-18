# -*- coding: utf-8 -*-
"""插件注册表与生命周期状态机。

扫描元数据（不 import）→ 结构/版本/依赖/包路径校验 → AST 静态审查
→ pending_review → approved(绑定完整包内容摘要) → loaded → registry 快照发布。

规则：未知包/名称冲突/min_core_version 不兼容/批准后内容摘要变化 → 拒绝；
禁用插件不得 import；按实例禁用。
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import logging
import sys
import tempfile
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from plugin_manager.loader import PluginDescriptor, scan_metadata, scan_plugin_dirs
from plugin_manager.validator import (
    check_content_integrity,
    compute_content_hash,
    validate_entry_point,
    validate_metadata,
)
from security.plugin_validator_v3 import validate_v3_plugin
from security.plugin_validator import ValidationResult

logger = logging.getLogger(__name__)


class PluginState(str, Enum):
    """插件生命周期状态。"""
    DISCOVERED = "discovered"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    LOADED = "loaded"
    DISABLED = "disabled"
    REJECTED = "rejected"


@dataclass
class PluginEntry:
    """注册表中的单个插件条目。"""
    descriptor: PluginDescriptor
    state: PluginState = PluginState.DISCOVERED
    content_hash: str = ""
    approved_by: str = ""
    approved_at: str = ""
    reject_reason: str = ""
    requires_restart: bool = False
    reference_count: int = 0
    module: Any = None  # loaded 后才有值


@dataclass
class RegistrySnapshot:
    """不可变的注册表快照。"""
    registry_revision: int
    created_at: str
    plugins: dict[str, PluginEntry]
    frozen: bool = True

    def get_plugin(self, plugin_id: str) -> PluginEntry | None:
        return self.plugins.get(plugin_id)

    def get_loaded_plugins(self, plugin_type: str = "") -> list[PluginEntry]:
        entries = [
            e for e in self.plugins.values()
            if e.state == PluginState.LOADED
        ]
        if plugin_type:
            entries = [e for e in entries if e.descriptor.plugin_type == plugin_type]
        return entries

    def to_dict(self) -> dict[str, Any]:
        return {
            "registry_revision": self.registry_revision,
            "created_at": self.created_at,
            "plugin_count": len(self.plugins),
            "loaded_count": sum(
                1 for e in self.plugins.values() if e.state == PluginState.LOADED
            ),
            "plugins": {
                pid: {
                    "name": e.descriptor.name,
                    "version": e.descriptor.version,
                    "plugin_type": e.descriptor.plugin_type,
                    "state": e.state.value,
                    "content_hash": e.content_hash[:16] if e.content_hash else "",
                }
                for pid, e in self.plugins.items()
            },
        }


class PluginRegistry:
    """插件注册表：管理发现、校验、批准、加载的完整生命周期。"""

    def __init__(self, core_version: str = "3.0.0"):
        self._entries: dict[str, PluginEntry] = {}
        self._revision: int = 0
        self._snapshots: list[RegistrySnapshot] = []
        self._core_version = core_version
        self._audit_log: list[dict[str, Any]] = []

    @property
    def current_revision(self) -> int:
        return self._revision

    @property
    def current_snapshot(self) -> RegistrySnapshot | None:
        return self._snapshots[-1] if self._snapshots else None

    @property
    def audit_log(self) -> list[dict[str, Any]]:
        return list(self._audit_log)

    def _audit(self, action: str, plugin_id: str, **kwargs: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "plugin_id": plugin_id,
            **kwargs,
        }
        self._audit_log.append(entry)
        logger.info("审计: %s %s %s", action, plugin_id, kwargs)

    def _publish_snapshot(self) -> RegistrySnapshot:
        """发布新的不可变快照。"""
        self._revision += 1
        snapshot = RegistrySnapshot(
            registry_revision=self._revision,
            created_at=datetime.now(timezone.utc).isoformat(),
            plugins=dict(self._entries),
        )
        self._snapshots.append(snapshot)
        logger.info("注册表快照 v%d 已发布 (%d 插件)", self._revision, len(self._entries))
        return snapshot

    # ── 发现阶段 ──

    def scan(self, plugins_root: Path | None = None) -> tuple[int, list[str]]:
        """扫描插件目录，发现所有 metadata.json。

        Returns:
            (发现数量, 错误/告警列表)
        """
        descriptors, warnings, errors = scan_plugin_dirs(plugins_root)
        messages: list[str] = list(warnings)

        for desc in descriptors:
            pid = desc.plugin_id

            # 名称冲突检查
            if pid in self._entries:
                existing = self._entries[pid]
                if existing.descriptor.version != desc.version:
                    messages.append(
                        f"版本冲突: {pid} 已注册 v{existing.descriptor.version}，"
                        f"发现 v{desc.version}"
                    )
                    continue

            # 版本兼容性检查
            if not desc.core_version_compatible(self._core_version):
                messages.append(
                    f"版本不兼容: {pid} 要求核心 {desc.min_core_version}，"
                    f"当前 {self._core_version}"
                )
                self._entries[pid] = PluginEntry(
                    descriptor=desc,
                    state=PluginState.REJECTED,
                    reject_reason="min_core_version 不兼容",
                )
                continue

            # 结构校验
            meta_data = desc.to_dict()
            meta_result = validate_metadata(meta_data, desc.metadata_path)
            if not meta_result.ok:
                messages.append(f"结构校验失败 {pid}: {'; '.join(meta_result.errors)}")
                self._entries[pid] = PluginEntry(
                    descriptor=desc,
                    state=PluginState.REJECTED,
                    reject_reason="; ".join(meta_result.errors),
                )
                continue

            # entry_point 格式校验和文件可达性
            ep_result = validate_entry_point(desc.entry_point, desc.package_dir)
            if not ep_result.ok:
                messages.append(f"entry_point 不可达 {pid}: {'; '.join(ep_result.errors)}")
                self._entries[pid] = PluginEntry(
                    descriptor=desc,
                    state=PluginState.REJECTED,
                    reject_reason="; ".join(ep_result.errors),
                )
                continue

            # AST 静态审查（只检查 entry_point 对应的源文件）
            if desc.package_dir and desc.package_dir.is_dir():
                entry_module = desc.entry_point.split(":")[0]
                entry_parts = entry_module.split(".")
                # entry_point 格式：plugins.spiders.static_html.plugin:Class
                # 对应文件：package_dir / plugin.py
                entry_filename = entry_parts[-1] + ".py"
                entry_file = desc.package_dir / entry_filename

                if entry_file.exists():
                    try:
                        source = entry_file.read_text(encoding="utf-8")
                        ast_result = validate_v3_plugin(
                            source, desc.to_dict(), desc.plugin_type, entry_filename
                        )
                        if not ast_result.ok:
                            messages.append(
                                f"AST 审查失败 {pid}/{entry_filename}: "
                                f"{'; '.join(ast_result.errors)}"
                            )
                            self._entries[pid] = PluginEntry(
                                descriptor=desc,
                                state=PluginState.REJECTED,
                                reject_reason="; ".join(ast_result.errors),
                            )
                            continue
                    except (OSError, UnicodeError) as exc:
                        messages.append(f"读取源码失败 {entry_file}: {exc}")

                # 同时检查包内其他 .py 文件的安全性（仅危险调用，不要求继承）
                for py_file in desc.package_dir.glob("*.py"):
                    if py_file.name.startswith("_") or py_file.name == entry_filename:
                        continue
                    try:
                        source = py_file.read_text(encoding="utf-8")
                        from security.plugin_validator_v3 import _check_v3_safety
                        import ast as _ast
                        tree = _ast.parse(source)
                        safety = _check_v3_safety(tree)
                        if safety:
                            messages.append(
                                f"安全审查失败 {pid}/{py_file.name}: "
                                f"{'; '.join(safety)}"
                            )
                            self._entries[pid] = PluginEntry(
                                descriptor=desc,
                                state=PluginState.REJECTED,
                                reject_reason="; ".join(safety),
                            )
                            break
                    except (OSError, UnicodeError, SyntaxError) as exc:
                        messages.append(f"读取源码失败 {py_file}: {exc}")

                if pid not in self._entries or self._entries[pid].state != PluginState.REJECTED:
                    self._entries[pid] = PluginEntry(
                        descriptor=desc,
                        state=PluginState.PENDING_REVIEW,
                    )
                    self._audit("discovered", pid, version=desc.version)
            else:
                self._entries[pid] = PluginEntry(
                    descriptor=desc,
                    state=PluginState.PENDING_REVIEW,
                )
                self._audit("discovered", pid, version=desc.version)

        messages.extend(errors)
        return len(descriptors), messages

    # ── 审批阶段 ──

    def approve(
        self,
        plugin_id: str,
        admin_id: str = "system",
    ) -> tuple[bool, str]:
        """批准插件，绑定内容摘要。

        Returns:
            (成功, 消息)
        """
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False, f"插件不存在: {plugin_id}"

        if entry.state not in (PluginState.PENDING_REVIEW, PluginState.REJECTED):
            return False, f"插件状态 {entry.state.value} 不可批准，需要 pending_review"

        # 计算内容摘要
        pkg_dir = entry.descriptor.package_dir
        if pkg_dir and pkg_dir.is_dir():
            content_hash = compute_content_hash(pkg_dir)
        else:
            content_hash = ""

        entry.state = PluginState.APPROVED
        entry.content_hash = content_hash
        entry.approved_by = admin_id
        entry.approved_at = datetime.now(timezone.utc).isoformat()
        entry.reject_reason = ""

        self._audit(
            "approved", plugin_id,
            admin_id=admin_id,
            version=entry.descriptor.version,
            content_hash=content_hash[:16],
        )

        self._publish_snapshot()
        return True, f"已批准 {plugin_id} v{entry.descriptor.version}"

    def reject(self, plugin_id: str, reason: str) -> tuple[bool, str]:
        """拒绝插件。"""
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False, f"插件不存在: {plugin_id}"

        entry.state = PluginState.REJECTED
        entry.reject_reason = reason
        self._audit("rejected", plugin_id, reason=reason)
        return True, f"已拒绝 {plugin_id}: {reason}"

    # ── 加载阶段 ──

    def load(self, plugin_id: str) -> tuple[bool, str]:
        """加载已批准的插件（动态 import entry_point）。

        Returns:
            (成功, 消息)
        """
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False, f"插件不存在: {plugin_id}"

        if entry.state == PluginState.DISABLED:
            return False, f"插件已禁用: {plugin_id}"

        if entry.state != PluginState.APPROVED:
            return False, f"插件状态 {entry.state.value} 不可加载，需要 approved"

        desc = entry.descriptor

        # 内容摘要校验（批准后篡改检测）
        if entry.content_hash and desc.package_dir and desc.package_dir.is_dir():
            integrity = check_content_integrity(desc.package_dir, entry.content_hash)
            if not integrity.ok:
                entry.state = PluginState.REJECTED
                entry.reject_reason = "批准后内容被篡改"
                self._audit("tampered", plugin_id)
                self._publish_snapshot()
                return False, f"批准后内容被篡改: {plugin_id}"

        # 动态 import
        try:
            module = self._import_entry_point(desc.entry_point)
        except Exception as exc:
            entry.state = PluginState.REJECTED
            entry.reject_reason = f"import 失败: {exc}"
            self._audit("import_failed", plugin_id, error=str(exc))
            self._publish_snapshot()
            return False, f"import 失败: {exc}"

        # 基类验证
        class_name = desc.entry_point.split(":")[-1]
        if not hasattr(module, class_name):
            entry.state = PluginState.REJECTED
            entry.reject_reason = f"模块中未找到类 {class_name}"
            self._publish_snapshot()
            return False, f"模块中未找到类 {class_name}"

        cls = getattr(module, class_name)
        if not isinstance(cls, type):
            entry.state = PluginState.REJECTED
            entry.reject_reason = f"{class_name} 不是类"
            self._publish_snapshot()
            return False, f"{class_name} 不是类"

        entry.state = PluginState.LOADED
        entry.module = module
        self._audit("loaded", plugin_id, version=desc.version)
        self._publish_snapshot()
        return True, f"已加载 {plugin_id} v{desc.version}"

    def _import_entry_point(self, entry_point: str) -> Any:
        """动态 import entry_point，不使用 exec/eval。"""
        module_path, class_name = entry_point.split(":", 1)

        # 如果已导入，直接返回
        if module_path in sys.modules:
            return sys.modules[module_path]

        # 尝试标准 import
        try:
            return importlib.import_module(module_path)
        except ImportError:
            pass

        # 尝试文件路径导入：将 module path 转为文件路径
        parts = module_path.split(".")
        # 从项目根目录尝试解析
        file_path = Path(*parts).with_suffix(".py")
        if not file_path.exists():
            # 尝试包目录（__init__.py）
            pkg_path = Path(*parts) / "__init__.py"
            if pkg_path.exists():
                file_path = pkg_path
            else:
                raise ImportError(
                    f"无法定位模块文件: {file_path} 或 {pkg_path}"
                )

        spec = importlib.util.spec_from_file_location(module_path, str(file_path))
        if spec is None or spec.loader is None:
            raise ImportError(f"无法创建模块 spec: {module_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_path] = module
        spec.loader.exec_module(module)
        return module

    # ── 管理操作 ──

    def disable(self, plugin_id: str) -> tuple[bool, str]:
        """禁用插件（不删除，保留注册）。"""
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False, f"插件不存在: {plugin_id}"

        if entry.state == PluginState.LOADED and entry.reference_count > 0:
            return False, (
                f"插件 {plugin_id} 有 {entry.reference_count} 个活动引用，"
                "不可禁用；等待运行完成后重试"
            )

        old_state = entry.state
        entry.state = PluginState.DISABLED
        self._audit("disabled", plugin_id, old_state=old_state.value)
        self._publish_snapshot()
        return True, f"已禁用 {plugin_id}"

    def enable(self, plugin_id: str) -> tuple[bool, str]:
        """重新启用已禁用的插件。"""
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False, f"插件不存在: {plugin_id}"

        if entry.state != PluginState.DISABLED:
            return False, f"插件状态 {entry.state.value} 不是禁用状态"

        entry.state = PluginState.APPROVED
        self._audit("enabled", plugin_id)
        self._publish_snapshot()
        return True, f"已启用 {plugin_id}"

    def acquire_reference(self, plugin_id: str) -> bool:
        """增加引用计数（运行开始时调用）。"""
        entry = self._entries.get(plugin_id)
        if entry is None or entry.state != PluginState.LOADED:
            return False
        entry.reference_count += 1
        return True

    def release_reference(self, plugin_id: str) -> bool:
        """减少引用计数（运行结束时调用）。"""
        entry = self._entries.get(plugin_id)
        if entry is None:
            return False
        entry.reference_count = max(0, entry.reference_count - 1)
        return True

    # ── 查询接口 ──

    def get_entry(self, plugin_id: str) -> PluginEntry | None:
        return self._entries.get(plugin_id)

    def get_state(self, plugin_id: str) -> PluginState | None:
        entry = self._entries.get(plugin_id)
        return entry.state if entry else None

    def list_entries(
        self,
        state: PluginState | None = None,
        plugin_type: str = "",
    ) -> list[PluginEntry]:
        entries = list(self._entries.values())
        if state is not None:
            entries = [e for e in entries if e.state == state]
        if plugin_type:
            entries = [e for e in entries if e.descriptor.plugin_type == plugin_type]
        return entries

    def freeze_revision(self) -> int:
        """返回当前 revision，供运行开始时冻结。"""
        return self._revision

    def snapshot_for_run(self) -> RegistrySnapshot:
        """获取当前快照供运行使用。如果没有快照则发布一个。"""
        if not self._snapshots:
            self._publish_snapshot()
        return self._snapshots[-1]

    # ── 预检函数（供 W2 POST /api/pipeline/validate 调用）──

    def validate_pipeline_config(
        self,
        instances: dict[str, Any],
        pipeline_config: dict[str, Any] | None = None,
    ) -> ValidationResult:
        """预检：拒绝未知 ID、重复实例、禁用却被引用、schema 不匹配、依赖缺失。

        不执行任何插件代码。
        """
        errors: list[str] = []
        warnings: list[str] = []

        if not self._snapshots:
            return ValidationResult(
                ok=False,
                errors=["注册表未初始化，请先运行 scan()"],
            )

        snapshot = self._snapshots[-1]
        seen_ids: set[str] = set()

        for instance_name, instance_config in instances.items():
            if not isinstance(instance_config, dict):
                errors.append(f"实例 {instance_name}: 配置格式无效")
                continue

            plugin_ref = instance_config.get("plugin", "")
            if not plugin_ref:
                errors.append(f"实例 {instance_name}: 缺少 plugin 引用")
                continue

            # 格式：type:name
            if ":" not in plugin_ref:
                errors.append(f"实例 {instance_name}: plugin 引用格式应为 type:name")
                continue

            plugin_id = plugin_ref
            entry = snapshot.get_plugin(plugin_id)

            if entry is None:
                errors.append(f"实例 {instance_name}: 引用未知插件 {plugin_id}")
                continue

            # 重复实例检查
            if plugin_id in seen_ids:
                warnings.append(f"实例 {instance_name}: 插件 {plugin_id} 被多次引用")
            seen_ids.add(plugin_id)

            # 禁用检查
            if instance_config.get("enabled", True) is False:
                warnings.append(f"实例 {instance_name}: 已禁用")

            # schema 匹配（如果 pipeline_config 提供了输入/输出链信息）
            if entry.state not in (PluginState.APPROVED, PluginState.LOADED):
                errors.append(
                    f"实例 {instance_name}: 插件 {plugin_id} "
                    f"状态为 {entry.state.value}，不可用于执行"
                )

        return ValidationResult(
            ok=not errors,
            errors=errors,
            warnings=warnings,
        )


# ── 上传流程（待审区）──

UPLOAD_DIR = Path("data/plugin_uploads")


def upload_to_pending(
    filename: str,
    source: str,
    metadata: dict[str, Any],
    registry: PluginRegistry,
) -> tuple[bool, str]:
    """上传插件到待审区。

    只写 data/plugin_uploads/，不参与发现、不执行。
    返回"已接收、待批准"状态。
    """
    import re as _re

    # 基本校验
    meta_result = validate_metadata(metadata)
    if not meta_result.ok:
        return False, f"元数据校验失败: {'; '.join(meta_result.errors)}"

    # AST 校验
    ast_result = validate_v3_plugin(
        source, metadata, metadata.get("plugin_type", "")
    )
    if not ast_result.ok:
        return False, f"源码校验失败: {'; '.join(ast_result.errors)}"

    # 安全文件名
    safe_name = _re.sub(r"[^0-9a-zA-Z_.-]", "_", filename)
    if not safe_name.endswith(".py"):
        safe_name += ".py"

    plugin_name = metadata.get("name", "unknown")
    pkg_dir = UPLOAD_DIR / plugin_name
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # 写入源码
    target = pkg_dir / safe_name
    fd, tmp_path = tempfile.mkstemp(
        dir=str(pkg_dir), prefix=".tmp_upload_", suffix=".py"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(source)
        os.replace(tmp_path, target)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    # 写入 metadata.json
    meta_path = pkg_dir / "metadata.json"
    fd, tmp_meta = tempfile.mkstemp(
        dir=str(pkg_dir), prefix=".tmp_meta_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        os.replace(tmp_meta, meta_path)
    except Exception:
        if os.path.exists(tmp_meta):
            os.unlink(tmp_meta)
        raise

    plugin_id = f"{metadata['plugin_type']}:{plugin_name}"
    registry._audit(
        "uploaded", plugin_id,
        version=metadata.get("version", "unknown"),
        filename=safe_name,
    )

    return True, f"已接收 {plugin_id}，待管理员批准"


def approve_upload(
    plugin_name: str,
    plugin_type: str,
    admin_id: str,
    registry: PluginRegistry,
    plugins_root: Path | None = None,
) -> tuple[bool, str]:
    """批准待审区的插件，移到正式目录。

    要求管理员权限标识 + 记录审计条目。
    """
    if plugins_root is None:
        plugins_root = Path("plugins")

    plugin_id = f"{plugin_type}:{plugin_name}"
    pending_dir = UPLOAD_DIR / plugin_name

    if not pending_dir.is_dir():
        return False, f"待审区未找到: {plugin_name}"

    # 读取 metadata 确认一致性
    meta_path = pending_dir / "metadata.json"
    if not meta_path.exists():
        return False, f"待审区缺少 metadata.json: {plugin_name}"

    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"metadata.json 解析失败: {exc}"

    if data.get("plugin_type") != plugin_type:
        return False, (
            f"plugin_type 不匹配: 期望 {plugin_type}，"
            f"实际 {data.get('plugin_type')}"
        )

    # 移动到正式目录
    target_dir = plugins_root / _PLUGIN_TYPE_TO_DIR.get(plugin_type, plugin_type) / plugin_name
    target_dir.parent.mkdir(parents=True, exist_ok=True)

    if target_dir.exists():
        return False, f"正式目录已存在: {target_dir}，需先处理冲突"

    # 原子操作：复制后删除
    import shutil
    shutil.copytree(str(pending_dir), str(target_dir))

    # 计算内容摘要
    content_hash = compute_content_hash(target_dir)

    # 删除待审区
    shutil.rmtree(str(pending_dir))

    # 如果在注册表中，更新状态
    entry = registry._entries.get(plugin_id)
    if entry:
        entry.state = PluginState.APPROVED
        entry.content_hash = content_hash
        entry.approved_by = admin_id
        entry.approved_at = datetime.now(timezone.utc).isoformat()
        registry._publish_snapshot()

    registry._audit(
        "upload_approved", plugin_id,
        admin_id=admin_id,
        version=data.get("version", "unknown"),
        content_hash=content_hash[:16],
    )

    return True, f"已批准并移入正式目录: {plugin_id}"


# 插件类型 → 目录名映射
_PLUGIN_TYPE_TO_DIR = {
    "spider": "spiders",
    "processor": "processors",
    "storage": "storage",
    "presenter": "presenters",
    "ui": "ui",
}


__all__ = [
    "PluginState",
    "PluginEntry",
    "RegistrySnapshot",
    "PluginRegistry",
    "upload_to_pending",
    "approve_upload",
    "UPLOAD_DIR",
]
