# Agent A 指导书：服务层与接口层重构

> 对应阶段：阶段一 P0  
> 波次：Wave 1  
> 预计工作量：3-4 天

## 1. 目标

把 `main.py`（831 行）的 10 项职责拆到 `services/`，保留 CLI 编排；让 `api/server.py`（1391 行）调用服务层，而不是直接调用底层模块。

## 2. 可写文件

| 操作 | 文件路径 |
|---|---|
| 新建 | `services/__init__.py` |
| 新建 | `services/crawler_service.py` |
| 新建 | `services/merge_service.py` |
| 新建 | `services/export_service.py` |
| 修改 | `main.py` |
| 修改 | `api/server.py` |

**禁止修改**：`pipelines/`、`storage/`、`spiders/`、`config/plugins.py`、`utils/http.py`、`utils/cache.py`、`utils/progress.py`

## 3. 冻结接口契约

```python
# services/crawler_service.py
@dataclass
class CrawlTask:
    school: str
    category: str
    source: str
    year: int
    execution_state: str = "pending"   # pending/running/done/failed
    retry_count: int = 0
    last_attempt_at: str | None = None

@dataclass
class CrawlResult:
    task_id: str
    status: str                        # success/failed/skipped
    records: list[dict]
    failures: list[dict]

class CrawlerService:
    def __init__(self, config, cache, progress, session_factory): ...
    def build_tasks(self, args) -> list[CrawlTask]: ...
    def run_source_a(self, task: CrawlTask) -> CrawlResult: ...
    def run_source_b(self, task: CrawlTask) -> CrawlResult: ...
    def run_merge(self, tasks: list[CrawlTask]) -> list[dict]: ...
    def execute_task(self, task: CrawlTask) -> CrawlResult: ...
```

```python
# services/merge_service.py
class MergeService:
    def merge_sources(self, source_a_records: list[dict], source_b_records: list[dict]) -> list[dict]: ...
    def match_records(self, a: dict, b: dict) -> tuple[bool, str]: ...
```

```python
# services/export_service.py
class ExportService:
    def export_merged(self, records: list[dict], path) -> None: ...
    def export_summary(self, records: list[dict], path) -> None: ...
    def export_failures(self, failures: list[dict], path) -> None: ...
```

## 4. 现有代码分析

### 4.1 `main.py` 当前职责清单（需拆分）

| 行范围 | 职责 | 归属 |
|---|---|---|
| 68-81 | `CrawlTask` 数据类 | → `services/crawler_service.py` |
| 84-88 | `SchoolConfig` 数据类 | → `services/crawler_service.py` |
| 94-148 | `CircuitBreaker` + `_extract_domain` | → 删除，改为调用 `PoliteSession.is_blocked()` |
| 156-181 | `load_school_configs` + `get_college_config` | → `services/crawler_service.py`（私有方法） |
| 189-281 | `run_source_a()` | → `CrawlerService.run_source_a()` |
| 284-354 | `run_source_b()` | → `CrawlerService.run_source_b()` |
| 357-427 | `run_merge()` | → `CrawlerService.run_merge()` + `MergeService` |
| 430-454 | `run_processor_pipeline()` + `run_export_pipeline()` | → `ExportService` |
| 457-560 | `execute_task()` | → `CrawlerService.execute_task()` |
| 568-643 | `build_tasks()` | → `CrawlerService.build_tasks()` |
| 652-831 | `main()` | 保留 CLI 编排，业务逻辑委托服务层 |

### 4.2 `api/server.py` 当前关键依赖

| 调用点 | 当前直接依赖 | 重构后 |
|---|---|---|
| `_run_crawl_task()` L396-472 | `from main import build_tasks, execute_task, run_export_pipeline` | `from services.crawler_service import CrawlerService` |
| `_read_all_merged_records()` L120-134 | 直接 `open()` 读 JSONL | 委托 `ExportService` 或 `JSONLStore` |
| `api_crawl()` L314-393 | 直接创建任务 + 启动线程 | 委托 `CrawlerService` |
| 配置相关 | `from config.loader import ...` | 保持不变（Agent A 不动 config 层） |

## 5. 实施步骤

