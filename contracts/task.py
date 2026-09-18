"""Task configuration and run state DTOs for V3.0."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import uuid4


@dataclass
class TaskConfigDTO:
    """Immutable task configuration passed to SpiderPlugin.execute().

    This is the frozen snapshot of all configuration needed for a single
    acquisition run. It is created by request_converter from user input
    and validated configuration profiles.
    """
    task_id: str
    dataset: str
    source_id: str
    profile_id: str
    target_url: str
    config_revision: int
    config_snapshot: dict[str, Any] = field(default_factory=dict)  # Read-only validated config
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.task_id:
            self.task_id = uuid4().hex

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "dataset": {"type": "string", "minLength": 1},
                "source_id": {"type": "string", "minLength": 1},
                "profile_id": {"type": "string", "minLength": 1},
                "target_url": {"type": "string", "format": "uri"},
                "config_revision": {"type": "integer", "minimum": 1},
                "config_snapshot": {"type": "object"},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["task_id", "dataset", "source_id", "profile_id", "target_url", "config_revision"],
            "additionalProperties": False,
        }


@dataclass
class TaskRunState:
    """Mutable execution state for a task run.

    Separated from TaskConfigDTO because it changes during execution
    while the config remains immutable.
    """
    run_id: str
    task_id: str
    status: str  # pending, running, succeeded, failed, partial, cancelled, skipped
    retry_count: int = 0
    last_attempt_at: Optional[str] = None
    checkpoint: dict[str, Any] = field(default_factory=dict)  # Plugin-specific resume data
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    VALID_STATUSES = {"pending", "running", "succeeded", "failed", "partial", "cancelled", "skipped"}

    def __post_init__(self):
        if not self.run_id:
            self.run_id = uuid4().hex
        if self.status not in self.VALID_STATUSES:
            raise ValueError(f"status must be one of {self.VALID_STATUSES}")

    # V2.2 compatibility mapping
    V22_STATUS_MAP = {
        "pending": "pending",
        "running": "running",
        "succeeded": "done",
        "failed": "failed",
        "partial": "partial",
        "cancelled": "cancelled",
        "skipped": "skipped",
    }

    def to_v22_status(self) -> str:
        """Map to V2.2 done/success enum for backward compatibility."""
        return self.V22_STATUS_MAP.get(self.status, self.status)

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "task_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"},
                "status": {"type": "string", "enum": list(TaskRunState.VALID_STATUSES)},
                "retry_count": {"type": "integer", "minimum": 0},
                "last_attempt_at": {"type": ["string", "null"], "format": "date-time"},
                "checkpoint": {"type": "object"},
                "started_at": {"type": "string", "format": "date-time"},
                "completed_at": {"type": ["string", "null"], "format": "date-time"},
            },
            "required": ["run_id", "task_id", "status"],
            "additionalProperties": False,
        }


@dataclass
class OutputSpec:
    """Specification for a single output product.

    Created from user configuration (pipeline.yaml present section)
    and passed to view_converter + presenter.execute().
    """
    output_id: str
    format: str  # html, text, markdown, jsonl, csv, pdf
    template: Optional[str] = None
    presenter_instance: Optional[str] = None  # Named presenter instance from plugins.yaml
    params: dict[str, Any] = field(default_factory=dict)
    required: bool = False

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "output_id": {"type": "string", "minLength": 1},
                "format": {"type": "string", "enum": ["html", "text", "markdown", "jsonl", "csv", "pdf"]},
                "template": {"type": ["string", "null"]},
                "presenter_instance": {"type": ["string", "null"]},
                "params": {"type": "object"},
                "required": {"type": "boolean"},
            },
            "required": ["output_id", "format"],
            "additionalProperties": False,
        }


def validate_task_config(dto: TaskConfigDTO) -> bool:
    import jsonschema
    jsonschema.validate(dto.__dict__, TaskConfigDTO.v1_schema())
    return True


def validate_task_run_state(state: TaskRunState) -> bool:
    import jsonschema
    jsonschema.validate(state.__dict__, TaskRunState.v1_schema())
    return True


def validate_output_spec(spec: OutputSpec) -> bool:
    import jsonschema
    jsonschema.validate(spec.__dict__, OutputSpec.v1_schema())
    return True