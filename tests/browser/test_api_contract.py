# -*- coding: utf-8 -*-
"""
前端 API 契约测试
=================
枚举 dashboard/ 下前端实际调用的每一个端点，逐个断言：

1. 它在 ``api.server.app.url_map`` 里真实存在（**读 url_map，而不是只发请求**）
   —— 端点被删时这条才会失败；只发请求的话，Flask 的 catch-all 静态路由
   （``/<path:filename>``）会对大部分路径返回 404，把「端点没了」伪装成
   「资源不存在」，测不出来。
2. 它用真实请求打过去，状态码不是 5xx。

另有一条非 /api/ 的同源抓取扫描：Flask 的 static_folder 是 dashboard/，
而前端还会抓仓库根下的静态资源（目前是 /templates/registry.json），
这条 /api/ 扫描覆盖不到，单独查。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

REPO_ROOT = Path(__file__).resolve().parents[2]

# 与 V3.0「闭环补全」批次共享的发现命令同一套正则，保证各窗口口径一致
API_CALL_RE = re.compile(r"""['"](/api/[A-Za-z0-9_/<>.\$-]*)""")

# 已知红灯（G2 负责补后端）：前端在调，后端没有
KNOWN_MISSING_ENDPOINTS = [
    "/api/plugins/errors",   # dashboard/console/plugins.html
    "/api/outputs/serve",   # dashboard/runtime/preview.html
]


def _frontend_files():
    dashboard = REPO_ROOT / "dashboard"
    return sorted(
        p for p in dashboard.rglob("*")
        if p.suffix in (".html", ".js") and p.is_file()
    )


def _scan_api_calls() -> dict[str, set[str]]:
    calls: dict[str, set[str]] = {}
    for path in _frontend_files():
        text = path.read_text(encoding="utf-8")
        for match in API_CALL_RE.findall(text):
            calls.setdefault(match, set()).add(str(path.relative_to(REPO_ROOT)))
    return calls


def _scan_non_api_fetches() -> dict[str, set[str]]:
    """抓取/加载的同源静态路径（不以 /api/ 开头）。"""
    pattern = re.compile(r"""['"](/(?!api/)[A-Za-z0-9_./\-]+\.(?:json|css|js|html))""")
    found: dict[str, set[str]] = {}
    for path in _frontend_files():
        text = path.read_text(encoding="utf-8")
        for match in pattern.findall(text):
            found.setdefault(match, set()).add(str(path.relative_to(REPO_ROOT)))
    return found


def _rule_exists(rules: set[str], url: str) -> bool:
    """与共享发现命令同一套匹配口径（含带路径参数的动态段）。"""
    base = url.split("?")[0].rstrip("/")
    if "<" in base or base in rules:
        return base in rules
    return any(r.startswith(base + "/<") for r in rules)


@pytest.fixture(scope="module")
def url_map_rules() -> set[str]:
    import api.server as server_module

    return {rule.rule for rule in server_module.app.url_map.iter_rules()}


@pytest.fixture(scope="module")
def api_calls() -> dict[str, set[str]]:
    calls = _scan_api_calls()
    assert calls, "没能从前端扫到任何 /api/ 调用，正则或目录结构变了？"
    return calls


def _http_status(client, url: str) -> int:
    """用 Playwright 的 APIRequestContext 打一发，拿状态码。"""
    response = client.get(url, timeout=30_000)
    return response.status


# ------------------------------------------------------------------


def test_frontend_api_calls_are_registered(api_calls, url_map_rules):
    """前端调用的每个端点都必须出现在 Flask url_map 里。"""
    missing = [
        (url, sorted(files)) for url, files in sorted(api_calls.items())
        if not _rule_exists(url_map_rules, url)
    ]
    assert not missing, (
        "前端调用了 url_map 里不存在的端点：\n"
        + "\n".join(f"    - {url}  <- {files}" for url, files in missing)
    )


@pytest.mark.parametrize("endpoint", KNOWN_MISSING_ENDPOINTS)
def test_known_missing_endpoint_is_registered(endpoint, url_map_rules):
    """两个已知红灯的定点用例。

    单独拎出来是为了让失败信息一眼可读、可 grep。这两个端点 G2 补齐后
    本用例自然转绿，无需改动。
    """
    assert _rule_exists(url_map_rules, endpoint), (
        f"{endpoint} 仍不在 url_map 中：前端 console/plugins.html、"
        f"runtime/preview.html 已经在调它，后端必须补上"
    )


def test_concrete_api_endpoints_do_not_error(api_calls, live_server, api_client):
    """所有无路径参数的端点实际打一遍，不得返回 5xx。

    POST-only 的端点用 GET 打会得到 405，那不是 5xx，属于预期。
    """
    concrete = sorted(
        url for url in api_calls
        if "<" not in url and "?" not in url
    )
    assert concrete, "没有扫到任何可直接 GET 的端点，扫描逻辑可能坏了"

    failures = []
    for url in concrete:
        status = _http_status(api_client, live_server + url)
        if status >= 500:
            failures.append(f"{url} -> {status}")

    assert not failures, "以下端点返回 5xx：\n" + "\n".join(
        f"    - {f}" for f in failures
    )


def test_non_api_static_fetches_are_served(live_server, api_client):
    """前端抓取的同源静态资源必须真的存在。

    Flask 的 static_folder 是 dashboard/，仓库根下的 templates/ 不在其中；
    这条专门盯住那一类「文件明明在仓库里、但 URL 取不到」的缺口。
    """
    fetches = _scan_non_api_fetches()
    assert fetches, "没扫到任何非 /api/ 的静态抓取，正则可能失效了"

    broken = []
    for url, files in sorted(fetches.items()):
        status = _http_status(api_client, live_server + url)
        if status != 200:
            broken.append(f"{url} -> {status}  <- {sorted(files)}")

    assert not broken, (
        "前端引用的同源静态资源取不到：\n"
        + "\n".join(f"    - {b}" for b in broken)
    )


def test_no_silent_fallback_to_fake_data():
    """守护：禁止前端使用「r.ok ? r.json() : { ... }」静默回退假数据模式。

    这种模式会把后端 4xx/5xx 故障伪装成「本来就没数据」，导致：
    - 页面渲染空白但无报错，极难排查
    - 监控告警失效（前端不报错、后端也不一定有告警）
    - 用户看到「暂无数据」实为后端挂了

    扫描 dashboard/ 下所有 .html/.js，若发现以下模式则失败：
      - r.ok ? r.json() : { ... }
      - r.ok ? r.json() : []
      - response.ok ? response.json() : ...
      - 任何 .ok ? .json() : 字面量对象/数组 的三元表达式
    """
    import re

    dashboard = REPO_ROOT / "dashboard"
    pattern = re.compile(
        r"\.ok\s*\?\s*\w*\.json\(\)\s*:\s*[\{\[]",  # .ok ? .json() : { or [
        re.MULTILINE,
    )

    violations = []
    for path in dashboard.rglob("*"):
        if path.suffix in (".html", ".js") and path.is_file():
            text = path.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                # 定位行号用于报告
                line_no = text[: match.start()].count("\n") + 1
                # 取上下文片段
                start = max(0, match.start() - 40)
                end = min(len(text), match.end() + 40)
                snippet = text[start:end].replace("\n", " ")
                rel = path.relative_to(REPO_ROOT)
                violations.append(f"  - {rel}:{line_no}  {snippet.strip()}")

    assert not violations, (
        "检测到「静默回退假数据」模式（.ok ? .json() : { ... }），"
        "请改为显式错误处理（抛出/上报/展示错误态）：\n"
        + "\n".join(violations)
    )
