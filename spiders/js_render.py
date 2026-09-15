"""Playwright 渲染引擎（js_render 型学院官网）

适用场景：学院师资页为 SPA 或 JS 动态渲染，静态 HTML 中无教师列表内容。
典型建站平台：Vue/React 构建的院校官网。

下游复用现有的 BS4 解析链：获取 page.content() 后交给现有解析逻辑。
"""

import logging
from typing import Optional
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Browser, Page

from utils.http import PoliteSession
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)


def fetch_faculty_via_playwright(
    session: PoliteSession,
    list_url: str,
    selectors: dict,
    wait_selector: Optional[str] = None,
    timeout: int = 30000,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> list[dict]:
    """
    通过 Playwright headless 渲染师资页，提取教师列表。

    Args:
        session: PoliteSession 实例（用于复用 UA、限速等配置）
        list_url: 师资页 URL
        selectors: 详情页选择器配置（传递给 detail_parser）
        wait_selector: Playwright 等待的选择器（默认等待 .faculty-list 或 li）
        timeout: 页面加载超时（毫秒）
        cache: CrawlCache 实例
        force: True 时忽略缓存

    Returns:
        list[dict]: 每条包含 name, profile_url 等字段
    """
    from spiders.detail_parser import fetch_detail
    from spiders.static_list import parse_faculty_html

    cache_key = f"js_render:{list_url}"

    def _do_fetch() -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(list_url, timeout=timeout, wait_until="networkidle")

            # 等待目标元素出现
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=10000)
                except Exception:
                    logger.warning("等待选择器 %s 超时，继续获取页面内容", wait_selector)
            else:
                # 默认等待常见列表元素
                for sel in [".faculty-list", "li[class*='teacher']", ".teacher-item", "table"]:
                    try:
                        page.wait_for_selector(sel, timeout=5000)
                        break
                    except Exception:
                        continue

            content = page.content()
            browser.close()
        return content

    if cache is not None:
        html = cache.get_or_fetch(_do_fetch, cache_key, force=force)
    else:
        html = _do_fetch()

    # 复用现有 BS4 解析链
    soup = BeautifulSoup(html, "lxml")
    faculty_cfg = {
        "list_item_selector": selectors.get("list_item_selector", "li"),
        "list_research_selector": selectors.get("list_research_selector", ""),
    }
    # 静态列表的选择器配置
    base_url = f"{list_url.split('//')[0]}//{list_url.split('/')[2]}" if '//' in list_url else list_url
    results = parse_faculty_html(soup, faculty_cfg, base_url)

    logger.info("Playwright 渲染提取到 %d 位教师", len(results))
    return results


def fetch_faculty_via_playwright_with_detail(
    session: PoliteSession,
    list_url: str,
    selectors: dict,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> list[dict]:
    """
    Playwright 渲染 + 详情页丰富字段。

    与 fetch_faculty_via_playwright 区别：额外抓取每个教师的详情页以丰富字段。
    """
    from spiders.detail_parser import fetch_detail

    teachers = fetch_faculty_via_playwright(
        session, list_url, selectors, cache=cache, force=force,
    )

    # 详情页丰富
    enriched = []
    for teacher in teachers:
        profile_url = teacher.get("profile_url", "")
        if not profile_url:
            enriched.append(teacher)
            continue
        try:
            detail = fetch_detail(
                session, profile_url, detail_type="auto",
                selectors=selectors.get("detail_selectors", {}),
                cache=cache, force=force,
            )
            enriched.append({**teacher, **detail})
        except Exception:
            enriched.append(teacher)

    return enriched
