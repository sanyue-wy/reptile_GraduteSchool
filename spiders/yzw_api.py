# -*- coding: utf-8 -*-
"""
研招网 API 爬虫客户端
====================
封装研招网 (yz.chsi.com.cn) 的两个核心接口：
1. 学校代码查找：GET /zsml/querySchAction.do?dwmc=<学校名>
2. 专业目录爬取：POST /zsml/rs/dws.do （分页 + 参数构造）

遵循 INTERFACE_SPEC.md §2.1 Spider 层约定：
- 复用 PoliteSession 发请求（限速、重试、UA 轮换）
- 复用 CrawlCache 页面缓存
- 原件落盘到 data/raw/{university}/{year}/yzw/major_{school_code}.json
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional, List, Dict

from utils.http import PoliteSession
from utils.cache import CrawlCache
from spiders.engine import SpiderEngine, register_engine

logger = logging.getLogger(__name__)

BASE_URL = "https://yz.chsi.com.cn"
SCHOOL_CODE_URL = f"{BASE_URL}/zsml/querySchAction.do"
MAJOR_DIR_URL = f"{BASE_URL}/zsml/rs/dws.do"
EXAM_SUBJECTS_URL = f"{BASE_URL}/zsml/kskm.do"


@register_engine
class YzwEngine(SpiderEngine):
    """组合原有客户端，保留其分页、专业过滤和原件保存行为。"""

    name = "yzw_api"
    supported_source = "source_b"

    def __init__(self, session, cache=None):
        super().__init__(session, cache)
        self._client = YzwClient(session, cache)

    def fetch(self, url: str = "", *, school_code: str, year: int,
              major_codes=None, category=None, university=None, **kwargs) -> list[dict]:
        return self._client.fetch_major_directory(
            school_code, year, major_codes, category, university,
        )

    def parse(self, html: str, selectors: dict, **kwargs) -> list[dict]:
        """目录结构由 parsers.yzw_major 处理，按契约保留空实现。"""
        return []


class YzwClient:
    """研招网学校代码查询 + 专业目录爬取客户端。"""

    BASE_URL = BASE_URL

    def __init__(self, session: PoliteSession, cache: Optional[CrawlCache] = None):
        self.session = session
        self.cache = cache
        self._school_code_cache: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # 学校代码查找
    # ------------------------------------------------------------------

    def get_school_code(self, university: str) -> Optional[str]:
        """查找研招网学校代码。

        优先读内存缓存，无则请求 /zsml/querySchAction.do?dwmc=<学校名>，
        解析返回 HTML 中的学校链接提取 dwdm。

        Args:
            university: 学校名称（如 "东南大学"）

        Returns:
            学校代码字符串（如 "10213"），未找到返回 None
        """
        if university in self._school_code_cache:
            return self._school_code_cache[university]

        logger.info("查找学校代码：%s", university)
        resp = self.session.get(
            SCHOOL_CODE_URL,
            params={"dwmc": university},
            save_raw=True,
        )

        # 响应 HTML 包含形如
        #   <a href="/zsml/querySchAction.do?dwdm=10213&dlmc=...">东南大学</a>
        # 或  <a href="/zsml/rs/dws.do?dwdm=10213&...">东南大学</a>
        from utils.http import response_text
        html = response_text(resp)
        pattern = re.compile(
            r'dwdm=([^&"\']+)[^>]*>([^<]*)</a>',
            re.IGNORECASE,
        )
        for m in pattern.finditer(html):
            code, name = m.group(1).strip(), m.group(2).strip()
            if university in name or name in university:
                self._school_code_cache[university] = code
                logger.info("匹配到学校代码：%s -> %s", university, code)
                return code

        # 兜底：匹配第一个 dwdm
        first_match = re.search(r'dwdm=([^&"\']+)', html)
        if first_match:
            code = first_match.group(1).strip()
            self._school_code_cache[university] = code
            logger.info("未精确匹配，取第一个结果：%s -> %s", university, code)
            return code

        logger.warning("未找到学校代码：%s", university)
        return None

    # ------------------------------------------------------------------
    # 专业目录爬取
    # ------------------------------------------------------------------

    def fetch_major_directory(
        self,
        school_code: str,
        year: int,
        major_codes: Optional[List[str]] = None,
        category: Optional[str] = None,
        university: Optional[str] = None,
    ) -> List[Dict]:
        """抓取研招网专业目录完整数据。

        遍历 category 对应的一级学科代码列表，POST /zsml/rs/dws.do，
        自动分页获取全部结果，过滤并返回原始记录列表。

        Args:
            school_code: 研招网学校代码（如 "10213"）
            year: 年份（如 2026），用于 raw 文件路径
            major_codes: 专业代码白名单（6 位）。None 表示全专业。
            category: 学科分类（"mechanical" / "automation"），用于映射 yjxkdm。
            university: 学校名称，用于 raw 文件路径。

        Returns:
            研招网原始记录列表，每项含 dwmc, yjfxmc, zdjs, zydm, nzsrsstr, kskm 等字段
        """
        # 确定一级学科代码列表
        if category:
            from config.major_mapping import get_major_codes
            yjxkdm_list = get_major_codes(category, level="first_level")
        elif major_codes:
            # 从专业代码推导一级学科代码（前 4 位）
            yjxkdm_list = sorted({mc[:4] for mc in major_codes if len(mc) >= 4})
        else:
            logger.warning("未提供 category 或 major_codes，无法确定 yjxkdm，跳过")
            return []

        if not yjxkdm_list:
            logger.warning("category=%s 未匹配到 yjxkdm，跳过", category)
            return []

        all_records: List[Dict] = []
        for yjxkdm in yjxkdm_list:
            records = self._fetch_one_discipline(
                school_code=school_code,
                university=university or "",
                year=year,
                yjxkdm=yjxkdm,
            )
            all_records.extend(records)
            logger.info("yjxkdm=%s 获取 %d 条记录", yjxkdm, len(records))

        # 专业代码过滤
        if major_codes:
            filtered = [r for r in all_records if r.get("zydm", "") in major_codes]
            logger.info("按 major_codes 过滤：%d -> %d", len(all_records), len(filtered))
            all_records = filtered

        # 保存合并后的原件
        if university:
            self._save_raw_merged(university, year, school_code, all_records)

        logger.info("总计获取 %d 条专业目录记录", len(all_records))
        return all_records

    def _fetch_one_discipline(
        self,
        school_code: str,
        university: str,
        year: int,
        yjxkdm: str,
    ) -> List[Dict]:
        """抓取单个一级学科下的所有专业记录（自动分页）。"""
        # 门类代码：工学 = 08
        params = {
            "dwmc": university,
            "dwdm": school_code,
            "mldm": "08",
            "mlmc": "工学",
            "yjxkdm": yjxkdm,
            "zymc": "",
            "xxfs": "1",    # 全日制
            "tydxs": "",
            "jsggjh": "",
            "start": 0,
            "pageSize": 500,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        # 第一页获取 total
        resp = self.session.post(
            MAJOR_DIR_URL,
            data=params,
            extra_headers=headers,
            save_raw=False,
        )
        try:
            data = resp.json()
        except Exception:
            logger.warning("yjxkdm=%s 响应非 JSON，跳过", yjxkdm)
            return []

        total = data.get("total", 0)
        items = data.get("data", [])
        all_items = list(items)

        # 分页（如果 total > pageSize，继续获取）
        page_size = params["pageSize"]
        fetched = len(items)
        while fetched < total:
            params["start"] = fetched
            resp = self.session.post(
                MAJOR_DIR_URL,
                data=params,
                extra_headers=headers,
                save_raw=False,
            )
            try:
                data = resp.json()
            except Exception:
                logger.warning("yjxkdm=%s 分页响应非 JSON，停止分页", yjxkdm)
                break
            items = data.get("data", [])
            all_items.extend(items)
            fetched += len(items)
            if not items:
                break

        logger.info("yjxkdm=%s 共获取 %d 条（total=%d）", yjxkdm, len(all_items), total)
        return all_items

    def _save_raw_merged(
        self,
        university: str,
        year: int,
        school_code: str,
        records: List[Dict],
    ) -> None:
        """保存合并后的原始记录到 data/raw/{university}/{year}/yzw/major_{school_code}.json。"""
        raw_dir = Path("data") / "raw" / university / str(year) / "yzw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / f"major_{school_code}.json"
        payload = {
            "total": len(records),
            "data": records,
        }
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        logger.info("原件已保存：%s（%d 条）", raw_path, len(records))

    # ------------------------------------------------------------------
    # 考试科目（可选 API）
    # ------------------------------------------------------------------

    def fetch_exam_subjects(
        self,
        school_code: str,
        major_code: str,
    ) -> List[str]:
        """获取指定专业的考试科目列表。"""
        params = {
            "dwdm": school_code,
            "zydm": major_code,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
        }
        resp = self.session.post(
            EXAM_SUBJECTS_URL,
            data=params,
            extra_headers=headers,
            save_raw=True,
        )
        try:
            data = resp.json()
        except Exception:
            logger.warning("考试科目接口响应非 JSON")
            return []

        subjects = []
        for item in data.get("data", []):
            km = (item.get("kmmc") or "").strip()
            km_code = (item.get("kmdm") or "").strip()
            if km:
                subjects.append(f"{km_code} {km}" if km_code else km)
        return subjects
