#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量 URL 发现脚本
=================
为所有配置的学校运行 URL 自动发现流水线，生成候选列表供人工审核。

用法：
    python scripts/batch_discover_urls.py [--schools "东南大学,北京大学"] [--categories "mechanical,automation"]
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

# 确保能导入本地模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.loader import load_schools_config
from spiders.url_resolver import URLResolver
from utils.http import PoliteSession
from utils.cache import CrawlCache

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def get_target_schools(
    schools_filter: Optional[list[str]] = None,
    categories_filter: Optional[list[str]] = None,
) -> list[tuple[str, str, str]]:
    """
    获取目标学校列表。

    Returns:
        list[tuple]: (university, college, category)
    """
    configs = load_schools_config()
    targets = []

    for item in configs:
        university = item["university"]
        if schools_filter and university not in schools_filter:
            continue

        for cat in item["categories"]:
            category = cat["category"]
            college = cat["college"]

            if categories_filter and category not in categories_filter:
                continue

            targets.append((university, college, category))

    return targets


def run_batch_discovery(
    targets: list[tuple[str, str, str]],
    delay_range: tuple[float, float] = (1.0, 3.0),
    max_workers: int = 1,
) -> dict:
    """
    批量运行 URL 发现。

    Args:
        targets: (university, college, category) 列表
        delay_range: 请求延迟范围
        max_workers: 并发数（建议保持 1 避免被搜索引擎限制）

    Returns:
        dict: 统计结果
    """
    session = PoliteSession(delay_range=delay_range)
    cache = CrawlCache(max_age_days=7)
    resolver = URLResolver(session=session, cache=cache)

    stats = {
        "total": len(targets),
        "success": 0,
        "failed": 0,
        "no_candidates": 0,
        "errors": [],
    }

    for i, (university, college, category) in enumerate(targets, 1):
        logger.info("=" * 60)
        logger.info("[%d/%d] 发现 URL: %s / %s (%s)", i, len(targets), university, college, category)

        try:
            candidates = resolver.resolve(university, college, category)

            if not candidates:
                logger.warning("  无候选结果")
                stats["no_candidates"] += 1
            else:
                reachable = sum(1 for c in candidates if c.reachable)
                logger.info("  发现 %d 个候选，可达 %d 个", len(candidates), reachable)
                stats["success"] += 1

        except Exception as e:
            logger.exception("  发现失败: %s", e)
            stats["failed"] += 1
            stats["errors"].append(f"{university}/{college}: {e}")

    return stats


def main():
    parser = argparse.ArgumentParser(description="批量 URL 发现脚本")
    parser.add_argument(
        "--schools",
        help="目标学校列表，逗号分隔（默认全部）",
    )
    parser.add_argument(
        "--categories",
        help="学科分类，逗号分隔（默认全部）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        nargs=2,
        default=[1.0, 3.0],
        help="请求延迟范围（秒）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="并发数（建议 1）",
    )
    parser.add_argument(
        "--output-summary",
        default="data/candidates/discovery_summary.json",
        help="汇总报告输出路径",
    )

    args = parser.parse_args()

    schools_filter = [s.strip() for s in args.schools.split(",")] if args.schools else None
    categories_filter = [c.strip() for c in args.categories.split(",")] if args.categories else None

    targets = get_target_schools(schools_filter, categories_filter)

    if not targets:
        logger.warning("无匹配的学校/学院组合")
        return

    logger.info("共 %d 个目标待发现", len(targets))
    for uni, college, cat in targets[:5]:
        logger.info("  - %s / %s / %s", uni, college, cat)
    if len(targets) > 5:
        logger.info("  ... 共 %d 个", len(targets))

    stats = run_batch_discovery(targets, tuple(args.delay), args.workers)

    # 输出汇总
    logger.info("=" * 60)
    logger.info("批量发现完成：")
    logger.info("  总计: %d", stats["total"])
    logger.info("  成功: %d", stats["success"])
    logger.info("  无候选: %d", stats["no_candidates"])
    logger.info("  失败: %d", stats["failed"])

    # 保存汇总
    output_path = Path(args.output_summary)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("汇总报告已保存: %s", output_path)

    if stats["errors"]:
        logger.error("错误详情:")
        for err in stats["errors"]:
            logger.error("  %s", err)


if __name__ == "__main__":
    main()