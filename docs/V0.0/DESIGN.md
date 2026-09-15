# 技术设计与执行流程

> 配套文档：[REQUIREMENTS.md](REQUIREMENTS.md)（需求）｜本文档回答：**用什么技术、代码怎么跑、整体思路是什么**

---

## 一、技术选型

| 层 | 技术 | 选择理由 |
|---|---|---|
| 语言 | Python 3.10+ | 生态成熟，团队熟悉 |
| HTTP 请求 | `requests` + `httpx`（备用） | 静态页够用；httpx 支持超时更细 |
| HTML 解析 | `BeautifulSoup4` + `lxml` | 选择器灵活，容错好 |
| JS 渲染兜底 | `playwright`（**按需引入**） | 仅当调研确认某校页面必须 JS 渲染时启用，默认不装 |
| PDF/Excel 公示解析 | `pdfplumber`（PDF 表格）、`openpyxl`（xlsx） | 覆盖"名单以附件发布"的主流情况 |
| OCR（暂缓） | `paddleocr` | 仅当扫描件数量进入 unknown_format 队列达到阈值再评估 |
| 数据存储 | JSONL（中间态）→ `pandas` → Excel（交付态） | 轻量、无数据库依赖，单机可跑 |
| 任务编排 | 标准库 `concurrent.futures` 线程池 + 自研断点续抓 | 抓取是 IO 密集，线程足够；不上 Scrapy/Celery（规模 147 所 × 2 学院，无需分布式） |
| 配置管理 | `config/schools.py`（Python 字典列表） | 学校条目需要人工核对，代码即文档 |
| CLI | `argparse` | 零依赖 |
| 日志 | `logging`（控制台 + 滚动文件） | 全量跑 147 所需可追溯 |

**明确不用的**：Scrapy（框架约束 > 灵活性，且插件化 parser 自己写更直接）、Selenium（慢，Playwright 替代）、MySQL/SQLite（数据量 ~万人级导师，文件即可）。

---

## 二、整体架构与数据流

```
                    ┌─────────────────────────────────────────────────┐
                    │              main.py (CLI 编排)                  │
                    │  --school --category --year --force              │
                    │  --retry-failed --limit                          │
                    └──────────────┬──────────────────────────────────┘
                                   │ 读取 config/schools.py
         ┌─────────────────────────┼──────────────────────────┐
         ▼                         ▼                          ▼
  ┌──────────────────┐   ┌────────────────────┐   ┌─────────────────────┐
  │ Source A: 官网师资 │   │ Source B: 研招网      │   │ Source C: 研究生院    │
  │ list/detail spider│   │ 专业目录 (主数据源)    │   │ 公示 (补充层)        │
  │ (requests/BS4)   │   │ yzw_major_parser    │   │ notice_parser       │
  └────────┬─────────┘   │ (对接 zsml/rs/dws.do)│   │ (插件化,按需启用)    │
           │             └──────────┬──────────┘   └──────────┬──────────┘
           ▼                        ▼                          ▼
  data/raw/<校>/faculty/   data/raw/<校>/yzw/         data/raw/<校>/<年份>/notice/
  （HTML 原件）            （API JSON 原件）           （公示原件）
           │                        │                          │
           ▼                        ▼                          ▼
  faculty.jsonl            yzw_major.jsonl            notice.jsonl
  （姓名/职称/方向/邮箱）   （导师/名额/方向/科目）    （姓名/类别/在招状态）
           │                        │                          │
           └────────────┬───────────┴──────────────────────────┘
                        ▼
         pipelines/merge.py  三源按「姓名+学院」软合并
         （精确→merged / 部分→partial / 模糊走 difflib）
                        ▼
         pipelines/export.py
         ├─ data/output/<校>_<学院>.json
         ├─ data/output/summary.xlsx（全校汇总）
         └─ data/output/failures.json（失败隔离）
```

**核心原则：原件先行**。任何一页抓到就先落盘 `data/raw/`，再解析。解析挂了可以离线重跑，不用重新请求网站。

---

## 三、代码运行流程（一次完整执行发生了什么）

### 命令示例
```bash
python main.py --school 东南大学 --year 2026          # 单校试点
python main.py --all --year 2026 --workers 4          # 全量 147 所
python main.py --retry-failed                         # 补跑失败项
python main.py --school 东南大学 --force               # 强制刷新已完成的
```

