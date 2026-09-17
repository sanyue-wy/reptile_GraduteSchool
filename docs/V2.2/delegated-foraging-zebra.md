# 工程重构优化计划（2026-09-17 完善版）

## 背景与问题分析（重新审查确认）

工程 `reptile_GraduteSchool` 是双一流高校研究生导师信息采集系统。重新审查代码（2026-09-17）确认以下关键数据：

- `main.py`：831 行（与初步分析一致），直接导入 12 个模块（line 29-50），职责混合严重
- `api/server.py`：1391 行（比初步估计的 1250+ 行更多），17 个 REST 接口，直接调用底层模块
- `spiders/yzw_api.py`：285 行，直接实例化 `YzwClient`（line 318）并调用 `fetch_major_directory`（line 331）
- `tests/test_integration.py`：仅 5 个测试方法，无熔断/缓存/插件安全测试
- `config/plugins.py`：549 行，安全检查逻辑分散在 `_check_import_safety`（line 261）、`_validate_plugin_source`（line 286）、`BLOCKED_MODULES`（line 44）、`BLOCKED_CALLS`（line 45）

### 核心缺陷（重新审查确认无遗漏）

1. **职责混乱**：`main.py` 同时承担 CLI 解析、任务构建、并发调度、熔断控制、进度追踪、错误分类、失败记录管理、导出触发、统计输出（共 10 项职责）
2. **缺乏抽象层**：无服务层、无数据访问层、无任务抽象、无引擎抽象
3. **扩展性差**：新增数据源需修改 `main.py`（`run_source_a`/`run_source_b` 硬编码），新增插件需手动注册
4. **性能与可维护性**：并发任务通过文件系统通信（`progress.json`、`failures.json`），熔断与冷却机制独立管理状态不一致
5. **测试覆盖不足**：集成测试仅覆盖 Source A 流程，缺少熔断/缓存/插件安全测试

---

## 优化方案（5 阶段，渐进式重构）

### 阶段一：建立服务层（P0，预计 3-5 天）

目标：分离 `main.py` 的业务逻辑，保留 CLI 编排职责。

**新建文件**：
- `services/crawler_service.py`：封装 `run_source_a`（line 189-281）、`run_source_b`（line 284-354）、`run_merge`（line 357-427）、`execute_task`（line 457-560）的完整执行链，管理 `CrawlTask` 执行状态
- `services/merge_service.py`：封装 `merge_sources`（line 218-267 in `pipelines/merge.py`）的三阶匹配（精确/去空格/模糊）
- `services/export_service.py`：封装 `export_merged`（line 31-63）、`export_summary`（line 66-123）、`export_failures`（line 126-159）

**修改文件**：
- `main.py`：将业务逻辑迁移到服务层，保留 CLI 编排（`build_tasks`、`main()` 流程控制）
- `api/server.py`：使用服务层接口，替代直接调用 `main.build_tasks`、`execute_task`、`run_export_pipeline`

**验证方式**：
- `pytest tests/test_integration.py` 行为不变
- `python main.py --school "东南大学" --source source_a --force` 运行正常
- `data/output/` 生成正确的 `.jsonl` 和 `summary.xlsx`

---

### 阶段二：抽象数据访问层（P1，预计 2 天）

目标：统一文件读写接口，替换所有直接 `open()` 操作，保留原子写入机制。

**新建文件**：
- `storage/jsonl_store.py`：统一 JSONL 读写（处理 `data/output/*_faculty.jsonl`、`*_notice.jsonl`、`*.jsonl`）
- `storage/progress_store.py`：封装 `ProgressTracker` 的原子读写（`data/output/progress.json`）
- `storage/config_store.py`：封装 `load_schools_config`、`save_school_config` 的配置访问

**修改文件**：
- `pipelines/merge.py`：使用 `JSONLStore` 替代直接 `open()`
- `pipelines/export.py`：使用 `JSONLStore` 替代直接 `open()`
- `utils/progress.py`：使用 `ProgressStore` 替代直接文件操作

**验证方式**：
- 检查所有 `.json`/`.jsonl` 读写路径是否通过 `storage` 层访问
- 确认原子写入机制（`tempfile.mkstemp` + `os.replace`）未被破坏

---

### 阶段三：统一爬虫引擎接口（P2，预计 2 天）

目标：降低 `spiders/` 模块间直接依赖，提升可扩展性。

**新建文件**：
- `spiders/engine.py`：抽象基类 `SpiderEngine`，包含 `fetch(url, session, **kwargs) -> list[dict]` 和 `parse(html, selectors) -> list[dict]`

**修改文件**：
- `spiders/static_list.py`（149行）：继承 `SpiderEngine`，实现 `fetch()` 和 `parse()`
- `spiders/ajax_api.py`（141行）：继承 `SpiderEngine`，实现 `fetch()`（API 模式）
- `spiders/yzw_api.py`（285行）：继承 `SpiderEngine`，实现 `fetch()`（研招网 API 模式）
- `spiders/detail_parser.py`（290行）：继承 `SpiderEngine`，实现 `parse()`（详情页解析）
- `spiders/js_render.py`（130行）：继承 `SpiderEngine`，实现 `fetch()`（Playwright 模式）
- `spiders/pdf_list.py`（未直接读取，但存在）：继承 `SpiderEngine`，实现 `fetch()`

