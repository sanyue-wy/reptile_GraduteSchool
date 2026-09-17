# 通用网络数据采集与处理平台 · V3.0 计划书

> 版本：2026-09-17 · 取代 2026-09 的《插件化配置系统 · 计划书》
> 定位升级：从「研究生导师采集脚本」升级为**数据契约驱动的通用网络数据采集与处理平台**——主干稳定如磐石，插件灵活如积木。
> 本文档是 **V3.0 的实施计划书**，不是 V2.2 完成证明。V3.0 开工前提见 §1.3「V2.2 启动门槛」。

---

## 0. 阅读指引

| 章节 | 回答的问题 |
|---|---|
| §1 执行摘要与启动门槛 | 本次升级做什么？何时可以开工？ |
| §2 目录结构与放置规则 | 目录怎么排布？文件放哪里？（用户重点关注） |
| §3 架构与渐进迁移 | 新旧结构如何过渡？ |
| §4 数据契约（DTO）与调用语义 | 阶段之间传什么数据？ |
| §5 调度、合并与副作用边界 | 并发、重试、失败、多存储怎么处理？ |
| §6 插件迁移映射与配置系统 | 旧 7 类插件怎么迁？配置怎么管？ |
| §7 插件治理与安全 | 外部插件如何安全加载？ |
| §8 UI 组件插件化与 API | 前端怎么插拔？接口怎么变？ |
| §9 开源参考与依赖策略 | 借鉴谁？引入什么？ |
| §10 Wave 划分、文件所有权与实施步骤 | 谁做什么？什么顺序？ |
| §11 验收标准与回滚 | 怎么算做完？怎么退回来？ |

---

## 1. 执行摘要、范围与启动门槛

### 1.1 项目定位

**一句话定位**：数据契约（DTO）驱动的「管道-过滤器」平台 + 统一插件生态，覆盖采集 → 处理 → 存储 → 展示全链路可插拔。

核心目标：

1. **主干稳定**：`pipeline/` 只负责流程编排，不含任何具体数据源、解析或存储逻辑；新增数据源/处理器/存储/UI 组件，主干零修改。
2. **契约先行**：阶段之间只传标准 DTO，杜绝隐式 `dict` 透传；DTO 有版本与校验。
3. **四类插件**：采集（spider）、处理（processor）、存储（storage）、展示（ui），全部继承统一基类、输出标准 DTO。
4. **UI 也插件化**：表格、图表、卡片、过滤器组件通过配置切换，宿主按描述 DTO 渲染。
5. **兼容旧世界**：旧 CLI、旧配置、旧 JSONL 输出、旧 API 均保留兼容视图。

**不做什么**（本期明确排除，避免范围膨胀）：

- 不重命名仓库、不改 `data/` 既有路径。
- 不引入 Scrapy/Crawlee 等重框架作为核心依赖（仅可选适配器）。
- 不做分布式采集、复杂 DAG 编排、async 双栈、非 Python 插件（列入 §12 路线图）。
- 不承诺跨文件/数据库的分布式事务（多存储是同一结果的 fan-out，各自回执）。

### 1.2 现状盘点（2026-09-17 代码快照）

状态标记：**已存在** = 代码中已观察到；**待验收** = V2.2 指导书要求但本次快照未确证；**V3.0 新增** = 本计划新增。

| 能力 | 状态 | 位置/说明 |
|---|---|---|
| 爬虫引擎抽象基类 | 已存在 | `spiders/engine.py`：`SpiderEngine` ABC + 类注册表；与包级旧函数注册表并存 |
| 五个采集引擎 | 已存在 | `spiders/static_list.py`、`ajax_api.py`、`js_render.py`、`pdf_list.py`、`yzw_api.py` |
| 插件元信息与七类清单 | 已存在 | `config/plugins.py`：七类（source/fetcher/parser/processor/exporter/presenter/utility）、外部插件发现/启停/上传/重载 |
| 权重链 processor/exporter | 已存在 | `processors/__init__.py`、`exporters/__init__.py`；权重链由 `config/plugins.json` 驱动 |
| 服务层 | 待验收 | `services/`（CrawlerService/MergeService/ExportService）在 V2.2 Agent A 指导书中定义，代码快照未观察到 |
| 存储抽象层 | 待验收 | `storage/jsonl_store.py`、`progress_store.py`、`config_store.py` 已出现在 git status，接口以 V2.2 验收为准 |
| 插件安全校验 | 已存在 | `security/plugin_validator.py`：AST 黑名单 + META 校验；**明确：AST 检查是静态审查门禁，不是安全沙箱** |
| 缓存/熔断整合 | 待验收 | `PoliteSession` 按域熔断（V2.2 Agent E 契约），main.py 旧 `CircuitBreaker` 退役情况待确认 |
| 插件管理 API | 已存在 | `api/server.py`：`/api/plugins` 全套（清单/上传/更新/删除/重载/流水线权重） |
| 配置校验联动注册表 | 已存在 | `config/validator.py`：`list_type`/`template` 已从注册表动态查询 |
| 管道引擎 `pipeline/` | V3.0 新增 | 单数 `pipeline/`，区别于旧复数 `pipelines/` |
| `contracts/`、`converters/` | V3.0 新增 | DTO 契约层与转换层 |
| `plugin_manager/` | V3.0 新增 | 发现/校验/注册治理框架 |
| UI 组件插件 | V3.0 新增 | `plugins/ui/` 表格/图表/卡片/过滤器 |

### 1.3 V2.2 启动门槛（Gate）

V3.0 Wave 0 开工前，须完成 V2.2 交接确认，逐项打勾并记录到 `docs/refactor/acceptance.md`：

- [ ] `services/` 服务层接入：`main.py` 与 `api/server.py` 通过服务层调用底层（或记录为何保留直接调用）。
- [ ] 旧函数兼容：`main.run_source_a/b`、`main.execute_task`、`main.build_tasks`、`run_merge` 兼容层存在且测试通过。
- [ ] 存储抽象：`JSONLStore/ProgressStore/ConfigStore` 落地，原子写入 `tempfile.mkstemp + os.replace` 未破坏。
- [ ] HTTP 熔断单一真值：`PoliteSession.is_blocked()` 生效，生产路径无双熔断状态。
- [ ] `ProgressTracker`、`CrawlCache` 线程锁保留，跨线程更新测试通过。
- [ ] 测试隔离：全量 `pytest tests/ -q` 在临时目录下通过，不以真实 `data/` 为依赖。
- [ ] V2.2 验收报告存在（提交标识、环境、测试输出、实际覆盖率）。

