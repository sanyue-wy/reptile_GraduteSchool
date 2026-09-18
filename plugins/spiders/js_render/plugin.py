# -*- coding: utf-8 -*-
"""
JS Render Spider Plugin
=======================
Migrated from spiders/js_render.py - JSRenderEngine.

Uses Playwright for headless rendering. Optional dependency:
- If Playwright not installed, plugin reports "dependency missing" in precheck
  rather than crashing.
- Test environment without Playwright: test cases explicitly skip.

Delivers TRUE raw material batches with rendered HTML as MediaAsset.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from utils.http import PoliteSession, BlockedError
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)

# Track Playwright availability
_PLAYWRIGHT_AVAILABLE = False
_PLAYWRIGHT_IMPORT_ERROR = None

try:
    from playwright.sync_api import sync_playwright
    _PLAYWRIGHT_AVAILABLE = True
except ImportError as e:
    _PLAYWRIGHT_IMPORT_ERROR = str(e)
    logger.info("Playwright not available: %s", e)


class JSRenderSpiderPlugin:
    """Spider plugin for JavaScript-rendered pages via Playwright.

    Input: TaskConfigDTO with config_snapshot containing list_url, selectors, wait_selector, timeout.
    Output: RawDataBatch containing RawDataDTO items with rendered HTML assets.

    If Playwright is not installed, execute() raises DependencyError which
    should be caught at precheck stage.
    """

    name = "js_render"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    class DependencyError(RuntimeError):
        """Raised when Playwright is not available."""
        pass

    def __init__(self):
        self._session: Optional[PoliteSession] = None
        self._cache: Optional[CrawlCache] = None
        self._cancel_token: Any = None

    def setup(self, context) -> None:
        self._session = context.http
        self._cache = context.cache
        self._cancel_token = context.cancel_token

    def precheck(self) -> tuple[bool, Optional[str]]:
        """Check if dependencies are available. Returns (ok, error_message)."""
        if not _PLAYWRIGHT_AVAILABLE:
            return False, f"Playwright not installed: {_PLAYWRIGHT_IMPORT_ERROR}"
        return True, None

    def execute(self, task_config: TaskConfigDTO, context) -> RawDataBatch:
        # Precheck at execution time too
        ok, err = self.precheck()
        if not ok:
            raise self.DependencyError(err)

        self.setup(context)

        if not self._session:
            raise RuntimeError("PoliteSession not injected via context")

        cfg = task_config.config_snapshot
        list_url = cfg.get("list_url") or task_config.target_url
        selectors = cfg.get("selectors", {})
        max_pages = cfg.get("max_pages", 5)
        wait_selector = cfg.get("wait_selector")
        timeout = cfg.get("timeout", 30000)

        if not list_url:
            raise ValueError("list_url is required in config_snapshot")

        items: list[RawDataDTO] = []
        errors: list[dict] = []
        pagination_complete = False
        next_page_token = None
        page_num = 1

        current_url = list_url
        visited_urls = set()

        while page_num <= max_pages:
            if self._cancel_token and self._cancel_token.is_set():
                errors.append(self._make_error(
                    "CANCELLED", "Crawl cancelled by user", "acquire", task_config.task_id, task_config.source_id, retryable=False
                ))
                break

            if current_url in visited_urls:
                logger.info("Already visited %s, stopping pagination", current_url)
                break
            visited_urls.add(current_url)

            # Fetch rendered page
            dto, error = self._fetch_rendered_page(current_url, task_config, f"rendered_page_{page_num}", wait_selector, timeout)
            if error:
                errors.append(error)
                if not error.get("retryable", False):
                    break
                continue

            if dto:
                items.append(dto)

            # Extract detail URLs from rendered HTML
            detail_urls = self._extract_detail_urls(dto, selectors, current_url)
            logger.info("Rendered page %d: found %d detail URLs", page_num, len(detail_urls))

            # Fan-out to detail pages (also rendered)
            for idx, detail_url in enumerate(detail_urls):
                if self._cancel_token and self._cancel_token.is_set():
                    break
                if detail_url in visited_urls:
                    continue
                visited_urls.add(detail_url)

                detail_dto, detail_error = self._fetch_rendered_page(
                    detail_url, task_config, f"detail_{page_num}_{idx}", wait_selector, timeout
                )
                if detail_error:
                    errors.append(detail_error)
                    continue
                if detail_dto:
                    items.append(detail_dto)

            # Check for next page
            next_url = self._find_next_page(dto, selectors, current_url, page_num)
            if not next_url:
                pagination_complete = True
                break

            current_url = next_url
            page_num += 1
            next_page_token = str(page_num)

        return RawDataBatch(
            schema_version="1",
            task_id=task_config.task_id,
            items=items,
            pagination_complete=pagination_complete,
            next_page_token=next_page_token if not pagination_complete else None,
            errors=errors,
        )

    def _fetch_rendered_page(
        self,
        url: str,
        task_config: TaskConfigDTO,
        trace_label: str,
        wait_selector: Optional[str],
        timeout: int,
    ) -> tuple[Optional[RawDataDTO], Optional[dict]]:
        """Fetch a page via Playwright and wrap as RawDataDTO."""
        try:
            cache_key = f"js_render:{url}"

            def _do_fetch() -> str:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    try:
                        page = browser.new_page()
                        page.goto(url, timeout=timeout, wait_until="networkidle")

                        # Wait for target element
                        if wait_selector:
                            try:
                                page.wait_for_selector(wait_selector, timeout=10000)
                            except Exception:
                                logger.warning("Wait selector %s timeout, continuing", wait_selector)
                        else:
                            # Default wait for common list elements
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

            if self._cache:
                html = self._cache.get_or_fetch(_do_fetch, cache_key, force=False)
            else:
                html = _do_fetch()

            asset = MediaAsset(
                media_type="text",
                mime_type="text/html",
                data=html.encode("utf-8"),
                metadata={"source_url": url, "trace_label": trace_label, "rendered": True},
            )

            dto = RawDataDTO(
                source_id=task_config.source_id,
                url=url,
                content_type="text/html",
                encoding="utf-8",
                fetched_at=datetime.now().isoformat(),
                trace={
                    "trace_label": trace_label,
                    "task_id": task_config.task_id,
                    "rendered": True,
                    "wait_selector": wait_selector,
                },
                assets=[asset],
            )
            return dto, None

        except BlockedError as e:
            return None, self._make_error("BLOCKED", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=True)
        except Exception as e:
            logger.exception("Playwright render failed for %s", url)
            return None, self._make_error("RENDER_ERROR", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=True)

    def _extract_detail_urls(self, dto: RawDataDTO, selectors: dict, base_url: str) -> list[str]:
        """Parse rendered HTML to extract detail page URLs."""
        if not dto.assets:
            return []

        asset = dto.assets[0]
        if asset.media_type != "text" or not asset.data:
            return []

        html = asset.data.decode("utf-8", errors="replace")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        item_sel = selectors.get("item") or selectors.get("list_item_selector") or "li"
        profile_sel = selectors.get("profile") or selectors.get("list_profile_selector") or "href"

        items = soup.select(item_sel)
        urls = []

        for item in items:
            from urllib.parse import urljoin
            url = self._get_field(item, profile_sel)
            if url:
                urls.append(urljoin(base_url, url))
            else:
                tag = item if item.name == "a" else item.find("a")
                if tag and tag.get("href"):
                    urls.append(urljoin(base_url, tag["href"]))

        return urls

    def _find_next_page(self, dto: RawDataDTO, selectors: dict, base_url: str, current_page: int) -> Optional[str]:
        """Find next page URL from rendered HTML."""
        if not dto.assets:
            return None

        asset = dto.assets[0]
        if asset.media_type != "text" or not asset.data:
            return None

        html = asset.data.decode("utf-8", errors="replace")
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")

        next_sel = selectors.get("next_page")
        if next_sel:
            next_link = soup.select_one(next_sel)
            if next_link:
                href = next_link.get("href")
                if href:
                    from urllib.parse import urljoin
                    return urljoin(base_url, href)

        # Fallback patterns
        from urllib.parse import urljoin
        for sel in [".next a", ".pagination .next a", "a[rel='next']"]:
            try:
                next_link = soup.select_one(sel)
                if next_link:
                    href = next_link.get("href")
                    if href:
                        return urljoin(base_url, href)
            except Exception:
                continue

        return None

    def _get_field(self, tag, selector: str) -> Optional[str]:
        """Extract field from tag."""
        if selector == "text" or selector == tag.name:
            return tag.get_text(strip=True) or tag.get("title", "")
        found = tag.select_one(selector)
        if found:
            return found.get_text(strip=True) or found.get("title", "")
        val = tag.get(selector)
        if val:
            return str(val)
        return None

    def _make_error(self, code: str, message: str, stage: str, task_id: str, source_id: str, retryable: bool) -> dict:
        return {
            "code": code,
            "message": message,
            "stage": stage,
            "task_id": task_id,
            "source_id": source_id,
            "retryable": retryable,
            "diagnostics": {},
        }

    def close(self) -> None:
        pass