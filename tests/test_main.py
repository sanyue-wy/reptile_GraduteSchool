# -*- coding: utf-8 -*-
"""
主入口模块单元测试
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from dataclasses import dataclass

import pytest


class TestCrawlTask:
    """CrawlTask dataclass 单测"""

    def test_key(self):
        """key 方法返回正确格式"""
        from main import CrawlTask
        task = CrawlTask(university="测试大学", college="机械学院", category="mechanical", source="source_a", year=2026)
        assert task.key() == "测试大学|机械学院|source_a"

    def test_key_with_force(self):
        """key 方法包含 force 字段不影响"""
        from main import CrawlTask
        task = CrawlTask(university="测试大学", college="机械学院", category="mechanical", source="source_a", year=2026, force=True)
        assert task.key() == "测试大学|机械学院|source_a"


class TestLoadSchoolConfigs:
    """load_school_configs 单测"""

    @patch("main.load_schools_config")
    def test_loads_configs(self, mock_load):
        """正常加载学校配置"""
        mock_load.return_value = [
            {"university": "测试大学", "categories": [{"college": "机械学院", "category": "mechanical"}]},
        ]
        from main import load_school_configs
        result = load_school_configs()
        assert "测试大学" in result
        assert result["测试大学"].university == "测试大学"

    @patch("main.load_schools_config")
    def test_empty_configs(self, mock_load):
        """空配置返回空 dict"""
        mock_load.return_value = []
        from main import load_school_configs
        result = load_school_configs()
        assert result == {}

    @patch("main.load_schools_config")
    def test_load_exception(self, mock_load):
        """加载异常时返回空 dict"""
        mock_load.side_effect = Exception("load failed")
        from main import load_school_configs
        result = load_school_configs()
        assert result == {}


class TestGetCollegeConfig:
    """get_college_config 单测"""

    def test_finds_config(self):
        """找到匹配的学院配置"""
        from main import get_college_config, SchoolConfig
        configs = {
            "测试大学": SchoolConfig(
                university="测试大学",
                categories=[
                    {"college": "机械学院", "category": "mechanical", "faculty": {"list_url": "http://test.edu.cn"}},
                    {"college": "自动化学院", "category": "automation"},
                ],
            )
        }
        result = get_college_config(configs, "测试大学", "mechanical")
        assert result is not None
        assert result["college"] == "机械学院"

    def test_category_not_found(self):
        """类别不存在返回 None"""
        from main import get_college_config, SchoolConfig
        configs = {
            "测试大学": SchoolConfig(
                university="测试大学",
                categories=[{"college": "机械学院", "category": "mechanical"}],
            )
        }
        result = get_college_config(configs, "测试大学", "automation")
        assert result is None

    def test_university_not_found(self):
        """学校不存在返回 None"""
        from main import get_college_config
        configs = {}
        result = get_college_config(configs, "不存在", "mechanical")
        assert result is None


class TestBuildTasks:
    """build_tasks 单测"""

    @patch("main.load_school_configs")
    @patch("main.get_progress_tracker")
    def test_builds_tasks_for_all(self, mock_get_progress, mock_load):
        """构建 __all__ 任务"""
        from main import build_tasks, SchoolConfig
        mock_load.return_value = {
            "测试大学": SchoolConfig(
                university="测试大学",
                categories=[
                    {"college": "机械学院", "category": "mechanical", "faculty": {"list_url": "http://a.com"}},
                    {"college": "自动化学院", "category": "automation", "faculty": {"list_url": "http://b.com"}},
                ],
            )
        }
        mock_get_progress.return_value.get_school_status.return_value = {"source_a": "pending", "source_b": "pending"}

        tasks = build_tasks(["__all__"], ["mechanical", "automation"], ["source_a"], 2026, False, False, False)
        assert len(tasks) >= 2  # mechanical + automation

    @patch("main.load_school_configs")
    def test_skips_source_a_without_url(self, mock_load):
        """source_a 缺少 list_url 时跳过"""
        from main import build_tasks, SchoolConfig
        from unittest.mock import MagicMock

        mock_load.return_value = {
            "测试大学": SchoolConfig(
                university="测试大学",
                categories=[
                    {"college": "机械学院", "category": "mechanical", "faculty": {"list_url": ""}},
                ],
            )
        }
        mock_get_progress = MagicMock()
        mock_get_progress.get_school_status.return_value = {"source_a": "pending", "source_b": "pending"}

        with patch("main.load_school_configs", mock_load), patch("main.get_progress_tracker", mock_get_progress):
            tasks = build_tasks(["测试大学"], ["mechanical"], ["source_a"], 2026, False, False, False)
        # 无 list_url 的 source_a 应被跳过
        assert len(tasks) == 0

    @patch("main.load_school_configs")
    def test_skips_source_b_when_disabled(self, mock_load):
        """source_b 未启用时跳过"""
        from main import build_tasks, SchoolConfig
        from unittest.mock import MagicMock

        mock_load.return_value = {
            "测试大学": SchoolConfig(
                university="测试大学",
                categories=[
                    {"college": "机械学院", "category": "mechanical", "faculty": {"list_url": "http://a.com"},
                     "notice": {"enabled": False}},
                ],
            )
        }
        mock_get_progress = MagicMock()
        mock_get_progress.get_school_status.return_value = {"source_a": "pending", "source_b": "pending"}

        with patch("main.load_school_configs", mock_load), patch("main.get_progress_tracker", mock_get_progress):
            tasks = build_tasks(["测试大学"], ["mechanical"], ["source_b"], 2026, False, False, False)
        assert len(tasks) == 0


class TestExecuteTask:
    """execute_task 单测"""

    @patch("main.run_source_a")
    @patch("main.run_source_b")
    @patch("main.run_merge")
    @patch("main.get_progress_tracker")
    @patch("main.add_failure")
    @patch("main.export_failures")
    @patch("main.Path")
    def test_execute_source_a_success(self, mock_path, mock_export_failures, mock_add_failure,
                                        mock_progress, mock_run_merge,
                                        mock_run_source_b, mock_run_source_a):
        """成功执行 source_a 任务"""
        from main import execute_task, CrawlTask
        from unittest.mock import MagicMock

        mock_run_source_a.return_value = [{"name": "张三", "title": "教授"}]
        mock_progress.return_value.get_school_status.return_value = {"source_a": "pending"}

        task = CrawlTask(university="测试大学", college="机械学院", category="mechanical", source="source_a", year=2026)
        session = MagicMock()
        progress = mock_progress()
        cache = MagicMock()

        # Mock Path for file operations
        mock_path_obj = MagicMock()
        mock_path_obj.__str__ = MagicMock(return_value="data/output/test.jsonl")
        mock_path_obj.parent = MagicMock()
        mock_path_obj.parent.mkdir = MagicMock()
        mock_path_obj.with_suffix = MagicMock(return_value=MagicMock())
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_path_obj.open = MagicMock(return_value=mock_file)
        mock_path.return_value = mock_path_obj

        success, error, error_type = execute_task(task, session, progress, cache)
        assert success is True
        assert error is None

    @patch("main.run_source_b")
    @patch("main.run_source_a")
    @patch("main.run_merge")
    @patch("main.get_progress_tracker")
    @patch("main.Path")
    def test_execute_source_b_disabled(self, mock_path, mock_run_merge, mock_run_source_a,
                                        mock_run_source_b, mock_progress):
        """source_b 未启用时返回空列表"""
        from main import execute_task, CrawlTask
        from unittest.mock import MagicMock

        mock_run_source_b.return_value = []
        mock_progress.return_value.get_school_status.return_value = {"source_b": "pending"}

        task = CrawlTask(university="测试大学", college="机械学院", category="mechanical", source="source_b", year=2026)
        session = MagicMock()
        progress = mock_progress()
        cache = MagicMock()

        mock_path_obj = MagicMock()
        mock_path.return_value = mock_path_obj

        success, error, error_type = execute_task(task, session, progress, cache)
        assert success is True
        assert error is None

    @patch("main.run_source_a")
    @patch("main.run_source_b")
    @patch("main.get_progress_tracker")
    def test_execute_skips_completed(self, mock_progress, mock_run_source_b, mock_run_source_a):
        """断点续抓跳过已完成任务"""
        from main import execute_task, CrawlTask
        from unittest.mock import MagicMock

        mock_progress.return_value.get_school_status.return_value = {"source_a": "done"}

        task = CrawlTask(university="测试大学", college="机械学院", category="mechanical", source="source_a", year=2026)
        session = MagicMock()
        cache = MagicMock()

        success, error, error_type = execute_task(task, session, mock_progress(), cache)
        assert success is True
        assert error is None

    @patch("main.run_source_a")
    @patch("main.run_source_b")
    @patch("main.add_failure")
    @patch("main.export_failures")
    @patch("main.get_progress_tracker")
    @patch("main.Path")
    def test_execute_blocked_error(self, mock_path, mock_progress, mock_export_failures, mock_add_failure,
                                    mock_run_source_b, mock_run_source_a):
        """BlockedError 处理"""
        from main import execute_task, CrawlTask, BlockedError
        from unittest.mock import MagicMock

        mock_run_source_a.side_effect = BlockedError("测试冷却")
        mock_progress.return_value.get_school_status.return_value = {"source_a": "pending"}

        task = CrawlTask(university="测试大学", college="机械学院", category="mechanical", source="source_a", year=2026)
        session = MagicMock()
        progress = mock_progress()
        cache = MagicMock()

        mock_path_obj = MagicMock()
        mock_path.return_value = mock_path_obj

        success, error, error_type = execute_task(task, session, progress, cache)
        assert success is False
        assert error is not None


class TestRunMerge:
    """run_merge 单测"""

    @patch("main.Path")
    @patch("main.merge_sources")
    @patch("main.json")
    @patch("main.get_progress_tracker")
    def test_run_merge_no_data(self, mock_progress, mock_json, mock_merge, mock_path):
        """无数据时返回空列表"""
        from main import run_merge
        from unittest.mock import MagicMock

        mock_path.return_value.exists.return_value = False
        mock_progress.return_value.update_school_status = MagicMock()

        result = run_merge("测试大学", "机械学院", 2026, mock_progress())
        assert result == []

    @patch("builtins.open")
    @patch("main.merge_sources")
    @patch("main.json")
    @patch("main.get_progress_tracker")
    def test_run_merge_with_data(self, mock_progress, mock_json, mock_merge, mock_open):
        """有数据时执行合并"""
        from main import run_merge
        from unittest.mock import MagicMock

        # Mock open to return test data
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read.return_value = '{"name": "张三"}\n'
        mock_open.return_value = mock_file

        mock_json.loads.return_value = {"name": "张三"}
        mock_merge.return_value = {"total": 1, "merged": 1, "partial_faculty": 0, "partial_notice": 0}
        mock_progress.return_value.update_school_status = MagicMock()
        mock_progress.return_value.update_source_breakdown = MagicMock()

        result = run_merge("测试大学", "机械学院", 2026, mock_progress())
        assert isinstance(result, list)


class TestMainCLIParsing:
    """main() argparse 解析单测"""

    @patch("main.logger")
    @patch("main.validate_all_configs")
    @patch("main.load_schools_config")
    def test_main_with_no_tasks(self, mock_load, mock_validate, mock_logger):
        """无任务时正常退出"""
        from main import main
        from unittest.mock import MagicMock, patch
        import sys

        mock_load.return_value = []
        mock_validate.return_value = {"summary": {"errors": 0, "warnings": 0, "ok": 0}, "errors": [], "warnings": []}

        # 模拟 args.school=None, 但使用默认 __all__
        with patch.object(sys, "argv", ["main.py"]), \
             patch("main.build_tasks", return_value=[]), \
             patch("main.get_progress_tracker"), \
             patch("main.Path.mkdir"), \
             patch("main.concurrent.futures.ThreadPoolExecutor") as mock_executor, \
             patch("main.export_summary"), \
             patch("main.export_merged"):
            try:
                main()
            except SystemExit:
                pass

    @patch("main.logger")
    @patch("main.validate_all_configs")
    @patch("main.load_schools_config")
    def test_main_with_config_errors(self, mock_load, mock_validate, mock_logger):
        """配置校验有错误时退出"""
        from main import main
        import sys

        mock_load.return_value = [{"university": "测试", "categories": []}]
        mock_validate.return_value = {
            "summary": {"errors": 1, "warnings": 0, "ok": 0},
            "errors": [MagicMock()],
            "warnings": [],
        }

        with patch.object(sys, "argv", ["main.py"]), \
             patch("main.build_tasks", return_value=[]), \
             patch("main.get_progress_tracker"), \
             patch("main.Path.mkdir"):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestCircuitBreaker:
    """CircuitBreaker 单测"""

    def test_initial_state(self):
        """初始状态未熔断"""
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=3)
        assert not cb.is_tripped("example.com")
        assert len(cb.tripped_domains) == 0

    def test_record_below_threshold(self):
        """未达阈值不触发熔断"""
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=5)
        for _ in range(4):
            assert not cb.record("example.com", "timeout")
        assert not cb.is_tripped("example.com")

    def test_record_at_threshold(self):
        """达到阈值触发熔断"""
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=3)
        assert not cb.record("example.com", "timeout")
        assert not cb.record("example.com", "timeout")
        assert cb.record("example.com", "timeout") is True
        assert cb.is_tripped("example.com")

    def test_dns_error_fast_trip(self):
        """DNS 错误立即熔断，不做计数等待"""
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=5)
        assert cb.record("bad.example", "dns_error") is True
        assert cb.is_tripped("bad.example")

    def test_different_domains_independent(self):
        """不同域名独立计数"""
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=3)
        for _ in range(3):
            cb.record("example.com", "timeout")
        assert cb.is_tripped("example.com")
        assert not cb.is_tripped("other.com")

    def test_reset(self):
        """reset 恢复状态"""
        from main import CircuitBreaker
        cb = CircuitBreaker(threshold=3)
        for _ in range(3):
            cb.record("example.com", "timeout")
        assert cb.is_tripped("example.com")
        cb.reset("example.com")
        assert not cb.is_tripped("example.com")

    def test_extract_domain(self):
        """_extract_domain 正确提取域名"""
        from main import _extract_domain
        assert _extract_domain("http://me.seu.edu.cn/path") == "me.seu.edu.cn"
        assert _extract_domain("https://example.com") == "example.com"
        assert _extract_domain("") == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
