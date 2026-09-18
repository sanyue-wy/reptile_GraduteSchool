"""Shared helpers for presenter plugins.

Provides output path resolution, atomic file writing, record preparation,
and the common execute() wrapper that converts render() return values
into RenderedOutputDTO.
"""

import csv
import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from contracts.output import PresentationRequest, RenderedOutputDTO
from plugins.base import PresenterPlugin, PluginContext

logger = logging.getLogger(__name__)


class BasePresenterHelper:
    """Mixin-style helper providing shared presenter logic.

    Callers (concrete PresenterPlugin subclasses) use these methods
    inside their render() implementation.
    """

    @staticmethod
    def resolve_output_dir(
        config: dict[str, Any],
        context: PluginContext,
        request: PresentationRequest,
        extension: str,
    ) -> Path:
        """Resolve the output directory for a presenter.

        Priority: config output_dir > context storage workspace > default.
        """
        output_dir = config.get("output_dir")
        if output_dir:
            base = Path(output_dir)
        elif context.storage and hasattr(context.storage, "workspace"):
            ws = context.storage.workspace
            if hasattr(ws, "get_store_path"):
                base = Path(ws.get_store_path(request.dataset, extension)).parent
            else:
                base = Path("data/runs") / request.run_state.get("run_id", "adhoc") / "outputs"
        else:
            base = Path("data/runs") / request.run_state.get("run_id", "adhoc") / "outputs"
        base.mkdir(parents=True, exist_ok=True)
        return base

    @staticmethod
    def make_output_path(base_dir: Path, dataset: str, extension: str, request_id: str = "") -> Path:
        """Generate a unique output file path."""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rid = request_id[:8] if request_id else uuid4().hex[:8]
        filename = f"{dataset}_{rid}_{ts}{extension}"
        return base_dir / filename

    @staticmethod
    def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> int:
        """Write text to file atomically (temp + replace). Returns byte count."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(content)
            os.replace(tmp_path, str(path))
            return len(content.encode(encoding))
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def atomic_write_bytes(path: Path, data: bytes) -> int:
        """Write bytes to file atomically. Returns byte count."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, str(path))
            return len(data)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def prepare_records(
        request: PresentationRequest,
    ) -> tuple[list[dict], list[str]]:
        """Apply field selection from output_spec to records.

        Returns (filtered_records, fieldnames).
        """
        records = request.records
        output_spec = request.output_spec or {}

        if not records:
            return [], []

        field_selection = output_spec.get("field_selection")
        include_fields = output_spec.get("include_fields")
        exclude_fields = output_spec.get("exclude_fields")

        # field_selection is the primary whitelist
        fields_filter = field_selection or include_fields

        if fields_filter and isinstance(fields_filter, list):
            fieldnames = [f for f in fields_filter if f]
            filtered = [{k: v for k, v in rec.items() if k in fieldnames} for rec in records]
            return filtered, fieldnames

        if exclude_fields and isinstance(exclude_fields, list):
            exc = set(exclude_fields)
            fieldnames = [k for k in records[0].keys() if k not in exc]
            filtered = [{k: v for k, v in rec.items() if k not in exc} for rec in records]
            return filtered, fieldnames

        fieldnames = list(records[0].keys())
        return records, fieldnames

    @staticmethod
    def json_default(obj: Any) -> Any:
        """JSON serializer for non-standard types."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return str(obj)

    @staticmethod
    def csv_value(value: Any) -> str:
        """Convert a value to CSV-safe string."""
        if value is None:
            return ""
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    @staticmethod
    def make_rendered_output(
        output_format: str,
        path: Path,
        metadata: dict[str, Any] | None = None,
        media_assets: list | None = None,
    ) -> RenderedOutputDTO:
        """Build a RenderedOutputDTO from common fields."""
        return RenderedOutputDTO(
            output_id=uuid4().hex,
            output_format=output_format,
            path=str(path),
            media_assets=media_assets or [],
            metadata=metadata or {},
        )
