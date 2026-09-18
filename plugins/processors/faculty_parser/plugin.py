# -*- coding: utf-8 -*-
"""
Faculty Parser Plugin
=====================
Parse stage plugin: RawDataBatch -> RecordBatch.

Extracts education faculty fields from static HTML assets produced by
the static_html spider. Selectors are driven by instance params (profile: education.tutor.v1).
Pure parsing — no network requests.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from contracts.asset import MediaAsset
from contracts.profiles.education import EDUCATION_TUTOR_V1
from contracts.raw import RawDataBatch
from contracts.record import NormalizedRecordDTO, RecordBatch

logger = logging.getLogger(__name__)

# Default selectors for common faculty list pages
DEFAULT_ITEM_SEL = ".teacher"
DEFAULT_NAME_SEL = "a"
DEFAULT_RESEARCH_SEL = ".research"
DEFAULT_PROFILE_URL_ATTR = "href"
DEFAULT_TITLE_SEL = ".title"
DEFAULT_COLLEGE_SEL = ".college"
DEFAULT_CATEGORY_SEL = ".category"


def _normalize_text(value: str) -> str:
    """Normalize whitespace: full-width to half-width, collapse spaces."""
    if not value:
        return ""
    value = value.replace("　", " ").replace("\xa0", " ")
    return " ".join(value.split())


def _extract_text(tag, selector: str) -> str:
    """Extract text from a BeautifulSoup tag using a CSS selector."""
    if not tag:
        return ""
    found = tag.select_one(selector)
    return _normalize_text(found.get_text(strip=True)) if found else ""


def _generate_record_id(university: str, college: str, name: str, url: str) -> str:
    """Generate deterministic record_id from natural key fields."""
    key = f"{university}|{college}|{name}|{url}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class FacultyParserPlugin:
    """Parse faculty list HTML pages into NormalizedRecordDTO records.

    Input:  RawDataBatch.v1  (HTML assets from static_html spider)
    Output: RecordBatch.v1   (NormalizedRecordDTO with education.tutor.v1 fields)
    """

    name = "faculty_parser"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RawDataBatch.v1"
    output_schema = "RecordBatch.v1"

    def __init__(self):
        self._params: dict[str, Any] = {}
        self._profile: str = EDUCATION_TUTOR_V1

    def setup(self, context) -> None:
        """Read selectors and profile from instance params."""
        self._params = context.config_snapshot.get("plugins", {}).get("faculty_parse", {}).get("params", {})
        self._profile = self._params.get("profile", EDUCATION_TUTOR_V1)

    def execute(self, raw_batch: RawDataBatch, context) -> RecordBatch:
        """Parse all HTML assets in the raw batch into records."""
        self.setup(context)

        item_sel = self._params.get("item_selector", DEFAULT_ITEM_SEL)
        name_sel = self._params.get("name_selector", DEFAULT_NAME_SEL)
        research_sel = self._params.get("research_selector", DEFAULT_RESEARCH_SEL)
        profile_url_attr = self._params.get("profile_url_attr", DEFAULT_PROFILE_URL_ATTR)
        title_sel = self._params.get("title_selector", DEFAULT_TITLE_SEL)
        college_sel = self._params.get("college_selector", DEFAULT_COLLEGE_SEL)
        category_sel = self._params.get("category_selector", DEFAULT_CATEGORY_SEL)

        # Derive university / college / year from context or config
        cfg = context.config_snapshot
        university = cfg.get("university", "")
        college = cfg.get("college", "")
        category = cfg.get("category", "")
        year = cfg.get("year", 0)
        base_url = cfg.get("base_url", "")
        source_id = cfg.get("source_id", raw_batch.items[0].source_id if raw_batch.items else "")

        records: list[NormalizedRecordDTO] = []
        media_refs: list[str] = []
        errors: list[dict] = []

        for idx, raw_item in enumerate(raw_batch.items):
            if context.check_cancelled():
                break

            # Extract HTML from assets
            html_content = self._get_html_content(raw_item)
            if html_content is None:
                errors.append(self._make_error(
                    "PARSE_FAILED",
                    f"No HTML content found in item {idx}",
                    context,
                    source_id=raw_item.source_id,
                ))
                continue

            # Collect media refs for images/assets found in HTML
            item_media = self._extract_media_refs(html_content, raw_item.url, base_url)
            media_refs.extend(item_media)

            # Parse faculty entries from this page
            page_records = self._parse_faculty_list(
                html=html_content,
                source_url=raw_item.url,
                university=university,
                college=college,
                category=category,
                year=year,
                source_id=raw_item.source_id,
                fetched_at=raw_item.fetched_at,
                item_sel=item_sel,
                name_sel=name_sel,
                research_sel=research_sel,
                profile_url_attr=profile_url_attr,
                title_sel=title_sel,
                college_sel=college_sel,
                category_sel=category_sel,
                base_url=base_url or raw_item.url,
                media_refs=item_media,
            )
            records.extend(page_records)

        logger.info(
            "faculty_parser: parsed %d records from %d raw items (%s/%s)",
            len(records), len(raw_batch.items), university, college,
        )

        return RecordBatch(
            schema_version="1",
            records=records,
            stats={"parsed_count": len(records), "source_items": len(raw_batch.items)},
            source_completion={source_id: raw_batch.pagination_complete},
            errors=errors,
        )

    def _get_html_content(self, raw_item) -> Optional[str]:
        """Extract HTML string from a RawDataDTO's assets or legacy content."""
        # Prefer assets
        for asset in raw_item.assets:
            if asset.media_type == "text" and asset.data:
                return asset.data.decode("utf-8", errors="replace")
            if asset.media_type == "text" and asset.url:
                # URL-only assets need fetching — not in parser scope
                logger.warning("Asset has URL but no data; parser cannot fetch: %s", asset.url)
                return None
        # Legacy fallback
        if raw_item.content:
            return raw_item.content
        return None

    def _extract_media_refs(self, html: str, page_url: str, base_url: str) -> list[str]:
        """Extract image/media URLs from HTML for provenance tracking."""
        soup = BeautifulSoup(html, "lxml")
        refs = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                full_url = urljoin(base_url or page_url, src)
                refs.append(full_url)
        return refs

    def _parse_faculty_list(
        self,
        html: str,
        source_url: str,
        university: str,
        college: str,
        category: str,
        year: int,
        source_id: str,
        fetched_at: str,
        item_sel: str,
        name_sel: str,
        research_sel: str,
        profile_url_attr: str,
        title_sel: str,
        college_sel: str,
        category_sel: str,
        base_url: str,
        media_refs: list[str],
    ) -> list[NormalizedRecordDTO]:
        """Parse one HTML page into NormalizedRecordDTO records."""
        soup = BeautifulSoup(html, "lxml")
        items = soup.select(item_sel)
        records = []

        for item in items:
            # Name
            name_tag = item.select_one(name_sel) if name_sel else item.find("a")
            name = _normalize_text(name_tag.get_text(strip=True)) if name_tag else ""
            if not name:
                continue

            # Profile URL
            profile_url = ""
            if name_tag:
                href = name_tag.get(profile_url_attr, "")
                if href:
                    profile_url = urljoin(base_url, href)

            # Research areas
            research_text = _extract_text(item, research_sel)
            research_areas = [r.strip() for r in re.split(r"[,;，；、]", research_text) if r.strip()] if research_text else []

            # Title (if available)
            title = _extract_text(item, title_sel)

            # College override (if per-item selector exists)
            item_college = _extract_text(item, college_sel) or college

            # Category override
            item_category = _extract_text(item, category_sel) or category

            fields = {
                "university": university,
                "college": item_college,
                "category": item_category,
                "year": year,
                "name": name,
                "title": title,
                "research": "; ".join(research_areas) if research_areas else research_text,
                "profile_url": profile_url,
                "source_type": "官网师资页",
                "email": "",
                "phone": "",
                "education_background": "",
                "honors": [],
                "projects": [],
                "papers": [],
            }

            record_id = _generate_record_id(university, item_college, name, profile_url)

            records.append(NormalizedRecordDTO(
                record_id=record_id,
                dataset=f"{university}:{item_college}",
                schema_id=self._profile,
                fields=fields,
                provenance={
                    "source_id": source_id,
                    "url": source_url,
                    "fetched_at": fetched_at,
                },
                media_refs=media_refs[:],
            ))

        return records

    def _make_error(self, code: str, message: str, context, source_id: str = "") -> dict:
        return {
            "code": code,
            "message": message,
            "stage": "process",
            "task_id": getattr(context, "task_id", ""),
            "source_id": source_id,
            "retryable": False,
            "diagnostics": {},
        }

    def close(self) -> None:
        pass
