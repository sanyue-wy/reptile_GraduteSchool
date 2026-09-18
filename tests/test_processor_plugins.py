# -*- coding: utf-8 -*-
"""
Tests for Processor Plugins (W5)
=================================
Offline fixture-based tests for all 6 processor plugins.

Covers:
- faculty_parser: HTML → RecordBatch, selector-driven parsing
- yzw_major_parser: JSON → RecordBatch, YZW data extraction
- normalize: text normalization, whitespace handling
- dedup: composite key deduplication
- education_merge: three-phase matching (exact/strip/fuzzy)
- statistics: group-by counts and distributions
"""

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from contracts.asset import MediaAsset
from contracts.raw import RawDataDTO, RawDataBatch
from contracts.record import NormalizedRecordDTO, RecordBatch
from contracts.profiles.education import EDUCATION_TUTOR_V1

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "raw_pages"


class ProcessorContext:
    """Mock PluginContext for processor plugin tests."""

    def __init__(self, config_snapshot=None, task_id="test_task_001", run_id="test_run_001"):
        self.config_snapshot = config_snapshot or {}
        self.task_id = task_id
        self.run_id = run_id
        self.logger = Mock()
        self.http = None
        self.cache = None
        self.storage = None
        self.cancel_token = MockCancelToken(cancelled=False)
        self.allowed_paths = []
        self.registry_revision = 0

    def check_cancelled(self):
        return self.cancel_token.is_set()


class MockCancelToken:
    def __init__(self, cancelled=False):
        self._cancelled = cancelled

    def is_set(self):
        return self._cancelled


def _make_html_raw_batch(html: str, source_id="faculty_src", url="http://example.com/faculty") -> RawDataBatch:
    """Create a RawDataBatch with one HTML asset."""
    asset = MediaAsset(media_type="text", mime_type="text/html", data=html.encode("utf-8"))
    item = RawDataDTO(
        source_id=source_id,
        url=url,
        content_type="text/html",
        encoding="utf-8",
        fetched_at="2026-01-01T00:00:00",
        assets=[asset],
    )
    return RawDataBatch(schema_version="1", task_id="a" * 32, items=[item], pagination_complete=True)


def _make_json_raw_batch(json_data: dict, source_id="yzw_src", url="http://yzw.example.com/api") -> RawDataBatch:
    """Create a RawDataBatch with one JSON asset."""
    asset = MediaAsset(media_type="text", mime_type="application/json", data=json.dumps(json_data).encode("utf-8"))
    item = RawDataDTO(
        source_id=source_id,
        url=url,
        content_type="application/json",
        encoding="utf-8",
        fetched_at="2026-01-01T00:00:00",
        assets=[asset],
    )
    return RawDataBatch(schema_version="1", task_id="b" * 32, items=[item], pagination_complete=True)


def _make_context(plugin_name="test", extra_config=None) -> ProcessorContext:
    """Create a mock context with plugin config."""
    cfg = {
        "university": "测试大学",
        "college": "机械学院",
        "category": "mechanical",
        "year": 2026,
        "source_id": "test_source",
        "base_url": "http://example.com",
        "plugins": {
            plugin_name: {"params": {}},
        },
    }
    if extra_config:
        cfg.update(extra_config)
    return ProcessorContext(config_snapshot=cfg)


# ================================================================
# Faculty Parser Tests
# ================================================================

