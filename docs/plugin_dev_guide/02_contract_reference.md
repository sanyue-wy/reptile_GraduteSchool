# 02 - 契约速查

> **版本**：v3.0.0
> **状态**：已定稿
> **读者**：所有插件开发者
> **权威来源**：`docs/V3.0/INTERFACES.md`（本篇是摘编，有歧义时以 INTERFACES.md 为准）

## 五分钟最小运行示例

```python
# 快速验证 DTO 签名
from contracts.task import TaskConfigDTO
from contracts.raw import RawDataBatch

# 创建最小合法 TaskConfigDTO
config = TaskConfigDTO(
    task_id="a" * 32,
    dataset="demo",
    source_id="static_html",
    profile_id="default",
    target_url="https://example.com/list",
    config_revision=1,
    config_snapshot={"max_pages": 1},
    created_at="2026-09-20T00:00:00+00:00",
)

# 创建最小合法 RawDataBatch
batch = RawDataBatch(
    schema_version="1",
    task_id=config.task_id,
    items=[],
    pagination_complete=True,
    fetched_at="2026-09-20T00:00:00+00:00",
)
print(f"✓ TaskConfigDTO 输出: {config.dataset}")
print(f"✓ RawDataBatch 输出: {len(batch.items)} 条记录")
```

运行：
> ⚠️ **2026-10-01（G4）更正**：原文写作 `python docs/plugin_dev_guide/02_contract_reference.py`，
> 但该 `.py` 文件**从未创建**，照抄会得到 `can't open file ... No such file or directory`。
> 本节代码片段目前**无配套可运行脚本**——请自行粘贴到临时 `.py` 文件中执行。
> 若要本仓库提供正式示例，请先创建该脚本或改指向已有示例（如 `scaffolds/` 下的生成物）。

## 核心 DTO 字段表

> 注：以下字段表摘自 `contracts/` 代码，字段数量/必填项/类型以代码行为准。

### TaskConfigDTO (TaskConfigDTO.v1)

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| task_id | str | ✓ | 32 位 hex 字符串 |
| dataset | str | ✓ | 数据集标识 |
| source_id | str | ✓ | 来源插件 ID |
| profile_id | str | ✓ | 领域画像标识 |
| target_url | str | ✓ | 入口 URL |
| config_revision | int | ✓ | 配置快照版本 |
| config_snapshot | dict | ✓ | 只读校验后配置 |
| created_at | str | ✓ | ISO 8601 时间戳 |

### RawDataBatch (RawDataBatch.v1)

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| schema_version | str | ✓ | 固定值为 "1" |
| task_id | str | ✓ | 关联 TaskConfigDTO |
| items | list[RawDataDTO] | ✓ | 可为空（合法空结果） |
| pagination_complete | bool | ✓ | 分页是否结束 |
| next_page_token | str? | ✗ | 继续翻页凭证 |
| errors | list[ErrorDTO] | ✗ | 采集期错误 |
| fetched_at | str | ✓ | ISO 8601 时间戳 |

### Storage 链路 DTO

| DTO | Schema ID | 必填核心字段 |
|---|---|---|
| StoreRequest.v1 | StoreRequest | schema_version, task_id, dataset, idempotency_key |
| StoreReceipt.v1 | StoreReceipt | target_id, written, skipped, failed, output_ref |
| StageResult.v1 | StageResult | stage, success, records, receipt |
| RunResult.v1 | RunResult | run_id, task_id, stages, errors |

## 五组插件输入/输出契约

| 插件类型 | input_schema | output_schema | 基类 |
|---|---|---|---|
| spider | TaskConfigDTO.v1 | RawDataBatch.v1 | SpiderPlugin |
| processor (parse) | RawDataBatch.v1 | RecordBatch.v1 | ParserPlugin |
| processor (post) | RecordBatch.v1 | RecordBatch.v1 | RecordProcessorPlugin |
| storage | StoreRequest.v1 | StoreReceipt.v1 | StoragePlugin |
| presenter | PresentationRequest.v1 | RenderedOutputDTO.v1 | PresenterPlugin |

## 错误码速查

| 错误码 | 阶段 | 可重试 | 说明 |
|---|---|---|---|
| HTTP_TIMEOUT | acquire | ✓ | 请求超时 |
| HTTP_CONNECTION_ERROR | acquire | ✓ | 连接错误 |
| HTTP_BLOCKED | acquire | ✗ | 反爬冷却/熔断 |
| PARSE_FAILED | process | ✗ | 解析失败 |
| VALIDATION_SCHEMA_MISMATCH | process | ✗ | Schema 不匹配 |
| STORAGE_WRITE_FAILED | store | ✓ | 写入失败 |
| STORAGE_IDEMPOTENCY_CONFLICT | store | ✗ | 幂等冲突 |
| RENDER_TEMPLATE_MISSING | present | ✗ | 模板缺失 |
| PIPELINE_CONFIG_INVALID | — | ✗ | 配置无效 |

## 常见错误与修复

| 错误 | 原因 | 修复 |
|---|---|---|
| `PluginExecutionError: HTTP_TIMEOUT` | 目标站点限速 | 增加 `retry_count`；检查 `PoliteSession` 限速配置 |
| `ValidationError: Missing required field 'task_id'` | TaskConfigDTO 构造不完整 | 检查所有必填字段；使用 `config.validator.validate_all_configs` 预检 |
| `JSONDecodeError` 解析 metadata.json | JSON 格式错误 | 验证 JSON 格式；检查特殊字符转义 |
| `ImportError: cannot import BasePlugin` | 基类导入错误 | 确认 `plugins/base.py` 存在；检查相对导入路径 |
| `ValueError: entry_point format error` | entry_point 格式错误 | `module.path:ClassName` 格式；确保 ClassName 正确 |
| `AssertionError: assets must not be empty` | RawDataDTO 资产为空 | 填充 `assets` 列表或使用 legacy `raw_ref` |
| `SchemaValidationError` | JSON Schema 不匹配 | 检查 `input_schema`/`output_schema` 是否匹配插件类型 |
| `FileNotFoundError: plugin.py` | 插件文件未生成 | 使用脚手架生成；检查 `allowed_paths` 权限 |

## 反面示例 → 修复后示例

**错误：硬编码 HTTP 请求**

```python
# BAD: 绕过 context.http
import requests

class MySpider(BasePlugin):
    def execute(self, data, context):
        resp = requests.get(data.target_url)  # 未受限速/重试
        content = resp.text
        return RawDataBatch(...)
```

**修复后：使用受管会话**

```python
# GOOD: 使用 context.http
class MySpider(BasePlugin):
    def execute(self, data, context):
        session = context.http  # PoliteSession: 限速/重试/冷却
        resp = session.get(data.target_url)
        content = resp.text
        return RawDataBatch(...)
```

**错误：直接修改共享批次**

```python
# BAD: 原地修改 RecordBatch
class DedupProcessor(BasePlugin):
    def execute(self, data, context):
        data.records.sort()  # 直接修改
        data.records = data.records[:-1]  # 破坏不可变约束
        return data
```

**修复后：返回新批次**

```python
# GOOD: 返回新批次
class DedupProcessor(BasePlugin):
    def execute(self, data, context):
        unique_records = list({r.record_id: r for r in data.records}.values())
        return RecordBatch(
            schema_version="1",
            records=unique_records,
            stats=data.stats,
        )
```