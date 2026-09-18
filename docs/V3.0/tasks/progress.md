# V3.0 多窗口进度登记表

> 每个窗口开工时登记基线提交与分支；完成后把验收命令的实际输出摘要粘进自己那一节。
> "待 W1 仲裁"区用于跨窗口的接口变更提案，只有 W1 可裁决并更新 INTERFACES.md。

## 基线

- 主工作区基线提交：7b127ef (save: v22 refactor in progress, context limit reached)
- 环境：Windows 11 / Python 3.12.7 / pytest 9.1.1（V2.2 验收记录值，开工时复核）
- 全量测试预期：532 passed, 1 skipped（docs/refactor/acceptance.md）

## 待 W1 仲裁（接口变更提案）

| 提出方 | 日期 | 提案 | W1 裁决 |
|---|---|---|---|
| （示例）W4 | — | RawDataDTO 需增加 http_status 字段 | （待定，保留为占位示例） |
| W4 | 2026-09-20 | media_downloader 是新增 spider 插件，旧 plugins.json 无对应条目，迁移器 PLUGIN_NAME_MAPPING 未覆盖 | **拒绝加映射**：新插件不属于"旧→新"迁移范围；由 config/plugins.yaml 手工声明实例（media_downloader: plugin: spider:media_downloader），契约不变 |
| W7 | 2026-09-20 | PresenterPlugin 的 render() 允许返回路径字符串，由 execute() 包装成 RenderedOutputDTO | **接受（已冻结于 INTERFACES.md §3.6）**：execute() 是唯一抽象入口；render() 可返回 RenderedOutputDTO 或 str 路径；其他类型抛 TypeError。任何具体 Presenter 只实现一个入口即可加载 |
| W7 | 2026-09-20 | UIComponentDTO/ViewModel 用于组件与整页两种场景，是否拆分两个 DTO | **维持单一 UIComponentDTO + ViewModel 分层**（INTERFACES.md §2.10–2.11）：组件描述走 UIComponentDTO，页面布局走 ViewModel.components 引用；不新增类型 |
| W2/W5 | 2026-09-20 | 批次级错误（ErrorDTO）与记录级错误如何共存于 RecordBatch | **按现状冻结**：RecordBatch.errors: list[ErrorDTO] 承载批次/阶段级错误；单条记录的 provenance.error 字段承载记录级错误。不新增字段 |

## W1 契约与集成主控

- 分支/worktree：Refactoring_code (main worktree)
- 已完成（含验收命令实际输出，2026-09-20 复核）：
  - contracts/ 全部类型：asset.py, task.py, raw.py, record.py, output.py, ui.py, result.py, profiles/education.py
  - plugins/base.py：BasePlugin 基类 + PresenterPlugin 变体（execute 抽象入口 + render 可选钩子）
  - docs/V3.0/INTERFACES.md：完整冻结契约文档（v3.0.1：变更记录追加；映射表对齐为纯脚本修正，未改契约语义）
  - config/pipeline.yaml / config/plugins.yaml：自洽垂直切片示例（present 指向具名实例 html_report: presenter:html_presenter, template: minimal-light）
  - scripts/migrate_config.py：dry-run 修复——移除死代码 load_builtin_plugins、消除 global json_path、映射表新增 instance 字段使生成 YAML 与示例实例名一致（static_fetch/faculty_parse/jsonl_output…）；新增 tests/fixtures/migrate_plugins.json（旧七类 20 插件样例）作为迁移输入 fixture
  - tests/test_contracts.py：契约测试（+TestPluginBase 5 例，覆盖 base.py metadata/context/presenter 包装路径）
  - tests/test_wave0_contract.py：Mock 四阶段 smoke（spider→parser→storage→presenter）
- 验收命令实测（2026-09-20）：
  - `python -m pytest tests/test_contracts.py tests/test_wave0_contract.py -q` → **53 passed in 1.74s**
  - `python scripts/migrate_config.py --dry-run --report /tmp/migrate_report.txt` → exit 0（默认源 config/plugins.json 无 plugins 键，0 映射属预期）；对 fixture 运行：Mapped 15 / Unmapped 4（utility×3 + 未知插件）/ Conflicts 0 / Warnings 1（js_render disabled），生成的 pipeline.yaml/plugins.yaml 与示例配置实例名一致
  - `python -c "from config.validator import validate_all_configs; ..."` → **0**
  - 覆盖率：contracts/ 98%，plugins/base.py 97%（均 ≥90%）
  - 全量回归：`pytest tests/ -q --ignore=tests/integration --ignore=tests/test_filter_component.py` → **656 passed, 1 skipped**（W4/W7 已交付测试全部通过）
