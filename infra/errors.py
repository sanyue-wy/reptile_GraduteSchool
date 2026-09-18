# -*- coding: utf-8 -*-
"""
错误码 → ErrorDTO 映射（V3.0）
==============================
把各层异常统一映射为 contracts.result.ErrorDTO。
错误码表与 INTERFACES.md §2.14 标准错误码表一致；未知异常按阶段给出
默认可重试标记，并保留脱敏后的诊断信息（不写凭据/完整请求体）。
"""

import re
from typing import Any, Optional

from contracts.result import ErrorDTO
from utils.http import BlockedError, MaxRetriesExceeded

_SECRET_PATTERNS = [
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+"), r"\1***"),
    (re.compile(r"(?i)((?:password|passwd|token|api[_-]?key)\s*[:=]\s*)[^\s,;&\"']+"), r"\1***"),
]


def sanitize(message: str) -> str:
    """去除常见凭据片段；message 面向人类展示，长度截断到 500。"""
    text = str(message)
    for pattern, repl in _SECRET_PATTERNS:
        text = pattern.sub(repl, text)
    return text[:500]


def classify_http_error(error: Exception) -> str:
    """requests/PoliteSession 异常 → HTTP_* 错误码。也处理裸 Python 网络异常。"""
    if isinstance(error, BlockedError):
        return "HTTP_BLOCKED"
    if isinstance(error, MaxRetriesExceeded):
        return "HTTP_MAX_RETRIES"
    # bare builtin TimeoutError/ConnectionError
    if isinstance(error, TimeoutError) and type(error) is TimeoutError:
        return "HTTP_TIMEOUT"
    if isinstance(error, ConnectionError) and type(error) is ConnectionError:
        return "HTTP_CONNECTION_ERROR"
    try:
        import requests
        import socket
    except ImportError:
        requests = None
        socket = None

    pending = [error]
    seen = set()
    while pending:
        exc = pending.pop()
        if id(exc) in seen:
            continue
        seen.add(id(exc))
        if requests is not None and isinstance(exc, requests.exceptions.Timeout):
            return "HTTP_TIMEOUT"
        if socket is not None and isinstance(exc, socket.gaierror):
            return "HTTP_DNS_ERROR"
        if requests is not None and isinstance(exc, (requests.exceptions.ConnectionError, OSError)):
            text = str(exc).lower()
            dns_markers = ("getaddrinfo", "name or service not known",
                           "nameresolutionerror", "temporary failure in name resolution",
                           "nodename nor servname", "failed to resolve")
            if any(marker in text for marker in dns_markers):
                return "HTTP_DNS_ERROR"
            return "HTTP_CONNECTION_ERROR"
        pending.extend(item for item in (
            exc.__cause__, exc.__context__, getattr(exc, "reason", None), *exc.args
        ) if isinstance(item, BaseException))
    return "HTTP_CONNECTION_ERROR"


def error_from_exception(
    error: Exception,
    stage: str,
    *,
    task_id: str = "",
    source_id: str = "",
    code_override: Optional[str] = None,
    message_override: Optional[str] = None,
    diagnostics: Optional[dict[str, Any]] = None,
) -> ErrorDTO:
    """任意异常 → ErrorDTO。code_override 用于非网络异常显式指定错误码。"""
    if code_override:
        code = code_override
    elif isinstance(error, (BlockedError, MaxRetriesExceeded)) or \
            type(error).__module__.startswith("requests"):
        code = classify_http_error(error)
    elif isinstance(error, (ConnectionError, TimeoutError)):
        # 裸 Python ConnectionError/TimeoutError 也是网络异常，不限于 requests 包装
        code = classify_http_error(error)
    else:
        # 按阶段给默认可重试错误码（OSError/IOError 在 store 阶段属写入失败）
        code = _default_code_for_stage(stage, error)

    message = message_override if message_override is not None else f"{type(error).__name__}: {error}"
    return ErrorDTO(
        code=code,
        message=sanitize(message),
        stage=stage,
        task_id=task_id,
        source_id=source_id,
        diagnostics=dict(diagnostics or {}),
    )


def _default_code_for_stage(stage: str, error: Exception) -> str:
    if stage == "store" and isinstance(error, (OSError, IOError)):
        return "STORAGE_WRITE_FAILED"
    if stage == "present":
        if isinstance(error, FileNotFoundError):
            return "RENDER_TEMPLATE_MISSING"
        return "PLUGIN_EXECUTE_FAILED"
    return "PLUGIN_EXECUTE_FAILED"


def plugin_setup_error(error: Exception, *, task_id: str = "", source_id: str = "") -> ErrorDTO:
    return error_from_exception(
        error, "acquire", task_id=task_id, source_id=source_id,
        code_override="PLUGIN_SETUP_FAILED",
    )


def cancelled_error(*, task_id: str = "", source_id: str = "", stage: str = "acquire") -> ErrorDTO:
    return ErrorDTO(
        code="PIPELINE_CANCELLED",
        message="pipeline run cancelled by user",
        stage=stage,
        task_id=task_id,
        source_id=source_id,
    )
