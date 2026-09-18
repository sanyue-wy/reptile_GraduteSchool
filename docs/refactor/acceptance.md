# V2.2 离线集成验收报告

- 日期：2026-09-17
- 分支：Refactoring_code（基线提交 7b127ef + 本次修复）
- 执行环境：Windows 11，Python 3.12.7，pytest 9.1.1

## 一、自动验收（scripts/acceptance.py，退出码 0）

| 关卡 | 结果 |
|---|---|
| py_compile（main.py、api/server.py、config/loader.py、services/、storage/、security/、spiders/、utils/） | 通过 |
| main.py --help CLI 可用性 | 通过 |
| 全量 pytest（隔离临时工作区，禁真实网络/DNS） | 532 passed, 1 skipped |
| 核心模块覆盖率（services、storage、spiders.engine、security、utils.http） | 全部 ≥ 80%，总计 94% |
| 真实 config/data 内容校验和 | 通过，未改动 |
| git diff --check | 通过 |

各模块覆盖率：security 100%、services/crawler_service 92.86%、services/export_service 100%、services/merge_service 95.65%、spiders/engine 100%、storage/config_store 85.71%、storage/file_utils 97.5%、storage/jsonl_store 100%、storage/progress_store 100%、utils/http 90.98%。

## 二、浏览器闭环验收（scripts/offline_preview.py --port 5099 + 独立 Chromium）

在私有临时工作区、合成 HTTP 传输、出站 socket 全部封禁的条件下，通过真实浏览器驱动完成：

1. **总览面板**：GET / 返回 HTTP 200，147 所高校统计、失败记录预览、五页导航正常。
2. **采集闭环**：在开始采集对话框中确认采集（学校=测试大学，双源），POST /api/crawl 返回 task_id；任务经 queued → running → completed（2/2 子任务，percent 100）。
3. **导师数据**：tutors.html 显示 1 位导师（张三，教授，博导，已合并，在招）；详情弹窗含研招网招生信息（080200 机械工程，学术型硕士）与原件链接。
4. **真实下载**：导出 JSON 下载并解析成功（1 条记录含张三）；导出 Excel 下载后经 openpyxl 读取成功（2 行表头+数据）。
5. **失败重试闭环**：failures.html 点击单条重试 → 新任务 completed → 失败记录状态翻转为 resolved（卡片"重试"按钮消失）；重试后导师数据保留。
6. **配置管理**：config.html 正常渲染（学校树、全局参数、插件配置页签）。
7. 全程无页面 JS 错误（pageerror 监听为空）。

## 三、本轮修复

- 问题：重试采集成功后，对应失败记录停留在 active（"待重试/未重试"），重试闭环无法自动关闭。
- 根因：`_run_crawl_task` 成功路径未更新失败状态；`api/server.py` 中 `update_failure_status` 此前仅被"忽略"端点使用。main 分支行为一致，属既有缺口，非迁移回归。
- 修复（TDD）：
  - 新增失败测试 tests/test_api.py::TestApiFailuresExtended::test_retry_resolves_failure_after_success（先确认 RED：status 仍为 active）。
  - 实现：api/server.py `_run_crawl_task` 在 `service.run_merge(tasks)` 成功后，将目标学校且仍为 active 的失败记录置为 resolved。
  - 验证 GREEN：单测通过；全量 532 passed；浏览器重试后 /api/failures 返回 `"status":"resolved"`。

## 四、未验证范围（如实标记）

- 真实网站采集、真实 DNS、真实浏览器渲染（js_render）、真实 PDF 下载未运行——离线预览使用合成传输。
- 上述范围需在具备外网条件的部署环境另行抽验。

## 五、结论

自动验收与浏览器闭环验收全部通过，V2.2 重构（引擎抽象层、服务层、存储层、安全校验、测试迁移）达到 docs/refactor/interfaces.md 定义的验收标准。v22-full-refactor 完成度：已完成。
