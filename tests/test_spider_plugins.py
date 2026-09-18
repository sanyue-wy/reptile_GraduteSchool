# -*- coding: utf-8 -*-
"""
Tests for Spider Plugins (W4)
==============================
Offline fixture-based tests for all 6 spider plugins.
Uses mocked network responses and temporary directories.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

import pytest
import requests

# Import all spider plugins
from plugins.spiders.static_html.plugin import StaticHtmlSpiderPlugin
from plugins.spiders.ajax_api.plugin import AjaxApiSpiderPlugin
from plugins.spiders.js_render.plugin import JSRenderSpiderPlugin
from plugins.spiders.pdf_list.plugin import PDFListSpiderPlugin
from plugins.spiders.yzw_api.plugin import YzwApiSpiderPlugin
from plugins.spiders.media_downloader.plugin import MediaDownloaderSpiderPlugin

from contracts.task import TaskConfigDTO
from contracts.raw import RawDataBatch, RawDataDTO
from contracts.asset import MediaAsset


def _make_mock_response(text="", content=b"", headers=None, status_code=200):
    """Create a proper mock requests.Response."""
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
    """Mock PipelineContext for testing."""
    def __init__(self, http_session=None, cache=None, cancel_token=None):
        self.http = http_session
        self.cache = cache
        self.cancel_token = cancel_token


class MockCancelToken:
    """Mock cancellation token."""
    def __init__(self, cancelled=False):
        self._cancelled = cancelled

    def is_set(self):
        return self._cancelled


@pytest.fixture
def mock_session():
    """Create a mock PoliteSession."""
    session = Mock()
    session.get = Mock(return_value=_make_mock_response(text="<html><body>test</body></html>"))
    session.post = Mock(return_value=_make_mock_response(text='{"total": 0, "data": []}'))
    session.close = Mock()
    session.stats = {"requests": 0, "success": 0, "failed": 0, "raw_saved": 0}
    session.is_blocked = Mock(return_value=False)
    return session


@pytest.fixture
def mock_cache():
    """Create a mock CrawlCache."""
    cache = Mock()
    cache.get_or_fetch = Mock(side_effect=lambda fn, key, force=False: fn())
    cache.stats = {"hits": 0, "misses": 0, "writes": 0}
    return cache


@pytest.fixture
def task_config():
    """Create a sample TaskConfigDTO."""
    return TaskConfigDTO(
        task_id="test_task_123",
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


# --- Static HTML Plugin Tests ---

class TestStaticHtmlSpiderPlugin:
    """Tests for static_html spider plugin."""

    def test_plugin_metadata(self):
        """Verify plugin metadata loads correctly."""
        import json
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

    def test_execute_returns_raw_batch(self, mock_session, mock_cache, task_config):
        """Test execute returns RawDataBatch with proper structure."""
        plugin = StaticHtmlSpiderPlugin()

        # Mock HTML response
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
        assert len(batch.items) >= 1  # At least list page
        assert all(isinstance(item, RawDataDTO) for item in batch.items)
        assert all(item.assets for item in batch.items)
        assert all(asset.media_type == "text" for item in batch.items for asset in item.assets)

    def test_list_page_asset_has_html_content(self, mock_session, mock_cache, task_config):
        """Test that list page produces MediaAsset with HTML content."""
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
        """Test pagination respects max_pages limit."""
        task_config.config_snapshot["max_pages"] = 1
        plugin = StaticHtmlSpiderPlugin()
        # Use different HTML for list vs detail page
        list_html = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul><a class='next' href='page2.html'>Next</a></body></html>"
        detail_html = "<html><body><div class='teacher-detail'>Detail page</div></body></html>"

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            resp = Mock()
            if call_count[0] == 1:
                resp.text = list_html
            else:
                resp.text = detail_html
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.encoding = "utf-8"
            return resp

        mock_session.get.side_effect = mock_get

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        # Should fetch list page + 1 detail page, but NOT go to page 2
        assert mock_session.get.call_count == 2
        assert batch.pagination_complete is True

    def test_cancellation_stops_execution(self, mock_session, mock_cache, task_config):
        """Test cancellation token stops crawl."""
        plugin = StaticHtmlSpiderPlugin()
        html_content = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul></body></html>"
        mock_session.get.return_value.text = html_content

        cancel_token = MockCancelToken(cancelled=True)
        context = MockContext(http_session=mock_session, cache=mock_cache, cancel_token=cancel_token)
        batch = plugin.execute(task_config, context)

        assert any(e["code"] == "CANCELLED" for e in batch.errors)

    def test_network_error_produces_error_dto(self, mock_session, mock_cache, task_config):
        """Test network errors produce ErrorDTO with retryable=True."""
        from utils.http import BlockedError
        plugin = StaticHtmlSpiderPlugin()
        mock_session.get.side_effect = BlockedError("Rate limited")

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert len(batch.items) == 0
        assert any(e["code"] == "BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is True for e in batch.errors)

    def test_empty_list_page_returns_empty_batch(self, mock_session, mock_cache, task_config):
        """Test empty list page produces valid empty batch."""
        plugin = StaticHtmlSpiderPlugin()
        html_content = "<html><body><ul></ul></body></html>"
        mock_session.get.return_value.text = html_content

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert batch.pagination_complete is True
        # List page itself should still be in items
        assert len(batch.items) >= 1

    def test_detail_page_error_handled_gracefully(self, mock_session, mock_cache, task_config):
        """Test detail page errors don't stop the crawl."""
        from utils.http import BlockedError
        plugin = StaticHtmlSpiderPlugin()

        list_html = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul></body></html>"

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            resp = Mock()
            if call_count[0] == 1:
                resp.text = list_html
            else:
                raise BlockedError("Detail page blocked")
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.encoding = "utf-8"
            return resp

        mock_session.get.side_effect = mock_get

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        # List page should be in items, detail page error recorded
        assert len(batch.items) >= 1
        assert any(e["code"] == "BLOCKED" for e in batch.errors)

    def test_next_page_fallback_selectors(self, mock_session, mock_cache, task_config):
        """Test pagination uses fallback selectors when configured next_page not found."""
        plugin = StaticHtmlSpiderPlugin()
        task_config.config_snapshot["max_pages"] = 2
        task_config.config_snapshot["selectors"]["next_page"] = ".nonexistent"

        # Page 1 with fallback next link
        page1_html = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul><a class='next' href='/faculty/list_2.htm'>Next</a></body></html>"
        # Page 2 (no next link)
        page2_html = "<html><body><ul><li class='teacher'><a href='/faculty/li.html' title='李四'>李四</a></li></ul></body></html>"

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            resp = Mock()
            if call_count[0] == 1:
                resp.text = page1_html
            elif call_count[0] == 2:
                resp.text = page2_html
            else:
                resp.text = page2_html
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.encoding = "utf-8"
            return resp

        mock_session.get.side_effect = mock_get

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        # Should fetch page 1 and page 2, then stop (no next on page 2)
        assert mock_session.get.call_count >= 2
        assert batch.pagination_complete is True

    def test_retry_on_fetch_error(self, mock_session, mock_cache, task_config):
        """Test retry logic on fetch error."""
        from utils.http import BlockedError
        plugin = StaticHtmlSpiderPlugin()

        call_count = [0]
        def mock_get(*args, **kwargs):
            call_count[0] += 1
            resp = Mock()
            if call_count[0] == 1:
                raise BlockedError("First attempt failed")
            resp.text = "<html><body><ul><li class='teacher'><a href='/faculty/zhang.html' title='张三'>张三</a></li></ul></body></html>"
            resp.status_code = 200
            resp.headers = {"Content-Type": "text/html; charset=utf-8"}
            resp.encoding = "utf-8"
            return resp

        mock_session.get.side_effect = mock_get

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        # Should retry and succeed (1 fail + 1 retry + 1 detail = 3 calls)
        assert mock_session.get.call_count == 3
        assert len(batch.items) >= 1


