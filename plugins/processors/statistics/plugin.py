# -*- coding: utf-8 -*-
"""
Statistics Plugin
=================
Post stage plugin: RecordBatch -> RecordBatch.

Computes group-by counts and field distributions. Results are written
to RecordBatch.stats — the main data (records) is NOT modified.
"""

import logging
from collections import Counter, defaultdict
from typing import Any

from contracts.record import RecordBatch
from plugins.base import RecordProcessorPlugin

logger = logging.getLogger(__name__)

DEFAULT_GROUP_BY = ["university", "college", "year"]
DEFAULT_COUNT_FIELDS = ["source_type", "match_status"]


class StatisticsPlugin(RecordProcessorPlugin):
    """Compute group-by statistics on a RecordBatch.

    Results go into RecordBatch.stats only — records are passed through unchanged.
    """

    name = "statistics"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RecordBatch.v1"
    output_schema = "RecordBatch.v1"

    def __init__(self):
        self._group_by: list[str] = DEFAULT_GROUP_BY
        self._count_fields: list[str] = DEFAULT_COUNT_FIELDS

    def setup(self, context) -> None:
        params = context.config_snapshot.get("plugins", {}).get("statistics", {}).get("params", {})
        self._group_by = params.get("group_by", DEFAULT_GROUP_BY)
        self._count_fields = params.get("count_fields", DEFAULT_COUNT_FIELDS)

    def execute(self, record_batch: RecordBatch, context) -> RecordBatch:
        """Compute statistics and return the batch with updated stats."""
        self.setup(context)

        records = record_batch.records
        total = len(records)

        # Group counts
        group_counts: dict[str, int] = defaultdict(int)
        for rec in records:
            gkey = "|".join(str(rec.fields.get(f, "")) for f in self._group_by)
            group_counts[gkey] += 1

        # Field distribution counts
        field_distributions: dict[str, dict[str, int]] = {}
        for field_name in self._count_fields:
            counter: Counter = Counter()
            for rec in records:
                value = rec.fields.get(field_name, "")
                if isinstance(value, list):
                    for v in value:
                        counter[str(v)] += 1
                else:
                    counter[str(value)] += 1
            field_distributions[field_name] = dict(counter)

        stats = {
            **record_batch.stats,
            "statistics": {
                "total_records": total,
                "group_count": len(group_counts),
                "groups": dict(group_counts),
                "distributions": field_distributions,
            },
        }

        logger.info(
            "statistics: %d records, %d groups, fields=%s",
            total, len(group_counts), self._count_fields,
        )

        return RecordBatch(
            schema_version=record_batch.schema_version,
            group_key=record_batch.group_key,
            records=records,  # Records are NOT modified
            stats=stats,
            source_completion=dict(record_batch.source_completion),
            errors=record_batch.errors[:],
        )

    def close(self) -> None:
        pass
