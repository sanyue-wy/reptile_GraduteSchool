# 通用网络数据采集与处理平台 · V3.0 可执行计划书

> 编制日期：2026-09-17
> 实施前提：完成 V2.2 重构并通过验收，再启动本计划。
> 本次交付仅为计划书，不代表以下目录、功能或测试已实现。
> 核心方向：多媒体资产契约驱动的管道—过滤器架构，统一 spider、processor、storage、presenter、ui 五组插件。
> 控制台仅负责插件管理、任务定义、输出定义；成品输出由呈现器负责。导师调研是基本验证组合，不是核心数据模型。
> 开发辅助目标：5 分钟定义任务、30 分钟完成首个插件、约 30 行业务代码起步、20 套 HTML 模板快速切换。时间目标须实测，不是已达成结论。

### 阅读顺序

先读 §2 目录、§3 数据流、§4 契约，再按 §10 分工实施；§8 定义控制台/呈现器，编辑器、脚手架、20 套模板和十篇指南的落地规格见 [tasks/](tasks/README.md) 多窗口任务卡（W7/W8），§11 是最终验收门槛。

本次只修改计划书，不创建目录、不实现代码、不安装依赖、不执行采集或发布。以下新路径、接口和命令均为未来交付要求。

## 1. 目标、现状与启动门槛

### 1.1 本期交付

1. 统一主干 acquire → process → store → present，不按学校、来源、媒体类型或具体输出格式写业务分支。
2. MediaAsset、原始资产批次、通用记录、存储回执、呈现请求及 RenderedOutputDTO；支持文本/图片/音频/视频/文档/二进制。
3. 静态 HTML、AJAX、JS、PDF、研招网采集，以及受控直接媒体 URL 下载示例。OCR/音频分析/转码预留协议与可选适配点，不宣称已经具备生产级处理能力。
4. 列表/详情/研招解析、归一、去重、合并、统计；资产引用在处理后保持可追踪。
5. JSONL、Excel、SQLite、进度快照、媒体存储；兼容旧数据路径和格式。
6. 五个内置呈现器：HTML、Text（含 Markdown 模式）、JSONL、CSV、PDF；XML 定义扩展格式规范，不列入五个内置实现。
7. HTML 下的 table/chart/card/filter 四个 UI 组件、20 套完整模板、ThemeSwitcher 与预览图；不是只交付模板名称。
8. 控制台三功能、schema_editor 三个预设、五类插件及模板脚手架、十篇开发指南、MkDocs/mkdocstrings 文档构建。
9. 配置迁移、批准与生命周期管理、CLI/API 兼容、离线回归、浏览器验收、新手计时和回滚演练。

“主干零修改”指在既有契约和执行模型内新增能力，只新增插件包、插件自带 schema/资源及配置。新增执行模型或改变核心契约仍需版本化升级，不能承诺任意变化永远无需改主干。

本期不重命名仓库，不重写为 SPA，不引入分布式调度、复杂 DAG 或另一套异步运行时。Scrapy/Crawlee 等只作为可选适配器，不成为核心依赖。不支持未经审查的任意 Python 代码安全执行。

### 1.2 当前资产与 V2.2 预期交付分开记录

依据：[V2.2 架构分析](../V2.2/ARCHITECTURE_ANALYSIS.md)、[实施总览](../V2.2/agents/README.md)、[冻结契约登记](../refactor/interfaces.md)。冻结登记中的纠正优先于原指导书冲突示例，最终签名以 V2.2 验收结果为准。

| 资产 | 当前观察 | V3.0 处理 |
|---|---|---|
| [config/plugins.py](../../config/plugins.py) | 已有七类清单、覆盖配置、发现/上传/重载 | 迁移治理逻辑，保留旧管理入口 |
| [spiders/engine.py](../../spiders/engine.py) | 类注册表与包级函数表并存；fetch 返回已解析记录 | 统一 registry，显式 legacy 适配，再拆分抓取与解析 |
| [processors/__init__.py](../../processors/__init__.py) | normalize/dedup/merge；merge 是兼容占位 | 复用算法，不把占位当作实际多源合并 |
| [exporters/__init__.py](../../exporters/__init__.py) | JSONL/Excel 注册入口 | 包装成 storage 插件 |
| [security/plugin_validator.py](../../security/plugin_validator.py) | 加载前 AST 校验；非沙箱 | 保留拒绝策略，扩展元数据和批准流程 |
| services、storage、HTTP/缓存整合 | V2.2 交付范围；部分模块存在不等于整体完成 | 必须先核验服务接入、线程安全与兼容性 |
| pipeline、contracts、converters、统一 UI 组件 | 本计划新增 | 不描述为当前已实现 |

### 1.3 V2.2 Gate

开工前由集成人员记录基线提交、Python/依赖版本、实际测试输出和覆盖率，检查：

- [ ] CrawlerService、MergeService、ExportService 已接入 CLI/API；旧函数签名和返回值保留。
- [ ] JSONLStore、ProgressStore、ConfigStore 已验收；原子写入和失败清理正常。
- [ ] 生产路径由 PoliteSession 管理唯一熔断状态；不存在两套独立熔断器。
- [ ] ProgressTracker、CrawlCache 的锁及并发测试保留。
- [ ] 测试隔离真实配置/数据，source A/B、resume、retry_failed、force 均有回归证据。
- [ ] V2.2 验收报告已交接。历史测试数量不能代替本次基线。

未通过项返回 V2.2 收尾。本计划可先编写，V3.0 代码实施不得以“已有几个目录”为由跳过 Gate。

## 2. 目录结构与文件放置规则

### 2.1 推荐目标目录

保持与原草案一致的六个核心目录，不额外增加 core/platform/runtime 等同义层。下树表示目标组织；兼容期仍保留 §2.4 的旧入口。省略常规 `__init__.py`。

