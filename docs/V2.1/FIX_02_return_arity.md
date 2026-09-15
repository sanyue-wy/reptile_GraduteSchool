# FIX 02 — `_run_crawl_task` 返回值解包崩溃

**严重度**：🔴 严重
**问题根因**：`execute_task()` 返回 3 元组 `(success, error, error_type)`，但 `api/server.py` 的 `_run_crawl_task()` 按 2 元组解包，dashboard「重试」按钮触发时直接 `ValueError` 崩溃。
**涉及文件**：`api/server.py`
**依赖**：无（独立修改）

---

## 问题详解

`main.py` 第 449 行定义：
```python
def execute_task(...) -> tuple[bool, Optional[str], str]:
    # 所有 return 路径都返回 3 个值
    return True, None, "none"
    return False, err_msg, error_type
```

`api/server.py` 第 439 行：
```python
success, error = execute_task(task, session, progress, cache)  # ← 只解 2 个
```

当 `execute_task` 内部 catch 住异常并返回 `(False, msg, "dns_error")` 时，解包产生：
```
ValueError: too many values to unpack (expected 2)
```

该异常在 `_run_crawl_task` 的外层 `except Exception` 之前就已发生，导致整个后台任务标记为 `failed`。

**已实际复现**：通过 pytest mock 注入 3 元组返回值，确认解包崩溃。

---

## 修改指令

### 步骤 1：修复解包（第 439 行）

```python
# 修改前
success, error = execute_task(task, session, progress, cache)
```

改为：

```python
# 修改后：匹配 execute_task 的 3 元组返回值
success, error, error_type = execute_task(task, session, progress, cache)
```

### 步骤 2：增强失败日志（紧跟其后，约第 442 行）

```python
# 修改前
if not success:
    logger.warning("任务 %s 子任务失败: %s / %s / %s",
                   task_id, task.university, task.college, task.source)
```

改为：

```python
# 修改后：输出 error_type 便于排查
if not success:
    logger.warning("任务 %s 子任务失败 [%s]: %s / %s / %s — %s",
                   task_id, error_type, task.university, task.college, task.source, error)
```

---

## 验证方法

```bash
# 1. 运行现有 API 测试
python -m pytest tests/test_api.py -v

# 2. 手动验证：模拟 dashboard 重试流程（用不存在域名触发失败路径）
python -c "
from api.server import _run_crawl_task, _new_task_id, _set_task, _get_task
from datetime import datetime

task_id = _new_task_id()
_set_task(task_id, {
    'task_id': task_id, 'status': 'queued', 'progress': {},
    'started_at': datetime.now().isoformat(), 'estimated_remaining': '',
    'params': {
        'schools': ['测试大学'], 'categories': ['mechanical'],
        'sources': ['source_a'], 'force': True, 'year': 2026,
    },
})

import threading
t = threading.Thread(target=_run_crawl_task, args=(task_id,), daemon=True)
t.start()
t.join(timeout=30)
result = _get_task(task_id)
print('task status:', result.get('status'))
assert result.get('status') != 'failed', '不应因 ValueError 崩溃'
print('PASS')
"
```

预期：后台任务正常完成（`status=completed`），不再出现 `ValueError`。

---

## 影响范围

仅修改 `api/server.py` 1 行代码 + 1 行日志，不影响其他模块。
