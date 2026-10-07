# V3.0「闭环补全」批次 G5 验收报告（证伪窗口）

- 窗口代号：G5
- 日期：2026-10-01
- 分支：Refactoring_code
- 结论：**❌ 不通过**（阻断项见 §1）

> ⚠️ **执行受限声明（必读）**
> 本窗口在执行阶段遭遇工具侧限流（`Bash` 安全分类器持续返回
> `claude-opus-5[1M] is temporarily unavailable (rate-limited)`）。
> **两条 pytest 验收命令、以及职责 3 要求的安全实测，均未能实际跑完。**
> 限流期间只有短命令偶发放行，已抢到并作为硬证据写入本报告的有：
>
> | 命令 | 结果 |
> |---|---|
> | `git ls-files infra` | ✅ 成功（见 B-3） |
> | `git ls-files tools .github` | ✅ 成功，返回空（B-3） |
> | `git ls-files data/domain_kb.json plugins/__init__.py …` | ✅ 成功，返回空（B-3） |
> | `cat data/output/plugin_errors/stage_acquire_test_source_….json` | ✅ 成功（见 B-2） |
> | `git ls-files templates/` | ✅ 成功（见职责 4） |
> | `python -m pytest tests/browser/ -q` | ❌ **COULD NOT RUN** |
> | `python -m pytest tests/ -q --ignore=tests/integration` | ❌ **COULD NOT RUN** |
> | 启动 Flask 实测 `/api/outputs/serve` 穿越/令牌 | ❌ **COULD NOT RUN** |
>
> 因此本报告中：
> - 凡标注 **【已实测】** 的，附有真实命令输出；
> - 凡标注 **【静态判定】** 的，是逐行读代码得出的确定性结论，**未执行**，
>   需在限流解除后复跑确认；
> - **没有任何未跑过的命令被写成"已验证"。**

---

## 1. 阻断项

### B-1　`tests/browser/` 必红：前端静态抓取 `/templates/registry.json` 必然 404【静态判定】

`tests/browser/test_api_contract.py::test_non_api_static_fetches_are_served`
扫描 `dashboard/**` 里所有非 `/api/` 的静态抓取并断言 **status == 200**。

