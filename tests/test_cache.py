# -*- coding: utf-8 -*-
"""
CrawlCache 单元测试
"""

import json
import time
import threading
from pathlib import Path

import pytest

from utils.cache import CrawlCache


class TestCrawlCache:
    """CrawlCache 单测"""

    def test_init(self, tmp_dir):
        """初始化"""
        cache = CrawlCache(cache_dir=tmp_dir / "cache", max_age_days=7)
        assert cache.cache_dir == tmp_dir / "cache"
        assert cache.max_age_seconds == 7 * 86400
        assert cache.stats == {"hits": 0, "misses": 0, "writes": 0}

    def test_ext_for_json(self, mock_cache):
        """JSON 内容嗅探为 .json 扩展名"""
        assert mock_cache._ext_for('{"key": "value"}') == ".json"
        assert mock_cache._ext_for('[1, 2, 3]') == ".json"

    def test_ext_for_html(self, mock_cache):
        """HTML 内容嗅探为 .html 扩展名"""
        assert mock_cache._ext_for("<html>") == ".html"
        assert mock_cache._ext_for("<!DOCTYPE html>") == ".html"

    def test_cache_miss(self, mock_cache):
        """缓存未命中返回 None"""
        url = "http://test.edu.cn/page"
        result = mock_cache.read_text(url)
        assert result is None
        assert mock_cache.stats["misses"] == 0  # read_text doesn't increment misses

    def test_cache_hit(self, mock_cache):
        """缓存命中返回原始内容"""
        url = "http://test.edu.cn/page"
        content = "<html><body>cached content</body></html>"
        mock_cache.write(url, content)

        result = mock_cache.read_text(url)
        assert result == content

    def test_cache_expired(self, tmp_dir):
        """过期缓存视为 miss"""
        import os
        import time
        cache = CrawlCache(cache_dir=tmp_dir / "cache", max_age_days=0)
        url = "http://test.edu.cn/page"
        cache.write(url, "<html>old</html>")

        # 设置 mtime 为过去时间，确保过期
        for p in (cache.cache_dir / "test.edu.cn").glob("*"):
            os.utime(p, (time.time() - 100, time.time() - 100))

        result = cache.read_text(url)
        assert result is None

    def test_inflight_dedup(self, mock_cache):
        """并发相同 URL 只发出一次请求"""
        url = "http://test.edu.cn/page"
        call_count = [0]
        result_holder = []

        def fetch_fn():
            call_count[0] += 1
            time.sleep(0.1)  # 模拟网络延迟
            return "content"

        def worker():
            text = mock_cache.get_or_fetch(fetch_fn, url)
            result_holder.append(text)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert call_count[0] == 1  # 只调用一次
        assert all(r == "content" for r in result_holder)
        assert len(result_holder) == 5

    def test_thread_safety(self, mock_cache):
        """多线程并发写入无数据损坏"""
        url = "http://test.edu.cn/page"
        errors = []

        def write_worker(i):
            try:
                content = f"content-{i}"
                mock_cache.write(url, content)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=write_worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_get_or_fetch_cache_hit(self, mock_cache):
        """缓存命中时不调用 fetch_fn"""
        url = "http://test.edu.cn/page"
        mock_cache.write(url, "cached content")

        fetch_called = [False]

        def fetch_fn():
            fetch_called[0] = True
            return "fresh content"

        result = mock_cache.get_or_fetch(fetch_fn, url)
        assert result == "cached content"
        assert fetch_called[0] is False

    def test_get_or_fetch_cache_miss(self, mock_cache):
        """缓存未命中时调用 fetch_fn 并写缓存"""
        url = "http://test.edu.cn/page"

        def fetch_fn():
            return "fresh content"

        result = mock_cache.get_or_fetch(fetch_fn, url)
        assert result == "fresh content"
        assert mock_cache.stats["misses"] == 1
        assert mock_cache.stats["writes"] == 1

    def test_get_or_fetch_force(self, mock_cache):
        """force=True 时忽略新鲜缓存并重新抓取"""
        url = "http://test.edu.cn/page"
        mock_cache.write(url, "old content")

        def fetch_fn():
            return "new content"

        result = mock_cache.get_or_fetch(fetch_fn, url, force=True)
        assert result == "new content"

    def test_clear(self, tmp_dir):
        """clear 删除当前缓存目录中的文件"""
        cache = CrawlCache(cache_dir=tmp_dir / "cache", max_age_days=7)
        cache.write("http://test.edu.cn/page", "<html>cached</html>")
        cache.write("http://test.edu.cn/api", '{"data": []}')

        assert cache.clear() == 2
        assert not cache.cache_dir.exists()

    def test_get_or_fetch_no_cache(self, mock_cache):
        """use_cache=False 时不读不写缓存"""
        url = "http://test.edu.cn/page"
        mock_cache.write(url, "cached content")

        def fetch_fn():
            return "fresh content"

        result = mock_cache.get_or_fetch(fetch_fn, url, use_cache=False)
        assert result == "fresh content"
        assert mock_cache.stats["misses"] == 1

    def test_read_text_after_write(self, mock_cache):
        """写入后能正确读取"""
        url = "http://test.edu.cn/detail/teacher1"
        content = '{"name": "张三", "title": "教授"}'
        mock_cache.write(url, content)
        result = mock_cache.read_text(url)
        assert result == content

    def test_write_creates_dirs(self, tmp_dir):
        """write 会自动创建缓存目录"""
        cache = CrawlCache(cache_dir=tmp_dir / "deep" / "cache" / "path", max_age_days=7)
        url = "http://test.edu.cn/page"
        cache.write(url, "<html>content</html>")
        assert cache.cache_dir.exists()

    def test_json_content_stored_as_json(self, mock_cache):
        """JSON 内容存储为 .json 文件"""
        url = "http://test.edu.cn/api/data"
        json_content = '{"total": 2, "data": [1, 2]}'
        mock_cache.write(url, json_content)

        # 检查文件扩展名
        domain, tail = "test.edu.cn", "data"
        files = list((mock_cache.cache_dir / "test.edu.cn").glob("*"))
        assert any(f.suffix == ".json" for f in files)


