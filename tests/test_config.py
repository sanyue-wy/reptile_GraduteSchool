# -*- coding: utf-8 -*-
"""
配置模块单元测试
"""

import json
from pathlib import Path

import pytest

from config.school_level_raw import (
    SCHOOLS_985,
    SCHOOLS_211,
    SCHOOLS_SHUANGYILIU,
    get_school_level,
)
from config.major_mapping import (
    MAJOR_MAPPING,
    get_major_codes,
)
from config.loader import (
    load_schools_config,
    get_school_config,
    save_school_config,
    reload_config,
)
from config.validator import (
    ConfigError,
    validate_school_config,
    validate_all_configs,
)
from config.dedup import (
    deduplicate_schools,
    merge_category,
    merge_dicts,
)
from config.schools import SCHOOLS_CONFIG


class TestSchoolLevel:
    """学校层级映射单测"""

    def test_985_school(self):
        """985高校返回 '985'"""
        level = get_school_level("北京大学")
        assert "985" in level

    def test_211_school(self):
        """211高校返回 '211'"""
        level = get_school_level("北京交通大学")
        assert "211" in level

    def test_shuangyiliu_school(self):
        """双一流高校"""
        level = get_school_level("东南大学")
        assert "双一流" in level

    def test_multiple_levels(self):
        """多层级学校返回斜杠拼接"""
        level = get_school_level("北京大学")
        assert "985" in level
        assert "211" in level

    def test_unknown_school(self):
        """未知学校返回空字符串"""
        level = get_school_level("不存在的大学")
        assert level == ""

    def test_empty_name(self):
        """空名称返回空字符串"""
        assert get_school_level("") == ""
        assert get_school_level(None) == ""

    def test_schools_sets(self):
        """学校集合非空"""
        assert len(SCHOOLS_985) > 0
        assert len(SCHOOLS_211) > 0
        assert len(SCHOOLS_SHUANGYILIU) > 0

    def test_985_subset_of_211(self):
        """985 ⊆ 211"""
        assert SCHOOLS_985.issubset(SCHOOLS_211)


class TestMajorMapping:
    """专业代码映射单测"""

    def test_get_major_codes_mechanical(self):
        """机械工程专业代码"""
        codes = get_major_codes("mechanical", level="first_level")
        assert "0855" in codes

    def test_get_major_codes_automation(self):
        """自动化专业代码"""
        codes = get_major_codes("automation", level="first_level")
        assert len(codes) > 0

    def test_get_major_codes_detail(self):
        """明细码"""
        codes = get_major_codes("mechanical", level="detail")
        assert "085501" in codes

    def test_get_major_codes_unknown(self):
        """未知类别返回空列表"""
        assert get_major_codes("unknown_category") == []

    def test_major_mapping_structure(self):
        """映射结构完整"""
        assert "mechanical" in MAJOR_MAPPING
        assert "automation" in MAJOR_MAPPING
        assert "name" in MAJOR_MAPPING["mechanical"]
        assert "first_level_codes" in MAJOR_MAPPING["mechanical"]
        assert "detail_codes" in MAJOR_MAPPING["mechanical"]


class TestSchoolsConfig:
    """学校配置单测"""

    def test_schools_config_exists(self):
        """SCHOOLS_CONFIG 非空"""
        assert len(SCHOOLS_CONFIG) > 0

    def test_config_structure(self):
        """配置结构完整"""
        for school in SCHOOLS_CONFIG:
            assert "university" in school
            assert "categories" in school
            assert len(school["categories"]) > 0

    def test_category_structure(self):
        """学院配置结构"""
        for school in SCHOOLS_CONFIG:
            for cat in school.get("categories", []):
                assert "college" in cat
                assert "category" in cat
                assert cat["category"] in ("mechanical", "automation")

    def test_east_south_university(self):
        """东南大学配置正确"""
        seu = next((s for s in SCHOOLS_CONFIG if s["university"] == "东南大学"), None)
        assert seu is not None
        assert len(seu["categories"]) >= 2
        mechanical = next((c for c in seu["categories"] if c["category"] == "mechanical"), None)
        assert mechanical is not None
        assert mechanical["college"] == "机械工程学院"


