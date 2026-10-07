# 04 - 编写 Processor 插件

> **版本**：v3.0.0
> **状态**：已定稿
> **读者**：数据处理阶段开发者

## 五分钟最小运行示例

```python
# 使用脚手架生成 processor 并运行
# 命令：python -m scaffolds.cli new processor quick_parse
#      python -m pytest tests/fixtures/generated_plugin/quick_parse -v

from pathlib import Path
from plugins.processors.spi_berkeley.plugin import SpiBerkeleyProcessor
from contracts.raw import RawDataBatch, RawDataDTO
from contracts.record import RecordBatch
from plugins.base import PluginContext

# 创建最小 RawDataBatch
batch = RawDataBatch(
    schema_version="1",
    task_id="a" * 32,
    items=[
        RawDataDTO(
            source_id="test",
            url="https://example.com/item/1",
            content_type="text/html",
            encoding="utf-8",
            fetched_at="2026-09-20T00:00:00+00:00",
            assets=[],
        ),
    ],
    pagination_complete=True,
    fetched_at="2026-09-20T00:00:00+00:00",
)

class MockContext:
    task_id = batch.task_id
    config_snapshot = {}

processor = SpiBerkeleyProcessor()
result = processor.execute(batch, MockContext())
print(f"✓ processor 返回 RecordBatch: {len(result.records)} 条记录")
```

## API 参考：解析器 vs 后处理器

### ParserPlugin（parse 阶段）

```python
# plugins/processors/ 基类定义
class ParserPlugin(BasePlugin[RawDataBatch, RecordBatch]):
    """纯解析，字段抽取，media_refs 建立"""

    def execute(self, data: RawDataBatch, context: PluginContext) -> RecordBatch:
        """
        输入：RawDataBatch
        输出：RecordBatch
        约束：不得暗中发起网络请求
        """
        ...
```

| 特性 | 说明 |
|---|---|
| `input_schema` | RawDataBatch.v1 |
| `output_schema` | RecordBatch.v1 |
| 阶段 | pipeline.process.parse |
| 副作用 | 无（纯函数） |
| 网络请求 | 禁止 |

### RecordProcessorPlugin（post 阶段）

```python
from plugins.base import RecordProcessorPlugin
from contracts.record import RecordBatch

class NormalizeProcessor(RecordProcessorPlugin):
    """清洗、合并、统计、媒体处理"""

    def execute(self, data: RecordBatch, context: PluginContext) -> RecordBatch:
        ...
```

| 特性 | 说明 |
|---|---|
| `input_schema` | RecordBatch.v1 |
| `output_schema` | RecordBatch.v1 |
| 阶段 | pipeline.process.post |
| 副作用 | 可选（通过 context.storage） |
| 媒体处理 | 可通过 `media_refs` 引用 |

### 关键类型：NormalizedRecordDTO

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| record_id | str | ✓ | 32 位 hex，自然键 |
| dataset | str | ✓ | 数据集标识 |
| schema_id | str | ✓ | 引用注册表 schema |
| fields | dict | ✓ | 已校验的 JSON 值 |
| provenance | dict | ✗ | source_id, url, fetched_at 等 |
| media_refs | list[str] | ✗ | AssetRef 路径或 RawDataDTO 索引 |
| created_at | str | ✓ | ISO 8601 |

### RecordBatch 构建

```python
from contracts.record import RecordBatch, NormalizedRecordDTO

records = [
    NormalizedRecordDTO(
        record_id="b" * 32,
        dataset="demo",
        schema_id="Default.v1",
        fields={"title": "样例标题", "url": "https://example.com"},
        created_at=datetime.now(timezone.utc).isoformat(),
    ),
]

batch = RecordBatch(
    schema_version="1",
    records=records,
    stats={"processed": len(batch.records)},
    errors=[],
)
```

## 媒体引用追踪

Parser 插件建立媒体引用：

```python
# 从 RawDataDTO 索引建立 media_refs
media_refs = [
        f"__raw__.{i}"  # RawDataDTO 索引
        for i, item in enumerate(data.items)
        if item.assets
    ]

record = NormalizedRecordDTO(
    ...,
    media_refs=media_refs,
)
```

RecordProcessorPlugin 可选媒体处理：

```python
# 通过 context.storage 处理媒体
for ref in record.media_refs:
    if ref.startswith("__raw__."):
        raw_idx = int(ref.split(".")[1])
        asset = data.items[raw_idx].assets[0]
        if asset.size > 10 * 1024 * 1024:  # >10MiB
            processed = await self._download_and_process(asset)
```

## 常见错误与 Top 10 修复

| 错误 | 原因 | 修复 |
|---|---|---|
| `ImportError: cannot import 'ParserPlugin'` | 基类导入错误 | 使用 `from plugins.base import ParserPlugin` |
| `TypeError: ParserPlugin expects (RawDataBatch, RecordBatch)` | 类型不匹配 | 确认输入输出类型 |
| `ValueError: media_refs contains invalid reference` | 引用格式错误 | 使用 `__raw__.i` 或 AssetRef 路径 |
| `ValidationError: Additional properties not allowed` | fields 字段非法 | 确保 fields 值是 JSON 可序列化类型 |
| `KeyError: 'items'` | RawDataBatch.items 为空 | 允许空 items；检查 pagination_complete |
| `AttributeError: 'RecordBatch' object has no attribute 'records'` | 版本不匹配 | 确认 schema_version="1" |
| `RuntimeError: network request in parser` | 禁止发起请求 | 网络请求返回给 Spider 或 Storage |
| `ImportError: No module named 'plugins.base'` | 依赖未安装 / 未在项目根目录 | 在**仓库根目录**执行 `pip install -r requirements.txt`（⚠️ 2026-10-01 G4 实测更正：原文此处写 `pip install -e .`，该命令**必然失败**——仓库根目录既无 `setup.py` 也无 `pyproject.toml`，实测报 `does not appear to be a Python project`） |
| `AssertionError: expected 5 positional args` | RecordBatch 构造错误 | 检查字段顺序 |

## 反面示例 → 修复后示例

**错误：在 Parser 中发起网络请求**

```python
# BAD: Parser 里发 HTTP 请求
class BadParser(ParserPlugin):
    def execute(self, data, context):
        # 禁止！
        resp = requests.get("https://api.example.com/detail")
        detail = resp.json()
        fields = {"detail": detail}
        return RecordBatch(schema_version="1", records=[...])
```

**修复后：返回引用，交给后续阶段**

```python
# GOOD: Parser 只抽取，不请求
class GoodParser(ParserPlugin):
    def execute(self, data, context):
        # 只从 RawDataDTO 字段抽取
        fields = {"title": extract_title(data.items[0])}

        return RecordBatch(
            schema_version="1",
            records=[
                NormalizedRecordDTO(
                    record_id=context.task_id[:16] + "_r1",
                    dataset="demo",
                    schema_id="Default.v1",
                    fields=fields,
                    created_at=datetime.now(timezone.utc).isoformat(),
                )
            ],
            stats={"processed": 1},
        )
```