class TestFacultyParser:
    """Tests for faculty_parser plugin."""

    def _get_plugin(self):
        from plugins.processors.faculty_parser.plugin import FacultyParserPlugin
        return FacultyParserPlugin()

    def test_parse_fixture_page(self):
        """Parse w4_static_list_page.html fixture."""
        html_path = FIXTURES_DIR / "w4_static_list_page.html"
        html = html_path.read_text(encoding="utf-8")

        plugin = self._get_plugin()
        batch = _make_html_raw_batch(html)
        ctx = _make_context("faculty_parse")

        result = plugin.execute(batch, ctx)

        assert isinstance(result, RecordBatch)
        assert len(result.records) == 3

        # Verify first record
        rec = result.records[0]
        assert rec.fields["name"] == "张三"
        assert rec.fields["university"] == "测试大学"
        assert rec.fields["college"] == "机械学院"
        assert rec.fields["source_type"] == "官网师资页"
        assert rec.schema_id == EDUCATION_TUTOR_V1
        assert rec.record_id  # non-empty
        assert len(rec.record_id) == 32

    def test_parse_extracts_research_areas(self):
        """Research areas are correctly parsed from HTML."""
        html_path = FIXTURES_DIR / "w4_static_list_page.html"
        html = html_path.read_text(encoding="utf-8")

        plugin = self._get_plugin()
        batch = _make_html_raw_batch(html)
        ctx = _make_context("faculty_parse")

        result = plugin.execute(batch, ctx)

        names = {r.fields["name"]: r.fields["research"] for r in result.records}
        assert "人工智能" in names["张三"]
        assert "机器学习" in names["张三"]
        assert "计算机视觉" in names["李四"]

    def test_parse_extracts_profile_url(self):
        """Profile URLs are built from href attributes."""
        html_path = FIXTURES_DIR / "w4_static_list_page.html"
        html = html_path.read_text(encoding="utf-8")

        plugin = self._get_plugin()
        batch = _make_html_raw_batch(html)
        ctx = _make_context("faculty_parse")

        result = plugin.execute(batch, ctx)

        urls = {r.fields["name"]: r.fields["profile_url"] for r in result.records}
        assert "http://example.com/faculty/zhang.html" == urls["张三"]
        assert "http://example.com/faculty/li.html" == urls["李四"]

    def test_empty_batch(self):
        """Empty batch produces empty RecordBatch."""
        plugin = self._get_plugin()
        batch = RawDataBatch(schema_version="1", task_id="c" * 32, items=[], pagination_complete=True)
        ctx = _make_context("faculty_parse")

        result = plugin.execute(batch, ctx)

        assert isinstance(result, RecordBatch)
        assert len(result.records) == 0

    def test_missing_html_asset_produces_error(self):
        """RawDataDTO without HTML content produces ErrorDTO."""
        plugin = self._get_plugin()
        item = RawDataDTO(
            source_id="test", url="http://example.com",
            content_type="image/png", encoding="utf-8",
            fetched_at="2026-01-01T00:00:00",
            assets=[MediaAsset(media_type="image", mime_type="image/png", data=b"\x89PNG")],
        )
        batch = RawDataBatch(schema_version="1", task_id="d" * 32, items=[item], pagination_complete=True)
        ctx = _make_context("faculty_parse")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 0
        assert len(result.errors) == 1
        assert result.errors[0]["code"] == "PARSE_FAILED"

    def test_cancel_token(self):
        """Cancellation stops processing mid-batch."""
        html_path = FIXTURES_DIR / "w4_static_list_page.html"
        html = html_path.read_text(encoding="utf-8")

        plugin = self._get_plugin()
        batch = _make_html_raw_batch(html)
        ctx = _make_context("faculty_parse")
        ctx.cancel_token = MockCancelToken(cancelled=True)

        result = plugin.execute(batch, ctx)

        # Cancelled before processing any item
        assert len(result.records) == 0


# ================================================================
# YZW Major Parser Tests
# ================================================================

