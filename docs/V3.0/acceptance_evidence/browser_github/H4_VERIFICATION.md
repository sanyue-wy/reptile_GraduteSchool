# H4 窗口复核报告 — V3.0 闭环补全第二批修复

> **复核窗口**: 独立证伪窗口（H4_VERIFICATION）
> **复核时间**: 2026-10-07
> **被复核对象**: H4 窗口报告 (docs/V3.0/acceptance_evidence/browser_github/H4_REPORT.md)
> **复核方法**: 读取文件、运行只读命令、对比代码与文档断言

---

## 复核结论: ❌ **REFUTED**

**核心判定理由**: H4 报告包含**多处失实/过期断言**，将陈旧测量数据作为当前可复算事实呈现，且对 `.gitignore` 现状描述与实际工作区不符。文档声称「已修正」的表述在代码层面并未真正落地或已过期。

---

## 1. 关键命令实测与 H4 报告对比

### 1.1 `.gitignore` 第 15 行内容

| 维度 | H4 报告声称 | 实际工作区 (HEAD) | 实际提交态 (HEAD) |
|------|-------------|-------------------|-------------------|
| `cat .gitignore | sed -n '15p'` | `*preview.png` | `# preview.png 仅忽略根目录下的临时预览图...` (注释行) | `*preview.png` |
| 第 16 行 | 未提及 | `/preview.png` | (不存在，原第 16 行为空或后续内容) |
| 第 25 行 | 未提及 | `/*.png` | (不存在) |

**实测输出**:
```bash
$ cat .gitignore | sed -n '15p'
# preview.png 仅忽略根目录下的临时预览图，避免误伤 templates/*/preview.png 等正式模板预览

$ git show HEAD:.gitignore | sed -n '15p'
*preview.png
```

**判定**: H4 报告引用的命令输出对应 **提交态 (HEAD)**，而非 **当前工作区**。报告未明确区分两者，导致「H3 正在修正」的表述产生歧义——工作区已修正（第 15 行变注释、第 16 行成 `/preview.png`、第 25 行增 `/*.png`），但未提交。干净克隆将获得旧规则 `*preview.png`，H4 关于「干净克隆无 preview.png」的结论虽正确，但证据链混淆了工作区与提交态。

### 1.2 `git ls-files templates/*/preview.png`

| 维度 | H4 报告 | 实测 |
|------|---------|------|
| 输出 | 空 (无输出) | 空 (无输出) |

**判定**: 一致。20 个 preview.png 均未入库。

### 1.3 `grep -r "validate_domain_kb" --include="*.py" .`

| 维度 | H4 报告 | 实测 |
|------|---------|------|
| 结果 | 仅定义处与 `__all__` 导出 | 仅 `plugin_manager/validator.py:303` 导出、`plugin_manager/validator.py:369` 定义 |

**判定**: 一致。全仓**无调用方**，无插件声明 `depends_on: ["domain_kb"]`。H4 登记为「已知偏差」属实。

### 1.4 `grep -r "depends_on.*domain_kb" --include="*.py" --include="*.json" --include="*.yaml" .`

| 维度 | H4 报告 | 实测 |
|------|---------|------|
| 结果 | 空输出 | 仅 `plugin_manager/validator.py:372` 注释行 `供插件依赖 depends_on: ["domain_kb"] 时使用。` |

**判定**: 一致。无实际依赖声明。

### 1.5 `ls templates/minimal-light/`

| 维度 | H4 报告 | 实测 |
|------|---------|------|
| 结果 | `layout.html style.css variables.json preview.png` | `layout.html preview.png style.css variables.json` |

**判定**: 一致。工作区含文件。

### 1.6 `python -c "import json; r=json.load(open('templates/registry.json',encoding='utf-8')); print(len(r['templates']))"`

| 维度 | H4 报告 | 实测 |
|------|---------|------|
| 结果 | 20 | 20 |

**判定**: 一致。

### 1.7 `python -m pytest tests/ -q --ignore=tests/integration` **【关键差异】**

| 维度 | H4 报告 (G4 2026-10-01) | 实测 (2026-10-07) |
|------|--------------------------|-------------------|
| 收集用例数 | ~958 (隐含) | **1035** |
| 通过数 | **955** | **1030** |
| 跳过数 | **3** | **4** |
| 失败数 | **0** | **1** |
| 耗时 | 20.36s | **101.61s** |