### 执行时序
1. **加载配置**：读 `config/schools.py`，展开成任务列表，任务粒度 = `学校 × 学院 × 数据源(A/B)`
2. **断点过滤**：读 `data/output/progress.json`（记录每个任务的完成状态），去掉已完成任务（除非 `--force`）
3. **Source A 抓取**（每任务）：
   - `list_spider.fetch_list()`：请求师资列表页 → 存原件 → 解析出教师条目（姓名 + 详情页链接）→ 自动翻页直到重复/末页
   - `detail_spider.fetch_detail()`：逐人请求详情页 → 存原件 → 提取职称、研究方向、邮箱
   - 输出 `faculty.jsonl`（一人一行）
4. **Source B 抓取**（每任务）：
   - `fetch_notice()`：请求研究生院公示列表 → 按标题正则（含"招生""指导教师/导师""名单""公示"+年份）定位目标公告 → 下载正文或附件（HTML/PDF/XLSX）→ 存原件
   - `parsers/dispatch.py`：按配置里的模板类型路由到对应 parser；识别不了 → 记入 `unknown_format` 队列，任务标记 `partial_success` 继续
   - 输出 `notice.jsonl`（一人一行：姓名/类别/方向/是否在名单）
5. **合并**：`merge.py` 对两路 jsonl 做姓名+学院匹配（精确 → 去空格归一 → `difflib` 相似度 ≥0.85 兜底），产出带 `match_status` 的合并记录
6. **导出**：`export.py` 写单校 JSON、追加全校 summary.xlsx、更新 failures.json 和 progress.json
7. **限速贯穿全程**：所有 HTTP 请求经过 `utils/http.py` 的统一出口，随机 1~3s 间隔 + 指数退避重试（最多 3 次，429/5xx 触发）

### 失败处理矩阵
| 故障 | 行为 |
|---|---|
| 列表页 404/改版 | 该任务记 failures.json（附 URL+错误码），其余任务不受影响 |
| 某人详情页打不开 | 保留其列表页字段，详情字段置 null，记 warning 不记 failure |
| 公示格式未识别 | 原件已落盘，任务标 partial_success，进 unknown_format 队列 |
| 整站反爬封禁 | 连续 5 次 403/验证码特征 → 暂停该域名 30 分钟（冷却），任务挂起而非失败 |

---

## 四、关键模块设计

### 1. `config/schools.py` — 配置即数据
```python
{
  "university": "东南大学",
  "categories": [{
    "college": "机械工程学院",
    "category": "mechanical",
    "faculty": {                          # Source A
      "list_url": "...",                  # 师资列表入口
      "list_item_selector": "...",        # 教师条目 CSS 选择器
      "detail_selectors": {...}           # 详情页各字段选择器
    },
    "notice": {                           # Source B
      "entry_url": "...",                 # 研究生院公示栏目
      "title_pattern": r"(硕士|博士).*(导师|指导教师).*名单",
      "template": "table_html"            # 路由到 parsers/table_html.py
    }
  }]
}
```
新增一所学校 = 加一个字典条目，**不改任何 spider 代码**。

### 2. `utils/http.py` — 唯一网络出口
- 类 `PoliteSession`：内置 UA 池、`time.sleep(random.uniform(1,3))`、重试装饰器、响应必落盘 `save_raw(url, path) -> local_path`
- 所有模块禁止直接 import requests，保证限速/留痕不可绕过
- **东大实测校准**：两站无登录/验证码/WAF，API 调用需带 `Referer` + `X-Requested-With: XMLHttpRequest`；限速 1~3s 足够保守

### 3. Source A 的两种列表适配器（由东大调研确定的实际形态）
- `spiders/static_list.py` — 静态 HTML 名录（机械院型）：单页全量或分页，CSS 选择器从配置读
- `spiders/ajax_api.py` — SudyCMS/WebPlus AJAX 教师接口（自动化院型）：POST `/_wp3services/generalQuery?queryObj=teacherHome`，form 参数 `siteId/pageIndex/rows/conditions/orders/returnInfos/articleType/level`；**同建站平台的高校可整段复用**，批量阶段先探测该特征（页面含 `generalQuery` 字样即命中）
- 详情页两个 parser：`detail_me.py`（`.carrer` 头部 + `tit/con` 板块）、`detail_auto.py`（`.xing` + span 序列 + `<p>` 列表），共享"板块标题同义词表"（研究方向≈研究兴趣≈Research Interests）

