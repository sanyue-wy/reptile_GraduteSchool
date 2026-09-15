"""配置去重

将旧格式（faculty 位于大学级别）转换为新格式（faculty 嵌入每个 category），
去重合并同校条目，生成 config/school_data.json。

运行方式：
    python -m config.dedup
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def merge_dicts(a: Dict, b: Dict) -> Dict:
    """合并两个字典，非空优先"""
    result = a.copy()
    for k, v in b.items():
        if v and not result.get(k):
            result[k] = v
    return result


def merge_category(a: Dict, b: Dict) -> Dict:
    """合并两个同类配置，非空优先，数组取并集"""
    result = a.copy()
    for key, val_b in b.items():
        if key in ("faculty", "notice"):
            # 子字典递归合并
            if isinstance(val_b, dict) and isinstance(result.get(key), dict):
                result[key] = merge_dicts(result[key], val_b)
            elif val_b and not result.get(key):
                result[key] = val_b
        elif isinstance(val_b, list):
            # 列表取并集
            existing = set(str(x) for x in result.get(key, []))
            for item in val_b:
                if str(item) not in existing:
                    result[key] = result.get(key, []) + [item]
                    existing.add(str(item))
        elif val_b and not result.get(key):
            result[key] = val_b
    return result


def deduplicate_schools(configs: List[Dict]) -> tuple[List[Dict], List[str]]:
    """
    去重学校配置。

    Args:
        configs: 原始配置列表（可能含重复）

    Returns:
        (deduped, logs)
        - deduped: 去重后的配置列表
        - logs: 去重操作日志列表，每条描述合并详情

    处理流程：
        1. 按 university 分组
        2. 同校内按 category 去重（university + category 唯一）
        3. 合并冲突字段（非空优先，数组并集）
        4. 输出去重日志
    """
    merged: Dict[str, Dict] = {}
    logs: List[str] = []

    for cfg in configs:
        uni = cfg.get("university", "").strip()
        if not uni:
            logs.append("跳过空 university 条目")
            continue

        if uni not in merged:
            merged[uni] = cfg.copy()
            merged[uni]["categories"] = list(cfg.get("categories", []))
            continue

        # 合并 categories — 按 category 去重（university + category 唯一）
        existing_cats: Dict[str, Dict] = {}
        for c in merged[uni].get("categories", []):
            existing_cats[c.get("category")] = c

        for cat in cfg.get("categories", []):
            cat_key = cat.get("category")
            if cat_key in existing_cats:
                # 合并：字段取非空值
                existing = existing_cats[cat_key]
                merged_cat = merge_category(existing, cat)
                existing_cats[cat_key] = merged_cat
                logs.append(f"合并 {uni}/{cat.get('college', '?')} ({cat_key}) 重复配置")
            else:
                existing_cats[cat_key] = cat
                logs.append(f"新增 {uni}/{cat.get('college', '?')} ({cat_key})")

        merged[uni]["categories"] = list(existing_cats.values())

    return list(merged.values()), logs


# ------------------------------------------------------------------
# 迁移脚本：旧 schools.py → school_data.json
# ------------------------------------------------------------------

def _convert_old_to_new(old_configs: List[Dict]) -> List[Dict]:
    """
    将旧格式配置（faculty 位于大学级别）转换为新格式（faculty 嵌入 category）。

    旧格式：
        {university, categories:[{college, category, notice}], faculty:{mechanical: {...}, automation: {...}}}

    新格式：
        {university, level, categories:[{college, category, faculty:{...}, notice:{...}}]}
    """
    from config.school_level_raw import get_school_level, validate_and_fix_levels

    validate_and_fix_levels()  # 确保 985 ⊂ 211 ⊂ 双一流

    converted: List[Dict] = []
    for cfg in old_configs:
        uni = cfg.get("university", "").strip()
        faculty_map = cfg.get("faculty", {})

        new_categories = []
        for cat in cfg.get("categories", []):
            category_name = cat.get("category")
            # 从顶层 faculty 字典中提取对应 category 的 faculty 配置
            cat_faculty = faculty_map.get(category_name, {}) if category_name else {}

            new_cat = {
                "college": cat.get("college", ""),
                "category": category_name or "",
            }
            if cat_faculty:
                new_cat["faculty"] = cat_faculty
            else:
                new_cat["faculty"] = {
                    "list_url": "",
                    "list_type": "static_html",
                    "list_item_selector": "",
                    "list_research_selector": "",
                    "detail_selectors": {},
                    "api_params": {},
                    "referer": "",
                }

            # 迁移 notice，确保 enabled 字段存在
            notice = cat.get("notice", {})
            if not isinstance(notice, dict):
                notice = {}
            new_cat["notice"] = {
                "enabled": notice.get("enabled", False),
                "entry_url": notice.get("entry_url", ""),
                "school_code": notice.get("school_code", ""),
                "major_codes": notice.get("major_codes", {}),
                "title_pattern": notice.get("title_pattern", ""),
                "template": notice.get("template", "yzw_major"),
            }

            new_categories.append(new_cat)

        new_cfg = {
            "university": uni,
            "level": get_school_level(uni),
            "categories": new_categories,
        }
        converted.append(new_cfg)

    return converted


def migrate() -> None:
    """从 config/schools.py 读取旧格式，转换并去重，写入 config/school_data.json。"""
    # 确保能导入 config 包
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from config.schools import SCHOOLS_CONFIG
    except ImportError:
        logger.error("无法导入 config.schools.SCHOOLS_CONFIG，迁移中止")
        sys.exit(1)

    logger.info("读取旧格式配置：%d 条", len(SCHOOLS_CONFIG))

    # 转换到新格式
    converted = _convert_old_to_new(SCHOOLS_CONFIG)

    # 去重
    deduped, logs = deduplicate_schools(converted)

    for log in logs:
        logger.info("  %s", log)

    logger.info("去重完成：%d → %d 校", len(converted), len(deduped))

    # 写入 school_data.json
    output_path = project_root / "config" / "school_data.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(deduped, f, ensure_ascii=False, indent=2)

    logger.info("写入 %s，共 %d 所学校", output_path, len(deduped))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    migrate()
