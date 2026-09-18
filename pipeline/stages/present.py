# -*- coding: utf-8 -*-
"""
present 阶段（V3.0）
====================
view_converter → PresentationRequest → PresenterPlugin.execute → RenderedOutputDTO。

成品写 data/runs/<run_id>/outputs/<output_id>/（临时根下同理）。
present 默认 optional：失败只重建展示，不重抓、不重复写入成功目标。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from contracts.output import PresentationRequest, RenderedOutputDTO
from contracts.record import RecordBatch
from contracts.result import StageResult, StoreReceipt
from contracts.task import OutputSpec, TaskRunState
from converters.view_converter import build_presentation_request
from infra.context import PipelineContextManager
from infra.errors import error_from_exception, plugin_setup_error
from infra.storage.workspace import ManagedWorkspace

logger = logging.getLogger(__name__)


@dataclass
class PresentPlan:
    """pipeline.yaml present 段。"""
    outputs: list[dict[str, Any]] = field(default_factory=list)   # OutputSpec dicts
    required: bool = False


def render_outputs(
    batch: RecordBatch,
    receipts: list[StoreReceipt],
    output_specs: list[OutputSpec],
    run_state: TaskRunState,
    presenter_plugins: dict[str, Any],
    manager: PipelineContextManager,
    workspace: ManagedWorkspace,
) -> tuple[list[RenderedOutputDTO], StageResult]:
    """逐输出产品渲染；单产品失败不影响其他产品。"""
    rendered: list[RenderedOutputDTO] = []
    errors: list[dict] = []
    for spec in output_specs:
        if manager.is_cancelled():
            errors.append(vars(error_from_exception(
                RuntimeError("cancelled"), "present", code_override="PIPELINE_CANCELLED")))
            break
        plugin = _resolve_presenter(presenter_plugins, spec)
        if plugin is None:
            errors.append(vars(error_from_exception(
                RuntimeError(f"presenter instance {spec.presenter_instance} not loaded"),
                "present", code_override="PIPELINE_DEPENDENCY_MISSING")))
            continue
        request = build_presentation_request(batch, receipts, spec, run_state)
        dto = _execute_presenter(plugin, request, manager, spec, workspace)
        if isinstance(dto, RenderedOutputDTO):
            rendered.append(dto)
        else:
            errors.append(dto)

    any_failed = len(errors) > 0
    status = "failed" if (any_failed and _has_required_failure(output_specs, rendered)) \
        else ("partial" if any_failed else "succeeded")
    result = StageResult(stage="present", status=status,
                         input_count=len(batch.records), output_count=len(rendered))
    result.errors.extend(errors)
    return rendered, result


def _resolve_presenter(presenter_plugins: dict[str, Any], spec: OutputSpec) -> Optional[Any]:
    if spec.presenter_instance:
        return presenter_plugins.get(spec.presenter_instance)
    # 无具名实例时按格式回退到 <format>_presenter
    return presenter_plugins.get(f"{spec.format}_presenter")


def _execute_presenter(plugin: Any, request: PresentationRequest,
                       manager: PipelineContextManager, spec: OutputSpec,
                       workspace: ManagedWorkspace) -> Any:
    """执行单个 presenter；成功返回 RenderedOutputDTO，失败返回 ErrorDTO dict。"""
    context = _presenter_context(manager, spec, workspace)
    try:
        try:
            plugin.setup(context)
        except Exception as error:
            return vars(plugin_setup_error(error))
        dto = plugin.execute(request, context)
        if not isinstance(dto, RenderedOutputDTO):
            return vars(error_from_exception(
                TypeError(f"presenter returned {type(dto).__name__}"),
                "present", code_override="VALIDATION_SCHEMA_MISMATCH"))
        _ensure_under_outputs_dir(dto, workspace)
        return dto
    except Exception as error:
        logger.exception("presenter %s failed", spec.presenter_instance or spec.format)
        return vars(error_from_exception(error, "present"))
    finally:
        try:
            plugin.close()
        except Exception:
            pass


def _ensure_under_outputs_dir(dto: RenderedOutputDTO, workspace: ManagedWorkspace) -> None:
    """成品路径必须落在 runs/<run_id>/outputs/ 下（含 output_id 子目录约定由插件负责）。"""
    path = Path(dto.path)
    if not path.exists():
        raise FileNotFoundError(f"presenter output missing: {dto.path}")
    outputs_root = workspace.outputs_dir.resolve()
    try:
        path.resolve().relative_to(outputs_root)
    except ValueError as error:
        raise ValueError(
            f"presenter output {path} outside managed outputs dir {outputs_root}"
        ) from error


def _presenter_context(manager: PipelineContextManager, spec: OutputSpec,
                       workspace: ManagedWorkspace) -> Any:
    from plugins.base import PluginContext
    snapshot = {
        "task_id": "",
        "run_id": manager.run_id,
        "data_root": str(manager.data_root),
        "workspace": str(workspace.run_dir),
        "outputs_dir": str(workspace.outputs_dir),
        "params": dict(spec.params),
        "plugins": {},
    }
    return PluginContext(
        http=None, cache=None, progress=None, storage=None,
        logger=manager.logger,
        allowed_paths=[str(workspace.run_dir)],
        cancel_token=manager.cancel_token,
        config_snapshot=snapshot,
        registry_revision=1,
        task_id="",
        run_id=manager.run_id,
    )


def _has_required_failure(specs: list[OutputSpec], rendered: list[RenderedOutputDTO]) -> bool:
    rendered_ids = {dto.output_id for dto in rendered}
    return any(spec.required and spec.output_id not in rendered_ids for spec in specs)
