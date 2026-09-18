# -*- coding: utf-8 -*-
"""
Dedup Plugin
============
Post stage plugin: RecordBatch -> RecordBatch.

Wraps the V2.2 deduplicate_records algorithm. Dedup key is configurable
via instance params (default: university + college + name + title).
"""

import logging
from typing import Any

from contracts.record import NormalizedRecordDTO, RecordBatch

logger = logging.getLogger(__name__)

DEFAULT_KEY_FIELDS = ["university", "college", "name", "title"]


class DedupPlugin:
    """Remove duplicate records within a RecordBatch.

    Dedup key is built from configurable fields (default: university, college, name, title).
    First occurrence wins; subsequent duplicates are dropped.
    """

    name = "dedup"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RecordBatch.v1"
    output_schema = "RecordBatch.v1"

    def __init__(self):
        self._key_fields: list[str] = DEFAULT_KEY_FIELDS

    def setup(self, context) -> None:
        params = context.config_snapshot.get("plugins", {}).get("dedup", {}).get("params", {})
        self._key_fields = params.get("key_fields", DEFAULT_KEY_FIELDS)

    def execute(self, record_batch: RecordBatch, context) -> RecordBatch:
        """Deduplicate records by composite key and return a new batch."""
        self.setup(context)

        seen: set[tuple] = set()
        unique_records: list[NormalizedRecordDTO] = []

        for rec in record_batch.records:
            key = tuple(rec.fields.get(f, "") for f in self._key_fields)
            if key in seen:
                continue
            seen.add(key)
            unique_records.append(rec)

        dropped = len(record_batch.records) - len(unique_records)
        if dropped:
            logger.info("dedup: dropped %d duplicates (%d -> %d)", dropped, len(record_batch.records), len(unique_records))

        return RecordBatch(
            schema_version=record_batch.schema_version,
            group_key=record_batch.group_key,
            records=unique_records,
            stats={**record_batch.stats, "dedup_dropped": dropped, "dedup_input": len(record_batch.records)},
            source_completion=dict(record_batch.source_completion),
            errors=record_batch.errors[:],
        )

    def close(self) -> None:
        pass
