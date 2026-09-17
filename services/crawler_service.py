"""Crawler application service. One injected session owns all HTTP circuit state."""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from config.loader import load_schools_config
from parsers import dispatch
from pipelines.export import add_failure, append_failures, get_active_failures
from spiders import SPIDER_ENGINE_REGISTRY
from storage import JSONLStore, path_lock
from utils.http import PoliteSession
from utils.progress import get_progress_tracker
from utils.errors import classify_error
from .merge_service import MergeService
from .export_service import ExportService


@dataclass
class CrawlTask:
    university: str
    college: str
    category: str
    source: str
    year: int
    force: bool = False
    config: dict = field(default_factory=dict)
    execution_state: str = "pending"
    retry_count: int = 0
    last_attempt_at: str | None = None

    def key(self):
        return f"{self.university}|{self.college}|{self.source}"

    @property
    def school(self):
        return self.university


@dataclass
class CrawlResult:
    task_id: str
    status: str
    records: list
    failures: list
    error_message: str | None = None
    error_type: str = "none"


class CrawlerService:
    def __init__(self, config=None, cache=None, progress=None, session_factory=None,
                 output_dir="data/output"):
        self.config = load_schools_config() if config is None else config
        self.cache = cache
        self.progress = progress if progress is not None else get_progress_tracker()
        self.session = (session_factory or PoliteSession)()
        self.output_dir = Path(output_dir)
        self.exporter = ExportService()
        self.merger = MergeService()

    def build_tasks(self, args):
        schools = getattr(args, "school", None) or ["__all__"]
        categories = getattr(args, "category", None) or []
        sources = getattr(args, "source", None) or ["source_a", "source_b"]
        force = getattr(args, "force", False)
        retry = getattr(args, "retry_failed", False)
        active = set()
        if retry:
            for failure in get_active_failures(self.output_dir / "failures.json"):
                source = {"Source A": "source_a", "Source B": "source_b"}.get(failure.get("source"), failure.get("source"))
                active.add((failure.get("school"), failure.get("college"), source))
        tasks = {}
        for school in self.config:
            university = school["university"]
            if "__all__" not in schools and university not in schools:
                continue
            for cat in school.get("categories", []):
                if categories and cat["category"] not in categories:
                    continue
                for source in sources:
                    if source == "source_a" and not cat.get("faculty", {}).get("list_url"):
                        continue
                    if source == "source_b" and not cat.get("notice", {}).get("enabled", False):
                        continue
                    if source not in ("source_a", "source_b"):
                        continue
                    if retry and (university, cat["college"], source) not in active:
                        continue
                    if getattr(args, "resume", False) and not force and not retry:
                        if self.progress.get_school_status(university, cat["college"]).get(source) == "done":
                            continue
                    task = CrawlTask(university, cat["college"], cat["category"], source,
                                     args.year, force or retry, cat)
                    tasks[task.key()] = task
        return list(tasks.values())

    def _failure(self, task, error):
        kind = classify_error(error)
        source_config = task.config.get("faculty" if task.source == "source_a" else "notice", {})
        failure = add_failure(uuid4().hex, task.university, task.college,
                              "Source A" if task.source == "source_a" else "Source B",
                              kind, str(error), source_config.get("list_url", source_config.get("entry_url", "")))
        return CrawlResult(task.key(), "failed", [], [failure], str(error), kind)

    def run_source_a(self, task):
        try:
            cfg = task.config.get("faculty", {})
            url = cfg.get("list_url", "")
            if not url:
                raise ValueError(f"{task.university}/{task.college} 缺少 Source A 列表页 URL")
            name = cfg.get("list_type", "static_html")
            name = "static_list" if name == "static_html" else name
            engine = SPIDER_ENGINE_REGISTRY[name](self.session, self.cache)
            selectors = cfg.get("selectors") or {
                "item": cfg.get("list_item_selector", "li"),
                "name": cfg.get("list_name_selector", "title"),
                "profile": "href", "research": cfg.get("list_research_selector", "")}
            kwargs = {"selectors": selectors, "force": task.force}
            if name == "ajax_api":
                kwargs.update(site_id=cfg.get("api_params", {}).get("siteId"),
                              referer=cfg.get("referer") or url, extra_params=cfg.get("api_params", {}))
            teachers = engine.fetch(url, **kwargs)
            detail_engine = SPIDER_ENGINE_REGISTRY["detail_parser"](self.session, self.cache)
            records = []
            for teacher in teachers:
                record = dict(teacher)
                profile = record.get("profile_url")
                if profile:
                    try:
                        detail = detail_engine.fetch(profile, selectors=cfg.get("detail_selectors", {}), force=task.force)
                        if detail:
                            record.update(detail[0])
                    except Exception as error:
                        self.progress.add_log("WARN", f"{task.university}/{task.college} 详情页解析失败: {error}")
                record.update(university=task.university, college=task.college,
                              category=task.category, source_type="官网师资页")
                records.append(record)
            return CrawlResult(task.key(), "success", records, [])
        except Exception as error:
            return self._failure(task, error)

    def run_source_b(self, task):
        try:
            cfg = task.config.get("notice", {})
            if not cfg.get("enabled", False):
                return CrawlResult(task.key(), "success", [], [])
            engine = SPIDER_ENGINE_REGISTRY["yzw_api"](self.session, self.cache)
            code = cfg.get("school_code") or engine._client.get_school_code(task.university)
            if not code:
                raise ValueError(f"无法获取 {task.university} 研招网学校代码")
            codes = cfg.get("major_codes", {}).get(task.category)
            raw_path = Path(f"data/raw/{task.university}/{task.year}/yzw/major_{code}.json")
            # The legacy client shares this raw filename across colleges. Keep
            # fetch+parse in one transaction so a peer cannot replace its input.
            with path_lock(raw_path):
                raw = engine.fetch(school_code=code, year=task.year, major_codes=codes,
                                   category=task.category, university=task.university)
                if not raw:
                    return CrawlResult(task.key(), "success", [], [])
                records = dispatch(str(raw_path), {
                    "university": task.university, "college": task.college,
                    "category": task.category, "year": task.year, "school_code": code,
                    "template": cfg.get("template", "yzw_major"), "major_codes": codes})
            return CrawlResult(task.key(), "success", records, [])
        except Exception as error:
            return self._failure(task, error)

    def execute_task(self, task):
        if not task.force and self.progress.get_school_status(task.university, task.college).get(task.source) == "done":
            task.execution_state = "skipped"
            return CrawlResult(task.key(), "skipped", [], [])
        if task.last_attempt_at is not None:
            task.retry_count += 1
        task.last_attempt_at = datetime.now().isoformat()
        task.execution_state = "running"
        try:
            if task.source not in ("source_a", "source_b"):
                raise ValueError(f"未知数据源: {task.source}")
            result = getattr(self, "run_" + task.source)(task)
            if result.status == "success":
                suffix = "faculty" if task.source == "source_a" else "notice"
                JSONLStore(self.output_dir / f"{task.university}_{task.college}_{suffix}.jsonl").write_all(result.records)
                self.progress.update_school_status(task.university, task.college, **{task.source: "done"})
                self.run_merge([task])
        except Exception as error:
            result = self._failure(task, error)
        task.execution_state = result.status
        if result.status == "failed":
            append_failures(result.failures, self.output_dir / "failures.json")
            self.progress.update_school_status(task.university, task.college, **{task.source: "failed"})
            self.progress.add_log("ERROR", result.error_message)
        return result

    def run_merge(self, tasks):
        merged = []
        seen = set()
        for task in tasks:
            identity = (task.university, task.college)
            if identity in seen:
                continue
            seen.add(identity)
            stem = f"{task.university}_{task.college}"
            output = self.output_dir / f"{stem}.jsonl"
            with path_lock(output):
                faculty = JSONLStore(self.output_dir / f"{stem}_faculty.jsonl").read_all()
                notice = JSONLStore(self.output_dir / f"{stem}_notice.jsonl").read_all()
                records = self.merger.merge_sources(faculty, notice)
                records = self.exporter.run_processor_pipeline(records, {
                    "university": task.university, "college": task.college, "year": task.year})
                JSONLStore(output).write_all(records)
                self.progress.update_school_status(task.university, task.college,
                                                   merged="done" if records else "pending", tutor_count=len(records))
                self.progress.update_source_breakdown(*(
                    sum(r["match_status"] == status for r in records)
                    for status in ("merged", "partial_notice", "partial_faculty")), 0)
                merged.extend(records)
        return merged
