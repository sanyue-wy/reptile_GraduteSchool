# 回归测量报告 — 浏览器套件验收证据

**执行时间**: 2026-10-07  
**仓库根目录**: `c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool`  
**分支**: `Refactoring_code`  
**执行者**: 回归测量窗口 A

---

## 职责 1 — 真实基线（含 `tests/browser/`）

**命令**:
```bash
cd c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool && python -m pytest tests/ -q --ignore=tests/integration
```

**真实汇总行**:
```
============ 1 failed, 1030 passed, 4 skipped in 88.19s (0:01:28) =============
```

**失败用例**:
- `tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list`

**说明**: 该数字**包含** `tests/browser/` 目录（共 48 个测试）。早先流传的「955 passed」基线**不含** `tests/browser/`，因此与本条命令的口径不可直接比较。

---

## 职责 2 — 浏览器套件

**命令**:
```bash
cd c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool && python -m pytest tests/browser/ -q
```

**真实汇总行**:
```
======================== 48 passed in 82.01s (0:01:22) ========================
```

**失败用例**: 无（全部通过）

**用例明细**:
- `tests/browser/test_api_contract.py` — 6 passed
- `tests/browser/test_console_pages.py` — 15 passed
- `tests/browser/test_rendered_output.py` — 5 passed
- `tests/browser/test_responsive.py` — 22 passed

---

## 职责 3 — CI 口径（不含 integration、不含 browser）

**命令**:
```bash
cd c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool && python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser
```

**真实汇总行**:
```
================== 1 failed, 982 passed, 4 skipped in 18.95s ==================
```

**失败用例**:
- `tests/test_api_closed_loop_g2.py::TestPluginErrorsEndpoint::test_error_keys_intersect_with_plugins_list`

**说明**: 同职责 1 中的同一个预既有失败，非浏览器套件引入。

---

## 职责 4 — 证伪测试（确认浏览器套件有牙）

**目的**: 验证 `test_known_missing_endpoint_is_registered` 在端点被删除时确实转红，证明套件不是摆设。

**插件文件**: `/tmp/remove_errors_endpoint.py`

```python
"""Pytest plugin to remove /api/plugins/errors from app.url_map for falsification test."""
import pytest

@pytest.fixture(scope="module", autouse=True)
def remove_errors_endpoint():
    """Remove /api/plugins/errors endpoint from Flask app url_map."""
    import api.server as server_module
    
    rules_to_remove = []
    for rule in server_module.app.url_map.iter_rules():
        if rule.rule == "/api/plugins/errors" or rule.rule.startswith("/api/plugins/errors/"):
            rules_to_remove.append(rule)
    
    for rule in rules_to_remove:
        server_module.app.url_map._rules.remove(rule)
        if rule.endpoint in server_module.app.url_map._rules_by_endpoint:
            server_module.app.url_map._rules_by_endpoint[rule.endpoint].remove(rule)
            if not server_module.app.url_map._rules_by_endpoint[rule.endpoint]:
                del server_module.app.url_map._rules_by_endpoint[rule.endpoint]
    
    yield
```

**命令**:
```bash
cd c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool && PYTHONPATH=/tmp python -m pytest tests/browser/test_api_contract.py::test_known_missing_endpoint_is_registered -q -p remove_errors_endpoint
```

**真实汇总行**:
```
Exit code 1
========================= 1 failed, 1 passed in 0.91s =========================
```

**失败用例 ID + 断言信息**:
```
_______ test_known_missing_endpoint_is_registered[/api/plugins/errors] ________
c:\Users\wy\OneDrive\Desktop\scripts\reptile_GraduteSchool\tests\browser\test_api_contract.py:117: in test_known_missing_endpoint_is_registered
    assert _rule_exists(url_map_rules, endpoint), (
E   AssertionError: /api/plugins/errors �Բ��� url_map �У�ǰ�� console/plugins.html、runtime/preview.html 已经在调它，后端必须补上
E   assert False
E    +  where False = _rule_exists({'/', '/<path:filename>', '/api/cache/clear', '/api/config', '/api/config/export', '/api/config/global', ...}, '/api/plugins/errors')
=========================== short test summary info ===========================
FAILED tests/browser/test_api_contract.py::test_known_missing_endpoint_is_registered[/api/plugins/errors]
========================= 1 failed, 1 passed in 0.91s =========================
```

**结论**: ✅ **证伪成功**。当 `/api/plugins/errors` 端点从 `app.url_map` 中移除时，`test_known_missing_endpoint_is_registered[/api/plugins/errors]` 确实转红。浏览器套件具有真实的检测能力，不是摆设。

---

## 总结

| 职责 | 结果 | 关键指标 |
|------|------|----------|
| 1. 真实基线（含 browser） | ✅ 完成 | 1 failed, 1030 passed, 4 skipped |
| 2. 浏览器套件 | ✅ 全绿 | 48 passed |
| 3. CI 口径 | ✅ 完成 | 1 failed, 982 passed, 4 skipped |
| 4. 证伪测试 | ✅ 通过 | 端点删除 → 测试转红，套件有效 |

**整体结论**: 浏览器套件 48 个测试全部通过，且通过证伪测试证明其具备真实的回归检测能力。CI 口径下的单个失败为预既有问题（`test_error_keys_intersect_with_plugins_list`），非浏览器套件引入。