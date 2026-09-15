# -*- coding: utf-8 -*-
"""
教师详情页解析器
=================
从教师个人主页提取：职称、博硕导身份、研究方向、邮箱等。
支持两种典型模板（通过 detail_type 配置区分）。
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

from utils.http import PoliteSession
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)

# 板块标题同义词表：统一 key → 标准化名称
_SECTION_ALIASES = {
    "研究方向": "research",
    "研究兴趣": "research",
    "research interests": "research",
    "research direction": "research",
    "研究领域": "research",
    "个人简介": "bio",
    "个人简介": "bio",
    "教育背景": "education",
    "教育经历": "education",
    "工作经历": "work",
    "工作履历": "work",
    "讲授课程": "courses",
    "教学课程": "courses",
    "学术兼职": "service",
    "获奖情况": "awards",
    "论文著作": "publications",
    "论文发表": "publications",
    "科研项目": "projects",
    "专利": "patents",
}


def fetch_detail(
    session: PoliteSession,
    profile_url: str,
    detail_type: str = "auto",
    selectors: Optional[dict] = None,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> dict:
    """
    抓取教师详情页并提取字段。

    Args:
        session: PoliteSession 实例
        profile_url: 教师个人主页 URL
        detail_type: 页面模板类型
            - "me": 机械工程学院型（.carrer 头部 + tit/con 板块）
            - "auto": 自动化学院型（.xing + span 序列 + p 列表）
            - "auto"：自动检测（默认）
        selectors: 自定义选择器覆盖（可选）
        cache: CrawlCache 实例（提供时命中缓存则跳过网络请求）
        force: True 时忽略缓存强制重新抓取

    Returns:
        dict: title, advisor_level, email, research_areas, sections, ...
    """
    def _do_fetch() -> str:
        return session.get(profile_url).text

    if cache is not None:
        html = cache.get_or_fetch(_do_fetch, profile_url, force=force)
    else:
        html = _do_fetch()

    soup = BeautifulSoup(html, "lxml")

    if detail_type == "auto":
        detail_type = _detect_type(soup)

    if detail_type == "me":
        return _parse_me_style(soup, profile_url)
    elif detail_type == "auto_type":
        return _parse_auto_style(soup, profile_url)
    else:
        return _parse_generic(soup, profile_url)


def _detect_type(soup: BeautifulSoup) -> str:
    """自动检测页面模板类型。"""
    if soup.select_one(".carrer"):
        return "me"
    if soup.select_one(".xing"):
        return "auto_type"
    return "generic"


# ------------------------------------------------------------------
# 机械工程学院型：.carrer 头部 + tit/con 板块
# ------------------------------------------------------------------

def _parse_me_style(soup: BeautifulSoup, url: str) -> dict:
    result = {"profile_url": url}

    # 头部信息卡
    career = soup.select_one(".carrer")
    if career:
        title_div = career.select_one(".title")
        if title_div:
            # 姓名在 .jsbt 里
            jsbt = title_div.select_one(".jsbt")
            if jsbt:
                result["name"] = jsbt.get_text(strip=True)
            # 职称/博硕导是 .jsbt 之后的裸文本
            full_text = title_div.get_text(separator=" ", strip=True)
            _parse_title_text(full_text, result)

        # 键值对字段：所在院系、邮箱、电话等
        for text_div in career.select(".text"):
            kv_text = text_div.get_text(strip=True)
            _parse_kv_field(kv_text, result)

    # 板块内容（研究方向、简介等）
    _parse_sections(soup, result)

    return result


# ------------------------------------------------------------------
# 自动化学院型：.xing + 并列 span + .text 键值对
# ------------------------------------------------------------------

def _parse_auto_style(soup: BeautifulSoup, url: str) -> dict:
    result = {"profile_url": url}

    # 姓名
    xing = soup.select_one(".xing")
    if xing:
        result["name"] = xing.get_text(strip=True)

    # 职称等信息在 .xing 的兄弟 span 中
    parent = xing.parent if xing else None
    if parent:
        spans = parent.find_all("span")
        for span in spans:
            text = span.get_text(strip=True)
            if not text:
                continue
            if text in ("男", "女"):
                continue
            if text in ("博士", "硕士", "学士"):
                result.setdefault("degree", text)
            elif text in ("教授", "副教授", "讲师", "助理教授", "研究员", "副研究员"):
                result.setdefault("title", text)
            elif "导师" in text:
                result.setdefault("advisor_tags_raw", text)
                result.setdefault("advisor_level", _parse_advisor_level_text(text))

    # 键值对
    for text_div in soup.select(".text"):
        kv_text = text_div.get_text(strip=True)
        _parse_kv_field(kv_text, result)

    # 板块内容
    _parse_sections(soup, result)

    return result


# ------------------------------------------------------------------
# 通用 fallback
# ------------------------------------------------------------------

def _parse_generic(soup: BeautifulSoup, url: str) -> dict:
    result = {"profile_url": url}
    # 尝试各种常见姓名选择器
    for sel in [".jsbt", ".xing", "h1", ".name", ".title h2"]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text and len(text) <= 10:
                result["name"] = text
                break

    # 邮箱正则
    email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", soup.get_text())
    if email_match:
        result["email"] = email_match.group(0)

    _parse_sections(soup, result)
    return result


# ------------------------------------------------------------------
# 共用工具
# ------------------------------------------------------------------

def _parse_title_text(text: str, result: dict):
    """从标题文本提取职称和博硕导身份。"""
    # 职称
    for kw in ("教授", "副教授", "讲师", "助理教授", "研究员", "副研究员", "助理研究员"):
        if kw in text:
            result.setdefault("title", kw)
            break
    # 博硕导
    advisor_parts = []
    if "博士生导师" in text:
        advisor_parts.append("博导")
    if "硕士生导师" in text:
        advisor_parts.append("硕导")
    if advisor_parts:
        result.setdefault("advisor_level", "/".join(advisor_parts))


def _parse_kv_field(text: str, result: dict):
    """解析 '键:值' 或 '键：值' 格式的字段。"""
    m = re.match(r"(邮箱|Email|E-mail|电话|办公室|所在院系|姓名|地点|教师主页)\s*[:：]\s*(.+)", text)
    if not m:
        return
    key, val = m.group(1).strip(), m.group(2).strip()
    if key in ("邮箱", "Email", "E-mail"):
        result.setdefault("email", val)
    elif key == "电话":
        result.setdefault("phone", val)
    elif key == "办公室":
        result.setdefault("office", val)
    elif key in ("所在院系",):
        result.setdefault("department", val)
    elif key == "姓名":
        result.setdefault("name", val)
    elif key == "地点":
        result.setdefault("address", val)
    elif key == "教师主页":
        result.setdefault("homepage", val)


def _parse_sections(soup: BeautifulSoup, result: dict):
    """提取各板块（tit/con 结构），特别关注研究方向。"""
    sections = {}
    for news_box in soup.select("div.news_box"):
        tit = news_box.select_one("div.tit")
        con = news_box.select_one("div.con")
        if not tit or not con:
            continue
        raw_title = tit.get_text(strip=True)
        key = _normalize_section_title(raw_title)
        content = con.get_text(separator="\n", strip=True)
        if key and content:
            sections[key] = content

    result["sections"] = sections

    # 研究方向特殊处理
    if "research" in sections:
        result.setdefault("research_areas_raw", sections["research"])
        result.setdefault("research_areas", _split_research(sections["research"]))


def _normalize_section_title(title: str) -> Optional[str]:
    """板块标题标准化（查同义词表）。"""
    title_lower = title.lower().strip()
    # 精确匹配
    for alias, key in _SECTION_ALIASES.items():
        if alias.lower() in title_lower:
            return key
    return None


def _split_research(text: str) -> list[str]:
    """把研究方向文本拆分为列表。"""
    # 支持 "1、xxx" / "1. xxx" / "N、xxx" / "N. xxx" 编号格式
    parts = re.split(r"\d+[、．.]\s*", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1:
        # 没有编号格式，用分隔符拆
        parts = re.split(r"[；;，,\n]+", text)
        parts = [p.strip() for p in parts if p.strip()]
    return parts


def _parse_advisor_level_text(text: str) -> str:
    """从文本解析博导/硕导。"""
    levels = []
    if "博士生导师" in text:
        levels.append("博导")
    if "硕士生导师" in text:
        levels.append("硕导")
    return "/".join(levels) if levels else ""
