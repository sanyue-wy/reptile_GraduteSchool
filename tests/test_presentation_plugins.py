# -*- coding: utf-8 -*-
"""
Tests for Presentation Plugins (W7)
====================================
Covers all 5 built-in presenters:
  - html_presenter
  - text_presenter (text + markdown modes)
  - jsonl_presenter
  - csv_presenter
  - pdf_presenter (skips if WeasyPrint missing)

Each presenter: normal render, empty records, field selection, output path.
Uses temporary directories and mocked contexts.
"""

import csv
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, PropertyMock
from uuid import uuid4

import pytest

from contracts.output import PresentationRequest, RenderedOutputDTO
from contracts.asset import MediaAsset


# ─── Fixtures ─────────────────────────────────────────────────────────────


def _make_presentation_request(
    records=None,
    output_spec=None,
    dataset="test_dataset",
    schema_id="education.tutor.v1",
):
    """Build a PresentationRequest with sensible defaults."""
    if records is None:
        records = [
            {"name": "Alice", "title": "Professor", "university": "TestU"},
            {"name": "Bob", "title": "Associate Prof", "university": "TestU"},
            {"name": "Charlie", "title": "Lecturer", "university": "OtherU"},
        ]
    return PresentationRequest(
        request_id=uuid4().hex,
        dataset=dataset,
        schema_id=schema_id,
        output_spec=output_spec or {},
        records=records,
        stats={"total": len(records)},
    )


class MockContext:
    """Minimal mock PluginContext for presenter tests."""

    def __init__(self, tmp_path=None):
        self.config_snapshot = {"plugins": {}}
        self.storage = MagicMock()
        self.logger = Mock()
        self.task_id = uuid4().hex
        self.run_id = uuid4().hex
        self.allowed_paths = [str(tmp_path)] if tmp_path else []
        if tmp_path:
            ws = MagicMock()
            ws.get_store_path = lambda ds, ext: str(Path(tmp_path) / f"{ds}{ext}")
            self.storage.workspace = ws


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def mock_ctx(tmp_dir):
    return MockContext(tmp_path=tmp_dir)


# ─── Text Presenter ───────────────────────────────────────────────────────


class TestTextPresenter:
    def test_text_mode(self, tmp_dir, mock_ctx):
        from plugins.presenters.text_presenter.plugin import TextPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["text_presenter"] = {"mode": "text", "output_dir": str(tmp_dir)}
        p = TextPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        assert isinstance(result, RenderedOutputDTO)
        assert result.output_format == "text"
        assert Path(result.path).exists()
        content = Path(result.path).read_text(encoding="utf-8")
        assert "Alice" in content
        assert "TestU" in content

    def test_markdown_mode(self, tmp_dir, mock_ctx):
        from plugins.presenters.text_presenter.plugin import TextPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["text_presenter"] = {"mode": "markdown", "output_dir": str(tmp_dir)}
        p = TextPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        assert result.output_format == "markdown"
        content = Path(result.path).read_text(encoding="utf-8")
        assert "| name |" in content or "| name" in content
        assert "---" in content

    def test_empty_records(self, tmp_dir, mock_ctx):
        from plugins.presenters.text_presenter.plugin import TextPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["text_presenter"] = {"output_dir": str(tmp_dir)}
        p = TextPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(records=[])
        result = p.render(req, mock_ctx)
        assert Path(result.path).exists()
        content = Path(result.path).read_text(encoding="utf-8")
        assert "No records" in content


# ─── CSV Presenter ────────────────────────────────────────────────────────


