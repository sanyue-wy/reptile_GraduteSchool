"""PDF 名单解析引擎（pdf_list 型学院官网）

适用场景：学院官网以 PDF 公示名单形式发布教师信息。
典型场景：研究生院/学科建设处发布的"导师简介""师资队伍"PDF 文件。

使用 pdfplumber 解析 PDF 表格，识别"姓名/职称/研究方向"表头行，按表切列。
"""

import base64
import io
import logging
import re
from typing import Optional

from utils.http import PoliteSession
from utils.cache import CrawlCache
from spiders.engine import SpiderEngine, register_engine

logger = logging.getLogger(__name__)

# 常见表头行关键词（用于识别 PDF 中的表格）
TABLE_HEADER_KEYWORDS = ["姓名", "职称", "研究方向", "学位", "学历", "导师", "专业"]

# 受控职称词表
TITLE_VOCABULARY = {
    "教授", "副教授", "讲师", "助教",
    "研究员", "副研究员", "高级工程师",
    "博士生导师", "硕士生导师",
}


@register_engine
class PDFListEngine(SpiderEngine):
    name = "pdf_list"
    supported_source = "source_a"

    def fetch(self, url: str, *, force=False, **kwargs) -> list[dict]:
        return parse_pdf_faculty_list(self.session, url, cache=self.cache, force=force)

    def parse(self, html: bytes, selectors: dict, **kwargs) -> list[dict]:
        """PDF 的原始输入为 bytes；selectors 为统一接口保留参数。"""
        return _parse_pdf_bytes(html)


