# 研究生导师信息采集系统 · 技术 2.0 升级报告

> 日期：2026-09-15 ｜ 主题：针对「Source A 全量无法获取数据」问题的诊断与 2.0 升级方案
> 范围：采集链路（config → spider → parser → failure）；不涉及 Source B / 合并 / 面板改造

---

## 一、TL;DR

当前"采不到数据"**不是反爬、不是网络问题，而是配置里根本没有真实数据源**：
`config/school_data.json` 中全部 **112 所学校 × 222 个学院的 `list_url` 均为占位符 `http://x.com`**（另 1 条为测试用的 `test.edu.cn`）。爬虫忠实地对一个不存在的域名发起请求，于是全军覆没。

233 条失败记录中 **233 条被归类为 `parse_error`**，其中至少三类错误（连接被重置、DNS 解析失败、上游 500）本应分别归入 `connection_error` / `dns_error` / `http_error`——**错误分类把配置缺陷伪装成了"页面解析失败"**，进一步误导排查方向。

因此 2.0 的核心不是加代理、加浏览器，而是三件事：

1. **URL 发现层**（新增 `url_resolver`）：把"人工维护 222 个 URL"升级为"自动发现 + 探测验证 + 人工确认入库"的流水线；
2. **可观测性修正**：按异常类型精确分类错误，并对"整批同因失败"熔断停跑，避免再出现一次 8 小时的无效运行；
3. **多引擎抓取**：静态 HTML / AJAX 接口 / JS 渲染（Playwright）/ PDF 名单四种模式，覆盖不同建站平台的学院官网。

预计工作量约 **4~5 人日**（不含人工核对 URL 的时间），完成后 Source A 才具备真正跑通的前提条件。

---

## 二、故障现象与证据

### 2.1 现象

- 命令行与面板触发的 Source A 采集，所有学校全部失败，无任何导师数据产出；
- `data/output/failures.json`：**total = 233，summary 全部记为 `parse_error: 233`**，`http_error / timeout / dns_error` 均为 0；
- `progress.json` 中各学院 `source_a: "failed"`、`tutor_count: 0`，Source B 与合并阶段全部停留在 `pending`。

### 2.2 根因定位（三层）

| 层级 | 问题 | 证据 |
| --- | --- | --- |
| **L1 配置（根本原因）** | 222 个学院的 `list_url` 全是占位符 `http://x.com` | 对 `school_data.json` 统计：`Counter(list_url) = { 'http://x.com': 222, 'http://test.edu.cn': 1 }` |
| **L2 错误分类（放大器）** | 所有异常一律记为 `parse_error`，掩盖真实原因 | failures.json 中同一 `parse_error` 标签下混有：`ConnectionResetError(10054)`、`RemoteDisconnected`、`NameResolutionError (getaddrinfo failed)`、`ResponseError('too many 500 error responses')` |
| **L3 缺乏熔断（代价放大）** | 同一域名连续失败数千次仍逐个重试，单轮全量跑了约 8 小时（日志 07:39 → 11:41） | crawl.log 中每 ~9 秒一条相同错误，直到队列耗尽 |

补充说明：`utils/http.py` 已有域名级冷却机制（`--cooldown-threshold` 默认 5 次触发 `--cooldown-seconds` 默认 1800s 暂停），但本次日志显示冷却并未有效拦截后续任务——因为失败发生在**任务级 catch-all**（`main.py` 对每个 task 捕获异常后直接写 failure 并进入下一个 task），冷却只作用于单次 HTTP 请求内部，管不到"换了一个学院、还是同一个坏域名"这种跨任务的重复失败。**2.0 需要在任务调度层增加"同因熔断"**（见 §4.2）。

### 2.3 为什么现在必须升级

即便立刻把 222 个 URL 手工填对，现有架构仍有三个结构性短板会在批量阶段暴露：

1. **无 URL 发现能力**：112 校 × 2 学院 = 222 个入口，且高校官网改版频繁（换域名、换建站平台、改目录结构），纯手工维护不可持续；
2. **仅两种列表模式**：`static_html` 与 `ajax_api`（SudyCMS/WebPlus 特征）。调研（`docs/GITHUB_RESEARCH.md`、`DESIGN.md`）已表明部分学院是 JS 渲染页或 PDF 公示名单，现有引擎无法处理；
3. **失败信号失真**：如本次事故所示，错误分类不准会直接把"配置问题"引导成"反爬问题"，浪费数小时排查。

