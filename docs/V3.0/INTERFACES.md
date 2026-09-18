# V3.0 接口契约文档 (INTERFACES.md)

> 冻结版本：v3.0.0
> 生成日期：2026-09-18
> 基准：V2.2 冻结契约 + V3.0 计划书 §4
> 唯一真相源：本文件与 contracts/ 代码必须一致，以代码为准

---

## 1. 类型定义总览

| 类型 | 模块 | Schema ID | 说明 |
|------|------|-----------|------|
| MediaAsset | contracts.asset | MediaAsset.v1 | 媒体资产真值 |
| AssetRef | contracts.asset | AssetRef.v1 | 落盘资产引用 |
| TaskConfigDTO | contracts.task | TaskConfigDTO.v1 | 任务不可变配置 |
| TaskRunState | contracts.task | TaskRunState.v1 | 任务可变运行状态 |
| OutputSpec | contracts.task | OutputSpec.v1 | 输出产品规格 |
| RawDataDTO | contracts.raw | RawDataDTO.v1 | 单条原始材料 |
| RawDataBatch | contracts.raw | RawDataBatch.v1 | 原始材料批次 |
| NormalizedRecordDTO | contracts.record | NormalizedRecordDTO.v1 | 归一化记录 |
| RecordBatch | contracts.record | RecordBatch.v1 | 记录批次 |
| PresentationRequest | contracts.output | PresentationRequest.v1 | 呈现请求 |
| RenderedOutputDTO | contracts.output | RenderedOutputDTO.v1 | 呈现产出 |
| ViewModel | contracts.ui | ViewModel.v1 | UI 视图模型 |
| UIComponentDTO | contracts.ui | UIComponentDTO.v1 | UI 组件描述 |
| StoreRequest | contracts.result | StoreRequest.v1 | 存储请求 |
| StoreReceipt | contracts.result | StoreReceipt.v1 | 存储回执 |
| StageResult | contracts.result | StageResult.v1 | 阶段结果 |
| RunResult | contracts.result | RunResult.v1 | 运行聚合结果 |
| ErrorDTO | contracts.result | ErrorDTO.v1 | 标准错误 |

教育扩展（contracts.profiles.education）：
- education.tutor.v1 (TUTOR_V1_SCHEMA)
- education.major.v1 (MAJOR_V1_SCHEMA)

---

## 2. 核心类型字段表

### 2.1 MediaAsset (contracts.asset)

| 字段 | 类型 | 必填 | 约束 | 说明 |
|------|------|------|------|------|
| media_type | str | ✓ | enum: text/image/audio/video/document/binary | 媒体大类 |
| mime_type | str | ✓ | IANA MIME | 精确 MIME |
| data | bytes | ✗ | 与 url 二选一 | 内存二进制 (≤10MiB) |
| url | str | ✗ | 与 data 二选一 | 落盘后的访问 URL |
| metadata | dict | ✗ | - | 扩展元数据 |
| size | int | ✗ | ≥0 | 字节数 |
| sha256 | str | ✗ | ^[a-f0-9]{64}$ | 完整性校验 |
| fetched_at | str | ✓ | ISO 8601 | 抓取时间 |

> **红线**：data 与 url 互斥且必填其一；超 10 MiB 必须落盘转 AssetRef。

### 2.2 TaskConfigDTO (contracts.task)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | str | ✓ | 32位 hex |
| dataset | str | ✓ | 数据集标识 |
| source_id | str | ✓ | 来源标识 |
| profile_id | str | ✓ | 领域画像标识 |
| target_url | str | ✓ | 入口 URL |
| config_revision | int | ✓ | 配置快照版本 |
| config_snapshot | dict | ✓ | 只读校验后配置 |
| created_at | str | ✓ | ISO 8601 |

### 2.3 TaskRunState (contracts.task)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| run_id | str | ✓ | 32位 hex |
| task_id | str | ✓ | 关联 TaskConfigDTO |
| status | str | ✓ | pending/running/succeeded/failed/partial/cancelled/skipped |
| retry_count | int | | 重试次数 |
| last_attempt_at | str? | | ISO 8601 |
| checkpoint | dict | | 插件自定义恢复数据 |
| started_at | str | ✓ | ISO 8601 |
| completed_at | str? | | ISO 8601 |

> **V2.2 映射**：succeeded→done, failed→failed, partial→partial, cancelled→cancelled, skipped→skipped

