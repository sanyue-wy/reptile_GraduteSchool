# -*- coding: utf-8 -*-
"""
YZW Major Parser Plugin
=======================
Parse stage plugin: RawDataBatch -> RecordBatch.

Migrated from parsers/yzw_major.py. Parses研招网 API JSON assets
into education.tutor.v1 records with enrollment sub-objects.
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

from contracts.profiles.education import EDUCATION_TUTOR_V1
from contracts.raw import RawDataBatch
from contracts.record import NormalizedRecordDTO, RecordBatch

logger = logging.getLogger(__name__)

# Placeholders that signal "no specific advisor"
_NAME_PLACEHOLDERS = frozenset({"不区分导师", "请登录各学院网站查看", "--", "无", ""})


def _split_names(raw: str) -> list[str]:
    """Split advisor names field into individual names.

    Replicates parsers.utils.split_names logic:
    - Split on whitespace, semicolons, commas, Chinese punctuation
    - Filter placeholders and single-character fragments
    """
    if not raw or raw.strip() in _NAME_PLACEHOLDERS:
        return []
    names = re.split(r"[\s;；,，、]+", raw.strip())
    return [n.strip() for n in names if n.strip() and len(n.strip()) >= 2]


def _split_exam_subjects(kskm: str) -> list[str]:
    """Parse exam subjects string.

    Format: "101 政治 201 英语一 301 数学一 801 机械原理"
    Returns: ["101 政治", "201 英语一", ...]
    """
    if not kskm:
        return []
    parts = kskm.split()
    subjects = []
    i = 0
    while i + 1 < len(parts):
        subjects.append(f"{parts[i]} {parts[i + 1]}")
        i += 2
    return subjects


def _generate_record_id(university: str, college: str, name: str, major_code: str) -> str:
    """Generate deterministic record_id from natural key."""
    key = f"{university}|{college}|{name}|yzw|{major_code}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _build_record(name: str, item: dict, meta: dict, profile: str) -> NormalizedRecordDTO:
    """Build a NormalizedRecordDTO from a single YZW data item."""
    university = meta["university"]
    college = meta["college"]
    category = meta["category"]
    year = meta["year"]
    source_id = meta.get("source_id", "")
    source_url = meta.get("source_url", "")
    fetched_at = meta.get("fetched_at", "")

    directions = [{
        "code": item.get("zydm", ""),
        "name": item.get("zymc", ""),
        "research_direction": item.get("yjfxmc", ""),
    }]

    exam_subjects = _split_exam_subjects(item.get("kskm", ""))

    planned_count = None
    raw_count = item.get("nzsrsstr")
    if raw_count:
        try:
            planned_count = int(raw_count)
        except (ValueError, TypeError):
            planned_count = None

    xxfs = item.get("xxfs", "")
    degree_types = ["学术型硕士"] if xxfs == "1" else ["专业型硕士"]

    enrollment = {
        "in_roster": True,
        "degree_types": degree_types,
        "directions": directions,
        "planned_count": planned_count,
        "exam_subjects": exam_subjects,
        "source_url": source_url,
        "notice_year": year,
    }

    major_code = item.get("zydm", "")

    fields = {
        "university": university,
        "college": college,
        "category": category,
        "year": year,
        "name": name,
        "title": "",
        "research": "",
        "profile_url": "",
        "source_type": "研招网",
        "email": "",
        "phone": "",
        "education_background": "",
        "honors": [],
        "projects": [],
        "papers": [],
        "enrollment": enrollment,
        "match_status": "partial_notice",
        "major_code": major_code,
    }

    record_id = _generate_record_id(university, college, name, major_code)

    return NormalizedRecordDTO(
        record_id=record_id,
        dataset=f"{university}:{college}",
        schema_id=profile,
        fields=fields,
        provenance={
            "source_id": source_id,
            "url": source_url,
            "fetched_at": fetched_at,
        },
        media_refs=[],
    )


class YzwMajorParserPlugin:
    """Parse YZW API JSON responses into NormalizedRecordDTO records.

    Input:  RawDataBatch.v1  (JSON assets from yzw_api spider)
    Output: RecordBatch.v1   (NormalizedRecordDTO with education.tutor.v1 fields)
    """

    name = "yzw_major_parser"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RawDataBatch.v1"
    output_schema = "RecordBatch.v1"

    def __init__(self):
        self._params: dict[str, Any] = {}
        self._profile: str = EDUCATION_TUTOR_V1

    def setup(self, context) -> None:
        self._params = context.config_snapshot.get("plugins", {}).get("yzw_major_parse", {}).get("params", {})
        self._profile = self._params.get("profile", EDUCATION_TUTOR_V1)

    def execute(self, raw_batch: RawDataBatch, context) -> RecordBatch:
        """Parse all JSON assets in the raw batch into records."""
        self.setup(context)

        cfg = context.config_snapshot
        university = cfg.get("university", "")
        college = cfg.get("college", "")
        category = cfg.get("category", "")
        year = cfg.get("year", 0)
        source_id = cfg.get("source_id", raw_batch.items[0].source_id if raw_batch.items else "")
        major_codes = self._params.get("major_codes", [])

        records: list[NormalizedRecordDTO] = []
        errors: list[dict] = []

        for idx, raw_item in enumerate(raw_batch.items):
            if context.check_cancelled():
                break

            json_content = self._get_json_content(raw_item)
            if json_content is None:
                errors.append(self._make_error(
                    "PARSE_FAILED",
                    f"No JSON content found in item {idx}",
                    context,
                    source_id=raw_item.source_id,
                ))
                continue

            meta = {
                "university": university,
                "college": college,
                "category": category,
                "year": year,
                "source_id": raw_item.source_id or source_id,
                "source_url": raw_item.url,
                "fetched_at": raw_item.fetched_at,
            }

            page_records = self._parse_json_batch(json_content, meta, major_codes)
            records.extend(page_records)

        logger.info(
            "yzw_major_parser: parsed %d records from %d raw items (%s/%s)",
            len(records), len(raw_batch.items), university, college,
        )

        return RecordBatch(
            schema_version="1",
            records=records,
            stats={"parsed_count": len(records), "source_items": len(raw_batch.items)},
            source_completion={source_id: raw_batch.pagination_complete},
            errors=errors,
        )

    def _get_json_content(self, raw_item) -> Optional[dict]:
        """Extract JSON dict from a RawDataDTO's assets or legacy content."""
        for asset in raw_item.assets:
            if asset.data:
                try:
                    text = asset.data.decode("utf-8", errors="replace")
                    return json.loads(text)
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.warning("Failed to decode asset JSON: %s", e)
                    return None
        # Legacy fallback
        if raw_item.content:
            try:
                return json.loads(raw_item.content)
            except json.JSONDecodeError:
                return None
        if raw_item.raw_ref:
            try:
                with open(raw_item.raw_ref, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to read raw_ref %s: %s", raw_item.raw_ref, e)
                return None
        return None

    def _parse_json_batch(self, data: dict, meta: dict, major_codes: list[str]) -> list[NormalizedRecordDTO]:
        """Parse one YZW API JSON response into records."""
        raw_items = data.get("data", [])
        records = []

        for item in raw_items:
            major_code = item.get("zydm", "")
            if major_codes and major_code not in major_codes:
                continue

            names = _split_names(item.get("zdjs", ""))
            if not names:
                # No specific advisor — generate one record with empty name
                records.append(_build_record("", item, meta, self._profile))
            else:
                for name in names:
                    records.append(_build_record(name, item, meta, self._profile))

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
