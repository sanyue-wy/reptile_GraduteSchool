# -*- coding: utf-8 -*-
"""
Parser 公共工具函数
===================
供各 parser 文件复用的通用解析逻辑。
"""

import re
from typing import Dict, List


def split_names(raw: str, separators: str = r"[\s;；,，、]+") -> List[str]:
    """通用姓名拆分（供研招网、公示 PDF 等复用）。

    - 空字符串 / 占位文本（"不区分导师"、"请登录..."、"--"、"无"）返回空列表
    - 分隔后过滤长度 < 2 的碎片（避免单个字被误当姓名）
    """
    if not raw or raw.strip() in ("不区分导师", "请登录各学院网站查看", "--", "无"):
        return []
    names = re.split(separators, raw.strip())
    return [n.strip() for n in names if n.strip() and len(n.strip()) >= 2]


def normalize_whitespace(text: str) -> str:
    """归一化空白字符（全角→半角、连续空格→单空格）。"""
    if not text:
        return ""
    text = text.replace("　", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def build_raw_ref(meta: dict, source_type: str) -> dict:
    """构造 raw_ref 结构（INTERFACE_SPEC.md 1.1）。

    用于最终合并记录；单个 source 的记录中 raw_ref 应为字符串路径。
    """
    return {
        "faculty": meta.get("faculty_raw_ref", ""),
        "notice": f"data/raw/{meta.get('university', '')}/{meta.get('year', '')}/{source_type}/",
    }


def build_source_type(faculty: str = "", notice: str = "") -> dict:
    """构造 source_type 结构（INTERFACE_SPEC.md 1.1）。

    用于最终合并记录；单个 source 的记录中 source_type 应为字符串。
    """
    return {"faculty": faculty, "notice": notice}
