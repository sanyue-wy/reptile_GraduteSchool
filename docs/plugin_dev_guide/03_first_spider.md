# 03 - 编写第一个 Spider 插件

> **状态**：初稿
> **读者**：首次接触本平台的开发者

## 目标

用脚手架生成一个 spider 插件，理解其结构，实现一个最简单的页面采集。

## 第一步：生成骨架

```bash
python -m scaffolds.cli new spider demo_probe
```

生成产物（默认在 `tests/fixtures/generated_plugin/demo_probe/`）：

```
demo_probe/
├── __init__.py
├── plugin.py         # 主插件类
├── metadata.json     # 元数据声明
├── test_plugin.py    # 单测
└── README.md
```

## 第二步：理解 metadata.json

参考 `plugins/spiders/static_html/metadata.json`：

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
    "properties": {
      "max_pages": {"type": "integer", "minimum": 1}
    },
    "additionalProperties": false
  },
  "license": "MIT"
}
```

**必须字段**：name, version, author, plugin_type, input_schema, output_schema, entry_point。

## 第三步：实现 execute()

骨架的 `execute()` 留有 TODO。参考 `plugins/spiders/static_html/plugin.py` 的模式：

```python
def execute(self, task_config: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
    session = context.http          # 受管 HTTP 会话（限速/重试/冷却）
    cfg = task_config.config_snapshot
    list_url = cfg.get("list_url") or task_config.target_url

    # 使用受管会话发起请求
    resp = session.get(list_url)
    # ... 解析页面 ...

    return RawDataBatch(
        schema_version="1",
        task_id=context.task_id,
        items=[...],  # List[RawDataDTO]
        pagination_complete=True,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
```

**红线**：不得绕过 `context.http` 直接用 requests；不得写业务解析逻辑（解析归 processor）。

## 第四步：运行测试

```bash
python -m pytest tests/fixtures/generated_plugin/demo_probe -v
```

骨架自带一个 `test_metadata_self_consistent` 必过用例。

## 多媒体资产用法

`plugins/spiders/media_downloader/` 展示了多媒体采集模式：

```python
# 直接 URL 引用（无需下载二进制）
asset = MediaAsset(
    media_type="image",
    mime_type="image/jpeg",
    url="https://example.edu/photo.jpg",
    fetched_at=datetime.now(timezone.utc).isoformat(),
)

# 流式落盘（大文件，> 10 MiB 限制）
asset = MediaAsset(
    media_type="video",
    mime_type="video/mp4",
    url=local_path,  # 落盘后的本地路径
    size=file_size,
    sha256=hash_value,
    fetched_at=datetime.now(timezone.utc).isoformat(),
)
```

超 10 MiB 的资产必须落盘后用 `url` 引用，不能放在 `data` 字段。

## 参考插件

| 插件 | 目录 | 特点 |
|---|---|---|
| static_html | `plugins/spiders/static_html/` | 最基础的静态页面采集 |
| ajax_api | `plugins/spiders/ajax_api/` | AJAX/JSON API 采集 |
| js_render | `plugins/spiders/js_render/` | 需要 JS 渲染的页面 |
| media_downloader | `plugins/spiders/media_downloader/` | 流式多媒体下载 |
| pdf_list | `plugins/spiders/pdf_list/` | PDF 文件列表采集 |
| yzw_api | `plugins/spiders/yzw_api/` | 研招网 API 采集 |
