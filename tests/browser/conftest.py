# -*- coding: utf-8 -*-
"""
浏览器验收 fixtures（V3.0 W7 收口）
==================================
三件套：

1. ``live_server``  —— session 级，用 werkzeug 在空闲端口拉起真实 app
   （``api.server:app``），轮询 ``/api/healthz`` 到 200 才放行。
   不假设 ``data/output/`` 里有采集结果（该目录被 gitignore，全新克隆时为空）。
2. ``page``         —— 挂 console / pageerror / requestfailed / response 监听器，
   收集「未捕获 JS 异常」与「同源 >=400 的响应」，**在 teardown 里断言为空**。
   本套件最有价值的一条断言就是它。它已经被验证能抓到真问题：G2 补后端之前，
   console/plugins.html 的 /api/plugins/errors 与 runtime/preview.html 的
   /api/outputs/serve 这两个 404 就是被它暴露出来的（G2 落地后自然转绿）；
   现在仍在报的三条是 dashboard/tasks.html 与 dashboard/console/failures.html
   的真实前端缺陷，详见交付报告。
3. ``browser``      —— session 级 Chromium；未安装 Playwright 或未下载
   Chromium 时 clean skip，并给出可操作的安装提示（绝不让整套测试 error）。

服务器用线程内嵌 werkzeug（而非子进程），这样 session 结束能可靠回收，
且不会因为 ``api.server.__main__`` 去弹浏览器窗口。
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ------------------------------------------------------------------
# 页面清单：管理台 5 页 + 主面板 6 页
# (路径, 主容器选择器, 分组)
# 主容器逐页指定，不写死成通用选择器——各页结构不同（表格页是 .main .content，
# 管理台是 #plugin-list / #failures-list / form），写死了反而测不准。
# ------------------------------------------------------------------
MAIN_PANEL_PAGES = [
    ("/index.html", ".main .content", "main"),
    ("/schools.html", ".main .content", "main"),
    ("/failures.html", ".main .content", "main"),
    ("/tutors.html", ".main .content", "main"),
    ("/tasks.html", ".main .content", "main"),
    ("/config.html", ".main .content", "main"),
]

CONSOLE_PAGES = [
    ("/console/index.html", "main.nav-grid", "console"),
    ("/console/plugins.html", "#plugin-list", "console"),
    ("/console/failures.html", "#failures-list", "console"),
    ("/console/task-config.html", "#task-form", "console"),
    ("/console/output-config.html", "form", "console"),
]

ALL_PAGES = MAIN_PANEL_PAGES + CONSOLE_PAGES
PAGE_IDS = [path for path, _, _ in ALL_PAGES]


# ------------------------------------------------------------------
# 噪声过滤：只放行「已知无害」的浏览器公告，且必须逐条写明理由。
# 这里刻意不提供「忽略所有 console error」的开关——那会让整套断言失效。
# ------------------------------------------------------------------

# 页面把 frame-ancestors 写进了 <meta http-equiv="Content-Security-Policy">。
# 按 CSP 规范该指令只在 HTTP 头里生效，经 meta 传递时 Chromium 会打一条 error
# 级别的公告。console/* 的 5 个页面和 html_presenter 成品都带这条 meta，
# 它是「页面作者把 frame-ancestors 放错了位置」的提示，不是页面运行故障。
_BENIGN_CONSOLE_SUBSTRINGS = (
    "The Content Security Policy directive 'frame-ancestors' is ignored",
)

# 静态文件加载失败时 Chromium 会在 console 里回显一行 "Failed to load resource"。
# 它与 response 监听器捕获的 4xx/5xx 是同一件事，assert_clean 里会做关联去重，
# 避免同一次故障在报告里出现两遍。
_RESOURCE_ECHO = "Failed to load resource: the server responded with a status of"

# 应用没有提供 favicon。浏览器会无条件请求 /favicon.ico，它的 404 与页面代码无关，
# 且不同 Chromium 版本是否请求不稳定——不排除会让套件在不同机器上飘。
_IGNORED_LOCAL_URL_SUFFIXES = ("/favicon.ico",)


def _is_benign_console(text: str) -> bool:
    return any(s in text for s in _BENIGN_CONSOLE_SUBSTRINGS)


class PageAudit:
    """收集单个 page 的运行期故障；``assert_clean`` 汇总成可读的失败信息。"""

    def __init__(self, page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url
        self.page_errors: list[str] = []
        self.console_errors: list[str] = []
        self.bad_responses: list[str] = []
        self.failed_requests: list[str] = []
        self.external_failures: list[str] = []
        self._asserted = False
        self._bind()

    # -- 同源判定 ---------------------------------------------------
    def _base_netloc(self) -> Optional[str]:
        if self.base_url.startswith("file://"):
            return None  # file:// 下所有 URL 都算本地
        return urlparse(self.base_url).netloc

    def _is_local(self, url: str) -> bool:
        netloc = self._base_netloc()
        if netloc is None:
            return url.startswith("file://")
        parsed = urlparse(url)
        if not parsed.netloc:  # 相对路径，由页面自己解析成同源
            return True
        return parsed.netloc == netloc

    # -- 监听器 -----------------------------------------------------
    def _bind(self) -> None:
        p = self.page

        def on_pageerror(exc) -> None:
            self.page_errors.append(str(exc))

        def on_console(msg) -> None:
            if msg.type != "error":
                return
            text = msg.text
            if _is_benign_console(text):
                return
            self.console_errors.append(text)

        def on_request_failed(request) -> None:
            entry = f"{request.method} {request.url}"
            failure = request.failure or ""
            entry = f"{entry} ({failure})" if failure else entry
            if self._is_local(request.url):
                self.failed_requests.append(entry)
            else:
                # 跨域资源（如 cdn.jsdelivr.net 上的 chart.js）失败取决于网络环境，
                # 不是应用缺陷，只记录不判失败。
                self.external_failures.append(entry)

        def on_response(response) -> None:
            if response.status < 400:
                return
            url = response.url
            if not self._is_local(url):
                return
            if any(url.endswith(sfx) for sfx in _IGNORED_LOCAL_URL_SUFFIXES):
                return
            self.bad_responses.append(f"{response.status} {url}")

        p.on("pageerror", on_pageerror)
        p.on("console", on_console)
        p.on("requestfailed", on_request_failed)
        p.on("response", on_response)

    # -- 报告 -------------------------------------------------------
    def failures(self) -> list[str]:
        """返回人类可读的问题清单；空列表表示页面干净。"""
        problems: list[str] = []

        bad_statuses = {r.split(" ", 1)[0] for r in self.bad_responses}
        for entry in self.bad_responses:
            problems.append(f"同源响应 >=400：{entry}")
        for text in self.console_errors:
            if _RESOURCE_ECHO in text:
                status = text.rsplit(" ", 1)[-1]
                if status in bad_statuses:
                    continue  # 与上面同一条故障，重复计入没有信息量
            problems.append(f"console error：{text}")
        for entry in self.page_errors:
            problems.append(f"未捕获 JS 异常：{entry}")
        for entry in self.failed_requests:
            problems.append(f"同源请求失败：{entry}")
        return problems

    def assert_clean(self) -> None:
        self._asserted = True
        problems = self.failures()
        if not problems:
            return
        bullet = "\n".join(f"    - {p}" for p in problems)
        raise AssertionError(
            f"页面运行期不干净（{self.page.url}）：\n{bullet}\n"
            f"  未捕获 JS 异常 {len(self.page_errors)} 条，"
            f"同源 >=400 响应 {len(self.bad_responses)} 条，"
            f"console error {len(self.console_errors)} 条，"
            f"同源请求失败 {len(self.failed_requests)} 条。"
        )


# 首屏渲染等待：前端在 DOMContentLoaded 里发 API 请求，load 之后还要一小段时间
# 数据才落到 DOM 上。
DEFAULT_SETTLE_MS = 1_200


def open_page(page, url: str, settle_ms: int = DEFAULT_SETTLE_MS, timeout: int = 30_000):
    """载入页面并等首屏数据渲染完，返回 response。

    刻意**不用** ``wait_until="networkidle"``：tasks.html 会挂一条
    /api/logs/stream 的 SSE 长连接，而 networkidle 的判据是「500ms 内零活跃
    连接」，长连接会让它永远等不到，表现成时好时坏的 30s 超时。
    页面是否真的把数据渲染出来，由各用例自己去断言容器内容。
    """
    response = page.goto(url, wait_until="load", timeout=timeout)
    page.wait_for_timeout(settle_ms)
    return response


# ------------------------------------------------------------------
# 服务器
# ------------------------------------------------------------------

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _healthz_ok(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


@pytest.fixture(scope="session")
def live_server():
    """在空闲端口拉起真实 app，/api/healthz 返回 200 之后才放行。"""
    import logging

    from werkzeug.serving import make_server

    # api/server.py 里有若干相对路径（config/*.yaml、data/*、GLOBAL_CONFIG_PATH），
    # 必须在仓库根下运行。session 级 chdir，退出时复原。
    old_cwd = os.getcwd()
    os.chdir(REPO_ROOT)

    # 只压这几个具体 logger，不动 root：config.loader 在导入时会为每所大学
    # 打一条 faculty.list_url 为空的 WARNING，werkzeug 会为每次请求打一行访问
    # 日志，混在测试报告里会淹没真正的失败。只影响日志，不影响任何断言。
    for noisy in ("config.loader", "werkzeug", "api.server"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    import api.server as server_module

    port = _free_port()
    server = make_server("127.0.0.1", port, server_module.app, threaded=True)
    thread = threading.Thread(
        target=server.serve_forever, name="g1-live-server", daemon=True
    )
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30.0
    while time.time() < deadline:
        if _healthz_ok(f"{base_url}/api/healthz"):
            break
        time.sleep(0.15)
    else:
        server.shutdown()
        os.chdir(old_cwd)
        pytest.fail(
            f"Flask 实例未在 30s 内就绪：{base_url}/api/healthz 始终不可达。"
            f"请单独执行 `python -m api.server --port {port}` 复现。"
        )

    try:
        yield base_url
    finally:
        server.shutdown()
        thread.join(timeout=10)
        os.chdir(old_cwd)


# ------------------------------------------------------------------
# 浏览器
# ------------------------------------------------------------------

_SKIP_PLAYWRIGHT = (
    "未安装 Playwright，无法运行浏览器验收。安装方式：\n"
    "    pip install playwright\n"
    "    python -m playwright install chromium\n"
    "或用 `-m 'not browser'` 跳过全部浏览器用例。"
)
_SKIP_BROWSER = (
    "Playwright 已安装但 Chromium 不可用（多半是没下载浏览器）。修复方式：\n"
    "    python -m playwright install chromium\n"
    "若在 Linux 上还缺系统依赖，执行 `python -m playwright install --with-deps chromium`。"
)


@pytest.fixture(scope="session")
def browser():
    """session 级 Chromium。缺 Playwright / 缺 Chromium 一律 clean skip。

    这里没用 ``pytest.importorskip``：pytest 9 起它只吞 ``ModuleNotFoundError``，
    「装了但 import 就炸」（半截安装、依赖版本冲突）这种更常见的坏法会直接
    报 error。整套浏览器测试在没装浏览器的机器上一条都不该 error。
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        pytest.skip(f"{_SKIP_PLAYWRIGHT}\n实际错误：{exc!r}")

    try:
        pw = sync_playwright().start()
    except Exception as exc:  # pragma: no cover - 仅在 Playwright 装坏时触发
        pytest.skip(f"{_SKIP_PLAYWRIGHT}\n实际错误：{exc!r}")
    try:
        try:
            b = pw.chromium.launch()
        except Exception as exc:
            pytest.skip(f"{_SKIP_BROWSER}\n实际错误：{exc!r}")
        try:
            yield b
        finally:
            b.close()
    finally:
        pw.stop()


