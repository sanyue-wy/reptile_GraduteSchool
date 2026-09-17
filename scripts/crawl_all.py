#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全量采集一键启动脚本（集成 URL 发现 + 审核 + 采集）
=================================================

用法：
    # 全自动：发现 URL -> 自动选最高分 -> 采集
    python scripts/crawl_all.py --auto-discover --auto-approve

    # 交互式：发现 URL -> 人工审核 -> 采集
    python scripts/crawl_all.py --auto-discover --interactive

    # 仅采集（已有配置）
    python scripts/crawl_all.py --resume

    # 仅发现 URL（不采集）
    python scripts/crawl_all.py --discover-only

    # 仅审核候选（不采集）
    python scripts/crawl_all.py --review-only
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_cmd(cmd: list[str], description: str = "") -> bool:
    """运行命令并返回是否成功。"""
    if description:
        logger.info("%s", description)
    logger.info("执行: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error("命令失败 (退出码 %d): %s", e.returncode, " ".join(cmd))
        return False
    except KeyboardInterrupt:
        logger.info("用户中断")
        return False


def check_configs_ready() -> tuple[bool, int, list[tuple[str, str]]]:
    """检查配置就绪情况，返回 (是否有就绪, 就绪数量, 未就绪列表)。"""
    config_path = Path("config/school_data.json")
    if not config_path.exists():
        return False, 0, []

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ready = []
    not_ready = []

    for item in data:
        uni = item["university"]
        for cat in item["categories"]:
            faculty = cat.get("faculty", {})
            key = (uni, cat["college"], cat["category"])
            if faculty.get("enabled") and faculty.get("list_url"):
                ready.append(key)
            else:
                not_ready.append(key)

    return len(ready) > 0, len(ready), not_ready


def get_schools_without_config(not_ready: list[tuple[str, str, str]], schools_filter: list[str] = None) -> list[str]:
    """获取需要发现 URL 的学校列表（去重）。"""
    schools = set()
    for uni, college, cat in not_ready:
        if schools_filter is None or uni in schools_filter:
            schools.add(uni)
    return sorted(schools)


def main():
    parser = argparse.ArgumentParser(description="全量采集一键启动（集成 URL 发现 + 审核 + 采集）")

    # 模式选择
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--auto-discover", action="store_true", help="自动发现缺失配置的学校 URL")
    mode.add_argument("--discover-only", action="store_true", help="仅运行 URL 发现，不采集")
    mode.add_argument("--review-only", action="store_true", help="仅审核候选 URL，不采集")
    mode.add_argument("--resume", action="store_true", help="断点续抓（默认模式）")

    # 审核模式
    review = parser.add_mutually_exclusive_group()
    review.add_argument("--auto-approve", action="store_true", help="自动选择最高分候选（需配合 --auto-discover）")
    review.add_argument("--interactive", action="store_true", help="交互式审核候选（默认）")

    # 采集参数
    parser.add_argument("--year", type=int, default=2026, help="数据年份")
    parser.add_argument("--workers", type=int, default=4, help="并发线程数")
    parser.add_argument("--force", action="store_true", help="强制重新采集已完成项")
    parser.add_argument("--retry-failed", action="store_true", help="重试所有失败项")
    parser.add_argument("--delay", type=float, nargs=2, default=[2.0, 5.0], help="请求延迟范围（秒）")
    parser.add_argument("--max-retries", type=int, default=3, help="最大重试次数")
    parser.add_argument("--timeout", type=int, default=30, help="连接超时（秒）")
    parser.add_argument("--no-cache", action="store_true", help="禁用缓存")
    parser.add_argument("--cache-days", type=int, default=7, help="缓存天数")
    parser.add_argument("--source", nargs="+", default=["source_a", "source_b"], help="数据源")
    parser.add_argument("--category", nargs="+", default=["mechanical", "automation"], help="学科分类")
    parser.add_argument("--batch-size", type=int, default=10, help="URL 发现批次大小")
    parser.add_argument("--schools", help="指定要发现/采集的学校（逗号分隔），默认所有未配置学校")
    parser.add_argument("--dry-run", action="store_true", help="仅显示将执行的步骤")

    args = parser.parse_args()

    # 默认模式：如果没有指定任何模式，且有配置就绪，则 resume
    if not any([args.auto_discover, args.discover_only, args.review_only, args.resume]):
        ready, count, _ = check_configs_ready()
        if ready:
            args.resume = True
        else:
            args.auto_discover = True
            logger.info("无就绪配置，自动启用 --auto-discover 模式")

    logger.info("=" * 60)
    logger.info("全量采集工作流启动")
    logger.info("=" * 60)

    # 步骤 1：URL 发现
    if args.auto_discover or args.discover_only:
        ready, count, not_ready = check_configs_ready()
        schools_filter = [s.strip() for s in args.schools.split(",")] if args.schools else None
        schools_to_discover = get_schools_without_config(not_ready, schools_filter)

        if not schools_to_discover:
            logger.info("所有学校已有配置，跳过 URL 发现")
        else:
            logger.info("需发现 URL 的学校 (%d): %s", len(schools_to_discover), ", ".join(schools_to_discover[:10]) + ("..." if len(schools_to_discover) > 10 else ""))

            if args.dry_run:
                logger.info("[DRY-RUN] 将运行 batch_discover_urls.py 分批发现")
            else:
                # 分批运行发现
                for i in range(0, len(schools_to_discover), args.batch_size):
                    batch = schools_to_discover[i:i + args.batch_size]
                    logger.info("批次 %d/%d: %s", i // args.batch_size + 1, (len(schools_to_discover) + args.batch_size - 1) // args.batch_size, ", ".join(batch))

                    cmd = [
                        sys.executable, "scripts/batch_discover_urls.py",
                        "--schools", ",".join(batch),
                        "--delay", str(args.delay[0]), str(args.delay[1]),
                        "--workers", "1"  # 发现时建议单线程
                    ]
                    if not run_cmd(cmd, f"发现 URL (批次 {i // args.batch_size + 1})"):
                        logger.error("URL 发现失败，停止")
                        sys.exit(1)

                    # 批次间等待，避免搜索引擎限流
                    if i + args.batch_size < len(schools_to_discover):
                        wait_time = 30
                        logger.info("等待 %d 秒避免限流...", wait_time)
                        time.sleep(wait_time)

        if args.discover_only:
            logger.info("URL 发现完成，退出")
            return

    # 步骤 2：审核候选（仅当有候选文件且有可达候选时）
    if args.auto_discover or args.review_only:
        # 检查是否有候选文件且有可达候选
        candidates_dir = Path("data/candidates")
        has_reviewable = False
        if candidates_dir.exists():
            for cf in candidates_dir.glob("*_candidates.json"):
                try:
                    with open(cf, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if any(c.get("reachable") for c in data.get("candidates", [])):
                        has_reviewable = True
                        break
                except Exception:
                    pass

        if not has_reviewable:
            logger.info("无可审核的候选 URL，跳过审核步骤")
        elif args.dry_run:
            logger.info("[DRY-RUN] 将运行 review_candidates.py")
        else:
            review_cmd = [sys.executable, "scripts/review_candidates.py"]
            if args.auto_approve:
                review_cmd.extend(["--auto-approve", "--apply"])
                logger.info("自动审核模式：选择最高分候选并应用")
            else:
                review_cmd.append("--apply")
                logger.info("交互式审核模式：请在终端选择候选")

            if not run_cmd(review_cmd, "审核候选 URL"):
                logger.error("审核失败，停止")
                sys.exit(1)

        if args.review_only:
            logger.info("审核完成，退出")
            return

    # 步骤 3：采集
    ready, count, _ = check_configs_ready()
    if not ready:
        logger.error("仍无就绪配置，无法开始采集")
        sys.exit(1)

    logger.info("配置就绪：%d 个学院可采集", count)

    # 构建 main.py 命令
    cmd = [
        sys.executable, "main.py",
        "--school", "__all__",
        "--year", str(args.year),
        "--workers", str(args.workers),
        "--delay", str(args.delay[0]), str(args.delay[1]),
        "--max-retries", str(args.max_retries),
        "--timeout", str(args.timeout),
        "--cache-days", str(args.cache_days),
        "--source"] + args.source + ["--category"] + args.category

    if args.resume or args.auto_discover:
        cmd.append("--resume")
    if args.force:
        cmd.append("--force")
    if args.retry_failed:
        cmd.append("--retry-failed")
    if args.no_cache:
        cmd.append("--no-cache")

    logger.info("=" * 60)
    logger.info("开始采集 (就绪: %d 学院, 线程: %d)", count, args.workers)
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("[DRY-RUN] 将执行: %s", " ".join(cmd))
        return

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("采集过程出错，退出码: %d", e.returncode)
        sys.exit(e.returncode)
    except KeyboardInterrupt:
        logger.info("用户中断")
        sys.exit(130)

    logger.info("=" * 60)
    logger.info("全量采集工作流完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()