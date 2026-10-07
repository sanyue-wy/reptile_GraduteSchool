# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v3.0.0] - 2026-09-18

> 📌 **2026-10-01（G4）事实校正**：本节原先只覆盖合并签字当天的快照，漏记了随后大量产出，
> 且插件计数有误。计数已按实际扫描结果更正；签字之后的工作另见下方 `[Unreleased]`。
> 另注：本项目 git 提交日期全部落在 2026-09-18，而 progress.md / merge_report.md 叙述的
> 工作日期为 2026-09-19 ~ 09-22。两者不一致，本文件**以 git 提交日期为准**，未按叙述日期改写。

### 新增 Features

#### 插件化架构 (V3.0 重构)

- **Spider 插件**：7 个采集插件
  - `static_html`, `ajax_api`, `js_render`, `pdf_list`, `yzw_api`, `media_downloader`, `url_prober`
  - 支持离线 fixture 测试
  - 受控 HTTP 会话 (PoliteSession)
  - 原始材料批次输出 (RawDataBatch)
  - 📌 校正：原文写"5 个"但只列出 6 个名字，实际为 7 个（漏记 `url_prober`）

- **Processor 插件**：10 个
  - 解析类（继承 `ParserPlugin`）：`faculty_parser`, `yzw_major_parser`, `parser_fallback`
  - 记录处理类（继承 `RecordProcessorPlugin`）：`normalize`, `dedup`, `education_merge`,
    `statistics`, `error_analyzer`
  - 前置处理类（继承 `BasePlugin`）：`url_normalizer`, `domain_rewriter`
  - 分离抓取与解析职责
  - 归一化记录输出 (NormalizedRecordDTO)
  - 📌 校正：原文仅以 "faculty_parse 等" 一笔带过，未给出数量

- **Storage 插件**：5 个存储插件
  - `jsonl_store` - JSONL 输出 (legacy_education_v1 / generic_record 格式)
  - `xlsx_store` - Excel 汇总表
  - `sql_store` - SQLite 存储 (UPSERT 支持)
  - `progress_store` - 进度快照导出
  - `media_store` - 媒体资产存储 (内容寻址，10MiB 大文件流式拷贝)

- **Presenter 插件**：6 个呈现器
  - `html_presenter`, `text_presenter`, `csv_presenter`, `jsonl_presenter`, `pdf_presenter`, `markdown_presenter`
  - 模板渲染分离
  - 多格式输出
  - 📌 校正：原文写"呈现器 (HTML、PDF、Markdown 等)"未给数量，实为 6 个

- **UI 插件**：4 个 UI 组件
  - `table_component`, `chart_component`, `card_component`, `filter_component`
  - 📌 校正：原文**完全未记录** UI 插件这一类

> 合计 **32 个插件**（spider 7 / processor 10 / storage 5 / presenter 6 / ui 4）。
> 复算命令：
> `python -c "from plugin_manager.loader import scan_plugin_dirs; d,_,_=scan_plugin_dirs(); print(len(d))"`
> → `32`
> `plugin_manager/registry_snapshot.json` 独立复核同为 32（registry_revision=32）。

#### 接口契约

- **DTO 定义**：
  - TaskConfigDTO / TaskRunState - 任务配置与运行状态
  - RawDataDTO / RawDataBatch - 原始材料批次
  - NormalizedRecordDTO / RecordBatch - 归一化记录批次
  - StoreRequest / StoreReceipt - 存储请求与回执
  - PresentationRequest / RenderedOutputDTO - 呈现请求与输出

- **插件协议**：
  - BasePlugin - 所有插件统一基类
  - SpiderPlugin - 采集插件协议
  - ParserPlugin - 解析插件协议
  - RecordProcessorPlugin - 记录处理插件协议
  - StoragePlugin - 存储插件协议
  - PresenterPlugin - 呈现插件协议
  - UIPlugin - UI 组件插件协议

#### 工具模块

- **infra/storage**：
  - atomic_io - 原子 I/O 工具 (path_lock, atomic_writer, atomic_write_json, atomic_write_bytes)
  - idempotency - 幂等键支持
  - workspace - ManagedWorkspace 受管输出工作区
  - 📌 校正：原文只列 atomic_io，漏记 idempotency.py / workspace.py

- **utils/progress.py** 扩展：
  - V3.0 状态映射 (pending/running/succeeded/failed/partial/cancelled/skipped)
  - export_snapshot() - 导出进度快照
  - to_task_run_state() - 转换为 TaskRunState

### 破坏性变更 (BREAKING CHANGES)

- V3.0 采用全新插件架构，旧 CLI 参数/行为保持兼容
- `storage/` 目录保留旧实现，插件委托其实现

### 兼容性保证

- **旧 CLI 参数**：`--school`, `--source`, `--workers`, `--force`, `--resume`, `--retry-failed` 等
- **旧 API 端点**：V2.2 端口 `/api/crawl`, `/api/tutors` 等保留
- **数据输出格式**：`data/output/summary.xlsx`, `progress.json` 结构保持

### 技术细节

