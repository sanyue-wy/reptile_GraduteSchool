"""Managed output workspace for storage plugins.

Provides structured layout: runs/<run_id>/{store,media,outputs}
"""

import os
import shutil
from pathlib import Path
from typing import Optional


class ManagedWorkspace:
    """Creates and manages the output workspace for a run.

    Layout:
        runs/<run_id>/
            store/          # storage plugin outputs (jsonl, xlsx, sqlite)
            media/          # media_store files (images, videos, documents)
            outputs/        # presenter outputs (html, pdf, etc.)
    """

    def __init__(self, run_id: str, base_dir: Optional[Path] = None):
        self.run_id = run_id
        self.base_dir = Path(base_dir) if base_dir else Path("data/runs")
        self.run_dir = self.base_dir / run_id
        self.store_dir = self.run_dir / "store"
        self.media_dir = self.run_dir / "media"
        self.outputs_dir = self.run_dir / "outputs"

    def create(self) -> None:
        """Create the workspace directory structure."""
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def get_store_path(self, target_id: str, extension: str = "") -> Path:
        """Get path for a storage target output."""
        self.store_dir.mkdir(parents=True, exist_ok=True)
        if extension and not extension.startswith("."):
            extension = "." + extension
        return self.store_dir / f"{target_id}{extension}"

    def get_media_path(self, media_type: str, filename: str) -> Path:
        """Get path for a media file under media/<media_type>/."""
        media_type_dir = self.media_dir / media_type
        media_type_dir.mkdir(parents=True, exist_ok=True)
        return media_type_dir / filename

    def get_output_path(self, output_id: str, extension: str = "") -> Path:
        """Get path for a presenter output."""
        self.outputs_dir.mkdir(parents=True, exist_ok=True)
        if extension and not extension.startswith("."):
            extension = "." + extension
        return self.outputs_dir / f"{output_id}{extension}"

    def list_store_files(self) -> list[Path]:
        """List all files in the store directory."""
        if not self.store_dir.exists():
            return []
        return list(self.store_dir.rglob("*"))

    def list_media_files(self) -> list[Path]:
        """List all files in the media directory."""
        if not self.media_dir.exists():
            return []
        return list(self.media_dir.rglob("*"))

    def cleanup(self, keep_empty_dirs: bool = False) -> None:
        """Remove the entire run workspace.

        Args:
            keep_empty_dirs: If True, only remove files, keep directory structure
        """
        if self.run_dir.exists():
            if keep_empty_dirs:
                for file in self.run_dir.rglob("*"):
                    if file.is_file():
                        file.unlink()
            else:
                shutil.rmtree(self.run_dir)

    @staticmethod
    def list_runs(base_dir: Optional[Path] = None) -> list[str]:
        """List all run IDs in the base directory."""
        base = Path(base_dir) if base_dir else Path("data/runs")
        if not base.exists():
            return []
        return [d.name for d in base.iterdir() if d.is_dir()]

    @staticmethod
    def cleanup_old_runs(max_runs: int = 10, base_dir: Optional[Path] = None) -> None:
        """Keep only the most recent N runs, remove older ones."""
        base = Path(base_dir) if base_dir else Path("data/runs")
        if not base.exists():
            return
        runs = sorted(
            [d for d in base.iterdir() if d.is_dir()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old_run in runs[max_runs:]:
            shutil.rmtree(old_run, ignore_errors=True)


def get_allowed_paths(run_id: str, base_dir: Optional[Path] = None) -> list[str]:
    """Get list of allowed paths for a run's plugins.

    Used for PluginContext.allowed_paths to restrict plugin filesystem access.
    """
    workspace = ManagedWorkspace(run_id, base_dir)
    return [
        str(workspace.store_dir.resolve()),
        str(workspace.media_dir.resolve()),
        str(workspace.outputs_dir.resolve()),
    ]


def resolve_safe_path(path: str, allowed_paths: list[str]) -> Path:
    """Resolve a path and verify it's within allowed directories.

    Raises:
        ValueError: If path is outside allowed directories
    """
    target = Path(path).resolve()
    for allowed in allowed_paths:
        allowed_path = Path(allowed).resolve()
        try:
            target.relative_to(allowed_path)
            return target
        except ValueError:
            continue
    raise ValueError(f"Path {path} is not within allowed directories")