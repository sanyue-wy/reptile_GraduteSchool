"""UI and view model types for V3.0 presentation layer."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import uuid4

from contracts.asset import MediaAsset
from contracts.record import RecordBatch
from contracts.result import StoreReceipt


@dataclass
class ViewModel:
    """Data model passed to UIPlugin for component rendering.

    Contains dataset description, paginated data references, statistics,
    storage receipts, and run status - everything needed for UI rendering
    without embedding full datasets in the page.
    """
    dataset: str
    schema_id: str
    field_descriptions: dict[str, Any] = field(default_factory=dict)  # Field name -> {type, label, format}
    data_ref: str = ""  # Reference to paginated data endpoint
    page: int = 1
    page_size: int = 50
    total_count: int = 0
    stats: dict[str, Any] = field(default_factory=dict)
    store_receipts: list[dict] = field(default_factory=list)  # StoreReceipt as dicts
    run_state: dict[str, Any] = field(default_factory=dict)  # TaskRunState as dict
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "dataset": {"type": "string", "minLength": 1},
                "schema_id": {"type": "string", "minLength": 1},
                "field_descriptions": {"type": "object"},
                "data_ref": {"type": "string"},
                "page": {"type": "integer", "minimum": 1},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 500},
                "total_count": {"type": "integer", "minimum": 0},
                "stats": {"type": "object"},
                "store_receipts": {"type": "array", "items": {"type": "object"}},
                "run_state": {"type": "object"},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["dataset", "schema_id"],
            "additionalProperties": False,
        }


@dataclass
class UIComponentDTO:
    """Declarative description of a UI component instance.

    Rendered by approved frontend renderers (table, chart, card, filter).
    No arbitrary HTML - only structured payload validated against
    component_type's parameter schema.
    """
    component_id: str
    component_type: str  # table, chart, card, filter
    renderer_id: str  # Registered renderer implementation ID
    payload: dict[str, Any] = field(default_factory=dict)  # Validated against component schema
    data_ref: str = ""  # Reference to data endpoint for this component
    events: list[dict[str, Any]] = field(default_factory=list)  # Declared event handlers
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    @classmethod
    def v1_schema(cls) -> dict:
        return {
            "type": "object",
            "properties": {
                "component_id": {"type": "string", "minLength": 1},
                "component_type": {"type": "string", "enum": ["table", "chart", "card", "filter"]},
                "renderer_id": {"type": "string", "minLength": 1},
                "payload": {"type": "object"},
                "data_ref": {"type": "string"},
                "events": {"type": "array", "items": {"type": "object"}},
                "created_at": {"type": "string", "format": "date-time"},
            },
            "required": ["component_id", "component_type", "renderer_id"],
            "additionalProperties": False,
        }


def validate_view_model(vm: ViewModel) -> bool:
    import jsonschema
    jsonschema.validate(vm.__dict__, ViewModel.v1_schema())
    return True


def validate_ui_component(dto: UIComponentDTO) -> bool:
    import jsonschema
    jsonschema.validate(dto.__dict__, UIComponentDTO.v1_schema())
    return True