class TestYzwMajorParser:
    """Tests for yzw_major_parser plugin."""

    def _get_plugin(self):
        from plugins.processors.yzw_major_parser.plugin import YzwMajorParserPlugin
        return YzwMajorParserPlugin()

    def test_parse_fixture_json(self):
        """Parse w4_yzw_api_response.json fixture."""
        json_path = FIXTURES_DIR / "w4_yzw_api_response.json"
        json_data = json.loads(json_path.read_text(encoding="utf-8"))

        plugin = self._get_plugin()
        batch = _make_json_raw_batch(json_data)
        ctx = _make_context("yzw_major_parse")

        result = plugin.execute(batch, ctx)

        assert isinstance(result, RecordBatch)
        assert len(result.records) == 2

        # Check fields
        rec0 = result.records[0]
        assert rec0.fields["name"] == "张三"
        assert rec0.fields["university"] == "测试大学"
        assert rec0.fields["source_type"] == "研招网"
        assert rec0.fields["match_status"] == "partial_notice"
        assert rec0.fields["enrollment"]["in_roster"] is True

    def test_enrollment_sub_object(self):
        """Enrollment contains directions and exam subjects."""
        json_path = FIXTURES_DIR / "w4_yzw_api_response.json"
        json_data = json.loads(json_path.read_text(encoding="utf-8"))

        plugin = self._get_plugin()
        batch = _make_json_raw_batch(json_data)
        ctx = _make_context("yzw_major_parse")

        result = plugin.execute(batch, ctx)

        enr = result.records[0].fields["enrollment"]
        assert enr["directions"][0]["code"] == "080200"
        assert enr["notice_year"] == 2026
        assert enr["in_roster"] is True

    def test_major_code_filter(self):
        """major_codes param filters items."""
        json_data = {
            "total": 2,
            "data": [
                {"zdjs": "张三", "zydm": "080200", "yjfxmc": "机械工程", "nzsrsstr": "10"},
                {"zdjs": "李四", "zydm": "080201", "yjfxmc": "机械制造", "nzsrsstr": "8"},
            ],
        }

        plugin = self._get_plugin()
        batch = _make_json_raw_batch(json_data)
        ctx = _make_context("yzw_major_parse")
        ctx.config_snapshot["plugins"]["yzw_major_parse"]["params"]["major_codes"] = ["080200"]

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 1
        assert result.records[0].fields["name"] == "张三"

    def test_empty_json_data(self):
        """Empty data array produces empty batch."""
        plugin = self._get_plugin()
        batch = _make_json_raw_batch({"total": 0, "data": []})
        ctx = _make_context("yzw_major_parse")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 0

    def test_multi_name_field(self):
        """zdjs with multiple names produces multiple records."""
        json_data = {
            "data": [
                {"zdjs": "张三;李四", "zydm": "080200", "yjfxmc": "机械工程", "nzsrsstr": "10"},
            ],
        }

        plugin = self._get_plugin()
        batch = _make_json_raw_batch(json_data)
        ctx = _make_context("yzw_major_parse")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 2
        names = {r.fields["name"] for r in result.records}
        assert names == {"张三", "李四"}


# ================================================================
# Normalize Tests
# ================================================================

class TestNormalize:
    """Tests for normalize plugin."""

    def _get_plugin(self):
        from plugins.processors.normalize.plugin import NormalizePlugin
        return NormalizePlugin()

    def _make_batch(self, fields_list: list[dict]) -> RecordBatch:
        records = []
        for i, f in enumerate(fields_list):
            records.append(NormalizedRecordDTO(
                record_id=f"{i:032d}",
                dataset="test",
                schema_id=EDUCATION_TUTOR_V1,
                fields=f,
            ))
        return RecordBatch(schema_version="1", records=records)

    def test_fullwidth_space(self):
        """Full-width spaces normalized to half-width."""
        plugin = self._get_plugin()
        batch = self._make_batch([{"name": "张　三", "title": "教授"}])
        ctx = _make_context("normalize")

        result = plugin.execute(batch, ctx)

        assert result.records[0].fields["name"] == "张 三"

    def test_collapse_whitespace(self):
        """Multiple spaces collapsed to single space."""
        plugin = self._get_plugin()
        batch = self._make_batch([{"name": "张  三  李"}])
        ctx = _make_context("normalize")

        result = plugin.execute(batch, ctx)

        assert result.records[0].fields["name"] == "张 三 李"

    def test_non_string_fields_preserved(self):
        """Non-string fields (int, list, dict) are preserved."""
        plugin = self._get_plugin()
        batch = self._make_batch([{"year": 2026, "tags": ["a", "b"], "nested": {"x": 1}}])
        ctx = _make_context("normalize")

        result = plugin.execute(batch, ctx)

        assert result.records[0].fields["year"] == 2026
        assert result.records[0].fields["tags"] == ["a", "b"]
        assert result.records[0].fields["nested"] == {"x": 1}

    def test_list_string_items_normalized(self):
        """String items inside lists are normalized."""
        plugin = self._get_plugin()
        batch = self._make_batch([{"honors": ["优秀　教师", "教学  先进"]  }])
        ctx = _make_context("normalize")

        result = plugin.execute(batch, ctx)

        assert result.records[0].fields["honors"] == ["优秀 教师", "教学 先进"]

    def test_nonbascii_whitespace(self):
        """Non-breaking spaces (\xa0) normalized."""
        plugin = self._get_plugin()
        batch = self._make_batch([{"name": "张\xa0三"}])
        ctx = _make_context("normalize")

        result = plugin.execute(batch, ctx)

        assert result.records[0].fields["name"] == "张 三"

    def test_empty_batch(self):
        """Empty batch passes through."""
        plugin = self._get_plugin()
        batch = RecordBatch(schema_version="1", records=[])
        ctx = _make_context("normalize")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 0

    def test_does_not_mutate_input(self):
        """Input batch is not mutated."""
        plugin = self._get_plugin()
        batch = self._make_batch([{"name": "张　三"}])
        ctx = _make_context("normalize")

        _ = plugin.execute(batch, ctx)

        # Original batch untouched
        assert batch.records[0].fields["name"] == "张　三"