**实测完整输出**:
```
collected 1035 items
...
FAILED tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list
...
1 failed, 1030 passed, 4 skipped in 101.61s
```

**失败用例详情**:
```
tests/test_api_closed_loop_g2.py:158: AssertionError: errors keys ['pipeline:stage:acquire:test_source'] 不与 plugins keys [...] 交集
```

**判定**: **H4 报告严重失实**。H4 将 6 天前的陈旧测量 (955 passed, 3 skipped, 0 failed) 作为「当前可复算的表述」呈现，但实际测试集已显著膨胀 (+77 collected)，且**出现 1 个失败用例**。H4 声称的「回归测试全绿」在当前代码库**不成立**。

> ⚠️ 该失败用例涉及错误键与插件列表交集断言，属于现有测试逻辑与当前插件注册不一致，非 H4 引入，但 H4 不应将过期绿标作为现状引用。

---

## 2. 阻断项 B1–B5 复核逐项确认

### B1: 4 个中间基类缺失

| 子项 | H4 记录 | 代码实测 | 判定 |
|------|---------|----------|------|
| 类是否存在 | ✅ 已补齐 (第 205/215/225/235 行) | `plugins/base.py` 确有 4 类 | ✅ 成立 |
| `ParserPlugin.plugin_type` | ⚠️ `"parser"` 与契约 §3.3 `"processor"` 冲突 | 代码第 210 行 `plugin_type = "parser"`；INTERFACES.md §3.3 第 293 行 `"processor"`；`PLUGIN_TYPES` 无 `"parser"` | ✅ 冲突确认 |
| `parser_fallback` 插件自相矛盾 | ⚠️ 类属性 `"parser"` vs metadata.json `"processor"` | `plugin.py:77` 类属性 `"parser"`；`metadata.json:6` `"processor"` | ✅ 确认 |
| `StoragePlugin`/`UIPlugin` 零继承 | ⚠️ 5 个 storage、4 个 UI 全直继 `BasePlugin` | 全部 `class XxxPlugin(BasePlugin[...])`，未继承中间基类 | ✅ 确认 |

**结论**: H4 记录准确，**遗留问题真实存在**，未被粉饰为完全闭环。

### B2: PresenterPlugin 契约未对齐

| 维度 | H4 记录 | 代码实测 | 判定 |
|------|---------|----------|------|
| `input_schema`/`output_schema` | ✅ 已声明 | `plugins/base.py:149-150` 确有 | ✅ 成立 |
| `execute()` 具体方法 | ✅ 保留具体实现 | 符合 INTERFACES.md §3.6 设计决议 | ✅ 成立 |

**结论**: H4 记录准确，节号引错已更正。

### B3: RawDataDTO assets 未入 required

| 维度 | H4 记录 | 代码实测 | 判定 |
|------|---------|----------|------|
| `contracts/raw.py:74` required 列表 | ✅ 已含 `assets` | 实测 required 含 `assets`，与 §2.4 一致 | ✅ 完全成立 |

### B4: markdown 格式分发无 fallback

| 维度 | H4 记录 | 代码/配置实测 | 判定 |
|------|---------|---------------|------|
| `_FORMAT_FALLBACK` 映射 | ✅ 代码已修复 | `present.py:30-32` 含 `{"markdown": "markdown_presenter"}` | ✅ 代码层面成立 |
| `markdown_presenter` 插件存在 | ✅ 存在且可加载 | `plugins/presenters/markdown_presenter/` 存在，metadata.json 含 license | ✅ 成立 |
| `config/plugins.yaml` 声明实例 | ⚠️ **缺失** | 5 个 presenter 实例中**无 `markdown_presenter`** | ✅ 配置层面缺失确认 |
| 真实配置下分发可达性 | ⚠️ 不可达 | `PluginResolver` 仅加载配置声明的实例，`presenter_map` 为空 | ✅ 遗留确认 |

**结论**: H4 记录准确，**配置缺失导致真实环境不可用**属实。

### B5: PDF XSS 转义 no-op

| 维度 | H4 记录 | 代码实测 | 判定 |
|------|---------|----------|------|
| 修复方式 | ✅ `html_mod.escape(value, quote=True)` | `pdf_presenter/plugin.py:246` 确已替换旧 replace 链 | ✅ 完全成立 |

