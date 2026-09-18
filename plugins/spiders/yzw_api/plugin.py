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
from datetime import datetime
from typing import Optional

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from plugins.base import PluginContext
from plugins.spiders import SpiderPlugin, make_error, ERROR_HTTP_BLOCKED, ERROR_PIPELINE_CANCELLED, ERROR_PARSE_FAILED, ERROR_PIPELINE_CONFIG_INVALID
from utils.http import BlockedError

logger = logging.getLogger(__name__)

BASE_URL = "https://yz.chsi.com.cn"
SCHOOL_CODE_URL = f"{BASE_URL}/zsml/querySchAction.do"
MAJOR_DIR_URL = f"{BASE_URL}/zsml/rs/dws.do"


class YzwApiSpiderPlugin(SpiderPlugin):
    """Spider plugin for 研招网 (yz.chsi.com.cn) API.

    Input: TaskConfigDTO with config_snapshot containing school_code, year, category/major_codes, university.
    Output: RawDataBatch containing RawDataDTO items with JSON assets (one per yjxkdm discipline).

    Must produce different schema_id than static HTML to ensure separate parse chain.
    """

    name = "yzw_api"
    version = "1.0.0"

    def execute(self, task_config: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        session = context.http
        cache = context.cache
        cancel_token = context.cancel_token

        if not session:
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

        yjxkdm_list = self._resolve_yjxkdm(category, major_codes)
        if not yjxkdm_list:
            errors.append(make_error(
                ERROR_PIPELINE_CONFIG_INVALID,
                "No yjxkdm resolved from category/major_codes",
                task_id=task_config.task_id,
                source_id=task_config.source_id,
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
            if cancel_token and cancel_token.is_set():
                errors.append(make_error(
                    ERROR_PIPELINE_CANCELLED,
                    "Crawl cancelled by user",
                    task_id=task_config.task_id,
                    source_id=task_config.source_id,
                ))
                break

            discipline_items, discipline_errors = self._fetch_discipline(
                school_code=school_code,
                university=university or "",
                year=year,
                yjxkdm=yjxkdm,
                page_size=page_size,
                task_config=task_config,
                session=session,
                cache=cache,
                cancel_token=cancel_token,
            )
            items.extend(discipline_items)
            errors.extend(discipline_errors)
            logger.info("yjxkdm=%s fetched %d items", yjxkdm, len(discipline_items))

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

    def _resolve_yjxkdm(self, category, major_codes):
        if category:
            try:
                from config.major_mapping import get_major_codes
                return get_major_codes(category, level="first_level")
            except Exception as e:
                logger.warning("Failed to get major codes for category %s: %s", category, e)
        elif major_codes:
            return sorted({mc[:4] for mc in major_codes if len(mc) >= 4})
        return []

    def _fetch_discipline(self, school_code, university, year, yjxkdm, page_size, task_config, session, cache, cancel_token):
        items: list[RawDataDTO] = []
        errors: list[dict] = []

        params = {
            "dwmc": university,
            "dwdm": school_code,
            "mldm": "08",
            "mlmc": "工学",
            "yjxkdm": yjxkdm,
            "zymc": "",
            "xxfs": "1",
            "tydxs": "",
            "jsggjh": "",
            "start": 0,
            "pageSize": page_size,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        dto, error = self._fetch_api_page(MAJOR_DIR_URL, params, headers, task_config, f"yzw_{yjxkdm}_page_1", session, cache)
        if error:
            errors.append(error)
            return items, errors
        if not dto:
            return items, errors

        items.append(dto)

        try:
            data = json.loads(dto.assets[0].data.decode("utf-8"))
            total = data.get("total", 0)
            fetched = len(data.get("data", []))

            while fetched < total:
                if cancel_token and cancel_token.is_set():
                    errors.append(make_error(
                        ERROR_PIPELINE_CANCELLED,
                        "Crawl cancelled",
                        task_id=task_config.task_id,
                        source_id=task_config.source_id,
                    ))
                    break

                params["start"] = fetched
                page_num = (fetched // page_size) + 1
                dto, error = self._fetch_api_page(MAJOR_DIR_URL, params, headers, task_config, f"yzw_{yjxkdm}_page_{page_num}", session, cache)
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
            errors.append(make_error(ERROR_PARSE_FAILED, str(e), task_id=task_config.task_id, source_id=task_config.source_id))

        return items, errors

    def _fetch_api_page(self, url, params, headers, task_config, trace_label, session, cache):
        try:
            def _do_fetch() -> str:
                return session.post(url, data=params, extra_headers=headers).text

            if cache:
                cache_key = f"{url}?yjxkdm={params.get('yjxkdm')}&start={params.get('start')}"
                text = cache.get_or_fetch(_do_fetch, cache_key, force=False)
            else:
                text = _do_fetch()

            asset = MediaAsset(
                media_type="text",
                mime_type="application/json",
                data=text.encode("utf-8"),
                metadata={"source_url": url, "trace_label": trace_label, "params": params},
            )
            return RawDataDTO(
                source_id=task_config.source_id,
                url=url,
                content_type="application/json",
                encoding="utf-8",
                fetched_at=datetime.now().isoformat(),
                trace={"trace_label": trace_label, "task_id": task_config.task_id, "params": params},
                assets=[asset],
            ), None

        except BlockedError as e:
            return None, make_error(ERROR_HTTP_BLOCKED, str(e), task_id=task_config.task_id, source_id=task_config.source_id)
        except Exception as e:
            logger.exception("YZW API fetch failed for %s", url)
            return None, make_error("PLUGIN_EXECUTE_FAILED", str(e), task_id=task_config.task_id, source_id=task_config.source_id)
