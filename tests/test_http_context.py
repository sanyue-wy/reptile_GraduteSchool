# -*- coding: utf-8 -*-
"""W2 基建测试：infra/http、infra/cache、infra/errors、infra/context。

全部使用临时根目录 + 模拟网络（Mock session），不触真实请求。
"""

import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from utils.http import PoliteSession, BlockedError, MaxRetriesExceeded
from utils.cache import CrawlCache
from infra.http import ManagedHttpSession, CancelledPipelineError
from infra.cache import ManagedCrawlCache
from infra.errors import (
    classify_http_error,
    error_from_exception,
    plugin_setup_error,
    cancelled_error,
    sanitize,
)
from infra.context import PipelineContextManager


@pytest.fixture
def fake_session():
    return PoliteSession(delay_range=(0.0, 0.0), max_retries=1, timeout=5)


@pytest.fixture
def real_cache(tmp_path):
    return CrawlCache(cache_dir=tmp_path / "cache")


class TestManagedHttpSession:
    def test_delegates_to_polite_session(self, fake_session):
        managed = ManagedHttpSession(fake_session)
        fake_session.get = Mock(return_value="RESP")
        assert managed.get("https://x.example/a") == "RESP"
        fake_session.get.assert_called_once_with("https://x.example/a")

    def test_cancel_token_blocks_dispatch(self, fake_session):
        token = threading.Event()
        managed = ManagedHttpSession(fake_session, cancel_token=token)
        fake_session.get = Mock()
        token.set()
        with pytest.raises(CancelledPipelineError):
            managed.get("https://x.example/a")
        fake_session.get.assert_not_called()

    def test_single_circuit_state_shared(self, fake_session):
        """红线：包装不得新建第二套熔断器——is_blocked/tripped 透传同一实例状态。"""
        managed = ManagedHttpSession(fake_session)
        fake_session._circuit_tripped.add("blocked.example")
        assert managed.is_blocked("blocked.example") is True
        assert "blocked.example" in managed.tripped_domains

    def test_stats_snapshot_is_copy(self, fake_session):
        managed = ManagedHttpSession(fake_session)
        snapshot = managed.stats
        snapshot["requests"] = 999
        assert fake_session.stats["requests"] == 0

    def test_close_delegates(self, fake_session):
        managed = ManagedHttpSession(fake_session)
        fake_session.close = Mock()
        managed.close()
        fake_session.close.assert_called_once()


class TestManagedCrawlCache:
    def test_read_and_write_delegate(self, real_cache):
        managed = ManagedCrawlCache(real_cache)
        assert managed.read_text("https://x.example/none") is None
        managed.write("https://x.example/page", "<html>x</html>")
        assert managed.read_text("https://x.example/page") == "<html>x</html>"

    def test_get_or_fetch_uses_single_cache_lock(self, real_cache):
        managed = ManagedCrawlCache(real_cache)
        calls = []

        def fetcher():
            calls.append(1)
            return "FRESH"

        first = managed.get_or_fetch(fetcher, "https://x.example/p")
        second = managed.get_or_fetch(fetcher, "https://x.example/p")
        assert first == second == "FRESH"
        assert len(calls) == 1  # 第二次走缓存，不重复抓取
        assert managed.hit_rate() > 0

    def test_cancel_token_blocks_reads(self, real_cache):
        token = threading.Event()
        token.set()
        managed = ManagedCrawlCache(real_cache, cancel_token=token)
        with pytest.raises(RuntimeError):
            managed.read_text("https://x.example/x")


class TestErrors:
    def test_classify_timeout(self):
        assert classify_http_error(requests.Timeout("t")) == "HTTP_TIMEOUT"

    def test_classify_connection(self):
        assert classify_http_error(requests.ConnectionError("boom")) == "HTTP_CONNECTION_ERROR"

    def test_classify_dns(self):
        err = requests.ConnectionError("[Errno -3] Temporary failure in name resolution")
        assert classify_http_error(err) == "HTTP_DNS_ERROR"

    def test_classify_blocked(self, fake_session):
        assert classify_http_error(BlockedError("冷却")) == "HTTP_BLOCKED"

    def test_classify_max_retries(self):
        assert classify_http_error(MaxRetriesExceeded("x")) == "HTTP_MAX_RETRIES"

    def test_error_dto_retryable_from_code_table(self):
        dto = error_from_exception(requests.Timeout("t"), "acquire")
        assert dto.code == "HTTP_TIMEOUT"
        assert dto.retryable is True
        blocked = error_from_exception(BlockedError("b"), "acquire")
        assert blocked.code == "HTTP_BLOCKED"
        assert blocked.retryable is False

    def test_plugin_setup_error_code(self):
        dto = plugin_setup_error(RuntimeError("bad dep"))
        assert dto.code == "PLUGIN_SETUP_FAILED"
        assert dto.retryable is False

    def test_cancelled_error(self):
        dto = cancelled_error(task_id="t" * 32)
        assert dto.code == "PIPELINE_CANCELLED"
        assert dto.stage == "acquire"

    def test_sanitize_strips_credentials(self):
        text = sanitize("failed Authorization: Bearer secret-token password=hunter2 end")
        assert "secret-token" not in text
        assert "hunter2" not in text
        assert "Authorization: ***" in text


