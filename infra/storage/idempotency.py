"""File-based idempotency key registry for storage plugins.

Tracks StoreRequest execution results so repeated calls with the same
idempotency_key return the cached receipt without re-executing side effects.

Uses the shared path_lock from atomic_io for thread safety.
"""

import json
from pathlib import Path

from .atomic_io import atomic_write_json, path_lock, read_json


def _registry_path(base_dir: Path, run_id: str) -> Path:
    """Registry file location: <base_dir>/runs/<run_id>/.idempotency.json"""
    return base_dir / "runs" / run_id / ".idempotency.json"


def check_and_reserve(base_dir: Path, run_id: str, idempotency_key: str) -> dict | None:
    """Check if an idempotency key has already been committed.

    Returns the cached receipt dict if committed, None if new.
    Thread-safe via path_lock on the registry file.
    """
    registry = _registry_path(base_dir, run_id)
    with path_lock(registry):
        data = read_json(registry, {})
        entry = data.get(idempotency_key)
        if entry and entry.get("status") == "committed":
            return entry.get("receipt")
    return None


def commit(base_dir: Path, run_id: str, idempotency_key: str, receipt: dict) -> None:
    """Record a successful execution under the given idempotency key.

    Thread-safe via path_lock on the registry file.
    """
    registry = _registry_path(base_dir, run_id)
    with path_lock(registry):
        data = read_json(registry, {})
        data[idempotency_key] = {
            "status": "committed",
            "receipt": receipt,
        }
        registry.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(registry, data)


def clear(base_dir: Path, run_id: str) -> None:
    """Remove the idempotency registry for a run (cleanup)."""
    registry = _registry_path(base_dir, run_id)
    with path_lock(registry):
        try:
            registry.unlink()
        except FileNotFoundError:
            pass
