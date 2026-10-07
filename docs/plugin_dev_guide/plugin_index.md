# 插件索引

> 基于 v3.0.0 注册表快照生成
>
> ⚠️ **2026-10-01（G4）勘误**：本索引生成于 `revision=21`，其后注册表已推进至 **revision=32**。
> 原「概览」表把 8 个 processor 标为 rejected「待 W5 修复」，但 W5 已于 2026-09-20 修复全部 10 个处理器的基类继承
> （见 `docs/V3.0/tasks/progress.md` W5 区段），该"待修复"状态**已过期**。
> 另：`plugin_manager/registry_snapshot.json` 中 32 条记录**均无 `status` 字段**，
> 故本索引原有的 approved/rejected 拆分无法从快照复核，下表只列实测数量。

## 概览

| 类型 | 数量 | 实测来源 |
|------|------|----------|
| spider | 7 | `scan_plugin_dirs()` |
| processor | 10 | 同上（core 8 + 前置 2：url_normalizer / domain_rewriter） |
| storage | 5 | 同上 |
| presenter | 6 | 同上 |
| ui | 4 | 同上 |

**总计**: **32 个插件**（`registry_snapshot.json` 的 `registry_revision = 32` 独立复核一致）

> 复算命令：
> `python -c "from plugin_manager.loader import scan_plugin_dirs; d,_,_=scan_plugin_dirs(); print(len(d))"` → `32`

## 采集插件 (Spider)

| 插件 ID | 版本 | 状态 | 说明 |
|---------|------|------|------|
| ajax_api | 1.0.0 | approved | AJAX API 数据采集 |
| js_render | 1.0.0 | approved | JavaScript 渲染采集 |
| media_downloader | 1.0.0 | approved | 媒体文件下载器 |
| pdf_list | 1.0.0 | approved | PDF 列表采集 |
| static_html | 1.0.0 | approved | 静态 HTML 采集 |
| url_prober | 1.0.0 | approved | URL 可达性探测器 |
| yzw_api | 1.0.0 | approved | 阳光高考 API 采集 |

## 处理器插件 (Processor)

### 已批准 (APPROVED)

| 插件 ID | 版本 | 状态 | 说明 |
|---------|------|------|------|
| domain_rewriter | 1.0.0 | approved | 域名重写处理器 |
| url_normalizer | 1.0.0 | approved | URL 归一化处理器 |

### 处理器 (Processor) — 原标记 REJECTED，2026-10-01 G4 更正为已修复

| 插件 ID | 版本 | 状态 | 说明 | 实际继承 |
|---------|------|------|------|----------|
| dedup | 1.0.0 | ✅ 已修复 | 去重处理器 | `RecordProcessorPlugin` |
| education_merge | 1.0.0 | ✅ 已修复 | 教育数据合并 | `RecordProcessorPlugin` |
| error_analyzer | 1.0.0 | ✅ 已修复 | 错误分析器 | `RecordProcessorPlugin` |
| faculty_parser | 1.0.0 | ✅ 已修复 | 教师信息解析 | `ParserPlugin` |
| normalize | 1.0.0 | ✅ 已修复 | 数据归一化 | `RecordProcessorPlugin` |
| parser_fallback | 1.0.0 | ✅ 已修复 | 解析回退器 | `ParserPlugin` |
| statistics | 1.0.0 | ✅ 已修复 | 统计分析 | `RecordProcessorPlugin` |
| yzw_major_parser | 1.0.0 | ✅ 已修复 | 阳光高考专业解析 | `ParserPlugin` |

> ⚠️ **2026-10-01（G4）勘误**：原文把上表 8 个处理器全部标为 `rejected`，并注明
> "因未继承 BasePlugin 子类被注册表拒绝，需 W5 修复"——**该状态已过期**。
> W5 已于 2026-09-20 完成修复（见 `docs/V3.0/tasks/progress.md` W5 区段"继承关系修复"条目）。
> G4 于 2026-10-01 实测复核继承链，确认上表"实际继承"列全部属实
> （`ParserPlugin` 实有 3 个子类、`RecordProcessorPlugin` 实有 5 个子类，合计正是这 8 个）。
>
> ⚠️ 但**仍有一处未闭环**：`ParserPlugin` 自身的 `plugin_type` 被声明为 `"parser"`，
> 而 `plugins/base.py` 之外的加载器（`plugin_manager.loader.PLUGIN_TYPES`）与冻结契约
> `INTERFACES.md` §3.3 用的都是 `"processor"`。其中 `parser_fallback` 因此出现
> 类属性 `'parser'` 与 `metadata.json` `'processor'` 不一致的分裂值。详见 merge_report.md §6.3。

