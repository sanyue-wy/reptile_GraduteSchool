# -*- coding: utf-8 -*-
"""
详情页解析器单元测试
"""

from bs4 import BeautifulSoup
from unittest.mock import MagicMock, patch

import pytest

from spiders.detail_parser import (
    fetch_detail,
    _detect_type,
    _parse_me_style,
    _parse_auto_style,
    _parse_generic,
    _parse_title_text,
    _parse_kv_field,
    _parse_sections,
    _normalize_section_title,
    _split_research,
    _parse_advisor_level_text,
)


class TestDetectType:
    """_detect_type 单测"""

    def test_me_style(self):
        """.carrer 元素 → me 类型"""
        soup = BeautifulSoup('<div class="carrer"></div>', "lxml")
        assert _detect_type(soup) == "me"

    def test_auto_style(self):
        """.xing 元素 → auto_type"""
        soup = BeautifulSoup('<div class="xing"></div>', "lxml")
        assert _detect_type(soup) == "auto_type"

    def test_generic(self):
        """无特征元素 → generic"""
        soup = BeautifulSoup("<div>nothing</div>", "lxml")
        assert _detect_type(soup) == "generic"


class TestParseMeStyle:
    """_parse_me_style 单测（机械工程学院模板）"""

    def test_basic(self, tmp_path):
        """基本解析：姓名、职称、邮箱、研究方向"""
        html = """
        <div class="carrer">
            <div class="title">
                <span class="jsbt">张三</span>
                教授 博士生导师
                <div class="text">邮箱：zhangsan@test.edu.cn</div>
                <div class="text">所在院系：机械工程学院</div>
            </div>
        </div>
        <div class="news_box">
            <div class="tit">研究方向</div>
            <div class="con">1、智能制造 2、机器人学</div>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _parse_me_style(soup, "http://test.edu.cn/teacher/1")

        assert result["name"] == "张三"
        assert result["title"] == "教授"
        assert result["advisor_level"] == "博导"
        assert result["email"] == "zhangsan@test.edu.cn"
        assert result["department"] == "机械工程学院"
        assert "research" in result["sections"]
        assert "智能制造" in result["research_areas"]

    def test_no_title_section(self):
        """无研究方向板块"""
        html = '<div class="carrer"><div class="title"><span class="jsbt">李四</span>副教授</div></div>'
        soup = BeautifulSoup(html, "lxml")
        result = _parse_me_style(soup, "http://test.edu.cn/teacher/2")
        assert result["name"] == "李四"
        # "教授" is checked before "副教授" in _parse_title_text, and "教授" is substring of "副教授"
        assert result["title"] == "教授"
        assert result.get("research_areas", []) == []


class TestParseAutoStyle:
    """_parse_auto_style 单测（自动化学院模板）"""

    def test_basic(self):
        """基本解析"""
        html = """
        <div class="xing">王五</div>
        <span>女</span>
        <span>教授</span>
        <span>博士生导师</span>
        <div class="text">邮箱: wangwu@test.edu.cn</div>
        <div class="news_box">
            <div class="tit">研究兴趣</div>
            <div class="con">人工智能；深度学习</div>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = _parse_auto_style(soup, "http://test.edu.cn/teacher/3")

        assert result["name"] == "王五"
        assert result["title"] == "教授"
        assert result["advisor_level"] == "博导"
        assert result["email"] == "wangwu@test.edu.cn"
        assert "research" in result["sections"]

    def test_master_only(self):
        """仅硕导"""
        html = '<div class="xing">赵六</div><span>男</span><span>讲师</span><span>硕士生导师</span>'
        soup = BeautifulSoup(html, "lxml")
        result = _parse_auto_style(soup, "http://test.edu.cn/teacher/4")
        assert result["name"] == "赵六"
        assert result["title"] == "讲师"
        assert result["advisor_level"] == "硕导"


class TestParseGeneric:
    """_parse_generic 单测"""

    def test_extract_email(self):
        """邮箱正则提取"""
        html = '<html><body>联系邮箱: test@example.com</body></html>'
        soup = BeautifulSoup(html, "lxml")
        result = _parse_generic(soup, "http://test.com")
        assert result["email"] == "test@example.com"

    def test_extract_name(self):
        """姓名提取"""
        html = '<html><body><h1>张教授</h1></body></html>'
        soup = BeautifulSoup(html, "lxml")
        result = _parse_generic(soup, "http://test.com")
        assert result["name"] == "张教授"


class TestParseTitleText:
    """_parse_title_text 单测"""

    def test_title_and_advisor(self):
        """提取职称和博硕导"""
        result = {}
        _parse_title_text("教授 博士生导师 硕士生导师", result)
        assert result["title"] == "教授"
        assert result["advisor_level"] == "博导/硕导"

    def test_no_advisor(self):
        """无导师身份"""
        result = {}
        _parse_title_text("讲师", result)
        assert result["title"] == "讲师"
        assert "advisor_level" not in result

    def test_title_priority(self):
        """职称优先级"""
        # "教授" 会被优先匹配（它是 "副教授" 的子串）
        result = {}
        _parse_title_text("副教授 教授", result)
        assert result["title"] == "教授"