```text
reptile_DataPlatform/                # 目标名称；迁移期实际仓库名暂保留
├── main.py
├── api/server.py
├── pipeline/
│   ├── engine.py
│   └── stages/                     # acquire/process/store/present.py
├── contracts/
│   ├── asset.py                    # MediaAsset、AssetRef
│   ├── task.py                     # TaskConfigDTO、TaskRunState、OutputSpec
│   ├── raw.py                      # RawDataDTO、RawDataBatch
│   ├── record.py                   # NormalizedRecordDTO、RecordBatch
│   ├── output.py                   # PresentationRequest、RenderedOutputDTO
│   ├── ui.py                       # ViewModel、UIComponentDTO
│   ├── result.py                   # StoreRequest/Receipt、RunResult、ErrorDTO
│   └── profiles/education.py       # 领域扩展，不作为通用必填字段
├── converters/
│   ├── request_converter.py
│   ├── raw_converter.py
│   ├── storage_converter.py
│   └── view_converter.py
├── plugins/
│   ├── base.py
│   ├── spiders/                    # 五种旧引擎 + media_downloader 示例
│   ├── processors/                 # 解析/合并/统计，媒体处理按能力声明
│   ├── storage/                    # JSONL/Excel/SQLite/Progress/Media
│   ├── presenters/
│   │   ├── base_presenter.py
│   │   ├── html_presenter/          # plugin.py、theme_switcher.py
│   │   ├── text_presenter/          # text / markdown 两种模式
│   │   ├── jsonl_presenter/
│   │   ├── csv_presenter/
│   │   └── pdf_presenter/
│   └── ui/                         # table/chart/card/filter_component
├── plugin_manager/
│   ├── loader.py
│   ├── validator.py
│   └── registry.py
├── infra/
│   ├── context.py
│   ├── http.py
│   ├── cache.py
│   ├── progress.py
│   ├── errors.py
│   └── storage/                    # 原子 I/O、媒体引用、受管输出工作区
├── scaffolds/
│   ├── cli.py
│   ├── generator.py
│   └── templates/                 # 五类插件骨架 + HTML 模板骨架
├── templates/
│   ├── registry.json
│   ├── minimal-light/             # layout.html/style.css/variables.json/preview.png
│   ├── academic-serif/
│   └── ...                        # 共 20 套，规格见 tasks/W7_presenters_ui_templates.md
├── schema_editor/
│   ├── editor.py
│   ├── generator.py
│   └── presets/                   # tutor_research/paper_collection/news_monitor.yaml
├── config/
│   ├── pipeline.yaml
│   ├── plugins.yaml
│   ├── global.json
│   ├── school_data.json
│   └── examples/tutor_research.yaml
├── dashboard/
│   ├── console/
│   │   ├── index.html             # 仅三功能导航
│   │   ├── plugins.html
│   │   ├── task-config.html
│   │   └── output-config.html
│   └── runtime/                   # 成品授权预览/静态服务桥，不保存配置逻辑
├── tests/                         # 集成/fixtures；插件包单测收集约定见 tasks/W8_editor_scaffolds_docs.md
├── scripts/                       # 迁移、验收
├── docs/
│   ├── V2.2/                      # 保留历史
│   ├── V3.0/                      # 本计划、INTERFACES、ACCEPTANCE、tasks/ 多窗口任务卡
│   ├── refactor/                  # 保留 V2.2 冻结记录和验收
│   ├── plugin_dev_guide/           # 十篇指南，规格见 tasks/W8_editor_scaffolds_docs.md
│   └── api/                       # mkdocstrings API 参考源页面
├── mkdocs.yml                     # site_dir 指向独立构建目录
└── data/
    ├── raw/                       # 原件与暂存媒体
    ├── cache/
    ├── output/                    # 旧结果兼容
    └── runs/<run_id>/outputs/      # 新成品及随附媒体，不写代码目录
```

此处没有要求本次立刻移动目录。最终目录名调整与兼容入口删除是两件事，后者须有正式废弃周期。

### 2.2 职责与依赖边界

| 目录 | 允许内容/依赖 | 禁止内容 |
|---|---|---|
| pipeline | 契约、转换器、registry 协议、受管上下文 | 具体站点 URL、教育匹配算法、插件名称分支 |
| contracts | 标准库、schema 校验；纯数据类型 | 网络、文件写入、依赖 pipeline/plugins |
| converters | 通用编解码、版本映射、已登记 legacy 格式 | 集中维护每个插件的私有解析分支 |
| plugins | contracts、infra 的公共接口；包内工具 | 反向调用 pipeline；直接依赖其他插件私有模块 |
| plugin_manager | 元数据/版本/批准/接口校验及生命周期 | 数据抓取与业务处理 |
| infra | 受管 HTTP、缓存、锁、原子 I/O | 学校/导师字段逻辑 |
| dashboard/console | 插件管理、任务定义、输出定义 | 成品布局、导师业务图表 |
| presenters | 顶层格式生成；HTML 通过受管 resolver 组合 UI | 重新抓取、重复存储、直接导入其他插件私有实现 |
| schema_editor | 字段定义、Schema/FormSpec 导出 | 自动发明抓取规则、执行用户 Python |
| scaffolds | 从统一契约生成骨架 | 自动安装/启用/批准插件 |
| templates | HTML 布局与变量声明 | 爬虫、业务合并、控制台 API 调用 |

特别区分：

- `pipeline/` 单数是新主干；旧 `pipelines/` 复数只作为过渡入口。
- `plugins/storage/` 是存储节点；`infra/storage/` 是节点复用的底层 I/O。
- `plugins/presenters/` 决定输出格式；`plugins/ui/` 仅服务 HTML 呈现器；`dashboard/console/` 不负责成品展示，runtime 只是授权访问桥。
- `templates/` 是成品 HTML 模板库；`scaffolds/templates/` 是生成代码的骨架，两者不能混用。
- 内置教育模型放 `contracts/profiles/`；外部新领域 schema 随插件包声明并注册，不必修改核心契约目录。

### 2.3 插件包与扩展速查

```text
plugins/spiders/static_html/
├── plugin.py                       # 对外入口类
├── metadata.json                   # 唯一元数据来源
└── schemas/                        # 仅确有需要时增加配置/领域 schema

plugins/ui/table_component/
├── plugin.py
├── metadata.json
└── assets/renderer.js              # 已批准的前端实现
```

