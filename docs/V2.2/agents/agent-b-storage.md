# Agent B 指导书：存储抽象层

> 对应阶段：阶段二 P1  
> 波次：Wave 1  
> 预计工作量：2-3 天

## 1. 目标

统一 JSONL、进度、配置的文件访问，替换直接 `open()`，保留原子写入和线程安全。

## 2. 可写文件

| 操作 | 文件路径 |
|---|---|
| 新建 | `storage/__init__.py` |
| 新建 | `storage/jsonl_store.py` |
| 新建 | `storage/progress_store.py` |
| 新建 | `storage/config_store.py` |
| 修改 | `pipelines/merge.py` |
| 修改 | `pipelines/export.py` |
| 修改 | `utils/progress.py` |

**禁止修改**：`main.py`、`api/server.py`、`spiders/**`、`config/plugins.py`

## 3. 冻结接口契约

```python
# storage/jsonl_store.py
class JSONLStore:
    def __init__(self, path): ...
    def read_all(self) -> list[dict]: ...
    def write_all(self, records: list[dict], atomic: bool = True) -> None: ...
    def append(self, record: dict) -> None: ...
```

```python
# storage/progress_store.py
class ProgressStore:
    def load(self) -> dict: ...
    def save(self, data: dict) -> None: ...
    def update_school_status(self, school: str, **kwargs) -> None: ...
    def read_all_schools(self) -> dict: ...
```

```python
# storage/config_store.py
class ConfigStore:
    def load_schools(self) -> list[dict]: ...
    def save_school(self, university: str, data: dict) -> bool: ...
    def load_global(self) -> dict: ...
    def save_global(self, data: dict) -> None: ...
```

## 4. 现有代码分析

### 4.1 JSONL 读写散布点

| 文件 | 行范围 | 当前实现 |
|---|---|---|
| `main.py` L365-379 | `run_merge()` | `open()` + `json.loads()` 逐行读取 |
| `main.py` L488-491 | `execute_task()` | `open()` + `json.dumps()` 写 faculty.jsonl |
| `main.py` L497-499 | `execute_task()` | `open()` + `json.dumps()` 写 notice.jsonl |
| `main.py` L407-409 | `run_merge()` | `open()` + `json.dumps()` 写合并结果 |
| `main.py` L802-809 | `main()` 全量导出 | `open()` + `json.loads()` 读所有 JSONL |
| `api/server.py` L114-117 | `_read_merged_records()` | 调用 `pipelines.merge._read_jsonl()` |
| `api/server.py` L120-134 | `_read_all_merged_records()` | `open()` + `json.loads()` |
| `pipelines/merge.py` L303-318 | `_read_jsonl()` | `open()` 逐行读取 |
| `pipelines/merge.py` L321-328 | `_write_jsonl()` | `open()` 写出 |

### 4.2 进度文件读写

| 文件 | 行范围 | 当前实现 |
|---|---|---|
| `utils/progress.py` L84-90 | `_read_raw()` | `open()` + `json.load()`，带 1 秒内存缓存 |
| `utils/progress.py` L92-101 | `_write_raw()` | 临时文件 + `os.replace`（原子写入） |

**关键特性**：`ProgressTracker` 使用 `threading.Lock` 保证线程安全，`_cache_ttl` 默认 1 秒。重构时必须保留这两个特性。

### 4.3 配置文件读写

| 文件 | 行范围 | 当前实现 |
|---|---|---|
| `config/loader.py` | 全文 | `load_schools_config()` + `save_school_config()` |
| `api/server.py` L944-960 | `_write_schools_config()` | `tempfile.mkstemp` + `os.replace` |

## 5. 实施步骤

### Step 1：创建 `storage/__init__.py`

```python
"""存储抽象层：统一 JSONL、进度、配置的文件访问。"""
from .jsonl_store import JSONLStore
from .progress_store import ProgressStore
from .config_store import ConfigStore

__all__ = ["JSONLStore", "ProgressStore", "ConfigStore"]
```

### Step 2：创建 `storage/jsonl_store.py`

```python
class JSONLStore:
    """JSONL 文件读写，保证原子写入。"""

    def __init__(self, path: str | Path):
        self._path = Path(path)

    def read_all(self) -> list[dict]:
        """逐行读取，忽略格式错误行（复用 _read_jsonl 逻辑）。"""

    def write_all(self, records: list[dict], atomic: bool = True) -> None:
        """写全量记录。atomic=True 时使用临时文件 + os.replace。"""

    def append(self, record: dict) -> None:
        """追加单条记录（线程安全，加锁）。"""
```

实现要点：
- `read_all()` 从 `pipelines/merge.py` 的 `_read_jsonl()` 搬入
- `write_all()` 使用 `tempfile.mkstemp` + `os.replace`，与现有 `ProgressTracker._write_raw()` 模式一致
- `append()` 使用 `threading.Lock`，追加写入后不需要原子替换（append 本身是追加模式）
- 目录不存在时自动创建：`self._path.parent.mkdir(parents=True, exist_ok=True)`

