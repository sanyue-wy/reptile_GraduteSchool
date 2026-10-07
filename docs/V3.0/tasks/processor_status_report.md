# Processor 插件状态诊断与修复报告

> 生成时间：2026-09-21
> 诊断脚本：`scripts/_diagnose_processors.py`
> 任务来源：W9 复验报告与任务卡（W5_processors.md）不一致排查

---

## 1. 诊断结论

**命中分支：C（插件完整，仅需微调 1 处类属性不一致）**

- `plugins/processors/` 下共有 **10 个** processor 类插件目录
- `loader.scan_plugin_dirs("plugins")` 成功识别全部 **10 个** processor 插件
- 所有插件的 `metadata.json` 必填字段齐全（含 `license: MIT`、`min_core_version`、`author` 等）
- **8 个核心插件**（W5 任务卡 6 个 + `parser_fallback` + `error_analyzer`）均正确继承中间基类：
  - **ParserPlugin**（parse 阶段：`RawDataBatch → RecordBatch`）：`faculty_parser`、`yzw_major_parser`、`parser_fallback`
  - **RecordProcessorPlugin**（post 阶段：`RecordBatch → RecordBatch`）：`normalize`、`dedup`、`education_merge`、`statistics`、`error_analyzer`
- **2 个前置插件**（pre-acquire 阶段：`TaskConfigDTO → TaskConfigDTO`）：`url_normalizer`、`domain_rewriter` 直接继承 `BasePlugin`，符合架构设计（无专用中间基类）
- 修复项：`yzw_major_parser` 类属性 `plugin_type` 由 `"parser"` 改为 `"processor"`，与 `metadata.json` 保持一致

---

## 2. 诊断证据

### 2.1 目录结构（第 1 步输出）

```
plugins/processors 目录存在，子目录 (10 个):
['dedup', 'domain_rewriter', 'education_merge', 'error_analyzer',
 'faculty_parser', 'normalize', 'parser_fallback', 'statistics',
 'url_normalizer', 'yzw_major_parser']
```

### 2.2 Loader 接口签名（第 2 步输出）

```
loader.scan_plugin_dirs 签名:
(plugins_root: 'Path | None' = None, upload_root: 'Path | None' = None) 
-> 'tuple[list[PluginDescriptor], list[str], list[str]]'
```

> **修正 W9 报告**：W9 使用了不存在的 `PluginLoader().scan()` 接口。实际 loader 暴露的是模块级函数 `scan_plugin_dirs` / `scan_metadata` / `scan_with_error_markers`。

### 2.3 Loader 扫描识别的 10 个 processor 插件（第 3 步输出）

| 插件名 | version | min_core_version | license | input_schema | output_schema | entry_point |
|--------|---------|------------------|---------|--------------|---------------|-------------|
| dedup | 1.0.0 | 3.0.0 | MIT | RecordBatch.v1 | RecordBatch.v1 | plugins.processors.dedup.plugin:DedupPlugin |
| domain_rewriter | 1.0.0 | 1.0.0 | MIT | TaskConfigDTO.v1 | TaskConfigDTO.v1 | plugins.processors.domain_rewriter.plugin:DomainRewriterProcessor |
| education_merge | 1.0.0 | 3.0.0 | MIT | RecordBatch.v1 | RecordBatch.v1 | plugins.processors.education_merge.plugin:EducationMergePlugin |
| error_analyzer | 1.0.0 | 1.0.0 | MIT | RecordBatch.v1 | RecordBatch.v1 | plugins.processors.error_analyzer.plugin:ErrorAnalyzerPlugin |
| faculty_parser | 1.0.0 | 3.0.0 | MIT | RawDataBatch.v1 | RecordBatch.v1 | plugins.processors.faculty_parser.plugin:FacultyParserPlugin |
| normalize | 1.0.0 | 3.0.0 | MIT | RecordBatch.v1 | RecordBatch.v1 | plugins.processors.normalize.plugin:NormalizePlugin |
| parser_fallback | 1.0.0 | 1.0.0 | MIT | RawDataBatch.v1 | RecordBatch.v1 | plugins.processors.parser_fallback.plugin:ParserFallbackPlugin |
| statistics | 1.0.0 | 3.0.0 | MIT | RecordBatch.v1 | RecordBatch.v1 | plugins.processors.statistics.plugin:StatisticsPlugin |
| url_normalizer | 1.0.0 | 1.0.0 | MIT | TaskConfigDTO.v1 | TaskConfigDTO.v1 | plugins.processors.url_normalizer.plugin:UrlNormalizerProcessor |
| yzw_major_parser | 1.0.0 | 3.0.0 | MIT | RawDataBatch.v1 | RecordBatch.v1 | plugins.processors.yzw_major_parser.plugin:YzwMajorParserPlugin |

> 无告警、无错误。

### 2.4 兜底扫描 metadata.json（第 4 步输出）

遍历 `plugins/**/metadata.json`，统计 `plugin_type == "processor"` 条目：**10 个**，与 loader 识别结果完全一致，无遗漏。

### 2.5 MRO 继承链检查（第 5 步输出）

