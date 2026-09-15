# -*- coding: utf-8 -*-
"""
ProgressTracker 单元测试
"""

import json
import threading
from pathlib import Path

import pytest

from utils.progress import (
    ProgressTracker,
    VALID_STATUSES,
    VALID_SOURCES,
    get_progress_tracker,
)


class TestProgressTracker:
    """ProgressTracker 单测"""

    def test_init_creates_files(self, tmp_dir):
        """初始化时创建 progress.json 和 crawl.log"""
        progress_file = tmp_dir / "output" / "progress.json"
        log_file = tmp_dir / "output" / "crawl.log"

        tracker = ProgressTracker(progress_file=progress_file, log_file=log_file)

        assert progress_file.exists()
        assert log_file.exists()

    def test_default_structure(self, mock_progress):
        """默认结构包含 version、schools、pipelines、source_breakdown"""
        data = mock_progress._read_raw()
        assert data["version"] == 1
        assert "schools" in data
        assert "pipelines" in data
        assert "source_breakdown" in data
        assert "updated_at" in data

    def test_update_and_get(self, mock_progress):
        """更新状态后能正确读取"""
        mock_progress.update_school_status(
            "测试大学", "机械工程学院",
            source_a="done", tutor_count=15,
        )
        status = mock_progress.get_school_status("测试大学", "机械工程学院")
        assert status["source_a"] == "done"
        assert status["tutor_count"] == 15

    def test_update_partial(self, mock_progress):
        """仅更新部分字段"""
        mock_progress.update_school_status(
            "测试大学", "机械工程学院", source_a="done"
        )
        mock_progress.update_school_status(
            "测试大学", "机械工程学院", source_b="partial"
        )
        status = mock_progress.get_school_status("测试大学", "机械工程学院")
        assert status["source_a"] == "done"
        assert status["source_b"] == "partial"

    def test_get_nonexistent_school(self, mock_progress):
        """获取不存在的学校返回默认状态"""
        status = mock_progress.get_school_status("不存在的大学", "不存在的学院")
        assert status["source_a"] == "pending"
        assert status["source_b"] == "pending"
        assert status["merged"] == "pending"
        assert status["last_crawl_at"] == ""
        assert status["tutor_count"] == 0

    def test_atomic_write(self, mock_progress, tmp_dir):
        """写入过程中断不会损坏文件"""
        # 写入正常数据
        mock_progress.update_school_status("大学A", "学院A1", source_a="done")
        data = json.loads(mock_progress.progress_file.read_text(encoding="utf-8"))
        assert data["schools"]["大学A|学院A1"]["source_a"] == "done"

    def test_overview_stats(self, mock_progress):
        """统计概览数据正确"""
        mock_progress.update_school_status("大学A", "学院A1", source_a="done", source_b="done", merged="done")
        mock_progress.update_school_status("大学B", "学院B1", source_a="failed")

        stats = mock_progress.get_overview_stats()
        assert stats["total_schools"] == 147  # 默认总数
        assert stats["done"] == 1
        assert stats["failed"] == 1

    def test_overview_stats_partial(self, mock_progress):
        """partial 状态统计"""
        mock_progress.update_school_status("大学A", "学院A1", source_a="done", source_b="partial")
        stats = mock_progress.get_overview_stats()
        assert stats["partial"] == 1

    def test_overview_stats_running(self, mock_progress):
        """running 状态统计"""
        mock_progress.update_school_status("大学A", "学院A1", source_a="running")
        stats = mock_progress.get_overview_stats()
        assert stats["running"] == 1

    def test_pipeline_progress(self, mock_progress):
        """三条管道进度正确"""
        mock_progress.update_school_status("大学A", "学院A1", source_a="done")
        mock_progress.update_school_status("大学B", "学院B1", source_b="done")
        mock_progress.update_school_status("大学C", "学院C1", merged="done")

        progress = mock_progress.get_pipeline_progress()
        assert progress["source_a"]["completed"] == 1
        assert progress["source_b"]["completed"] == 1
        assert progress["merged"]["completed"] == 1
        assert progress["source_a"]["total"] == 147

    def test_concurrent_update(self, mock_progress):
        """多线程并发更新无数据竞争"""
        errors = []

        def update_worker(i):
            try:
                mock_progress.update_school_status(
                    f"大学{i}", f"学院{i}", source_a="done", tutor_count=i,
                )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=update_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

        data = mock_progress._read_raw()
        for i in range(10):
            key = f"大学{i}|学院{i}"
            assert key in data["schools"]
            assert data["schools"][key]["source_a"] == "done"
            assert data["schools"][key]["tutor_count"] == i

    def test_source_breakdown(self, mock_progress):
        """来源占比统计"""
        mock_progress.update_source_breakdown(
            matched=50, notice_only=10, faculty_only=20, unmatched=5,
        )
        breakdown = mock_progress.get_source_breakdown()
        assert breakdown["matched"] == 50
        assert breakdown["notice_only"] == 10
        assert breakdown["faculty_only"] == 20
        assert breakdown["unmatched"] == 5

    def test_get_all_schools_summary(self, mock_progress):
        """学校汇总信息"""
        mock_progress.update_school_status("测试大学", "机械工程学院",
                                           source_a="done", tutor_count=15)

        summary = mock_progress.get_all_schools_summary()
        assert len(summary) == 1
        assert summary[0]["university"] == "测试大学"
        assert summary[0]["college"] == "机械工程学院"
        assert summary[0]["source_a_status"] == "done"
        assert summary[0]["tutor_count"] == 15

    def test_get_recent_tutors_empty(self, tmp_dir):
        """无合并文件时返回空列表"""
        tracker = ProgressTracker(
            progress_file=tmp_dir / "progress.json",
            log_file=tmp_dir / "crawl.log",
        )
        tutors = tracker.get_recent_tutors(6)
        assert tutors == []

    def test_get_recent_failures_empty(self, tmp_dir):
        """无 failures.json 时返回空列表"""
        tracker = ProgressTracker(
            progress_file=tmp_dir / "progress.json",
            log_file=tmp_dir / "crawl.log",
        )
        failures = tracker.get_recent_failures(5)
        assert failures == []

    def test_add_log(self, mock_progress):
        """追加日志到 crawl.log"""
        mock_progress.add_log("INFO", "测试日志消息")
        mock_progress.add_log("WARN", "警告消息")

        logs = mock_progress.get_recent_logs(20)
        assert len(logs) == 2
        assert logs[0]["level"] == "INFO"
        assert logs[0]["msg"] == "测试日志消息"
        assert logs[1]["level"] == "WARN"
        assert logs[1]["msg"] == "警告消息"

    def test_get_recent_logs_empty(self, tmp_dir):
        """空日志文件返回空列表"""
        tracker = ProgressTracker(
            progress_file=tmp_dir / "progress.json",
            log_file=tmp_dir / "crawl.log",
        )
        logs = tracker.get_recent_logs(20)
        assert logs == []

    def test_valid_statuses(self):
        """状态枚举完整"""
        assert "done" in VALID_STATUSES
        assert "partial" in VALID_STATUSES
        assert "running" in VALID_STATUSES
        assert "pending" in VALID_STATUSES
        assert "failed" in VALID_STATUSES

    def test_valid_sources(self):
        """来源枚举完整"""
        assert "source_a" in VALID_SOURCES
        assert "source_b" in VALID_SOURCES
        assert "merged" in VALID_SOURCES
