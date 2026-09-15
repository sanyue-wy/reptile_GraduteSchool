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

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 进度文件路径
PROGRESS_FILE = Path("data/output/progress.json")
LOG_FILE = Path("data/output/crawl.log")

# 状态枚举
VALID_STATUSES = {"done", "partial", "running", "pending", "failed"}
VALID_SOURCES = {"source_a", "source_b", "merged"}


class ProgressTracker:
    """进度追踪器，线程安全。"""

    def __init__(self, progress_file: Path = PROGRESS_FILE, log_file: Path = LOG_FILE):
        self.progress_file = progress_file
        self.log_file = log_file
        self._lock = threading.Lock()
        self._cache: Optional[dict] = None
        self._cache_time = 0
        self._cache_ttl = 1.0  # 秒

        # 确保目录存在
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # 初始化文件
        if not self.progress_file.exists():
            self._write_raw(self._default_structure())
        if not self.log_file.exists():
            self.log_file.write_text("", encoding="utf-8")

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _default_structure(self) -> dict:
        """默认进度结构。"""
        return {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "schools": {},  # key: "大学|学院" -> {source_a, source_b, merged, last_crawl_at, tutor_count}
            "pipelines": {
                "source_a": {"completed": 0, "total": 147},
                "source_b": {"completed": 0, "total": 147},
                "merged": {"completed": 0, "total": 147},
            },
            "source_breakdown": {
                "matched": 0,
                "notice_only": 0,
                "faculty_only": 0,
                "unmatched": 0,
            },
        }

    def _read_raw(self) -> dict:
        """读取原始 JSON（带缓存）。"""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        with self._lock:
            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                data = self._default_structure()
            self._cache = data
            self._cache_time = now
            return data

    def _write_raw(self, data: dict) -> None:
        """原子写入：写临时文件再 rename。"""
        data["updated_at"] = datetime.now().isoformat()
        with self._lock:
            tmp = self.progress_file.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.progress_file)
            self._cache = data
            self._cache_time = time.time()

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
        data = self._read_raw()
        key = self._school_key(university, college)
        school = data["schools"].get(
            key,
            {
                "source_a": "pending",
                "source_b": "pending",
                "merged": "pending",
                "last_crawl_at": "",
                "tutor_count": 0,
            },
        )
        if source_a is not None:
            school["source_a"] = source_a
        if source_b is not None:
            school["source_b"] = source_b
        if merged is not None:
            school["merged"] = merged
        if tutor_count is not None:
            school["tutor_count"] = tutor_count
        if any(v is not None for v in (source_a, source_b, merged, tutor_count)):
            school["last_crawl_at"] = datetime.now().isoformat()
        data["schools"][key] = school
        self._recalc_pipelines(data)
        self._write_raw(data)

    def _recalc_pipelines(self, data: dict) -> None:
        """根据 schools 重新计算三条管道进度。"""
        total = 147  # 双一流高校总数，后续可从配置读取
        counts = {"source_a": 0, "source_b": 0, "merged": 0}
        for school in data["schools"].values():
            for src in ("source_a", "source_b", "merged"):
                if school.get(src) == "done":
                    counts[src] += 1
        for src in counts:
            data["pipelines"][src]["completed"] = counts[src]
            data["pipelines"][src]["total"] = total

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
        data = self._read_raw()
        data["source_breakdown"] = {
            "matched": matched,
            "notice_only": notice_only,
            "faculty_only": faculty_only,
            "unmatched": unmatched,
        }
        self._write_raw(data)

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
                with open(f, "r", encoding="utf-8") as fp:
                    for line in fp:
                        line = line.strip()
                        if not line:
                            continue
                        rec = json.loads(line)
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
            with open(failures_file, "r", encoding="utf-8") as f:
                data = json.load(f)
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
        with self._lock:
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