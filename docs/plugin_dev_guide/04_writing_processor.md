# 04 - 编写 Processor

> **状态**：初稿
> **读者**：需要实现数据解析或处理逻辑的开发者

## 两种 Processor

| 阶段 | 基类 | 输入 → 输出 | 典型职责 |
|---|---|---|---|
| parse | `BasePlugin[RawDataBatch, RecordBatch]` | RawDataBatch → RecordBatch | 字段抽取、选择器匹配 |
| post | `BasePlugin[RecordBatch, RecordBatch]` | RecordBatch → RecordBatch | 清洗、去重、合并、统计 |

两者都在 `plugins/processors/` 目录下，区别在 input_schema/output_schema。

## parse 阶段示例：faculty_parser

`plugins/processors/faculty_parser/plugin.py` 从 HTML assets 抽取教育字段：

```python
class FacultyParserPlugin(BasePlugin[RawDataBatch, RecordBatch]):
    name = "faculty_parser"
    plugin_type = "processor"
    input_schema = "RawDataBatch.v1"
    output_schema = "RecordBatch.v1"

    def execute(self, raw_batch: RawDataBatch, context: PluginContext) -> RecordBatch:
        records = []
        for item in raw_batch.items:
            for asset in item.assets:
                if asset.mime_type == "text/html":
                    # BeautifulSoup 解析 HTML
                    soup = BeautifulSoup(asset.data, "html.parser")
                    # ... 选择器抽取字段 ...
                    fields = {"name": "...", "title": "...", ...}
                    records.append(NormalizedRecordDTO(
                        record_id=uuid5_hex(fields),
                        dataset="...",
                        schema_id="education.tutor.v1",
                        fields=fields,
                        media_refs=[],
                        created_at=datetime.now(timezone.utc).isoformat(),
                    ))

        return RecordBatch(schema_version="1", records=records, stats={...})
```

**红线**：parse 阶段不得发起网络请求；只从 assets 数据中提取字段。

## post 阶段示例：normalize

`plugins/processors/normalize/plugin.py` 展示了最简单的 post 插件：

```python
def execute(self, record_batch: RecordBatch, context: PluginContext) -> RecordBatch:
    normalized = []
    for rec in record_batch.records:
        new_fields = {k: _normalize(v) for k, v in rec.fields.items()}
        normalized.append(NormalizedRecordDTO(...))

    return RecordBatch(
        schema_version="1",
        records=normalized,
        stats={**record_batch.stats, "normalized_count": len(normalized)},
    )
```

**红线**：不得原地修改共享批次；返回新 RecordBatch。

## media_refs 追踪

parse 阶段在 `NormalizedRecordDTO.media_refs` 中记录关联的资产引用：

```python
media_refs = [f"raw/{item.source_id}/{asset_idx}"]
```

后续 storage 阶段通过 media_refs 追踪哪些记录关联了哪些媒体文件。

## 参考插件

| 插件 | 阶段 | 目录 |
|---|---|---|
| faculty_parser | parse | `plugins/processors/faculty_parser/` |
| yzw_major_parser | parse | `plugins/processors/yzw_major_parser/` |
| normalize | post | `plugins/processors/normalize/` |
| dedup | post | `plugins/processors/dedup/` |
| education_merge | post | `plugins/processors/education_merge/` |
| statistics | post | `plugins/processors/statistics/` |
