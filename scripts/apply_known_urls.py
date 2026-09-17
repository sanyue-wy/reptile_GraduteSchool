#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
应用已知 URL 到学校配置
======================
从 known_urls.py 读取映射并写入 school_data.json
"""

import sys
from pathlib import Path

# 确保能导入本地模块
sys.path.insert(0, str(Path(__file__).parent.parent))

import json

# 导入已知 URL 映射
from config.known_urls import KNOWN_FACULTY_URLS, generate_template_urls


def apply_known_urls():
    """将已知 URL 应用到 school_data.json"""
    config_path = Path("config/school_data.json")

    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 合并模板 URL
    templates = generate_template_urls()
    all_urls = {**KNOWN_FACULTY_URLS, **templates}

    updated = 0
    for item in data:
        uni = item["university"]
        if uni not in all_urls:
            continue

        for cat in item["categories"]:
            cat_key = cat["category"]
            if cat_key not in all_urls[uni]:
                continue

            url_info = all_urls[uni][cat_key]

            # 更新学院名称（如果映射中有）
            if "college" in url_info:
                cat["college"] = url_info["college"]

            # 更新 faculty 配置
            faculty = cat.setdefault("faculty", {})
            faculty["enabled"] = True
            faculty["list_type"] = url_info.get("list_type", "static_html")
            faculty["list_url"] = url_info["list_url"]

            if faculty["list_type"] == "static_html":
                faculty["list_item_selector"] = url_info.get("list_item_selector", "")
                faculty["list_name_selector"] = url_info.get("list_name_selector", "text")
                faculty["list_research_selector"] = url_info.get("list_research_selector", "")
            elif faculty["list_type"] == "ajax_api":
                faculty["api_params"] = url_info.get("api_params", {})

            if "detail_selectors" in url_info:
                faculty["detail_selectors"] = url_info["detail_selectors"]

            updated += 1
            print(f"  [OK] {uni} / {cat['college']} ({cat_key}) -> {url_info['list_url']}")

    # 写回配置
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n共更新 {updated} 个学院配置")


def export_known_urls():
    """导出完整映射到 JSON 文件供参考"""
    templates = generate_template_urls()
    all_urls = {**KNOWN_FACULTY_URLS, **templates}

    with open("config/known_urls.json", "w", encoding="utf-8") as f:
        json.dump(all_urls, f, ensure_ascii=False, indent=2)

    print(f"已导出完整映射到 config/known_urls.json ({len(all_urls)} 所)")


def verify_urls():
    """验证配置中的 URL 是否已填充"""
    with open("config/school_data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    total = 0
    enabled = 0
    for item in data:
        for cat in item["categories"]:
            total += 1
            faculty = cat.get("faculty", {})
            if faculty.get("enabled") and faculty.get("list_url"):
                enabled += 1

    print(f"总学院数: {total}, 已启用并有 URL: {enabled}, 待配置: {total - enabled}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "export":
            export_known_urls()
        elif sys.argv[1] == "verify":
            verify_urls()
    else:
        apply_known_urls()
        verify_urls()