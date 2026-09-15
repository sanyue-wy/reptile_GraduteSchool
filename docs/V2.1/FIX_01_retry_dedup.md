# FIX 01 — DNS/确定性错误双重重试消除

**严重度**：🔴 严重
**问题根因**：urllib3 Retry 策略与 `PoliteSession._request()` 应用层重试循环重叠，DNS 错误被重试 4×3=12 次，耗时约 37 秒后才失败。
**涉及文件**：`utils/http.py`
**依赖**：无（独立修改）

---

## 问题详解

`PoliteSession.__init__()` 创建了 urllib3 的 `Retry(total=3)` 策略挂载到 adapter 上，同时 `_request()` 内部又有 `for attempt in range(max_retries+1)` 循环。当 urllib3 抛出 `ConnectionError`（已被包装为 `MaxRetriesError`）后，应用层再捕获并重试，又触发 urllib3 新一轮 Retry。

日志中的实际表现：
```
urllib3 Retrying(total=2) ... NameResolutionError
urllib3 Retrying(total=1) ... NameResolutionError
urllib3 Retrying(total=0) ... NameResolutionError
应用层第1次重试 → urllib3 又来一轮3次
应用层第2次重试 → urllib3 又来一轮3次
应用层第3次重试 → urllib3 又来一轮3次
总耗时: ~37秒
```

---

## 修改指令

### 步骤 1：移除 urllib3 Retry，仅保留应用层重试

在 `utils/http.py` 中修改 `__init__` 方法（约第 60-70 行）：

```python
# 修改前
retry_strategy = Retry(
    total=max_retries,
    backoff_factor=1.0,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)
adapter = HTTPAdapter(max_retries=retry_strategy)
```

改为：

```python
# 修改后：HTTPAdapter 不再内置重试，由 _request() 统一控制
adapter = HTTPAdapter()
```

删除不再需要的 `Retry` import（第 21 行）：
```python
# 删除这行
from urllib3.util.retry import Retry
```

### 步骤 2：在 `_request()` 中对 DNS 错误快速失败

在 `utils/http.py` 的 `_request()` 方法中（约第 191 行的 `except` 块），在重试前判断是否为确定性错误：

```python
# 修改前（约第 191-199 行）
except (requests.ConnectionError, requests.Timeout) as e:
    if attempt < self.max_retries:
        backoff = (2 ** attempt) * random.uniform(1, 3)
        logger.warning("连接失败 %s，%d 次重试，等待 %.1fs: %s",
                       url, attempt + 1, backoff, e)
        time.sleep(backoff)
    else:
        self.stats["failed"] += 1
        raise
```

改为：

```python
# 修改后：DNS 错误立即失败，不做无意义重试
except (requests.ConnectionError, requests.Timeout) as e:
    # DNS 解析失败是确定性错误，重试无意义
    err_str = str(e).lower()
    is_dns = ("getaddrinfo" in err_str
              or "name or service not known" in err_str
              or "nameresolutionerror" in err_str)
    if is_dns:
        self.stats["failed"] += 1
        raise

    if attempt < self.max_retries:
        backoff = (2 ** attempt) * random.uniform(1, 3)
        logger.warning("连接失败 %s，%d 次重试，等待 %.1fs: %s",
                       url, attempt + 1, backoff, e)
        time.sleep(backoff)
    else:
        self.stats["failed"] += 1
        raise
```

---

## 验证方法

```bash
# 1. 运行单元测试
python -m pytest tests/test_http.py -v

# 2. 手动验证：用一个不存在的域名，应快速失败（< 5秒）
python -c "
from utils.http import PoliteSession
import time
s = PoliteSession(delay_range=(0,0), max_retries=3)
t0=time.time()
try:
    s.get('https://no-such-domain-xyz.example/test')
except Exception as e:
    elapsed=time.time()-t0
    print(f'失败耗时: {elapsed:.1f}s (应 < 5s)')
    print(f'异常类型: {type(e).__name__}')
"
```

预期：失败耗时应从 ~37 秒降至 < 5 秒。
