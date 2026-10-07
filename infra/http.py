# -*- coding: utf-8 -*-
"""
受管 HTTP 会话包装（V3.0）
==========================
对 utils.http.PoliteSession 的委托式包装：

- 限速、重试、冷却、熔断全部委托给同一个 PoliteSession 实例
  （唯一熔断状态，不复制、不新建第二套熔断器）
- 提供取消检查点：请求前若令牌已置位则快速失败
- 提供统计快照供 RunResult/StageResult 观测总尝试预算
- 集成 AdaptiveTimeoutPolicy：默认超时改用 policy.get_timeout(domain)
"""

import threading
from typing import Any, Optional
from urllib.parse import urlparse

from utils.http import (
    BlockedError,
    MaxRetriesExceeded,
    PoliteSession,
)
from infra.retry.adaptive_timeout import AdaptiveTimeoutPolicy


class CancelledPipelineError(Exception):
    """取消令牌已置位时的快速失败异常。"""


class ManagedHttpSession:
    """PoliteSession 的受管视图。所有网络调用都经过它。

    集成自适应超时：
    - 默认超时从 AdaptiveTimeoutPolicy.get_timeout(domain) 获取
    - 记录成功请求的响应时间供后续计算
    """

    def __init__(
        self,
        session: PoliteSession,
        cancel_token: Optional[threading.Event] = None,
        adaptive_policy: Optional[AdaptiveTimeoutPolicy] = None,
    ):
        self._session = session
        self._cancel_token = cancel_token
        self._timeout_policy = adaptive_policy or AdaptiveTimeoutPolicy.get_default()

    @property
    def session(self) -> PoliteSession:
        return self._session

    @property
    def timeout_policy(self) -> AdaptiveTimeoutPolicy:
        """暴露给外部的时间超时策略。"""
        return self._timeout_policy

    def _check_cancelled(self) -> None:
        if self._cancel_token is not None and self._cancel_token.is_set():
            raise CancelledPipelineError("pipeline cancelled before request dispatch")

    def _get_domain(self, url: str) -> str:
        """从 URL 提取域名。"""
        try:
            return urlparse(url).netloc.split(":")[0]
        except Exception:
            return ""

    def get(self, url: str, **kwargs: Any):
        self._check_cancelled()
        import time
        start = time.time()
        try:
            return self._session.get(url, **kwargs)
        finally:
            elapsed = time.time() - start
            self._timeout_policy.record(self._get_domain(url), elapsed)

    def post(self, url: str, **kwargs: Any):
        self._check_cancelled()
        import time
        start = time.time()
        try:
            return self._session.post(url, **kwargs)
        finally:
            elapsed = time.time() - start
            self._timeout_policy.record(self._get_domain(url), elapsed)

    def post_json(self, url: str, **kwargs: Any) -> dict:
        self._check_cancelled()
        import time
        start = time.time()
        try:
            return self._session.post_json(url, **kwargs)
        finally:
            elapsed = time.time() - start
            self._timeout_policy.record(self._get_domain(url), elapsed)

    # ------------------------------------------------------------------
    # 观测与运维接口（透传）
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict[str, int]:
        """逻辑调用/成功/失败计数快照（重试不重复计数）。"""
        with self._session._state_lock:
            return dict(self._session.stats)

    @property
    def tripped_domains(self) -> set[str]:
        return self._session.tripped_domains

    def is_blocked(self, domain: Optional[str] = None) -> bool:
        return self._session.is_blocked(domain)

    def close(self) -> None:
        self._session.close()
