# 09 - 模板开发

> **状态**：初稿
> **读者**：需要创建或自定义 HTML 呈现模板的开发者

## 模板四件套

每个模板是一个目录，包含四个文件：

```
templates/<name>/
├── layout.html       # 主页面结构（Jinja2 模板）
├── style.css         # 样式表
├── variables.json    # 可配置变量声明
└── preview.png       # 预览截图（构建时生成）
```

**注意**：这是 `templates/` 成品模板库（W7 维护），不是 `scaffolds/templates/` 脚手架模板。

## variables.json 约定

```json
{
  "name": "minimal-light",
  "author": "platform",
  "version": "1.0.0",
  "description": "极简亮色模板",
  "variables": {
    "primary_color": {
      "type": "color",
      "default": "#3b82f6",
      "label": "主色调"
    },
    "font_family": {
      "type": "string",
      "default": "system-ui, sans-serif",
      "label": "字体"
    },
    "show_header": {
      "type": "boolean",
      "default": true,
      "label": "显示页头"
    }
  }
}
```

变量在 layout.html 中通过 Jinja2 引用：

```html
<style>
:root {
  --primary: {{ variables.primary_color }};
  --font: {{ variables.font_family }};
}
</style>
```

## ThemeSwitcher 接入

ThemeSwitcher（`plugins/presenters/html_presenter/theme_switcher.py`）负责：

1. 读取 `templates/registry.json` 获取所有模板清单
2. 根据用户选择加载对应模板目录
3. 将 variables.json 中的变量注入模板渲染上下文
4. 在生成的 HTML 中嵌入主题切换 UI

### registry.json

```json
{
  "templates": [
    {
      "name": "minimal-light",
      "path": "minimal-light",
      "description": "极简亮色",
      "preview": "minimal-light/preview.png"
    }
  ]
}
```

## 用脚手架生成模板骨架

```bash
python -m scaffolds.cli new template my_theme
```

生成 `tests/fixtures/generated_plugin/my_theme/` 下的四件套骨架。

## 构建预览图

preview.png 在构建时由 headless browser 截图生成：

```bash
# 需要 playwright 或 selenium（未自动安装）
# 具体构建命令见 scripts/build_template_previews.py（计划中）
```
