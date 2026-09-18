# 01 - 平台总览与架构

> **状态**：初稿
> **读者**：新加入的插件开发者

## 架构模型

本平台采用**管道-过滤器**架构，数据流经四个阶段：

```
acquire (采集) → process (处理) → store (存储) → present (呈现)
```

每个阶段由一组**插件**驱动，插件通过统一基类 `BasePlugin` 接入。

## 五组插件

| 组 | 目录 | 输入 → 输出 | 职责 |
|---|---|---|---|
| spider | `plugins/spiders/` | TaskConfigDTO → RawDataBatch | 网页/数据源采集 |
| processor | `plugins/processors/` | RawDataBatch/RecordBatch → RecordBatch | 解析、清洗、去重、合并、统计 |
| storage | `plugins/storage/` | StoreRequest → StoreReceipt | JSONL/Excel/SQLite 落盘 |
| presenter | `plugins/presenters/` | PresentationRequest → RenderedOutputDTO | HTML/Text/CSV/PDF 输出 |
| ui | `plugins/ui/` | ViewModel → UIComponentDTO | table/chart/card/filter 组件描述 |

## 数据流图

```
TaskConfigDTO
    │
    ▼
┌──────────┐    RawDataBatch     ┌──────────┐    RecordBatch     ┌──────────┐
│  Spider  │ ─────────────────► │  Parser  │ ────────────────► │  Post    │
│ (acquire)│                    │ (parse)  │                   │ (steps)  │
└──────────┘                    └──────────┘                   └──────────┘
                                                                    │
                                                              RecordBatch
                                                                    │
                    ┌──────────┐    StoreReceipt    ┌──────────┐   │
                    │ Storage  │ ◄──────────────── │  Store   │ ◄─┘
                    │ (output) │                    └──────────┘
                    └──────────┘
                         │
                    RenderedOutputDTO
                         │
                    ┌──────────┐
                    │Presenter │
                    │ (render) │
                    └──────────┘
```

## 目录职责速查

| 目录 | 职责 | 维护窗口 |
|---|---|---|
| `contracts/` | DTO 类型定义（不可变契约） | W1 |
| `plugins/base.py` | 统一基类 + PluginContext | W1 |
| `pipeline/` | 四阶段引擎 | W2 |
| `plugin_manager/` | 加载/校验/生命周期 | W3 |
| `plugins/spiders/` | 采集插件 | W4 |
| `plugins/processors/` | 处理器插件 | W5 |
| `plugins/storage/` | 存储插件 | W6 |
| `plugins/presenters/` | 呈现器 | W7 |
| `plugins/ui/` | UI 组件 | W7 |
| `schema_editor/` | 任务配置编辑器 | W8 |
| `scaffolds/` | 插件脚手架 CLI | W8 |

## 两个重要区分

### scaffolds/templates vs templates/

- **`scaffolds/templates/`**：脚手架模板目录，存放插件包生成的骨架代码。由 `scaffolds.cli` 使用。
- **`templates/`**：成品模板库，存放20套完整的 HTML 呈现模板（layout.html + style.css + variables.json + preview.png）。由 W7 维护，呈现器加载。

两者**完全不同**，不要混淆。

### 插件包 vs 插件实例

- **插件包**：`plugins/spiders/static_html/` 整个目录（plugin.py + metadata.json）
- **插件实例**：`config/plugins.yaml` 里的 `static_fetch: plugin: spider:static_html`，是插件包在 pipeline 中的具体配置化使用

## 快速上手

1. 安装开发环境：`pip install -r requirements.txt`（如适用）
2. 跑基线测试：`python -m pytest tests/ -q --ignore=tests/test_filter_component.py`
3. 用脚手架生成第一个插件：`python -m scaffolds.cli new spider my_first`
4. 阅读 [03 - 编写第一个 Spider](03_first_spider.md)
