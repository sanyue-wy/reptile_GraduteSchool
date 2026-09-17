"""CLI compatibility contracts. Patch service dependencies, not main internals."""
import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestTestIsolation:
    def test_default_paths_are_temporary(self, isolated_workspace):
        import config.loader as loader
        import config.plugins as plugins
        from storage import ConfigStore
        assert Path.cwd() == isolated_workspace
        assert loader.DEFAULT_CONFIG_PATH.is_relative_to(isolated_workspace)
        assert loader._config_path.is_relative_to(isolated_workspace)
        assert plugins.PLUGIN_CONFIG_PATH.resolve().is_relative_to(isolated_workspace)
        assert plugins.EXT_PLUGIN_DIR.resolve().is_relative_to(isolated_workspace)
        assert ConfigStore()._path.is_relative_to(isolated_workspace)

    def test_loader_cache_starts_empty(self):
        import config.loader as loader
        assert loader._config_cache is None

    def test_progress_singleton_starts_clean(self, isolated_workspace):
        import utils.progress as progress
        assert progress._progress_tracker is None
        tracker = progress.get_progress_tracker()
        assert tracker.progress_file.resolve().is_relative_to(isolated_workspace)
        assert tracker.get_school_status("测试大学", "机械学院").get("source_a") != "done"
        tracker.update_school_status("测试大学", "机械学院", source_a="done")

    def test_plugin_cache_starts_clean(self):
        import config.plugins as plugins
        assert plugins._EXTERNAL_CACHE == {}
        plugins._EXTERNAL_CACHE["test-only"] = {"loaded": True}

    def test_network_guard_and_local_mock(self, no_real_network, monkeypatch):
        import socket
        import requests
        from requests.adapters import HTTPAdapter
        assert HTTPAdapter.send is no_real_network
        assert socket.getaddrinfo is no_real_network
        assert socket.socket.connect is no_real_network
        with pytest.raises(pytest.fail.Exception, match="Real network disabled"):
            requests.get("https://offline.invalid", timeout=0.01)
        response = MagicMock(status_code=200)
        monkeypatch.setattr(requests.Session, "request", MagicMock(return_value=response))
        assert requests.get("https://offline.invalid") is response

    def test_candidates_default_writes_to_temporary_directory(self, isolated_workspace, mock_session):
        from spiders.url_resolver import CANDIDATES_DIR, URLCandidate, URLResolver
        assert CANDIDATES_DIR.resolve().is_relative_to(isolated_workspace)
        URLResolver(session=mock_session)._save_candidates(
            "测试大学", "机械学院", [URLCandidate(url="https://offline.invalid")])
        target = isolated_workspace / "data/candidates/测试大学_机械学院_candidates.json"
        assert json.loads(target.read_text(encoding="utf-8"))["summary"]["total"] == 1
        mock_session.get.assert_not_called()


class TestLegacySignatures:
    @pytest.mark.parametrize("name,params", [
        ("build_tasks", ["schools", "categories", "sources", "year", "force", "resume", "retry_failed"]),
        ("run_merge", ["university", "college", "year", "progress"]),
        ("run_source_a", ["task", "session", "progress", "cache"]),
        ("run_source_b", ["task", "session", "progress", "cache"]),
        ("execute_task", ["task", "session", "progress", "cache"]),
    ])
    def test_signatures_unchanged(self, name, params):
        import main
        assert list(inspect.signature(getattr(main, name)).parameters) == params

    def test_task_key_unchanged(self):
        from main import CrawlTask
        task = CrawlTask("测试大学", "机械学院", "mechanical", "source_a", 2026, True)
        assert task.key() == "测试大学|机械学院|source_a"

    def test_build_wrapper_converts_seven_args_to_service_namespace(self, monkeypatch):
        from main import build_tasks
        from services.crawler_service import CrawlerService, CrawlTask
        task = CrawlTask("测试大学", "机械学院", "mechanical", "source_a", 2026)
        received = []
        def build(service, args):
            received.append(args)
            return [task]
        monkeypatch.setattr(CrawlerService, "build_tasks", build)
        assert build_tasks(["测试大学"], ["mechanical"], ["source_a"], 2026, True, False, True) == [task]
        assert vars(received[0]) == dict(school=["测试大学"], category=["mechanical"], source=["source_a"],
                                        year=2026, force=True, resume=False, retry_failed=True)

    @pytest.mark.parametrize("source", ["a", "b"])
    def test_source_wrapper_returns_old_list(self, source, monkeypatch, mock_progress, mock_session):
        import main
        from services.crawler_service import CrawlerService, CrawlResult
        task = main.CrawlTask("测试大学", "机械学院", "mechanical", f"source_{source}", 2026)
        records = [{"name": "张三"}]
        def run(service, actual):
            assert actual is task
            return CrawlResult(task.key(), "success", records, [])
        monkeypatch.setattr(CrawlerService, f"run_source_{source}", run)
        assert getattr(main, f"run_source_{source}")(task, mock_session, mock_progress) == records

    @pytest.mark.parametrize("status,error,kind,expected", [
        ("success", None, "none", (True, None, "none")),
        ("skipped", None, "none", (True, None, "none")),
        ("failed", "offline timeout", "timeout", (False, "offline timeout", "timeout")),
    ])
    def test_execute_wrapper_old_three_tuple(self, status, error, kind, expected, monkeypatch, mock_progress, mock_session):
        from main import execute_task, CrawlTask
        from services.crawler_service import CrawlerService, CrawlResult
        task = CrawlTask("测试大学", "机械学院", "mechanical", "source_a", 2026)
        def execute(service, actual):
            assert actual is task
            return CrawlResult(task.key(), status, [], [], error, kind)
        monkeypatch.setattr(CrawlerService, "execute_task", execute)
        assert execute_task(task, mock_session, mock_progress, None) == expected

    def test_run_merge_old_four_args_real_storage(self, mock_progress, isolated_workspace):
        from main import run_merge
        from storage import JSONLStore
        path = isolated_workspace / "data/output/测试大学_机械学院_faculty.jsonl"
        JSONLStore(path).write_all([{"name": "张三", "university": "测试大学", "college": "机械学院"}])
        merged = run_merge("测试大学", "机械学院", 2026, mock_progress)
        assert len(merged) == 1
        assert merged[0]["match_status"] == "partial_faculty"
        assert JSONLStore(path.with_name("测试大学_机械学院.jsonl")).read_all() == merged

    def test_run_merge_no_data(self, mock_progress):
        from main import run_merge
        assert run_merge("测试大学", "机械学院", 2026, mock_progress) == []


class TestCircuitBreaker:
    def test_initial_threshold_reset_and_domain_isolation(self):
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=3)
        assert not cb.is_tripped("example.com")
        assert not cb.record("example.com", "timeout")
        assert not cb.record("example.com", "timeout")
        assert cb.record("example.com", "timeout")
        assert cb.is_tripped("example.com")
        assert not cb.is_tripped("other.com")
        cb.reset("example.com")
        assert cb.tripped_domains == set()

    def test_dns_error_fast_trip(self):
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=5)
        assert cb.record("bad.example", "dns_error") is True
        assert cb.is_tripped("bad.example")

    def test_extract_domain(self):
        from main import _extract_domain
        assert _extract_domain("https://offline.invalid/path") == "offline.invalid"
        assert _extract_domain("") == ""
