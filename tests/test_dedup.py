# -*- coding: utf-8 -*-
"""
配置去重模块单元测试
"""

import pytest

from config.dedup import (
    merge_dicts,
    merge_category,
    deduplicate_schools,
    _convert_old_to_new,
)


class TestMergeDicts:
    """merge_dicts 单测"""

    def test_both_nonempty(self):
        """两个非空字典合并（a 的非空值优先）"""
        a = {"name": "old", "value": "a"}
        b = {"name": "", "value": "b"}
        result = merge_dicts(a, b)
        assert result["name"] == "old"
        assert result["value"] == "a"  # a 的 value 已非空，保留 a

    def test_b_empty(self):
        """b 为空时保留 a"""
        a = {"name": "old", "value": "a"}
        b = {"name": "", "value": ""}
        result = merge_dicts(a, b)
        assert result["name"] == "old"
        assert result["value"] == "a"

    def test_a_empty_b_nonempty(self):
        """a 为空时取 b"""
        a = {"name": "", "value": ""}
        b = {"name": "new", "value": "b"}
        result = merge_dicts(a, b)
        assert result["name"] == "new"
        assert result["value"] == "b"

    def test_both_empty(self):
        """都为空"""
        a = {"name": ""}
        b = {"name": ""}
        result = merge_dicts(a, b)
        assert result["name"] == ""

    def test_new_keys_from_b(self):
        """b 中的新 key 被添加"""
        a = {"a": 1}
        b = {"b": 2}
        result = merge_dicts(a, b)
        assert result["a"] == 1
        assert result["b"] == 2


class TestMergeCategory:
    """merge_category 单测"""

    def test_nonempty_wins(self):
        """非空优先"""
        a = {"college": "旧学院", "category": "mechanical", "faculty": {"list_url": "http://old.com"}, "notice": {"enabled": False}}
        b = {"college": "新学院", "category": "mechanical", "faculty": {"list_url": ""}, "notice": {"enabled": True}}
        merged = merge_category(a, b)
        assert merged["faculty"]["list_url"] == "http://old.com"
        assert merged["notice"]["enabled"] is True

    def test_list_union(self):
        """列表取并集"""
        a = {"tags": ["a", "b"]}
        b = {"tags": ["b", "c"]}
        merged = merge_category(a, b)
        assert set(merged["tags"]) == {"a", "b", "c"}

    def test_empty_faculty_gets_b(self):
        """faculty 为空时取 b 的值"""
        a = {"college": "A", "category": "mechanical", "faculty": {}}
        b = {"college": "A", "category": "mechanical", "faculty": {"list_url": "http://x.com"}}
        merged = merge_category(a, b)
        assert merged["faculty"]["list_url"] == "http://x.com"

    def test_faculty_recursive_merge(self):
        """faculty 子字典递归合并（非空优先）"""
        a = {"college": "A", "category": "mechanical", "faculty": {"list_url": "http://a.com", "list_type": "static_html"}}
        b = {"college": "A", "category": "mechanical", "faculty": {"list_url": "", "list_type": "ajax_api"}}
        merged = merge_category(a, b)
        assert merged["faculty"]["list_url"] == "http://a.com"
        # a 的 list_type 非空，所以保留 a 的值
        assert merged["faculty"]["list_type"] == "static_html"

    def test_notice_recursive_merge(self):
        """notice 子字典递归合并"""
        a = {"college": "A", "category": "mechanical", "notice": {"enabled": False, "template": ""}}
        b = {"college": "A", "category": "mechanical", "notice": {"enabled": True, "template": "yzw_major"}}
        merged = merge_category(a, b)
        assert merged["notice"]["enabled"] is True
        assert merged["notice"]["template"] == "yzw_major"

    def test_simple_key_from_b(self):
        """简单 key 从 b 取值"""
        a = {"college": "A"}
        b = {"category": "automation"}
        merged = merge_category(a, b)
        assert merged["category"] == "automation"

    def test_val_b_nonempty_result_empty(self):
        """merge_category: val_b 非空但 result 中 key 为空时取 b"""
        a = {"college": "A", "data": ""}
        b = {"college": "B", "data": "value"}
        merged = merge_category(a, b)
        assert merged["data"] == "value"


