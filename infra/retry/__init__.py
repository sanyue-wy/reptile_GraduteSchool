# -*- coding: utf-8 -*-
"""
自适应超时模块（V3.0）
=====================

域名维度的响应时间记录与 P95 超时计算。
"""

from infra.retry.adaptive_timeout import AdaptiveTimeoutPolicy

__all__ = ["AdaptiveTimeoutPolicy"]
