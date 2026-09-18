"""Output and presentation types for V3.0 present stage."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from contracts.asset import MediaAsset, AssetRef
from contracts.record import RecordBatch
from contracts.result import StoreReceipt


@dataclass
class PresentationRequest:
    """Request to render a RecordBatch into a specific output format.

    Created by view_converter from RecordBatch + StoreReceipt[] + OutputSpec + TaskRunState.
    Contains all data needed for a presenter to produce output without re-fetching.
    """
    request_id: str
    dataset: str
    schema_id: str
    output_spec: dict[str, Any]  # OutputSpec as dict
    records: list[dict] = field(default_factory=list)  # Simplified record view for templates
    media_assets: list[MediaAsset] = field(default_factory=list)  # Referenced assets
    store_receipts: list[dict] = field(default_factory=list)  # StoreReceipt as dicts
    run_state: dict[str, Any] = field(default_factory=dict)  # TaskRunState as dict
    stats: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.request_id:
            self.request_id = uuid4().hex

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "request_id": self.request_id,
            "dataset": self.dataset,
            "schema_id": self.schema_id,
            "output_spec": self.output_spec,
            "records": self.records,
            "media_assets": [asset.to_dict() for asset in self.media_assets],
            "store_receipts": self.store_receipts,
            "run_state": self.run_state,
            "stats": self.stats,
            "created_at": self.created_at,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "request_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "dataset": {"type": "string", "minLength": 1},
                "schema_id": {"type": "string", "minLength": 1},
                "output_spec": {"type": "object"},
                "records": {"type": "array", "items": {"type": "object"}},
                "media_assets": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/MediaAsset"},
                },
                "store_receipts": {"type": "array", "items": {"type": "object"}},
                "run_state": {"type": "object"},
                "stats": {"type": "object"},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["request_id", "dataset", "schema_id", "output_spec"],
            "definitions": {
                "MediaAsset": MediaAsset.v1,
            },
            "additionalProperties": False,
        }


@dataclass
class RenderedOutputDTO:
    """Result of a presenter.execute() call.

    Contains the output file path, format, and any media assets
    that were embedded or referenced in the output.
    """
    output_id: str
    output_format: str  # html, text, markdown, jsonl, csv, pdf
    path: str  # Absolute path to output file or directory
    media_assets: list[MediaAsset] = field(default_factory=list)  # Assets embedded in output
    metadata: dict[str, Any] = field(default_factory=dict)  # Page count, size, etc.
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "output_id": self.output_id,
            "output_format": self.output_format,
            "path": self.path,
            "media_assets": [asset.to_dict() for asset in self.media_assets],
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "output_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "output_format": {"type": "string", "enum": ["html", "text", "markdown", "jsonl", "csv", "pdf"]},
                "path": {"type": "string"},
                "media_assets": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/MediaAsset"},
                },
                "metadata": {"type": "object"},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["output_id", "output_format", "path"],
            "definitions": {
                "MediaAsset": MediaAsset.v1,
            },
            "additionalProperties": False,
        }


def validate_presentation_request(req: PresentationRequest) -> bool:
    import jsonschema
    jsonschema.validate(req.to_dict(), PresentationRequest.v1_schema())
    return True


def validate_rendered_output(dto: RenderedOutputDTO) -> bool:
    import jsonschema
    jsonschema.validate(dto.to_dict(), RenderedOutputDTO.v1_schema())
    return True