# -*- coding: utf-8 -*-
"""
API 响应模型定义
================
使用 TypedDict 定义所有接口的请求/响应结构，便于类型检查和文档生成。
"""

from typing import TypedDict, Literal, Optional, List, Union
from datetime import datetime


# =====================================================================
# 通用响应格式
# =====================================================================

class APIResponse(TypedDict):
    code: int
    data: dict
    message: Optional[str]
    detail: Optional[str]


class ErrorResponse(TypedDict):
    code: int
    message: str
    detail: Optional[str]


# 错误码常量
class ErrorCode:
    SUCCESS = 0
    # 参数校验错误 40001-40099
    VALIDATION_ERROR = 40001
    MISSING_PARAM = 40002
    INVALID_PARAM = 40003
    # 资源不存在 40401-40499
    NOT_FOUND = 40401
    SCHOOL_NOT_FOUND = 40402
    TUTOR_NOT_FOUND = 40403
    TASK_NOT_FOUND = 40404
    FAILURE_NOT_FOUND = 40405
    # 冲突 40901
    TASK_CONFLICT = 40901
    # 服务器错误 50001-50099
    INTERNAL_ERROR = 50001
    CRAWL_ERROR = 50002
    CONFIG_ERROR = 50003


def success_response(data: dict) -> APIResponse:
    return {"code": ErrorCode.SUCCESS, "data": data, "message": None, "detail": None}


def error_response(code: int, message: str, detail: Optional[str] = None) -> ErrorResponse:
    return {"code": code, "message": message, "detail": detail}


# =====================================================================
# 2.1 GET /api/overview
# =====================================================================

class StatsData(TypedDict):
    total_schools: int
    done: int
    running: int
    failed: int
    partial: int
    pending: int


class PipelineProgress(TypedDict):
    completed: int
    total: int


class SourceBreakdown(TypedDict):
    matched: int
    notice_only: int
    faculty_only: int
    unmatched: int


class RecentTutor(TypedDict):
    name: str
    title: str
    level: str
    school: str
    college: str
    areas: List[str]


class RecentFailure(TypedDict):
    school: str
    college: str
    source: str
    error: str
    time: str


class LogEntry(TypedDict):
    time: str
    level: str
    msg: str


class OverviewResponseData(TypedDict):
    stats: StatsData
    progress: dict[str, PipelineProgress]
    source_breakdown: SourceBreakdown
    recent_tutors: List[RecentTutor]
    recent_failures: List[RecentFailure]
    logs: List[LogEntry]


# =====================================================================
# 2.2 GET /api/schools
# =====================================================================

class SchoolItem(TypedDict):
    id: int
    name: str
    level: str
    mech_college: str
    auto_college: str
    source_a_status: Literal["done", "running", "pending", "failed"]
    source_b_status: Literal["done", "running", "pending", "failed"]
    tutor_count: int
    match_rate: int
    status: Literal["done", "partial", "running", "pending", "failed"]


class SchoolsSummary(TypedDict):
    done: int
    partial: int
    running: int
    pending: int
    failed: int


class SchoolsResponseData(TypedDict):
    total: int
    page: int
    page_size: int
    items: List[SchoolItem]
    summary: SchoolsSummary


# =====================================================================
# 2.3 GET /api/schools/{school_id}
# =====================================================================

class CollegeConfig(TypedDict):
    college: str
    category: Literal["mechanical", "automation"]
    faculty_config: dict
    tutor_count: int
    source_a_status: Literal["done", "running", "pending", "failed"]
    source_b_status: Literal["done", "running", "pending", "failed"]
    last_crawl_at: str


class SchoolDetailResponseData(TypedDict):
    id: int
    name: str
    level: str
    categories: List[CollegeConfig]


# =====================================================================
# 2.4 POST /api/crawl
# =====================================================================

class CrawlRequest(TypedDict):
    schools: List[str]
    categories: Optional[List[Literal["mechanical", "automation"]]]
    sources: Optional[List[Literal["source_a", "source_b"]]]
    force: Optional[bool]
    year: Optional[int]


class CrawlResponseData(TypedDict):
    task_id: str
    status: Literal["queued"]
    message: str


# =====================================================================
# 2.5 GET /api/tasks/{task_id}
# =====================================================================

class TaskProgress(TypedDict):
    total_steps: int
    completed_steps: int
    current_step: str
    percent: float


class TaskResponseData(TypedDict):
    task_id: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    progress: TaskProgress
    started_at: str
    estimated_remaining: str


