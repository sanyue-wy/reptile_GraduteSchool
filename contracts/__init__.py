"""V3.0 Contracts Package - All DTO types and validation."""

from contracts.asset import MediaAsset, AssetRef, validate_media_asset
from contracts.task import (
    TaskConfigDTO,
    TaskRunState,
    OutputSpec,
    validate_task_config,
    validate_task_run_state,
    validate_output_spec,
)
from contracts.raw import (
    RawDataDTO,
    RawDataBatch,
    LegacyRecordBatch,
    validate_raw_dto,
    validate_raw_batch,
)
from contracts.record import (
    NormalizedRecordDTO,
    RecordBatch,
    validate_normalized_record,
    validate_record_batch,
)
from contracts.output import (
    PresentationRequest,
    RenderedOutputDTO,
    validate_presentation_request,
    validate_rendered_output,
)
from contracts.ui import (
    ViewModel,
    UIComponentDTO,
    validate_view_model,
    validate_ui_component,
)
from contracts.result import (
    StoreRequest,
    StoreReceipt,
    StageResult,
    RunResult,
    ErrorDTO,
    validate_store_request,
    validate_store_receipt,
    validate_stage_result,
    validate_run_result,
    validate_error_dto,
)
from contracts.profiles.education import (
    EDUCATION_TUTOR_V1,
    EDUCATION_MAJOR_V1,
    EducationTutorFields,
    EducationMajorFields,
    TUTOR_V1_SCHEMA,
    MAJOR_V1_SCHEMA,
    SCHEMA_REGISTRY,
    get_education_schema,
    validate_education_fields,
)

__all__ = [
    # Asset
    "MediaAsset",
    "AssetRef",
    "validate_media_asset",
    # Task
    "TaskConfigDTO",
    "TaskRunState",
    "OutputSpec",
    "validate_task_config",
    "validate_task_run_state",
    "validate_output_spec",
    # Raw
    "RawDataDTO",
    "RawDataBatch",
    "LegacyRecordBatch",
    "validate_raw_dto",
    "validate_raw_batch",
    # Record
    "NormalizedRecordDTO",
    "RecordBatch",
    "validate_normalized_record",
    "validate_record_batch",
    # Output
    "PresentationRequest",
    "RenderedOutputDTO",
    "validate_presentation_request",
    "validate_rendered_output",
    # UI
    "ViewModel",
    "UIComponentDTO",
    "validate_view_model",
    "validate_ui_component",
    # Result
    "StoreRequest",
    "StoreReceipt",
    "StageResult",
    "RunResult",
    "ErrorDTO",
    "validate_store_request",
    "validate_store_receipt",
    "validate_stage_result",
    "validate_run_result",
    "validate_error_dto",
    # Profiles
    "EDUCATION_TUTOR_V1",
    "EDUCATION_MAJOR_V1",
    "EducationTutorFields",
    "EducationMajorFields",
    "TUTOR_V1_SCHEMA",
    "MAJOR_V1_SCHEMA",
    "SCHEMA_REGISTRY",
    "get_education_schema",
    "validate_education_fields",
]