---

## 三、目标与非目标

### 目标

- G1：Source A 在真实 URL 下跑通首批试点院校（建议先东南大学、同济大学 2~3 所），产出非空 jsonl 与 summary.xlsx；
- G2：建立 URL 自动发现流水线，新增一所学校的配置成本从"人工找页面 + 调 selector"降到"自动发现 + 点选确认"；
- G3：任何一轮采集，若前 N 个任务同因失败则自动熔断，损失上限从"8 小时"降到"N × 单任务耗时"；
- G4：failures.json 的错误分类与真实异常一一对应，面板可按类别直接定位问题。

### 非目标（本期不做）

- 不改 Source B（研招网）链路——其 CAS 登录与 `zsml/rs/dws.do` 接口按原计划另行推进；
- 不做分布式 / 代理池（本次故障证明瓶颈不在出口 IP，先不过度设计）；
- 不动 dashboard 前端（仅后端 API 响应体字段变化，向下兼容）。

---

## 四、2.0 技术方案

### 4.1 模块总览

```
                        ┌──────────────────────────────┐
 config/school_data ──▶ │ url_resolver（新增）          │
   （占位/缺 URL）      │  ① 站点搜索  ② 链接挖掘       │
                        │  ③ 特征打分  ④ 连通性探测     │
                        │  ⑤ 候选落盘待人工确认         │
                        └──────────────┬───────────────┘
                                       ▼ 确认后写入 list_url + list_type
 ┌─────────────────────────────────────────────────────────────┐
 │ 调度层 main.py                                              │
 │  · 启动前配置体检（§4.2-A）                                 │
 │  · 同因熔断（§4.2-B）                                       │
 │  · 错误分类器 classify_error()（§4.2-C）                    │
 └──────────────┬──────────────────────────────────────────────┘
                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │ 抓取引擎层 spiders/（按 list_type 分派）                     │
 │  static_list   现有，补健壮性                                │
 │  ajax_api      现有，扩 WebPlus/SudyCMS 之外的通用 JSON 接口 │
 │  js_render     新增：Playwright headless（懒加载/SPA 页）    │
 │  pdf_list      新增：pdfplumber 解析 PDF 公示名单            │
 └─────────────────────────────────────────────────────────────┘
```

### 4.2 调度层修复（P0，先行，约 0.5 人日）

**A. 启动前配置体检**

`config/validator.py` 目前能拦"缺字段"，但要再加两条规则并在 CLI/面板双端生效：

- `list_url` 命中占位符模式（`x.com`、`example.com`、`test.edu.cn`、`localhost`、`*placeholder*`）→ **error 级**，启动即退出并在终端逐行列出受影响学校；
- `list_url` 域名与该校其它已知来源不一致时给 warning（弱信号，不阻断）。

这是最便宜的一道保险：本次事故的 8 小时损耗，理论上应该在进程启动的第 1 秒就终止。

**B. 同因熔断（circuit breaker）**

在 `main.py` 的任务循环内维护一个滑动窗口计数器：

```
key = (domain, error_class)      # error_class ∈ {conn_reset, dns, http_5xx, ...}
窗口内同一 key 累计 ≥ K（默认 5，可用 --circuit-break-threshold 调）→
  该 domain 挂起，剩余含该 domain 的任务直接标记 skipped_unreachable
  并写入 failures.json（status=skipped，附聚合说明），不再逐个重试
```

与现有域名冷却的区别：冷却是"慢下来"，熔断是"停止并汇报"。二者互补保留。

**C. 错误分类器**

新增 `utils/errors.py:classify_error(exc) -> str`，按异常类型映射到固定枚举：

| 异常特征 | 分类 |
| --- | --- |
| `requests.exceptions.ConnectionError` + `NameResolutionError` | `dns_error` |
| `ConnectionResetError` / `RemoteDisconnected` / `ProtocolError` | `connection_error` |
| `ReadTimeout` / `ConnectTimeout` | `timeout` |
| HTTP 403/429/401 | `blocked`（触发反爬冷却） |
| HTTP 5xx | `http_error` |
| 选择器匹配为空 / JSON 结构不符 | `parse_error`（**唯一保留此标签的场景**） |

