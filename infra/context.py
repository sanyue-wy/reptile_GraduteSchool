# -*- coding: utf-8 -*-
"""
PipelineContext（V3.0 受管上下文）
==================================
对 plugins.base.PluginContext 的引擎侧构造与生命周期管理：

- 每任务独立 HTTP 会话（PoliteSession 委托，不复制熔断逻辑）
- 共享 CrawlCache / ProgressTracker（实例本身带锁，显式复用同一实例）
- 取消令牌、允许路径集合、只读配置快照、registry_revision、task/run 标识
- setup 失败 / execute 异常 / 取消均在 finally 关闭已创建资源
"""

import logging
import threading
from pathlib import Path
from typing import Any, Optional

from plugins.base import PluginContext
from utils.cache import CrawlCache
from utils.http import PoliteSession


class PipelineContextManager:
    """为单个 pipeline 运行创建并回收任务级上下文。

    用法::

        with PipelineContextManager(run_id, data_root) as manager:
            context = manager.build_context(task_config)
            try:
                plugin.setup(context)
                result = plugin.execute(data, context)
            finally:
                manager.release_context(context)

    跨任务的限速/缓存/按域熔断共享状态通过传入同一个 PoliteSession 工厂
    结果或同一个 CrawlCache 实例实现；本管理器不新建第二套熔断器。
    """

    def __init__(
        self,
        run_id: str,
        data_root: Optional[Path] = None,
        *,
        shared_session_factory=None,
        cache: Optional[CrawlCache] = None,
        progress: Any = None,
        registry_revision: int = 1,
        allowed_paths: Optional[list[str]] = None,
        logger: Optional[logging.Logger] = None,
        session_kwargs: Optional[dict[str, Any]] = None,
    ):
        self.run_id = run_id
        self.data_root = Path(data_root) if data_root else Path("data")
        self._shared_session_factory = shared_session_factory
        self._cache = cache
        self._progress = progress
        self._registry_revision = registry_revision
        self._allowed_paths_extra = list(allowed_paths or [])
        self.logger = logger or logging.getLogger("pipeline")
        self._session_kwargs = dict(session_kwargs or {})
        self._cancel_token = threading.Event()
        self._active: dict[str, _ActiveTask] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 取消
    # ------------------------------------------------------------------

    @property
    def cancel_token(self) -> threading.Event:
        return self._cancel_token

    def request_cancel(self) -> None:
        """请求取消：停止派发并在安全检查点退出（不强杀线程）。"""
        self._cancel_token.set()

    def is_cancelled(self) -> bool:
        return self._cancel_token.is_set()

    # ------------------------------------------------------------------
    # 上下文构造
    # ------------------------------------------------------------------

    def build_context(
        self,
        task_config: Any,
        *,
        config_snapshot: Optional[dict[str, Any]] = None,
        extra_allowed_paths: Optional[list[str]] = None,
    ) -> PluginContext:
        """为一次插件调用构造独立上下文（独立 HTTP 会话 + 独立插件实例由调用方保证）。"""
        raw_dir = self.data_root / "raw" / (task_config.task_id or "unknown")
        kwargs = dict(self._session_kwargs)
        kwargs.setdefault("raw_dir", str(raw_dir))
        if self._shared_session_factory is not None:
            http = self._shared_session_factory()
        else:
            http = PoliteSession(**kwargs)

        if self._cache is None:
            self._cache = CrawlCache(cache_dir=self.data_root / "cache")
        if self._progress is None:
            from utils.progress import get_progress_tracker
            self._progress = get_progress_tracker()

        allowed = [
            str((self.data_root / p).resolve())
            for p in ("raw", "cache", "output", f"runs/{self.run_id}")
        ] + self._allowed_paths_extra + list(extra_allowed_paths or [])

        snapshot = dict(config_snapshot if config_snapshot is not None
                        else getattr(task_config, "config_snapshot", {}) or {})
        snapshot.setdefault("task_id", getattr(task_config, "task_id", ""))
        snapshot.setdefault("run_id", self.run_id)
        snapshot.setdefault("data_root", str(self.data_root))

        active = _ActiveTask(http=http)
        with self._lock:
            self._active[getattr(task_config, "task_id", "") or str(len(self._active))] = active

        return PluginContext(
            http=http,
            cache=self._cache,
            progress=self._progress,
            storage=None,  # 存储句柄由 store 阶段经 workspace 提供
            logger=self.logger,
            allowed_paths=allowed,
            cancel_token=self._cancel_token,
            config_snapshot=snapshot,
            registry_revision=self._registry_revision,
            task_id=getattr(task_config, "task_id", ""),
            run_id=self.run_id,
        )

    def release_context(self, context: PluginContext) -> None:
        """finally 中调用：关闭该上下文的 HTTP 会话等资源。幂等。"""
        if context.http is None:
            return
        key = getattr(context, "task_id", "")
        with self._lock:
            active = self._active.pop(key, None)
        if active is not None and active.http is context.http and not active.closed:
            active.close()

    # ------------------------------------------------------------------
    # 运行期生命周期
    # ------------------------------------------------------------------

    def __enter__(self) -> "PipelineContextManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.shutdown()

    def shutdown(self) -> None:
        """关闭全部仍活跃的 HTTP 会话。"""
        with self._lock:
            actives = list(self._active.values())
            self._active.clear()
        for active in actives:
            if not active.closed:
                active.close()


class _ActiveTask:
    """登记一个任务级 HTTP 会话，保证 close 恰好一次。"""

    def __init__(self, http: PoliteSession):
        self.http = http
        self.closed = False

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            self.http.close()
        except Exception:
            pass