## 存储插件 (Storage)

| 插件 ID | 版本 | 状态 | 说明 |
|---------|------|------|------|
| jsonl_store | 1.0.0 | approved | JSONL 格式存储 |
| media_store | 1.0.0 | approved | 媒体文件存储 |
| progress_store | 1.0.0 | approved | 进度状态存储 |
| sql_store | 1.0.0 | approved | SQL 数据库存储 |
| xlsx_store | 1.0.0 | approved | Excel 格式存储 |

## 呈现器插件 (Presenter)

| 插件 ID | 版本 | 状态 | 说明 |
|---------|------|------|------|
| csv_presenter | 1.0.0 | approved | CSV 格式呈现 |
| html_presenter | 1.0.0 | approved | HTML 独立页面呈现 |
| jsonl_presenter | 1.0.0 | approved | JSONL 格式呈现 |
| markdown_presenter | 1.0.0 | approved | Markdown 格式呈现 |
| pdf_presenter | 1.0.0 | approved | PDF 文档呈现 |
| text_presenter | 1.0.0 | approved | 纯文本呈现 |

## UI 组件 (UI)

| 插件 ID | 版本 | 状态 | 说明 |
|---------|------|------|------|
| card_component | 1.0.0 | approved | 卡片组件 |
| chart_component | 1.0.0 | approved | 图表组件 |
| filter_component | 1.0.0 | approved | 筛选组件 |
| table_component | 1.0.0 | approved | 表格组件 |

## API 接口

### GET /api/plugins/list

获取所有已批准插件的完整元数据。

**请求示例**:
```bash
curl http://localhost:5000/api/plugins/list
```

**响应格式**:
```json
[
  {
    "id": "spider:static_html",
    "name": "static_html",
    "plugin_type": "spider",
    "version": "1.0.0",
    "author": "maintainers",
    "description": "...",
    "description_long": "...",
    "license": "MIT",
    "dependencies": [],
    "input_schema": "TaskConfigDTO.v1",
    "output_schema": "RawDataBatch.v1",
    "config_schema": {...},
    "min_core_version": "3.0.0",
    "entry_point": "plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin",
    "state": "approved",
    "content_hash": "abc123...",
    "reference_count": 0,
    "installed_at": "2026-09-18T10:00:00+00:00",
    "updated_at": "2026-09-18T10:00:00+00:00",
    "requires_restart": false
  }
]
```

## 快照元信息

- **release_tag**: v3.0.0
- **registry_revision**: **32**（⚠️ 2026-10-01 G4 更正：原文记 21，为本索引生成时的旧快照值）
- **生成时间**: 2026-09-18
- **快照文件**: `plugin_manager/registry_snapshot.json`
- **插件数量**: **32 个**（⚠️ 2026-10-01 G4 更正：原文写"24 个可用，8 个 rejected"；
  该 approved/rejected 拆分来自 revision=21 的旧快照，且 8 个 rejected 处理器已于 2026-09-20 由 W5 全部修复）

## 快速使用

```python
from config.plugins import list_all_plugins_with_metadata

# 获取所有插件完整元数据
plugins = list_all_plugins_with_metadata()

# 按类型筛选
spiders = [p for p in plugins if p['plugin_type'] == 'spider']
```

## 开发新插件

参考脚手架 CLI（`scaffolds/cli.py`，⚠️ 2026-10-01 G4 更正：原文链接指向 `../../scaffolds/README.md`，
该文件**不存在**，scaffolds/ 下只有 `cli.py` / `generator.py` / `loader_protocol.py`）快速创建新插件：

```bash
python -m scaffolds.cli new spider my_spider
python -m scaffolds.cli new processor my_processor
python -m scaffolds.cli new storage my_storage
python -m scaffolds.cli new presenter my_presenter
python -m scaffolds.cli new ui my_component
```

生成的插件自动包含：
- `plugin.py`（继承对应基类，业务逻辑 ≤30 行）
- `metadata.json`（含 license/min_core_version/config_schema）
- `test_plugin.py`（一个必过用例）
- `README.md`