# ================================================================
# Dedup Tests
# ================================================================

class TestDedup:
    """Tests for dedup plugin."""

    def _get_plugin(self):
        from plugins.processors.dedup.plugin import DedupPlugin
        return DedupPlugin()

    def _make_batch(self, fields_list: list[dict]) -> RecordBatch:
        records = []
        for i, f in enumerate(fields_list):
            records.append(NormalizedRecordDTO(
                record_id=f"{i:032d}",
                dataset="test",
                schema_id=EDUCATION_TUTOR_V1,
                fields=f,
            ))
        return RecordBatch(schema_version="1", records=records)

    def test_dedup_by_default_key(self):
        """Default key: university + college + name + title."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            {"university": "A", "college": "B", "name": "张三", "title": "教授"},
            {"university": "A", "college": "B", "name": "张三", "title": "教授"},  # dup
            {"university": "A", "college": "B", "name": "李四", "title": "副教授"},
        ])
        ctx = _make_context("dedup")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 2
        assert result.stats["dedup_dropped"] == 1

    def test_different_college_not_deduped(self):
        """Same name in different college is not a duplicate."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            {"university": "A", "college": "B", "name": "张三", "title": "教授"},
            {"university": "A", "college": "C", "name": "张三", "title": "教授"},
        ])
        ctx = _make_context("dedup")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 2

    def test_custom_key_fields(self):
        """Custom key_fields override default dedup key."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            {"university": "A", "college": "B", "name": "张三", "title": "教授"},
            {"university": "A", "college": "B", "name": "张三", "title": "副教授"},
        ])
        ctx = _make_context("dedup")
        ctx.config_snapshot["plugins"]["dedup"]["params"]["key_fields"] = ["university", "name"]

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 1

    def test_empty_batch(self):
        """Empty batch passes through."""
        plugin = self._get_plugin()
        batch = RecordBatch(schema_version="1", records=[])
        ctx = _make_context("dedup")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 0


# ================================================================
# Education Merge Tests
# ================================================================

class TestEducationMerge:
    """Tests for education_merge plugin — three-phase matching."""

    def _get_plugin(self):
        from plugins.processors.education_merge.plugin import EducationMergePlugin
        return EducationMergePlugin()

    def _make_batch(self, records_data: list[tuple[dict, str]]) -> RecordBatch:
        """Create batch from (fields, source_type) pairs."""
        records = []
        for i, (fields, source_type) in enumerate(records_data):
            fields["source_type"] = source_type
            records.append(NormalizedRecordDTO(
                record_id=f"{i:032d}",
                dataset=f"{fields.get('university', '')}:{fields.get('college', '')}",
                schema_id=EDUCATION_TUTOR_V1,
                fields=fields,
                provenance={"source_id": f"src_{source_type}", "url": f"http://{source_type}", "fetched_at": "2026-01-01"},
            ))
        return RecordBatch(schema_version="1", records=records)

    def test_exact_match_merge(self):
        """Two records with same name in same university/college merge."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            ({"university": "A", "college": "B", "year": 2026, "name": "张三", "title": "教授", "research": "AI"}, "官网师资页"),
            ({"university": "A", "college": "B", "year": 2026, "name": "张三", "title": "", "enrollment": {"in_roster": True}}, "研招网"),
        ])
        ctx = _make_context("education_merge")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 1
        rec = result.records[0]
        assert rec.fields["match_status"] == "merged"
        # Provenance should contain both sources
        assert len(rec.provenance.get("sources", [])) == 2

    def test_strip_match(self):
        """'张 三' and '张三' match via strip phase."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            ({"university": "A", "college": "B", "year": 2026, "name": "张 三", "title": ""}, "官网师资页"),
            ({"university": "A", "college": "B", "year": 2026, "name": "张三", "title": ""}, "研招网"),
        ])
        ctx = _make_context("education_merge")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 1
        assert result.records[0].fields["match_status"] == "merged"

    def test_cross_college_no_merge(self):
        """Same name in different college does NOT merge."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            ({"university": "A", "college": "B", "year": 2026, "name": "张三", "title": ""}, "官网师资页"),
            ({"university": "A", "college": "C", "year": 2026, "name": "张三", "title": ""}, "研招网"),
        ])
        ctx = _make_context("education_merge")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 2
        statuses = {r.fields["match_status"] for r in result.records}
        assert "partial_faculty" in statuses
        assert "partial_notice" in statuses

    def test_cross_university_no_merge(self):
        """Same name in different university does NOT merge."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            ({"university": "A", "college": "B", "year": 2026, "name": "张三", "title": ""}, "官网师资页"),
            ({"university": "X", "college": "B", "year": 2026, "name": "张三", "title": ""}, "研招网"),
        ])
        ctx = _make_context("education_merge")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 2

    def test_single_source_pass_through(self):
        """Only faculty records → all partial_faculty."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            ({"university": "A", "college": "B", "year": 2026, "name": "张三", "title": ""}, "官网师资页"),
            ({"university": "A", "college": "B", "year": 2026, "name": "李四", "title": ""}, "官网师资页"),
        ])
        ctx = _make_context("education_merge")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 2
        assert all(r.fields["match_status"] == "partial_faculty" for r in result.records)

    def test_empty_batch(self):
        """Empty batch produces empty result."""
        plugin = self._get_plugin()
        batch = RecordBatch(schema_version="1", records=[])
        ctx = _make_context("education_merge")

        result = plugin.execute(batch, ctx)

        assert len(result.records) == 0


