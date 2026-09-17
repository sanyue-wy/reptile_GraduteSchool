# -*- coding: utf-8 -*-
"""导出器插件注册表。

接口：export(records: list[dict], output_dir: Path) -> dict
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Dict

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Callable[[list[dict], Path], dict]] = {}


def register(name: str):
    """注册一个导出器插件。"""
    def decorator(func: Callable[[list[dict], Path], dict]):
        if name in _REGISTRY:
            logger.warning("Exporter '%s' 已注册，将被覆盖", name)
        _REGISTRY[name] = func
        return func
    return decorator


def dispatch(name: str, records: list[dict], output_dir: Path) -> dict:
    if name not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"未注册的 exporter: '{name}'，可用: {available}")
    return _REGISTRY[name](records, output_dir)


def list_registered() -> list[str]:
    return sorted(_REGISTRY.keys())


@register("jsonl")
def export_jsonl(records: list[dict], output_dir: Path) -> dict:
    from pipelines.export import export_merged
    return export_merged(records, output_dir)


@register("xlsx")
def export_xlsx(records: list[dict], output_dir: Path) -> dict:
    from pipelines.export import export_summary
    count = export_summary(records, output_path=output_dir / "summary.xlsx")
    return {"files_written": 1 if count else 0, "total_records": count}


__all__ = ["register", "dispatch", "list_registered"]