### 2.4 RawDataDTO (contracts.raw)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source_id | str | ✓ | 来源标识 |
| url | str | ✓ | 源 URL |
| content_type | str | ✓ | MIME |
| encoding | str | ✓ | 编码 |
| fetched_at | str | ✓ | ISO 8601 |
| trace | dict | | 请求/响应元数据 |
| assets | list[MediaAsset] | ✓ | **资产真值** |
| content | str? | ✗ | **Legacy only** 与 raw_ref 二选一 |
| raw_ref | str? | ✗ | **Legacy only** 与 content 二选一 |

> **红线**：新插件必须填充 assets；content/raw_ref 仅供 legacy 适配，raw_converter 负责归一。

### 2.5 RawDataBatch (contracts.raw)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| schema_version | str | ✓ | "1" |
| task_id | str | ✓ | 32位 hex |
| items | list[RawDataDTO] | ✓ | 可为空（合法空结果） |
| pagination_complete | bool | ✓ | 分页是否结束 |
| next_page_token | str? | | 继续翻页凭证 |
| errors | list[ErrorDTO] | | 采集期错误 |
| fetched_at | str | ✓ | ISO 8601 |

### 2.6 NormalizedRecordDTO (contracts.record)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| record_id | str | ✓ | 32位 hex，自然键生成 |
| dataset | str | ✓ | 数据集 |
| schema_id | str | ✓ | 引用注册表 schema |
| fields | dict | ✓ | 仅含 JSON 值，已校验 |
| provenance | dict | | source_id, url, fetched_at 等 |
| media_refs | list[str] | | AssetRef 路径或 RawDataDTO 索引 |
| created_at | str | ✓ | ISO 8601 |

### 2.7 RecordBatch (contracts.record)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| schema_version | str | ✓ | "1" |
| group_key | tuple[str] | | 分组键 (university, college, year...) |
| records | list[NormalizedRecordDTO] | ✓ | |
| stats | dict | | 统计信息 |
| source_completion | dict[str,bool] | | source_id → 完成标记 |
| errors | list[ErrorDTO] | | 处理期错误 |

### 2.8 PresentationRequest (contracts.output)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| request_id | str | ✓ | 32位 hex |
| dataset | str | ✓ | |
| schema_id | str | ✓ | |
| output_spec | dict | ✓ | OutputSpec 字典 |
| records | list[dict] | | 简化记录视图 |
| media_assets | list[MediaAsset] | | 引用的媒体资产 |
| store_receipts | list[dict] | | StoreReceipt 字典 |
| run_state | dict | | TaskRunState 字典 |
| stats | dict | | 聚合统计 |
| created_at | str | ✓ | ISO 8601 |

### 2.9 RenderedOutputDTO (contracts.output)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| output_id | str | ✓ | 32位 hex |
| output_format | str | ✓ | html/text/markdown/jsonl/csv/pdf |
| path | str | ✓ | 输出文件/目录绝对路径 |
| media_assets | list[MediaAsset] | | 嵌入输出的媒体 |
| metadata | dict | | 页数、大小等 |
| created_at | str | ✓ | ISO 8601 |

### 2.10 ViewModel (contracts.ui)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| dataset | str | ✓ | |
| schema_id | str | ✓ | |
| field_descriptions | dict | | 字段→{type,label,format} |
| data_ref | str | | 分页数据端点引用 |
| page | int | | 当前页 |
| page_size | int | | 页大小 |
| total_count | int | | 总记录数 |
| stats | dict | | 统计 |
| store_receipts | list[dict] | | 存储回执 |
| run_state | dict | | 运行状态 |
| created_at | str | ✓ | ISO 8601 |

### 2.11 UIComponentDTO (contracts.ui)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| component_id | str | ✓ | |
| component_type | str | ✓ | table/chart/card/filter |
| renderer_id | str | ✓ | 已批准渲染器 ID |
| payload | dict | | 经 schema 校验的参数 |
| data_ref | str | | 组件专用数据引用 |
| events | list[dict] | | 声明式事件处理 |
| created_at | str | ✓ | ISO 8601 |