class TestConfigLoader:
    def test_load_returns_list(self):
        configs = load_schools_config()
        assert isinstance(configs, list)
        assert len(configs) >= 100  # 至少 100 校

    def test_load_has_level(self, monkeypatch):
        """加载后每校都有 level 字段（测试大学不在真实学校列表中）"""
        import config.school_level_raw as sl_mod
        import config.loader as loader_mod
        original = sl_mod.get_school_level
        original_cache = loader_mod._config_cache

        def patched(name):
            if name == "测试大学":
                return "985"
            return original(name)

        monkeypatch.setattr(sl_mod, 'get_school_level', patched)
        loader_mod._config_cache = None
        try:
            configs = load_schools_config()
            for cfg in configs:
                assert cfg.get("level"), f"{cfg['university']} 缺少 level"
        finally:
            loader_mod._config_cache = original_cache

    def test_get_existing_school(self):
        cfg = get_school_config("东南大学")
        assert cfg is not None
        assert cfg["university"] == "东南大学"

    def test_get_nonexistent_school(self):
        assert get_school_config("不存在的大学") is None

    def test_reload_returns_count(self):
        count = reload_config()
        assert isinstance(count, int)
        assert count > 0

    def test_resolve_path_with_argument(self):
        """_resolve_path 传入路径参数时返回该路径"""
        import config.loader as loader_mod
        from pathlib import Path
        result = loader_mod._resolve_path("/tmp/test.json")
        assert result == Path("/tmp/test.json")

    def test_resolve_path_without_argument(self):
        """_resolve_path 不传参数时返回默认路径"""
        import config.loader as loader_mod
        result = loader_mod._resolve_path()
        assert result == loader_mod._config_path

    def test_save_and_get(self, tmp_path):
        """保存后能立即读取到（使用临时文件）"""
        import config.loader as loader_mod
        original_path = loader_mod._config_path
        tmp_file = tmp_path / "test_school_data.json"
        tmp_file.write_text(json.dumps([]), encoding="utf-8")
        loader_mod._config_path = tmp_file
        loader_mod._config_cache = None

        cfg = {
            "university": "测试大学",
            "level": "985",
            "categories": [
                {
                    "college": "机械工程学院",
                    "category": "mechanical",
                    "faculty": {
                        "list_url": "https://faculty.seu.edu.cn/teacher",
                        "list_type": "static_html",
                    },
                    "notice": {"enabled": False, "template": "yzw_major"},
                }
            ],
        }
        assert save_school_config("测试大学", cfg) is True

        result = get_school_config("测试大学")
        assert result is not None
        assert result["university"] == "测试大学"

        # restore
        loader_mod._config_path = original_path
        loader_mod._config_cache = None


class TestConfigValidator:
    def test_valid_config(self):
        cfg = {
            "university": "测试大学",
            "categories": [{
                "college": "测试学院",
                "category": "mechanical",
                "faculty": {"list_url": "https://faculty.seu.edu.cn/teacher", "list_type": "static_html"},
                "notice": {"enabled": False, "template": "yzw_major"},
            }]
        }
        errors = validate_school_config(cfg)
        assert len(errors) == 0

    def test_missing_university(self):
        cfg = {"categories": []}
        errors = validate_school_config(cfg)
        assert any(e.field == "university" for e in errors)

    def test_missing_categories(self):
        cfg = {"university": "测试大学"}
        errors = validate_school_config(cfg)
        assert any(e.field == "categories" for e in errors)

    def test_invalid_category_type(self):
        cfg = {
            "university": "测试",
            "categories": [{"category": "invalid", "faculty": {"list_url": "http://x.com", "list_type": "static_html"}, "notice": {"enabled": False}}],
        }
        errors = validate_school_config(cfg)
        assert any(e.field == "category" for e in errors)

    def test_missing_list_url(self):
        cfg = {
            "university": "测试",
            "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_type": "static_html"}, "notice": {"enabled": False}}],
        }
        errors = validate_school_config(cfg)
        assert any(e.field == "faculty.list_url" for e in errors)

    def test_invalid_list_type(self):
        cfg = {
            "university": "测试",
            "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://x.com", "list_type": "unknown"}, "notice": {"enabled": False}}],
        }
        errors = validate_school_config(cfg)
        assert any(e.field == "faculty.list_type" for e in errors)

    def test_notice_enabled_without_template(self):
        cfg = {
            "university": "测试",
            "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://x.com", "list_type": "static_html"}, "notice": {"enabled": True}}],
        }
        errors = validate_school_config(cfg)
        assert any(e.field == "notice.template" for e in errors)

    def test_yzw_major_requires_school_code(self):
        cfg = {
            "university": "测试",
            "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://x.com", "list_type": "static_html"}, "notice": {"enabled": True, "template": "yzw_major"}}],
        }
        errors = validate_school_config(cfg)
        assert any(e.field == "notice.school_code" for e in errors)

    def test_validate_all_configs_structure(self):
        """validate_all_configs 返回正确结构"""
        configs = load_schools_config()
        report = validate_all_configs(configs)
        assert "errors" in report
        assert "warnings" in report
        assert "summary" in report
        assert report["summary"]["total"] == len(configs)

    def test_config_error_str(self):
        err = ConfigError("大学", "学院", "university", "不能为空")
        assert "ERROR" in str(err)
        assert "大学" in str(err)

    def test_placeholder_url_detected(self):
        """占位符 URL 被检测为 error"""
        cfg = {
            "university": "测试大学",
            "categories": [{
                "college": "机械学院",
                "category": "mechanical",
                "faculty": {"list_url": "http://x.com", "list_type": "static_html"},
                "notice": {"enabled": False, "template": "yzw_major"},
            }]
        }
        errors = validate_school_config(cfg)
        placeholder_errors = [e for e in errors if "占位符" in e.message]
        assert len(placeholder_errors) > 0
        assert placeholder_errors[0].level == "error"

    def test_placeholder_urls_detected(self):
        """多种占位符 URL 模式均被检测"""
        from config.validator import _check_placeholder_url
        assert _check_placeholder_url("http://x.com") is True
        assert _check_placeholder_url("http://example.com") is True
        assert _check_placeholder_url("http://test.edu.cn") is True
        assert _check_placeholder_url("http://localhost:8080") is True
        assert _check_placeholder_url("") is False
        assert _check_placeholder_url("https://real.seu.edu.cn") is False

    def test_new_list_types_accepted(self):
        """js_render 和 pdf_list 作为合法 list_type"""
        cfg = {
            "university": "测试大学",
            "categories": [{
                "college": "机械学院",
                "category": "mechanical",
                "faculty": {"list_url": "https://faculty.seu.edu.cn", "list_type": "js_render"},
                "notice": {"enabled": False},
            }]
        }
        errors = validate_school_config(cfg)
        list_type_errors = [e for e in errors if e.field == "faculty.list_type"]
        assert len(list_type_errors) == 0

        cfg2 = {
            "university": "测试大学",
            "categories": [{
                "college": "机械学院",
                "category": "mechanical",
                "faculty": {"list_url": "https://faculty.seu.edu.cn", "list_type": "pdf_list"},
                "notice": {"enabled": False},
            }]
        }
        errors2 = validate_school_config(cfg2)
        list_type_errors2 = [e for e in errors2 if e.field == "faculty.list_type"]
        assert len(list_type_errors2) == 0

    def test_invalid_list_type_rejected(self):
        """非法 list_type 被拒绝"""
        cfg = {
            "university": "测试大学",
            "categories": [{
                "college": "机械学院",
                "category": "mechanical",
                "faculty": {"list_url": "https://faculty.seu.edu.cn", "list_type": "unknown_type"},
                "notice": {"enabled": False},
            }]
        }
        errors = validate_school_config(cfg)
        assert any(e.field == "faculty.list_type" for e in errors)


