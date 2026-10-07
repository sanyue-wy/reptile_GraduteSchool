# -*- coding: utf-8 -*-
"""
Education Merge Plugin
======================
Post stage plugin: RecordBatch -> RecordBatch.

Multi-source merge using V2.2 three-phase matching (exact→strip→fuzzy).
Reuses pipelines.merge.match_records + merge_pair via services.merge_service.

Grouping: [university, college, year] — cross-university/college never matches.
Single-source runs pass records through as partial.
"""

import hashlib
import logging
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from contracts.record import NormalizedRecordDTO, RecordBatch
from pipelines.merge import match_records, merge_pair, normalize_name, strip_name
from plugins.base import RecordProcessorPlugin

logger = logging.getLogger(__name__)

DEFAULT_GROUP_BY = ["university", "college", "year"]
DEFAULT_FUZZY_THRESHOLD = 0.85

# Source classification from fields.source_type
FACULTY_SOURCE = "官网师资页"
NOTICE_SOURCE = "研招网"
NOTICE_SOURCE = "研招网"


def _generate_merged_record_id(university: str, college: str, name: str, year: int) -> str:
    """Generate stable record_id from natural key for merged records."""
    key = f"{university}|{college}|{name}|{year}|merged"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _record_to_dict(rec: NormalizedRecordDTO) -> dict:
    """Convert NormalizedRecordDTO to dict format expected by pipelines.merge functions."""
    d = dict(rec.fields)
    d["record_id"] = rec.record_id
    d["provenance"] = rec.provenance
    d["media_refs"] = rec.media_refs
    d["schema_id"] = rec.schema_id
    d["dataset"] = rec.dataset
    return d


def _merged_dict_to_record(
    merged: dict,
    dataset: str,
    schema_id: str,
    provenances: list[dict],
    media_refs: list[str],
) -> NormalizedRecordDTO:
    """Convert a merged dict (from merge_pair) back to NormalizedRecordDTO."""
    university = merged.get("university", "")
    college = merged.get("college", "")
    name = merged.get("name", "")
    year = merged.get("enrollment", {}).get("notice_year", 0) if merged.get("enrollment") else 0

    record_id = _generate_merged_record_id(university, college, name, year)

    # Build fields from merged dict — map V2.2 keys to education.tutor.v1
    fields = {
        "university": university,
        "college": college,
        "category": merged.get("category", ""),
        "year": year,
        "name": name,
        "title": merged.get("title", ""),
        "research": "; ".join(merged.get("research_areas", [])) if merged.get("research_areas") else "",
        "profile_url": merged.get("profile_url", ""),
        "source_type": merged.get("source_type", ""),
        "email": merged.get("email", ""),
        "phone": "",
        "education_background": "",
        "honors": [],
        "projects": [],
        "papers": [],
    }

    # Include enrollment sub-object if present
    if merged.get("enrollment"):
        fields["enrollment"] = merged["enrollment"]
    if merged.get("match_status"):
        fields["match_status"] = merged["match_status"]
    if merged.get("raw_ref"):
        fields["raw_ref"] = merged["raw_ref"]

    # Merge provenance from all contributing sources
    combined_provenance = {
        "sources": provenances,
        "merged_at": datetime.now().isoformat(),
    }

    return NormalizedRecordDTO(
        record_id=record_id,
        dataset=dataset,
        schema_id=schema_id,
        fields=fields,
        provenance=combined_provenance,
        media_refs=media_refs,
    )