命中的唯一一处是 [dashboard/console/output-config.html:127](dashboard/console/output-config.html#L127)：

```js
fetch('/templates/registry.json', { credentials: 'same-origin' })
```

而 [api/server.py:1898-1910](api/server.py#L1898-L1910) 的 catch-all 路由：

```python
@app.route("/<path:filename>")
def dashboard_file(filename: str):
    if not filename.endswith((".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".ico")):
        abort(404)
    target = (_DASHBOARD_DIR / filename).resolve()
```

`.json` **不在**白名单内 → 直接 `abort(404)`；即便在白名单里，
`static_folder` 是 `dashboard/`，`dashboard/templates/registry.json` 也不存在。

结论：该用例**必然失败**。这不是测试写坏了，是**真实产品缺陷**——
输出配置页的模板下拉框恒为空（前端走 `r.ok ? r.json() : { templates: [] }` 静默回退）。

全仓 `dashboard/` 下非 `/api/` 的 fetch 仅此一处（已全量 grep `fetch\(` 核对）。

### B-2　插件错误中心的分组键与前端查找键永不相交【静态判定 + 真实数据】

后端 [api/server.py:1377](api/server.py#L1377) 按
`f"{plugin_type}:{plugin_name}"` 分组；前端
[dashboard/console/plugins.html:267](dashboard/console/plugins.html#L267) 按

```js
var key = (p.plugin_type || p.kind || '') + ':' + (p.name || p.id || '');
```

查找。两侧键空间：

| 来源 | 取值 | 例子 |
|---|---|---|
| 前端（插件卡片） | `list_plugins()` 只产出 `kind`，无 `plugin_type` | `processor:dedup`、`fetcher:static_html` |
| 后端（错误记录） | 全仓**唯一**写入方 [pipeline/engine.py:510-516](pipeline/engine.py#L510-L516) 写死 `plugin_type="pipeline"` | `pipeline:stage:acquire` |

真实落盘证据 `data/output/plugin_errors/stage_acquire_test_source_20260920_235000_000001.json`【已实测 cat】：

```json
{ "plugin_name": "stage:acquire:test_source", "plugin_type": "pipeline", ... }
```

即后端产出 `pipeline:stage:acquire:test_source`，前端只会去查 `fetcher:*` / `processor:*`。
**两侧永不相交** → 每个插件卡片的 `errorCount` 恒为 0，状态徽章恒为正常，
按钮恒显示「配置」而非「查看错误」，点开恒显示「暂无错误记录」。

**为什么 G2 的测试没抓到**：`tests/test_api_closed_loop_g2.py:59-71` 自己
**手写**了 `plugin_type: "processor"` 的合成记录，而真实写入方从不产出该值。
测试锁住了「字段名对齐」，没锁住「键空间对齐」。

严重度：Major。端点返回 200、单条记录字段正确，但功能整体不亮。

### B-3　干净克隆会直接塌：多个被 import 的模块尚未入库【已实测 git ls-files】

**实测输出（原样粘贴）**：

```
$ git ls-files infra
infra/cache.py
infra/context.py
infra/errors.py          ← 旧单文件模块，工作树里已被删除（D）
infra/http.py
infra/storage/__init__.py
infra/storage/atomic_io.py
infra/storage/idempotency.py
infra/storage/workspace.py

$ git ls-files tools .github
（空 —— 两者都未被跟踪）

$ git ls-files data/domain_kb.json plugins/__init__.py plugin_manager/error_reporter.py \
    plugin_manager/registry_snapshot.json plugins/plugin_manifest.py
（空 —— 五者都未被跟踪）
```

`infra/errors.py` 仍在索引里，而取代它的 `infra/errors/` 包不在；
`infra/retry/`、`infra/state_tracker.py` 同样不在。下表为影响面：

| 未跟踪路径 | 被谁 import | 缺失后果 |
|---|---|---|
| `infra/errors/`（`__init__.py` + `plugin_error.py`） | `pipeline/stages/{acquire,present,process,store}.py` **模块级** import | 四个 stage 全部 ImportError |
| `infra/retry/`（`__init__.py` + `adaptive_timeout.py`） | `infra/http.py:23` **模块级** import | infra.http 不可导入 |
| `infra/state_tracker.py` | `api/server.py:1580`（函数内，惰性） | 仅单端点降级 |
| `plugins/__init__.py`、`plugins/plugin_manifest.py` | 插件注册链路 | 插件发现异常 |
| `plugin_manager/error_reporter.py` | `api/server.py:1365`（函数内） | `/api/plugins/errors` 500 |
| `plugin_manager/registry_snapshot.json` | `list_plugins()` 优先数据源 | 插件列表降级 |
| `tools/` | CI `syntax` job 的 `compileall … tools …` | 该 job 直接失败 |
| `.github/` | **CI workflow 本身** | 干净克隆里根本没有 CI |

关键点：被删除的 `infra/errors.py`（git status 显示 `D`）正是被
`infra/errors/` 包取代的。**干净克隆若漏提交 `infra/errors/`，
整个 pipeline 包无法导入，测试大面积 error。**

这些路径均**未**被 `.gitignore` 命中（已通读 `.gitignore` 全部 42 行确认），
因此一次 `git add -A` 即可带上——但这是**条件**，不是现状。

---

## 2. 职责逐条核对

### 职责 1　浏览器未捕获异常与 404 门禁

- `python -m pytest tests/browser/ -q` — **COULD NOT RUN**（限流）。
- 门禁设计**经静态审阅确认有效**，不是摆设：
  - `test_frontend_api_calls_are_registered` 读的是 `app.url_map` 而非发请求，
    端点被删时必红（这正是防 B-1 类回归的关键，注释见
    [test_api_contract.py:7-11](tests/browser/test_api_contract.py#L7-L11)）；
  - 套件自带**免疫性测试**：`test_audit_detects_injected_js_error` 注入
    `undefinedFunction()` 断言 PageAudit 必须抓到；
    `test_audit_detects_same_origin_404` 断言必须抓到 404。
    监听器哪天失灵，会先红而不是静默放过。
- ❌ 但套件**当前是红的**（见 B-1）。G1 自己在
  [tests/browser/conftest.py:15-16](tests/browser/conftest.py#L15-L16)
  写明「现在仍在报的三条是 dashboard/tasks.html 与 dashboard/console/failures.html
  的真实前端缺陷」。加上 B-1，红色用例数 ≥ 3。

### 职责 2　全量回归不破

- `python -m pytest tests/ -q --ignore=tests/integration` — **COULD NOT RUN**（限流）。
- ⚠️ **口径提醒**：给定的 955 基线是在 `tests/browser/` 诞生**之前**测的
  （`tests/browser/` 目前仍是 untracked）。现在这条命令**会包含**浏览器套件，
  因此 955 这个数字与当前命令**不可直接比较**。
- CI（`.github/workflows/ci.yml`）跑的是
  `--ignore=tests/integration --ignore=tests/browser`，
  即**刻意排除**浏览器套件。这个设计是自洽的（G3 在 workflow 注释里写明
  「装上了包但没浏览器、结果全部静默跳过」的假绿风险）。

### 职责 3　G2 的端点真修好了吗

**逐字段比对结果（静态，比对两侧真实代码）**：

`GET /api/plugins/errors`
- 前端 [plugins.html:248](dashboard/console/plugins.html#L248) 读 `data.errors || data || {}`
  → 后端把 `errors` 放**顶层**（[server.py:1384](api/server.py#L1384)），✅ 对齐。
- 前端读 `e.created_at||e.timestamp`、`e.code`、`e.message||e.error`、`e.suggestion||e.advice`
  → `_normalize_plugin_error`（[server.py:1324-1349](api/server.py#L1324-L1349)）
  全部产出，✅ 字段级对齐。
- ❌ 但**分组键不相交**（B-2）。

`GET /api/outputs/serve`
- 调用方 [preview.html:86](dashboard/runtime/preview.html#L86) 传 `output.path`；
  后端 [server.py:1777-1798](api/server.py#L1777-L1798) 产出的 `path` 是
  **项目根相对路径**，与 `_resolve_preview_target` 的解析口径
  （`Path.cwd()/candidate`）自洽，✅ 闭环成立。
- preview.html 还读 `output_id / output_format / created_at / metadata.size_bytes`
  → 后端全部产出，✅。
- `metadata.record_count` 后端不产出 → 预览页该行显示 `—`，**仅观感问题，非功能缺陷**。

**安全项（路径穿越 / 令牌）—— 代码审阅结论**：
[server.py:1751-1767](api/server.py#L1751-L1767) 先 `Path(raw).resolve()`
再 `relative_to(_RUNS_DIR.resolve())`，越界即 `(None, "")`；
随后要求 `len(parts) >= 3 且 parts[1] == "outputs"`，挡住 `runs/<id>/store/`；
`resolve()` 天然吃掉 `../` 与符号链接。令牌侧 HMAC-SHA256 + `compare_digest`
+ run 绑定 + TTL，四项齐全。
`tests/test_api_closed_loop_g2.py` 已覆盖穿越/伪造/过期/跨 run/符号链接/类型白名单。

> ❌ **但我没有实测**。G5 职责 3 明确要求「必须实测，不接受代码看起来对」。
> 受限流所阻，**该项未完成**。

### 职责 4　CI 在干净克隆上真能跑

- workflow 本身在 `.github/` 下，**untracked** → 不提交就没有 CI。
- 三个 job 的文件前置条件：

| job | 前置 | 状态 |
|---|---|---|
| `test` | `requirements.txt` / `requirements-dev.txt` | 已入库 ✅ |
| `syntax` | `compileall api infra pipeline plugin_manager plugins contracts converters scaffolds tests tools main.py` | **`tools/` untracked** —— 干净克隆下该目录不存在，`compileall` 对不存在路径报 `Can't list` 并非零退出 → **job 失败** |
| `docs` | `mkdocs build --strict` | nav 指向的 `docs/plugin_dev_guide/01..10.md` 与 `docs/api/{contracts,plugins_base,pipeline,plugin_manager}.md` **全部存在** ✅（已 Glob 确认）；`mkdocs.yml` 的 `exclude_docs` 已排除 V3.0/ 等目录，G4 改的 acceptance.md 不参与构建 ✅ |

补充实测：`$ git ls-files templates/registry.json` → `templates/registry.json`
（**已入库**）。即 B-1 的修复只差一个路由/白名单，文件本身不缺。

- **`.gitignore` 卫生有遗漏**：第 15 行 `*preview.png` **未锚定**，
  命中 `templates/*/preview.png` → 20 张模板预览图**永不入库**。
  G3 把 `/*.png` 锚定到了根目录（并写进注释说明理由），却漏了 `*preview.png`。
  影响：`docs/V3.0/acceptance.md:103` 的证据「20 个模板目录均存在且各含
  4 个文件（含 preview.png）」在干净克隆上不成立；
  `templates/registry.json` 每条目都指向 `templates/<name>/preview.png`，指向空。
  未发现任何**测试**依赖 preview.png（`tests/test_presentation_plugins.py:250`
  是在 tmp 里自造），故**不阻断 CI**，但文档证据链在克隆后失效。

- `data/domain_kb.json` untracked（未被 ignore）。三个插件声明
  `depends_on: ["domain_kb"]`。查证：`validate_domain_kb()` 在
  `plugin_manager/validator.py` 内**无任何调用方**（全仓 grep 仅有定义与 `__all__`），
  因此**干净克隆缺该文件不会导致插件加载失败**，只是
  `load_domain_kb()` 告警并返回空映射 → `domain_rewriter`/`url_normalizer`
  静默退化为空操作。**不阻断 CI，但会让 IDN 域名修复在 GitHub 上失效**。

### 职责 5　G4 的文档现在说真话了吗

抽查 5 项 acceptance 阻断声明 + 3 项非阻断，**逐条回代码核对**：

| # | G4 声称 | 核对结果 |
|---|---|---|
| B1 | 4 个中间基类存在；`plugin_type` 齐全 | ✅ **准确**。`plugins/base.py:205/215/225/235` 行号完全一致，三属性齐全。G4 **主动自曝**的两处遗留亦属实：`base.py:210` 为 `plugin_type="parser"`，而 `loader.PLUGIN_TYPES = ("spider","processor","storage","presenter","ui")` 确无 `"parser"`，`validator.PLUGIN_BASE_CLASSES` 亦无该键 |
| B2 | PresenterPlugin 已对齐 | ✅ **准确**。`base.py:148-150` 确为 `presenter` / `PresentationRequest.v1` / `RenderedOutputDTO.v1` |
| B3 | RawDataDTO assets 已入 required | ✅ **准确**。`contracts/raw.py:74` required 数组确含 `assets` |
| B4 | markdown 回退链「代码已修复，配置未接线」 | ✅ **准确，且 G4 还说轻了**。`present.py:30-32` 确有 `_FORMAT_FALLBACK`；`config/plugins.yaml` 确只有 5 个 presenter 实例、无 `markdown_presenter`；`pipeline.yaml` present 段只引用 `html_report`。补充：`present.py:36` 还有第三层 `_GENERIC_FALLBACK = "text_presenter"`，但 `engine.py:409-421` 的 `presenter_map` 是用**配置实例名**（`html_report`）做键的，`text_presenter` 永远不在其中 → **第三层同样是死代码** |
| B5 | PDF XSS 已修 | ✅ **准确**。`pdf_presenter/plugin.py:246` 确为 `html_mod.escape(value, quote=True)` |
| N1 | 全部 32 个 metadata.json 含 license | ✅ **准确**。实测 Glob 得 32 个文件，Grep `"license"` 亦命中 32 个 |
| N2 | 越权清单已登记 | ✅ commit `2e0aec8` 存在 |
| N3 | LICENSE/NOTICE 存在 | ✅ 两文件均在磁盘，且不在 untracked 列表 → 已入库 |

**未发现「文档说已修复而代码里没有」的情况。G4 的自曝（B1 遗留、B4 未接线）
反而是加分项——它没有把未闭环的项粉饰成闭环。**

⚠️ 但发现一处**反向**的文档失真（属冻结契约，**仅报告不修改**）：
`docs/V3.0/INTERFACES.md:599`（§12.4）称
「若插件声明 `depends_on: ["domain_kb"]`，加载时校验 `data/domain_kb.json` 存在且 schema 合法」——
该校验**代码里根本没有任何调用方**，契约承诺的能力未接线。

---

## 3. 复跑指引（限流解除后按序执行）

```bash
# 1) 浏览器套件（预期红：B-1 的 test_non_api_static_fetches_are_served + G1 自曝的 3 条）
python -m pytest tests/browser/ -q

# 2) CI 口径（预期绿）
python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser

# 3) 验收命令（预期红，含浏览器套件）
python -m pytest tests/ -q --ignore=tests/integration

# 4) 证伪测试：套件是否真有牙
#    不改仓库文件，用 -p 插件在运行时把规则从 url_map 摘掉：
#    /tmp/falsify.py 内定义 autouse fixture，执行
#      [r for r in app.url_map.iter_rules() if r.rule == "/api/plugins/errors"]
#      → app.url_map._rules 移除
#    然后 python -m pytest tests/browser/test_api_contract.py -q -p falsify
#    预期：test_known_missing_endpoint_is_registered[...plugins/errors] 转红
#    （本窗口未执行）

# 5) 干净克隆演练
git clone <本地路径> /tmp/clean && cd /tmp/clean && \
  python -m compileall -q api infra pipeline plugin_manager plugins contracts converters scaffolds tests tools main.py
```

## 4. 给下一窗口的结论

**不要推 GitHub**，直到满足：

1. **B-2 修掉**：让后端分组键与前端查找键落在同一空间
   （建议后端按前端口径产出 `<kind>:<name>`，或前端改读 `plugin_name`）。
   修完请补一条**用真实写入方产出的记录**（`plugin_type="pipeline"`）的用例，
   否则同类问题会再次被合成数据掩盖。
2. **B-1 决策**：`/templates/registry.json` 要么加路由/放宽扩展名白名单，
   要么前端改成走已存在的 API。修完 `tests/browser/` 应转绿。
3. **B-3 核对**：`git add -A` 前逐条确认上表 6 项已入库；
   其中 `infra/errors/`、`infra/retry/` 漏任意一个，干净克隆直接塌。
4. `.gitignore` 第 15 行 `*preview.png` 改为锚定形式（如 `/*preview.png` 或
   `!/templates/**/preview.png`），否则 20 张模板预览图永远推不上去。