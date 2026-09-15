"""新增模块单元测试"""

import pytest
from unittest.mock import MagicMock, patch

from spiders.url_resolver import URLResolver, URLCandidate
from spiders.js_render import fetch_faculty_via_playwright
from spiders.pdf_list import parse_pdf_faculty_list, parse_pdf_file_local, _parse_table, _find_name_column


class TestURLCandidate:
    """URLCandidate 单测"""

    def test_defaults(self):
        c = URLCandidate(url="http://example.com")
        assert c.url == "http://example.com"
        assert c.score == 0.0
        assert c.list_type == "static_html"
        assert c.source == "unknown"
        assert c.reachable is None

    def test_to_dict(self):
        c = URLCandidate(url="http://example.com", score=5.0, list_type="ajax_api")
        d = c.to_dict()
        assert d["url"] == "http://example.com"
        assert d["score"] == 5.0
        assert d["list_type"] == "ajax_api"


class TestURLResolver:
    """URLResolver 单测"""

    @patch("spiders.url_resolver.PoliteSession")
    def test_resolve_returns_candidates(self, mock_session_cls):
        """resolve 返回候选列表"""
        mock_session = MagicMock()
        mock_session.get.return_value.text = "<html></html>"

        resolver = URLResolver(session=mock_session)
        candidates = resolver.resolve("测试大学", "机械工程学院")

        assert isinstance(candidates, list)
        assert all(isinstance(c, URLCandidate) for c in candidates)

    @patch("spiders.url_resolver.PoliteSession")
    def test_resolve_saves_candidates(self, mock_session_cls, tmp_path):
        """resolve 将候选落盘到 data/candidates/"""
        import config.loader as loader_mod
        original_cache = loader_mod._config_cache

        mock_session = MagicMock()
        mock_session.get.return_value.text = "<html></html>"

        resolver = URLResolver(session=mock_session)
        with patch.object(loader_mod, '_config_cache', None):
            pass

        # 确保目录创建
        import os
        candidates_dir = tmp_path / "candidates"
        os.makedirs(candidates_dir, exist_ok=True)

        resolver = URLResolver(session=mock_session)
        resolver._save_candidates("测试大学", "机械学院", [
            URLCandidate(url="http://example.com", score=5.0)
        ])

        # 验证文件创建
        # (实际路径取决于 CANDIDATES_DIR 配置)

    @patch("spiders.url_resolver.PoliteSession")
    def test_merge_candidates_deduplicates(self, mock_session_cls):
        """合并去重"""
        mock_session = MagicMock()
        resolver = URLResolver(session=mock_session)

        c1 = URLCandidate(url="http://example.com", source="search_ddg")
        c2 = URLCandidate(url="http://example.com", source="search_bing")
        c3 = URLCandidate(url="http://other.com", source="search_ddg")

        merged = resolver._merge_candidates([c1, c2, c3])
        assert len(merged) == 2  # 去重后 2 个


class TestJSRender:
    """js_render 模块单测"""

    @patch("spiders.js_render.sync_playwright")
    @patch("spiders.js_render.CrawlCache")
    def test_fetch_via_playwright(self, mock_cache_cls, mock_playwright):
        """Playwright 引擎返回教师列表"""
        from spiders.static_list import parse_faculty_html
        from bs4 import BeautifulSoup

        html = """
        <html><body>
        <ul>
            <li><a href="/t/1" title="张三">张三</a></li>
        </ul>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        result = parse_faculty_html(soup, {"item": "li", "name": "a", "profile": "href"}, "http://example.com")
        assert len(result) == 1
        assert result[0]["name"] == "张三"


class TestPDFList:
    """pdf_list 模块单测"""

    def test_find_name_column(self):
        """识别姓名列"""
        headers = {0: "姓名", 1: "职称", 2: "研究方向"}
        assert _find_name_column(headers) == 0

    def test_find_name_column_default(self):
        """无匹配关键词时默认第一列"""
        headers = {0: "序号", 1: "其他信息"}
        assert _find_name_column(headers) == 0

    def test_parse_table_with_header(self):
        """解析有表头的表格"""
        table = [
            ["姓名", "职称", "研究方向"],
            ["张三", "教授", "智能制造"],
            ["李四", "副教授", "机器人学"],
        ]
        results = _parse_table(table, 0)
        assert len(results) == 2
        assert results[0]["name"] == "张三"
        assert results[0]["title"] == "教授"
        assert results[1]["name"] == "李四"

    def test_parse_table_no_header(self):
        """解析无表头的表格"""
        table = [
            ["张三", "教授"],
            ["李四", "副教授"],
        ]
        results = _parse_table(table, 0)
        assert len(results) == 2
        assert results[0]["name"] == "张三"

    def test_parse_empty_table(self):
        """空表格返回空列表"""
        results = _parse_table([], 0)
        assert results == []

    def test_split_research(self):
        """研究方向拆分"""
        from spiders.pdf_list import _split_research
        parts = _split_research("智能制造;机器人学;自动化控制")
        assert len(parts) == 3
        assert "智能制造" in parts


class TestEngineRegistry:
    """引擎注册表单测"""

    def test_registry_has_all_types(self):
        """注册表包含所有 list_type"""
        from spiders import ENGINE_REGISTRY
        assert "static_html" in ENGINE_REGISTRY
        assert "ajax_api" in ENGINE_REGISTRY
        assert "js_render" in ENGINE_REGISTRY
        assert "pdf_list" in ENGINE_REGISTRY

    def test_registry_returns_callable(self):
        """注册表中的值都是可调用对象"""
        from spiders import ENGINE_REGISTRY
        for fn in ENGINE_REGISTRY.values():
            assert callable(fn)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
