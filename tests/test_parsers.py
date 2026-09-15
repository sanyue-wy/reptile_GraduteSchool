# -*- coding: utf-8 -*-
"""
Parser 注册表单元测试
"""

import json
from pathlib import Path

import pytest

from parsers import dispatch, list_registered, _REGISTRY


class TestParserRegistry:
    """Parser 注册表测"""

    def test_registered_parsers(self):
        """验证所有预期 parser 已注册"""
        registered = list_registered()
        assert "yzw_major" in registered

    def test_dispatch_unknown_template(self):
        """未知 template 应抛出 ValueError"""
        with pytest.raises(ValueError, match="未注册"):
            dispatch("dummy.json", {"template": "nonexistent"})

    def test_dispatch_missing_template(self):
        """meta 缺少 template 应抛出 ValueError"""
        with pytest.raises(ValueError, match="缺少 template"):
            dispatch("dummy.json", {"university": "测试"})

    def test_dispatch_routes_to_yzw_major(self, tmp_path):
        """dispatch 正确路由到 yzw_major parser"""
        data = {"data": [{"zydm": "085501", "zymc": "机械工程", "zdjs": "张三", "kskm": "101 政治", "nzsrsstr": "3", "xxfs": "1"}]}
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
        results = dispatch(str(raw_path), meta)
        assert len(results) == 1
        assert results[0]["name"] == "张三"
        assert results[0]["match_status"] == "partial_notice"


class TestParserUtils:
    """公共工具函数测试"""

    def test_split_names_normal(self):
        from parsers.utils import split_names
        assert split_names("张三 李四") == ["张三", "李四"]

    def test_split_names_semicolon(self):
        from parsers.utils import split_names
        assert split_names("张三;李四") == ["张三", "李四"]

    def test_split_names_chinese_semicolon(self):
        from parsers.utils import split_names
        assert split_names("张三；李四") == ["张三", "李四"]

    def test_split_names_dunhao(self):
        from parsers.utils import split_names
        assert split_names("张三、李四") == ["张三", "李四"]

    def test_split_names_empty(self):
        from parsers.utils import split_names
        assert split_names("") == []

    def test_split_names_placeholder(self):
        from parsers.utils import split_names
        assert split_names("不区分导师") == []
        assert split_names("请登录各学院网站查看") == []
        assert split_names("--") == []
        assert split_names("无") == []

    def test_split_names_single(self):
        from parsers.utils import split_names
        assert split_names("张三") == ["张三"]

    def test_split_names_short_name(self):
        from parsers.utils import split_names
        assert split_names("张") == []

    def test_normalize_whitespace(self):
        from parsers.utils import normalize_whitespace
        assert normalize_whitespace("  hello   world  ") == "hello world"
        assert normalize_whitespace("hello　world") == "hello world"
        assert normalize_whitespace("hello\xa0world") == "hello world"
        assert normalize_whitespace("") == ""
        assert normalize_whitespace(None) == ""
