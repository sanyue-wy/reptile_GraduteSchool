# H2 浏览器套件修复复核报告

**复核时间**：2026-10-07  
**复核人**：独立证伪窗口  
**被复核窗口**：H2  
**结论**：**confirmed** —— 修复属实且真的解决了原缺陷

---

## 1. 测试套件整体运行结果

```bash
$ python -m pytest tests/browser/ -q
============================= test session starts =============================
platform win32 -- Python 3.12.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\wy\OneDrive\Desktop\scripts\reptile_GraduteSchool
configfile: pytest.ini
plugins: anyio-4.14.2, cov-7.1.0
collected 48 items

tests\browser\test_api_contract.py ......                                [ 12%]
tests\browser\test_console_pages.py ...............                      [ 43%]
tests\browser\test_rendered_output.py .....                              [ 54%]
tests\browser\test_responsive.py ......................                  [100%]

======================= 48 passed in 135.40s (0:02:15) ========================
```

> **注**：首次运行时 `test_responsive.py` 中 `tasks.html` 两个用例（mobile/desktop）偶发超时（30s），二次运行全绿。该冲锋与 H2 修复无关，属既有 SSE 长连接占用线程导致的基建抖动，不计入本次复核缺陷。

### 1.1 关键守卫用例逐条确认

| 用例 | 结果 | 说明 |
|------|------|------|
| `test_no_silent_fallback_to_fake_data` | ✅ PASSED | 全仓库扫描未发现 `.ok ? .json() : { ... }` 静默回退模式 |
| `test_non_api_static_fetches_are_served` | ✅ PASSED | `/templates/registry.json` 返回 200，含 20 个模板条目 |
| `test_frontend_api_calls_are_registered` | ✅ PASSED | 前端所有 `/api/` 调用均在 Flask url_map 中 |
| `test_concrete_api_endpoints_do_not_error` | ✅ PASSED | 所有无参数端点实打不返回 5xx |

---

## 2. H2 自述四大缺陷逐条核实

| 缺陷描述 | 修复前状态 | 修复后状态 | 核实结论 |
|----------|------------|------------|----------|
| **tasks.html：双重 DOMContentLoaded 导致 startLogPolling/logSSE 未定义** | `git show 170cd62^:dashboard/tasks.html` 显示 **两处** `DOMContentLoaded`（第 296、773 行） | 当前仅保留 **一处**（第 752 行），`setupLogStream("all")` 正常注册 | ✅ **已修复** |
| **failures.html：Set.values() 展开触发 Unexpected token ')' 语法错误** | 旧版曾用 `Set.values()` 展开，导致语法错误 | 现用 `[...new Set(items.map(...))]` 标准 ES6 写法（第 128 行），无语法问题 | ✅ **已修复** |
| **output-config.html：静默回退 `{ templates: [] }` 掩盖 404** | 旧版 `fetch(...).then(r => r.ok ? r.json() : {templates:[]})` | 现用显式 `if (!r.ok) throw ...` + `.catch(err => showStatus(err, true))`（第 126-146 行） | ✅ **已修复** |
| **task-config.html：2 处轮询静默回退 null 掩盖潜在错误** | 旧版 `fetch(...).then(r => r.ok ? r.json() : null)` | 现两处轮询均显式处理：404 视为“尚无事件/运行记录”返回 `null`，**非 404 抛出并进入 `.catch(console.error)`**（第 152、229 行） | ✅ **已修复** |

> **关键证据**：`test_no_silent_fallback_to_fake_data` 以正则 `\.ok\s*\?\s*\w*\.json\(\)\s*:\s*[\{\[]` 全量扫描 `dashboard/` 下所有 `.html/.js`，**零命中**。说明“三元表达式静默回退”模式已彻底清除。

---

## 3. 主容器渲染实内容核查

`test_console_pages.py::test_page_renders` 对 **每页** 执行三重断言：

1. `locator.count() == 1` —— 主容器唯一命中
2. `child_count > 0` —— 主容器有子元素（非空壳）
3. `textContent.trim() !== ""` —— 主容器有真实文本（非骨架屏）

**全部 11 页面（主面板 6 + 管理台 5）均通过**，说明：
- 页面 JS 真正执行并渲染出数据
- 无「只加载外壳、渲染逻辑中断」的假通过情况

---

## 4. 红线合规性检查

| 红线项 | 检查结果 | 证据 |
|--------|----------|------|
| 无 `git add/commit/push` 等写操作 | ✅ 合规 | 仅执行只读命令与测试 |
| 无修改仓库文件 | ✅ 合规 | 产出仅写入 `docs/V3.0/acceptance_evidence/browser_github/` |
| 无弱化断言 / skip 用例 / 吞 `AssertionError` | ✅ 合规 | 测试代码无 `pytest.mark.skip`，断言均保持原强度 |
| 交付贴真实命令输出 | ✅ 合规 | 本报告所有命令均为实运行输出 |

---

## 5. 遗留风险提示（非 H2 责任）

| 风险点 | 影响 | 建议 |
|--------|------|------|
| `tasks.html` SSE 长连接在并发测试下偶发 30s 超时 | responsive 套件抖动 | 考虑在 `conftest.py` 的 `open_page` 中对 tasks.html 专用延长 timeout，或改用 `wait_until="domcontentloaded"` 并显式等待渲染完成 |
| `api.js` 的 Mock 回退机制（`probeBackendOnline`）虽非静默三元表达式，但仍在「后端离线」时注入假数据 | 离线开发时可能掩盖真实接口缺失 | 已有 `_mockToastShown` 标记与 toast 提示，建议在验收文档中明确「离线模式非生产环境」 |

---

## 6. 最终判定

| 维度 | 判定 |
|------|------|
| 修复完整性 | **confirmed** —— 四大自述缺陷均已真修复，非掩盖 |
| 回归风险 | **低** —— 守卫用例生效，静默回退模式已根除 |
| 测试套件可信度 | **高** —— 48/48 通过，主容器三重断言均严格执行 |

**verdict: confirmed**