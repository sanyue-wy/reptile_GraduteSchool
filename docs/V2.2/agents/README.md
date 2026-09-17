# V2.2 重构 — 并行 Agent 指导书总览

> 版本：2026-09-17  
> 基于：《工程架构分析与优化方案》《工程重构优化计划（2026-09-17 完善版）》

## 并行波次

| 波次 | 参与 Agent | 内容 |
|---|---|---|
| Wave 0 | Agent G | 冻结接口契约、创建分支、建立验收脚本 |
| Wave 1 | Agent A / B / C / D / E / F | 按文件所有权并行开发 |
| Wave 2 | Agent G | 按顺序合并、解决冲突、跑全量回归 |
| Wave 3 | 各 Agent + G | 修复集成问题，完成最终验收 |

## 文件所有权矩阵

| Agent | 可写文件/目录 | 禁止修改 |
|---|---|---|
| A | `main.py`、`api/server.py`、`services/**` | 其他 Agent 文件 |
| B | `storage/**`、`pipelines/merge.py`、`pipelines/export.py`、`utils/progress.py` | `main.py`、`api/server.py`、`spiders/**`、`config/plugins.py` |
| C | `spiders/engine.py`、`spiders/static_list.py`、`spiders/ajax_api.py`、`spiders/yzw_api.py`、`spiders/detail_parser.py`、`spiders/js_render.py`、`spiders/pdf_list.py` | `main.py`、`api/server.py`、`utils/**` |
| D | `security/**`、`config/plugins.py` | `main.py`、`api/server.py`、`spiders/**` |
| E | `utils/http.py`、`utils/cache.py` | `main.py`、`utils/progress.py`、`services/**` |
| F | `tests/**` | 生产代码 |
| G | 集成阶段可临时修改所有文件 | 开发阶段不直接写业务代码 |

## 推荐合并顺序

1. **Agent C** — `spiders/engine.py` + spiders，兼容旧函数
2. **Agent D** — `security/` + `config/plugins.py`，独立
3. **Agent E** — `utils/http.py`、`utils/cache.py`，独立底层
4. **Agent B** — `storage/` + pipelines + progress，保持旧接口
5. **Agent A** — `services/` + `main.py` + `api/server.py`，调用前四者
6. **Agent F** — 测试增强，切换真实实现
7. **Agent G** — 总集成与验收

## 硬性规则

1. 一个文件同一时间只有一个 Agent 可写
2. 旧接口必须兼容：CLI 参数、旧函数名、旧配置格式、旧 JSONL 结构不得破坏
3. 原子写入不得破坏：保留 `tempfile.mkstemp` + `os.replace` 模式
4. 线程安全不得删除：保留 `ProgressTracker`、`CrawlCache` 中的 `threading.Lock`
5. 共享接口变更必须登记到 `docs/refactor/interfaces.md`
6. 测试使用临时目录，不污染 `data/` 真实数据
7. 集成前不删除旧实现：新服务层/存储层/引擎层可先并行存在

## 各 Agent 指导书

| 文件 | Agent | 职责 |
|---|---|---|
| [agent-a-service.md](agent-a-service.md) | Agent A | 服务层与接口层重构 |
| [agent-b-storage.md](agent-b-storage.md) | Agent B | 存储抽象层 |
| [agent-c-spider.md](agent-c-spider.md) | Agent C | 统一爬虫引擎接口 |
| [agent-d-security.md](agent-d-security.md) | Agent D | 插件安全检查标准化 |
| [agent-e-http.md](agent-e-http.md) | Agent E | HTTP 熔断/冷却与缓存优化 |
| [agent-f-tests.md](agent-f-tests.md) | Agent F | 测试增强与回归守护 |
| [agent-g-integrate.md](agent-g-integrate.md) | Agent G | 集成、合并与最终验收 |
