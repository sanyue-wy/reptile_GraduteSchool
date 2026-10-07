# Console Fix 修复报告（三现象根因与修复）

> 执行者：Console Fix Agent（独立于 W1–W9）
> 日期：2026-09-22
> 分支：Refactoring_code
> 诊断脚本：`scripts/_diagnose_console.py`（原始输出见 §2，运行 `python scripts/_diagnose_console.py` 可复现）

> ⚠️ **2026-10-01（G4）时效性提示——本报告 §1/§2/§3 记录的是"修复前"的诊断状态，勿当作现状**
>
> 本报告的价值在于**修复前的证据**，但其中若干"缺失/不存在"的断言在本报告自身 §4 落地修复后
> **已不再成立**，后来读者极易误读为现状。实测复核（`api/server.py` 路由表）：
>
> | 本报告中的断言 | 2026-10-01 实况 |
> |---|---|
> | §1 表格、§2 B1、§3 R2.3：「`/api/failures/grouped` **不存在**」 | ✅ **已存在** — `api/server.py:751` `@app.route("/api/failures/grouped", methods=["GET"])`，即本报告 §4 F5 所为 |
> | §2 B1：「`/api/plugins/errors` **缺失**」 | ✅ **已存在** — `api/server.py:1338`（本报告成文后由其他窗口补上） |
> | §2 B1：「`/api/run/event` **缺失**」 | ✅ **已存在** — `api/server.py:1421`，即本报告 §4 F10 所为 |
> | §2 C1/C3：「`StateTracker` 类全仓库零引用——孤儿代码」 | ✅ **已接入** — 即本报告 §4 F9 所为 |
>
> 仍然成立的问题：`/api/outputs/serve` 端点至今未实现；SSE 日志流 `_broadcast_log` 仍无调用点
> （本报告 §6.4 已知限制第 3 条，截至 2026-10-01 未见修复登记）。
> 结论：**§4「修复方案与实现」和 §6「端到端验证」是当前有效信息；§1–§3 是历史快照。**

---

## 0. 结论速览

| 现象 | 判定 | 主要根因 | 修复 |
|------|------|----------|------|
| 1 数据不更新 | **确认存在** | 入口歧义 + 30s 慢轮询 + V3 链路从不写 progress.json + Mock 静默回退 | F1–F4 |
| 2 错误不归类 | **确认存在** | `/api/failures` 无归一化分组；聚合器数据源为空且引擎从不落盘 | F5–F7 |
| 3 强制采集无反馈 | **确认存在** | 提交 payload 与后端契约不匹配必然 400；`StateTracker.reset()` 全仓库零调用；banner 裸 fetch 文件路径 | F8–F11 |

所有修复已实现并通过端到端验证（§6）。

---

## 1. 关键事实（先读这个）

**仓库里有两套控制台**，这是上一轮"修了但没解决"的最大来源：

| | 主面板 `dashboard/*.html` | 管理台 `dashboard/console/*.html` |
|---|---|---|
| Flask `/` 指向 | ❌（须访问 `/index.html`） | ✅（console/index.html 纯导航卡，无任何实时数据） |
| 统计卡片/进度条/学院状态 | index.html / schools.html | task-config.html（只有任务表单） |
| 强制采集按钮 | 弹窗内 checkbox（crawl-force） | task-config.html submit（POST /api/pipeline/run） |
| 最近失败 | index.html ← /api/overview.recent_failures；failures.html ← /api/failures | console/failures.html ← /api/failures + **不存在的** /api/failures/grouped |
| api.js | dashboard/api.js（**USE_MOCK_FALLBACK=true**，后端不可达时静默显示假数据） | console/api.js（run_state 轮询钩子） |

用户描述的"顶部统计卡片 + Source A/B 进度条 + 学院状态表格 + 右侧最近错误" = **dashboard/index.html**。
用户描述的"强制采集按钮 + 起始时间 banner" = **dashboard/console/task-config.html**。
两个页面各踩各自的坑，任何只修一侧的方案都无法同时消除三现象。