`failures.json` schema 不变，仅 `error_type` 取值域扩大；面板「失败记录」页的分类统计卡片同步支持新枚举（纯展示层改动）。

### 4.3 URL 自动发现流水线 `spiders/url_resolver.py`（P0，约 1.5 人日）

输入：`university` + `college` 名称。输出：带置信度的候选 URL 列表 + 建议的 `list_type`，**落盘到 `data/candidates/{学校}_{学院}.json` 等待人工在面板/CLI 确认**（不自动写回 school_data.json，防止脏数据静默入库）。

四步流水线：

1. **站点搜索**：`"{university} {college} 师资队伍"` 走 DuckDuckGo html 端点（无需 key）+ Bing 兜底，取 top-20；过滤出 `*.edu.cn` 且二级域名归属该校（用 WHOIS-free 的启发式：域名前缀包含校名拼音缩写 / 与学校主站同域）。
2. **链接挖掘**：先抓学校主页导航栏，提取所有 `/szdw`、`/rsgz`、`/teacher(s)`、`师资`、`队伍` 等关键词锚点的站内链接；比搜索引擎更准，因为很多学院页不出现在搜索前 20 名。
3. **特征打分**：对每个候选页下载后评分——
   - 命中教师卡特征（`jsbt`、`.name`、`职称`、`教授/副教授/讲师` 密度高）→ 强正分；
   - 命中分页控件 / `generalQuery` / `queryObj=teacherHome` → 判定 `ajax_api` 型并加分；
   - 页面主体是 `<canvas>` / 空 body / 需要 JS → 判定 `js_render` 型；
   - 站内 `.pdf` 公告中含"师资""教师名录" → 判定 `pdf_list` 型。
4. **连通性探测**：复用现有 `POST /api/config/test` 的探测逻辑做最终验证（状态码、编码、内容长度 > 阈值），把结果连同得分一起写入候选文件。

人工确认入口：CLI `python main.py --review-candidates [学校]` 交互式选择；面板「配置管理」页增加"候选 URL"区，点选后一键回填对应学院的 `list_url` / `list_type` 并触发保存前校验。

### 4.4 抓取引擎扩展（P1，约 2 人日）

| 引擎 | 现状 | 2.0 动作 |
| --- | --- | --- |
| `static_list.py` | 已有 | 补三项健壮性：响应编码自动嗅探（`resp.encoding = resp.apparent_encoding` 兜底 GBK）、列表项数为 0 时区分"真没有"与"选择器失效"（后者落 `parse_error` 并附页面快照到 raw）、详情页 404 时降级保留列表页字段 |
| `ajax_api.py` | SudyCMS/WebPlus | 抽成"通用 JSON 接口适配器"：`list_url` 指向接口时，用 `faculty.api_config`（method / form 参数模板 / 数据路径 JSONPath）描述接口，selectors 改为 JSONPath；老配置零迁移 |
| `js_render.py` | 无 | 新增 Playwright headless 引擎（依赖已在环境内）：等待选择器出现后 `page.content()` 交给现有 BS4 解析链，**下游完全复用**；仅在 `list_type == "js_render"` 时启用，控制开销 |
| `pdf_list.py` | 无 | 新增 pdfplumber 表格抽取：识别"姓名/职称/研究方向"表头行，按表切列；用于 PDF 公示名单类学院 |

`list_type` 枚举扩展为 `static_html / ajax_api / js_render / pdf_list`，`main.py` 的分派逻辑改为注册表模式（type → engine 函数），新增引擎不再动调度代码。

### 4.5 数据质量护栏（P2，约 0.5 人日）

- **采样抽检**：每校采集完随机抽 3 名导师，检查 `name` 非空且长度 2~4 字、`title` 属于受控词表（教授/副教授/讲师/研究员…）；命中率 < 50% 则该学院结果标 `suspect`，不进合并，提示 selector 可能失效；
- **数量合理性**：学院导师数 < 5 或 > 150 时打 warning 进 overview；
- **变更告警**：同一学院两次成功采集的导师数波动 > 30% 时在日志与面板 overview 提示（官网改版的最早信号）。

