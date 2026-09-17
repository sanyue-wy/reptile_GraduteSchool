"""Playwright 渲染引擎（js_render 型学院官网）

适用场景：学院师资页为 SPA 或 JS 动态渲染，静态 HTML 中无教师列表内容。
典型建站平台：Vue/React 构建的院校官网。

下游复用现有的 BS4 解析链：获取 page.content() 后交给现有解析逻辑。
"""

import logging
from typing import Optional

from bs4 import BeautifulSoup

from utils.http import PoliteSession
from utils.cache import CrawlCache
from spiders.engine import SpiderEngine, register_engine

logger = logging.getLogger(__name__)


def sync_playwright():
    """仅渲染时导入可选依赖，同时保留旧模块的 mock 入口。"""
    from playwright.sync_api import sync_playwright as factory
    return factory()


@register_engine
class JSRenderEngine(SpiderEngine):
    name = "js_render"
    supported_source = "source_a"

    def fetch(self, url: str, *, selectors: dict, wait_selector=None, timeout=30000,
              force=False, **kwargs) -> list[dict]:
        return fetch_faculty_via_playwright(
            self.session, url, selectors, wait_selector=wait_selector, timeout=timeout,
            cache=self.cache, force=force,
        )

    def parse(self, html: str, selectors: dict, *, base_url="", **kwargs) -> list[dict]:
        """解析已渲染 HTML，无需安装或启动 Playwright。"""
        return _parse_rendered_html(html, selectors, base_url or kwargs.get("url", ""))


def _parse_rendered_html(html: str, selectors: dict, base_url: str) -> list[dict]:
    """将学院配置和标准选择器统一为静态解析器的 item/name/profile/research。"""
    from spiders.static_list import parse_faculty_html

    faculty_cfg = {
        "item": selectors.get("item") or selectors.get("list_item_selector") or "li",
        "name": selectors.get("name") or selectors.get("list_name_selector") or "a",
        "profile": selectors.get("profile") or selectors.get("list_profile_selector") or "href",
        "research": selectors.get("research") or selectors.get("list_research_selector"),
    }
    return parse_faculty_html(BeautifulSoup(html, "lxml"), faculty_cfg, base_url)


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
    cache_key = f"js_render:{list_url}"

    def _do_fetch() -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
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
            finally:
                browser.close()
        return content

    if cache is not None:
        html = cache.get_or_fetch(_do_fetch, cache_key, force=force)
    else:
        html = _do_fetch()

    # 以完整页面 URL 解析相对链接，与离线 parse(base_url=list_url) 一致。
    results = _parse_rendered_html(html, selectors, list_url)

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
