# 插件化配置系统 · 计划书（含开源工程借鉴）

> 目标：在「配置管理」中新增**插件配置**，让全部 7 个环节均可插拔、可在线启用、可自由扩展。
> 原则：**最小侵入** —— 复用已有注册表模式，照搬成熟框架的配置约定，不改现有采集主流程。
> 决定：UI 完整展示 7 类；开放用户自定义插件开发。

---

## 一、开源工程调研结论（可直接借鉴的做法）

### 1. Scrapy（★最相关：Python 爬虫 + 配置驱动组件）

Scrapy 的组件分类几乎就是你想要的答案，它给出的标准配置格式：

| Scrapy 组件 | 职责 | 映射到你的项目 |
|-------------|------|---------------|
| Spider | 定义抓什么、怎么解析入口 | `spiders/*` + `school_data.json` |
| Downloader Middleware | 请求/响应前后横切钩子 | `utils/http.py`、`utils/cache.py` → utility |
| Item Pipeline | 拿到 item 后的**有序处理链** | `pipelines/merge.py`、`config/dedup.py` → processor |
| Feed Export / Exporters | 结果导出为 json/csv/xml… | `pipelines/export.py` → exporter |
| Extensions | 不进入数据流的旁挂能力（信号监听） | 日志/进度/通知 → utility |

**Scrapy 里要抄的两个关键机制：**

- **带权重的有序字典**：`ITEM_PIPELINES = {"a.Validate": 300, "b.Store": 800}` —— 数字即执行顺序。比裸 list 更好插入中间件。
- **BASE + 覆盖置 None 禁用**：`DOWNLOADER_MIDDLEWARES_BASE`（内置默认）与用户设置合并；`{"pkg.X": None}` 表示关掉某个内置组件而不删默认。→ 直接采用 **代码内置真值 + 用户 json 覆盖** 的双层结构。

### 2. pyload（下载管理器，插件种类划分的教科书）

`plugins/base/` 下的基类即全部合法类别：`downloader / decrypter / container / adder / extractor / captcha / notifier / account / hoster`。

**借鉴点**：它明确区分 *container*（一个链接展开成多个任务 ≈ 你的 URL 发现 `url_resolver`）、*decrypter*（拿到加密原文再解 ≈ fetch+parse）。印证 **fetch 与 parse 应作两类**，且需要「URL 发现/任务展开」这一横切能力。

### 3. Apache NiFi（数据流编排）

核心模式：**Processor（有输入输出的处理单元）+ Controller Service（被多个 processor 共享的横切服务：DB 连接池、SSL、记录读写器）**。

**借鉴点**：把「限速会话、缓存、代理」这类被多处复用的东西建成独立的 **controller-service 型插件**（utility 类），而不是塞进每个 fetcher 里重复配置。

### 4. pluggy（pytest 插件内核，★1691）

纯 Python 的 hook 注册/调用库，提供 `hookspec`(声明接口) + `hookimpl`(实现) + 自动发现。

**借鉴点/取舍**：你已经手搓了一个精简版（`parsers/__init__.py`）。**不引入 pluggy 依赖**（违背最小侵入），但应学它的纪律：用一个 **hookspec 风格的显式接口约定文档**，固定每类插件必须实现的函数签名，避免接口漂移。

---

## 二、插件类别设计（7 类，UI 完整展示）

| # | kind | 中文名 | 职责 | 现状代码 | 对标框架 | 基类接口 |
|---|------|--------|------|---------|---------|---------|
| 1 | `source` | 数据源 | 组合声明：某校某院用哪套 fetcher+parser | `school_data.json` | Scrapy Spider | `describe() → dict` |
| 2 | `fetcher` | 数据获取 | 抓原始 HTML/JSON/PDF | `spiders.ENGINE_REGISTRY` | Scrapy Downloader | `fetch(session, url, opts) → str/bytes` |
| 3 | `parser` | 数据解析 | 原文→统一 Schema | `parsers._REGISTRY` | pyload Decrypter | `parse(raw_path, meta) → list[dict]` |
| 4 | `processor` | 数据处理 | 清洗/归一/合并/去重（有序链） | `merge.py`,`dedup.py` | Scrapy Item Pipeline | `process(records, ctx) → list[dict]` |
| 5 | `exporter` | 数据导出 | 结果→xlsx/jsonl/DB/… | `pipelines/export.py` | Scrapy Feed Export | `export(records, output_dir) → dict` |
| 6 | `presenter` | 数据呈现 | 前端页面/图表/视图 | `dashboard/*.html` | — | `render(ctx) → html_fragment` |
| 7 | `utility` | 辅助能力 | 限速/UA/缓存/代理/通知/调度 | `utils/*`,`config/global.json` | NiFi Controller Service / Scrapy Middleware | `setup(config) → None` |

### 每类插件的显式接口约定（hookspec 风格）

每类插件**必须实现**以下函数，违反时 loader 拒绝注册并报错：