class TestPipelineContextManager:
    def _manager(self, tmp_path):
        return PipelineContextManager("a" * 32, tmp_path,
                                      session_kwargs={"delay_range": (0.0, 0.0)})

    def test_build_context_injects_all_fields(self, tmp_path):
        from contracts.task import TaskConfigDTO
        manager = self._manager(tmp_path)
        task = TaskConfigDTO(task_id="b" * 32, dataset="education", source_id="source_a",
                             profile_id="education.tutor.v1", target_url="https://x.example/l",
                             config_revision=1, config_snapshot={"list_url": "https://x.example/l"})
        context = manager.build_context(task)
        try:
            assert isinstance(context.http, PoliteSession)
            assert isinstance(context.cache, CrawlCache)
            assert context.progress is not None
            assert context.run_id == "a" * 32
            assert context.task_id == "b" * 32
            assert context.cancel_token is manager.cancel_token
            assert any(str(tmp_path) in p for p in context.allowed_paths)
            assert context.config_snapshot["task_id"] == "b" * 32
        finally:
            manager.release_context(context)

    def test_release_closes_session_exactly_once(self, tmp_path):
        manager = self._manager(tmp_path)
        from contracts.task import TaskConfigDTO
        task = TaskConfigDTO(task_id="c" * 32, dataset="d", source_id="s",
                             profile_id="p", target_url="https://x.example/l",
                             config_revision=1)
        context = manager.build_context(task)
        close_mock = Mock(wraps=context.http.close)
        context.http.close = close_mock
        manager.release_context(context)
        manager.release_context(context)  # 幂等
        assert close_mock.call_count == 1

    def test_shutdown_closes_remaining_sessions(self, tmp_path):
        manager = self._manager(tmp_path)
        from contracts.task import TaskConfigDTO
        tasks = [TaskConfigDTO(task_id=f"{i:x}".zfill(32), dataset="d", source_id="s",
                               profile_id="p", target_url="u", config_revision=1)
                 for i in range(3)]
        contexts = [manager.build_context(t) for t in tasks]
        for ctx in contexts:
            ctx.http.close = Mock(wraps=ctx.http.close)
        manager.shutdown()
        assert all(ctx.http.close.call_count == 1 for ctx in contexts)
        manager.shutdown()  # 二次 shutdown 无异常

    def test_cancel_token_propagates(self, tmp_path):
        manager = self._manager(tmp_path)
        assert manager.is_cancelled() is False
        manager.request_cancel()
        assert manager.is_cancelled() is True

    def test_shared_session_factory_reused(self, tmp_path):
        shared = PoliteSession(delay_range=(0.0, 0.0))
        factory_calls = []

        def factory():
            factory_calls.append(1)
            return shared

        manager = PipelineContextManager("d" * 32, tmp_path, shared_session_factory=factory)
        from contracts.task import TaskConfigDTO
        task = TaskConfigDTO(task_id="e" * 32, dataset="d", source_id="s",
                             profile_id="p", target_url="u", config_revision=1)
        context = manager.build_context(task)
        assert context.http is shared
        assert factory_calls == [1]
        manager.release_context(context)

    def test_exit_closes_active_sessions(self, tmp_path):
        from contracts.task import TaskConfigDTO
        with PipelineContextManager("f" * 32, tmp_path,
                                    session_kwargs={"delay_range": (0.0, 0.0)}) as manager:
            task = TaskConfigDTO(task_id="1" * 32, dataset="d",
                                 source_id="s", profile_id="p", target_url="u",
                                 config_revision=1)
            context = manager.build_context(task)
            context.http.close = Mock(wraps=context.http.close)
        assert context.http.close.call_count == 1
