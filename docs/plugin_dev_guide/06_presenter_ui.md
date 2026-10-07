# 06 - 编写 Presenter 与 UI 组件

> **版本**：v3.0.0
> **状态**：已定稿
> **读者**：呈现阶段与 UI 开发者

## 五分钟最小运行示例

```python
# 使用脚手架生成 presenter 并运行
# 命令：python -m scaffolds.cli new presenter quick_text
#      python -m pytest tests/fixtures/generated_plugin/quick_text -v

from pathlib import Path
from plugins.presenters.text_presenter.plugin import TextPresenterPlugin
from contracts.output import PresentationRequest, RenderedOutputDTO
from plugins.base import PluginContext

# 创建最小 PresentationRequest
request = PresentationRequest(
    request_id="a" * 32,
    dataset="test",
    schema_id="Default.v1",
    output_spec={},
    records=[],
    created_at="2026-09-20T00:00:00+00:00",
)

class MockContext:
    task_id = "b" * 32
    config_snapshot = {}

presenter = TextPresenterPlugin()
result = presenter.execute(request, MockContext())
print(f"✓ presenter 返回 RenderedOutputDTO: {result.output_format}, {result.path}")
```

## API 参考：PresenterPlugin 接口

### PresenterPlugin 核心设计

```python
# plugins/base.py 中的 PresenterPlugin 定义
class PresenterPlugin(BasePlugin[PresentationRequest, RenderedOutputDTO]):
    plugin_type: str = "presenter"
    input_schema: str = "PresentationRequest.v1"
    output_schema: str = "RenderedOutputDTO.v1"

    def execute(self, data: PresentationRequest, context: PluginContext) -> RenderedOutputDTO:
        """
        具体方法（非抽象）：调用 render() 并包装结果
        子类可覆盖 execute() 实现自定义逻辑
        """
        rendered = self.render(data, context)
        if isinstance(rendered, RenderedOutputDTO):
            return rendered
        if isinstance(rendered, str):
            return RenderedOutputDTO(
                output_id=context.run_id[:16] if hasattr(context, 'run_id') else 'out',
                output_format=self.default_format,
                path=rendered,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        raise TypeError(f"render() 必须返回 RenderedOutputDTO 或 str")

    def render(self, data: PresentationRequest, context: PluginContext) -> RenderedOutputDTO | str:
        """抽象钩子：子类必须实现此方法"""
        raise NotImplementedError
```

### PresentationRequest 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| request_id | str | ✓ | 32 位 hex |
| dataset | str | ✓ | 数据集标识 |
| schema_id | str | ✓ | Schema ID |
| output_spec | dict | ✓ | 输出规格参数 |
| records | list[dict] | ✗ | 简化记录视图 |
| media_assets | list[MediaAsset] | ✗ | 引用的媒体 |
| store_receipts | list[dict] | ✗ | 存储回执 |
| run_state | dict | ✗ | 运行状态 |
| stats | dict | ✗ | 聚合统计 |
| created_at | str | ✓ | ISO 8601 |

### RenderedOutputDTO 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| output_id | str | ✓ | 32 位 hex |
| output_format | str | ✓ | html/text/markdown/jsonl/csv/pdf |
| path | str | ✓ | 输出文件/目录绝对路径 |
| media_assets | list[MediaAsset] | ✗ | 嵌入输出的媒体 |
| metadata | dict | ✗ | 页数、大小等 |
| created_at | str | ✓ | ISO 8601 |

### 自定义 render() 实现

```python
from uuid import uuid4
from datetime import datetime, timezone
from contracts.output import RenderedOutputDTO

class TextPresenter(PresenterPlugin):
    default_format = "text"

    def render(self, request, context) -> str:
        lines = []
        for record in request.records:
            title = record.get("title", "无标题")
            url = record.get("url", "")
            lines.append(f"{title}\n  {url}\n")

        output_path = Path(context.allowed_paths[0]) / f"output_{uuid4().hex}.txt"
        output_path.write_text("\n".join(lines), encoding="utf-8")
        return str(output_path)
```

## UIPlugin 接口

```python
# plugins/base.py 中的 UIPlugin 定义
class UIPlugin(BasePlugin[ViewModel, UIComponentDTO]):
    plugin_type: str = "ui"
    input_schema: str = "ViewModel.v1"
    output_schema: str = "UIComponentDTO.v1"

    def execute(self, data: ViewModel, context: PluginContext) -> UIComponentDTO:
        """声明式组件描述，不返回任意 HTML"""
        ...
```

