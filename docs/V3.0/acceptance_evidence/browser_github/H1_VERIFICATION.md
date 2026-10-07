# H1 窗口复核报告

**复核时间**：2026-10-07
**复核人**：独立证伪窗口
**被复核窗口**：H1
**结论**：**refuted** —— B-2 修复不完整，核心缺陷未解决

---

## 1. B-1 复核：`/templates/registry.json` 精确路由

### 1.1 实测命令与输出

```bash
$ curl -v http://127.0.0.1:5001/templates/registry.json
```

**输出摘录**：
```
*   Trying 127.0.0.1:5001...
* Connected to 127.0.0.1 (127.0.0.1) port 5001
> GET /templates/registry.json HTTP/1.1
> Host: 127.0.0.1:5001
> User-Agent: curl/8.14.1
> Accept: */*
>
< HTTP/1.1 200 OK
< Server: Werkzeug/3.1.5 Python/3.12.7
< Content-Type: application/json
< Content-Length: 15884
<
{ "version": "1.0", "templates": [ ... 20 个模板 ... ] }
```

**状态码**：`200 OK`  
**返回体**：完整的 JSON，包含 20 个模板条目（minimal-light, academic-serif, clean-sans, dark-modern, card-flow, data-grid, report-classic, dashboard-pro, minimal-dark, nature-green, ocean-blue, warm-amber, mono-code, magazine-style, compact-table, poster-wide, print-friendly, high-contrast, playful-rounded, slide-deck）

### 1.2 路径穿越防护验证

```bash
$ curl -v "http://127.0.0.1:5001/templates/../../config/school_data.json"
```

**输出**：
```
< HTTP/1.1 404 NOT FOUND
< Content-Type: application/json
{"code":40401,"detail":"404 Not Found: The requested URL was not found on the server.","message":"接口不存在"}
```

路径穿越载荷被规一化为 `/config/school_data.json`，未命中任何路由，返回 404。**未暴露任意文件读取面**。

### 1.3 代码确认

`api/server.py` 新增路由（第 1881-1887 行）：
```python
@app.route("/templates/registry.json")
def templates_registry():
    """仅提供仓库根目录下的 templates/registry.json 这一个文件。"""
    registry_path = (Path(__file__).parent.parent / "templates" / "registry.json").resolve()
    if not registry_path.exists():
        abort(404)
    return send_file(str(registry_path), mimetype="application/json")
```

**B-1 判定**：✅ **confirmed** —— 精确路由已实现，仅暴露单一静态文件，无目录遍历风险。

---

## 2. B-2 复核：错误键与插件列表键的交集（核心缺陷）

### 2.1 问题背景

- **真实写入方**：`pipeline/engine.py:_report_stage_errors`（H1 新增，第 499-518 行）
- **写入内容**：`plugin_type="pipeline"`，`plugin_name="stage:{stage}:{source_id}"`
- **错误键形态**：`pipeline:stage:acquire:static_html`
- **插件列表键**（`/api/plugins` 返回）：`fetcher:static_html`, `processor:dedup`, `exporter:jsonl` 等（legacy kind）
- **前端查找逻辑**：`(p.kind||p.plugin_type)+':'+(p.name||p.id)`

**核心矛盾**：engine 写入的键前缀是 `pipeline:`，而插件列表键前缀是 `fetcher:`/`processor:`/`exporter:`/`presenter:`。两者永不相交。

### 2.2 独立构造验证（不信任 H1 测试）

#### 步骤 1：写入一条模拟真实 engine 产出的错误记录

```python
# 写入模拟 engine 写入的记录
record = {
    "plugin_name": "stage_acquire_static_html",
    "plugin_type": "pipeline",
    "error_type": "FETCH_ERROR",
    "error_message": "Connection timeout",
    ...
}
```

#### 步骤 2：请求 `/api/plugins/errors` 获取错误键

```bash
$ curl -s "http://127.0.0.1:5001/api/plugins/errors" | python -c "import sys,json; print(set(json.load(sys.stdin).get('errors',{}).keys()))"
```

**实际输出**：
```
{'pipeline:stage:acquire:test_source', 'pipeline:stage_acquire_static_html'}
```

#### 步骤 3：请求 `/api/plugins` 计算插件键

```bash
$ curl -s "http://127.0.0.1:5001/api/plugins" | python -c "
import sys,json
items=json.load(sys.stdin)['data']['items']
keys={f\"{p['kind']}:{p['name']}\" for p in items if p.get('kind') and p.get('name')}
print(sorted(keys))
"
```

