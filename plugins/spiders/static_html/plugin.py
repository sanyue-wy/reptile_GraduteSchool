# -*- coding: utf-8 -*-
"""
Static HTML Spider Plugin
=========================
Migrated from spiders/static_list.py - StaticListEngine.

Delivers TRUE raw material batches (RawDataBatch with MediaAsset assets),
not pre-parsed records. Each page/detail fetch produces a RawDataDTO with
the original HTML as MediaAsset(media_type="text", mime_type="text/html").

List page discovery + pagination termination + detail fan-out all happen
inside execute(), driven by validated config snapshot (selectors, URLs).
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin, urlparse
from uuid import uuid4

from bs4 import BeautifulSoup, Tag

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from utils.http import PoliteSession, BlockedError
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)


class StaticHtmlSpiderPlugin:
    """Spider plugin for static HTML faculty list pages.

    Input: TaskConfigDTO (with config_snapshot containing selectors, list_url, etc.)
    Output: RawDataBatch containing RawDataDTO items with HTML assets.
    """

    name = "static_html"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def __init__(self):
        self._session: Optional[PoliteSession] = None
        self._cache: Optional[CrawlCache] = None
        self._cancel_token: Any = None

    def setup(self, context) -> None:
        """Inject managed context (http, cache, cancel_token, etc.)."""
        self._session = context.http
        self._cache = context.cache
        self._cancel_token = context.cancel_token

    def execute(self, task_config: TaskConfigDTO, context) -> RawDataBatch:
        """Execute full static HTML crawl: list pages -> detail pages -> RawDataBatch."""
        self.setup(context)

        if not self._session:
            raise RuntimeError("PoliteSession not injected via context")

        # Extract validated config from snapshot
        cfg = task_config.config_snapshot
        list_url = cfg.get("list_url") or task_config.target_url
        selectors = cfg.get("selectors", {})
        max_pages = cfg.get("max_pages", 20)
        base_url = cfg.get("base_url")

        if not list_url:
            raise ValueError("list_url is required in config_snapshot")

        items: list[RawDataDTO] = []
        errors: list[dict] = []
        pagination_complete = False
        next_page_token = None
        page_num = 1

        # Resolve base_url for relative links
        if not base_url:
            p = urlparse(list_url)
            base_url = f"{p.scheme}://{p.netloc}{p.path.rsplit('/', 1)[0]}/"

        current_url = list_url
        visited_urls = set()

        while page_num <= max_pages:
            # Check cancellation
            if self._cancel_token and self._cancel_token.is_set():
                errors.append(self._make_error(
                    "CANCELLED", "Crawl cancelled by user", "acquire", task_config.task_id, task_config.source_id, retryable=False
                ))
                break

            if current_url in visited_urls:
                logger.info("Already visited %s, stopping pagination", current_url)
                break
            visited_urls.add(current_url)

            # Fetch list page
            list_dto, list_error = self._fetch_page(current_url, task_config, f"list_page_{page_num}")
            if list_error:
                errors.append(list_error)
                # Check if we should retry or stop
                if not list_error.get("retryable", False):
                    break
                # Retry once
                time.sleep(2)
                list_dto, list_error = self._fetch_page(current_url, task_config, f"list_page_{page_num}_retry")
                if list_error:
                    errors.append(list_error)
                    break

            if list_dto:
                items.append(list_dto)

            # Parse list page to find detail URLs
            detail_urls = self._extract_detail_urls(list_dto, selectors, base_url)
            logger.info("Page %d: found %d detail URLs", page_num, len(detail_urls))

            # Fan-out to detail pages
            for idx, detail_url in enumerate(detail_urls):
                if self._cancel_token and self._cancel_token.is_set():
                    break

                if detail_url in visited_urls:
                    continue
                visited_urls.add(detail_url)

                detail_dto, detail_error = self._fetch_page(detail_url, task_config, f"detail_{page_num}_{idx}")
                if detail_error:
                    errors.append(detail_error)
                    continue
                if detail_dto:
                    items.append(detail_dto)

            # Check if we've reached max_pages before looking for next page
            if page_num >= max_pages:
                pagination_complete = True
                logger.info("Reached max_pages=%d, stopping pagination", max_pages)
                break

            # Check for next page
            next_url = self._find_next_page(list_dto, selectors, base_url, page_num)
            if not next_url:
                pagination_complete = True
                logger.info("No next page found, pagination complete")
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

    def _fetch_page(self, url: str, task_config: TaskConfigDTO, trace_label: str) -> tuple[Optional[RawDataDTO], Optional[dict]]:
        """Fetch a single page and wrap as RawDataDTO with HTML asset."""
        try:
            def _do_fetch() -> str:
                from utils.http import response_text
                return response_text(self._session.get(url))

            # Use cache if available
            if self._cache:
                html = self._cache.get_or_fetch(_do_fetch, url, force=False)
            else:
                html = _do_fetch()

            # Create MediaAsset with raw HTML
            asset = MediaAsset(
                media_type="text",
                mime_type="text/html",
                data=html.encode("utf-8"),
                metadata={"source_url": url, "trace_label": trace_label},
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
                    "status_code": 200,  # Would need session to expose this
                },
                assets=[asset],
            )
            return dto, None

        except BlockedError as e:
            return None, self._make_error("BLOCKED", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=True)
        except Exception as e:
            logger.exception("Fetch failed for %s", url)
            return None, self._make_error("FETCH_ERROR", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=True)

    def _extract_detail_urls(self, dto: RawDataDTO, selectors: dict, base_url: str) -> list[str]:
        """Parse list page HTML to extract detail page URLs."""
        if not dto.assets:
            return []

        asset = dto.assets[0]
        if asset.media_type != "text" or not asset.data:
            return []

        html = asset.data.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")

        item_sel = selectors.get("item")
        profile_sel = selectors.get("profile", "href")

        if not item_sel:
            logger.warning("No 'item' selector configured, cannot extract detail URLs")
            return []

        items = soup.select(item_sel)
        urls = []

        for item in items:
            url = self._get_field(item, profile_sel)
            if url:
                urls.append(urljoin(base_url, url))
            else:
                # Fallback: if item itself is <a>
                tag = item if item.name == "a" else item.find("a")
                if tag and tag.get("href"):
                    urls.append(urljoin(base_url, tag["href"]))

        return urls

    def _find_next_page(self, dto: RawDataDTO, selectors: dict, base_url: str, current_page: int) -> Optional[str]:
        """Find next page URL from pagination controls."""
        if not dto.assets:
            return None

        asset = dto.assets[0]
        if asset.media_type != "text" or not asset.data:
            return None

        html = asset.data.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")

        # Try configured next_page selector
        next_sel = selectors.get("next_page")
        if next_sel:
            next_link = soup.select_one(next_sel)
            if next_link:
                href = next_link.get("href")
                if href:
                    return urljoin(base_url, href)

        # Fallback: look for common pagination patterns
        for sel in [".next a", ".pagination .next a", "a[rel='next']", f"a:contains('{current_page + 1}')"]:
            try:
                next_link = soup.select_one(sel)
                if next_link:
                    href = next_link.get("href")
                    if href:
                        return urljoin(base_url, href)
            except Exception:
                continue

        return None

    def _get_field(self, tag: Tag, selector: str) -> Optional[str]:
        """Extract field from tag using selector (CSS or attribute)."""
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
        """Cleanup resources."""
        pass