# ================================================================
# Statistics Tests
# ================================================================

class TestStatistics:
    """Tests for statistics plugin."""

    def _get_plugin(self):
        from plugins.processors.statistics.plugin import StatisticsPlugin
        return StatisticsPlugin()

    def _make_batch(self, fields_list: list[dict]) -> RecordBatch:
        records = []
        for i, f in enumerate(fields_list):
            records.append(NormalizedRecordDTO(
                record_id=f"{i:032d}",
                dataset="test",
                schema_id=EDUCATION_TUTOR_V1,
                fields=f,
            ))
        return RecordBatch(schema_version="1", records=records)

    def test_group_count(self):
        """Records grouped by university+college+year."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            {"university": "A", "college": "B", "year": 2026, "source_type": "官网师资页"},
            {"university": "A", "college": "B", "year": 2026, "source_type": "官网师资页"},
            {"university": "A", "college": "C", "year": 2026, "source_type": "研招网"},
        ])
        ctx = _make_context("statistics")

        result = plugin.execute(batch, ctx)

        stats = result.stats["statistics"]
        assert stats["total_records"] == 3
        assert stats["group_count"] == 2

    def test_field_distribution(self):
        """Field distribution counts are correct."""
        plugin = self._get_plugin()
        batch = self._make_batch([
            {"university": "A", "college": "B", "year": 2026, "source_type": "官网师资页", "match_status": "merged"},
            {"university": "A", "college": "B", "year": 2026, "source_type": "研招网", "match_status": "merged"},
            {"university": "A", "college": "C", "year": 2026, "source_type": "研招网", "match_status": "partial_notice"},
        ])
        ctx = _make_context("statistics")

        result = plugin.execute(batch, ctx)

        dist = result.stats["statistics"]["distributions"]
        assert dist["source_type"]["官网师资页"] == 1
        assert dist["source_type"]["研招网"] == 2
        assert dist["match_status"]["merged"] == 2
        assert dist["match_status"]["partial_notice"] == 1

    def test_records_unchanged(self):
        """Records are NOT modified by statistics."""
        plugin = self._get_plugin()
        batch = self._make_batch([{"university": "A", "college": "B", "year": 2026, "source_type": "官网师资页"}])
        ctx = _make_context("statistics")

        result = plugin.execute(batch, ctx)

        # Same record objects
        assert result.records is batch.records

    def test_empty_batch(self):
        """Empty batch produces zero stats."""
        plugin = self._get_plugin()
        batch = RecordBatch(schema_version="1", records=[])
        ctx = _make_context("statistics")

        result = plugin.execute(batch, ctx)

        assert result.stats["statistics"]["total_records"] == 0


# ================================================================
# Cross-Plugin Chain Tests
# ================================================================

class TestProcessorChain:
    """Test the post-chain order: normalize → dedup → merge → statistics."""

    def _get_plugins(self):
        from plugins.processors.normalize.plugin import NormalizePlugin
        from plugins.processors.dedup.plugin import DedupPlugin
        from plugins.processors.education_merge.plugin import EducationMergePlugin
        from plugins.processors.statistics.plugin import StatisticsPlugin
        return NormalizePlugin(), DedupPlugin(), EducationMergePlugin(), StatisticsPlugin()

    def test_chain_execution(self):
        """Full chain produces valid RecordBatch with stats."""
        norm, dedup, merge, stats = self._get_plugins()

        records = [
            NormalizedRecordDTO(
                record_id=f"{i:032d}", dataset="A:B", schema_id=EDUCATION_TUTOR_V1,
                fields={
                    "university": "A", "college": "B", "year": 2026, "name": name,
                    "title": "", "source_type": st,
                },
                provenance={"source_id": f"s{i}"},
            )
            for i, (name, st) in enumerate([
                ("张 三", "官网师资页"),
                ("张三", "研招网"),
            ])
        ]
        batch = RecordBatch(schema_version="1", records=records)
        ctx = _make_context("normalize")

        # Step 1: normalize
        batch = norm.execute(batch, ctx)
        # Step 2: dedup (no effect — different source_type)
        ctx2 = _make_context("dedup")
        batch = dedup.execute(batch, ctx2)
        # Step 3: merge
        ctx3 = _make_context("education_merge")
        batch = merge.execute(batch, ctx3)
        # Step 4: statistics
        ctx4 = _make_context("statistics")
        batch = stats.execute(batch, ctx4)

        assert isinstance(batch, RecordBatch)
        assert "statistics" in batch.stats
        assert len(batch.records) == 1  # Merged via strip match
        assert batch.records[0].fields["match_status"] == "merged"

    def test_schema_id_rejection(self):
        """Unknown schema_id should be handled gracefully."""
        from plugins.processors.normalize.plugin import NormalizePlugin

        records = [
            NormalizedRecordDTO(
                record_id="0" * 32, dataset="test", schema_id="unknown.schema.v99",
                fields={"name": "test"},
            ),
        ]
        batch = RecordBatch(schema_version="1", records=records)

        norm = NormalizePlugin()
        ctx = _make_context("normalize")

        # Normalize doesn't validate schema_id — it just normalizes text
        result = norm.execute(batch, ctx)
        assert len(result.records) == 1