---

## 3. 文档边界合规性复核

| 检查项 | H4 声称 | 实测 | 判定 |
|--------|---------|------|------|
| 未修改 `contracts/` | ✅ 无修改 | `git diff HEAD -- contracts/` 空输出 | ✅ 成立 |
| 未修改 `docs/V3.0/INTERFACES.md` | ✅ 无修改 | `git diff HEAD -- docs/V3.0/INTERFACES.md` 空输出 | ✅ 成立 |
| 仅修改 `docs/` 与 `CHANGELOG.md` | ✅ 符合范围 | 变更文件: `acceptance.md`, `plugin_dev_guide/01_platform_overview.md` | ✅ 成立 |

---

## 4. 发现的 H4 报告缺陷

### 4.1 测试回归数字严重过期 (Critical)

- **位置**: H4_REPORT.md 第 167 行、第 137-168 节「关键命令输出记录」
- **问题**: 引用 G4 2026-10-01 测量 (955 passed, 3 skipped) 作为「当前可复算表述」
- **实测**: 2026-10-07 为 1030 passed, 4 skipped, **1 failed** (1035 collected)
- **影响**: 误导决策者认为回归测试全绿，实则有失败用例且规模显著变化

### 4.2 `.gitignore` 状态描述混淆工作区与提交态 (Major)

- **位置**: H4_REPORT.md 第 30-40 行、第 141-142 行
- **问题**: 命令输出展示提交态 (`*preview.png`)，叙述却称「H3 正在修正」，暗示工作区未修正
- **实情**: 工作区已修正 (第 15 行注释、第 16 行 `/preview.png`、第 25 行 `/*.png`)，仅未提交
- **影响**: 证据链不清，第三方无法复现「当前状态」

### 4.3 `plugin_dev_guide/01_platform_overview.md:74` 修正同步了错误信息 (Major)

- **位置**: `docs/plugin_dev_guide/01_platform_overview.md` 第 74 行
- **现文**: `preview.png 存在于工作区但被 .gitignore 原规则 *preview.png 命中`
- **问题**: 工作区 `.gitignore` **不再含** `*preview.png` 规则 (已改为 `/preview.png` + `/*.png`)，原规则仅存在于提交态
- **影响**: 文档修正引入了新的不准确描述

### 4.4 CHANGELOG.md 核对结论过于乐观 (Minor)

- **位置**: H4_REPORT.md 第 100-109 行
- **问题**: 称「无需补记——现有记录完整」
- **实测**: `[Unreleased]` 节未记录：
  - `tests/browser/` 新增数十用例 (2026-10-01 后)
  - `test_api_closed_loop_g2.py` 新增失败用例
  - `.gitignore` 修正 (工作区未提交)
  - B1/B4 遗留问题的最新状态
- **影响**: 变更日志不完整

---

## 5. acceptance.md 中 H4 修正部分的实测验证

| acceptance.md 位置 | H4 修正内容 | 实测结论 |
|-------------------|-------------|----------|
| 第 103-106 行 (实验 C) | preview.png 表述修正 | **部分准确** — 结论正确但 .gitignore 规则描述引用提交态非工作区 |
| 第 17/31/198/208 行 (L3 数字) | 标注 ⚠️ 未复验 | **必要且正确** — 但 H4 自身报告又引用过期数字作为「当前可复算」 |
| §4 第 13 项 (validate_domain_kb) | 登记为已知偏差 | **准确** — 代码确无调用方，契约冻结不可改 |
| §7.1 B1/B4 遗留记录 | 逐项记录遗留 | **准确** — 代码确认遗留真实存在 |

---

## 6. 综合判定

| 维度 | 评分 | 说明 |
|------|------|------|
| 事实准确性 | ❌ **不通过** | 核心测试数据过期失实，.gitignore 状态描述混淆 |
| 遗留问题登记诚实度 | ✅ 通过 | B1/B4 遗留如实记录，未粉饰 |
| 边界合规 | ✅ 通过 | 未越权修改 contracts/ 与 INTERFACES.md |
| 文档自洽性 | ❌ **不通过** | 报告内部引用过期数据与自身修正的 acceptance.md 矛盾 |

**最终 Verdict: REFUTED**

