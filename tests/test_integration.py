# -*- coding: utf-8 -*-
"""
端到端集成测试
================
集成测试：使用 Mock HTTP，验证完整数据流。
不依赖真实网络，CI 环境可运行。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from spiders.static_list import fetch_faculty_list
from pipelines.merge import merge_sources
from pipelines.export import export_merged, export_summary


class TestEndToEnd:
    """
    集成测试：使用 Mock HTTP，验证完整数据流。
    不依赖真实网络，CI 环境可运行。
    """

    def test_source_a_pipeline(self, tmp_dir, mock_session, sample_config, sample_faculty_html):
        """
        Source A 完整流程：
        抓取列表 → 详情页解析 → 写入 _faculty.jsonl
        """
        # 1. Mock HTTP 响应
        mock_session.get.return_value.text = sample_faculty_html

        # 2. 调用静态列表爬虫
        faculty_cfg = sample_config["categories"][0]["faculty"]
        selectors = {
            "item": faculty_cfg["list_item_selector"],
            "name": "title",
            "profile": "href",
            "research": faculty_cfg.get("list_research_selector", ""),
        }
        tutors = fetch_faculty_list(
            session=mock_session,
            list_url="http://test.edu.cn/faculty",
            selectors=selectors,
        )
        assert len(tutors) > 0

        # 3. 写入 JSONL
        university = sample_config["university"]
        college = sample_config["categories"][0]["college"]
        output_path = tmp_dir / f"{university}_{college}_faculty.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for t in tutors:
                t["university"] = university
                t["college"] = college
                t["category"] = "mechanical"
                t["source_type"] = "官网师资页"
                t["raw_ref"] = ""
                f.write(json.dumps(t, ensure_ascii=False) + "\n")

        # 4. 验证文件可读
        with open(output_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == len(tutors)

        # 5. 验证每行都是有效 JSON
        for line in lines:
            record = json.loads(line.strip())
            assert "name" in record
            assert "university" in record
            assert "college" in record

    def test_merge_pipeline(self, tmp_dir):
        """
        合并管道完整流程：
        读取 _faculty.jsonl + _notice.jsonl → 输出合并 .jsonl
        """
        # 构造 faculty 数据
        faculty_data = [
            {"name": "张三", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "教授", "advisor_level": "博导",
             "email": "zhangsan@test.edu.cn", "profile_url": "http://test.edu.cn/1",
             "research_areas": ["智能制造"], "raw_ref": "", "source_type": "官网师资页"},
            {"name": "李四", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "副教授", "advisor_level": "硕导",
             "email": "lisi@test.edu.cn", "profile_url": "http://test.edu.cn/2",
             "research_areas": ["机器人学"], "raw_ref": "", "source_type": "官网师资页"},
        ]

        # 构造 notice 数据（张三重名匹配，新名赵六）
        notice_data = [
            {"name": "张三", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "", "advisor_level": "",
             "email": "", "profile_url": "", "research_areas": [],
             "enrollment": {"in_roster": True, "directions": [{"code": "085501", "name": "机械工程"}],
                            "planned_count": 3, "exam_subjects": [], "source_url": "", "notice_year": 2026},
             "raw_ref": "", "source_type": "研招网专业目录"},
            {"name": "赵六", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "", "advisor_level": "",
             "email": "", "profile_url": "", "research_areas": [],
             "enrollment": {"in_roster": True, "directions": [{"code": "085502", "name": "车辆工程"}],
                            "planned_count": 2, "exam_subjects": [], "source_url": "", "notice_year": 2026},
             "raw_ref": "", "source_type": "研招网专业目录"},
        ]

        # 写入中间态文件
        faculty_path = tmp_dir / "faculty.jsonl"
        notice_path = tmp_dir / "notice.jsonl"
        output_path = tmp_dir / "merged.jsonl"

        for path, data in [(faculty_path, faculty_data), (notice_path, notice_data)]:
            with open(path, "w", encoding="utf-8") as f:
                for d in data:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")

        # 调用合并
        stats = merge_sources(str(faculty_path), str(notice_path), str(output_path))

        # 验证统计
        assert stats["total"] == 3  # 张三(merged) + 李四(partial_faculty) + 赵六(partial_notice)
        assert stats["merged"] == 1
        assert stats["partial_faculty"] == 1
        assert stats["partial_notice"] == 1

        # 验证输出文件
        with open(output_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        assert len(records) == 3
        assert any(r["name"] == "张三" and r["match_status"] == "merged" for r in records)
        assert any(r["name"] == "李四" and r["match_status"] == "partial_faculty" for r in records)
        assert any(r["name"] == "赵六" and r["match_status"] == "partial_notice" for r in records)

    def test_full_export_flow(self, tmp_dir):
        """
        完整导出流程：
        合并数据 → JSONL 导出 + Excel 汇总
        """
        # 构造合并后的记录
        merged_records = [
            {
                "schema_version": 1,
                "name": "张三",
                "university": "测试大学", "college": "机械学院", "category": "mechanical",
                "title": "教授", "advisor_level": "博导/硕导", "email": "zhangsan@test.edu.cn",
                "profile_url": "http://test.edu.cn/1", "research_areas": ["智能制造", "机器人学"],
                "enrollment": {"in_roster": True, "directions": [{"code": "0855", "name": "机械工程"}],
                               "degree_types": ["硕士"], "planned_count": 3, "exam_subjects": ["政治"],
                               "source_url": "", "notice_year": 2026},
                "match_status": "merged",
                "raw_ref": {"faculty": "", "notice": ""},
                "source_type": {"faculty": "官网师资页", "notice": "研招网专业目录"},
            },
        ]

        # 1. 导出 JSONL
        jsonl_result = export_merged(merged_records, output_dir=tmp_dir)
        assert jsonl_result["files_written"] == 1
        assert jsonl_result["total_records"] == 1

        # 2. 导出 Excel
        xlsx_path = tmp_dir / "summary.xlsx"
        count = export_summary(merged_records, output_path=xlsx_path)
        assert count == 1
        assert xlsx_path.exists()

        # 3. 验证 JSONL 可读
        jsonl_files = list(tmp_dir.glob("*.jsonl"))
        assert len(jsonl_files) == 1
        with open(jsonl_files[0], "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
        assert len(records) == 1
        assert records[0]["name"] == "张三"
        assert records[0]["match_status"] == "merged"

    def test_source_a_only(self, tmp_dir, mock_session, sample_config):
        """
        仅有 Source A 数据，合并后全部标记 partial_faculty
        """
        faculty_data = [
            {"name": "张三", "university": "测试大学", "college": "机械学院",
             "title": "教授", "email": "zhangsan@test.edu.cn", "raw_ref": "", "source_type": "官网师资页"},
        ]
        faculty_path = tmp_dir / "faculty_only.jsonl"
        notice_path = tmp_dir / "nonexistent_notice.jsonl"
        output_path = tmp_dir / "merged.jsonl"

        with open(faculty_path, "w", encoding="utf-8") as f:
            for d in faculty_data:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")

        stats = merge_sources(str(faculty_path), str(notice_path), str(output_path))
        assert stats["total"] == 1
        assert stats["merged"] == 0
        assert stats["partial_faculty"] == 1
        assert stats["partial_notice"] == 0

    def test_empty_inputs(self, tmp_dir):
        """两个空文件输入不报错"""
        faculty_path = tmp_dir / "empty_faculty.jsonl"
        notice_path = tmp_dir / "empty_notice.jsonl"
        output_path = tmp_dir / "merged.jsonl"

        faculty_path.write_text("", encoding="utf-8")
        notice_path.write_text("", encoding="utf-8")

        stats = merge_sources(str(faculty_path), str(notice_path), str(output_path))
        assert stats["total"] == 0
        assert stats["merged"] == 0
        assert stats["partial_faculty"] == 0
        assert stats["partial_notice"] == 0
        assert output_path.exists()
