# 03 - 编写第一个 Spider 插件

> **版本**：v3.0.0
> **状态**：已定稿
> **读者**：首次接触本平台的开发者

## 五分钟最小运行示例

```python
# 使用脚手架生成并运行最小 spider
# 命令：python -m scaffolds.cli new spider quick_spider
#      python -m pytest tests/fixtures/generated_plugin/quick_spider -v

from pathlib import Path
from plugins.spiders.spi_berkeley.plugin import BerkeleySpiderPlugin
from contracts.task import TaskConfigDTO
from plugins.base import PluginContext

# 创建最小 TaskConfigDTO
config = TaskConfigDTO(
    task_id="a" * 32, dataset="test", source_id="spi_berkeley",
    profile_id="default", target_url="https://example.com/feed",
    config_revision=1, config_snapshot={}, created_at="2026-09-20T00:00:00+00:00",
)

# 模拟 PluginContext（测试环境）
class MockHTTP:
    def get(self, url, timeout=30):
        class Resp:
            text = '<html><body>sample</body></html>'
        return Resp()

class MockContext:
    http = MockHTTP()
    task_id = config.task_id
    config_snapshot = config.config_snapshot

plugin = BerkeleySpiderPlugin()
plugin.setup(MockContext())
result = plugin.execute(config, MockContext())
print(f"✓ spider 返回 RawDataBatch: {len(result.items)} 条, {result.pagination_complete=}")
```

## API 参考（从 BasePlugin 派生）

### BasePlugin 接口

```python
# plugins/base.py 中的 SpiderPlugin 定义
class SpiderPlugin(BasePlugin[TaskConfigDTO, RawDataBatch]):
    plugin_type: str = "spider"
    input_schema: str = "TaskConfigDTO.v1"
    output_schema: str = "RawDataBatch.v1"

    def setup(self, context: PluginContext) -> None:
        """插件初始化，获得受管依赖。"""
        ...

    def execute(self, data: TaskConfigDTO, context: PluginContext) -> RawDataBatch:
        """**唯一入口**：实现采集逻辑，返回 RawDataBatch。"""
        ...

    def close(self) -> None:
        """清理资源，可选。"""
        ...
```

### 关键依赖注入

| 注入项 | 类型 | 用途 |
|---|---|---|
| `context.http` | `PoliteSession` | 受限速/重试/冷却的 HTTP 会话 |
| `context.cache` | `CrawlCache` | 结果缓存，降低重复请求 |
| `context.progress` | `ProgressTracker` | 汇报进度，避免失败重跑 |
| `task_id` | `str` | 当前任务唯一标识 |
| `config_snapshot` | `dict` | 任务配置快照 |

### RawDataBatch 构建要点

```python
from datetime import datetime, timezone
from contracts.raw import RawDataBatch, RawDataDTO, MediaAsset

batch = RawDataBatch(
    schema_version="1",
    task_id=context.task_id,
    items=[
        RawDataDTO(
            source_id=data.source_id,
            url="https://example.com/item/1",
            content_type="text/html",
            encoding="utf-8",
            fetched_at=datetime.now(timezone.utc).isoformat(),
            assets=[
                MediaAsset(  # 资产依赖，新插件必须填写
                    media_type="image",
                    mime_type="image/jpeg",
                    url="https://example.com/item/1.jpg",
                    fetched_at=datetime.now(timezone.utc).isoformat(),
                )
            ],
        ),
    ],
    pagination_complete=True,
    fetched_at=datetime.now(timezone.utc).isoformat(),
)
```

## 常见错误与 Top 10 修复

| 错误 | 原因 | 修复 |
|---|---|---|
| `AttributeError: 'MockContext' object has no 'http'` | 上下文缺失 http | 使用 `context.http` 而非 `requests` |
| `ValueError: assets must not be empty` | RawDataDTO 资产为空 | 填充 `assets` 或 legacy `raw_ref` |
| `HTTPError: 429 Too Many Requests` | 未使用 PoliteSession | 必须使用 `context.http` |
| `TypeError: DataBatch.__init__() missing 5 positional args` | 构造不完整 | 检查 `schema_version`、`task_id`、`items`、`pagination_complete`、`fetched_at` |
| `ImportError: No module named 'contracts'` | 依赖未安装 | 运行 `pip install -r requirements.txt` |
| `KeyError: 'list_url'` | config_snapshot 字段缺失 | 检查 `config_schema` 是否匹配 |
| `AssertionError: metadata.json 缺少 entry_point` | metadata 字段不全 | 检查 REQUIRED_METADATA_FIELDS |
| `FileExistsError` 写入冲突 | 多进程写同一文件 | 使用 `ManagedStorage` 或文件锁 |
| `ValidationError: schema_version must be "1"` | 版本硬编码错误 | 使用字符串 `"1"` 而非整数 |

## 反面示例 → 修复后示例

**错误：直接使用 requests 绕过限速**

```python
# BAD
import requests
from plugins.base import BasePlugin

class BadSpider(BasePlugin):
    def execute(self, data, context):
        resp = requests.get(data.target_url)  # 429 风险
        html = resp.text
        return RawDataBatch(schema_version="1", ...)  # 遗漏字段
```

**修复后：使用 PoliteSession**

```python
# GOOD
from plugins.spiders import SpiderPlugin
from contracts.raw import RawDataBatch, RawDataDTO
from contracts.task import TaskConfigDTO

class GoodSpider(SpiderPlugin):
    def execute(self, data: TaskConfigDTO, context):
        # PoliteSession 自动重试、限速、冷却
        resp = context.http.get(data.target_url)
        html = resp.text

        return RawDataBatch(
            schema_version="1",
            task_id=context.task_id,
            items=[],
            pagination_complete=True,
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
```