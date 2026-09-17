"""Atomic configuration persistence without importing config.loader.

This layer preserves both legacy flat university/college entries and nested
university/categories entries. Validation, level enrichment and legacy fallback
belong to config.loader, not the storage layer.
"""

from copy import deepcopy
import logging
from pathlib import Path

from .file_utils import path_lock, read_json, write_json

logger = logging.getLogger(__name__)
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "school_data.json"


class ConfigStore:
    def __init__(self, config_path=None, global_path=None):
        self._path = Path(config_path if config_path is not None else DEFAULT_CONFIG_PATH).resolve()
        self._global_path = Path(global_path).resolve() if global_path is not None else self._path.parent / "global.json"
        self._lock = path_lock(self._path)

    def load_schools(self) -> list[dict]:
        data = read_json(self._path, [])
        if not isinstance(data, list):
            raise ValueError("School configuration must be a JSON list")
        return data

    def save_schools(self, schools: list[dict]) -> None:
        if not isinstance(schools, list):
            raise ValueError("School configuration must be a JSON list")
        write_json(self._path, deepcopy(schools))

    def save_school(self, university: str, data: dict) -> bool:
        """Upsert by university/college, without changing the existing format.

        A composite ``university|college`` key is also accepted; its identity
        overrides the payload, just as the university argument does in the old API.
        The caller's dictionary is never mutated.
        """
        try:
            entry = deepcopy(data)
            if "|" in university:
                university, college = university.split("|", 1)
                entry["college"] = college
            entry["university"] = university
            identity = (university, entry.get("college", ""))
            with self._lock:
                schools = self.load_schools()
                for index, old in enumerate(schools):
                    if (old.get("university", ""), old.get("college", "")) == identity:
                        schools[index] = entry
                        break
                else:
                    schools.append(entry)
                self.save_schools(schools)
            return True
        except Exception:
            logger.exception("写入学校配置失败: %s", self._path)
            return False

    def load_global(self) -> dict:
        data = read_json(self._global_path, {})
        if not isinstance(data, dict):
            raise ValueError("Global configuration must be a JSON object")
        return data

    def save_global(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise ValueError("Global configuration must be a JSON object")
        write_json(self._global_path, deepcopy(data))
