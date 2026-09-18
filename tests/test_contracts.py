"""Contract validation tests for V3.0 DTOs."""

import pytest
from datetime import datetime
from uuid import uuid4

from contracts import (
    MediaAsset,
    AssetRef,
    TaskConfigDTO,
    TaskRunState,
    OutputSpec,
    RawDataDTO,
    RawDataBatch,
    LegacyRecordBatch,
    NormalizedRecordDTO,
    RecordBatch,
    PresentationRequest,
    RenderedOutputDTO,
    ViewModel,
    UIComponentDTO,
    StoreRequest,
    StoreReceipt,
    StageResult,
    RunResult,
    ErrorDTO,
    validate_media_asset,
    validate_task_config,
    validate_task_run_state,
    validate_output_spec,
    validate_raw_dto,
    validate_raw_batch,
    validate_normalized_record,
    validate_record_batch,
    validate_presentation_request,
    validate_rendered_output,
    validate_view_model,
    validate_ui_component,
    validate_store_request,
    validate_store_receipt,
    validate_stage_result,
    validate_run_result,
    validate_error_dto,
    EDUCATION_TUTOR_V1,
    EDUCATION_MAJOR_V1,
    TUTOR_V1_SCHEMA,
    MAJOR_V1_SCHEMA,
    get_education_schema,
    validate_education_fields,
)


class TestMediaAsset:
    def test_valid_text_asset(self):
        asset = MediaAsset(
            media_type="text",
            mime_type="text/html",
            data=b"<html>test</html>",
        )
        assert validate_media_asset(asset)
        assert asset.size == 17

    def test_valid_image_asset_with_url(self):
        asset = MediaAsset(
            media_type="image",
            mime_type="image/png",
            url="https://example.com/image.png",
            metadata={"size": 1024},
        )
        assert validate_media_asset(asset)
        assert asset.size == 1024

    def test_invalid_both_data_and_url(self):
        with pytest.raises(ValueError, match="cannot have both data and url"):
            MediaAsset(
                media_type="text",
                mime_type="text/plain",
                data=b"test",
                url="https://example.com",
            )

    def test_invalid_neither_data_nor_url(self):
        with pytest.raises(ValueError, match="must have either data or url"):
            MediaAsset(media_type="text", mime_type="text/plain")

    def test_invalid_media_type(self):
        with pytest.raises(ValueError, match="media_type must be one of"):
            MediaAsset(media_type="invalid", mime_type="text/plain", data=b"test")


class TestAssetRef:
    def test_valid_asset_ref(self):
        ref = AssetRef(
            path="assets/image.png",
            media_type="image",
            mime_type="image/png",
            size=1024,
            sha256="a" * 64,
        )
        # Schema validation would require jsonschema
        assert ref.path == "assets/image.png"


class TestTaskConfigDTO:
    def test_valid_task_config(self):
        config = TaskConfigDTO(
            task_id=uuid4().hex,
            dataset="education",
            source_id="source_a",
            profile_id="tutor_profile",
            target_url="https://example.com/list",
            config_revision=1,
            config_snapshot={"selectors": {"item": "li"}},
        )
        assert validate_task_config(config)
        assert config.task_id is not None

    def test_auto_generates_task_id(self):
        config = TaskConfigDTO(
            task_id="",
            dataset="test",
            source_id="src",
            profile_id="prof",
            target_url="https://example.com",
            config_revision=1,
        )
        assert len(config.task_id) == 32


class TestTaskRunState:
    def test_valid_run_state(self):
        state = TaskRunState(
            run_id=uuid4().hex,
            task_id=uuid4().hex,
            status="running",
            retry_count=0,
        )
        assert validate_task_run_state(state)

    def test_invalid_status(self):
        with pytest.raises(ValueError, match="status must be one of"):
            TaskRunState(
                run_id=uuid4().hex,
                task_id=uuid4().hex,
                status="invalid_status",
            )

    def test_v22_status_mapping(self):
        state = TaskRunState(
            run_id=uuid4().hex,
            task_id=uuid4().hex,
            status="succeeded",
        )
        assert state.to_v22_status() == "done"

        state.status = "failed"
        assert state.to_v22_status() == "failed"


