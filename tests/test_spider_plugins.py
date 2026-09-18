# -*- coding: utf-8 -*-
"""
Tests for Spider Plugins (W4)
==============================
Offline fixture-based tests for all 6 spider plugins.
Uses mocked network responses and temporary directories.

Each plugin: normal→schema valid, pagination/cancel/token, network→ErrorDTO(retryable),
empty result valid, js_render no-dep graceful skip.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest
import requests

from plugins.spiders.static_html.plugin import StaticHtmlSpiderPlugin
from plugins.spiders.ajax_api.plugin import AjaxApiSpiderPlugin
from plugins.spiders.js_render.plugin import JSRenderSpiderPlugin
from plugins.spiders.pdf_list.plugin import PDFListSpiderPlugin
from plugins.spiders.yzw_api.plugin import YzwApiSpiderPlugin
from plugins.spiders.media_downloader.plugin import MediaDownloaderSpiderPlugin
from plugins.spiders import SpiderPlugin

from contracts.task import TaskConfigDTO
from contracts.raw import RawDataBatch, RawDataDTO
from contracts.asset import MediaAsset


def _make_mock_response(text="", content=b"", headers=None, status_code=200):
    resp = Mock(spec=requests.Response)
    resp.text = text
    resp.content = content
    resp.status_code = status_code
    resp.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
    resp.encoding = "utf-8"
    resp.raise_for_status = Mock()
    resp.json = Mock(return_value=json.loads(text) if text.startswith("{") else {})
    resp.iter_content = Mock(return_value=[content] if content else [b""])
    resp.close = Mock()
    return resp


class MockContext:
    def __init__(self, http_session=None, cache=None, cancel_token=None, allowed_paths=None):
        self.http = http_session
        self.cache = cache
        self.cancel_token = cancel_token
        self.allowed_paths = allowed_paths or []
        self.logger = Mock()


class MockCancelToken:
    def __init__(self, cancelled=False):
        self._cancelled = cancelled

    def is_set(self):
        return self._cancelled


@pytest.fixture
def mock_session():
    session = Mock()
    session.get = Mock(return_value=_make_mock_response(text="<html><body>test</body></html>"))
    session.post = Mock(return_value=_make_mock_response(text='{"total": 0, "data": []}'))
    session.close = Mock()
    session.stats = {"requests": 0, "success": 0, "failed": 0, "raw_saved": 0}
    session.is_blocked = Mock(return_value=False)
    return session


@pytest.fixture
def mock_cache():
    cache = Mock()
    cache.get_or_fetch = Mock(side_effect=lambda fn, key, force=False: fn())
    cache.stats = {"hits": 0, "misses": 0, "writes": 0}
    return cache


@pytest.fixture
def task_config():
    return TaskConfigDTO(
        task_id="aabbccddeeff0011aabbccddeeff0011",
        dataset="education",
        source_id="source_a",
        profile_id="faculty.v1",
        target_url="https://example.edu/faculty/list.htm",
        config_revision=1,
        config_snapshot={
            "list_url": "https://example.edu/faculty/list.htm",
            "selectors": {
                "item": "li.teacher a",
                "name": "title",
                "profile": "href",
                "research": ".research"
            },
            "max_pages": 2,
            "base_url": "https://example.edu/faculty/"
        }
    )


# --- SpiderPlugin Inheritance Tests ---

class TestSpiderPluginInheritance:
    """Verify all plugins inherit from SpiderPlugin(BasePlugin)."""

    def test_static_html_inherits_spider_plugin(self):
        assert issubclass(StaticHtmlSpiderPlugin, SpiderPlugin)

    def test_ajax_api_inherits_spider_plugin(self):
        assert issubclass(AjaxApiSpiderPlugin, SpiderPlugin)

    def test_js_render_inherits_spider_plugin(self):
        assert issubclass(JSRenderSpiderPlugin, SpiderPlugin)

    def test_pdf_list_inherits_spider_plugin(self):
        assert issubclass(PDFListSpiderPlugin, SpiderPlugin)

    def test_yzw_api_inherits_spider_plugin(self):
        assert issubclass(YzwApiSpiderPlugin, SpiderPlugin)

    def test_media_downloader_inherits_spider_plugin(self):
        assert issubclass(MediaDownloaderSpiderPlugin, SpiderPlugin)

    def test_spider_plugin_inherits_base_plugin(self):
        from plugins.base import BasePlugin
        assert issubclass(SpiderPlugin, BasePlugin)

    def test_plugin_type_is_spider(self):
        for cls in [StaticHtmlSpiderPlugin, AjaxApiSpiderPlugin, JSRenderSpiderPlugin,
                     PDFListSpiderPlugin, YzwApiSpiderPlugin, MediaDownloaderSpiderPlugin]:
            assert cls.plugin_type == "spider"
            assert cls.input_schema == "TaskConfigDTO.v1"
            assert cls.output_schema == "RawDataBatch.v1"


# --- Static HTML Plugin Tests ---

class TestStaticHtmlSpiderPlugin:

    def test_plugin_metadata(self):
        meta_path = Path(__file__).parent.parent / "plugins/spiders/static_html/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "static_html"
        assert meta["plugin_type"] == "spider"
        assert meta["input_schema"] == "TaskConfigDTO.v1"
        assert meta["output_schema"] == "RawDataBatch.v1"
        assert "additionalProperties" in meta["config_schema"]
        assert meta["config_schema"]["additionalProperties"] is False
        assert meta.get("license") == "MIT"

    def test_execute_returns_raw_batch(self, mock_session, mock_cache, task_config):
        plugin = StaticHtmlSpiderPlugin()
        html_content = """
        <html><body>
            <ul>
                <li class="teacher"><a href="/faculty/zhang.html" title="张三">张三</a><span class="research">AI</span></li>
                <li class="teacher"><a href="/faculty/li.html" title="李四">李四</a><span class="research">ML</span></li>
            </ul>
        </body></html>
        """
        mock_session.get.return_value.text = html_content
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert batch.schema_version == "1"
        assert batch.task_id == task_config.task_id
        assert len(batch.items) >= 1
        assert all(isinstance(item, RawDataDTO) for item in batch.items)
        assert all(item.assets for item in batch.items)
        assert all(asset.media_type == "text" for item in batch.items for asset in item.assets)

    def test_list_page_asset_has_html_content(self, mock_session, mock_cache, task_config):
        plugin = StaticHtmlSpiderPlugin()
        html_content = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul></body></html>"
        mock_session.get.return_value.text = html_content
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        list_page_item = batch.items[0]
        assert list_page_item.assets[0].media_type == "text"
        assert list_page_item.assets[0].mime_type == "text/html"
        assert b"<html" in list_page_item.assets[0].data

    def test_pagination_stops_at_max_pages(self, mock_session, mock_cache, task_config):
        task_config.config_snapshot["max_pages"] = 1
        plugin = StaticHtmlSpiderPlugin()
        list_html = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul><a class='next' href='page2.html'>Next</a></body></html>"
        detail_html = "<html><body><div class='teacher-detail'>Detail page</div></body></html>"

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            resp = Mock()
            resp.text = list_html if call_count[0] == 1 else detail_html
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.encoding = "utf-8"
            return resp

        mock_session.get.side_effect = mock_get
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert mock_session.get.call_count == 2
        assert batch.pagination_complete is True

    def test_cancellation_stops_execution(self, mock_session, mock_cache, task_config):
        plugin = StaticHtmlSpiderPlugin()
        html_content = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul></body></html>"
        mock_session.get.return_value.text = html_content

        cancel_token = MockCancelToken(cancelled=True)
        context = MockContext(http_session=mock_session, cache=mock_cache, cancel_token=cancel_token)
        batch = plugin.execute(task_config, context)

        assert any(e["code"] == "PIPELINE_CANCELLED" for e in batch.errors)

    def test_network_error_produces_error_dto(self, mock_session, mock_cache, task_config):
        from utils.http import BlockedError
        plugin = StaticHtmlSpiderPlugin()
        mock_session.get.side_effect = BlockedError("Rate limited")

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any(e["code"] == "HTTP_BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is False for e in batch.errors)

    def test_empty_list_page_returns_empty_batch(self, mock_session, mock_cache, task_config):
        plugin = StaticHtmlSpiderPlugin()
        html_content = "<html><body><ul></ul></body></html>"
        mock_session.get.return_value.text = html_content

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert batch.pagination_complete is True
        assert len(batch.items) >= 1

    def test_detail_page_error_handled_gracefully(self, mock_session, mock_cache, task_config):
        from utils.http import BlockedError
        plugin = StaticHtmlSpiderPlugin()

        list_html = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul></body></html>"

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            resp = Mock()
            if call_count[0] == 1:
                resp.text = list_html
                resp.status_code = 200
                resp.headers = {"Content-Type": "text/html; charset=utf-8"}
                resp.encoding = "utf-8"
                return resp
            raise BlockedError("Detail page blocked")

        mock_session.get.side_effect = mock_get
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) >= 1
        assert any(e["code"] == "HTTP_BLOCKED" for e in batch.errors)

    def test_next_page_fallback_selectors(self, mock_session, mock_cache, task_config):
        plugin = StaticHtmlSpiderPlugin()
        task_config.config_snapshot["max_pages"] = 2
        task_config.config_snapshot["selectors"]["next_page"] = ".nonexistent"

        page1_html = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul><a class='next' href='/faculty/list_2.htm'>Next</a></body></html>"
        page2_html = "<html><body><ul><li class='teacher'><a href='/faculty/li.html' title='李四'>李四</a></li></ul></body></html>"

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            resp = Mock()
            if call_count[0] == 1:
                resp.text = page1_html
            else:
                resp.text = page2_html
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.encoding = "utf-8"
            return resp

        mock_session.get.side_effect = mock_get
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert mock_session.get.call_count >= 2
        assert batch.pagination_complete is True

    def test_retry_on_fetch_error(self, mock_session, mock_cache, task_config):
        plugin = StaticHtmlSpiderPlugin()

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("Network unreachable")
            resp = Mock()
            resp.text = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul></body></html>"
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.encoding = "utf-8"
            return resp

        mock_session.get.side_effect = mock_get
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        # 1 fail (PLUGIN_EXECUTE_FAILED, retryable) + 1 retry + 1 detail = 3 calls
        assert mock_session.get.call_count == 3
        assert len(batch.items) >= 1


# --- AJAX API Plugin Tests ---

class TestAjaxApiSpiderPlugin:

    def test_plugin_metadata(self):
        meta_path = Path(__file__).parent.parent / "plugins/spiders/ajax_api/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "ajax_api"
        assert meta["plugin_type"] == "spider"
        assert meta.get("license") == "MIT"

    def test_execute_returns_json_assets(self, mock_session, mock_cache):
        plugin = AjaxApiSpiderPlugin()
        api_response = {
            "total": 2,
            "data": [
                {"title": "张三", "post": "教授", "degree": "博士", "exField1": "博士生导师", "cnUrl": "/faculty/zhang.html", "headerPic": "/images/zhang.jpg"},
                {"title": "李四", "post": "副教授", "degree": "博士", "exField1": "硕士生导师", "cnUrl": "/faculty/li.html", "headerPic": "/images/li.jpg"}
            ]
        }
        mock_resp = Mock()
        mock_resp.text = json.dumps(api_response)
        mock_resp.json.return_value = api_response
        mock_session.post.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0012",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/api",
            config_revision=1,
            config_snapshot={
                "api_url": "https://example.edu/_wp3services/generalQuery",
                "site_id": "338",
                "referer": "https://example.edu/faculty/list.htm",
                "max_pages": 2,
                "page_size": 500
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert len(batch.items) >= 1
        assert batch.items[0].assets[0].media_type == "text"
        assert batch.items[0].assets[0].mime_type == "application/json"

    def test_pagination_stops_when_total_reached(self, mock_session, mock_cache):
        plugin = AjaxApiSpiderPlugin()
        page1 = {"total": 3, "data": [{"title": "A"}, {"title": "B"}]}
        page2 = {"total": 3, "data": [{"title": "C"}]}

        mock_resp1 = Mock()
        mock_resp1.text = json.dumps(page1)
        mock_resp2 = Mock()
        mock_resp2.text = json.dumps(page2)
        mock_session.post.side_effect = [mock_resp1, mock_resp2]

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0013",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/api",
            config_revision=1,
            config_snapshot={
                "api_url": "https://example.edu/_wp3services/generalQuery",
                "site_id": "338",
                "referer": "https://example.edu/faculty/list.htm",
                "max_pages": 10,
                "page_size": 2
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert mock_session.post.call_count == 2
        assert batch.pagination_complete is True

    def test_network_error_produces_error_dto(self, mock_session, mock_cache):
        from utils.http import BlockedError
        plugin = AjaxApiSpiderPlugin()
        mock_session.post.side_effect = BlockedError("Rate limited")

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0014",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/api",
            config_revision=1,
            config_snapshot={
                "api_url": "https://example.edu/_wp3services/generalQuery",
                "site_id": "338",
                "referer": "https://example.edu/faculty/list.htm",
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any(e["code"] == "HTTP_BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is False for e in batch.errors)

    def test_empty_api_response_returns_empty_batch(self, mock_session, mock_cache):
        plugin = AjaxApiSpiderPlugin()
        api_response = {"total": 0, "data": []}
        mock_resp = Mock()
        mock_resp.text = json.dumps(api_response)
        mock_resp.json.return_value = api_response
        mock_session.post.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0015",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/api",
            config_revision=1,
            config_snapshot={
                "api_url": "https://example.edu/_wp3services/generalQuery",
                "site_id": "338",
                "referer": "https://example.edu/faculty/list.htm",
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert batch.pagination_complete is True
        assert len(batch.items) >= 1


# --- JS Render Plugin Tests ---

class TestJSRenderSpiderPlugin:

    def test_plugin_metadata(self):
        meta_path = Path(__file__).parent.parent / "plugins/spiders/js_render/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "js_render"
        assert meta["plugin_type"] == "spider"
        assert "playwright" in meta.get("optional_dependencies", [])
        assert meta.get("license") == "MIT"

    def test_precheck_reports_dependency_status(self):
        plugin = JSRenderSpiderPlugin()
        ok, err = plugin.precheck()
        assert isinstance(ok, bool)
        if not ok:
            assert "Playwright not installed" in err

    def test_execute_raises_without_playwright(self, mock_session, mock_cache, task_config):
        plugin = JSRenderSpiderPlugin()
        with patch.object(plugin, 'precheck', return_value=(False, "Playwright not installed")):
            context = MockContext(http_session=mock_session, cache=mock_cache)
            with pytest.raises(JSRenderSpiderPlugin.DependencyError):
                plugin.execute(task_config, context)


# --- PDF List Plugin Tests ---

class TestPDFListSpiderPlugin:

    def test_plugin_metadata(self):
        meta_path = Path(__file__).parent.parent / "plugins/spiders/pdf_list/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "pdf_list"
        assert meta["plugin_type"] == "spider"
        assert meta.get("license") == "MIT"

    def test_execute_returns_pdf_asset(self, mock_session, mock_cache):
        plugin = PDFListSpiderPlugin()
        pdf_content = b"%PDF-1.4\nfake pdf content"
        mock_resp = Mock()
        mock_resp.content = pdf_content
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0016",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/faculty/list.pdf",
            config_revision=1,
            config_snapshot={"pdf_url": "https://example.edu/faculty/list.pdf"}
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert len(batch.items) == 1
        assert batch.items[0].assets[0].media_type == "document"
        assert batch.items[0].assets[0].mime_type == "application/pdf"
        assert batch.items[0].assets[0].data == pdf_content

    def test_network_error_produces_error_dto(self, mock_session, mock_cache):
        from utils.http import BlockedError
        plugin = PDFListSpiderPlugin()
        mock_session.get.side_effect = BlockedError("Rate limited")

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0017",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/faculty/list.pdf",
            config_revision=1,
            config_snapshot={"pdf_url": "https://example.edu/faculty/list.pdf"}
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any(e["code"] == "HTTP_BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is False for e in batch.errors)

    def test_cancellation_stops_execution(self, mock_session, mock_cache):
        plugin = PDFListSpiderPlugin()
        cancel_token = MockCancelToken(cancelled=True)

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0018",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/faculty/list.pdf",
            config_revision=1,
            config_snapshot={"pdf_url": "https://example.edu/faculty/list.pdf"}
        )
        context = MockContext(http_session=mock_session, cache=mock_cache, cancel_token=cancel_token)
        batch = plugin.execute(task_config, context)

        assert any(e["code"] == "PIPELINE_CANCELLED" for e in batch.errors)


# --- YZW API Plugin Tests ---

class TestYzwApiSpiderPlugin:

    def test_plugin_metadata(self):
        meta_path = Path(__file__).parent.parent / "plugins/spiders/yzw_api/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "yzw_api"
        assert meta["plugin_type"] == "spider"
        assert meta.get("license") == "MIT"

    def test_execute_returns_json_assets(self, mock_session, mock_cache):
        plugin = YzwApiSpiderPlugin()
        api_response = {
            "total": 2,
            "data": [
                {"dwmc": "东南大学", "yjfxmc": "机械工程", "zdjs": "张三", "zydm": "080200", "nzsrsstr": "10"},
                {"dwmc": "东南大学", "yjfxmc": "机械工程", "zdjs": "李四", "zydm": "080201", "nzsrsstr": "8"}
            ]
        }
        mock_resp = Mock()
        mock_resp.text = json.dumps(api_response)
        mock_resp.json.return_value = api_response
        mock_session.post.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0019",
            dataset="education",
            source_id="source_b",
            profile_id="major.v1",
            target_url="https://yz.chsi.com.cn",
            config_revision=1,
            config_snapshot={
                "school_code": "10213",
                "year": 2026,
                "category": "mechanical",
                "university": "东南大学",
                "page_size": 500
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert len(batch.items) >= 1
        assert batch.items[0].assets[0].media_type == "text"
        assert batch.items[0].assets[0].mime_type == "application/json"

    def test_network_error_produces_error_dto(self, mock_session, mock_cache):
        from utils.http import BlockedError
        plugin = YzwApiSpiderPlugin()
        mock_session.post.side_effect = BlockedError("Rate limited")

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff001a",
            dataset="education",
            source_id="source_b",
            profile_id="major.v1",
            target_url="https://yz.chsi.com.cn",
            config_revision=1,
            config_snapshot={
                "school_code": "10213",
                "year": 2026,
                "category": "mechanical",
                "university": "东南大学",
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any(e["code"] == "HTTP_BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is False for e in batch.errors)

    def test_cancellation_stops_execution(self, mock_session, mock_cache):
        plugin = YzwApiSpiderPlugin()
        cancel_token = MockCancelToken(cancelled=True)

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff001b",
            dataset="education",
            source_id="source_b",
            profile_id="major.v1",
            target_url="https://yz.chsi.com.cn",
            config_revision=1,
            config_snapshot={
                "school_code": "10213",
                "year": 2026,
                "category": "mechanical",
                "university": "东南大学",
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache, cancel_token=cancel_token)
        batch = plugin.execute(task_config, context)

        assert any(e["code"] == "PIPELINE_CANCELLED" for e in batch.errors)

    def test_pagination_multiple_pages(self, mock_session, mock_cache):
        plugin = YzwApiSpiderPlugin()
        page1 = {"total": 3, "data": [{"zydm": "080200"}, {"zydm": "080201"}]}
        page2 = {"total": 3, "data": [{"zydm": "080202"}]}

        mock_resp1 = Mock()
        mock_resp1.text = json.dumps(page1)
        mock_resp2 = Mock()
        mock_resp2.text = json.dumps(page2)
        mock_session.post.side_effect = [mock_resp1, mock_resp2, mock_resp2, mock_resp2]

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff001c",
            dataset="education",
            source_id="source_b",
            profile_id="major.v1",
            target_url="https://yz.chsi.com.cn",
            config_revision=1,
            config_snapshot={
                "school_code": "10213",
                "year": 2026,
                "major_codes": ["080200", "080201", "080202"],
                "university": "东南大学",
                "page_size": 2
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert mock_session.post.call_count >= 2
        assert batch.pagination_complete is True


# --- Media Downloader Plugin Tests ---

class TestMediaDownloaderSpiderPlugin:

    def test_plugin_metadata(self):
        meta_path = Path(__file__).parent.parent / "plugins/spiders/media_downloader/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "media_downloader"
        assert meta["plugin_type"] == "spider"
        assert "required" in meta["config_schema"]
        assert "urls" in meta["config_schema"]["required"]
        assert meta.get("license") == "MIT"

    def test_execute_downloads_images(self, mock_session, mock_cache):
        plugin = MediaDownloaderSpiderPlugin()
        img_content = b"fake png content"
        mock_resp = Mock()
        mock_resp.headers = {"Content-Type": "image/png", "Content-Length": str(len(img_content))}
        mock_resp.iter_content.return_value = [img_content]
        mock_resp.close = Mock()
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0020",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://example.edu/photo.png",
            config_revision=1,
            config_snapshot={
                "urls": ["https://example.edu/photo.png"],
                "max_size_mb": 10,
                "allowed_domains": ["example.edu"],
                "allowed_mime_types": ["image/*"]
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert len(batch.items) == 1
        assert batch.items[0].assets[0].media_type == "image"
        assert batch.items[0].assets[0].mime_type == "image/png"
        assert batch.items[0].assets[0].data == img_content

    def test_domain_whitelist_blocks_unallowed(self, mock_session, mock_cache):
        plugin = MediaDownloaderSpiderPlugin()

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0021",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://evil.com/photo.png",
            config_revision=1,
            config_snapshot={
                "urls": ["https://evil.com/photo.png"],
                "allowed_domains": ["example.edu"]
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any("not in allowed list" in e["message"] for e in batch.errors)
        assert any(e["retryable"] is False for e in batch.errors)

    def test_mime_type_filter(self, mock_session, mock_cache):
        plugin = MediaDownloaderSpiderPlugin()
        mock_resp = Mock()
        mock_resp.headers = {"Content-Type": "application/x-executable", "Content-Length": "100"}
        mock_resp.iter_content.return_value = [b"x" * 100]
        mock_resp.close = Mock()
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0022",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://example.edu/bad.exe",
            config_revision=1,
            config_snapshot={
                "urls": ["https://example.edu/bad.exe"],
                "allowed_mime_types": ["image/*"]
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any("not allowed" in e["message"] for e in batch.errors)

    def test_network_error_produces_error_dto(self, mock_session, mock_cache):
        plugin = MediaDownloaderSpiderPlugin()
        mock_session.get.side_effect = Exception("Connection timeout")

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0023",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://example.edu/photo.png",
            config_revision=1,
            config_snapshot={
                "urls": ["https://example.edu/photo.png"],
                "allowed_domains": ["example.edu"],
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any(e["code"] in ("HTTP_TIMEOUT", "PLUGIN_EXECUTE_FAILED") for e in batch.errors)
        assert any(e["retryable"] is True for e in batch.errors)

    def test_cancellation_stops_execution(self, mock_session, mock_cache):
        plugin = MediaDownloaderSpiderPlugin()
        cancel_token = MockCancelToken(cancelled=True)

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0024",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://example.edu/photo.png",
            config_revision=1,
            config_snapshot={
                "urls": ["https://example.edu/photo.png"],
                "allowed_domains": ["example.edu"],
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache, cancel_token=cancel_token)
        batch = plugin.execute(task_config, context)

        assert any(e["code"] == "PIPELINE_CANCELLED" for e in batch.errors)

    def test_multiple_urls_downloaded(self, mock_session, mock_cache):
        plugin = MediaDownloaderSpiderPlugin()
        img1 = b"fake png 1"
        img2 = b"fake jpg 2"
        mock_resp1 = Mock()
        mock_resp1.headers = {"Content-Type": "image/png", "Content-Length": str(len(img1))}
        mock_resp1.iter_content.return_value = [img1]
        mock_resp1.close = Mock()
        mock_resp2 = Mock()
        mock_resp2.headers = {"Content-Type": "image/jpeg", "Content-Length": str(len(img2))}
        mock_resp2.iter_content.return_value = [img2]
        mock_resp2.close = Mock()
        mock_session.get.side_effect = [mock_resp1, mock_resp2]

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0025",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://example.edu/photo.png",
            config_revision=1,
            config_snapshot={
                "urls": ["https://example.edu/photo1.png", "https://example.edu/photo2.jpg"],
                "allowed_domains": ["example.edu"],
                "allowed_mime_types": ["image/*"]
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 2
        assert batch.items[0].assets[0].media_type == "image"
        assert batch.items[1].assets[0].media_type == "image"

    def test_oversized_file_streams_to_disk(self, mock_session, mock_cache, tmp_path):
        """Test that files exceeding max_size get streamed to disk as url-referenced assets."""
        plugin = MediaDownloaderSpiderPlugin()

        # Content-Length exceeds max_size_mb=0 limit, triggers _stream_to_disk
        big_content = b"x" * 200
        mock_resp = Mock()
        mock_resp.headers = {"Content-Type": "image/png", "Content-Length": "200"}
        mock_resp.iter_content.return_value = [big_content]
        mock_resp.close = Mock()
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0026",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://example.edu/big.png",
            config_revision=1,
            config_snapshot={
                "urls": ["https://example.edu/big.png"],
                "allowed_domains": ["example.edu"],
                "allowed_mime_types": ["image/*"],
                "max_size_mb": 0,
            }
        )
        context = MockContext(
            http_session=mock_session,
            cache=mock_cache,
            allowed_paths=[str(tmp_path)],
        )
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 1
        asset = batch.items[0].assets[0]
        assert asset.media_type == "image"
        assert asset.url is not None
        assert asset.data is None
        assert asset.size == 200
        assert len(asset.sha256) == 64

    def test_oversized_no_output_dir_produces_error(self, mock_session, mock_cache):
        """Test oversized file with no output dir produces error."""
        plugin = MediaDownloaderSpiderPlugin()

        big_content = b"x" * 200
        mock_resp = Mock()
        mock_resp.headers = {"Content-Type": "image/png", "Content-Length": "200"}
        mock_resp.iter_content.return_value = [big_content]
        mock_resp.close = Mock()
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0027",
            dataset="education",
            source_id="source_a",
            profile_id="media.v1",
            target_url="https://example.edu/big.png",
            config_revision=1,
            config_snapshot={
                "urls": ["https://example.edu/big.png"],
                "allowed_domains": ["example.edu"],
                "allowed_mime_types": ["image/*"],
                "max_size_mb": 0,
            }
        )
        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any(e["code"] == "PLUGIN_EXECUTE_FAILED" for e in batch.errors)


# --- Raw Converter Tests ---

class TestRawConverter:

    def test_convert_legacy_list_dict(self):
        from converters.raw_converter import convert_to_raw_batch
        records = [
            {"name": "张三", "title": "教授", "profile_url": "https://example.edu/zhang.html"},
            {"name": "李四", "title": "副教授", "profile_url": "https://example.edu/li.html"},
        ]
        task_config = TaskConfigDTO(
            task_id="aabbccddeeff0011aabbccddeeff0028",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/faculty/list.htm",
            config_revision=1,
            config_snapshot={}
        )
        batch = convert_to_raw_batch(records, task_config)

        assert isinstance(batch, RawDataBatch)
        assert batch.schema_version == "1"
        assert batch.task_id == task_config.task_id
        assert len(batch.items) == 2
        assert all(item.assets for item in batch.items)
        assert all(asset.media_type == "text" for item in batch.items for asset in item.assets)

    def test_convert_raw_batch_pass_through(self):
        from converters.raw_converter import convert_to_raw_batch
        asset = MediaAsset(media_type="text", mime_type="text/html", data=b"<html>test</html>")
        dto = RawDataDTO(
            source_id="source_a",
            url="https://example.edu",
            content_type="text/html",
            encoding="utf-8",
            fetched_at="2024-01-01T00:00:00",
            trace={},
            assets=[asset]
        )
        batch = RawDataBatch(schema_version="1", task_id="test", items=[dto], pagination_complete=True)
        result = convert_to_raw_batch(batch)

        assert isinstance(result, RawDataBatch)
        assert result.task_id == batch.task_id
        assert len(result.items) == len(batch.items)
        assert result.items[0].url == batch.items[0].url

    def test_convert_legacy_raw_ref(self, tmp_path):
        from converters.raw_converter import RawConverter
        raw_dir = tmp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)
        test_file = raw_dir / "test.html"
        test_file.write_text("<html>test</html>", encoding="utf-8")

        converter = RawConverter(allowed_dirs=[raw_dir])
        dto = RawDataDTO(
            source_id="source_a",
            url="https://example.edu",
            content_type="text/html",
            encoding="utf-8",
            fetched_at="2024-01-01T00:00:00",
            trace={},
            raw_ref=str(test_file)
        )
        normalized = converter._convert_raw_ref_to_asset(dto)
        assert normalized.assets
        assert normalized.assets[0].media_type == "text"
        assert b"<html>test</html>" in normalized.assets[0].data

    def test_raw_ref_outside_allowed_dir_rejected(self, tmp_path):
        from converters.raw_converter import RawConverter
        outside_file = tmp_path / "outside.html"
        outside_file.write_text("<html>test</html>")

        converter = RawConverter(allowed_dirs=[tmp_path / "data" / "raw"])
        dto = RawDataDTO(
            source_id="source_a",
            url="https://example.edu",
            content_type="text/html",
            encoding="utf-8",
            fetched_at="2024-01-01T00:00:00",
            trace={},
            raw_ref=str(outside_file)
        )
        with pytest.raises(ValueError, match="outside allowed directories"):
            converter._convert_raw_ref_to_asset(dto)


# --- Fixture-based Integration Tests ---

@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures" / "raw_pages"


def test_static_html_with_fixture(fixture_dir, mock_session, mock_cache):
    fixture_file = fixture_dir / "w4_static_list_page.html"
    if not fixture_file.exists():
        pytest.skip("Fixture not available")

    html_content = fixture_file.read_text(encoding="utf-8")
    mock_session.get.return_value = _make_mock_response(text=html_content)

    plugin = StaticHtmlSpiderPlugin()
    task_config = TaskConfigDTO(
        task_id="aabbccddeeff0011aabbccddeeff0030",
        dataset="education",
        source_id="source_a",
        profile_id="faculty.v1",
        target_url="https://example.edu/list.htm",
        config_revision=1,
        config_snapshot={
            "list_url": "https://example.edu/list.htm",
            "selectors": {"item": "li.teacher a", "name": "title", "profile": "href"},
            "max_pages": 1
        }
    )
    context = MockContext(http_session=mock_session, cache=mock_cache)
    batch = plugin.execute(task_config, context)

    assert len(batch.items) >= 1
    assert batch.items[0].assets[0].data.decode("utf-8") == html_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