### 2.12 StoreRequest (contracts.result)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| schema_version | str | ✓ | "1" |
| dataset | str | ✓ | |
| run_id | str | ✓ | |
| target_id | str | ✓ | 存储插件实例 ID |
| format_id | str | ✓ | 格式标识 |
| data_refs | list[str] | | 数据引用 |
| idempotency_key | str | ✓ | 幂等键 |
| state_snapshot | dict | | TaskRunState 快照 |
| created_at | str | ✓ | ISO 8601 |

### 2.13 StoreReceipt (contracts.result)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| target_id | str | ✓ | |
| written | int | ✓ | 成功写入 |
| skipped | int | ✓ | 跳过（幂等/已存在） |
| failed | int | ✓ | 失败 |
| records_written | int | ✓ | 记录条数 |
| output_ref | str | ✓ | 输出路径/标识 |
| error | ErrorDTO? | | 失败诊断 |
| created_at | str | ✓ | ISO 8601 |

### 2.14 ErrorDTO (contracts.result)

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | str | ✓ | 错误码（见下表） |
| message | str | ✓ | 脱敏人类可读 |
| stage | str | ✓ | acquire/process/store/present |
| task_id | str | | |
| source_id | str | | |
| retryable | bool | | 是否可重试 |
| diagnostics | dict | | 脱敏调试信息 |

**标准错误码表**：

| 代码 | 可重试 | 说明 |
|------|--------|------|
| HTTP_TIMEOUT | ✓ | 请求超时 |
| HTTP_CONNECTION_ERROR | ✓ | 连接错误 |
| HTTP_BLOCKED | ✗ | 反爬冷却/熔断 |
| HTTP_DNS_ERROR | ✓ | DNS 解析失败 |
| HTTP_MAX_RETRIES | ✓ | 达到最大重试 |
| PARSE_FAILED | ✗ | 解析失败 |
| PARSE_SELECTOR_MISSING | ✗ | 选择器缺失 |
| PARSE_ENCODING_ERROR | ✗ | 编码错误 |
| VALIDATION_SCHEMA_MISMATCH | ✗ | Schema 不匹配 |
| VALIDATION_MISSING_REQUIRED | ✗ | 缺必填字段 |
| VALIDATION_UNKNOWN_SCHEMA_ID | ✗ | 未知 schema_id |
| STORAGE_WRITE_FAILED | ✓ | 写入失败 |
| STORAGE_LOCK_TIMEOUT | ✓ | 锁超时 |
| STORAGE_IDEMPOTENCY_CONFLICT | ✗ | 幂等冲突 |
| RENDER_TEMPLATE_MISSING | ✗ | 模板缺失 |
| RENDER_ASSET_MISSING | ✗ | 资产缺失 |
| PIPELINE_CANCELLED | ✗ | 取消 |
| PIPELINE_CONFIG_INVALID | ✗ | 配置无效 |
| PIPELINE_DEPENDENCY_MISSING | ✗ | 依赖缺失 |
| PLUGIN_SETUP_FAILED | ✗ | 插件初始化失败 |
| PLUGIN_EXECUTE_FAILED | ✓ | 插件执行失败 |
| PLUGIN_DEPENDENCY_MISSING | ✗ | 插件依赖缺失 |

---

## 3. 五组插件协议签名

### 3.1 统一基类 (plugins.base.BasePlugin)

```python
class BasePlugin(ABC, Generic[InputT, OutputT]):
    name: str
    version: str
    plugin_type: str  # spider/processor/storage/presenter/ui
    input_schema: str  # JSON Schema ID
    output_schema: str  # JSON Schema ID

    def setup(self, context: PluginContext) -> None: ...
    @abstractmethod
    def execute(self, data: InputT, context: PluginContext) -> OutputT: ...
    def close(self) -> None: ...
```

### 3.2 SpiderPlugin

```python
class SpiderPlugin(BasePlugin[TaskConfigDTO, RawDataBatch]):
    plugin_type = "spider"
    input_schema = "TaskConfigDTO.v1"
    output_schema = "RawDataBatch.v1"

    # execute(task_config, context) -> RawDataBatch
    # 职责：列表发现、分页、详情 fan-out、受管网络
    # 约束：不得绕过 context.http；不得写业务解析逻辑
```

### 3.3 ParserPlugin (processor.parse 阶段)

```python
class ParserPlugin(BasePlugin[RawDataBatch, RecordBatch]):
    plugin_type = "processor"
    input_schema = "RawDataBatch.v1"
    output_schema = "RecordBatch.v1"

    # execute(raw_batch, context) -> RecordBatch
    # 职责：纯解析，字段抽取，media_refs 建立
    # 约束：不得暗中发起网络请求
```

