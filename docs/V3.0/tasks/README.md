# V3.0 多窗口并行执行 · 总览（所有窗口必读）

> 依据：[../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md)（下称"计划书"）。
> 本目录是 8 个并行开发窗口的入口。每个窗口只读本目录的总览 + 自己的任务卡 + 契约登记，**不读完整对话历史、不读其他窗口的任务卡**。

## 0. 开工前置（每个窗口第一天先做，约 15 分钟）

- [ ] 确认工作区干净或已按 §6 建立 worktree；记录基线提交号到 `progress.md`。
- [ ] 通读本文件（约 2 页）+ 自己的任务卡。
- [ ] 跑一次基线测试确认环境可用：`python -m pytest tests/ -q`（预期 532 passed, 1 skipped，见 docs/refactor/acceptance.md）。
- [ ] 若发现任务卡引用路径不存在或与代码不符，**先在 progress.md 记一条"卡面问题"并继续可做的部分**，不要自行改契约。

## 1. 唯一真相源与读取顺序

| 优先级 | 文件 | 说明 |
|---|---|---|
| 1 | [../../refactor/interfaces.md](../../refactor/interfaces.md) | V2.2 冻结契约（当前实现的签名基准），**不得修改** |
| 2 | `docs/V3.0/INTERFACES.md` | V3.0 冻结契约，由 **W1 创建**；W1 完成前其余窗口只能按任务卡内嵌的"契约摘要"先行搭建纯新增文件 |
| 3 | 自己的任务卡 `tasks/Wx_*.md` | 角色、可写范围、交付、验收命令 |
| 4 | 计划书对应章节 | 细节有歧义时回查计划书原文，以计划书为准 |

接口变更规则：任何窗口认为需要改动契约（DTO 字段、BasePlugin 签名、metadata 格式、API 端点），**不得直接改共享文件**，在 `progress.md` 的"待 W1 仲裁"区登记提案 → W1 裁决后更新 INTERFACES.md → 全体按新契约执行。

## 2. 八窗口分工速查

| 窗口 | 角色 | 独占可写范围（生产代码） | 依赖 |
|---|---|---|---|
| W1 | 契约与集成主控 | contracts/、plugins/base.py、config YAML schema、scripts/migrate_config.py、docs/V3.0/ | 无 |
| W2 | 主干管道 | pipeline/、main.py、api/server.py、converters/request_converter.py、converters/view_converter.py | W1 契约 |
| W3 | 插件治理 | plugin_manager/、security/（适配层）、scaffolds/、config/plugins.py | W1 契约 |
| W4 | 采集插件 | plugins/spiders/、converters/raw_converter.py | W1 契约 |
| W5 | 处理器插件 | plugins/processors/ | W1 契约 |
| W6 | 存储插件 | plugins/storage/、infra/storage/、utils/progress.py（门面） | W1 契约 |
| W7 | 呈现器·UI·模板 | plugins/presenters/、plugins/ui/、templates/、dashboard/ | W1 契约 |
| W8 | 编辑器·脚手架 CLI·文档 | schema_editor/、scaffolds/cli.py、scaffolds/generator.py、scaffolds/templates/、docs/plugin_dev_guide/、mkdocs.yml | W1 契约、W3 loader 协议 |

注意两处刻意拆分避免争写：`scaffolds/` 的包骨架与模板归 W8，但"生成物如何被 loader 发现/校验"的协议归 W3；`infra/` 的非 storage 文件（context/http/cache/errors）**归 W2**（因为引擎和 context 是一体的），W6 只写 infra/storage/。

## 3. 全局红线（违反即返工）

1. **只写自己任务卡的"可写范围"**。共享文件（contracts/、plugins/base.py、INTERFACES.md、tests/conftest.py、pytest.ini）只有 W1 可写；发现需要改 → 走 §1 的仲裁流程。
2. **不改旧行为**：旧 CLI 参数、旧 API 端点响应、旧 JSONL/Excel 输出路径与格式、ProgressTracker/CrawlCache 的锁、PoliteSession 的唯一熔断状态——全部保持 V2.2 语义。新能力只加新文件/新端点/新配置。
3. **原子写入保留**：一切落盘走 `tempfile.mkstemp` + `os.replace`，异常清理临时文件（沿用 storage/file_utils 既有实现，勿另写一套）。
4. **AST 校验不是沙箱**：加载外部插件必须过 AST 黑名单（os.system/subprocess/eval 等），且上传只进待审区 `data/plugin_uploads/`，批准前不 import、不执行。
5. **测试隔离**：所有测试用临时根目录 + 模拟网络（参考现有 tests/ 的 fixture 约定），禁止污染 data/、config/ 真实内容；不运行真实学校采集。
6. **不装依赖**：不自动 pip install；确需新依赖时在 progress.md 登记并说明用途与许可证。
7. **每窗口一个分支/worktree**（§6）；不推 main，不合并他人分支，合并不在本次范围内。
8. **诚实登记**：progress.md 里"完成"必须有验收命令的实际输出佐证；没跑过的写"未验证"。

## 4. 建议启动顺序（窗口数量有限时按此裁剪）

```text
第一批（立即开）: W1（契约）        —— 产出 INTERFACES.md 之前其他窗口只做纯新增骨架
第二批（契约冻结后）: W2 W3 W4 W5 W6 W7 并行
第三批（随第二批推进）: W8（其文档部分最后收尾）
```

单人串行时按 W1→W2→(W3∥W4W5∥W6W7)→W8 的顺序实施即可，任务卡内的验收命令不变。

## 5. 冲突避免规则

1. 一个文件同一时间只有一个窗口可写（见各任务卡清单）。
2. 公共契约文件只有 W1 可写。
3. 各窗口独立 worktree/分支（§6），互不 checkout 对方改动。
4. 需要别人模块的接口时，以 INTERFACES.md 为准写**本地 stub 测试**，不等对方实现；对方交付后换真实现重跑。
5. 集成由 W1 按 W2→W3→W4→W5→W6→W7→W8 依赖序发起，子窗口不互相合并。

## 6. Git 工作区约定

推荐（本机 Windows + Git Bash）：

```bash
git worktree add ../reptile-W2 feature/v3-w2-pipeline
git worktree add ../reptile-W3 feature/v3-w3-governance
git worktree add ../reptile-W4 feature/v3-w4-spiders
git worktree add ../reptile-W5 feature/v3-w5-processors
git worktree add ../reptile-W6 feature/v3-w6-storage
git worktree add ../reptile-W7 feature/v3-w7-present
git worktree add ../reptile-W8 feature/v3-w8-editor-docs
# W1 使用主工作区当前分支 Refactoring_code
```

若不用 worktree，则各窗口至少用不同分支名并在 progress.md 登记分支名。**共享工作区直接并行开发禁止**（会互相覆盖未提交改动）。

## 7. 每窗口结束时的交付动作

1. 跑任务卡里的全部验收命令，把结果粘进 `progress.md` 自己那一节。
2. 提交自己分支上的改动（commit message 末尾附 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`），**不 push**。
3. 在 `progress.md` 登记：已完成项 / 未完成项 / 待 W1 仲裁的接口提案 / 阻塞原因。
4. 留下可复现的失败测试优于不留（TDD 红绿记录进 progress.md）。
