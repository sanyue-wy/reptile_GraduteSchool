# -*- coding: utf-8 -*-
"""插件错误上报与聚合。

负责收集、存储和聚合插件运行时错误，支持通过 REST 接口查询。
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = __import__('logging').getLogger(__name__)

# 错误存储目录
ERRORS_DIR = Path("data/output/plugin_errors")


@dataclass
class PluginErrorContext:
    """插件错误上下文。"""
    plugin_name: str
    plugin_type: str
    error_type: str  # ImportError, ValidationError, RuntimeError 等
    error_message: str
    traceback: str | None = None
    stack: list[dict[str, Any]] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    registry_revision: int = 0
    run_id: str | None = None


def report(ctx: PluginErrorContext, errors_dir: Path | None = None) -> Path:
    """上报插件错误，写入 JSON 文件。

    Args:
        ctx: 错误上下文
        errors_dir: 存储目录，默认 data/output/plugin_errors

    Returns:
        写入的文件路径
    """
    if errors_dir is None:
        errors_dir = ERRORS_DIR

    errors_dir.mkdir(parents=True, exist_ok=True)

    # 生成文件名: <插件名>_<时间戳>.json
    timestamp_ns = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    safe_name = ctx.plugin_name.replace("/", "_").replace("\\", "_")
    filename = f"{safe_name}_{timestamp_ns}.json"
    filepath = errors_dir / filename

    # 写入 JSON
    data = asdict(ctx)
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        logger.exception(f"写入错误报告失败: {filepath}")
        raise

    logger.warning(
        "插件错误上报: %s (%s) - %s",
        ctx.plugin_name, ctx.error_type, ctx.error_message[:100]
    )

    return filepath


def _load_error_files(errors_dir: Path | None = None, limit: int = 100) -> list[dict[str, Any]]:
    """加载错误文件，返回列表（按时间倒序）。"""
    if errors_dir is None:
        errors_dir = ERRORS_DIR

    if not errors_dir.exists():
        return []

    files = []
    for f in sorted(errors_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                data["_filepath"] = str(f)
                files.append(data)
                if len(files) >= limit:
                    break
        except (json.JSONDecodeError, OSError):
            continue

    return files


def has_recent_error(plugin_name: str, hours: int = 24, errors_dir: Path | None = None) -> bool:
    """检查指定插件最近 N 小时内是否有错误。"""
    import time
    if errors_dir is None:
        errors_dir = ERRORS_DIR

    if not errors_dir.exists():
        return False

    cutoff = time.time() - (hours * 3600)
    safe_name = plugin_name.replace("/", "_").replace("\\", "_")

    for f in errors_dir.glob(f"{safe_name}_*.json"):
        try:
            if f.stat().st_mtime > cutoff:
                return True
        except OSError:
            continue

    return False


def get_recent_errors(plugin_name: str | None = None, limit: int = 10, errors_dir: Path | None = None) -> list[dict[str, Any]]:
    """获取最近的错误记录。

    Args:
        plugin_name: 如果提供，仅返回该插件的错误
        limit: 最多返回多少条
        errors_dir: 存储目录

    Returns:
        错误列表（按时间倒序）
    """
    files = _load_error_files(errors_dir, limit * 10)  # 加载更多做筛选

    if plugin_name:
        safe_name = plugin_name.replace("/", "_").replace("\\", "_")
        files = [f for f in files if f.get("plugin_name") == safe_name or Path(f.get("_filepath", "")).stem.startswith(safe_name)]

    return files[:limit]


def _extract_domain_from_url(url: str) -> str | None:
    """从 URL 或错误消息中提取域名。"""
    import re
    # 匹配 https://domain.com 或 http://domain.com 开头的 URL
    match = re.search(r'https?://([^/\s]+)', url)
    if match:
        return match.group(1)
    return None


def _normalize_error_message(message: str) -> str:
    """归一化错误消息：剥离 IP、端口、路径、时间戳、数字 ID。"""
    import re

    text = message

    # 剥离 IP 地址
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '<IP>', text)

    # 剥离 IPv6 地址
    text = re.sub(r'\b[xX]?:[xX]?:[xX]?:[xX]?:[xX]?:[xX]?:[xX]?:[xX]? ', '<IPv6> ', text)

    # 剥离端口号
    text = re.sub(r':(\d{4,5})', ':<PORT>', text)

    # 剥离 URL 路径（保留域名）
    text = re.sub(r'https?://[^/\s]+(/[^\s]*)', r'https://<DOMAIN>/', text)

    # 剥离时间戳（ISO 8601 格式）
    text = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?', '<TIMESTAMP>', text)

    # 剥离文件路径中的数字 ID
    text = re.sub(r'/id/\d+', '/id/<ID>', text)

    # 剥离纯数字 ID
    text = re.sub(r'\bid[_-]?(\d+)\b', 'id_<ID>', text, flags=re.IGNORECASE)

    return text


def _compute_group_key(error: dict[str, Any]) -> str:
    """计算错误的归类键。

    优先级：
    1. 若 error_message 含域名 → 用域名
    2. 否则用 error_type + 前 50 字归一化后的 error_message
    """
    error_msg = error.get("error_message", "")
    error_type = error.get("error_type", "Unknown")
    plugin_name = error.get("plugin_name", "")

    # 优先从错误消息提取域名
    domain = _extract_domain_from_url(str(error_msg))
    if domain:
        return f"{error_type}|{domain}"

    # 获取学校名称（如果包含）
    school_match = re.search(r'[东南北广中华华东华北华南黄河|:]\s*([^\s]+大学?|师大|学院)', error_msg)
    if school_match:
        school = school_match.group(1)
        return f"{error_type}|{school}"

    # 归一化后取前 50 字
    normalized = _normalize_error_message(error_msg)[:50]
    return f"{error_type}|{normalized}"


def aggregate(n_recent: int = 50, window_hours: float | None = None) -> dict[str, Any]:
    """聚合最近 N 次错误，识别高频模式。

    Args:
        n_recent: 最近返回多少条错误
        window_hours: 时间窗口（小时），None 表示全部历史

    Returns:
        聚合报告，包含：
        - total_errors: 总错误数
        - by_type: 错误类型分布
        - by_plugin: 按插件统计
        - grouped: 按域名/类型归类的错误分组
        - recent: 最近 N 条错误（向后兼容）
    """
    import time

    files = _load_error_files(limit=10000)  # 加载更多用于分组统计

    # 如果有时间窗口过滤
    if window_hours is not None:
        cutoff = time.time() - (window_hours * 3600)
        files = [f for f in files if f.get("_filepath") and Path(f["_filepath"]).stat().st_mtime > cutoff]

    if not files:
        return {
            "total_errors": 0,
            "by_type": {},
            "by_plugin": {},
            "grouped": [],
            "recent": [],
        }

    # 按类型统计
    type_counter = Counter(f.get("error_type", "Unknown") for f in files)

    # 按插件统计
    plugin_counter = Counter(f.get("plugin_name", "unknown") for f in files)

    # 分组聚合
    groups: dict[str, dict[str, Any]] = {}

    for f in files:
        key = _compute_group_key(f)
        if key not in groups:
            groups[key] = {
                "key": key,
                "count": 0,
                "error_type": f.get("error_type", "Unknown"),
                "sample_schools": set(),
                "sample_url": None,
                "first_seen": f.get("timestamp", ""),
                "last_seen": f.get("timestamp", ""),
                "first_filepath": f.get("_filepath", ""),
            }

        groups[key]["count"] += 1
        groups[key]["last_seen"] = f.get("timestamp", "")

        # 收集样本学校
        msg = f.get("error_message", "")
        school_match = re.search(r'[东南北广中华华东华北华南黄河|:]\s*([^\s]+大学?|师大|学院)', msg)
        if school_match:
            groups[key]["sample_schools"].add(school_match.group(1))

        # 收集样本 URL
        if not groups[key]["sample_url"]:
            url_match = re.search(r'https?://[^\s]+', msg)
            if url_match:
                groups[key]["sample_url"] = url_match.group(0)

    # 转换为列表并构建输出
    grouped_list = []
    for key, g in groups.items():
        sample_schools = list(g["sample_schools"])[:5]  # 最多 5 个
        # 从 first_filepath 提取 school 作为补充
        if not sample_schools and g["first_filepath"]:
            filepath = Path(g["first_filepath"])
            school_names = re.findall(r'\d{4}|\w+大学', filepath.stem)
            if school_names:
                sample_schools = school_names[:5]

        grouped_list.append({
            "key": g["key"],
            "count": g["count"],
            "error_type": g["error_type"],
            "sample_schools": sample_schools,
            "sample_url": g["sample_url"],
            "first_seen": g["first_seen"],
            "last_seen": g["last_seen"],
        })

    # 按次数降序排序
    grouped_list.sort(key=lambda x: -x["count"])

    return {
        "total_errors": len(files),
        "by_type": dict(type_counter),
        "by_plugin": dict(plugin_counter),
        "grouped": grouped_list,
        "recent": files[:n_recent],
    }


def clear_errors(plugin_name: str | None = None, errors_dir: Path | None = None) -> int:
    """清除错误记录。

    Args:
        plugin_name: 如果提供，仅清除该插件的错误
        errors_dir: 存储目录

    Returns:
        清除的文件数
    """
    if errors_dir is None:
        errors_dir = ERRORS_DIR

    if not errors_dir.exists():
        return 0

    count = 0
    if plugin_name:
        safe_name = plugin_name.replace("/", "_").replace("\\", "_")
        pattern = f"{safe_name}_*.json"
    else:
        pattern = "*.json"

    for f in errors_dir.glob(pattern):
        try:
            f.unlink()
            count += 1
        except OSError:
            continue

    return count


__all__ = [
    "ERRORS_DIR",
    "PluginErrorContext",
    "report",
    "has_recent_error",
    "get_recent_errors",
    "aggregate",
    "clear_errors",
]