class TestOutputSpec:
    def test_valid_output_spec(self):
        spec = OutputSpec(
            output_id="out_1",
            format="html",
            template="minimal-light",
            presenter_instance="html_report",
            required=True,
        )
        assert validate_output_spec(spec)


class TestRawDataDTO:
    def test_valid_raw_dto_with_assets(self):
        asset = MediaAsset(media_type="text", mime_type="text/html", data=b"<html></html>")
        dto = RawDataDTO(
            source_id="source_a",
            url="https://example.com/page1",
            content_type="text/html",
            encoding="utf-8",
            fetched_at=datetime.now().isoformat(),
            assets=[asset],
        )
        assert validate_raw_dto(dto)

    def test_legacy_content_field(self):
        asset = MediaAsset(media_type="text", mime_type="text/html", data=b"<html>legacy</html>")
        dto = RawDataDTO(
            source_id="source_a",
            url="https://example.com/page1",
            content_type="text/html",
            encoding="utf-8",
            fetched_at=datetime.now().isoformat(),
            content="<html>legacy</html>",
            assets=[asset],
        )
        assert validate_raw_dto(dto)

    def test_legacy_raw_ref_field(self):
        asset = MediaAsset(media_type="text", mime_type="text/html", data=b"placeholder")
        dto = RawDataDTO(
            source_id="source_a",
            url="https://example.com/page1",
            content_type="text/html",
            encoding="utf-8",
            fetched_at=datetime.now().isoformat(),
            raw_ref="data/raw/example.html",
            assets=[asset],
        )
        assert validate_raw_dto(dto)

    def test_invalid_both_legacy_fields(self):
        asset = MediaAsset(media_type="text", mime_type="text/html", data=b"placeholder")
        with pytest.raises(ValueError, match="cannot have both content and raw_ref"):
            RawDataDTO(
                source_id="source_a",
                url="https://example.com",
                content_type="text/html",
                encoding="utf-8",
                fetched_at=datetime.now().isoformat(),
                content="html",
                raw_ref="path",
                assets=[asset],
            )


class TestRawDataBatch:
    def test_valid_batch(self):
        asset = MediaAsset(media_type="text", mime_type="text/html", data=b"test")
        item = RawDataDTO(
            source_id="source_a",
            url="https://example.com",
            content_type="text/html",
            encoding="utf-8",
            fetched_at=datetime.now().isoformat(),
            assets=[asset],
        )
        batch = RawDataBatch(
            task_id=uuid4().hex,
            items=[item],
            pagination_complete=True,
        )
        assert validate_raw_batch(batch)

    def test_empty_batch_valid(self):
        batch = RawDataBatch(
            task_id=uuid4().hex,
            items=[],
            pagination_complete=True,
        )
        assert validate_raw_batch(batch)


class TestLegacyRecordBatch:
    def test_to_raw_batch(self):
        legacy = LegacyRecordBatch(
            records=[{"name": "Test", "title": "Prof"}],
            source_id="source_a",
            task_id=uuid4().hex,
        )
        batch = legacy.to_raw_batch()
        assert len(batch.items) == 1
        assert batch.items[0].assets[0].media_type == "text"
        assert batch.items[0].assets[0].mime_type == "application/json"


class TestNormalizedRecordDTO:
    def test_valid_record(self):
        record = NormalizedRecordDTO(
            record_id=uuid4().hex,
            dataset="education",
            schema_id=EDUCATION_TUTOR_V1,
            fields={"name": "Test", "title": "Prof", "university": "Test Univ"},
            provenance={"source_id": "source_a", "url": "https://example.com"},
        )
        assert validate_normalized_record(record)

    def test_auto_generates_record_id(self):
        record = NormalizedRecordDTO(
            record_id="",
            dataset="test",
            schema_id="test.v1",
            fields={},
        )
        assert len(record.record_id) == 32


class TestRecordBatch:
    def test_valid_batch(self):
        record = NormalizedRecordDTO(
            record_id=uuid4().hex,
            dataset="education",
            schema_id=EDUCATION_TUTOR_V1,
            fields={"name": "Test"},
        )
        batch = RecordBatch(
            records=[record],
            group_key=("university", "college", "year"),
        )
        assert validate_record_batch(batch)


