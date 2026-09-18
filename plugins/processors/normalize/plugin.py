# -*- coding: utf-8 -*-
"""
Normalize Plugin
================
Post stage plugin: RecordBatch -> RecordBatch.

Wraps the V2.2 normalize_records algorithm (text normalization, null handling).
Returns a new RecordBatch; never mutates the input.
"""

import logging
from copy import deepcopy
from typing import Any

from contracts.record import NormalizedRecordDTO, RecordBatch

logger = logging.getLogger(__name__)


def _normalize_text(value: Any) -> Any:
    """Normalize a single value: full-width space, collapse whitespace."""
    if not isinstance(value, str):
        return value
    return " ".join(value.replace("　", " ").replace("\xa0", " ").split())


def _normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Normalize all string fields in a record's fields dict."""
    result = {}
    for key, value in fields.items():
        if isinstance(value, str):
            result[key] = _normalize_text(value)
        elif isinstance(value, list):
            result[key] = [_normalize_text(item) if isinstance(item, str) else item for item in value]
        else:
            result[key] = value
    return result


class NormalizePlugin:
    """Normalize text fields in all records of a RecordBatch.

    Applies: full-width → half-width space, whitespace collapsing,
    null/empty string handling. Returns new RecordBatch (never in-place).
    """

    name = "normalize"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RecordBatch.v1"
    output_schema = "RecordBatch.v1"

    def setup(self, context) -> None:
        pass

    def execute(self, record_batch: RecordBatch, context) -> RecordBatch:
        """Normalize all records and return a new batch."""
        if not record_batch.records:
            return RecordBatch(
                schema_version=record_batch.schema_version,
                group_key=record_batch.group_key,
                records=[],
                stats={**record_batch.stats, "normalized_count": 0},
                source_completion=record_batch.source_completion,
                errors=record_batch.errors[:],
            )

        normalized_records: list[NormalizedRecordDTO] = []
        for rec in record_batch.records:
            normalized_fields = _normalize_fields(rec.fields)
            normalized_records.append(NormalizedRecordDTO(
                record_id=rec.record_id,
                dataset=rec.dataset,
                schema_id=rec.schema_id,
                fields=normalized_fields,
                provenance=deepcopy(rec.provenance),
                media_refs=rec.media_refs[:],
                created_at=rec.created_at,
            ))

        logger.info("normalize: normalized %d records", len(normalized_records))

        return RecordBatch(
            schema_version=record_batch.schema_version,
            group_key=record_batch.group_key,
            records=normalized_records,
            stats={**record_batch.stats, "normalized_count": len(normalized_records)},
            source_completion=dict(record_batch.source_completion),
            errors=record_batch.errors[:],
        )

    def close(self) -> None:
        pass
