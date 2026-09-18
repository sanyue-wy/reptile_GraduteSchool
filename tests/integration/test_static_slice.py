# -*- coding: utf-8 -*-
"""Wave 1a 静态切片集成测试（W2 引擎侧用例段）。

离线 fixture 经真实引擎 + 真实 DTO 边界跑通 acquire→process→store→present。
具体插件实现由 W4/W5/W6/W7 交付；本文件当前以最小真实行为桩（读离线
fixture 文件、写真实 JSONL）贯穿引擎编排，待各窗口交付后替换为真插件重跑。

退出条件对照：
- 四阶段及失败清理通过（见 TestStaticSlice）
- 取消令牌在安全检查点停止派发（见 test_cancel_stops_dispatch）
- JSONL 输出与旧格式逐行一致 → 待 W6 jsonl_store legacy_education_v1 就位后补
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from contracts.asset import MediaAsset
from contracts.raw import RawDataBatch, RawDataDTO
from contracts.record import NormalizedRecordDTO, RecordBatch
from contracts.result import StoreReceipt
from pipeline.engine import PipelineDefinition, PipelineEngine
from converters.request_converter import PipelinePlanInput
from pipeline.stages.acquire import AcquirePlan
from pipeline.stages.process import ProcessPlan
from pipeline.stages.store import StorePlan
from pipeline.stages.present import PresentPlan

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "raw_pages"


class FixtureSpider:
    """acquire 桩：从离线 fixture 读取列表页 HTML 作为原始材料（不发网络）。"""
    name = "fixture_spider"
    plugin_type = "spider"

    def setup(self, context):
        pass

    def execute(self, task_config, context):
        html = (FIXTURE_DIR / "w4_static_list_page.html").read_text(encoding="utf-8")
        asset = MediaAsset(media_type="text", mime_type="text/html",
                           data=html.encode("utf-8"))
        item = RawDataDTO(
            source_id=task_config.source_id, url=task_config.target_url,
            content_type="text/html", encoding="utf-8",
            fetched_at=datetime.now().isoformat(),
            trace={"fixture": True}, assets=[asset],
        )
        return RawDataBatch(schema_version="1", task_id=task_config.task_id,
                            items=[item], pagination_complete=True)

    def close(self):
        pass


class FixtureParser:
    """parse 桩：把列表页解析为教育记录（字段来自 fixture 内容）。"""
    name = "fixture_parser"
    plugin_type = "processor"

    def setup(self, context):
        assert context.http is None

    def execute(self, raw_batch, context):
        records = []
        for index, item in enumerate(raw_batch.items):
            text = item.assets[0].data.decode("utf-8") if item.assets and item.assets[0].data else ""
            names = ["张三", "李四", "王五"]
            name = names[index % len(names)] if name_in(text, index) else f"教师{index}"
            records.append(NormalizedRecordDTO(
                record_id=f"{index:x}".zfill(32),
                dataset="education", schema_id="education.tutor.v1",
                fields={
                    "university": "测试大学", "college": "机械工程学院",
                    "category": "mechanical", "year": 2026,
                    "name": name, "source_type": "官网师资页",
                    "profile_url": item.url,
                },
                provenance={"source_id": item.source_id, "url": item.url},
            ))
        return RecordBatch(schema_version="1", group_key=["university", "college", "year"],
                           records=records)

    def close(self):
        pass


def name_in(text: str, index: int) -> bool:
    return ["张三", "李四", "王五"][index % 3] in text


class JsonlStorageStub:
    """store 桩：写真实 JSONL 文件（legacy 单行 JSON），返回真回执。"""
    name = "jsonl_stub"
    plugin_type = "storage"

    def setup(self, context):
        self._workspace = Path(context.config_snapshot["workspace"])

    def execute(self, request, context):
        batch_file = self._workspace.parent / request.run_id / "batch.json"
        batch = json.loads(batch_file.read_text(encoding="utf-8"))
        out_path = self._workspace / "store" / f"{request.target_id}.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(r["fields"], ensure_ascii=False) for r in batch["records"]]
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return StoreReceipt(target_id=request.target_id, written=len(lines), skipped=0,
                            failed=0, records_written=len(lines), output_ref=str(out_path))

    def close(self):
        pass


class HtmlPresenterStub:
    """present 桩：写最小 HTML 成品到受管 outputs 目录。"""
    name = "html_stub"
    plugin_type = "presenter"

    def setup(self, context):
        self._outputs_dir = Path(context.config_snapshot["outputs_dir"])

    def execute(self, request, context):
        from contracts.output import RenderedOutputDTO
        from uuid import uuid4
        out_dir = self._outputs_dir / uuid4().hex
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = "".join(f"<tr><td>{r['fields'].get('name', '')}</td></tr>"
                       for r in request.records)
        (out_dir / "report.html").write_text(
            f"<html><body><table>{rows}</table></body></html>", encoding="utf-8")
        return RenderedOutputDTO(output_id=uuid4().hex, output_format="html",
                                 path=str(out_dir / "report.html"))

    def close(self):
        pass


def _definition():
    instances = {
        "static_fetch": {"plugin": "spider:fixture", "enabled": True, "params": {}},
        "faculty_parse": {"plugin": "processor:fixture", "enabled": True, "params": {}},
        "jsonl_output": {"plugin": "storage:jsonl", "enabled": True,
                         "params": {"format": "legacy_education_v1"}},
        "html_report": {"plugin": "presenter:html", "enabled": True, "params": {}},
    }
    return PipelineDefinition(
        pipeline_id="static_slice",
        sources=[AcquirePlan(source_id="source_a", instance="static_fetch",
                             parse_instances=["faculty_parse"], required=True)],
        process=ProcessPlan(post_instances=[], group_by=["university", "college", "year"]),
        store=[StorePlan(instance="jsonl_output", required=True, format_id="legacy_education_v1")],
        present=PresentPlan(outputs=[{"output_id": "slice_html", "format": "html",
                                      "template": None, "presenter_instance": "html_report",
                                      "params": {}, "required": False}],
                            required=False),
        instances=instances,
    )


@pytest.fixture
def slice_engine(tmp_path):
    engine = PipelineEngine(
        _definition(), data_root=tmp_path / "data", max_workers=2,
        plugins={
            "static_fetch": FixtureSpider(),
            "faculty_parse": FixtureParser(),
            "jsonl_output": JsonlStorageStub(),
            "html_report": HtmlPresenterStub(),
        },
        session_kwargs={"delay_range": (0.0, 0.0)},
    )
    plan = PipelinePlanInput(
        dataset="education", profile_id="education.tutor.v1",
        sources=[{"source_id": "source_a", "target_url": "https://offline.example/list.htm",
                  "config": {"list_url": "https://offline.example/list.htm"}}],
    )
    return engine, plan


class TestStaticSlice:
    def test_offline_four_stage_run(self, slice_engine):
        engine, plan = slice_engine
        result = engine.run(plan)
        assert result.status == "succeeded", result.errors
        stages = {s.stage: s for s in result.stages}
        assert stages["acquire"].status == "succeeded"
        assert stages["process"].status == "succeeded"
        assert stages["store"].status == "succeeded"
        assert stages["present"].status == "succeeded"
        # JSONL 落盘且每行是合法 JSON（legacy 单行格式）
        run_dir = next((engine.data_root / "runs").iterdir())
        jsonl_files = list((run_dir / "store").glob("*.jsonl"))
        assert jsonl_files, "JSONL 存储输出缺失"
        lines = jsonl_files[0].read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        first = json.loads(lines[0])
        assert "name" in first and "university" in first
        # 成品 HTML 在受管 outputs 下
        report = next(run_dir.glob("outputs/*/report.html"))
        assert "张三" in report.read_text(encoding="utf-8")

    def test_failure_cleanup_closes_plugins(self, tmp_path):
        class FailingSpider(FixtureSpider):
            def execute(self, task_config, context):
                raise ConnectionError("offline fixture unreachable")

        definition = _definition()
        spider = FailingSpider()
        engine = PipelineEngine(definition, data_root=tmp_path / "data",
                                plugins={"static_fetch": spider,
                                         "faculty_parse": FixtureParser(),
                                         "jsonl_output": JsonlStorageStub(),
                                         "html_report": HtmlPresenterStub()},
                                session_kwargs={"delay_range": (0.0, 0.0)})
        plan = PipelinePlanInput(dataset="education", profile_id="education.tutor.v1",
                                 sources=[{"source_id": "source_a",
                                           "target_url": "https://offline.example/x"}])
        result = engine.run(plan)
        assert result.status == "failed"
        assert any(e["code"] == "HTTP_CONNECTION_ERROR" for e in result.stages[0].errors)

    def test_cancel_stops_dispatch(self, tmp_path):
        from infra.context import PipelineContextManager
        from pipeline.stages.acquire import acquire_source
        from converters.request_converter import to_task_configs

        definition = _definition()
        plan = PipelinePlanInput(dataset="education", profile_id="education.tutor.v1",
                                 sources=[{"source_id": f"source_{i}",
                                           "target_url": f"https://o.example/{i}"}
                                          for i in range(3)])
        manager = PipelineContextManager("c" * 32, tmp_path / "data",
                                         session_kwargs={"delay_range": (0.0, 0.0)})
        try:
            tasks = to_task_configs(plan)
            statuses = []
            for i, (source_plan, task) in enumerate(zip(definition.sources, tasks)):
                batch, stage_result = acquire_source(source_plan, task, FixtureSpider(), manager)
                statuses.append(stage_result.status)
                if i == 0:
                    manager.request_cancel()
            assert statuses[0] == "succeeded"
            assert all(s == "skipped" for s in statuses[1:]), statuses
        finally:
            manager.shutdown()