| 插件 | MRO 前 3 项 | 继承中间基类 | 判定 |
|------|-------------|-------------|------|
| dedup | `DedupPlugin` → `RecordProcessorPlugin` → `BasePlugin` | ✅ RecordProcessorPlugin | 正确 |
| domain_rewriter | `DomainRewriterProcessor` → `BasePlugin` → `object` | （无中间基类） | 正确（pre-acquire 特殊类型） |
| education_merge | `EducationMergePlugin` → `RecordProcessorPlugin` → `BasePlugin` | ✅ RecordProcessorPlugin | 正确 |
| error_analyzer | `ErrorAnalyzerPlugin` → `RecordProcessorPlugin` → `BasePlugin` | ✅ RecordProcessorPlugin | 正确 |
| faculty_parser | `FacultyParserPlugin` → `ParserPlugin` → `BasePlugin` | ✅ ParserPlugin | 正确 |
| normalize | `NormalizePlugin` → `RecordProcessorPlugin` → `BasePlugin` | ✅ RecordProcessorPlugin | 正确 |
| parser_fallback | `ParserFallbackPlugin` → `ParserPlugin` → `BasePlugin` | ✅ ParserPlugin | 正确 |
| statistics | `StatisticsPlugin` → `RecordProcessorPlugin` → `BasePlugin` | ✅ RecordProcessorPlugin | 正确 |
| url_normalizer | `UrlNormalizerProcessor` → `BasePlugin` → `object` | （无中间基类） | 正确（pre-acquire 特殊类型） |
| yzw_major_parser | `YzwMajorParserPlugin` → `ParserPlugin` → `BasePlugin` | ✅ ParserPlugin | 正确（修复后） |

---

## 3. 修复动作

### 3.1 修复前对比（仅 1 处变更）

**文件**：`plugins/processors/yzw_major_parser/plugin.py`  
**行号**：141

| 项目 | 修复前 | 修复后 |
|------|--------|--------|
| `plugin_type` 类属性 | `"parser"` | `"processor"` |

**原因**：`metadata.json` 中声明 `"plugin_type": "processor"`，类属性应与之保持一致，避免运行时元数据不一致。Loader 读取的是 `metadata.json`，但插件实例的 `metadata` property 会读取类属性。

### 3.2 无需修改的插件

- `url_normalizer`、`domain_rewriter`：pre-acquire 处理器，input/output 均为 `TaskConfigDTO`，无对应中间基类，直接继承 `BasePlugin` 符合设计
- 其余 8 个核心插件：继承关系、字段声明、metadata.json 均完整正确

---

## 4. 验证结果

### 4.1 诊断脚本复跑

```bash
python scripts/_diagnose_processors.py
```
**结果**：processor 总数 = 10，全部通过 MRO 校验，loader 识别无错误无告警。

### 4.2 单元测试全量通过

```bash
python -m pytest tests/test_processor_plugins.py -q
```
**结果**：
```
============================= test session starts =============================
collected 34 items
tests\test_processor_plugins.py ..................................       [100%]
============================= 34 passed in 0.76s ==============================
```
覆盖：faculty_parser(6)、yzw_major_parser(5)、normalize(7)、dedup(4)、education_merge(6)、statistics(4)、ProcessorChain(2)

### 4.3 metadata.json 必填字段完整性检查

```bash
python -c "
import json
from pathlib import Path
required = {'name','version','plugin_type','input_schema','output_schema',
            'author','license','min_core_version'}
bad = []
for m in Path('plugins/processors').rglob('metadata.json'):
    d = json.loads(m.read_text(encoding='utf-8'))
    missing = required - set(d.keys())
    if missing:
        bad.append((str(m), missing))
print('缺失字段的插件:', bad if bad else '无')
"
```
**结果**：`缺失字段的插件: 无` —— 10 个插件的 metadata.json 均包含全部 8 个必填字段。

---

## 5. 对 W9 报告的修正说明

| W9 报告内容 | 实际情况 | 修正依据 |
|-------------|----------|----------|
| 称 processor 插件有 **2 个** | 实际 **10 个**（loader 识别） | W9 使用了不存在的 `PluginLoader().scan()` 接口；实际应用 `loader.scan_plugin_dirs("plugins")` |
| 使用接口 `PluginLoader().scan()` | 该类/方法不存在 | `plugin_manager/loader.py` 暴露的是模块级函数：`scan_plugin_dirs`、`scan_metadata`、`scan_with_error_markers` |
| 未区分 parse/post/pre-acquire 阶段 | 10 个插件分属 3 类阶段 | 依据 `INTERFACES.md §3.3-3.4`：ParserPlugin(parse)、RecordProcessorPlugin(post)、BasePlugin(pre-acquire) |

**W9 报告应修正为**：
- processor 插件总数：10 个
- 其中 W5 任务卡预期的 8 个核心插件（6 个 W5 任务 + parser_fallback + error_analyzer）均已实现、字段齐全、继承正确
- 额外 2 个 pre-acquire 插件（url_normalizer、domain_rewriter）已就位，配合 pipeline.yaml pre_acquire 阶段使用

---

## 6. 是否建议 W1 合并签字

**建议：✅ 同意合并签字**

理由：
1. 所有 10 个 processor 插件代码完整、字段齐全、继承关系正确
2. 单元测试 34/34 全绿，集成测试 `test_static_slice.py` 亦通过
3. 仅修复 1 处类属性不一致（`yzw_major_parser.plugin_type`），无破坏性变更
4. 未修改 contracts/**、pipeline/**、plugins/base.py、其他插件组，符合“禁止修改 W1–W9 既有交付物”约束
5. 诊断脚本可复现、输出稳定，作为后续回归依据

---

## 附录：进度登记

> 将在 `docs/V3.0/tasks/progress.md` 追加：
> ```
> Diagnose Agent 完成 processor 状态诊断与修复，命中分支 C，
> processor 实际数量 10（核心 8 + 前置 2），详见 docs/V3.0/tasks/processor_status_report.md
> ```