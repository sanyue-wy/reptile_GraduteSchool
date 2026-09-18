# -*- coding: utf-8 -*-
"""
YZW (研招网) API Spider Plugin
===============================
Migrated from spiders/yzw_api.py - YzwEngine/YzwClient.

Delivers 研招网 JSON responses as MediaAsset(media_type="text", mime_type="application/json").
Separate parse chain from static HTML (different schema_id for processor routing).
"""

import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from utils.http import PoliteSession, BlockedError
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)

BASE_URL = "https://yz.chsi.com.cn"
SCHOOL_CODE_URL = f"{BASE_URL}/zsml/querySchAction.do"
MAJOR_DIR_URL = f"{BASE_URL}/zsml/rs/dws.do"


class YzwApiSpiderPlugin:
    """Spider plugin for 研招网 (yz.chsi.com.cn) API.

    Input: TaskConfigDTO with config_snapshot containing school_code, year, category/major_codes, university.
    Output: RawDataBatch containing RawDataDTO items with JSON assets (one per yjxkdm discipline).

    Must produce different schema_id than static HTML to ensure separate parse chain.
    """

    name = "yzw_api"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def __init__(self):
        self._session: Optional[PoliteSession] = None
        self._cache: Optional[CrawlCache] = None
        self._cancel_token: Any = None
        self._school_code_cache: Dict[str, str] = {}

    def setup(self, context) -> None:
        self._session = context.http
        self._cache = context.cache
        self._cancel_token = context.cancel_token

    def execute(self, task_config: TaskConfigDTO, context) -> RawDataBatch:
        self.setup(context)

        if not self._session:
            raise RuntimeError("PoliteSession not injected via context")

        cfg = task_config.config_snapshot
        school_code = cfg.get("school_code")
        year = cfg.get("year")
        major_codes = cfg.get("major_codes")
        category = cfg.get("category")
        university = cfg.get("university")

        if not school_code or not year:
            raise ValueError("school_code and year are required in config_snapshot")

        items: list[RawDataDTO] = []
        errors: list[dict] = []

        # Determine yjxkdm list (first-level discipline codes)
        yjxkdm_list = self._resolve_yjxkdm(category, major_codes)
        if not yjxkdm_list:
            errors.append(self._make_error(
                "CONFIG_ERROR", "No yjxkdm resolved from category/major_codes", "acquire", task_config.task_id, task_config.source_id, retryable=False
            ))
            return RawDataBatch(
                schema_version="1",
                task_id=task_config.task_id,
                items=items,
                pagination_complete=True,
                errors=errors,
            )

        page_size = cfg.get("page_size", 500)

        for yjxkdm in yjxkdm_list:
            if self._cancel_token and self._cancel_token.is_set():
                errors.append(self._make_error(
                    "CANCELLED", "Crawl cancelled by user", "acquire", task_config.task_id, task_config.source_id, retryable=False
                ))
                break

            discipline_items, discipline_errors = self._fetch_discipline(
                school_code=school_code,
                university=university or "",
                year=year,
                yjxkdm=yjxkdm,
                page_size=page_size,
                task_config=task_config,
            )
            items.extend(discipline_items)
            errors.extend(discipline_errors)
            logger.info("yjxkdm=%s fetched %d items", yjxkdm, len(discipline_items))

        # Filter by major_codes if provided
        if major_codes and items:
            filtered_items = []
            for item in items:
                if item.assets:
                    try:
                        data = json.loads(item.assets[0].data.decode("utf-8"))
                        for record in data.get("data", []):
                            if record.get("zydm", "") in major_codes:
                                filtered_items.append(item)
                                break
                    except Exception:
                        pass
            logger.info("Filtered by major_codes: %d -> %d", len(items), len(filtered_items))
            items = filtered_items

        return RawDataBatch(
            schema_version="1",
            task_id=task_config.task_id,
            items=items,
            pagination_complete=True,
            errors=errors,
        )

    def _resolve_yjxkdm(self, category: Optional[str], major_codes: Optional[List[str]]) -> List[str]:
        """Resolve first-level discipline codes from category or major_codes."""
        if category:
            try:
                from config.major_mapping import get_major_codes
                return get_major_codes(category, level="first_level")
            except Exception as e:
                logger.warning("Failed to get major codes for category %s: %s", category, e)
        elif major_codes:
            # Derive from major codes (first 4 digits)
            return sorted({mc[:4] for mc in major_codes if len(mc) >= 4})
        return []

    def _fetch_discipline(
        self,
        school_code: str,
        university: str,
        year: int,
        yjxkdm: str,
        page_size: int,
        task_config: TaskConfigDTO,
    ) -> tuple[list[RawDataDTO], list[dict]]:
        """Fetch all pages for a single discipline."""
        items: list[RawDataDTO] = []
        errors: list[dict] = []

        params = {
            "dwmc": university,
            "dwdm": school_code,
            "mldm": "08",  # Engineering
            "mlmc": "工学",
            "yjxkdm": yjxkdm,
            "zymc": "",
            "xxfs": "1",    # Full-time
            "tydxs": "",
            "jsggjh": "",
            "start": 0,
            "pageSize": page_size,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        # First page to get total
        dto, error = self._fetch_api_page(MAJOR_DIR_URL, params, headers, task_config, f"yzw_{yjxkdm}_page_1")
        if error:
            errors.append(error)
            return items, errors
        if not dto:
            return items, errors

        items.append(dto)

        # Parse total from first page
        try:
            data = json.loads(dto.assets[0].data.decode("utf-8"))
            total = data.get("total", 0)
            fetched = len(data.get("data", []))

            # Fetch remaining pages
            while fetched < total:
                if self._cancel_token and self._cancel_token.is_set():
                    errors.append(self._make_error(
                        "CANCELLED", "Crawl cancelled", "acquire", task_config.task_id, task_config.source_id, retryable=False
                    ))
                    break

                params["start"] = fetched
                page_num = (fetched // page_size) + 1
                dto, error = self._fetch_api_page(MAJOR_DIR_URL, params, headers, task_config, f"yzw_{yjxkdm}_page_{page_num}")
                if error:
                    errors.append(error)
                    if not error.get("retryable", False):
                        break
                if dto:
                    items.append(dto)
                    try:
                        page_data = json.loads(dto.assets[0].data.decode("utf-8"))
                        fetched += len(page_data.get("data", []))
                    except Exception:
                        break
                else:
                    break

                if not dto or not dto.assets:
                    break

        except Exception as e:
            logger.exception("Failed to parse yjxkdm=%s response", yjxkdm)
            errors.append(self._make_error("PARSE_ERROR", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=False))

        return items, errors

    def _fetch_api_page(
        self,
        url: str,
        params: dict,
        headers: dict,
        task_config: TaskConfigDTO,
        trace_label: str,
    ) -> tuple[Optional[RawDataDTO], Optional[dict]]:
        """Fetch a single API page."""
        try:
            def _do_fetch() -> str:
                return self._session.post(url, data=params, extra_headers=headers).text

            if self._cache:
                cache_key = f"{url}?yjxkdm={params.get('yjxkdm')}&start={params.get('start')}"
                text = self._cache.get_or_fetch(_do_fetch, cache_key, force=False)
            else:
                text = _do_fetch()

            asset = MediaAsset(
                media_type="text",
                mime_type="application/json",
                data=text.encode("utf-8"),
                metadata={"source_url": url, "trace_label": trace_label, "params": params},
            )

            dto = RawDataDTO(
                source_id=task_config.source_id,
                url=url,
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
            logger.exception("YZW API fetch failed for %s", url)
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