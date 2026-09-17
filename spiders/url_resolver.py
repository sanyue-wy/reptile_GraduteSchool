"""URL 自动发现流水线

根据学校和学院名称，自动发现真实的师资列表页 URL。

流程：
    ① 站点搜索（DuckDuckGo + Bing）
    ② 链接挖掘（学校主页导航栏）
    ③ 特征打分（教师卡 / AJAX / JS渲染 / PDF）
    ④ 连通性探测
    ⑤ 候选落盘待人工确认（不自动写回 school_data.json）
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urljoin
from datetime import datetime

from utils.http import PoliteSession
from utils.cache import CrawlCache

logger = logging.getLogger(__name__)

# 候选文件存放目录
CANDIDATES_DIR = Path("data/candidates")

# 搜索引擎端点
DDG_HTML_ENDPOINT = "https://html.duckduckgo.com/html/"
BING_SEARCH_ENDPOINT = "https://www.bing.com/search"

# 关键词：用于识别师资页
FACULTY_KEYWORDS = [
    "师资", "教师", "教员", "faculty", "teacher", "instructor",
    "教授", "副教授", "讲师", "导师",
]

# 路径关键词：URL 路径中包含这些词大概率是师资页
PATH_FACULTY_KEYWORDS = [
    "szdw", "rsgz", "teacher", "faculty", "staff",
    "师资", "教师", "professor", "facultypage",
    "teacherHome", "teacherList", "facultyList",
]

# 教师卡特征标记（页面文本中出现这些词的概率高 → 强正分）
TEACHER_CARD_MARKERS = [
    "jsbt", ".name", "职称", "教授", "副教授", "讲师",
    "研究方向", "学历", "学位", "post", "degree",
]

# AJAX 接口特征标记
AJAX_MARKERS = [
    "generalQuery", "queryObj=teacherHome", "pageIndex",
    "rows=", "conditions", "returnInfos",
]

# JS 渲染特征标记
JS_RENDER_MARKERS = [
    "<canvas", "react", "vue", "angular",
    "window.__INITIAL_STATE__", "ssr",
    "data-react-", "data-v-",
]

# PDF 名单特征标记
PDF_MARKERS = [
    ".pdf", "师资", "教师名录", "名单",
]


class URLCandidate:
    """单个候选 URL。"""

    def __init__(
        self,
        url: str,
        score: float = 0.0,
        list_type: str = "static_html",
        source: str = "unknown",
        title: str = "",
        markers: list[str] = None,
    ):
        self.url = url
        self.score = score
        self.list_type = list_type
        self.source = source
        self.title = title
        self.markers = markers or []
        self.reachable: Optional[bool] = None
        self.status_code: Optional[int] = None
        self.discovered_at: str = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "score": self.score,
            "list_type": self.list_type,
            "source": self.source,
            "title": self.title,
            "markers": self.markers,
            "reachable": self.reachable,
            "status_code": self.status_code,
            "discovered_at": self.discovered_at,
        }


class URLResolver:
    """URL 自动发现流水线。

    输入：university + college 名称。
    输出：带置信度的候选 URL 列表，落盘到 data/candidates/ 等待人工确认。
    """

    def __init__(
        self,
        session: Optional[PoliteSession] = None,
        cache: Optional[CrawlCache] = None,
    ):
        self.session = session or PoliteSession()
        self.cache = cache or CrawlCache(max_age_days=7)

    def resolve(
        self,
        university: str,
        college: str,
        category: str = "mechanical",
    ) -> list[URLCandidate]:
        """
        执行完整的 URL 发现流水线。

        Args:
            university: 学校名称（如 "东南大学"）
            college: 学院名称（如 "机械工程学院"）
            category: 学科分类

        Returns:
            list[URLCandidate]: 按 score 降序排列的候选列表
        """
        logger.info("开始 URL 发现：%s / %s", university, college)

        # ① 站点搜索
        search_candidates = self._search(university, college)
        logger.info("搜索引擎发现 %d 个候选", len(search_candidates))

        # ② 链接挖掘
        link_candidates = self._mine_links(university, college)
        logger.info("站内链接挖掘发现 %d 个候选", len(link_candidates))

        # 合并去重
        all_candidates = self._merge_candidates(search_candidates + link_candidates)

        # ③ 特征打分
        for candidate in all_candidates:
            self._score_candidate(candidate, university, college)

        # ④ 连通性探测
        self._probe_candidates(all_candidates)

        # 按分数降序排列
        all_candidates.sort(key=lambda c: c.score, reverse=True)

        # ⑤ 落盘待人工确认
        self._save_candidates(university, college, all_candidates)

        logger.info("URL 发现完成：%d 个候选，最高分 %.2f",
                     len(all_candidates),
                     all_candidates[0].score if all_candidates else 0)

        return all_candidates

    # ------------------------------------------------------------------
    # ① 站点搜索
    # ------------------------------------------------------------------

    def _search(self, university: str, college: str) -> list[URLCandidate]:
        """通过搜索引擎搜索师资页 URL。"""
        query = f"{university} {college} 师资队伍"
        candidates = []

        for engine_name, endpoint in [("duckduckgo", DDG_HTML_ENDPOINT), ("bing", BING_SEARCH_ENDPOINT)]:
            try:
                html = self._fetch_search_results(endpoint, query, engine_name)
                urls = self._extract_urls_from_html(html, engine_name)
                for url in urls:
                    candidates.append(URLCandidate(
                        url=url,
                        source=f"search_{engine_name}",
                    ))
            except Exception as e:
                logger.warning("%s 搜索失败：%s", engine_name, e)

        return candidates

    def _fetch_search_results(self, endpoint: str, query: str, engine: str) -> str:
        """抓取搜索引擎结果页。"""
        if engine == "duckduckgo":
            resp = self.session.get(endpoint, params={"q": query})
        else:
            resp = self.session.get(endpoint, params={"q": query})
        from utils.http import response_text
        return response_text(resp)

    def _extract_urls_from_html(self, html: str, engine: str) -> list[str]:
        """从搜索结果 HTML 中提取 .edu.cn 链接。"""
        urls = []
        # 简单的正则提取
        found = re.findall(r'href="(https?://[^"\']+\.edu\.cn[^"]*)"', html)
        for url in found:
            # 只保留包含师资关键词的 URL
            if any(kw in url.lower() for kw in PATH_FACULTY_KEYWORDS):
                urls.append(url)
        return urls

    # ------------------------------------------------------------------
    # ② 链接挖掘
    # ------------------------------------------------------------------

    def _mine_links(self, university: str, college: str) -> list[URLCandidate]:
        """从学校主页导航栏挖掘师资页链接。"""
        candidates = []
        # 尝试常见学校域名格式
        domain_patterns = [
            f"{university.split('大学')[0].lower()}.edu.cn",
            f"{university.lower().replace('大学', 'daxue')}.edu.cn",
        ]

        for domain in domain_patterns:
            try:
                homepage_url = f"https://{domain}"
                from utils.http import response_text
                html = response_text(self.session.get(homepage_url))
                links = self._extract_faculty_links(html, homepage_url)
                for link in links:
                    candidates.append(URLCandidate(
                        url=link,
                        source="homepage_navigation",
                    ))
            except Exception as e:
                logger.warning("主页挖掘失败 %s: %s", domain, e)

        return candidates

    def _extract_faculty_links(self, html: str, base_url: str) -> list[str]:
        """从 HTML 中提取含师资关键词的链接。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if any(kw in text for kw in FACULTY_KEYWORDS) or \
               any(kw in href.lower() for kw in PATH_FACULTY_KEYWORDS):
                full_url = urljoin(base_url, href)
                if full_url not in links:
                    links.append(full_url)
        return links

    # ------------------------------------------------------------------
    # ③ 特征打分
    # ------------------------------------------------------------------

    def _score_candidate(self, candidate: URLCandidate, university: str, college: str):
        """对候选 URL 进行特征打分。"""
        try:
            from utils.http import response_text
            html = response_text(self.session.get(candidate.url))
        except Exception:
            return

        score = 0.0
        markers = []

        # 教师卡特征 → 强正分
        for marker in TEACHER_CARD_MARKERS:
            if marker.lower() in html.lower():
                score += 2.0
                markers.append(f"teacher_card:{marker}")

        # AJAX 接口特征
        for marker in AJAX_MARKERS:
            if marker.lower() in html.lower() or marker.lower() in candidate.url.lower():
                score += 1.5
                markers.append(f"ajax:{marker}")
                candidate.list_type = "ajax_api"

        # JS 渲染特征
        for marker in JS_RENDER_MARKERS:
            if marker.lower() in html.lower():
                score += 1.0
                markers.append(f"js_render:{marker}")
                candidate.list_type = "js_render"

        # 页面标题包含学校/学院名称 → 正分
        if university.lower() in html.lower() or college.lower() in html.lower():
            score += 1.0
            markers.append("title_match")

        # 路径包含师资关键词 → 正分
        path = urlparse(candidate.url).path.lower()
        for kw in PATH_FACULTY_KEYWORDS:
            if kw.lower() in path:
                score += 1.5
                markers.append(f"path:{kw}")
                break

        candidate.score = score
        candidate.markers = markers

    # ------------------------------------------------------------------
    # ④ 连通性探测
    # ------------------------------------------------------------------

    def _probe_candidates(self, candidates: list[URLCandidate]):
        """验证候选 URL 是否可达。"""
        for candidate in candidates:
            try:
                resp = self.session.get(candidate.url)
                candidate.reachable = resp.status_code == 200
                candidate.status_code = resp.status_code
            except Exception:
                candidate.reachable = False
                candidate.status_code = None

    # ------------------------------------------------------------------
    # ⑤ 候选落盘
    # ------------------------------------------------------------------

    def _save_candidates(
        self,
        university: str,
        college: str,
        candidates: list[URLCandidate],
    ):
        """将候选列表落盘到 data/candidates/ 目录。"""
        CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{university}_{college}_candidates.json"
        filepath = CANDIDATES_DIR / filename

        data = {
            "university": university,
            "college": college,
            "discovered_at": datetime.now().isoformat(),
            "candidates": [c.to_dict() for c in candidates],
            "summary": {
                "total": len(candidates),
                "reachable": sum(1 for c in candidates if c.reachable),
                "top_score": candidates[0].score if candidates else 0,
            },
        }

        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("候选已落盘：%s", filepath)

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_candidates(candidates: list[URLCandidate]) -> list[URLCandidate]:
        """合并去重候选列表。"""
        seen = set()
        unique = []
        for c in candidates:
            if c.url not in seen:
                seen.add(c.url)
                unique.append(c)
        return unique
