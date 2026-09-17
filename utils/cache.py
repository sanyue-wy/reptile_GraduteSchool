# -*- coding: utf-8 -*-
"""
采集缓存模块
============
把第一次爬取的页面（列表页 / 教师详情页）按 URL 稳定落盘到 data/cache/，
后续重跑默认读本地缓存，跳过网络请求，加快页面刷新速度。

设计要点：
- 缓存键 = 域名 + URL 路径尾段，与 utils/http.py 的原件落盘命名保持一致
- 新鲜度由 max_age_days 控制（默认 7 天），过期或 --force 时重新抓取并覆盖
- 读取失败（文件损坏等）自动回退为重新抓取
- 线程安全：写临时文件后 os.replace 原子替换；并发同 URL 靠文件锁去重
"""

import hashlib
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CACHE_DIR = Path("data/cache")


def _url_key(url: str) -> tuple[str, str]:
    """返回 (domain_dir, filename_stem)，不含扩展名。"""
    parsed = urlparse(url)
    domain = parsed.netloc.replace(":", "_") or "unknown"
    # POST API（如 SudyCMS generalQuery）用 query 串做指纹区分不同参数
    tail = parsed.path.rstrip("/").split("/")[-1] or "index"
    if parsed.query:
        qhash = hashlib.md5(parsed.query.encode("utf-8")).hexdigest()[:8]
        tail = f"{tail}_{qhash}"
    return domain, tail


