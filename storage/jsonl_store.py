"""JSONL file access with atomic replacement and shared per-path locks."""

import json
import logging
from pathlib import Path

from .file_utils import atomic_writer, path_lock

logger = logging.getLogger(__name__)


class JSONLStore:
    def __init__(self, path):
        # Path('') is '.', not an empty filename.
        self._path = Path(path).resolve() if path else None
        self._lock = path_lock(self._path) if self._path is not None else None

    def read_all(self) -> list[dict]:
        if self._path is None:
            return []
        records = []
        with self._lock:
            try:
                with self._path.open("r", encoding="utf-8") as stream:
                    for number, line in enumerate(stream, 1):
                        if not line.strip():
                            continue
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            logger.warning("JSONL 解析失败，跳过第 %d 行: %s", number, self._path)
            except FileNotFoundError:
                logger.debug("文件不存在: %s", self._path)
        return records

    def _require_path(self):
        if self._path is None:
            raise ValueError("A non-empty file path is required for writing")
        return self._path

    def write_all(self, records: list[dict], atomic: bool = True) -> None:
        path = self._require_path()
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = atomic_writer(path) if atomic else path.open("w", encoding="utf-8")
            with writer as stream:
                for record in records:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def append(self, record: dict) -> None:
        path = self._require_path()
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as stream:
                stream.write(line)
