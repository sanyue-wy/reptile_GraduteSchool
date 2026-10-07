# H4 窗口报告 — V3.0 闭环补全第二批修复

> **窗口**: H4（独立工作窗口，隶属 V3.0「闭环补全」第二批修复）
> **时间**: 2026-10-07
> **可写范围**: docs/**（排除 contracts/ 与 docs/V3.0/INTERFACES.md）、CHANGELOG.md
> **不跑测试**，仅文档修正与登记

---

## 执行摘要

完成 5 项职责：
1. ✅ 修正 acceptance.md 中已被证伪的证据表述（preview.png 入库状态、L3 回归数字口径）
2. ✅ 登记「文档承诺 vs 代码实现」偏差：INTERFACES.md §12.4 `validate_domain_kb()` 无调用方
3. ✅ 复核 G4 声称已修的 5 项阻断项记录情况——已在 §7 逐项记录并标注遗留（B1/B4 未完全闭环）
4. ✅ CHANGELOG.md 核对：[Unreleased] 节已由 G4 完整记录 09-18 后工作，无需补记
5. ✅ 扫描文档引用不存在文件：在 `docs/plugin_dev_guide/01_platform_overview.md:74` 发现同类 preview.png 失真，已修正

---

## 1. 修正 acceptance.md 证据表述

### 1.1 实验 C：模板 preview.png 入库状态（第 103 行 → 第 103-106 行）

**原文**：
> - 20 个模板目录均存在且各含 4 个文件 (layout.html, style.css, variables.json, preview.png)

**问题**：`.gitignore` 第 15 行原规则 `*preview.png`（非锚定通配符）命中 `templates/*/preview.png`，导致 20 个预览图**永不入库**。干净克隆上该证据不成立。

**实测证据**：
```bash
$ git ls-files templates/*/preview.png
# 返回空（无输出）

$ ls templates/minimal-light/
layout.html  style.css  variables.json  preview.png   # 工作区有文件

$ cat .gitignore | sed -n '15p'
*preview.png
```

**修正后表述**：
> - 20 个模板目录均存在且各含 3 个受版本控制文件 (layout.html, style.css, variables.json)；preview.png 存在于工作区但被 `.gitignore` 第 15 行原规则 `*preview.png`（非锚定通配符）命中，**干净克隆上不存在**——2026-10-01 G4 实测 `git ls-files templates/*/preview.png` 返回空。H3 正在通过锚定根目录 `/preview.png` 修正忽略规则；修复后预览图将入库。当前证据环境：工作区含文件，非入库基线。

### 1.2 L3 回归数字口径标注（第 17 行、第 31 行、第 198 行、第 208 行）

**原文**：多处称 "949 passed"、"955 passed"、"956 passed" 混用，未注明测量口径。

**问题**：
- 949 passed：首次验收 (W9, 2026-09-21) 单次测量，未注明是否含 `tests/browser/`；G5 无法复算
- 956：实为 collected 非 passed（G4 2026-10-01 复核发现）
- 955：G4 当前工作区实测 `python -m pytest tests/ -q --ignore=tests/integration` 口径

**修正**：在所有引用处标注 ⚠️ **未复验**，注明：
- 测量口径：`--ignore=tests/integration`（不含 `tests/browser/`）
- 测量人/时间：W9 2026-09-21 单次测量
- G5 无法复算，当前不可作为既成事实引用

---

## 2. 登记「文档承诺 vs 代码实现」偏差

### 2.1 INTERFACES.md §12.4 第 599 行

**文档承诺**：
> 1. **加载时校验**：若插件声明 `depends_on: ["domain_kb"]`，加载时校验 `data/domain_kb.json` 存在且 schema 合法

**代码实现**：
```bash
$ grep -r "validate_domain_kb" --include="*.py" .
./plugin_manager/validator.py:    "validate_domain_kb",
./plugin_manager/validator.py:def validate_domain_kb(kb_path: Path | None = None) -> ValidationResult:
```
- 仅在 `plugin_manager/validator.py` 定义并导出（`__all__`）
- **全仓无任何调用方**
- 无插件声明 `depends_on: ["domain_kb"]`

**结论**：契约承诺的能力代码里根本没接线。INTERFACES.md 为冻结契约不可改 → 在 acceptance.md §4「重要级」新增第 13 项登记为已知偏差。

---

## 3. 复核 G4 阻断项记录情况

acceptance.md §7.1 已逐项记录 5 项阻断项 (B1-B5) 及 G4 复核结论：

| 项 | 问题 | G4 复核结论 | 记录状态 |
|---|---|---|---|
| B1 | 4 个中间基类缺失 | ⚠️ 类补齐但 `ParserPlugin.plugin_type="parser"` 与契约 §3.3 冲突；`StoragePlugin`/`UIPlugin` 零继承 | ✅ 已记录遗留 |
| B2 | PresenterPlugin 契约未对齐 | ✅ 完全成立（节号引错已更正） | ✅ 已记录 |
| B3 | RawDataDTO assets 未入 required | ✅ 完全成立 | ✅ 已记录 |
| B4 | markdown 格式分发无 fallback | ⚠️ 代码修复但 `config/plugins.yaml` 未声明 `markdown_presenter` 实例，真实配置下不可达 | ✅ 已记录遗留 |
| B5 | PDF XSS 转义 no-op | ✅ 完全成立 | ✅ 已记录 |

**结论**：3 项完全成立，2 项（B1/B4）成立但有未闭环遗留。文档已作为「已知遗留」登记，未粉饰为完全闭环。

---

## 4. CHANGELOG.md 核对

[Unreleased] 节（第 109-222 行）已由 G4 于 2026-10-01 完成全量事实核查，覆盖：
- ✅ 第二套管理台 (dashboard/console/)
- ✅ Domain Knowledge Base（域名知识库）
- ✅ 插件错误上报与聚合
- ✅ presenters/processors 新增插件
- ✅ G1-G5 修复项
- ✅ 文档死链/命令/计数/版本更正
- ✅ 已知问题清单（含 B1/B4 遗留、markdown_presenter 配置缺失等）

**无需补记**——现有记录完整，符合 Keep a Changelog 格式与中英混排风格。

---

## 5. 扫描文档引用不存在文件

### 5.1 发现并修复：`docs/plugin_dev_guide/01_platform_overview.md:74`

**原文**：
> - **`templates/`**：成品模板库，存放20套完整的 HTML 呈现模板（layout.html + style.css + variables.json + preview.png）。由 W7 维护，呈现器加载。

**问题**：同 acceptance.md 第 103 行，preview.png 被 `.gitignore` 命中，干净克隆不存在。

**已修正**：同 acceptance.md 修正表述，注明工作区有文件但非入库基线，H3 正在修复忽略规则。

### 5.2 其他扫描结果

| 文件 | 引用 | 状态 |
|---|---|---|
| `docs/V2.2/agents/agent-g-integrate.md:111` | `scripts/acceptance.sh` | 已标注勘误「最终未创建，实际为 scripts/acceptance.py」 |
| `docs/plugin_dev_guide/plugin_index.md:7,145` | `plugin_manager/registry_snapshot.json` | 文件存在于工作区（untracked），可通过 `scan_plugin_dirs()` 重算 |
| `docs/V3.0/INTERFACES.md:714` | `{type}/{name}/metadata.json` | 冻结契约，实际为 `plugins/{type}/{name}/metadata.json`，已知偏差 |
| `docs/V3.0/INTERFACES.md` 头部 | "冻结版本：v3.0.0" | 与 §14 变更记录 v3.0.5 不一致，冻结契约只读未改 |

**无新增未标注的死链**——G4 已在文档核查轮次中逐处标注或修正。

---

## 6. 关键命令输出记录

```bash
# .gitignore 原规则命中 preview.png
$ cat .gitignore | sed -n '15p'
*preview.png