最小手写插件只需 plugin.py 与 metadata.json；脚手架生成完整包（含 README、requirements、test_plugin.py），生成物约定见 [tasks/W8_editor_scaffolds_docs.md](tasks/W8_editor_scaffolds_docs.md)。集成和 fixture 统一放 tests，不复制包级测试。

| 我要做什么 | 放在哪里 |
|---|---|
| 新增采集方式或数据源连接器 | plugins/spiders/新插件 |
| 新解析、字段映射、合并、统计 | plugins/processors/新插件 |
| 新数据库或持久化策略 | plugins/storage/新插件 |
| 新成品格式（Markdown/CSV 等） | plugins/presenters/新插件 |
| 新 HTML 风格 | templates/新模板 + registry.json |
| 新表格/图表等展示实现 | plugins/ui/新插件及 assets |
| 切换已有能力/调整顺序 | config/pipeline.yaml、plugins.yaml |
| 新领域的数据形状 | 插件自带 schema；内置领域可放 contracts/profiles |

### 2.4 迁移期目录与去留

| 旧目录/入口 | 迁移去向 | 保留方式 | 所有者 |
|---|---|---|---|
| services | 编排进 pipeline；业务算法进插件 | 切换后旧服务仅作门面 | A |
| spiders | plugins/spiders；纯解析进 processors | 旧函数/类入口转发 | C |
| parsers、processors | plugins/processors | dispatch 兼容视图 | D |
| exporters | plugins/storage | jsonl/xlsx ID 与旧返回值适配 | B |
| pipelines/merge.py、export.py | 业务插件与存储插件 | 旧路径/签名保留 | D/B |
| storage | infra/storage | 先委托旧实现，后只留转发 | B |
| utils | infra | 同一实现、同一缓存/熔断状态 | E |
| security | plugin_manager/validator.py | 校验函数旧入口保留 | D |
| config/plugins.py | plugin_manager + 活动配置后端 | 原管理接口兼容 | D |
| plugins_ext | 显式适配或迁移到统一插件包 | 不可迁移项列清单，不静默丢弃 | D/插件作者 |

每个目录迁移退出条件：新模块单测通过、旧入口对照测试通过、生产调用方向单一、没有复制业务实现。V3.0 保留必要门面；后续版本经过调用方迁移、废弃通知及回归后才删除旧目录。

## 3. 架构与数据流

```text
控制台（三功能） / CLI / REST
  schema_editor → request_converter → TaskConfigDTO + OutputSpec
                            │
                      pipeline.engine
                            │
           registry + PipelineContext（冻结版本）
                 HTTP/cache/progress/assets/artifacts
```

```text
acquire: TaskConfigDTO → RawDataBatch[RawDataDTO.assets: MediaAsset[]]
  → raw_converter（引用与编码标准化，不丢资产）
  → processor.parse: RawDataBatch → RecordBatch（字段 + media_refs）
  → processor.post: RecordBatch → RecordBatch（合并/统计/可选媒体处理）
     ├── storage_converter → StoreRequest → storage → StoreReceipt[]
     └── view_converter(RecordBatch, receipts, OutputSpec, RunState)
              → PresentationRequest
              → presenter.execute → RenderedOutputDTO
                    ├── HTML：受管 UI resolver → UIComponentDTO[]
                    │         + ThemeSwitcher + templates → HTML 成品包
                    └── Text/Markdown/JSONL/CSV/PDF：直接成品文件

控制台输出定义 → 新 OutputSpec → 从已有记录重新呈现（不重新抓取）
```

**存储与呈现边界**：store 保存可复用的标准记录、媒体及检查点；present 制作面向人的报告/交换文件。jsonl_store 与 jsonl_presenter 可以共享底层序列化器，但写不同命名空间，分别记录回执，不能再次发起采集或覆盖同一文件。旧 JSONL/Excel 保持 data/output；新成品写 data/runs/<run_id>/outputs/<output_id>/。

view_converter 保留记录与媒体引用，不把 StoreReceipt 当数据本身。所有格式使用相同 PresentationRequest；无 HTML 输出时不加载 UI、模板或浏览器依赖。控制台只创建任务/输出配置、展示状态与下载链接，成品是可独立打开的文件或文件包。

迁移分两条不互调的路径：Wave 1 旧 CLI/API 继续走 V2.2 服务，新链路仅离线独立运行；Wave 2 单次切换后 CLI/API 进入 pipeline，旧服务改成调用新链路的门面。新链路可暂时调用尚未迁走的**叶子算法**，但不得调用再次进入 pipeline 的旧服务。

## 4. 数据契约、插件接口与上下文

### 4.1 类型清单（Wave 0 冻结）

默认使用标准库 dataclass + jsonschema 运行时验证，YAML 使用 PyYAML 安全加载，版本约束使用 packaging。具体兼容版本在 Gate 环境中验证并锁定，不同时维护 Pydantic 与 dataclass 两套模型。

| 类型 | 必要字段与约束 |
|---|---|
| TaskConfigDTO | task_id、dataset、source_id、profile_id、target_url、config_revision、只读配置快照；领域字段不作为通用必填 |
| TaskRunState | run_id、task_id、状态、retry_count、last_attempt_at、检查点；与不可变配置分开 |
| RawDataDTO | source_id、url、content_type、encoding、fetched_at、trace；content 或 raw_ref 二选一 |
| RawDataBatch | schema_version、task_id、items、分页完成标记、ErrorDTO 列表；允许合法空结果 |
| NormalizedRecordDTO | record_id、dataset、schema_id、fields、provenance；fields 只允许经 schema 校验的 JSON 值 |
| RecordBatch | schema_version、分组键、records、stats、来源完成状态、errors；统计不改变主数据类型 |
| StoreRequest | schema_version、dataset、run_id、target_id、格式标识、经校验的行/数据引用、幂等键、状态快照 |
| StoreReceipt | target_id、written/skipped/failed、records_written、output_ref、error；每个目标独立返回 |
| ViewModel | dataset、字段描述、受限数据引用/分页数据、统计、存储回执、运行状态 |
| UIComponentDTO | component_id、component_type、renderer_id、经校验的 payload、data_ref、事件声明 |
| StageResult / RunResult | 阶段状态、输入/输出计数、TaskRunState 列表、回执、组件引用、ErrorDTO 列表 |
| ErrorDTO | code、message、stage、task_id、source_id、可重试标记、脱敏诊断 |

