# W1 任务卡：契约与集成主控

## 角色

架构师/集成者。你是唯一有权修改共享契约文件的人，负责冻结 V3.0 契约、产出 INTERFACES.md、主持接口仲裁、最后做依赖序集成。你消化计划书全文一次，其他窗口不再读完整对话历史。

## 必读（只读这些）

- [README.md](README.md)（本目录总览，红线与规则）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §1–§7、§10–§11（目标、契约、执行语义、配置、治理、波次、验收）
- [../../refactor/interfaces.md](../../refactor/interfaces.md)（V2.2 冻结契约，签名基准，不得修改）
- contracts/ 相关旧代码：services/、spiders/engine.py、processors/__init__.py、exporters/__init__.py（了解要兼容的既有形状）

## 可写范围（独占）

```text
contracts/**                  # 全部 DTO + profiles/education.py
plugins/base.py               # BasePlugin 基类（含 presenter 变体，见交付 3）
config/pipeline.yaml          # 示例（自洽垂直切片，计划书 §6.2 两份 YAML 之一）
config/plugins.yaml           # 示例（同上）
config/examples/**
scripts/migrate_config.py
docs/V3.0/INTERFACES.md
tests/test_contracts.py
tests/test_wave0_contract.py
docs/V3.0/tasks/progress.md   # 只写自己那一节
```

**禁止修改**：pipeline/、plugins/spiders|processors|storage|presenters|ui/、plugin_manager/、infra/、main.py、api/server.py、dashboard/、schema_editor/、scaffolds/、templates/、tests/conftest.py、pytest.ini、docs/refactor/**。

## 交付清单

1. **contracts/ 全部类型**（标准库 dataclass + jsonschema 运行时校验；YAML 用 PyYAML `safe_load`，版本比较用 packaging）：
   - asset.py：MediaAsset(media_type, mime_type, data, url=None, metadata=None)、AssetRef
   - task.py：TaskConfigDTO(task_id, dataset, source_id, profile_id, target_url, config_revision, 只读配置快照)、TaskRunState(run_id, task_id, status, retry_count, last_attempt_at, checkpoint)、OutputSpec
   - raw.py：RawDataDTO(source_id, url, content_type, encoding, fetched_at, trace, assets: list[MediaAsset])——**assets 列表为资产真值**；保留 content/raw_ref 二选一作为 legacy 输入适配入口，raw_converter 负责归一到 assets
   - record.py：NormalizedRecordDTO(record_id, dataset, schema_id, fields, provenance, media_refs)、RecordBatch
   - output.py：PresentationRequest、RenderedOutputDTO(output_format, path, media_assets)
   - ui.py：ViewModel、UIComponentDTO
   - result.py：StoreRequest、StoreReceipt(target_id, written/skipped/failed, records_written, output_ref, error)、StageResult、RunResult、ErrorDTO(code, message, stage, task_id, source_id, retryable, diagnostics)
   - profiles/education.py：university/college/category/year/name/title/研究方向等教育扩展字段（领域 schema v1，不作通用必填）
   - 每个边界类型配 JSON Schema 常量（如 `RawDataBatch.v1`），并提供 validate(dto) 函数；dataclass 注解本身不算校验。
2. **docs/V3.0/INTERFACES.md**：把上述全部类型字段表、五组插件协议签名（SpiderPlugin / ParserPlugin / RecordProcessorPlugin / StoragePlugin / **PresenterPlugin** / UIPlugin）、metadata.json 格式（必须含 license 字段：GPL 类依赖声明时加载告警）、PipelineContext 注入项、错误码表、状态机映射（新枚举 → V2.2 旧 done/success 枚举）、schema ID 注册表、API 端点表（计划书 §8.2）逐条冻结。这是其余七个窗口的契约唯一真相源。
3. **plugins/base.py**：BasePlugin(ABC, Generic[InputT, OutputT])，属性 name/version/plugin_type/input_schema/output_schema，方法 setup(context)/execute(data, context)/close()。**PresenterPlugin 设计决议**（解决 render 与 execute 的一致性）：PresenterPlugin 继承 BasePlugin，`execute(presentation_request: PresentationRequest, context) -> RenderedOutputDTO` 是抽象方法；子类若偏好分离模板渲染，可提供非抽象 `render(records, context)` 辅助钩子，默认实现由 execute 调用——保证任何具体 Presenter 只需实现一个入口即可实例化，不存在"只有 render 没实现 execute 导致无法加载"的抽象类陷阱。
4. **mock 四阶段 smoke**：tests/test_wave0_contract.py 内用 4 个 mock 插件（各 5–10 行）贯穿 acquire→process→store→present，验证 DTO 序列化/反序列化往返、非法 schema_id 拒绝、空批次合法通过。
5. **示例配置两份 YAML**（计划书 §6.2 原文为基础，修正使其自洽）：pipeline.yaml 中 present 段须指向具名 presenter 实例（如 `instance: html_report, template: minimal-light`），plugins.yaml 增加对应 `html_report: plugin: presenter:html_presenter` 实例及 OutputSpec 关联；URL/学校/年份不硬编码进 YAML。
6. **scripts/migrate_config.py**（骨架+dry-run）：旧 plugins.json 七类（source/fetcher/parser/processor/exporter/presenter/utility，见 config/plugins.py PLUGIN_KINDS）→ 新两 YAML 的映射器；支持 --dry-run 输出映射/冲突报告；成对发布（配置锁 + 版本清单，失败恢复）；真实切换留到集成期。
7. **进度登记**：progress.md 自己的节 + 裁决"待 W1 仲裁"区的所有提案。

## 验收命令

```bash
python -m pytest tests/test_contracts.py tests/test_wave0_contract.py -q
python scripts/migrate_config.py --dry-run --report /tmp/migrate_report.txt
python -c "from config.validator import validate_all_configs; from config.loader import load_schools_config; r = validate_all_configs(load_schools_config()); print(len(r['errors']))"
```

退出条件：契约测试全绿；INTERFACES.md 覆盖上面第 2 条全部内容且与代码一致（以代码为准更新文档）；至少 3 个其他窗口的仲裁提案已裁决并回写。

## 完成定义与交接

- [ ] 其他窗口可以只凭 INTERFACES.md 开工，无需回问（自检：把 INTERFACES.md 单独交给别人能否无歧义实现一个 spider 插件？）
- [ ] progress.md 记录契约冻结时间戳与各窗口开工许可
- [ ] 集成期（各窗口交付后）按 W2→W3→W4→W5→W6→W7→W8 顺序跑全量 `python -m pytest tests/ -q`，处理跨模块冲突，最终产出 docs/V3.0/ACCEPTANCE.md 初稿

## 特别注意

- Wave 0 是"冻结而非搭空壳"：不要预创建 pipeline/、plugins/*/ 的空目录或占位文件，那是各窗口自己的事。
- 旧 CrawlTask 执行状态映射、旧 key()（大学|学院|source）、旧 progress.json 投影规则，从 ../../refactor/interfaces.md 抄录进 INTERFACES.md，不要重新发明。
- 覆盖率要求：contracts/ 与 base.py ≥90%（纯数据类型容易测满）。
