"""Atomic I/O utilities with shared path locks.

This module provides thread-safe atomic file operations used by all storage plugins.
Reuses and extends storage.file_utils implementation.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
import threading


# Shared reentrant locks keyed by normalized absolute path
_locks = {}
_locks_guard = threading.Lock()


def path_lock(path):
    """Return the same reentrant lock for equivalent absolute file paths.

    Used to coordinate read/modify/write transactions across storage plugin instances.
    This coordinates threads within a process, not separate processes.
    """
    key = os.path.normcase(str(Path(path).resolve()))
    with _locks_guard:
        return _locks.setdefault(key, threading.RLock())


@contextmanager
def atomic_writer(path, *, binary=False):
    """Write a unique sibling temporary file, replace on success, always clean up.

    Args:
        path: Target file path
        binary: If True, open in binary mode; otherwise text mode with UTF-8

    Yields:
        File stream for writing
    """
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


def atomic_write_json(path, data, *, indent=2, ensure_ascii=False):
    """Atomically write a JSON document."""
    with atomic_writer(path) as stream:
        json.dump(data, stream, ensure_ascii=ensure_ascii, indent=indent)


def atomic_write_bytes(path, data: bytes):
    """Atomically write binary data."""
    with atomic_writer(path, binary=True) as stream:
        stream.write(data)


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
    atomic_write_json(path, data)