**验证方式**：
- 所有爬虫引擎可通过 `SpiderEngine` 统一接口调用
- `main.py` 的 `run_source_a` 可使用抽象接口替代直接调用具体函数

---

### 阶段四：插件安全检查标准化（P2，预计 1 天）

目标：将 `config/plugins.py`（549行）的安全检查逻辑模块化，提升可测试性。

**新建文件**：
- `security/plugin_validator.py`：统一处理 `_check_import_safety`（AST 解析）、`_validate_plugin_source`、黑名单检查（`BLOCKED_MODULES`、`BLOCKED_CALLS`）

**修改文件**：
- `config/plugins.py`：将安全检查逻辑提取到 `security/plugin_validator.py`，保留 `load_plugin_config`、`save_plugin_config`、`list_plugins`、`get_plugin` 等接口不变

**验证方式**：
- 运行 `python -c "from security.plugin_validator import validate_plugin_source; print('OK')"`
- `pytest tests/test_plugins.py`（如存在）通过

---

### 阶段五：性能与可维护性优化（P3，预计 2 天）

目标：优化并发性能，提升缓存效率，增强错误恢复能力。

**修改内容**：

1. **熔断与冷却机制整合**（`main.py` + `utils/http.py`）：
   - 当前 `CircuitBreaker`（line 94-143）与 `PoliteSession` 的冷却计数（`self._block_count`、`self._blocked_domains` 在 `utils/http.py` line 95-96）独立管理
   - 优化：在 `PoliteSession` 中增加熔断状态查询方法，`main.py` 移除独立 `CircuitBreaker` 类，直接使用 `session.is_blocked()`

2. **进度追踪缓存优化**（`utils/progress.py`）：
   - 当前 `_cache_ttl = 1.0`（line 41），可优化为可配置（如通过 `ProgressTracker` 构造函数参数）
   - 增加 `read_all_schools()` 批量读取方法，优化 `get_overview_stats()`（line 183-201）的性能

3. **任务模型扩展**（`main.py`）：
   - 当前 `CrawlTask`（line 68-80）缺少执行状态管理
   - 优化：增加 `execution_state`（pending/running/done/failed）、`retry_count`、`last_attempt_at`

**验证方式**：
- 并发执行 4 个任务，无文件竞争错误（`data/output/progress.json` 无损坏）
- 熔断机制在 DNS 错误时立即触发（line 108-114），冷却机制在 HTTP 403/429 时正确计数（line 186-194）
- 缓存命中时速度明显加快（`cache.stats["hits"]` 增加）

---

### 阶段六：测试增强（P3，预计 1-2 天）

目标：覆盖核心业务场景，确保重构行为一致。

**新增测试文件**：
- `tests/test_crawler_service.py`：测试 `CrawlerService` 的爬取逻辑（Source A/B 执行、任务状态管理）
- `tests/test_merge_service.py`：测试 `MergeService` 的多源合并（精确/去空格/模糊匹配）
- `tests/test_plugin_security.py`：测试插件安全检查（AST 解析、黑名单、受限函数检测）
- `tests/test_storage_layer.py`：测试 `Storage` 层的原子读写、缓存优化

**修改测试文件**：
- `tests/conftest.py`：增加 `mock_crawler_service`、`mock_merge_service` fixtures

**验证方式**：
- `pytest tests/` 全部通过（包括新增测试）
- 测试覆盖率 ≥ 80%（核心模块：`main.py`、`services/`、`spiders/`、`pipelines/`、`utils/http.py`、`utils/progress.py`）

---

## 关键文件修改清单（重新审查确认的精确路径）

| 优先级 | 文件路径 | 修改内容 | 代码位置参考 |
|---|---|---|---|
| P0 | `main.py` | 提取业务逻辑到服务层，保留 CLI 编排 | `run_source_a` (189-281)、`run_source_b` (284-354)、`run_merge` (357-427)、`execute_task` (457-560)、`build_tasks` (568-644)、`main()` (652-832) |
| P0 | 新建 `services/` | 建立服务抽象层 | `crawler_service.py`、`merge_service.py`、`export_service.py` |
| P1 | `api/server.py` | 使用服务层接口，替代直接调用底层模块 | `_run_crawl_task` (395-471)、`api_crawl` (313-393) |
| P1 | 新建 `storage/` | 抽象数据访问层 | `jsonl_store.py`、`progress_store.py`、`config_store.py` |
| P2 | `spiders/` | 统一引擎抽象接口 | `static_list.py` (149行)、`ajax_api.py` (141行)、`yzw_api.py` (285行)、`js_render.py` (130行)、`pdf_list.py` |
| P2 | 新建 `spiders/engine.py` | 抽象基类 `SpiderEngine` | 包含 `fetch()`、`parse()` 方法 |
| P2 | `config/plugins.py` | 安全检查模块化 | `_check_import_safety` (261)、`_validate_plugin_source` (286)、黑名单管理 |
| P2 | 新建 `security/plugin_validator.py` | 统一安全检查 | 整合 AST 解析、黑名单、受限函数检测 |
| P3 | `main.py`（熔断部分） | 熔断与冷却机制整合 | `CircuitBreaker` (94-143)、`PoliteSession` 冷却 (95-96 in `utils/http.py`) |
| P3 | `utils/http.py` | 增加熔断状态查询 | `is_blocked()` 方法 |
| P3 | `utils/progress.py` | 缓存优化、批量读取 | `_cache_ttl` (41)、`get_all_schools_summary()` (317) |
| P3 | 新建测试文件 | 补充缺失测试 | `test_crawler_service.py`、`test_merge_service.py`、`test_plugin_security.py`、`test_storage_layer.py` |

