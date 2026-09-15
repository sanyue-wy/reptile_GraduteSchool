# -*- coding: utf-8 -*-
"""
静态 HTML 师资列表爬虫单元测试
"""

from unittest.mock import MagicMock, patch
from bs4 import BeautifulSoup

import pytest

from spiders.static_list import (
    fetch_faculty_list,
    parse_faculty_html,
    _extract_one,
    _get_field,
    _split_research,
)


class TestParseFacultyHtml:
    """parse_faculty_html 单测"""

    def test_parse_static_list(self, sample_faculty_html):
        """解析静态列表页"""
        soup = BeautifulSoup(sample_faculty_html, "lxml")
        selectors = {
            "item": "li a",
            "name": "title",
            "profile": "href",
        }
        results = parse_faculty_html(soup, selectors, "http://test.edu.cn")

        assert len(results) == 3
        assert results[0]["name"] == "张三"
        assert results[0]["profile_url"] == "http://test.edu.cn/teacher/1"
        assert results[1]["name"] == "李四"
        assert results[2]["name"] == "王五"

    def test_parse_with_research(self):
        """解析包含研究方向的列表"""
        html = """
        <html><body>
        <ul class="faculty-list">
            <li><a href="/teacher/1" title="张三"><span class="name">张三</span><p class="desc">研究方向：智能制造</p></a></li>
        </ul>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        selectors = {
            "item": "li a",
            "name": "title",
            "profile": "href",
            "research": ".desc",
        }
        results = parse_faculty_html(soup, selectors, "http://test.edu.cn")
        assert len(results) == 1
        assert "research_areas" in results[0]
        assert "智能制造" in results[0]["research_areas"]

    def test_parse_dedup_same_name(self):
        """同名教师只保留第一条"""
        html = """
        <html><body>
        <ul>
            <li><a href="/teacher/1" title="张三">张三</a></li>
            <li><a href="/teacher/2" title="张三">张三</a></li>
            <li><a href="/teacher/3" title="李四">李四</a></li>
        </ul>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        selectors = {"item": "li a", "name": "title", "profile": "href"}
        results = parse_faculty_html(soup, selectors, "http://test.edu.cn")
        assert len(results) == 2
        names = [r["name"] for r in results]
        assert names.count("张三") == 1

    def test_parse_empty_list(self):
        """空列表返回空"""
        soup = BeautifulSoup("<html><body></body></html>", "lxml")
        selectors = {"item": ".teacher", "name": "title", "profile": "href"}
        results = parse_faculty_html(soup, selectors, "http://test.edu.cn")
        assert results == []

    def test_extract_one_no_name(self):
        """无姓名的条目返回 None"""
        soup = BeautifulSoup('<li><a href="/teacher/1"></a></li>', "lxml")
        selectors = {"name": "title", "profile": "href"}
        result = _extract_one(soup, selectors, "http://test.edu.cn")
        assert result is None

    def test_extract_one_with_name(self):
        """有姓名的条目正确提取"""
        soup = BeautifulSoup('<li><a href="/teacher/1" title="张三">张三</a></li>', "lxml")
        a_tag = soup.find("a")
        selectors = {"name": "title", "profile": "href"}
        result = _extract_one(a_tag, selectors, "http://test.edu.cn")
        assert result is not None
        assert result["name"] == "张三"
        assert result["profile_url"] == "http://test.edu.cn/teacher/1"


class TestGetField:
    """_get_field 单测"""

    def test_as_attribute(self):
        """作为属性名提取"""
        soup = BeautifulSoup('<a href="/teacher/1" title="张三">链接</a>', "lxml")
        a_tag = soup.find("a")
        assert _get_field(a_tag, "title") == "张三"
        assert _get_field(a_tag, "href") == "/teacher/1"

    def test_as_css_selector(self):
        """作为 CSS 选择器提取"""
        soup = BeautifulSoup('<div class="name">张三</div>', "lxml")
        assert _get_field(soup, ".name") == "张三"

    def test_not_found(self):
        """未找到返回 None"""
        soup = BeautifulSoup("<div>hello</div>", "lxml")
        assert _get_field(soup, ".nonexistent") is None
        assert _get_field(soup, "nonexistent_attr") is None


class TestSplitResearch:
    """_split_research 单测"""

    def test_split_by_semicolon(self):
        """分号分割"""
        result = _split_research("智能制造；机器人学；自动化控制")
        assert result == ["智能制造", "机器人学", "自动化控制"]

    def test_split_by_comma(self):
        """逗号分割"""
        result = _split_research("智能制造,机器人学,自动化控制")
        assert result == ["智能制造", "机器人学", "自动化控制"]

    def test_split_by_dunhao(self):
        """顿号分割"""
        result = _split_research("智能制造、机器人学、自动化控制")
        assert result == ["智能制造", "机器人学", "自动化控制"]

    def test_empty(self):
        """空字符串返回空列表"""
        assert _split_research("") == []


class TestFetchFacultyList:
    """fetch_faculty_list 单测"""

    def test_with_mock_session(self, mock_session, sample_faculty_html):
        """使用 Mock session 获取列表"""
        mock_session.get.return_value.text = sample_faculty_html

        selectors = {
            "item": "li a",
            "name": "title",
            "profile": "href",
        }
        results = fetch_faculty_list(
            session=mock_session,
            list_url="http://test.edu.cn/faculty",
            selectors=selectors,
        )

        assert len(results) > 0
        assert "name" in results[0]
        assert "profile_url" in results[0]

    def test_with_cache(self, mock_session, sample_faculty_html, mock_cache):
        """使用缓存命中时跳过网络请求"""
        url = "http://test.edu.cn/faculty_cached"
        mock_cache.write(url, sample_faculty_html)

        selectors = {"item": "li a", "name": "title", "profile": "href"}
        results = fetch_faculty_list(
            session=mock_session,
            list_url=url,
            selectors=selectors,
            cache=mock_cache,
        )

        assert len(results) > 0
        # 缓存命中，session 不应被调用
        mock_session.get.assert_not_called()
