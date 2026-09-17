#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
候选审核与配置更新工具
=====================
1. 列出所有候选文件
2. 显示每个候选的详细信息
3. 交互式选择最佳候选
4. 自动生成 CSS 选择器建议（可选）
5. 更新 school_data.json

用法：
    python scripts/review_candidates.py [--school "东南大学"] [--college "机械工程学院"] [--auto-approve]
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

# 确保能导入本地模块
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.loader import load_schools_config, save_school_config
from config.validator import validate_school_config

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CANDIDATES_DIR = Path("data/candidates")


def list_candidates(school_filter: Optional[str] = None, college_filter: Optional[str] = None) -> list[dict]:
    """列出所有候选文件。"""
    candidates_files = list(CANDIDATES_DIR.glob("*_candidates.json"))
    results = []

    for cf in candidates_files:
        try:
            data = json.loads(cf.read_text(encoding="utf-8"))
            university = data.get("university", "")
            college = data.get("college", "")

            if school_filter and school_filter not in university:
                continue
            if college_filter and college_filter not in college:
                continue

            # 只保留可达的候选
            reachable = [c for c in data["candidates"] if c.get("reachable")]
            data["candidates"] = sorted(reachable, key=lambda x: x["score"], reverse=True)
            data["reachable_count"] = len(reachable)
            data["file_path"] = str(cf)
            results.append(data)
        except Exception as e:
            logger.warning("读取候选文件失败 %s: %s", cf, e)

    return results


def display_candidates(candidates: list[dict]):
    """显示候选列表。"""
    for i, c in enumerate(candidates, 1):
        print(f"\n{'='*60}")
        print(f"[{i}] {c['university']} / {c['college']}")
        print(f"    文件: {c['file_path']}")
        print(f"    发现时间: {c['discovered_at']}")
        print(f"    可达候选: {c['reachable_count']}")

        for j, cand in enumerate(c["candidates"][:5], 1):
            markers = ", ".join(cand.get("markers", []))
            print(f"      {j}. [{cand['score']:.1f}] {cand['url']}")
            print(f"         类型: {cand['list_type']} | 来源: {cand['source']} | 标记: {markers}")
            if cand.get("title"):
                print(f"         标题: {cand['title'][:80]}")


def interactive_select(candidates: list[dict]) -> dict[str, dict]:
    """交互式选择最佳候选。"""
    selections = {}

    for c in candidates:
        print(f"\n{'='*60}")
        print(f"学校: {c['university']} / 学院: {c['college']}")
        print(f"可达候选: {c['reachable_count']}")

        if not c["candidates"]:
            print("  无可达候选，跳过")
            continue

        for j, cand in enumerate(c["candidates"][:10], 1):
            markers = ", ".join(cand.get("markers", []))
            print(f"  {j}. [{cand['score']:.1f}] {cand['url']} ({cand['list_type']}) - {markers}")

        print("  0. 跳过此学校")
        print("  c. 自定义 URL")

        while True:
            choice = input("请选择 (1-10, 0跳过, c自定义): ").strip()
            if choice == "0":
                break
            elif choice.lower() == "c":
                custom_url = input("请输入自定义 URL: ").strip()
                if custom_url:
                    selections[f"{c['university']}|{c['college']}"] = {
                        "url": custom_url,
                        "list_type": "static_html",
                        "source": "manual",
                    }
                break
            elif choice.isdigit() and 1 <= int(choice) <= len(c["candidates"]):
                selected = c["candidates"][int(choice) - 1]
                selections[f"{c['university']}|{c['college']}"] = {
                    "url": selected["url"],
                    "list_type": selected["list_type"],
                    "source": selected["source"],
                }
                print(f"  已选择: {selected['url']}")
                break
            else:
                print("  无效选择，请重新输入")

    return selections