---

## 五、实施顺序与验收标准

| 阶段 | 内容 | 工时 | 验收标准 |
| --- | --- | --- | --- |
| **M0** | §4.2 调度层修复（体检 + 熔断 + 分类器）+ 对应单测 | 0.5d | 用占位 URL 启动，进程 1s 内退出并列出清单；mock 同域名连败 5 次后其余任务全部 `skipped`；`classify_error` 对 6 类异常的映射用例全绿 |
| **M1** | §4.3 url_resolver + 面板候选确认 UI | 1.5d | 对东南大学机械工程学院、同济大学机械与能源工程学院跑发现流水线，top-3 候选中包含正确师资页；确认后 CLI 单校采集产出非空 jsonl |
| **M2** | §4.4 四引擎齐备 + 注册表分派 | 2d | 每种 list_type 至少 1 个真实学院端到端通过；全量 335 个存量用例 + 新增用例通过 |
| **M3** | §4.5 质量护栏 + 文档更新（README/DESIGN/INTERFACE_SPEC） | 0.5d | suspect 标记在 overview 可见；文档与实际行为一致 |

里程碑之间允许并行：M1 的发现流水线可以先用 M0 完成后的 CLI 手工喂 URL 验证引擎，不必等 UI。

**试点口径**：M1 完成前先只对 3 所学校（东南大学、同济大学、浙江大学）开放 Source A 全量采集，跑通后再放开 `__all__`。

---

## 六、风险与对策

| 风险 | 影响 | 对策 |
| --- | --- | --- |
| 搜索引擎结果不稳定（DuckDuckGo 偶尔限流） | 发现召回率下降 | 双引擎（DDG+Bing）互为兜底；**站内导航挖掘永远优先于搜索结果**；最终有人工确认环节兜底，不会静默错配 |
| 学院官网改版导致 selector 批量失效 | 解析成功率骤降 | §4.5 的 suspect 抽检 + 变更告警把失效暴露在"下一轮采集"而非"用户投诉"；raw 原件落盘保留现场便于修 selector |
| Playwright 引入内存占用（headless 常驻 ~200MB） | 长时批量任务资源压力 | 仅 js_render 型学院按需启停浏览器实例，用完即关；并发数单独设上限（默认 2，独立于 `--workers`） |
| 误判 URL 指向错误学院（如同名"机械工程学院"在不同校区） | 数据串校 | 候选打分中加入"页面文本包含学院全称"硬校验；人工确认时展示页面标题预览 |
| 法律与合规 | 抓取频率过高可能影响对方服务 | 保持现有礼貌限速（1~3s 随机延迟、UA 标识、缓存 7 天）；熔断机制同时降低了对故障域名的无效请求量 |

---

## 七、立即可执行的止血动作（今天就能做，不等开发）

在 M0 合入之前，若需要立即看到真实数据，可以手工执行以下最小步骤：

1. 打开 `config/school_data.json`，将 2~3 所试点学校的 `list_url` 替换为真实师资页地址（浏览器访问学院官网 → 师资队伍 → 复制 URL）；
2. 用面板「配置管理」的 URL 连通性测试确认可达；
3. `python main.py --school 东南大学 --source source_a --force`，确认 `data/output/` 出现非空 `{学校}_{学院}_faculty.jsonl`。

这一步本身也是 M1 验收前的手工基线：如果手工填对 URL 仍采不到，说明问题还有一层（selector 不匹配），届时以 raw 原件为准调整 `detail_selectors`。

---

## 附：关键证据索引

- `data/output/failures.json` — 233 条失败，全部 `parse_error`，URL 全部 `http://x.com`
- `data/output/crawl.log`（2026-09-15 07:39–11:41）— 单轮全量约 4 小时仍在逐校重试同一坏域名
- `config/school_data.json` — `list_url` 分布统计：`x.com ×222`、`test.edu.cn ×1`
- `main.py:415/432/449` — 三处 catch-all 写 failure 的位置（分类器改造点）
- `utils/http.py:62-196` — 现有 Retry / 退避 / 域名冷却实现（保留，与熔断互补）
- `docs/GITHUB_RESEARCH.md` — 同类工程调研（freecho/yzw 等），2.0 限速与断点策略沿用其结论
