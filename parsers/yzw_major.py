# -*- coding: utf-8 -*-
"""
研招网专业目录解析器插件
========================
注册名: yzw_major

用于解析研招网 API 返回的专业目录 JSON，提取导师招生信息。
实现接口约定：parse(raw_path: str, meta: dict) -> List[dict]

输出记录遵循 INTERFACE_SPEC.md §1.2 Source B 中间态格式：
  - raw_ref: str  (data/raw/{university}/{year}/yzw/major_{school_code}.json)
  - source_type: str ("研招网专业目录")
  - enrollment: dict (in_roster, degree_types, directions, planned_count,
                       exam_subjects, source_url, notice_year)
  - match_status: "partial_notice"

注意：此处 raw_ref / source_type 为字符串（不是 TutorRecord Schema 中的嵌套 dict），
因为合并管道 merge_pair() 会在合并时构造嵌套结构。
"""

import json
import logging
from pathlib import Path
from typing import List, Dict

from parsers import register
from parsers.utils import split_names

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 字段拆分工具
# ------------------------------------------------------------------

def split_advisor_names(zdjs: str) -> List[str]:
    """拆分指导教师字段为姓名列表。

    复用 parsers.utils.split_names 的标准逻辑。
    支持分隔符：空格、中英文分号、逗号、顿号。
    过滤特殊占位值如"不区分导师"、"请登录各学院网站查看"、"--"。
    """
    return split_names(zdjs)


def split_exam_subjects(kskm: str) -> List[str]:
    """解析考试科目字符串。

    格式: "101 政治 201 英语一 301 数学一 801 机械原理"
    返回: ["101 政治", "201 英语一", "301 数学一", "801 机械原理"]
    """
    if not kskm:
        return []
    parts = kskm.split()
    subjects = []
    i = 0
    while i + 1 < len(parts):
        code = parts[i]
        name = parts[i + 1]
        subjects.append(f"{code} {name}")
        i += 2
    return subjects


# ------------------------------------------------------------------
# 记录构造
# ------------------------------------------------------------------

def build_tutor_record(name: str, raw_item: Dict, meta: Dict) -> Dict:
    """构造符合 Source B 中间态 Schema 的单条记录。

    输出字段：
      name, university, college, category, enrollment(match_status="partial_notice"),
      raw_ref(路径字符串), source_type(字符串), schema_version
      title/advisor_level/email/profile_url/research_areas 留空（由 Source A 或合并填充）
    """
    directions = [{
        "code": raw_item.get("zydm", ""),
        "name": raw_item.get("zymc", ""),
        "research_direction": raw_item.get("yjfxmc", ""),
    }]

    exam_subjects = split_exam_subjects(raw_item.get("kskm", ""))

    planned_count_raw = raw_item.get("nzsrsstr")
    planned_count = None
    if planned_count_raw:
        try:
            planned_count = int(planned_count_raw)
        except (ValueError, TypeError):
            planned_count = None

    xxfs = raw_item.get("xxfs", "")
    degree_types = ["学术型硕士"] if xxfs == "1" else ["专业型硕士"]

    # 构造研招网详情页 URL
    source_url = (
        f"https://yz.chsi.com.cn/zsml/rs/dws.do"
        f"?dwmc={meta.get('university', '')}"
        f"&dwdm={meta.get('school_code', '')}"
    )

    enrollment = {
        "in_roster": True,
        "degree_types": degree_types,
        "directions": directions,
        "planned_count": planned_count,
        "exam_subjects": exam_subjects,
        "source_url": source_url,
        "notice_year": meta["year"],
    }

    raw_ref = meta.get("raw_ref") or (
        f"data/raw/{meta['university']}/{meta['year']}/yzw/major_{meta['school_code']}.json"
    )

    return {
        "schema_version": 1,
        "name": name,
        "university": meta["university"],
        "college": meta["college"],
        "category": meta["category"],
        "title": "",
        "advisor_level": "",
        "email": "",
        "profile_url": "",
        "research_areas": [],
        "enrollment": enrollment,
        "match_status": "partial_notice",
        "raw_ref": raw_ref,
        "source_type": "研招网专业目录",
    }


# ------------------------------------------------------------------
# 标准 parse() 接口
# ------------------------------------------------------------------

@register("yzw_major")
def parse(raw_path: str, meta: Dict) -> List[Dict]:
    """解析研招网专业目录 JSON 文件。

    Args:
        raw_path: 原件 JSON 文件路径
        meta: {
            "university": str,
            "college": str,
            "category": "mechanical" | "automation",
            "year": int,
            "school_code": str,
            "template": "yzw_major",
            "raw_ref": str (optional, 原件路径),
            "major_codes": List[str] (optional, 专业代码白名单)
        }

    Returns:
        List[dict] — 每项为 TutorRecord 中间态（match_status="partial_notice"）
    """
    # 检查原件文件是否存在
    if not Path(raw_path).exists():
        logger.error("原件文件不存在: %s", raw_path)
        return []

    # 将 raw_path 传入 meta，供 build_tutor_record 使用
    meta = {**meta, "raw_ref": raw_path}

    # 加载 JSON
    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        logger.warning("JSON 解析失败 %s: %s", raw_path, e)
        return []
    except Exception as e:
        logger.error("读取原件失败 %s: %s", raw_path, e)
        return []

    raw_items = data.get("data", [])
    results = []

    for item in raw_items:
        # 专业代码过滤（若配置了 major_codes）
        major_code = item.get("zydm", "")
        if meta.get("major_codes") and major_code not in meta["major_codes"]:
            continue

        names = split_advisor_names(item.get("zdjs", ""))
        if not names:
            # 无具体导师名：生成一条空名记录，靠专业+学校匹配
            results.append(build_tutor_record("", item, meta))
        else:
            for name in names:
                results.append(build_tutor_record(name, item, meta))

    logger.info("yzw_major parser: %s/%s 解析 %d 条记录（raw: %s）",
                meta.get("university", "?"), meta.get("college", "?"), len(results), raw_path)
    return results
