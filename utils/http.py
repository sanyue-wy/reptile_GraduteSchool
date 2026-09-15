# -*- coding: utf-8 -*-
"""
礼貌 HTTP 请求封装
===================
唯一网络出口，所有模块必须通过 PoliteSession 发请求。
保证：限速、User-Agent 轮换、重试、原件落盘、日志。
"""

import json
import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

# 常规桌面 Chrome UA 池
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


class PoliteSession:
    """带限速、重试、UA 轮换、原件落盘的 HTTP 会话。"""

    def __init__(
        self,
        delay_range: tuple[float, float] = (1.0, 3.0),
        max_retries: int = 3,
        raw_dir: Optional[str] = None,
        cooldown_threshold: int = 5,
        cooldown_seconds: int = 1800,
    ):
        """
        Args:
            delay_range: 请求间随机延迟区间（秒）
            max_retries: 最大重试次数（指数退避）
            raw_dir: 原件落盘根目录（None 则不落盘）
            cooldown_threshold: 连续 403/429 达到此数触发冷却
            cooldown_seconds: 冷却等待秒数
        """
        self.delay_range = delay_range
        self.max_retries = max_retries
        self.raw_dir = raw_dir
        self.cooldown_threshold = cooldown_threshold
        self.cooldown_seconds = cooldown_seconds

        # 构建 requests Session（HTTPAdapter 不再内置重试，由 _request() 统一控制）
        self._session = requests.Session()
        adapter = HTTPAdapter()
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

        # 反爬冷却计数
        self._block_count = 0
        self._blocked_domains: set[str] = set()

        # 统计
        self.stats = {"requests": 0, "success": 0, "failed": 0, "raw_saved": 0}

    # ------------------------------------------------------------------
    # 核心请求
    # ------------------------------------------------------------------

    def get(
        self,
        url: str,
        params: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
        save_raw: bool = True,
        **kwargs,
    ) -> requests.Response:
        return self._request("GET", url, params=params, extra_headers=extra_headers,
                             save_raw=save_raw, **kwargs)

    def post(
        self,
        url: str,
        data: Optional[dict] = None,
        json_data: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
        save_raw: bool = True,
        **kwargs,
    ) -> requests.Response:
        return self._request("POST", url, data=data, json=json_data,
                             extra_headers=extra_headers, save_raw=save_raw, **kwargs)

    def post_json(
        self,
        url: str,
        data: Optional[dict] = None,
        extra_headers: Optional[dict] = None,
        save_raw: bool = True,
        **kwargs,
    ) -> dict:
        """POST 并返回 JSON。"""
        resp = self.post(url, data=data, extra_headers=extra_headers,
                         save_raw=save_raw, **kwargs)
        return resp.json()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        params=None,
        data=None,
        json=None,
        extra_headers=None,
        save_raw: bool = True,
        **kwargs,
    ) -> requests.Response:
        # 冷却检查
        domain = urlparse(url).netloc
        if domain in self._blocked_domains:
            raise BlockedError(f"域名 {domain} 已被冷却，请等待或手动解除")

        # 限速
        self._sleep()

        # 构造 headers
        headers = {
            "User-Agent": random.choice(_USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if extra_headers:
            headers.update(extra_headers)

        self.stats["requests"] += 1

        for attempt in range(self.max_retries + 1):
            try:
                resp = self._session.request(
                    method, url,
                    params=params, data=data, json=json,
                    headers=headers, timeout=30,
                    **kwargs,
                )

                # 反爬检测
                if resp.status_code in (403, 429):
                    self._block_count += 1
                    if self._block_count >= self.cooldown_threshold:
                        self._blocked_domains.add(domain)
                        logger.warning(
                            "域名 %s 连续触发 %d 次反爬，冷却 %d 秒",
                            domain, self._block_count, self.cooldown_seconds,
                        )
                        raise BlockedError(f"域名 {domain} 触发冷却")
                    backoff = (2 ** attempt) * random.uniform(1, 3)
                    logger.warning(
                        "HTTP %d for %s，第 %d 次重试，等待 %.1fs",
                        resp.status_code, url, attempt + 1, backoff,
                    )
                    time.sleep(backoff)
                    continue

                resp.raise_for_status()
                self._block_count = 0  # 成功则重置
                self.stats["success"] += 1

                # 原件落盘
                if save_raw and self.raw_dir:
                    self._save_raw(url, resp)

                return resp

            except (requests.ConnectionError, requests.Timeout) as e:
                # DNS 解析失败是确定性错误，重试无意义
                err_str = str(e).lower()
                is_dns = ("getaddrinfo" in err_str
                          or "name or service not known" in err_str
                          or "nameresolutionerror" in err_str)
                if is_dns:
                    self.stats["failed"] += 1
                    raise

                if attempt < self.max_retries:
                    backoff = (2 ** attempt) * random.uniform(1, 3)
                    logger.warning("连接失败 %s，%d 次重试，等待 %.1fs: %s",
                                   url, attempt + 1, backoff, e)
                    time.sleep(backoff)
                else:
                    self.stats["failed"] += 1
                    raise

        self.stats["failed"] += 1
        raise MaxRetriesExceeded(f"请求 {url} 达到最大重试次数")

    def _sleep(self):
        delay = random.uniform(*self.delay_range)
        time.sleep(delay)

    def _save_raw(self, url: str, resp: requests.Response):
        """把响应原件落盘到 raw_dir/<domain>/<timestamp>_<hash>.html。"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace(":", "_")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            # 用 URL 的尾部路径做文件名，避免太长
            tail = parsed.path.rstrip("/").split("/")[-1] or "index"
            fname = f"{ts}_{tail}"
            # 判断内容类型
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct:
                ext = ".json"
            elif "pdf" in ct:
                ext = ".pdf"
            elif "excel" in ct or "spreadsheet" in ct:
                ext = ".xlsx"
            else:
                ext = ".html"
                # JSON 响应可能没标 Content-Type
                text = resp.text[:200].strip()
                if text.startswith("{") or text.startswith("["):
                    ext = ".json"

            dest_dir = Path(self.raw_dir) / domain
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{fname}{ext}"

            if ext in (".json", ".html"):
                dest.write_text(resp.text, encoding="utf-8")
            else:
                dest.write_bytes(resp.content)

            self.stats["raw_saved"] += 1
            logger.debug("原件已落盘: %s", dest)
        except Exception as e:
            logger.warning("原件落盘失败 %s: %s", url, e)

    def clear_cooldown(self, domain: str):
        """手动解除域名冷却。"""
        self._blocked_domains.discard(domain)
        self._block_count = 0


# ------------------------------------------------------------------
# 异常
# ------------------------------------------------------------------

class BlockedError(Exception):
    """域名被反爬冷却时抛出。"""


class MaxRetriesExceeded(Exception):
    """达到最大重试次数时抛出。"""