---

## 验证计划（每阶段执行）

每阶段完成后必须执行：

1. **单元测试**：`pytest tests/` 全部通过
2. **集成测试**：`tests/test_integration.py` 行为不变（5 个测试方法全部通过）
3. **手动验证**：
   ```bash
   python main.py --school "东南大学" --source source_a --force
   # 检查：data/output/ 生成正确的 .jsonl 和 summary.xlsx
   # 检查：data/output/progress.json 状态正确
   ```
4. **性能验证**：并发执行 4 个任务，确认无文件竞争错误
   ```bash
   python main.py --school "东南大学" --source source_a --workers 4 --year 2026
   ```
5. **安全验证**：插件上传时安全检查正常工作
   ```bash
   # 确认 plugins_ext/ 目录中的插件被正确验证
   python -c "from config.plugins import validate_all_configs; print('配置验证通过')"
   ```

---

## 风险控制（重新审查确认）

1. **向后兼容**：重构期间保留原有 `main.py` 的 CLI 接口（`--school`、`--category`、`--source`、`--year`、`--workers`、`--force`、`--resume`、`--retry-failed`、`--delay`、`--max-retries`、`--timeout`、`--cooldown-threshold`、`--cooldown-seconds`、`--raw-dir`、`--no-cache`、`--cache-days`、`--clear-cache`、`--circuit-break-threshold`、`--circuit-break-window`）不变，内部实现逐步迁移
2. **渐进式重构**：每个阶段独立可测试（阶段一完成后可运行全流程，阶段二完成后可运行全流程），不一次性大规模重写
3. **数据安全**：修改 `storage/` 层时，确保原子写入机制（`tempfile.mkstemp` + `os.replace` 模式，参考 `pipelines/export.py` line 148-150、`config/loader.py` line 148-163）不被破坏
4. **并发安全**：所有文件访问保持线程安全（`ProgressTracker` 已使用 `threading.Lock` 在 line 38，`CrawlCache` 已使用 `threading.Lock` 在 line 47，重构时不删除）
5. **配置兼容**：`config/school_data.json` 格式保持不变（`university`、`categories`、`faculty`、`notice` 结构不变），重构仅涉及访问方式变化
6. **测试隔离**：测试使用临时目录（`tmp_dir` fixture 在 `tests/conftest.py` line 16-20），不污染真实数据

---

## 附录：重新审查使用的关键代码位置参考

以下为重新审查（2026-09-17）时确认的精确代码位置，用于验证重构正确性：

- `main.py` 关键函数：`run_source_a` (189)、`run_source_b` (284)、`run_merge` (357)、`execute_task` (457)、`build_tasks` (568)、`main()` (652)
- `api/server.py` 关键函数：`api_crawl` (313)、`_run_crawl_task` (395)、`api_config_get` (836)、`api_plugins_list` (1117)
- `spiders/yzw_api.py` 关键类：`YzwClient.__init__` (35)、`get_school_code` (46)、`fetch_major_directory` (99)、`_fetch_one_discipline` (161)
- `pipelines/merge.py` 关键函数：`match_records` (63)、`merge_pair` (169)、`merge_sources` (218)、`to_summary_row` (273)
- `pipelines/export.py` 关键函数：`export_merged` (31)、`export_summary` (66)、`export_failures` (126)、`load_failures` (162)
- `utils/http.py` 关键类：`PoliteSession.__init__` (63)、`_request` (146)、`_save_raw` (239)、`BlockedError` (287)、`MaxRetriesExceeded` (291)
- `utils/progress.py` 关键类：`ProgressTracker.__init__` (32)、`get_school_status` (110)、`update_school_status` (127)、`get_overview_stats` (183)、`get_pipeline_progress` (203)、`add_log` (305)
- `utils/cache.py` 关键类：`CrawlCache.__init__` (44)、`read_text` (106)、`write` (119)、`get_or_fetch` (133)、`clear` (84)
- `config/plugins.py` 关键函数：`load_plugin_config` (170)、`list_plugins` (395)、`upload_plugin` (479)、`delete_plugin` (502)、`is_enabled` (523)、`plugin_config` (528)
- `tests/conftest.py` 关键 fixtures：`tmp_dir` (16)、`mock_session` (24)、`mock_cache` (48)、`mock_progress` (55)、`sample_config` (65)、`sample_faculty_html` (101)、`sample_yzw_json` (115)
