# 研究生导师信息采集系统 · 使用说明

## 项目定位

通用网络数据采集与处理平台，专为构建多源数据采集管道而设计。支持：

- **Spider 插件**：静态 HTML、Ajax API、JS 渲染、PDF 列表等多种采集方式
- **Processor 插件**：结构化解析、数据清洗、字段抽取
- **Storage 插件**：JSONL/Excel/SQLite 存储，支持幂等写入
- **Presenter 插件**：多格式呈现（HTML、PDF、Markdown 等）

---

## 快速开始（3 条命令）

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 Web 监控面板
python -m api.server --port 5000

# 3. 开始采集（或通过面板点击「开始采集」）
python main.py --school 东南大学 同济大学
```

访问 `http://127.0.0.1:5000/` 查看监控面板。

---

## 两套面板与正确启动方式

仓库里有两套页面，服务方式不同：

| 面板 | 入口 | 说明 |
|------|------|------|
| 主面板 | `/`（有采集记录时）或 `/index.html` | 统计卡片、进度条、学院状态、最近错误 |
| 管理台 | `/?view=console` 或 `/console/index.html` | 插件管理、任务定义、输出定义 |

> ⚠️ **必须由 Flask 托管**：`python -m api.server --port 5000`。
> 不要用 `python -m http.server` 直接开 `dashboard/` 目录——那样所有 `/api/*` 请求都会 404，
> 前端会静默回退到假数据，看起来"页面正常但数据永远不变"。

采集启动：

```bash
python main.py --school 东南大学 同济大学
python main.py --engine v3 --school 东南大学    # V3.0 插件管道
```

---

## 插件开发入口

想开发自定义插件？请参考：

**[docs/plugin_dev_guide/01_platform_overview.md](docs/plugin_dev_guide/01_platform_overview.md)**

快速指南：
- [01_platform_overview.md](docs/plugin_dev_guide/01_platform_overview.md) - 平台架构概览
- [03_first_spider.md](docs/plugin_dev_guide/03_first_spider.md) - 编写第一个 Spider 插件
- [05_writing_storage.md](docs/plugin_dev_guide/05_writing_storage.md) - 编写 Storage 插件
- [10_testing.md](docs/plugin_dev_guide/10_testing.md) - 插件测试规范

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           W3 架构总览                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│   │   Config     │    │    Pipeline    │    │   Storage    │                │
│   │   Layer      │───▶│   Engine       │───▶│   Layer      │                │
│   │              │    │                │    │              │                │
│   └──────────────┘    └──────────────┘    └──────────────┘                │
│         │                      │                     │                     │
│         ▼                      ▼                     ▼                     │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                │
│   │  Metadata    │    │   Plugins    │    │   Plugins    │                │
│   │  Registry    │    │  (Spider)    │    │  (Storage)   │                │
│   └──────────────┘    └──────────────┘    └──────────────┘                │
│                                                                             │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                          Web Dashboard                              │   │
│   │                                                                   │   │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │   │
│   │  │ Overview │  │ Schools  │  │ Tutors   │  │ Config   │         │   │
│   │  └──────────┘  └──────────┘  └──────────┘  └──────────┘         │   │
│   │                                                                   │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

插件管道：
┌─────────────────────────────────────────────────────────────────┐
│  Pipeline Stage   │  Input          │  Output       │  Plugin Type │
├───────────────────┼─────────────────┼───────────────┼──────────────┤
│  acquire          │ TaskConfigDTO   │ RawDataBatch  │ spider       │
│  process          │ RawDataBatch    │ RecordBatch   │ processor    │
│  store            │ RecordBatch     │ StoreReceipt  │ storage      │
│  present          │ RecordBatch     │ RenderedOutput│ presenter    │
└───────────────────┴─────────────────┴───────────────┴──────────────┘
```

---

## 命令行快速上手

```bash
# 启动 Web 监控面板
python -m api.server --port 5000

# 采集指定学校的导师信息
python main.py --school 东南大学 同济大学

# 采集全部已配置学校
python main.py --school __all__

# 只跑 Source A，强制重抓，4 线程
python main.py --school 东南大学 --source source_a --force --workers 4

# 重试所有失败项
python main.py --retry-failed
```

---

## 详细文档

| 文档 | 说明 |
|------|------|
| docs/V3.0/INTERFACES.md | V3.0 接口契约（DTO 定义、插件协议） |
| docs/plugin_dev_guide/ | 插件开发指南 |
| docs/V3.0/tasks/README.md | V3.0 多窗口开发指南 |
| config/school_data.json | 学校与学院配置 |

---

## 许可证

本项目遵循 MIT 许可证发布。详见 LICENSE 文件。

第三方借鉴项目许可证见 [NOTICE](NOTICE)。