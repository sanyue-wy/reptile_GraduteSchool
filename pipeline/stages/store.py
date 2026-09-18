# -*- coding: utf-8 -*-
"""
store 阶段（V3.0）
==================
同一 RecordBatch 向多个 storage 目标 fan-out，分别构造 StoreRequest；
收集 StoreReceipt[]。required 目标失败 → run failed；可选目标失败 → partial。

幂等键 = f"{run_id}:{target_id}:{dataset}"（同运行同目标重放可识别）。
数据引用采用受管批次文件：RecordBatch 先原子落盘到 runs/<run_id>/batch.jsonl，
StoreRequest.data_refs 指向该路径，插件按引用读取，不把回执当数据。
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from contracts.record import RecordBatch
from contracts.result import ErrorDTO, StageResult, StoreReceipt, StoreRequest
from infra.context import PipelineContextManager
from infra.errors import error_from_exception, plugin_setup_error
from infra.storage.atomic_io import atomic_writer
from infra.storage.workspace import ManagedWorkspace

logger = logging.getLogger(__name__)


@dataclass
class StorePlan:
    """pipeline.yaml store.targets 段。"""
    instance: str
    required: bool = True
    format_id: str = "generic_record"


def build_store_request(
    plan: StorePlan,
    batch: RecordBatch,
    *,
    run_id: str,
    dataset: str,
    data_ref: str,
    state_snapshot: dict[str, Any],
) -> StoreRequest:
    return StoreRequest(
        schema_version="1",
        dataset=dataset,
        run_id=run_id,
        target_id=plan.instance,
        format_id=plan.format_id,
        data_refs=[data_ref],
        idempotency_key=f"{run_id}:{plan.instance}:{dataset}",
        state_snapshot=dict(state_snapshot),
    )


def write_batch_reference(batch: RecordBatch, workspace: ManagedWorkspace) -> Path:
    """RecordBatch 原子落盘为批次引用文件（存储/呈现共享真值）。"""
    path = workspace.run_dir / "batch.json"
    payload = json.dumps(batch.to_dict(), ensure_ascii=False)
    with atomic_writer(path) as stream:
        stream.write(payload)
    return path


def store_batch(
    batch: RecordBatch,
    plans: list[StorePlan],
    storage_plugins: dict[str, Any],
    manager: PipelineContextManager,
    workspace: ManagedWorkspace,
    *,
    dataset: str,
    state_snapshot: dict[str, Any],
) -> tuple[list[StoreReceipt], StageResult]:
    """fan-out 到全部目标，返回 (receipts, stage_result)。"""
    receipts: list[StoreReceipt] = []
    errors: list[dict] = []
    if not batch.records:
        # 空批次：仍向目标发请求以维持幂等占位（各插件自行决定跳过语义）
        pass

    data_ref = str(write_batch_reference(batch, workspace))
    for plan in plans:
        plugin = storage_plugins.get(plan.instance)
        if plugin is None:
            errors.append(vars(error_from_exception(
                RuntimeError(f"storage instance {plan.instance} not loaded"),
                "store", code_override="PIPELINE_DEPENDENCY_MISSING")))
            continue
        request = build_store_request(plan, batch, run_id=manager.run_id,
                                      dataset=dataset, data_ref=data_ref,
                                      state_snapshot=state_snapshot)
        receipt = _execute_target(plugin, request, manager)
        receipts.append(receipt)
        if receipt.error is not None:
            errors.append(vars(receipt.error) if hasattr(receipt.error, "__dict__") else dict(receipt.error))

    any_required_failed = any(
        not r.success and next((p.required for p in plans if p.instance == r.target_id), False)
        for r in receipts
    )
    any_failed = any(not r.success for r in receipts)
    status = "failed" if any_required_failed else ("partial" if any_failed else "succeeded")
    result = StageResult(stage="store", status=status,
                         input_count=len(batch.records),
                         output_count=sum(r.records_written for r in receipts))
    result.receipts.extend(_receipt_dict(r) for r in receipts)
    result.errors.extend(errors)
    return receipts, result


def _execute_target(plugin: Any, request: StoreRequest,
                    manager: PipelineContextManager) -> StoreReceipt:
    context = _storage_context(manager, request)
    try:
        try:
            plugin.setup(context)
        except Exception as error:
            return _failure_receipt(request, plugin_setup_error(error))
        receipt = plugin.execute(request, context)
        if not isinstance(receipt, StoreReceipt):
            return _failure_receipt(request, error_from_exception(
                TypeError(f"storage returned {type(receipt).__name__}"),
                "store", code_override="VALIDATION_SCHEMA_MISMATCH"))
        # 部分失败语义：目标自报 failed 计数但没有 ErrorDTO 时补标准错误码
        if receipt.failed > 0 and receipt.error is None:
            error_dto = ErrorDTO(
                code="STORAGE_WRITE_FAILED",
                message=f"target {request.target_id} reported {receipt.failed} failed write(s)",
                stage="store", task_id=(request.state_snapshot or {}).get("task_id", ""),
            )
            receipt.error = vars(error_dto)
            errors.append(vars(error_dto))
        return receipt
    except Exception as error:
        logger.exception("storage target %s failed", request.target_id)
        return _failure_receipt(request, error_from_exception(error, "store"))
    finally:
        try:
            plugin.close()
        except Exception:
            pass


def _storage_context(manager: PipelineContextManager, request: StoreRequest) -> Any:
    from plugins.base import PluginContext
    snapshot = dict(manager._session_kwargs or {})
    snapshot.update({
        "task_id": (request.state_snapshot or {}).get("task_id", ""),
        "run_id": request.run_id,
        "data_root": str(manager.data_root),
        "workspace": str(manager.data_root / "runs" / request.run_id),
        "allowed_paths": [str(manager.data_root)],
        "plugins": {},
    })
    return PluginContext(
        http=None, cache=None, progress=None, storage=None,
        logger=manager.logger,
        allowed_paths=snapshot["allowed_paths"],
        cancel_token=manager.cancel_token,
        config_snapshot=snapshot,
        registry_revision=1,
        task_id=snapshot["task_id"],
        run_id=request.run_id,
    )


def _failure_receipt(request: StoreRequest, error_dto: Any) -> StoreReceipt:
    return StoreReceipt(
        target_id=request.target_id,
        written=0, skipped=0, failed=1, records_written=0, output_ref="",
        error=vars(error_dto) if hasattr(error_dto, "__dict__") else dict(error_dto),
    )


def _receipt_dict(receipt: StoreReceipt) -> dict[str, Any]:
    d = vars(receipt)
    if d.get("error") is not None and hasattr(receipt.error, "__dict__"):
        d["error"] = vars(receipt.error)
    return d