# --- AJAX API Plugin Tests ---

class TestAjaxApiSpiderPlugin:
    """Tests for ajax_api spider plugin."""

    def test_plugin_metadata(self):
        """Verify plugin metadata."""
        import json
        meta_path = Path(__file__).parent.parent / "plugins/spiders/ajax_api/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "ajax_api"
        assert meta["plugin_type"] == "spider"

    def test_execute_returns_json_assets(self, mock_session, mock_cache):
        """Test execute returns RawDataBatch with JSON assets."""
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
            task_id="test_ajax_123",
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
        """Test pagination stops when all items fetched."""
        plugin = AjaxApiSpiderPlugin()

        # First page: total=3, page_size=2
        page1 = {"total": 3, "data": [{"title": "A"}, {"title": "B"}]}
        page2 = {"total": 3, "data": [{"title": "C"}]}

        mock_resp1 = Mock()
        mock_resp1.text = json.dumps(page1)
        mock_resp2 = Mock()
        mock_resp2.text = json.dumps(page2)
        mock_session.post.side_effect = [mock_resp1, mock_resp2]

        task_config = TaskConfigDTO(
            task_id="test_ajax_456",
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

        # Should fetch 2 pages (page_size=2, total=3)
        assert mock_session.post.call_count == 2
        assert batch.pagination_complete is True

    def test_network_error_produces_error_dto(self, mock_session, mock_cache):
        """Test network errors produce ErrorDTO with retryable=True."""
        from utils.http import BlockedError
        plugin = AjaxApiSpiderPlugin()
        mock_session.post.side_effect = BlockedError("Rate limited")

        task_config = TaskConfigDTO(
            task_id="test_ajax_err",
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
        assert any(e["code"] == "BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is True for e in batch.errors)

    def test_empty_api_response_returns_empty_batch(self, mock_session, mock_cache):
        """Test empty API response produces valid batch."""
        plugin = AjaxApiSpiderPlugin()
        api_response = {"total": 0, "data": []}
        mock_resp = Mock()
        mock_resp.text = json.dumps(api_response)
        mock_resp.json.return_value = api_response
        mock_session.post.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="test_ajax_empty",
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
        assert len(batch.items) >= 1  # First page fetched


# --- JS Render Plugin Tests ---

class TestJSRenderSpiderPlugin:
    """Tests for js_render spider plugin."""

    def test_plugin_metadata(self):
        """Verify plugin metadata."""
        import json
        meta_path = Path(__file__).parent.parent / "plugins/spiders/js_render/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "js_render"
        assert meta["plugin_type"] == "spider"
        assert "playwright" in meta.get("optional_dependencies", [])

    def test_precheck_reports_dependency_status(self):
        """Test precheck reports Playwright availability."""
        plugin = JSRenderSpiderPlugin()
        ok, err = plugin.precheck()
        # Result depends on whether playwright is installed in test env
        assert isinstance(ok, bool)
        if not ok:
            assert "Playwright not installed" in err

    def test_execute_raises_without_playwright(self, mock_session, mock_cache, task_config):
        """Test execute raises DependencyError when Playwright not available."""
        plugin = JSRenderSpiderPlugin()

        # Mock precheck to fail
        with patch.object(plugin, 'precheck', return_value=(False, "Playwright not installed")):
            context = MockContext(http_session=mock_session, cache=mock_cache)
            with pytest.raises(JSRenderSpiderPlugin.DependencyError):
                plugin.execute(task_config, context)


# --- PDF List Plugin Tests ---

class TestPDFListSpiderPlugin:
    """Tests for pdf_list spider plugin."""

    def test_plugin_metadata(self):
        """Verify plugin metadata."""
        import json
        meta_path = Path(__file__).parent.parent / "plugins/spiders/pdf_list/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "pdf_list"
        assert meta["plugin_type"] == "spider"
        assert "pdfplumber" in meta.get("dependencies", [])

    def test_execute_returns_pdf_asset(self, mock_session, mock_cache):
        """Test execute returns RawDataBatch with PDF document asset."""
        plugin = PDFListSpiderPlugin()

        # Mock PDF content
        pdf_content = b"%PDF-1.4\nfake pdf content"
        mock_resp = Mock()
        mock_resp.content = pdf_content
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="test_pdf_123",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/faculty/list.pdf",
            config_revision=1,
            config_snapshot={
                "pdf_url": "https://example.edu/faculty/list.pdf"
            }
        )

        context = MockContext(http_session=mock_session, cache=mock_cache)
        batch = plugin.execute(task_config, context)

        assert isinstance(batch, RawDataBatch)
        assert len(batch.items) == 1
        assert batch.items[0].assets[0].media_type == "document"
        assert batch.items[0].assets[0].mime_type == "application/pdf"
        assert batch.items[0].assets[0].data == pdf_content

    def test_network_error_produces_error_dto(self, mock_session, mock_cache):
        """Test network errors produce ErrorDTO with retryable=True."""
        from utils.http import BlockedError
        plugin = PDFListSpiderPlugin()
        mock_session.get.side_effect = BlockedError("Rate limited")

        task_config = TaskConfigDTO(
            task_id="test_pdf_err",
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
        assert any(e["code"] == "BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is True for e in batch.errors)

    def test_cancellation_stops_execution(self, mock_session, mock_cache):
        """Test cancellation token stops crawl."""
        plugin = PDFListSpiderPlugin()
        cancel_token = MockCancelToken(cancelled=True)

        task_config = TaskConfigDTO(
            task_id="test_pdf_cancel",
            dataset="education",
            source_id="source_a",
            profile_id="faculty.v1",
            target_url="https://example.edu/faculty/list.pdf",
            config_revision=1,
            config_snapshot={"pdf_url": "https://example.edu/faculty/list.pdf"}
        )

        context = MockContext(http_session=mock_session, cache=mock_cache, cancel_token=cancel_token)
        batch = plugin.execute(task_config, context)

        assert any(e["code"] == "CANCELLED" for e in batch.errors)


# --- YZW API Plugin Tests ---

class TestYzwApiSpiderPlugin:
    """Tests for yzw_api spider plugin."""

    def test_plugin_metadata(self):
        """Verify plugin metadata."""
        import json
        meta_path = Path(__file__).parent.parent / "plugins/spiders/yzw_api/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "yzw_api"
        assert meta["plugin_type"] == "spider"

    def test_execute_returns_json_assets(self, mock_session, mock_cache):
        """Test execute returns RawDataBatch with JSON assets for each discipline."""
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
            task_id="test_yzw_123",
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
        """Test network errors produce ErrorDTO with retryable=True."""
        from utils.http import BlockedError
        plugin = YzwApiSpiderPlugin()
        mock_session.post.side_effect = BlockedError("Rate limited")

        task_config = TaskConfigDTO(
            task_id="test_yzw_err",
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
        assert any(e["code"] == "BLOCKED" for e in batch.errors)
        assert any(e["retryable"] is True for e in batch.errors)

    def test_cancellation_stops_execution(self, mock_session, mock_cache):
        """Test cancellation token stops crawl."""
        plugin = YzwApiSpiderPlugin()
        cancel_token = MockCancelToken(cancelled=True)

        task_config = TaskConfigDTO(
            task_id="test_yzw_cancel",
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

        assert any(e["code"] == "CANCELLED" for e in batch.errors)

    def test_pagination_multiple_pages(self, mock_session, mock_cache):
        """Test pagination fetches multiple pages."""
        plugin = YzwApiSpiderPlugin()

        # First page: total=3, page_size=2
        page1 = {"total": 3, "data": [{"zydm": "080200"}, {"zydm": "080201"}]}
        page2 = {"total": 3, "data": [{"zydm": "080202"}]}

        mock_resp1 = Mock()
        mock_resp1.text = json.dumps(page1)
        mock_resp2 = Mock()
        mock_resp2.text = json.dumps(page2)
        # Use side_effect that returns responses indefinitely
        mock_session.post.side_effect = [mock_resp1, mock_resp2, mock_resp2, mock_resp2]

        task_config = TaskConfigDTO(
            task_id="test_yzw_page",
            dataset="education",
            source_id="source_b",
            profile_id="major.v1",
            target_url="https://yz.chsi.com.cn",
            config_revision=1,
            config_snapshot={
                "school_code": "10213",
                "year": 2026,
                "major_codes": ["080200", "080201", "080202"],  # Use major_codes directly to avoid config lookup
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
    """Tests for media_downloader spider plugin."""

    def test_plugin_metadata(self):
        """Verify plugin metadata."""
        import json
        meta_path = Path(__file__).parent.parent / "plugins/spiders/media_downloader/metadata.json"
        assert meta_path.exists()
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["name"] == "media_downloader"
        assert meta["plugin_type"] == "spider"
        assert "required" in meta["config_schema"]
        assert "urls" in meta["config_schema"]["required"]

    def test_execute_downloads_images(self, mock_session, mock_cache):
        """Test downloading image URLs."""
        plugin = MediaDownloaderSpiderPlugin()

        # Mock image response
        img_content = b"fake png content"
        mock_resp = Mock()
        mock_resp.headers = {"Content-Type": "image/png", "Content-Length": str(len(img_content))}
        mock_resp.iter_content.return_value = [img_content]
        mock_resp.close = Mock()
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="test_media_123",
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
        """Test domain whitelist rejects non-allowed domains."""
        plugin = MediaDownloaderSpiderPlugin()

        task_config = TaskConfigDTO(
            task_id="test_media_456",
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
        assert any(e["code"] == "DOMAIN_NOT_ALLOWED" for e in batch.errors)

    def test_mime_type_filter(self, mock_session, mock_cache):
        """Test MIME type filtering."""
        plugin = MediaDownloaderSpiderPlugin()

        mock_resp = Mock()
        mock_resp.headers = {"Content-Type": "application/x-executable", "Content-Length": "100"}
        mock_resp.iter_content.return_value = [b"x" * 100]
        mock_resp.close = Mock()
        mock_session.get.return_value = mock_resp

        task_config = TaskConfigDTO(
            task_id="test_media_789",
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
        assert any(e["code"] == "MIME_NOT_ALLOWED" for e in batch.errors)

    def test_network_error_produces_error_dto(self, mock_session, mock_cache):
        """Test network errors produce ErrorDTO with retryable=True."""
        import requests
        plugin = MediaDownloaderSpiderPlugin()
        mock_session.get.side_effect = requests.Timeout("Connection timeout")

        task_config = TaskConfigDTO(
            task_id="test_media_err",
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
        assert any(e["code"] == "TIMEOUT" for e in batch.errors)
        assert any(e["retryable"] is True for e in batch.errors)

    def test_cancellation_stops_execution(self, mock_session, mock_cache):
        """Test cancellation token stops crawl."""
        plugin = MediaDownloaderSpiderPlugin()
        cancel_token = MockCancelToken(cancelled=True)

        task_config = TaskConfigDTO(
            task_id="test_media_cancel",
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

        assert any(e["code"] == "CANCELLED" for e in batch.errors)

    def test_multiple_urls_downloaded(self, mock_session, mock_cache):
        """Test multiple URLs are downloaded."""
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
            task_id="test_media_multi",
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


# --- Raw Converter Tests ---

class TestRawConverter:
    """Tests for raw_converter.py."""

    def test_convert_legacy_list_dict(self):
        """Test converting legacy list[dict] to RawDataBatch."""
        from converters.raw_converter import convert_to_raw_batch

        records = [
            {"name": "张三", "title": "教授", "profile_url": "https://example.edu/zhang.html"},
            {"name": "李四", "title": "副教授", "profile_url": "https://example.edu/li.html"},
        ]

        task_config = TaskConfigDTO(
            task_id="test_convert_123",
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
        """Test RawDataBatch passes through with validation."""
        from converters.raw_converter import convert_to_raw_batch

        # Create a valid RawDataBatch
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
        # Should return equivalent batch (validation normalizes)
        assert isinstance(result, RawDataBatch)
        assert result.task_id == batch.task_id
        assert len(result.items) == len(batch.items)
        assert result.items[0].url == batch.items[0].url

    def test_convert_legacy_raw_ref(self, tmp_path):
        """Test converting legacy raw_ref file path."""
        from converters.raw_converter import RawConverter

        # Create a test file in allowed directory
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
        """Test raw_ref outside allowed directories is rejected."""
        from converters.raw_converter import RawConverter

        # Create file outside allowed dirs
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
    """Path to test fixtures."""
    return Path(__file__).parent / "fixtures" / "raw_pages"


def test_static_html_with_fixture(fixture_dir, mock_session, mock_cache):
    """Test static_html plugin with real fixture HTML."""
    fixture_file = fixture_dir / "w4_static_list_page.html"
    if not fixture_file.exists():
        pytest.skip("Fixture not available")

    html_content = fixture_file.read_text(encoding="utf-8")
    mock_session.get.return_value = _make_mock_response(text=html_content)

    plugin = StaticHtmlSpiderPlugin()
    task_config = TaskConfigDTO(
        task_id="fixture_test",
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