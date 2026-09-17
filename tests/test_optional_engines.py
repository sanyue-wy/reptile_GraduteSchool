"""Optional-dependency engines (js_render, pdf_list) driven through fake modules."""
import base64
import sys
import types

import pytest


@pytest.fixture
def fake_pdfplumber(monkeypatch):
    """Minimal pdfplumber fake serving fixed pages through the real parser."""
    module = types.ModuleType("pdfplumber")

    class Page:
        def __init__(self, tables, text):
            self._tables, self._text = tables, text

        def extract_tables(self):
            return self._tables

        def extract_text(self):
            return self._text

    pages = [
        Page([[["姓名", "职称", "研究方向"], ["张三", "教授", "机器人; 智能制造"],
               ["", "", ""], ["李四", "副教授", "控制"]]], None),
        Page([], "王五 教授\n\n赵六 副教授"),
    ]
    opened = []

    class Pdf:
        def __init__(self):
            self.pages = pages

        def __enter__(self):
            opened.append(self)
            return self

        def __exit__(self, *args):
            return False

    module.open = lambda source: Pdf()
    monkeypatch.setitem(sys.modules, "pdfplumber", module)
    return pages, opened


@pytest.fixture
def fake_playwright(monkeypatch):
    """Playwright fake capturing goto/wait calls and returning rendered HTML."""
    module = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    rendered = {"html": "<ul class='faculty-list'><li><a href='/t/1' title='张三'>张三</a></li></ul>", "count": 0}
    calls = []

    class Page:
        def goto(self, url, timeout=None, wait_until=None):
            calls.append(("goto", url, timeout, wait_until))

        def wait_for_selector(self, selector, timeout=None):
            calls.append(("wait", selector, timeout))
            if selector == "table":
                raise RuntimeError("selector never appears")

        def content(self):
            rendered["count"] += 1
            return rendered["html"]

    class Browser:
        def new_page(self):
            return Page()

        def close(self):
            calls.append(("close",))

    class Chromium:
        def launch(self, headless=None):
            return Browser()

    class Manager:
        chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    sync_api.sync_playwright = lambda: Manager()
    module.sync_api = sync_api
    monkeypatch.setitem(sys.modules, "playwright", module)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    return rendered, calls


class TestJsRenderEngine:
    def test_fetch_uses_fake_playwright_and_default_wait(self, fake_playwright, mock_session, mock_cache):
        from spiders.js_render import JSRenderEngine
        rendered, calls = fake_playwright
        engine = JSRenderEngine(mock_session, mock_cache)
        records = engine.fetch("https://offline.invalid/list", selectors={"item": "li a", "name": "title"})
        assert [r["name"] for r in records] == ["张三"]
        assert ("close",) in calls and rendered["count"] == 1
        assert any(entry[:2] == ("wait", ".faculty-list") for entry in calls)

    def test_fetch_explicit_wait_selector_and_custom_parse(self, fake_playwright, mock_session):
        from spiders.js_render import JSRenderEngine
        rendered, calls = fake_playwright
        rendered["html"] = "<div class='teacher-item'><a href='/t/2' title='李四'>李四</a></div>"
        engine = JSRenderEngine(mock_session)
        records = engine.fetch("https://offline.invalid/spa", selectors={"item": ".teacher-item a", "name": "title"}, wait_selector=".teacher-item")
        assert records[0]["name"] == "李四"
        assert ("wait", ".teacher-item", 10000) in calls

    def test_wait_failure_falls_through_and_parse_standalone(self, fake_playwright, mock_session):
        from spiders.js_render import JSRenderEngine
        rendered, calls = fake_playwright
        rendered["html"] = "<table><tr><td><a href='/t/3' title='王五'>王五</a></td></tr></table>"
        engine = JSRenderEngine(mock_session)
        records = engine.fetch("https://offline.invalid/fallback", selectors={"item": "table td a", "name": "title"})
        assert records[0]["name"] == "王五"
        parsed = engine.parse("<ul><li><a href='/t/4' title='孙七'>孙七</a></li></ul>",
                              {"list_item_selector": "li a", "list_name_selector": "title"},
                              url="https://offline.invalid/x")
        assert parsed[0]["name"] == "孙七"

    def test_playwright_with_detail_enriches_records(self, fake_playwright, mock_session, mock_cache, monkeypatch):
        import spiders.js_render as js
        monkeypatch.setattr("spiders.detail_parser.fetch_detail", lambda session, url, detail_type, selectors, cache, force:
                            {"title": "教授", "profile_url": url})
        records = js.fetch_faculty_via_playwright_with_detail(
            mock_session, "https://offline.invalid/list", {"item": "li a", "name": "title"},
            cache=mock_cache, force=True)
        assert records[0]["name"] == "张三" and records[0]["title"] == "教授"
        # Detail failure keeps the base record instead of crashing the batch.
        def broken(*args, **kwargs):
            raise RuntimeError("offline")
        monkeypatch.setattr("spiders.detail_parser.fetch_detail", broken)
        records = js.fetch_faculty_via_playwright_with_detail(
            mock_session, "https://offline.invalid/list", {"item": "li a", "name": "title"}, cache=mock_cache)
        assert records[0]["name"] == "张三" and records[0].get("title") is None


class TestPdfListEngine:
    def test_fetch_network_parse_table_and_dedup(self, fake_pdfplumber, mock_session):
        from spiders.pdf_list import PDFListEngine
        engine = PDFListEngine(mock_session)
        response = types.SimpleNamespace(content=b"%PDF-1.4 fake")
        mock_session.get.return_value = response
        records = engine.fetch("https://offline.invalid/list.pdf")
        assert [r["name"] for r in records] == ["张三", "李四", "王五", "赵六"]
        assert records[0]["title"] == "教授"
        assert records[0]["research_areas"] == ["机器人", "智能制造"]

    def test_cache_roundtrip_base64(self, fake_pdfplumber, mock_session, mock_cache):
        from spiders.pdf_list import PDFListEngine
        engine = PDFListEngine(mock_session, mock_cache)
        mock_session.get.return_value = types.SimpleNamespace(content=b"%PDF-fake-bytes")
        assert engine.fetch("https://offline.invalid/a.pdf", force=True) == engine.fetch("https://offline.invalid/a.pdf")
        assert mock_session.get.call_count == 1
        cached = mock_cache.get_or_fetch(lambda: "", "pdf_list:base64:v1:https://offline.invalid/a.pdf")
        assert base64.b64decode(cached) == b"%PDF-fake-bytes"

    def test_parse_accepts_bytes_directly(self, fake_pdfplumber, mock_session):
        from spiders.pdf_list import PDFListEngine
        assert PDFListEngine(mock_session).parse(b"%PDF-x", {})[0]["name"] == "张三"

    def test_local_file_helper(self, fake_pdfplumber, tmp_path):
        from spiders.pdf_list import parse_pdf_file_local
        path = tmp_path / "local.pdf"
        path.write_bytes(b"%PDF-local")
        assert [r["name"] for r in parse_pdf_file_local(object(), str(path))] == ["张三", "李四", "王五", "赵六"]
