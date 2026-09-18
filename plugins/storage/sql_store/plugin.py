"""SQLite Storage Plugin.

Implements SQLite storage with UPSERT support, schema migration, and atomic transactions.
"""

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from contracts.result import StoreRequest, StoreReceipt, ErrorDTO
from plugins.base import BasePlugin, PluginContext

logger = logging.getLogger(__name__)

INIT_SQL = """
CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    dataset TEXT NOT NULL,
    schema_id TEXT NOT NULL,
    fields_json TEXT NOT NULL,
    provenance_json TEXT,
    media_refs_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_records_dataset ON records(dataset);
CREATE INDEX IF NOT EXISTS idx_records_schema ON records(schema_id);
CREATE INDEX IF NOT EXISTS idx_records_created ON records(created_at);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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
        self._context = context
        self._config = context.config_snapshot.get("plugins", {}).get("sql_store", {})

        db_path = self._config.get("database_path")
        if not db_path:
            raise ValueError("database_path is required in config")

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._transaction() as cur:
            cur.executescript(INIT_SQL)

    @contextmanager
    def _transaction(self):
        cur = self._conn.cursor()
        try:
            yield cur
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
        try:
            from infra.storage import check_and_reserve, commit as idem_commit
            from converters.storage_converter import records_from_data_refs

            # Idempotency check
            base_dir = Path("data")
            if context.storage and hasattr(context.storage, "workspace"):
                base_dir = context.storage.workspace.base_dir
            cached = check_and_reserve(base_dir, request.run_id, request.idempotency_key)
            if cached is not None:
                return StoreReceipt(
                    target_id=cached.get("target_id", request.target_id),
                    written=0,
                    skipped=cached.get("records_written", 0),
                    failed=0,
                    records_written=0,
                    output_ref=cached.get("output_ref", ""),
                )

            records = records_from_data_refs(request.data_refs)

            if not records:
                receipt = StoreReceipt(
                    target_id=request.target_id,
                    written=0,
                    skipped=0,
                    failed=0,
                    records_written=0,
                    output_ref=self._config.get("database_path", ""),
                )
            else:
                written, skipped = self._upsert_records(records, request.dataset)
                receipt = StoreReceipt(
                    target_id=request.target_id,
                    written=written,
                    skipped=skipped,
                    failed=0,
                    records_written=written,
                    output_ref=self._config.get("database_path", ""),
                )

            idem_commit(base_dir, request.run_id, request.idempotency_key, {
                "target_id": receipt.target_id,
                "records_written": receipt.records_written,
                "output_ref": receipt.output_ref,
            })

            return receipt

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
                ),
            )

    def _upsert_records(self, records: list[dict], dataset: str) -> tuple[int, int]:
        """Upsert records using SQLite INSERT ... ON CONFLICT (record_id).

        Returns (written_count, skipped_count).
        """
        written = 0
        skipped = 0
        now = datetime.now().isoformat()

        with self._transaction() as cur:
            for rec in records:
                record_id = rec.get("record_id")
                if not record_id:
                    logger.warning("Record missing record_id, skipping: %s", rec)
                    continue

                fields_json = json.dumps(rec.get("fields", {}), ensure_ascii=False)
                provenance_json = json.dumps(rec.get("provenance", {}), ensure_ascii=False)
                media_refs_json = json.dumps(rec.get("media_refs", []), ensure_ascii=False)
                created_at = rec.get("created_at", now)

                # Check existence before upsert to track written vs skipped
                cur.execute("SELECT 1 FROM records WHERE record_id = ?", (record_id,))
                existed = cur.fetchone() is not None

                cur.execute("""
                    INSERT INTO records (record_id, dataset, schema_id, fields_json,
                                         provenance_json, media_refs_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(record_id) DO UPDATE SET
                        dataset = excluded.dataset,
                        schema_id = excluded.schema_id,
                        fields_json = excluded.fields_json,
                        provenance_json = excluded.provenance_json,
                        media_refs_json = excluded.media_refs_json,
                        updated_at = excluded.updated_at
                """, (
                    record_id, dataset, rec.get("schema_id", ""),
                    fields_json, provenance_json, media_refs_json,
                    created_at, now,
                ))

                if existed:
                    skipped += 1
                else:
                    written += 1

        logger.info("SQLite upsert: written=%d, skipped=%d", written, skipped)
        return written, skipped

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def get_schema_sql() -> str:
    """Return the schema initialization SQL for distribution with plugin package."""
    return INIT_SQL.strip()