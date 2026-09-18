# -*- coding: utf-8 -*-
"""
Storage Converter (V3.0)
========================
RecordBatch → StoreRequest + record dicts for storage plugins.

Handles:
- Extracting NormalizedRecordDTOs from RecordBatch or from data_refs file paths
- Building StoreRequest with proper idempotency key derivation
- Legacy education format mapping (V2.2 output schema)
"""

import json
import logging
from pathlib import Path
from typing import Any

from contracts.result import StoreRequest
from uuid import uuid4

logger = logging.getLogger(__name__)

# V2.2 legacy output column order
LEGACY_FIELDS = [
    "university", "college", "name", "title",
    "advisor_status", "research_areas", "source_url",
]


def records_from_data_refs(data_refs: list[str]) -> list[dict]:
    """Load records from data_refs file paths.

    Each ref is a path to a JSONL batch file (written by pipeline store stage).
    Returns list of record dicts ready for storage plugins.
    """
    records = []
    for ref in data_refs:
        path = Path(ref)
        if not path.exists():
            logger.warning("data_ref not found: %s", ref)
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    records.append(json.loads(line))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Failed to read data_ref %s: %s", ref, e)
    return records


def records_to_legacy_format(records: list[dict]) -> list[dict]:
    """Map NormalizedRecordDTO-style dicts to V2.2 legacy education output schema.

    Input fields come from NormalizedRecordDTO.fields dict.
    Output matches the legacy JSONL column set:
      university, college, name, title, advisor_status, research_areas, source_url
    """
    result = []
    for rec in records:
        fields = rec.get("fields", rec)
        provenance = rec.get("provenance", {})
        legacy = {
            "university": fields.get("university", provenance.get("university", "")),
            "college": fields.get("college", provenance.get("college", "")),
            "name": fields.get("name", fields.get("tutor_name", "")),
            "title": fields.get("title", fields.get("advisor_title", "")),
            "advisor_status": fields.get("advisor_status", fields.get("status", "")),
            "research_areas": fields.get("research_areas", fields.get("research_directions", [])),
            "source_url": provenance.get("url", fields.get("source_url", "")),
        }
        # Serialize list fields for JSONL line output
        if isinstance(legacy["research_areas"], list):
            legacy["research_areas"] = ", ".join(legacy["research_areas"])
        result.append(legacy)
    return result


def build_store_request(
    *,
    dataset: str,
    run_id: str,
    target_id: str,
    format_id: str,
    data_refs: list[str] | None = None,
    state_snapshot: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> StoreRequest:
    """Build a StoreRequest with deterministic idempotency key.

    If idempotency_key is not provided, derives one from run_id + target_id + data_refs
    so the same logical request always gets the same key.
    """
    refs = data_refs or []
    if idempotency_key is None:
        # Deterministic key from the logical request identity
        ref_hash = "|".join(sorted(refs))
        idempotency_key = f"{run_id}:{target_id}:{format_id}:{ref_hash}"

    return StoreRequest(
        dataset=dataset,
        run_id=run_id,
        target_id=target_id,
        format_id=format_id,
        data_refs=refs,
        idempotency_key=idempotency_key,
        state_snapshot=state_snapshot or {},
    )


def records_from_batch_dict(batch: dict) -> list[dict]:
    """Extract record dicts from a RecordBatch serialized as dict.

    Used when data_refs point to a JSON batch file rather than JSONL.
    """
    records = batch.get("records", [])
    if isinstance(records, list):
        return records
    return []
