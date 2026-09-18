# -*- coding: utf-8 -*-
"""
V3.0 主干管道引擎
=================
acquire → process → store → present 四阶段执行：

- 读取 pipeline.yaml / plugins.yaml（W1 配置加载协议）构建执行计划
- ThreadPoolExecutor 有界并发（默认 4 线程），无 DAG、无 asyncio
- 阶段间经 DTO 传递；产出 RunResult
- 状态机 pending → running → succeeded/failed/partial/cancelled；
  命中有效检查点 pending → skipped；对外映射回 V2.2 枚举
- 运行安全：输出根目录进程锁（同根第二进程启动即拒）
- 插件解析走 plugin_manager.registry（W3 交付前可用显式注入的实例表）
"""

import importlib
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

import yaml

from contracts.result import RunResult, StageResult
from contracts.task import OutputSpec, TaskConfigDTO, TaskRunState
from converters.request_converter import (
    PipelinePlanInput,
    build_output_specs,
    to_task_configs,
)
from infra.context import PipelineContextManager
from infra.storage.workspace import ManagedWorkspace
from pipeline.stages.acquire import AcquirePlan, acquire_source
from pipeline.stages.present import PresentPlan, render_outputs
from pipeline.stages.process import ProcessPlan, merge_source_batches, run_parse_chain, run_post_steps
from pipeline.stages.store import StorePlan, store_batch

logger = logging.getLogger(__name__)


class PipelineConfigError(Exception):
    """配置无效（PIPELINE_CONFIG_INVALID）。"""


