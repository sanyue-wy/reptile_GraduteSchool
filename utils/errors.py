"""错误分类器

按异常类型映射到固定枚举，用于 failures.json 的 error_type 字段。
"""

import logging

import requests
from requests.exceptions import Timeout, ReadTimeout, ConnectTimeout
from urllib3.exceptions import NameResolutionError, ProtocolError

logger = logging.getLogger(__name__)

# RemoteDisconnected 可能不在所有 urllib3 版本中存在
try:
    from urllib3.exceptions import RemoteDisconnected
except ImportError:
    RemoteDisconnected = None

# 错误类型枚举
ERROR_TYPES = frozenset({
    "dns_error",        # DNS 解析失败
    "connection_error", # 连接被重置/断开
    "timeout",          # 连接/读取超时
    "blocked",          # HTTP 403/429/401 被反爬拦截
    "http_error",       # HTTP 5xx
    "parse_error",      # 选择器匹配为空 / JSON 结构不符（唯一保留场景）
})

# 占位符 URL 模式
PLACEHOLDER_URL_PATTERNS = (
    "x.com",
    "example.com",
    "test.edu.cn",
    "localhost",
    "placeholder",
    "your-domain",
    "http://x",
)


def classify_error(exc: Exception) -> str:
    """
    根据异常类型映射到固定的错误分类。

    Args:
        exc: 捕获到的异常对象

    Returns:
        str: 错误分类，见 ERROR_TYPES 枚举

    分类规则：
        - NameResolutionError / DNS 相关 → dns_error
        - ConnectionResetError / RemoteDisconnected / ProtocolError → connection_error
        - ReadTimeout / ConnectTimeout / Timeout → timeout
        - HTTP 403/429/401 → blocked
        - HTTP 5xx → http_error
        - 其他（包括选择器为空、JSON 结构不符）→ parse_error
    """
    # DNS 解析失败
    if isinstance(exc, NameResolutionError):
        return "dns_error"
    if isinstance(exc.__cause__, NameResolutionError):
        return "dns_error"

    # 连接被重置/断开（ProtocolError、RemoteDisconnected 来自 urllib3；ConnectionResetError 是 Python built-in）
    _conn_types = (ProtocolError,)
    if RemoteDisconnected is not None:
        _conn_types += (RemoteDisconnected,)
    if isinstance(exc, _conn_types):
        return "connection_error"
    if isinstance(exc, ConnectionResetError):
        return "connection_error"

    # 超时（必须在 ConnectionError 之前检查，因为 ReadTimeout/ConnectTimeout 继承自 ConnectionError）
    if isinstance(exc, (ReadTimeout, ConnectTimeout, Timeout)):
        return "timeout"

    # ConnectionError（requests 封装）
    if isinstance(exc, requests.exceptions.ConnectionError):
        err_str = str(exc).lower()
        if "getaddrinfo" in err_str or "name or service not known" in err_str:
            return "dns_error"
        return "connection_error"

    # HTTP 错误（requests 抛出）
    if isinstance(exc, requests.HTTPError):
        if hasattr(exc, 'response') and exc.response is not None:
            status = exc.response.status_code
            if status in (403, 429, 401):
                return "blocked"
            if 500 <= status < 600:
                return "http_error"
        return "http_error"

    # BlockedError（自定义）
    from utils.http import BlockedError
    if isinstance(exc, BlockedError):
        return "blocked"

    # MaxRetriesExceeded
    from utils.http import MaxRetriesExceeded
    if isinstance(exc, MaxRetriesExceeded):
        return "timeout"

    # 默认：解析错误
    return "parse_error"


def is_placeholder_url(url: str) -> bool:
    """
    检查 URL 是否为占位符。

    Args:
        url: 待检查的 URL 字符串

    Returns:
        True 如果 URL 匹配占位符模式
    """
    if not url or not isinstance(url, str):
        return False
    url_lower = url.lower().strip()
    return any(pattern.lower() in url_lower for pattern in PLACEHOLDER_URL_PATTERNS)


def get_error_type_name(exc: Exception) -> str:
    """返回异常的可读名称，用于日志和面板展示。"""
    type_map = {
        "dns_error": "DNS 解析失败",
        "connection_error": "连接被重置/断开",
        "timeout": "请求超时",
        "blocked": "被反爬拦截",
        "http_error": "上游 HTTP 错误",
        "parse_error": "页面解析失败",
    }
    return type_map.get(classify_error(exc), "未知错误")
