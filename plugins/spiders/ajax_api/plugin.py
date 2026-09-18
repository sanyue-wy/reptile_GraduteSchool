# -*- coding: utf-8 -*-
"""
AJAX API Spider Plugin
======================
Migrated from spiders/ajax_api.py - AjaxApiEngine.

Delivers TRUE raw material batches for SudyCMS/WebPlus JSON APIs.
Each API response stored as MediaAsset(media_type="text", mime_type="application/json").
Pagination token loop with upper bound.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from utils.http import PoliteSession, BlockedError
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)

# SudyCMS generalQuery defaults
_DEFAULT_PARAMS = {
    "pageIndex": "1",
    "rows": "999",
    "conditions": '[{"field":"published","value":"1","judge":"="}]',
    "orders": '[{"field":"letter","type":"asc"}]',
    "returnInfos": (
        '[{"field":"title","name":"title"},'
        '{"field":"exField1","name":"exField1"},'
        '{"field":"degree","name":"degree"},'
        '{"field":"post","name":"post"},'
        '{"field":"cnUrl","name":"cnUrl"},'
        '{"field":"headerPic","name":"headerPic"}]'
    ),
    "articleType": "1",
    "level": "1",
}


class AjaxApiSpiderPlugin:
    """Spider plugin for SudyCMS/WebPlus AJAX JSON APIs.

    Input: TaskConfigDTO with config_snapshot containing api_url, site_id, referer, etc.
    Output: RawDataBatch containing RawDataDTO items with JSON assets.
    """

    name = "ajax_api"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def __init__(self):
        self._session: Optional[PoliteSession] = None
        self._cache: Optional[CrawlCache] = None
        self._cancel_token: Any = None

    def setup(self, context) -> None:
        self._session = context.http
        self._cache = context.cache
        self._cancel_token = context.cancel_token

    def execute(self, task_config: TaskConfigDTO, context) -> RawDataBatch:
        self.setup(context)

        if not self._session:
            raise RuntimeError("PoliteSession not injected via context")

        cfg = task_config.config_snapshot
        api_url = cfg.get("api_url")
        site_id = cfg.get("site_id")
        referer = cfg.get("referer")
        extra_params = cfg.get("extra_params", {})
        max_pages = cfg.get("max_pages", 10)
        page_size = cfg.get("page_size", 500)

        if not api_url or not site_id or not referer:
            raise ValueError("api_url, site_id, and referer are required in config_snapshot")

        items: list[RawDataDTO] = []
        errors: list[dict] = []
        pagination_complete = False
        next_page_token = None

        params = dict(_DEFAULT_PARAMS)
        params["siteId"] = site_id
        params["rows"] = str(page_size)
        if extra_params:
            params.update(extra_params)

        headers = {
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }

        # Resolve base_url from api_url for relative links
        p = urlparse(api_url)
        base_url = f"{p.scheme}://{p.netloc}" if p.netloc else ""

        for page_idx in range(1, max_pages + 1):
            if self._cancel_token and self._cancel_token.is_set():
                errors.append(self._make_error(
                    "CANCELLED", "Crawl cancelled by user", "acquire", task_config.task_id, task_config.source_id, retryable=False
                ))
                break

            params["pageIndex"] = str(page_idx)

            dto, error = self._fetch_api_page(api_url, params, headers, task_config, f"api_page_{page_idx}", base_url)
            if error:
                errors.append(error)
                if not error.get("retryable", False):
                    break
                continue

            if dto:
                items.append(dto)

            # Check if we got all data (pagination logic)
            # The API returns total in first page; we can check if we've fetched all
            if page_idx == 1 and dto and dto.assets:
                try:
                    data = json.loads(dto.assets[0].data.decode("utf-8"))
                    total = data.get("total", 0)
                    if total <= page_size:
                        pagination_complete = True
                        break
                except Exception:
                    pass

            # If this page returned fewer items than page_size, we're done
            if dto and dto.assets:
                try:
                    data = json.loads(dto.assets[0].data.decode("utf-8"))
                    items_count = len(data.get("data", []))
                    if items_count < page_size:
                        pagination_complete = True
                        break
                except Exception:
                    pass

            next_page_token = str(page_idx + 1)

        return RawDataBatch(
            schema_version="1",
            task_id=task_config.task_id,
            items=items,
            pagination_complete=pagination_complete,
            next_page_token=next_page_token if not pagination_complete else None,
            errors=errors,
        )

    def _fetch_api_page(
        self,
        api_url: str,
        params: dict,
        headers: dict,
        task_config: TaskConfigDTO,
        trace_label: str,
        base_url: str,
    ) -> tuple[Optional[RawDataDTO], Optional[dict]]:
        """Fetch a single API page and wrap as RawDataDTO with JSON asset."""
        try:
            def _do_fetch() -> str:
                return self._session.post(api_url, data=params, extra_headers=headers).text

            if self._cache:
                cache_key = f"{api_url}?pageIndex={params.get('pageIndex')}"
                text = self._cache.get_or_fetch(_do_fetch, cache_key, force=False)
            else:
                text = _do_fetch()

            # Create MediaAsset with raw JSON
            asset = MediaAsset(
                media_type="text",
                mime_type="application/json",
                data=text.encode("utf-8"),
                metadata={"source_url": api_url, "trace_label": trace_label, "params": params},
            )

            dto = RawDataDTO(
                source_id=task_config.source_id,
                url=api_url,
                content_type="application/json",
                encoding="utf-8",
                fetched_at=datetime.now().isoformat(),
                trace={
                    "trace_label": trace_label,
                    "task_id": task_config.task_id,
                    "params": params,
                },
                assets=[asset],
            )
            return dto, None

        except BlockedError as e:
            return None, self._make_error("BLOCKED", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=True)
        except Exception as e:
            logger.exception("API fetch failed for %s", api_url)
            return None, self._make_error("FETCH_ERROR", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=True)

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