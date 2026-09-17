"""Real MergeService contracts; imports stay inside tests so absent services fail visibly."""
from copy import deepcopy

import pytest


def record(name="张三", **kwargs):
    return {"name": name, "university": "测试大学", "college": "机械学院", **kwargs}


@pytest.mark.parametrize("left,right,expected", [
    ("张三", "张三", (True, "exact")),
    (" 张三 ", "张三", (True, "exact")),
    ("张 三", "张三", (True, "strip")),
    ("Alexander", "Alexandre", (True, "fuzzy")),
    ("张三", "李四", (False, "none")),
])
def test_pair_matching_reasons(left, right, expected):
    from services.merge_service import MergeService
    assert MergeService().match_records(record(left), record(right)) == expected


@pytest.mark.parametrize("difference", [{"university": "另一大学"}, {"college": "物理学院"}])
def test_never_match_across_identity(difference):
    from services.merge_service import MergeService
    service = MergeService()
    a, b = record(), record(**difference)
    assert service.match_records(a, b) == (False, "none")
    assert sorted(r["match_status"] for r in service.merge_sources([a], [b])) == [
        "partial_faculty", "partial_notice"]


def test_real_schema_and_no_input_mutation():
    from services.merge_service import MergeService
    a = [record(title="教授", research_areas=["机器人"]), record("李四")]
    b = [record(in_roster=True, directions=[{"name": "机械工程", "code": "080200"}]), record("王五")]
    before = deepcopy((a, b))
    merged = MergeService().merge_sources(a, b)
    assert (a, b) == before
    by_name = {r["name"]: r for r in merged}
    assert set(by_name) == {"张三", "李四", "王五"}
    assert all(r["schema_version"] == 1 for r in merged)
    assert by_name["张三"]["match_status"] == "merged"
    assert by_name["张三"]["title"] == "教授"
    assert by_name["张三"]["enrollment"]["in_roster"] is True
    assert by_name["李四"]["match_status"] == "partial_faculty"
    assert by_name["王五"]["match_status"] == "partial_notice"


def test_empty_and_same_name_one_to_one():
    from services.merge_service import MergeService
    service = MergeService()
    assert service.merge_sources([], []) == []
    merged = service.merge_sources([record(), record()], [record()])
    assert sorted(r["match_status"] for r in merged) == ["merged", "partial_faculty"]


def test_real_yzw_parser_to_merge_preserves_enrollment(tmp_path):
    """Direct lower-layer regression, executable even before services exists."""
    import json
    from parsers.yzw_major import parse
    from pipelines.merge import merge_sources
    from storage import JSONLStore
    raw = tmp_path / "major.json"
    raw.write_text(json.dumps({"data": [{"zdjs": "张三", "zydm": "080200", "zymc": "机械工程",
        "yjfxmc": "机器人", "xxfs": "1", "nzsrsstr": "3"}]}), encoding="utf-8")
    notice = parse(str(raw), {"university": "测试大学", "college": "机械学院",
                             "category": "mechanical", "year": 2026, "school_code": "99999"})
    assert notice[0]["enrollment"]["in_roster"] is True
    faculty_path, notice_path, output_path = (tmp_path / name for name in (
        "faculty.jsonl", "notice.jsonl", "merged.jsonl"))
    JSONLStore(faculty_path).write_all([record(title="教授")])
    JSONLStore(notice_path).write_all(notice)
    stats = merge_sources(str(faculty_path), str(notice_path), str(output_path))
    assert stats["merged"] == 1
    merged = JSONLStore(output_path).read_all()
    assert merged[0]["enrollment"] == notice[0]["enrollment"]