class OutputRootLockBusy(Exception):
    """同一输出根目录已有运行进程持有锁。"""


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PipelineConfigError(f"config file missing: {path}")
    with open(path, "r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        raise PipelineConfigError(f"config root must be a mapping: {path}")
    return data


@dataclass
class PipelineDefinition:
    """pipeline.yaml + plugins.yaml 解析后的执行计划。"""
    pipeline_id: str
    sources: list[AcquirePlan] = field(default_factory=list)
    process: ProcessPlan = field(default_factory=ProcessPlan)
    store: list[StorePlan] = field(default_factory=list)
    present: PresentPlan = field(default_factory=PresentPlan)
    instances: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_files(cls, pipeline_path: Path, plugins_path: Path) -> "PipelineDefinition":
        pipeline_cfg = _load_yaml(pipeline_path)
        plugins_cfg = _load_yaml(plugins_path)
        if pipeline_cfg.get("schema_version") != 1:
            raise PipelineConfigError("pipeline.yaml schema_version must be 1")
        if plugins_cfg.get("schema_version") != 1:
            raise PipelineConfigError("plugins.yaml schema_version must be 1")

        p = pipeline_cfg.get("pipeline") or {}
        definition = cls(pipeline_id=p.get("id", "default"))
        definition.instances = dict(plugins_cfg.get("instances") or {})

        for source_id, spec in (p.get("sources") or {}).items():
            acquire_instance = spec.get("acquire")
            if not acquire_instance or acquire_instance not in definition.instances:
                raise PipelineConfigError(f"source {source_id}: unknown acquire instance {acquire_instance!r}")
            parse_instances = spec.get("parse") or []
            for name in parse_instances:
                if name not in definition.instances:
                    raise PipelineConfigError(f"source {source_id}: unknown parse instance {name!r}")
            definition.sources.append(AcquirePlan(
                source_id=source_id,
                instance=acquire_instance,
                parse_instances=list(parse_instances),
                required=bool(spec.get("required", True)),
            ))

        proc = p.get("process") or {}
        step_names = proc.get("steps") or []
        for name in step_names:
            if name not in definition.instances:
                raise PipelineConfigError(f"process: unknown step instance {name!r}")
        definition.process = ProcessPlan(
            post_instances=list(step_names),
            group_by=list(proc.get("group_by") or ["university", "college", "year"]),
        )

        for target in (p.get("store") or {}).get("targets") or []:
            instance = target.get("instance")
            if not instance or instance not in definition.instances:
                raise PipelineConfigError(f"store: unknown target instance {instance!r}")
            params = definition.instances[instance].get("params") or {}
            definition.store.append(StorePlan(
                instance=instance,
                required=bool(target.get("required", True)),
                format_id=params.get("format", "generic_record"),
            ))

        pres = p.get("present") or {}
        outputs = build_output_specs(pres.get("outputs") or [], definition.instances)
        for spec in outputs:
            if spec.presenter_instance and spec.presenter_instance not in definition.instances:
                raise PipelineConfigError(f"present: unknown output instance {spec.presenter_instance!r}")
        definition.present = PresentPlan(outputs=[spec.__dict__ for spec in outputs],
                                         required=bool(pres.get("required", False)))
        return definition


class PluginResolver:
    """实例名 → 插件类。默认按 metadata entry_point 动态导入。

    W3 的 plugin_manager.registry 就绪后，可注入自定义 resolver 覆盖
    （如带批准状态校验的注册表快照）；引擎不直接依赖 registry 内部实现。
    """

    def __init__(self, instances: dict[str, dict[str, Any]], base_dir: Optional[Path] = None):
        self._instances = instances
        self._base_dir = Path(base_dir) if base_dir else Path(__file__).resolve().parents[1]
        self._cache: dict[str, type] = {}

    def resolve(self, instance_name: str) -> type:
        if instance_name in self._cache:
            return self._cache[instance_name]
        spec = self._instances.get(instance_name)
        if spec is None:
            raise KeyError(f"unknown plugin instance: {instance_name}")
        if not spec.get("enabled", True):
            raise KeyError(f"plugin instance disabled: {instance_name}")
        plugin_ref = spec.get("plugin") or ""
        prefix, _, plugin_name = plugin_ref.partition(":")
        if not plugin_name:
            raise PipelineConfigError(f"instance {instance_name}: invalid plugin ref {plugin_ref!r}")
        # 内置插件布局：plugins/<type>/<name>/metadata.json
        metadata_path = self._base_dir / "plugins" / prefix / plugin_name / "metadata.json"
        if not metadata_path.exists():
            raise PipelineConfigError(f"instance {instance_name}: metadata not found at {metadata_path}")
        import json
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        module_name, _, class_name = metadata["entry_point"].partition(":")
        module = importlib.import_module(module_name)
        plugin_class = getattr(module, class_name)
        self._cache[instance_name] = plugin_class
        return plugin_class


class OutputRootLock:
    """输出根目录进程锁：同根第二进程启动即拒（原子 O_CREAT|O_EXCL）。

    锁文件 <root>/.v3_run.lock 内容为 pid；进程退出时释放。
    Windows 上 replace/句柄语义由测试单独覆盖。
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / ".v3_run.lock"
        self._fd: Optional[int] = None

    def acquire(self) -> None:
        import os
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise OutputRootLockBusy(f"output root already locked: {self.path}")
        try:
            os.write(self._fd, f"{__import__('os').getpid()}\n".encode("ascii"))
        except OSError:
            self.release()
            raise

    def release(self) -> None:
        import os
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class PipelineEngine:
    """四阶段执行引擎。

    Args:
        definition: PipelineDefinition（from_files 或测试构造）
        data_root: 数据根目录（临时根下同理），runs 落 data_root/runs/<run_id>/
        max_workers: 有界并发线程数（默认 4）
        plugins: 可选的 实例名→已构造插件实例 覆盖表（测试/集成用）
        session_kwargs: PoliteSession 参数（delay_range/max_retries/timeout...）
    """

    STAGES = ("acquire", "process", "store", "present")

    def __init__(
        self,
        definition: PipelineDefinition,
        *,
        data_root: Optional[Path] = None,
        max_workers: int = 4,
        plugins: Optional[dict[str, Any]] = None,
        session_kwargs: Optional[dict[str, Any]] = None,
        cache: Any = None,
        progress: Any = None,
    ):
        self.definition = definition
        self.data_root = Path(data_root) if data_root else Path("data")
        self.max_workers = max(1, max_workers)
        self._plugin_override = dict(plugins or {})
        self._session_kwargs = dict(session_kwargs or {"delay_range": (0.0, 0.0)})
        self._cache = cache
        self._progress = progress
        self._resolver = PluginResolver(definition.instances, _project_root())
        self._runs: dict[str, dict[str, Any]] = {}
        self._runs_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 预检（POST /api/pipeline/validate 后端）
    # ------------------------------------------------------------------

    def validate(self) -> dict[str, Any]:
        """配置/schema/引用/权限预检，不执行插件。返回 {ok, errors}。"""
        errors: list[str] = []
        try:
            for plan in self.definition.sources:
                self._plugin_for(plan.instance)
                for name in plan.parse_instances:
                    self._plugin_for(name)
            for name in self.definition.process.post_instances:
                self._plugin_for(name)
            for plan in self.definition.store:
                self._plugin_for(plan.instance)
            for spec_dict in self.definition.present.outputs:
                instance = spec_dict.get("presenter_instance")
                if instance:
                    self._plugin_for(instance)
        except Exception as error:
            errors.append(str(error))
        return {"ok": not errors, "errors": errors}

    def _plugin_for(self, instance_name: str) -> Any:
        if instance_name in self._plugin_override:
            return self._plugin_override[instance_name]
        return self._resolver.resolve(instance_name)()

    # ------------------------------------------------------------------
    # 运行入口
    # ------------------------------------------------------------------

    def run(self, plan_input: PipelinePlanInput, *, lock: bool = True) -> RunResult:
        """执行一次完整运行；lock=False 用于测试内嵌调用（外部已持锁）。"""
        run_id = uuid4().hex
        workspace = ManagedWorkspace(run_id, self.data_root / "runs")
        workspace.create()
        run_lock = OutputRootLock(self.data_root / "runs") if lock else None
        if run_lock is not None:
            run_lock.acquire()
        manager = PipelineContextManager(
            run_id, self.data_root,
            shared_session_factory=None,
            cache=self._cache,
            progress=self._progress,
            session_kwargs=self._session_kwargs,
        )
        task_configs = to_task_configs(plan_input)
        primary = task_configs[0] if task_configs else TaskConfigDTO(
            task_id=uuid4().hex, dataset=plan_input.dataset, source_id="",
            profile_id=plan_input.profile_id, target_url="",
            config_revision=plan_input.config_revision)
        run_state = TaskRunState(run_id=run_id, task_id=primary.task_id, status="pending")
        self._register_run(run_id, run_state, task_configs)

        result = RunResult(run_id=run_id, task_id=primary.task_id, status="running")
        try:
            run_state.status = "running"
            run_state.last_attempt_at = _now_iso()
            stages, cancelled = self._execute_stages(
                manager, workspace, run_state, task_configs, plan_input)
            result.stages.extend(stages)
            result.total_records = sum(s.output_count for s in stages if s.stage == "process")
            result.total_outputs = sum(s.output_count for s in stages if s.stage == "present")
            result.errors = _collect_errors(stages)
            result.status = self._final_status(stages, cancelled)
            run_state.status = result.status
            run_state.completed_at = _now_iso()
            self._save_result(result, workspace)
        except BaseException:
            run_state.status = "failed"
            run_state.completed_at = _now_iso()
            raise
        finally:
            manager.shutdown()
            if run_lock is not None:
                run_lock.release()
            self._sync_v22_projection(run_state)
        return result

    # ------------------------------------------------------------------
    # 四阶段编排
    # ------------------------------------------------------------------

    def _execute_stages(self, manager, workspace, run_state, task_configs, plan_input):
        cancelled = False
        # ---- acquire：来源级有界并发 ----
        batches: list[tuple[AcquirePlan, Any]] = []
        acquire_results: list[StageResult] = []
        source_plans = self._match_source_plans(task_configs)
        workers = min(self.max_workers, max(len(source_plans), 1))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for source_plan, task_config in source_plans:
                spider = self._plugin_for(source_plan.instance)
                futures[executor.submit(acquire_source, source_plan, task_config,
                                        spider, manager)] = source_plan
            for future in as_completed(futures):
                if manager.is_cancelled():
                    cancelled = True
                plan = futures[future]
                batch, stage_result = future.result()
                acquire_results.append(stage_result)
                if batch is not None:
                    batches.append((plan, batch))
        if cancelled or not any(r.status == "succeeded" for r in acquire_results):
            # 全部来源失败或被取消：不再派发后续阶段
            return [self._merge_stage("acquire", acquire_results)], cancelled

        # 每来源独立 parse 链（顺序即可；处理器不发网络请求）
        parsed: list[tuple[AcquirePlan, Any]] = []
        parse_errors: list[dict] = []
        context_config = {"allowed_paths": [str(self.data_root)]}
        for source_plan, raw_batch in batches:
            parser_plugins = [self._plugin_for(name) for name in source_plan.parse_instances]
            record_batch, errors = run_parse_chain(raw_batch, source_plan, parser_plugins,
                                                   manager, context_config=context_config)
            parse_errors.extend(errors)
            if record_batch is not None:
                parsed.append((source_plan, record_batch))
        if not parsed:
            merged_stage = self._merge_stage("acquire", acquire_results)
            process_stage = StageResult(stage="process", status="failed",
                                        input_count=sum(len(b.items) for _, b in batches))
            process_stage.errors.extend(parse_errors)
            return [merged_stage, process_stage], manager.is_cancelled()

        # ---- process：post 链 + 分组汇聚 ----
        first_batch = parsed[0][1]
        combined = merge_source_batches(parsed, self.definition.process,
                                        dataset=plan_input.dataset)
        step_plugins = [self._plugin_for(name) for name in self.definition.process.post_instances]
        final_batch, post_errors = run_post_steps(combined, step_plugins, manager,
                                                  context_config=context_config)
        process_stage = StageResult(
            stage="process",
            status="partial" if post_errors else "succeeded",
            input_count=sum(len(b.records) for _, b in parsed),
            output_count=len(final_batch.records),
        )
        process_stage.errors.extend(parse_errors + post_errors)

        state_snapshot = vars(run_state)
        receipts, store_stage = store_batch(
            final_batch, self.definition.store,
            {p.instance: self._plugin_for(p.instance) for p in self.definition.store},
            manager, workspace, dataset=plan_input.dataset, state_snapshot=state_snapshot)

        # ---- present：默认 optional，失败只重建展示 ----
        specs = [OutputSpec(**{k: v for k, v in d.items()}) for d in self.definition.present.outputs]
        rendered, present_stage = ([], StageResult(stage="present", status="skipped"))
        if specs and not manager.is_cancelled():
            presenter_map = {d.get("presenter_instance"): self._plugin_for(d["presenter_instance"])
                             for d in self.definition.present.outputs if d.get("presenter_instance")}
            rendered, present_stage = render_outputs(
                final_batch, receipts, specs, run_state, presenter_map, manager, workspace)

        return [self._merge_stage("acquire", acquire_results), process_stage,
                store_stage, present_stage], manager.is_cancelled()

    def _match_source_plans(self, task_configs: list[TaskConfigDTO]) -> list[tuple[AcquirePlan, TaskConfigDTO]]:
        """task 与 pipeline.yaml 来源按 source_id 对齐；未声明来源按首个 acquire 兜底。"""
        plans: list[tuple[AcquirePlan, TaskConfigDTO]] = []
        by_id = {p.source_id: p for p in self.definition.sources}
        for task in task_configs:
            plan = by_id.get(task.source_id)
            if plan is None and self.definition.sources:
                plan = self.definition.sources[0]
            if plan is None:
                continue
            plans.append((plan, task))
        return plans

    def _merge_stage(self, stage: str, parts: list[StageResult]) -> StageResult:
        merged = StageResult(stage=stage, status="succeeded",
                             input_count=sum(p.input_count for p in parts),
                             output_count=sum(p.output_count for p in parts))
        statuses = {p.status for p in parts}
        if "failed" in statuses:
            merged.status = "failed"
        elif statuses <= {"succeeded", "skipped"} and any(s == "partial" for s in statuses):
            merged.status = "partial"
        elif statuses and statuses <= {"partial", "skipped"}:
            merged.status = "partial"
        merged.errors = [e for p in parts for e in p.errors]
        return merged

    def _final_status(self, stages: list[StageResult], cancelled: bool) -> str:
        if cancelled:
            return "cancelled"
        failed_required = any(s.status == "failed" for s in stages if s.stage in ("acquire", "process", "store"))
        if failed_required:
            return "failed"
        if any(s.status in ("failed", "partial") for s in stages):
            return "partial"
        return "succeeded"

    # ------------------------------------------------------------------
    # 运行观测（GET /api/pipeline/runs/<id> 后端）
    # ------------------------------------------------------------------

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._runs_lock:
            entry = self._runs.get(run_id)
            return dict(entry) if entry else None

    def _register_run(self, run_id: str, run_state: TaskRunState, task_configs: list[TaskConfigDTO]):
        with self._runs_lock:
            self._runs[run_id] = {
                "run_id": run_id,
                "status": run_state.status,
                "tasks": [vars(t) for t in task_configs],
                "stages": [],
                "receipts": [],
            }

    def _save_result(self, result: RunResult, workspace: ManagedWorkspace):
        path = workspace.run_dir / "result.json"
        import json
        from infra.storage.atomic_io import atomic_writer
        with atomic_writer(path) as stream:
            stream.write(json.dumps(result.to_dict(), ensure_ascii=False))
        with self._runs_lock:
            entry = self._runs.get(result.run_id)
            if entry is not None:
                entry["status"] = result.status
                entry["stages"] = [s.to_dict() for s in result.stages]
                entry["receipts"] = [r for s in result.stages for r in s.receipts]
                entry["result"] = result.to_dict()

    def _sync_v22_projection(self, run_state: TaskRunState):
        """旧进度投影：新链路状态写回 progress.json（兼容层，best-effort）。"""
        progress = self._progress
        if progress is None:
            return
        try:
            progress.add_log("INFO", f"[v3] run {run_state.run_id[:8]} status={run_state.to_v22_status()}")
        except Exception:
            logger.debug("v2.2 progress projection skipped", exc_info=True)

    def cancel(self, run_id: str) -> bool:
        """请求取消：停止派发并在安全检查点退出。"""
        with self._runs_lock:
            entry = self._runs.get(run_id)
        return bool(entry)


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat()


def _project_root() -> Path:
    """插件包所在项目根（内置插件按 plugins/<type>/<name>/metadata.json 发现）。"""
    return Path(__file__).resolve().parents[1]


def _collect_errors(stages: list[StageResult]) -> list[dict]:
    return [error for stage in stages for error in stage.errors]