**未通过项返回 V2.2 收尾，不带入 V3.0。** 基线以验收报告中的实测数字为准，不沿用历史「405 passed」等快照。

---

## 2. 目录结构与放置规则（重点章节）

### 2.1 最终目录树

目标组织，兼容期结束后应呈现的结构（省略常规 `__init__.py`）：

```text
reptile_GraduteSchool/                # 仓库名保留；对外展示名可升级
├── main.py                          # CLI 参数解析 + 调用 Pipeline
├── api/server.py                    # REST 路由 + 调用入口
├── pipeline/                        # ★ 主干：流程怎么走
│   ├── engine.py                    #   流程控制、插件调度、异常熔断
│   └── stages/                      #   acquire.py / process.py / store.py / present.py
├── contracts/                       # ★ 契约：数据长什么样
│   ├── task.py                      #   TaskConfigDTO + TaskRunState
│   ├── raw.py                       #   RawDataDTO、RawDataBatch
│   ├── record.py                    #   NormalizedRecordDTO、RecordBatch
│   ├── ui.py                        #   UIComponentDTO、ViewModel
│   ├── result.py                    #   StoreReceipt、StageResult、RunResult
│   └── profiles/                    #   领域 schema（education.py 等）
├── converters/                      # ★ 转换：边界怎么转
│   ├── request_converter.py         #   外部请求 → TaskConfigDTO
│   ├── raw_converter.py             #   RawDataDTO ↔ 插件输入
│   ├── storage_converter.py         #   NormalizedRecordDTO → 存储格式
│   └── view_converter.py            #   分析结果 → UIComponentDTO
├── plugins/                         # ★ 插件生态：能力怎么扩展
│   ├── base.py                      #   BasePlugin 及四类协议
│   ├── spiders/                     #   采集组
│   ├── processors/                  #   处理组
│   ├── storage/                     #   存储组
│   └── ui/                          #   展示组
├── plugin_manager/                  # ★ 治理：插件怎么管理
│   ├── loader.py                    #   发现、加载（候选发现不 import）
│   ├── validator.py                 #   metadata/接口/AST 校验
│   └── registry.py                  #   单一注册表、生命周期
├── infra/                           # ★ 基建：运行靠什么
│   ├── context.py                   #   PipelineContext
│   ├── http.py                      #   受管 HTTP（委托 utils/http.py 实现）
    ├── cache.py                     #   受管缓存
    ├── progress.py                  #   进度门面
    ├── errors.py                    #   错误分类与重试预算
│   └── storage/                     #   原子文件、JSONL/进度/配置底层读写
├── config/                          # 配置：启用什么、怎样组合
│   ├── pipeline.yaml                #   声明式管道（新增）
│   ├── plugins.yaml                 #   插件实例与参数（新增）
│   ├── global.json                  #   全局参数（保留）
│   └── school_data.json             #   教育领域旧配置（兼容）
├── dashboard/                       # UI 宿主：加载组件插件、布局、renderer
├── tests/                           # 镜像模块目录；fixtures/、integration/
├── scripts/                         # 迁移、验收等维护脚本
├── docs/                            # V0.0–V3.0 文档
└── data/                            # raw/cache/output 路径不变
```

### 2.2 目录职责一句话

| 目录 | 一句话职责 | 放什么 | 不放什么 |
|---|---|---|---|
| `pipeline/` | 流程怎么走 | 阶段调度、权重链执行、异常熔断 | 业务字段判断、具体站点逻辑 |
| `contracts/` | 数据长什么样 | DTO、校验、领域 profile | IO、网络、日志 |
| `converters/` | 边界怎么转 | DTO ↔ 旧格式/外部输入的通用转换 | 每插件的私有解析（归插件包） |
| `plugins/` | 能力怎么扩展 | 四类插件包 | 主干逻辑、跨类共享工具 |
| `plugin_manager/` | 插件怎么管理 | 发现、校验、注册、生命周期 | 数据处理逻辑 |
| `infra/` | 运行靠什么 | HTTP/缓存/进度/原子 I/O/上下文 | 领域字段、插件业务 |
| `config/` | 启用什么 | YAML/JSON 配置 | 代码逻辑 |
| `dashboard/` | 展示宿主 | renderer、布局、静态资源 | 组件业务逻辑（归 `plugins/ui/`） |
| `tests/` | 质量保障 | 单元/集成/fixtures | 生产代码 |
| `data/` | 数据 | 运行产物 | 代码 |

### 2.3 插件包组织（两层：类别 / 插件名）

每个插件是一个自包含目录：

```text
plugins/spiders/static_html/
├── plugin.py          # 实现（类 + PLUGIN_META 或 metadata.json 之一，见 §7.2）
├── metadata.json      # 名称/版本/依赖/入口
└── （可选）schema.json、依赖说明、静态资源
```

- 插件内部再分模块随意（`fetcher.py`、`parser.py`），对外只暴露 `metadata.json` 声明的入口。
- UI 组件的前端资源（JS/CSS）随组件包放置，由 dashboard 宿主按 manifest 加载（§7.5）。
- **测试统一放 `tests/`**，镜像插件路径；不把测试塞进插件目录。

### 2.4 容易混淆的目录对

| 目录对 | 区分 |
|---|---|
| `pipeline/`（单数） vs 旧 `pipelines/`（复数） | `pipeline/` 是 V3.0 唯一管道主干；旧 `pipelines/` 是 V2.2 资产，兼容期保留 |
| `plugins/storage/` vs `infra/storage/` | 前者是管道节点插件（决定「存到哪、怎么存」）；后者是复用的底层 I/O（原子写、JSONL 行编解码），插件调用之 |
| `plugins/ui/` vs `dashboard/` | 前者是组件实现（描述 DTO + 受管资源）；后者是加载/布局/受管 renderer 宿主 |
| `contracts/profiles/` vs `converters/` | profiles 定义领域数据形状（教育）；converters 做边界格式转换 |
| `plugin_manager/` vs `config/plugins.py` | 前者是 V3.0 治理框架；后者是 V2.2 已有实现，兼容期作为旧入口保留并逐步委托 |

### 易混淆规则（速查）

- 新能力放置速查：
  - 新数据源 → `plugins/spiders/<新插件>/`
  - 新解析/清洗/统计 → `plugins/processors/<新插件>/`
  - 新存储目标 → `plugins/storage/<新插件>/`
  - 新展示组件 → `plugins/ui/<新插件>/`
  - 新领域数据形状 → `contracts/profiles/<领域>.py`
  - 只调组合 → `config/pipeline.yaml`、`config/plugins.yaml`