@pytest.mark.parametrize("old_fails", [False, True])
def test_timed_out_old_owner_cannot_delete_new_generation(mock_cache, monkeypatch, old_fails):
    from concurrent.futures import ThreadPoolExecutor
    url = "https://offline.invalid/generation"
    old_started, release_old = threading.Event(), threading.Event()
    new_started, release_new = threading.Event(), threading.Event()

    def old_fetch():
        old_started.set()
        assert release_old.wait(5)
        if old_fails:
            raise RuntimeError("old owner failed")
        return "old"

    def new_fetch():
        new_started.set()
        assert release_new.wait(5)
        return "new"

    with ThreadPoolExecutor(max_workers=2) as pool:
        old = pool.submit(mock_cache.get_or_fetch, old_fetch, url)
        try:
            assert old_started.wait(5)
            old_entry = mock_cache._inflight[url]
            # Simulate only this generation's 300s waiter timeout, not real time.
            monkeypatch.setattr(old_entry[0], "wait", lambda timeout=None: False)
            new = pool.submit(mock_cache.get_or_fetch, new_fetch, url)
            assert new_started.wait(5)
            new_entry = mock_cache._inflight[url]
            assert new_entry is not old_entry
            release_old.set()
            if old_fails:
                with pytest.raises(RuntimeError, match="old owner failed"):
                    old.result(timeout=5)
            else:
                assert old.result(timeout=5) == "old"
            assert mock_cache._inflight[url] is new_entry
            assert mock_cache.read_text(url) is None  # obsolete owner did not write
            release_new.set()
            assert new.result(timeout=5) == "new"
        finally:
            release_old.set()
            release_new.set()
    assert url not in mock_cache._inflight
    assert mock_cache.read_text(url) == "new"
    assert mock_cache.stats["misses"] == 2
    assert mock_cache.stats["writes"] == 1


def test_owner_failure_releases_waiter_and_retry_succeeds(mock_cache):
    from concurrent.futures import ThreadPoolExecutor
    started, release = threading.Event(), threading.Event()
    url = "https://offline.invalid/retry"
    def failing():
        started.set()
        assert release.wait(5)
        raise ValueError("owner error")
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(mock_cache.get_or_fetch, failing, url)
        try:
            assert started.wait(5)
            second = pool.submit(mock_cache.get_or_fetch, lambda: "recovered", url)
            release.set()
            with pytest.raises(ValueError, match="owner error"):
                first.result(timeout=5)
            assert second.result(timeout=5) == "recovered"
        finally:
            release.set()
    assert mock_cache.read_text(url) == "recovered"
    assert mock_cache._inflight == {}


def test_batch_reads_deduplicate_and_hit_rate(mock_cache):
    a, b = "https://offline.invalid/a", "https://offline.invalid/b"
    assert mock_cache.get_hit_rate() == 0
    assert mock_cache.get_or_fetch(lambda: "A", a) == "A"
    assert mock_cache.read_many([a, a, b]) == {a: "A", b: None}
    assert mock_cache.stats["hits"] == 1
    assert mock_cache.get_hit_rate() == 0.5
