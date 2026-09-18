# -*- coding: utf-8 -*-
"""
请求转换器（V3.0）
==================
schema_editor 产物 / 旧 CLI 参数 → TaskConfigDTO + OutputSpec[]。

本模块只做通用映射与校验，不集中维护任何具体插件的私有规则；
选择器、URL、学校/年份来自已校验的任务配置快照。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from contracts.task import OutputSpec, TaskConfigDTO

logger = logging.getLogger(__name__)

_PRESENT_FORMATS = {"html", "text", "markdown", "jsonl", "csv", "pdf"}


@dataclass
class PipelinePlanInput:
    """一次运行的完整输入：任务定义 + 输出产品规格。"""
    dataset: str
    profile_id: str
    sources: list[dict[str, Any]] = field(default_factory=list)   # [{source_id, target_url, config}]
    outputs: list[OutputSpec] = field(default_factory=list)
    config_revision: int = 1
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


def build_task_config(
    source: dict[str, Any],
    *,
    dataset: str,
    profile_id: str,
    config_revision: int = 1,
    task_id: Optional[str] = None,
) -> TaskConfigDTO:
    """单个来源定义 → TaskConfigDTO。

    source 字段：source_id、target_url（必填），config（可选 dict）。
    """
    if not source.get("source_id"):
        raise ValueError("source definition requires 'source_id'")
    if not source.get("target_url"):
        raise ValueError(f"source {source['source_id']} requires 'target_url'")
    return TaskConfigDTO(
        task_id=task_id or uuid4().hex,
        dataset=dataset,
        source_id=source["source_id"],
        profile_id=profile_id,
        target_url=source["target_url"],
        config_revision=config_revision,
        config_snapshot=dict(source.get("config") or {}),
    )


def _infer_format(item: dict[str, Any], instances: Optional[dict[str, dict[str, Any]]]) -> str:
    """format 解析顺序：显式 format > params.format > 实例 params.format > 实例名词法推断。

    无论来自哪一级，最终都必须通过白名单校验；无法确定则报错（不猜测）。
    实例名形如 html_report/text_report/csv_report。
    """
    fmt = item.get("format") or (item.get("params") or {}).get("format")
    instance_name = item.get("presenter_instance") or item.get("instance")
    if not fmt and instance_name and instances:
        inst = (instances or {}).get(instance_name) or {}
        fmt = (inst.get("params") or {}).get("format")
    if not fmt and instance_name:
        stem = instance_name.rsplit("_", 1)[0]
        if stem in _PRESENT_FORMATS:
            fmt = stem
    if fmt not in _PRESENT_FORMATS:
        raise ValueError(f"unsupported output format: {fmt!r} for {instance_name}")
    return fmt


def build_output_specs(outputs: list[dict[str, Any]],
                       instances: Optional[dict[str, dict[str, Any]]] = None) -> list[OutputSpec]:
    """present.outputs 列表 → OutputSpec[]，做格式白名单校验。"""
    specs = []
    for item in outputs or []:
        fmt = _infer_format(item, instances)
        specs.append(OutputSpec(
            output_id=item.get("output_id") or f"{fmt}_{uuid4().hex[:8]}",
            format=fmt,
            template=item.get("template"),
            presenter_instance=item.get("presenter_instance") or item.get("instance"),
            params=dict(item.get("params") or {}),
            required=bool(item.get("required", False)),
        ))
    return specs


def from_legacy_cli(args: Any, school_configs: list[dict[str, Any]],
                    pipeline_cfg: dict[str, Any]) -> PipelinePlanInput:
    """旧 CLI 参数 + 学校配置 + pipeline.yaml → PipelinePlanInput。

    每个 (university, category, source) 组合展开为一个 source 条目；
    教育画像固定 university/college/category/year 进 config_snapshot。
    """
    year = getattr(args, "year", datetime.now().year)
    sources: list[dict[str, Any]] = []
    for school in school_configs or []:
        uni = school.get("university")
        if getattr(args, "school", None) and "__all__" not in args.school and uni not in args.school:
            continue
        for cat in school.get("categories", []):
            category = cat.get("category")
            if getattr(args, "category", None) and category not in args.category:
                continue
            college = cat.get("college")
            selectors = cat.get("selectors") or {}
            base = cat.get("base_url") or cat.get("list_url") or ""
            for src in (getattr(args, "source", None) or ["source_a", "source_b"]):
                entry = cat.get(src) or {}
                url = entry.get("url") or base
                if not url:
                    continue
                sources.append({
                    "source_id": f"{uni}|{college}|{src}",
                    "target_url": url,
                    "config": {
                        "university": uni,
                        "college": college,
                        "category": category,
                        "year": year,
                        "source_type": src,
                        "list_url": url,
                        "selectors": selectors,
                        "max_pages": cat.get("max_pages", 20),
                    },
                })
    present = (pipeline_cfg or {}).get("present", {}) or {}
    return PipelinePlanInput(
        dataset="education",
        profile_id=(pipeline_cfg or {}).get("profile_id", "education.tutor.v1"),
        sources=sources,
        outputs=build_output_specs(present.get("outputs")),
    )


def to_task_configs(plan: PipelinePlanInput) -> list[TaskConfigDTO]:
    """PipelinePlanInput → 每来源一个 TaskConfigDTO。"""
    return [
        build_task_config(
            source, dataset=plan.dataset, profile_id=plan.profile_id,
            config_revision=plan.config_revision,
        )
        for source in plan.sources
    ]
