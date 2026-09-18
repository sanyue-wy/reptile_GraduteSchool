# -*- coding: utf-8 -*-
"""
process 阶段（V3.0）
====================
parse 链：每来源独立 RawDataBatch → RecordBatch；
post 链：RecordBatch → RecordBatch，多步顺序执行。

完成后按 dataset + profile 分组汇聚；教育分组键含 university/college/year，
不能跨学校/学院匹配。处理器只处理已取得材料，不发网络请求（约束由插件
自身遵守，本阶段提供不含 http 的上下文视图）。
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from contracts.record import NormalizedRecordDTO, RecordBatch
from contracts.raw import RawDataBatch
from contracts.result import StageResult
from infra.context import PipelineContextManager
from infra.errors import error_from_exception, plugin_setup_error

logger = logging.getLogger(__name__)


@dataclass
class ProcessPlan:
    """pipeline.yaml process 段 + 各来源 parse 实例。"""
    post_instances: list[str] = field(default_factory=list)   # normalize/merge/statistics...
    group_by: list[str] = field(default_factory=lambda: ["university", "college", "year"])


def _offline_context(manager: PipelineContextManager, task_id: str, config_snapshot: dict) -> Any:
    """处理阶段的上下文视图：不提供 http，杜绝处理器发网络请求。"""
    from plugins.base import PluginContext
    return PluginContext(
        http=None,
        cache=None,
        progress=None,
        storage=None,
        logger=manager.logger,
        allowed_paths=list(config_snapshot.get("allowed_paths", [])),
        cancel_token=manager.cancel_token,
        config_snapshot=dict(config_snapshot),
        registry_revision=1,
        task_id=task_id,
        run_id=manager.run_id,
    )


def run_parse_chain(
    raw_batch: RawDataBatch,
    source_plan: Any,
    parser_plugins: list[Any],
    manager: PipelineContextManager,
    *,
    context_config: dict[str, Any],
) -> tuple[Optional[RecordBatch], list[dict]]:
    """单来源 parse 链：RawDataBatch 依次过各 parser 插件。"""
    errors: list[dict] = []
    current: Any = raw_batch
    for plugin in parser_plugins:
        if manager.is_cancelled():
            errors.append(vars(_cancelled(source_plan)))
            return None, errors
        try:
            plugin.setup(_offline_context(manager, raw_batch.task_id, context_config))
        except Exception as error:
            errors.append(vars(plugin_setup_error(error, task_id=raw_batch.task_id,
                                                  source_id=getattr(source_plan, "source_id", ""))))
            return None, errors
        try:
            current = plugin.execute(current, _offline_context(manager, raw_batch.task_id, context_config))
        except Exception as error:
            logger.exception("parse failed in source %s", getattr(source_plan, "source_id", "?"))
            errors.append(vars(error_from_exception(error, "process",
                                                    task_id=raw_batch.task_id,
                                                    source_id=getattr(source_plan, "source_id", ""),
                                                    code_override="PARSE_FAILED")))
            return None, errors
        finally:
            try:
                plugin.close()
            except Exception:
                pass
        if not isinstance(current, RecordBatch):
            errors.append(vars(_mismatch(f"parser returned {type(current).__name__}")))
            return None, errors
    return current, errors


def run_post_steps(
    batch: RecordBatch,
    step_plugins: list[Any],
    manager: PipelineContextManager,
    *,
    context_config: dict[str, Any],
) -> tuple[RecordBatch, list[dict]]:
    """post 链：多步顺序执行；任一步失败返回已完成的批次与错误。"""
    errors: list[dict] = []
    current = batch
    for plugin in step_plugins:
        if manager.is_cancelled():
            errors.append(vars(_cancelled(None)))
            break
        try:
            plugin.setup(_offline_context(manager, "", context_config))
            current = plugin.execute(current, _offline_context(manager, "", context_config))
        except Exception as error:
            logger.exception("post step failed")
            errors.append(vars(error_from_exception(error, "process",
                                                    code_override="PARSE_FAILED")))
            break
        finally:
            try:
                plugin.close()
            except Exception:
                pass
        if not isinstance(current, RecordBatch):
            errors.append(vars(_mismatch(f"post step returned {type(current).__name__}")))
            break
    return current, errors


def merge_source_batches(
    batches: list[tuple[Any, RecordBatch]],
    plan: ProcessPlan,
    *,
    dataset: str,
) -> RecordBatch:
    """按 dataset+profile 分组规则汇聚各来源批次。

    教育分组键 university/college/year 来自记录 fields；不跨学校/学院匹配。
    合并后的 record_id 由自然键重新生成（不简单沿用来源 ID），保留全部 provenance。
    """
    from uuid import uuid5, NAMESPACE_URL

    records: list[NormalizedRecordDTO] = []
    seen_keys: set[tuple] = set()
    source_completion: dict[str, bool] = {}
    errors: list[dict] = []
    stats: dict[str, Any] = {"sources": len(batches)}

    for source_plan, batch in batches:
        source_id = getattr(source_plan, "source_id", "unknown")
        source_completion[source_id] = True
        for record in batch.records:
            key_fields = tuple(str(record.fields.get(key, "")) for key in plan.group_by)
            natural = "|".join([dataset, record.schema_id, *key_fields,
                                str(record.fields.get("name", ""))])
            stable_id = uuid5(NAMESPACE_URL, natural).hex
            provenance = dict(record.provenance or {})
            provenance.setdefault("source_id", source_id)
            records.append(NormalizedRecordDTO(
                record_id=stable_id,
                dataset=record.dataset or dataset,
                schema_id=record.schema_id,
                fields=dict(record.fields),
                provenance=provenance,
                media_refs=list(record.media_refs),
            ))
            seen_keys.add((stable_id,))
    stats["records"] = len(records)
    return RecordBatch(
        schema_version="1",
        group_key=list(plan.group_by),
        records=records,
        stats=stats,
        source_completion=source_completion,
        errors=errors,
    )


def build_stage_result(status: str, input_count: int, output_count: int,
                       errors: list[dict]) -> StageResult:
    result = StageResult(stage="process", status=status,
                         input_count=input_count, output_count=output_count)
    result.errors.extend(errors)
    return result


def _cancelled(source_plan: Any) -> Any:
    from contracts.result import ErrorDTO
    return ErrorDTO(code="PIPELINE_CANCELLED", message="cancelled during process", stage="process",
                    source_id=getattr(source_plan, "source_id", ""))


def _mismatch(message: str) -> Any:
    from contracts.result import ErrorDTO
    return ErrorDTO(code="VALIDATION_SCHEMA_MISMATCH", message=message, stage="process")
