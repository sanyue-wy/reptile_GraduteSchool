"""Service export contracts preserve real pipeline formats and return values."""
from copy import deepcopy
import json

import openpyxl
import pytest

from pipelines.merge import merge_pair
from storage import JSONLStore


@pytest.fixture
def records():
    return [merge_pair({"name": "张三", "university": "测试大学", "college": "机械学院",
                        "title": "教授", "research_areas": ["机器人"]},
                       {"in_roster": True, "directions": [{"name": "机械工程"}]}, "merged")]


def test_real_exports_roundtrip_and_legacy_return_values(records, tmp_output_dir):
    from services.export_service import ExportService
    service = ExportService()
    before = deepcopy(records)
    assert service.export_merged(records, tmp_output_dir) == {"files_written": 1, "total_records": 1}
    assert JSONLStore(tmp_output_dir / "测试大学_机械学院.jsonl").read_all() == records
    path = tmp_output_dir / "summary.xlsx"
    assert service.export_summary(records, path) == 1
    wb = openpyxl.load_workbook(path, read_only=True)
    try:
        rows = list(wb.active.values)
        assert len(rows) == 2
        assert rows[1][:7] == ("测试大学", "机械学院", "张三", "教授", "是", "机械工程", "机器人")
    finally:
        wb.close()
    assert records == before


def test_failures_json_shape_and_empty_exports(tmp_output_dir):
    from services.export_service import ExportService
    from pipelines.export import add_failure
    service = ExportService()
    item = add_failure("1", "测试大学", "机械学院", "Source A", "timeout", "offline", "")
    path = tmp_output_dir / "failures.json"
    assert service.export_failures([item], path) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["total"] == 1 and data["items"] == [item]
    assert data["summary"]["timeout"] == 1
    assert service.export_merged([], tmp_output_dir) == {"files_written": 0, "total_records": 0}
    assert service.export_summary([], tmp_output_dir / "empty.xlsx") == 0


def test_processor_pipeline_weight_order_context_and_disabled(records, monkeypatch):
    from services.export_service import ExportService
    import services.export_service as module
    monkeypatch.setattr(module, "load_plugin_config", lambda: {"pipeline": {"processors": {
        "last": 20, "disabled": 1, "first": 10}}})
    monkeypatch.setattr(module, "is_enabled", lambda kind, name: name != "disabled")
    monkeypatch.setattr(module, "plugin_config", lambda kind, name: {"tag": name})
    calls = []
    def dispatch(name, current, ctx):
        calls.append((name, deepcopy(current), deepcopy(ctx)))
        return [{**r, "trail": r.get("trail", []) + [name]} for r in current]
    monkeypatch.setattr(module, "dispatch_processor", dispatch)
    context = {"year": 2026}
    result = ExportService().run_processor_pipeline(records, context)
    assert [c[0] for c in calls] == ["first", "last"]
    assert result[0]["trail"] == ["first", "last"]
    assert calls[0][2] == {"year": 2026, "plugin_config": {"tag": "first"}}
    assert context == {"year": 2026}
    assert "trail" not in records[0]


def test_real_default_exporter_pipeline(records, tmp_output_dir):
    from services.export_service import ExportService
    result = ExportService().run_export_pipeline(records, tmp_output_dir)
    assert result
    assert JSONLStore(tmp_output_dir / "测试大学_机械学院.jsonl").read_all() == records
    assert (tmp_output_dir / "summary.xlsx").is_file()
