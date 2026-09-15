# -*- coding: utf-8 -*-
"""处理器插件注册表。

接口：process(records: list[dict], ctx: dict) -> list[dict]
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Callable[[List[dict], Dict], List[dict]]] = {}


def register(name: str):
    """注册一个处理器插件。"""
    def decorator(func: Callable[[List[dict], Dict], List[dict]]):
        if name in _REGISTRY:
            logger.warning("Processor '%s' 已注册，将被覆盖", name)
        _REGISTRY[name] = func
        return func
    return decorator


def dispatch(name: str, records: List[dict], ctx: Dict) -> List[dict]:
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"未注册的 processor: '{name}'，可用: {available}")
    return _REGISTRY[name](records, ctx)


def list_registered() -> List[str]:
    return sorted(_REGISTRY.keys())


def _normalize_text(value):
    if not isinstance(value, str):
        return value
    return " ".join(value.replace("　", " ").split())


@register("normalize")
def normalize_records(records: List[dict], ctx: Dict) -> List[dict]:
    normalized = []
    for original in records:
        record = dict(original)
        for key, value in list(record.items()):
            if isinstance(value, str):
                record[key] = _normalize_text(value)
            elif isinstance(value, list):
                record[key] = [_normalize_text(item) if isinstance(item, str) else item for item in value]
        normalized.append(record)
    return normalized


@register("dedup")
def deduplicate_records(records: List[dict], ctx: Dict) -> List[dict]:
    seen = set()
    result = []
    for record in records:
        key = (
            record.get("university", ""),
            record.get("college", ""),
            record.get("name", ""),
            record.get("title", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(record)
    return result


@register("merge")
def merge_records(records: List[dict], ctx: Dict) -> List[dict]:
    """兼容默认处理链，合并动作仍由 pipelines.merge 完成。"""
    return list(records)


__all__ = ["register", "dispatch", "list_registered"]
