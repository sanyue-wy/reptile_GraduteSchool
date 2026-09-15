# 研究生导师信息采集系统 · 使用说明

面向双一流高校机械 / 自动化类学院研究生导师信息的采集、合并与监控系统。
系统从两个数据源抓取导师信息——**Source A**（学院官网师资页）与 **Source B**（研招网招生专业目录），
按姓名匹配合并后导出 Excel 汇总表，并提供 Flask API 与 Web 监控面板（dashboard）。

---

## 1. 环境准备

- Python 3.10+（开发验证环境：3.12.7，Windows / Linux 均可）
- 安装依赖：

```bash
pip install -r requirements.txt        # 运行依赖：flask / requests / beautifulsoup4 / lxml / openpyxl / pdfplumber
pip install -r requirements-dev.txt    # 可选：pytest / pytest-cov 等测试工具
```

---

## 2. 快速开始

### 2.1 方式一：Web 监控面板（推荐）

```bash
python -m api.server --port 5000
```

启动后约 1 秒自动打开默认浏览器，跳转到 **http://127.0.0.1:5000/**（日志中也会打印面板地址）。
前端页面由 Flask 同源托管（`/` 即 dashboard 首页），因此页面内的 API 调用自动指向同一后端，无需额外配置、无跨域问题。

> 侧边栏底部会显示「后端在线」。若显示「后端离线（演示模式）」，说明 API 未连通，
> 页面正在展示内置 Mock 演示数据——请确认是通过上述同源地址访问、且服务已启动。

可选参数：

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `--port` | 监听端口 | 5000 |
| `--host` | 监听地址 | 127.0.0.1 |
| `--debug` | Flask debug 模式 | 关闭 |
| `--no-browser` | 不自动打开 WEB 面板 | 关闭（即默认自动打开） |

### 2.2 方式二：命令行采集

```bash
# 采集指定学校
python main.py --school 东南大学 同济大学

# 采集全部已配置学校
python main.py --school __all__

# 只跑 Source A、强制重抓、4 线程
python main.py --school 东南大学 --source source_a --force --workers 4

# 重试所有失败项
python main.py --retry-failed
```

命令行采集结束后自动合并并生成 `data/output/summary.xlsx` 全量汇总表。

---

## 3. 命令行参数一览（main.py）

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--school` | 目标学校列表（空格分隔）；`__all__` 表示全部 | 全部 |
| `--category` | 学科分类：`mechanical` / `automation` | 两者 |
| `--source` | 数据源：`source_a` / `source_b` | 两者 |
| `--year` | 数据年份 | 当前年 |
| `--workers` | 并发线程数 | 4 |
| `--force` | 强制重新采集已完成项 | 关 |
| `--resume` | 断点续抓（跳过已完成） | 关 |
| `--retry-failed` | 重试所有失败项 | 关 |
| `--delay` | 请求延迟范围（秒，两个数） | 1.0 3.0 |
| `--max-retries` | 最大重试次数 | 3 |
| `--timeout` | 连接超时（秒） | 30 |
| `--cooldown-threshold` | 反爬冷却触发阈值（连续失败次数） | 5 |
| `--cooldown-seconds` | 冷却等待秒数 | 1800 |
| `--raw-dir` | 原件落盘目录 | data/raw |
| `--no-cache` | 禁用页面缓存 | 关 |
| `--cache-days` | 页面缓存新鲜期（天） | 7 |

启动时会对 `config/school_data.json` 做校验，存在 error 级问题时直接退出（退出码 1）并在日志中列出原因。

---

## 4. 配置学校（config/school_data.json）

文件为 JSON 数组，每所学校一项。最小示例：

```json
[
  {
    "university": "东南大学",
    "level": "985",
    "categories": [
      {
        "college": "机械工程学院",
        "category": "mechanical",
        "faculty": {
          "list_url": "http://me.seu.edu.cn/xscz/list.htm",
          "list_type": "static_html",
          "list_item_selector": "li > a[title=姓名]",
          "detail_selectors": { "name": ".carrer .jsbt" }
        },
        "notice": { "enabled": true }
      }
    ]
  }
]
```

关键字段：

| 字段 | 说明 |
| --- | --- |
| `university` | 学校名（唯一标识，须与研招网匹配用名一致） |
| `level` | 985 / 211 / 双一流 |
| `categories[].college` | 学院名 |
| `categories[].category` | `mechanical` 或 `automation` |
| `categories[].faculty.list_type` | `static_html`（静态列表页）或 `ajax_api`（接口返回 JSON） |
| `categories[].faculty.list_url` | 师资列表入口 URL |
| `categories[].notice.enabled` | 是否启用 Source B（研招网）匹配 |

配置修改方式（任选其一）：

1. 直接编辑 `config/school_data.json`；
2. 面板「配置管理」页在线编辑并保存（保存前自动校验）；
3. 面板「配置管理」页导入 / 导出整份配置（支持 `.json`）。

「配置管理」页还提供 **URL 连通性测试**（`POST /api/config/test`），可在保存前验证 `list_url` 是否可达。

---

## 5. 数据流与输出文件

```
data/raw/                                抓取原件（HTML / JSON）落盘
data/output/
  {学校}_{学院}_faculty.jsonl            Source A 中间产物
  {学校}_{学院}_notice.jsonl             Source B 中间产物
  {学校}_{学院}.jsonl                    合并结果（统一 Schema）
  summary.xlsx                           全量汇总表（Excel）
  failures.json                          失败记录
  progress.json / crawl.log              采集进度与运行日志