- **线程安全**：跨存储实例共享路径锁 (threading.RLock)
- **幂等写入**：StoreRequest.idempotency_key 支持
- **原子写入**：tempfile.mkstemp + os.replace 模式
- **AST 验证**：加载外部插件经黑名单校验

---

## [Unreleased]

> 📌 **2026-10-01（G4）新增本节**。以下产出全部发生在 v3.0.0 签字之后，v3.0.0 条目当时未予记录。
> 工作区未提交，因此无对应 commit 号；证据为文件路径与实测命令输出。

### 新增 Features

#### 第二套管理台 (dashboard/console/)

- 仓库自此有**两套前端**，此前 v3.0.0 条目未提及：
  - **主面板** `dashboard/{index,schools,failures,tutors,tasks,config}.html` + `dashboard/api.js`
  - **管理台** `dashboard/console/{index,plugins,failures,task-config,output-config}.html`
    + `dashboard/console/api.js`（卡片流插件管理、状态徽章、错误详情抽屉、任务/输出定义表单）
  - **运行时预览** `dashboard/runtime/preview.html`（token 化临时授权、只读 iframe）
- 新增端点：`GET /api/failures/grouped`（失败归一化分组）、`GET /api/run/event`（强制采集事件）
- 首页分流：`/` 按 progress.json 是否有记录决定返回主面板还是管理台导航卡，`?view=console` 显式进管理台

#### Domain Knowledge Base（域名知识库）

- `data/domain_kb.json` — 101 所学校主流域名映射（main / szdw / faculty / verified）
- `plugin_manager/validator.py` — 新增 `validate_domain_kb()`
- `config/plugins.py` — 新增 `load_domain_kb()` / `reload_domain_kb()` / `get_school_domain()` 热加载接口
- 配套插件：`url_normalizer`（中文域名正规化、double punycode 检测）、
  `domain_rewriter`（子域名回退主域名）、`url_prober`（HEAD 逐候选路径探测）
- `INTERFACES.md §12` 定义规范

#### 插件错误上报与聚合

- `plugin_manager/error_reporter.py` — `report()` / `aggregate(n_recent)` /
  `get_recent_errors()` / `has_recent_error()`，落盘 `data/output/plugin_errors/<插件名>_<时间戳>.json`
- `plugin_manager/loader.py` — 新增 `check_plugin_errors()` / `scan_with_error_markers()`，
  扫描时标记「该插件最近报过错」
- `config/plugins.py` — 新增 `get_plugin_errors()` 供 API 调用
- V3 引擎 best-effort 把 stage 错误写入聚合池（失败仅 debug 日志，不影响 run 结果）

#### 其他

- `plugins/plugin_manifest.py` — PluginManifestDTO 插件契约声明规范
- `infra/retry/adaptive_timeout.py` — AdaptiveTimeoutPolicy，按域名记历史响应时间，P95 作基础超时（clamp 15s–120s）
- `infra/state_tracker.py` — StateTracker 管理 `run_state.json` / `run_event.json`（原子写）
- `infra/errors/` — 由单文件 `infra/errors.py` 重构为包，新增
  `classify_plugin_error()` 与 `PluginErrorContext` / `ErrorType`
- `docs/plugin_dev_guide/plugin_index.md` — 插件清单文档
- `LICENSE`（MIT）+ `NOTICE` — 第三方许可证声明
- 20 套 HTML 模板（`templates/`，registry.json + 每套 layout/style/variables/preview）
- `schema_editor/`（字段定义 CLI + 生成器 + 3 套预设）与 `scaffolds/`（六类插件脚手架 CLI）

### 修复 Fixed

- **4 个中间基类补全**：`ParserPlugin` / `RecordProcessorPlugin` / `StoragePlugin` / `UIPlugin`
  此前仅存在于契约文档，代码中缺失，导致各插件被迫重复声明泛型参数。
  ⚠️ 补全后仍有两处遗留未闭环：`StoragePlugin`/`UIPlugin` 零继承（9 个插件仍直接继承 `BasePlugin`），
  且 `ParserPlugin.plugin_type` 被声明为 `"parser"` 而非契约规定的 `"processor"`（详见下方「已知问题」）
- **PresenterPlugin 契约对齐**：补齐 `input_schema="PresentationRequest.v1"` /
  `output_schema="RenderedOutputDTO.v1"`
- **RawDataDTO**：`assets` 加入 `v1_schema()` required；`__post_init__` 在 assets 为空且无
  `raw_ref` 时抛 `ValueError`
- **markdown 格式分发**：`present.py` 新增 `_FORMAT_FALLBACK` / `_GENERIC_FALLBACK` 三级回退，
  此前 format='markdown' 必然抛 `PIPELINE_DEPENDENCY_MISSING`；并新增原生 `markdown_presenter`
- **PDF XSS 转义**：`pdf_presenter` 原用 `value.replace("&", "&")` 等三条 no-op 调用（搜索串=替换串，
  实际什么都不替换），改为 `html.escape(value, quote=True)`，并同时转义 `<th>` 表头字段名
- **metadata 必填字段**：`license` 升级为必填，全部 metadata.json 补齐 `"license": "MIT"`
- **IDN 中文域名**：根因导致的大批量 `dns_error` 失败项经 domain_kb 正规化后收敛