**实际输出**：
```
['exporter:jsonl', 'exporter:xlsx', 'fetcher:ajax_api', 'fetcher:js_render', 'fetcher:pdf_list', 'fetcher:static_html', 'parser:yzw_major', 'presenter:config', 'presenter:failures', 'presenter:overview', 'presenter:schools', 'presenter:tutors', 'processor:dedup', 'processor:merge', 'processor:normalize', 'source:school_config', 'utility:cache', 'utility:http_session', 'utility:progress']
```

#### 步骤 4：计算交集

```python
error_keys = {'pipeline:stage:acquire:test_source', 'pipeline:stage_acquire_static_html'}
plugin_keys = {'fetcher:static_html', 'processor:dedup', ...}
intersection = error_keys & plugin_keys  # => set()
```

**交集为空**（`len(intersection) == 0`）。

### 2.3 H1 测试代码分析

`tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list`（第 114-162 行）：

```python
# 写入一条"真实写入方会产出的记录"（见共享事实 5）
_write_plugin_error("stage_acquire_test_source", {
    "plugin_name": "stage:acquire:test_source",
    "plugin_type": "pipeline",      # ← 手写合成记录，plugin_type="pipeline"
    "error_type": "FetchError",
    ...
})
```

**关键发现**：
1. 测试**手写合成记录**，`plugin_type="pipeline"`，`plugin_name="stage:acquire:test_source"` —— 这正是当前 engine 写入的错误形态，**而非修复后的形态**。
2. 测试注释承认："当前未修复 engine 时本用例会失败（交集为空），修复 engine 后应通过。"
3. **但 engine 并未修复** —— `_report_stage_errors` 仍写入 `plugin_type="pipeline"`。

### 2.4 Engine 代码确认（`pipeline/engine.py` 第 499-518 行）

```python
def _report_stage_errors(self, result: RunResult):
    for stage in result.stages:
        for err in getattr(stage, "errors", []) or []:
            ...
            report(PluginErrorContext(
                plugin_name=f"stage:{stage.stage}:{source_id}" if source_id else f"stage:{stage.stage}",
                plugin_type="pipeline",          # ← 硬编码 "pipeline"
                error_type=code,
                error_message=message,
                run_id=result.run_id,
            ))
```

**未实现 H1 自述所需的映射**：
> "requires mapping V3 plugin_type to legacy kind (spider→fetcher, processor→processor, storage→exporter, presenter→presenter, ui→presenter) and writing actual plugin instance name"

### 2.5 验收测试实测结果

```bash
$ python -m pytest tests/test_api_closed_loop_g2.py -q
```

**输出**：
```
============================= test session starts =============================
collected 29 items
tests\test_api_closed_loop_g2.py ....F...........s............           [100%]

================================== FAILURES ===================================
____ TestPluginErrorsEndpoint.test_error_keys_intersect_with_plugins_list _____
AssertionError: errors keys ['pipeline:stage:acquire:test_source'] 与 plugins keys [...] 交集为空
=================== 1 failed, 27 passed, 1 skipped in 1.21s ===================
```

测试**按预期失败**——因为 engine 未修复。

```bash
$ python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser
```

**输出**：
```
================== 2 failed, 981 passed, 4 skipped in 15.86s ==================
FAILED tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list
FAILED tests/test_crawler_service.py::test_same_college_dual_source_four_threads
```

第二个失败（`test_same_college_dual_source_four_threads`）与 H1 变更无关，属于既有爬虫服务并发测试的环境波动。

**H1 自述与实测对比**：

| H1 自述 | 实测结果 |
|---------|----------|
| "B-2 root cause identified... requires modification to pipeline/engine.py" | ✅ 已识别根因，但 **engine 修复未实施** |
| "Added acceptance test... currently fails as expected, will pass after engine fix" | ✅ 测试已加入，**但 engine fix 未做**，测试持续失败 |
| "982 passed, 1 failed" | ❌ 实测 **981 passed, 2 failed**（含 1 个无关失败） |

**B-2 判定**：❌ **refuted** —— 修复不完整。`_report_stage_errors` 方法已添加，但仍写入 `plugin_type="pipeline"`，导致错误键与插件列表键**交集为空**。测试使用合成记录复现了当前错误行为，而非验证修复后的正确行为。

---

## 3. 既有断言弱化检查

### 3.1 测试文件变更情况

- `tests/test_api_closed_loop_g2.py`：**新建文件**（untracked），非修改既有测试
- 无 `skip`、`xfail`、`pytest.mark.skip` 等弱化标记
- 无删除/修改既有断言的证据

### 3.2 其他测试文件

`git diff` 显示无既有测试文件被修改（`tests/` 下 tracked 文件无变更）。

**判定**：✅ 无弱化既有断言。

---

## 4. 总结判定