共同要求：

- 每个边界验证结构、schema_id 和 schema_version；注解或 dataclass 本身不构成校验。
- 原始内容建议默认上限 10 MiB，超限流式落盘，只传受管 raw_ref；下载本身也要有限额，不能全部读入内存后再检查。
- 引用路径必须在允许目录内，不能让插件自由读取任意路径。外部引用通过受管服务解析。
- record_id 由数据集自然键规则生成；合并后的 ID 不简单沿用来源 ID，必须稳定且保留全部 provenance。
- 字段损失、未知版本、错误编码都有明确诊断；不以宽松 dict 掩盖跨阶段契约错误。

### 4.2 教育领域与旧格式

education profile 定义 university、college、category、year、name、title、研究方向等字段，任务与记录分别校验。保留 source_type、raw_ref、来源信息及旧 schema v1 的所有既有字段；旧字段以 V2.2 fixture 为准，不通过删字段实现“通用化”。

旧 CrawlTask 的执行状态映射到 TaskRunState，旧 `key()` 保持大学/学院/source；新内部检查点增加 dataset/year/config_revision，避免跨年份误判完成。旧 progress.json 仍由兼容投影生成。

旧引擎的 list[dict] 经 `LegacyRecordBatch` 专用适配进入记录侧，不能伪装成 HTML RawDataBatch。适配是迁移手段；最终五类采集插件必须能交付真正的原始批次与相应解析器。

### 4.3 统一基类及四类协议

以下为签名草图，实际实现由 Wave 0 冻结；示例不承诺此刻可导入运行。

```python
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")

class BasePlugin(ABC, Generic[InputT, OutputT]):
    name: str
    version: str
    plugin_type: str
    input_schema: str
    output_schema: str

    def setup(self, context) -> None:
        pass

    @abstractmethod
    def execute(self, data: InputT, context) -> OutputT:
        raise NotImplementedError

    def close(self) -> None:
        pass
```

| 插件协议 | 输入 → 输出 | 特殊约束 |
|---|---|---|
| SpiderPlugin | TaskConfigDTO → RawDataBatch | 抓取与页面发现，受管网络 |
| ParserPlugin（processor） | RawDataBatch → RecordBatch | 纯解析，不暗中补发网络请求 |
| RecordProcessorPlugin（processor） | RecordBatch → RecordBatch | 清洗、合并、统计；不得原地改共享批次 |
| StoragePlugin | StoreRequest → StoreReceipt | 显式副作用、幂等与回执 |
| UIPlugin | ViewModel → UIComponentDTO | 声明式描述，不返回任意 HTML |

四类插件是四种 kind；processor 内有两个输入阶段，不增加第五类。metadata 声明输入/输出 schema，类属性与 metadata 必须一致；配置预检检查链路类型兼容。

### 4.4 PipelineContext

上下文注入 http、cache、progress、受管存储、日志、允许路径、取消令牌、配置快照、registry_revision、任务/运行标识。每任务获取独立 HTTP 会话和插件实例；跨任务缓存、限速、按域熔断协调器使用显式共享且加锁的状态。不要以复制 PoliteSession 的方式重建另一套重试逻辑。

上下文对插件提供只读配置；共享状态通过受管接口操作。setup 失败、execute 异常或取消时均须在 finally 关闭已创建资源；重试是否创建新实例由生命周期约定确定。

## 5. 执行、并发和失败语义

### 5.1 调度与多源汇聚

继续采用 ThreadPoolExecutor，有界并发队列，不在本期加入通用 DAG。acquire 内允许列表发现、分页和详情 fan-out；设置最大页数、请求去重、每域并发与取消检查。发现链接属于采集职责，处理器只处理已取得的原始材料。

每个来源有独立 parse 链。完成后按 dataset + profile 分组规则汇聚；教育分组包含 university、college、year，不能跨学校/学院匹配。复用 V2.2 MergeService/匹配算法的 exact→strip→fuzzy 规则，并用既有 fixture 固定阈值与字段优先级。

配置明确所选来源、required 来源、缺失来源策略。默认不自动混入历史结果；如用户显式复用，必须匹配年份、领域 schema 和来源版本并记录出处。单来源运行允许合并器输出部分来源记录，不应永久等待未选来源。

### 5.2 重试与状态

任务状态：pending → running → succeeded/failed/partial/cancelled；命中有效检查点时 pending → skipped。旧接口分别映射回 V2.2 的 done/success 等既有枚举，不能把新枚举直接透传给旧前端。

HTTP 层负责单请求重试；管道默认不立即整任务重试，可显式恢复失败检查点。总尝试预算和重试责任须记录，禁止两层循环相乘。非幂等存储不得自动重放；取消应停止派发并在安全检查点退出，不伪称线程已被强杀。

### 5.3 存储与进度

- 同一 RecordBatch 向多个 storage 目标 fan-out，分别构造 StoreRequest。storage_converter 只负责格式契约；具体 SQL/Excel 语义在插件内。
- JSONL/Excel 使用受管临时文件与 replace；SQLite 使用事务和稳定键 UPSERT。SQLite 是本期 SQL 实现，其他数据库后续适配。
- 引擎通过 infra.progress 持续保存检查点；progress_store 插件负责可选进度快照导出。不能因禁用导出插件而失去运行状态管理。
- 必需来源或必需存储失败使 run failed；可选目标失败或允许的记录级拒收为 partial；完全成功为 succeeded。空结果是否有效由来源契约定义，不自动视为失败。
- present 可配置 required，默认 optional。数据成功、展示失败只重建展示，不重抓或重复写入成功目标。
- 不承诺跨文件/SQLite 的全局事务，报告哪些目标已成功；副作用有回执和幂等键。