### 3.4 RecordProcessorPlugin (processor.post 阶段)

```python
class RecordProcessorPlugin(BasePlugin[RecordBatch, RecordBatch]):
    plugin_type = "processor"
    input_schema = "RecordBatch.v1"
    output_schema = "RecordBatch.v1"

    # execute(record_batch, context) -> RecordBatch
    # 职责：清洗、合并、统计、可选媒体处理
    # 约束：不得原地修改共享批次；返回新批次
```

### 3.5 StoragePlugin

```python
class StoragePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    plugin_type = "storage"
    input_schema = "StoreRequest.v1"
    output_schema = "StoreReceipt.v1"

    # execute(store_request, context) -> StoreReceipt
    # 职责：显式副作用、幂等、原子写入、回执
```

### 3.6 PresenterPlugin (plugins.base.PresenterPlugin)

```python
class PresenterPlugin(BasePlugin):
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def execute(self, request: PresentationRequest, context) -> RenderedOutputDTO:
        # 抽象方法，必须实现
        ...

    def render(self, request: PresentationRequest, context) -> RenderedOutputDTO | str:
        # 可选钩子：模板渲染分离时使用
        # 默认 execute() 调用 render() 并包装
        raise NotImplementedError
```

> **设计决议**：PresenterPlugin 继承 BasePlugin，execute() 为抽象方法；
> 子类可提供非抽象 render() 辅助钩子，默认 execute() 调用 render()。
> 保证任何具体 Presenter 只需实现一个入口即可实例化。

### 3.7 UIPlugin

```python
class UIPlugin(BasePlugin[ViewModel, UIComponentDTO]):
    plugin_type = "ui"
    input_schema = "ViewModel.v1"
    output_schema = "UIComponentDTO.v1"

    # execute(view_model, context) -> UIComponentDTO
    # 职责：声明式组件描述，不返回任意 HTML
```

---

