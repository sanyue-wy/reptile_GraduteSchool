# -*- coding: utf-8 -*-
"""
合并管道单元测试
"""

import json

import pytest

from pipelines.merge import (
    normalize_name,
    strip_name,
    _build_index,
    match_records,
    merge_pair,
    merge_sources,
    to_summary_row,
)


class TestNormalizeName:
    """姓名归一化"""

    def test_basic_strip(self):
        assert normalize_name("  张三  ") == "张三"

    def test_fullwidth_space(self):
        """全角空格 → 半角"""
        assert normalize_name("張　三") == "張 三"

    def test_compress_internal_spaces(self):
        """压缩连续空格"""
        assert normalize_name("张  三") == "张 三"

    def test_empty(self):
        assert normalize_name("") == ""

    def test_none(self):
        assert normalize_name(None) == ""


class TestStripName:
    """去空格姓名"""

    def test_remove_spaces(self):
        assert strip_name("张 三 李") == "张三李"

    def test_fullwidth_space(self):
        assert strip_name("张　三") == "张三"


class TestBuildIndex:
    """倒排索引构建"""

    def test_basic(self):
        records = [{"name": "张三"}, {"name": "李四"}, {"name": "张三"}]
        idx = _build_index(records)
        assert len(idx["张三"]) == 2
        assert len(idx["李四"]) == 1

    def test_empty_names(self):
        records = [{"name": ""}, {"name": "  "}, {"name": "张三"}]
        idx = _build_index(records)
        assert "张三" in idx
        assert "" not in idx


class TestMatchRecords:
    """匹配策略"""

    def test_exact_match(self):
        """姓名完全匹配正确合并"""
        faculty = [
            {"name": "张三", "university": "测试大学", "college": "机械学院", "email": "a@test.edu"},
        ]
        notice = [
            {"name": "张三", "university": "测试大学", "college": "机械学院", "directions": [{"code": "0855", "name": "机械工程"}]},
        ]
        matched, unmatched_fac, unmatched_not = match_records(faculty, notice)
        assert len(matched) == 1
        assert matched[0][2] == "merged"
        assert matched[0][0]["email"] == "a@test.edu"
        assert matched[0][1]["directions"] == [{"code": "0855", "name": "机械工程"}]

    def test_fuzzy_name_match(self):
        """姓名近似匹配（difflib ≥0.85）正确合并"""
        faculty = [
            {"name": "赵钱孙印", "university": "测试大学", "college": "机械学院"},
        ]
        notice = [
            {"name": "赵钱孙吉", "university": "测试大学", "college": "机械学院"},  # 印→吉 差一个字
        ]
        matched, _, _ = match_records(faculty, notice, fuzzy_threshold=0.7)
        assert len(matched) == 1
        assert matched[0][2] == "merged"

    def test_whitespace_normalize(self):
        """姓名含全角空格正确归一化匹配"""
        faculty = [
            {"name": "张三", "university": "测试大学", "college": "机械学院"},
        ]
        notice = [
            {"name": "张　三", "university": "测试大学", "college": "机械学院"},  # 全角空格
        ]
        matched, _, _ = match_records(faculty, notice)
        assert len(matched) == 1
        assert matched[0][2] == "merged"

    def test_different_college_no_match(self):
        """不同学院不匹配"""
        faculty = [
            {"name": "张三", "university": "测试大学", "college": "机械学院"},
        ]
        notice = [
            {"name": "张三", "university": "测试大学", "college": "自动化学院"},
        ]
        matched, _, _ = match_records(faculty, notice)
        # 不同学院在不同分组，均标记为 partial
        assert len(matched) == 2
        statuses = [m[2] for m in matched]
        assert "partial_faculty" in statuses
        assert "partial_notice" in statuses

    def test_only_faculty(self):
        """仅有 Source A 时，全部标记 partial_faculty"""
        faculty = [
            {"name": "张三", "university": "测试大学", "college": "机械学院"},
            {"name": "李四", "university": "测试大学", "college": "机械学院"},
        ]
        matched, unmatched_fac, unmatched_not = match_records(faculty, [])
        assert len(matched) == 2
        assert all(m[2] == "partial_faculty" for m in matched)
        assert len(unmatched_not) == 0

    def test_only_notice(self):
        """仅有 Source B 时，全部标记 partial_notice"""
        notice = [
            {"name": "张三", "university": "测试大学", "college": "机械学院"},
            {"name": "赵六", "university": "测试大学", "college": "机械学院"},
        ]
        matched, unmatched_fac, unmatched_not = match_records([], notice)
        assert len(matched) == 2
        assert all(m[2] == "partial_notice" for m in matched)
        assert len(unmatched_fac) == 0

    def test_empty_files(self):
        """两个空文件输入不报错"""
        matched, unmatched_fac, unmatched_not = match_records([], [])
        assert len(matched) == 0
        assert len(unmatched_fac) == 0
        assert len(unmatched_not) == 0