```python
# 所有插件共同的元信息
def metadata() -> dict:
    """返回 {"name": str, "kind": str, "version": str, "author": str, "description": str}"""
    ...

# 各类特有接口（上面基类接口列所示）
def fetch(session, url: str, opts: dict) -> str | bytes: ...
def parse(raw_path: str, meta: dict) -> list[dict]: ...
def process(records: list[dict], ctx: dict) -> list[dict]: ...
def export(records: list[dict], output_dir: Path) -> dict: ...
def render(ctx: dict) -> str: ...  # 返回 HTML 片段
def setup(config: dict) -> None: ...
```

---

## 三、实现方案（四阶段，每阶段独立可交付）

### 阶段 A｜零风险：已有注册表 → 「插件配置」只读页

不加任何运行逻辑，只把现成两张注册表读出来展示。

- **数据文件** `config/plugins.json`（只存用户对内置插件的开关/元数据覆盖，遵循 Scrapy「BASE 在代码、覆盖在配置」双层结构）：
  ```json
  {
    "overrides": {
      "fetcher:js_render": {"enabled": false},
      "parser:yzw_major":  {"enabled": true}
    },
    "pipeline": {
      "processors": {"normalize": 100, "dedup": 200, "merge": 300},
      "exporters":  {"xlsx": 100, "jsonl": 200}
    }
  }
  ```
  > 内置清单由后端从 `ENGINE_REGISTRY` 与 `list_registered()` 自动生成，标 `builtin:true`，`overrides` 只做增删开关，彻底避免漂移。
- **后端**：`api/server.py` 加 `GET /api/plugins`，返回 builtin ∪ overrides 合并清单。
- **前端**：`dashboard/config.html` 加第 4 个 tab「🔌 插件配置」，按 kind 分 7 组只读列表。
- **触及文件**：+`config/plugins.json`、server(+1 端点)、config.html(+1 tab)。**不动 main.py / pipelines / spiders / parsers。**

### 阶段 B｜小侵入：processor/exporter 注册表 + 有序链 + 启停

把 `main.py` 里硬编码的 merge→export 改成查表分派。**默认链 = 现有顺序，行为不变。**

- 复制 `parsers/__init__.py`（40 行 register/dispatch）两遍：
  - `processors/__init__.py`：`@register(name)` + `process(records, ctx)`；把 `merge_sources`、`dedup`、`major_mapping` 包成插件。
  - `exporters/__init__.py`：`@register(name)`；把 xlsx/jsonl 拆成两个 exporter。
- 读取 `plugins.json.pipeline.processors` 的 `{name: weight}`，按 weight 升序依次 dispatch（Scrapy Item Pipeline 语义）。
- 新增 `PUT /api/plugins/{kind}:{id}`（切 enabled）、`PUT /api/plugins/pipeline`（调权重顺序）。
- **校验联动**：`validator.py` 里 `VALID_LIST_TYPES`、`notice.template` 改为向注册表查询，新增插件自动被体检接受，不再写死常量。
- **触及文件**：+`processors/`、+`exporters/`、`main.py`、`validator.py`、server(+2 端点)。

### 阶段 C｜核心扩展：用户自定义插件开发与加载

这是你要求的「允许用户自由开发」的核心阶段。

#### C.1 插件目录约定

```
plugins_ext/
  fetcher/
    my_custom_fetcher.py       # 用户自写
  parser/
    school_notice_parser.py
  processor/
    field_mapper.py
  exporter/
    csv_exporter.py
  presenter/
    chart_view.py
  utility/
    proxy_rotator.py
```

#### C.2 插件文件规范（hookspec 风格）

每个插件文件**必须**：

```python
# plugins_ext/processor/field_mapper.py

# ① 声明元信息（必填，loader 校验后才允许注册）
PLUGIN_META = {
    "name": "field_mapper",
    "kind": "processor",          # 必须与所在目录名一致
    "version": "1.0.0",
    "author": "用户名",
    "description": "按规则映射字段名",
    "config_schema": {            # 可选：声明此插件接受的配置项（JSON Schema 子集）
        "mapping": {"type": "object", "description": "原始字段→目标字段映射表"}
    }
}

# ② 实现该 kind 的标准接口
def process(records: list[dict], ctx: dict) -> list[dict]:
    """
    ctx 中包含:
      - plugin_config: dict  ← 用户在 plugins.json 里为此插件填写的配置
      - university: str
      - college: str
      - ...
    """
    mapping = ctx.get("plugin_config", {}).get("mapping", {})
    for r in records:
        for old_key, new_key in mapping.items():
            if old_key in r:
                r[new_key] = r.pop(old_key)
    return records
```

#### C.3 加载机制

`config/loader.py` 增加 `load_plugins()` 函数：

