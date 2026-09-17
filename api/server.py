#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API 服务层
================
提供前端 Dashboard 所需的全部 17 个 REST 接口。
"""

import json
import logging
import os
import queue
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Optional

from flask import Flask, jsonify, request, send_file, abort

# 本地模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.school_level_raw import get_school_level, SCHOOLS_SHUANGYILIU, SCHOOLS_211, SCHOOLS_985
from pipelines.export import (
    load_failures,
    export_failures,
    update_failure_status,
    get_active_failures,
    clear_failure,
)
from pipelines.merge import merge_sources, _read_jsonl
from utils.progress import get_progress_tracker, ProgressTracker

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=str(Path(__file__).parent.parent / "dashboard"))

# 全局配置落盘路径（模块级常量，测试可 monkeypatch 以避免污染真实配置）
GLOBAL_CONFIG_PATH = Path("config/global.json")

# ------------------------------------------------------------------
# 前端静态托管：同源提供 dashboard 页面，避免 CORS / Mock 回退
# / 与 /dashboard/ 均指向 dashboard 目录；/api/* 由注册的路由优先匹配
# ------------------------------------------------------------------
_DASHBOARD_DIR = (Path(__file__).parent.parent / "dashboard").resolve()

# ------------------------------------------------------------------
# 全局状态：任务队列（内存存储，生产环境可改用 Redis）
# ------------------------------------------------------------------
_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()


def _new_task_id() -> str:
    return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _get_task(task_id: str) -> Optional[dict]:
    with _tasks_lock:
        return _tasks.get(task_id)


def _set_task(task_id: str, data: dict) -> None:
    with _tasks_lock:
        _tasks[task_id] = data


def _update_task(task_id: str, **kwargs) -> None:
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id].update(kwargs)


# ------------------------------------------------------------------
# 统一错误处理
# ------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return jsonify({"code": 40401, "message": "接口不存在", "detail": str(e)}), 404


@app.errorhandler(500)
def internal_error(e):
    logger.exception("内部错误")
    return jsonify({"code": 50001, "message": "服务器内部错误", "detail": str(e)}), 500


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------
def _load_school_configs() -> list[dict]:
    """从 config/loader.py 加载学校配置。"""
    from config.loader import load_schools_config
    try:
        return load_schools_config()
    except Exception:
        return []


def _get_all_universities() -> list[str]:
    """获取所有配置的大学名称。"""
    configs = _load_school_configs()
    return [c["university"] for c in configs]


def _read_merged_records(university: str, college: str) -> list[dict]:
    """读取某学校学院的合并记录。"""
    path = Path(f"data/output/{university}_{college}.jsonl")
    if not path.exists():
        return []
    return _read_jsonl(str(path))


def _read_all_merged_records() -> list[dict]:
    """读取所有合并记录（用于导师列表、导出等）。"""
    records = []
    for jsonl_file in Path("data/output").glob("*_*.jsonl"):
        if jsonl_file.name.endswith("_faculty.jsonl") or jsonl_file.name.endswith("_notice.jsonl"):
            continue
        try:
            records.extend(_read_jsonl(str(jsonl_file)))
        except Exception as e:
            logger.warning("读取 %s 失败: %s", jsonl_file, e)
    return records


# ------------------------------------------------------------------
# 2.1 GET /api/overview
# ------------------------------------------------------------------
@app.route("/api/overview", methods=["GET"])
def api_overview():
    progress = get_progress_tracker()

    data = {
        "stats": progress.get_overview_stats(),
        "progress": progress.get_pipeline_progress(),
        "source_breakdown": progress.get_source_breakdown(),
        "recent_tutors": progress.get_recent_tutors(6),
        "recent_failures": progress.get_recent_failures(5),
        "logs": progress.get_recent_logs(20),
    }
    return jsonify({"code": 0, "data": data})


# ------------------------------------------------------------------
# 2.2 GET /api/schools
# ------------------------------------------------------------------
@app.route("/api/schools", methods=["GET"])
def api_schools():
    q = request.args.get("q", "").strip().lower()
    status_filter = request.args.get("status", "").strip()
    category_filter = request.args.get("category", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(1, int(request.args.get("page_size", 20))))

    configs = _load_school_configs()
    progress = get_progress_tracker()

    items = []
    for idx, config in enumerate(configs, 1):
        university = config["university"]
        level = get_school_level(university) or "双一流"

        # 按学校聚合状态（跨学院取最差）
        total_tutors = 0
        src_a_statuses = []
        src_b_statuses = []
        merged_statuses = []

        for cat in config.get("categories", []):
            college = cat["college"]
            category = cat["category"]

            if category_filter and category != category_filter:
                continue

            school_status = progress.get_school_status(university, college)
            src_a_statuses.append(school_status.get("source_a", "pending"))
            src_b_statuses.append(school_status.get("source_b", "pending"))
            merged_statuses.append(school_status.get("merged", "pending"))
            total_tutors += school_status.get("tutor_count", 0)

        if category_filter and not src_a_statuses:
            continue

        # 整体状态：取最差
        all_statuses = set(src_a_statuses + src_b_statuses + merged_statuses)
        if "failed" in all_statuses:
            overall = "failed"
        elif "running" in all_statuses:
            overall = "running"
        elif "partial" in all_statuses:
            overall = "partial"
        elif "pending" in all_statuses and len(all_statuses) == 1:
            overall = "pending"
        else:
            overall = "done"

        if status_filter and overall != status_filter:
            continue
        if q and q not in university.lower():
            continue

        # Source A/B 状态：如果有学院 done，则显示 done；否则取最差
        src_a = "done" if "done" in src_a_statuses else (src_a_statuses[0] if src_a_statuses else "pending")
        if "failed" in src_a_statuses:
            src_a = "failed"
        if "running" in src_a_statuses:
            src_a = "running" if src_a != "failed" else src_a
        src_b = "done" if "done" in src_b_statuses else (src_b_statuses[0] if src_b_statuses else "pending")
        if "failed" in src_b_statuses:
            src_b = "failed"
        if "running" in src_b_statuses:
            src_b = "running" if src_b != "failed" else src_b

        # 匹配率
        match_rate = 90 if total_tutors > 0 else 0

        items.append({
            "id": idx,
            "name": university,
            "level": level,
            "mech_college": next((c["college"] for c in config["categories"] if c["category"] == "mechanical"), ""),
            "auto_college": next((c["college"] for c in config["categories"] if c["category"] == "automation"), ""),
            "source_a_status": src_a,
            "source_b_status": src_b,
            "tutor_count": total_tutors,
            "match_rate": match_rate,
            "status": overall,
        })

    # 统计摘要
    summary = {"done": 0, "partial": 0, "running": 0, "pending": 0, "failed": 0}
    for item in items:
        summary[item["status"]] = summary.get(item["status"], 0) + 1

    # 分页
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return jsonify({
        "code": 0,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": page_items,
            "summary": summary,
        }
    })


# ------------------------------------------------------------------
# 2.3 GET /api/schools/{school_id}
# ------------------------------------------------------------------
@app.route("/api/schools/<int:school_id>", methods=["GET"])
def api_school_detail(school_id: int):
    configs = _load_school_configs()
    if school_id < 1 or school_id > len(configs):
        return jsonify({"code": 40402, "message": "学校不存在"}), 404

    config = configs[school_id - 1]
    university = config["university"]
    progress = get_progress_tracker()

    categories = []
    for cat in config.get("categories", []):
        college = cat["college"]
        school_status = progress.get_school_status(university, college)

        # 获取 faculty 配置
        faculty_cfg = cat.get("faculty", {})
        faculty_config = {
            "list_url": faculty_cfg.get("list_url", ""),
            "list_type": faculty_cfg.get("list_type", "static_html"),
        }

        categories.append({
            "college": college,
            "category": cat["category"],
            "faculty_config": faculty_config,
            "tutor_count": school_status.get("tutor_count", 0),
            "source_a_status": school_status.get("source_a", "pending"),
            "source_b_status": school_status.get("source_b", "pending"),
            "last_crawl_at": school_status.get("last_crawl_at", ""),
        })

    return jsonify({
        "code": 0,
        "data": {
            "id": school_id,
            "name": university,
            "level": get_school_level(university) or "双一流",
            "categories": categories,
        }
    })


# ------------------------------------------------------------------
# 2.4 POST /api/crawl
# ------------------------------------------------------------------
@app.route("/api/crawl", methods=["POST"])
def api_crawl():
    data = request.get_json() or {}
    schools = data.get("schools", [])
    categories = data.get("categories", ["mechanical", "automation"])
    sources = data.get("sources", ["source_a", "source_b"])
    force = data.get("force", False)
    year = data.get("year", datetime.now().year)

    if not schools:
        return jsonify({"code": 40001, "message": "schools 参数不能为空"}), 400

    # 检查是否有冲突任务
    progress = get_progress_tracker()
    configs = _load_school_configs()

    target_schools = _get_all_universities() if schools == ["__all__"] else schools

    for uni in target_schools:
        sc = next((c for c in configs if c["university"] == uni), None)
        if not sc:
            continue
        for cat in sc.get("categories", []):
            if cat["category"] not in categories:
                continue
            college = cat["college"]
            for src in sources:
                status = progress.get_school_status(uni, college).get(src, "pending")
                if status == "running" and not force:
                    return jsonify({
                        "code": 40901,
                        "message": f"{uni}/{college} {src} 正在采集中，请勿重复提交",
                        "detail": f"当前状态: {status}"
                    }), 409

    # 创建任务
    task_id = _new_task_id()
    task_data = {
        "task_id": task_id,
        "status": "queued",
        "progress": {
            "total_steps": 0,
            "completed_steps": 0,
            "current_step": "任务已加入队列",
            "percent": 0.0,
        },
        "started_at": datetime.now().isoformat(),
        "estimated_remaining": "计算中...",
        "params": {
            "schools": target_schools,
            "categories": categories,
            "sources": sources,
            "force": force,
            "year": year,
        },
    }
    _set_task(task_id, task_data)

    # 启动后台线程执行爬虫
    threading.Thread(target=_run_crawl_task, args=(task_id,), daemon=True).start()

    # 构建返回消息
    msg_parts = []
    for uni in target_schools:
        sc = next((c for c in configs if c["university"] == uni), None)
        if not sc:
            continue
        colleges = [c["college"] for c in sc["categories"] if c["category"] in categories]
        if colleges:
            msg_parts.append(f"{uni}（{', '.join(colleges)}）")
    message = f"已加入采集队列：{'; '.join(msg_parts)}"

    return jsonify({
        "code": 0,
        "data": {
            "task_id": task_id,
            "status": "queued",
            "message": message,
        }
    })


def _run_crawl_task(task_id: str) -> None:
    """后台线程执行爬虫任务。"""
    task = _get_task(task_id)
    if not task:
        return

    params = task["params"]
    target_schools = params["schools"]
    categories = params["categories"]
    sources = params["sources"]
    force = params["force"]
    year = params["year"]

    service = None
    try:
        _update_task(task_id, status="running")

        from types import SimpleNamespace
        from services import CrawlerService, ExportService
        from utils.cache import CrawlCache

        service = CrawlerService(cache=CrawlCache(max_age_days=7), progress=get_progress_tracker())
        tasks = service.build_tasks(SimpleNamespace(
            school=target_schools, category=categories, source=sources,
            year=year, force=force, resume=False, retry_failed=False))
        _update_task(task_id, progress={
            "total_steps": len(tasks),
            "completed_steps": 0,
            "current_step": f"开始执行 {len(tasks)} 个子任务",
            "percent": 0.0,
        })

        completed = 0
        for task in tasks:
            _update_task(task_id, progress={
                "total_steps": len(tasks),
                "completed_steps": completed,
                "current_step": f"{task.university}/{task.college} {task.source} 进行中",
                "percent": round(completed / len(tasks) * 100, 1),
            })

            result = service.execute_task(task)
            completed += 1

            if result.status == "failed":
                logger.warning("任务 %s 子任务失败 [%s]: %s", task_id, result.error_type, result.error_message)

        service.run_merge(tasks)

        # 全量导出
        _update_task(task_id, progress={
            "total_steps": len(tasks),
            "completed_steps": completed,
            "current_step": "生成汇总表...",
            "percent": 95.0,
        })

        all_merged = _read_all_merged_records()
        if all_merged:
            ExportService().run_export_pipeline(all_merged, Path("data/output"))

        _update_task(task_id, status="completed", progress={
            "total_steps": len(tasks),
            "completed_steps": completed,
            "current_step": "全部完成",
            "percent": 100.0,
        })

    except Exception as e:
        logger.exception("任务 %s 执行异常", task_id)
        _update_task(task_id, status="failed", progress={
            "total_steps": 0,
            "completed_steps": 0,
            "current_step": f"执行失败: {e}",
            "percent": 0.0,
        })
    finally:
        if service is not None:
            service.session.close()


# ------------------------------------------------------------------
# 2.5 GET /api/tasks/{task_id}
# ------------------------------------------------------------------
@app.route("/api/tasks/<task_id>", methods=["GET"])
def api_task_status(task_id: str):
    task = _get_task(task_id)
    if not task:
        return jsonify({"code": 40404, "message": "任务不存在"}), 404

    return jsonify({"code": 0, "data": task})


# ------------------------------------------------------------------
# 2.6 GET /api/tutors
# ------------------------------------------------------------------
@app.route("/api/tutors", methods=["GET"])
def api_tutors():
    q = request.args.get("q", "").strip().lower()
    school_filter = request.args.get("school", "").strip()
    college_filter = request.args.get("college", "").strip()
    level_filter = request.args.get("level", "").strip()
    match_filter = request.args.get("match", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(1, int(request.args.get("page_size", 20))))

    all_records = _read_all_merged_records()

    # 筛选
    filtered = []
    for rec in all_records:
        if q and q not in rec.get("name", "").lower():
            continue
        if school_filter and school_filter != rec.get("university", ""):
            continue
        if college_filter and college_filter != rec.get("college", ""):
            continue
        if level_filter and level_filter != rec.get("advisor_level", ""):
            continue
        if match_filter and match_filter != rec.get("match_status", ""):
            continue
        filtered.append(rec)

    total = len(filtered)
    start = (page - 1) * page_size
    end = start + page_size
    page_records = filtered[start:end]

    # 转换为前端格式
    items = []
    for rec in page_records:
        enrollment = rec.get("enrollment")
        enr_data = None
        if enrollment and (enrollment.get("in_roster") or enrollment.get("directions")):
            enr_data = {
                "in_roster": enrollment.get("in_roster", False),
                "directions": [{"code": d.get("code", ""), "name": d.get("name", "")} for d in enrollment.get("directions", [])],
                "degree_types": enrollment.get("degree_types", []),
                "source_url": enrollment.get("source_url", ""),
            }

        items.append({
            "name": rec.get("name", ""),
            "school": rec.get("university", ""),
            "college": rec.get("college", ""),
            "title": rec.get("title", ""),
            "level": rec.get("advisor_level", ""),
            "email": rec.get("email", ""),
            "profile_url": rec.get("profile_url", ""),
            "areas": rec.get("research_areas", []),
            "enrollment": enr_data,
            "match_status": rec.get("match_status", "merged"),
            "source_type": rec.get("source_type", {"faculty": "官网师资页", "notice": "研招网"}),
        })

    return jsonify({
        "code": 0,
        "data": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }
    })


# ------------------------------------------------------------------
# 2.7 GET /api/tutors/{school}/{name}
# ------------------------------------------------------------------
@app.route("/api/tutors/<path:school>/<path:name>", methods=["GET"])
def api_tutor_detail(school: str, name: str):
    # 从所有记录中查找
    all_records = _read_all_merged_records()
    for rec in all_records:
        if rec.get("university") == school and rec.get("name") == name:
            enrollment = rec.get("enrollment")
            enr_data = None
            if enrollment and (enrollment.get("in_roster") or enrollment.get("directions")):
                enr_data = {
                    "in_roster": enrollment.get("in_roster", False),
                    "directions": [{"code": d.get("code", ""), "name": d.get("name", "")} for d in enrollment.get("directions", [])],
                    "degree_types": enrollment.get("degree_types", []),
                    "source_url": enrollment.get("source_url", ""),
                }

            return jsonify({
                "code": 0,
                "data": {
                    "name": rec.get("name", ""),
                    "school": rec.get("university", ""),
                    "college": rec.get("college", ""),
                    "title": rec.get("title", ""),
                    "level": rec.get("advisor_level", ""),
                    "email": rec.get("email", ""),
                    "profile_url": rec.get("profile_url", ""),
                    "areas": rec.get("research_areas", []),
                    "enrollment": enr_data,
                    "match_status": rec.get("match_status", "merged"),
                    "source_type": rec.get("source_type", {"faculty": "官网师资页", "notice": "研招网"}),
                    "raw_ref": rec.get("raw_ref", {"faculty": "", "notice": ""}),
                }
            })

    return jsonify({"code": 40403, "message": "导师不存在"}), 404


# ------------------------------------------------------------------
# 2.8 GET /api/tutors/export
# ------------------------------------------------------------------
@app.route("/api/tutors/export", methods=["GET"])
def api_tutors_export():
    fmt = request.args.get("format", "excel").lower()
    school_filter = request.args.get("school", "").strip()
    college_filter = request.args.get("college", "").strip()

    all_records = _read_all_merged_records()

    if school_filter:
        all_records = [r for r in all_records if r.get("university") == school_filter]
    if college_filter:
        all_records = [r for r in all_records if r.get("college") == college_filter]

    if fmt == "json":
        # 返回 JSON 文件下载
        import io
        json_str = json.dumps(all_records, ensure_ascii=False, indent=2)
        buf = io.BytesIO(json_str.encode("utf-8"))
        return send_file(
            buf,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"tutors_{datetime.now().strftime('%Y%m%d')}.json",
        )
    else:
        # 返回 Excel 文件下载
        from pipelines.export import export_summary
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "导师数据"

        headers = ["学校", "学院", "姓名", "职称", "招生状态", "招生方向", "研究方向", "来源链接"]
        ws.append(headers)

        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="4F46E5", end_color="4F46E5", fill_type="solid")
        wrap_alignment = Alignment(wrap_text=True, vertical="top")

        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        from pipelines.merge import to_summary_row
        for rec in all_records:
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
            for col_idx in range(1, len(headers) + 1):
                ws.cell(row=ws.max_row, column=col_idx).alignment = wrap_alignment

        column_widths = [18, 18, 12, 10, 10, 40, 40, 50]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width

        ws.freeze_panes = "A2"

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"tutors_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )


# ------------------------------------------------------------------
# 2.9 GET /api/failures
# ------------------------------------------------------------------
@app.route("/api/failures", methods=["GET"])
def api_failures():
    status_filter = request.args.get("status", "").strip()  # active / resolved / ignored
    source_filter = request.args.get("source", "").strip()  # Source A / Source B
    page = max(1, int(request.args.get("page", 1)))
    page_size = min(100, max(1, int(request.args.get("page_size", 20))))

    failures = load_failures()

    if status_filter:
        failures = [f for f in failures if f.get("status") == status_filter]
    if source_filter:
        failures = [f for f in failures if f.get("source") == source_filter]

    # 按时间倒序
    failures.sort(key=lambda x: x.get("occurred_at", ""), reverse=True)

    total = len(failures)
    start = (page - 1) * page_size
    end = start + page_size
    page_failures = failures[start:end]

    summary = {"http_error": 0, "timeout": 0, "parse_error": 0, "dns_error": 0}
    for f in failures:
        et = f.get("error_type", "")
        if et in summary:
            summary[et] += 1

    return jsonify({
        "code": 0,
        "data": {
            "total": total,
            "summary": summary,
            "items": page_failures,
        }
    })


# ------------------------------------------------------------------
# 2.10 POST /api/failures/retry
# ------------------------------------------------------------------
@app.route("/api/failures/retry", methods=["POST"])
def api_failures_retry():
    data = request.get_json() or {}
    failure_ids = data.get("failure_ids", [])
    retry_all = data.get("retry_all", False)

    if not retry_all and not failure_ids:
        return jsonify({"code": 40001, "message": "failure_ids 不能为空"}), 400

    active_failures = [failure for failure in load_failures() if failure.get("status") == "active"]

    if retry_all:
        target_failures = active_failures
    else:
        target_failures = [f for f in active_failures if f["id"] in failure_ids]

    if not target_failures:
        return jsonify({"code": 40405, "message": "无匹配的失败记录"}), 404

    # 构建学校列表用于重新触发爬虫
    schools = list(set(f["school"] for f in target_failures))

    # 创建任务（复用 crawl 逻辑）
    task_id = _new_task_id()
    task_data = {
        "task_id": task_id,
        "status": "queued",
        "progress": {
            "total_steps": 0,
            "completed_steps": 0,
            "current_step": "失败重试任务已加入队列",
            "percent": 0.0,
        },
        "started_at": datetime.now().isoformat(),
        "estimated_remaining": "计算中...",
        "params": {
            "schools": schools,
            "categories": ["mechanical", "automation"],
            "sources": ["source_a", "source_b"],
            "force": True,
            "year": datetime.now().year,
        },
    }
    _set_task(task_id, task_data)

    # 启动后台线程
    threading.Thread(target=_run_crawl_task, args=(task_id,), daemon=True).start()

    return jsonify({
        "code": 0,
        "data": {
            "task_id": task_id,
            "status": "queued",
            "message": f"已加入重试队列：{len(target_failures)} 条失败记录，涉及 {len(schools)} 所学校",
        }
    })


# ------------------------------------------------------------------
# 2.11 POST /api/failures/{id}/ignore
# ------------------------------------------------------------------
@app.route("/api/failures/<failure_id>/ignore", methods=["POST"])
def api_failure_ignore(failure_id: str):
    success = update_failure_status(failure_id, "ignored")
    if not success:
        return jsonify({"code": 40405, "message": "失败记录不存在"}), 404

    return jsonify({"code": 0, "data": {"id": failure_id, "status": "ignored"}})


# ------------------------------------------------------------------
# 2.12 GET /api/raw/<path:raw_path>
# ------------------------------------------------------------------
@app.route("/api/raw/<path:raw_path>", methods=["GET"])
def api_raw_file(raw_path: str):
    # 防路径穿越
    raw_dir = Path("data/raw").resolve()
    target_path = (raw_dir / raw_path).resolve()

    # 确保目标路径在 raw_dir 内
    try:
        target_path.relative_to(raw_dir)
    except ValueError:
        return jsonify({"code": 40301, "message": "路径穿越被拒绝"}), 403

    if not target_path.exists():
        return jsonify({"code": 40401, "message": "文件不存在"}), 404

    # 根据扩展名设置 MIME
    mime_map = {
        ".html": "text/html",
        ".json": "application/json",
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    ext = target_path.suffix.lower()
    mimetype = mime_map.get(ext, "application/octet-stream")

    return send_file(str(target_path), mimetype=mimetype)


# ------------------------------------------------------------------
# 2.13 GET /api/config
# ------------------------------------------------------------------
@app.route("/api/config", methods=["GET"])
def api_config_get():
    from config.validator import validate_all_configs

    configs = _load_school_configs()
    progress = get_progress_tracker()

    # 全局配置（可从文件读取，这里用默认值）
    global_config = {
        "delay_range": [1.0, 3.0],
        "max_retries": 3,
        "timeout": 30,
        "cooldown_threshold": 5,
        "cooldown_seconds": 1800,
        "workers": 4,
        "year": datetime.now().year,
        "fuzzy_threshold": 0.85,
        "user_agents": [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        ],
    }

    schools = []
    for config in configs:
        university = config["university"]
        total_tutors = 0
        verified = True

        for cat in config.get("categories", []):
            college = cat["college"]
            school_status = progress.get_school_status(university, college)
            total_tutors += school_status.get("tutor_count", 0)
            if school_status.get("source_a") == "failed" or school_status.get("source_b") == "failed":
                verified = False

        schools.append({
            "university": university,
            "categories": config.get("categories", []),
            "tutor_count": total_tutors,
            "verified": verified,
        })

    validation_report = validate_all_configs(configs)
    # 转换为可 JSON 序列化的格式
    validation_report = {
        "errors": [e.to_dict() for e in validation_report["errors"]],
        "warnings": [e.to_dict() for e in validation_report["warnings"]],
        "summary": validation_report["summary"],
    }

    return jsonify({
        "code": 0,
        "data": {
            "global": global_config,
            "schools": schools,
            "validation": validation_report,
            "plugins": _list_plugins_payload(),
        }
    })


def _list_plugins_payload():
    from config.plugins import list_plugins
    return {"items": list_plugins()}


# ------------------------------------------------------------------
# 2.14 PUT /api/config/schools/{school_name}
# ------------------------------------------------------------------
@app.route("/api/config/schools/<path:school_name>", methods=["PUT"])
def api_config_school_save(school_name: str):
    from config.loader import save_school_config
    from config.validator import validate_school_config

    data = request.get_json() or {}

    # 验证必填字段
    required = ["university", "categories"]
    for field in required:
        if field not in data:
            return jsonify({"code": 40001, "message": f"缺少必填字段: {field}"}), 400

    # 校验配置合法性
    errors = validate_school_config(data)
    if errors:
        return jsonify({
            "code": 40001,
            "message": "配置校验失败",
            "detail": [str(e) for e in errors],
        }), 400

    success = save_school_config(school_name, data)
    if not success:
        return jsonify({"code": 50001, "message": "保存失败，请检查日志"}), 500

    return jsonify({
        "code": 0,
        "data": {
            "status": "ok",
            "message": f"{school_name} 配置已保存",
            "validation": {"valid": True, "errors": []},
        }
    })


def _write_schools_config(configs: list[dict]) -> None:
    """将配置写入 config/school_data.json（经 ConfigStore 原子写入）。"""
    from config.loader import DEFAULT_CONFIG_PATH
    from storage import ConfigStore
    store = ConfigStore(config_path=DEFAULT_CONFIG_PATH)
    store.save_schools(configs)
    logger.info("已更新 %s，共 %d 所学校", store._path, len(configs))


# ------------------------------------------------------------------
# 2.15 PUT /api/config/global
# ------------------------------------------------------------------
@app.route("/api/config/global", methods=["PUT"])
def api_config_global_save():
    data = request.get_json() or {}

    from storage import ConfigStore
    ConfigStore(global_path=GLOBAL_CONFIG_PATH).save_global(data)

    return jsonify({
        "code": 0,
        "data": {
            "status": "ok",
            "message": "全局配置已保存",
            "validation": {"valid": True, "errors": []},
        }
    })


# ------------------------------------------------------------------
# 2.16 POST /api/config/test
# ------------------------------------------------------------------
@app.route("/api/config/test", methods=["POST"])
def api_config_test():
    data = request.get_json() or {}
    url = data.get("url", "").strip()
    method = data.get("method", "GET").upper()
    headers = data.get("headers", {})

    if not url:
        return jsonify({"code": 40001, "message": "url 参数不能为空"}), 400

    from utils.http import PoliteSession

    session = PoliteSession(delay_range=(0, 0), max_retries=1)
    start = time.time()

    try:
        if method == "GET":
            resp = session.get(url, extra_headers=headers, save_raw=False)
        else:
            resp = session.post(url, data=data.get("data"), extra_headers=headers, save_raw=False)

        elapsed = int((time.time() - start) * 1000)

        # 提取标题
        sample_title = ""
        if "html" in resp.headers.get("Content-Type", ""):
            from bs4 import BeautifulSoup
            from utils.http import response_text
            soup = BeautifulSoup(response_text(resp), "lxml")
            if soup.title:
                sample_title = soup.title.string.strip()[:100]

        return jsonify({
            "code": 0,
            "data": {
                "status_code": resp.status_code,
                "reachable": True,
                "response_time_ms": elapsed,
                "content_type": resp.headers.get("Content-Type", ""),
                "content_length": len(resp.content),
                "sample_title": sample_title,
            }
        })
    except Exception as e:
        elapsed = int((time.time() - start) * 1000)
        return jsonify({
            "code": 0,
            "data": {
                "status_code": 0,
                "reachable": False,
                "response_time_ms": elapsed,
                "content_type": "",
                "content_length": 0,
                "sample_title": f"错误: {e}",
            }
        })


# ------------------------------------------------------------------
# 2.17 POST /api/config/import | GET /api/config/export
# ------------------------------------------------------------------
@app.route("/api/config/import", methods=["POST"])
def api_config_import():
    if "file" not in request.files:
        return jsonify({"code": 40001, "message": "未上传文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"code": 40001, "message": "未选择文件"}), 400

    try:
        content = file.read().decode("utf-8")
        if file.filename.endswith(".json"):
            configs = json.loads(content)
        elif file.filename.endswith(".py"):
            # 简单处理：执行 py 文件获取 SCHOOLS_CONFIG
            namespace = {}
            exec(content, namespace)
            configs = namespace.get("SCHOOLS_CONFIG", [])
        else:
            return jsonify({"code": 40001, "message": "仅支持 .json 或 .py 文件"}), 400

        # 校验结构
        errors = []
        for i, c in enumerate(configs):
            if "university" not in c:
                errors.append(f"第 {i+1} 项缺少 university")
            if "categories" not in c:
                errors.append(f"第 {i+1} 项缺少 categories")

        if errors:
            return jsonify({
                "code": 40001,
                "message": "配置校验失败",
                "detail": "; ".join(errors),
            }), 400

        _write_schools_config(configs)

        return jsonify({
            "code": 0,
            "data": {
                "status": "ok",
                "message": f"成功导入 {len(configs)} 所学校配置",
                "validation": {"valid": True, "errors": []},
            }
        })
    except Exception as e:
        logger.exception("配置导入失败")
        return jsonify({"code": 50003, "message": "配置导入失败", "detail": str(e)}), 500


@app.route("/api/config/export", methods=["GET"])
def api_config_export():
    """导出配置为 JSON 文件。"""
    configs = _load_school_configs()
    if not configs:
        return jsonify({"code": 40401, "message": "无配置可导出"}), 404

    content = json.dumps(configs, ensure_ascii=False, indent=2)

    import io
    buf = io.BytesIO(content.encode("utf-8"))

    return send_file(
        buf,
        mimetype="application/json",
        as_attachment=True,
        download_name="school_data.json",
    )


@app.route("/api/plugins", methods=["GET"])
def api_plugins_list():
    from config.plugins import list_plugins
    return jsonify({"code": 0, "data": {"items": list_plugins()}})


@app.route("/api/plugins/pipeline/<pipeline_type>", methods=["PUT"])
def api_plugin_pipeline_save(pipeline_type: str):
    from config.plugins import update_pipeline
    data = request.get_json() or {}
    weights = data.get("weights", data)
    if not isinstance(weights, dict):
        return jsonify({"code": 40001, "message": "weights 必须是对象"}), 400
    result = update_pipeline(pipeline_type, weights)
    if result is None:
        return jsonify({"code": 40001, "message": "pipeline_type 必须是 processors 或 exporters"}), 400
    return jsonify({"code": 0, "data": {"pipeline_type": pipeline_type, "weights": result}})


@app.route("/api/plugins/upload", methods=["POST"])
def api_plugin_upload():
    from config.plugins import upload_plugin
    kind = request.form.get("kind", "")
    filename = request.form.get("filename", "")
    source = request.form.get("source", "")
    if "file" in request.files:
        uploaded = request.files["file"]
        filename = filename or uploaded.filename
        source = source or uploaded.read().decode("utf-8")
    if not kind or not filename or not source:
        return jsonify({"code": 40001, "message": "kind、filename 和 source 不能为空"}), 400
    try:
        plugin = upload_plugin(kind, filename, source)
    except ValueError as e:
        return jsonify({"code": 40002, "message": str(e)}), 400
    except Exception as e:
        logger.exception("插件上传失败")
        return jsonify({"code": 50001, "message": "插件上传失败", "detail": str(e)}), 500
    return jsonify({"code": 0, "data": plugin})


@app.route("/api/plugins/<path:plugin_key>", methods=["PUT", "DELETE"])
def api_plugin_update(plugin_key: str):
    from config.plugins import delete_plugin, update_plugin
    if ":" not in plugin_key:
        return jsonify({"code": 40001, "message": "插件标识必须为 kind:id"}), 400
    kind, plugin_id = plugin_key.split(":", 1)
    if request.method == "DELETE":
        if not delete_plugin(kind, plugin_id):
            return jsonify({"code": 40401, "message": "插件不存在"}), 404
        return jsonify({"code": 0, "data": {"status": "deleted", "plugin": f"{kind}:{plugin_id}"}})
    data = request.get_json() or {}
    plugin = update_plugin(kind, plugin_id, data)
    if plugin is None:
        return jsonify({"code": 40401, "message": "插件不存在"}), 404
    return jsonify({"code": 0, "data": plugin})


@app.route("/api/plugins/<path:plugin_key>/reload", methods=["POST"])
def api_plugin_reload(plugin_key: str):
    from config.plugins import reload_plugin
    if ":" not in plugin_key:
        return jsonify({"code": 40001, "message": "插件标识必须为 kind:id"}), 400
    kind, plugin_id = plugin_key.split(":", 1)
    plugin = reload_plugin(kind, plugin_id)
    if plugin is None:
        return jsonify({"code": 40401, "message": "插件不存在"}), 404
    return jsonify({"code": 0, "data": plugin})


@app.route("/api/cache/clear", methods=["POST"])
def api_cache_clear():
    from utils.cache import CrawlCache
    removed = CrawlCache().clear()
    return jsonify({"code": 0, "data": {"removed": removed, "message": f"已清理 {removed} 个缓存文件"}})


# ------------------------------------------------------------------
# 2.18 SSE 实时日志流
# ------------------------------------------------------------------
_log_subscribers: dict[str, list] = {}
_log_lock = threading.Lock()


def _broadcast_log(log_entry: dict):
    """广播日志到所有订阅者。"""
    message = f"data: {json.dumps(log_entry, ensure_ascii=False)}\n\n"
    with _log_lock:
        # 广播给 "all" 订阅者
        for queue in _log_subscribers.get("all", []):
            try:
                queue.put(message)
            except Exception:
                pass
        # 广播给特定 task_id 订阅者
        task_id = log_entry.get("task_id")
        if task_id:
            for queue in _log_subscribers.get(task_id, []):
                try:
                    queue.put(message)
                except Exception:
                    pass


@app.route("/api/logs/stream")
def api_logs_stream():
    """SSE 实时日志流端点。

    Query 参数:
        task_id: 可选，过滤特定任务的日志。默认 "all" 订阅所有日志。
    """
    task_id = request.args.get("task_id", "all")

    def event_stream():
        q = queue.Queue()
        with _log_lock:
            _log_subscribers.setdefault(task_id, []).append(q)

        try:
            # 发送连接确认
            yield f"data: {json.dumps({'type': 'connected', 'task_id': task_id}, ensure_ascii=False)}\n\n"

            while True:
                try:
                    message = q.get(timeout=30)
                    yield message
                except queue.Empty:
                    # 心跳
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            pass
        finally:
            with _log_lock:
                if queue in _log_subscribers.get(task_id, []):
                    _log_subscribers[task_id].remove(queue)

    return app.response_class(event_stream(), mimetype="text/event-stream")


# ------------------------------------------------------------------
# 2.19 任务管理扩展端点
# ------------------------------------------------------------------
@app.route("/api/tasks", methods=["GET"])
def api_tasks_list():
    """获取所有任务列表。"""
    with _tasks_lock:
        tasks = list(_tasks.values())
    return jsonify({"code": 0, "data": {"tasks": tasks}})


@app.route("/api/tasks/<task_id>/cancel", methods=["POST"])
def api_task_cancel(task_id: str):
    """取消任务。"""
    task = _get_task(task_id)
    if not task:
        return jsonify({"code": 40404, "message": "任务不存在"}), 404

    if task["status"] not in ("running", "queued"):
        return jsonify({"code": 40001, "message": f"任务状态 {task['status']} 不可取消"}), 400

    _update_task(task_id, status="canceled")
    return jsonify({"code": 0, "data": {"status": "canceled", "task_id": task_id}})


@app.route("/api/tasks/<task_id>/retry", methods=["POST"])
def api_task_retry(task_id: str):
    """重试失败任务。"""
    task = _get_task(task_id)
    if not task:
        return jsonify({"code": 40404, "message": "任务不存在"}), 404

    if task["status"] != "failed":
        return jsonify({"code": 40001, "message": f"任务状态 {task['status']} 不可重试"}), 400

    # 重置任务状态并重新入队
    params = task.get("params", {})
    new_task_id = _new_task_id()
    new_task = {
        "task_id": new_task_id,
        "status": "queued",
        "progress": {
            "total_steps": 0,
            "completed_steps": 0,
            "current_step": "重试任务已加入队列",
            "percent": 0.0,
        },
        "started_at": datetime.now().isoformat(),
        "estimated_remaining": "计算中...",
        "params": params,
    }
    _set_task(new_task_id, new_task)

    # 启动后台线程
    threading.Thread(target=_run_crawl_task, args=(new_task_id,), daemon=True).start()

    return jsonify({
        "code": 0,
        "data": {
            "task_id": new_task_id,
            "status": "queued",
            "message": f"重试任务已加入队列 (原任务: {task_id})",
        }
    })


# ------------------------------------------------------------------
# 前端页面托管：同源提供 dashboard，避免 CORS / Mock 回退
# /api/* 已由上方显式路由匹配，不会被此处 catch-all 抢占
# ------------------------------------------------------------------
@app.route("/")
def dashboard_index():
    return send_file(str(_DASHBOARD_DIR / "index.html"), mimetype="text/html")


@app.route("/<path:filename>")
def dashboard_file(filename: str):
    # 仅允许访问 dashboard 目录内文件，防路径穿越
    if not filename.endswith((".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico")):
        abort(404)
    target = (_DASHBOARD_DIR / filename).resolve()
    try:
        target.relative_to(_DASHBOARD_DIR)
    except ValueError:
        abort(403)
    if not target.exists():
        abort(404)
    return send_file(str(target))


# ------------------------------------------------------------------
# 启动入口
# ------------------------------------------------------------------
def _dashboard_url(host: str, port: int) -> str:
    """浏览器可访问的面板地址：0.0.0.0/:: 等通配监听地址回退为 127.0.0.1。"""
    if host in ("0.0.0.0", "::", ""):
        host = "127.0.0.1"
    return f"http://{host}:{port}/"


def _open_browser_later(url: str, delay: float = 1.0) -> None:
    """后台线程延时打开浏览器，避免在服务尚未监听时跳转失败（异常静默忽略）。"""

    def _worker() -> None:
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception as e:  # 无图形环境等场景不影响服务运行
            logger.warning("自动打开浏览器失败：%s", e)

    threading.Thread(target=_worker, name="open-browser", daemon=True).start()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="启动后不自动打开 WEB 面板（默认自动打开）",
    )
    args = parser.parse_args()

    # 确保数据目录存在
    Path("data/output").mkdir(parents=True, exist_ok=True)
    Path("data/raw").mkdir(parents=True, exist_ok=True)

    url = _dashboard_url(args.host, args.port)
    logger.info("WEB 面板地址：%s", url)
    if not args.no_browser:
        _open_browser_later(url)

    app.run(host=args.host, port=args.port, debug=args.debug)