### Step 3：创建 `storage/progress_store.py`

```python
class ProgressStore:
    """进度文件读写，封装 progress.json 的原子访问。"""

    def __init__(self, path: Path = PROGRESS_FILE):
        self._path = path
        self._lock = threading.Lock()
        self._cache: dict | None = None
        self._cache_time = 0.0
        self._cache_ttl = 1.0  # 可配置

    def load(self) -> dict:
        """读取进度文件（带缓存）。"""

    def save(self, data: dict) -> None:
        """原子写入进度文件。"""

    def update_school_status(self, school: str, **kwargs) -> None:
        """更新学校状态（读-改-写）。"""

    def read_all_schools(self) -> dict:
        """批量读取所有学校状态。"""
```

实现要点：
- 从 `ProgressTracker` 抽取底层 I/O，`ProgressTracker` 改为内部使用 `ProgressStore`
- `_cache_ttl` 改为构造参数，可配置
- 保留 `threading.Lock` + 原子写入模式
- `ProgressTracker` 的所有高层 API（`get_overview_stats`、`get_pipeline_progress` 等）保持不变

### Step 4：创建 `storage/config_store.py`

```python
class ConfigStore:
    """配置文件读写，封装 school_data.json 和 global.json。"""

    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH):
        self._path = config_path

    def load_schools(self) -> list[dict]:
        """读取学校配置列表。"""

    def save_school(self, university: str, data: dict) -> bool:
        """保存单个学校配置（原子写入）。"""

    def load_global(self) -> dict:
        """读取全局配置。"""

    def save_global(self, data: dict) -> None:
        """保存全局配置（原子写入）。"""
```

实现要点：
- 从 `config/loader.py` 和 `api/server.py` 的 `_write_schools_config()` 抽取
- 原子写入使用 `tempfile.mkstemp` + `os.replace`

### Step 5：改造 `pipelines/merge.py`

1. `_read_jsonl()` 改为内部使用 `JSONLStore(path).read_all()`
2. `_write_jsonl()` 改为内部使用 `JSONLStore(path).write_all()`
3. **保留旧函数签名**：`_read_jsonl(path)` 和 `_write_jsonl(path, records)` 继续作为兼容层导出
4. 公开 API `merge_sources()` 参数不变

### Step 6：改造 `pipelines/export.py`

1. `export_merged()` 中的 `open()` 改为 `JSONLStore`
2. `export_failures()` 和 `load_failures()` 中的 `open()` 改为 `JSONLStore`（failures.json 是 JSON，不是 JSONL，可用 `ConfigStore` 模式或保留原样）
3. 保留所有公开函数签名不变

### Step 7：改造 `utils/progress.py`

1. `ProgressTracker.__init__()` 内部创建 `ProgressStore`
2. `_read_raw()` 委托 `ProgressStore.load()`
3. `_write_raw()` 委托 `ProgressStore.save()`
4. **保留所有公开 API 不变**：`get_school_status()`、`update_school_status()`、`get_overview_stats()` 等
5. `_cache_ttl` 改为构造参数

## 6. 同步点

| 依赖 | 接口 | 说明 |
|---|---|---|
| Agent A | `services/crawler_service.py` 调用 `main.py` 的 `run_merge()` | B 改造 `pipelines/merge.py` 时保留旧接口 |
| Agent A | `services/export_service.py` 调用 `pipelines/export.py` | B 改造 `pipelines/export.py` 时保留旧接口 |
| Agent E | `utils/progress.py` 归 B 独占 | E 不修改 `utils/progress.py` |

## 7. 验收命令

```bash
# 1. 语法检查
python -m py_compile storage/jsonl_store.py
python -m py_compile storage/progress_store.py
python -m py_compile storage/config_store.py
python -m py_compile pipelines/merge.py
python -m py_compile pipelines/export.py
python -m py_compile utils/progress.py

# 2. 存储层测试
pytest tests/test_storage_layer.py -q

# 3. 现有测试不破坏
pytest tests/test_merge.py -q
pytest tests/test_export.py -q
pytest tests/test_progress.py -q

# 4. 检查所有 json/jsonl 读写均通过 storage 层
grep -rn "open(" pipelines/merge.py pipelines/export.py | grep -v "# noqa"
# 期望：无直接 open() 调用（全部通过 JSONLStore）
```

## 8. 注意事项

1. **原子写入模式必须保留**：`tempfile.mkstemp` + `os.replace`，不得改为直接 `open(..., "w")`
2. **线程安全必须保留**：`threading.Lock` 在 `ProgressStore` 和 `JSONLStore.append()` 中
3. **缓存 TTL 可配置**：`ProgressStore` 的 `_cache_ttl` 通过构造参数传入
4. **旧函数签名兼容**：`_read_jsonl(path)` 和 `_write_jsonl(path, records)` 继续导出
5. **不改 `main.py` 和 `api/server.py`**：这两个文件归 Agent A，B 只改 pipelines 和 progress