class EducationMergePlugin(RecordProcessorPlugin):
    """Multi-source education record merge using three-phase matching.

    Phase 1: exact name match (after normalization)
    Phase 2: strip-all-spaces match ("张 三" → "张三")
    Phase 3: fuzzy match (difflib ≥ threshold, default 0.85)

    Grouping: [university, college, year]. Cross-university/college never merges.
    Single-source runs pass records through as partial.
    """

    name = "education_merge"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RecordBatch.v1"
    output_schema = "RecordBatch.v1"

    def __init__(self):
        self._group_by: list[str] = DEFAULT_GROUP_BY
        self._fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD

    def setup(self, context) -> None:
        params = context.config_snapshot.get("plugins", {}).get("education_merge", {}).get("params", {})
        self._group_by = params.get("group_by", DEFAULT_GROUP_BY)
        self._fuzzy_threshold = params.get("fuzzy_threshold", DEFAULT_FUZZY_THRESHOLD)

    def execute(self, record_batch: RecordBatch, context) -> RecordBatch:
        """Merge records across sources within each group."""
        self.setup(context)

        if not record_batch.records:
            return RecordBatch(
                schema_version=record_batch.schema_version,
                group_key=self._group_by,
                records=[],
                stats={"merge_total": 0, "merged": 0, "partial_faculty": 0, "partial_notice": 0},
                source_completion=dict(record_batch.source_completion),
                errors=record_batch.errors[:],
            )

        # Group records by group_by fields
        groups: dict[tuple, list[NormalizedRecordDTO]] = defaultdict(list)
        for rec in record_batch.records:
            gkey = tuple(rec.fields.get(f, "") for f in self._group_by)
            groups[gkey].append(rec)

        merged_records: list[NormalizedRecordDTO] = []
        stats = {"merged": 0, "partial_faculty": 0, "partial_notice": 0}
        errors = list(record_batch.errors)

        for gkey, group_records in groups.items():
            if context.check_cancelled():
                break

            # Split by source_type within each group
            faculty_recs = []
            notice_recs = []
            other_recs = []

            for rec in group_records:
                source_type = rec.fields.get("source_type", "")
                if source_type == FACULTY_SOURCE:
                    faculty_recs.append(rec)
                elif source_type == NOTICE_SOURCE:
                    notice_recs.append(rec)
                else:
                    other_recs.append(rec)

            # If only one source present, pass through as partial
            if not faculty_recs and notice_recs:
                # Only notice records
                for rec in notice_recs:
                    merged_records.append(self._as_partial(rec, "partial_notice"))
                    stats["partial_notice"] += 1
                continue
            if faculty_recs and not notice_recs:
                # Only faculty records
                for rec in faculty_recs:
                    merged_records.append(self._as_partial(rec, "partial_faculty"))
                    stats["partial_faculty"] += 1
                continue
            if not faculty_recs and not notice_recs:
                # Other source types — pass through
                merged_records.extend(other_recs)
                continue

            # Both sources present — run three-phase matching
            try:
                fac_dicts = [_record_to_dict(r) for r in faculty_recs]
                not_dicts = [_record_to_dict(r) for r in notice_recs]

                pairs, _, _ = match_records(fac_dicts, not_dicts, self._fuzzy_threshold)

                dataset = group_records[0].dataset
                schema_id = group_records[0].schema_id

                for fac_d, not_d, status in pairs:
                    merged_dict = merge_pair(fac_d, not_d, status)

                    # Collect provenance from contributing records
                    provenances = []
                    all_media = []
                    if fac_d:
                        provenances.append(fac_d.get("provenance", {}))
                        all_media.extend(fac_d.get("media_refs", []))
                    if not_d:
                        provenances.append(not_d.get("provenance", {}))
                        all_media.extend(not_d.get("media_refs", []))

                    merged_rec = _merged_dict_to_record(
                        merged_dict, dataset, schema_id, provenances, all_media,
                    )
                    merged_records.append(merged_rec)
                    stats[status] = stats.get(status, 0) + 1

            except Exception as e:
                logger.error("Merge failed for group %s: %s", gkey, e)
                errors.append({
                    "code": "PLUGIN_EXECUTE_FAILED",
                    "message": f"Merge failed for group {gkey}: {e}",
                    "stage": "process",
                    "retryable": False,
                    "diagnostics": {"group_key": list(gkey)},
                })
                # Pass through unmerged
                merged_records.extend(group_records)

        logger.info(
            "education_merge: %d records -> %d (merged=%d, partial_faculty=%d, partial_notice=%d)",
            len(record_batch.records), len(merged_records),
            stats["merged"], stats["partial_faculty"], stats["partial_notice"],
        )

        return RecordBatch(
            schema_version=record_batch.schema_version,
            group_key=self._group_by,
            records=merged_records,
            stats={**record_batch.stats, "merge": stats, "merge_total": len(merged_records)},
            source_completion=dict(record_batch.source_completion),
            errors=errors,
        )

    def _as_partial(self, rec: NormalizedRecordDTO, status: str) -> NormalizedRecordDTO:
        """Mark a record as partial (single-source, no merge partner)."""
        new_fields = dict(rec.fields)
        new_fields["match_status"] = status

        # Wrap provenance in standard merge format
        provenance = {
            "sources": [rec.provenance],
            "merged_at": datetime.now().isoformat(),
        }

        return NormalizedRecordDTO(
            record_id=rec.record_id,
            dataset=rec.dataset,
            schema_id=rec.schema_id,
            fields=new_fields,
            provenance=provenance,
            media_refs=rec.media_refs[:],
            created_at=rec.created_at,
        )

    def close(self) -> None:
        pass
