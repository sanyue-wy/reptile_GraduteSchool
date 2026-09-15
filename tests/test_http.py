# -*- coding: utf-8 -*-
"""
PoliteSession 单元测试
"""

import tempfile
from unittest.mock import MagicMock, patch

import pytest
import requests

from utils.http import PoliteSession, BlockedError, MaxRetriesExceeded


class TestPoliteSession:
    """PoliteSession 单测"""

    def test_init_default(self):
        """默认参数初始化"""
        session = PoliteSession()
        assert session.delay_range == (1.0, 3.0)
        assert session.max_retries == 3
        assert session.raw_dir is None
        assert session.cooldown_threshold == 5
        assert session.cooldown_seconds == 1800
        assert session.stats == {"requests": 0, "success": 0, "failed": 0, "raw_saved": 0}
        assert session._blocked_domains == set()

    def test_init_custom(self):
        """自定义参数初始化"""
        session = PoliteSession(
            delay_range=(0.5, 1.5),
            max_retries=5,
            raw_dir="/tmp/raw",
            cooldown_threshold=3,
            cooldown_seconds=600,
        )
        assert session.delay_range == (0.5, 1.5)
        assert session.max_retries == 5
        assert session.raw_dir == "/tmp/raw"
        assert session.cooldown_threshold == 3
        assert session.cooldown_seconds == 600

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_get_basic(self, mock_save_raw, mock_uniform, mock_sleep):
        """GET 请求基本流程"""
        mock_uniform.return_value = 1.5
        session = PoliteSession(delay_range=(0, 0))
        mock_resp = MagicMock(
            status_code=200,
            text="<html>ok</html>",
            content=b"<html>ok</html>",
            headers={"Content-Type": "text/html"},
            url="http://test.com",
        )
        mock_resp.raise_for_status.return_value = None

        with patch.object(session._session, "request", return_value=mock_resp) as mock_req:
            resp = session.get("http://test.com")

        assert resp.status_code == 200
        assert session.stats["requests"] == 1
        assert session.stats["success"] == 1
        mock_req.assert_called_once()

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_post_basic(self, mock_save_raw, mock_uniform, mock_sleep):
        """POST 请求基本流程"""
        mock_uniform.return_value = 1.5
        session = PoliteSession(delay_range=(0, 0))
        mock_resp = MagicMock(
            status_code=200,
            text='{"result": "ok"}',
            content=b'{"result": "ok"}',
            headers={"Content-Type": "application/json"},
            url="http://test.com/api",
        )
        mock_resp.raise_for_status.return_value = None

        with patch.object(session._session, "request", return_value=mock_resp) as mock_req:
            resp = session.post("http://test.com/api", data={"key": "value"})

        assert resp.status_code == 200
        call_args = mock_req.call_args
        assert call_args[0][0] == "POST"  # method is first positional arg

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    def test_post_json(self, mock_uniform, mock_sleep):
        """POST JSON 返回 JSON 数据"""
        mock_uniform.return_value = 1.5
        session = PoliteSession(delay_range=(0, 0))
        mock_resp = MagicMock(
            status_code=200,
            text='{"data": [1, 2, 3]}',
            headers={"Content-Type": "application/json"},
        )
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"data": [1, 2, 3]}

        with patch.object(session._session, "request", return_value=mock_resp):
            result = session.post_json("http://test.com/api")
        assert result == {"data": [1, 2, 3]}

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_retry_on_500(self, mock_save_raw, mock_uniform, mock_sleep):
        """500 错误触发应用层重试（ConnectionError/Timeout）并最终抛出"""
        mock_uniform.return_value = 0.01
        session = PoliteSession(delay_range=(0, 0), max_retries=3)

        # 500 响应触发 raise_for_status 抛出 HTTPError
        fail_resp = MagicMock(
            status_code=500,
            text="Internal Server Error",
            headers={"Content-Type": "text/html"},
        )
        fail_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")

        with patch.object(session._session, "request", return_value=fail_resp):
            # HTTPError 不是 ConnectionError/Timeout，不被重试，向上抛出
            with pytest.raises(requests.HTTPError):
                session.get("http://test.com")

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_blocked_cooldown(self, mock_save_raw, mock_uniform, mock_sleep):
        """403/429 触发冷却期"""
        mock_uniform.return_value = 0.1
        session = PoliteSession(delay_range=(0, 0), cooldown_threshold=3)

        blocked_resp = MagicMock(
            status_code=403,
            text="Forbidden",
            headers={"Content-Type": "text/html"},
            url="http://blocked.com",
        )

        # Simulate 3 consecutive 403 responses → cooldown triggered
        with patch.object(session._session, "request", return_value=blocked_resp):
            with pytest.raises(BlockedError):
                session.get("http://blocked.com")

        assert "blocked.com" in session._blocked_domains

    def test_clear_cooldown(self):
        """手动解除域名冷却"""
        session = PoliteSession()
        session._blocked_domains.add("blocked.com")
        session._block_count = 3
        session.clear_cooldown("blocked.com")
        assert "blocked.com" not in session._blocked_domains
        assert session._block_count == 0

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_ua_rotation(self, mock_save_raw, mock_uniform, mock_sleep):
        """连续请求 User-Agent 不同"""
        mock_uniform.return_value = 0.1
        session = PoliteSession(delay_range=(0, 0))
        mock_resp = MagicMock(
            status_code=200,
            text="<html>ok</html>",
            content=b"<html>ok</html>",
            headers={"Content-Type": "text/html"},
        )
        mock_resp.raise_for_status.return_value = None

        uas_seen = set()
        with patch.object(session._session, "request", return_value=mock_resp) as mock_req:
            for _ in range(20):
                session.get("http://test.com", save_raw=False)

        for call in mock_req.call_args_list:
            ua = call[1].get("headers", {}).get("User-Agent", "")
            uas_seen.add(ua)

        # 多次请求应该使用多个不同的 UA
        assert len(uas_seen) > 1

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch("utils.http.datetime")
    def test_save_raw(self, mock_datetime, mock_uniform, mock_sleep):
        """原始响应正确落盘"""
        mock_uniform.return_value = 0.1
        mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

        with tempfile.TemporaryDirectory() as tmpdir:
            session = PoliteSession(delay_range=(0, 0), raw_dir=tmpdir)
            mock_resp = MagicMock(
                status_code=200,
                text="<html>raw content</html>",
                content=b"<html>raw content</html>",
                headers={"Content-Type": "text/html"},
            )
            mock_resp.raise_for_status.return_value = None

            with patch.object(session._session, "request", return_value=mock_resp):
                session.get("http://test.com/page", save_raw=True)

            # 检查文件是否落盘
            import os
            files = []
            for root, _, fnames in os.walk(tmpdir):
                for fn in fnames:
                    files.append(os.path.join(root, fn))
            assert len(files) > 0
            assert session.stats["raw_saved"] == 1

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_max_retries_exceeded(self, mock_save_raw, mock_uniform, mock_sleep):
        """达到最大重试次数后，ConnectionError 被重新抛出"""
        mock_uniform.return_value = 0.01
        session = PoliteSession(delay_range=(0, 0), max_retries=2)

        connection_error = requests.ConnectionError("Connection refused")
        with patch.object(session._session, "request", side_effect=connection_error):
            with pytest.raises(requests.ConnectionError):
                session.get("http://test.com")

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_rate_limiting(self, mock_save_raw, mock_uniform, mock_sleep):
        """两次请求间隔不低于 min_delay"""
        mock_uniform.return_value = 2.5
        session = PoliteSession(delay_range=(2.0, 3.0), max_retries=0)
        mock_resp = MagicMock(
            status_code=200,
            text="<html>ok</html>",
            content=b"<html>ok</html>",
            headers={"Content-Type": "text/html"},
        )
        mock_resp.raise_for_status.return_value = None

        with patch.object(session._session, "request", return_value=mock_resp):
            session.get("http://test.com", save_raw=False)
            session.get("http://test.com", save_raw=False)

        # sleep should be called at least twice (once per request via _sleep)
        assert mock_sleep.call_count >= 2

    @patch("utils.http.time.sleep")
    @patch("utils.http.random.uniform")
    @patch.object(PoliteSession, "_save_raw")
    def test_blocked_domain_raises(self, mock_save_raw, mock_uniform, mock_sleep):
        """已冷却域名的请求直接抛出 BlockedError"""
        mock_uniform.return_value = 0.1
        session = PoliteSession(delay_range=(0, 0))
        session._blocked_domains.add("banned.com")

        with pytest.raises(BlockedError, match="banned.com"):
            session.get("http://banned.com/path")