- **主干零修改的判定**：新增上述能力时，`pipeline/`、`contracts/`、`converters/` 通用部分、`plugin_manager/`、`infra/` 不应有 diff。若有 diff，说明该能力本应做成插件或配置。
- 不新增同义目录层（core/platform/runtime/components 等）。
- 不为每个小函数建子目录；插件包内模块划分自由，对外只暴露 metadata 声明的入口。

### 2.5 迁移期附加目录（临时存在，非目标架构）

兼容期内旧目录继续存在，但**不在旧入口新增 V3.0 业务**：

| 迁移期目录 | 内容 | 迁移去向 | 负责人 | 退出条件 |
|---|---|---|验收后删除 |
|---|---|---|---|
| `services/` | V2.2 服务层 | legacy 门面调用 pipeline | A | Wave 2 切换完成，兼容测试通过 |
| 旧 `spiders/` | 五个引擎 + engine.py | `plugins/spiders/` 各插件 + legacy 适配 | C | 对应插件交付并对照通过 |
| 旧 `parsers/`、`processors/`、`exporters/` | 解析/处理/导出注册表 | `plugins/processors/`、`plugins/storage/` | D / B | 对应插件交付并对照通过 |
| 旧 `pipelines/` | merge/export 管道 | `pipeline/stages/` + 插件 | A | 切换完成 |
| 旧 `storage/` | JSONL/进度/配置存储 | `infra/storage/` + `plugins/storage/` | B | 对应插件交付 |
| `security/` | AST 校验 | `plugin_manager/validator.py` | D | 治理框架交付 |
| `utils/` | http/cache/progress 等 | `infra/`（委托，不复制） | E | infra 委托层交付 |
| `plugins_ext/` | V2.2 外部插件 | 逐个显式映射迁移 | 插件作者 + D | 映射表确认，不静默丢弃 |

**删除旧目录不属于本次任务**：需后续版本确认调用方迁移、回归通过、正式废弃通知后另行处理。兼容期旧导入门面必须保留，不为目录美观破坏已承诺接口。

---

## 3. 架构与渐进迁移

### 3.1 分层架构

```text
┌─────────────────────────────────────────────────────┐
│ 接口层：CLI / REST API / Dashboard                   │
│ main.py  api/server.py  dashboard/                   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│ 管道引擎层：pipeline/                                │
│ engine.py  stages/acquire|process|store|present     │
└──────────────────────┬──────────────────────┘
│
┌──────────────────────▼──────────────────────────────� │
│ 契约层与转换层：contracts/ + converters/              │
│ DTO 定义 + 模块间数据转换（箭头实体化）               │
└──────────────────────┬──────────────────────────────┘
│
┌──────────────────────▼──────────────────────────────┐
│ 插件生态：plugins/                                   │
│ spiders/  processors/  storage/  ui/                 │
└──────────────────────┬──────────────────────────────┘
│
┌──────────────────────▼──────────────────────────────┐
│ 治理与基建：plugin_manager/ + infra/                 │
│ 插件发现、加载、安全校验、HTTP、缓存、上下文           │
└─────────────────────────────────────────────────────┘
```

### 3.2 数据流闭环

```text
TaskConfigDTO
   │
   ▼
[acquire] 调度采集插件 → RawDataDTO / RawDataBatch
   │
   ▼
[converters/raw_converter] → 处理器输入格式
   │
  ▼
[process] 调度处理器插件（解析/合并/统计）→ NormalizedRecordDTO / RecordBatch
   │
   ▼
[converters/storage_converter] → 存储格式
   │
   ▼
[store] 谎度存储插件 → StoreReceipt
   │
   ▼
[converters/view_converter] → UIComponentDTO / ViewModel
   │
   ▼
[present] 调度 UI 组件插件 → 页面/描述文件
   │
   ▼
页面交互 → request_converter → TaskConfigDTO（闭环）
```

> 注：`[store] 谎度存储插件` 为笔误，实为「调度存储插件」。

### 3.3 分阶段调用方向（防递归）

```text
阶段 1（Wave 1a）：
  main/api → pipeline.engine → plugins（经 registry）→ infra（委托 utils/）

阶段 2（Wave 2 切换期）：
  main/api → services（legacy 门面）→ pipeline.engine → plugins → infra
  旧 spiders/parsers/exporters 导入门面 → 转发到 plugins/

阶段 3（兼容期结束，目标态）：
  main/api → pipeline.engine → plugins → infra
  services/ 移除或退化为纯 DTO 别名
```

**禁止调用方向**：service → pipeline → 同一 service（递归）；插件反向调用 pipeline；contracts 依赖 plugins/pipeline（契约层保持无依赖）。

### 调用方向硬性规则

1. 契约层零依赖（仅标准库 + 校验库）。
2. 插件只向内依赖：plugins → contracts/infra，禁止 plugins → pipeline。
3. 转换器只做格式转换，不写业务判断。
4. 段落标号小节（§）引用保持与本节一致，修订时同步。

### 3.4 渐进迁移三阶段

| 阶段 | 调用链 | 说明 |
|---|---|---|
| 阶段 1 | main/api → pipeline.engine → registry → plugins（经 infra） | 新链路最小可用（垂直切片） |
| �阶段 2 | main/api → services（兼容门面）→ pipeline | 旧入口转发到新引擎；旧函数签名不变 |
| 阶段 3 | main/api → pipeline | services 退化为 DTO 别名或移除 |

> 每阶段结束全量回归 + CLI/API 手动验证。阶段 2 起旧入口与新链路必须**同任务禁止双跑**（防止重复副作用，§5.5）。

---

## 3A. `services/` 与 `storage/` 的定位说明

**`services/` 是 V2.2 资产，不是 V3.0 的组成**。V2.2 验收后 `services/` 存在时：

1. Wave 1a 期间：pipeline 不调用 services；services 继续服务旧入口（旧 CLI/API 兼容）。
2. Wave 2 切换：`main.py`/`api/server.py` 切到 pipeline，services 变成 legacy 门面（仅转发，无业务）。
3. 兼容期结束后：services 移除或退化。**核心仅依赖协议、DTO 与注册表，不按学校/source/plugin_id 写分支。**

`infra/storage/` 复用 V2.2 `storage/`（JSONLStore/ProgressStore/ConfigStore）已验收实现，初期直接导入旧包路径；Wave 2 集成时如路径调整，由 G 统一改导入并登记到 interfaces.md。**不得复制成两套缓存、熔断或存储实现。**

---

## 4. 数据契约（DTO）与调用语义

### 4.1 通用 DTO 草图

