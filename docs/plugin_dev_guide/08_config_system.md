# 08 - 配置系统

> **状态**：初稿
> **读者**：需要配置 pipeline 或插件实例的开发者

## 两个核心配置文件

### config/pipeline.yaml

定义 pipeline 的四阶段执行计划：

```yaml
schema_version: 1
pipeline:
  id: education_default
  sources:
    source_a:
      acquire: static_fetch       # 引用 plugins.yaml 中的实例名
      parse: [faculty_parse]      # parse 阶段插件列表
      required: true
  process:
    steps: [normalize_records, merge_records, statistics]
  store:
    targets:
      - instance: jsonl_output
        required: true
      - instance: excel_output
        required: false
  present:
    required: false
    components: [table_view, chart_view, card_view, filter_view]
    outputs:
      - instance: html_report
        required: false
```

### config/plugins.yaml

声明插件实例（同一个插件包可以有多个实例，配置不同 params）：

```yaml
schema_version: 1
instances:
  static_fetch:
    plugin: spider:static_html    # type:name 引用插件包
    enabled: true
    params:
      max_pages: 20
      delay: 1.5
  faculty_parse:
    plugin: processor:faculty_parser
    enabled: true
    params:
      profile: education.tutor.v1
  jsonl_output:
    plugin: storage:jsonl_store
    enabled: true
    params: {}
```

## 实例规则

- `instance` 名称在 pipeline.yaml 中引用
- `plugin` 格式为 `type:name`（type = spider/processor/storage/presenter/ui）
- 同一插件包可以有多个实例（不同 params）
- `enabled: false` 的实例不参与执行

## 预检

使用 `config.validator` 在启动前校验配置：

```python
from config.validator import validate_all_configs
from config.loader import load_schools_config

result = validate_all_configs(load_schools_config())
if result["errors"]:
    print("配置错误:", result["errors"])
```

## schema_editor 快速配置

使用 schema_editor 预设快速生成任务配置：

```bash
# 列出可用预设
python schema_editor/editor.py --list

# 加载预设并查看
python schema_editor/editor.py tutor_research
```

预设文件在 `schema_editor/presets/` 目录下。

## 迁移

从 V2.2 配置迁移到 V3.0：

```bash
python scripts/migrate_config.py --dry-run --report /tmp/migrate_report.txt
```

迁移器自动映射旧插件名到新实例名（参见 `scripts/migrate_config.py` 的映射表）。
