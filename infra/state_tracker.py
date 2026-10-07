# -*- coding: utf-8 -*-
"""
状态追踪器（V3.0）
=================
提供运行时状态查询接口，用于控制台实时刷新。
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class StateTracker:
    """管道运行状态追踪器。

    维护 data/output/run_state.json 和 data/output/run_event.json。
    所有写入使用 tempfile + os.replace 保证原子。
    """

    def __init__(self, output_dir: Path = Path("data/output")):
        self._output_dir = Path(output_dir)
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._runs_lock = threading.Lock()

    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        """原子写入 JSON 文件。

        Windows 兼容：直接 os.replace(tmp, target) 即可（POSIX 语义，
        Python 在 Windows 上也会先替换再返回）。旧实现"先删后 replace"
        在极短窗口内会令读者看到文件不存在，前端轮询可能恰好落空。
        """
        import os
        import tempfile
        self._output_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self._output_dir, suffix=".tmp")
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, str(path))
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def update(self, run_id: str, progress: Optional[dict[str, float]] = None,
               stats: Optional[dict[str, int]] = None) -> dict[str, Any]:
        """更新运行状态。

        Args:
            run_id: 运行唯一标识
            progress: 各 source_a: 0.5（0.0-1.0）
            stats: {"records": N, "tutors": N, "failures": N, "requests": N}

        Returns:
            当前完整状态快照
        """
        with self._lock:
            run_state = self._runs.setdefault(run_id, {
                "run_id": run_id,
                "status": "idle",
                "progress": {},
                "stats": {"records": 0, "tutors": 0, "failures": 0, "requests": 0},
                "updated_at": datetime.now().isoformat(),
                "force": False,
                "started_at": None,
            })

            if progress is not None:
                run_state["progress"].update(progress)
            if stats is not None:
                run_state["stats"].update(stats)
            run_state["updated_at"] = datetime.now().isoformat()

            # 写盘
            self._atomic_write(
                self._output_dir / "run_state.json",
                {"runs": self._runs, "updated_at": run_state["updated_at"]}
            )

            return run_state

    def reset(self, run_id: str, force: bool = False) -> dict[str, Any]:
        """重置运行状态（强制采集开始前调用）。

        记录 force=true 和 started_at 时间。
        """
        with self._lock:
            now = datetime.now().isoformat()
            self._runs[run_id] = {
                "run_id": run_id,
                "status": "running",
                "progress": {},
                "stats": {"records": 0, "tutors": 0, "failures": 0, "requests": 0},
                "updated_at": now,
                "force": force,
                "started_at": now,
            }

            # 写盘 run_state.json
            self._atomic_write(
                self._output_dir / "run_state.json",
                {"runs": self._runs, "updated_at": now}
            )

            # 写盘 run_event.json（前端检测新一轮开始）
            self._atomic_write(
                self._output_dir / "run_event.json",
                {
                    "run_id": run_id,
                    "force": force,
                    "started_at": now,
                    "status": "running"
                }
            )

            return self._runs[run_id]

    def finish(self, run_id: str, status: str = "done") -> dict[str, Any]:
        """标记运行结束。

        Args:
            run_id: 运行唯一标识
            status: done / failed / cancelled

        事件文件（run_event.json）保留到下一次 reset 覆盖：前端在任务结束后
        仍能看到"本轮为强制采集"横幅；若在此处删除，短任务的整个可见窗口
        会被清空，轮询永远抓不到。（Console Fix R3.2）
        """
        with self._lock:
            if run_id not in self._runs:
                return {}

            self._runs[run_id]["status"] = status
            self._runs[run_id]["updated_at"] = datetime.now().isoformat()

            # 写盘
            self._atomic_write(
                self._output_dir / "run_state.json",
                {"runs": self._runs, "updated_at": self._runs[run_id]["updated_at"]}
            )

            return self._runs[run_id]

    def get_run_state(self, run_id: str) -> Optional[dict[str, Any]]:
        """获取指定运行的状态。"""
        with self._runs_lock:
            return self._runs.get(run_id)

    def list_active_runs(self) -> list[str]:
        """列出所有处于 running 状态的 run_id。"""
        with self._runs_lock:
            return [
                rid for rid, state in self._runs.items()
                if state.get("status") == "running"
            ]

    def load_history(self) -> None:
        """从磁盘加载历史状态（启动时调用）。"""
        state_path = self._output_dir / "run_state.json"
        if not state_path.exists():
            return
        try:
            data = json.loads(state_path.read_text(encoding='utf-8'))
            with self._runs_lock:
                self._runs = data.get("runs", {})
        except Exception:
            pass

    def reset_all(self) -> None:
        """重置所有运行状态（用于测试）。"""
        with self._runs_lock:
            self._runs.clear()