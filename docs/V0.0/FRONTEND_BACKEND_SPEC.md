# 前后端对接技术报告

> 版本：v1｜日期：2026-09-14  
> 目标：明确前端 Dashboard 与后端爬虫引擎之间的接口约定、开发流程、技术栈和注意事项

---

## 一、整体架构概览

```
┌──────────────────────────────────────────────────────────┐
│                  前端 Dashboard (纯静态 HTML)               │
│  index.html · schools.html · tutors.html                  │
│  failures.html · config.html                               │
│  技术：原生 HTML/CSS/JS + Chart.js（CDN）                   │
└────────────────────────┬─────────────────────────────────┘
                         │  HTTP REST API（JSON）
                         ▼
┌──────────────────────────────────────────────────────────┐
│              后端 API 服务层（新增）                         │
│  Flask / FastAPI · 提供 REST 接口                          │
│  读写 data/output/*.json · progress.json                   │
│  调用 main.py 触发爬取任务                                  │
└────────────────────────┬─────────────────────────────────┘
                         │  Python 内部调用
                         ▼
┌──────────────────────────────────────────────────────────┐
│                 后端爬虫引擎（已有）                         │
│  main.py → spiders/ → parsers/ → pipelines/               │
│  utils/http.py · config/schools.py                        │
└──────────────────────────────────────────────────────────┘
```

**核心原则**：前端是纯静态页面，不直接访问文件系统；所有数据通过后端 API 获取，后端负责读取 `data/output/` 下的 JSON 文件并以标准格式返回。

---

## 二、API 接口清单（前端交接端口）

### 2.1 总览面板 `GET /api/overview`

> 对应页面：[index.html](dashboard/index.html)

**请求参数**：无

**响应格式**：

```json
{
  "stats": {
    "total_schools": 147,
    "done": 38,
    "running": 6,
    "failed": 3,
    "partial": 12,
    "pending": 88
  },
  "progress": {
    "source_a": { "completed": 44, "total": 147 },
    "source_b": { "completed": 100, "total": 147 },
    "merged":   { "completed": 38, "total": 147 }
  },
  "source_breakdown": {
    "matched": 6200,
    "notice_only": 1800,
    "faculty_only": 950,
    "unmatched": 340
  },
  "recent_tutors": [
    {
      "name": "张三",
      "title": "教授",
      "level": "博导",
      "school": "东南大学",
      "college": "机械工程学院",
      "areas": ["智能制造", "机器人学"]
    }
  ],
  "recent_failures": [
    {
      "school": "北京航空航天大学",
      "college": "机械工程学院",
      "source": "Source A",
      "error": "HTTP 403 Forbidden",
      "time": "2026-09-14T14:23:05"
    }
  ],
  "logs": [
    {
      "time": "2026-09-14T16:02:31",
      "level": "INFO",
      "msg": "东南大学/机械工程学院 Source A 完成，获取 196 条导师记录"
    }
  ]
}
```

**字段说明**：

| 字段 | 类型 | 说明 | 来源文件 |
|---|---|---|---|
| `stats` | object | 学校维度统计汇总 | `progress.json` 聚合 |
| `progress` | object | 三条管道各自进度 | `progress.json` |
| `source_breakdown` | object | 导师维度数据来源占比 | 合并后 `*.json` 统计 |
| `recent_tutors` | array | 最近采集的 6 位导师（首页预览卡片用） | 最新 `*.json` 取尾部 |
| `recent_failures` | array | 最近 5 条失败记录 | `failures.json` 取头部 |
| `logs` | array | 最近 20 条运行日志 | `crawl.log` 尾部 |

---

### 2.2 学校列表 `GET /api/schools`

> 对应页面：[schools.html](dashboard/schools.html)

**请求参数**（Query String）：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `q` | string | 否 | 学校名称模糊搜索 |
| `status` | string | 否 | 筛选状态：`done` / `partial` / `running` / `pending` / `failed` |
| `category` | string | 否 | 学科筛选：`mechanical` / `automation` |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20 |

**响应格式**：