```python
# contracts/task.py
@dataclass(frozen=True)
class TaskConfigDTO:
    task_id: str                    # 任务唯一标识
    dataset: str                    # 数据集标识（如 education.tutor）
    source_id: str                  # 数据源标识
    config_ref: str                 # 配置引用（如 config/school_data.json#东南大学/机械工程学院）
    config_snapshot: dict | None    # 配置快照（可选，冻结用）
    target_url: str | None = None
    # 学校/学院/学科/年份是教育领域字段，在 profiles/education.py 中定义，不是通用必填字段

# contracts/task.py（运行状态，与不可变配置分离）
@dataclass
class TaskRunState:
    execution_state: str            # pending/running/succeeded/failed/skipped/cancelled/partial
    retry_count: int = 0
    last_attempt_at: str | None = None

# contracts/raw.py
@dataclass
class RawDataDTO:
    source_id: str
    url: str
    content_type: str               # text/html、application/json、application/pdf…
    encoding: str | None
    content: str | bytes | None     # 内容或原件引用二选一
    raw_ref: str | None             # 原件落盘路径（超限时的引用）
    fetched_at: str                 # ISO8601
    trace: dict | None = None       # 任务/页码/分页/重试链等追踪信息
    # 体积上限：content 超限（默认 10 MiB，可配）必须落盘，DTO 只带 raw_ref

# contracts/record.py
@dataclass
class NormalizedRecordDTO:
    record_id: str                  # 稳定标识（来源+自然键哈希）
    dataset: str
    schema_id: str                  # 指向 contracts/profiles/ 中的领域 schema
    fields: dict                    # 按 schema 校验的 JSON 值；非无约束 Any
    provenance: dict                # 来源、抓取时间、raw_ref、匹配依据

# contracts/ui.py
@dataclass
class UIComponentDTO:
    component_type: str             # table/chart/card/filter（内置四种；未知类型占位并报错，不无声消失）
    payload: dict
    data_ref: str | None            # 数据引用（文件/API 路径），与渲染声明分离
    events: dict | None             # 事件声明（如过滤 → request_converter）
```

### 4.2 各阶段输入/输出契约表

| 阶段 | 输入 | 输出 | 基数 | 错误行为 | 版本 |
|---|---||---|---|---|
| acquire | TaskConfigDTO | RawDataBatch（1..N RawDataDTO） | 1→N | 单页失败记录进 trace，全部失败抛 StageError | raw.schema=v1 |
| process | RawDataBatch 或 RecordBatch | RecordBatch | N→N | 单条失败不阻断批次，记 provenance.error | record.schema=v1 |
| store | RecordBatch | StoreReceipt（每目标一份） | 1→N（fan-out） | 单目标失败只影响该目标回执 | store.schema=v1 |
| present | ViewModel | UIComponentDTO 列表 | N→N | 单组件失败占位 + 错误提示，不阻断整页 | ui.schema=v1 |

### 4.3 新增辅助 DTO

```python
# contracts/result.py
@dataclass
class StoreReceipt:
    target: str                     # 存储目标标识
    status: str                     # written/skipped/failed
    records_written: int
    output_ref: str | None          # 输出文件/表路径
    error: str | None = None

@dataclass
class StageResult:
    stage: str
    status: str                     # succeeded/failed/partial
    items_in: int
    items_out: int
    errors: list[dict]

@dataclass
class RunResult:
    run_id: str
    tasks: list[TaskRunState]
    receipts: list[StoreReceipt]
    errors: CLI/API 汇总
```

> 注：`RunResult.errors` 上一行伪代码笔误，正式冻结时以 dataclass 字段类型补齐（如 `errors: list[dict]`）[sic] [sic]——修正为统一类型再冻结。

[sic][sic] [sic]

[sic][sic][sic] [sic]

[sic][sic] [sic]

[sic]

---

## 4A. `services/` 契约兼容

V2.2 `CrawlerService.run_source_a/b`、`execute_task` 返回 `CrawlResult(task_id, status, records, failures, error_message, error_type)`；V3.0 阶段间传 DTO，不直接复用该形状。转换关系：

- V2.2 引擎产出的 `list[dict]` 经**显式** LegacyRecordBatch 适配进 record 侧（不伪装成 HTML RawDataDTO）。
- 教育 profile 回 schema v1 时：**university 不得被 school 简单替换**；保持 `university、college、category、source_type、raw_ref` 及其他既有字段不丢。
- `execution_state/retry_count/last_attempt_at` 归 TaskRunState，legacy 转换兼容 V2.2 CrawlTask。

---

## 5. 调度、合并与副作用边界

### 5.1 并发模型

- 保留 `ThreadPoolExecutor`（现 `main.py` 模式），先实现有界任务并发。
- 不同时引入分布式、复杂 DAG、asyncio 双栈。
- **列表→详情 fan-out**（现 `run_source_a` 逐条 `fetch_detail` 的模式）由采集插件内部组装为有界原始批次；分页终止条件：去重/最大页数/取消令牌。页面发现不藏进纯处理器。
- **HTTP 重试由 infra/http 负责；管道重试有独立边界/预算**，两者不相乘。失败任务重试从明确检查点恢复；非幂等插件不自动重放。

### 5.2 多源合并

- 多源合并按 dataset/领域分组，汇聚**本次运行范围**的批次后合并；不逐条合并，不跨学校/学院混合。
- 复用现有三阶匹配算法（`pipelines/merge.py`：exact → strip → fuzzy 0.85 阈值，见 `match_records`）。
- 参与策略显式化：所选来源、缺失来源、失败来源、历史来源是否参与，由配置决定；**默认不读旧年份文件混入新结果**。

### 5.3 状态机

```text
pending → running → succeeded
                 ↘ failed → （重试）→ running
                 ↘ partial → running（补采）
                 ↘ cancelled
跳过：pending → skipped（断点续抓命中）
```

旧 API 状态映射：`done→succeeded`、`pending→pending`、`failed→failed`，映射表在 `contracts/task.py` 中定义。

### 5.4 多存储 fan-out 与失败语义

- 多存储是同一处理结果 fan-out：JSONL、Excel、SQLite 各自回执 StoreReceipt，不承诺跨目标全局事务。
- 存储成功但展示失败：**不重抓、不重写存储**；present 标记 partial，由用户决定重试。
- required/optional 存储目标明确决定 RunResult 总体状态：required 失败 → run failed；optional 太败 → partial。

### 5.5 原子写与线程安全

