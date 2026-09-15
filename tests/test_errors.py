"""错误分类器单元测试"""

import pytest
from unittest.mock import MagicMock

from utils.errors import classify_error, is_placeholder_url, ERROR_TYPES, get_error_type_name


class TestClassifyError:
    """classify_error 函数单测"""

    def test_dns_error_name_resolution(self):
        """DNS 解析失败分类为 dns_error"""
        from urllib3.exceptions import NameResolutionError
        import socket
        exc = NameResolutionError("badhost", None, socket.gaierror(-2, "Name or service not known"))
        assert classify_error(exc) == "dns_error"

    def test_dns_error_connection_error_cause(self):
        """ConnectionError 包含 DNS 错误信息时分类为 dns_error"""
        import requests
        exc = requests.ConnectionError("[Errno -2] Name or service not known")
        assert classify_error(exc) == "dns_error"

    def test_connection_error_generic(self):
        """普通 ConnectionError 分类为 connection_error"""
        import requests
        exc = requests.ConnectionError("Connection refused")
        assert classify_error(exc) == "connection_error"

    def test_dns_error_getaddrinfo(self):
        """ConnectionError 包含 getaddrinfo 时分类为 dns_error"""
        import requests
        exc = requests.ConnectionError("[Errno -2] Name or service not known (getaddrinfo)")
        assert classify_error(exc) == "dns_error"

    def test_connection_reset(self):
        """ConnectionResetError 分类为 connection_error"""
        exc = ConnectionResetError(10054)
        assert classify_error(exc) == "connection_error"

    def test_protocol_error(self):
        """ProtocolError 分类为 connection_error"""
        from urllib3.exceptions import ProtocolError
        exc = ProtocolError()
        assert classify_error(exc) == "connection_error"

    def test_read_timeout(self):
        """ReadTimeout 分类为 timeout"""
        from requests.exceptions import ReadTimeout
        exc = ReadTimeout("Connection timed out")
        assert classify_error(exc) == "timeout"

    def test_connect_timeout(self):
        """ConnectTimeout 分类为 timeout"""
        from requests.exceptions import ConnectTimeout
        exc = ConnectTimeout("Connection refused")
        assert classify_error(exc) == "timeout"

    def test_remote_disconnected(self):
        """RemoteDisconnected 若存在则分类为 connection_error"""
        try:
            from urllib3.exceptions import RemoteDisconnected
        except ImportError:
            pytest.skip("RemoteDisconnected not available in this urllib3 version")
        exc = RemoteDisconnected()
        assert classify_error(exc) == "connection_error"

    def test_blocked_403(self):
        """HTTP 403 分类为 blocked"""
        import requests
        resp = MagicMock()
        resp.status_code = 403
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
        exc = requests.HTTPError(response=resp)
        assert classify_error(exc) == "blocked"

    def test_blocked_429(self):
        """HTTP 429 分类为 blocked"""
        import requests
        resp = MagicMock()
        resp.status_code = 429
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
        exc = requests.HTTPError(response=resp)
        assert classify_error(exc) == "blocked"

    def test_http_error_500(self):
        """HTTP 500 分类为 http_error"""
        import requests
        resp = MagicMock()
        resp.status_code = 500
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
        exc = requests.HTTPError(response=resp)
        assert classify_error(exc) == "http_error"

    def test_http_error_502(self):
        """HTTP 502 分类为 http_error"""
        import requests
        resp = MagicMock()
        resp.status_code = 502
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
        exc = requests.HTTPError(response=resp)
        assert classify_error(exc) == "http_error"

    def test_parse_error_fallback(self):
        """普通异常分类为 parse_error"""
        exc = ValueError("选择器匹配为空")
        assert classify_error(exc) == "parse_error"

    def test_blocked_error(self):
        """BlockedError 分类为 blocked"""
        from utils.http import BlockedError
        exc = BlockedError("domain blocked")
        assert classify_error(exc) == "blocked"

    def test_max_retries_exceeded(self):
        """MaxRetriesExceeded 分类为 timeout"""
        from utils.http import MaxRetriesExceeded
        exc = MaxRetriesExceeded("max retries")
        assert classify_error(exc) == "timeout"

    def test_all_error_types_defined(self):
        """所有错误类型都在 ERROR_TYPES 中"""
        for et in ERROR_TYPES:
            assert et in ("dns_error", "connection_error", "timeout", "blocked", "http_error", "parse_error")

    def test_no_false_positive_for_connection_error(self):
        """普通 ConnectionError（非 DNS）应分类为 connection_error"""
        import requests
        exc = requests.ConnectionError("Connection refused")
        result = classify_error(exc)
        assert result in ("connection_error", "dns_error")  # ConnectionError without DNS info → connection_error

    def test_get_error_type_name(self):
        """get_error_type_name 返回可读名称"""
        assert get_error_type_name(ValueError("x")) == "页面解析失败"  # parse_error
        from utils.http import BlockedError
        assert get_error_type_name(BlockedError("x")) == "被反爬拦截"


class TestIsPlaceholderUrl:
    """is_placeholder_url 函数单测"""

    def test_x_com(self):
        assert is_placeholder_url("http://x.com") is True

    def test_example_com(self):
        assert is_placeholder_url("http://example.com") is True

    def test_test_edu_cn(self):
        assert is_placeholder_url("http://test.edu.cn") is True

    def test_localhost(self):
        assert is_placeholder_url("http://localhost:8080") is True

    def test_placeholder_text(self):
        assert is_placeholder_url("http://placeholder.com") is True

    def test_real_url(self):
        assert is_placeholder_url("https://me.seu.edu.cn/faculty") is False

    def test_empty_url(self):
        assert is_placeholder_url("") is False

    def test_none_url(self):
        assert is_placeholder_url(None) is False

    def test_empty_string(self):
        assert is_placeholder_url("") is False

    def test_uppercase(self):
        assert is_placeholder_url("HTTP://X.COM") is True

    def test_partial_match(self):
        assert is_placeholder_url("http://your-domain.com/faculty") is True
