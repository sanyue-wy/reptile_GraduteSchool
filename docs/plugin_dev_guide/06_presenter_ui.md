# 06 - 编写 Presenter 与 UI 组件

> **状态**：初稿
> **读者**：需要实现数据呈现或 UI 组件的开发者

## Presenter 插件

Presenter 继承 `PresenterPlugin`（`plugins/base.py`），将 `PresentationRequest` 渲染为人类可读格式。

### execute() 是唯一抽象入口

```python
class MyPresenter(PresenterPlugin):
    name = "my_presenter"
    plugin_type = "presenter"
    input_schema = "PresentationRequest.v1"
    output_schema = "RenderedOutputDTO.v1"

    def execute(self, request: PresentationRequest, context: PluginContext) -> RenderedOutputDTO:
        # 渲染逻辑
        content = self._render(request)
        output_path = self._write_output(request, content)

        return RenderedOutputDTO(
            output_id=uuid4().hex,
            output_format="text",
            path=str(output_path),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
```

### render() 可选钩子

如果偏好"加载模板 → 渲染 → 写文件"的标准模式，可覆盖 `render()` 而不覆盖 `execute()`：

```python
def render(self, request: PresentationRequest, context: PluginContext) -> RenderedOutputDTO | str:
    """返回 RenderedOutputDTO 或输出文件路径字符串。"""
    template = self._load_template()
    return template.render(records=request.records)
```

默认的 `execute()` 会自动调用 `render()` 并包装结果。其他类型抛 `TypeError`。

### 安全文本插入

生成 HTML 时，所有用户数据必须转义：

```python
from markupsafe import escape
safe_name = escape(record.get("name", ""))
```

### 参考插件

| 插件 | 目录 | 格式 |
|---|---|---|
| text_presenter | `plugins/presenters/text_presenter/` | text/markdown |
| jsonl_presenter | `plugins/presenters/jsonl_presenter/` | JSONL |
| csv_presenter | `plugins/presenters/csv_presenter/` | CSV |
| pdf_presenter | `plugins/presenters/pdf_presenter/` | PDF (WeasyPrint) |

---

## UI 组件插件

UI 组件继承 `BasePlugin[ViewModel, UIComponentDTO]`，产出声明式组件描述（不返回任意 HTML）。

### 组件描述

```python
class MyComponent(BasePlugin[ViewModel, UIComponentDTO]):
    name = "my_component"
    plugin_type = "ui"
    input_schema = "ViewModel.v1"
    output_schema = "UIComponentDTO.v1"

    def execute(self, view_model: ViewModel, context: PluginContext) -> UIComponentDTO:
        return UIComponentDTO(
            component_id=uuid4().hex,
            component_type="custom",
            renderer_id=self.name,
            payload={...},       # 经 schema 校验的参数
            data_ref="...",      # 组件专用数据引用
            created_at=datetime.now(timezone.utc).isoformat(),
        )
```

### 四个内置组件

| 组件 | component_type | 目录 |
|---|---|---|
| table_component | table | `plugins/ui/table_component/` |
| chart_component | chart | `plugins/ui/chart_component/` |
| card_component | card | `plugins/ui/card_component/` |
| filter_component | filter | `plugins/ui/filter_component/` |

### Renderer Manifest

UI 组件通过 `renderer_id` 关联前端渲染器。渲染器 manifest 声明组件的渲染方式、可用配置项和事件处理。