class TestDeduplicateSchools:
    """deduplicate_schools 单测"""

    def test_merge_same_university(self):
        """同名学校合并"""
        configs = [
            {"university": "测试大学", "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://a.com"}, "notice": {"enabled": False}}]},
            {"university": "测试大学", "categories": [{"college": "B", "category": "automation", "faculty": {"list_url": "http://b.com"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 1
        assert len(result[0]["categories"]) == 2
        assert len(logs) > 0

    def test_no_duplicates(self):
        """无重复"""
        configs = [
            {"university": "大学A", "categories": [{"category": "mechanical", "faculty": {"list_url": "http://a.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
            {"university": "大学B", "categories": [{"category": "automation", "faculty": {"list_url": "http://b.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 2

    def test_empty_name_skipped(self):
        """空 university 跳过"""
        configs = [
            {"university": "", "categories": []},
            {"university": "大学A", "categories": [{"category": "mechanical", "faculty": {"list_url": "http://a.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 1
        assert any("跳过" in log for log in logs)

    def test_same_category_different_college(self):
        """同校同类别不同学院 -> 合并"""
        configs = [
            {"university": "测试大学", "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://a.com"}, "notice": {"enabled": False}}]},
            {"university": "测试大学", "categories": [{"college": "B", "category": "mechanical", "faculty": {"list_url": "http://b.com"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 1
        assert len(result[0]["categories"]) == 1

    def test_multiple_universities(self):
        """多所学校"""
        configs = [
            {"university": "大学A", "categories": [{"category": "mechanical", "faculty": {"list_url": "http://a.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
            {"university": "大学B", "categories": [{"category": "automation", "faculty": {"list_url": "http://b.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
            {"university": "大学A", "categories": [{"category": "automation", "faculty": {"list_url": "http://a2.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 2
        assert any(len(r["categories"]) == 2 for r in result if r["university"] == "大学A")

    def test_log_messages(self):
        """日志包含合并信息"""
        configs = [
            {"university": "测试大学", "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://a.com"}, "notice": {"enabled": False}}]},
            {"university": "测试大学", "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://b.com"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert any("合并" in log for log in logs)

    def test_empty_input(self):
        """空输入"""
        result, logs = deduplicate_schools([])
        assert result == []
        assert logs == []


class TestConvertOldToNew:
    """_convert_old_to_new 单测"""

    def test_convert_faculty_map(self):
        """旧格式转换正确"""
        from config.school_level_raw import validate_and_fix_levels
        validate_and_fix_levels()

        old_configs = [
            {
                "university": "测试大学",
                "level": "985",
                "categories": [{"college": "机械学院", "category": "mechanical", "notice": {"enabled": False}}],
                "faculty": {
                    "mechanical": {"list_url": "http://test.edu.cn", "list_type": "static_html"},
                    "automation": {"list_url": "", "list_type": "static_html"},
                },
            }
        ]
        result = _convert_old_to_new(old_configs)
        assert len(result) == 1
        assert result[0]["university"] == "测试大学"
        assert len(result[0]["categories"]) == 1
        cat = result[0]["categories"][0]
        assert cat["faculty"]["list_url"] == "http://test.edu.cn"
        assert cat["notice"]["enabled"] is False

    def test_convert_empty_faculty(self):
        """旧格式中 faculty 无对应 category 时使用默认值"""
        from config.school_level_raw import validate_and_fix_levels
        validate_and_fix_levels()

        old_configs = [
            {
                "university": "测试大学",
                "level": "985",
                "categories": [{"college": "机械学院", "category": "unknown", "notice": {"enabled": True}}],
                "faculty": {},
            }
        ]
        result = _convert_old_to_new(old_configs)
        assert result[0]["categories"][0]["faculty"]["list_url"] == ""
        assert result[0]["categories"][0]["faculty"]["list_type"] == "static_html"

    def test_convert_notice_migration(self):
        """notice 字段正确迁移"""
        from config.school_level_raw import validate_and_fix_levels
        validate_and_fix_levels()

        old_configs = [
            {
                "university": "测试大学",
                "level": "985",
                "categories": [{"college": "机械学院", "category": "mechanical", "notice": {"enabled": True, "entry_url": "https://yz.chsi.com.cn"}}],
                "faculty": {"mechanical": {"list_url": "http://test.edu.cn", "list_type": "static_html"}},
            }
        ]
        result = _convert_old_to_new(old_configs)
        cat = result[0]["categories"][0]
        assert cat["notice"]["entry_url"] == "https://yz.chsi.com.cn"
        assert cat["notice"]["school_code"] == ""
        assert cat["notice"]["template"] == "yzw_major"

    def test_convert_notice_not_dict(self):
        """notice 不是 dict 时使用默认值"""
        from config.school_level_raw import validate_and_fix_levels
        validate_and_fix_levels()

        old_configs = [
            {
                "university": "测试大学",
                "level": "985",
                "categories": [{"college": "机械学院", "category": "mechanical", "notice": "invalid"}],
                "faculty": {"mechanical": {"list_url": "http://test.edu.cn", "list_type": "static_html"}},
            }
        ]
        result = _convert_old_to_new(old_configs)
        cat = result[0]["categories"][0]
        assert cat["notice"]["enabled"] is False

    def test_convert_gets_level(self):
        """转换后包含 level 字段"""
        from config.school_level_raw import validate_and_fix_levels
        validate_and_fix_levels()

        old_configs = [
            {
                "university": "北京大学",
                "categories": [{"college": "A", "category": "mechanical", "notice": {"enabled": False}}],
                "faculty": {},
            }
        ]
        result = _convert_old_to_new(old_configs)
        assert "985" in result[0]["level"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
