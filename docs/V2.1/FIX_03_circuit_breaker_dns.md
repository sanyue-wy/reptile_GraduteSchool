# FIX 03 — CircuitBreaker DNS 错误快速熔断

**严重度**：🟡 中等
**问题根因**：DNS 错误是确定性故障（域名不存在），重试多少次也不会恢复，但 CircuitBreaker 默认阈值 = 5，单域名仅 1 次失败无法触发熔断，后续同域名的剩余任务仍然白白排队。
**涉及文件**：`main.py`
**依赖**：无（独立修改）

---

## 问题详解

当前 `CircuitBreaker.record()` 不区分错误类型，DNS / 超时 / 403 都用同一套计数阈值。对于 DNS NXDOMAIN，单次失败就应立即熔断。

---

## 修改指令

### 步骤 1：在 `CircuitBreaker.record()` 开头添加 DNS 快速熔断

定位 `main.py` 约第 93 行的 `record()` 方法，在 `if domain in self._tripped_domains: return True` 之后、`key = (domain, error_class)` 之前插入：

```python
# 新增：DNS 错误立即熔断，不做计数等待
if error_class == "dns_error":
    self._tripped_domains.add(domain)
    logger.warning(
        "DNS 错误快速熔断: domain=%s（域名不可达，跳过后续重试）",
        domain,
    )
    return True
```

其余逻辑（超时/HTTP 错误的计数熔断）保持不变。

---

## 验证方法

```bash
python -m pytest tests/test_main.py -v -k circuit

python -c "
from main import CircuitBreaker
cb = CircuitBreaker(threshold=5)

# DNS 错误应立即触发
assert cb.record('bad.example', 'dns_error') is True
assert cb.is_tripped('bad.example') is True

# 非 DNS 错误仍需累积到阈值
cb2 = CircuitBreaker(threshold=5)
for i in range(4):
    assert cb2.record('slow.example', 'timeout') is False
assert cb2.record('slow.example', 'timeout') is True

print('PASS')
"
```

---

## 影响范围

仅修改 `main.py` 的 `CircuitBreaker.record()` 方法，新增约 8 行。不影响配置、前端、数据结构。