### 文档 Documentation

2026-10-01 由 G4 窗口完成一轮全量文档事实核查，改动集中于"让文档只说真话"：

- **死链修复**：`01_quickstart.md` → `01_platform_overview.md`（README）、
  `docs/INTERFACES.md` → `docs/V3.0/INTERFACES.md`（README）、
  `w4_static_sample.html` → `w4_static_list_page.html`（10_testing.md）、
  `scaffolds/README.md` → `scaffolds/cli.py`（plugin_index.md）、
  `REQUIREMENTS.md` → `../V2.0/REQUIREMENTS.md`（V0.0/DESIGN.md）、
  `docs/GITHUB_RESEARCH.md` → `docs/V0.0/GITHUB_RESEARCH.md`（V2.0 升级报告）
- **不存在的文件被明写为不存在**：`scripts/build_template_previews.py`（09_template_dev.md）、
  `docs/plugin_dev_guide/02_contract_reference.py`（02_contract_reference.md）
- **无法运行的命令已更正**：`python main.py --ui` → `python -m api.server --port 5000`（3 处）、
  `pip install -e .` → `pip install -r requirements.txt`（04_writing_processor.md）、
  `findstr /c:"..."` → `grep -E`（W2 任务卡，Git Bash 下 `/c:` 会被 MSYS 当路径转换）、
  `python main.py --all` → `--school __all__`、`--limit` → `--max-retries`、
  `main.py --review-candidates` → `scripts/review_candidates.py`、
  `schema_editor/editor.py <preset>` 标注为交互式（无 stdin 会 EOFError，不可用于计时）
- **回归数字更正**：**"956 passed" 实为 collected 而非 passed**，已给出可复算口径
  `python -m pytest tests/ -q --ignore=tests/integration` → **955 passed, 3 skipped**
- **计数更正**：插件 32（spider 7 / processor 10 / storage 5 / presenter 6 / ui 4）；
  metadata.json 32 个（原文写 22）；`test_storage_plugins.py` 51（原文写 42）；
  `test_pipeline_engine.py` 23（原文写 25）；registry revision 32（原文写 24/21）
- **契约版本订正**：所有引用文档统一为 **v3.0.5**（原写 v3.0.1 / v3.0.3）；
  B2 的授权出处订正为 §3.6（原引 §4）
- **补登**：progress.md 的 W6 区段原本四栏全空，已按实测证据补齐

### 已知问题 Known Issues

- `GET /api/outputs/serve` 端点**尚未实现**，`dashboard/runtime/preview.html` 调用它会 404
  （2026-10-01 G4 实测 `api/server.py` 无该路由）
- ⚠️ **状态已变化**：`GET /api/plugins/errors` 在 2026-10-01 早先的核对中还缺失，
  但随后由并行窗口补上——`api/server.py:1338` 现已有 `@app.route("/api/plugins/errors", methods=["GET"])`。
  `dashboard/console/plugins.html` 的错误抽屉调用方已有着落。
  连续运行「前端 API 调用 vs Flask url_map」比对命令可自行复核当前剩余缺口
- `INTERFACES.md` 头部标注"冻结版本：v3.0.0"，与其自身 §14 变更记录（已至 v3.0.5）不一致
  （INTERFACES.md 属冻结契约，G4 只读未改）
- `INTERFACES.md` 内部另有一处节号错位：§13 的标题写作「插件开发者契约 (§14)」，而 §14 实为「变更记录」
- `INTERFACES.md:714` 的插件配置路径模板写作 `{type}/{name}/metadata.json`，
  实际布局为 `plugins/{type}/{name}/metadata.json`（同上，只读未改）
- `plugins/base.py:210` 的 `ParserPlugin.plugin_type = "parser"` 与 `INTERFACES.md` §3.3 声明的
  `"processor"` 冲突，且 `"parser"` 不在 `plugin_manager.loader.PLUGIN_TYPES` 内；
  `StoragePlugin` / `UIPlugin` 两个中间基类实际零继承
- `config/plugins.yaml` 未声明 `markdown_presenter` 实例，markdown 呈现回退链在真实配置下不可达
- 3 个 skipped 用例原因各不相同（WeasyPrint 缺失 / urllib3 版本 / 无 pending_review 插件数据），
  并非全部由 WeasyPrint 缺失导致；其中 1 个依赖运行时插件注册表状态，插件数变化时 skip 数会变
- `scripts/build_template_previews.py`（模板 preview.png 自动构建）仍不存在
- `python main.py --all` / `--limit` / `--review-candidates` / `--ui` 均**不是** main.py 的合法参数，
  文档中出现的这些写法已逐处标注更正

---

## [v2.2.0] - 2024-03-15

### 已发布版本

- 基础爬虫框架 (静态页面、Ajax API、JS 渲染、PDF 下载)
- Flask API 监控面板
- Excel 汇总导出
- 学校配置管理系统

---

## [v1.0.0] - 2023-01-01

### 初始版本

- 研究生导师信息采集原型
- 单体架构设计