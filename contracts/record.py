"""Normalized record types for V3.0 processing stage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class NormalizedRecordDTO:
    """A single normalized record after parsing and field extraction.

    Fields must contain only JSON-serializable values that have passed
    schema validation for the given schema_id.
    """
    record_id: str
    dataset: str
    schema_id: str
    fields: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)  # source_id, url, fetched_at, etc.
    media_refs: list[str] = field(default_factory=list)  # AssetRef paths or RawDataDTO indices
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.record_id:
            self.record_id = uuid4().hex

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "record_id": self.record_id,
            "dataset": self.dataset,
            "schema_id": self.schema_id,
            "fields": self.fields,
            "provenance": self.provenance,
            "media_refs": self.media_refs,
            "created_at": self.created_at,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "record_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "dataset": {"type": "string", "minLength": 1},
                "schema_id": {"type": "string", "minLength": 1},
                "fields": {"type": "object"},
                "provenance": {"type": "object"},
                "media_refs": {"type": "array", "items": {"type": "string"}},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["record_id", "dataset", "schema_id"],
            "additionalProperties": False,
        }


@dataclass
class RecordBatch:
    """Batch of normalized records after processing.

    Contains records, aggregation statistics, and completion status
    for each source.
    """
    schema_version: str = "1"
    group_key: list[str] = field(default_factory=list)  # e.g., ["university", "college", "year"]
    records: list[NormalizedRecordDTO] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)
    source_completion: dict[str, bool] = field(default_factory=dict)  # source_id -> complete
    errors: list[dict] = field(default_factory=list)  # ErrorDTO dicts

    def __post_init__(self):
        # Ensure group_key is a list (convert from tuple if needed)
        if isinstance(self.group_key, tuple):
            self.group_key = list(self.group_key)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "schema_version": self.schema_version,
            "group_key": self.group_key,
            "records": [record.to_dict() for record in self.records],
            "stats": self.stats,
            "source_completion": self.source_completion,
            "errors": self.errors,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "schema_version": {"type": "string", "const": "1"},
                "group_key": {"type": "array", "items": {"type": "string"}},
                "records": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/NormalizedRecordDTO"},
                },
                "stats": {"type": "object"},
                "source_completion": {"type": "object", "additionalProperties": {"type": "boolean"}},
                "errors": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/ErrorDTO"},
                },
            },
            "required": ["schema_version", "records"],
            "definitions": {
                "NormalizedRecordDTO": NormalizedRecordDTO.v1_schema(),
                "ErrorDTO": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "stage": {"type": "string"},
                        "task_id": {"type": "string"},
                        "source_id": {"type": "string"},
                        "retryable": {"type": "boolean"},
                        "diagnostics": {"type": "object"},
                    },
                    "required": ["code", "message", "stage"],
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        }


def validate_normalized_record(dto: NormalizedRecordDTO) -> bool:
    import jsonschema
    jsonschema.validate(dto.to_dict(), NormalizedRecordDTO.v1_schema())
    return True


def validate_record_batch(batch: RecordBatch) -> bool:
    import jsonschema
    from contracts.profiles.education import SCHEMA_REGISTRY
    # Structural validation
    jsonschema.validate(batch.to_dict(), RecordBatch.v1_schema())
    # Semantic validation: check schema_id is registered
    for record in batch.records:
        if record.schema_id not in SCHEMA_REGISTRY:
            raise ValueError(f"Unknown schema_id in record: {record.schema_id}")
    return True