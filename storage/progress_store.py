"""Cached progress snapshots and atomic, cross-instance thread transactions."""

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import time

from .file_utils import path_lock, read_json, write_json

PROGRESS_FILE = Path("data/output/progress.json")
SOURCES = ("source_a", "source_b", "merged")


def default_structure() -> dict:
    return {
        "version": 1,
        "updated_at": datetime.now().isoformat(),
        "schools": {},
        "pipelines": {source: {"completed": 0, "total": 147} for source in SOURCES},
        "source_breakdown": {key: 0 for key in ("matched", "notice_only", "faculty_only", "unmatched")},
    }


def default_school() -> dict:
    return {"source_a": "pending", "source_b": "pending", "merged": "pending",
            "last_crawl_at": "", "tutor_count": 0}


def recalc_pipelines(data: dict) -> None:
    pipelines = data.setdefault("pipelines", {})
    for source in SOURCES:
        entry = pipelines.setdefault(source, {})
        entry["completed"] = sum(school.get(source) == "done" for school in data["schools"].values())
        entry["total"] = 147


class ProgressStore:
    def __init__(self, path=PROGRESS_FILE, cache_ttl=1.0):
        self._path = Path(path).resolve()
        self._lock = path_lock(self._path)
        self._cache = None
        self._cache_time = 0.0
        self._cache_ttl = cache_ttl
        self._cache_signature = None

    def _signature(self):
        try:
            stat = self._path.stat()
            return stat.st_mtime_ns, stat.st_size, stat.st_ino
        except FileNotFoundError:
            return None

    def _read_disk(self):
        try:
            data = read_json(self._path)
        except json.JSONDecodeError:
            data = None
        if not isinstance(data, dict):
            return default_structure()
        for key, value in default_structure().items():
            data.setdefault(key, value)
        return data

    def _remember(self, data):
        self._cache = deepcopy(data)
        self._cache_time = time.time()
        self._cache_signature = self._signature()

    def load(self) -> dict:
        """Return a detached snapshot; external file changes invalidate the cache."""
        with self._lock:
            if (self._cache is not None
                    and time.time() - self._cache_time < self._cache_ttl
                    and self._cache_signature == self._signature()):
                return deepcopy(self._cache)
            data = self._read_disk()
            self._remember(data)
            return deepcopy(data)

    def save(self, data: dict) -> None:
        """Replace the complete snapshot; use transaction() for read/modify/write."""
        with self._lock:
            snapshot = deepcopy(data)
            snapshot["updated_at"] = datetime.now().isoformat()
            write_json(self._path, snapshot)
            self._remember(snapshot)

    def initialize(self) -> None:
        """Create defaults only if missing, inside the shared file lock."""
        with self._lock:
            if not self._path.exists():
                self.save(default_structure())

    def transaction(self, update):
        """Apply update(data) to fresh disk state and commit under one path lock.

        Return the callback result. Exceptions leave the previous file/cache intact.
        Transactions bypass TTL so stale instances cannot overwrite peer updates.
        """
        with self._lock:
            data = self._read_disk()
            result = update(data)
            self.save(data)
            return deepcopy(result)

    def update_school_status(self, university: str, college: str = "", **kwargs) -> None:
        def update(data):
            key = f"{university}|{college}"
            school = data["schools"].setdefault(key, default_school())
            changes = {key: deepcopy(value) for key, value in kwargs.items() if value is not None}
            school.update(changes)
            if changes and "last_crawl_at" not in changes:
                school["last_crawl_at"] = datetime.now().isoformat()
            recalc_pipelines(data)
        self.transaction(update)

    def read_all_schools(self) -> dict:
        return self.load()["schools"]
