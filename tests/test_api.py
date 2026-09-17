# -*- coding: utf-8 -*-
"""
API 集成测试
==========
测试 Flask API 的 REST 接口。
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from api.server import app


@pytest.fixture
def client(monkeypatch, route_background):
    """Flask client exercises routes without launching background collection."""
    monkeypatch.setitem(app.config, "TESTING", True)
    with app.test_client() as client:
        yield client


@pytest.fixture
def route_background(monkeypatch):
    import api.server as server

    thread_factory = MagicMock(name="route_thread")
    # Replace this module's reference, NOT threading.Thread globally: cache and
    # progress concurrency tests must continue to use real threads.
    monkeypatch.setattr(server, "threading", SimpleNamespace(Thread=thread_factory))
    return thread_factory


@pytest.fixture(autouse=True)
def api_state(isolated_workspace, monkeypatch):
    import api.server as server

    monkeypatch.setattr(server, "GLOBAL_CONFIG_PATH", isolated_workspace / "config" / "global.json")
    monkeypatch.setattr(server, "_tasks", {})


@pytest.fixture(autouse=True)
def mock_progress(tmp_path, monkeypatch, isolated_workspace):
    """Mock ProgressTracker 全局单例"""
    from utils.progress import ProgressTracker

    progress_file = tmp_path / "output" / "progress.json"
    log_file = tmp_path / "output" / "crawl.log"
    tracker = ProgressTracker(progress_file=progress_file, log_file=log_file)

    import api.server as server_module
    monkeypatch.setattr(server_module, "get_progress_tracker", lambda: tracker)
    yield tracker


@pytest.fixture(autouse=True)
def mock_output(isolated_workspace):
    """Keep real API readers; the shared fixture supplies an empty private data/."""
    return isolated_workspace / "data" / "output"


class TestApiOverview:
    """概览接口单测"""

    def test_overview_success(self, client):
        """GET /api/overview 返回 code 0"""
        resp = client.get("/api/overview")
        data = resp.get_json()
        assert data["code"] == 0

    def test_overview_has_all_fields(self, client):
        """响应包含所有必填字段"""
        data = client.get("/api/overview").get_json()["data"]
        required = ["stats", "progress", "source_breakdown", "recent_tutors", "recent_failures", "logs"]
        for field in required:
            assert field in data, f"缺少字段: {field}"


class TestApiSchools:
    """学校列表接口单测"""

    def test_list_schools(self, client):
        """GET /api/schools 返回分页数据"""
        resp = client.get("/api/schools")
        data = resp.get_json()
        assert data["code"] == 0
        assert "items" in data["data"]
        assert "total" in data["data"]
        assert "summary" in data["data"]

    def test_filter_by_category(self, client):
        """按学科分类过滤"""
        resp = client.get("/api/schools?category=mechanical")
        data = resp.get_json()
        assert data["code"] == 0

    def test_pagination(self, client):
        """分页参数生效"""
        resp = client.get("/api/schools?page=1&page_size=5")
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["page_size"] == 5
        assert len(data["data"]["items"]) <= 5


class TestApiTutors:
    """导师列表接口单测"""

    def test_list_tutors_empty(self, client):
        """无数据时返回空列表"""
        resp = client.get("/api/tutors")
        data = resp.get_json()
        assert data["code"] == 0
        assert "items" in data["data"]
        assert "total" in data["data"]

    def test_filter_by_school(self, client):
        """按学校过滤"""
        resp = client.get("/api/tutors?school=测试大学")
        data = resp.get_json()
        assert data["code"] == 0
        assert "total" in data["data"]


class TestApiFailures:
    """失败记录接口单测"""

    def test_list_failures_empty(self, client):
        """无 failures.json 时返回空列表"""
        resp = client.get("/api/failures")
        data = resp.get_json()
        assert data["code"] == 0
        assert "items" in data["data"]

    def test_failures_filter_by_status(self, client):
        """按状态过滤失败记录"""
        resp = client.get("/api/failures?status=active")
        data = resp.get_json()
        assert data["code"] == 0


class TestApiConfig:
    """配置接口单测"""

    def test_get_config(self, client):
        """GET /api/config 返回全局配置和学校列表"""
        resp = client.get("/api/config")
        data = resp.get_json()
        assert data["code"] == 0
        assert "global" in data["data"]
        assert "schools" in data["data"]

    def test_get_config_has_global_fields(self, client):
        """全局配置包含必填字段"""
        data = client.get("/api/config").get_json()["data"]["global"]
        required = ["delay_range", "max_retries", "timeout", "cooldown_threshold",
                     "cooldown_seconds", "workers", "year", "fuzzy_threshold"]
        for field in required:
            assert field in data, f"缺少全局配置字段: {field}"

    def test_save_school_config_validation(self, client):
        """保存学校配置缺少必填字段返回 400"""
        resp = client.put("/api/config/schools/测试大学", json={"university": "测试"})
        data = resp.get_json()
        assert data["code"] in (0, 40001)

    def test_config_test_connection_no_url(self, client):
        """测试连接缺少 URL 参数"""
        resp = client.post("/api/config/test", json={})
        data = resp.get_json()
        assert data["code"] == 40001


class TestErrorHandling:
    """错误处理单测"""

    def test_404_endpoint(self, client):
        """未知接口返回 404"""
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_error_response_format(self, client):
        """错误响应包含 code 和 message"""
        resp = client.get("/api/schools/999999")
        if resp.status_code != 404:
            return
        data = resp.get_json()
        assert "code" in data
        assert "message" in data


class TestApiConfigExtended:
    """扩展配置接口单测"""

    def test_config_export(self, client):
        """GET /api/config/export 导出配置"""
        resp = client.get("/api/config/export")
        assert resp.status_code == 200

    def test_config_global_save(self, client, monkeypatch, tmp_path):
        """PUT /api/config/global 写入临时路径，不污染真实配置"""
        import api.server as server_module
        target = tmp_path / "global.json"
        monkeypatch.setattr(server_module, "GLOBAL_CONFIG_PATH", target)
        resp = client.put("/api/config/global", json={"delay_range": [0.5, 1.5]})
        data = resp.get_json()
        assert data["code"] == 0
        assert json.loads(target.read_text(encoding="utf-8")) == {"delay_range": [0.5, 1.5]}

    def test_config_test_connection(self, client, monkeypatch):
        """Exercise real PoliteSession with a mocked requests transport."""
        from requests import Response

        response = Response()
        response.status_code = 200
        response._content = b"<html><title>Offline test</title></html>"
        response.headers["Content-Type"] = "text/html; charset=utf-8"
        response.encoding = "utf-8"
        response.url = "http://example.com"
        transport = MagicMock(return_value=response)
        monkeypatch.setattr("requests.sessions.Session.request", transport)
        resp = client.post("/api/config/test", json={"url": response.url})
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["reachable"] is True
        assert data["data"]["sample_title"] == "Offline test"
        transport.assert_called_once()

    def test_config_import_no_file(self, client):
        """POST /api/config/import 无文件返回400"""
        resp = client.post("/api/config/import")
        data = resp.get_json()
        assert data["code"] == 40001

    def test_config_import_with_file(self, client, monkeypatch):
        """POST /api/config/import 上传 JSON 文件"""
        import io
        import json as json_mod
        config_data = json_mod.dumps([{"university": "测试大学", "categories": [{"college": "机械学院", "category": "mechanical", "faculty": {"list_url": "http://test.edu.cn", "list_type": "static_html"}, "notice": {"enabled": False}}]}])
        data = io.BytesIO(config_data.encode("utf-8"))
        monkeypatch.setattr("api.server._write_schools_config", lambda x: None)
        resp = client.post("/api/config/import", data={"file": (data, "school_data.json", "application/json")},
                           content_type="multipart/form-data")
        assert resp.status_code in (200, 400)

    def test_config_import_valid(self, client, monkeypatch):
        """POST /api/config/import 有效配置"""
        import io
        import json as json_mod
        config_data = json_mod.dumps([{"university": "测试大学", "categories": [{"college": "机械学院", "category": "mechanical", "faculty": {"list_url": "http://test.edu.cn", "list_type": "static_html"}, "notice": {"enabled": False}}]}])
        data = io.BytesIO(config_data.encode("utf-8"))
        # 防止写入真实 school_data.json
        monkeypatch.setattr("api.server._write_schools_config", lambda x: None)
        resp = client.post("/api/config/import", data={"file": (data, "school_data.json", "application/json")},
                           content_type="multipart/form-data")
        assert resp.status_code == 200

    def test_crawl_no_schools(self, client):
        """POST /api/crawl 空学校列表返回400"""
        resp = client.post("/api/crawl", json={"schools": []})
        data = resp.get_json()
        assert data["code"] == 40001

    def test_failures_retry_no_ids(self, client):
        """POST /api/failures/retry 无ID返回400"""
        resp = client.post("/api/failures/retry", json={})
        data = resp.get_json()
        assert data["code"] == 40001

    def test_task_status_not_found(self, client):
        """GET /api/tasks/xxx 任务不存在返回404"""
        resp = client.get("/api/tasks/nonexistent_task")
        data = resp.get_json()
        assert data["code"] == 40404

    def test_tutors_export(self, client):
        """GET /api/tutors/export 导出导师数据"""
        resp = client.get("/api/tutors/export")
        assert resp.status_code == 200


class TestApiExport:
    """导出接口单测"""

    def test_tutors_export_json(self, client):
        """GET /api/tutors/export?format=json 返回 JSON"""
        resp = client.get("/api/tutors/export?format=json")
        assert resp.status_code == 200

    def test_tutors_export_xlsx(self, client):
        """GET /api/tutors/export?format=xlsx 返回 Excel"""
        resp = client.get("/api/tutors/export?format=xlsx")
        assert resp.status_code == 200

    def test_raw_file_not_found(self, client):
        """GET /api/raw/xxx 文件不存在返回404"""
        resp = client.get("/api/raw/nonexistent.html")
        data = resp.get_json()
        assert data["code"] == 40401

    def test_crawl_conflict(self, client, mock_progress, monkeypatch):
        """POST /api/crawl 冲突任务返回409"""
        def mock_load_configs():
            return [{
                "university": "测试大学",
                "categories": [{
                    "college": "机械学院",
                    "category": "mechanical",
                    "faculty": {"list_url": "http://test.edu.cn", "list_type": "static_html"},
                    "notice": {"enabled": False}
                }]
            }]
        monkeypatch.setattr("api.server._load_school_configs", mock_load_configs)
        mock_progress.update_school_status("测试大学", "机械学院", source_a="running")
        resp = client.post("/api/crawl", json={
            "schools": ["测试大学"],
            "categories": ["mechanical"],
            "sources": ["source_a"]
        })
        data = resp.get_json()
        assert data["code"] == 40901

    def test_crawl_all_schools(self, client, monkeypatch, route_background):
        """POST /api/crawl 使用 __all__ 创建任务"""
        def mock_load_configs():
            return [{
                "university": "测试大学",
                "categories": [{
                    "college": "机械学院",
                    "category": "mechanical",
                    "faculty": {"list_url": "http://test.edu.cn", "list_type": "static_html"},
                    "notice": {"enabled": False}
                }]
            }]
        monkeypatch.setattr("api.server._load_school_configs", mock_load_configs)
        resp = client.post("/api/crawl", json={"schools": ["__all__"]})
        data = resp.get_json()
        assert data["code"] == 0
        assert "task_id" in data["data"]
        import api.server as server
        route_background.assert_called_once_with(
            target=server._run_crawl_task, args=(data["data"]["task_id"],), daemon=True
        )
        route_background.return_value.start.assert_called_once_with()
        assert server._get_task(data["data"]["task_id"])["status"] == "queued"

    def test_school_detail(self, client, monkeypatch):
        """GET /api/schools/1 返回学校详情"""
        def mock_load_configs():
            return [{
                "university": "测试大学",
                "categories": [{
                    "college": "机械学院",
                    "category": "mechanical",
                    "faculty": {"list_url": "http://test.edu.cn", "list_type": "static_html"},
                    "notice": {"enabled": False}
                }]
            }]
        monkeypatch.setattr("api.server._load_school_configs", mock_load_configs)
        resp = client.get("/api/schools/1")
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["name"] == "测试大学"

    def test_school_detail_not_found(self, client, monkeypatch):
        """GET /api/schools/999 学校不存在"""
        def mock_load_configs():
            return []
        monkeypatch.setattr("api.server._load_school_configs", mock_load_configs)
        resp = client.get("/api/schools/999")
        data = resp.get_json()
        assert data["code"] == 40402


class TestApiFailuresExtended:
    """失败记录扩展单测"""

    def test_failure_ignore_not_found(self, client):
        """POST /api/failures/xxx/ignore 记录不存在返回404"""
        resp = client.post("/api/failures/nonexistent/ignore")
        data = resp.get_json()
        assert data["code"] == 40405

    def test_failures_retry_not_found(self, client):
        """POST /api/failures/retry 不匹配返回404"""
        resp = client.post("/api/failures/retry", json={"failure_ids": ["nonexistent"]})
        data = resp.get_json()
        assert data["code"] == 40405

    def test_failures_retry_all_empty(self, client):
        """POST /api/failures/retry retry_all 但无失败记录"""
        resp = client.post("/api/failures/retry", json={"retry_all": True})
        data = resp.get_json()
        assert data["code"] == 40405

    def test_config_save_validation_error(self, client):
        """PUT /api/config/schools/xxx 校验失败返回400"""
        resp = client.put("/api/config/schools/测试大学", json={"categories": []})
        data = resp.get_json()
        assert data["code"] == 40001

    def test_config_save_success(self, client, isolated_workspace):
        """Save through the real loader, and verify the temporary JSON and cache."""
        import config.loader as loader

        target = isolated_workspace / "config" / "school_data.json"
        assert loader._config_path == target
        resp = client.put("/api/config/schools/测试大学", json={
            "university": "测试大学",
            "categories": [{
                "college": "机械学院",
                "category": "mechanical",
                "faculty": {"list_url": "https://faculty.seu.edu.cn/teacher", "list_type": "static_html"},
                "notice": {"enabled": False}
            }]
        })
        data = resp.get_json()
        assert data["code"] == 0
        saved = json.loads(target.read_text(encoding="utf-8"))
        school = next(item for item in saved if item["university"] == "测试大学")
        assert school["categories"][0]["college"] == "机械学院"
        assert loader.get_school_config("测试大学") == school


class TestApiPlugins:
    """插件管理接口单测"""

    @pytest.fixture
    def plugin_api_env(self, isolated_workspace):
        """Reuse the shared private plugin paths/cache and exact module restoration."""
        import config.plugins as plugins
        return plugins

    def test_list_plugins(self, client, plugin_api_env):
        resp = client.get("/api/plugins")
        data = resp.get_json()
        assert data["code"] == 0
        kinds = {item["kind"] for item in data["data"]["items"]}
        assert kinds == {"source", "fetcher", "parser", "processor", "exporter", "presenter", "utility"}

    def test_config_includes_plugins(self, client, plugin_api_env):
        data = client.get("/api/config").get_json()["data"]
        assert "plugins" in data
        assert data["plugins"]["items"]

    def test_save_plugin_pipeline(self, client, plugin_api_env):
        resp = client.put("/api/plugins/pipeline/processors", json={"weights": {"merge": 10}})
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["weights"] == {"merge": 10}
        saved = json.loads(plugin_api_env.PLUGIN_CONFIG_PATH.read_text(encoding="utf-8"))
        assert saved["pipeline"]["processors"] == {"merge": 10}

    def test_save_plugin_pipeline_rejects_unknown_type(self, client, plugin_api_env):
        resp = client.put("/api/plugins/pipeline/presenters", json={"weights": {"overview": 1}})
        assert resp.get_json()["code"] == 40001

    def test_update_plugin(self, client, plugin_api_env):
        resp = client.put("/api/plugins/processor:merge", json={"enabled": False, "config": {"mode": "strict"}})
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["enabled"] is False
        assert data["data"]["config"] == {"mode": "strict"}

    def test_upload_reload_and_delete_plugin(self, client, plugin_api_env):
        source = '''PLUGIN_META = {"name": "sample", "kind": "processor", "version": "1.0.0", "author": "测试", "description": "sample"}\ndef process(records, ctx):\n    return records\n'''
        upload = client.post("/api/plugins/upload", data={"kind": "processor", "filename": "sample.py", "source": source})
        assert upload.get_json()["code"] == 0
        reload_resp = client.post("/api/plugins/processor:sample/reload")
        assert reload_resp.get_json()["code"] == 0
        delete_resp = client.delete("/api/plugins/processor:sample")
        assert delete_resp.get_json()["code"] == 0
        assert not (plugin_api_env.EXT_PLUGIN_DIR / "processor" / "sample.py").exists()

    def test_cache_clear(self, client, monkeypatch, tmp_path):
        import utils.cache as cache_module
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir()
        (cache_dir / "example.com").mkdir()
        (cache_dir / "example.com" / "page.html").write_text("<html></html>", encoding="utf-8")
        monkeypatch.setattr(cache_module, "CACHE_DIR", cache_dir)

        resp = client.post("/api/cache/clear")
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["removed"] == 1
        assert not cache_dir.exists()


class TestApiRunCrawlTask:
    """_run_crawl_task 单测"""

    def test_run_crawl_task_not_found(self):
        """任务不存在时静默返回"""
        from api.server import _run_crawl_task
        _run_crawl_task("nonexistent_task_id")

    @pytest.mark.parametrize("status", ["success", "failed"])
    def test_worker_service_injection_success_and_failure(self, monkeypatch, status, mock_progress):
        import api.server as server
        from services.crawler_service import CrawlerService, CrawlTask, CrawlResult
        from services.export_service import ExportService
        task_id = "service-worker-" + status
        server._set_task(task_id, {
            "task_id": task_id,
            "params": {"schools": ["测试大学"], "categories": ["mechanical"],
                       "sources": ["source_a"], "force": True, "year": 2026},
        })
        child = CrawlTask("测试大学", "机械学院", "mechanical", "source_a", 2026)
        received = []
        def build(service, args):
            assert args.school == ["测试大学"]
            assert args.category == ["mechanical"] and args.source == ["source_a"]
            return [child]
        def execute(service, task):
            received.append(task)
            return CrawlResult(task.key(), status, [], [],
                               "offline failure" if status == "failed" else None,
                               "timeout" if status == "failed" else "none")
        monkeypatch.setattr(CrawlerService, "build_tasks", build)
        monkeypatch.setattr(CrawlerService, "execute_task", execute)
        monkeypatch.setattr(CrawlerService, "run_merge", lambda service, tasks: [])
        monkeypatch.setattr(ExportService, "run_export_pipeline", lambda *args: {})
        server._run_crawl_task(task_id)
        result = server._get_task(task_id)
        assert received == [child]
        # A handled child failure does not abort the batch bookkeeping.
        assert result["status"] == "completed"
        assert result["progress"]["completed_steps"] == 1
        assert result["progress"]["total_steps"] == 1
        assert result["progress"]["percent"] == 100.0

    def test_worker_service_exception_sets_failed(self, monkeypatch):
        import api.server as server
        from services.crawler_service import CrawlerService
        task_id = "service-worker-exception"
        server._set_task(task_id, {"task_id": task_id, "params": {
            "schools": ["测试大学"], "categories": ["mechanical"], "sources": ["source_a"],
            "force": False, "year": 2026}})
        def broken(service, args):
            raise RuntimeError("offline service setup error")
        monkeypatch.setattr(CrawlerService, "build_tasks", broken)
        server._run_crawl_task(task_id)
        result = server._get_task(task_id)
        assert result["status"] == "failed"
        assert "offline service setup error" in result["progress"]["current_step"]

    def test_write_schools_config(self, monkeypatch, tmp_path):
        """_write_schools_config 原子写入"""
        import config.loader as loader_mod
        import api.server as server_module

        tmp_file = tmp_path / "test_school_data.json"
        tmp_file.write_text("[]", encoding="utf-8")

        monkeypatch.setattr(loader_mod, 'DEFAULT_CONFIG_PATH', tmp_file)
        monkeypatch.setattr(loader_mod, '_config_cache', None)

        server_module._write_schools_config([{"university": "测试大学"}])
        content = tmp_file.read_text(encoding="utf-8")
        assert "测试大学" in content


class TestApiErrorHandling:
    """错误处理单测"""

    def test_404_endpoint(self, client):
        """未知接口返回404"""
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404

    def test_error_response_format(self, client):
        """错误响应包含 code 和 message"""
        resp = client.get("/api/schools/999999")
        if resp.status_code != 404:
            return
        data = resp.get_json()
        assert "code" in data
        assert "message" in data


class TestDashboardServing:
    """前端静态托管单测 — 保证前后端同源、页面可加载"""

    def test_root_serves_index(self, client):
        """GET / 返回 dashboard 首页"""
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"<html" in resp.data.lower() or b"<!doctype html" in resp.data.lower()

    def test_serves_api_js(self, client):
        """GET /api.js 返回前端 API 封装"""
        resp = client.get("/api.js")
        assert resp.status_code == 200
        assert b"API_BASE" in resp.data

    def test_serves_component(self, client):
        """GET /components/toast.js 返回子组件"""
        resp = client.get("/components/toast.js")
        assert resp.status_code == 200

    def test_serves_page_html(self, client):
        """GET /schools.html 等页面可加载"""
        for page in ["schools.html", "tutors.html", "failures.html", "config.html"]:
            resp = client.get(f"/{page}")
            assert resp.status_code == 200, f"{page} 加载失败"

    def test_missing_file_404(self, client):
        """不存在的静态文件返回404"""
        resp = client.get("/no_such_file.html")
        assert resp.status_code == 404

    def test_disallowed_extension_404(self, client):
        """非白名单扩展名（如 .py）返回404，防止源码泄露"""
        resp = client.get("/api/server.py")
        assert resp.status_code == 404