### 5.4 文件与运行安全

原子 replace 防半文件，不防丢失更新。同规范化路径的锁必须跨存储实例共享，读改写整体加锁；保留 V2.2 cache/progress 锁和临时文件异常清理。

本期默认同一输出根目录只允许一个运行进程，内部支持四线程；CLI/API 第二个进程应在启动时被输出目录进程锁拒绝。四线程测试不能作为多进程共享写入的证据。Windows 上须测试锁释放、文件句柄关闭和 replace 失败。

## 6. 配置系统与旧七类插件迁移

### 6.1 映射

| 旧 kind | V3.0 归属 | 兼容处理 |
|---|---|---|
| source | 数据源/profile 配置 | describe 结果显式转为来源配置，任意可执行 source 需专用适配 |
| fetcher | spider | static_html 与旧 static_list 类名建立明确别名 |
| parser | processor.parse | 旧 raw_path/meta 接口经适配转换 |
| processor | processor.post | 旧 records/ctx 转换为批次协议 |
| exporter | storage | jsonl/xlsx ID 和返回形状兼容 |
| presenter | ui | 旧页面导航另保留；组件与整页不是同一概念 |
| utility | 受管基础服务或批准的 legacy 扩展 | 不允许开关关闭必要的校验/锁/检查点；不支持项列迁移错误 |

registry 是唯一能力表；旧函数表/类表从其派生兼容视图，不保留三套各自写入的真值。新增插件在管理清单可见不等于已被执行链调用，必须有执行集成测试。

### 6.2 自洽的静态垂直切片配置

以下两个文件是一组完整示例。研招来源应单独声明 yzw_api + yzw_major_parser 分支，不能把静态 HTML 交给研招 JSON 解析器。

```yaml
# config/pipeline.yaml（拟新增）
schema_version: 1
pipeline:
  id: education_default
  sources:
    source_a:
      acquire: static_fetch
      parse: [faculty_parse]
      required: true
  process:
    steps: [normalize_records, merge_records, statistics]
  store:
    targets:
      - instance: jsonl_output
        required: true
      - instance: excel_output
        required: false
  present:
    required: false
    components: [table_view, chart_view, card_view, filter_view]
```

```yaml
# config/plugins.yaml（拟新增）
schema_version: 1
instances:
  static_fetch:
    plugin: spider:static_html
    enabled: true
    params: {max_pages: 20}
  faculty_parse:
    plugin: processor:faculty_parser
    enabled: true
    params: {profile: education.tutor.v1}
  normalize_records:
    plugin: processor:normalize
    enabled: true
    params: {}
  merge_records:
    plugin: processor:education_merge
    enabled: true
    params: {group_by: [university, college, year]}
  statistics:
    plugin: processor:statistics
    enabled: true
    params: {group_by: [university]}
  jsonl_output:
    plugin: storage:jsonl_store
    enabled: true
    params: {format: legacy_education_v1, output_dir: data/output}
  excel_output:
    plugin: storage:xlsx_store
    enabled: true
    params: {format: legacy_education_v1, output_dir: data/output}
  table_view:
    plugin: ui:table_component
    enabled: true
    params: {}
  chart_view:
    plugin: ui:chart_component
    enabled: true
    params: {}
  card_view:
    plugin: ui:card_component
    enabled: true
    params: {}
  filter_view:
    plugin: ui:filter_component
    enabled: true
    params: {}
```

URL、学校、年份和选择器来自任务与已校验的教育配置快照，不重复硬编码到示例。JSONL/Excel 默认兼容旧格式；其他领域使用通用记录格式。SQLite 和进度快照用相同实例规则增加 sql_store、progress_store，必须纳入 Wave 1b 测试，不能因未列在默认链而漏交付。

### 6.3 真值、预检与迁移

1. 无新 YAML 时：加载旧 JSON 兼容模式；新 YAML 成对有效时：只以 YAML 为活动真值。只存在其中一个或配置损坏时拒绝启动，不能悄悄退回旧配置。
2. 元数据描述能力，plugins.yaml 描述实例，pipeline.yaml 描述执行顺序。预检拒绝未知 ID、重复实例、禁用却被引用、schema 不匹配和依赖缺失。
3. 旧权重按 `(weight, id)` 确定顺序；合法 null/禁用值按旧实际语义迁移。旧 merge 占位不应重复执行实际合并：迁移器保留旧“先合并后后处理”的行为，优化顺序须单独对照验证。
4. `scripts/migrate_config.py`（拟新增）：dry-run → 映射/冲突报告 → 用户确认 → 备份 → staging 校验 → 成对发布新配置。两个 YAML 不可能靠两次 replace 自动构成事务，需配置锁、版本清单及失败恢复；启动只接受完整版本。
5. 旧 API 写入活动后端，JSON 兼容表示只读生成，不再同时写两套。配置更新带 revision，旧 revision 冲突返回 409。
6. 运行开始冻结配置和 registry revision；更新只影响后续任务。不自动安装 metadata 的 dependencies。

## 7. 插件治理与安全

### 7.1 唯一元数据格式

```json
{
  "name": "static_html",
  "version": "1.0.0",
  "author": "maintainers",
  "plugin_type": "spider",
  "input_schema": "TaskConfigDTO.v1",
  "output_schema": "RawDataBatch.v1",
  "entry_point": "plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin",
  "dependencies": ["requests", "beautifulsoup4"],
  "min_core_version": "3.0.0",
  "config_schema": {
    "type": "object",
    "properties": {"max_pages": {"type": "integer", "minimum": 1}},
    "additionalProperties": false
  }
}
```

统一使用 metadata.json。旧 PLUGIN_META 仅作为迁移输入，用 AST 字面量提取，不再新建装饰器自动注册的第二真值。schema 名称从受控注册表解析，禁止 eval 任意字符串。

### 7.2 生命周期

