# -*- coding: utf-8 -*-
"""
爬虫引擎模块

引擎注册表（按 list_type 分派）：
    static_html → spiders.static_list
    ajax_api   → spiders.ajax_api
    js_render  → spiders.js_render
    pdf_list   → spiders.pdf_list

URL 发现：
    spiders.url_resolver → URLResolver
"""

from spiders.engine import SpiderEngine, ENGINE_REGISTRY as SPIDER_ENGINE_REGISTRY, register_engine
from spiders.static_list import StaticListEngine, fetch_faculty_list, parse_faculty_html
from spiders.ajax_api import AjaxApiEngine, fetch_faculty_via_api
from spiders.detail_parser import DetailParserEngine, fetch_detail
from spiders.yzw_api import YzwEngine, YzwClient
from spiders.js_render import JSRenderEngine, fetch_faculty_via_playwright, fetch_faculty_via_playwright_with_detail
from spiders.pdf_list import PDFListEngine, parse_pdf_faculty_list, parse_pdf_file_local
from spiders.url_resolver import URLResolver, URLCandidate

# 引擎注册表：list_type → 获取函数
ENGINE_REGISTRY = {
    "static_html": fetch_faculty_list,
    "ajax_api": fetch_faculty_via_api,
    "js_render": fetch_faculty_via_playwright,
    "pdf_list": parse_pdf_faculty_list,
}

__all__ = [
    "SpiderEngine",
    "SPIDER_ENGINE_REGISTRY",
    "register_engine",
    "StaticListEngine",
    "AjaxApiEngine",
    "YzwEngine",
    "DetailParserEngine",
    "JSRenderEngine",
    "PDFListEngine",
    "YzwClient",
    "fetch_detail",
    "fetch_faculty_list",
    "parse_faculty_html",
    "fetch_faculty_via_api",
    "fetch_faculty_via_playwright",
    "fetch_faculty_via_playwright_with_detail",
    "parse_pdf_faculty_list",
    "parse_pdf_file_local",
    "URLResolver",
    "URLCandidate",
    "ENGINE_REGISTRY",
]
