# -*- coding: utf-8 -*-
"""
Parser Fallback Plugin
======================
Parser plugin for fallback use when main faculty parser fails.

Input:  RawDataBatch (HTML pages with faculty content)
Output: RecordBatch

Fallback strategies:
  1. 常见 CSS 类名 (.teacher, .faculty, .person, .card, [class*=teacher])
  2. 收集含 @xxx.edu.cn 邮箱的父级块，提取姓名（中文 2-4 字）+ 邮箱
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import Any, Optional

from bs4 import BeautifulSoup

from contracts.raw import RawDataBatch, RawDataDTO
from contracts.record import NormalizedRecordDTO, RecordBatch
from contracts.profiles.education import EDUCATION_TUTOR_V1
from plugins.base import ParserPlugin

logger = logging.getLogger(__name__)

# Common faculty CSS selectors (in priority order)
FACULTY_SELECTORS = [
    ".teacher",
    ".faculty",
    ".person",
    ".person-card",
    ".teacher-card",
    ".faculty-card",
    "[class*='teacher']",
    "[class*='faculty']",
    ".teacher-list li",
]

# Chinese character class for name extraction
CHINESE_NAME_PATTERN = re.compile("[\\u4e00-\\u9fff]{2,4}")

# Pattern for .edu.cn email addresses
EMAIL_PATTERN = re.compile(r"@[\\w.\\-]+\\.(?:edu\\.cn|cn)$")


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.replace("　", " ").split())


def _extract_text(tag) -> str:
    return _normalize_text(tag.get_text(strip=True)) if tag else ""


def _generate_record_id(university: str, college: str, name: str, source: str) -> str:
    key = f"{university}|{college}|{name}|{source}|fallback"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class ParserFallbackPlugin(ParserPlugin):
    """Fallback parser for faculty pages when main parser fails.

    Strategies:
      1. Extract from common CSS class names (.teacher, .faculty, etc.)
      2. Find email patterns, extract name from parent block

    Records include: email, raw_text (truncated to 500 chars)
    """

    name = "parser_fallback"
    version = "1.0.0"
    plugin_type = "parser"
    input_schema = "RawDataBatch.v1"
    output_schema = "RecordBatch.v1"

    def setup(self, context) -> None:
        self._params = context.config_snapshot.get("plugins", {}).get("parser_fallback", {}).get("params", {})
        self._profile = self._params.get("profile", EDUCATION_TUTOR_V1)

    def execute(self, data: Any, context) -> Any:
        """Parse RawDataBatch using fallback strategies."""
        self.setup(context)

        # Handle both RawDataBatch and single RawDataDTO
        if hasattr(data, "items"):
            raw_batch = data
            items = raw_batch.items
        else:
            items = [data]

        cfg = context.config_snapshot
        university = cfg.get("university", "")
        college = cfg.get("college", "")
        category = cfg.get("category", "")
        year = cfg.get("year", 0)
        source_id = cfg.get("source_id", "")

        all_records: list[NormalizedRecordDTO] = []
        errors: list[dict] = []
        media_refs: list[str] = []

        for item in items:
            html = self._get_html(item)
            if html:
                records = self._try_selectors(html, university, college, category, year, item)
                all_records.extend(records)
                media_refs.extend(self._extract_media_refs(html, item.url))
            else:
                errors.append({
                    "code": "PARSE_FAILED",
                    "message": "No HTML content for fallback parsing",
                    "stage": "process",
                    "source_id": item.source_id or source_id,
                    "retryable": False,
                })

        return RecordBatch(
            schema_version="1",
            records=all_records,
            stats={"fallback_count": len(all_records), "sources": "raw"},
            source_completion={source_id: True},
            errors=errors,
        )

    def _get_html(self, item) -> Optional[str]:
        """Extract HTML from RawDataDTO asset or legacy content."""
        if hasattr(item, "content") and item.content:
            return item.content
        if not hasattr(item, "assets"):
            return None
        for asset in item.assets:
            if hasattr(asset, "media_type") and asset.media_type == "text":
                if hasattr(asset, "data") and asset.data:
                    return asset.data.decode("utf-8", errors="replace")
                if hasattr(asset, "url"):
                    return None
        return None

    def _extract_media_refs(self, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        refs = []
        for img in soup.find_all("img"):
            src = img.get("src", "")
            if src:
                refs.append(src)
        return refs

    def _try_selectors(
        self, html: str, university: str, college: str, category: str,
        year: int, item,
    ) -> list[NormalizedRecordDTO]:
        """Try CSS selector strategy."""
        soup = BeautifulSoup(html, "lxml")
        records = []

        # Strategy 1: Try each selector until we find content
        for sel in FACULTY_SELECTORS:
            found = soup.select(sel)
            if found:
                logger.info("Fallback: found %d items with selector '%s'", len(found), sel)
                return self._parse_by_selector(found, university, college, category, year, item)

        # Strategy 2: Email-based extraction
        logger.info("Fallback: trying email-based extraction")
        return self._try_email_strategy(html, university, college, category, year, item)

    def _parse_by_selector(
        self, items, university: str, college: str, category: str,
        year: int, item,
    ) -> list[NormalizedRecordDTO]:
        """Parse items found via CSS selector."""
        records = []

        for person in items:
            name = ""
            title = ""
            research = ""

            # Try to get name from various elements
            for name_tag in person.find_all(["a", "span", "h3", "h4", "div"]):
                text = name_tag.get_text(strip=True)
                match = CHINESE_NAME_PATTERN.search(text)
                if match and len(match.group()) >= 2:
                    name = match.group()
                    break

            # Extract title if present
            title_tag = person.select_one(".title, .job, .position")
            if title_tag:
                title = _extract_text(title_tag)

            # Extract research areas
            for research_sel in [".research", ".field", ".intro", "p"]:
                text = _extract_text(person.select_one(research_sel))
                if text and len(text) > 2:
                    research = text
                    break

            if name:
                fields = {
                    "university": university,
                    "college": college,
                    "category": category,
                    "year": year,
                    "name": name,
                    "title": title,
                    "research": research,
                    "source_type": "官网师资页",
                    "email": "",
                    "raw_text": _extract_text(person)[:500],
                }
                record_id = _generate_record_id(university, college, name, item.url or "unknown")
                records.append(NormalizedRecordDTO(
                    record_id=record_id,
                    dataset=f"{university}:{college}",
                    schema_id=self._profile,
                    fields=fields,
                    provenance={"source_id": item.source_id, "url": item.url},
                ))

        return records

    def _try_email_strategy(
        self, html: str, university: str, college: str, category: str,
        year: int, item,
    ) -> list[NormalizedRecordDTO]:
        """Strategy 2: Find emails, extract name from parent block."""
        soup = BeautifulSoup(html, "lxml")
        records = []

        for email_tag in soup.find_all("a", href=re.compile(r"^mailto:")):
            email = email_tag.get_text(strip=True)
            if not email:
                continue

            # Check if it's an edu.cn email
            if not EMAIL_PATTERN.search(email):
                continue

            # Look for name in parent block
            parent = email_tag.find_parent()
            name = ""
            while parent and len(name) < 2:
                text = parent.get_text(strip=True)
                match = CHINESE_NAME_PATTERN.search(text)
                if match:
                    candidate = match.group()
                    # Avoid matching the email itself
                    if candidate not in email:
                        name = candidate
                        break
                parent = parent.find_parent() if parent else None

            if not name:
                name = "未知教师"

            fields = {
                "university": university,
                "college": college,
                "category": category,
                "year": year,
                "name": name,
                "title": "",
                "research": "",
                "source_type": "官网师资页",
                "email": email,
                "raw_text": parent.get_text(strip=True)[:500] if parent else "",
            }

            record_id = _generate_record_id(university, college, name, email)
            records.append(NormalizedRecordDTO(
                record_id=record_id,
                dataset=f"{university}:{college}",
                schema_id=self._profile,
                fields=fields,
                provenance={"source_id": item.source_id, "url": item.url},
            ))

        return records

    def close(self) -> None:
        pass