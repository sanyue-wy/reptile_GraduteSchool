# W3 任务卡：插件治理（发现 / 校验 / 批准 / 注册表）

## 角色

平台治理开发者。把 V2.2 的"七类清单 + AST 校验 + plugins.json 覆盖"升级为 V3.0 的"metadata.json 单一真值 + registry 快照 + 批准生命周期"，并维护旧管理入口兼容。

## 必读（只读这些）

- [README.md](README.md)
- `docs/V3.0/INTERFACES.md`（重点：metadata.json 格式、生命周期状态机、registry 协议、API 端点表）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §6.1、§7、§8.2
- 现状代码：config/plugins.py（PLUGIN_KINDS 七类、BUILTIN_METADATA、list_plugins/update_plugin/upload_plugin/_all_external_plugins）、security/plugin_validator.py（BLOCKED_CALLS/BLOCKED_MODULES/PLUGIN_INTERFACES/validate_plugin_source）、plugins_ext/ 目录结构

## 可写范围（独占）

```text
plugin_manager/**                  # loader.py / validator.py / registry.py
security/plugin_validator_v3.py    # 新校验层；security/plugin_validator.py 原文件不动（W2 等仍 import 它）
scaffolds/loader_protocol.py       # 与 W8 脚手架的交接协议：生成物应满足的发现/校验约定（纯文档+常量，不含 CLI）
config/plugins.py                  # 加兼容适配层：从 registry 派生旧七类视图；原函数签名与返回形状不变
tests/test_plugin_loader.py
tests/test_plugin_security.py
```

**禁止修改**：contracts/、plugins/base.py、security/plugin_validator.py（原文件）、main.py、api/server.py（新端点由 W2 写，你提供后端函数并在 INTERFACES.md 登记签名）、各 plugins 子目录（但可以为测试创建 mock 插件 fixture，放 tests/fixtures/）。

## 交付清单

1. **metadata.json 规范落地**（loader 侧）：字段 name/version/author/license/description/plugin_type(spider|processor|storage|presenter|ui)/input_schema/output_schema/entry_point/dependencies/min_core_version/config_schema/additionalProperties=false。GPL 类依赖声明 → 加载时告警日志（不阻断）；缺 license 且 dependencies 非空 → 拒绝。
2. **生命周期状态机**（registry.py）：扫描元数据（不 import）→ 结构/版本/依赖/包路径校验 → AST 静态审查 → pending_review → approved(绑定完整包内容摘要) → loaded → registry 快照发布。规则：未知包/名称冲突/min_core_version 不兼容/批准后内容摘要变化 → 拒绝；禁用插件不得 import；按实例禁用（不是靠加载失败静默跳过必需节点）。
3. **validator**：复用 security/plugin_validator.py 的 BLOCKED_* 常量与 AST 提取逻辑（import 使用，勿复制代码），扩展：新类接口校验（BasePlugin 子类）与旧顶层函数校验分开适配；schema 名称从受控注册表解析，禁止 eval 任意字符串。文档与日志中明确"AST 检查是门禁不是沙箱"。
4. **上传流程收紧**：upload 只写待审区 `data/plugin_uploads/`（该目录不参与发现、不挂静态服务）；返回"已接收、待批准"状态；批准动作要求管理员权限标识 + 记录审计条目（时间/操作者/包摘要）；批准/停用/删除有引用计数，活动运行引用的版本不可删。
5. **registry 快照与热更新**：每次批准/变更生成不可变快照（含 registry_revision）；运行开始冻结 revision，新版本只影响后续运行；不得清空 sys.modules 强替活动实例；依赖/原生库升级标记 requires_restart。
6. **旧七类兼容视图**：config/plugins.py 的 list_plugins()/get_plugin/update_plugin 等保持签名与返回形状，内部改从 registry 派生（source/fetcher/parser/processor/exporter/presenter/utility 映射关系按计划书 §6.1；fetcher↔spider 中 static_html 与旧 static_list 建显式别名）。旧 weight 按 (weight, id) 排序语义保留。
7. **预检函数**：供 W2 的 POST /api/pipeline/validate 调用——拒绝未知 ID、重复实例、禁用却被引用、schema 不匹配、依赖缺失；不执行任何插件代码。

## 验收命令

```bash
python -m pytest tests/test_plugin_loader.py tests/test_plugin_security.py -q
python -c "from config.plugins import list_plugins; ps=list_plugins(); print(len(ps))"   # 旧入口仍可用，数量与迁移前一致
```

关键用例（必须存在）：
- metadata-only 发现：未批准的包不出现在可执行清单、不被 import（用 sys.modules 断言验证）。
- 含 `subprocess.run` 的插件源被 AST 拒绝；含 GPL 依赖声明的包加载出告警。
- 批准后篡改任一字节 → 重新加载被拒。
- 同一输出场景下活动快照在批准新版前后：进行中 run 用旧版、新 run 用新版。
- 旧 API 形状回归：list_plugins() 输出与改造前 golden fixture 逐字段一致。

## 特别注意

- registry 是唯一能力表；旧函数表/类表（spiders.ENGINE_REGISTRY、processors.dispatch 等）只能作为派生视图存在，不得各自写入真值。
- 新增插件"出现在管理清单"≠"被执行链调用"：为每个内置五组插件各留一个执行集成测试钩子（真正 invoke execute），Wave 1b 由 W1 编排跑通。
- 不可信插件隔离（OS 级沙箱）本期不交付，配置项若开启该模式必须直接报错拒绝，不得静默降级。