扫描元数据（不 import）→ 结构/版本/依赖/包路径校验 → AST 静态策略审查 → 外部包管理员批准 → 对批准的包内容摘要校验 → 加载 → 基类和接口验证 → 发布 registry 快照。

未知包、名称冲突、版本不兼容、批准后内容变化均拒绝；禁用插件不得 import。支持按实例禁用，不能靠加载失败后静默跳过必需节点继续运行。

### 7.3 信任边界

AST 检查是静态审查门禁，**不是沙箱，也不是可信证明**。沿用 V2.2 对受限导入/调用的拒绝策略；新类接口校验与旧顶层函数校验分开适配，不直接套错检查器。底层可信文件实现通过 infra 使用，不能为让存储插件工作而全局取消限制。

上传只写待审区 `data/plugin_uploads/`，该目录不参与发现或静态文件服务。保留旧上传入口，但变更为“已接收、待批准”，不自动执行。后台管理需权限验证、请求防护、大小限制、路径约束、审计及版本留存。批准绑定完整包摘要；依赖和静态资源变更同样重新审查。

可信插件仍具有进程权限；未经批准代码不得在 API 进程运行。不可信插件隔离须单独提供操作系统级沙箱、文件/网络限制及资源限额，本期未交付前禁用该模式。

### 7.4 热更新

新版本形成新 registry 快照，仅影响后续运行。活动实例不得靠清空 sys.modules 强行替换；停用/删除有引用计数，活动版本完成后释放。依赖或原生库升级要求重启 worker。不得声称任意插件无重启热加载都安全。

抓取保持合规限速和站点访问边界，凭据使用受管引用且日志脱敏；不把反爬绕过或验证绕过列为平台功能。

## 8. UI 插件与接口

### 8.1 组件与 renderer

继续使用现有 Flask、原生前端和 Chart.js。UIPlugin 输出描述 DTO；table/chart/card/filter 具有独立参数 schema。运行描述保存到受管输出路径，前端通过授权 API 分页读取，避免将整个大数据集嵌入页面。

宿主提供 `registerRenderer(id, implementation)` 风格的通用注册入口；metadata 的 renderer manifest 声明版本、同源资源、payload schema 和能力。经过批准的资源由受管路由提供，新 renderer 只新增插件包/资源/配置，不改宿主 if/else。未知 renderer 显示占位和诊断。

配置切换已有组件与安装新渲染实现分别验收。不能用四个硬编码 renderer 冒充开放 UI 插件。第三方 JS 本质是可执行代码，须管理员批准；HTML 文本使用安全文本插入，启用 CSP，不接收任意脚本 URL/事件代码。

过滤器事件只传动作 ID 和经校验参数：查询过滤走授权查询接口；明确的“开始采集”才经 request_converter 创建 TaskConfigDTO。普通筛选不能意外触发重新抓取。

### 8.2 API 迁移表

| 端点 | 状态 | 行为 |
|---|---|---|
| GET /api/plugins | 已有，升级 | 四组清单 + 旧 kind 兼容表示；批准状态/版本可见 |
| POST /api/plugins/upload | 已有，行为收紧 | 待审，不执行，返回明确状态 |
| PUT/DELETE /api/plugins/<key> | 已有，升级 | 更新活动后端、版本冲突检查、活动引用保护 |
| POST /api/plugins/<key>/reload | 已有，升级 | 下次运行生效，不改变活动快照 |
| PUT /api/plugins/pipeline/<type> | 已有，兼容 | 旧权重映射为新有序步骤；不支持映射明确报错 |
| POST /api/pipeline/validate | 拟新增 | 配置/schema/引用/权限预检，不执行插件 |
| POST /api/pipeline/run | 拟新增 | 返回 run_id，受控后台运行 |
| GET /api/pipeline/runs/<id> | 拟新增 | 状态、阶段结果、存储回执 |
| GET /api/ui/components | 拟新增 | 已批准组件描述与布局 |
| PUT /api/ui/components/layout | 拟新增 | 校验后持久化布局和 revision |
| 旧 crawl/tutors/进度/失败接口 | 保留 | 教育兼容视图，响应字段及状态以旧测试固定 |

批准/版本激活端点由 Wave 0 同步冻结，必须具有管理员权限；不能只增加按钮却缺少后端审批状态机。

## 9. 开源参考与依赖选择

核验状态（2026-09-17 经浏览器直连确认）：Scrapy 官方文档（Item Pipeline，当前版本 2.19.0）、Crawlee Python 官方仓库（apify/crawlee-python）、Meltano 插件概念文档（extractors/loaders/mappers/utility 等类型、discoverable/custom 插件机制）均可访问且内容与下表相符。此核对仅确认入口与文档存在，未逐行核验当前源码、许可证文本或 API 细节；引入依赖前仍须按本节末尾要求记录仓库、版本与 LICENSE。WaterCrawl、Scrapling 及名称存疑项目仍未核验，实现不依赖名称含糊项目的未证实功能。

