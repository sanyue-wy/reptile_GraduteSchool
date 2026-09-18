# -*- coding: utf-8 -*-
"""V3.0 Spider Plugin base and shared utilities."""

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import uuid4

from plugins.base import BasePlugin, PluginContext
from contracts.task import TaskConfigDTO
from contracts.raw import RawDataBatch

# Standard error codes for spider/acquire stage
ERROR_HTTP_TIMEOUT = "HTTP_TIMEOUT"
ERROR_HTTP_CONNECTION_ERROR = "HTTP_CONNECTION_ERROR"
ERROR_HTTP_BLOCKED = "HTTP_BLOCKED"
ERROR_HTTP_DNS_ERROR = "HTTP_DNS_ERROR"
ERROR_HTTP_MAX_RETRIES = "HTTP_MAX_RETRIES"
ERROR_PARSE_FAILED = "PARSE_FAILED"
ERROR_PARSE_SELECTOR_MISSING = "PARSE_SELECTOR_MISSING"
ERROR_PARSE_ENCODING_ERROR = "PARSE_ENCODING_ERROR"
ERROR_PIPELINE_CANCELLED = "PIPELINE_CANCELLED"
ERROR_PIPELINE_CONFIG_INVALID = "PIPELINE_CONFIG_INVALID"
ERROR_PIPELINE_DEPENDENCY_MISSING = "PIPELINE_DEPENDENCY_MISSING"
ERROR_PLUGIN_SETUP_FAILED = "PLUGIN_SETUP_FAILED"
ERROR_PLUGIN_EXECUTE_FAILED = "PLUGIN_EXECUTE_FAILED"
ERROR_PLUGIN_DEPENDENCY_MISSING = "PLUGIN_DEPENDENCY_MISSING"

# retryable map for standard codes
_CODE_RETRYABLE: dict[str, bool] = {
    ERROR_HTTP_TIMEOUT: True,
    ERROR_HTTP_CONNECTION_ERROR: True,
    ERROR_HTTP_BLOCKED: False,
    ERROR_HTTP_DNS_ERROR: True,
    ERROR_HTTP_MAX_RETRIES: True,
    ERROR_PARSE_FAILED: False,
    ERROR_PARSE_SELECTOR_MISSING: False,
    ERROR_PARSE_ENCODING_ERROR: False,
    ERROR_PIPELINE_CANCELLED: False,
    ERROR_PIPELINE_CONFIG_INVALID: False,
    ERROR_PIPELINE_DEPENDENCY_MISSING: False,
    ERROR_PLUGIN_SETUP_FAILED: False,
    ERROR_PLUGIN_EXECUTE_FAILED: True,
    ERROR_PLUGIN_DEPENDENCY_MISSING: False,
}


def make_error(code: str, message: str, stage: str = "acquire",
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


class SpiderPlugin(BasePlugin[TaskConfigDTO, RawDataBatch]):
    """Base class for all V3.0 spider plugins.

    Lifecycle: pipeline engine calls setup(context) once, then
    execute(task_config, context) one or more times (pagination),
    then close() once.

    Subclasses MUST implement execute(). They receive context in
    execute() as a second argument (convenience for spider pattern).
    """
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        raise NotImplementedError


__all__ = [
    "SpiderPlugin",
    "make_error",
    "ERROR_HTTP_TIMEOUT",
    "ERROR_HTTP_CONNECTION_ERROR",
    "ERROR_HTTP_BLOCKED",
    "ERROR_HTTP_DNS_ERROR",
    "ERROR_HTTP_MAX_RETRIES",
    "ERROR_PARSE_FAILED",
    "ERROR_PARSE_SELECTOR_MISSING",
    "ERROR_PARSE_ENCODING_ERROR",
    "ERROR_PIPELINE_CANCELLED",
    "ERROR_PIPELINE_CONFIG_INVALID",
    "ERROR_PIPELINE_DEPENDENCY_MISSING",
    "ERROR_PLUGIN_SETUP_FAILED",
    "ERROR_PLUGIN_EXECUTE_FAILED",
    "ERROR_PLUGIN_DEPENDENCY_MISSING",
]
