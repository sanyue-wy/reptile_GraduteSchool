"""SQLite Storage Plugin.

Implements SQLite storage with UPSERT support, schema migration, and atomic transactions.
"""

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from contracts.result import StoreRequest, StoreReceipt, ErrorDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)

# Schema for the records table
INIT_SQL = """
-- Records table with natural key (record_id)
CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    fields_json TEXT NOT NULL,  -- JSON serialized fields
    provenance_json TEXT,       -- JSON serialized provenance
    media_refs_json TEXT,       -- JSON serialized media_refs list
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_records_dataset ON records(dataset);
CREATE INDEX IF NOT EXISTS idx_records_schema ON records(schema_id);
CREATE INDEX IF NOT EXISTS idx_records_created ON records(created_at);

-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial schema version
INSERT OR IGNORE INTO schema_version (version) VALUES (1);
"""


class SqlStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    """Storage plugin for SQLite."""

    name = "sql_store"
    version = "1.0.0"
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    def __init__(self):
        super().__init__()
        self._config = {}
        self._conn = None

    def setup(self, context: PluginContext) -> None:
        """Initialize database connection and schema."""
        self._context = context
        # Read config from context.config_snapshot
        plugin_config = context.config_snapshot.get("plugins", {}).get("sql_store", {})
        self._config = plugin_config

        db_path = self._config.get("database_path")
        if not db_path:
            raise ValueError("database_path is required in config")

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")  # Better concurrency
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._transaction() as cur:
            cur.executescript(INIT_SQL)

    @contextmanager
    def _transaction(self):
        """Context manager for database transactions."""
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        """Execute SQLite storage with UPSERT.

        Args:
            request: StoreRequest with dataset, run_id, target_id, format_id, data_refs
            context: PluginContext with storage workspace

        Returns:
            StoreReceipt with written/skipped/failed counts and output_ref
        """
        try:
            records = self._load_records(request, context)

            if not records:
                return StoreReceipt(
                    target_id=request.target_id,
                    written=0,
                    skipped=0,
                    failed=0,
                    records_written=0,
                    output_ref=self._config.get("database_path", ""),
                )

            written, skipped = self._upsert_records(records, request.dataset)

            return StoreReceipt(
                target_id=request.target_id,
                written=written,
                skipped=skipped,
                failed=0,
                records_written=written,
                output_ref=self._config.get("database_path", ""),
            )

        except Exception as e:
            logger.exception("SQLite storage failed for target %s", request.target_id)
            return StoreReceipt(
                target_id=request.target_id,
                written=0,
                skipped=0,
                failed=1,
                records_written=0,
                output_ref="",
                error=ErrorDTO(
                    code="STORAGE_WRITE_FAILED",
                    message=str(e),
                    stage="store",
                    task_id=request.state_snapshot.get("task_id", ""),
                    retryable=True,
                ),
            )

    def _load_records(self, request: StoreRequest, context: PluginContext) -> list[dict]:
        """Load records from data_refs (placeholder)."""
        # Actual implementation would fetch from data_refs
        return []

    def _upsert_records(self, records: list[dict], dataset: str) -> tuple[int, int]:
        """Upsert records using natural key (record_id).

        Returns:
            Tuple of (written_count, skipped_count)
        """
        written = 0
        skipped = 0

        with self._transaction() as cur:
            for rec in records:
                record_id = rec.get("record_id")
                if not record_id:
                    logger.warning("Record missing record_id, skipping: %s", rec)
                    continue

                # Check if record exists
                cur.execute("SELECT record_id FROM records WHERE record_id = ?", (record_id,))
                exists = cur.fetchone() is not None

                import json
                from datetime import datetime
                now = datetime.now().isoformat()

                if exists:
                    # Update existing record
                    cur.execute("""
                        UPDATE records SET
                            dataset = ?,
                            schema_id = ?,
                            fields_json = ?,
                            provenance_json = ?,
                            media_refs_json = ?,
                            updated_at = ?
                        WHERE record_id = ?
                    """, (
                        dataset,
                        rec.get("schema_id", ""),
                        json.dumps(rec.get("fields", {}), ensure_ascii=False),
                        json.dumps(rec.get("provenance", {}), ensure_ascii=False),
                        json.dumps(rec.get("media_refs", []), ensure_ascii=False),
                        now,
                        record_id,
                    ))
                    skipped += 1
                else:
                    # Insert new record
                    cur.execute("""
                        INSERT INTO records (record_id, dataset, schema_id, fields_json, provenance_json, media_refs_json, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record_id,
                        dataset,
                        rec.get("schema_id", ""),
                        json.dumps(rec.get("fields", {}), ensure_ascii=False),
                        json.dumps(rec.get("provenance", {}), ensure_ascii=False),
                        json.dumps(rec.get("media_refs", []), ensure_ascii=False),
                        rec.get("created_at", now),
                        now,
                    ))
                    written += 1

        logger.info("SQLite upsert: written=%d, skipped=%d", written, skipped)
        return written, skipped

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


def get_schema_sql() -> str:
    """Return the schema initialization SQL for distribution with plugin package."""
    return INIT_SQL.strip()