```

合并结果中每条记录带 `match_status`：

| 取值 | 含义 |
| --- | --- |
| `merged` | 官网与研招网均匹配到 |
| `partial_faculty` | 仅官网有 |
| `partial_notice` | 仅研招网有 |

导出途径：面板「导师数据」页导出按钮（Excel / JSON），或直接请求 `GET /api/tutors/export?format=xlsx|json`。

---

## 6. 监控面板各页面

| 页面 | 路径 | 主要功能 |
| --- | --- | --- |
| 总览面板 | `/`（index.html） | 统计卡片、三线进度（Source A / Source B / 合并）、来源占比图、最近导师与失败、实时日志；「开始采集」按钮提交采集任务 |
| 学校列表 | `/schools.html` | 按状态 / 分类 / 关键字筛选学校，查看各校 Source A/B 状态与导师数，单校触发采集 |
| 导师数据 | `/tutors.html` | 导师检索与筛选（学校 / 学院 / 导师级别 / 匹配状态）、详情弹窗、导出 |
| 失败记录 | `/failures.html` | 失败列表与分类统计、单条 / 全部重试、忽略 |
| 配置管理 | `/config.html` | 全局参数与学校配置在线编辑、校验报告、URL 测试、配置导入导出 |

采集为后台任务：提交后通过 `GET /api/tasks/{task_id}` 轮询进度，面板自动刷新状态。

---

## 7. 失败处理

- 失败记录写入 `data/output/failures.json`，状态为 `active` / `resolved` / `ignored`，错误类型含 `http_error` / `timeout` / `parse_error` / `dns_error`。
- 重试：面板「失败记录」页勾选重试或「全部重试」，等价于 `POST /api/failures/retry`；命令行用 `python main.py --retry-failed`。
- 忽略：面板单条忽略，等价于 `POST /api/failures/{id}/ignore`。
- 触发反爬冷却（同一域名连续失败达阈值）后该域名暂停 `--cooldown-seconds` 秒，属预期行为。

---

## 8. API 一览（17 个接口）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/overview` | 总览统计、进度、来源占比、最近导师/失败、日志 |
| GET | `/api/schools` | 学校列表（q / status / category / 分页） |
| GET | `/api/schools/{id}` | 学校详情（各学院配置与状态） |
| POST | `/api/crawl` | 提交采集任务（schools / categories / sources / force / year） |
| GET | `/api/tasks/{task_id}` | 查询任务进度 |
| GET | `/api/tutors` | 导师列表（q / school / college / level / match / 分页） |
| GET | `/api/tutors/{school}/{name}` | 导师详情 |
| GET | `/api/tutors/export` | 导出导师数据（format=xlsx 或 json） |
| GET | `/api/failures` | 失败记录（status / source / 分页） |
| POST | `/api/failures/retry` | 重试失败（failure_ids 或 retry_all） |
| POST | `/api/failures/{id}/ignore` | 忽略单条失败 |
| GET | `/api/raw/{path}` | 查看抓取原件（限 data/raw 内） |
| GET | `/api/config` | 读取全局配置、学校配置与校验报告 |
| PUT | `/api/config/schools/{name}` | 保存单校配置（带校验） |
| PUT | `/api/config/global` | 保存全局配置 |
| POST | `/api/config/test` | URL 连通性测试 |
| POST / GET | `/api/config/import` 、 `/api/config/export` | 配置导入 / 导出 |

统一响应体：`{"code": 0, "data": ...}`；`code != 0` 为业务错误，HTTP 状态码与 `code` 语义见 `docs/INTERFACE_SPEC.md`。

---

## 9. 运行测试

```bash
python -m pytest                 # 全量 335 个用例
python -m pytest tests/test_api.py -q
```

全部测试离线运行（HTTP 用 Mock），不访问真实网络，可在 CI 直接执行。

---

## 10. 常见问题

- **面板显示演示数据 / 后端离线**：未通过同源地址访问或后端未启动。请用 `python -m api.server` 启动后访问 `http://127.0.0.1:5000/`，不要以 `file://` 方式直接打开 HTML。
- **端口被占用（Windows）**：`netstat -ano | findstr :5000` 找到 PID 后 `taskkill /F /PID <pid>`，再重启服务。旧的 Flask 进程未退出时会出现"改了代码不生效"，务必确认只有一个服务进程。
- **启动即退出并报配置错误**：`school_data.json` 校验未通过，按日志逐条修正，或到「配置管理」页查看校验报告。
- **采集完成但没有 summary.xlsx**：合并数据为空时会跳过导出；确认 `data/output/` 下存在非 `_faculty` / `_notice` 结尾的合并 jsonl。
- **想重新抓取已缓存页面**：加 `--force`，或 `--no-cache` 完全禁用缓存；缓存默认 7 天过期（`--cache-days`）。

---

更多设计细节见 `docs/` 目录：`REQUIREMENTS.md`（需求）、`DESIGN.md`（架构）、`INTERFACE_SPEC.md`（接口规范）、`FRONTEND_BACKEND_SPEC.md`（前后端约定）等。
