# 02 - 契约速查

> **状态**：初稿
> **读者**：所有插件开发者
> **权威来源**：`docs/V3.0/INTERFACES.md`（本篇是摘编，有歧义时以 INTERFACES.md 为准）

## 核心 DTO 表

| DTO | Schema ID | 所在模块 | 用途 |
|---|---|---|---|
| TaskConfigDTO | TaskConfigDTO.v1 | contracts.task | 任务不可变配置 |
| TaskRunState | TaskRunState.v1 | contracts.task | 任务可变运行状态 |
| OutputSpec | OutputSpec.v1 | contracts.task | 输出产品规格 |
| RawDataDTO | RawDataDTO.v1 | contracts.raw | 单条原始材料 |
| RawDataBatch | RawDataBatch.v1 | contracts.raw | 原始材料批次 |
| NormalizedRecordDTO | NormalizedRecordDTO.v1 | contracts.record | 归一化记录 |
| RecordBatch | RecordBatch.v1 | contracts.record | 记录批次 |
| PresentationRequest | PresentationRequest.v1 | contracts.output | 呈现请求 |
| RenderedOutputDTO | RenderedOutputDTO.v1 | contracts.output | 呈现产出 |
| ViewModel | ViewModel.v1 | contracts.ui | UI 视图模型 |
| UIComponentDTO | UIComponentDTO.v1 | contracts.ui | UI 组件描述 |
| StoreRequest | StoreRequest.v1 | contracts.result | 存储请求 |
| StoreReceipt | StoreReceipt.v1 | contracts.result | 存储回执 |
| ErrorDTO | ErrorDTO.v1 | contracts.result | 标准错误 |
| MediaAsset | MediaAsset.v1 | contracts.asset | 媒体资产真值 |
| AssetRef | AssetRef.v1 | contracts.asset | 落盘资产引用 |

## 五组插件输入/输出

| 插件类型 | input_schema | output_schema | 基类 |
|---|---|---|---|
| spider | TaskConfigDTO.v1 | RawDataBatch.v1 | SpiderPlugin |
| processor (parse) | RawDataBatch.v1 | RecordBatch.v1 | ParserPlugin |
| processor (post) | RecordBatch.v1 | RecordBatch.v1 | RecordProcessorPlugin |
| storage | StoreRequest.v1 | StoreReceipt.v1 | StoragePlugin |
| presenter | PresentationRequest.v1 | RenderedOutputDTO.v1 | PresenterPlugin |
| ui | ViewModel.v1 | UIComponentDTO.v1 | UIPlugin |

## 标准错误码

| 错误码 | 阶段 | 可重试 |
|---|---|---|
| HTTP_TIMEOUT | acquire | 是 |
| HTTP_CONNECTION_ERROR | acquire | 是 |
| HTTP_BLOCKED | acquire | 否 |
| HTTP_DNS_ERROR | acquire | 是 |
| HTTP_MAX_RETRIES | acquire | 是 |
| PARSE_FAILED | process | 否 |
| PARSE_SELECTOR_MISSING | process | 否 |
| PARSE_ENCODING_ERROR | process | 否 |
| VALIDATION_SCHEMA_MISMATCH | process | 否 |
| VALIDATION_MISSING_REQUIRED | process | 否 |
| STORAGE_WRITE_FAILED | store | 是 |
| STORAGE_LOCK_TIMEOUT | store | 是 |
| STORAGE_IDEMPOTENCY_CONFLICT | store | 否 |
| RENDER_TEMPLATE_MISSING | present | 否 |
| RENDER_ASSET_MISSING | present | 否 |
| PIPELINE_CANCELLED | — | 否 |
| PIPELINE_CONFIG_INVALID | — | 否 |
| PIPELINE_DEPENDENCY_MISSING | — | 否 |
| PLUGIN_SETUP_FAILED | — | 否 |
| PLUGIN_EXECUTE_FAILED | — | 是 |
| PLUGIN_DEPENDENCY_MISSING | — | 否 |

## 红线速记

- `RawDataDTO.assets` 是资产真值，新插件必须填充；`content`/`raw_ref` 仅 legacy 兼容
- `MediaAsset.data` 与 `url` 互斥且必填其一；超 10 MiB 必须落盘转 AssetRef
- 一切落盘走 `tempfile.mkstemp` + `os.replace`（原子写入）
- 外部插件必须过 AST 黑名单；上传只进待审区 `data/plugin_uploads/`
- 跨任务共享状态须显式加锁
