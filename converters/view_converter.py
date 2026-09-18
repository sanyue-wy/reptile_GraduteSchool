# -*- coding: utf-8 -*-
"""
视图转换器（V3.0）
==================
RecordBatch + StoreReceipt[] + OutputSpec + TaskRunState → PresentationRequest。

保留记录与媒体引用，不把 StoreReceipt 当数据本身；无 HTML 输出时不加载
UI/模板依赖。field_descriptions 来自已登记 schema（领域扩展）。
"""

import logging
from typing import Any, Optional

from contracts.output import PresentationRequest
from contracts.record import RecordBatch
from contracts.result import StoreReceipt
from contracts.task import OutputSpec, TaskRunState
from contracts.profiles.education import SCHEMA_REGISTRY

logger = logging.getLogger(__name__)


def build_field_descriptions(schema_id: str) -> dict[str, dict[str, Any]]:
    """schema_id → {field: {type}}；未登记 schema 返回空描述而非报错。"""
    schema = SCHEMA_REGISTRY.get(schema_id)
    if not schema:
        return {}
    descriptions: dict[str, dict[str, Any]] = {}
    for name, spec in (schema.get("properties") or {}).items():
        descriptions[name] = {"type": spec.get("type", "string")}
    return descriptions


def build_presentation_request(
    batch: RecordBatch,
    receipts: list[StoreReceipt],
    output_spec: OutputSpec,
    run_state: TaskRunState,
    *,
    media_assets: Optional[list[Any]] = None,
    stats: Optional[dict[str, Any]] = None,
) -> PresentationRequest:
    """四要素 → PresentationRequest（每个输出产品构造一次）。"""
    schema_id = batch.records[0].schema_id if batch.records else ""
    records = [record.to_dict() for record in batch.records]
    merged_stats = dict(batch.stats or {})
    if stats:
        merged_stats.update(stats)
    return PresentationRequest(
        request_id="",  # dataclass 自动生成 32hex
        dataset=batch.records[0].dataset if batch.records else "",
        schema_id=schema_id,
        output_spec=output_spec.__dict__,
        records=records,
        media_assets=list(media_assets or []),
        store_receipts=[receipt.__dict__ | {"error": _error_dict(receipt.error)} for receipt in receipts],
        run_state={
            "run_id": run_state.run_id,
            "task_id": run_state.task_id,
            "status": run_state.status,
            "retry_count": run_state.retry_count,
            "started_at": run_state.started_at,
            "completed_at": run_state.completed_at,
        },
        stats=merged_stats,
    )


def _error_dict(error: Any) -> Optional[dict[str, Any]]:
    if error is None:
        return None
    if isinstance(error, dict):
        return error
    return vars(error)