### ViewModel → UIComponentDTO

```python
from contracts.ui import ViewModel, UIComponentDTO
from uuid import uuid4
from datetime import datetime, timezone

class TableComponent(UIPlugin):
    def execute(self, data: ViewModel, context) -> UIComponentDTO:
        return UIComponentDTO(
            component_id=uuid4().hex,
            component_type="table",
            renderer_id="table_renderer",  # 引用已批准的渲染器
            payload={
                "columns": [{"field": "title", "header": "标题"}],
                "rows": [{"title": r.get("title") for r in data.data_ref}],
            },
            data_ref=data.data_ref,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
```

### Renderer Manifest

呈现器在 metadata.json 中声明：

```json
{
  "name": "csv_presenter",
  "plugin_type": "presenter",
  "output_format": "csv",
  "renderer_id": "csv_renderer",
  "config_schema": {
    "type": "object",
    "properties": {
      "delimiter": {"type": "string", "default": ","},
      "encoding": {"type": "string", "default": "utf-8"}
    }
  }
}
```

## 安全文本插入

### 防止 XSS

```python
from html import escape

# 错误：直接插入用户内容
html = f"<td>{record['title']}</td>"  # 可能含 <script>

# 正确：HTML 转义
html = f"<td>{escape(record['title'], quote=True)}</td>"
```

### PDF 呈现安全

```python
# 使用 WeasyPrint 渲染 HTML → PDF
from weasyprint import HTML

def render_pdf(html_content: str, output_path: str):
    # WeasyPrint 自动转义 HTML 内容
    HTML(string=html_content).write_pdf(output_path)
```

## 常见错误与 Top 10 修复

| 错误 | 原因 | 修复 |
|---|---|---|
| `TypeError: render() must return RenderedOutputDTO or str` | 返回类型错误 | 返回 str 或 RenderedOutputDTO |
| `FileNotFoundError: allowed_paths` | 写入路径未授权 | 使用 `context.allowed_paths[0]` |
| `ValidationError: output_format must be one of ['html','text',...]` | format 不合法 | 选用标准 format |
| `ImportError: No module named 'weasyprint'` | 依赖缺失 | 在 metadata.json 中声明 |
| `AttributeError: 'ViewModel' has no 'data_ref'` | 字段缺失 | 检查 input_schema 匹配 |
| `ValueError: renderer_id not in approved list` | 渲染器未批准 | 提交到 W3 注册表 |
| `UnicodeEncodeError: gbk codec` | 写入编码问题 | 使用 `encoding='utf-8'` |
| `FileExistsError` 复制媒体 | 路径冲突 | 使用 `uuid4().hex` 生成唯一名 |
| `OSError: No space left on device` | 输出目录满 | 检查磁盘空间；清理旧文件 |
| `TypeError: Unsupported data type` | data_ref 格式错误 | 确认是 list[dict]，非嵌套结构 |

## 反面示例 → 修复后示例

**错误：直接写 HTML，易 XSS**

```python
# BAD: 未转义用户内容
class BadPresenter(PresenterPlugin):
    def render(self, request, context):
        html = f"<html><body>"
        for r in request.records:
            html += f"<div>{r.get('title', '')}</div>"  # XSS 风险
        path = f"/output/{context.run_id}.html"
        Path(path).write_text(html)
        return RenderedOutputDTO(output_format="html", path=path, ...)
```

**修复后：HTML 转义 + 原子写入**

```python
# GOOD: 安全 + 原子
from html import escape
from uuid import uuid4

class GoodPresenter(PresenterPlugin):
    def render(self, request, context) -> str:
        lines = ["<html><body>"]
        for r in request.records:
            lines.append(f"<div>{escape(str(r.get('title', '')))}</div>")
        lines.append("</body></html>")

        html = "\n".join(lines)
        out_dir = Path(context.allowed_paths[0])
        out_name = f"output_{uuid4().hex}.html"
        tmp_path = out_dir / f".tmp_{out_name}"
        final_path = out_dir / out_name

        tmp_path.write_text(html, encoding="utf-8")
        os.replace(str(tmp_path), str(final_path))

        return str(final_path)
```