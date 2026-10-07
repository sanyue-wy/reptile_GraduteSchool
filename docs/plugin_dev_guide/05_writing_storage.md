# 05 - 编写 Storage 插件

> **版本**：v3.0.0
> **状态**：已定稿
> **读者**：存储阶段开发者

## 五分钟最小运行示例

```python
# 使用脚手架生成 storage 并运行
# 命令：python -m scaffolds.cli new storage quick_store
#      python -m pytest tests/fixtures/generated_plugin/quick_store -v

from pathlib import Path
from plugins.storage.sql_store.plugin import SqlStorePlugin
from contracts.result import StoreRequest
from plugins.base import PluginContext

# 创建最小 StoreRequest
class MockContext:
    task_id = "a" * 32
    config_snapshot = {}

request = StoreRequest(
    schema_version="1",
    dataset="test",
    run_id="b" * 32,
    target_id="sql_store_test",
    format_id="jsonl",
    data_refs=["__records__.0"],
    idempotency_key="test_20260920",
    created_at="2026-09-20T00:00:00+00:00",
)

store = SqlStorePlugin()
receipt = store.execute(request, MockContext())
print(f"✓ storage 返回 StoreReceipt: written={receipt.written}, output_ref={receipt.output_ref}")
```

## API 参考：StoragePlugin 接口

```python
# plugins/base.py 中的 StoragePlugin 定义
class StoragePlugin(BasePlugin[StoreRequest, StoreReceipt]):
    """显式副作用、幂等、原子写入、回执"""

    plugin_type: str = "storage"
    input_schema: str = "StoreRequest.v1"
    output_schema: str = "StoreReceipt.v1"

    def execute(self, data: StoreRequest, context: PluginContext) -> StoreReceipt:
        """
        唯一入口：实现存储逻辑
        约束：幂等、原子写入、返回回执
        """
        ...
```

### StoreRequest 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| schema_version | str | ✓ | 固定为 "1" |
| dataset | str | ✓ | 数据集标识 |
| run_id | str | ✓ | 任务运行 ID |
| target_id | str | ✓ | 存储插件实例 ID |
| format_id | str | ✓ | 格式：jsonl/csv/xlsx/sql |
| data_refs | list[str] | ✓ | 数据引用列表 |
| idempotency_key | str | ✓ | 幂等键，避免重复写入 |
| state_snapshot | dict | ✗ | TaskRunState 快照 |
| created_at | str | ✓ | ISO 8601 |

### StoreReceipt 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| target_id | str | ✓ | 存储插件实例 ID |
| written | int | ✓ | 成功写入条数 |
| skipped | int | ✓ | 跳过（幂等/已存在） |
| failed | int | ✓ | 失败条数 |
| records_written | int | ✓ | 写入的记录数 |
| output_ref | str | ✓ | 输出路径/标识 |
| error | ErrorDTO? | ✗ | 失败诊断 |
| created_at | str | ✓ | ISO 8601 |

### 幂等写入模式

```python
def execute(self, request: StoreRequest, context) -> StoreReceipt:
    # 1. 检查幂等
    cache = context.cache
    cache_key = f"store:{request.idempotency_key}"

    cached = cache.get(cache_key)
    if cached:
        return cached  # 幂等返回

    # 2. 原子写入
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', dir=allowed_path) as tmp:
        writer = jsonlines.Writer(tmp)
        for ref in request.data_refs:
            record = self._resolve_data(ref)
            writer.write(record)
        tmp.flush()

        # 3. 原子提交
        final_path = self._get_output_path(request)
        os.replace(tmp.name, final_path)

    # 4. 回执 + 缓存幂等结果
    receipt = StoreReceipt(...)
    cache.set(cache_key, receipt)
    return receipt
```

### 原子写入要点

```python
import tempfile
import os

# 正确：tempfile.mkstemp + os.replace
fd, tmp_path = tempfile.mkstemp(suffix='.jsonl', dir=self._allowed_path)
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(content)
    os.replace(tmp_path, self._output_path)  # 原子替换
except:
    os.unlink(tmp_path)  # 清理临时文件
    raise
```

### 引用解析

```python
def _resolve_data(self, ref: str) -> dict:
    """解析 data_refs 中的数据引用"""

    if ref.startswith("__records__."):
        # 处理器阶段产生的记录引用
        idx = int(ref.split(".")[1])
        batch = self._get_record_batch()
        return batch.records[idx].fields

    elif ref.startswith("__raw__."):
        # Spider 阶段产生的 RawDataDTO 索引
        idx = int(ref.split(".")[1])
        batch = self._get_raw_batch()
        return self._extract_fields(batch.items[idx])

    elif "/" in ref or ref.endswith((".jsonl", ".csv", ".sql")):
        # 文件路径引用
        with open(ref, 'r', encoding='utf-8') as f:
            return json.load(f)

    raise ValueError(f"Unknown data reference: {ref}")
```

## 常见错误与 Top 10 修复

| 错误 | 原因 | 修复 |
|---|---|---|
| `FileExistsError` 写入冲突 | 未使用幂等键 | 使用 `idempotency_key` + 缓存 |
| `OSError: [Errno 13] Permission denied` | 写入不在 allowed_paths | 使用 `context.allowed_paths` |
| `JSONDecodeError` 读取失败 | 写入不完整 | 使用 `os.replace` 保证原子写 |
| `ValueError: Unknown data reference` | data_refs 格式错误 | 检查 `__records_.i`、`__raw__.i` 格式 |
| `TypeError: StoreReceipt missing positional args` | 回执构造不全 | 检查 7 个必填字段 |
| `ImportError: No module named 'jsonlines'` | 依赖缺失 | 在 metadata.json 中声明 dependencies |
| `UnicodeEncodeError: gbk codec` | Windows 编码问题 | 写入时使用 `encoding='utf-8'` |
| `FileNotFoundError: output file` | 路径不存在 | 确保目录存在；创建后再写 |
| `AssertionError: idempotency_key empty` | 幂等键缺失 | 在 StoreRequest 中生成唯一键 |

## 反面示例 → 修复后示例

**错误：直接覆写文件，无幂等**

```python
# BAD
def execute(self, request, context):
    with open("/data/output.jsonl", "w") as f:
        for ref in request.data_refs:
            f.write(json.dumps(self._load(ref)))
    return StoreReceipt(target_id=request.target_id, written=0, ...)
```

**修复后：原子写入 + 幂等**

```python
# GOOD
import tempfile
import os
from datetime import datetime, timezone

def execute(self, request: StoreRequest, context) -> StoreReceipt:
    cache_key = f"store:{request.idempotency_key}"
    if cached := context.cache.get(cache_key):
        return cached

    output_path = Path("/data/output.jsonl")
    fd, tmp_path = tempfile.mkstemp(suffix='.jsonl', dir=output_path.parent)

    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            written = 0
            for ref in request.data_refs:
                f.write(json.dumps(self._load(ref)) + '\n')
                written += 1
        os.replace(tmp_path, output_path)
    except:
        os.unlink(tmp_path)
        raise

    receipt = StoreReceipt(
        target_id=request.target_id,
        written=written,
        skipped=0,
        failed=0,
        records_written=written,
        output_ref=str(output_path),
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    context.cache.set(cache_key, receipt)
    return receipt
```