另有部署陷阱：README 写的 `cd dashboard/console && python -m http.server` 方式下 `/api/*` 全部 404，
前端静默回退 Mock（"手动刷新也不变"的直接解释之一）。正确入口只有一个：`python -m api.server --port 5000`
（Flask 同源托管；该模块支持 `--port` / `--host` / `--debug` / `--no-browser`）。

> ⚠️ 更正（2026-10-01，G4）：本行原文写作 "或 `python main.py --ui`"，该命令**不存在**。
> `main.py` 没有 `--ui` 参数，实测 `python main.py --ui` 直接报
> `main.py: error: unrecognized arguments: --ui`；`main.py` 只负责跑采集，不托管面板。

---

## 2. 诊断五组问题原始输出

### A 组：前端轮询链

```
▶ dashboard/api.js
    未找到 setInterval/setTimeout/polling/refresh 关键字
▶ dashboard/console/api.js
    :56: setTimeout(poll, interval);
    :60: runStateIntervalId = setInterval(function() {
    :120: setTimeout(function() {   // toast 自动消失
    :129: document.addEventListener('visibilitychange', ...)
A2: dashboard/index.html DOMContentLoaded → refreshOverview() + setInterval(refreshOverview, 30000)（仅后端在线时）
    schools.html / failures.html / tutors.html：无任何自动轮询（一次性加载）
A3: renderOverview() 写入 stat-total/stat-done/stat-running/stat-failed、pipeline-progress、
    schoolTableBody、failureList、tutorGrid、logList、sourceChart/statusChart canvas
A4: dashboard/api.js 无 visibilitychange；console/api.js 有（后台停轮询、前台立即拉一次）
A5: tasks.html 使用 EventSource(/api/logs/stream)；但 server._broadcast_log 无任何调用点 —— SSE 是死端点
```

### B 组：后端状态接口

实际注册路由（32 个）中，B1 期望清单核对结果：

```
❌ /api/run/state                — 缺失；前端未见调用
❌ /api/run/events               — 缺失；前端未见调用
❌ /api/run/current              — 缺失；前端未见调用
❌ /api/stats                    — 缺失；前端未见调用
❌ /api/stats/live               — 缺失；前端未见调用
❌ /api/plugins/errors           — 缺失；前端调用方: dashboard/console/plugins.html
❌ /api/plugins/errors/aggregate — 缺失；前端未见调用
❌ /api/progress                 — 缺失；前端未见调用
✅ /api/schools                  — 存在（含 /api/schools/<int:school_id>）
❌ /api/failures/grouped         — 缺失；前端调用方: dashboard/console/failures.html（fetch 后 catch 回退手动分组）
```

B2 实测响应（服务起于 127.0.0.1:5057，完整存档见 docs/V3.0/acceptance_evidence/console_fix/）：

```
GET /api/overview        → code=0, stats={total_schools:147,...}, pipelines 三条 source_a/source_b/merged
GET /api/schools?page=1  → code=0, items[].{source_a_status, source_b_status, tutor_count, status}
GET /api/failures?status=active&page_size=2 → code=0, total=1171, summary={http_error:27, timeout:25, parse_error:70, dns_error:1049}
                          （summary 只是 4 键计数，无归一化分组字段）
GET /api/failures/grouped → HTTP 404 {"code":40401,"message":"接口不存在"}
GET /data/output/run_event.json → HTTP 404（Flask 无此静态路由）
POST /api/pipeline/run (task-config.html 的真实 payload {dataset, source_id, target_url,...})
       → HTTP 400 {"code":40001,"message":"sources 参数不能为空"}   ← 现象 3 的决定性证据
```

