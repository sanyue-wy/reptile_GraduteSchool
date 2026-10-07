# -*- coding: utf-8 -*-
"""
URL Prober Spider Plugin
========================
HEAD probes candidate paths to find working URLs for a target domain.

Input:  TaskConfigDTO with target_url as base domain
Output: RawDataDTO with content from first 200 response
"""

import logging
from datetime import datetime
from typing import Optional

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.task import TaskConfigDTO
from plugins.base import PluginContext
from plugins.spiders import SpiderPlugin, make_error, ERROR_HTTP_BLOCKED, ERROR_HTTP_TIMEOUT

logger = logging.getLogger(__name__)

CANDIDATE_PATHS = [
    "/szdw/list.htm",
    "/szdw/zzjs.htm",
    "/dept/list.htm",
    "/faculty/",
    "/teachers/",
    "/",
    "/index.htm",
]


class UrlProberSpiderPlugin(SpiderPlugin):
    """Probe candidate paths to find available URLs.

    Takes a base URL (or domain), tries multiple path candidates via HEAD requests,
    returns the first one that returns 200 OK.
    """

    name = "url_prober"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        session = context.http
        cancel_token = context.cancel_token

        if not session:
            raise RuntimeError("PoliteSession not injected via context")

        base_url = data.target_url
        source_id = getattr(data, 'source_id', data.source_id if hasattr(data, 'source_id') else 'prober')

        # Ensure base_url ends without trailing slash for path joining
        base = base_url.rstrip("/")

        attempts: list[dict] = []
        errors: list[dict] = []

        if cancel_token and cancel_token.is_set():
            errors.append(make_error(
                ERROR_HTTP_BLOCKED,
                "Crawl cancelled by user",
                task_id=data.task_id,
                source_id=source_id,
            ))
            return RawDataBatch(
                schema_version="1",
                task_id=data.task_id,
                items=[],
                pagination_complete=True,
                errors=errors,
            )

        for path in CANDIDATE_PATHS:
            if cancel_token and cancel_token.is_set():
                break

            probe_url = f"{base}{path}"
            result = self._probe_url(probe_url, data, context, f"probe_{path.replace('/', '_')}")

            if result.success:
                # Found working URL - return it as RawDataDTO
                logger.info("Successfully probed: %s", probe_url)
                asset = MediaAsset(
                    media_type="text",
                    mime_type=result.content_type or "text/html",
                    data=result.content.encode("utf-8") if isinstance(result.content, str) else result.content,
                    metadata={
                        "source_url": probe_url,
                        "success": True,
                        "http_status": 200,
                        "probe_path": path,
                    },
                    fetched_at=datetime.now().isoformat(),
                )
                dto = RawDataDTO(
                    source_id=source_id,
                    url=probe_url,
                    content_type=result.content_type or "text/html",
                    encoding="utf-8",
                    fetched_at=datetime.now().isoformat(),
                    trace={"probe_attempted": path},
                    assets=[asset],
                )
                return RawDataBatch(
                    schema_version="1",
                    task_id=data.task_id,
                    items=[dto],
                    pagination_complete=True,
                    errors=errors,
                    fetched_at=datetime.now().isoformat(),
                )

            attempts.append({
                "path": path,
                "status": result.status_code,
                "code": result.error_code,
            })

        # All probes failed
        logger.warning("All probe paths failed for %s: %s", base_url, attempts)
        error_msg = f"All probe paths exhausted: {attempts}"
        errors.append(make_error(
            ERROR_HTTP_BLOCKED if any(a.get('code') in ('BLOCKED', 'FORBIDDEN') for a in attempts) else ERROR_HTTP_TIMEOUT,
            error_msg,
            task_id=data.task_id,
            source_id=source_id,
            retryable=True,
            diagnostics={"attempts": attempts},
        ))

        return RawDataBatch(
            schema_version="1",
            task_id=data.task_id,
            items=[],
            pagination_complete=True,
            errors=errors,
            fetched_at=datetime.now().isoformat(),
        )

    def _probe_url(self, url: str, task_config: TaskConfigDTO, context: PluginContext, trace_label: str):
        """Probe a single URL with HEAD request."""

        class ProbeResult:
            def __init__(self, success=False, content=b"", content_type="", status_code=0, error_code=None):
                self.success = success
                self.content = content
                self.content_type = content_type
                self.status_code = status_code
                self.error_code = error_code

        try:
            response = context.http.head(url, timeout=10)
            if response.status_code == 200:
                # For content, we might need to GET the page
                content_resp = context.http.get(url, timeout=10)
                return ProbeResult(
                    success=True,
                    content=content_resp.text if hasattr(content_resp, 'text') else b"",
                    content_type=response.headers.get("Content-Type", "text/html"),
                    status_code=200,
                )
            return ProbeResult(success=False, status_code=response.status_code)

        except Exception as e:
            logger.debug("Probe failed for %s: %s", url, e)
            return ProbeResult(success=False, error_code="ERROR", status_code=0)
