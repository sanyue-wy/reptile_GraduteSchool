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
from datetime import datetime
from urllib.parse import urlparse

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from plugins.base import PluginContext
from plugins.spiders import SpiderPlugin, make_error, ERROR_HTTP_BLOCKED, ERROR_PIPELINE_CANCELLED
from utils.http import BlockedError

logger = logging.getLogger(__name__)

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


class AjaxApiSpiderPlugin(SpiderPlugin):
    """Spider plugin for SudyCMS/WebPlus AJAX JSON APIs.

    Input: TaskConfigDTO with config_snapshot containing api_url, site_id, referer, etc.
    Output: RawDataBatch containing RawDataDTO items with JSON assets.
    """

    name = "ajax_api"
    version = "1.0.0"

    def execute(self, task_config: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        session = context.http
        cache = context.cache
        cancel_token = context.cancel_token

        if not session:
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

        p = urlparse(api_url)
        base_url = f"{p.scheme}://{p.netloc}" if p.netloc else ""

        for page_idx in range(1, max_pages + 1):
            if cancel_token and cancel_token.is_set():
                errors.append(make_error(
                    ERROR_PIPELINE_CANCELLED,
                    "Crawl cancelled by user",
                    task_id=task_config.task_id,
                    source_id=task_config.source_id,
                ))
                break

            params["pageIndex"] = str(page_idx)

            dto, error = self._fetch_api_page(api_url, params, headers, task_config, f"api_page_{page_idx}", base_url, session, cache)
            if error:
                errors.append(error)
                if not error.get("retryable", False):
                    break
                continue

            if dto:
                items.append(dto)

            if page_idx == 1 and dto and dto.assets:
                try:
                    data = json.loads(dto.assets[0].data.decode("utf-8"))
                    total = data.get("total", 0)
                    if total <= page_size:
                        pagination_complete = True
                        break
                except Exception:
                    pass

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

    def _fetch_api_page(self, api_url, params, headers, task_config, trace_label, base_url, session, cache):
        try:
            def _do_fetch() -> str:
                return session.post(api_url, data=params, extra_headers=headers).text

            if cache:
                cache_key = f"{api_url}?pageIndex={params.get('pageIndex')}"
                text = cache.get_or_fetch(_do_fetch, cache_key, force=False)
            else:
                text = _do_fetch()

            asset = MediaAsset(
                media_type="text",
                mime_type="application/json",
                data=text.encode("utf-8"),
                metadata={"source_url": api_url, "trace_label": trace_label, "params": params},
            )
            return RawDataDTO(
                source_id=task_config.source_id,
                url=api_url,
                content_type="application/json",
                encoding="utf-8",
                fetched_at=datetime.now().isoformat(),
                trace={"trace_label": trace_label, "task_id": task_config.task_id, "params": params},
                assets=[asset],
            ), None

        except BlockedError as e:
            return None, make_error(ERROR_HTTP_BLOCKED, str(e), task_id=task_config.task_id, source_id=task_config.source_id)
        except Exception as e:
            logger.exception("API fetch failed for %s", api_url)
            return None, make_error("PLUGIN_EXECUTE_FAILED", str(e), task_id=task_config.task_id, source_id=task_config.source_id)
