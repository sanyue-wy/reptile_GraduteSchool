# 05 - 编写 Storage 插件

> **状态**：初稿
> **读者**：需要实现数据持久化的开发者

## 核心概念

Storage 插件接收 `StoreRequest`，将数据落盘，返回 `StoreReceipt`。

```python
class StoreRequest:
    schema_version: str       # "1"
    dataset: str
    run_id: str
    target_id: str            # 插件实例 ID
    format_id: str            # 格式标识
    data_refs: list[str]      # 数据引用
    idempotency_key: str      # 幂等键
    created_at: str           # ISO 8601

class StoreReceipt:
    target_id: str
    written: int              # 成功写入
    skipped: int              # 跳过（幂等/已存在）
    failed: int               # 失败
    records_written: int
    output_ref: str           # 输出路径/标识
    created_at: str
```

## 幂等键

`idempotency_key` 保证同一数据不会重复写入：

```python
def execute(self, request: StoreRequest, context: PluginContext) -> StoreReceipt:
    output_path = self._resolve_path(request)

    # 幂等检查：已存在且 key 匹配则跳过
    if output_path.exists() and self._read_key(output_path) == request.idempotency_key:
        return StoreReceipt(target_id=request.target_id, written=0, skipped=1, ...)

    # 原子写入
    self._atomic_write(output_path, data)
    return StoreReceipt(target_id=request.target_id, written=1, skipped=0, ...)
```

## 原子写入

**红线**：一切落盘走 `tempfile.mkstemp` + `os.replace`：

```python
import tempfile, os

def _atomic_write(self, path: Path, content: str):
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)  # 原子操作
    except:
        os.unlink(tmp)
        raise
```

## 回执

回执必须包含：
- `written`/`skipped`/`failed`：准确反映实际操作数
- `records_written`：记录条数（可能与文件数不同）
- `output_ref`：输出文件/目录路径

## 参考插件

| 插件 | 目录 | 格式 |
|---|---|---|
| jsonl_store | `plugins/storage/jsonl_store/` | JSONL 文本 |
| xlsx_store | `plugins/storage/xlsx_store/` | Excel 二进制 |
| sql_store | `plugins/storage/sql_store/` | SQLite 数据库 |
| progress_store | `plugins/storage/progress_store/` | 进度快照 |
| media_store | `plugins/storage/media_store/` | 媒体文件 |
