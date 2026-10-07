# -*- coding: utf-8 -*-
"""
响应式回归：手机 375x812 与桌面 1440x900 两个视口跑全部页面
=============================================================
断言不出现横向溢出。溢出时逐个子元素量 scrollWidth / getBoundingClientRect，
把「是哪个元素顶出去了」连同它的宽度和右边界一起报出来——只报一句
「横向溢出了」等于没报。
"""

from __future__ import annotations

import pytest

from tests.browser.conftest import ALL_PAGES, PAGE_IDS, open_page

pytestmark = pytest.mark.browser

VIEWPORTS = [
    pytest.param({"width": 375, "height": 812}, id="mobile-375x812"),
    pytest.param({"width": 1440, "height": 900}, id="desktop-1440x900"),
]

# 允许 1px 的亚像素误差；超过就是真溢出
TOLERANCE_PX = 1

# 逐元素探测时最多列出多少个越界元素，够定位问题又不至于刷屏
MAX_REPORTED = 8


def _describe_element(el: dict) -> str:
    bits = [el["tag"].lower()]
    if el.get("id"):
        bits.append(f"#{el['id']}")
    if el.get("cls"):
        bits.append("." + ".".join(el["cls"].split()[:3]))
    if el.get("text"):
        text = " ".join(el["text"].split())[:30]
        bits.append(f'"{text}"')
    return (
        "".join(bits)
        + f"  right={el['right']}px  width={el['width']}px  scrollWidth={el['scrollWidth']}px"
    )


@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("path,container,group", ALL_PAGES, ids=PAGE_IDS)
def test_no_horizontal_overflow(page, page_audit, live_server, viewport, path, container, group):
    page.set_viewport_size(viewport)
    open_page(page, live_server + path)

    # 先查运行期故障再量布局：JS 抛异常中断渲染时，页面多半也还没布局完，
    # 那时报出来的溢出量是次生现象。先报根因。
    page_audit.assert_clean()

    report = page.evaluate(
        """(args) => {
            const [sel, tolerance] = args;
            const doc = document.documentElement;
            const overflow = doc.scrollWidth - doc.clientWidth;
            if (overflow <= tolerance) return {overflow: overflow, offenders: []};

            const offenders = [];
            for (const el of document.querySelectorAll('body *')) {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;
                const rect = el.getBoundingClientRect();
                if (rect.width === 0) continue;
                if (rect.right <= doc.clientWidth + tolerance) continue;
                offenders.push({
                    tag: el.tagName,
                    id: el.id || '',
                    cls: (typeof el.className === 'string') ? el.className : '',
                    text: (el.textContent || '').trim(),
                    right: Math.round(rect.right),
                    width: Math.round(rect.width),
                    scrollWidth: el.scrollWidth,
                });
            }
            offenders.sort((a, b) => b.right - a.right);
            return {overflow: overflow, offenders: offenders};
        }""",
        [container, TOLERANCE_PX],
    )

    assert report["overflow"] <= TOLERANCE_PX, (
        f"{path} 在 {viewport['width']}x{viewport['height']} 下横向溢出 "
        f"{report['overflow']}px（视口宽 {viewport['width']}px）。"
        f"越界最深的前 {MAX_REPORTED} 个元素：\n"
        + "\n".join(
            "    - " + _describe_element(el)
            for el in report["offenders"][:MAX_REPORTED]
        )
        + (f"\n    ... 共 {len(report['offenders'])} 个元素越界"
           if len(report["offenders"]) > MAX_REPORTED else "")
    )
