"""Media asset and reference types for V3.0."""

import base64
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4


@dataclass
class MediaAsset:
    """A single media asset carried in a RawDataDTO.

    Attributes:
        media_type: One of "text", "image", "audio", "video", "document", "binary".
        mime_type: IANA MIME type, e.g. "text/html", "image/png", "application/pdf".
        data: Raw bytes for in-memory assets (<=10 MiB). Mutually exclusive with url.
        url: Source URL if asset was streamed to disk via raw_ref. Mutually exclusive with data.
        metadata: Optional extensible metadata (headers, content-disposition, etc.).
        size: Size in bytes (populated on write if not provided).
        sha256: SHA-256 hex digest for integrity verification.
        fetched_at: Timestamp when the asset was fetched.
    """
    media_type: str
    mime_type: str
    data: Optional[bytes] = None
    url: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    size: Optional[int] = None
    sha256: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        # Validate media_type
        valid_types = {"text", "image", "audio", "video", "document", "binary"}
        if self.media_type not in valid_types:
            raise ValueError(f"media_type must be one of {valid_types}, got {self.media_type}")

        # Mutually exclusive: data or url
        if self.data is not None and self.url is not None:
            raise ValueError("MediaAsset cannot have both data and url set")
        if self.data is None and self.url is None:
            raise ValueError("MediaAsset must have either data or url set")

        # Populate size if missing
        if self.size is None:
            if self.data is not None:
                self.size = len(self.data)
            elif self.url is not None and self.metadata:
                self.size = self.metadata.get("size")

        # Auto-compute sha256 if data is present and sha256 not provided
        if self.sha256 is None and self.data is not None:
            import hashlib
            self.sha256 = hashlib.sha256(self.data).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict (data as base64 string)."""
        result = {
            "media_type": self.media_type,
            "mime_type": self.mime_type,
            "metadata": self.metadata,
            "size": self.size,
            "sha256": self.sha256,
            "fetched_at": self.fetched_at,
        }
        if self.data is not None:
            result["data"] = base64.b64encode(self.data).decode("ascii")
        if self.url is not None:
            result["url"] = self.url
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaAsset":
        """Create MediaAsset from JSON dict (data as base64 string)."""
        import base64
        asset_data = data.copy()
        if "data" in asset_data and isinstance(asset_data["data"], str):
            asset_data["data"] = base64.b64decode(asset_data["data"])
        return cls(**asset_data)


@dataclass
class AssetRef:
    """Reference to a media asset stored in the managed output workspace.

    Used when an asset exceeds the in-memory size limit and is stored
    as a file. The path is relative to the run's output root.
    """
    path: str  # Relative path under data/runs/<run_id>/assets/
    media_type: str
    mime_type: str
    size: int
    sha256: str

    # JSON Schema for validation
    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "media_type": {"type": "string", "enum": ["text", "image", "audio", "video", "document", "binary"]},
                "mime_type": {"type": "string"},
                "size": {"type": "integer", "minimum": 0},
                "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
            "required": ["path", "media_type", "mime_type", "size", "sha256"],
            "additionalProperties": False,
        }


# JSON Schema constants for validation
MediaAsset.v1 = {
    "type": "object",
    "properties": {
        "media_type": {"type": "string", "enum": ["text", "image", "audio", "video", "document", "binary"]},
        "mime_type": {"type": "string"},
        "data": {"type": "string", "format": "byte", "description": "Base64 encoded bytes"},
        "url": {"type": "string", "format": "uri"},
        "metadata": {"type": "object"},
        "size": {"type": "integer", "minimum": 0},
        "sha256": {"type": ["string", "null"], "pattern": "^[a-f0-9]{64}$"},
        "fetched_at": {"type": "string", "format": "date-time"},
    },
    "required": ["media_type", "mime_type", "fetched_at"],
    "oneOf": [
        {"required": ["data"]},
        {"required": ["url"]},
    ],
    "additionalProperties": False,
}


def validate_media_asset(asset: MediaAsset) -> bool:
    """Validate a MediaAsset instance against its JSON Schema."""
    import jsonschema
    jsonschema.validate(asset.to_dict(), MediaAsset.v1)
    return True