### 4. `parsers/` — 公示解析器插件
- 约定接口：`def parse(raw_path: str, meta: dict) -> list[dict]`
- 注册表模式：`Parsers = {"table_html": ..., "pdf_excel": ..., "richtext_notice": ...}`
- 首批模板：纯 HTML 表格、Excel 附件、富文本遴选通知正文（东大学院级公示即此形态，整段去标签提取）；PDF 文本表格与扫描件进 unknown_format 队列

### 4. 统一导师 Schema（v1）
```json
{
  "schema_version": 1,
  "name": "张三",
  "university": "东南大学",
  "college": "机械工程学院",
  "category": "mechanical",
  "title": "教授",
  "advisor_level": "博导",
  "email": "zhangsan@seu.edu.cn",
  "profile_url": "https://...",
  "research_areas": ["机器人学", "智能制造"],
  "enrollment": {
    "in_roster_2026": true,
    "degree_types": ["学术型硕士", "博士"],
    "directions": [{"code": "085501", "name": "机械工程"}],
    "source_url": "https://gr.seu.edu.cn/xxx",
    "notice_year": 2026
  },
  "match_status": "merged | partial_faculty | partial_notice",
  "raw_ref": {"faculty": "data/raw/东南大学/faculty/xxx.html",
              "notice": "data/raw/东南大学/2026/notice/xxx.pdf"}
}
```

---

## 五、实施大致思路（为什么这么做）

1. **先攻最难的（阶段 1b）**：研究生院公示格式千校千面，是整个项目成败手。用东大先把"定位公告→下原件→选 parser"这条路踩通，后面的 146 所只是重复劳动 + 补 parser。
2. **两条数据源解耦**：官网师资页和公示页抓取逻辑、失败模式完全不同，各自独立成 pipeline，只在最后合并。任何一条断了，另一条的数据依然可用（partial 也不丢）。
3. **原件与解析分离**：网站会改版、公示会撤换，但 `data/raw/` 里躺着的原件永远可以重新解析——这是"冗余设计"的落地形态，比任何数据库备份都实在。
4. **配置驱动扩校**：把"每校的差异"全部压进 `schools.py`（URL、选择器、模板类型），代码只写共性。这样阶段 5 的批量工作变成"填表"，甚至可以让脚本半自动预填（搜索各校公示入口后生成待核对的配置草稿）。
5. **渐进式上重量工具**：默认纯 requests 静态抓取；只有调研证据表明某校必须 JS 渲染时才对该校启用 Playwright，避免全局拖慢。
6. **断点续抓是硬需求**：147 所全量跑预计数小时~数天（礼貌限速下），中途断网/改版/封 IP 必然发生，progress.json 让任何时候停下来都能续。

---

## 六、开发顺序（文件级）

| 序 | 文件 | 依赖 | 说明 |
|---|---|---|---|
| 1 | `utils/http.py` | 无 | PoliteSession + 落盘，最先写因为它被一切依赖 |
| 2 | `spiders/static_list.py` | http | 静态名录（东大机械院 `/xscz/list.htm` 为基准，选择器已确认） |
| 3 | `spiders/ajax_api.py` | http | SudyCMS generalQuery API（东大自动化院为基准，接口已逆向实测通过） |
| 4 | `spiders/detail_me.py` / `detail_auto.py` | http | 两学院详情页 parser，共享板块同义词表 |
| 5 | `parsers/` 富文本通知 parser | http | 对应年度遴选公示正文（模板 `richtext_notice`） |
| 6 | `pipelines/merge.py` | 上述 jsonl 格式 | 软合并 + match_status |
| 7 | `pipelines/export.py` | merge | JSON/xlsx/failures/progress |
| 8 | `main.py` | 全部 | CLI + 线程池编排 + 断点过滤 |
| 9 | `config/schools.py` 补全 | 阶段 1 调研（已完成） | 东大两条目可立即写入，其余批量填 |

> **阻塞点已解除**：东大调研完成，所有 URL、选择器、API 参数均已实测确认（见 REQUIREMENTS.md 阶段 1 表格）。唯一遗留：`seugs.seu.edu.cn` 在当前网络不可达，年度公示入口待正常网络下补验——但不阻塞开发，先用"导师资格标签 + 研究方向"主数据跑通全链路。
