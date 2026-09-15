# -*- coding: utf-8 -*-
"""
多源合并管道
============
把 Source A（官网师资页 faculty.jsonl）和 Source B（研招网 yzw_major.jsonl）
按「姓名 + 学院」做软合并。

匹配策略（三阶）：
  1. 精确匹配：归一化后姓名完全相同
  2. 去空格匹配：去掉所有空格后相同（覆盖"张 三" vs "张三"）
  3. 模糊匹配：difflib 相似度 ≥ 0.85（覆盖同音字/简繁差异）

合并结果的 match_status：
  - "merged"：两侧均有数据且匹配成功
  - "partial_faculty"：仅有官网师资页数据
  - "partial_notice"：仅有研招网数据
"""

import difflib
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 姓名归一化
# ------------------------------------------------------------------

def normalize_name(name: str) -> str:
    """去首尾空格、全角转半角、压缩内部空格。"""
    if not name:
        return ""
    name = name.strip()
    # 全角空格 → 半角
    name = name.replace("　", " ")
    # 压缩连续空格
    name = " ".join(name.split())
    return name


def strip_name(name: str) -> str:
    """去掉所有空格（用于第二阶匹配）。"""
    return normalize_name(name).replace(" ", "")


# ------------------------------------------------------------------
# 匹配核心
# ------------------------------------------------------------------

def _build_index(records: list[dict], key_field: str = "name") -> dict[str, list[dict]]:
    """按归一化姓名建倒排索引，支持同名多人。"""
    idx: dict[str, list[dict]] = {}
    for rec in records:
        key = normalize_name(rec.get(key_field, ""))
        if key:
            idx.setdefault(key, []).append(rec)
    return idx


def match_records(
    faculty_records: list[dict],
    notice_records: list[dict],
    fuzzy_threshold: float = 0.85,
) -> tuple[list[tuple[Optional[dict], Optional[dict], str]], list[dict], list[dict]]:
    """匹配两个来源的记录。

    Returns:
        (matched_pairs, unmatched_faculty, unmatched_notice)
        matched_pairs 中每项为 (faculty_rec | None, notice_rec | None, match_status)
        match_status: "merged" | "partial_faculty" | "partial_notice"
    """
    # 按学校+学院分组建索引
    def _group_key(rec: dict) -> str:
        return f"{rec.get('university', '')}|{rec.get('college', '')}"

    fac_by_group: dict[str, list[dict]] = {}
    for r in faculty_records:
        fac_by_group.setdefault(_group_key(r), []).append(r)

    not_by_group: dict[str, list[dict]] = {}
    for r in notice_records:
        not_by_group.setdefault(_group_key(r), []).append(r)

    all_groups = set(fac_by_group.keys()) | set(not_by_group.keys())

    matched: list[tuple[Optional[dict], Optional[dict], str]] = []
    unmatched_fac: list[dict] = []
    unmatched_not: list[dict] = []

    for group in all_groups:
        fac_list = fac_by_group.get(group, [])
        not_list = not_by_group.get(group, [])

        fac_idx_exact = _build_index(fac_list)
        not_idx_exact = _build_index(not_list)

        # 已匹配集合（用 id 去重）
        fac_matched_ids: set[int] = set()
        not_matched_ids: set[int] = set()

        # 第 1 阶：精确匹配
        for name, fac_recs in fac_idx_exact.items():
            if name in not_idx_exact:
                for fr in fac_recs:
                    # 取第一个未匹配的 notice_rec
                    for nr in not_idx_exact[name]:
                        if id(nr) not in not_matched_ids:
                            matched.append((fr, nr, "merged"))
                            fac_matched_ids.add(id(fr))
                            not_matched_ids.add(id(nr))
                            break

        # 第 2 阶：去空格匹配
        not_strip_idx: dict[str, list[dict]] = {}
        for r in not_list:
            if id(r) not in not_matched_ids:
                not_strip_idx.setdefault(strip_name(r.get("name", "")), []).append(r)

        for fr in fac_list:
            if id(fr) in fac_matched_ids:
                continue
            stripped = strip_name(fr.get("name", ""))
            if stripped in not_strip_idx:
                for nr in not_strip_idx[stripped]:
                    if id(nr) not in not_matched_ids:
                        matched.append((fr, nr, "merged"))
                        fac_matched_ids.add(id(fr))
                        not_matched_ids.add(id(nr))
                        break

        # 第 3 阶：模糊匹配
        remaining_fac = [r for r in fac_list if id(r) not in fac_matched_ids]
        remaining_not = [r for r in not_list if id(r) not in not_matched_ids]

        if remaining_fac and remaining_not:
            not_names = [strip_name(r.get("name", "")) for r in remaining_not]
            for fr in remaining_fac:
                if id(fr) in fac_matched_ids:
                    continue
                fr_stripped = strip_name(fr.get("name", ""))
                close = difflib.get_close_matches(fr_stripped, not_names, n=1, cutoff=fuzzy_threshold)
                if close:
                    target = close[0]
                    for nr in remaining_not:
                        if strip_name(nr.get("name", "")) == target and id(nr) not in not_matched_ids:
                            matched.append((fr, nr, "merged"))
                            fac_matched_ids.add(id(fr))
                            not_matched_ids.add(id(nr))
                            break

        # 未匹配的
        for fr in fac_list:
            if id(fr) not in fac_matched_ids:
                matched.append((fr, None, "partial_faculty"))
        for nr in not_list:
            if id(nr) not in not_matched_ids:
                matched.append((None, nr, "partial_notice"))

    return matched, unmatched_fac, unmatched_not