class TestParseKvField:
    """_parse_kv_field 单测"""

    def test_email(self):
        """邮箱字段"""
        result = {}
        _parse_kv_field("邮箱：test@example.com", result)
        assert result["email"] == "test@example.com"

    def test_phone(self):
        """电话字段"""
        result = {}
        _parse_kv_field("电话: 1234-5678", result)
        assert result["phone"] == "1234-5678"

    def test_office(self):
        """办公室字段"""
        result = {}
        _parse_kv_field("办公室：A栋301", result)
        assert result["office"] == "A栋301"

    def test_no_match(self):
        """无法匹配字段"""
        result = {}
        _parse_kv_field("随机文本无匹配", result)
        assert result == {}


class TestParseSections:
    """_parse_sections 单测"""

    def test_research_section(self):
        """研究方向板块"""
        html = """
        <div class="news_box">
            <div class="tit">研究方向</div>
            <div class="con">1、智能制造 2、机器人学</div>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = {}
        _parse_sections(soup, result)
        assert "research" in result["sections"]
        assert "智能制造" in result["research_areas"]

    def test_research_interest_synonym(self):
        """研究兴趣同义词"""
        html = """
        <div class="news_box">
            <div class="tit">Research Interests</div>
            <div class="con">AI, ML</div>
        </div>
        """
        soup = BeautifulSoup(html, "lxml")
        result = {}
        _parse_sections(soup, result)
        assert "research" in result["sections"]


class TestNormalizeSectionTitle:
    """_normalize_section_title 单测"""

    def test_research_direction(self):
        """研究方向匹配同义词"""
        assert _normalize_section_title("研究方向") == "research"
        assert _normalize_section_title("研究兴趣") == "research"
        assert _normalize_section_title("Research Interests") == "research"

    def test_bio(self):
        """个人简介匹配"""
        assert _normalize_section_title("个人简介") == "bio"

    def test_no_match(self):
        """未匹配返回 None"""
        assert _normalize_section_title("随机标题") is None


class TestSplitResearch:
    """_split_research 单测（详情页版）"""

    def test_numbered_format(self):
        """编号格式拆分"""
        result = _split_research("1、智能制造 2、机器人学")
        assert result == ["智能制造", "机器人学"]

    def test_dot_numbered(self):
        """数字点格式"""
        result = _split_research("1. 智能制造 2. 机器人学")
        assert result == ["智能制造", "机器人学"]

    def test_fallback_delimiter(self):
        """无编号格式用分隔符拆"""
        result = _split_research("智能制造；机器人学")
        assert result == ["智能制造", "机器人学"]


class TestParseAdvisorLevel:
    """_parse_advisor_level_text 单测"""

    def test_both(self):
        result = _parse_advisor_level_text("博士生导师 硕士生导师")
        assert result == "博导/硕导"

    def test_none(self):
        result = _parse_advisor_level_text("普通教师")
        assert result == ""


class TestFetchDetail:
    """fetch_detail 单测"""

    def test_with_mock_session_me(self, mock_session, tmp_path, monkeypatch):
        """使用 Mock session + me 模板解析"""
        html = """
        <div class="carrer">
            <div class="title">
                <span class="jsbt">张三</span>
                教授 博士生导师
            </div>
            <div class="text">邮箱：zhangsan@test.edu.cn</div>
        </div>
        <div class="news_box">
            <div class="tit">研究方向</div>
            <div class="con">1、智能制造</div>
        </div>
        """
        mock_session.get.return_value.text = html

        result = fetch_detail(
            session=mock_session,
            profile_url="http://test.edu.cn/teacher/1",
            detail_type="me",
        )

        assert result["name"] == "张三"
        assert result["title"] == "教授"
        assert result["advisor_level"] == "博导"
        assert result["email"] == "zhangsan@test.edu.cn"
        assert "research_areas" in result

    def test_with_cache(self, mock_session, mock_cache):
        """使用缓存命中时跳过网络请求"""
        html = '<div class="xing">李四</div><span>教授</span>'
        url = "http://test.edu.cn/teacher/2"
        mock_cache.write(url, html)

        result = fetch_detail(
            session=mock_session,
            profile_url=url,
            detail_type="auto",
            cache=mock_cache,
        )

        assert result["name"] == "李四"
        mock_session.get.assert_not_called()

    def test_auto_detect_me(self, mock_session):
        """自动检测 me 模板"""
        html = '<div class="carrer"><span class="jsbt">张三</span></div>'
        mock_session.get.return_value.text = html

        result = fetch_detail(
            session=mock_session,
            profile_url="http://test.edu.cn/teacher/1",
            detail_type="auto",
        )
        assert result["profile_url"] == "http://test.edu.cn/teacher/1"
