"""Wave 0 Contract Smoke Tests - Mock 4-stage pipeline.

Tests the full acquire -> process -> store -> present flow using
minimal mock plugins to verify DTO serialization/round-trip,
schema validation, and error handling.
"""

import pytest
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from contracts import (
    TaskConfigDTO,
    TaskRunState,
    RawDataDTO,
    RawDataBatch,
    NormalizedRecordDTO,
    RecordBatch,
    PresentationRequest,
    RenderedOutputDTO,
    StoreRequest,
    StoreReceipt,
    MediaAsset,
    ErrorDTO,
    validate_task_config,
    validate_raw_batch,
    validate_record_batch,
    validate_presentation_request,
    validate_rendered_output,
    validate_store_request,
    validate_store_receipt,
    EDUCATION_TUTOR_V1,
)
from plugins.base import BasePlugin, PluginContext, PresenterPlugin


# ============================================================================
# Mock Plugins (5-10 lines each)
# ============================================================================

class MockSpiderPlugin(BasePlugin[TaskConfigDTO, RawDataBatch]):
    """Mock spider: produces a RawDataBatch with one RawDataDTO containing a MediaAsset."""
    name = "mock_spider"
    version = "1.0.0"
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    def execute(self, data: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        asset = MediaAsset(
            media_type="text",
            mime_type="text/html",
            data=b"<html><body>Mock page</body></html>",
        )
        item = RawDataDTO(
            source_id=data.source_id,
            url=data.target_url,
            content_type="text/html",
            encoding="utf-8",
            fetched_at=datetime.now().isoformat(),
            trace={"mock": True},
            assets=[asset],
        )
        return RawDataBatch(
            schema_version="1",
            task_id=data.task_id,
            items=[item],
            pagination_complete=True,
        )


class MockParserPlugin(BasePlugin[RawDataBatch, RecordBatch]):
    """Mock parser: extracts a simple record from the raw HTML."""
    name = "mock_parser"
    version = "1.0.0"
    plugin_type = "processor"
    input_schema = "RawDataBatch.v1"
    output_schema = "RecordBatch.v1"

    def execute(self, data: RawDataBatch, context: PluginContext) -> RecordBatch:
        records = []
        for item in data.items:
            # Simulate parsing HTML to extract fields
            record = NormalizedRecordDTO(
                record_id=uuid4().hex,
                dataset="test_dataset",
                schema_id=EDUCATION_TUTOR_V1,
                fields={
                    "name": "Mock Teacher",
                    "title": "Professor",
                    "university": "Mock University",
                    "college": "Mock College",
                    "category": "CS",
                    "year": 2024,
                    "source_type": "官网师资页",
                },
                provenance={
                    "source_id": item.source_id,
                    "url": item.url,
                    "fetched_at": item.fetched_at,
                },
                media_refs=[f"raw_batch[{data.items.index(item)}]"],
            )
            records.append(record)

        return RecordBatch(
            schema_version="1",
            group_key=("university", "college", "year"),
            records=records,
            source_completion={data.items[0].source_id: True} if data.items else {},
        )


class MockStoragePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    """Mock storage: records the request and returns a success receipt."""
    name = "mock_storage"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    def execute(self, data: StoreRequest, context: PluginContext) -> StoreReceipt:
        return StoreReceipt(
            target_id=data.target_id,
            written=len(data.data_refs),
            skipped=0,
            failed=0,
            records_written=len(data.data_refs),
            output_ref=f"mock://{data.target_id}/{data.run_id}",
        )


class MockPresenterPlugin(PresenterPlugin):
    """Mock presenter: renders a simple text output."""
    name = "mock_presenter"
    version = "1.0.0"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def render(self, data: PresentationRequest, context: PluginContext) -> RenderedOutputDTO:
        # Simple text rendering
        lines = [f"Dataset: {data.dataset}", f"Records: {len(data.records)}"]
        for i, record in enumerate(data.records):
            lines.append(f"  {i+1}. {record.get('name', 'Unknown')} - {record.get('title', '')}")

        output_text = "\n".join(lines)
        output_path = f"/tmp/mock_output_{uuid4().hex[:8]}.txt"

        return RenderedOutputDTO(
            output_id=uuid4().hex,
            output_format="text",
            path=output_path,
            metadata={"lines": len(lines), "chars": len(output_text)},
        )


# ============================================================================
# Test Helpers
# ============================================================================

def create_task_config() -> TaskConfigDTO:
    return TaskConfigDTO(
        task_id=uuid4().hex,
        dataset="test_dataset",
        source_id="source_a",
        profile_id="tutor_profile",
        target_url="https://example.com/list",
        config_revision=1,
        config_snapshot={"selectors": {"item": "li"}},
    )


def create_plugin_context() -> PluginContext:
    return PluginContext(
        task_id=uuid4().hex,
        run_id=uuid4().hex,
    )


# ============================================================================
# Wave 0 Tests
# ============================================================================

def test_mock_spider_execute():
    """Test SpiderPlugin produces valid RawDataBatch."""
    config = create_task_config()
    context = create_plugin_context()

    plugin = MockSpiderPlugin()
    plugin.setup(context)

    result = plugin.execute(config, context)

    assert isinstance(result, RawDataBatch)
    assert validate_raw_batch(result)
    assert len(result.items) == 1
    assert result.items[0].source_id == "source_a"
    assert len(result.items[0].assets) == 1
    assert result.items[0].assets[0].media_type == "text"
    assert result.pagination_complete is True

    plugin.close()


def test_mock_parser_execute():
    """Test ParserPlugin produces valid RecordBatch."""
    config = create_task_config()
    context = create_plugin_context()

    # First run spider to get raw batch
    spider = MockSpiderPlugin()
    spider.setup(context)
    raw_batch = spider.execute(config, context)
    spider.close()

    # Then run parser
    parser = MockParserPlugin()
    parser.setup(context)

    record_batch = parser.execute(raw_batch, context)

    assert isinstance(record_batch, RecordBatch)
    assert validate_record_batch(record_batch)
    assert len(record_batch.records) == 1
    record = record_batch.records[0]
    assert record.schema_id == EDUCATION_TUTOR_V1
    assert record.fields["name"] == "Mock Teacher"
    assert record.fields["university"] == "Mock University"
    assert len(record.media_refs) == 1

    parser.close()


def test_mock_storage_execute():
    """Test StoragePlugin produces valid StoreReceipt."""
    context = create_plugin_context()

    # Create a record batch first
    record = NormalizedRecordDTO(
        record_id=uuid4().hex,
        dataset="test_dataset",
        schema_id=EDUCATION_TUTOR_V1,
        fields={"name": "Test"},
    )
    record_batch = RecordBatch(records=[record])

    # Create store request
    store_request = StoreRequest(
        dataset="test_dataset",
        run_id=context.run_id,
        target_id="mock_output",
        format_id="generic_v1",
        data_refs=[record.record_id],
    )
    assert validate_store_request(store_request)

    # Execute storage
    storage = MockStoragePlugin()
    storage.setup(context)

    receipt = storage.execute(store_request, context)

    assert isinstance(receipt, StoreReceipt)
    assert validate_store_receipt(receipt)
    assert receipt.written == 1
    assert receipt.success
    assert receipt.output_ref.startswith("mock://")

    storage.close()


def test_mock_presenter_execute():
    """Test PresenterPlugin produces valid RenderedOutputDTO."""
    context = create_plugin_context()

    # Create presentation request with mock records
    pres_request = PresentationRequest(
        request_id=uuid4().hex,
        dataset="test_dataset",
        schema_id=EDUCATION_TUTOR_V1,
        output_spec={"output_id": "out_1", "format": "text"},
        records=[{"name": "Mock Teacher", "title": "Professor"}],
    )
    assert validate_presentation_request(pres_request)

    # Execute presenter
    presenter = MockPresenterPlugin()
    presenter.setup(context)

    rendered = presenter.execute(pres_request, context)

    assert isinstance(rendered, RenderedOutputDTO)
    assert validate_rendered_output(rendered)
    assert rendered.output_format == "text"
    assert rendered.path.startswith("/tmp/mock_output_")

    presenter.close()


def test_full_four_stage_pipeline():
    """Integration test: acquire -> process -> store -> present."""
    context = create_plugin_context()
    config = create_task_config()

    # Stage 1: Acquire
    spider = MockSpiderPlugin()
    spider.setup(context)
    raw_batch = spider.execute(config, context)
    spider.close()

    assert validate_raw_batch(raw_batch)
    assert len(raw_batch.items) == 1

    # Stage 2: Process (parse)
    parser = MockParserPlugin()
    parser.setup(context)
    record_batch = parser.execute(raw_batch, context)
    parser.close()

    assert validate_record_batch(record_batch)
    assert len(record_batch.records) == 1

    # Stage 3: Store
    store_request = StoreRequest(
        dataset=config.dataset,
        run_id=context.run_id,
        target_id="mock_output",
        format_id="generic_v1",
        data_refs=[r.record_id for r in record_batch.records],
    )

    storage = MockStoragePlugin()
    storage.setup(context)
    receipt = storage.execute(store_request, context)
    storage.close()

    assert validate_store_receipt(receipt)
    assert receipt.written == 1

    # Stage 4: Present
    pres_request = PresentationRequest(
        request_id=uuid4().hex,
        dataset=config.dataset,
        schema_id=EDUCATION_TUTOR_V1,
        output_spec={"output_id": "out_1", "format": "text"},
        records=[r.fields for r in record_batch.records],
        store_receipts=[{
            "target_id": receipt.target_id,
            "written": receipt.written,
            "output_ref": receipt.output_ref,
        }],
        run_state={"run_id": context.run_id, "status": "succeeded"},
    )

    presenter = MockPresenterPlugin()
    presenter.setup(context)
    rendered = presenter.execute(pres_request, context)
    presenter.close()

    assert validate_rendered_output(rendered)
    assert rendered.output_format == "text"


def test_invalid_schema_id_rejected():
    """Test that invalid schema_id is rejected during validation."""
    record = NormalizedRecordDTO(
        record_id=uuid4().hex,
        dataset="test",
        schema_id="invalid.schema.id",
        fields={},
    )
    batch = RecordBatch(records=[record])

    # Should fail validation because schema_id not in registry
    with pytest.raises(Exception):
        validate_record_batch(batch)


def test_empty_batch_valid():
    """Test that empty batches are valid (legitimate empty results)."""
    config = create_task_config()
    context = create_plugin_context()

    # Spider returns empty batch
    class EmptySpiderPlugin(MockSpiderPlugin):
        def execute(self, data, context):
            return RawDataBatch(
                schema_version="1",
                task_id=data.task_id,
                items=[],
                pagination_complete=True,
            )

    spider = EmptySpiderPlugin()
    spider.setup(context)
    raw_batch = spider.execute(config, context)
    spider.close()

    assert validate_raw_batch(raw_batch)
    assert len(raw_batch.items) == 0

    # Parser handles empty batch
    parser = MockParserPlugin()
    parser.setup(context)
    record_batch = parser.execute(raw_batch, context)
    parser.close()

    assert validate_record_batch(record_batch)
    assert len(record_batch.records) == 0


def test_error_dto_in_batch():
    """Test that ErrorDTO can be included in batches."""
    error = ErrorDTO(
        code="HTTP_TIMEOUT",
        message="Request timed out",
        stage="acquire",
        task_id=uuid4().hex,
        source_id="source_a",
        retryable=True,
    )

    raw_batch = RawDataBatch(
        schema_version="1",
        task_id=uuid4().hex,
        items=[],
        pagination_complete=True,
        errors=[{
            "code": error.code,
            "message": error.message,
            "stage": error.stage,
            "task_id": error.task_id,
            "source_id": error.source_id,
            "retryable": error.retryable,
            "diagnostics": error.diagnostics,
        }],
    )

    assert validate_raw_batch(raw_batch)
    assert len(raw_batch.errors) == 1
    assert raw_batch.errors[0]["code"] == "HTTP_TIMEOUT"


def test_dto_serialization_roundtrip():
    """Test DTOs can be serialized to dict and back."""
    import json

    config = create_task_config()
    config_dict = {
        "task_id": config.task_id,
        "dataset": config.dataset,
        "source_id": config.source_id,
        "profile_id": config.profile_id,
        "target_url": config.target_url,
        "config_revision": config.config_revision,
        "config_snapshot": config.config_snapshot,
        "created_at": config.created_at,
    }

    # Serialize to JSON
    json_str = json.dumps(config_dict, ensure_ascii=False)
    parsed = json.loads(json_str)

    # Reconstruct
    restored = TaskConfigDTO(**parsed)
    assert restored.task_id == config.task_id
    assert restored.dataset == config.dataset
    assert validate_task_config(restored)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])