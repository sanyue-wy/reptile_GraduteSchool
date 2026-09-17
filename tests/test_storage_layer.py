# -*- coding: utf-8 -*-
"""存储层回归测试（临时目录，无真实配置/数据写入）"""

import json
import threading
from pathlib import Path

import pytest

from storage import ConfigStore, JSONLStore, ProgressStore
from utils.progress import ProgressTracker


class TestJSONLStore:
    def test_empty_path_reads_empty(self, tmp_dir):
        assert JSONLStore("").read_all() == []

    def test_missing_file_reads_empty(self, tmp_dir):
        assert JSONLStore(tmp_dir / "nope.jsonl").read_all() == []

    def test_empty_path_write_rejected(self, tmp_dir):
        with pytest.raises(ValueError):
            JSONLStore("").append({"a": 1})

    def test_roundtrip_and_malformed_skip(self, tmp_dir):
        path = tmp_dir / "x.jsonl"
        store = JSONLStore(path)
        store.append({"a": 1})
        store.write_all([{"b": 2}, {"c": "中文"}])
        assert store.read_all() == [{"b": 2}, {"c": "中文"}]
        path.write_text('{"ok":1}\nbroken\n\n{"ok":2}\n', encoding="utf-8")
        assert JSONLStore(path).read_all() == [{"ok": 1}, {"ok": 2}]

    def test_write_all_non_atomic_then_append(self, tmp_dir):
        path = tmp_dir / "y.jsonl"
        store = JSONLStore(path)
        store.write_all([{"a": 2}], atomic=False)
        store.append({"a": 3})
        assert [r["a"] for r in store.read_all()] == [2, 3]

    def test_atomic_replace_failure_preserves_original_and_cleans_temp(self, tmp_dir, monkeypatch):
        import storage.file_utils as files
        path = tmp_dir / "atomic.jsonl"
        store = JSONLStore(path)
        store.write_all([{"name": "original"}])
        original = path.read_bytes()
        def fail(*args, **kwargs):
            raise OSError("simulated replace failure")
        monkeypatch.setattr(files.os, "replace", fail)
        with pytest.raises(OSError, match="simulated"):
            store.write_all([{"name": "replacement"}])
        assert path.read_bytes() == original
        assert sorted(p.name for p in tmp_dir.iterdir()) == ["atomic.jsonl"]

    def test_atomic_serialization_failure_preserves_original(self, tmp_dir):
        path = tmp_dir / "atomic.jsonl"
        store = JSONLStore(path)
        store.write_all([{"name": "original"}])
        original = path.read_bytes()
        with pytest.raises(TypeError):
            store.write_all([{"good": 1}, {"bad": object()}])
        assert path.read_bytes() == original
        assert sorted(p.name for p in tmp_dir.iterdir()) == ["atomic.jsonl"]

    def test_append_threads_share_one_lock(self, tmp_dir):
        path = tmp_dir / "concurrent.jsonl"
        errors = []

        def worker(i):
            try:
                JSONLStore(path).append({"id": i})
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        assert sorted(r["id"] for r in JSONLStore(path).read_all()) == list(range(50))


class TestProgressStore:
    def test_stale_instance_cannot_drop_peer_update(self, tmp_dir):
        path = tmp_dir / "progress.json"
        a = ProgressStore(path, cache_ttl=3600)
        b = ProgressStore(path, cache_ttl=3600)
        a.load()
        b.load()
        a.update_school_status("大学A", "学院A1", source_a="done")
        b.update_school_status("大学B", "学院B1", source_b="done")
        assert set(a.load()["schools"]) == {"大学A|学院A1", "大学B|学院B1"}

    def test_load_returns_detached_copy(self, tmp_dir):
        store = ProgressStore(tmp_dir / "p.json", cache_ttl=3600)
        store.load()["schools"]["污染"] = {}
        assert "污染" not in store.load()["schools"]

    def test_external_change_invalidates_cache(self, tmp_dir):
        path = tmp_dir / "p.json"
        store = ProgressStore(path, cache_ttl=3600)
        store.load()
        peer = ProgressStore(path, cache_ttl=3600)
        peer.save({"version": 1, "schools": {"大学A|学院A1": {"tutor_count": 7}}})
        assert store.load()["schools"]["大学A|学院A1"]["tutor_count"] == 7

    def test_same_school_cross_instance_four_thread_updates(self, tmp_dir):
        from concurrent.futures import ThreadPoolExecutor
        path = tmp_dir / "p.json"
        stores = [ProgressStore(path, cache_ttl=3600) for _ in range(4)]
        for store in stores:
            store.load()
        barrier = threading.Barrier(4)
        def update(i):
            barrier.wait(timeout=5)
            stores[i].update_school_status("大学", "学院", **{f"field_{i}": i})
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(update, range(4)))
        result = stores[0].read_all_schools()["大学|学院"]
        assert {k: result[k] for k in result if k.startswith("field_")} == {
            f"field_{i}": i for i in range(4)}

    def test_ttl_cache_reads_once_then_expires(self, tmp_dir, monkeypatch):
        from unittest.mock import Mock
        import storage.progress_store as module
        clock = [100.0]
        monkeypatch.setattr(module.time, "time", lambda: clock[0])
        store = ProgressStore(tmp_dir / "p.json", cache_ttl=10)
        read = Mock(wraps=store._read_disk)
        monkeypatch.setattr(store, "_read_disk", read)
        store.load()
        store.load()
        assert read.call_count == 1
        clock[0] += 11
        store.load()
        assert read.call_count == 2

    def test_failed_save_preserves_file_and_cached_snapshot(self, tmp_dir, monkeypatch):
        import storage.file_utils as module
        path = tmp_dir / "p.json"
        store = ProgressStore(path, cache_ttl=3600)
        store.update_school_status("大学", "学院", source_a="done")
        original = path.read_bytes()
        def fail(*args):
            raise OSError("replace interrupted")
        monkeypatch.setattr(module.os, "replace", fail)
        with pytest.raises(OSError):
            store.update_school_status("大学", "学院", source_b="done")
        assert path.read_bytes() == original
        assert store.read_all_schools()["大学|学院"]["source_b"] == "pending"
        assert sorted(p.name for p in tmp_dir.iterdir()) == ["p.json"]

    def test_transaction_keeps_data_on_error(self, tmp_dir):
        path = tmp_dir / "p.json"
        store = ProgressStore(path)
        store.update_school_status("大学A", "学院A1", source_a="done")
        with pytest.raises(RuntimeError):
            store.transaction(lambda data: (_ for _ in ()).throw(RuntimeError("boom")))
        assert store.load()["schools"]["大学A|学院A1"]["source_a"] == "done"

    def test_corrupt_file_falls_back_to_defaults(self, tmp_dir):
        path = tmp_dir / "p.json"
        path.write_text("{broken", encoding="utf-8")
        data = ProgressStore(path).load()
        assert data["version"] == 1 and data["pipelines"]["source_a"]["total"] == 147

    def test_default_structure_preserved(self, tmp_dir):
        store = ProgressStore(tmp_dir / "p.json")
        data = store.load()
        assert data["version"] == 1
        assert data["pipelines"] == {
            "source_a": {"completed": 0, "total": 147},
            "source_b": {"completed": 0, "total": 147},
            "merged": {"completed": 0, "total": 147},
        }


