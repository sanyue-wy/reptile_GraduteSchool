# W8 任务卡：schema_editor / 脚手架 CLI / 开发者文档

## 角色

开发者体验负责人。交付可视化字段编辑器（三预设）、五类插件 + HTML 模板的代码脚手架、十篇开发指南与 MkDocs/mkdocstrings API 文档构建。你的目标度量是计划书首页的三个时间指标：**5 分钟定义任务、30 分钟完成首个插件、约 30 行业务代码起步**——结束时必须实测计时并记录真实结果，不达标就如实写差距。

## 必读（只读这些）

- [README.md](README.md)
- `docs/V3.0/INTERFACES.md`（重点：TaskConfigDTO/OutputSpec、metadata.json 格式、五组插件协议签名、config_schema 约定）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §2.1–2.3（目录职责）、§6.3（配置真值与预检）、§9（依赖引入须记仓库/版本/LICENSE）
- `scaffolds/loader_protocol.py`（W3 维护的交接协议文件；未就位时按本卡"生成物约定"实现并在 progress.md 登记对齐项）

## 可写范围（独占）

```text
schema_editor/**                   # editor.py generator.py presets/{tutor_research,paper_collection,news_monitor}.yaml
scaffolds/cli.py                   # python -m scaffolds.cli new <kind> <name>
scaffolds/generator.py
scaffolds/templates/**             # 五类插件骨架 + HTML 模板骨架（注意：与 templates/ 成品模板库是两回事）
docs/plugin_dev_guide/**           # 十篇指南
docs/api/**                        # mkdocstrings 源页面
mkdocs.yml                         # site_dir 指向独立构建目录（如 docs/_site_build），不与现有 docs 混淆
tests/test_schema_editor.py
tests/test_scaffolds.py
```

**禁止修改**：contracts/、plugins/（但脚手架生成的示例包写到 tests/fixtures/generated_plugin/ 供测试用，不进 plugins/）、templates/（成品模板归 W7）、dashboard/、plugin_manager/。

## 交付清单

### A. schema_editor（三件套产出：任务配置 + JSON Schema + FormSpec）

1. **editor.py**：交互式字段定义（CLI 向导即可，不要求 GUI）：数据集名 → 来源选择 → 字段增删改（名称/类型/必填/描述）→ profile 选择（education 内置或自定义）。
2. **generator.py**：从字段定义产出三份产物：① 任务配置片段（并入 pipeline.yaml/plugins.yaml 的实例条目）② 该 dataset 的 JSON Schema（进受控 schema 注册表命名空间）③ FormSpec（供 W7 task-config.html 渲染表单）。**生成的 YAML 必须经 W1 的配置校验器通过后才算完成**（调 config.validator 实际执行并检查 errors，不是 import 后打印"通过"）。
3. **presets/**：三个预设 yaml——tutor_research（教育导师调研基本组合）、paper_collection（论文收集，非教育领域，验证通用性）、news_monitor（新闻监控）。每个预设跑通"生成→校验→(离线)dry-run 预检"链路。

### B. 脚手架 CLI

`python -m scaffolds.cli new spider|processor|storage|presenter|ui|template <name>`：
- 生成完整插件包：plugin.py（继承对应基类的最小可运行骨架，业务逻辑处留 TODO，**正文 ≤30 行**）、metadata.json（含 license/min_core_version/config_schema 占位）、schemas/（按需）、README.md、requirements.txt（空则省略）、test_plugin.py（一个必过用例：元数据自洽 + execute 返回 schema 合法的空结果）。
- template 子命令：在 templates/ 下生成新模板四件套骨架 + registry.json 追加条目（若 templates/registry.json 被 W7 占用产生冲突 → 生成到临时目录输出 diff，由人合并；走仲裁登记）。
- 红线：脚手架**只生成代码**，不自动安装依赖、不自动启用、不自动批准——生成物默认进入待审状态（对接 W3 生命周期）。
- 生成物约定：目录结构、entry_point 写法、metadata 字段与 W3 loader_protocol 完全一致；tests/test_scaffolds.py 对六类生成物各跑一次"生成→W3 validator 静态校验通过→pytest 单测通过"（validator 未就位时 stub，交付后换真实现重跑）。

### C. 十篇开发指南（docs/plugin_dev_guide/，编号 01–10）

01 平台总览与架构（管道—过滤器、五组插件、数据流图）
02 契约速查（DTO 表、schema ID、错误码——从 INTERFACES.md 摘编并注明以它为准）
03 编写第一个 spider 插件（含 media_downloader 多媒体资产用法）
04 编写 processor（parse vs post 边界、媒体引用追踪）
05 编写 storage 插件（幂等键、回执、原子写、路径锁）
06 编写 presenter 与 UI 组件（execute 唯一入口、renderer manifest、安全文本插入）
07 metadata.json 与批准流程（license 声明、min_core_version、内容摘要）
08 配置系统（pipeline.yaml/plugins.yaml 实例规则、预检、迁移）
09 模板开发（variables.json 约定、ThemeSwitcher 接入）
10 测试与验收（fixture 约定、离线模拟网络、覆盖率要求、进度登记规范）

每篇含可直接复制运行的最小示例；示例代码必须是仓库里真实存在过的（引用实际插件路径），不虚构 API。

### D. MkDocs 文档站

mkdocs.yml：nav 覆盖 plugin_dev_guide 十章 + api 参考；mkdocstrings 生成 contracts/、plugins/base.py、pipeline/、plugin_manager/ 的 API 页；`pip list | findstr mkdocs` 确认依赖已具备再构建，缺依赖 → progress.md 登记，不自行安装；site_dir 独立目录且不提交构建产物（加入 .gitignore 由你提议、W1 落盘）。

## 验收命令

```bash
python -m pytest tests/test_schema_editor.py tests/test_scaffolds.py -q
python -m scaffolds.cli new spider demo_probe && python -m pytest tests/fixtures/generated_plugin -q   # 30 分钟挑战：从敲命令到测试全绿
python -c "from config.validator import validate_all_configs; from config.loader import load_schools_config; r=validate_all_configs(load_schools_config()); assert not r['errors'], r['errors']"
mkdocs build --strict    # 若环境有 mkdocs；否则标记"未验证：依赖缺失"
```

计时实测记录（写进 progress.md）：
- 5 分钟任务定义：从一个 preset 到生成并通过校验的任务配置，记录实际耗时。
- 30 分钟首插件：new 命令 → 填业务字段 → 测试全绿，记录实际耗时与业务代码行数。

## 特别注意

- 文档是最后收尾项：A/B 先做（其他窗口交付时你可能需要更新指南中的示例），C/D 在全接口稳定后定稿；progress.md 标注"初稿/定稿"两态。
- 指南中所有"已实现"表述必须以当时仓库真实状态为准；未交付的能力写"计划中"，不得写成现状（这是本项目文档纪律的红线）。
- scaffolds/templates 与 templates 两个目录在指南 01 中必须显式区分，防止后续开发者混用。
