"""Frozen crawler contracts with real storage/parsers and fake HTTP only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from types import SimpleNamespace
import threading

import pytest
import requests

from pipelines.export import add_failure, export_failures, load_failures
from storage import JSONLStore


def args(**changes):
    values = dict(school=["__all__"], category=[], source=["source_a", "source_b"],
                  year=2026, force=False, resume=False, retry_failed=False)
    values.update(changes)
    return SimpleNamespace(**values)


def make_service(config, mock_progress, offline_transport, tmp_output_dir):
    from services.crawler_service import CrawlerService
    from utils.cache import CrawlCache
    session, _, _ = offline_transport
    return CrawlerService(config=config, cache=CrawlCache(tmp_output_dir / "cache"),
                          progress=mock_progress, session_factory=lambda: session,
                          output_dir=tmp_output_dir)


@pytest.fixture
def config(sample_config):
    first = deepcopy(sample_config)
    first["categories"][0]["college"] = "机械学院"
    second = deepcopy(first["categories"][0])
    second.update(college="自动化学院", category="automation")
    first["categories"].append(second)
    other = deepcopy(first)
    other["university"] = "另一大学"
    return [first, other]


@pytest.fixture
def service(config, mock_progress, offline_transport, tmp_output_dir):
    return make_service(config, mock_progress, offline_transport, tmp_output_dir)


def keys(tasks):
    return {t.key() for t in tasks}


def failure(identifier, school="测试大学", college="机械学院", source="Source A", status="active"):
    return add_failure(identifier, school, college, source, "timeout", "offline failure",
                       "http://test.edu.cn/faculty", status=status)


def test_dataclass_compatibility_and_state():
    from services.crawler_service import CrawlTask, CrawlResult
    task = CrawlTask("测试大学", "机械学院", "mechanical", "source_a", 2026)
    assert task.key() == "测试大学|机械学院|source_a"
    assert (task.force, task.config, task.execution_state, task.retry_count, task.last_attempt_at) == (
        False, {}, "pending", 0, None)
    result = CrawlResult(task.key(), "success", [], [])
    assert (result.error_message, result.error_type) == (None, "none")


def test_explicit_empty_config_does_not_load_defaults(mock_progress, offline_transport, tmp_output_dir):
    service = make_service([], mock_progress, offline_transport, tmp_output_dir)
    assert service.build_tasks(args()) == []


def test_exact_all_and_filter_scopes(service):
    tasks = service.build_tasks(args())
    expected = {f"{u}|{c}|{s}" for u in ("测试大学", "另一大学")
                for c in ("机械学院", "自动化学院") for s in ("source_a", "source_b")}
    assert len(tasks) == 8
    assert keys(tasks) == expected
    selected = service.build_tasks(args(school=["测试大学", "不存在"], category=["automation"],
                                        source=["source_b"], year=2025, force=True))
    assert keys(selected) == {"测试大学|自动化学院|source_b"}
    assert (selected[0].year, selected[0].force) == (2025, True)


def test_missing_source_config_is_excluded(config, mock_progress, offline_transport, tmp_output_dir):
    config[0]["categories"][0]["faculty"]["list_url"] = ""
    config[0]["categories"][1]["notice"]["enabled"] = False
    service = make_service(config, mock_progress, offline_transport, tmp_output_dir)
    assert keys(service.build_tasks(args(school=["测试大学"]))) == {
        "测试大学|机械学院|source_b", "测试大学|自动化学院|source_a"}


def test_resume_only_skips_done_selected_source(service, mock_progress):
    mock_progress.update_school_status("测试大学", "机械学院", source_a="done", source_b="failed")
    mock_progress.update_school_status("另一大学", "机械学院", source_b="done")
    tasks = service.build_tasks(args(resume=True))
    assert len(tasks) == 6
    assert keys(tasks) == keys(service.build_tasks(args())) - {
        "测试大学|机械学院|source_a", "另一大学|机械学院|source_b"}
    assert len(service.build_tasks(args(resume=True, force=True))) == 8


def test_retry_intersects_filters_deduplicates_and_ignores_inactive(service, tmp_output_dir, mock_progress):
    export_failures([
        failure("1"), failure("duplicate"), failure("B", source="Source B"),
        failure("other", school="另一大学"), failure("other-college", college="自动化学院"),
        failure("ignored", status="ignored"), failure("resolved", status="resolved"),
        failure("missing", college="不存在"),
    ], tmp_output_dir / "failures.json")
    mock_progress.update_school_status("测试大学", "机械学院", source_a="done")
    tasks = service.build_tasks(args(school=["测试大学"], category=["mechanical"],
                                    source=["source_a"], resume=True, retry_failed=True))
    assert len(tasks) == 1
    assert keys(tasks) == {"测试大学|机械学院|source_a"}
    # A retry selected from an active failure must actually execute despite done progress.
    assert tasks[0].force is True or tasks[0].execution_state == "failed"


def test_retry_empty_failure_file_has_no_tasks(service):
    assert service.build_tasks(args(retry_failed=True)) == []


def install_pages(offline_transport):
    _, routes, _ = offline_transport
    routes["http://test.edu.cn/faculty"] = '<ul><li><a href="/teacher/1" title="张三">张三</a></li></ul>'
    routes["http://test.edu.cn/teacher/1"] = '<div class="carrer"><div class="title"><span class="jsbt">张三</span>教授 博士生导师</div></div>'
    def directory(method, url, kwargs):
        assert method == "POST"
        # Only one discipline yields a record, avoiding artificial duplicates.
        if kwargs["data"]["yjxkdm"] != "0802":
            return {"total": 0, "data": []}
        return {"total": 1, "data": [{"dwmc": "测试大学", "dwdm": "99999", "zymc": "机械工程",
            "zydm": "080200", "yjfxmc": "机器人", "zdjs": "张三", "xxfs": "1", "nzsrsstr": "3"}]}
    routes["https://yz.chsi.com.cn/zsml/rs/dws.do"] = directory


def test_source_a_enrichment_real_lower_layers(service, offline_transport):
    install_pages(offline_transport)
    task = service.build_tasks(args(school=["测试大学"], category=["mechanical"], source=["source_a"]))[0]
    result = service.run_source_a(task)
    assert (result.task_id, result.status, result.failures) == (task.key(), "success", [])
    assert len(result.records) == 1
    rec = result.records[0]
    assert (rec["name"], rec["university"], rec["college"], rec["title"]) == ("张三", "测试大学", "机械学院", "教授")
    assert {call[1] for call in offline_transport[2]} == {
        "http://test.edu.cn/faculty", "http://test.edu.cn/teacher/1"}


def test_dual_source_real_storage_merge_export(service, offline_transport, tmp_output_dir, mock_progress):
    from services.export_service import ExportService
    import openpyxl
    install_pages(offline_transport)
    tasks = service.build_tasks(args(school=["测试大学"], category=["mechanical"]))
    results = [service.execute_task(t) for t in tasks]
    assert [r.status for r in results] == ["success", "success"]
    assert all(r.records for r in results)
    assert len(JSONLStore(tmp_output_dir / "测试大学_机械学院_faculty.jsonl").read_all()) == 1
    assert len(JSONLStore(tmp_output_dir / "测试大学_机械学院_notice.jsonl").read_all()) == 1
    merged = service.run_merge(tasks + tasks)
    assert len(merged) == 1  # one college, not one merge per source/task
    assert merged[0]["match_status"] == "merged"
    assert merged[0]["enrollment"]["in_roster"] is True
    assert merged[0]["enrollment"]["directions"]
    exporter = ExportService()
    exporter.export_merged(merged, tmp_output_dir)
    exporter.export_summary(merged, tmp_output_dir / "summary.xlsx")
    assert JSONLStore(tmp_output_dir / "测试大学_机械学院.jsonl").read_all() == merged
    book = openpyxl.load_workbook(tmp_output_dir / "summary.xlsx", read_only=True)
    try:
        assert list(book.active.values)[1][:4] == ("测试大学", "机械学院", "张三", "教授")
    finally:
        book.close()
    status = mock_progress.get_school_status("测试大学", "机械学院")
    assert (status["source_a"], status["source_b"], status["merged"]) == ("done", "done", "done")


def test_same_college_dual_source_four_threads(service, offline_transport, tmp_output_dir):
    install_pages(offline_transport)
    tasks = service.build_tasks(args(school=["测试大学"], category=["mechanical"], force=True))
    barrier = threading.Barrier(4)
    def execute(task):
        barrier.wait(timeout=10)
        return service.execute_task(task)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(execute, [deepcopy(t) for t in tasks * 2]))
    assert all(r.status == "success" for r in results)
    merged = service.run_merge(tasks)
    assert len(merged) == 1
    assert merged[0]["match_status"] == "merged"
    assert JSONLStore(tmp_output_dir / "测试大学_机械学院.jsonl").read_all() == merged


def test_concurrent_failures_preserve_existing_and_every_task(service, offline_transport, tmp_output_dir):
    _, routes, _ = offline_transport
    routes["http://test.edu.cn/faculty"] = requests.Timeout("offline timeout")
    export_failures([failure("existing", status="ignored")], tmp_output_dir / "failures.json")
    tasks = service.build_tasks(args(source=["source_a"], force=True))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(service.execute_task, tasks))
    assert all(r.status == "failed" and r.error_type == "timeout" for r in results)
    assert all(r.failures for r in results)
    persisted = load_failures(tmp_output_dir / "failures.json")
    assert len(persisted) == len(tasks) + 1
    assert len({r["id"] for r in persisted}) == len(persisted)
    assert {r["school"] + "|" + r["college"] for r in persisted if r["id"] != "existing"} == {
        t.university + "|" + t.college for t in tasks}


def test_skip_completed_does_not_request(service, mock_progress, offline_transport):
    mock_progress.update_school_status("测试大学", "机械学院", source_a="done")
    task = service.build_tasks(args(school=["测试大学"], category=["mechanical"], source=["source_a"]))[0]
    assert service.execute_task(task).status == "skipped"
    assert offline_transport[2] == []


def test_missing_list_url_execute_returns_failure(service):
    from services.crawler_service import CrawlTask
    task = CrawlTask("测试大学", "机械学院", "mechanical", "source_a", 2026)
    result = service.execute_task(task)
    assert result.status == "failed"
    assert result.error_message
    assert result.failures


def test_disabled_notice_is_empty_success(service, offline_transport):
    from services.crawler_service import CrawlTask
    task = CrawlTask("测试大学", "机械学院", "mechanical", "source_b", 2026)
    result = service.run_source_b(task)
    assert result.records == []
    assert result.status in ("success", "skipped")
    assert offline_transport[2] == []
