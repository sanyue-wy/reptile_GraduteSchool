# 07 - metadata.json 与批准流程

> **状态**：初稿
> **读者**：所有插件开发者

## metadata.json 必须字段

| 字段 | 类型 | 说明 |
|---|---|---|
| name | string | 插件唯一标识 (snake_case) |
| version | string | 语义版本号 (semver) |
| author | string | 维护者名称 |
| plugin_type | string | spider/processor/storage/presenter/ui |
| input_schema | string | 输入 Schema ID (如 TaskConfigDTO.v1) |
| output_schema | string | 输出 Schema ID (如 RawDataBatch.v1) |
| entry_point | string | Python 模块:类名 (如 plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin) |

## 可选字段

| 字段 | 类型 | 说明 |
|---|---|---|
| dependencies | list[string] | Python 包依赖 |
| min_core_version | string | 最低核心版本要求 |
| config_schema | object | JSON Schema，描述插件接受的 params |
| license | string | 许可证标识 (MIT/Apache-2.0/BSD-3-Clause 等) |
| description | string | 一句话描述 |

## entry_point 格式

```
module.path:ClassName
```

示例：`plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin`

- `module.path` 从项目根目录开始的 Python 模块路径
- `ClassName` 模块中定义的类名
- 类必须继承对应基类（SpiderPlugin/BasePlugin/PresenterPlugin 等）

## config_schema

描述插件接受的 `params` 参数，使用 JSON Schema draft-07：

```json
{
  "type": "object",
  "properties": {
    "max_pages": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
    "delay": {"type": "number", "minimum": 0.5, "maximum": 10.0, "default": 1.5}
  },
  "additionalProperties": false
}
```

设置 `additionalProperties: false` 可以在启动前捕获拼写错误的参数名。

## license 声明

- MIT/Apache-2.0/BSD：直接声明，无额外限制
- GPL/AGPL/LGPL：加载时产生告警（INTERFACES.md 规定），因为可能影响整个项目的分发许可

## 批准流程

1. 开发者提交插件包到 `data/plugin_uploads/`（待审区）
2. 管理员审查代码安全性（AST 黑名单检查）
3. 审查通过后移入正式 `plugins/` 目录
4. 在 `config/plugins.yaml` 声明实例

**红线**：待审区插件不参与自动发现、不 import、不执行。