class TestPresentationRequest:
    def test_valid_request(self):
        req = PresentationRequest(
            request_id=uuid4().hex,
            dataset="education",
            schema_id=EDUCATION_TUTOR_V1,
            output_spec={"output_id": "out_1", "format": "html"},
        )
        assert validate_presentation_request(req)


class TestRenderedOutputDTO:
    def test_valid_output(self):
        output = RenderedOutputDTO(
            output_id=uuid4().hex,
            output_format="html",
            path="/tmp/output.html",
        )
        assert validate_rendered_output(output)


class TestViewModel:
    def test_valid_view_model(self):
        vm = ViewModel(
            dataset="education",
            schema_id=EDUCATION_TUTOR_V1,
            data_ref="/api/data/education?page=1",
            total_count=100,
        )
        assert validate_view_model(vm)


class TestUIComponentDTO:
    def test_valid_component(self):
        comp = UIComponentDTO(
            component_id="table_1",
            component_type="table",
            renderer_id="table_renderer_v1",
            payload={"columns": ["name", "title"]},
        )
        assert validate_ui_component(comp)


class TestStoreRequest:
    def test_valid_request(self):
        req = StoreRequest(
            dataset="education",
            run_id=uuid4().hex,
            target_id="jsonl_output",
            format_id="legacy_education_v1",
            data_refs=["records_1"],
        )
        assert validate_store_request(req)
        assert req.idempotency_key != ""


class TestStoreReceipt:
    def test_valid_receipt(self):
        receipt = StoreReceipt(
            target_id="jsonl_output",
            written=10,
            skipped=0,
            failed=0,
            records_written=10,
            output_ref="/data/output/education.jsonl",
        )
        assert validate_store_receipt(receipt)
        assert receipt.success
        assert receipt.total == 10


class TestStageResult:
    def test_valid_stage_result(self):
        result = StageResult(
            stage="acquire",
            status="succeeded",
            input_count=0,
            output_count=10,
        )
        assert validate_stage_result(result)


class TestRunResult:
    def test_valid_run_result(self):
        stage = StageResult(stage="acquire", status="succeeded")
        result = RunResult(
            run_id=uuid4().hex,
            task_id=uuid4().hex,
            status="succeeded",
            stages=[stage],
        )
        assert validate_run_result(result)


class TestErrorDTO:
    def test_valid_error(self):
        error = ErrorDTO(
            code="HTTP_TIMEOUT",
            message="Request timed out",
            stage="acquire",
            task_id=uuid4().hex,
            source_id="source_a",
        )
        assert validate_error_dto(error)
        assert error.retryable is True

    def test_non_retryable_error(self):
        error = ErrorDTO(
            code="PARSE_FAILED",
            message="Selector not found",
            stage="process",
        )
        assert error.retryable is False

    def test_unknown_code_defaults_false(self):
        error = ErrorDTO(
            code="UNKNOWN_CODE",
            message="Something went wrong",
            stage="acquire",
        )
        assert error.retryable is False


class TestEducationProfiles:
    def test_tutor_schema_exists(self):
        schema = get_education_schema(EDUCATION_TUTOR_V1)
        assert schema is not None
        assert "university" in schema["required"]

    def test_major_schema_exists(self):
        schema = get_education_schema(EDUCATION_MAJOR_V1)
        assert schema is not None
        assert "major_code" in schema["required"]

    def test_validate_tutor_fields(self):
        fields = {
            "university": "Test Univ",
            "college": "CS College",
            "category": "CS",
            "year": 2024,
            "name": "Prof. Test",
            "source_type": "官网师资页",
        }
        assert validate_education_fields(EDUCATION_TUTOR_V1, fields)

    def test_validate_missing_required(self):
        fields = {"name": "Test"}  # Missing required
        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_education_fields(EDUCATION_TUTOR_V1, fields)

    def test_unknown_schema_raises(self):
        with pytest.raises(ValueError, match="Unknown education schema_id"):
            get_education_schema("unknown.v1")