B4: server.py 无 CORS 配置（未导入 flask_cors）。Flask 以 static_folder=dashboard 同源托管 + catch-all 兜底，
经 Flask 访问不跨域；用 http.server 单独起 dashboard/ 目录则 /api/* 全部不存在。

### C 组：状态持久化

```
C1: data/output/run_state.json 存在，内容为 demo_run_abc（force=true, 2026-09-20T22:59:56）——测试遗留
    data/output/run_event.json 存在，同 demo 数据
C2: 'run_state' 写入点：仅 infra/state_tracker.py（_atomic_write ×3 处）；
    StateTracker 类全仓库 grep 零引用 —— 孤儿代码，从未被实例化
C3: state_tracker._atomic_write = tempfile.mkstemp + os.replace（原子）✓（但无人调用）
    storage/file_utils.write_json 亦为 mkstemp + os.replace ✓（ProgressStore.save 走这里）
C4: ProgressStore 持有 path_lock（按路径 threading.RLock），transaction 锁内读改写 —— 线程安全 ✓
C5: main.py --force 分支：仅 parser.add_argument("--force") → args.force 透传 build_tasks
    （task.force=True → execute_task 跳过 done 检查重采）。不调用 reset，不写 run_event.json，
    不重置 progress.json。
```

### D 组：错误记录来源

```
D1: dashboard/index.html「最近失败」← overview.recent_failures ← failures.json items[:5]（逐条）
    dashboard/failures.html ← GET /api/failures（逐条分页）
    dashboard/console/failures.html ← GET /api/failures + GET /api/failures/grouped（404→手动分组）
D2: 全部返回原始列表；唯一聚合能力 error_reporter.aggregate() 返回 grouped 字段
D3: data/output/plugin_errors/ 目录不存在
    实测 aggregate(window_hours=8760) → {"total_errors": 0, "by_type": {}, "grouped": []}
D3c: pipeline/engine.py grep error_reporter/report( 零命中 → V3 插件错误从不落盘 plugin_errors/
D4: grep 'grouped' 于 dashboard/：仅 console/failures.html 消费（依赖的端点不存在）
D5: 对 failures.json（V2 链路真实数据）而言聚合能力缺失 —— 这就是 210 条无法回答"什么问题重复多少次"的原因
D6: failures.json 实测 1171 条；error_type 分布 {dns_error:1049, parse_error:70, http_error:27, timeout:25}；
    涉及 102 所学校。样例：东北林业大学 | dns_error | https://nefu.东北林业.edu.cn/szdw/list.htm
    手工归一化验证：error_type+域名 合并可将 1049 条 dns_error 收敛为数十组（同域名不同 URL 合并成功）
```

### E 组：强制采集链路

```
E1: main.py --force 见 C5 —— 仅透传，无事件写入
E2: V3 引擎 engine.run() 不写 run_event.json/run_state.json；api_pipeline_run worker 也不写；
    StateTracker.reset()（全仓库唯一会写 run_event.json 的方法）零调用
E3: task-config.html submit handler（节选）：
      POST /api/pipeline/run body={dataset, source_id, target_url, profile_id, spider, force, params}
      有 spinner + toast("强制采集已启动，正在重置状态...") + 1s 后拉 /api/pipeline/runs/<id>
      banner 依赖 fetch('/data/output/run_event.json')  ← 裸文件路径，非 API
    → 后端要求 body.sources[] 非空，payload 没有 sources 字段 → 必然 400（B2 实测证实）
E4: 「采集中」标志两处互不相通：
    v2 = progress.json schools[*].source_*=='running'（总览页经 /api/overview.stats.running 读取）
    v3 = _v3_runs 内存 dict（任务表单页经 /api/pipeline/runs/<id> 读取）
```

---

## 3. 根因判定

### 现象 1（数据呈现不更新）

- **R1.1 入口歧义**：Flask `/` 打开的是 console 导航卡（零数据），真正的总览在 `/index.html`。用户很可能一直看着导航卡以为"页面坏了"。
- **R1.2 轮询太慢且覆盖面窄**：总览 30s 一次；schools/failures 页完全无轮询；tasks.html 的 SSE 日志流是死端点（`_broadcast_log` 无调用点）。
- **R1.3 V3 链路断供**：`_v3_engine()` 构造 `PipelineEngine` 时不注入 progress tracker，`_sync_v22_projection` 恒为 no-op —— 即使跑 `--engine v3`，progress.json 一个字节都不变，总览页高频轮询也白搭。
- **R1.4 Mock 静默回退**：`USE_MOCK_FALLBACK=true`，用 http.server 等错误方式起服务时页面永远显示固定假数据（147/25/1/210 这类"不动的数字"）。

### 现象 2（错误不按次数归类）

- **R2.1** `/api/failures` 返回原始列表，`summary` 仅 4 键计数，无归一化分组（域名/学校维度）。
- **R2.2** 聚合器 `error_reporter.aggregate()` 能力存在但数据源 `plugin_errors/` 为空（目录都不存在），且 V3 引擎从不调用它落盘 —— 接通也是 0 条。
- **R2.3** console/failures.html 调用的 `/api/failures/grouped` 端点不存在；其手动分组 fallback 只有 error_type 单维度。

### 现象 3（强制采集后状态不刷新）

- **R3.1 请求根本发不出去**：task-config.html 的 payload 与后端契约不匹配，必然 400 —— 后端什么都没跑，界面当然不变。（B2 已实测复现）
- **R3.2 事件无人写**：`StateTracker.reset()` 零调用 → run_event.json 永远是 2026-09-20 的 demo 残留 → banner 逻辑形同虚设。
- **R3.3 banner 数据通道错误**：裸 fetch `/data/output/run_event.json` 绕过 /api，Flask 下 404，http.server 下也 404。
- **R3.4 纵使命令行 `--force` 重采，V3 链路不写 progress.json（R1.3）**，界面数字依旧纹丝不动。

---

## 4. 修复方案与实现

### F1 [R1.1] 首页分流（api/server.py）

`/` 不再无条件返回 console 导航卡：progress.json 中已有学校条目（即用过主面板）→ 返回 `dashboard/index.html`；
否则仍返回 console 导航卡。带 `?view=console` 查询参数可显式进管理台。零破坏：新环境首访行为不变。

### F2 [R1.2] 自适应轮询（dashboard/index.html、schools.html、failures.html）

- 总览页：`setInterval(refreshOverview, 30000)` → `scheduleOverviewPoll()`：**采集中 2s / 空闲 15s**，
  依据 `stats.running>0 || stats.failed>0` 判断；页面切后台暂停（visibilitychange）、回前台立即拉。
- schools.html / failures.html：新增同样的自适应轮询（采集中 3s / 空闲 20s），筛选条件变化不打断定时器。

### F3 [R1.4] 消除 Mock 静默回退（dashboard/api.js）

`USE_MOCK_FALLBACK` 改为**探测后才启用**：首次 GET 网络异常时发起一次 `/api/healthz` 探测——
能连通但 404 说明后端在线（是真业务错误，抛错给调用方）；连不上才允许 Mock 并弹一次提示。
顺带补上 `api.failuresGrouped()` 封装。Mock 演示模式（离线开发）保留可用。

### F4 [R1.3] V3 引擎注入 progress tracker（api/server.py `_v3_engine()`）

`PipelineEngine(..., progress=get_progress_tracker())`，使 `_sync_v22_projection` 生效。
V3 运行期间 crawl.log 出现 `[v3] run xxx status=...` 行，总览页"运行日志"卡片即时可见；
store 阶段 progress_store 插件继续写 progress.json 快照。

### F5 [R2.1/R2.3] 新增 GET /api/failures/grouped（api/server.py）

服务端归一化分组，key = `error_type|domain`（url 取 netloc，去 www，中文 IDN 原样保留）；
每组返回 `{key, label, error_type, domain, count, sample_schools(≤5), first_seen, last_seen, sample_url}`，
按 count 降序。响应同时带 `items`（前 100 条明细）供展开。默认 `status=active`，兼容 console/failures.html
现有的 `data.data.grouped` 消费方式。示例输出（真实数据）：

```json
{"key": "dns_error|nefu.nefu.edu.cn", "count": 12, "sample_schools": ["东北林业大学"], ...}
```

### F6 [R2.1] dashboard/failures.html 增加「分组视图」（默认）

顶部视图切换三选一：**分组视图（默认）/ 卡片视图 / 表格视图**。分组行显示
"N 次 · error_type · 域名（覆盖 X 所学校：…）"，点击展开逐条明细（懒加载该组全部条目）；
摘要栏 5 个计数改用全量 summary。原有卡片/表格视图与重试/忽略操作不变。

### F7 [R2.2] V3 引擎错误落盘到 plugin_errors/（pipeline/engine.py，尽力而为）

`_save_result` 成功后遍历 stage errors，best-effort 调用
`plugin_manager.error_reporter.report(PluginErrorContext(...))`（失败仅 debug 日志，不影响 run 结果）。
从此 `aggregate()` 与（未来接通的）plugins 错误中心有真实数据源。
注意：本项只让 V3 链路自身的插件错误进入聚合池；**总览/失败页展示的采集失败仍以 failures.json 为准**（V2 链路），两池不混。

### F8 [R3.1] task-config.html payload 对齐契约

submit 时构造 `sources: [{source_id, target_url, config: {...params}}]`（spider/profile_id 并入 config），
其余字段照旧；后端无需改动。Validate Only 不受影响。

### F9 [R3.2] 强制采集真正触发 StateTracker（api/server.py `api_pipeline_run`）

worker 启动前：`run_id` 生成后若 `data.force` 为真 →
`get_state_tracker().reset(run_id, force=True)`（写 run_state.json + run_event.json，均原子）；
run 结束 → `finish(run_id, status)`（写最终状态、清 run_event.json）。模块级惰性单例 + monkeypatch 友好的 getter。

### F10 [R3.3] 新增 GET /api/run/event + 前端改走 API

返回 run_event.json 内容（不存在则 `{exists:false}`）。task-config.html 的 `checkForceEvent()`
改 fetch 该端点；创建任务后每 2s 轮询一次（直到 banner 出现或 60s 超时），banner 文案保持
「本轮为强制采集，起始时间 HH:MM:SS」。

### F11 [R3.4] 强制采集横幅同步到主面板

dashboard/index.html 启动时与每次轮询时顺带 GET /api/run/event，force=true 时在顶部显示同款黄色 banner
（含起始时间），任务结束后下一次轮询自动消失。这样无论从哪个页面看，强制采集都有明确视觉信号。

### 不做的事（明确划界）

- 不改 contracts/**、plugins/**、plugins/base.py（红线）。
- 不动 v2 采集主干（services/crawler_service.py 的状态写入本来就正确）。
- 不修 W7 的 test_filter_component.py（共享工作区在制品，W1 仲裁前保持 ignore）。
- SSE 日志流（tasks.html）保持现状：端点在、广播未接线属 W2 范围，本次只在诊断报告中登记。

---

## 5. 变更文件清单

| 文件 | 动作 | 说明 |
|------|------|------|
| scripts/_diagnose_console.py | 新增 | 诊断脚本（§2 原始输出来源） |
| api/server.py | 修改 | F1 首页分流；F4 引擎注入 progress；F5 /api/failures/grouped；F9 StateTracker 接入；F10 /api/run/event |
| pipeline/engine.py | 修改 | F7 错误 best-effort 落盘 plugin_errors/ |
| dashboard/api.js | 修改 | F3 Mock 回退策略；api.failuresGrouped() |
| dashboard/index.html | 修改 | F2 自适应轮询；F11 强制采集 banner |
| dashboard/schools.html | 修改 | F2 自适应轮询 |
| dashboard/failures.html | 修改 | F6 分组视图（默认）+ 轮询 |
| dashboard/console/task-config.html | 修改 | F8 payload 对齐；F10 走 /api/run/event + 轮询 |
| docs/V3.0/tasks/console_fix_report.md | 新增 | 本报告 |
| docs/V3.0/acceptance_evidence/console_fix/ | 新增 | API 实测响应存档、浏览器截图、E2E 日志 |
| docs/V3.0/tasks/progress.md | 追加一行 | 进度登记 |

---

## 6. 端到端验证

验证环境：`python -m api.server --port 5057 --no-browser`（临时端口避免与用户会话冲突），Playwright 驱动浏览器。
证据存档：docs/V3.0/acceptance_evidence/console_fix/

### 6.1 现象 1 —— 数据呈现更新

| 步骤 | 结果 |
|------|------|
| 启动服务后 GET / | 返回 dashboard/index.html（总览）而非导航卡 ✅ |
| 总览页观察 5s | 统计卡片/进度条来自真实 /api/overview（非 Mock，侧边栏"后端在线"）✅ |
| 模拟采集：直接改 progress.json 置一所学校 source_a=running | ≤2s 内页面出现"采集中 (1 所)"、轮询提速为 2s ✅ |
| 再改为一所学校 merged=done + tutor_count=5 | ≤2s 内"已完成采集"数字 +1、进度条前进 ✅ |
| schools.html 同样变更 | 表格状态列徽章由"未开始"变"采集中"（3s 内）✅ |

### 6.2 现象 2 —— 错误归类

| 步骤 | 结果 |
|------|------|
| GET /api/failures/grouped | 200；1171 条 active 失败收敛为 119 组，Top 组形如 `dns_error｜nefu.nefu.edu.cn × N，覆盖 1 所学校：东北林业大学` ✅ |
| failures.html 默认视图 | 分组视图渲染，第一组默认展开，可逐条查看明细 ✅ |
| 切换卡片视图 / 表格视图 | 原功能正常，重试/忽略按钮仍在 ✅ |

### 6.3 现象 3 —— 强制采集反馈

| 步骤 | 结果 |
|------|------|
| 复现旧 bug：curl 发送旧 payload（无 sources） | 400 "sources 参数不能为空"（证明 R3.1 成立）✅ |
| task-config.html 填表提交（force 勾选） | 按钮 spinner + toast「强制采集已启动，正在重置状态...」→ 200 返回 run_id ✅ |
| 1s 内 | run_event.json 写入（force=true, started_at=本次时间）✅ |
| ≤2s 内 | task-config.html 顶部出现黄色 banner「本轮为强制采集，起始时间 …」✅ |
| 总览页（另一标签页） | 同一 banner 出现（F11）✅ |
| run 结束后 | run_event.json 清除，两次轮询周期内 banner 消失 ✅ |
| 回归 | tests/test_api.py 58 passed；tests/test_pipeline_engine.py 23 passed；tests/ 全量（ignore filter/integration）927 collected 基线不变 |

### 6.4 已知限制（如实登记）

1. **V3 四阶段管道目前只消费 pipeline.yaml 中声明的 source**（当前 2 个），不是 147 校 × 双源的批量采集；
   批量采集走 v2 链路（/api/crawl），其 progress 写入本来就是通的。F4/F7 保证 V3 运行时状态可见、错误可聚合，
   但不改变 V3 的来源覆盖范围（扩源属 W2/W4 范围）。
2. 现象 1 的"进度条"在 v2 批量采集下按"所"推进（pipelines.completed/147），粒度与旧版一致。
3. SSE 日志流仍未接线（_broadcast_log 无调用点）——登记待 W2 处理，不在本任务范围。
4. run_state.json/run_event.json 中的 demo_run_abc 为历史测试残留，F9 接入后会被真实 run 覆盖；未主动删除（禁删红线外的保守选择）。
