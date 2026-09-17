# -*- coding: utf-8 -*-
"""
礼貌 HTTP 请求封装
===================
唯一网络出口，所有模块必须通过 PoliteSession 发请求。
保证：限速、User-Agent 轮换、重试、原件落盘、日志。
"""

import logging
import random
import re
import socket
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)


def response_text(resp: "requests.Response") -> str:
    """按正确编码取响应文本，避免中文页面被 ISO-8859-1 默认解码产生乱码。

    requests 对无 charset 声明的 text/html 响应默认按 ISO-8859-1 解码，
    而国内高校站点普遍是 UTF-8（meta 声明或实际字节），直接取 resp.text
    会把中文变乱码。策略：header 显式声明 > meta charset > apparent_encoding。
    """
    ct = resp.headers.get("Content-Type", "")
    if "html" in ct.lower():
        # header 显式声明的编码可信；requests 未声明时 text/html 会默认 ISO-8859-1，不可信
        if "charset=" in ct.lower() and resp.encoding:
            return resp.text
        head = resp.content[:4096]
        m = re.search(rb'charset=["\']?([\w-]+)', head, re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
            try:
                return resp.content.decode(enc)
            except (LookupError, UnicodeDecodeError):
                pass
        if isinstance(resp.apparent_encoding, str):
            try:
                return resp.content.decode(resp.apparent_encoding)
            except (LookupError, UnicodeDecodeError):
                pass
    return resp.text

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
        circuit_threshold: int = 5,
        circuit_window: float = 3600,
        timeout: float = 30,
    ):
        """
        Args:
            delay_range: 请求间随机延迟区间（秒）
            max_retries: 最大重试次数（指数退避）
            raw_dir: 原件落盘根目录（None 则不落盘）
            cooldown_threshold: 连续 403/429 达到此数触发冷却
            cooldown_seconds: 保留的冷却参数；标记后须手动解除，不长时间 sleep
            circuit_threshold: 同域名、同因失败次数阈值（按实际 HTTP 尝试计数）
            circuit_window: 同因失败的滑动时间窗口（秒）
            timeout: 默认请求超时（可由单次请求的 timeout 覆盖）
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

        # 同一个锁保护所有冷却、熔断及统计状态；不在网络等待期间持锁。
        self._state_lock = threading.RLock()
        self._block_counts: dict[str, int] = {}
        self._blocked_domains: set[str] = set()
        self._circuit_history: dict[tuple[str, str], list[float]] = {}
        self._circuit_tripped: set[str] = set()
        self._circuit_threshold = circuit_threshold
        self._circuit_window = circuit_window
        self.timeout = timeout

        # requests 为逻辑调用数，success/failed 为调用结果，重试不重复计数。
        self.stats = {"requests": 0, "success": 0, "failed": 0, "raw_saved": 0}

    def close(self):
        """Release the underlying connection pools after a batch finishes."""
        self._session.close()

    def _increment_stat(self, name: str):
        with self._state_lock:
            self.stats[name] += 1

    def is_blocked(self, domain: Optional[str] = None) -> bool:
        """查询冷却或熔断；None 表示任意域名。"""
        with self._state_lock:
            if domain is None:
                return bool(self._blocked_domains or self._circuit_tripped)
            return domain in self._blocked_domains or domain in self._circuit_tripped

    def get_block_count(self, domain: Optional[str] = None) -> int:
        """查询连续 403/429 尝试次数；None 返回所有域名之和。"""
        with self._state_lock:
            if domain is None:
                return sum(self._block_counts.values())
            return self._block_counts.get(domain, 0)

    @property
    def _block_count(self) -> int:
        """旧私有计数的汇总视图，生产代码使用按域接口。"""
        return self.get_block_count()

    @_block_count.setter
    def _block_count(self, value):
        # 兼容旧单域调用者；无法确定所属域名时不能改写全局计数。
        with self._state_lock:
            domains = set(self._block_counts) | self._blocked_domains
            if len(domains) != 1:
                raise AttributeError("请使用按域名冷却接口，不能写入全局计数")
            self._block_counts[next(iter(domains))] = value

    @property
    def tripped_domains(self) -> set[str]:
        """返回冷却/熔断域名的独立快照。"""
        with self._state_lock:
            return self._blocked_domains | self._circuit_tripped

    def _record_failure(self, domain: str, error_class: str,
                        window_size: Optional[int] = None) -> bool:
        """唯一熔断记录入口；兼容适配器也使用此状态。"""
        with self._state_lock:
            if domain in self._circuit_tripped:
                return True
            if error_class == "dns_error":
                self._circuit_tripped.add(domain)
                logger.warning("DNS 错误快速熔断: domain=%s", domain)
                return True
            now = time.time()
            key = (domain, error_class)
            history = [t for t in self._circuit_history.get(key, [])
                       if t > now - self._circuit_window]
            history.append(now)
            if window_size is not None and len(history) > window_size:
                history = history[-window_size:]
            self._circuit_history[key] = history
            if len(history) >= self._circuit_threshold:
                self._circuit_tripped.add(domain)
                logger.warning("同因熔断: domain=%s error_class=%s", domain, error_class)
                return True
            return False

    def reset_circuit(self, domain: str):
        """仅解除目标域名的同因熔断和历史，不解除反爬冷却。"""
        with self._state_lock:
            self._circuit_tripped.discard(domain)
            for key in [key for key in self._circuit_history if key[0] == domain]:
                del self._circuit_history[key]

    @staticmethod
    def _is_dns_error(error: Exception) -> bool:
        # requests/urllib3 可能把 DNS 异常封装在 cause、reason 或 args 中。
        pending = [error]
        seen = set()
        while pending:
            exc = pending.pop()
            if id(exc) in seen:
                continue
            seen.add(id(exc))
            if isinstance(exc, socket.gaierror):
                return True
            text = str(exc).lower()
            if any(marker in text for marker in (
                "getaddrinfo", "name or service not known", "nameresolutionerror",
                "temporary failure in name resolution", "nodename nor servname",
                "failed to resolve",
            )):
                return True
            pending.extend(item for item in (
                exc.__cause__, exc.__context__, getattr(exc, "reason", None), *exc.args
            ) if isinstance(item, BaseException))
        return False

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
        # 冷却/熔断检查；已挂起的调用不计入实际请求数。
        domain = urlparse(url).netloc
        if self.is_blocked(domain):
            raise BlockedError(f"域名 {domain} 已被冷却或熔断，请手动解除")

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

        timeout = kwargs.pop("timeout", self.timeout)
        self._increment_stat("requests")

        for attempt in range(self.max_retries + 1):
            # 其他线程可在本线程限速/退避时触发熔断，重试前再次检查。
            if self.is_blocked(domain):
                self._increment_stat("failed")
                raise BlockedError(f"域名 {domain} 已被冷却或熔断，请手动解除")
            try:
                resp = self._session.request(
                    method, url,
                    params=params, data=data, json=json,
                    headers=headers, timeout=timeout,
                    **kwargs,
                )

                # 反爬计数只影响当前域名；同因熔断复用同一会话状态。
                if resp.status_code in (403, 429):
                    with self._state_lock:
                        count = self._block_counts.get(domain, 0) + 1
                        self._block_counts[domain] = count
                        if count >= self.cooldown_threshold:
                            self._blocked_domains.add(domain)
                        self._record_failure(domain, "blocked")
                        blocked = self.is_blocked(domain)
                    if blocked:
                        self._increment_stat("failed")
                        logger.warning("域名 %s 触发冷却或熔断，停止请求", domain)
                        raise BlockedError(f"域名 {domain} 触发冷却或熔断")
                    if attempt < self.max_retries:
                        backoff = (2 ** attempt) * random.uniform(1, 3)
                        logger.warning(
                            "HTTP %d for %s，第 %d 次重试，等待 %.1fs",
                            resp.status_code, url, attempt + 1, backoff,
                        )
                        time.sleep(backoff)
                    continue

                resp.raise_for_status()
                with self._state_lock:
                    self._block_counts.pop(domain, None)
                    # 窗口内累计失败不因穿插成功而清空；已触发状态须显式解除，
                    # 避免稍晚返回的并发成功请求意外解开其他请求触发的熔断。
                    self.stats["success"] += 1

                # 原件落盘
                if save_raw and self.raw_dir:
                    self._save_raw(url, resp)

                return resp

            except (requests.ConnectionError, requests.Timeout) as e:
                is_dns = self._is_dns_error(e)
                error_class = ("dns_error" if is_dns else
                               "timeout" if isinstance(e, requests.Timeout) else
                               "connection_error")
                tripped = self._record_failure(domain, error_class)
                # 当前调用保留原始 requests 异常；后续调用才抛 BlockedError。
                if is_dns or tripped or attempt >= self.max_retries:
                    self._increment_stat("failed")
                    raise
                backoff = (2 ** attempt) * random.uniform(1, 3)
                logger.warning("连接失败 %s，%d 次重试，等待 %.1fs: %s",
                               url, attempt + 1, backoff, e)
                time.sleep(backoff)
            except requests.HTTPError:
                self._record_failure(domain, "http_error")
                self._increment_stat("failed")
                raise

        self._increment_stat("failed")
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
                text = response_text(resp)[:200].strip()
                if text.startswith("{") or text.startswith("["):
                    ext = ".json"

            dest_dir = Path(self.raw_dir) / domain
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"{fname}{ext}"

            if ext in (".json", ".html"):
                dest.write_text(response_text(resp), encoding="utf-8")
            else:
                dest.write_bytes(resp.content)

            self._increment_stat("raw_saved")
            logger.debug("原件已落盘: %s", dest)
        except Exception as e:
            logger.warning("原件落盘失败 %s: %s", url, e)

    def clear_cooldown(self, domain: str):
        """仅解除目标域名的反爬冷却和计数，不解除同因熔断。"""
        with self._state_lock:
            self._blocked_domains.discard(domain)
            self._block_counts.pop(domain, None)


class CircuitBreaker:
    """旧接口适配器；所有状态均由 PoliteSession 持有。

    旧独立用法仍可 CircuitBreaker(threshold=5, window_size=100)。如需查询
    现有会话，传 session=session；threshold 以该会话配置为准。生产 CLI/API
    应直接使用会话，不能再次 record 已由 HTTP 层计入的失败。
    window_size 保留旧语义（记录条数上限），不是时间窗口秒数。
    """

    def __init__(self, threshold: int = 5, window_size: int = 100,
                 *, session: Optional[PoliteSession] = None):
        self._session = session if session is not None else PoliteSession(
            circuit_threshold=threshold)
        self.window_size = window_size

    @property
    def threshold(self) -> int:
        with self._session._state_lock:
            return self._session._circuit_threshold

    @threshold.setter
    def threshold(self, value: int):
        with self._session._state_lock:
            self._session._circuit_threshold = value

    def record(self, domain: str, error_class: str) -> bool:
        return self._session._record_failure(domain, error_class, self.window_size)

    def is_tripped(self, domain: str) -> bool:
        return self._session.is_blocked(domain)

    def reset(self, domain: str):
        self._session.reset_circuit(domain)

    @property
    def tripped_domains(self) -> set[str]:
        return self._session.tripped_domains


# ------------------------------------------------------------------
# 异常
# ------------------------------------------------------------------

class BlockedError(Exception):
    """域名被反爬冷却时抛出。"""


class MaxRetriesExceeded(Exception):
    """达到最大重试次数时抛出。"""