### Step 1：创建 `services/__init__.py`

```python
"""服务层：封装核心业务逻辑，供 main.py CLI 和 api/server.py 调用。"""
```

### Step 2：创建 `services/crawler_service.py`

1. 把 `CrawlTask` 和 `SchoolConfig` 数据类搬入
2. 实现 `CrawlerService`：
   - `__init__(config, cache, progress, session_factory)` — 注入依赖
   - `build_tasks(args)` — 从 `main.py` 的 `build_tasks()` 搬入，保留所有过滤逻辑（resume/retry_failed）
   - `run_source_a(task)` — 从 `main.py` 的 `run_source_a()` 搬入
   - `run_source_b(task)` — 从 `main.py` 的 `run_source_b()` 搬入
   - `run_merge(tasks)` — 从 `main.py` 的 `run_merge()` 搬入
   - `execute_task(task)` — 从 `main.py` 的 `execute_task()` 搬入
3. **关键**：不直接 import `CircuitBreaker`，改为调用 `session.is_blocked(domain)`（Agent E 提供）
4. 保留旧函数名作为兼容层：`run_source_a = CrawlerService.run_source_a` 等

### Step 3：创建 `services/merge_service.py`

1. 封装 `pipelines/merge.py` 的 `merge_sources` 和 `match_records`
2. 提供更面向对象的接口，内部调用现有 `pipelines.merge`

### Step 4：创建 `services/export_service.py`

1. 封装 `pipelines/export.py` 的导出函数
2. 封装 `run_processor_pipeline()` 和 `run_export_pipeline()`
3. 内部仍调用现有 `pipelines.export` 和 `plugins` 模块

### Step 5：改造 `main.py`

1. 删除 `CircuitBreaker` 类（约 55 行）
2. 删除 `run_source_a`、`run_source_b`、`run_merge`、`execute_task`、`build_tasks` 的实现
3. `main()` 函数改为：
   ```python
   from services.crawler_service import CrawlerService
   service = CrawlerService(config, cache, progress, PoliteSession)
   tasks = service.build_tasks(args)
   # 并发执行...
   ```
4. 保留所有 CLI 参数定义不变
5. 保留 `main()` 函数的参数解析、日志配置、统计输出

### Step 6：改造 `api/server.py`

1. `_run_crawl_task()` 改用 `CrawlerService`：
   ```python
   from services.crawler_service import CrawlerService
   service = CrawlerService(...)
   tasks = service.build_tasks(...)
   ```
2. 保留所有 Flask 路由定义不变
3. `_read_all_merged_records()` 短期内可保留（长期由 B 的 `JSONLStore` 替换）

## 6. 同步点

| 依赖 | 接口 | 状态 |
|---|---|---|
| Agent E | `PoliteSession.is_blocked(domain)` | 开发期间先用 `PoliteSession._blocked_domains` 临时访问，集成时切换 |
| Agent B | `JSONLStore` | 开发期间继续用 `open()`，集成时切换 |
| Agent C | `SpiderEngine` | 不直接依赖，继续调用旧函数 |

## 7. 验收命令

```bash
# 1. 语法检查
python -m py_compile services/crawler_service.py
python -m py_compile services/merge_service.py
python -m py_compile services/export_service.py
python -m py_compile main.py
python -m py_compile api/server.py

# 2. 集成测试
pytest tests/test_integration.py -q

# 3. CLI 手动验证
python main.py --school "东南大学" --source source_a --force
# 检查 data/output/ 生成 .jsonl 和 summary.xlsx

# 4. API 手动验证
python api/server.py --port 5001 --no-browser
# 访问 /api/overview 检查返回正常
```

## 8. 注意事项

1. **不删除旧函数**：`run_source_a` 等旧函数名需保留至少一个版本的兼容期
2. **不改配置格式**：`school_data.json` 结构不变
3. **不改 JSONL Schema**：输出格式 `schema_version: 1` 不变
4. **日志格式不变**：`%(asctime)s - %(levelname)s - %(message)s`
5. **`CircuitBreaker` 迁移策略**：先在 `CrawlerService` 内部保留一份简化版，集成时切换到 `PoliteSession.is_blocked()`
