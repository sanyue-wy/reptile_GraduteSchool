"""Result and error types for V3.0 storage and execution stages."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4


@dataclass
class StoreRequest:
    """Request to store a RecordBatch to a specific target.

    Created by storage_converter from RecordBatch + target configuration.
    Contains validated data references and idempotency key.
    """
    schema_version: str = "1"
    dataset: str = ""
    run_id: str = ""
    target_id: str = ""  # Storage plugin instance ID
    format_id: str = ""  # e.g., "legacy_education_v1", "generic_v1"
    data_refs: list[str] = field(default_factory=list)  # References to records/assets
    idempotency_key: str = ""
    state_snapshot: dict[str, Any] = field(default_factory=dict)  # TaskRunState for resume
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.idempotency_key:
            self.idempotency_key = f"{self.run_id}:{self.target_id}:{uuid4().hex[:8]}"

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "schema_version": {"type": "string", "const": "1"},
                "dataset": {"type": "string", "minLength": 1},
                "run_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "target_id": {"type": "string", "minLength": 1},
                "format_id": {"type": "string", "minLength": 1},
                "data_refs": {"type": "array", "items": {"type": "string"}},
                "idempotency_key": {"type": "string", "minLength": 1},
                "state_snapshot": {"type": "object"},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["schema_version", "dataset", "run_id", "target_id", "format_id", "idempotency_key"],
            "additionalProperties": False,
        }


@dataclass
class StoreReceipt:
    """Receipt from a StoragePlugin.execute() call.

    Each target returns its own receipt independently. Contains
    written/skipped/failed counts and output reference.
    """
    target_id: str
    written: int = 0
    skipped: int = 0
    failed: int = 0
    records_written: int = 0
    output_ref: str = ""  # Path or identifier for the written output
    error: dict[str, Any] | None = None  # ErrorDTO if failed
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def total(self) -> int:
        return self.written + self.skipped + self.failed

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.error is None

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "target_id": {"type": "string", "minLength": 1},
                "written": {"type": "integer", "minimum": 0},
                "skipped": {"type": "integer", "minimum": 0},
                "failed": {"type": "integer", "minimum": 0},
                "records_written": {"type": "integer", "minimum": 0},
                "output_ref": {"type": "string"},
                "error": {"type": ["object", "null"]},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["target_id", "written", "skipped", "failed", "records_written", "output_ref"],
            "additionalProperties": False,
        }


@dataclass
class StageResult:
    """Result of a single pipeline stage execution."""
    stage: str  # acquire, process, store, present
    status: str  # succeeded, failed, partial, skipped
    input_count: int = 0
    output_count: int = 0
    task_states: list[dict[str, Any]] = field(default_factory=list)  # TaskRunState as dicts
    receipts: list[dict[str, Any]] = field(default_factory=list)  # StoreReceipt as dicts
    components: list[dict[str, Any]] = field(default_factory=list)  # UIComponentDTO as dicts
    errors: list[dict[str, Any]] = field(default_factory=list)  # ErrorDTO as dicts
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "stage": self.stage,
            "status": self.status,
            "input_count": self.input_count,
            "output_count": self.output_count,
            "task_states": self.task_states,
            "receipts": self.receipts,
            "components": self.components,
            "errors": self.errors,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "stage": {"type": "string", "enum": ["acquire", "process", "store", "present"]},
                "status": {"type": "string", "enum": ["succeeded", "failed", "partial", "skipped"]},
                "input_count": {"type": "integer", "minimum": 0},
                "output_count": {"type": "integer", "minimum": 0},
                "task_states": {"type": "array", "items": {"type": "object"}},
                "receipts": {"type": "array", "items": {"type": "object"}},
                "components": {"type": "array", "items": {"type": "object"}},
                "errors": {"type": "array", "items": {"type": "object"}},
                "started_at": {"type": "string", "format": "date-time"},
                "completed_at": {"type": ["string", "null"], "format": "date-time"},
            },
            "required": ["stage", "status"],
            "additionalProperties": False,
        }


@dataclass
class RunResult:
    """Aggregate result of a full pipeline run."""
    run_id: str
    task_id: str
    status: str  # succeeded, failed, partial, cancelled
    stages: list[StageResult] = field(default_factory=list)
    total_records: int = 0
    total_outputs: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)  # ErrorDTO as dicts
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "status": self.status,
            "stages": [stage.to_dict() for stage in self.stages],
            "total_records": self.total_records,
            "total_outputs": self.total_outputs,
            "errors": self.errors,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "task_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "status": {"type": "string", "enum": ["succeeded", "failed", "partial", "cancelled"]},
                "stages": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/StageResult"},
                },
                "total_records": {"type": "integer", "minimum": 0},
                "total_outputs": {"type": "integer", "minimum": 0},
                "errors": {"type": "array", "items": {"type": "object"}},
                "started_at": {"type": "string", "format": "date-time"},
                "completed_at": {"type": ["string", "null"], "format": "date-time"},
            },
            "required": ["run_id", "task_id", "status", "stages"],
            "definitions": {
                "StageResult": StageResult.v1_schema(),
            },
            "additionalProperties": False,
        }


@dataclass
class ErrorDTO:
    """Standardized error information across all stages.

    Used in RawDataBatch.errors, RecordBatch.errors, StageResult.errors,
    StoreReceipt.error, and RunResult.errors.
    """
    code: str  # Error code from registry (e.g., "HTTP_TIMEOUT", "PARSE_FAILED")
    message: str  # Human-readable message (sanitized, no secrets)
    stage: str  # acquire, process, store, present
    task_id: str = ""
    source_id: str = ""
    retryable: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)  # Sanitized context for debugging

    # Standard error codes (extendable via registry)
    CODES = {
        # Network errors
        "HTTP_TIMEOUT": {"retryable": True},
        "HTTP_CONNECTION_ERROR": {"retryable": True},
        "HTTP_BLOCKED": {"retryable": False},
        "HTTP_DNS_ERROR": {"retryable": True},
        "HTTP_MAX_RETRIES": {"retryable": True},
        # Parse errors
        "PARSE_FAILED": {"retryable": False},
        "PARSE_SELECTOR_MISSING": {"retryable": False},
        "PARSE_ENCODING_ERROR": {"retryable": False},
        # Validation errors
        "VALIDATION_SCHEMA_MISMATCH": {"retryable": False},
        "VALIDATION_MISSING_REQUIRED": {"retryable": False},
        "VALIDATION_UNKNOWN_SCHEMA_ID": {"retryable": False},
        # Storage errors
        "STORAGE_WRITE_FAILED": {"retryable": True},
        "STORAGE_LOCK_TIMEOUT": {"retryable": True},
        "STORAGE_IDEMPOTENCY_CONFLICT": {"retryable": False},
        # Presenter errors
        "RENDER_TEMPLATE_MISSING": {"retryable": False},
        "RENDER_ASSET_MISSING": {"retryable": False},
        # Pipeline errors
        "PIPELINE_CANCELLED": {"retryable": False},
        "PIPELINE_CONFIG_INVALID": {"retryable": False},
        "PIPELINE_DEPENDENCY_MISSING": {"retryable": False},
        # Plugin errors
        "PLUGIN_SETUP_FAILED": {"retryable": False},
        "PLUGIN_EXECUTE_FAILED": {"retryable": True},
        "PLUGIN_DEPENDENCY_MISSING": {"retryable": False},
    }

    def __post_init__(self):
        if self.code in self.CODES:
            self.retryable = self.CODES[self.code].get("retryable", False)

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "stage": {"type": "string", "enum": ["acquire", "process", "store", "present"]},
                "task_id": {"type": "string"},
                "source_id": {"type": "string"},
                "retryable": {"type": "boolean"},
                "diagnostics": {"type": "object"},
            },
            "required": ["code", "message", "stage"],
            "additionalProperties": False,
        }


def validate_store_request(req: StoreRequest) -> bool:
    import jsonschema
    jsonschema.validate(req.__dict__, StoreRequest.v1_schema())
    return True


def validate_store_receipt(receipt: StoreReceipt) -> bool:
    import jsonschema
    jsonschema.validate(receipt.__dict__, StoreReceipt.v1_schema())
    return True


def validate_stage_result(result: StageResult) -> bool:
    import jsonschema
    jsonschema.validate(result.to_dict(), StageResult.v1_schema())
    return True


def validate_run_result(result: RunResult) -> bool:
    import jsonschema
    jsonschema.validate(result.to_dict(), RunResult.v1_schema())
    return True


def validate_error_dto(error: ErrorDTO) -> bool:
    import jsonschema
    jsonschema.validate(error.__dict__, ErrorDTO.v1_schema())
    return True