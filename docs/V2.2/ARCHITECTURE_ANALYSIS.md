# 工程架构分析与优化方案

> 生成时间：2026-09-16
> 目标：对 `reptile_GraduteSchool` 工程进行详细架构分析，识别问题，给出优化方案

## 1. 工程概述

### 1.1 项目定位
双一流高校研究生导师信息采集系统，支持：
- Source A：官网师资页（静态HTML / AJAX API / JS渲染 / PDF）
- Source B：研招网专业目录（yz.chsi.com.cn API）
- 多源合并：姓名软匹配（精确/去空格/模糊三阶）
- 数据导出：JSONL / Excel
- 前端面板：Flask + Chart.js Dashboard

### 1.2 技术栈
- 语言：Python 3.12
- 框架：Flask 3.x, requests, BeautifulSoup4, lxml, openpyxl, pdfplumber
- 测试：pytest 9.x
- 并发：ThreadPoolExecutor

---

## 2. 详细架构分析

### 2.1 目录结构与文件职责

```
reptile_GraduteSchool/
├── main.py                    # 主编排入口（CLI + 并发调度 + 熔断）
├── api/
│   ├── __init__.py
│   └── server.py              # Flask API 服务（17个REST接口）
├── config/
│   ├── __init__.py
│   ├── loader.py              # 配置加载、缓存、保存
│   ├── validator.py           # 配置校验器
│   ├── plugins.py             # 插件系统管理
│   ├── dedup.py               # 配置去重与迁移
│   ├── major_mapping.py       # 专业代码映射
│   ├── school_data.json       # 学校配置数据
│   ├── school_level_raw.py    # 学校层级数据（985/211/双一流）
│   └── schools.py.bak         # 旧配置备份
├── spiders/
│   ├── __init__.py            # 引擎注册表
│   ├── static_list.py         # 静态HTML列表解析
│   ├── detail_parser.py       # 教师详情页解析
│   ├── ajax_api.py            # AJAX API 爬虫
│   ├── js_render.py           # Playwright JS渲染
│   ├── pdf_list.py            # PDF解析
│   ├── url_resolver.py        # URL自动发现
│   └── yzw_api.py             # 研招网API客户端
├── parsers/
│   ├── __init__.py            # 解析器注册表
│   ├── utils.py               # 解析工具
│   └── yzw_major.py           # 研招网专业目录解析器
├── processors/
│   └── __init__.py            # 处理器插件（normalize/dedup/merge）
├── exporters/
│   └── __init__.py            # 导出器插件（jsonl/xlsx）
├── pipelines/
│   ├── __init__.py
│   ├── merge.py               # 多源合并管道
│   └── export.py              # 导出管道
├── utils/
│   ├── __init__.py
│   ├── cache.py               # 页面缓存
│   ├── errors.py              # 错误分类器
│   ├── http.py                # HTTP会话封装
│   ├── logging_config.py     # 日志配置
│   └── progress.py            # 进度追踪
├── dashboard/                 # 前端面板
│   ├── index.html, schools.html, tutors.html, failures.html, config.html
│   ├── style.css
│   ├── api.js
│   └── components/            # toast.js, badge.js, pagination.js
├── tests/                     # 测试套件
│   ├── conftest.py            # 全局fixtures
│   ├── test_integration.py    # 端到端集成测试
│   ├── test_export.py, test_merge.py, test_parsers.py
│   ├── test_http.py, test_progress.py
│   ├── test_spiders_*.py
│   └── fixtures/              # 测试数据
├── scripts/                   # 辅助脚本
│   ├── crawl_all.py           # 全量采集启动脚本
│   ├── batch_discover_urls.py # 批量URL发现
│   └── review_candidates.py   # 候选审核
├── docs/                      # 文档
│   ├── V0.0/, V2.0/, V2.1/, V3.0/
│   └── V2.2/                  # 本文档
├── data/
│   ├── candidates/            # URL发现候选结果
│   ├── raw/                   # 原始页面缓存
│   └── output/                # 采集结果、日志、进度
└── requirements.txt
```
---

## 3. 核心缺陷分析

### 3.1 职责混乱（Single Responsibility Violation）

**main.py（829行）** 同时承担以下职责：
1. CLI 参数解析（argparse）
2. 配置加载与校验
3. 任务队列构建
4. 并发调度（ThreadPoolExecutor）
5. 熔断控制（CircuitBreaker）
6. 进度追踪（ProgressTracker）
7. 错误分类（classify_error）
8. 失败记录管理（add_failure / export_failures）
9. 导出触发（run_export_pipeline）
10. 统计输出

**api/server.py（1250+行）** 同时承担：
1. Flask 路由定义（17个接口）
2. 业务逻辑（crawl / config / plugins / failures）
3. 数据访问（直接读写文件系统）
4. 前端静态托管
5. 任务队列管理（内存 dict + threading）

