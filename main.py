#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主入口：爬虫编排器
==================
功能：
- CLI 参数解析（学校、学院、数据源、年份、线程数、断点续抓、失败重试）
- 任务队列构建与去重
- ThreadPoolExecutor 并发执行
- 进度追踪（progress.json）与失败记录（failures.json）
- 完成后自动触发合并导出（summary.xlsx + 分校 JSONL）
"""

import argparse
import concurrent.futures
import json
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# 确保能导入本地模块
sys.path.insert(0, str(Path(__file__).parent))

from config.loader import load_schools_config, get_school_config
from config.validator import validate_all_configs
from parsers import dispatch
from pipelines.export import (
    export_merged,
    export_summary,
    export_failures,
    add_failure,
    load_failures,
    get_active_failures,
)
from pipelines.merge import merge_sources
from spiders.ajax_api import fetch_faculty_via_api
from spiders.detail_parser import fetch_detail
from spiders.static_list import fetch_faculty_list, parse_faculty_html
from utils.cache import CrawlCache
from utils.http import PoliteSession, BlockedError, MaxRetriesExceeded
from utils.progress import get_progress_tracker, ProgressTracker
from utils.errors import classify_error

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/output/crawl.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 数据结构
# ------------------------------------------------------------------


@dataclass
class CrawlTask:
    """单个采集任务。"""
    university: str
    college: str
    category: str  # mechanical / automation
    source: str    # source_a / source_b
    year: int
    force: bool = False
    config: dict = field(default_factory=dict)

    def key(self) -> str:
        return f"{self.university}|{self.college}|{self.source}"


@dataclass
class SchoolConfig:
    """学校配置（从 config/schools.py 读取）。"""
    university: str
    categories: list[dict]  # 每项包含 college, category, faculty, notice


# ------------------------------------------------------------------
# 同因熔断器（Circuit Breaker）
# ------------------------------------------------------------------

class CircuitBreaker:
    """同因熔断：当同一 (domain, error_class) 在窗口内累计失败 ≥ K 次时，挂起该 domain。"""

    def __init__(self, threshold: int = 5, window_size: int = 100):
        self.threshold = threshold
        self.window_size = window_size
        self._history: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._tripped_domains: set[str] = set()

    def record(self, domain: str, error_class: str) -> bool:
        """记录一次失败。返回 True 表示已触发熔断。"""
        if domain in self._tripped_domains:
            return True
        key = (domain, error_class)
        now = time.time()
        self._history[key].append(now)
        cutoff = now - 3600
        self._history[key] = [t for t in self._history[key] if t > cutoff]
        if len(self._history[key]) > self.window_size:
            self._history[key] = self._history[key][-self.window_size:]
        if len(self._history[key]) >= self.threshold:
            self._tripped_domains.add(domain)
            logger.warning(
                "同因熔断触发: domain=%s error_class=%s 累计 %d 次失败，已挂起",
                domain, error_class, len(self._history[key]),
            )
            return True
        return False

    def is_tripped(self, domain: str) -> bool:
        return domain in self._tripped_domains

    def reset(self, domain: str):
        self._tripped_domains.discard(domain)
        keys_to_remove = [k for k in self._history if k[0] == domain]
        for k in keys_to_remove:
            del self._history[k]

    @property
    def tripped_domains(self) -> set[str]:
        return self._tripped_domains.copy()


def _extract_domain(url: str) -> str:
    """从 URL 中提取域名。"""
    from urllib.parse import urlparse
    return urlparse(url).netloc if url else ""


# ------------------------------------------------------------------
# 配置加载
# ------------------------------------------------------------------


def load_school_configs() -> dict[str, SchoolConfig]:
    """从 config/loader.py 加载所有学校配置。"""
    try:
        configs = load_schools_config()
    except Exception as e:
        logger.warning("加载学校配置失败: %s，使用空配置", e)
        return {}

    configs_dict = {}
    for item in configs:
        configs_dict[item["university"]] = SchoolConfig(
            university=item["university"],
            categories=item["categories"],
        )
    return configs_dict


def get_college_config(configs: dict[str, SchoolConfig], university: str, category: str) -> Optional[dict]:
    """获取指定学校、学科的学院配置。"""
    sc = configs.get(university)
    if not sc:
        return None
    for cat in sc.categories:
        if cat["category"] == category:
            return cat
    return None


# ------------------------------------------------------------------
# 单任务执行
# ------------------------------------------------------------------


def run_source_a(
    task: CrawlTask,
    session: PoliteSession,
    progress: ProgressTracker,
    cache: Optional[CrawlCache] = None,
) -> list[dict]:
    """执行 Source A（官网师资页）采集。"""
    university = task.university
    college = task.college
    category = task.category
    config = task.config

    # 缓存命中统计：进入本函数前的 hits 数
    cache_hits_before = cache.stats["hits"] if cache else 0

    faculty_cfg = config.get("faculty", {})
    list_type = faculty_cfg.get("list_type", "static_html")
    list_url = faculty_cfg.get("list_url", "")
    selectors = faculty_cfg.get("detail_selectors", {})

    if not list_url:
        raise ValueError(f"{university}/{college} 缺少 Source A 列表页 URL")

    logger.info("【Source A】开始采集 %s / %s", university, college)
    progress.add_log("INFO", f"{university}/{college} Source A 开始采集")

    # 1. 获取列表页教师基础信息
    if list_type == "ajax_api":
        # AJAX API 模式（如 SudyCMS）
        api_url = list_url
        site_id = faculty_cfg.get("api_params", {}).get("siteId")
        referer = faculty_cfg.get("referer", list_url)
        extra_params = faculty_cfg.get("api_params", {})
        teachers = fetch_faculty_via_api(
            session, api_url, site_id, referer, extra_params,
            cache=cache, force=task.force,
        )
    else:
        # 静态 HTML 模式
        teachers = fetch_faculty_list(session, list_url, {
            "item": faculty_cfg.get("list_item_selector", "li"),
            "name": "title",
            "profile": "href",
            "research": faculty_cfg.get("list_research_selector", ""),
        }, cache=cache, force=task.force)

    # 缓存加速日志
    if cache is not None:
        hits = cache.stats["hits"] - cache_hits_before
        if hits > 0:
            logger.info("【Source A】%s / %s 本次命中缓存 %d 次，跳过网络请求", university, college, hits)
            progress.add_log("INFO", f"{university}/{college} Source A 缓存命中 {hits} 次，刷新速度加快")

    logger.info("【Source A】列表页获取 %d 位教师", len(teachers))
    progress.add_log("INFO", f"{university}/{college} Source A 列表页获取 {len(teachers)} 条记录")

    # 2. 详情页解析（丰富字段）
    enriched = []
    for i, teacher in enumerate(teachers, 1):
        profile_url = teacher.get("profile_url", "")
        if not profile_url:
            enriched.append(teacher)
            continue

        try:
            detail = fetch_detail(
                session, profile_url, detail_type="auto", selectors=selectors,
                cache=cache, force=task.force,
            )
            # 合并：优先保留列表页已有字段
            merged_teacher = {**teacher, **detail}
            merged_teacher["university"] = university
            merged_teacher["college"] = college
            merged_teacher["category"] = category
            merged_teacher["source_type"] = "官网师资页"
            merged_teacher["raw_ref"] = f"data/raw/{university}/{profile_url.split('/')[-1]}"
            enriched.append(merged_teacher)
        except Exception as e:
            logger.warning("详情页解析失败 %s: %s", profile_url, e)
            progress.add_log("WARN", f"{university}/{college} 详情页解析失败 {teacher.get('name')}: {e}")
            teacher["university"] = university
            teacher["college"] = college
            teacher["category"] = category
            teacher["source_type"] = "官网师资页"
            enriched.append(teacher)

        # 进度日志
        if i % 20 == 0:
            progress.add_log("INFO", f"{university}/{college} 详情页解析：{i}/{len(teachers)} 成功")

    logger.info("【Source A】完成 %s / %s，共 %d 位导师", university, college, len(enriched))
    progress.add_log("INFO", f"{university}/{college} Source A 完成，获取 {len(enriched)} 条导师记录")
    return enriched


def run_source_b(
    task: CrawlTask,
    session: PoliteSession,
    progress: ProgressTracker,
    cache: Optional[CrawlCache] = None,
) -> list[dict]:
    """执行 Source B（研招网专业目录）采集。

    流程：
    1. 读取 notice 配置 → 检查 enabled / school_code / major_codes
    2. 实例化 YzwClient（复用 PoliteSession + CrawlCache）
    3. 自动查找学校代码（配置优先）
    4. 抓取专业目录（分页 + 原件落盘）
    5. 调用 parsers.yzw_major.parse() 解析为统一 Schema
    6. 返回记录列表（由 execute_task 写入 _notice.jsonl）
    """
    university = task.university
    college = task.college
    category = task.category
    config = task.config

    notice_cfg = config.get("notice", {})
    if not notice_cfg.get("enabled", False):
        logger.info("【Source B】%s / %s 未启用研招网采集", university, college)
        return []

    logger.info("【Source B】开始采集 %s / %s（研招网）", university, college)
    progress.add_log("INFO", f"{university}/{college} Source B 开始采集")

    # 复用 caller 提供的缓存，避免重复创建
    if cache is None:
        cache = CrawlCache(max_age_days=7)

    from spiders.yzw_api import YzwClient
    client = YzwClient(session, cache=cache)

    # 学校代码：配置优先，无则自动查找
    school_code = notice_cfg.get("school_code") or client.get_school_code(task.university)
    if not school_code:
        raise ValueError(f"无法获取 {task.university} 研招网学校代码")

    logger.info("【Source B】学校代码: %s", school_code)

    # 专业代码白名单（可选）
    major_codes = notice_cfg.get("major_codes", {}).get(task.category, None)

    # 抓取专业目录（自动分页 + 原件落盘）
    raw_records = client.fetch_major_directory(
        school_code, task.year, major_codes,
        category=task.category, university=task.university,
    )
    logger.info("【Source B】获取 %d 条原始专业记录", len(raw_records))

    # 解析为统一 Schema（通过统一入口 dispatch 路由，无需直引入具体 parser）
    template = notice_cfg.get("template", "yzw_major")
    meta = {
        "university": task.university,
        "college": task.college,
        "category": task.category,
        "year": task.year,
        "school_code": school_code,
        "template": template,
        "major_codes": major_codes,
    }
    raw_path = f"data/raw/{task.university}/{task.year}/yzw/major_{school_code}.json"
    parsed = dispatch(raw_path, meta)

    logger.info("【Source B】完成 %s / %s，解析 %d 位导师记录", university, college, len(parsed))
    progress.add_log("INFO", f"{university}/{college} Source B 完成，解析 {len(parsed)} 条导师记录")

    return parsed


def run_merge(university: str, college: str, year: int, progress: ProgressTracker) -> list[dict]:
    """对单个学校/学院执行多源合并并导出。"""
    faculty_path = Path(f"data/output/{university}_{college}_faculty.jsonl")
    notice_path = Path(f"data/output/{university}_{college}_notice.jsonl")
    output_path = Path(f"data/output/{university}_{college}.jsonl")

    # 读取现有 faculty 数据（如果有）
    faculty_records = []
    if faculty_path.exists():
        with open(faculty_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    faculty_records.append(json.loads(line))

    # 读取现有 notice 数据（如果有）
    notice_records = []
    if notice_path.exists():
        with open(notice_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    notice_records.append(json.loads(line))

    if not faculty_records and not notice_records:
        logger.warning("无数据可合并：%s / %s", university, college)
        return []

    # 执行合并
    stats = merge_sources(
        str(faculty_path) if faculty_records else "",
        str(notice_path) if notice_records else "",
        str(output_path),
        fuzzy_threshold=0.85,
    )

    # 读取合并结果
    merged = []
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    merged.append(json.loads(line))

    # 更新进度
    progress.update_school_status(
        university, college,
        merged="done" if merged else "pending",
        tutor_count=len(merged),
    )
    progress.update_source_breakdown(
        stats.get("merged", 0),
        stats.get("partial_notice", 0),
        stats.get("partial_faculty", 0),
        0,  # unmatched 暂不统计
    )

    logger.info("合并完成：%s / %s，%s", university, college, stats)
    progress.add_log("INFO", f"{university}/{college} 合并完成：merged {stats.get('merged',0)} / partial_faculty {stats.get('partial_faculty',0)} / partial_notice {stats.get('partial_notice',0)}")

    return merged


def execute_task(
    task: CrawlTask,
    session: PoliteSession,
    progress: ProgressTracker,
    cache: Optional[CrawlCache] = None,
) -> tuple[bool, Optional[str], str]:
    """
    执行单个采集任务。

    Returns:
        (success: bool, error_message: str|None, error_type: str)
    """
    university = task.university
    college = task.college
    source = task.source

    # 检查是否已完成（断点续抓）
    if not task.force:
        status = progress.get_school_status(university, college)
        if source == "source_a" and status.get("source_a") == "done":
            logger.info("跳过已完成：%s / %s Source A", university, college)
            return True, None, "none"
        if source == "source_b" and status.get("source_b") == "done":
            logger.info("跳过已完成：%s / %s Source B", university, college)
            return True, None, "none"

    try:
        if source == "source_a":
            records = run_source_a(task, session, progress, cache=cache)
            # 保存中间结果
            faculty_path = Path(f"data/output/{university}_{college}_faculty.jsonl")
            faculty_path.parent.mkdir(parents=True, exist_ok=True)
            with open(faculty_path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            progress.update_school_status(university, college, source_a="done", tutor_count=len(records))
        elif source == "source_b":
            records = run_source_b(task, session, progress, cache=cache)
            notice_path = Path(f"data/output/{university}_{college}_notice.jsonl")
            notice_path.parent.mkdir(parents=True, exist_ok=True)
            with open(notice_path, "w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            progress.update_school_status(university, college, source_b="done")
        else:
            raise ValueError(f"未知数据源: {source}")

        # 执行合并
        run_merge(university, college, task.year, progress)
        return True, None, "none"

    except BlockedError as e:
        err_msg = f"域名被反爬冷却: {e}"
        logger.error(err_msg)
        progress.add_log("ERROR", f"{university}/{college} {source} {err_msg}")
        error_type = classify_error(e)
        failure = add_failure(
            failure_id=f"fail_{university}_{college}_{source}_{int(time.time())}",
            school=university,
            college=college,
            source="Source A" if source == "source_a" else "Source B",
            error_type=error_type,
            error_message=str(e),
            url=task.config.get("faculty", {}).get("list_url", ""),
        )
        export_failures(load_failures() + [failure])
        progress.update_school_status(university, college, **{source: "failed"})
        return False, err_msg, error_type

    except MaxRetriesExceeded as e:
        err_msg = f"达到最大重试次数: {e}"
        logger.error(err_msg)
        progress.add_log("ERROR", f"{university}/{college} {source} {err_msg}")
        error_type = classify_error(e)
        failure = add_failure(
            failure_id=f"fail_{university}_{college}_{source}_{int(time.time())}",
            school=university,
            college=college,
            source="Source A" if source == "source_a" else "Source B",
            error_type=error_type,
            error_message=str(e),
            url=task.config.get("faculty", {}).get("list_url", ""),
        )
        export_failures(load_failures() + [failure])
        progress.update_school_status(university, college, **{source: "failed"})
        return False, err_msg, error_type

    except Exception as e:
        err_msg = f"采集异常: {e}"
        logger.exception(err_msg)
        progress.add_log("ERROR", f"{university}/{college} {source} {err_msg}")
        error_type = classify_error(e)
        failure = add_failure(
            failure_id=f"fail_{university}_{college}_{source}_{int(time.time())}",
            school=university,
            college=college,
            source="Source A" if source == "source_a" else "Source B",
            error_type=error_type,
            error_message=str(e),
            url=task.config.get("faculty", {}).get("list_url", ""),
        )
        export_failures(load_failures() + [failure])
        progress.update_school_status(university, college, **{source: "failed"})
        return False, err_msg, error_type


# ------------------------------------------------------------------
# 任务队列构建
# ------------------------------------------------------------------


def build_tasks(
    schools: list[str],
    categories: list[str],
    sources: list[str],
    year: int,
    force: bool,
    resume: bool,
    retry_failed: bool,
) -> list[CrawlTask]:
    """构建任务队列。"""
    configs = load_school_configs()
    tasks = []

    # 处理 "__all__" 特殊值
    if schools == ["__all__"]:
        target_schools = list(configs.keys())
    else:
        target_schools = schools

    for uni in target_schools:
        sc = configs.get(uni)
        if not sc:
            logger.warning("学校 %s 无配置，跳过", uni)
            continue

        for cat_config in sc.categories:
            category = cat_config["category"]
            if categories and category not in categories:
                continue

            college = cat_config["college"]
            for source in sources:
                # 检查该源是否配置
                if source == "source_a" and not cat_config.get("faculty", {}).get("list_url"):
                    continue
                if source == "source_b" and not cat_config.get("notice", {}).get("enabled", False):
                    continue

                task = CrawlTask(
                    university=uni,
                    college=college,
                    category=category,
                    source=source,
                    year=year,
                    force=force,
                    config=cat_config,
                )
                tasks.append(task)

    # 断点续抓：过滤掉已完成的
    if resume and not force and not retry_failed:
        progress = get_progress_tracker()
        filtered = []
        for task in tasks:
            status = progress.get_school_status(task.university, task.college)
            src_status = status.get(task.source, "pending")
            if src_status != "done":
                filtered.append(task)
            else:
                logger.info("断点续抓跳过：%s / %s %s", task.university, task.college, task.source)
        tasks = filtered

    # 失败重试模式
    if retry_failed:
        active_failures = get_active_failures()
        retry_tasks = []
        for fail in active_failures:
            # 根据失败记录重建任务
            source = "source_a" if fail["source"] == "Source A" else "source_b"
            for t in tasks:
                if t.university == fail["school"] and t.college == fail["college"] and t.source == source:
                    retry_tasks.append(t)
                    break
        tasks = retry_tasks
        logger.info("失败重试模式：共 %d 个任务", len(tasks))

    return tasks


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="双一流高校研究生导师信息采集系统")
    parser.add_argument("--school", nargs="+", help="目标学校列表，用空格分隔；传 '__all__' 表示全部")
    parser.add_argument("--category", nargs="+", default=["mechanical", "automation"], help="学科分类")
    parser.add_argument("--source", nargs="+", default=["source_a", "source_b"], help="数据源")
    parser.add_argument("--year", type=int, default=datetime.now().year, help="数据年份")
    parser.add_argument("--workers", type=int, default=4, help="并发线程数")
    parser.add_argument("--force", action="store_true", help="强制重新采集已完成的")
    parser.add_argument("--resume", action="store_true", help="断点续抓（跳过已完成）")
    parser.add_argument("--retry-failed", action="store_true", help="重试所有失败项")
    parser.add_argument("--delay", type=float, nargs=2, default=[1.0, 3.0], help="请求延迟范围（秒）")
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")
    parser.add_argument("--timeout", type=int, default=30, help="连接超时（秒）")
    parser.add_argument("--cooldown-threshold", type=int, default=5, help="反爬冷却阈值")
    parser.add_argument("--cooldown-seconds", type=int, default=1800, help="冷却等待秒数")
    parser.add_argument("--raw-dir", default="data/raw", help="原件落盘目录")
    parser.add_argument("--no-cache", action="store_true", help="禁用页面缓存（每次强制走网络）")
    parser.add_argument("--cache-days", type=int, default=7, help="缓存新鲜期（天），默认 7 天")
    parser.add_argument("--circuit-break-threshold", type=int, default=5, help="同因熔断阈值（同一 domain+error_type 连续失败次数）")
    parser.add_argument("--circuit-break-window", type=int, default=3600, help="熔断窗口秒数（默认 3600）")

    args = parser.parse_args()

    # 加载并校验配置
    raw_configs = load_schools_config()
    report = validate_all_configs(raw_configs)

    if report["summary"]["errors"] > 0:
        logger.error("配置校验发现 %d 个错误:", report["summary"]["errors"])
        for err in report["errors"]:
            logger.error("  %s", err)
        sys.exit(1)

    if report["summary"]["warnings"] > 0:
        for warn in report["warnings"]:
            logger.warning("  %s", warn)

    logger.info("配置加载完成：%d 校通过校验", report["summary"]["ok"])

    # 构建任务
    if args.retry_failed:
        tasks = build_tasks([], [], [], args.year, True, False, True)
    else:
        schools = args.school or ["__all__"]
        tasks = build_tasks(schools, args.category, args.source, args.year, args.force, args.resume, False)

    if not tasks:
        logger.info("无任务可执行")
        return

    logger.info("任务队列构建完成：共 %d 个任务", len(tasks))
    for t in tasks:
        logger.info("  - %s / %s / %s", t.university, t.college, t.source)

    # 初始化会话与进度
    session = PoliteSession(
        delay_range=tuple(args.delay),
        max_retries=args.max_retries,
        raw_dir=args.raw_dir,
        cooldown_threshold=args.cooldown_threshold,
        cooldown_seconds=args.cooldown_seconds,
    )
    progress = get_progress_tracker()

    # 同因熔断器
    circuit_breaker = CircuitBreaker(threshold=args.circuit_break_threshold)
    skipped = 0  # 被熔断跳过的任务数

    # 页面缓存（第一次爬取的数据落盘，后续刷新走本地）
    cache = None if args.no_cache else CrawlCache(max_age_days=args.cache_days)
    if cache is not None:
        logger.info("已启用页面缓存：目录 %s，新鲜期 %d 天（--force 可强制刷新）", cache.cache_dir, args.cache_days)

    # 过滤已被熔断的任务
    active_tasks = []
    for task in tasks:
        list_url = task.config.get("faculty", {}).get("list_url", "")
        domain = _extract_domain(list_url)
        if circuit_breaker.is_tripped(domain):
            error_type = "skipped_unreachable"
            failure = add_failure(
                failure_id=f"skip_{task.university}_{task.college}_{task.source}_{int(time.time())}",
                school=task.university, college=task.college,
                source="Source A" if task.source == "source_a" else "Source B",
                error_type=error_type,
                error_message=f"域名 {domain} 因同因熔断被挂起，自动跳过",
                url=list_url,
            )
            export_failures(load_failures() + [failure])
            progress.update_school_status(task.university, task.college, **{task.source: "failed"})
            logger.warning("熔断跳过（启动时）: %s / %s (domain=%s)", task.university, task.college, domain)
            skipped += 1
        else:
            active_tasks.append(task)

    if not active_tasks:
        logger.info("所有任务均被熔断挂起，无任务可执行")
        return

    # 并发执行
    completed = 0
    failed = 0
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_task = {executor.submit(execute_task, task, session, progress, cache): task for task in active_tasks}

        for future in concurrent.futures.as_completed(future_to_task):
            task = future_to_task[future]
            list_url = task.config.get("faculty", {}).get("list_url", "")
            domain = _extract_domain(list_url)

            try:
                success, error, error_type = future.result()
                if success:
                    completed += 1
                    circuit_breaker.reset(domain)
                else:
                    failed += 1
                    # 记录到熔断器
                    if domain and error_type and error_type != "none":
                        circuit_breaker.record(domain, error_type)
            except Exception as e:
                failed += 1
                if domain:
                    etype = classify_error(e)
                    circuit_breaker.record(domain, etype)
                logger.exception("任务执行异常: %s / %s / %s", task.university, task.college, task.source)

            # 检查是否有新域名被熔断，跳过剩余任务中属于该域名的
            if circuit_breaker.tripped_domains:
                remaining = len(future_to_task) - completed - failed
                if remaining > 0:
                    logger.info("熔断生效中，已挂起域名: %s", circuit_breaker.tripped_domains)

            # 进度显示
            elapsed = time.time() - start_time
            rate = (completed + failed + skipped) / elapsed if elapsed > 0 else 0
            logger.info("进度：%d 完成，%d 失败，%d 跳过，%.1f 任务/秒", completed, failed, skipped, rate)

    logger.info("熔断统计：已挂起域名 %s", circuit_breaker.tripped_domains)

    # 全量导出 summary.xlsx
    logger.info("开始生成全量汇总表...")
    all_merged = []
    for jsonl_file in Path("data/output").glob("*_*.jsonl"):
        if jsonl_file.name.endswith("_faculty.jsonl") or jsonl_file.name.endswith("_notice.jsonl"):
            continue
        with open(jsonl_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    all_merged.append(json.loads(line))

    if all_merged:
        export_summary(all_merged)
        export_merged(all_merged)
        logger.info("全量导出完成：%d 条记录", len(all_merged))
    else:
        logger.warning("无合并数据，跳过汇总表生成")

    # 统计
    total_time = time.time() - start_time
    logger.info("=" * 50)
    logger.info("采集任务全部结束")
    logger.info("总任务数: %d", len(tasks))
    logger.info("成功: %d", completed)
    logger.info("失败: %d", failed)
    logger.info("耗时: %.1f 秒", total_time)
    logger.info("请求统计: %s", session.stats)
    if cache is not None:
        logger.info("缓存统计: %s", cache.stats)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()