| 参考项目/资料 | 拟借鉴内容 | 本地落点与取舍 |
|---|---|---|
| [Scrapy Item Pipeline](https://docs.scrapy.org/en/latest/topics/item-pipeline.html)、[Feed Exports](https://docs.scrapy.org/en/latest/topics/feed-exports.html)、[仓库](https://github.com/scrapy/scrapy) | 有序处理、生命周期、多目标导出 | 轻量 engine/storage；Scrapy 接入仅可选适配器 |
| [Crawlee Python](https://crawlee.dev/python)、[仓库](https://github.com/apify/crawlee-python) | 请求队列、浏览器资源管理 | 有界采集/JS 插件；核对 Python API，不能照搬 JS 示例 |
| [Meltano 插件文档](https://docs.meltano.com/concepts/plugins/)、[仓库](https://github.com/meltano/meltano) | 声明式配置、插件元数据 | YAML 实例与执行配置分离，不引入整个框架 |
| [PyPA entry points](https://packaging.python.org/en/latest/specifications/entry-points/) | Python 包发现机制 | 后续补充安装包发现，首期 metadata 扫描即可 |
| [jsonschema](https://python-jsonschema.readthedocs.io/)、[PyYAML](https://pyyaml.org/wiki/PyYAMLDocumentation)、[packaging](https://packaging.pypa.io/) | 运行时校验、安全解析、版本约束 | Wave 0 核验并锁定依赖 |
| [Pydantic](https://docs.pydantic.dev/) | 类型模型与 schema | 比较参考；首期不额外引入第二套 DTO 模型 |
| [pluggy](https://pluggy.readthedocs.io/) | 显式接口与生命周期纪律 | 不引入依赖，借鉴接口约定 |
| WaterCrawl、Scrapling | 插件接口、自适应选择器方向 | 当前未核验唯一仓库和版本，不作为必需依赖 |
| OmniData、Universal Harvester、Perseus、scpun-crawl | 自动发现、合并、UI 分包、可视化编排方向 | 名称不足以确认项目身份，取得明确仓库后再评价 |

引入或复制代码前记录仓库、版本/commit、LICENSE、NOTICE、分发义务与兼容性；不笼统宣称“借鉴就没有许可证问题”。可选依赖缺失时在预检可见，已选必需插件必须阻止启动；运行时不得自动 pip install。

## 10. 实施波次、所有权与工作量

### 10.1 阶段安排

以下为工程估算，不是运行代理的耗时承诺。5–7 名熟悉代码的实施者，完整交付约 35–55 人日、3–5 周工作日跨度；顺序开发按人日估算。10 天可作为垂直切片目标，不作为完整重构保证。Gate 未通过、真实站点适配及测试债务需重新估算。

| 波次 | 前置 | 工作量 | 交付与退出条件 |
|---|---|---|---|
| Gate | V2.2 收尾 | 1–2 人日 | 基线报告、所有启动项通过 |
| Wave 0 | Gate | 3–4 人日 | 契约/配置/错误/生命周期冻结，mock 四阶段 smoke |
| Wave 1a | Wave 0 | 5–8 人日 | 静态来源→faculty_parser→JSONL→表格离线贯穿 |
| Wave 1b | Wave 1a | 16–24 人日 | 五采集、全部处理/存储/UI、治理/API 兼容及单测 |
| Wave 2 | 模块验收 | 6–10 人日 | 迁移、对照、并发、故障恢复、入口切换 |
| Wave 3 | Wave 2 | 4–7 人日 | 第二领域、零主干扩展、回滚、最终验收 |

### 10.2 A–G 文件所有权

此表用于后续分工，本次不执行重构。单人也可按同顺序实施。

| 角色 | 独占生产文件 | 测试/依赖 |
|---|---|---|
| A 主干与接口 | pipeline、services 兼容、main.py、api/server.py | test_pipeline_engine、test_api_v3；依赖 G/D/E |
| B 存储 | plugins/storage、infra/storage、旧 storage/导出门面、storage_converter | test_storage_plugins；复用 V2.2 原子 I/O |
| C 采集 | plugins/spiders、旧 spiders 适配、raw_converter | test_spider_plugins；与 D 冻结原始页面契约 |
| D 治理与处理 | plugin_manager、security 适配、config/plugins.py、plugins/processors、旧解析/合并门面 | test_plugin_loader/security、test_processor_plugins；先治理后业务 |
| E 基建与 UI | infra 的非 storage 文件、utils 兼容、plugins/ui、dashboard、request/view_converter | test_http_context、test_ui_plugins；先基建后前端 |
| F 质量 | tests/integration、共享 fixtures、浏览器测试、覆盖率配置 | 不与模块所有者争写独占单测 |
| G 契约与集成 | contracts、plugins/base.py、config YAML/schema、迁移/验收脚本、V3.0 文档 | Wave 0 后接口变更须登记；集成时接管共享文件 |

utils/progress.py 的对外门面由 E 写，B 只交付其存储依赖；旧 pipelines/merge.py 归 D，export.py 归 B。A 不直接改这些文件，避免原方案共享热点争写。

共享工作区不得各自 checkout；同一文件仅一个写入者。若改用独立分支/worktree，须另行确定集成方式。F 从 Wave 0 准备 fixture，不能到最后才发现契约无法测试。

### 10.3 分阶段执行清单

**Wave 0：冻结而非搭空壳**

- G 定义 §4 全部类型、schema ID、运行/兼容状态映射、实例配置、registry 和 context 协议。
- 冻结教育 schema v1 的 golden fixtures、来源分组/历史参与策略、UI manifest 和批准接口。
- 新建 `docs/V3.0/INTERFACES.md`、`tests/test_contracts.py`、`tests/test_wave0_contract.py`；不覆盖 V2.2 冻结记录。
- 新增 mock 插件贯穿四阶段，错误链在执行前拒绝。命令：`python -m pytest tests/test_contracts.py tests/test_wave0_contract.py -q`。
- 退出：契约/示例可验证，mock smoke 通过；回滚：旧入口未变，仅移除新配置引用。

**Wave 1a：第一条真实插件切片**

- D/E 先交付 registry 和 context，A 接入最小引擎；C/D 交付 static_html/faculty_parser，B/E 交付 JSONL/table。
- 静态列表/详情全部使用离线 fixture，经真实插件而非全链 mock；JSONL 对照旧结果，生成 views 描述。
- 命令：`python -m pytest tests/integration/test_static_slice.py -q`（拟新增）。
- 退出：四阶段及失败清理通过；回滚：旧 CLI/API 仍不变，新链仅独立测试。

**Wave 1b：补齐完整范围**

- C/D 补齐 AJAX、JS、PDF、YZW 原始批次与解析，合并/统计/去重；不得只包装旧已解析记录充当完成。
- B 补齐 Excel/SQLite/进度快照，验证同路径锁和幂等；E 完成四组件、manifest、过滤交互。
- D 完成版本/审批/热更新和七类适配；G 完成配置迁移 dry-run；A 完成新端点但先保持旧入口默认。
- 命令：`python -m pytest tests/test_spider_plugins.py tests/test_processor_plugins.py tests/test_storage_plugins.py tests/test_plugin_loader.py tests/test_ui_plugins.py -q`（拟新增）。
- 退出：每插件有输入/输出/失败单测，配置预检覆盖所有默认引用；回滚：停止启用未验收插件，不覆盖旧数据。

**Wave 2：按依赖集成并切换**

- 集成顺序：契约→基建/治理→采集/处理/存储/UI→引擎/API→测试；不是机械合并字母顺序。
- 临时目录运行旧/新链路对照，稳定字段精确相同，时间戳等只按已列白名单比较；Excel 比较单元格/列，不比较 ZIP 二进制。
- 配置迁移冲突必须解决；备份后切换，禁止运行失败时自动转旧链重复副作用。
- 命令：`python -m pytest tests/integration/test_legacy_compat.py tests/integration/test_concurrency.py tests/integration/test_recovery.py -q`（拟新增）。
- 退出：兼容/并发/恢复通过，用户确认激活；回滚：固定版本及配置备份，见 §11.3。

**Wave 3：验收而非继续扩范围**

- 使用本地 fixture 建立无学校/导师字段的第二领域（如公开文章目录），贯穿采集/处理/存储/展示。
- 从冻结核心基线新增示例插件与 renderer；仅插件包/资源/配置有 diff，核心与宿主无改动。
- 跑全量测试、覆盖率、浏览器验证和回滚演练，生成 `docs/V3.0/ACCEPTANCE.md`。
- 退出：§11 全部取得证据；真实网络未跑则明确标记，不混同离线验收。

## 11. 验收矩阵、命令与回滚

### 11.1 必须留下的证据

| 范围 | 验收内容 | 通过标准 |
|---|---|---|
| 旧 CLI/函数 | 全参数、旧返回值、source A/B、resume/retry/force | 与 V2.2 golden fixtures/契约一致 |
| 数据兼容 | school_data、JSONL、Excel、进度、失败记录 | 字段/列/路径/状态投影不丢失 |
| 通用契约 | 非法 DTO/schema/链、空数据、二进制引用 | 明确诊断，执行前或边界拒绝 |
| 采集处理 | 五引擎、分页终止、详情 fan-out、三阶合并 | 来源与年份隔离，部分失败可解释 |
| 存储 | JSONL/Excel/SQLite/进度、故障注入、重跑 | 无半文件/重复副作用，回执与真实输出一致 |
| 并发 | 四线程、多实例同路径读改写 | 无丢失更新；第二进程同输出根被拒绝 |
| 治理 | metadata-only 发现、禁用不加载、冲突/版本/批准 | 未批准不执行，批准后内容变更拒绝 |
| 热更新 | 活动任务与新任务并行 | 活动快照不变，新任务使用新版本 |
| UI | 四组件切换、过滤、分页、刷新、未知类型 | 浏览器可见正确反馈，无任意 HTML 注入 |
| 扩展性 | 非教育数据集、新插件、新 renderer | 只增插件/配置/资源，核心和宿主零 diff |
| 回滚 | 配置恢复、固定旧版本、恢复运行 | 旧数据可读，不产生同任务自动双跑 |

### 11.2 验收命令约定

以下是未来实施时的验收命令，**本次文档修改没有运行这些业务测试**。新增测试文件和脚本必须先在对应 Wave 创建。所有自动测试使用临时根目录与模拟网络，不污染 data/。

```bash
python -m pytest tests/ -q
python -m pytest tests/ --cov=pipeline --cov=contracts --cov=converters --cov=plugins --cov=plugin_manager --cov=infra --cov-report=term-missing --cov-fail-under=80
```

整体覆盖率至少 80%，关键模块逐个报告；不得排除核心实现来抬高分数。可选浏览器/PDF 依赖须安装于专门测试环境，其跳过项单独报告，不能拿大量 skip 当功能已验收。

已有配置校验函数需**实际调用并检查 errors**，不是仅 import 后打印“通过”：

```python
from config.loader import load_schools_config
from config.validator import validate_all_configs

result = validate_all_configs(load_schools_config())
for error in result["errors"]:
    print(error)
raise SystemExit(1 if result["errors"] else 0)
```

CLI 冒烟使用独立子进程和临时工作目录，安装/路径按 Gate 环境固定；旧参数清单至少包含 school/category/source/year/workers/force/resume/retry-failed/delay/max-retries/timeout、缓存、冷却、raw-dir、熔断相关参数，最终以 V2.2 `--help` 快照穷举对照。

Playwright 测试启动临时 Flask 实例、注入 fixture 数据，验证四组件与完整事件链，不只测试 Python DTO。真实学校采集只作可选手工验证，先授权目标及隔离输出，记录认证/网络限制，不作为唯一验收依据。

### 11.3 发布与回滚步骤

1. 记录并保存可恢复的 V2.2 版本；版本/tag 操作由维护者明确执行，不自动提交。
2. 备份旧配置和受影响数据。新旧对照使用不同输出根，生产默认路径直到切换前不改。
3. 运行迁移 dry-run，审阅无法映射插件、排序、schema 和路径冲突；无冲突后成对发布配置。
4. 停止新任务派发，等待活动任务结束或安全取消，获取输出根锁后激活新版本；保留旧数据读取能力。
5. 如需回滚，先停止并释放新运行，恢复完整旧配置版本及兼容数据快照，再恢复旧代码；不能只切代码留下新 YAML。
6. 核对旧链路及输出，记录受影响 run_id、已成功副作用和恢复结果；不得自动重复执行已写入目标。

最终验收报告包括：基线/发布版本、环境、每项命令与结果、实际覆盖率、跳过项、配置映射报告、输出对照、浏览器记录、回滚演练。V2.2 文档与验收记录保留。

## 12. 后续路线图

完成上述验收后，再单独评估：插件市场、可视化编排、Scrapy/Crawlee 可选适配器、其他 SQL 数据库、非 Python 插件、LLM 解析、分布式队列、不可信插件隔离、通知信号扩展。每项重新定义信任边界、依赖和验收，不以本期“四类插件已建立”代替这些能力的实现。