- 保留 `tempfile.mkstemp + os.replace` 原子写；同输出路径**进程内锁**必须保留（V2.2 `ProgressTracker`/`CrawlCache` 的 `threading.Lock`）。
- 原子 replace 只防半文件，不防丢失更新：**读改写必须整体加锁**（V2.2 ProgressStore 契约延续）。
- 四线程并发 ≠ 多进程安全：若支持 CLI/API 多进程同目录，需另加进程锁或明确禁止并文档化。

### 5.6 present 不依赖浏览器

CLI 无界面执行同样生成展示 DTO/描述文件（`data/output/*.views.json` 拟新增），Dashboard 消费它们；present 阶段不强制启动浏览器。

---

## 6. 插件迁移映射与配置系统

### 6.1 旧 7 类 → 新 4 类映射

| 旧 kind | 新归属 | 说明 |
|---|---|---|
| source | 数据源/profile 声明（配置，非插件）+ legacy adapter | 组合声明由 `config/pipeline.yaml` 与教育 profile 承载 |
| fetcher | `plugins/spiders/` | 旧 fetch 函数表 + 新类注册表由统一 registry 派生兼容视图 |
| parser | `plugins/processors/`（解析阶段） | 与后处理区分阶段 |
| processor | `plugins/processors/`（后处理阶段） | |
| exporter | `plugins/storage/` | 保留 `jsonl`/`xlsx` 旧 ID 别名 |
| presenter | `plugins/ui/` | 旧页面导航与新组件清单分开维护 |
| utility | 受管基础服务/受控扩展 | cache/progress/http_session 并入 infra 受管服务；外部 setup 插件无法无损迁移的，输出诊断并留在明确标记的 legacy 模式，不静默忽略 |

**显式迁移约束**：
- `static_html` 旧配置名与 `static_list` 类名必须显式映射（registry 兼容视图）。
- 旧权重 `{name: weight}` 按 `(weight, id)` 升序确定顺序，默认链、禁用值、未知 ID、重复 ID、别名冲突行为确定（预检报错，不静默）。
- 旧外部插件（`plugins_ext/`）只经显式映射确认后迁移，映射/冲突报告随迁移脚本输出；**不静默丢弃**。

### 6.2 声明式配置（pipeline.yaml + plugins.yaml）

```yaml
# config/pipeline.yaml —— 明确有序步骤与 fan-out
pipeline:
  acquire:
    steps:
      - plugin: static_html          # 引用 plugins/spiders/static_html
        profile: education.tutor     # 领域 profile
  process:
    steps:
      - plugin: yzw_major_parser     # 解析
        stage: parse
      - plugin: normalize
        stage: post
      - plugin: dedup
        stage: post
      - plugin: merge                # 多源合并（按 university+college 分组）
        stage: post
  store:
    steps:
      - plugin: jsonl_store
        required: true
      - plugin: xlsx_store
        required: false
  present:
    components:
      - table_component
      - chart_component
```

```yaml
# config/plugins.yaml —— 插件实例、启用状态、参数
plugins:
  static_html:
    enabled: true
    version: ">=1.0"
    params: {timeout: 30}
  yzw_major_parser:
    enabled: true
    params: {fuzzy_threshold: 0.85}
  jsonl_store:
    enabled: true
    params: {output_dir: data/output}
  sql_store:
    enabled: false
    params: {dsn: sqlite:///data/output/platform.db}
```

**配置规则**：
- `pipeline.yaml` 存在时为唯一真值；仅当其不存在时读取旧 `plugins.json` 兼容模式；**禁止两套同时可写**。
- 旧 JSON 显式迁移：预览 → 校验 → 备份 → 原子写 → 切换，输出映射/冲突报告（`scripts/migrate_config.py` 拟新增）；不自动覆盖学校配置。
- 任务开始时冻结配置与注册表版本；运行中改配置只影响后续任务（§7.6）。
- YAML 解析用安全加载（禁止任意对象实例化，PyYAML `safe_load`）；schema 验证依赖（jsonschema/Pydantic）的选型与版本在 Wave 0 核验后冻结。

### 6.3 插件元数据（metadata.json）

```json
{
  "name": "static_html",
  "version": "1.0.0",
  "author": "community",
  "kind": "spider",
  "schema_in": "TaskConfigDTO",
  "schema_out": "RawDataBatch",
  "entry_point": "plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin",
entry_point_json": "plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin",
  "entry_point_py": "plugins.spiders.dynamic.plugin:DynamicPlugin",
  "dependencies": ["requests"],
  "min_core_version": "3.0.0"
}
metadata.json 中 entry_point 与 entry_point_py 为同一字段的别名（文档笔误，冻结时以 entry_point 为准）。
```

---

## 7. 插件治理与安全

### 7.1 发现与加载顺序

```text
1. 扫描 metadata（不 import 插件代码）          ← 候选发现
2. 校验 metadata（字段、kind、版本、依赖、入口路径）
3. AST 静态校验（既有 security/plugin_validator.py 规则延续）
4. 管理员批准（外部插件）
5. 加载（import）→ 接口验证（实现对应协议）
6. 注册到单一 registry
```

候选发现与加载/启用分离：发现只读 metadata；加载发生在批准之后。**禁用插件不加载。**

### 7.2 两种声明方式

- 方式一：`metadata.json`（推荐，外部插件必须）。
- §6.3 示例字段即 metadata.json 结构；`plugin.py` 内 `PLUGIN_META` 字典作为轻量替代，仅限内置插件使用。`kind` 取值固定四类：spider/processor/storage/ui。

###  declaration marker

- 内置插件用类装饰器注册：`@register_plugin` 声明 kind、name、version。
- 外部插件必须 metadata.json + 管理员批准。
- 单一 registry：插件 ID 不静默覆盖；同 ID 冲突预检报错。
- schema_id 映射受控：不 eval/动态导入任意字符串；schema_id → 校验器查注册表，未知 schema_id 拒绝。

### 7.3 AST 检查的定位（如实表述）

- AST 检查是**加载前的静态策略检查**（受限 import/调用黑名单），不是沙箱。
- **不照搬旧方案「先导入后安全检查」或「白名单沙箱」叙述**——加载（exec_module）在安全检查之后，且检查通过 ≠ 代码可信。
- 不扩大本次检查范围；不可信代码隔离运行作为独立能力，交付前禁用。

### 7.4 上传与审批

- Python 插件面向**已批准、可信开发者**；网页上传进入隔离待审区（`plugins_ext/_pending/`），**不自动导入/执行**。
- 未经批准代码不能在 API 进程执行。
- 上传管理保留既有能力，但**安全行为变更**：权限控制、请求防护、大小限制、路径规范化、审计日志、版本留存与回滚。
- 上传返回校验详情（通过/失败原因），与 V2.2 行为差异在 dashboard 提示中说明。

