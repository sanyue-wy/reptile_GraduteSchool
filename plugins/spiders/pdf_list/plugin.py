# -*- coding: utf-8 -*-
"""
PDF List Spider Plugin
======================
Migrated from spiders/pdf_list.py - PDFListEngine.

Delivers PDF content as MediaAsset(media_type="document", mime_type="application/pdf").
Parsing is left to processor plugins (or declared capability).
"""

import base64
import logging
from datetime import datetime

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from plugins.base import PluginContext
from plugins.spiders import SpiderPlugin, make_error, ERROR_HTTP_BLOCKED, ERROR_PIPELINE_CANCELLED
from utils.http import BlockedError

logger = logging.getLogger(__name__)


class PDFListSpiderPlugin(SpiderPlugin):
    """Spider plugin for PDF faculty lists.

    Input: TaskConfigDTO with config_snapshot containing pdf_url.
    Output: RawDataBatch containing RawDataDTO with PDF document asset.
    """

    name = "pdf_list"
    version = "1.0.0"

    def execute(self, task_config: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        session = context.http
        cache = context.cache
        cancel_token = context.cancel_token

        if not session:
            raise RuntimeError("PoliteSession not injected via context")

        cfg = task_config.config_snapshot
        pdf_url = cfg.get("pdf_url") or task_config.target_url

        if not pdf_url:
            raise ValueError("pdf_url is required in config_snapshot")

        items: list[RawDataDTO] = []
        errors: list[dict] = []

        if cancel_token and cancel_token.is_set():
            errors.append(make_error(
                ERROR_PIPELINE_CANCELLED,
                "Crawl cancelled by user",
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

        dto, error = self._fetch_pdf(pdf_url, task_config, "pdf_list", session, cache)
        if error:
            errors.append(error)
        if dto:
            items.append(dto)

        return RawDataBatch(
            schema_version="1",
            task_id=task_config.task_id,
            items=items,
            pagination_complete=True,
            errors=errors,
        )

    def _fetch_pdf(self, pdf_url, task_config, trace_label, session, cache):
        try:
            def _do_fetch() -> bytes:
                return session.get(pdf_url).content

            if cache:
                def _fetch_encoded() -> str:
                    return base64.b64encode(_do_fetch()).decode("ascii")

                encoded = cache.get_or_fetch(_fetch_encoded, f"pdf_list:base64:v1:{pdf_url}", force=False)
                pdf_bytes = base64.b64decode(encoded, validate=True)
            else:
                pdf_bytes = _do_fetch()

            asset = MediaAsset(
                media_type="document",
                mime_type="application/pdf",
                data=pdf_bytes,
                metadata={"source_url": pdf_url, "trace_label": trace_label},
            )
            return RawDataDTO(
                source_id=task_config.source_id,
                url=pdf_url,
                content_type="application/pdf",
                encoding="binary",
                fetched_at=datetime.now().isoformat(),
                trace={"trace_label": trace_label, "task_id": task_config.task_id},
                assets=[asset],
            ), None

        except BlockedError as e:
            return None, make_error(ERROR_HTTP_BLOCKED, str(e), task_id=task_config.task_id, source_id=task_config.source_id)
        except Exception as e:
            logger.exception("PDF fetch failed for %s", pdf_url)
            return None, make_error("PLUGIN_EXECUTE_FAILED", str(e), task_id=task_config.task_id, source_id=task_config.source_id)
