# -*- coding: utf-8 -*-
"""Loader 协议：生成物应满足的发现/校验约定。

纯文档 + 常量，不含 CLI（CLI 归 W8）。
脚手架生成的插件包必须满足以下规范才能被 plugin_manager 发现和加载。
"""

# ── metadata.json 必须字段 ──

REQUIRED_METADATA_FIELDS = (
    "name",
    "version",
    "author",
    "plugin_type",
    "input_schema",
    "output_schema",
    "entry_point",
)

OPTIONAL_METADATA_FIELDS = (
    "dependencies",
    "min_core_version",
    "config_schema",
    "license",
    "description",
)

# ── 插件类型 → 目录名 ──

PLUGIN_TYPE_TO_DIR = {
    "spider": "spiders",
    "processor": "processors",
    "storage": "storage",
    "presenter": "presenters",
    "ui": "ui",
}

# ── 目录名 → 插件类型 ──

DIR_TO_PLUGIN_TYPE = {v: k for k, v in PLUGIN_TYPE_TO_DIR.items()}

# ── entry_point 格式 ──
#
# 格式：module.path:ClassName
# 示例：plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin
#
# - module.path 是从项目根目录开始的 Python 模块路径
# - ClassName 是模块中定义的类名
# - 类必须继承 BasePlugin 的适当子类

ENTRY_POINT_FORMAT = "module.path:ClassName"

# ── metadata.json 示例 ──

METADATA_EXAMPLE = {
    "name": "my_plugin",
    "version": "1.0.0",
    "author": "developer",
    "plugin_type": "spider",
    "input_schema": "TaskConfigDTO.v1",
    "output_schema": "RawDataBatch.v1",
    "entry_point": "plugins.spiders.my_plugin.plugin:MyPlugin",
    "dependencies": [],
    "min_core_version": "3.0.0",
    "config_schema": {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    "license": "MIT",
    "description": "A short description of what this plugin does.",
}

# ── 目录结构约定 ──
#
# plugins/
#   {type_dir}/           # spiders, processors, storage, presenters, ui
#     {plugin_name}/      # 插件包目录
#       __init__.py       # 包初始化（可为空）
#       metadata.json     # 必须：插件元数据
#       plugin.py         # 推荐：主插件类
#       ...               # 其他源文件
#
# 加载器扫描规则：
# 1. 遍历 plugins/ 下的 {type_dir}/ 子目录
# 2. 每个 {plugin_name}/ 必须包含 metadata.json
# 3. metadata.json 的 plugin_type 必须与 type_dir 匹配
# 4. entry_point 的 module 路径必须可达
# 5. 源文件通过 AST 黑名单检查（BLOCKED_MODULES/BLOCKED_CALLS）
# 6. 待审区 data/plugin_uploads/ 的包不参与发现

# ── Schema ID 注册表 ──
#
# 新领域 schema 随插件包声明并注册，不修改核心 contracts/。
# 以下为 INTERFACES.md §7 冻结的核心 Schema ID：
#
# TaskConfigDTO.v1, TaskRunState.v1, OutputSpec.v1,
# RawDataDTO.v1, RawDataBatch.v1,
# NormalizedRecordDTO.v1, RecordBatch.v1,
# PresentationRequest.v1, RenderedOutputDTO.v1,
# ViewModel.v1, UIComponentDTO.v1,
# StoreRequest.v1, StoreReceipt.v1,
# StageResult.v1, RunResult.v1, ErrorDTO.v1,
# MediaAsset.v1, AssetRef.v1,
# education.tutor.v1, education.major.v1

# ── 插件类型 → 输入/输出 Schema 约定 ──

PLUGIN_TYPE_SCHEMAS = {
    "spider": {
        "input_schema": "TaskConfigDTO.v1",
        "output_schema": "RawDataBatch.v1",
        "base_class": "SpiderPlugin",
    },
    "processor": {
        "input_schema": "RawDataBatch.v1",  # parse 阶段
        "output_schema": "RecordBatch.v1",
        "base_class": "ParserPlugin",
        "alt": {
            "input_schema": "RecordBatch.v1",  # post 阶段
            "output_schema": "RecordBatch.v1",
            "base_class": "RecordProcessorPlugin",
        },
    },
    "storage": {
        "input_schema": "StoreRequest.v1",
        "output_schema": "StoreReceipt.v1",
        "base_class": "StoragePlugin",
    },
    "presenter": {
        "input_schema": "PresentationRequest.v1",
        "output_schema": "RenderedOutputDTO.v1",
        "base_class": "PresenterPlugin",
    },
    "ui": {
        "input_schema": "ViewModel.v1",
        "output_schema": "UIComponentDTO.v1",
        "base_class": "UIPlugin",
    },
}

__all__ = [
    "REQUIRED_METADATA_FIELDS",
    "OPTIONAL_METADATA_FIELDS",
    "PLUGIN_TYPE_TO_DIR",
    "DIR_TO_PLUGIN_TYPE",
    "ENTRY_POINT_FORMAT",
    "METADATA_EXAMPLE",
    "PLUGIN_TYPE_SCHEMAS",
]
