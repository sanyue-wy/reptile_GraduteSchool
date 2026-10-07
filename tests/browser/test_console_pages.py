# -*- coding: utf-8 -*-
"""
管理台 5 页 + 主面板 6 页的冒烟 + 契约测试（W7 收口）
====================================================
每页断言五件事：

1. 顶层导航返回 <400
2. ``<title>`` 非空
3. 页面主容器存在，且确实渲染出了子节点（空壳不算通过）
4. 主容器里有真实文本 —— 用 ``textContent`` 而不是 ``innerText``：
   后者对 ``display:none`` 的元素返回空串，而 tasks.html 的表格在未激活的
   tab 面板里，用 innerText 会把「已渲染但未激活」误判成「没渲染」。
   骨架屏 div 是空的，所以这条仍然能抓住「卡在 loading 没渲染出来」。
5. 无未捕获 JS 异常、无同源 4xx/5xx（由 conftest 的 page fixture 在 teardown 断言）

第 5 条由 fixture 统一兜底，本文件只补前四条。
"""

from __future__ import annotations

import pytest

from tests.browser.conftest import ALL_PAGES, PAGE_IDS, open_page

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("path,container,group", ALL_PAGES, ids=PAGE_IDS)
def test_page_renders(page, page_audit, live_server, path, container, group):
    """单页冒烟 + 契约。"""
    response = open_page(page, live_server + path)
    assert response is not None, f"{path} 没有收到任何响应"
    assert response.status < 400, (
        f"{path} 顶层导航返回 {response.status}，预期 <400"
    )

    title = page.title()
    assert title and title.strip(), f"{path} 的 <title> 为空"

    locator = page.locator(container)
    assert locator.count() == 1, (
        f"{path} 主容器 {container!r} 应恰好命中 1 个元素，"
        f"实际 {locator.count()} 个"
    )

    # 主容器必须渲染出子节点：只有静态骨架、JS 一行都没跑起来的空壳不算通过。
    child_count = locator.evaluate("el => el.children.length")
    assert child_count > 0, (
        f"{path} 主容器 {container!r} 没有任何子元素 —— 页面只加载了静态外壳，"
        f"渲染逻辑没有执行"
    )

    # 骨架屏 div 内无文本，因此这条能区分「渲染完成」与「卡在 loading」。
    text = locator.evaluate("el => (el.textContent || '').trim()")
    assert text, (
        f"{path} 主容器 {container!r} 渲染出了 {child_count} 个子元素但没有任何文本，"
        f"页面仍停留在未渲染状态（通常是渲染函数抛异常后中断）"
    )

    # 放最后：前四条都过了再报「未捕获 JS 异常 / 同源 4xx」，
    # 这样一条红灯只指向一个根因。
    page_audit.assert_clean()


def test_root_route_serves_a_page(page, page_audit, live_server):
    """`/` 分流到主面板或管理台，两条分支都必须能出页面。"""
    response = open_page(page, live_server + "/")
    assert response.status == 200
    assert page.title().strip(), "`/` 返回的页面 <title> 为空"

    # ?view=console 显式进入管理台导航页
    open_page(page, live_server + "/?view=console")
    assert page.title().strip() == "Console - GraduteSchool V3.0"
    assert page.locator("main.nav-grid .nav-card").count() >= 1

    page_audit.assert_clean()


# ------------------------------------------------------------------
# 自证：证明监听器不是摆设
# ------------------------------------------------------------------
# 下面两条是整套断言的「免疫性测试」。如果 page fixture 的监听器哪天失灵
# （比如 Chromium 升级后事件名变了），这里会先红，而不是等到真出 bug 时才发现
# 整套测试早就瞎了。

def test_audit_detects_injected_js_error(page_audit_factory):
    """注入一个未捕获 JS 异常，PageAudit 必须抓到。"""
    page, audit = page_audit_factory()
    page.goto("about:blank")
    page.evaluate("setTimeout(function () { undefinedFunction(); }, 0)")
    page.wait_for_timeout(300)

    assert audit.page_errors, (
        "注入的未捕获 JS 异常没有被 PageAudit 捕获 —— "
        "pageerror 监听器已失灵，整套浏览器断言不可信"
    )
    with pytest.raises(AssertionError, match="未捕获 JS 异常"):
        audit.assert_clean()


def test_audit_detects_same_origin_404(page_audit_factory, live_server):
    """访问一个必然 404 的同源地址，PageAudit 必须抓到。"""
    page, audit = page_audit_factory()
    page.goto(live_server + "/api/definitely-not-a-real-endpoint")
    page.wait_for_timeout(200)

    assert any("404" in entry for entry in audit.bad_responses), (
        f"同源 404 没有被 PageAudit 捕获，实际收集到 {audit.bad_responses} —— "
        f"response 监听器已失灵"
    )
    with pytest.raises(AssertionError, match="同源响应 >=400"):
        audit.assert_clean()


def test_audit_ignores_known_benign_csp_notice(page, page_audit, live_server):
    """frame-ancestors 的 meta CSP 公告是 Chromium 提示，不得当成页面故障。"""
    open_page(page, live_server + "/console/index.html")

    assert not page_audit.console_errors, (
        f"管理台首页本应只有 frame-ancestors 一条公告，实际还有 "
        f"{page_audit.console_errors}"
    )
    page_audit.assert_clean()
