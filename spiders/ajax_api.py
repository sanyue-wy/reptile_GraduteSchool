# -*- coding: utf-8 -*-
"""
AJAX API 师资列表解析器（SudyCMS/WebPlus 平台）
=================================================
适用场景：教师列表通过 JS 动态加载，底层调用 generalQuery JSON API。
典型代表：东大自动化学院 automation.seu.edu.cn。

若其他高校使用同建站平台（WebPlus/SudyCMS），可整段复用。
"""

import json
import logging
from typing import Optional

from utils.http import PoliteSession
from utils.cache import CrawlCache
from spiders.engine import SpiderEngine, register_engine

logger = logging.getLogger(__name__)

# SudyCMS generalQuery 默认参数模板
_DEFAULT_PARAMS = {
    "pageIndex": "1",
    "rows": "999",
    "conditions": '[{"field":"published","value":"1","judge":"="}]',
    "orders": '[{"field":"letter","type":"asc"}]',
    "returnInfos": (
        '[{"field":"title","name":"title"},'
        '{"field":"exField1","name":"exField1"},'
        '{"field":"degree","name":"degree"},'
        '{"field":"post","name":"post"},'
        '{"field":"cnUrl","name":"cnUrl"},'
        '{"field":"headerPic","name":"headerPic"}]'
    ),
    "articleType": "1",
    "level": "1",
}


@register_engine
class AjaxApiEngine(SpiderEngine):
    """SudyCMS JSON 接口适配器。"""

    name = "ajax_api"
    supported_source = "source_a"

    def fetch(self, url: str, *, site_id: str, referer: str, extra_params=None,
              force=False, **kwargs) -> list[dict]:
        return fetch_faculty_via_api(
            self.session, url, site_id, referer, extra_params,
            cache=self.cache, force=force,
        )

    def parse(self, html: str, selectors: dict, *, api_url="", base_url="", **kwargs) -> list[dict]:
        """解析 JSON 文本或已解码对象；API 字段固定，不使用 CSS selectors。"""
        data = json.loads(html) if isinstance(html, (str, bytes, bytearray)) else html
        return _parse_api_data(data, api_url or base_url or kwargs.get("url", ""))


def fetch_faculty_via_api(
    session: PoliteSession,
    api_url: str,
    site_id: str,
    referer: str,
    extra_params: Optional[dict] = None,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> list[dict]:
    """
    调用 SudyCMS generalQuery API 获取教师列表。

    Args:
        session: PoliteSession 实例
        api_url: API 地址（如 https://xxx.seu.edu.cn/_wp3services/generalQuery?queryObj=teacherHome）
        site_id: WebPlus 站点 ID（如 "338"）
        referer: 请求 Referer 头（列表页 URL）
        extra_params: 覆盖/追加默认参数（如 conditions 过滤博导）
        cache: CrawlCache 实例（提供时命中缓存则跳过网络请求）
        force: True 时忽略缓存强制重新抓取

    Returns:
        list[dict]: 每条包含 name, title(职称), degree(学位),
                    advisor_tags(exField1 原始值), profile_url, photo_url
    """
    params = dict(_DEFAULT_PARAMS)
    params["siteId"] = site_id
    if extra_params:
        params.update(extra_params)

    headers = {
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
    }

    def _do_fetch() -> str:
        return session.post(api_url, data=params, extra_headers=headers).text

    if cache is not None:
        text = cache.get_or_fetch(_do_fetch, api_url, force=force)
        data = json.loads(text)
    else:
        resp = session.post(api_url, data=params, extra_headers=headers)
        data = resp.json()

    return _parse_api_data(data, api_url)


def _parse_api_data(data: dict, api_url: str) -> list[dict]:
    """fetch 和离线 parse 共用同一条教师转换链。"""
    total = data.get("total", 0)
    items = data.get("data", [])
    logger.info("API 返回 total=%d, 实际 %d 条", total, len(items))

    results = []
    for item in items:
        teacher = _parse_teacher_item(item, api_url)
        if teacher:
            results.append(teacher)

    logger.info("解析到 %d 位教师", len(results))
    return results


def _parse_teacher_item(item: dict, api_url: str) -> Optional[dict]:
    """解析单条教师 API 返回数据。"""
    name = (item.get("title") or "").strip()
    if not name:
        return None

    # 从 API URL 推导 base_url
    from urllib.parse import urlparse
    p = urlparse(api_url)
    base_url = f"{p.scheme}://{p.netloc}" if p.netloc else ""

    profile_url = item.get("cnUrl", "")
    if profile_url and not profile_url.startswith("http"):
        profile_url = base_url + profile_url

    photo_url = item.get("headerPic", "")
    if photo_url and not photo_url.startswith("http"):
        photo_url = base_url + photo_url

    # exField1 可能是 "博士生导师,硕士生导师,全体教师" 这样的逗号分隔值
    raw_tags = (item.get("exField1") or "").strip()

    result = {
        "name": name,
        "title": (item.get("post") or "").strip(),  # 职称
        "degree": (item.get("degree") or "").strip(),  # 学位
        "advisor_tags_raw": raw_tags,
        "advisor_level": _parse_advisor_level(raw_tags),
        "profile_url": profile_url,
        "photo_url": photo_url,
    }
    return result


def _parse_advisor_level(raw_tags: str) -> str:
    """从 exField1 字段解析博导/硕导身份。"""
    tags = [t.strip() for t in raw_tags.split(",")]
    levels = []
    if any("博士生导师" in t for t in tags):
        levels.append("博导")
    if any("硕士生导师" in t for t in tags):
        levels.append("硕导")
    return "/".join(levels) if levels else ""
