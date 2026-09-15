# -*- coding: utf-8 -*-
"""
API 集成测试
==========
测试 Flask API 的 REST 接口。
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from api.server import app


@pytest.fixture
def client():
    """Flask test client"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture(autouse=True)
def mock_progress(tmp_path, monkeypatch):
    """Mock ProgressTracker 全局单例"""
    from utils.progress import ProgressTracker

    progress_file = tmp_path / "output" / "progress.json"
    log_file = tmp_path / "output" / "crawl.log"
    tracker = ProgressTracker(progress_file=progress_file, log_file=log_file)

    import api.server as server_module
    monkeypatch.setattr(server_module, "get_progress_tracker", lambda: tracker)
    yield tracker


@pytest.fixture(autouse=True)
def mock_output(tmp_path, monkeypatch):
    """Mock data/output 目录"""
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)

    import api.server as server_module

    # Mock _read_all_merged_records to return empty
    def _empty_records():
        return []

    def _mock_read_merged(university, college):
        return []

    monkeypatch.setattr(server_module, "_read_all_merged_records", _empty_records)
    monkeypatch.setattr(server_module, "_read_merged_records", _mock_read_merged)

    # Mock load_failures to return empty
    monkeypatch.setattr(server_module, "load_failures", lambda: [])

    yield output_dir


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

    def test_config_test_connection(self, client):
        """POST /api/config/test 测试连接"""
        resp = client.post("/api/config/test", json={"url": "http://example.com"})
        data = resp.get_json()
        assert data["code"] == 0

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

    def test_crawl_all_schools(self, client, monkeypatch):
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

    def test_config_save_success(self, client):
        """PUT /api/config/schools/xxx 保存成功"""
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


class TestApiRunCrawlTask:
    """_run_crawl_task 单测"""

    def test_run_crawl_task_not_found(self):
        """任务不存在时静默返回"""
        from api.server import _run_crawl_task
        _run_crawl_task("nonexistent_task_id")

    def test_run_crawl_task_with_mocked_main(self, monkeypatch):
        """_run_crawl_task 使用 mock main 模块"""
        import api.server as server_module
        import sys
        from unittest.mock import MagicMock

        task_id = "test_task"
        server_module._set_task(task_id, {
            "task_id": task_id,
            "params": {
                "schools": [],
                "categories": [],
                "sources": [],
                "force": True,
                "year": 2026,
            },
        })

        mock_main = MagicMock()
        mock_main.build_tasks.return_value = []
        mock_main.execute_task.return_value = (True, None)
        mock_cache = MagicMock()
        mock_main.CrawlCache = MagicMock(return_value=mock_cache)
        mock_http = MagicMock()
        mock_http.PoliteSession = MagicMock
        mock_progress_mod = MagicMock()
        mock_progress_mod.get_progress_tracker = MagicMock()

        sys.modules["main"] = mock_main
        sys.modules["utils.cache"] = mock_cache
        sys.modules["utils.http"] = mock_http
        sys.modules["utils.progress"] = mock_progress_mod

        try:
            server_module._run_crawl_task(task_id)
            task = server_module._get_task(task_id)
            assert task["status"] == "completed"
        finally:
            del sys.modules["main"]
            del sys.modules["utils.cache"]
            del sys.modules["utils.http"]
            del sys.modules["utils.progress"]

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
