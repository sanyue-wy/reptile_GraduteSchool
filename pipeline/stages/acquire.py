# -*- coding: utf-8 -*-
"""
acquire 阶段（V3.0）
====================
调用 SpiderPlugin.execute(TaskConfigDTO) → RawDataBatch，经 raw_converter
归一。列表发现/分页/详情 fan-out 的调度约束（最大页数、请求去重、每域
并发、取消检查点）由 spider 插件在 context.http/cache/cancel_token 上
实现；本阶段负责：

- 每任务独立插件实例 + 独立上下文（finally 关闭资源）
- setup/execute 异常 → ErrorDTO（不整任务自动重试，重试纪律见 §5.2）
- 批次结构校验（边界验证，不以宽松 dict 掩盖契约错误）
- 前置插件链：acquired_plugin_instances 中的插件在 spider 执行前调度
  （url_normalizer / domain_rewriter / url_prober 等），逐个处理 task_config
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from contracts.raw import RawDataBatch
from contracts.result import ErrorDTO, StageResult
from contracts.task import TaskConfigDTO
from converters.raw_converter import RawConverter
from infra.context import PipelineContextManager
from infra.errors import error_from_exception, plugin_setup_error

logger = logging.getLogger(__name__)


@dataclass
class AcquirePlan:
    """pipeline.yaml sources 段的执行计划。"""
    source_id: str                          # pipeline.yaml 中的来源键
    instance: str                           # plugins.yaml 实例名（spider）
    parse_instances: list[str] = field(default_factory=list)
    pre_acquire_instances: list[str] = field(default_factory=list)  # 前置插件链
    required: bool = True


def acquire_source(
    plan: AcquirePlan,
    task_config: TaskConfigDTO,
    spider_plugin: Any,
    manager: PipelineContextManager,
    pre_acquire_plugins: Optional[list[Any]] = None,
    *,
    converter: Optional[RawConverter] = None,
) -> tuple[Optional[RawDataBatch], StageResult]:
    """单个来源的采集。返回 (batch|None, stage_result)。

    batch 为 None 表示该来源失败（required 与否由引擎决定 run 状态）。
    
    前置插件链（pre_acquire_plugins）按顺序调度：
    - 每个插件在独立上下文中执行（finally 关闭）
    - 插件可返回修改后的 TaskConfigDTO 供后续使用
    - 插件失败则记录错误，但不阻断 spider（由 spider 自行处理无效 URL）
    """
    result = StageResult(stage="acquire", status="failed")
    result.input_count = 1
    
    # 前置插件链：在 spider 执行前处理 task_config
    active_context = None
    processed_config = task_config
    if pre_acquire_plugins:
        for plugin in pre_acquire_plugins:
            if manager.is_cancelled():
                result.status = "skipped"
                result.errors.append(_dict(ErrorDTO(
                    code="PIPELINE_CANCELLED",
                    message="cancelled before dispatch",
                    stage="acquire",
                    task_id=task_config.task_id,
                    source_id=plan.source_id,
                )))
                return None, result
            pre_context = manager.build_context(processed_config)
            try:
                plugin.setup(pre_context)
                pre_result = plugin.execute(processed_config, pre_context)
                # 插件返回的是 TaskConfigDTO 时，更新配置继续后续处理
                if isinstance(pre_result, TaskConfigDTO):
                    processed_config = pre_result
                elif pre_result is not None and not isinstance(pre_result, dict):
                    logger.warning(
                        "pre-acquire plugin %s returned %s, ignoring",
                        getattr(plugin, "name", "unknown"), type(pre_result).__name__
                    )
            except Exception as error:
                logger.warning(
                    "pre-acquire plugin %s failed (continuing with original config): %s",
                    getattr(plugin, "name", "unknown"), error
                )
            finally:
                try:
                    plugin.close()
                except Exception:
                    pass
                manager.release_context(pre_context)
                active_context = pre_context
    
    # 正常 spider 采集流程
    context = manager.build_context(processed_config)
    plugin = spider_plugin
    try:
        if manager.is_cancelled():
            result.status = "skipped"
            result.errors.append(_dict(ErrorDTO(code="PIPELINE_CANCELLED",
                                                message="cancelled before dispatch",
                                                stage="acquire",
                                                task_id=task_config.task_id,
                                                source_id=plan.source_id)))
            return None, result
        try:
            plugin.setup(context)
        except Exception as error:
            logger.exception("spider %s setup failed", plan.instance)
            result.errors.append(_dict(plugin_setup_error(error,
                                                          task_id=task_config.task_id,
                                                          source_id=plan.source_id)))
            return None, result

        batch = plugin.execute(processed_config, context)
        if not isinstance(batch, RawDataBatch):
            result.errors.append(_dict(ErrorDTO(
                code="VALIDATION_SCHEMA_MISMATCH",
                message=f"spider {plan.instance} returned {type(batch).__name__}, expected RawDataBatch",
                stage="acquire", task_id=task_config.task_id, source_id=plan.source_id,
            )))
            return None, result

        conv = converter or RawConverter()
        batch = conv.convert(batch, processed_config)
        result.items_count = len(batch.items)
        result.output_count = len(batch.items)
        result.errors.extend(batch.errors or [])
        result.status = "succeeded" if not _has_fatal_errors(batch) else "partial"
        return batch, result
    except Exception as error:
        logger.exception("acquire failed for source %s", plan.source_id)
        result.errors.append(_dict(error_from_exception(
            error, "acquire", task_id=task_config.task_id, source_id=plan.source_id)))
        return None, result
    finally:
        try:
            plugin.close()
        except Exception:
            pass
        manager.release_context(context)


def _has_fatal_errors(batch: RawDataBatch) -> bool:
    """批次内存在不可重试错误视为 partial（空结果是否合法由来源契约定义）。"""
    return any(not err.get("retryable", False) and err.get("code") != "PIPELINE_CANCELLED"
               for err in (batch.errors or []))


def _dict(dto: ErrorDTO) -> dict[str, Any]:
    return vars(dto)