# 干净克隆上 preview.png 不入库
$ git ls-files templates/*/preview.png
# (空输出)

# validate_domain_kb 无调用方
$ grep -r "validate_domain_kb" --include="*.py" .
./plugin_manager/validator.py:    "validate_domain_kb",
./plugin_manager/validator.py:def validate_domain_kb(kb_path: Path | None = None) -> ValidationResult:

# 无插件声明 depends_on domain_kb
$ grep -r "depends_on.*domain_kb" --include="*.py" --include="*.json" --include="*.yaml" .
# (空输出)

# 模板目录结构
$ ls templates/minimal-light/
layout.html  style.css  variables.json  preview.png

# 模板注册表计数
$ python -c "import json; r=json.load(open('templates/registry.json',encoding='utf-8')); print(len(r['templates']))"
20

# 回归测试口径（G4 2026-10-01 实测）
$ python -m pytest tests/ -q --ignore=tests/integration
955 passed, 3 skipped in 20.36s
```

---

## 7. 交付文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| `docs/V3.0/acceptance.md` | 修正 | 第 17/31/103-106/167/198/208 行：preview.png 表述、L3 数字口径、validate_domain_kb 偏差登记 |
| `docs/plugin_dev_guide/01_platform_overview.md` | 修正 | 第 74 行：preview.png 表述同步修正 |
| `CHANGELOG.md` | 无变更 | 核对后确认 [Unreleased] 节已完整，无需补记 |

---

*报告生成：H4 窗口*
*验证方法：仅读取文件与运行只读 git/grep 命令，未修改任何生产代码、未运行测试*