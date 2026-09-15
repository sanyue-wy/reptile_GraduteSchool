# 并行开发模块总览

> **核心前提**：所有模块开发前，接口规范已冻结在 [INTERFACE_SPEC.md](INTERFACE_SPEC.md)。各模块严格遵守接口契约，**开发过程零耦合、零阻塞**。

---

## 模块清单与依赖关系

```
                    ┌─────────────────────────────────┐
                    │      INTERFACE_SPEC.md           │
                    │   （接口规范基线，已冻结）         │
                    └──────────┬──────────────────────┘
                               │
          ┌────────────────────┼────────────────────────┐
          │                    │                         │
          ▼                    ▼                         ▼
┌─────────────────┐  ┌─────────────────┐   ┌─────────────────────┐
│  模块二          │  │  模块三          │   │  模块四              │
│  Parser 插件框架 │  │  配置去重与校验   │   │  前端 API 对接       │
│  IMPL_PARSERS    │  │  IMPL_CONFIG     │   │  IMPL_FRONTEND      │
│                 │  │                 │   │                     │
│  可立即开工 ✅   │  │  可立即开工 ✅    │   │  可立即开工 ✅       │
└────────┬────────┘  └────────┬────────┘   └─────────────────────┘
         │                    │
         ▼                    │
┌─────────────────┐           │
│  模块一          │           │
│  Source B 爬虫   │           │
│  IMPL_SOURCE_B   │           │
│                 │           │
│ 依赖模块二注册表 │           │
│ 依赖模块三配置   │◄──────────┘
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│  模块五                          │
│  测试体系与工程化                  │
│  IMPL_TESTING                    │
│                                  │
│  贯穿全部模块开发周期 ✅           │
└─────────────────────────────────┘
```

---

## 各模块概要

| # | 模块 | 文档 | 核心产出 | 可并行度 | 预估工作量 |
|---|------|------|----------|----------|-----------|
| 1 | **Source B 研招网爬虫** | [IMPL_SOURCE_B_YZW.md](IMPL_SOURCE_B_YZW.md) | `spiders/yzw_api.py`、`parsers/yzw_major.py` | 需模块二/三完成后集成 | 3-5 天 |
| 2 | **Parser 插件框架** | [IMPL_PARSERS.md](IMPL_PARSERS.md) | `parsers/__init__.py`（注册表）、`parsers/utils.py` | **立即开工**，无前置依赖 | 1-2 天 |
| 3 | **配置去重与校验** | [IMPL_CONFIG.md](IMPL_CONFIG.md) | `config/loader.py`、`config/validator.py`、`config/dedup.py` | **立即开工**，无前置依赖 | 2-3 天 |
| 4 | **前端 API 对接** | [IMPL_FRONTEND.md](IMPL_FRONTEND.md) | `dashboard/api.js`、5 个页面、公共组件 | **立即开工**，Mock 数据可独立开发 | 5-7 天 |
| 5 | **测试与工程化** | [IMPL_TESTING.md](IMPL_TESTING.md) | `tests/` 全套、日志规范、CI 配置 | **贯穿全程**，每个模块完成即补测试 | 持续 |

---

## 推荐并行开发计划

### 第一批（Day 1-3）：三个模块同时开工

| 负责人/工位 | 任务 | 产出 |
|-------------|------|------|
| **A 工位** | 模块二：Parser 插件框架 | `parsers/__init__.py`、`parsers/utils.py` |
| **B 工位** | 模块三：配置去重与校验 | `config/loader.py`、`config/validator.py`、`config/dedup.py`、`config/school_data.json` |
| **C 工位** | 模块四：前端 API 对接 | `dashboard/api.js`、`dashboard/style.css`、公共组件 |
| **D 工位** | 模块五：测试基础设施 | `tests/conftest.py`、`tests/fixtures/`、`pytest.ini` |

### 第二批（Day 3-5）：依赖模块 + 前端页面

| 负责人/工位 | 任务 | 依赖 |
|-------------|------|------|
| **A 工位** | 模块一：Source B 爬虫实现 | 模块二注册表就绪、模块三配置就绪 |
| **C 工位** | 前端 5 个页面实现 | `api.js` 已就绪，Mock 数据即可 |
| **B+D 工位** | 各模块单元测试补充 | 各模块核心代码就绪 |

### 第三天（Day 5-7）：集成与联调

| 任务 | 说明 |
|------|------|
| 端到端测试 | `test_integration.py` 跑通 Source A → 合并 → 导出全流程 |
| API 联调 | 前端切换真实 API，验证全部端点 |
| 配置全量校验 | `validate_all_configs()` 0 error |
| 东南大学试点 | 东南大学机械+自动化 Source A + Source B 全流程跑通 |

---

## 接口隔离红线（开发过程中严禁违反）

| 严禁操作 | 原因 | 替代方案 |
|----------|------|----------|
| `parsers/` import `spiders/` 或 `main.py` | 循环依赖 | 通过 `parse(raw_path, meta)` 接口解耦 |
| `spiders/` import `pipelines/` 或 `api/` | 循环依赖 | 通过 JSONL 文件解耦 |
| `dashboard/` 直接 import Python 模块 | 前后端未分离 | 通过 HTTP API（`/api/*`）通信 |
| `config/` 中硬编码学校数据 | 数据与逻辑未分离 | 使用 `school_data.json` + `loader.py` |
| 共享全局可变状态（如全局 dict） | 线程不安全 | 函数参数传递 + 文件系统通信 |
| `print()` 调试输出 | 日志不规范 | 统一使用 `logging.getLogger(__name__)` |

---

## 交付验收总清单

- [ ] [INTERFACE_SPEC.md](INTERFACE_SPEC.md) 所有接口签名在代码中完全实现
- [ ] 模块一：东南大学 Source B 端到端跑通
- [ ] 模块二：`parsers.dispatch()` 路由正确，新增 parser 零改动
- [ ] 模块三：147 校配置去重至 ~117 校，`validate_all_configs()` 0 error
- [ ] 模块四：5 个页面全部使用真实 API，无 Mock 硬编码
- [ ] 模块五：`pytest` 全绿，核心模块覆盖率 ≥80%
- [ ] 无循环 import（`grep` 验证）
- [ ] 无 `print()` 残留（`grep -r "print(" *.py` 验证）
