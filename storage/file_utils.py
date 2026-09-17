"""Shared, process-local path locks and atomic JSON file access.

Call ``path_lock(path)`` around a complete read/modify/write transaction.
The lock is reentrant so transactions may call the public read/write helpers.
These locks coordinate threads and store instances, not separate processes.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading


_locks = {}
_locks_guard = threading.Lock()


def path_lock(path):
    """Return the same reentrant lock for equivalent absolute file paths."""
    key = os.path.normcase(str(Path(path).resolve()))
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


@contextmanager
def atomic_writer(path, *, binary=False):
    """Write a unique sibling temporary file, replace on success, always clean up."""
    path = Path(path)
    with path_lock(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            stream = os.fdopen(fd, "wb" if binary else "w", **({} if binary else {"encoding": "utf-8"}))
            fd = None  # The stream now owns the descriptor.
            with stream:
                yield stream
            os.replace(temporary, path)
        finally:
            if fd is not None:
                os.close(fd)
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def read_json(path, default=None):
    """Read one JSON document; return default only when the file is missing."""
    with path_lock(path):
        try:
            with open(path, "r", encoding="utf-8") as stream:
                return json.load(stream)
        except FileNotFoundError:
            return default


def write_json(path, data):
    """Atomically replace one JSON document (not JSONL)."""
    with atomic_writer(path) as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
