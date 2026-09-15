# -*- coding: utf-8 -*-
"""
测试全局 fixtures
================
"""

import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def tmp_dir():
    """临时目录，测试结束自动清理"""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mock_session():
    """Mock PoliteSession，不发起真实 HTTP 请求"""
    session = MagicMock()
    session.get.return_value = MagicMock(
        status_code=200,
        text="<html></html>",
        content=b"<html></html>",
        headers={"Content-Type": "text/html"},
        url="http://test.edu.cn",
        encoding="utf-8",
    )
    session.post.return_value = MagicMock(
        status_code=200,
        text='{"data": []}',
        content=b'{"data": []}',
        headers={"Content-Type": "application/json"},
        url="http://test.edu.cn/api",
    )
    session.post.return_value.json = MagicMock(return_value={"data": []})
    session.save_raw.return_value = "/tmp/test_raw.html"
    return session


@pytest.fixture
def mock_cache(tmp_dir):
    """测试用 CrawlCache，指向临时目录"""
    from utils.cache import CrawlCache
    return CrawlCache(cache_dir=str(tmp_dir / "cache"), max_age_days=7)


@pytest.fixture
def mock_progress(tmp_dir):
    """测试用 ProgressTracker，指向临时目录"""
    from utils.progress import ProgressTracker
    return ProgressTracker(
        progress_file=tmp_dir / "output" / "progress.json",
        log_file=tmp_dir / "output" / "crawl.log",
    )


@pytest.fixture
def sample_config():
    """单校测试配置"""
    return {
        "university": "测试大学",
        "level": "985",
        "categories": [
            {
                "college": "机械工程学院",
                "category": "mechanical",
                "faculty": {
                    "list_url": "http://test.edu.cn/faculty",
                    "list_type": "static_html",
                    "list_item_selector": "li a",
                    "list_research_selector": "p.desc",
                    "detail_selectors": {
                        "name": ".name",
                        "title": ".title",
                        "email_re": r"[\w.]+@[\w.]+",
                    },
                    "api_params": {},
                    "referer": "",
                },
                "notice": {
                    "enabled": True,
                    "entry_url": "https://yz.chsi.com.cn/zsml/",
                    "school_code": "99999",
                    "major_codes": {},
                    "title_pattern": "",
                    "template": "yzw_major",
                },
            }
        ],
    }


@pytest.fixture
def sample_faculty_html():
    """Mock 师资列表页 HTML"""
    return """
    <html><body>
    <ul class="faculty-list">
        <li><a href="/teacher/1" title="张三">张三</a><p class="desc">研究方向：智能制造</p></li>
        <li><a href="/teacher/2" title="李四">李四</a><p class="desc">研究方向：机器人学</p></li>
        <li><a href="/teacher/3" title="王五">王五</a><p class="desc">研究方向：自动化控制</p></li>
    </ul>
    </body></html>
    """


@pytest.fixture
def sample_yzw_json():
    """Mock 研招网专业目录 JSON"""
    return {
        "total": 2,
        "data": [
            {
                "dwmc": "测试大学",
                "dwdm": "99999",
                "zymc": "机械工程",
                "zydm": "085501",
                "yjfxmc": "智能制造",
                "zdjs": "张三 李四",
                "xxfs": "1",
                "nzsrsstr": "3",
                "kskm": "101 政治 201 英语一 301 数学一 801 机械原理",
            },
            {
                "dwmc": "测试大学",
                "dwdm": "99999",
                "zymc": "车辆工程",
                "zydm": "085502",
                "yjfxmc": "新能源汽车",
                "zdjs": "王五",
                "xxfs": "1",
                "nzsrsstr": "2",
                "kskm": "101 政治 201 英语一 301 数学一 802 汽车理论",
            },
        ],
    }


@pytest.fixture
def sample_yzw_major_json():
    """Mock 研招网专业目录详细 JSON（用于 yzw_major parser 测试）"""
    return {
        "total": 2,
        "data": [
            {
                "dwmc": "测试大学",
                "dwdm": "99999",
                "zymc": "机械工程",
                "zydm": "085501",
                "yjfxmc": "智能制造",
                "zdjs": "张三 李四",
                "xxfs": "1",
                "nzsrsstr": "3",
                "kskm": "101 政治 201 英语一 301 数学一 801 机械原理",
            },
            {
                "dwmc": "测试大学",
                "dwdm": "99999",
                "zymc": "车辆工程",
                "zydm": "085502",
                "yjfxmc": "新能源汽车",
                "zdjs": "王五",
                "xxfs": "1",
                "nzsrsstr": "2",
                "kskm": "101 政治 201 英语一 301 数学一 802 汽车理论",
            },
        ],
    }