class TestCsvPresenter:
    def test_csv_output(self, tmp_dir, mock_ctx):
        from plugins.presenters.csv_presenter.plugin import CsvPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["csv_presenter"] = {"output_dir": str(tmp_dir)}
        p = CsvPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        assert result.output_format == "csv"
        assert Path(result.path).exists()

        with open(result.path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3
        assert rows[0]["name"] == "Alice"

    def test_field_selection(self, tmp_dir, mock_ctx):
        from plugins.presenters.csv_presenter.plugin import CsvPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["csv_presenter"] = {"output_dir": str(tmp_dir)}
        p = CsvPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(output_spec={"field_selection": ["name", "title"]})
        result = p.render(req, mock_ctx)

        with open(result.path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert "name" in rows[0]
        assert "title" in rows[0]
        assert "university" not in rows[0]

    def test_empty_records(self, tmp_dir, mock_ctx):
        from plugins.presenters.csv_presenter.plugin import CsvPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["csv_presenter"] = {"output_dir": str(tmp_dir)}
        p = CsvPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(records=[])
        result = p.render(req, mock_ctx)
        assert Path(result.path).exists()


# ─── JSONL Presenter ─────────────────────────────────────────────────────


class TestJsonlPresenter:
    def test_jsonl_output(self, tmp_dir, mock_ctx):
        from plugins.presenters.jsonl_presenter.plugin import JsonlPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["jsonl_presenter"] = {"output_dir": str(tmp_dir)}
        p = JsonlPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        # render() returns a path string for jsonl_presenter
        path = Path(result) if isinstance(result, str) else Path(result.path)
        assert path.exists()

        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 3
        first = json.loads(lines[0])
        assert first["name"] == "Alice"

    def test_include_fields(self, tmp_dir, mock_ctx):
        from plugins.presenters.jsonl_presenter.plugin import JsonlPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["jsonl_presenter"] = {"output_dir": str(tmp_dir)}
        p = JsonlPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(output_spec={"include_fields": ["name"]})
        result = p.render(req, mock_ctx)

        path = Path(result) if isinstance(result, str) else Path(result.path)
        first = json.loads(path.read_text(encoding="utf-8").strip().split("\n")[0])
        assert "name" in first
        assert "title" not in first


# ─── HTML Presenter ───────────────────────────────────────────────────────


class TestHtmlPresenter:
    def test_basic_html_output(self, tmp_dir, mock_ctx):
        from plugins.presenters.html_presenter.plugin import HtmlPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["html_presenter"] = {"output_dir": str(tmp_dir)}
        p = HtmlPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        assert isinstance(result, RenderedOutputDTO)
        assert result.output_format == "html"
        assert Path(result.path).exists()

        content = Path(result.path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Alice" in content
        assert "theme-switcher" in content or "theme-toggle" in content
        # CSP meta tag
        assert "Content-Security-Policy" in content

    def test_html_with_template(self, tmp_dir, mock_ctx):
        """Test HTML presenter loads template from registry."""
        from plugins.presenters.html_presenter.plugin import HtmlPresenterPlugin

        # Create a minimal template
        tmpl_dir = tmp_dir / "templates" / "test-tmpl"
        tmpl_dir.mkdir(parents=True)
        (tmpl_dir / "layout.html").write_text("{{ header }}\n{{ content }}", encoding="utf-8")
        (tmpl_dir / "style.css").write_text("body { margin: 0; }", encoding="utf-8")
        (tmpl_dir / "variables.json").write_text('{"color-primary": "#000"}', encoding="utf-8")
        (tmpl_dir / "preview.png").write_bytes(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 20  # minimal PNG-like header
        )

        mock_ctx.config_snapshot["plugins"]["html_presenter"] = {
            "output_dir": str(tmp_dir / "output"),
            "template": "test-tmpl",
        }
        p = HtmlPresenterPlugin()
        # Override template dir to use our test templates
        p._template_dir = tmp_dir / "templates"
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        assert Path(result.path).exists()
        content = Path(result.path).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_html_empty_records(self, tmp_dir, mock_ctx):
        from plugins.presenters.html_presenter.plugin import HtmlPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["html_presenter"] = {"output_dir": str(tmp_dir)}
        p = HtmlPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(records=[])
        result = p.render(req, mock_ctx)
        assert Path(result.path).exists()
        content = Path(result.path).read_text(encoding="utf-8")
        assert "No records" in content

    def test_html_xss_protection(self, tmp_dir, mock_ctx):
        """Ensure user data containing script tags is escaped."""
        from plugins.presenters.html_presenter.plugin import HtmlPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["html_presenter"] = {"output_dir": str(tmp_dir)}
        p = HtmlPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(
            records=[{"name": "<script>alert(1)</script>", "title": "Test"}]
        )
        result = p.render(req, mock_ctx)
        content = Path(result.path).read_text(encoding="utf-8")

        # Raw script tag must NOT appear in output
        assert "<script>alert(1)</script>" not in content
        # Escaped version should be present
        assert "&lt;script&gt;" in content or "alert(1)" not in content

    def test_theme_switcher_present(self, tmp_dir, mock_ctx):
        """Verify ThemeSwitcher JS is embedded."""
        from plugins.presenters.html_presenter.plugin import HtmlPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["html_presenter"] = {"output_dir": str(tmp_dir)}
        p = HtmlPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)
        content = Path(result.path).read_text(encoding="utf-8")

        assert "theme-toggle-btn" in content
        assert "cycleTheme" in content or "THEMES" in content

    def test_register_renderer(self):
        """Test renderer registration mechanism."""
        from plugins.presenters.html_presenter.plugin import register_renderer, get_renderer, list_renderers

        register_renderer("test_renderer", lambda req: "<div>test</div>")
        assert get_renderer("test_renderer") is not None
        assert "test_renderer" in list_renderers()


# ─── Markdown Presenter ─────────────────────────────────────────────────


class TestMarkdownPresenter:
    def test_table_mode(self, tmp_dir, mock_ctx):
        from plugins.presenters.markdown_presenter.plugin import MarkdownPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["markdown_presenter"] = {"mode": "table", "output_dir": str(tmp_dir)}
        p = MarkdownPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        assert isinstance(result, RenderedOutputDTO)
        assert result.output_format == "markdown"
        assert Path(result.path).exists()
        content = Path(result.path).read_text(encoding="utf-8")
        assert "| name |" in content or "| name" in content
        assert "---" in content
        assert "Alice" in content

    def test_list_mode(self, tmp_dir, mock_ctx):
        from plugins.presenters.markdown_presenter.plugin import MarkdownPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["markdown_presenter"] = {"mode": "list", "output_dir": str(tmp_dir)}
        p = MarkdownPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        content = Path(result.path).read_text(encoding="utf-8")
        assert "## Record 1" in content
        assert "- **name:** Alice" in content

    def test_empty_records(self, tmp_dir, mock_ctx):
        from plugins.presenters.markdown_presenter.plugin import MarkdownPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["markdown_presenter"] = {"output_dir": str(tmp_dir)}
        p = MarkdownPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(records=[])
        result = p.render(req, mock_ctx)

        assert result.output_format == "markdown"
        content = Path(result.path).read_text(encoding="utf-8")
        assert "No records" in content

    def test_field_selection(self, tmp_dir, mock_ctx):
        from plugins.presenters.markdown_presenter.plugin import MarkdownPresenterPlugin

        mock_ctx.config_snapshot["plugins"]["markdown_presenter"] = {"output_dir": str(tmp_dir)}
        p = MarkdownPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(output_spec={"include_fields": ["name", "title"]})
        result = p.render(req, mock_ctx)

        content = Path(result.path).read_text(encoding="utf-8")
        assert "name" in content
        assert "university" not in content

    def test_plugin_attributes(self):
        from plugins.presenters.markdown_presenter.plugin import MarkdownPresenterPlugin

        p = MarkdownPresenterPlugin()
        assert p.name == "markdown_presenter"
        assert p.plugin_type == "presenter"
        assert p.version == "1.0.0"
        assert p.output_format == "markdown"


# ─── PDF Presenter ────────────────────────────────────────────────────────


class TestPdfPresenter:
    def test_pdf_output_or_skip(self, tmp_dir, mock_ctx):
        """Test PDF generation if WeasyPrint available, else skip."""
        from plugins.presenters.pdf_presenter.plugin import PdfPresenterPlugin, _WEASYPRINT_AVAILABLE

        if not _WEASYPRINT_AVAILABLE:
            pytest.skip("WeasyPrint not installed")

        mock_ctx.config_snapshot["plugins"]["pdf_presenter"] = {"output_dir": str(tmp_dir)}
        p = PdfPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request()
        result = p.render(req, mock_ctx)

        assert isinstance(result, RenderedOutputDTO)
        assert result.output_format == "pdf"
        assert Path(result.path).exists()
        assert Path(result.path).stat().st_size > 0

    def test_pdf_precheck_missing_dep(self):
        """Test precheck reports missing dependency."""
        from plugins.presenters.pdf_presenter.plugin import PdfPresenterPlugin, _WEASYPRINT_AVAILABLE

        p = PdfPresenterPlugin()
        ok, msg = p.precheck()
        if _WEASYPRINT_AVAILABLE:
            assert ok is True
        else:
            assert ok is False
            assert "WeasyPrint" in msg

    def test_pdf_xss_escape(self, tmp_dir, mock_ctx):
        """Verify _generate_html escapes <script> payloads into HTML entities."""
        from plugins.presenters.pdf_presenter.plugin import PdfPresenterPlugin

        xss_payload = "<script>alert(1)</script>"
        records = [{"name": xss_payload, "title": '"><img src=x>'}]
        mock_ctx.config_snapshot["plugins"]["pdf_presenter"] = {"output_dir": str(tmp_dir)}
        p = PdfPresenterPlugin()
        p.setup(mock_ctx)
        req = _make_presentation_request(records=records)
        html = p._generate_html(req)

        # Raw payloads must NOT appear unescaped
        assert "<script>" not in html
        assert "<img" not in html

        # Properly escaped entities MUST appear
        assert "&lt;script&gt;" in html
        assert "&quot;&gt;" in html


# ─── Base Presenter Helper ────────────────────────────────────────────────


class TestBasePresenterHelper:
    def test_prepare_records_field_selection(self):
        from plugins.presenters.base_presenter import BasePresenterHelper

        req = _make_presentation_request(
            output_spec={"field_selection": ["name", "title"]},
        )
        records, fields = BasePresenterHelper.prepare_records(req)
        assert fields == ["name", "title"]
        assert "name" in records[0]
        assert "university" not in records[0]

    def test_prepare_records_exclude(self):
        from plugins.presenters.base_presenter import BasePresenterHelper

        req = _make_presentation_request(
            output_spec={"exclude_fields": ["university"]},
        )
        records, fields = BasePresenterHelper.prepare_records(req)
        assert "university" not in fields

    def test_prepare_records_empty(self):
        from plugins.presenters.base_presenter import BasePresenterHelper

        req = _make_presentation_request(records=[])
        records, fields = BasePresenterHelper.prepare_records(req)
        assert records == []
        assert fields == []

    def test_atomic_write(self, tmp_dir):
        from plugins.presenters.base_presenter import BasePresenterHelper

        path = tmp_dir / "test.txt"
        n = BasePresenterHelper.atomic_write_text(path, "hello world")
        assert path.read_text(encoding="utf-8") == "hello world"
        assert n > 0

    def test_make_rendered_output(self, tmp_dir):
        from plugins.presenters.base_presenter import BasePresenterHelper

        path = tmp_dir / "out.html"
        dto = BasePresenterHelper.make_rendered_output("html", path, {"size": 100})
        assert dto.output_format == "html"
        assert dto.metadata["size"] == 100


# ─── All presenter plugin attributes ─────────────────────────────────────


class TestPresenterPluginAttributes:
    """Verify all presenters have correct plugin attributes."""

    @pytest.mark.parametrize(
        "module_path,class_name",
        [
            ("plugins.presenters.html_presenter.plugin", "HtmlPresenterPlugin"),
            ("plugins.presenters.text_presenter.plugin", "TextPresenterPlugin"),
            ("plugins.presenters.csv_presenter.plugin", "CsvPresenterPlugin"),
            ("plugins.presenters.jsonl_presenter.plugin", "JsonlPresenterPlugin"),
            ("plugins.presenters.markdown_presenter.plugin", "MarkdownPresenterPlugin"),
            ("plugins.presenters.pdf_presenter.plugin", "PdfPresenterPlugin"),
        ],
    )
    def test_plugin_attributes(self, module_path, class_name):
        import importlib

        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        p = cls()
        assert p.plugin_type == "presenter"
        assert p.input_schema == "PresentationRequest.v1"
        assert p.output_schema == "RenderedOutputDTO.v1"
        assert p.name
        assert p.version
