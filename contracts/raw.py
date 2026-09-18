"""Raw data batch types for V3.0 acquisition stage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from contracts.asset import MediaAsset, AssetRef


@dataclass
class RawDataDTO:
    """A single raw data item fetched from a source.

    The assets list is the source of truth for all raw materials.
    The legacy content/raw_ref fields are preserved ONLY for backward
    compatibility with V2.2 engines and LegacyRecordBatch adapter.
    raw_converter is responsible for normalizing legacy shapes into assets.
    """
    source_id: str
    url: str
    content_type: str  # MIME type of primary content
    encoding: str
    fetched_at: str
    trace: dict[str, Any] = field(default_factory=dict)  # Request/response metadata, redirects, etc.
    assets: list[MediaAsset] = field(default_factory=list)  # TRUE SOURCE OF TRUTH

    # Legacy fields for V2.2 compatibility - DO NOT USE IN NEW CODE
    content: Optional[str] = None  # Legacy: raw HTML/JSON text (mutually exclusive with raw_ref)
    raw_ref: Optional[str] = None  # Legacy: path to raw file (mutually exclusive with content)

    def __post_init__(self):
        # Validate legacy mutual exclusion
        if self.content is not None and self.raw_ref is not None:
            raise ValueError("RawDataDTO cannot have both content and raw_ref (legacy)")

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "source_id": self.source_id,
            "url": self.url,
            "content_type": self.content_type,
            "encoding": self.encoding,
            "fetched_at": self.fetched_at,
            "trace": self.trace,
            "assets": [asset.to_dict() for asset in self.assets],
            "content": self.content,
            "raw_ref": self.raw_ref,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "minLength": 1},
                "url": {"type": "string", "format": "uri"},
                "content_type": {"type": "string"},
                "encoding": {"type": "string"},
                "fetched_at": {"type": "string", "format": "date-time"},
                "trace": {"type": "object"},
                "assets": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/MediaAsset"},
                },
                "content": {"type": ["string", "null"]},
                "raw_ref": {"type": ["string", "null"]},
            },
            "required": ["source_id", "url", "content_type", "encoding", "fetched_at", "assets"],
            "definitions": {
                "MediaAsset": MediaAsset.v1,
            },
            "additionalProperties": False,
        }


@dataclass
class RawDataBatch:
    """Batch of raw data items from a single acquisition run.

    Contains all items fetched for a task, along with pagination
    completion status and any errors encountered.
    """
    schema_version: str = "1"
    task_id: str = ""
    items: list[RawDataDTO] = field(default_factory=list)
    pagination_complete: bool = False
    next_page_token: Optional[str] = None
    errors: list[dict] = field(default_factory=list)  # ErrorDTO dicts
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.task_id:
            self.task_id = uuid4().hex

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "items": [item.to_dict() for item in self.items],
            "pagination_complete": self.pagination_complete,
            "next_page_token": self.next_page_token,
            "errors": self.errors,
            "fetched_at": self.fetched_at,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "schema_version": {"type": "string", "const": "1"},
                "task_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/RawDataDTO"},
                },
                "pagination_complete": {"type": "boolean"},
                "next_page_token": {"type": ["string", "null"]},
                "errors": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/ErrorDTO"},
                },
                "fetched_at": {"type": "string", "format": "date-time"},
            },
            "required": ["schema_version", "task_id", "items", "pagination_complete"],
            "definitions": {
                "RawDataDTO": RawDataDTO.v1_schema(),
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
                "MediaAsset": MediaAsset.v1,
            },
            "additionalProperties": False,
        }


# Legacy adapter for V2.2 list[dict] -> RawDataBatch
# This is used ONLY during migration. New spider plugins MUST produce
# proper RawDataBatch with populated assets.
@dataclass
class LegacyRecordBatch:
    """Adapter for V2.2 engine results (list[dict]) to RawDataBatch.

    V2.2 engines returned already-parsed records as list[dict]. This
    adapter wraps them for compatibility but they CANNOT be used as
    genuine RawDataBatch for the new pipeline - they lack assets.
    The real raw materials must come from the new spider plugins.
    """
    records: list[dict]
    source_id: str
    task_id: str

    def to_raw_batch(self) -> RawDataBatch:
        """Convert to RawDataBatch with minimal assets.

        WARNING: This creates placeholder assets. Real spider plugins
        must produce proper RawDataBatch with actual fetched assets.
        """
        items = []
        for record in self.records:
            # Create a minimal MediaAsset as placeholder
            # Real implementation would have actual fetched content
            from contracts.asset import MediaAsset
            asset = MediaAsset(
                media_type="text",
                mime_type="application/json",
                data=str(record).encode("utf-8"),
            )
            item = RawDataDTO(
                source_id=self.source_id,
                url=record.get("profile_url", ""),
                content_type="application/json",
                encoding="utf-8",
                fetched_at=datetime.now().isoformat(),
                trace={},
                assets=[asset],
            )
            items.append(item)

        return RawDataBatch(
            schema_version="1",
            task_id=self.task_id,
            items=items,
            pagination_complete=True,
        )


def validate_raw_dto(dto: RawDataDTO) -> bool:
    import jsonschema
    jsonschema.validate(dto.to_dict(), RawDataDTO.v1_schema())
    return True


def validate_raw_batch(batch: RawDataBatch) -> bool:
    import jsonschema
    jsonschema.validate(batch.to_dict(), RawDataBatch.v1_schema())
    return True