# -*- coding: utf-8 -*-
"""
导出管道
========
把合并后的导师数据导出为：
1. data/output/{学校}_{学院}.jsonl  —— 分校分院明细
2. data/output/summary.xlsx        —— 全校汇总表（Excel）
3. data/output/failures.json       —— 失败记录清单
"""

import json
import logging
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .merge import to_summary_row

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/output")


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def export_merged(merged_records: list[dict], output_dir: Path = OUTPUT_DIR) -> dict[str, int]:
    """
    按学校+学院分组写出 JSONL 文件。

    Args:
        merged_records: merge_pair() 产出的统一 Schema 记录列表
        output_dir: 输出目录

    Returns:
        {"files_written": N, "total_records": M}
    """
    ensure_output_dir()

    # 按学校+学院分组
    groups: dict[str, list[dict]] = {}
    for rec in merged_records:
        key = f"{rec.get('university', '未知')}_{rec.get('college', '未知')}"
        groups.setdefault(key, []).append(rec)

    files_written = 0
    total_records = 0

    for key, records in groups.items():
        safe_key = key.replace("/", "_").replace("\\", "_")
        out_path = output_dir / f"{safe_key}.jsonl"
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        files_written += 1
        total_records += len(records)
        logger.info("已写出 %d 条记录到 %s", len(records), out_path)

    return {"files_written": files_written, "total_records": total_records}


def export_summary(merged_records: list[dict], output_path: Path = OUTPUT_DIR / "summary.xlsx") -> int:
    """
    生成全校汇总 Excel 表格。

    列顺序：学校、学院、姓名、职称、招生状态、招生方向、研究方向、来源链接
    """
    ensure_output_dir()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "导师汇总"

    # 表头
    headers = ["学校", "学院", "姓名", "职称", "招生状态", "招生方向", "研究方向", "来源链接"]
    ws.append(headers)

    # 样式
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
    wrap_alignment = Alignment(wrap_text=True, vertical="top")

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # 数据行
    row_idx = 2
    for rec in merged_records:
        row_data = to_summary_row(rec)
        ws.append([
            row_data["学校"],
            row_data["学院"],
            row_data["姓名"],
            row_data["职称"],
            row_data["招生状态"],
            row_data["招生方向"],
            row_data["研究方向"],
            row_data["来源链接"],
        ])
        # 设置换行
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=row_idx, column=col_idx).alignment = wrap_alignment
        row_idx += 1

    # 列宽自适应
    column_widths = [18, 18, 12, 10, 10, 40, 40, 50]
    for i, width in enumerate(column_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # 冻结首行
    ws.freeze_panes = "A2"

    # 保存
    wb.save(output_path)
    logger.info("已生成汇总表 %s，共 %d 行", output_path, len(merged_records))
    return len(merged_records)


def export_failures(failures: list[dict], output_path: Path = OUTPUT_DIR / "failures.json") -> int:
    """
    导出失败记录 JSON。

    Args:
        failures: 失败记录列表，每项包含 id, school, college, source, error_type,
                  error_message, url, occurred_at, retry_count, status
        output_path: 输出路径

    Returns:
        写入的记录数
    """
    ensure_output_dir()

    # 按错误类型统计
    summary = {"http_error": 0, "timeout": 0, "parse_error": 0, "dns_error": 0, "other": 0}
    for f in failures:
        et = f.get("error_type", "other")
        if et in summary:
            summary[et] += 1
        else:
            summary["other"] += 1

    data = {
        "total": len(failures),
        "summary": summary,
        "items": failures,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("已写出 %d 条失败记录到 %s", len(failures), output_path)
    return len(failures)


def load_failures(input_path: Path = OUTPUT_DIR / "failures.json") -> list[dict]:
    """读取现有失败记录。"""
    if not input_path.exists():
        return []
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", [])
    except Exception as e:
        logger.warning("读取失败记录失败: %s", e)
        return []


def add_failure(
    failure_id: str,
    school: str,
    college: str,
    source: str,
    error_type: str,
    error_message: str,
    url: str,
    retry_count: int = 0,
    status: str = "active",
) -> dict:
    """创建一条失败记录（供爬虫调用）。"""
    from datetime import datetime
    return {
        "id": failure_id,
        "school": school,
        "college": college,
        "source": source,
        "error_type": error_type,
        "error_message": error_message,
        "url": url,
        "occurred_at": datetime.now().isoformat(),
        "retry_count": retry_count,
        "status": status,  # active / resolved / ignored
    }


def update_failure_status(failure_id: str, status: str, output_path: Path = OUTPUT_DIR / "failures.json") -> bool:
    """更新失败记录状态（resolved/ignored）。"""
    failures = load_failures(output_path)
    for f in failures:
        if f["id"] == failure_id:
            f["status"] = status
            export_failures(failures, output_path)
            return True
    return False


def get_active_failures(output_path: Path = OUTPUT_DIR / "failures.json") -> list[dict]:
    """获取所有 active 状态的失败记录（供重试使用）。"""
    return [f for f in load_failures(output_path) if f.get("status") == "active"]


def clear_failure(failure_id: str, output_path: Path = OUTPUT_DIR / "failures.json") -> bool:
    """删除一条失败记录（忽略后可选清理）。"""
    failures = load_failures(output_path)
    original_len = len(failures)
    failures = [f for f in failures if f["id"] != failure_id]
    if len(failures) < original_len:
        export_failures(failures, output_path)
        return True
    return False