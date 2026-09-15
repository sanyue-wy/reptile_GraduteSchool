# -*- coding: utf-8 -*-
"""
研招网爬虫 + parser 单元测试
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from spiders.yzw_api import YzwClient
from parsers.yzw_major import (
    split_advisor_names,
    split_exam_subjects,
    build_tutor_record,
    parse,
)


class TestSplitAdvisorNames:
    """split_advisor_names 单测"""

    def test_basic(self):
        assert split_advisor_names("张三 李四") == ["张三", "李四"]

    def test_semicolon(self):
        assert split_advisor_names("张三;李四") == ["张三", "李四"]

    def test_chinese_semicolon(self):
        assert split_advisor_names("张三；李四") == ["张三", "李四"]

    def test_dunhao(self):
        assert split_advisor_names("张三、李四") == ["张三", "李四"]

    def test_empty(self):
        assert split_advisor_names("") == []

    def test_placeholder_none(self):
        assert split_advisor_names("不区分导师") == []
        assert split_advisor_names("请登录各学院网站查看") == []
        assert split_advisor_names("--") == []

    def test_single_name(self):
        assert split_advisor_names("张三") == ["张三"]


class TestSplitExamSubjects:
    """split_exam_subjects 单测"""

    def test_basic(self):
        result = split_exam_subjects("101 政治 201 英语一 301 数学一 801 机械原理")
        assert result == ["101 政治", "201 英语一", "301 数学一", "801 机械原理"]

    def test_empty(self):
        assert split_exam_subjects("") == []

    def test_single_pair(self):
        assert split_exam_subjects("101 政治") == ["101 政治"]


class TestBuildTutorRecord:
    """build_tutor_record 单测"""

    def test_full_record(self):
        raw = {
            "zydm": "085501",
            "zymc": "机械工程",
            "yjfxmc": "智能制造",
            "kskm": "101 政治 201 英语一",
            "nzsrsstr": "3",
            "xxfs": "1",
        }
        meta = {
            "university": "测试大学",
            "college": "机梅工程学院",
            "category": "mechanical",
            "year": 2026,
            "school_code": "99999",
        }
        result = build_tutor_record("张三", raw, meta)

        assert result["name"] == "张三"
        assert result["university"] == "测试大学"
        assert result["college"] == "机梅工程学院"
        assert result["category"] == "mechanical"
        assert result["match_status"] == "partial_notice"
        assert result["schema_version"] == 1

        assert result["enrollment"]["in_roster"] is True
        assert len(result["enrollment"]["directions"]) == 1
        assert result["enrollment"]["directions"][0]["code"] == "085501"
        assert result["enrollment"]["directions"][0]["name"] == "机械工程"
        assert result["enrollment"]["planned_count"] == 3
        assert result["enrollment"]["degree_types"] == ["学术型硕士"]
        assert result["enrollment"]["notice_year"] == 2026

    def test_professional_degree(self):
        raw = {"zydm": "085501", "zymc": "机械工程", "xxfs": "2", "nzsrsstr": "5"}
        meta = {"university": "大学", "college": "学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        result = build_tutor_record("李四", raw, meta)
        assert result["enrollment"]["degree_types"] == ["专业型硕士"]

    def test_no_tutor_name(self):
        raw = {"zydm": "085501", "zymc": "机械工程", "kskm": ""}
        meta = {"university": "大学", "college": "学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        result = build_tutor_record("", raw, meta)
        assert result["name"] == ""
        assert result["enrollment"]["in_roster"] is True

    def test_raw_ref(self):
        raw = {"zydm": "085501"}
        meta = {"university": "大学", "college": "学院", "category": "mechanical", "year": 2026, "school_code": "12345"}
        result = build_tutor_record("张三", raw, meta)
        assert "data/raw/大学/2026/yzw/major_12345.json" in result["raw_ref"]


class TestYzwMajorParser:
    """yzw_major parser parse() 单测"""

    def test_parse_json_file(self, tmp_path):
        data = {
            "data": [
                {"zydm": "085501", "zymc": "机械工程", "yjfxmc": "智能制造",
                 "zdjs": "张三 李四", "kskm": "101 政治 201 英语一", "nzsrsstr": "3", "xxfs": "1"},
                {"zydm": "085502", "zymc": "车辆工程", "yjfxmc": "新能源",
                 "zdjs": "王五", "kskm": "101 政治 201 英语二", "nzsrsstr": "2", "xxfs": "1"},
            ]
        }
        raw_path = tmp_path / "major_99999.json"
        raw_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        meta = {
            "university": "测试大学",
            "college": "机梅工程学院",
            "category": "mechanical",
            "year": 2026,
            "school_code": "99999",
            "template": "yzw_major",
        }
        results = parse(str(raw_path), meta)

        assert len(results) == 3  # 张三, 李四, 王五
        assert results[0]["name"] == "张三"
        assert results[1]["name"] == "李四"
        assert results[2]["name"] == "王五"
        assert all(r["match_status"] == "partial_notice" for r in results)

    def test_parse_major_code_filter(self, tmp_path):
        data = {
            "data": [
                {"zydm": "085501", "zymc": "机械工程", "zdjs": "张三"},
                {"zydm": "085502", "zymc": "车辆工程", "zdjs": "李四"},
            ]
        }
        raw_path = tmp_path / "major_99999.json"
        raw_path.write_text(json.dumps(data), encoding="utf-8")

        meta = {
            "university": "测试大学",
            "college": "机梅工程学院",
            "category": "mechanical",
            "year": 2026,
            "school_code": "99999",
            "major_codes": ["085501"],
        }
        results = parse(str(raw_path), meta)
        assert len(results) == 1
        assert results[0]["name"] == "张三"

    def test_parse_empty_tutor_names(self, tmp_path):
        data = {"data": [{"zydm": "085501", "zymc": "机械工程", "zdjs": "不区分导师"}]}
        raw_path = tmp_path / "major.json"
        raw_path.write_text(json.dumps(data), encoding="utf-8")

        meta = {"university": "大学", "college": "学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        results = parse(str(raw_path), meta)
        assert len(results) == 1
        assert results[0]["name"] == ""

    def test_parse_file_not_found(self):
        """原件文件不存在应返回空列表，不抛出异常"""
        meta = {"university": "大学", "college": "学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        results = parse("/nonexistent/path/major.json", meta)
        assert results == []

    def test_parse_json_decode_error(self, tmp_path):
        """JSON 格式异常应返回空列表，不抛出异常"""
        raw_path = tmp_path / "broken.json"
        raw_path.write_text("{invalid json content", encoding="utf-8")

        meta = {"university": "大学", "college": "学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        results = parse(str(raw_path), meta)
        assert results == []

    def test_parse_empty_data_list(self, tmp_path):
        """空 data 列表应返回空列表"""
        raw_path = tmp_path / "empty.json"
        raw_path.write_text(json.dumps({"data": []}), encoding="utf-8")

        meta = {"university": "大学", "college": "学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        results = parse(str(raw_path), meta)
        assert results == []

    def test_parse_schema_fields(self, tmp_path):
        """验证输出记录包含所有必填字段"""
        data = {"data": [{"zydm": "085501", "zymc": "机械工程", "zdjs": "张三", "kskm": "101 政治", "nzsrsstr": "3", "xxfs": "1", "yjfxmc": "智能制造"}]}
        raw_path = tmp_path / "major.json"
        raw_path.write_text(json.dumps(data), encoding="utf-8")

        meta = {"university": "测试大学", "college": "机梅工程学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        results = parse(str(raw_path), meta)
        assert len(results) == 1
        r = results[0]
        # INTERFACE_SPEC.md 必含字段
        for field in ("name", "university", "college", "category", "match_status", "raw_ref", "source_type"):
            assert field in r, f"缺少必填字段: {field}"
        assert r["match_status"] == "partial_notice"
        assert r["source_type"] == "研招网专业目录"
        assert r["enrollment"]["in_roster"] is True
        assert r["enrollment"]["directions"][0]["code"] == "085501"
        assert r["schema_version"] == 1


class TestYzwClient:
    """YzwClient 单测"""

    def test_init(self, mock_session):
        client = YzwClient(session=mock_session)
        assert client.session is mock_session
        assert client.cache is None
        assert client._school_code_cache == {}

    def test_get_school_code_from_cache(self, mock_session):
        client = YzwClient(session=mock_session)
        client._school_code_cache["东南大学"] = "10213"
        assert client.get_school_code("东南大学") == "10213"
        mock_session.get.assert_not_called()

    def test_get_school_code_from_html(self, mock_session):
        html = '<a href="/zsml/rs/dws.do?dwdm=10213&dlmc=...">东南大学</a>'
        mock_session.get.return_value.text = html
        client = YzwClient(session=mock_session)
        code = client.get_school_code("东南大学")
        assert code == "10213"

    def test_get_school_code_not_found(self, mock_session):
        mock_session.get.return_value.text = "<html>no results</html>"
        client = YzwClient(session=mock_session)
        code = client.get_school_code("不存在大学")
        assert code is None

    def test_fetch_major_directory_no_category(self, mock_session):
        client = YzwClient(session=mock_session)
        results = client.fetch_major_directory("99999", year=2026)
        assert results == []

    def test_fetch_major_directory_with_category(self, mock_session):
        api_response = {
            "total": 1,
            "data": [
                {"zydm": "085501", "zymc": "机械工程", "yjfxmc": "智能制造",
                 "zdjs": "张三", "kskm": "101 政治", "nzsrsstr": "3", "xxfs": "1"},
            ],
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(api_response)
        mock_response.json.return_value = api_response
        mock_session.post.return_value = mock_response

        client = YzwClient(session=mock_session)
        results = client.fetch_major_directory(
            "99999", year=2026, category="mechanical", university="测试大学",
        )
        assert len(results) >= 1
        assert results[0]["zymc"] == "机械工程"


class TestYzwApiEdgeCases:
    """YzwClient 边界情况单测"""

    def test_get_school_code_fallback(self, mock_session):
        """get_school_code 使用兜底匹配"""
        html = '<a href="/zsml/xxgk/detailQuerySchAction.do?dwdm=10213&dwmc=测试大学">'
        mock_session.get.return_value.text = html
        client = YzwClient(session=mock_session)
        code = client.get_school_code("不存在的大学名")
        assert code == "10213"

    def test_get_school_code_no_match(self, mock_session):
        """get_school_code 无匹配返回 None"""
        mock_session.get.return_value.text = "<html>无匹配</html>"
        client = YzwClient(session=mock_session)
        code = client.get_school_code("完全不存在的大学")
        assert code is None

    def test_fetch_major_directory_major_codes(self, mock_session):
        """fetch_major_directory 使用 major_codes"""
        api_response = {
            "total": 1,
            "data": [{"zydm": "085501", "zymc": "机械工程", "yjfxmc": "智能制造",
                      "zdjs": "张三", "kskm": "101 政治", "nzsrsstr": "3", "xxfs": "1"}],
        }
        mock_response = MagicMock()
        mock_response.text = json.dumps(api_response)
        mock_response.json.return_value = api_response
        mock_session.post.return_value = mock_response

        client = YzwClient(session=mock_session)
        results = client.fetch_major_directory(
            "99999", year=2026, major_codes=["085501"], university="测试大学",
        )
        assert len(results) >= 1

    def test_fetch_major_directory_no_params(self, mock_session):
        """fetch_major_directory 无 category 和 major_codes 返回空"""
        client = YzwClient(session=mock_session)
        results = client.fetch_major_directory("99999", year=2026)
        assert results == []

    def test_fetch_major_directory_empty_yjxkdm(self, mock_session):
        """fetch_major_directory major_codes 太短返回空"""
        api_response = {"total": 0, "data": []}
        mock_response = MagicMock()
        mock_response.text = json.dumps(api_response)
        mock_response.json.return_value = api_response
        mock_session.post.return_value = mock_response

        client = YzwClient(session=mock_session)
        results = client.fetch_major_directory(
            "99999", year=2026, major_codes=["123"], university="测试大学",
        )
        assert results == []
