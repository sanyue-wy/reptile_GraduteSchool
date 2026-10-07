# -*- coding: utf-8 -*-
"""
HTML 成品 file:// 独立打开验收
=============================
关掉 progress.md 里挂了两个多月的第二条 W7 未完成项：
「HTML 成品 file:// 独立打开截图验证」。

做法：用仓库自带的 html_presenter 插件 + tests/test_presentation_plugins.py
里现成的 fixture 构造方式（``_make_presentation_request`` / ``MockContext``，
不另起炉灶）渲染一个真实 HTML 成品，写到 tmp_path，再用 Chromium 以
file:// 载入，断言：

* 没有 console 错误 / 未捕获 JS 异常（成品是自包含的，file:// 下不该有任何请求）
* 预期内容真的进了 DOM：dataset 名、字段表头、每一条记录的值
* 内嵌的 ThemeSwitcher 真的能跑：按钮存在、点击后 data-theme 真的切换

「能跑」而不只是「字符串在文件里」是这条测试与既有单元测试
（test_theme_switcher_present 只 grep 源码）的区别。
"""

from __future__ import annotations

from pathlib import Path
from urllib.request import pathname2url

import pytest

from plugins.presenters.html_presenter.plugin import HtmlPresenterPlugin
from tests.browser.conftest import REPO_ROOT, PageAudit
from tests.test_presentation_plugins import MockContext, _make_presentation_request

pytestmark = pytest.mark.browser

EXPECTED_FIELDS = ["name", "title", "university"]
EXPECTED_RECORDS = [
    {"name": "Alice", "title": "Professor", "university": "TestU"},
    {"name": "Bob", "title": "Associate Prof", "university": "TestU"},
    {"name": "Charlie", "title": "Lecturer", "university": "OtherU"},
]


def _render_html(tmp_path: Path, records=None) -> Path:
    """用 html_presenter 渲染一个真实成品，返回文件路径。"""
    context = MockContext(tmp_path=tmp_path)
    context.config_snapshot["plugins"]["html_presenter"] = {
        "output_dir": str(tmp_path)
    }
    plugin = HtmlPresenterPlugin()
    plugin.setup(context)
    # 显式钉住模板目录，不依赖当前工作目录：setup() 会在 templates/ 相对
    # CWD 存在时选中它，而 pytest 的 CWD 未必是仓库根。
    plugin._template_dir = REPO_ROOT / "templates"

    result = plugin.render(_make_presentation_request(records=records), context)
    path = Path(result.path)
    assert path.exists(), f"html_presenter 声称写出了 {path}，但文件不存在"
    return path


@pytest.fixture(scope="module")
def rendered_html(tmp_path_factory) -> Path:
    return _render_html(tmp_path_factory.mktemp("html_output"))


@pytest.fixture
def loaded_output(page_audit_factory, rendered_html) -> tuple:
    """以 file:// 载入成品，并挂上 PageAudit。"""
    url = "file://" + pathname2url(str(rendered_html.resolve()))
    page, audit = page_audit_factory()
    page.goto(url, wait_until="load", timeout=30_000)
    page.wait_for_timeout(600)
    return page, audit


def test_rendered_output_opens_standalone(loaded_output):
    """成品能在 file:// 下独立打开：标题正确、容器已渲染。"""
    page, audit = loaded_output

    assert page.title() == "test_dataset - education.tutor.v1", (
        f"成品标题不对：{page.title()!r}"
    )
    # 模板是 minimal-light，其内容容器是 .tpl-content
    assert page.locator(".tpl-content").count() == 1, "成品没有渲染出 .tpl-content 容器"

    audit.assert_clean()


def test_rendered_output_has_no_network_dependency(loaded_output):
    """成品是自包含的：file:// 下不应触发任何同源/跨域网络请求。"""
    _, audit = loaded_output

    assert not audit.failed_requests, f"成品发起了请求：{audit.failed_requests}"
    assert not audit.bad_responses, f"成品请求到了异常资源：{audit.bad_responses}"


def test_rendered_output_dom_contains_records(loaded_output):
    """记录真的进了 DOM（表头 + 每一条记录的值）。"""
    page, _ = loaded_output

    headers = page.locator("table.data-table thead th").all_text_contents()
    assert headers == EXPECTED_FIELDS, f"表头不对：{headers}"

    rows = page.locator("table.data-table tbody tr")
    assert rows.count() == len(EXPECTED_RECORDS), (
        f"表格行数不对：{rows.count()}，预期 {len(EXPECTED_RECORDS)}"
    )

    # 逐字段核对，不只看行数：行数对但值错，同样是成品坏了
    for index, record in enumerate(EXPECTED_RECORDS):
        cells = rows.nth(index).locator("td").all_text_contents()
        assert cells == [record[f] for f in EXPECTED_FIELDS], (
            f"第 {index} 行数据不对：{cells}"
        )


def test_rendered_output_theme_switcher_runs(loaded_output):
    """内嵌的 ThemeSwitcher 真的能执行，而不只是出现在文件里。"""
    page, audit = loaded_output

    button = page.locator("#theme-toggle-btn")
    assert button.count() == 1, "ThemeSwitcher 没有渲染出 #theme-toggle-btn"

    before = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert before, "根元素没有 data-theme 属性"

    button.click()
    page.wait_for_timeout(200)

    after = page.evaluate("document.documentElement.getAttribute('data-theme')")
    assert after != before, (
        f"点击主题按钮后 data-theme 没有变化（{before} -> {after}），"
        f"说明内嵌 JS 没有真正执行"
    )
    audit.assert_clean()


def test_rendered_output_escapes_hostile_records(page_audit_factory, tmp_path):
    """带 <script> 的记录不得在浏览器里变成可执行节点。"""
    path = _render_html(
        tmp_path,
        records=[{"name": "<script>window.pwned=1</script>",
                  "title": "T", "university": "U"}],
    )

    page, audit = page_audit_factory()
    page.goto(
        "file://" + pathname2url(str(path.resolve())),
        wait_until="load",
        timeout=30_000,
    )
    page.wait_for_timeout(400)

    assert page.evaluate("typeof window.pwned") == "undefined", (
        "记录里的 <script> 被当成了可执行脚本 —— 转义失效"
    )
    # 文本层面仍应完整可见（转义成实体后浏览器会还原成原文字面量）
    assert page.locator("text=<script>window.pwned=1</script>").count() >= 1
    audit.assert_clean()