def suggest_selectors(url: str, list_type: str) -> dict:
    """根据 URL 和类型建议 CSS 选择器。"""
    # 基于常见模式的启发式建议
    suggestions = {
        "list_item_selector": "li",
        "list_name_selector": "a",
        "list_research_selector": "",
    }

    if list_type == "ajax_api":
        # AJAX API 不需要列表页选择器
        return {}

    # 可以根据域名或路径进一步细化
    # 这里提供通用建议，实际需要人工调整
    return suggestions


def update_school_config(
    university: str,
    college: str,
    category: str,
    selected: dict,
    selectors: dict,
):
    """更新学校配置。"""
    configs = load_schools_config()

    for item in configs:
        if item["university"] != university:
            continue

        for cat in item["categories"]:
            if cat["college"] != college or cat["category"] != category:
                continue

            # 更新 faculty 配置
            faculty_cfg = cat.setdefault("faculty", {})
            faculty_cfg["enabled"] = True
            faculty_cfg["list_type"] = selected["list_type"]
            faculty_cfg["list_url"] = selected["url"]

            if selectors:
                faculty_cfg.update(selectors)

            # 验证配置
            errors = validate_school_config(item)
            if errors:
                logger.warning("配置校验警告: %s", errors)

            # 保存
            if save_school_config(university, item):
                logger.info("已更新配置: %s / %s", university, college)
            else:
                logger.error("保存配置失败: %s / %s", university, college)
            return

    logger.error("未找到匹配的学校配置: %s / %s", university, college)


def main():
    parser = argparse.ArgumentParser(description="候选审核与配置更新工具")
    parser.add_argument("--school", help="筛选学校名称")
    parser.add_argument("--college", help="筛选学院名称")
    parser.add_argument("--auto-approve", action="store_true", help="自动选择最高分候选")
    parser.add_argument("--list-only", action="store_true", help="仅列出候选，不交互")
    parser.add_argument("--apply", action="store_true", help="应用选择到配置")
    args = parser.parse_args()

    candidates = list_candidates(args.school, args.college)

    if not candidates:
        logger.info("无匹配的候选文件")
        return

    display_candidates(candidates)

    if args.list_only:
        return

    if args.auto_approve:
        # 自动选择最高分
        selections = {}
        for c in candidates:
            if c["candidates"]:
                best = c["candidates"][0]
                selections[f"{c['university']}|{c['college']}"] = {
                    "url": best["url"],
                    "list_type": best["list_type"],
                    "source": best["source"],
                }
                logger.info("自动选择: %s / %s -> %s", c["university"], c["college"], best["url"])
    else:
        selections = interactive_select(candidates)

    if not selections:
        logger.info("无选择，退出")
        return

    if args.apply:
        # 需要额外输入选择器
        for key, selected in selections.items():
            university, college = key.split("|", 1)

            # 找到对应的 category
            configs = load_schools_config()
            category = None
            for item in configs:
                if item["university"] == university:
                    for cat in item["categories"]:
                        if cat["college"] == college:
                            category = cat["category"]
                            break

            if not category:
                logger.error("找不到 category: %s / %s", university, college)
                continue

            print(f"\n配置选择器: {university} / {college} / {category}")
            print(f"URL: {selected['url']}")
            print(f"类型: {selected['list_type']}")

            if selected["list_type"] == "static_html":
                item_sel = input("  列表项选择器 (默认 li): ").strip() or "li"
                name_sel = input("  姓名选择器 (默认 a): ").strip() or "a"
                research_sel = input("  研究方向选择器 (可选): ").strip()

                selectors = {
                    "list_item_selector": item_sel,
                    "list_name_selector": name_sel,
                    "list_research_selector": research_sel,
                }
            else:
                selectors = {}

            update_school_config(university, college, category, selected, selectors)
    else:
        logger.info("预览模式，使用 --apply 应用更改")
        for key, selected in selections.items():
            print(f"  {key}: {selected['url']} ({selected['list_type']})")


if __name__ == "__main__":
    main()