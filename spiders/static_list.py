# -*- coding: utf-8 -*-
"""
静态 HTML 师资列表页解析器
===========================
适用场景：教师列表直接渲染在 HTML 中（如东大机械 /xscz/list.htm）。
从配置中的选择器提取教师条目列表。
"""

import logging
import re
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from utils.http import PoliteSession
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)


def fetch_faculty_list(
    session: PoliteSession,
    list_url: str,
    selectors: dict,
    base_url: Optional[str] = None,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> list[dict]:
    """
    抓取静态师资列表页，返回教师条目列表。

    Args:
        session: PoliteSession 实例
        list_url: 列表页 URL
        selectors: 选择器配置字典，包含:
            - item: 教师条目的 CSS 选择器（如 'li[style*="display"] a[title]'）
            - name: 条目内姓名的选择器或属性（如 'title' 表示取 a 标签的 title 属性）
            - research: 研究方向的选择器（如 '.research'），可选
            - profile: 个人主页链接的选择器或属性（如 'href'），可选
        base_url: 用于拼接相对链接的基 URL
        cache: CrawlCache 实例（提供时命中缓存则跳过网络请求）
        force: True 时忽略缓存强制重新抓取

    Returns:
        list[dict]: 每条包含 name, profile_url, research(可选)
    """
    if base_url is None:
        from urllib.parse import urlparse
        p = urlparse(list_url)
        # Use the full URL up to the last / as base for relative link resolution
        base_url = f"{p.scheme}://{p.netloc}{p.path.rsplit('/', 1)[0]}/"

    def _do_fetch() -> str:
        from utils.http import response_text
        return response_text(session.get(list_url))

    if cache is not None:
        html = cache.get_or_fetch(_do_fetch, list_url, force=force)
    else:
        html = _do_fetch()

    soup = BeautifulSoup(html, "lxml")
    return parse_faculty_html(soup, selectors, base_url)


def parse_faculty_html(
    soup: BeautifulSoup,
    selectors: dict,
    base_url: str,
) -> list[dict]:
    """从已解析的 BeautifulSoup 对象中提取教师列表。"""
    item_sel = selectors["item"]
    items = soup.select(item_sel)
    logger.info("列表页匹配到 %d 个教师条目（选择器: %s）", len(items), item_sel)

    results = []
    seen_names = set()

    for item in items:
        teacher = _extract_one(item, selectors, base_url)
        if not teacher:
            continue
        # 去重（同名只保留第一条）
        name = teacher.get("name", "")
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        results.append(teacher)

    logger.info("提取到 %d 位教师（去重后）", len(results))
    return results


def _extract_one(item: Tag, selectors: dict, base_url: str) -> Optional[dict]:
    """从一个教师条目 HTML 元素中提取字段。"""
    result = {}

    # 姓名
    name_sel = selectors.get("name", "title")
    name = _get_field(item, name_sel)
    if not name:
        return None
    result["name"] = name.strip()

    # 详情页链接
    profile_sel = selectors.get("profile", "href")
    profile = _get_field(item, profile_sel)
    if profile:
        result["profile_url"] = urljoin(base_url, profile)
    else:
        # 如果条目本身就是 <a>，取其 href
        tag = item if item.name == "a" else item.find("a")
        if tag and tag.get("href"):
            result["profile_url"] = urljoin(base_url, tag["href"])

    # 研究方向（列表页直接有的情况）
    research_sel = selectors.get("research")
    if research_sel:
        research = _get_field(item, research_sel)
        if research:
            # 去掉常见前缀
            research = re.sub(r"^研究方向[:：]?\s*", "", research.strip())
            result["research_areas_raw"] = research
            result["research_areas"] = _split_research(research)

    return result if result.get("name") else None


def _get_field(tag: Tag, selector: str) -> Optional[str]:
    """
    通用字段提取：selector 可以是 CSS 选择器或 HTML 属性名。
    """
    # 先尝试作为 CSS 选择器
    found = tag.select_one(selector)
    if found:
        return found.get_text(strip=True) or found.get("title", "")
    # 再尝试作为属性
    val = tag.get(selector)
    if val:
        return str(val)
    return None


def _split_research(text: str) -> list[str]:
    """把研究方向文本拆分为列表。支持多种分隔符。"""
    # 常见分隔符：；  ; 、  ,  ，  换行
    parts = re.split(r"[；;、，,\n]+", text)
    return [p.strip() for p in parts if p.strip()]