### 7.5 热更新语义

- 热更新只替换**后续任务**的 registry 快照；活动实例不能通过清 `sys.modules` 强行卸载（V2.2 实现维持）。
- 原生库/依赖更新要求重启 worker。

### 7.6 运行护栏

- HTTP 合规限速（PoliteSession 延续）；站点访问边界由配置声明；敏感信息不写日志；UI 输出转义。
- **不把反爬绕过作为必需功能**；自适应选择器等能力按需评估后作为可选插件。

---

## 8. UI 组件插件化与 API

### 8.1 设计要点

- 四种内置组件全部交付：`table_component`、`chart_component`、`card_component`、`filter_component`。
- 继续使用现有 Flask + 原生前端 + Chart.js；**不引入 SPA 重写**。
- 第一层插件返回**可校验描述 DTO**（UIComponentDTO），宿主固定 renderer 渲染：组件、数据引用、事件声明相互分离。
- 未知 component_type：可见占位 + 错误提示，不无声消失。

### 8.2 受管 renderer manifest

- dashboard 宿主内置固定 renderer（table/chart/card/filter）。
- 新增 renderer 的注册机制：**受信任静态资源 manifest**——新 renderer 安装 = 新增包 + 资源 + 配置登记，**不改宿主分支**。
- 不直接注入任意 HTML/JS：内容转义、CSP、同源受管资源、动作白名单；过滤器请求经 `request_converter` 转成有效 TaskConfigDTO。

### 8.3 明确边界（防虚报）

- 「只换已有组件配置」≠「新增渲染实现」；不能把硬编码几种 renderer 宣称为全部 UI 可插拔。
- 表格、图表、卡片、过滤器四种内置组件的**组件级可配置**是基线交付；新增渲染实现经 manifest 机制支持。

### 8.4 API 端点规划

**已有端点（升级兼容，V2.2 实现）**：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/plugins` | GET | 插件清单（builtin+external+overrides） |
| `/api/plugins/upload` | POST | 上传（进入待审区，不自动执行） |
| `/api/plugins/<key>` | PUT/DELETE | 启停/配置/卸载 |
| `/api/plugins/<key>/reload` | POST | 热重载（后续任务生效） |
| `/api/plugins/pipeline/<type>` | PUT | 权重链调整 |

**拟新增端点（V3.0）**：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/pipeline/run` | POST | 触发管道运行 |
| `/api/pipeline/runs/<id>` | GET | 运行状态/StageResult/回执 |
| `/api/pipeline/validate` | POST | 配置预检（YAML schema + 引用插件存在性） |
| `/api/ui/components` | GET | 当前配置的组件清单（UIComponentDTO） |
| `/api/ui/components/layout` | PUT | 组件布局持久化 |

旧 `/api/crawl`、`/api/tutors`、进度接口保留教育兼容视图。

---

## 9. 开源参考与依赖策略

> **调研状态声明**：以下条目基于既有认知与文档入口，本次编写时外部网络访问受限（Jina 超时、官方文档直连失败），**未完成在线核验**。表中「核验状态」如实标注；实施前须按官方文档核对机制细节，不把未核验内容当既定结论。

| 项目 | 官方入口 | 建议借鉴机制 | 本地落点 | 引入依赖？ | 核验状态 |
|---|---|---|---|---|---|
| Scrapy | docs.scrapy.org / github.com/scrapy/scrapy | Item Pipeline 有序链、Feed Exports 多目标、settings BASE+覆盖 | pipeline/engine.py、plugins/storage/ | 否（可选适配器） | 未在线核验 |
| Crawlee (Python) | crawlee.dev / github.com/apify/crawlee-python | RequestQueue、浏览器资源池 | plugins/spiders/js_render、infra | 可选 | 未在线核验 |
| Meltano | docs.meltano.com / github.com/meltano/meltano | 声明式 YAML 配置、连接器元数据 | config/pipeline.yaml、plugins.yaml | 否 | 未在线核验 |
| PyPA entry points | packaging.python.org | 插件发现补充机制（可选） | plugin_manager/loader.py | 否 | 未在线核验 |
| Pydantic / jsonschema | docs.pydantic.dev / jsonschema.readthedocs.io | DTO/schema 运行时校验 | contracts/ 校验 | 可选（Wave 0 冻结选型） | 未在线校验 |
| WaterCrawl | 待核验 | AbstractPlugin 抽象基类 | plugins/base.py | 否 | 待核验（仓库待确认） |
| Scrapling | 待核验 | 自适应选择器 | 可选 spider 插件 | 可选 | 待核验（仓库待确认） |
| OmniData / Universal Harvester / Perseus / scpun-crawl | 无唯一仓库地址，待确认 | 仅记录方向，不作为关键依赖 | — | 否 | 待核验 |

**依赖策略**：
- 直接依赖或复制代码必须核对实际版本、LICENSE/NOTICE 义务；**不宣称「借鉴设计思想完全不涉及许可证」**。
- 新增运行时依赖（YAML 解析、schema 校验）在 Wave 0 冻结选型与版本，登记 NOTICE；不执行 requirements 自动安装。
- 可选依赖（Playwright、Scrapling 等）由插件 metadata 声明，缺失时插件禁用而非崩溃。

### 9.1 重点机制结合说明

1. **Scrapy × pipeline**：权重字典 `{name: weight}` 按 `(weight, id)` 排序执行（延续 V2.2 `config/plugins.json` 语义）；BASE 内置 + 用户覆盖禁用。
2. **Crawlee × 采集**：列表→详情 fan-out、分页终止、有界批次（§5.1），浏览器插件借鉴资源池思想。
3. **Meltano × 配置**：pipeline.yaml/plugins.yaml 双文件、连接器元数据。
4. **pluggy 纪律**：不引入依赖，但保留 hookspec 式接口约定文档，固定各 kind 签名。
5. **UI 插件化**：借鉴 Perseus「components/views 分包」方向（待核验），落地为 `plugins/ui/` + dashboard manifest 机制。

---

## 10. Wave 划分、文件所有权与实施步骤

### 10.1 总览

```text
V2.2 Gate → Wave 0 契约冻结 → Wave 1a 垂直切片 → Wave 1b 并行开发 → Wave 2 集成切换 → Wave 3 验收交付
```