class TestDedup:
    def test_merge_same_university(self):
        configs = [
            {"university": "测试大学", "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://a.com"}, "notice": {"enabled": False}}]},
            {"university": "测试大学", "categories": [{"college": "B", "category": "automation", "faculty": {"list_url": "http://b.com"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 1
        assert len(result[0]["categories"]) == 2
        assert len(logs) > 0

    def test_no_duplicates(self):
        configs = [
            {"university": "大学A", "categories": [{"category": "mechanical", "faculty": {"list_url": "http://a.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
            {"university": "大学B", "categories": [{"category": "automation", "faculty": {"list_url": "http://b.com", "list_type": "static_html"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 2

    def test_merge_same_category_different_college(self):
        """同校同类别不同学院 -> 合并为一条"""
        configs = [
            {"university": "测试大学", "categories": [{"college": "A", "category": "mechanical", "faculty": {"list_url": "http://a.com"}, "notice": {"enabled": False}}]},
            {"university": "测试大学", "categories": [{"college": "B", "category": "mechanical", "faculty": {"list_url": "http://b.com"}, "notice": {"enabled": False}}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 1
        assert len(result[0]["categories"]) == 1  # 合并为一条

    def test_merge_category_nonempty_wins(self):
        """merge_category: 非空字段优先"""
        a = {"college": "旧学院", "category": "mechanical", "faculty": {"list_url": "http://old.com"}, "notice": {"enabled": False}}
        b = {"college": "新学院", "category": "mechanical", "faculty": {"list_url": ""}, "notice": {"enabled": True}}
        merged = merge_category(a, b)
        # 非空优先: list_url 保留旧值
        assert merged["faculty"]["list_url"] == "http://old.com"
        # notice.enabled 非空取新
        assert merged["notice"]["enabled"] is True

    def test_merge_dicts_nonempty_wins(self):
        a = {"name": "old", "value": ""}
        b = {"name": "", "value": "new"}
        merged = merge_dicts(a, b)
        assert merged["name"] == "old"
        assert merged["value"] == "new"

    def test_no_duplicate_university_category(self):
        """验收: school_data.json 中无重复 university + category"""
        configs = load_schools_config()
        seen = set()
        for cfg in configs:
            for cat in cfg.get("categories", []):
                key = (cfg["university"], cat["category"])
                assert key not in seen, f"重复: {key}"
                seen.add(key)