class TestConfigStore:
    def test_missing_files_empty(self, tmp_dir):
        store = ConfigStore(tmp_dir / "schools.json", tmp_dir / "global.json")
        assert store.load_schools() == [] and store.load_global() == {}

    def test_save_school_preserves_identity_and_format(self, tmp_dir):
        store = ConfigStore(tmp_dir / "schools.json", tmp_dir / "global.json")
        payload = {"university": "wrong", "categories": [{"college": "机械学院", "category": "mechanical"}]}
        assert store.save_school("测试大学", payload) is True
        assert payload == {"university": "wrong", "categories": [{"college": "机械学院", "category": "mechanical"}]}
        schools = store.load_schools()
        assert schools[0]["university"] == "测试大学"
        assert schools[0]["categories"][0]["college"] == "机械学院"

    def test_save_school_composite_key_upsert(self, tmp_dir):
        store = ConfigStore(tmp_dir / "schools.json", tmp_dir / "global.json")
        store.save_school("测试大学|物理学院", {"categories": []})
        store.save_school("测试大学|物理学院", {"categories": [{"college": "物理学院"}]})
        schools = store.load_schools()
        assert len(schools) == 1
        assert schools[0]["university"] == "测试大学"
        assert schools[0]["college"] == "物理学院"

    def test_save_schools_bulk_and_global(self, tmp_dir):
        store = ConfigStore(tmp_dir / "schools.json", tmp_dir / "global.json")
        store.save_schools([{"university": "大学A", "categories": []}])
        store.save_global({"concurrency": 4})
        assert store.load_schools() == [{"university": "大学A", "categories": []}]
        assert store.load_global() == {"concurrency": 4}


class TestProgressTrackerCompat:
    def test_cross_instance_updates_preserved(self, tmp_dir):
        path = tmp_dir / "progress.json"
        log = tmp_dir / "crawl.log"
        a = ProgressTracker(progress_file=path, log_file=log, cache_ttl=3600)
        b = ProgressTracker(progress_file=path, log_file=log, cache_ttl=3600)
        a._read_raw()
        b._read_raw()
        a.update_school_status("大学A", "学院A1", source_a="done")
        b.update_school_status("大学B", "学院B1", source_b="done")
        keys = set(b._read_raw()["schools"])
        assert keys == {"大学A|学院A1", "大学B|学院B1"}

    def test_update_source_breakdown_concurrent(self, tmp_dir):
        tracker = ProgressTracker(
            progress_file=tmp_dir / "progress.json",
            log_file=tmp_dir / "crawl.log",
        )

        def worker(i):
            tracker.update_school_status(f"大学{i}", "学院", source_a="done")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        tracker.update_source_breakdown(1, 2, 3, 4)
        data = json.loads((tmp_dir / "progress.json").read_text(encoding="utf-8"))
        assert data["source_breakdown"] == {"matched": 1, "notice_only": 2, "faculty_only": 3, "unmatched": 4}
        assert data["pipelines"]["source_a"]["completed"] == 10

    def test_cache_ttl_parameter(self, tmp_dir):
        tracker = ProgressTracker(
            progress_file=tmp_dir / "progress.json",
            log_file=tmp_dir / "crawl.log",
            cache_ttl=0,
        )
        tracker.update_school_status("大学A", "学院A1", source_a="done")
        assert tracker.get_school_status("大学A", "学院A1")["source_a"] == "done"