# ------------------------------------------------------------------
# 合并为统一 Schema
# ------------------------------------------------------------------

def merge_pair(fac: Optional[dict], not_: Optional[dict], status: str) -> dict:
    """把一对匹配记录合并为统一导师 Schema v1。

    优先使用 Source A（官网师资页）的基础字段，
    Source B（研招网）的招生结构化字段填入 enrollment 子对象。
    """
    base = fac or not_ or {}
    enr_src = not_ or {}

    enrollment = None
    if enr_src.get("directions") or enr_src.get("in_roster") is not None:
        enrollment = {
            "in_roster": enr_src.get("in_roster", False),
            "degree_types": enr_src.get("degree_types", []),
            "directions": enr_src.get("directions", []),
            "planned_count": enr_src.get("planned_count"),
            "exam_subjects": enr_src.get("exam_subjects", []),
            "source_url": enr_src.get("source_url", ""),
            "notice_year": enr_src.get("notice_year"),
        }

    return {
        "schema_version": 1,
        "name": base.get("name", ""),
        "university": base.get("university", ""),
        "college": base.get("college", ""),
        "category": base.get("category", ""),
        "title": (fac or {}).get("title", "") or (not_ or {}).get("title", ""),
        "advisor_level": (fac or {}).get("advisor_level", ""),
        "email": (fac or {}).get("email", ""),
        "profile_url": (fac or {}).get("profile_url", ""),
        "research_areas": (fac or {}).get("research_areas", []),
        "enrollment": enrollment,
        "match_status": status,
        "raw_ref": {
            "faculty": (fac or {}).get("raw_ref", ""),
            "notice": (not_ or {}).get("raw_ref", ""),
        },
        "source_type": {
            "faculty": (fac or {}).get("source_type", ""),
            "notice": (not_ or {}).get("source_type", ""),
        },
    }


# ------------------------------------------------------------------
# 公开 API
# ------------------------------------------------------------------

def merge_sources(
    faculty_path: str,
    notice_path: str,
    output_path: str,
    fuzzy_threshold: float = 0.85,
) -> dict:
    """执行完整合并流程，写入 output_path，返回统计摘要。

    Args:
        faculty_path: Source A 的 faculty.jsonl 路径
        notice_path:  Source B 的 notice.jsonl 路径（不存在则视为无数据）
        output_path:  合并结果输出路径
        fuzzy_threshold: 模糊匹配阈值

    Returns:
        {"total": N, "merged": N, "partial_faculty": N, "partial_notice": N}
    """
    # 读取 faculty
    fac_records = _read_jsonl(faculty_path)
    logger.info("Source A（官网师资页）加载 %d 条", len(fac_records))

    # 读取 notice（可能不存在）
    not_records = _read_jsonl(notice_path) if Path(notice_path).exists() else []
    logger.info("Source B（研招网）加载 %d 条", len(not_records))

    if not fac_records and not not_records:
        logger.warning("两个数据源均为空，跳过合并")
        _write_jsonl(output_path, [])
        return {"total": 0, "merged": 0, "partial_faculty": 0, "partial_notice": 0}

    # 匹配
    pairs, _, _ = match_records(fac_records, not_records, fuzzy_threshold)
    logger.info("匹配完成：%d 对（含单侧）", len(pairs))

    # 合并
    merged_records = [merge_pair(f, n, s) for f, n, s in pairs]

    # 统计
    stats = {
        "total": len(merged_records),
        "merged": sum(1 for _, _, s in pairs if s == "merged"),
        "partial_faculty": sum(1 for _, _, s in pairs if s == "partial_faculty"),
        "partial_notice": sum(1 for _, _, s in pairs if s == "partial_notice"),
    }
    logger.info("合并结果：%s", stats)

    # 写出
    _write_jsonl(output_path, merged_records)
    return stats


# ------------------------------------------------------------------
# Excel 汇总行转换
# ------------------------------------------------------------------

def to_summary_row(merged: dict) -> dict:
    """把一条 merged 记录转成 summary.xlsx 的一行。

    列顺序对齐需求文档：学校/学院/姓名/职称/招生状态/招生方向/研究方向/来源链接
    数据来源：官网师资页（Source A）提供姓名/职称/研究方向/个人主页；
              研招网（Source B）提供招生状态/招生方向。
    """
    enr = merged.get("enrollment") or {}
    dirs = enr.get("directions") or []
    direction_str = "; ".join(d.get("name", "") for d in dirs if d.get("name"))

    # 来源链接：优先官网个人主页，其次研招网公示页
    source_url = merged.get("profile_url") or enr.get("source_url") or ""

    return {
        "学校": merged.get("university", ""),
        "学院": merged.get("college", ""),
        "姓名": merged.get("name", ""),
        "职称": merged.get("title", ""),
        "招生状态": "是" if enr.get("in_roster") else "否",
        "招生方向": direction_str,
        "研究方向": "; ".join(merged.get("research_areas") or []),
        "来源链接": source_url,
    }


# ------------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------------

def _read_jsonl(path: str) -> list[dict]:
    """逐行读取 JSONL 文件，忽略格式错误行。"""
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("JSONL 解析失败，跳过第 %d 行: %s", i, path)
    except FileNotFoundError:
        logger.debug("文件不存在: %s", path)
    return records


def _write_jsonl(path: str, records: list[dict]):
    """写出 JSONL 文件。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.info("已写出 %d 条记录到 %s", len(records), path)