class CrawlCache:
    """URL 级页面缓存，线程安全。

    统计沿用旧口径：hits 仅计成功读出的新鲜磁盘缓存（含 read_many），
    misses 计实际 fetch_fn 调用（含 force、禁用缓存和失败请求）。读探测
    未命中和复用 inflight 结果不计数，损坏文件不算命中；命中率因此不是
    所有 API 调用中的成功比例。writes 仅计成功原子替换。
    """

    def __init__(self, cache_dir: Optional[Path] = None, max_age_days: int = 7):
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.max_age_seconds = max_age_days * 86400
        self._lock = threading.Lock()
        self.stats = {"hits": 0, "misses": 0, "writes": 0}
        # 同一 URL 并发抓取去重：url -> (Event, holder_dict)
        self._inflight: dict[str, tuple[threading.Event, dict]] = {}

    # ------------------------------------------------------------------
    # 路径与新鲜度
    # ------------------------------------------------------------------

    @staticmethod
    def _ext_for(text: str) -> str:
        """按内容嗅探扩展名：JSON 响应存 .json，其余存 .html。"""
        return ".json" if text.lstrip()[:1] in ("{", "[") else ".html"

    def _path_for(self, url: str, ext: str) -> Path:
        domain, tail = _url_key(url)
        return self.cache_dir / domain / f"{tail}{ext}"

    def _find_cached(self, url: str) -> tuple[Optional[Path], bool]:
        """查找该 URL 的缓存文件。返回 (path, fresh)。"""
        domain, tail = _url_key(url)
        d = self.cache_dir / domain
        if not d.exists():
            return None, False
        for p in sorted(d.iterdir()):
            if p.name.startswith(tail) and p.suffix in (".html", ".json"):
                try:
                    fresh = time.time() - p.stat().st_mtime <= self.max_age_seconds
                except OSError:
                    fresh = False
                return p, fresh
        return None, False

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def clear(self) -> int:
        """清空当前缓存目录并返回删除的文件数。"""
        if not self.cache_dir.exists():
            return 0
        removed = 0
        with self._lock:
            paths = sorted(self.cache_dir.rglob("*"), key=lambda path: len(path.parts), reverse=True)
            for path in paths:
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                        removed += 1
                    elif path.is_dir():
                        path.rmdir()
                except OSError:
                    logger.warning("清理缓存失败: %s", path)
            try:
                self.cache_dir.rmdir()
            except OSError:
                pass
        return removed

    def _read_text_locked(self, url: str) -> Optional[str]:
        """在持锁状态下读取，仅成功读取才算命中。"""
        try:
            p, fresh = self._find_cached(url)
            if p is None or not fresh:
                return None
            text = p.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("缓存读取失败 %s: %s（将重新抓取）", url, e)
            return None
        self.stats["hits"] += 1
        return text

    def read_text(self, url: str) -> Optional[str]:
        """读缓存文本；不存在、过期或读取失败返回 None，不计 misses。"""
        with self._lock:
            return self._read_text_locked(url)

    def read_many(self, urls: list[str]) -> dict[str, Optional[str]]:
        """批量读取；每个不同 URL 读取一次，未命中值为 None。"""
        with self._lock:
            return {url: self._read_text_locked(url) for url in dict.fromkeys(urls)}

    def get_hit_rate(self) -> float:
        """成功磁盘读取 / (成功磁盘读取 + 实际 fetch 次数)，空统计为 0。"""
        with self._lock:
            total = self.stats["hits"] + self.stats["misses"]
            return self.stats["hits"] / total if total else 0.0

    def _write_locked(self, url: str, text: str) -> None:
        """调用方持锁；临时文件唯一，替换失败仍清理。"""
        tmp = None
        try:
            p = self._path_for(url, self._ext_for(text))
            p.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=p.name + ".", suffix=".tmp", dir=p.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.replace(tmp, p)
            self.stats["writes"] += 1
            logger.debug("已写入缓存: %s", p)
        except Exception as e:
            logger.warning("缓存写入失败 %s: %s", url, e)
        finally:
            if tmp is not None:
                try:
                    os.unlink(tmp)
                except FileNotFoundError:
                    pass
                except OSError as e:
                    logger.warning("缓存临时文件清理失败 %s: %s", tmp, e)

    def write(self, url: str, text: str) -> None:
        """写缓存（原子替换），扩展名按内容嗅探。"""
        with self._lock:
            self._write_locked(url, text)

    def get_or_fetch(
        self,
        fetch_fn,
        url: str,
        force: bool = False,
        use_cache: bool = True,
    ) -> str:
        """
        带缓存的请求入口：命中且新鲜则直接返回文本，否则调用 fetch_fn() 抓取并写缓存。

        Args:
            fetch_fn: 无参可调用对象，执行一次真实网络请求并返回响应文本
            url: 请求 URL（用作缓存键）
            force: True 时忽略缓存强制抓取
            use_cache: False 时完全不读不写缓存
        """
        while True:
            with self._lock:
                # 查询缓存和登记 owner 是同一个临界区，避免前一 owner 刚写完
                # 并退出后，本线程带着过时的 miss 再次请求。
                if use_cache and not force:
                    text = self._read_text_locked(url)
                    if text is not None:
                        logger.info("【缓存命中】%s", url)
                        return text
                entry = self._inflight.get(url)
                if entry is None:
                    entry = (threading.Event(), {})
                    self._inflight[url] = entry
                    self.stats["misses"] += 1
                    break

            ev, holder = entry
            completed = ev.wait(timeout=300)
            with self._lock:
                if "text" in holder:
                    return holder["text"]
                # 失败/超时后仅淘汰自己等待的代。多个 waiter 回到循环后，
                # 只会有一个成为新 owner，其余跟随新代。
                if self._inflight.get(url) is entry:
                    del self._inflight[url]
            logger.warning("等待 %s 的在途请求%s，重新检查缓存", url,
                           "失败" if completed else "超时")

        ev, holder = entry
        try:
            logger.info("【缓存未命中】抓取 %s", url)
            text = fetch_fn()
            with self._lock:
                # 过时代 owner 可返回自己的结果，但不能覆盖新代已写入的缓存。
                if use_cache and self._inflight.get(url) is entry:
                    self._write_locked(url, text)
                holder["text"] = text
            return text
        except BaseException:
            with self._lock:
                holder["error"] = True
            raise
        finally:
            with self._lock:
                ev.set()
                if self._inflight.get(url) is entry:
                    del self._inflight[url]
