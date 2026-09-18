# -*- coding: utf-8 -*-
"""
受管缓存包装（V3.0）
====================
对 utils.cache.CrawlCache 的委托式包装：复用同一实例的锁、命中统计与
在途去重语义，不另建第二套缓存状态。新增能力仅为：

- 取消检查点（读/取之前检查令牌）
- 命中率快照（供 RunResult 观测）
"""

import threading
from typing import Callable, Optional

from utils.cache import CrawlCache


class ManagedCrawlCache:
    """CrawlCache 的受管视图。"""

    def __init__(self, cache: CrawlCache, cancel_token: Optional[threading.Event] = None):
        self._cache = cache
        self._cancel_token = cancel_token

    @property
    def cache(self) -> CrawlCache:
        return self._cache

    def _check_cancelled(self) -> None:
        if self._cancel_token is not None and self._cancel_token.is_set():
            raise RuntimeError("pipeline cancelled during cache access")

    def read_text(self, url: str) -> Optional[str]:
        self._check_cancelled()
        return self._cache.read_text(url)

    def read_many(self, urls: list[str]) -> dict[str, Optional[str]]:
        self._check_cancelled()
        return self._cache.read_many(urls)

    def write(self, url: str, text: str) -> None:
        self._cache.write(url, text)

    def get_or_fetch(self, fetch_fn: Callable[[], str], url: str,
                     force: bool = False, use_cache: bool = True) -> str:
        self._check_cancelled()
        return self._cache.get_or_fetch(fetch_fn, url, force=force, use_cache=use_cache)

    def clear(self) -> int:
        return self._cache.clear()

    def hit_rate(self) -> float:
        return self._cache.get_hit_rate()

    @property
    def stats(self) -> dict[str, int]:
        with self._cache._lock:
            return dict(self._cache.stats)
