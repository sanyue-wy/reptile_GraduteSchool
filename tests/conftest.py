# -*- coding: utf-8 -*-
"""
测试全局 fixtures
================
"""

import pytest
import socket
import sys
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import MagicMock


# Read the checked-in configuration only to seed private copies. Never copy data/.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def _school_config_seed():
    return (_PROJECT_ROOT / "config" / "school_data.json").read_bytes()


@pytest.fixture(autouse=True)
def isolated_workspace(tmp_path, monkeypatch, _school_config_seed):
    """Keep real loaders, stores and pipelines, but put all default I/O in tmp_path.

    Changing cwd covers relative defaults captured in function signatures (export,
    progress, cache, raw files and URLResolver candidates). The loader's absolute
    paths and mutable module state need separate patches, restored after each test.
    """
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.chdir(root)
    config_dir = root / "config"
    config_dir.mkdir()
    school_path = config_dir / "school_data.json"
    school_path.write_bytes(_school_config_seed)
    (config_dir / "global.json").write_text("{}", encoding="utf-8")
    for directory in ("output", "cache", "raw", "candidates"):
        (root / "data" / directory).mkdir(parents=True)

    import config.loader as loader
    import config.plugins as plugins
    import utils.progress as progress

    monkeypatch.setattr(loader, "DEFAULT_CONFIG_PATH", school_path)
    monkeypatch.setattr(loader, "_config_path", school_path)
    monkeypatch.setattr(loader, "_config_cache", None)
    # The storage layer is being introduced concurrently. When present it has
    # its own absolute default, independent of config.loader's compatibility API.
    if (_PROJECT_ROOT / "storage" / "config_store.py").is_file():
        from storage import config_store
        monkeypatch.setattr(config_store, "DEFAULT_CONFIG_PATH", school_path)
    monkeypatch.setattr(progress, "_progress_tracker", None)
    monkeypatch.setattr(plugins, "PLUGIN_CONFIG_PATH", config_dir / "plugins.json")
    monkeypatch.setattr(plugins, "EXT_PLUGIN_DIR", root / "plugins_ext")
    monkeypatch.setattr(plugins, "_EXTERNAL_CACHE", {})

    # Local plugin fixtures used to delete every plugins_ext.* entry. Preserve
    # modules present before the test, while removing only this test's imports.
    external_modules = {
        name: module for name, module in sys.modules.items()
        if name == "plugins_ext" or name.startswith("plugins_ext.")
    }
    try:
        yield root
    finally:
        for name in list(sys.modules):
            if name == "plugins_ext" or name.startswith("plugins_ext."):
                if name not in external_modules:
                    sys.modules.pop(name, None)
        sys.modules.update(external_modules)


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    """Fail at transport/DNS, not PoliteSession.get or Session.request.

    Existing request/session mocks still work; real HTTP logic and parsing remain
    testable. pytest.fail also escapes application-level ``except Exception`` so
    an accidentally unmocked request cannot masquerade as an expected failure.
    """
    from requests.adapters import HTTPAdapter

    def forbidden(*args, **kwargs):
        pytest.fail("Real network disabled in tests; mock the HTTP transport", pytrace=False)

    monkeypatch.setattr(HTTPAdapter, "send", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket.socket, "sendto", forbidden)
    return forbidden


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


@pytest.fixture(autouse=True)
def protect_checked_in_files(monkeypatch):
    """Reject writes to real data/config even if a default escapes cwd isolation."""
    import builtins
    import io
    import os

    protected = [(_PROJECT_ROOT / name).resolve() for name in ("data", "config")]

    def check(path):
        if isinstance(path, (str, bytes, os.PathLike)):
            resolved = Path(os.fsdecode(path)).resolve()
            if any(resolved.is_relative_to(root) for root in protected):
                pytest.fail(f"Attempted write to protected project path: {resolved}", pytrace=False)

    for module in (builtins, io):
        original = module.open

        def guarded_open(file, mode="r", *args, _open=original, **kwargs):
            if any(flag in mode for flag in "wax+"):
                check(file)
            return _open(file, mode, *args, **kwargs)

        monkeypatch.setattr(module, "open", guarded_open)

    original_open = os.open

    def guarded_os_open(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            check(path)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_os_open)
    for name in ("replace", "rename"):
        original = getattr(os, name)

        def guarded_move(src, dst, *args, _move=original, **kwargs):
            check(src)
            check(dst)
            return _move(src, dst, *args, **kwargs)

        monkeypatch.setattr(os, name, guarded_move)
    for name in ("unlink", "remove", "rmdir", "mkdir"):
        original = getattr(os, name)

        def guarded_change(path, *args, _change=original, **kwargs):
            check(path)
            return _change(path, *args, **kwargs)

        monkeypatch.setattr(os, name, guarded_change)


@pytest.fixture
def tmp_output_dir(tmp_path):
    output = tmp_path / "service-output"
    output.mkdir()
    return output


@pytest.fixture
def offline_transport(monkeypatch):
    """Real PoliteSession over deterministic in-memory requests responses."""
    from requests import Response
    from utils.http import PoliteSession

    calls = []
    routes = {}

    def request(session, method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url not in routes:
            pytest.fail(f"No offline response registered for {method} {url}")
        body = routes[url]
        if callable(body):
            body = body(method, url, kwargs)
        if isinstance(body, BaseException):
            raise body
        response = Response()
        response.status_code = 200
        response.url = url
        response.encoding = "utf-8"
        if isinstance(body, (dict, list)):
            response.headers["Content-Type"] = "application/json; charset=utf-8"
            response._content = json.dumps(body, ensure_ascii=False).encode("utf-8")
        else:
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            response._content = body.encode("utf-8")
        return response

    monkeypatch.setattr("requests.sessions.Session.request", request)
    session = PoliteSession(delay_range=(0, 0), max_retries=0)
    return session, routes, calls


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