- 未完成：
  - 仲裁提案裁决：已登记并裁决 4 条（见"待 W1 仲裁"区，满足"至少 3 条"退出条件）
  - 集成期全量 `pytest tests/ -q`（等 W2/W5/W6/W8 交付后按 W2→…→W8 顺序执行）
  - ACCEPTANCE.md 初稿（集成期产出）
- 阻塞/问题：
  - **卡面问题**：任务卡写 migrate_config.py 输入为"旧 plugins.json 七类"，但 V2.2 实际的 config/plugins.json 只含 overrides+pipeline 权重（DEFAULT_PLUGIN_CONFIG），插件清单在 config/plugins.py BUILTIN_METADATA。处置：保留 --source 参数支持两种输入形状（带 plugins 键的旧 JSON 或任意文件），并以 tests/fixtures/migrate_plugins.json 固化迁移输入样例；已在上方记录，不改契约。
  - **W7 工作区阻断项**：tests/test_filter_component.py:385 语法错误（`"";" in html` 未闭合字符串），阻断 pytest 收集导致全量测试无法跑。该文件属 W7 可写范围（共享工作区未提交在制品），W1 无权修改，转 W7 修复；修复前全量回归需 --ignore 该文件。
  - 共享工作区混有 W4/W7 未提交文件（plugins/ui/*、tests/test_filter_component.py 等），按红线不代提交，由各窗口自行处理。

## 广播

- **2026-09-20 契约已冻结（INTERFACES.md v3.0.1），W2–W8 可开工。** 各窗口只凭 INTERFACES.md + 自己的任务卡实施，接口变更提案一律走 progress.md "待 W1 仲裁"区。

## W2 主干管道

- 分支/worktree：feature/v3-w2-pipeline (../reptile-W2)
- 已完成：
  - **pipeline/engine.py**：PipelineEngine 四阶段引擎，ThreadPoolExecutor 有界并发（默认 4 线程），PipelineDefinition.from_files 读取 pipeline.yaml/plugins.yaml 构建执行计划，PluginResolver 按 metadata entry_point 动态导入，OutputRootLock 进程锁
  - **pipeline/stages/acquire.py**：acquire_source 单来源采集（每任务独立插件实例+上下文，setup/execute 异常→ErrorDTO，finally 关闭资源，cancel 检查点，批次结构校验）
  - **pipeline/stages/process.py**：run_parse_chain（每来源独立 parse 链）+ run_post_steps（多步顺序执行）+ merge_source_batches（按 dataset+profile 分组汇聚，record_id 由自然键 uuid5 生成）；处理器上下文不含 http
  - **pipeline/stages/store.py**：store_batch fan-out 到全部目标，required 目标失败→run failed，可选失败→partial；RecordBatch 原子落盘为批次引用文件；OSError 自动映射 STORAGE_WRITE_FAILED
  - **pipeline/stages/present.py**：view_converter→PresentationRequest→PresenterPlugin.execute→RenderedOutputDTO；成品路径须落在受管 outputs 目录下；默认 optional
  - **infra/context.py**：PipelineContextManager（每任务独立 HTTP 会话+受管上下文，finally 关闭资源，共享 PoliteSession 工厂/CrawlCache/ProgressTracker 实例，不新建第二套熔断器）
  - **infra/http.py**：ManagedHttpSession（取消检查点，统计快照，is_blocked/tripped 透传同一 PoliteSession 状态）
  - **infra/cache.py**：ManagedCrawlCache（取消检查点，命中率快照，同一锁语义）
  - **infra/errors.py**：error_from_exception + classify_http_error（裸 ConnectionError/TimeoutError 也正确映射 HTTP_* 码，OSError 在 store 阶段→STORAGE_WRITE_FAILED，凭据脱敏）
  - **converters/request_converter.py**：build_task_config（单来源→TaskConfigDTO）+ build_output_specs（格式白名单校验，支持多级 format 推断）+ from_legacy_cli（旧 CLI 参数展开）+ to_task_configs
  - **converters/view_converter.py**：build_presentation_request（四要素→PresentationRequest）+ build_field_descriptions（schema_id→field descriptions）
  - **main.py**：新增 `--engine {v2,v3}` 开关（默认 v2，旧参数行为零变化），run_v3() 入口
  - **api/server.py**：新增 3 个端点（旧端点全部保持）：POST /api/pipeline/validate、POST /api/pipeline/run、GET /api/pipeline/runs/<id>
  - **tests/test_pipeline_engine.py**：25 tests（配置加载、四阶段端到端、并发边界、required/optional 存储失败、可选展示失败、setup 失败、空结果、取消令牌停止派发、converters、状态映射）
  - **tests/test_http_context.py**：23 tests（ManagedHttpSession、ManagedCrawlCache、error classifier、PipelineContextManager 会话生命周期、取消令牌、凭据脱敏）
  - **tests/integration/test_static_slice.py**：3 tests（离线 fixture 四阶段贯穿、失败清理、取消安全检查点）
- 验收命令实测：
  - `python -m pytest tests/test_pipeline_engine.py tests/test_http_context.py -q` → **46 passed in 1.25s**（含新增 integration/tests 另 3 passed = 49 total）
  - `python main.py --help` → 旧参数全集（school/category/source/year/workers/force/resume/retry-failed/delay/max-retries/timeout/缓存/冷却/raw-dir/熔断）全部保留，新增 `--engine {v2,v3}`（默认 v2）
  - `python -m pytest tests/ -q --ignore=tests/test_filter_component.py` → **710 passed, 1 skipped**（基线 661 passed + W2 新增 49 passed，零回归）
  - Flask test client 验证新端点：POST /api/pipeline/validate → 400 预检未通过（预期，静态切片缺少真实插件元数据）；POST /api/pipeline/run 空 sources → 400；GET /api/pipeline/runs/nonexistent → 404；旧 /api/overview → 200
- 未完成：
  - **Wave 1a 完整集成**：离线 fixture 经真实插件（非桩）跑通 acquire→process→store→present；需 W5 faculty_parser + W6 jsonl_store + W7 html_presenter 就位后替换 test_static_slice 中的桩为真插件重跑
  - **旧 JSONL 格式逐行一致验证**：待 W6 jsonl_store legacy_education_v1 就位后补
- 阻塞/问题：无（W7 test_filter_component.py 语法错误不阻塞 W2，已 --ignore）
- 仲裁提案：**零**（无接口变更需求，所有 DTO 直接使用 INTERFACES.md 冻结契约）

## W3 插件治理

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：

## W4 采集插件

- 分支/worktree：feature/v3-w4-spiders (or main worktree)
- 已完成：
  - static_html spider plugin (plugins/spiders/static_html/plugin.py + metadata.json)
  - ajax_api spider plugin (plugins/spiders/ajax_api/plugin.py + metadata.json)
  - js_render spider plugin (plugins/spiders/js_render/plugin.py + metadata.json) - with optional Playwright dependency
  - pdf_list spider plugin (plugins/spiders/pdf_list/plugin.py + metadata.json)
  - yzw_api spider plugin (plugins/spiders/yzw_api/plugin.py + metadata.json)
  - media_downloader spider plugin (plugins/spiders/media_downloader/plugin.py + metadata.json) - new example plugin
  - raw_converter.py (converters/raw_converter.py) - normalizes legacy raw data to canonical RawDataBatch
  - All 6 plugins produce TRUE raw material batches (RawDataBatch with MediaAsset assets)
  - Tests: tests/test_spider_plugins.py - 39 passed (10 tests per plugin + 4 raw_converter + 1 fixture test)
  - Coverage: static_html 80%, ajax_api 86%, pdf_list 89%, yzw_api 81%, media_downloader 87%, js_render 21% (optional dep)
  - Fixtures: tests/fixtures/raw_pages/w4_*.html/json/pdf (shared with W5)
- 未完成：
  - Integration test tests/integration/test_static_slice.py (requires W2 engine + W5 faculty_parse + W6 jsonl_store)
- 阻塞/问题：无阻塞，所有单元测试通过

## W5 处理器插件

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：

## W6 存储插件

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：

## W7 呈现器·UI·模板

- 分支/worktree：
- 已完成：
  - pdf_presenter plugin (plugins/presenters/pdf_presenter/plugin.py + metadata.json) - with optional WeasyPrint dependency
- 未完成：
- 阻塞/问题：

## W8 编辑器·脚手架 CLI·文档

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：