| 阶段 | 内容 | 前置依赖 | 估时（工作量/关键路径） |
|---|---|---|---|
| V2.2 Gate | 交接确认（§1.3） | V2.2 完成 | 0.5 人日 |
| Wave 0 | 冻结 DTO/协议/配置 schema/错误/兼容契约；最小离线插件链测试 | Gate | 0.5–1 人日 |
| Wave 1a | 治理/基建/最小引擎 + 静态垂直切片（静态源→解析→JSONL→表格） | Wave 0 | 2–3 人日 |
| Wave 1b | 并行补齐四类插件 + 配置/API 兼容 | Wave 1a | 3–5 人日（并行 3–5 自然日） |
| Wave 2 | 按依赖集成、迁移预览、新旧对照、并发与失败恢复、逐步切换入口 | Wave 1b | 1.5–2.5 人日 |
| Wave 3 | 默认切换、全量兼容验收、示例插件 + 第二数据集验收、回滚演练 | Wave 2 | 1–2 人日 |

**总计**：约 8.5–14 人日；原「10 天」为原型目标而非完整交付保证。人日 ≠ 自然日；关键路径 = Wave 0 → 1a → 2 → 3。同一文件只能一个写入者；**共享工作区并行，不各自 checkout 分支**。

### 10.2 Agent 分工（后续职责，非本次启动代理）

| Agent | 职责 | 关键交付 |
|---|---|--|---|
| A | pipeline、services 兼容门面、main/API | pipeline/engine.py、stages、main.py/API 切换、兼容层 |
| B | 存储插件 + storage_converter | jsonl/xlsx/sql/progress 插件；复用 JSONLStore/ProgressStore/ConfigStore/ExportService |
| C | spider 插件 + raw_converter + legacy 引擎适配 | 五个采集插件、LegacyRecordBatch 适配、兼容视图 |
| D | processor 插件 + plugin_manager | 治理框架 + 解析/合并/统计插件；**工作量偏大，先治理后处理器，必要时 G 协调，不伪装全并行** |
| E | infra/context、UI 插件、Dashboard、request/view converter | 先交付基建，后 UI |
| F | 隔离 fixtures、集成/契约/覆盖率 | 模块所有者写各自独占单元测试；F 负责跨模块集成与覆盖率 |
| G | 契约/配置 schema/共享文件协调、分阶段集成、验收 | interfaces.md 增量登记、集成、验收报告 |

### 10.3 实施步骤（每阶段：任务→文件→测试→退出条件→回滚）

#### V2.2 Gate（0.5 人日）

- **任务**：逐项确认 §1.3 清单。
- **退出条件**：清单全勾或有书面豁免；登记实际基线。
- **回滚点**：不适用（只读确认）。

#### Wave 0（0.5–1 人日，Agent G，F 提前备 fixture）

- **任务**：冻结 `contracts/`（task/raw/record/ui/result/profiles 接口）、`plugins/base.py`、`infra/context.py`；配置 schema（YAML 结构 + 校验）；错误分类与兼容映射；`docs/refactor/interfaces.md` 增量登记；最小离线插件链测试（mock 插件贯穿四阶段）。
- **文件**：`contracts/**`、`plugins/base.py`、`infra/context.py`、`config/*.yaml` schema、`docs/refactor/interfaces.md`、`tests/test_wave0_contract.py`。
- **测试**：契约导入、DTO 校验、mock 链路 smoke。
- **退出条件**：契约文档冻结；smoke 测试通过。
- **回滚点**：契约 revert 即回 V2.2 行为（新目录独立存在）。

#### Wave 1a（2–3 人日，A + E + D 前置部分）

- **任务**：plugin_manager 最小实现（发现/校验/注册）、infra/context、最小 pipeline.engine + acquire/process/store/present 阶段调度、静态垂直切片。
- **文件**：`plugin_manager/**`、`infra/**`、`pipeline/**`、`plugins/spiders/static_html/`、`plugins/processors/yzw_major_parser/`（或静态解析插件）、`plugins/storage/jsonl_store/`、`plugins/ui/table_component/`。
- **测试**：垂直切片端到端（离线 fixtures）。
- **退出条件**：离线静态链路产出与旧链路同构 JSONL + 表格视图 DTO。
- **回滚点**：新链路独立目录，关闭即回 V2.2。

#### Wave 1b（3–5 人日，A/B/C/D/E 并行 + F）

| 责任块 | 任务 | 主要文件 |
|---|---|---|
| C | 五个采集插件 + raw_converter + legacy 适配 | `plugins/spiders/**`、`converters/raw_converter.py` |
| D | 解析/归一/合并/统计插件 | `plugins/processors/**` |
| B | JSONL/Excel/SQLite/进度存储插件 + storage_converter | `plugins/storage/**`、`converters/storage_converter.py` |
| E | UI 四组件 + view_converter + request_converter | `plugins/ui/**`、`converters/view_converter.py`、`request_converter.py` |
| A | 配置系统 + API 兼容 + main 改造 | `config/pipeline.yaml`、`config/plugins.yaml`、`api/server.py`、`main.py` |
| F | 契约/转换器/集成测试 + fixtures | `tests/**` |

- **退出条件**：各责任块测试通过；配置迁移预览工具可用（`scripts/migrate_config.py` 拟新增）。
- **回滚点**：每责任块独立目录，单块 revert 不影响他块。

#### Wave 2（1.5–2.5 人日，Agent G）

- **任务**：按依赖集成（E→D→C→B→A→F 顺序核对）；配置迁移预览 → 校验 → 备份 → 原子写 → 切换；旧/新离线结果对照（同输入 JSONL diff 为空）；四线程并发与失败恢复；逐步切换 main/API 入口。
- **退出条件**：§11 验收矩阵全绿；对照差异报告归档。
- **回滚点**：配置备份 + 固定 V2.2 版本可回退。

#### Wave 3（1–2 人日，Agent G + 各所有者）

- **任务**：默认入口切换；示例插件零主干改动验收；第二数据集（无教育字段）贯穿验收；交付文档；回滚演练。
- **退出条件**：§11 全部通过；验收报告输出。

### 10.4 并行纪律

- Wave 1b 各责任块文件不相交；共享文件（`config/pipeline.yaml` schema、`docs/refactor/interfaces.md`）由 G 独占写。
- Wave 1b 不能在 Wave 0 契约冻结前全速实施；先接口交付再按依赖汇合。
- 模块所有者写各自独占的单元测试；F 只写跨模块集成/契约测试，避免与所有者抢测试文件。

---

## 11. 验收标准与回滚

### 11.1 验收矩阵

