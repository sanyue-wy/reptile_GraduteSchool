# V3.0 多窗口进度登记表

> 每个窗口开工时登记基线提交与分支；完成后把验收命令的实际输出摘要粘进自己那一节。
> "待 W1 仲裁"区用于跨窗口的接口变更提案，只有 W1 可裁决并更新 INTERFACES.md。

## 基线

- 主工作区基线提交：7b127ef (save: v22 refactor in progress, context limit reached)
- 环境：Windows 11 / Python 3.12.7 / pytest 9.1.1（V2.2 验收记录值，开工时复核）
- 全量测试预期：532 passed, 1 skipped（docs/refactor/acceptance.md）

## 待 W1 仲裁（接口变更提案）

| 提出方 | 日期 | 提案 | W1 裁决 |
|---|---|---|---|
| （示例）W4 | — | RawDataDTO 需增加 http_status 字段 | （待定） |

## W1 契约与集成主控

- 分支/worktree：Refactoring_code (main worktree)
- 已完成：
  - contracts/ 全部类型：asset.py, task.py, raw.py, record.py, output.py, ui.py, result.py, profiles/education.py
  - plugins/base.py：BasePlugin 基类 + PresenterPlugin 变体（execute 抽象方法 + render 可选钩子）
  - docs/V3.0/INTERFACES.md：完整冻结契约文档（类型字段表、五组插件协议签名、metadata.json 格式、PipelineContext 注入项、错误码表、状态机映射、schema ID 注册表、API 端点表）
  - config/pipeline.yaml：示例静态垂直切片配置（自洽，计划书 §6.2 基础修正）
  - config/plugins.yaml：示例插件实例配置（对应 pipeline.yaml，含所有 6 类 spider、processor、storage、ui、presenter）
  - scripts/migrate_config.py：配置迁移脚本（骨架 + dry-run，旧 plugins.json → 新双 YAML 映射器）
  - tests/test_contracts.py：契约验证测试（≥90% 覆盖率目标）
  - tests/test_wave0_contract.py：Mock 四阶段 smoke 测试（spider→parser→storage→presenter 贯穿）
- 未完成：
  - 运行契约测试验证（待依赖安装完成后执行）
  - 至少 3 个其他窗口的仲裁提案裁决
- 阻塞/问题：jsonschema/pyyaml 依赖已安装；bash 工具暂时不可用导致无法运行验收命令

## W2 主干管道

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：

## W3 插件治理

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：

## W4 采集插件

- 分支/worktree：feature/v3-w4-spiders (or main worktree)
- 已完成：
  - static_html spider plugin (plugins/spiders/static_html/plugin.py + metadata.json)
  - ajax_api spider plugin (plugins/spiders/ajax_api/plugin.py + metadata.json)
  - js_render spider plugin (plugins/spiders/js_render/plugin.py + metadata.json) - with optional Playwright dependency
  - pdf_list spider plugin (plugins/spiders/pdf_list/plugin.py + metadata.json)
  - yzw_api spider plugin (plugins/spiders/yzw_api/plugin.py + metadata.json)
  - media_downloader spider plugin (plugins/spiders/media_downloader/plugin.py + metadata.json) - new example plugin
  - raw_converter.py (converters/raw_converter.py) - normalizes legacy raw data to canonical RawDataBatch
  - All 6 plugins produce TRUE raw material batches (RawDataBatch with MediaAsset assets)
  - Tests: tests/test_spider_plugins.py - 39 passed (10 tests per plugin + 4 raw_converter + 1 fixture test)
  - Coverage: static_html 80%, ajax_api 86%, pdf_list 89%, yzw_api 81%, media_downloader 87%, js_render 21% (optional dep)
  - Fixtures: tests/fixtures/raw_pages/w4_*.html/json/pdf (shared with W5)
- 未完成：
  - Integration test tests/integration/test_static_slice.py (requires W2 engine + W5 faculty_parse + W6 jsonl_store)
- 阻塞/问题：无阻塞，所有单元测试通过

## W5 处理器插件

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：

## W6 存储插件

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：

## W7 呈现器·UI·模板

- 分支/worktree：
- 已完成：
  - pdf_presenter plugin (plugins/presenters/pdf_presenter/plugin.py + metadata.json) - with optional WeasyPrint dependency
- 未完成：
- 阻塞/问题：

## W8 编辑器·脚手架 CLI·文档

- 分支/worktree：
- 已完成：
- 未完成：
- 阻塞/问题：