```python
import importlib, inspect, pkgutil
from pathlib import Path

EXT_DIR = Path("plugins_ext")

def _discover_external_plugins() -> dict[str, dict]:
    """
    扫描 plugins_ext/<kind>/*.py，导入并校验 PLUGIN_META，
    合法的注册到对应 kind 的注册表（builtin=False）。

    校验规则：
      1. PLUGIN_META 必填字段齐全且 kind 与目录名一致
      2. 必须实现该 kind 的标准接口函数（参见 §2 接口约定）
      3. 无恶意 import（白名单限制 sys/os/subprocess 等）
    """
    discovered = {}
    for kind_dir in sorted(EXT_DIR.iterdir()):
        if not kind_dir.is_dir(): continue
        kind = kind_dir.name
        for py_file in kind_dir.glob("*.mod_py") or kind_dir.glob("*.py"):
            spec = importlib.util.spec_from_file_location(
                f"plugins_ext.{kind}.{py_file.stem}", py_file
            )
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)
            except Exception as e:
                logger.warning("插件 %s 加载失败: %s", py_file, e)
                continue

            meta = getattr(mod, "PLUGIN_META", None)
            if not meta:
                logger.warning("%s 缺少 PLUGIN_META，跳过", py_file)
                continue

            # 校验必填字段和接口
            _validate_plugin(meta, kind, mod)
            discovered[f"{kind}:{meta['name']}"] = {
                "module": mod, "meta": meta,
                "builtin": False, "kind": kind,
            }
    return discovered
```

#### C.4 安全约束（白名单沙箱）

用户插件可自由 import，但 loader 层做**静态黑名单检测**（不重，轻量够用）：

```python
BLOCKED_MODULES = {"os", "subprocess", "shutil", "socket", "ctypes"}

def _check_import_safety(mod) -> list[str]:
    """检查模块源码中是否有危险 import（防意外误用，非恶意防护）。"""
    src = Path(mod.__file__).read_text(encoding="utf-8")
    warnings = []
    for blocked in BLOCKED_MODULES:
        if f"import {blocked}" in src or f"from {blocked}" in src:
            warnings.append(f"插件引入了受限模块 {blocked}")
    return warnings
```

> 这是轻量防护，不挡恶意代码，但能防止用户无意中写 `import os; os.system(...)` 之类。

#### C.5 前端：插件开发面板

在「🔌 插件配置」tab 里增加**「安装自定义插件」**区块：

- **上传入口**：拖拽 `.py` 文件到页面 → 调用 `POST /api/plugins/upload`（kind 由目录名推断，或让用户选）。
- **校验反馈**：后端即时校验 PLUGIN_META + 接口 + 安全，返回通过/失败详情。
- **配置表单**：如果插件声明了 `config_schema`，自动生成对应配置表单（学 Scrapy settings 的 key→default 逻辑）。
- **热加载**：上传成功后自动触发一次 `_discover_external_plugins()`，无需重启。

#### C.6 API 端点汇总

| 端点 | 方法 | 职责 |
|------|------|------|
| `/api/plugins` | GET | 全量插件清单（builtin + external + overrides 合并） |
| `/api/plugins/upload` | POST | 上传自定义 .py 插件文件 |
| `/api/plugins/{kind}:{id}` | PUT | 切 enabled / 更新 plugin_config |
| `/api/plugins/{kind}:{id}` | DELETE | 卸载自定义插件（删除 .py 文件 + 清 overrides） |
| `/api/plugins/{kind}:{id}/reload` | POST | 手动热重载某个插件 |
| `/api/plugins/pipeline` | PUT | 调整 processor/exporter 有序链权重 |

---

### 阶段 D｜可选深化：presenter 插件化 + 信号系统

- presenter 注册表：每个 dashboard 视图登记为插件（id、路由、菜单项、可见性），配置页控制左侧导航显示哪些页。
- 信号系统（学 Scrapy signals）：定义 `on_crawl_start` / `on_item_parsed` / `on_export_done` 等信号点，utility 插件可挂载回调（通知类插件从此处触发）。此阶段按需推进。

---

## 四、护栏（保证「最小侵入」成立）

1. **单一真值**：能力集合以代码注册表为准；`plugins.json` 只存开关与顺序，不枚举能力（学 Scrapy BASE/覆盖）。
2. **默认不变**：未配置时 dispatch 回退到当前硬编码路径，行为恒等于现状。
3. **有序链用权重**：采用 `{name: weight}` 字典（学 Scrapy），便于往中间插入而不打乱既有顺序。
4. **校验自动扩展**：合法取值来自注册表动态查询，新插件零改动即被接受。
5. **原子写入**：所有 json 保存复用现有 tempfile+os.replace。
6. **热加载不重启**：阶段 C 的 `_discover_external_plugins()` 可被 API 触发，无需重启整个服务。

---

## 五、落地顺序与工作量

| 阶段 | 交付物 | 风险 | 预估 |
|------|--------|------|------|
| A | 插件配置只读页（7 类分组展示） | 极低 | 0.5–1 天 |
| B | processor/exporter 注册表 + 有序链 + 启停 + 校验联动 | 低（默认链=现状） | 1–2 天 |
| C | 用户自定义插件开发/上传/热加载/沙箱 | 中 | 2–3 天 |
| D | presenter 插件化 + 信号系统 | 中低 | 1–2 天 |

**总计**：全做完约 5–8 天。A 单独可交付验证，B+C 是核心价值，D 按需。
