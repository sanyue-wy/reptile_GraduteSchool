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
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from plugins.base import PluginContext
from plugins.spiders import SpiderPlugin, make_error, ERROR_HTTP_BLOCKED, ERROR_PIPELINE_CANCELLED
from utils.http import BlockedError

logger = logging.getLogger(__name__)


class StaticHtmlSpiderPlugin(SpiderPlugin):
    """Spider plugin for static HTML faculty list pages.

    Input: TaskConfigDTO (with config_snapshot containing selectors, list_url, etc.)
    Output: RawDataBatch containing RawDataDTO items with HTML assets.
    """

    name = "static_html"
    version = "1.0.0"

    def execute(self, task_config: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        session = context.http
        cache = context.cache
        cancel_token = context.cancel_token

        if not session:
            raise RuntimeError("PoliteSession not injected via context")

        cfg = task_config.config_snapshot
        list_url = cfg.get("list_url") or task_config.target_url
        selectors = cfg.get("selectors", {})
        max_pages = cfg.get("max_pages", 20)
        base_url = cfg.get("base_url")
        # Timeout and retry config from plugin params
        request_timeout = cfg.get("timeout", 30)
        max_retries = cfg.get("max_retries", 3)
        retry_backoff = cfg.get("retry_backoff", 2)

        if not list_url:
            raise ValueError("list_url is required in config_snapshot")

        if not base_url:
            p = urlparse(list_url)
            base_url = f"{p.scheme}://{p.netloc}{p.path.rsplit('/', 1)[0]}/"

        items: list[RawDataDTO] = []
        errors: list[dict] = []
        pagination_complete = False
        next_page_token = None
        page_num = 1
        current_url = list_url
        visited_urls: set[str] = set()

        while page_num <= max_pages:
            if cancel_token and cancel_token.is_set():
                errors.append(make_error(
                    ERROR_PIPELINE_CANCELLED,
                    "Crawl cancelled by user",
                    task_id=task_config.task_id,
                    source_id=task_config.source_id,
                ))
                break

            if current_url in visited_urls:
                logger.info("Already visited %s, stopping pagination", current_url)
                break
            visited_urls.add(current_url)

            list_dto, list_error = self._fetch_page(
                current_url, task_config, f"list_page_{page_num}", session, cache,
                timeout=request_timeout, max_retries=max_retries, retry_backoff=retry_backoff
            )
            if list_error:
                errors.append(list_error)
                break  # 内部已含重试，外层不再二次重试

            if list_dto:
                items.append(list_dto)

            detail_urls = self._extract_detail_urls(list_dto, selectors, base_url)
            logger.info("Page %d: found %d detail URLs", page_num, len(detail_urls))

            for idx, detail_url in enumerate(detail_urls):
                if cancel_token and cancel_token.is_set():
                    break
                if detail_url in visited_urls:
                    continue
                visited_urls.add(detail_url)

                detail_dto, detail_error = self._fetch_page(
                    detail_url, task_config, f"detail_{page_num}_{idx}", session, cache,
                    timeout=request_timeout, max_retries=max_retries, retry_backoff=retry_backoff
                )
                if detail_error:
                    errors.append(detail_error)
                    continue
                if detail_dto:
                    items.append(detail_dto)

            if page_num >= max_pages:
                pagination_complete = True
                logger.info("Reached max_pages=%d, stopping pagination", max_pages)
                break

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

    def _fetch_page(self, url: str, task_config: TaskConfigDTO, trace_label: str,
                    session, cache, timeout: int = 30, max_retries: int = 3,
                    retry_backoff: int = 2) -> tuple[Optional[RawDataDTO], Optional[dict]]:
        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                def _do_fetch() -> str:
                    from utils.http import response_text
                    return response_text(session.get(url, timeout=timeout))

                if cache:
                    html = cache.get_or_fetch(_do_fetch, url, force=False)
                else:
                    html = _do_fetch()

                asset = MediaAsset(
                    media_type="text",
                    mime_type="text/html",
                    data=html.encode("utf-8"),
                    metadata={"source_url": url, "trace_label": trace_label},
                )
                return RawDataDTO(
                    source_id=task_config.source_id,
                    url=url,
                    content_type="text/html",
                    encoding="utf-8",
                    fetched_at=datetime.now().isoformat(),
                    trace={"trace_label": trace_label, "task_id": task_config.task_id, "status_code": 200},
                    assets=[asset],
                ), None

            except BlockedError as e:
                # 反爬拦截不可重试，直接返回
                return None, make_error(ERROR_HTTP_BLOCKED, str(e), task_id=task_config.task_id, source_id=task_config.source_id)
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = retry_backoff ** (attempt - 1) * 2
                    logger.warning("Fetch %s failed (attempt %d/%d): %s, retrying in %ds",
                                   url, attempt, max_retries, e, delay)
                    time.sleep(delay)
                else:
                    logger.exception("Fetch failed for %s after %d attempts", url, max_retries)
                    err_type = self._classify_error(e)
                    return None, make_error(err_type, str(e), task_id=task_config.task_id, source_id=task_config.source_id)
        return None, make_error("PLUGIN_EXECUTE_FAILED", str(last_error), task_id=task_config.task_id, source_id=task_config.source_id)

    @staticmethod
    def _classify_error(error: Exception) -> str:
        """将异常映射到失败分类（与 failures.json error_type 对齐）。"""
        msg = str(error).lower()
        if "getaddrinfo" in msg or "name resolution" in msg or "failed to resolve" in msg:
            return "DNS_ERROR"
        if "timed out" in msg or "timeout" in msg or "max retries" in msg:
            return "TIMEOUT"
        if "404" in msg or "not found" in msg:
            return "HTTP_ERROR"
        return "PLUGIN_EXECUTE_FAILED"

    def _extract_detail_urls(self, dto: RawDataDTO, selectors: dict, base_url: str) -> list[str]:
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
                tag = item if item.name == "a" else item.find("a")
                if tag and tag.get("href"):
                    urls.append(urljoin(base_url, tag["href"]))
        return urls

    def _find_next_page(self, dto: RawDataDTO, selectors: dict, base_url: str, current_page: int) -> Optional[str]:
        if not dto.assets:
            return None
        asset = dto.assets[0]
        if asset.media_type != "text" or not asset.data:
            return None

        html = asset.data.decode("utf-8", errors="replace")
        soup = BeautifulSoup(html, "lxml")

        next_sel = selectors.get("next_page")
        if next_sel:
            next_link = soup.select_one(next_sel)
            if next_link:
                href = next_link.get("href")
                if href:
                    return urljoin(base_url, href)

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

    def _get_field(self, tag: Tag, selector: str) -> Optional[str]:
        if selector == "text" or selector == tag.name:
            return tag.get_text(strip=True) or tag.get("title", "")
        found = tag.select_one(selector)
        if found:
            return found.get_text(strip=True) or found.get("title", "")
        val = tag.get(selector)
        if val:
            return str(val)
        return None