# ------------------------------------------------------------------
# 页面
# ------------------------------------------------------------------

@pytest.fixture
def page(live_server, browser):
    """全新 context + page，挂齐监听器；teardown 里断言页面无运行期故障。

    想在测试体内显式检查收集结果，用随附的 ``page_audit`` fixture。
    """
    context = browser.new_context()
    pg = context.new_page()
    audit = PageAudit(pg, live_server)
    pg._g1_audit = audit
    try:
        yield pg
    finally:
        # 断言放在 close 之前：page 关掉后再问 status 就没意义了。
        # 用例体内已经显式断言过就不再重复报，避免同一条故障出现两遍。
        try:
            if not audit._asserted:
                audit.assert_clean()
        finally:
            context.close()


@pytest.fixture
def page_audit(page) -> PageAudit:
    """暴露 page 上挂的 PageAudit，供测试显式断言收集结果。"""
    return page._g1_audit


@pytest.fixture
def page_audit_factory(live_server, browser):
    """开一个**不受 teardown 断言管辖**的 (page, PageAudit)。

    给「故意制造故障」的自证用例用：它们要拿到监听器，却不能被 page fixture
    的 teardown 断言反咬一口。所有创建的 context 在 fixture 结束时统一关闭。
    """
    created: list = []

    def make() -> tuple:
        context = browser.new_context()
        pg = context.new_page()
        audit = PageAudit(pg, live_server)
        created.append(context)
        return pg, audit

    try:
        yield make
    finally:
        for context in created:
            context.close()


@pytest.fixture(scope="module")
def api_client(browser):
    """一个独立于 page 的 HTTP 客户端（Playwright APIRequestContext）。

    为什么不直接用 urllib/requests：tests/conftest.py 有一条 autouse 的
    ``no_real_network``，把 socket.connect / create_connection / getaddrinfo
    全部打成 pytest.fail，任何 Python 层的真实请求都会挂。那条禁令的用意是
    拦住「测试里偷偷联网爬真实站点」，而本套件要访问的 127.0.0.1 上的
    实例正是被测对象本身。改走 Chromium 的网络栈，既不碰别人的 conftest，
    又能让请求真的经过 socket。
    """
    context = browser.new_context()
    try:
        yield context.request
    finally:
        context.close()