```json
{
  "total": 147,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "id": 1,
      "name": "东南大学",
      "level": "985",
      "mech_college": "机械工程学院",
      "auto_college": "自动化学院",
      "source_a_status": "done",
      "source_b_status": "done",
      "tutor_count": 311,
      "match_rate": 95,
      "status": "done"
    }
  ],
  "summary": {
    "done": 38,
    "partial": 12,
    "running": 6,
    "pending": 88,
    "failed": 3
  }
}
```

**字段枚举值**：

| 字段 | 可选值 | 含义 |
|---|---|---|
| `status` | `done` / `partial` / `running` / `pending` / `failed` | 学校整体采集状态 |
| `source_a_status` | `done` / `running` / `pending` / `failed` | 官网师资页采集状态 |
| `source_b_status` | `done` / `running` / `pending` / `failed` | 研招网数据采集状态 |
| `level` | `985` / `211` / `双一流` | 学校层次 |

---

### 2.3 学校详情 `GET /api/schools/{school_id}`

> 对应页面：schools.html 点击「查看」按钮

**响应格式**：

```json
{
  "id": 5,
  "name": "东南大学",
  "level": "985",
  "categories": [
    {
      "college": "机械工程学院",
      "category": "mechanical",
      "faculty_config": {
        "list_url": "http://me.seu.edu.cn/xscz/list.htm",
        "list_type": "static_html"
      },
      "tutor_count": 196,
      "source_a_status": "done",
      "source_b_status": "done",
      "last_crawl_at": "2026-09-14T16:02:31"
    }
  ]
}
```

---

### 2.4 触发采集 `POST /api/crawl`

> 对应按钮：「▶ 开始采集」「▶ 批量采集选中」「采集」（单校）

**请求体**：

