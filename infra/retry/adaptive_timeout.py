# -*- coding: utf-8 -*-
"""
自适应超时策略（V3.0）
=====================

按域名记录历史响应时间，计算 P95 作为基础超时值。
超时值被 clamp 到 [15s, 120s] 区间。
"""

import threading
from collections import defaultdict
from pathlib import Path
from typing import Optional


class AdaptiveTimeoutPolicy:
    """域名维度的自适应超时策略。

    使用滑动窗口记录最近的 N 次响应时间，计算 P95 作为新请求的
    超时阈值。每次请求后调用 record() 更新历史。

    超时值 clamp 到 [15s, 120s]：
    - 15s：过低会过早触发 DNS/连接超时
    - 120s：过高会卡住任务总量预算
    """

    DEFAULT_MIN_TIMEOUT: float = 15.0
    DEFAULT_MAX_TIMEOUT: float = 120.0
    DEFAULT_HISTORY_SIZE: int = 20  # 最近 N 次响应时间用于计算 P95

    def __init__(
        self,
        history_size: int = DEFAULT_HISTORY_SIZE,
        min_timeout: float = DEFAULT_MIN_TIMEOUT,
        max_timeout: float = DEFAULT_MAX_TIMEOUT,
        history_path: Optional[Path] = None,
    ):
        self.history_size = history_size
        self.min_timeout = min_timeout
        self.max_timeout = max_timeout
        self._history_path = history_path
        self._lock = threading.Lock()
        self._history: dict[str, list[float]] = defaultdict(list)

    def get_timeout(self, domain: str) -> float:
        """获取给定域名的自适应超时值（秒）。

        如果历史记录不足，返回 min_timeout。
        基于 P95 计算，结果 clamp 到 [min_timeout, max_timeout]。
        """
        with self._lock:
            history = self._history.get(domain, [])
            if len(history) < 3:
                return self.min_timeout
            # 计算 P95
            sorted_times = sorted(history)
            p95_index = int(len(sorted_times) * 0.95)
            p95 = sorted_times[min(p95_index, len(sorted_times) - 1)]
            return max(self.min_timeout, min(self.max_timeout, p95))

    def record(self, domain: str, elapsed: float) -> None:
        """记录一次请求的响应时间（秒）。

        维护滑动窗口，最多保留 history_size 条记录。
        """
        with self._lock:
            self._history[domain].append(elapsed)
            # 滑动窗口：只保留最近 history_size 条
            if len(self._history[domain]) > self.history_size:
                self._history[domain] = self._history[domain][-self.history_size :]
        if self._history_path:
            self._save_history()

    def _save_history(self) -> None:
        """持久化历史记录到磁盘（可选）。"""
        if not self._history_path:
            return
        try:
            import json
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._history_path, "w", encoding="utf-8") as f:
                json.dump(
                    {k: v for k, v in dict(self._history).items() if v},
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass  # 持久化失败不阻塞主流程

    def load_history(self) -> None:
        """从磁盘加载历史记录（可选）。"""
        if not self._history_path or not self._history_path.exists():
            return
        try:
            import json
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            with self._lock:
                for domain, times in data.items():
                    self._history[domain] = list(times)[-self.history_size :]
        except Exception:
            pass

    def reset(self) -> None:
        """重置所有域名的历史记录。"""
        with self._lock:
            self._history.clear()
        if self._history_path and self._history_path.exists():
            try:
                self._history_path.unlink()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 便捷函数（模块级单例）
    # ------------------------------------------------------------------

    _default_policy: Optional["AdaptiveTimeoutPolicy"] = None
    _default_lock = threading.Lock()

    @classmethod
    def get_default(cls) -> "AdaptiveTimeoutPolicy":
        """获取全局默认策略单例。"""
        if cls._default_policy is None:
            with cls._default_lock:
                if cls._default_policy is None:
                    cache_dir = Path("data") / "cache" / "timeout_history.json"
                    cls._default_policy = cls(history_path=cache_dir)
                    cls._default_policy.load_history()
        return cls._default_policy

    @classmethod
    def reset_default(cls) -> None:
        """重置默认策略单例。"""
        with cls._default_lock:
            if cls._default_policy is not None:
                cls._default_policy.reset()
            cls._default_policy = None
