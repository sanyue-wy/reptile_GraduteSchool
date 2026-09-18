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
from typing import Any, Optional

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from utils.http import PoliteSession, BlockedError
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)


class PDFListSpiderPlugin:
    """Spider plugin for PDF faculty lists.

    Input: TaskConfigDTO with config_snapshot containing pdf_url.
    Output: RawDataBatch containing RawDataDTO with PDF document asset.
    """

    name = "pdf_list"
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
        pdf_url = cfg.get("pdf_url") or task_config.target_url

        if not pdf_url:
            raise ValueError("pdf_url is required in config_snapshot")

        items: list[RawDataDTO] = []
        errors: list[dict] = []

        if self._cancel_token and self._cancel_token.is_set():
            errors.append(self._make_error(
                "CANCELLED", "Crawl cancelled by user", "acquire", task_config.task_id, task_config.source_id, retryable=False
            ))
            return RawDataBatch(
                schema_version="1",
                task_id=task_config.task_id,
                items=items,
                pagination_complete=True,
                errors=errors,
            )

        dto, error = self._fetch_pdf(pdf_url, task_config, "pdf_list")
        if error:
            errors.append(error)
        if dto:
            items.append(dto)

        return RawDataBatch(
            schema_version="1",
            task_id=task_config.task_id,
            items=items,
            pagination_complete=True,  # PDF is single document
            errors=errors,
        )

    def _fetch_pdf(self, pdf_url: str, task_config: TaskConfigDTO, trace_label: str) -> tuple[Optional[RawDataDTO], Optional[dict]]:
        """Fetch PDF and wrap as RawDataDTO with document asset."""
        try:
            def _do_fetch() -> bytes:
                resp = self._session.get(pdf_url)
                return resp.content

            if self._cache:
                # Cache stores base64-encoded bytes
                def _fetch_encoded() -> str:
                    return base64.b64encode(_do_fetch()).decode("ascii")

                encoded = self._cache.get_or_fetch(_fetch_encoded, f"pdf_list:base64:v1:{pdf_url}", force=False)
                pdf_bytes = base64.b64decode(encoded, validate=True)
            else:
                pdf_bytes = _do_fetch()

            # Create MediaAsset with PDF document
            asset = MediaAsset(
                media_type="document",
                mime_type="application/pdf",
                data=pdf_bytes,
                metadata={"source_url": pdf_url, "trace_label": trace_label},
            )

            dto = RawDataDTO(
                source_id=task_config.source_id,
                url=pdf_url,
                content_type="application/pdf",
                encoding="binary",
                fetched_at=datetime.now().isoformat(),
                trace={
                    "trace_label": trace_label,
                    "task_id": task_config.task_id,
                },
                assets=[asset],
            )
            return dto, None

        except BlockedError as e:
            return None, self._make_error("BLOCKED", str(e), "acquire", task_config.task_id, task_config.source_id, retryable=True)
        except Exception as e:
            logger.exception("PDF fetch failed for %s", pdf_url)
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