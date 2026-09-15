# -*- coding: utf-8 -*-
"""
AJAX API 爬虫单元测试
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from spiders.ajax_api import (
    fetch_faculty_via_api,
    _parse_teacher_item,
    _parse_advisor_level,
)


class TestParseTeacherItem:
    """_parse_teacher_item 单测"""

    def test_basic(self):
        """基本解析"""
        item = {
            "title": "张三",
            "post": "教授",
            "degree": "博士",
            "exField1": "博士生导师,硕士生导师",
            "cnUrl": "/teacher/1",
            "headerPic": "/photo/1.jpg",
        }
        result = _parse_teacher_item(item, "http://test.seu.edu.cn/api")

        assert result["name"] == "张三"
        assert result["title"] == "教授"
        assert result["degree"] == "博士"
        assert result["advisor_level"] == "博导/硕导"
        assert result["profile_url"] == "http://test.seu.edu.cn/teacher/1"
        assert result["photo_url"] == "http://test.seu.edu.cn/photo/1.jpg"

    def test_no_exfield(self):
        """无 exField1 时 advisor_level 为空"""
        item = {"title": "李四", "post": "副教授", "degree": "硕士", "exField1": "", "cnUrl": "", "headerPic": ""}
        result = _parse_teacher_item(item, "http://test.seu.edu.cn/api")
        assert result["name"] == "李四"
        assert result["advisor_level"] == ""

    def test_full_url(self):
        """cnUrl 已是完整 URL"""
        item = {"title": "王五", "post": "讲师", "exField1": "硕士生导师", "cnUrl": "http://other.com/teacher/3", "headerPic": ""}
        result = _parse_teacher_item(item, "http://test.seu.edu.cn/api")
        assert result["profile_url"] == "http://other.com/teacher/3"

    def test_empty_name(self):
        """空姓名返回 None"""
        item = {"title": "", "post": "", "exField1": "", "cnUrl": "", "headerPic": ""}
        result = _parse_teacher_item(item, "http://test.seu.edu.cn/api")
        assert result is None


class TestParseAdvisorLevel:
    """_parse_advisor_level 单测"""

    def test_both(self):
        """博导+硕导"""
        result = _parse_advisor_level("博士生导师,硕士生导师")
        assert result == "博导/硕导"

    def test_phd_only(self):
        """仅博导"""
        result = _parse_advisor_level("博士生导师")
        assert result == "博导"

    def test_master_only(self):
        """仅硕导"""
        result = _parse_advisor_level("硕士生导师")
        assert result == "硕导"

    def test_none(self):
        """无导师身份"""
        result = _parse_advisor_level("普通职工")
        assert result == ""

    def test_empty(self):
        """空字符串"""
        assert _parse_advisor_level("") == ""


class TestFetchFacultyViaApi:
    """fetch_faculty_via_api 单测"""

    def test_with_mock_session(self, mock_session):
        """使用 Mock session 获取 AJAX 列表"""
        api_response = {
            "total": 2,
            "data": [
                {"title": "张三", "post": "教授", "degree": "博士", "exField1": "博士生导师,硕士生导师", "cnUrl": "/teacher/1", "headerPic": "/photo/1.jpg"},
                {"title": "李四", "post": "副教授", "degree": "博士", "exField1": "博士生导师", "cnUrl": "/teacher/2", "headerPic": "/photo/2.jpg"},
            ],
        }
        mock_session.post.return_value.json.return_value = api_response
        mock_session.post.return_value.text = json.dumps(api_response)

        results = fetch_faculty_via_api(
            session=mock_session,
            api_url="http://test.seu.edu.cn/api",
            site_id="338",
            referer="http://test.seu.edu.cn/list",
        )

        assert len(results) == 2
        assert results[0]["name"] == "张三"
        assert results[0]["advisor_level"] == "博导/硕导"
        assert results[1]["name"] == "李四"

    def test_with_cache(self, mock_session, mock_cache):
        """使用缓存命中时跳过网络请求"""
        api_response = {
            "total": 1,
            "data": [
                {"title": "张三", "post": "教授", "exField1": "博士生导师", "cnUrl": "/t/1", "headerPic": "/p/1.jpg"},
            ],
        }
        url = "http://test.seu.edu.cn/api?q=1"
        mock_cache.write(url, json.dumps(api_response))

        results = fetch_faculty_via_api(
            session=mock_session,
            api_url=url,
            site_id="338",
            referer="http://test.seu.edu.cn/list",
            cache=mock_cache,
        )

        assert len(results) == 1
        mock_session.post.assert_not_called()

    def test_empty_response(self, mock_session):
        """空响应返回空列表"""
        mock_session.post.return_value.json.return_value = {"total": 0, "data": []}
        mock_session.post.return_value.text = '{"total": 0, "data": []}'

        results = fetch_faculty_via_api(
            session=mock_session,
            api_url="http://test.seu.edu.cn/api",
            site_id="338",
            referer="http://test.seu.edu.cn/list",
        )
        assert results == []

    def test_extra_params(self, mock_session):
        """自定义参数合并"""
        api_response = {"total": 1, "data": [{"title": "张三", "exField1": "", "cnUrl": "", "headerPic": ""}]}
        mock_session.post.return_value.json.return_value = api_response
        mock_session.post.return_value.text = json.dumps(api_response)

        fetch_faculty_via_api(
            session=mock_session,
            api_url="http://test.seu.edu.cn/api",
            site_id="338",
            referer="http://test.seu.edu.cn/list",
            extra_params={"siteId": "999", "rows": "100"},
        )

        call_data = mock_session.post.call_args[1].get("data")
        assert call_data is not None
        assert call_data["siteId"] == "999"  # extra_params overrides default
