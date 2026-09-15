# -*- coding: utf-8 -*-
"""
进度追踪和日志配置单测
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from utils.progress import ProgressTracker, get_progress_tracker
from utils.logging_config import setup_logging


class TestProgressTracker:
    """ProgressTracker 单测"""

    def test_default_structure(self, mock_progress):
        """默认结构包含正确字段"""
        data = mock_progress._default_structure()
        assert "version" in data
        assert "schools" in data
        assert "pipelines" in data
        assert "source_breakdown" in data

    def test_get_all_schools_summary(self, mock_progress, tmp_path):
        """get_all_schools_summary 返回汇总列表"""
        # 添加一些学校数据
        mock_progress.update_school_status("测试大学", "机械学院", source_a="done", tutor_count=5)
        mock_progress.update_school_status("测试大学", "自动化学院", source_b="running")

        summary = mock_progress.get_all_schools_summary()
        assert isinstance(summary, list)
        assert len(summary) >= 2

        # 验证结构
        for item in summary:
            assert "key" in item
            assert "university" in item
            assert "college" in item
            assert "status" in item
            assert "tutor_count" in item

    def test_get_all_schools_summary_empty(self, mock_progress):
        """无学校数据时返回空列表"""
        summary = mock_progress.get_all_schools_summary()
        assert summary == []

    def test_recalc_pipelines(self, mock_progress):
        """_recalc_pipelines 正确更新 pipelines"""
        from utils.progress import PROGRESS_FILE
        data = mock_progress._read_raw()

        # 模拟 done 状态
        mock_progress.update_school_status("测试大学", "机械学院", source_a="done")

        pipelines = mock_progress.get_pipeline_progress()
        assert pipelines["source_a"]["completed"] >= 1

    def test_update_source_breakdown(self, mock_progress):
        """update_source_breakdown 正确更新"""
        mock_progress.update_source_breakdown(10, 5, 3, 2)
        breakdown = mock_progress.get_source_breakdown()
        assert breakdown["matched"] == 10
        assert breakdown["notice_only"] == 5
        assert breakdown["faculty_only"] == 3
        assert breakdown["unmatched"] == 2

    def test_get_recent_logs_parsing(self, mock_progress, tmp_path):
        """get_recent_logs 正确解析日志格式"""
        log_file = mock_progress.log_file
        log_file.write_text(
            "2026-09-14 16:02:31,123 - INFO - 测试日志1\n"
            "2026-09-14 16:02:32,456 - ERROR - 测试日志2\n",
            encoding="utf-8",
        )

        logs = mock_progress.get_recent_logs(limit=10)
        assert len(logs) >= 1
        assert any("INFO" in log["level"] for log in logs)
        assert any("ERROR" in log["level"] for log in logs)

    def test_get_recent_logs_file_not_exist(self, mock_progress):
        """日志文件不存在时返回空列表"""
        import os
        os.unlink(mock_progress.log_file)
        logs = mock_progress.get_recent_logs()
        assert logs == []

    def test_get_recent_tutors_from_jsonl(self, mock_progress, tmp_path):
        """get_recent_tutors 从 JSONL 读取"""
        output_dir = Path("data/output")
        output_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = output_dir / "测试大学_机械学院.jsonl"
        jsonl_path.write_text(
            '{"name": "张三", "title": "教授", "advisor_level": "博导", "university": "测试大学", "college": "机械学院", "research_areas": ["AI"]}\n',
            encoding="utf-8",
        )

        tutors = mock_progress.get_recent_tutors(limit=5)
        assert len(tutors) >= 1
        assert tutors[0]["name"] == "张三"

        # 清理
        jsonl_path.unlink()

    def test_add_log(self, mock_progress, tmp_path):
        """add_log 追加日志"""
        log_file = mock_progress.log_file
        mock_progress.add_log("INFO", "测试日志")

        content = log_file.read_text(encoding="utf-8")
        assert "INFO" in content
        assert "测试日志" in content

    def test_concurrent_updates(self, mock_progress):
        """并发更新线程安全"""
        import threading

        def update(i):
            mock_progress.update_school_status(
                f"大学{i}", f"学院{i}", source_a="done", tutor_count=i
            )

        threads = [threading.Thread(target=update, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 验证所有学校都更新了
        summary = mock_progress.get_all_schools_summary()
        assert len(summary) >= 5

    def test_get_overview_stats(self, mock_progress):
        """get_overview_stats 返回正确统计"""
        mock_progress.update_school_status("测试大学", "机械学院", source_a="done")
        mock_progress.update_school_status("测试大学2", "自动化学院", source_a="pending")

        stats = mock_progress.get_overview_stats()
        assert "total_schools" in stats
        assert "done" in stats
        assert "pending" in stats
        assert stats["done"] >= 1


class TestLoggingConfig:
    """setup_logging 单测"""

    def test_setup_logging(self, tmp_path):
        """setup_logging 不抛异常"""
        log_file = str(tmp_path / "test.log")
        setup_logging(level="INFO", log_file=log_file)
        # 验证日志文件被创建
        assert Path(log_file).exists()

    def test_setup_logging_custom_level(self, tmp_path):
        """setup_logging 支持 DEBUG 级别"""
        log_file = str(tmp_path / "debug.log")
        setup_logging(level="DEBUG", log_file=log_file)
        assert Path(log_file).exists()