class TestSchemaConstants:
    def test_all_schemas_defined(self):
        # Verify all schema constants exist and are dicts
        from contracts.asset import MediaAsset
        from contracts.raw import RawDataDTO, RawDataBatch
        from contracts.task import TaskConfigDTO, TaskRunState, OutputSpec
        from contracts.record import NormalizedRecordDTO, RecordBatch
        from contracts.output import PresentationRequest, RenderedOutputDTO
        from contracts.ui import ViewModel, UIComponentDTO
        from contracts.result import StoreRequest, StoreReceipt, StageResult, RunResult, ErrorDTO

        assert isinstance(MediaAsset.v1, dict)
        assert isinstance(RawDataDTO.v1_schema(), dict)
        assert isinstance(RawDataBatch.v1_schema(), dict)
        assert isinstance(TaskConfigDTO.v1_schema(), dict)
        assert isinstance(TaskRunState.v1_schema(), dict)
        assert isinstance(OutputSpec.v1_schema(), dict)
        assert isinstance(NormalizedRecordDTO.v1_schema(), dict)
        assert isinstance(RecordBatch.v1_schema(), dict)
        assert isinstance(PresentationRequest.v1_schema(), dict)
        assert isinstance(RenderedOutputDTO.v1_schema(), dict)
        assert isinstance(ViewModel.v1_schema(), dict)
        assert isinstance(UIComponentDTO.v1_schema(), dict)
        assert isinstance(StoreRequest.v1_schema(), dict)
        assert isinstance(StoreReceipt.v1_schema(), dict)
        assert isinstance(StageResult.v1_schema(), dict)
        assert isinstance(RunResult.v1_schema(), dict)
        assert isinstance(ErrorDTO.v1_schema(), dict)


class TestPluginBase:
    """plugins/base.py 契约测试（W1 可写范围）。"""

    def test_metadata_auto_build(self):
        from plugins.base import BasePlugin, PluginContext

        class P(BasePlugin[str, str]):
            name = "p_test"
            plugin_type = "spider"
            input_schema = "TaskConfigDTO.v1"
            output_schema = "RawDataBatch.v1"

            def execute(self, data, context):
                return data

        p = P()
        m = p.metadata
        assert isinstance(m, type(P().metadata))
        assert m.name == "p_test"
        assert m.plugin_type == "spider"
        assert m.license == "MIT"
        assert m.entry_point.endswith(":P")
        assert p.metadata is m  # cached

    def test_context_defaults_and_cancel(self):
        from plugins.base import PluginContext

        ctx = PluginContext(task_id="t1", run_id="r1")
        assert ctx.allowed_paths == []
        assert ctx.config_snapshot == {}
        assert ctx.check_cancelled() is False

        class Token:
            def __init__(self, flag):
                self._flag = flag
            def is_set(self):
                return self._flag

        assert PluginContext(cancel_token=Token(True)).check_cancelled() is True
        assert PluginContext(cancel_token=Token(False)).check_cancelled() is False
        assert PluginContext(task_id="x").task_id == "x"

    def test_presenter_execute_wraps_path_string(self, tmp_path):
        from plugins.base import PresenterPlugin, PluginContext
        from contracts.output import RenderedOutputDTO

        out = tmp_path / "report.html"
        out.write_text("<html></html>", encoding="utf-8")

        class HtmlPresenter(PresenterPlugin):
            name = "html_presenter"
            output_schema = "RenderedOutputDTO.v1"

            def render(self, data, context):
                return str(out)

        dto = HtmlPresenter().execute(None, PluginContext())
        assert isinstance(dto, RenderedOutputDTO)
        assert dto.path == str(out)
        assert dto.output_format == "html"
        assert validate_rendered_output(dto)

    def test_presenter_execute_passthrough_dto(self, tmp_path):
        from plugins.base import PresenterPlugin, PluginContext
        from contracts.output import RenderedOutputDTO

        dto_in = RenderedOutputDTO(
            output_id="o1", output_format="csv", path=str(tmp_path / "a.csv"),
        )

        class CsvPresenter(PresenterPlugin):
            name = "csv_presenter"

            def render(self, data, context):
                return dto_in

        assert CsvPresenter().execute(None, PluginContext()) is dto_in

    def test_presenter_bad_render_return_raises(self):
        from plugins.base import PresenterPlugin, PluginContext

        class BadPresenter(PresenterPlugin):
            name = "bad_presenter"

            def render(self, data, context):
                return 42

        with pytest.raises(TypeError):
            BadPresenter().execute(None, PluginContext())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])