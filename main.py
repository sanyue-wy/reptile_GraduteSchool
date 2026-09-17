#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI and backwards-compatible function adapters over application services."""
import argparse
import concurrent.futures
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional
from urllib.parse import urlparse

from config.loader import load_schools_config, get_school_config
from config.plugins import is_enabled, load_plugin_config, plugin_config
from config.validator import validate_all_configs
from exporters import dispatch as dispatch_exporter
from parsers import dispatch
from processors import dispatch as dispatch_processor
from services import CrawlTask, CrawlResult, CrawlerService, ExportService
from storage import JSONLStore
from utils.cache import CrawlCache
from utils.http import PoliteSession, CircuitBreaker, BlockedError, MaxRetriesExceeded
from pipelines.export import export_merged, export_summary, export_failures, add_failure, load_failures, get_active_failures
from pipelines.merge import merge_sources
from spiders.ajax_api import fetch_faculty_via_api
from spiders.detail_parser import fetch_detail
from spiders.static_list import fetch_faculty_list, parse_faculty_html
from utils.errors import classify_error
from utils.progress import get_progress_tracker, ProgressTracker

logger = logging.getLogger(__name__)


@dataclass
class SchoolConfig:
    university: str
    categories: list[dict]


def _extract_domain(url: str) -> str:
    return urlparse(url).netloc if url else ""


def load_school_configs() -> dict[str, SchoolConfig]:
    try:
        return {c["university"]: SchoolConfig(c["university"], c["categories"])
                for c in load_schools_config()}
    except Exception as error:
        logger.warning("加载学校配置失败: %s", error)
        return {}


def get_college_config(configs, university, category):
    school = configs.get(university)
    if school:
        return next((c for c in school.categories if c["category"] == category), None)
    return None


def _service(session, progress, cache):
    return CrawlerService(config=[], session_factory=lambda: session, progress=progress, cache=cache)


def run_source_a(task, session, progress, cache=None):
    result = _service(session, progress, cache).run_source_a(task)
    if result.status == "failed":
        raise RuntimeError(result.error_message)
    return result.records


def run_source_b(task, session, progress, cache=None):
    result = _service(session, progress, cache).run_source_b(task)
    if result.status == "failed":
        raise RuntimeError(result.error_message)
    return result.records


def execute_task(task, session, progress, cache=None):
    result = _service(session, progress, cache).execute_task(task)
    return result.status in ("success", "skipped"), result.error_message, result.error_type


def run_merge(university, college, year, progress):
    task = CrawlTask(university, college, "", "source_a", year)
    return CrawlerService(config=[], progress=progress).run_merge([task])


def run_processor_pipeline(records, ctx=None):
    """Legacy patch surface: pass main's plugin hooks into the shared service."""
    return ExportService().run_processor_pipeline(
        records, ctx, load_config=load_plugin_config, enabled=is_enabled,
        config_for=plugin_config, dispatch=dispatch_processor)


def run_export_pipeline(records, output_dir):
    return ExportService().run_export_pipeline(
        records, output_dir, load_config=load_plugin_config,
        enabled=is_enabled, dispatch=dispatch_exporter)


def build_tasks(schools, categories, sources, year, force, resume, retry_failed):
    return CrawlerService().build_tasks(SimpleNamespace(
        school=schools, category=categories, source=sources, year=year,
        force=force, resume=resume, retry_failed=retry_failed))


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
    parser.add_argument("--clear-cache", action="store_true", help="启动前清空页面缓存")
    parser.add_argument("--circuit-break-threshold", type=int, default=5, help="同因熔断阈值")
    parser.add_argument("--circuit-break-window", type=int, default=3600, help="熔断窗口秒数")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers 必须大于零")
    Path("data/output").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler("data/output/crawl.log", encoding="utf-8")])
    configs = load_schools_config()
    report = validate_all_configs(configs)
    if report["summary"]["errors"]:
        for error in report["errors"]:
            logger.error("%s", error)
        raise SystemExit(1)
    for warning in report["warnings"]:
        logger.warning("%s", warning)
    if args.clear_cache:
        CrawlCache(max_age_days=args.cache_days).clear()
    cache = None if args.no_cache else CrawlCache(max_age_days=args.cache_days)
    session = PoliteSession(delay_range=tuple(args.delay), max_retries=args.max_retries,
                            raw_dir=args.raw_dir, cooldown_threshold=args.cooldown_threshold,
                            cooldown_seconds=args.cooldown_seconds, timeout=args.timeout,
                            circuit_threshold=args.circuit_break_threshold,
                            circuit_window=args.circuit_break_window)
    try:
        service = CrawlerService(configs, cache, get_progress_tracker(), lambda: session)
        tasks = service.build_tasks(args)
        if not tasks:
            logger.info("无任务可执行")
            return
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            results = list(executor.map(service.execute_task, tasks))
        service.run_merge(tasks)
        all_merged = []
        for path in service.output_dir.glob("*_*.jsonl"):
            if not path.name.endswith(("_faculty.jsonl", "_notice.jsonl")):
                all_merged.extend(JSONLStore(path).read_all())
        if all_merged:
            run_export_pipeline(all_merged, service.output_dir)
        logger.info("完成 %d，失败 %d，HTTP 熔断域 %s", sum(r.status == "success" for r in results),
                    sum(r.status == "failed" for r in results), session.tripped_domains)
    finally:
        session.close()


if __name__ == "__main__":
    main()