| # | 验收项 | 证据/命令（拟新增测试或脚本除注明外） | 通过标准 |
|---|---|---|---|
| 1 | 旧 CLI 全参数兼容 | `python main.py --help`；逐参数冒烟 | 全部参数可解析，退出码 0 |
| 2 | 旧函数兼容 | 调用 `main.run_source_a/b`、`main.execute_task`、`main.build_tasks`、`main.run_merge` 旧签名 | 返回形状与 V2.2 一致 |
| 3 | Source A/B 全流程 | 离线 fixtures 驱动 source_a/source_b | 产出与 V2.2 同构 JSONL |
| 4 | resume/retry_failed/force | 模拟中断重跑 | 行为与 V2.2 一致 |
| 5 | 旧配置/JSONL/Excel/进度/失败记录格式 | 读旧文件 → 新链路 → 对照 | 字段不丢、结构不变 |
| 6 | DTO 边界错误 | 非法链、空结果、DTO 校验失败 | 明确错误码与消息 |
| 7 | 分页/详情 fan-out | 多页 fixture | 批次完整、去重生效 |
| 8 | 多源部分失败 | 单源失败 fixture | partial 状态正确、成功源不回滚 |
| 9 | 三阶合并回归 | 复用 `tests/test_merge.py` 样例 | 匹配结果与 V2.2 一致 |
| 10 | 存储原子性 | 注入写失败 | 无半文件、临时文件清理、重执行幂等 |
| 11 | 并发 4 线程 | 同路径读改写 + 状态无丢失 | 无损坏、无丢失更新 |
| 12 | 插件发现不执行 | 发现阶段不 import | metadata-only 扫描验证 |
| 13 | 禁用不加载 | 禁用插件 | 模块未 import（sys.modules 检查） |
| 14 | 冲突/版本拒绝 | 同 ID 插件、低于 min_core_version | 拒绝并报错 |
| 15 | 热更新快照 | 运行中更新插件 | 后续任务生效，活动任务不受影响 |
| 16 | 上传进入待审区 | 上传外部插件 | 不自动执行，待批准 |
| 17 | 未知 UI 组件 | 未知 component_type | 可见占位+错误提示 |
| 18 | 第二数据集贯穿 | 无教育字段数据集走完四阶段 | 四阶段均产出标准 DTO |
| 19 | 示例插件零主干改动 | 新增插件只加包+配置 | `git diff pipeline/ contracts/ converters/ plugin_manager/ infra/` 为空 |
| 20 | UI 组件配置切换 | Playwright 驱动 dashboard | 组件切换/过滤/刷新/错误提示可用 |
| 21 | 覆盖率 ≥ 80% | `pytest tests/ --cov=pipeline --cov=contracts --cov=converters --cov=plugins --cov=plugin_manager --cov=infra --cov-report=term` | 整体 ≥ 80%；关键模块单独报告；注明排除范围 |
| 22 | 配置校验入口修正 | `python -c "from config.validator import validate_all_configs; from config.loader import load_schools_config; r=validate_all_configs(load_schools_config()); print('errors:', len(r['errors']))"` | errors==0 或逐条修复 |
| 23 | 真实站点可选手工验证 | 可控目标 + 隔离输出 | 标记「手工验证，非自动门槛」 |
| 24 | 回滚演练 | 恢复配置备份 + V2.2 版本 | 可回滚且数据不损 |

### 11.2 并发与多进程边界

- 四线程并发验证通过 = 线程安全证据；**不冒充多进程安全**。多进程同目录支持需进程锁，明确禁止或文档化，不在本期承诺。

### 11.3 灰度与回滚

- 固定 V2.2 版本（tag）+ 配置备份 + `data/` 快照。
- 新旧对照运行写入**不同输出目录**（如 `data/output_v3/`），同任务禁止自动双跑（防重复副作用）；差异报告人工评审后切换。
- 回滚步骤：恢复配置 → 切回 V2.2 版本 → 校验旧链路可用。
- 输出 V3.0 验收报告至 `docs/refactor/acceptance_v3.md`（拟新增），**保留 V2.2 `docs/refactor/interfaces.md` 冻结记录，不覆盖旧交接报告**。

### 11.4 真实网络验证定位

- 真实学校请求仅为**可选手工验证**：可控目标、隔离输出、记录网络/认证限制；**不作为自动验收门槛**。
- 自动化验收全部离线（fixtures + 临时目录）。

---

## 12. 后续扩展路线图（V3.0 之后）

1. 插件市场：内部注册中心，一键安装。
2. 可视化管道编排：拖拽配置 pipeline.yaml（参考方向待核验）。
3. 多语言插件：gRPC/HTTP 接入非 Python 插件。
4. AI 辅助解析：processors 中 LLM 解析插件。
5. 分布式采集：RequestQueue 多机协同（参考 Crawlee，未核验）。
6. 消息/通知类 utility 插件与信号系统（延续旧阶段 D 方向）。

---

## 附录 A：V2.2 → V3.0 术语映射

| V2.2 术语 | V3.0 术语 | 说明 |
|---|---|---|
| CrawlTask（university/college/category/source/year/force/config） | TaskConfigDTO + education profile | 领域字段进 profile |
| CrawlResult | RunResult / StageResult | 状态机见 §5.3 |
| ENGINE_REGISTRY（类/函数两套） | 统一 plugin registry | 兼容视图派生 |
| plugins.json（overrides/pipeline） | pipeline.yaml + plugins.yaml | 兼容期读取旧 JSON |
| 七类插件 | 四类插件 | 映射见 §6.1 |
| data/output/*_faculty.jsonl | RecordBatch → jsonl_store 插件 | 格式不变 |
| progress.json | ProgressStore（infra）+ progress_store 插件 | 格式不变 |
| summary.xlsx | xlsx_store 插件 | 格式不变 |

---

## 附录 B：与旧计划书（2026-09 版）的差异摘要

| 旧计划书 | 新计划书 |
|---|---|
| 7 类插件 + 配置只读页 | 4 类插件 + 契约驱动管道 + 配置迁移 |
| 最小侵入（不动主流程） | 渐进迁移（垂直切片→并行→集成切换） |
| 外部插件上传即执行 | 上传进待审区，批准后加载 |
| 「白名单沙箱」表述 | 如实表述：AST 是静态门禁，非沙箱 |
| 5–8 天完成 | 8.5–14 人日，标注原型目标 vs 完整交付 |
| 开源借鉴泛泛背书 | 借鉴机制 + 依赖策略 + 核验状态表 |
| 无目录章节 | §2 目录结构与放置规则（重点章节） |
| 无 DTO 语义表 | §4.2 部阶段输入/输出契约表 |
| 无所有权矩阵 | §10.2 Agent 分工 + 文件独占规则 |
| 无回滚与灰度 | §11.3 灰度、回滚、双跑禁止 |
| 未核验内容未标注 | 核验状态如实标注（未在线核验/待核验） |
