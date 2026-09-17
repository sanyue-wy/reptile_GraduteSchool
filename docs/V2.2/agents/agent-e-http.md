# Agent E 指导书：HTTP 熔断/冷却与缓存性能优化

> 对应阶段：阶段五 P3  
> 波次：Wave 1  
> 预计工作量：2 天

## 1. 目标

整合 `CircuitBreaker`（`main.py` L94-143）与 `PoliteSession`（`utils/http.py` L63-281）的状态，统一熔断/冷却查询接口；优化 `CrawlCache`（`utils/cache.py`）批量读取。不碰 `main.py` 和 `utils/progress.py`。

## 2. 可写文件

| 操作 | 文件路径 |
|---|---|
| 修改 | `utils/http.py`（292 行） |
| 修改 | `utils/cache.py`（199 行） |

**禁止修改**：`main.py`、`utils/progress.py`、`services/**`、`spiders/**`、`config/**`

## 3. 冻结接口契约

```python
# utils/http.py — PoliteSession 新增接口
class PoliteSession:
    # ... 现有接口不变 ...

    def is_blocked(self, domain: str | None = None) -> bool:
        """检查域名是否被冷却/熔断。domain=None 检查所有域名。"""

    def get_block_count(self, domain: str | None = None) -> int:
        """获取冷却计数。domain=None 返回全局计数。"""
```

## 4. 现有代码分析

### 4.1 `PoliteSession` 当前冷却机制（`utils/http.py`）

| 属性/方法 | 行范围 | 功能 |
|---|---|---|
| `self._block_count` | L95 | 连续 403/429 计数器 |
| `self._blocked_domains` | L96 | 已冷却域名集合 |
| `self.cooldown_threshold` | L86 | 冷却阈值（默认 5） |
| `self.cooldown_seconds` | L87 | 冷却等待秒数（默认 1800） |
| `_request()` L186-194 | 反爬检测 | 403/429 计数，达到阈值时 `add` 到 `_blocked_domains` |
| `_request()` L158-160 | 冷却检查 | 请求前检查域名是否在 `_blocked_domains` |
| `clear_cooldown(domain)` | L277-280 | 手动解除冷却 |

**问题**：`_block_count` 是全局计数，不区分域名。当 domain A 触发 3 次 403、domain B 触发 2 次 403，总计 5 次就触发冷却，但实际上每个域名都不够阈值。

### 4.2 `CircuitBreaker`（`main.py` L94-143）

| 方法 | 功能 |
|---|---|
| `record(domain, error_class)` | 记录失败，DNS 错误立即熔断 |
| `is_tripped(domain)` | 检查域名是否被熔断 |
| `reset(domain)` | 成功时重置熔断状态 |
| `tripped_domains` | 返回所有被熔断的域名集合 |

**与 PoliteSession 的区别**：
- `CircuitBreaker` 按 `(domain, error_class)` 维度记录
- `PoliteSession` 只按域名记录 403/429
- `CircuitBreaker` 支持 DNS 快速熔断
- `CircuitBreaker` 有滑动窗口机制

### 4.3 `CrawlCache` 当前实现（`utils/cache.py`）

| 方法 | 功能 |
|---|---|
| `read_text(url)` | 读缓存文本 |
| `write(url, text)` | 写缓存（原子替换） |
| `get_or_fetch(fetch_fn, url, force, use_cache)` | 带缓存的请求入口 |
| `clear()` | 清空缓存 |
| `stats` | 命中/未命中/写入统计 |

**可优化点**：
- 缺少批量读取接口（Agent A 的服务层可能需要）
- `_inflight` 去重机制的超时后清理不够健壮

## 5. 实施步骤

### Step 1：`PoliteSession` 增加按域名计数

修改 `_block_count` 为按域名分别计数：

```python
class PoliteSession:
    def __init__(self, ...):
        ...
        # 修改前：self._block_count = 0
        # 修改后：
        self._block_counts: dict[str, int] = {}  # domain -> 连续 403/429 次数
        self._blocked_domains: set[str] = set()   # 已冷却域名（保留）
```

修改 `_request()` 中的反爬检测逻辑：

```python
# 修改前（L186-194）：
if resp.status_code in (403, 429):
    self._block_count += 1
    if self._block_count >= self.cooldown_threshold:
        self._blocked_domains.add(domain)
        ...

# 修改后：
if resp.status_code in (403, 429):
    self._block_counts[domain] = self._block_counts.get(domain, 0) + 1
    if self._block_counts[domain] >= self.cooldown_threshold:
        self._blocked_domains.add(domain)
        ...
```

修改成功时的重置逻辑：

```python
# 修改前（L204）：self._block_count = 0
# 修改后：
self._block_counts.pop(domain, None)
```

### Step 2：增加同因熔断能力