class TestMergePair:
    """合并为统一 Schema"""

    def test_merge_faculty_priority(self):
        """优先使用 Source A 的基础字段"""
        fac = {"name": "张三", "title": "教授", "email": "a@test.edu", "source_type": "官网师资页", "raw_ref": "ref_a"}
        not_ = {"name": "张三", "title": "", "email": "", "source_type": "研招网", "raw_ref": "ref_b"}
        result = merge_pair(fac, not_, "merged")
        assert result["name"] == "张三"
        assert result["title"] == "教授"
        assert result["email"] == "a@test.edu"

    def test_merge_enrollment(self):
        """Source B 的 enrollment 子对象填入"""
        fac = {"name": "张三", "university": "测试大学", "college": "机械学院", "title": "教授", "source_type": "官网师资页", "raw_ref": ""}
        not_ = {"name": "张三", "university": "测试大学", "college": "机械学院",
                "directions": [{"code": "0855", "name": "机械工程"}],
                "in_roster": True, "degree_types": ["硕士"],
                "planned_count": 3, "exam_subjects": ["政治"],
                "source_url": "http://yz.edu.cn", "notice_year": 2026,
                "source_type": "研招网", "raw_ref": ""}
        result = merge_pair(fac, not_, "merged")
        assert result["enrollment"]["in_roster"] is True
        assert result["enrollment"]["directions"] == [{"code": "0855", "name": "机械工程"}]
        assert result["enrollment"]["planned_count"] == 3

    def test_merge_only_faculty(self):
        """仅有 faculty 数据，enrollment 为 None"""
        fac = {"name": "张三", "university": "大学", "college": "学院", "title": "教授", "source_type": "官网师资页", "raw_ref": ""}
        result = merge_pair(fac, None, "partial_faculty")
        assert result["match_status"] == "partial_faculty"
        assert result["enrollment"] is None

    def test_merge_only_notice(self):
        """仅有 notice 数据"""
        not_ = {"name": "李四", "university": "大学", "college": "学院",
                "directions": [{"code": "0855", "name": "机械工程"}],
                "in_roster": True, "degree_types": ["硕士"],
                "planned_count": 2, "exam_subjects": [],
                "source_url": "", "notice_year": 2026,
                "source_type": "研招网", "raw_ref": ""}
        result = merge_pair(None, not_, "partial_notice")
        assert result["match_status"] == "partial_notice"
        assert result["enrollment"]["in_roster"] is True

    def test_statistics(self, tmp_dir):
        """返回统计摘要含 total/merged/partial_faculty/partial_notice"""
        faculty_data = [
            {"name": "张三", "university": "测试大学", "college": "机械学院", "title": "教授", "email": "a@test.edu",
             "profile_url": "http://test.edu.cn/1", "research_areas": ["智能制造"], "raw_ref": "", "source_type": "官网师资页"},
            {"name": "李四", "university": "测试大学", "college": "机械学院", "title": "副教授", "email": "l@test.edu.cn",
             "profile_url": "http://test.edu.cn/2", "research_areas": ["机器人学"], "raw_ref": "", "source_type": "官网师资页"},
        ]
        notice_data = [
            {"name": "张三", "university": "测试大学", "college": "机械学院",
             "enrollment": {"in_roster": True, "directions": [{"code": "085501", "name": "机械工程"}],
                            "planned_count": 3, "exam_subjects": [], "source_url": "", "notice_year": 2026},
             "raw_ref": "", "source_type": "研招网专业目录"},
            {"name": "赵六", "university": "测试大学", "college": "机械学院",
             "enrollment": {"in_roster": True, "directions": [{"code": "085502", "name": "车辆工程"}],
                            "planned_count": 2, "exam_subjects": [], "source_url": "", "notice_year": 2026},
             "raw_ref": "", "source_type": "研招网专业目录"},
        ]

        faculty_path = tmp_dir / "faculty.jsonl"
        notice_path = tmp_dir / "notice.jsonl"
        output_path = tmp_dir / "merged.jsonl"

        for path, data in [(faculty_path, faculty_data), (notice_path, notice_data)]:
            with open(path, "w", encoding="utf-8") as f:
                for d in data:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")

        stats = merge_sources(str(faculty_path), str(notice_path), str(output_path))

        assert stats["total"] == 3  # 张三(merged) + 李四(partial_faculty) + 赵六(partial_notice)
        assert stats["merged"] == 1
        assert stats["partial_faculty"] == 1
        assert stats["partial_notice"] == 1

        # 验证输出文件
        with open(output_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
        assert len(records) == 3
        assert any(r["name"] == "张三" and r["match_status"] == "merged" for r in records)


class TestToSummaryRow:
    """Excel 汇总行转换"""

    def test_to_summary_row(self):
        merged = {
            "schema_version": 1,
            "name": "张三",
            "university": "测试大学",
            "college": "机械工程学院",
            "title": "教授",
            "advisor_level": "博导",
            "email": "zhangsan@test.edu.cn",
            "profile_url": "http://test.edu.cn/teacher/1",
            "research_areas": ["智能制造", "机器人学"],
            "enrollment": {
                "in_roster": True,
                "degree_types": ["硕士"],
                "directions": [{"code": "085501", "name": "机械工程"}],
                "planned_count": 3,
                "exam_subjects": ["政治", "英语一"],
                "source_url": "",
                "notice_year": 2026,
            },
            "match_status": "merged",
            "raw_ref": {"faculty": "", "notice": ""},
            "source_type": {"faculty": "官网师资页", "notice": "研招网"},
        }
        row = to_summary_row(merged)
        assert row["学校"] == "测试大学"
        assert row["学院"] == "机械工程学院"
        assert row["姓名"] == "张三"
        assert row["职称"] == "教授"
        assert row["招生状态"] == "是"
        assert row["招生方向"] == "机械工程"
        assert row["研究方向"] == "智能制造; 机器人学"
        assert row["来源链接"] == "http://test.edu.cn/teacher/1"

    def test_to_summary_row_no_enrollment(self):
        """无 enrollment 时招生状态为否"""
        merged = {
            "university": "测试大学",
            "college": "机械学院",
            "name": "李四",
            "title": "副教授",
            "research_areas": [],
            "enrollment": None,
        }
        row = to_summary_row(merged)
        assert row["招生状态"] == "否"
        assert row["招生方向"] == ""
        assert row["来源链接"] == ""