### 3.2 缺乏抽象层

| 缺失的抽象层 | 影响 |
|---|---|
| 服务层（Service Layer） | API 直接调用爬虫/解析器/导出器，无业务封装 |
| 数据访问层（DAL） | 所有文件操作（open/jsonl/progress.json）直接内嵌 |
| 任务抽象 | CrawlTask 是简单数据类，无执行状态管理 |
| 引擎抽象 | 4个爬虫引擎各自独立实现，无统一接口 |

### 3.3 扩展性问题

- 新增数据源必须修改 `main.py`（run_source_a/run_source_b 硬编码调用具体爬虫）
- 新增处理插件需手动注册并修改流水线配置
- 配置格式变化需修改多个模块（loader.py / validator.py / main.py）

### 3.4 性能与并发问题

- 并发任务通过文件系统通信（progress.json / failures.json），无内存共享机制
- 熔断机制（CircuitBreaker）与冷却机制（PoliteSession）独立管理，状态不一致
- ProgressTracker 全局单例无注入机制，测试时难以隔离
- 缓存读取每次打开文件，无批量读取优化

### 3.5 测试覆盖不足

- 集成测试仅覆盖 Source A 流程
- 缺少熔断机制、插件安全检查、配置迁移测试
- fixtures 与真实配置耦合度高

---

## 4. 优化方案

### 4.1 架构重构：建立分层架构

```
┌─────────────────────────────────────────────┐
│              接口层（CLI / API）              │
│   main.py (CLI编排)  │  api/server.py (REST) │
└──────────┬──────────────────────┬─────────────┘
           │                      │
┌──────────▼──────────────────────▼─────────────┐
│              服务层（Service Layer）            │
│  CrawlerService  │  MergeService  │ ExportService │
└──────────┬──────────────────────┬─────────────┘
           │                      │
┌──────────▼──────────────────────▼─────────────┐
│             数据访问层（Storage Layer）         │
│  JSONLStore  │  ProgressStore  │  ConfigStore  │
└──────────────────────────────────────────────┘
           │
┌──────────▼─────────────────────────────────────┐
│             基础设施层（Utils / Spiders）        │
│  http │ cache │ progress │ parsers │ spiders     │
└──────────────────────────────────────────────┘
```

### 4.2 实施步骤

#### 阶段一：建立服务层（services/ 目录）

新建文件：
- `services/crawler_service.py` — 封装爬取逻辑（Source A/B 执行、任务状态管理、熔断集成）
- `services/merge_service.py` — 封装多源合并逻辑
- `services/export_service.py` — 封装所有导出操作

修改文件：
- `main.py` — 将业务逻辑迁移到服务层，保留 CLI 编排职责
- `api/server.py` — 使用服务层接口，减少直接依赖

#### 阶段二：抽象数据访问层（storage/ 目录）

新建文件：
- `storage/jsonl_store.py` — 统一 JSONL 读写接口
- `storage/progress_store.py` — 进度数据访问封装
- `storage/config_store.py` — 配置数据访问封装

修改文件：
- `pipelines/merge.py` — 使用 storage 层
- `pipelines/export.py` — 使用 storage 层
- `utils/progress.py` — 使用 storage 层

#### 阶段三：统一爬虫引擎接口

新建文件：
- `spiders/engine.py` — 抽象基类 SpiderEngine

修改文件：
- `spiders/static_list.py` — 继承 SpiderEngine
- `spiders/ajax_api.py` — 继承 SpiderEngine
- `spiders/yzw_api.py` — 继承 SpiderEngine
- `spiders/js_render.py` — 继承 SpiderEngine
- `spiders/pdf_list.py` — 继承 SpiderEngine

#### 阶段四：插件安全检查标准化

新建文件：
- `security/plugin_validator.py` — 统一 AST 解析与安全检查

修改文件：
- `config/plugins.py` — 使用 security 层

#### 阶段五：测试增强

新建测试文件：
- `tests/test_crawler_service.py`
- `tests/test_merge_service.py`
- `tests/test_plugin_security.py`

---

## 5. 验证计划

每个阶段完成后执行：
1. `pytest tests/` 全部通过
2. `tests/test_integration.py` 行为与重构前一致
3. 手动验证：`python main.py --school "东南大学" --source source_a --force`
4. 性能验证：并发 4 任务无文件竞争错误

---

## 6. 风险控制

1. **向后兼容**：保留原有 CLI 接口不变，内部实现逐步迁移
2. **渐进式重构**：每个阶段独立可测试，不一次性大规模重写
3. **数据安全**：确保原子写入机制（临时文件 + rename）不被破坏
4. **并发安全**：所有文件访问保持线程安全