在 `PoliteSession` 中增加按 `(domain, error_class)` 维度的熔断逻辑：

```python
class PoliteSession:
    def __init__(self, ...):
        ...
        # 新增：同因熔断
        self._circuit_history: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._circuit_tripped: set[str] = set()
        self._circuit_threshold: int = 5      # 可由构造参数传入
        self._circuit_window: int = 3600       # 滑动窗口秒数
```

在 `_request()` 的异常处理中记录：

```python
except (requests.ConnectionError, requests.Timeout) as e:
    err_str = str(e).lower()
    is_dns = ("getaddrinfo" in err_str or ...)
    if is_dns:
        # DNS 错误立即熔断
        self._circuit_tripped.add(domain)
        self.stats["failed"] += 1
        raise
    ...
```

### Step 3：实现 `is_blocked()` 和 `get_block_count()`

```python
def is_blocked(self, domain: str | None = None) -> bool:
    """检查域名是否被冷却或熔断。"""
    if domain is None:
        return bool(self._blocked_domains or self._circuit_tripped)
    return domain in self._blocked_domains or domain in self._circuit_tripped

def get_block_count(self, domain: str | None = None) -> int:
    """获取冷却计数。"""
    if domain is None:
        return sum(self._block_counts.values())
    return self._block_counts.get(domain, 0)

@property
def tripped_domains(self) -> set[str]:
    """返回所有被熔断或冷却的域名。"""
    return self._blocked_domains | self._circuit_tripped
```

### Step 4：保留 `clear_cooldown()` 并增加 `reset_circuit()`

```python
def clear_cooldown(self, domain: str):
    """手动解除域名冷却。"""
    self._blocked_domains.discard(domain)
    self._block_counts.pop(domain, None)

def reset_circuit(self, domain: str):
    """手动解除域名熔断。"""
    self._circuit_tripped.discard(domain)
    keys_to_remove = [k for k in self._circuit_history if k[0] == domain]
    for k in keys_to_remove:
        del self._circuit_history[k]
```

### Step 5：`CrawlCache` 增加批量读取

```python
class CrawlCache:
    def read_many(self, urls: list[str]) -> dict[str, Optional[str]]:
        """批量读取多个 URL 的缓存。返回 {url: text_or_None}。"""
        results = {}
        for url in urls:
            results[url] = self.read_text(url)
        return results

    def get_hit_rate(self) -> float:
        """返回缓存命中率。"""
        total = self.stats["hits"] + self.stats["misses"]
        return self.stats["hits"] / total if total > 0 else 0.0
```

### Step 6：清理 `_inflight` 超时机制

```python
def get_or_fetch(self, fetch_fn, url, force=False, use_cache=True) -> str:
    ...
    if wait:
        ev.wait(timeout=300)
        if "text" in holder:
            return holder["text"]
        # 新增：清理无主的 inflight 条目
        with self._lock:
            if self._inflight.get(url) and self._inflight[url][0] is ev:
                del self._inflight[url]
        logger.warning("等待 %s 的在途请求超时，重新抓取", url)
    ...
```

## 6. 同步点

| 依赖 | 接口 | 说明 |
|---|---|---|
| Agent A | `CrawlerService` 调用 `session.is_blocked(domain)` | E 提供接口，A 在服务层使用 |
| Agent A | 删除 `main.py` 的 `CircuitBreaker` | E 的 `PoliteSession` 已包含同等功能 |
| Agent B | `utils/progress.py` 归 B 独占 | E 不修改 `utils/progress.py` |

## 7. 验收命令

```bash
# 1. 语法检查
python -m py_compile utils/http.py
python -m py_compile utils/cache.py

# 2. HTTP 测试
pytest tests/test_http.py -q

# 3. 缓存测试
pytest tests/test_cache.py -q

# 4. 新接口测试
pytest tests/test_http_circuit.py -q

# 5. 并发压力测试
python main.py --school "东南大学" --source source_a --workers 4 --year 2026
# 检查 progress.json 无损坏
```

## 8. 注意事项

1. **`_block_count` → `_block_counts` 是破坏性变更**：所有引用 `self._block_count` 的地方都要改，但只在 `utils/http.py` 内部
2. **`BlockedError` 和 `MaxRetriesExceeded` 行为不变**：异常类定义和抛出时机不变
3. **`response_text()` 函数不变**：这是模块级工具函数，所有 spider 都在用
4. **DNS 快速熔断**：从 `CircuitBreaker` 搬入 `PoliteSession`，DNS 错误不重试直接抛出
5. **`cooldown_seconds` 参数保留**：但不再使用 `time.sleep()` 等待，改为标记域名状态
6. **不改 `main.py`**：Agent A 负责删除 `CircuitBreaker`，E 只提供替代接口