```json
{
  "schools": ["东南大学", "清华大学"],
  "categories": ["mechanical", "automation"],
  "sources": ["source_a", "source_b"],
  "force": false,
  "year": 2026
}
```

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schools` | string[] | 是 | 要采集的学校名称列表；传 `["__all__"]` 表示全部 |
| `categories` | string[] | 否 | 限定学科，默认 `["mechanical", "automation"]` |
| `sources` | string[] | 否 | 限定数据源，默认全部 |
| `force` | bool | 否 | 是否强制重新采集已完成的，默认 `false` |
| `year` | int | 否 | 数据年份，默认当年 |

**响应格式**：

```json
{
  "task_id": "task_20260914_160000_a3f2",
  "status": "queued",
  "message": "已加入采集队列：东南大学（机械工程学院、自动化学院）、清华大学（机械工程系、自动化系）"
}
```

**注意**：采集是异步操作，前端需轮询 `GET /api/tasks/{task_id}` 获取进度。

---

### 2.5 任务状态查询 `GET /api/tasks/{task_id}`

**响应格式**：

```json
{
  "task_id": "task_20260914_160000_a3f2",
  "status": "running",
  "progress": {
    "total_steps": 8,
    "completed_steps": 3,
    "current_step": "东南大学/自动化学院 Source A 详情页解析中 (78/115)",
    "percent": 37.5
  },
  "started_at": "2026-09-14T16:00:00",
  "estimated_remaining": "12m"
}
```

| `status` 枚举 | 含义 |
|---|---|
| `queued` | 排队等待中 |
| `running` | 正在执行 |
| `completed` | 全部完成 |
| `failed` | 任务失败 |
| `cancelled` | 已取消 |

---

### 2.6 导师数据 `GET /api/tutors`

> 对应页面：[tutors.html](dashboard/tutors.html)

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `q` | string | 否 | 导师姓名模糊搜索 |
| `school` | string | 否 | 按学校筛选 |
| `college` | string | 否 | 按学院筛选 |
| `level` | string | 否 | 按导师级别：`博导` / `硕导` |
| `match` | string | 否 | 按匹配状态：`merged` / `partial_faculty` / `partial_notice` |
| `page` | int | 否 | 页码，默认 1 |
| `page_size` | int | 否 | 每页条数，默认 20 |

**响应格式**：

```json
{
  "total": 1234,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "name": "张三",
      "school": "东南大学",
      "college": "机械工程学院",
      "title": "教授",
      "level": "博导",
      "email": "zhangsan@seu.edu.cn",
      "profile_url": "https://me.seu.edu.cn/zhangsan",
      "areas": ["智能制造", "机器人学"],
      "enrollment": {
        "in_roster": true,
        "directions": [{"code": "085501", "name": "机械工程"}],
        "degree_types": ["学术型硕士"],
        "source_url": "https://yz.chsi.com.cn/..."
      },
      "match_status": "merged",
      "source_type": {
        "faculty": "官网师资页",
        "notice": "研招网"
      }
    }
  ]
}
```

**注意**：`enrollment` 字段可为 `null`（当仅有 Source A 数据时）。

---

### 2.7 导师详情弹窗 `GET /api/tutors/{school}/{name}`

> 对应页面：tutors.html 点击「详情」按钮，打开 Modal

**响应格式**：同 2.6 单条导师对象，额外包含：

```json
{
  "...": "...（同上）",
  "raw_ref": {
    "faculty": "data/raw/东南大学/me.seu.edu.cn/20260914_list.html",
    "notice": "data/raw/东南大学/2026/notice/yzw.json"
  }
}
```

---

### 2.8 导师数据导出 `GET /api/tutors/export`

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `format` | string | 是 | `excel` 或 `json` |
| `school` | string | 否 | 限定学校（不传则导出全部） |
| `college` | string | 否 | 限定学院 |

**响应**：直接返回文件下载（`Content-Disposition: attachment`）

---

### 2.9 失败记录 `GET /api/failures`

> 对应页面：[failures.html](dashboard/failures.html)

**请求参数**：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `status` | string | 否 | `active` / `resolved` / `ignored`，默认全部 |
| `source` | string | 否 | `source_a` / `source_b` |

**响应格式**：

```json
{
  "total": 12,
  "summary": {
    "http_error": 5,
    "timeout": 4,
    "parse_error": 3
  },
  "items": [
    {
      "id": "fail_001",
      "school": "北京航空航天大学",
      "college": "机械工程及自动化学院",
      "source": "Source A",
      "error_type": "http_403",
      "error_message": "HTTP 403 Forbidden — 触发反爬冷却",
      "url": "https://mea.buaa.edu.cn/szdw/list.htm",
      "occurred_at": "2026-09-14T14:23:05",
      "retry_count": 3,
      "status": "active"
    }
  ]
}
```

| `error_type` 枚举 | 含义 |
|---|---|
| `http_403` | 反爬封禁 |
| `http_404` | 页面不存在 |
| `timeout` | 连接超时 |
| `dns_error` | DNS 解析失败 |
| `parse_error` | 页面结构无法解析 |

| `status` 枚举 | 含义 |
|---|---|
| `active` | 待重试 |
| `resolved` | 已自动恢复 |
| `ignored` | 用户手动忽略 |

---

### 2.10 重试失败项 `POST /api/failures/retry`

**请求体**：

```json
{
  "failure_ids": ["fail_001", "fail_003"],
  "retry_all": false
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `failure_ids` | string[] | 指定要重试的失败 ID 列表 |
| `retry_all` | bool | 为 `true` 时忽略 `failure_ids`，重试全部 `active` 状态 |

**响应**：返回同 `POST /api/crawl` 的任务格式（异步执行）。

---

### 2.11 忽略失败项 `POST /api/failures/{id}/ignore`

**请求体**：无

**响应**：

```json
{ "id": "fail_001", "status": "ignored" }
```

---

### 2.12 查看原件 `GET /api/raw/{path}`

> 对应按钮：failures.html「📋 查看原件」

**请求参数**：`path` 为相对于 `data/raw/` 的路径（URL 编码）

**响应**：直接返回原始文件（HTML/JSON/PDF），`Content-Type` 按实际类型。

---

### 2.13 配置管理 `GET /api/config`

> 对应页面：[config.html](dashboard/config.html)

**响应格式**：

```json
{
  "global": {
    "delay_range": [1.0, 3.0],
    "max_retries": 3,
    "timeout": 30,
    "cooldown_threshold": 5,
    "cooldown_seconds": 1800,
    "workers": 4,
    "year": 2026,
    "fuzzy_threshold": 0.85,
    "user_agents": ["Mozilla/5.0 ..."]
  },
  "schools": [
    {
      "university": "东南大学",
      "categories": [
        {
          "college": "机械工程学院",
          "category": "mechanical",
          "faculty": {
            "list_url": "http://me.seu.edu.cn/xscz/list.htm",
            "list_type": "static_html",
            "list_item_selector": "li > a[title=姓名]",
            "detail_selectors": {
              "name": ".carrer .jsbt",
              "title": ".carrer .title",
              "email_re": "邮箱:([^\\s<]+)",
              "research": "tit==研究方向 → 兄弟 .con"
            }
          },
          "notice": {
            "enabled": false,
            "entry_url": "",
            "title_pattern": "",
            "template": ""
          }
        }
      ],
      "tutor_count": 311,
      "verified": true
    }
  ]
}
```

---

### 2.14 保存学校配置 `PUT /api/config/schools/{school_name}`

**请求体**：学校配置对象（结构同上 `schools[]` 中的单条）

**响应**：

```json
{
  "status": "ok",
  "message": "东南大学 配置已保存",
  "validation": { "valid": true, "errors": [] }
}
```

---

### 2.15 保存全局配置 `PUT /api/config/global`

**请求体**：全局配置对象（结构同上 `global` 字段）

**响应**：同 2.14

---

### 2.16 测试连接 `POST /api/config/test`

**请求体**：

```json
{
  "url": "http://me.seu.edu.cn/xscz/list.htm",
  "method": "GET",
  "headers": {}
}
```

**响应**：

```json
{
  "status_code": 200,
  "reachable": true,
  "response_time_ms": 342,
  "content_type": "text/html",
  "content_length": 48520,
  "sample_title": "师资队伍 - 机械工程学院"
}
```

---

### 2.17 导入/导出配置 `POST /api/config/import` / `GET /api/config/export`

- **导入**：上传 `.json` 或 `.py` 文件，后端解析后返回校验结果
- **导出**：直接返回 `config/schools.py` 文件下载

---

## 三、后端开发流程

### 3.1 待开发模块清单

| 优先级 | 模块 | 文件 | 状态 | 说明 |
|---|---|---|---|---|
| P0 | 合并管道 | `pipelines/merge.py` | ⚠️ 需重写 | 三源软合并 + match_status |
| P0 | 导出管道 | `pipelines/export.py` | ❌ 未开始 | JSON 明细 + summary.xlsx + failures.json |
| P0 | 主入口 | `main.py` | ❌ 未开始 | CLI 编排 + 线程池 + 断点续抓 |
| P0 | 进度追踪 | `utils/progress.py` | ❌ 未开始 | progress.json 读写 |
| P1 | API 服务 | `api/server.py` | ❌ 未开始 | Flask/FastAPI 提供 REST 接口 |
| P1 | 学校配置 | `config/schools.py` | ⚠️ 只有东大 | 147 所批量配置构建 |
| P2 | 前端对接 | `dashboard/` JS 改造 | ❌ 未开始 | fetch 替换 MOCK 数据 |

### 3.2 推荐开发顺序

```
阶段 A：数据管道补全（后端核心）
  ① pipelines/merge.py    ← 已有初版，需对齐 Schema v1
  ② pipelines/export.py   ← 新建
  ③ utils/progress.py     ← 新建，progress.json 读写
  ④ main.py               ← 新建，CLI + 线程池编排

阶段 B：API 服务层
  ⑤ api/__init__.py       ← 新建
  ⑥ api/server.py         ← 新建，Flask/FastAPI 路由
  ⑦ api/models.py         ← 新建，响应模型定义

阶段 C：前端对接
  ⑧ dashboard/api.js      ← 新建，封装 fetch + 错误处理
  ⑨ 各 HTML 页面           ← 替换 MOCK 为 API 调用

阶段 D：配置批量构建
  ⑩ config/schools.py     ← 147 所配置逐步填充
```

### 3.3 数据文件约定

| 文件路径 | 格式 | 读写方 | 说明 |
|---|---|---|---|
| `data/output/progress.json` | JSON | 后端读写 | 每个任务的完成状态 |
| `data/output/{校}_{院}.json` | JSON | 后端写，API 读 | 单校单院导师明细 |
| `data/output/summary.xlsx` | Excel | 后端写，API 导出 | 全校汇总表 |
| `data/output/failures.json` | JSON | 后端读写，API 读写 | 失败记录清单 |
| `data/raw/<学校>/<年份>/` | 原文件 | 后端写，API 读 | 原件快照 |
| `data/output/crawl.log` | 滚动日志 | 后端写，API 读尾部 | 运行日志 |
| `config/schools.py` | Python dict | 后端读，API 读写 | 学校配置 |

---

## 四、技术栈

### 4.1 前端

| 层 | 技术 | 版本 | 说明 |
|---|---|---|---|
| 结构 | 原生 HTML5 | — | 无框架，单文件页面 |
| 样式 | 原生 CSS3（CSS Variables） | — | 无预处理器，响应式 |
| 交互 | 原生 JavaScript（ES2020+） | — | 无打包工具 |
| 图表 | Chart.js | 4.4.x（CDN） | 仅 index.html 使用 |
| 数据请求 | 原生 `fetch()` API | — | 替换 MOCK 数据时使用 |

**为什么不用前端框架**：项目规模小（5 个页面），数据交互简单（读 JSON 为主），原生方案零构建成本，双击 HTML 即可预览。

### 4.2 后端

| 层 | 技术 | 版本 | 说明 |
|---|---|---|---|
| 语言 | Python | 3.10+ | 已有代码基础 |
| HTTP 请求 | `requests` | 2.31+ | 爬虫网络出口 |
| HTML 解析 | `BeautifulSoup4` + `lxml` | — | 已有 |
| JSONL 存储 | 标准库 `json` | — | 逐行读写 |
| Excel 导出 | `openpyxl` | 3.1+ | 生成 summary.xlsx |
| PDF 解析 | `pdfplumber` | 0.10+ | 公示附件解析（按需） |
| 任务编排 | `concurrent.futures.ThreadPoolExecutor` | 标准库 | IO 密集型，线程池够用 |
| CLI | `argparse` | 标准库 | 零依赖 |
| 日志 | `logging` | 标准库 | 控制台 + 滚动文件 |
| API 服务（新增） | `Flask` 或 `FastAPI` | Flask 3.x / FastAPI 0.110+ | REST 接口层 |

### 4.3 API 服务层选型建议

| 方案 | 优势 | 劣势 | 推荐场景 |
|---|---|---|---|
| **Flask** | 极简、生态成熟、团队熟悉度高 | 无原生异步 | 快速上线，请求量不大 |
| **FastAPI** | 原生 async、自动 Swagger 文档、类型校验 | 需要 Pydantic 模型定义 | 接口较多、未来可能有异步需求 |

**本项目推荐 Flask**：爬虫本身就是同步的，API 只是读写 JSON 文件，无高并发需求，Flask 开发速度最快。

---

## 五、注意事项

### 5.1 数据一致性

| 问题 | 策略 |
|---|---|
| 爬取过程中前端读取数据 | API 读取的是已完成的 JSON 文件，不会读到半写入状态；progress.json 用原子写（写临时文件再 rename） |
| 多线程并发写 progress.json | 加 `threading.Lock`，或改为 SQLite（后期按需升级） |
| 同一学校同时触发多次采集 | `POST /api/crawl` 需检查该学校是否有运行中的任务，有则返回 409 Conflict |

### 5.2 错误处理规范

所有 API 响应遵循统一格式：

```json
// 成功
{ "code": 0, "data": {...} }

// 失败
{ "code": 40001, "message": "学校名称不能为空", "detail": "..." }
```

| 错误码范围 | 含义 |
|---|---|
| 0 | 成功 |
| 40001-40099 | 参数校验错误 |
| 40401-40499 | 资源不存在 |
| 40901 | 任务冲突（重复采集） |
| 50001-50099 | 服务器内部错误 |

### 5.3 前端开发规范

| 规范 | 要求 |
|---|---|
| API 基地址 | 统一定义在 `dashboard/api.js` 的 `API_BASE` 常量，开发环境 `http://localhost:5000/api`，生产环境相对路径 `/api` |
| 错误处理 | 所有 `fetch` 调用统一包装，网络错误自动 Toast 提示 |
| 加载状态 | 每个页面进入时显示骨架屏/Loading，数据到达后替换 |
| 空状态 | 无数据时显示「暂无数据」插图，不显示空表格 |
| 分页 | 前端不缓存全量数据，每次翻页重新请求后端 |

### 5.4 安全注意事项

| 风险 | 措施 |
|---|---|
| API 被外部恶意调用 | 开发阶段无需认证；部署时绑定 `127.0.0.1`，仅本机访问 |
| 配置文件被篡改 | `PUT /api/config` 仅允许在开发/管理网络访问 |
| 文件路径穿越 | `GET /api/raw/{path}` 必须做路径白名单校验，禁止 `..` |
| 爬虫被滥用 | API 不暴露直接 URL 参数（不支持「帮我抓这个 URL」） |

### 5.5 部署方式

开发阶段最简方案：

```bash
# 终端 1：后端爬虫引擎
python main.py --school 东南大学 --year 2026

# 终端 2：API 服务
python api/server.py --port 5000

# 浏览器：打开前端
# 直接双击 dashboard/index.html，或
python -m http.server 8765 -d dashboard/
```

生产阶段建议：

```bash
# Nginx 反代 + Gunicorn
# nginx 配置：
#   /api → proxy_pass http://127.0.0.1:5000
#   /    → root /path/to/dashboard; index index.html
```

---

## 六、接口测试清单

开发完成后需验证的测试用例：

| 编号 | 场景 | 预期 |
|---|---|---|
| T01 | `GET /api/overview` 无数据 | 返回全零统计，不报错 |
| T02 | `GET /api/schools?status=done` | 仅返回已完成学校 |
| T03 | `GET /api/schools?q=东南` | 模糊匹配返回东南大学 |
| T04 | `GET /api/tutors?page=1&page_size=20` | 分页正确，total 准确 |
| T05 | `GET /api/tutors?level=博导` | 仅返回博导 |
| T06 | `POST /api/crawl` 重复触发 | 返回 409 Conflict |
| T07 | `POST /api/failures/retry` 重试全部 | 返回 task_id，任务开始执行 |
| T08 | `GET /api/config` | 返回完整配置 JSON |
| T09 | `PUT /api/config/schools/东南大学` 保存 | 写入成功，校验通过 |
| T10 | `POST /api/config/test` 测试可达 URL | 返回 200 + 响应时间 |
| T11 | `GET /api/raw/../../../etc/passwd` | 返回 403 拒绝（路径穿越防护） |
| T12 | `GET /api/tutors/export?format=excel` | 返回 .xlsx 文件下载 |

---

## 七、前端 MOCK 数据 → API 替换映射

开发前端对接时，按以下映射替换 MOCK 为 fetch 调用：

| 前端 MOCK 变量 | 替换为 | API 端点 |
|---|---|---|
| `MOCK_SCHOOLS` (index.html) | `fetch('/api/overview').then(...)` | `GET /api/overview` |
| `MOCK_TUTORS` (index.html 预览) | `overview.recent_tutors` | 同上 |
| `MOCK_FAILURES` (index.html) | `overview.recent_failures` | 同上 |
| `MOCK_LOGS` (index.html) | `overview.logs` | 同上 |
| Chart 硬编码数据 | `overview.stats` + `overview.source_breakdown` | 同上 |
| `SCHOOLS` (schools.html) | `fetch('/api/schools?...')` | `GET /api/schools` |
| `TUTORS` (tutors.html) | `fetch('/api/tutors?...')` | `GET /api/tutors` |
| 失败卡片 HTML (failures.html) | `fetch('/api/failures')` | `GET /api/failures` |
| `SAMPLE_CONFIG` (config.html) | `fetch('/api/config')` | `GET /api/config` |

---

*文档结束。有任何接口字段或流程需要调整，请在评审时标注。*