## 4. metadata.json 格式

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
  },
  "license": "MIT"
}
```

**必须字段**：name, version, author, plugin_type, input_schema, output_schema, entry_point
**license 字段**：GPL 类依赖声明时加载告警（AGPL/GPL/LGPL）
**config_schema**：additionalProperties=false 收紧参数

---

## 5. PipelineContext 注入项

| 名称 | 类型 | 说明 |
|------|------|------|
| http | PoliteSession | 受管 HTTP 会话（限速/重试/冷却/熔断） |
| cache | CrawlCache | 缓存（read_many, get_hit_rate） |
| progress | ProgressTracker | 进度跟踪（update_school_status 等） |
| storage | ManagedStorage | 受管存储（原子 I/O、媒体引用） |
| logger | logging.Logger | 标准日志 |
| allowed_paths | list[str] | 插件可读写的允许目录 |
| cancel_token | threading.Event | 取消令牌 |
| config_snapshot | dict | 只读配置快照 |
| registry_revision | int | 注册表版本 |
| task_id | str | 当前任务 ID |
| run_id | str | 当前运行 ID |

> **红线**：每任务独立 HTTP 会话和插件实例；跨任务共享状态须显式加锁；不得复制 PoliteSession 重建重试逻辑。

---

## 6. 状态机映射 (V3.0 → V2.2)

| V3.0 TaskRunState.status | V2.2 CrawlResult.status / 兼容枚举 |
|--------------------------|-----------------------------------|
| pending | pending |
| running | running |
| succeeded | done / success |
| failed | failed |
| partial | partial |
| cancelled | cancelled |
| skipped | skipped |

旧 API 响应必须映射回 V2.2 枚举，不能直接透传新枚举。

---

## 7. Schema ID 注册表

| Schema ID | 类型 | 版本 | 备注 |
|-----------|------|------|------|
| TaskConfigDTO.v1 | TaskConfigDTO | 1 | |
| TaskRunState.v1 | TaskRunState | 1 | |
| OutputSpec.v1 | OutputSpec | 1 | |
| RawDataDTO.v1 | RawDataDTO | 1 | |
| RawDataBatch.v1 | RawDataBatch | 1 | |
| NormalizedRecordDTO.v1 | NormalizedRecordDTO | 1 | |
| RecordBatch.v1 | RecordBatch | 1 | |
| PresentationRequest.v1 | PresentationRequest | 1 | |
| RenderedOutputDTO.v1 | RenderedOutputDTO | 1 | |
| ViewModel.v1 | ViewModel | 1 | |
| UIComponentDTO.v1 | UIComponentDTO | 1 | |
| StoreRequest.v1 | StoreRequest | 1 | |
| StoreReceipt.v1 | StoreReceipt | 1 | |
| StageResult.v1 | StageResult | 1 | |
| RunResult.v1 | RunResult | 1 | |
| ErrorDTO.v1 | ErrorDTO | 1 | |
| MediaAsset.v1 | MediaAsset | 1 | |
| AssetRef.v1 | AssetRef | 1 | |
| education.tutor.v1 | EducationTutorFields | 1 | 领域扩展 |
| education.major.v1 | EducationMajorFields | 1 | 领域扩展 |

新领域 schema 随插件包声明并注册，不修改核心 contracts/。

---

## 8. API 端点表 (计划书 §8.2)

| 端点 | 状态 | 行为 |
|------|------|------|
| GET /api/plugins | 升级 | 四组清单 + 旧 kind 兼容；批准状态/版本可见 |
| POST /api/plugins/upload | 收紧 | 待审区，不执行，返回明确状态 |
| PUT/DELETE /api/plugins/<key> | 升级 | 更新活动后端、版本冲突检查、活动引用保护 |
| POST /api/plugins/<key>/reload | 升级 | 下次运行生效，不改变活动快照 |
| PUT /api/plugins/pipeline/<type> | 兼容 | 旧权重→新有序步骤；映射失败报错 |
| POST /api/pipeline/validate | 新增 | 配置/schema/引用/权限预检，不执行 |
| POST /api/pipeline/run | 新增 | 返回 run_id，受控后台运行 |
| GET /api/pipeline/runs/<id> | 新增 | 状态、阶段结果、存储回执 |
| GET /api/ui/components | 新增 | 已批准组件描述与布局 |
| PUT /api/ui/components/layout | 新增 | 校验后持久化布局和 revision |
| 旧 crawl/tutors/进度/失败接口 | 保留 | 教育兼容视图，字段/状态以旧测试固定 |

批准/版本激活端点需管理员权限；不得只增按钮缺后端审批状态机。

---

## 9. 配置文件 Schema

### 9.1 config/pipeline.yaml

```yaml
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

### 9.2 config/plugins.yaml

```yaml
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
  # ... 其他实例
```

---

## 10. 兼容性承诺

1. **旧 CLI/函数签名**：全参数、旧返回值、source A/B、resume/retry/force 保持 V2.2 语义
2. **数据兼容**：school_data、JSONL、Excel、进度、失败记录 — 字段/列/路径/状态投影不丢失
3. **旧进度投影**：progress.json 仍由兼容层生成
4. **旧 key()**：大学|学院|source 保持；新增 dataset/year/config_revision 避免跨年误判
5. **旧熔断状态**：PoliteSession 唯一熔断器；CircuitBreaker 仅作兼容适配

---

## 11. 验收命令

```bash
# 契约测试
python -m pytest tests/test_contracts.py tests/test_wave0_contract.py -q

# 配置迁移 dry-run
python scripts/migrate_config.py --dry-run --report /tmp/migrate_report.txt

# 配置校验
python -c "
from config.loader import load_schools_config
from config.validator import validate_all_configs
r = validate_all_configs(load_schools_config())
print(len(r['errors']))
"
```

**退出条件**：契约测试全绿；INTERFACES.md 覆盖上述全部内容且与代码一致；至少 3 个其他窗口的仲裁提案已裁决并回写。

---

## 12. 变更记录

| 版本 | 日期 | 变更 | 操作人 |
|------|------|------|--------|
| 3.0.0 | 2026-09-18 | 初始冻结 | W1 |
| 3.0.1 | 2026-09-20 | 契约验收复核：迁移器映射表对齐示例 YAML 实例名（纯脚本，不改契约）；裁决仲裁提案 #1–#4 | W1 |

---

*本文件由 W1 窗口创建并维护。任何窗口认为需要改动契约，不得直接改共享文件，须在 progress.md "待 W1 仲裁" 区登记提案 → W1 裁决后更新本文件 → 全体按新契约执行。*