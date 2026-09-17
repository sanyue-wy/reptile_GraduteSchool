# -*- coding: utf-8 -*-
"""插件配置与扩展加载。

插件清单以代码注册表为真值，``plugins.json`` 只保存用户覆盖项和流水线权重。
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import logging
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from security.plugin_validator import (
    BLOCKED_CALLS,
    BLOCKED_MODULES,
    PLUGIN_INTERFACES,
    PLUGIN_META_FIELDS,
    _extract_plugin_meta,
    validate_plugin_source as _validate_source,
)

logger = logging.getLogger(__name__)

PLUGIN_KINDS = (
    "source",
    "fetcher",
    "parser",
    "processor",
    "exporter",
    "presenter",
    "utility",
)

# 校验常量由 security.plugin_validator 定义，在此保留原有导入入口。
PLUGIN_CONFIG_PATH = Path("config/plugins.json")
EXT_PLUGIN_DIR = Path("plugins_ext")

DEFAULT_PLUGIN_CONFIG: dict[str, Any] = {
    "overrides": {},
    "pipeline": {
        "processors": {"merge": 300},
        "exporters": {"jsonl": 100, "xlsx": 200},
    },
}

BUILTIN_METADATA: dict[str, dict[str, dict[str, str]]] = {
    "source": {
        "school_config": {
            "name": "school_config",
            "kind": "source",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "从 config/school_data.json 读取学校与学院数据源配置",
        },
    },
    "fetcher": {
        "static_html": {
            "name": "static_html",
            "kind": "fetcher",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "抓取并解析静态 HTML 师资列表",
        },
        "ajax_api": {
            "name": "ajax_api",
            "kind": "fetcher",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "抓取 SudyCMS/WebPlus AJAX 师资接口",
        },
        "js_render": {
            "name": "js_render",
            "kind": "fetcher",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "使用 Playwright 渲染 JavaScript 师资页面",
        },
        "pdf_list": {
            "name": "pdf_list",
            "kind": "fetcher",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "抓取并解析 PDF 师资名单",
        },
    },
    "presenter": {
        "overview": {
            "name": "overview",
            "kind": "presenter",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "总览面板",
        },
        "schools": {
            "name": "schools",
            "kind": "presenter",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "学校列表与采集进度",
        },
        "tutors": {
            "name": "tutors",
            "kind": "presenter",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "导师数据浏览与导出",
        },
        "failures": {
            "name": "failures",
            "kind": "presenter",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "失败记录与重试",
        },
        "config": {
            "name": "config",
            "kind": "presenter",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "配置与插件管理",
        },
    },
    "utility": {
        "cache": {
            "name": "cache",
            "kind": "utility",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "页面与接口响应缓存",
        },
        "progress": {
            "name": "progress",
            "kind": "utility",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "采集进度与日志追踪",
        },
        "http_session": {
            "name": "http_session",
            "kind": "utility",
            "version": "1.0.0",
            "author": "项目内置",
            "description": "限速、重试、冷却与 User-Agent 会话",
        },
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_plugin_config() -> dict[str, Any]:
    if not PLUGIN_CONFIG_PATH.exists():
        return json.loads(json.dumps(DEFAULT_PLUGIN_CONFIG))
    try:
        data = json.loads(PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("读取插件配置失败: %s", PLUGIN_CONFIG_PATH)
        return json.loads(json.dumps(DEFAULT_PLUGIN_CONFIG))
    return _deep_merge(DEFAULT_PLUGIN_CONFIG, data)


def save_plugin_config(config: dict[str, Any]) -> None:
    PLUGIN_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(PLUGIN_CONFIG_PATH.parent), prefix=".tmp_plugins_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, PLUGIN_CONFIG_PATH)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


def _safe_builtin_plugins() -> dict[str, list[dict[str, str]]]:
    plugins = {kind: [dict(meta) for meta in (BUILTIN_METADATA.get(kind, {}) or {}).values()] for kind in PLUGIN_KINDS}

    try:
        from spiders import ENGINE_REGISTRY
        for plugin_id in sorted(ENGINE_REGISTRY.keys()):
            if plugin_id not in {p["name"] for p in plugins["fetcher"]}:
                plugins["fetcher"].append({
                    "name": plugin_id,
                    "kind": "fetcher",
                    "version": "1.0.0",
                    "author": "项目内置",
                    "description": f"爬虫引擎 {plugin_id}",
                })
    except Exception:
        logger.debug("无法加载 fetcher 注册表，使用内置清单", exc_info=True)

    try:
        from parsers import list_registered
        for template in list_registered():
            if template not in {p["name"] for p in plugins["parser"]}:
                plugins["parser"].append({
                    "name": template,
                    "kind": "parser",
                    "version": "1.0.0",
                    "author": "项目内置",
                    "description": f"解析模板 {template}",
                })
    except Exception:
        logger.debug("无法加载 parser 注册表，使用内置清单", exc_info=True)

    try:
        from processors import list_registered
        for name in list_registered():
            if name not in {p["name"] for p in plugins["processor"]}:
                plugins["processor"].append({
                    "name": name,
                    "kind": "processor",
                    "version": "1.0.0",
                    "author": "项目内置",
                    "description": f"处理器 {name}",
                })
    except Exception:
        logger.debug("无法加载 processor 注册表", exc_info=True)

    try:
        from exporters import list_registered
        for name in list_registered():
            if name not in {p["name"] for p in plugins["exporter"]}:
                plugins["exporter"].append({
                    "name": name,
                    "kind": "exporter",
                    "version": "1.0.0",
                    "author": "项目内置",
                    "description": f"导出器 {name}",
                })
    except Exception:
        logger.debug("无法加载 exporter 注册表", exc_info=True)

    return plugins


def _external_module_name(kind: str, stem: str) -> str:
    safe_stem = re.sub(r"[^0-9a-zA-Z_]", "_", stem)
    return f"plugins_ext.{kind}.{safe_stem}"


def _check_import_safety(source: str) -> list[str]:
    """保留旧入口：返回受限导入/调用或语法错误的诊断列表。"""
    return _validate_source(source).errors


def _validate_plugin_source(source: str, kind: str, filename: str) -> tuple[dict, list[str]]:
    result = _validate_source(source, kind, filename)
    if not result.ok:
        raise ValueError("；".join(result.errors))
    if not kind:
        # 私有完整校验入口要求完整 META 和接口检查，kind 必须有效。
        raise ValueError(f"不支持的插件类型: {kind}")

    # ValidationResult 不携带 META；复用同一提取规则，且不执行源码。
    tree = ast.parse(source, filename=filename or "<unknown>")
    meta = _extract_plugin_meta(tree)
    return meta, result.warnings


def _module_from_path(kind: str, path: Path):
    module_name = _external_module_name(kind, path.stem)
    sys.modules.pop(module_name, None)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ValueError("无法创建插件模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_external_plugins() -> dict[str, dict[str, Any]]:
    discovered: dict[str, dict[str, Any]] = {}
    if not EXT_PLUGIN_DIR.exists():
        return discovered

    for kind_dir in sorted(EXT_PLUGIN_DIR.iterdir()):
        kind = kind_dir.name
        if kind not in PLUGIN_KINDS or not kind_dir.is_dir():
            continue
        for path in sorted(kind_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                source = path.read_text(encoding="utf-8")
                meta, _ = _validate_plugin_source(source, kind, path.name)
                module = _module_from_path(kind, path)
                if not hasattr(module, PLUGIN_INTERFACES[kind]):
                    raise ValueError(f"插件必须实现 {PLUGIN_INTERFACES[kind]}()")
                discovered[f"{kind}:{meta['name']}"] = {
                    "module": module,
                    "meta": meta,
                    "builtin": False,
                    "kind": kind,
                    "id": meta["name"],
                    "path": str(path),
                }
            except Exception as exc:
                logger.warning("插件加载失败 %s: %s", path, exc)
    return discovered


_EXTERNAL_CACHE: dict[str, dict[str, Any]] = {}


def reload_external_plugins() -> dict[str, dict[str, Any]]:
    global _EXTERNAL_CACHE
    for module_name in list(sys.modules.keys()):
        if module_name.startswith("plugins_ext."):
            sys.modules.pop(module_name, None)
    _EXTERNAL_CACHE = discover_external_plugins()
    return _EXTERNAL_CACHE


def _all_external_plugins() -> dict[str, dict[str, Any]]:
    if not EXT_PLUGIN_DIR.exists():
        return {}
    if not _EXTERNAL_CACHE:
        return reload_external_plugins()
    return _EXTERNAL_CACHE


def _plugin_ids(kind: str) -> set[str]:
    ids = {p["name"] for p in _safe_builtin_plugins().get(kind, [])}
    ids.update(info["id"] for info in _all_external_plugins().values() if info["kind"] == kind)
    return ids


def list_plugin_ids(kind: str) -> set[str]:
    return _plugin_ids(kind)


def list_plugins() -> list[dict[str, Any]]:
    config = load_plugin_config()
    overrides = config.get("overrides", {})
    pipeline = config.get("pipeline", {})
    plugins: list[dict[str, Any]] = []

    for builtin in sum(_safe_builtin_plugins().values(), []):
        key = f"{builtin['kind']}:{builtin['name']}"
        override = overrides.get(key, {})
        plugins.append({
            **builtin,
            "id": builtin["name"],
            "builtin": True,
            "enabled": bool(override.get("enabled", True)),
            "config": override.get("config", {}) if isinstance(override, dict) else {},
            "interface": PLUGIN_INTERFACES.get(builtin["kind"], ""),
        })

    for key, info in _all_external_plugins().items():
        override = overrides.get(key, {})
        meta = info.get("meta", {})
        plugins.append({
            "id": info["id"],
            "kind": info["kind"],
            "name": meta.get("name", info["id"]),
            "version": meta.get("version", ""),
            "author": meta.get("author", ""),
            "description": meta.get("description", ""),
            "builtin": False,
            "enabled": bool(override.get("enabled", True)),
            "config": override.get("config", {}) if isinstance(override, dict) else {},
            "interface": PLUGIN_INTERFACES.get(info["kind"], ""),
            "path": info.get("path", ""),
            "config_schema": meta.get("config_schema", {}),
        })

    for plugin in plugins:
        if plugin["kind"] in ("processor", "exporter"):
            plugin["weight"] = pipeline.get(f"{plugin['kind']}s", {}).get(plugin["id"])
    return sorted(plugins, key=lambda p: (PLUGIN_KINDS.index(p["kind"]), p["id"]))


def get_plugin(kind: str, plugin_id: str) -> Optional[dict[str, Any]]:
    if kind not in PLUGIN_KINDS:
        return None
    return next((p for p in list_plugins() if p["kind"] == kind and p["id"] == plugin_id), None)


def update_plugin(kind: str, plugin_id: str, payload: dict[str, Any]) -> Optional[dict[str, Any]]:
    plugin = get_plugin(kind, plugin_id)
    if plugin is None:
        return None
    config = load_plugin_config()
    key = f"{kind}:{plugin_id}"
    override = config.setdefault("overrides", {}).setdefault(key, {})
    if not isinstance(override, dict):
        override = {}
        config["overrides"][key] = override
    if "enabled" in payload:
        override["enabled"] = bool(payload["enabled"])
    if "config" in payload:
        override["config"] = payload["config"] if isinstance(payload["config"], dict) else {}
    save_plugin_config(config)
    reload_external_plugins()
    return get_plugin(kind, plugin_id)


def update_pipeline(pipeline_type: str, weights: dict[str, int]) -> Optional[dict[str, int]]:
    if pipeline_type not in ("processors", "exporters"):
        return None
    cleaned: dict[str, int] = {}
    for plugin_id, weight in weights.items():
        if plugin_id not in list_plugin_ids(pipeline_type[:-1]):
            continue
        try:
            cleaned[plugin_id] = int(weight)
        except (TypeError, ValueError):
            continue
    config = load_plugin_config()
    config.setdefault("pipeline", {})[pipeline_type] = cleaned
    save_plugin_config(config)
    return cleaned


def upload_plugin(kind: str, filename: str, source: str) -> dict[str, Any]:
    if kind not in PLUGIN_KINDS:
        raise ValueError(f"不支持的插件类型: {kind}")
    meta, _ = _validate_plugin_source(source, kind, filename)
    safe_name = re.sub(r"[^0-9a-zA-Z_.-]", "_", filename)
    if not safe_name.endswith(".py"):
        safe_name += ".py"
    target_dir = EXT_PLUGIN_DIR / kind
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / safe_name
    target.write_text(source, encoding="utf-8")
    try:
        _module_from_path(kind, target)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    reload_external_plugins()
    plugin = get_plugin(kind, meta["name"])
    if plugin is None:
        raise ValueError("插件已保存但无法注册")
    return plugin


def delete_plugin(kind: str, plugin_id: str) -> bool:
    info = _all_external_plugins().get(f"{kind}:{plugin_id}")
    if info is None:
        return False
    path = Path(info["path"])
    if path.exists():
        path.unlink()
    config = load_plugin_config()
    config.get("overrides", {}).pop(f"{kind}:{plugin_id}", None)
    save_plugin_config(config)
    reload_external_plugins()
    return True


def reload_plugin(kind: str, plugin_id: str) -> Optional[dict[str, Any]]:
    if get_plugin(kind, plugin_id) is None:
        return None
    reload_external_plugins()
    return get_plugin(kind, plugin_id)


def is_enabled(kind: str, plugin_id: str) -> bool:
    plugin = get_plugin(kind, plugin_id)
    return bool(plugin and plugin.get("enabled", True))


def plugin_config(kind: str, plugin_id: str) -> dict[str, Any]:
    plugin = get_plugin(kind, plugin_id)
    return dict(plugin.get("config", {})) if plugin else {}


__all__ = [
    "PLUGIN_KINDS",
    "PLUGIN_INTERFACES",
    "PLUGIN_CONFIG_PATH",
    "EXT_PLUGIN_DIR",
    "list_plugins",
    "get_plugin",
    "list_plugin_ids",
    "update_plugin",
    "update_pipeline",
    "upload_plugin",
    "delete_plugin",
    "reload_plugin",
    "reload_external_plugins",
    "is_enabled",
    "plugin_config",
]
