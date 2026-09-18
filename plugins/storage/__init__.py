# -*- coding: utf-8 -*-
"""V3.0 Storage Plugin base and shared utilities."""

from plugins.base import BasePlugin, PluginContext
from contracts.result import StoreRequest, StoreReceipt

# Standard error codes for storage stage
ERROR_STORAGE_WRITE_FAILED = "STORAGE_WRITE_FAILED"
ERROR_STORAGE_LOCK_TIMEOUT = "STORAGE_LOCK_TIMEOUT"
ERROR_STORAGE_IDEMPOTENCY_CONFLICT = "STORAGE_IDEMPOTENCY_CONFLICT"
ERROR_PLUGIN_SETUP_FAILED = "PLUGIN_SETUP_FAILED"
ERROR_PLUGIN_EXECUTE_FAILED = "PLUGIN_EXECUTE_FAILED"
ERROR_PLUGIN_DEPENDENCY_MISSING = "PLUGIN_DEPENDENCY_MISSING"

_CODE_RETRYABLE: dict[str, bool] = {
    ERROR_STORAGE_WRITE_FAILED: True,
    ERROR_STORAGE_LOCK_TIMEOUT: True,
    ERROR_STORAGE_IDEMPOTENCY_CONFLICT: False,
    ERROR_PLUGIN_SETUP_FAILED: False,
    ERROR_PLUGIN_EXECUTE_FAILED: True,
    ERROR_PLUGIN_DEPENDENCY_MISSING: False,
}


def make_error(code: str, message: str, stage: str = "store",
               task_id: str = "", source_id: str = "",
               retryable: bool | None = None,
               diagnostics: dict | None = None) -> dict:
    """Build a standard ErrorDTO dict with correct retryable flag."""
    if retryable is None:
        retryable = _CODE_RETRYABLE.get(code, False)
    return {
        "code": code,
        "message": message,
        "stage": stage,
        "task_id": task_id,
        "source_id": source_id,
        "retryable": retryable,
        "diagnostics": diagnostics or {},
    }


__all__ = [
    "BasePlugin",
    "PluginContext",
    "StoreRequest",
    "StoreReceipt",
    "make_error",
    "ERROR_STORAGE_WRITE_FAILED",
    "ERROR_STORAGE_LOCK_TIMEOUT",
    "ERROR_STORAGE_IDEMPOTENCY_CONFLICT",
    "ERROR_PLUGIN_SETUP_FAILED",
    "ERROR_PLUGIN_EXECUTE_FAILED",
    "ERROR_PLUGIN_DEPENDENCY_MISSING",
]