> H4 窗口报告**不能作为可信验收证据**。其核心缺陷是将 6 天前的测量快照作为当前事实呈现，掩盖了测试集膨胀与新增失败的现实。文档修正虽修复了部分 acceptance.md 表述，但自身引入了新的不准确描述 (.gitignore 规则、plugin_dev_guide 同步错误)。建议：
> 1. 重新运行全量回归测试并记录真实当前口径
> 2. 修正 `.gitignore` 描述区分提交态与工作区
> 3. 补记 CHANGELOG 缺失项
> 4. 同步修正 plugin_dev_guide 中的 .gitignore 规则描述

---

## 附录: 复核执行的完整命令记录

```bash
# .gitignore 状态
$ cat .gitignore | sed -n '15p'
# preview.png 仅忽略根目录下的临时预览图，避免误伤 templates/*/preview.png 等正式模板预览

$ git show HEAD:.gitignore | sed -n '15p'
*preview.png

$ git status .gitignore
Changes not staged for commit: modified: .gitignore

# preview.png 入库状态
$ git ls-files templates/*/preview.png
# (空输出)

$ ls templates/minimal-light/
layout.html  preview.png  style.css  variables.json

# validate_domain_kb 调用方
$ grep -r "validate_domain_kb" --include="*.py" .
./plugin_manager/validator.py:    "validate_domain_kb",
./plugin_manager/validator.py:def validate_domain_kb(kb_path: Path | None = None) -> ValidationResult:

# depends_on domain_kb
$ grep -r "depends_on.*domain_kb" --include="*.py" --include="*.json" --include="*.yaml" .
./plugin_manager/validator.py:    供插件依赖 `depends_on: ["domain_kb"]` 时使用。

# 模板注册表
$ python -c "import json; r=json.load(open('templates/registry.json',encoding='utf-8')); print(len(r['templates']))"
20

# 回归测试 (当前真实口径)
$ python -m pytest tests/ -q --ignore=tests/integration
collected 1035 items
...
FAILED tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list
...
1 failed, 1030 passed, 4 skipped in 101.61s

# ParserPlugin plugin_type
$ grep -A2 "class ParserPlugin" plugins/base.py
class ParserPlugin(BasePlugin[RawDataBatch, RecordBatch]):
    plugin_type = "parser"

# INTERFACES.md §3.3
$ grep -A5 "### 3.3 ParserPlugin" docs/V3.0/INTERFACES.md
class ParserPlugin(BasePlugin[RawDataBatch, RecordBatch]):
    plugin_type = "processor"

# PLUGIN_TYPES
$ grep "PLUGIN_TYPES" plugin_manager/loader.py
PLUGIN_TYPES = ("spider", "processor", "storage", "presenter", "ui")

# StoragePlugin/UIPlugin 继承情况
$ grep "class.*Plugin.*BasePlugin" plugins/storage/*/plugin.py plugins/ui/*/plugin.py
plugins/storage/jsonl_store/plugin.py:class JsonlStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
plugins/storage/media_store/plugin.py:class MediaStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
plugins/storage/progress_store/plugin.py:class ProgressStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
plugins/storage/sql_store/plugin.py:class SqlStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
plugins/storage/xlsx_store/plugin.py:class XlsxStorePlugin(BasePlugin[StoreRequest, StoreReceipt]):
plugins/ui/card_component/plugin.py:class CardComponentPlugin(BasePlugin[ViewModel, UIComponentDTO]):
plugins/ui/chart_component/plugin.py:class ChartComponentPlugin(BasePlugin[ViewModel, UIComponentDTO]):
plugins/ui/filter_component/plugin.py:class FilterComponentPlugin(BasePlugin[ViewModel, UIComponentDTO]):
plugins/ui/table_component/plugin.py:class TableComponentPlugin(BasePlugin[ViewModel, UIComponentDTO]):

# markdown_presenter 配置
$ grep "markdown_presenter" config/plugins.yaml
# (无输出)

$ ls plugins/presenters/markdown_presenter/
metadata.json  plugin.py

# PDF XSS 修复
$ grep -A2 "Escape HTML" plugins/presenters/pdf_presenter/plugin.py
value = str(record.get(field, ""))
# Escape HTML entities (& < > " ')
value = html_mod.escape(value, quote=True)
```

---

*复核完成: 2026-10-07*
*独立证伪窗口 H4_VERIFICATION*