# =====================================================================
# 2.6 GET /api/tutors
# =====================================================================

class EnrollmentDirection(TypedDict):
    code: str
    name: str


class EnrollmentData(TypedDict):
    in_roster: bool
    directions: List[EnrollmentDirection]
    degree_types: List[str]
    source_url: str


class TutorItem(TypedDict):
    name: str
    school: str
    college: str
    title: str
    level: Literal["博导", "硕导"]
    email: str
    profile_url: str
    areas: List[str]
    enrollment: Optional[EnrollmentData]
    match_status: Literal["merged", "partial_faculty", "partial_notice"]
    source_type: dict[str, str]


class TutorsResponseData(TypedDict):
    total: int
    page: int
    page_size: int
    items: List[TutorItem]


# =====================================================================
# 2.7 GET /api/tutors/{school}/{name}
# =====================================================================

class TutorDetailResponseData(TypedDict):
    # 继承 TutorItem 所有字段
    name: str
    school: str
    college: str
    title: str
    level: Literal["博导", "硕导"]
    email: str
    profile_url: str
    areas: List[str]
    enrollment: Optional[EnrollmentData]
    match_status: Literal["merged", "partial_faculty", "partial_notice"]
    source_type: dict[str, str]
    # 额外字段
    raw_ref: dict[str, str]


# =====================================================================
# 2.8 GET /api/tutors/export
# 返回文件下载，无 JSON 模型


# =====================================================================
# 2.9 GET /api/failures
# =====================================================================

class FailureItem(TypedDict):
    id: str
    school: str
    college: str
    source: Literal["Source A", "Source B"]
    error_type: Literal["http_403", "http_404", "timeout", "dns_error", "parse_error"]
    error_message: str
    url: str
    occurred_at: str
    retry_count: int
    status: Literal["active", "resolved", "ignored"]


class FailureSummary(TypedDict):
    http_error: int
    timeout: int
    parse_error: int


class FailuresResponseData(TypedDict):
    total: int
    summary: FailureSummary
    items: List[FailureItem]


# =====================================================================
# 2.10 POST /api/failures/retry
# =====================================================================

class RetryRequest(TypedDict):
    failure_ids: List[str]
    retry_all: bool


# 响应同 CrawlResponseData


# =====================================================================
# 2.11 POST /api/failures/{id}/ignore
# =====================================================================

class IgnoreResponseData(TypedDict):
    id: str
    status: Literal["ignored"]


# =====================================================================
# 2.12 GET /api/raw/{path}
# 返回原始文件，无 JSON 模型


# =====================================================================
# 2.13 GET /api/config
# =====================================================================

class GlobalConfig(TypedDict):
    delay_range: List[float]
    max_retries: int
    timeout: int
    cooldown_threshold: int
    cooldown_seconds: int
    workers: int
    year: int
    fuzzy_threshold: float
    user_agents: List[str]


class FacultyConfig(TypedDict):
    list_url: str
    list_type: Literal["static_html", "ajax_api"]
    list_item_selector: str
    detail_selectors: dict


class NoticeConfig(TypedDict):
    enabled: bool
    entry_url: str
    title_pattern: str
    template: str


class CategoryConfig(TypedDict):
    college: str
    category: Literal["mechanical", "automation"]
    faculty: FacultyConfig
    notice: NoticeConfig


class SchoolConfigItem(TypedDict):
    university: str
    categories: List[CategoryConfig]
    tutor_count: int
    verified: bool


class ConfigResponseData(TypedDict):
    global: GlobalConfig
    schools: List[SchoolConfigItem]


# =====================================================================
# 2.14 PUT /api/config/schools/{school_name}
# 请求体同 SchoolConfigItem 中的单条 categories 结构
# 响应
class ConfigSaveResponseData(TypedDict):
    status: Literal["ok"]
    message: str
    validation: dict


# =====================================================================
# 2.15 PUT /api/config/global
# 请求体同 GlobalConfig
# 响应同 ConfigSaveResponseData


# =====================================================================
# 2.16 POST /api/config/test
# =====================================================================

class TestConnectionRequest(TypedDict):
    url: str
    method: Literal["GET", "POST"]
    headers: dict


class TestConnectionResponseData(TypedDict):
    status_code: int
    reachable: bool
    response_time_ms: int
    content_type: str
    content_length: int
    sample_title: str


# =====================================================================
# 2.17 POST /api/config/import | GET /api/config/export
# 导入：multipart/form-data 文件上传
# 导出：文件下载
# 无额外 JSON 模型