def parse_pdf_faculty_list(
    session: PoliteSession,
    pdf_url: str,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> list[dict]:
    """
    解析 PDF 公示名单，提取教师信息。

    Args:
        session: PoliteSession 实例
        pdf_url: PDF 文件 URL
        cache: CrawlCache 实例
        force: True 时忽略缓存强制重新下载

    Returns:
        list[dict]: 每条包含 name, title, research_areas 等字段
    """
    def _do_fetch() -> bytes:
        resp = session.get(pdf_url)
        return resp.content

    if cache is not None:
        # CrawlCache 只存 UTF-8 文本，不能直接传 PDF bytes。
        # 使用独立、带版本的键，避免与旧 URL 对应的文本缓存互相污染。
        def _fetch_encoded() -> str:
            return base64.b64encode(_do_fetch()).decode("ascii")

        encoded = cache.get_or_fetch(_fetch_encoded, f"pdf_list:base64:v1:{pdf_url}", force=force)
        pdf_bytes = base64.b64decode(encoded, validate=True)
    else:
        pdf_bytes = _do_fetch()

    return _parse_pdf_bytes(pdf_bytes)


def parse_pdf_file_local(
    session: PoliteSession,
    pdf_path: str,
) -> list[dict]:
    """
    解析本地 PDF 文件（用于离线验证）。

    Args:
        session: PoliteSession 实例（用于一致性）
        pdf_path: 本地 PDF 文件路径

    Returns:
        list[dict]: 教师记录列表
    """
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    return _parse_pdf_bytes(pdf_bytes)


def _parse_pdf_bytes(pdf_bytes: bytes) -> list[dict]:
    """
    核心 PDF 解析逻辑。

    Args:
        pdf_bytes: PDF 文件字节

    Returns:
        list[dict]: 每条包含 name, title, research_areas 等字段
    """
    import pdfplumber  # 可选依赖：仅解析 PDF 字节时加载

    results = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            if not tables:
                # 尝试提取文本
                text = page.extract_text()
                if text:
                    results.extend(_parse_text_lines(text, page_num))
                continue

            for table in tables:
                parsed = _parse_table(table, page_num)
                results.extend(parsed)

    # 去重
    seen = set()
    unique_results = []
    for r in results:
        name = r.get("name", "")
        if name and name not in seen:
            seen.add(name)
            unique_results.append(r)

    logger.info("PDF 解析完成，共提取 %d 位教师", len(unique_results))
    return unique_results


def _parse_table(table: list[list[str]], page_num: int) -> list[dict]:
    """
    解析 PDF 表格。

    Args:
        table: pdfplumber 提取的表格（list of rows, each row is list of cells）
        page_num: 页码

    Returns:
        list[dict]: 教师记录
    """
    if not table or len(table) < 2:
        return []

    # 识别表头行
    header_row_idx = None
    header_cols = {}
    for i, row in enumerate(table):
        row_text = " ".join(str(cell) for cell in row if cell)
        if any(kw in row_text for kw in TABLE_HEADER_KEYWORDS):
            header_row_idx = i
            # 识别每列含义
            for j, cell in enumerate(row):
                if cell:
                    header_cols[j] = cell.strip()
            break

    if header_row_idx is None:
        # 无明确表头，尝试按列位置推断
        return _parse_table_no_header(table)

    # 解析数据行
    results = []
    name_col = _find_name_column(header_cols)
    title_col = _find_title_column(header_cols)
    research_col = _find_research_column(header_cols)

    for row in table[header_row_idx + 1:]:
        if not row or all(not cell for cell in row):
            continue

        teacher = {}
        if name_col is not None and name_col < len(row):
            teacher["name"] = str(row[name_col]).strip()
        if title_col is not None and title_col < len(row):
            teacher["title"] = str(row[title_col]).strip()
        if research_col is not None and research_col < len(row):
            research = str(row[research_col]).strip()
            teacher["research_areas"] = _split_research(research)

        if teacher.get("name"):
            results.append(teacher)

    return results


def _parse_table_no_header(table: list[list[str]]) -> list[dict]:
    """无明确表头的表格：按列位置推断（姓名在左列，职称在右列）。"""
    results = []
    for row in table:
        if len(row) >= 2:
            name = str(row[0]).strip()
            title = str(row[1]).strip() if len(row) > 1 else ""
            if name and len(name) <= 10:  # 姓名长度限制
                teacher = {"name": name}
                if title:
                    teacher["title"] = title
                results.append(teacher)
    return results


def _parse_text_lines(text: str, page_num: int) -> list[dict]:
    """从 PDF 文本中提取教师信息（适用于无表格的纯文本 PDF）。"""
    results = []
    # 按行解析，寻找"姓名+职称"模式
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # 尝试匹配"姓名 职称 研究方向"模式
        teacher = _parse_text_line(line)
        if teacher:
            results.append(teacher)
    return results


def _parse_text_line(line: str) -> Optional[dict]:
    """从单行文本解析教师信息。"""
    # 常见模式：姓名 职称 研究方向
    # 匹配以教授/副教授/讲师/研究员结尾或包含的行
    # Longest titles first: 教授 is a substring of 副教授, and the
    # vocabulary is a set whose iteration order varies across processes.
    for title in sorted(TITLE_VOCABULARY, key=lambda value: (-len(value), value)):
        if title in line:
            parts = line.split(title)
            name = parts[0].strip() if parts else ""
            if name and len(name) <= 10:
                return {"name": name, "title": title}
    return None


def _find_name_column(headers: dict) -> Optional[int]:
    """识别姓名列。"""
    for col, header in headers.items():
        if any(kw in header for kw in ["姓名", "名称", "名字", "姓名/名称", "Name", "name"]):
            return col
    # 默认第一列
    return 0 if headers else None


def _find_title_column(headers: dict) -> Optional[int]:
    """识别职称列。"""
    for col, header in headers.items():
        if any(kw in header for kw in ["职称", "职务", "等级", "Title", "title", "职务/职称"]):
            return col
    return None


def _find_research_column(headers: dict) -> Optional[int]:
    """识别研究方向列。"""
    for col, header in headers.items():
        if any(kw in header for kw in ["研究方向", "研究领域", "研究方向/领域", "Research"]):
            return col
    return None


def _split_research(text: str) -> list[str]:
    """拆分研究方向文本。"""
    import re
    parts = re.split(r"[；;、，,\n]+", text)
    return [p.strip() for p in parts if p.strip()]
