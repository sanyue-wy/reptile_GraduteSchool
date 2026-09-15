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
        """force=True 但缓存新鲕�时仍返回缓存（force 仅作用于过期缓存）"""
        url = "http://test.edu.cn/page"
        mock_cache.write(url, "old content")

        def fetch_fn():
            return "new content"

        result = mock_cache.get_or_fetch(fetch_fn, url, force=True)
        # 缓存新鲜，force 不会强制刷新
        assert result == "old content"

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
