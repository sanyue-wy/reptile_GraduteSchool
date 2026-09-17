# -*- coding: utf-8 -*-
"""
进度追踪模块
============
管理 data/output/progress.json 的原子读写，提供：
- 学校/学院级别的采集状态维护
- 三条管道（Source A / Source B / 合并）的整体进度聚合
- 运行日志的追加与尾部读取
- 线程安全操作
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from storage import JSONLStore, ProgressStore, path_lock, read_json
from storage.progress_store import default_structure, recalc_pipelines

logger = logging.getLogger(__name__)

# 进度文件路径
PROGRESS_FILE = Path("data/output/progress.json")
LOG_FILE = Path("data/output/crawl.log")

# 状态枚举
VALID_STATUSES = {"done", "partial", "running", "pending", "failed"}
VALID_SOURCES = {"source_a", "source_b", "merged"}


class ProgressTracker:
    """进度追踪器，线程安全。"""

    def __init__(self, progress_file: Path = PROGRESS_FILE, log_file: Path = LOG_FILE, cache_ttl: float = 1.0):
        self.progress_file = Path(progress_file)
        self.log_file = Path(log_file)
        self._store = ProgressStore(self.progress_file, cache_ttl=cache_ttl)
        # Shared reentrant thread lock: nested store calls cannot deadlock.
        self._lock = self._store._lock

        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._store.initialize()
        with path_lock(self.log_file):
            self.log_file.touch(exist_ok=True)

    # Compatibility aliases for callers that invalidate/tune the old cache.
    @property
    def _cache(self):
        from copy import deepcopy
        return deepcopy(self._store._cache)

    @_cache.setter
    def _cache(self, value):
        from copy import deepcopy
        with self._lock:
            self._store._cache = deepcopy(value)

    @property
    def _cache_time(self):
        return self._store._cache_time

    @_cache_time.setter
    def _cache_time(self, value):
        self._store._cache_time = value

    @property
    def _cache_ttl(self):
        return self._store._cache_ttl

    @_cache_ttl.setter
    def _cache_ttl(self, value):
        self._store._cache_ttl = value

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _default_structure(self) -> dict:
        """默认进度结构（version=1，三条流水线总数均为147）。"""
        return default_structure()

    def _read_raw(self) -> dict:
        """读取独立的进度快照，外部修改不会污染缓存。"""
        return self._store.load()

    def _write_raw(self, data: dict) -> None:
        """兼容完整快照写入；读改写操作应使用 store.transaction。"""
        self._store.save(data)

    def _school_key(self, university: str, college: str) -> str:
        return f"{university}|{college}"

    # ------------------------------------------------------------------
    # 学校状态维护
    # ------------------------------------------------------------------

    def get_school_status(
        self, university: str, college: str
    ) -> dict[str, str]:
        """获取单个学校/学院的状态。"""
        data = self._read_raw()
        key = self._school_key(university, college)
        return data["schools"].get(
            key,
            {
                "source_a": "pending",
                "source_b": "pending",
                "merged": "pending",
                "last_crawl_at": "",
                "tutor_count": 0,
            },
        )

    def update_school_status(
        self,
        university: str,
        college: str,
        *,
        source_a: Optional[str] = None,
        source_b: Optional[str] = None,
        merged: Optional[str] = None,
        tutor_count: Optional[int] = None,
    ) -> None:
        """更新学校/学院状态（部分字段可选）。"""
        self._store.update_school_status(
            university, college, source_a=source_a, source_b=source_b,
            merged=merged, tutor_count=tutor_count,
        )

    def _recalc_pipelines(self, data: dict) -> None:
        """根据 schools 重新计算三条管道进度。"""
        recalc_pipelines(data)

    # ------------------------------------------------------------------
    # 概览统计（供 /api/overview 使用）
    # ------------------------------------------------------------------

    def get_overview_stats(self) -> dict:
        """返回首页统计卡片数据。"""
        data = self._read_raw()
        stats = {"total_schools": 147, "done": 0, "running": 0, "failed": 0, "partial": 0, "pending": 0}
        for school in data["schools"].values():
            # 学校整体状态：以最差状态为准
            statuses = {school.get("source_a", "pending"), school.get("source_b", "pending"), school.get("merged", "pending")}
            if "failed" in statuses:
                overall = "failed"
            elif "running" in statuses:
                overall = "running"
            elif "partial" in statuses:
                overall = "partial"
            elif "pending" in statuses and len(statuses) == 1:
                overall = "pending"
            else:
                overall = "done"
            stats[overall] = stats.get(overall, 0) + 1
        return stats

    def get_pipeline_progress(self) -> dict:
        """返回三条管道进度。"""
        data = self._read_raw()
        return data["pipelines"]

    def get_source_breakdown(self) -> dict:
        """返回导师维度数据来源占比。"""
        data = self._read_raw()
        return data["source_breakdown"]

    def update_source_breakdown(self, matched: int, notice_only: int, faculty_only: int, unmatched: int) -> None:
        """更新来源占比统计。"""
        def update(data):
            data["source_breakdown"] = {
                "matched": matched,
                "notice_only": notice_only,
                "faculty_only": faculty_only,
                "unmatched": unmatched,
            }
        self._store.transaction(update)

    # ------------------------------------------------------------------
    # 最近记录（供 /api/overview 使用）
    # ------------------------------------------------------------------

    def get_recent_tutors(self, limit: int = 6) -> list[dict]:
        """从最新的合并 JSONL 文件中取最近的导师记录。"""
        output_dir = self.progress_file.parent
        if not output_dir.exists():
            return []

        # 找最新的 *_*.jsonl 文件
        jsonl_files = sorted(output_dir.glob("*_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        tutors = []
        for f in jsonl_files:
            if len(tutors) >= limit:
                break
            try:
                for rec in JSONLStore(f).read_all():
                    tutors.append({
                        "name": rec.get("name", ""),
                        "title": rec.get("title", ""),
                        "level": rec.get("advisor_level", ""),
                        "school": rec.get("university", ""),
                        "college": rec.get("college", ""),
                        "areas": rec.get("research_areas", []),
                    })
                    if len(tutors) >= limit:
                        break
            except Exception as e:
                logger.warning("读取导师文件失败 %s: %s", f, e)
        return tutors[:limit]

    def get_recent_failures(self, limit: int = 5) -> list[dict]:
        """从 failures.json 读取最近失败记录。"""
        failures_file = self.log_file.parent / "failures.json"
        if not failures_file.exists():
            return []
        try:
            data = read_json(failures_file, {})
            items = data.get("items", [])
            return items[:limit]
        except Exception as e:
            logger.warning("读取失败记录失败: %s", e)
            return []

    def get_recent_logs(self, limit: int = 20) -> list[dict]:
        """读取 crawl.log 尾部 N 行。"""
        if not self.log_file.exists():
            return []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            logs = []
            for line in lines[-limit:]:
                line = line.strip()
                if not line:
                    continue
                # 解析格式: 2026-09-14 16:02:31,123 - INFO - message
                parts = line.split(" - ", 2)
                if len(parts) == 3:
                    time_str, level, msg = parts
                    logs.append({
                        "time": time_str.strip(),
                        "level": level.strip(),
                        "msg": msg.strip(),
                    })
            return logs
        except Exception as e:
            logger.warning("读取日志失败: %s", e)
            return []

    # ------------------------------------------------------------------
    # 日志追加
    # ------------------------------------------------------------------

    def add_log(self, level: str, msg: str) -> None:
        """追加一条日志到 crawl.log（供爬虫进程调用）。"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
        line = f"{timestamp} - {level.upper()} - {msg}\n"
        with path_lock(self.log_file):
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line)

    # ------------------------------------------------------------------
    # 学校列表聚合（供 /api/schools 使用）
    # ------------------------------------------------------------------

    def get_all_schools_summary(self) -> list[dict]:
        """返回所有学校的汇总信息（用于列表页）。"""
        data = self._read_raw()
        # 从 config/schools.py 读取完整学校列表，这里只返回有进度的
        # 实际 API 会合并配置列表和进度数据
        result = []
        for key, school in data["schools"].items():
            if "|" in key:
                uni, college = key.split("|", 1)
            else:
                uni, college = key, ""
            statuses = {school.get("source_a", "pending"), school.get("source_b", "pending"), school.get("merged", "pending")}
            if "failed" in statuses:
                overall = "failed"
            elif "running" in statuses:
                overall = "running"
            elif "partial" in statuses:
                overall = "partial"
            elif "pending" in statuses and len(statuses) == 1:
                overall = "pending"
            else:
                overall = "done"
            result.append({
                "key": key,
                "university": uni,
                "college": college,
                "source_a_status": school.get("source_a", "pending"),
                "source_b_status": school.get("source_b", "pending"),
                "merged_status": school.get("merged", "pending"),
                "tutor_count": school.get("tutor_count", 0),
                "last_crawl_at": school.get("last_crawl_at", ""),
                "status": overall,
            })
        return result


# 全局单例
_progress_tracker: Optional[ProgressTracker] = None


def get_progress_tracker() -> ProgressTracker:
    """获取全局进度追踪器实例。"""
    global _progress_tracker
    if _progress_tracker is None:
        _progress_tracker = ProgressTracker()
    return _progress_tracker