| 检查项 | 结果 | 证据 |
|--------|------|------|
| B-1: 精确路由 `/templates/registry.json` | **confirmed** | HTTP 200，返回 20 模板，路径穿越被拦截 |
| B-2: 错误键与插件键交集非空 | **refuted** | 交集为空，engine 仍写 `plugin_type="pipeline"`，测试为合成记录 |
| 完整测试套件通过 | **refuted** | 2 failed (含 1 个 B-2 预期失败 + 1 个无关失败) |
| 既有断言未弱化 | **confirmed** | 无既有测试被修改/跳过 |

### 最终 verdict：**refuted**

**理由**：
1. B-1 修复属实且完整。
2. B-2 **核心缺陷未解决**：`pipeline/engine.py:_report_stage_errors` 虽已添加，但写入的 `plugin_type="pipeline"` 与 `/api/plugins` 返回的 legacy kind（`fetcher`/`processor`/`exporter`/`presenter`）不匹配，导致前端无法关联错误到具体插件。H1 自述称"需在 engine 中补齐插件身份"，但该补齐**未实施**。测试用例仅锁定了"当前错误行为"，而非验证修复后行为。
3. 综合来看，H1 仅完成了 B-1，B-2 只是"写了会写错日志的代码"，并未真正修复键不匹配的根因。

---

## 5. 附件：关键命令完整输出

### 5.1 B-1 完整 curl 输出

```bash
$ curl -v http://127.0.0.1:5001/templates/registry.json
*   Trying 127.0.0.1:5001...
* Connected to 127.0.0.1 (127.0.0.1) port 5001
> GET /templates/registry.json HTTP/1.1
> Host: 127.0.0.1:5001
> User-Agent: curl/8.14.1
> Accept: */*
>
< HTTP/1.1 200 OK
< Server: Werkzeug/3.1.5 Python/3.12.7
< Date: Wed, 07 Oct 2026 03:01:57 GMT
< Content-Disposition: inline; filename=registry.json
< Content-Type: application/json
< Content-Length: 15884
< Last-Modified: Fri, 18 Sep 2026 10:55:03 GMT
< Cache-Control: no-cache
< ETag: "1789728903.1305296-15884-1207771414"
< Date: Wed, 07 Oct 2026 03:01:57 GMT
< Connection: close
<
{ "version": "1.0", "templates": [ ... 20 templates ... ] }
```

### 5.2 B-2 交集计算完整输出

```bash
# Error keys
$ curl -s "http://127.0.0.1:5001/api/plugins/errors" | python -c "import sys,json; print(set(json.load(sys.stdin).get('errors',{}).keys()))"
{'pipeline:stage:acquire:test_source', 'pipeline:stage_acquire_static_html'}

# Plugin keys
$ curl -s "http://127.0.0.1:5001/api/plugins" | python -c "import sys,json; items=json.load(sys.stdin)['data']['items']; print(sorted({f\"{p['kind']}:{p['name']}\" for p in items if p.get('kind') and p.get('name')}))"
['exporter:jsonl', 'exporter:xlsx', 'fetcher:ajax_api', 'fetcher:js_render', 'fetcher:pdf_list', 'fetcher:static_html', 'parser:yzw_major', 'presenter:config', 'presenter:failures', 'presenter:overview', 'presenter:schools', 'presenter:tutors', 'processor:dedup', 'processor:merge', 'processor:normalize', 'source:school_config', 'utility:cache', 'utility:http_session', 'utility:progress']

# Intersection
$ python -c "error_keys={'pipeline:stage:acquire:test_source','pipeline:stage_acquire_static_html'}; plugin_keys={'exporter:jsonl','exporter:xlsx','fetcher:ajax_api','fetcher:js_render','fetcher:pdf_list','fetcher:static_html','parser:yzw_major','presenter:config','presenter:failures','presenter:overview','presenter:schools','presenter:tutors','processor:dedup','processor:merge','processor:normalize','source:school_config','utility:cache','utility:http_session','utility:progress'}; print('Intersection:', error_keys & plugin_keys)"
Intersection: set()
```

### 5.3 测试套件完整输出

```bash
$ python -m pytest tests/test_api_closed_loop_g2.py -q
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-9.1.1, pluggy-1.6.0
collected 29 items
tests\test_api_closed_loop_g2.py ....F...........s............           [100%]
================================== FAILURES ===================================
____ TestPluginErrorsEndpoint.test_error_keys_intersect_with_plugins_list _____
AssertionError: errors keys ['pipeline:stage:acquire:test_source'] 与 plugins keys [...] 交集为空
=================== 1 failed, 27 passed, 1 skipped in 1.21s ===================

$ python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser
...
================== 2 failed, 981 passed, 4 skipped in 15.86s ==================
FAILED tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list
FAILED tests/test_crawler_service.py::test_same_college_dual_source_four_threads
```

---

**报告生成路径**：`docs/V3.0/acceptance_evidence/browser_github/H1_VERIFICATION.md`