# Agent F 指导书：测试增强与回归守护

> 对应阶段：阶段六 P3  
> 波次：Wave 1（可与 A-E 同时开始，但最终验收在 Wave 3）  
> 预计工作量：3-4 天

## 1. 目标

按冻结接口先写契约测试，覆盖服务层、合并、插件安全、存储、引擎、熔断。初期可用 mock；集成后由 Agent G 切换真实实现。

## 2. 可写文件

| 操作 | 文件路径 |
|---|---|
| 新建 | `tests/test_crawler_service.py` |
| 新建 | `tests/test_merge_service.py` |
| 新建 | `tests/test_plugin_security.py` |
| 新建 | `tests/test_storage_layer.py` |
| 新建 | `tests/test_engine_abstraction.py` |
| 新建 | `tests/test_http_circuit.py` |
| 修改 | `tests/conftest.py`（仅追加 fixtures） |

**禁止修改**：任何生产代码

## 3. 现有测试分析

### 3.1 已有测试文件

| 文件 | 覆盖范围 |
|---|---|
| `tests/test_integration.py` | 集成测试（5 个方法） |
| `tests/test_merge.py` | 合并管道 |
| `tests/test_export.py` | 导出管道 |
| `tests/test_http.py` | HTTP 请求 |
| `tests/test_progress.py` | 进度追踪 |
| `tests/test_cache.py` | 缓存模块 |
| `tests/test_spiders_static.py` | 静态列表爬虫 |
| `tests/test_spiders_ajax.py` | AJAX API 爬虫 |
| `tests/test_spiders_detail.py` | 详情页解析 |
| `tests/test_plugins.py` | 插件系统 |
| `tests/test_config.py` | 配置加载 |
| `tests/test_dedup.py` | 去重 |
| `tests/test_errors.py` | 错误分类 |
| `tests/test_main.py` | 主入口 |
| `tests/conftest.py` | 公共 fixtures |

### 3.2 测试缺口（本次需覆盖）

| 模块 | 缺口 | 对应 Agent |
|---|---|---|
| `services/crawler_service.py` | 全新模块，无测试 | A |
| `services/merge_service.py` | 全新模块，无测试 | A |
| `services/export_service.py` | 全新模块，无测试 | A |
| `storage/jsonl_store.py` | 全新模块，无测试 | B |
| `storage/progress_store.py` | 全新模块，无测试 | B |
| `storage/config_store.py` | 全新模块，无测试 | B |
| `spiders/engine.py` | 全新模块，无测试 | C |
| `security/plugin_validator.py` | 全新模块，无测试 | D |
| `PoliteSession.is_blocked()` | 新增接口，无测试 | E |

## 4. 实施步骤

### Step 1：更新 `tests/conftest.py` — 追加 fixtures

```python
import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def tmp_output_dir(tmp_path):
    """临时输出目录，避免污染 data/。"""
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture
def tmp_cache_dir(tmp_path):
    """临时缓存目录。"""
    cache = tmp_path / "cache"
    cache.mkdir()
    return cache


@pytest.fixture
def mock_session():
    """Mock PoliteSession，不发真实请求。"""
    from unittest.mock import MagicMock
    session = MagicMock()
    session.stats = {"requests": 0, "success": 0, "failed": 0, "raw_saved": 0}
    session.is_blocked.return_value = False
    session.get_block_count.return_value = 0
    return session


@pytest.fixture
def mock_progress(tmp_path):
    """临时 ProgressTracker，使用临时目录。"""
    from utils.progress import ProgressTracker
    return ProgressTracker(
        progress_file=tmp_path / "progress.json",
        log_file=tmp_path / "crawl.log",
    )


@pytest.fixture
def sample_faculty_records():
    """示例 Source A 记录。"""
    return [
        {"name": "张三", "university": "测试大学", "college": "机械学院",
         "title": "教授", "research_areas": ["机器人"], "source_type": "官网师资页"},
        {"name": "李四", "university": "测试大学", "college": "机械学院",
         "title": "副教授", "research_areas": ["流体力学"], "source_type": "官网师资页"},
    ]


@pytest.fixture
def sample_notice_records():
    """示例 Source B 记录。"""
    return [
        {"name": "张三", "university": "测试大学", "college": "机械学院",
         "in_roster": True, "directions": [{"code": "080200", "name": "机械工程"}],
         "source_type": "研招网"},
        {"name": "王五", "university": "测试大学", "college": "机械学院",
         "in_roster": True, "directions": [{"code": "080200", "name": "机械工程"}],
         "source_type": "研招网"},
    ]


@pytest.fixture
def sample_plugin_source():
    """安全的示例插件源码。"""
    return '''
PLUGIN_META = {
    "name": "test_plugin",
    "kind": "processor",
    "version": "1.0.0",
    "author": "test",
    "description": "测试插件",
}

def process(records, ctx):
    return records
'''
```

### Step 2：创建 `tests/test_crawler_service.py`

```python
"""CrawlerService 契约测试。"""
import pytest
from unittest.mock import MagicMock, patch


class TestCrawlerServiceBuildTasks:
    """build_tasks() 测试。"""

    def test_build_tasks_with_all_schools(self, mock_session, mock_progress):
        """传入 __all__ 应返回所有配置的任务。"""
        from services.crawler_service import CrawlerService
        service = CrawlerService(config={}, cache=None, progress=mock_progress,
                                session_factory=lambda: mock_session)
        # 初期用 mock，集成后切换真实实现
        pytest.xfail("等待 Agent A 完成 CrawlerService 实现")

    def test_build_tasks_resume_skips_done(self):
        """断点续抓应跳过已完成的任务。"""
        pytest.xfail("等待 Agent A 完成 CrawlerService 实现")

    def test_build_tasks_retry_failed(self):
        """失败重试模式应只返回失败的任务。"""
        pytest.xfail("等待 Agent A 完成 CrawlerService 实现")


class TestCrawlerServiceRunSourceA:
    """run_source_a() 测试。"""

    def test_returns_enriched_records(self):
        """Source A 应返回 enriched 记录列表。"""
        pytest.xfail("等待 Agent A 完成 CrawlerService 实现")

    def test_handles_missing_list_url(self):
        """缺少 list_url 时应抛出 ValueError。"""
        pytest.xfail("等待 Agent A 完成 CrawlerService 实现")


class TestCrawlerServiceExecuteTask:
    """execute_task() 测试。"""

    def test_success_returns_true(self):
        """成功执行应返回 (True, None, 'none')。"""
        pytest.xfail("等待 Agent A 完成 CrawlerService 实现")

    def test_blocked_error_returns_false(self):
        """BlockedError 应返回 (False, error_msg, error_type)。"""
        pytest.xfail("等待 Agent A 完成 CrawlerService 实现")
```

### Step 3：创建 `tests/test_merge_service.py`

```python
"""MergeService 契约测试。"""
import pytest


class TestMergeServiceMatchRecords:
    """match_records() 三阶匹配测试。"""

    def test_exact_match(self, sample_faculty_records, sample_notice_records):
        """精确匹配：姓名完全相同。"""
        from services.merge_service import MergeService
        service = MergeService()
        # "张三" 精确匹配
        pytest.xfail("等待 Agent A 完成 MergeService 实现")

    def test_strip_match(self):
        """去空格匹配：'张 三' vs '张三'。"""
        pytest.xfail("等待 Agent A 完成 MergeService 实现")

    def test_fuzzy_match(self):
        """模糊匹配：相似度 ≥ 0.85。"""
        pytest.xfail("等待 Agent A 完成 MergeService 实现")

    def test_no_match_partial_faculty(self):
        """未匹配的 faculty 记录标记为 partial_faculty。"""
        pytest.xfail("等待 Agent A 完成 MergeService 实现")

    def test_no_match_partial_notice(self):
        """未匹配的 notice 记录标记为 partial_notice。"""
        pytest.xfail("等待 Agent A 完成 MergeService 实现")
```

### Step 4：创建 `tests/test_plugin_security.py`

```python
"""插件安全检查测试。"""
import pytest


class TestValidatePluginSource:
    """validate_plugin_source() 测试。"""

    def test_safe_source_passes(self, sample_plugin_source):
        """安全的插件源码应通过。"""
        from security.plugin_validator import validate_plugin_source
        result = validate_plugin_source(sample_plugin_source, kind="processor")
        assert result.ok is True
        assert result.errors == []

    def test_blocked_os_import(self):
        """import os 应被检测。"""
        from security.plugin_validator import validate_plugin_source
        source = '''
PLUGIN_META = {"name": "bad", "kind": "processor", "version": "1", "author": "x", "description": "x"}
import os
def process(records, ctx): return records
'''
        result = validate_plugin_source(source, kind="processor")
        assert any("os" in w for w in result.warnings)

    def test_blocked_eval_call(self):
        """eval() 调用应被检测。"""
        from security.plugin_validator import validate_plugin_source
        source = '''
PLUGIN_META = {"name": "bad", "kind": "processor", "version": "1", "author": "x", "description": "x"}
def process(records, ctx):
    eval("1+1")
    return records
'''
        result = validate_plugin_source(source, kind="processor")
        assert any("eval" in w for w in result.warnings)

    def test_missing_meta(self):
        """缺少 PLUGIN_META 应报错。"""
        from security.plugin_validator import validate_plugin_source
        result = validate_plugin_source("x = 1", kind="processor")
        assert result.ok is False
        assert any("PLUGIN_META" in e for e in result.errors)

    def test_syntax_error(self):
        """语法错误应报错。"""
        from security.plugin_validator import validate_plugin_source
        result = validate_plugin_source("def foo(:", kind="processor")
        assert result.ok is False
        assert any("语法" in e for e in result.errors)

    def test_missing_interface_function(self):
        """缺少接口函数应报错。"""
        from security.plugin_validator import validate_plugin_source
        source = '''
PLUGIN_META = {"name": "bad", "kind": "processor", "version": "1", "author": "x", "description": "x"}
x = 1
'''
        result = validate_plugin_source(source, kind="processor")
        assert result.ok is False
        assert any("process" in e for e in result.errors)
```

### Step 5：创建 `tests/test_storage_layer.py`

```python
"""存储层测试。"""
import pytest


class TestJSONLStore:
    """JSONLStore 测试。"""

    def test_read_empty_file(self, tmp_path):
        """读取不存在的文件应返回空列表。"""
        from storage.jsonl_store import JSONLStore
        store = JSONLStore(tmp_path / "nonexistent.jsonl")
        assert store.read_all() == []

    def test_write_and_read(self, tmp_path):
        """写入后读取应返回相同数据。"""
        from storage.jsonl_store import JSONLStore
        path = tmp_path / "test.jsonl"
        store = JSONLStore(path)
        records = [{"name": "张三"}, {"name": "李四"}]
        store.write_all(records)
        assert store.read_all() == records

    def test_atomic_write(self, tmp_path):
        """原子写入：写入过程中断不应损坏原文件。"""
        pytest.xfail("需要模拟写入中断")

    def test_append_thread_safe(self, tmp_path):
        """追加操作应线程安全。"""
        from storage.jsonl_store import JSONLStore
        import threading
        path = tmp_path / "concurrent.jsonl"
        store = JSONLStore(path)
        store.write_all([])

        def append_one(i):
            store.append({"id": i})

        threads = [threading.Thread(target=append_one, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        records = store.read_all()
        assert len(records) == 50


class TestProgressStore:
    """ProgressStore 测试。"""

    def test_default_structure(self, tmp_path):
        """新建文件应有默认结构。"""
        from storage.progress_store import ProgressStore
        store = ProgressStore(tmp_path / "progress.json")
        data = store.load()
        assert "version" in data
        assert "schools" in data

    def test_update_school_status(self, tmp_path):
        """更新学校状态应原子写入。"""
        pytest.xfail("等待 Agent B 完成 ProgressStore 实现")

    def test_cache_ttl_configurable(self, tmp_path):
        """缓存 TTL 应可配置。"""
        pytest.xfail("等待 Agent B 完成 ProgressStore 实现")
```

### Step 6：创建 `tests/test_engine_abstraction.py`

```python
"""SpiderEngine 抽象层测试。"""
import pytest


class TestSpiderEngineRegistry:
    """引擎注册表测试。"""

    def test_all_engines_registered(self):
        """所有内置引擎应已注册。"""
        from spiders.engine import ENGINE_REGISTRY
        expected = {"static_list", "ajax_api", "yzw_api", "detail_parser"}
        # js_render 和 pdf_list 可能条件导入
        for name in expected:
            assert name in ENGINE_REGISTRY, f"引擎 {name} 未注册"

    def test_engine_has_required_attrs(self):
        """每个引擎应有 name 和 supported_source。"""
        from spiders.engine import ENGINE_REGISTRY
        for name, cls in ENGINE_REGISTRY.items():
            engine = cls.__new__(cls)
            assert hasattr(engine, "name"), f"{name} 缺少 name"
            assert hasattr(engine, "supported_source"), f"{name} 缺少 supported_source"


class TestStaticListEngine:
    """StaticListEngine 测试。"""

    def test_fetch_returns_list(self):
        """fetch() 应返回 list[dict]。"""
        pytest.xfail("等待 Agent C 完成 Engine 实现")

    def test_parse_returns_list(self):
        """parse() 应返回 list[dict]。"""
        pytest.xfail("等待 Agent C 完成 Engine 实现")
```

### Step 7：创建 `tests/test_http_circuit.py`

```python
"""PoliteSession 熔断/冷却测试。"""
import pytest


class TestPoliteSessionBlocking:
    """is_blocked() 和 get_block_count() 测试。"""

    def test_is_blocked_false_initially(self):
        """初始状态应不被阻断。"""
        from utils.http import PoliteSession
        session = PoliteSession(delay_range=(0, 0))
        assert session.is_blocked("example.com") is False

    def test_cooldown_after_threshold(self):
        """达到阈值后应被冷却。"""
        pytest.xfail("等待 Agent E 完成 is_blocked 实现")

    def test_dns_fast_circuit(self):
        """DNS 错误应立即熔断。"""
        pytest.xfail("等待 Agent E 完成 DNS 熔断实现")

    def test_get_block_count_per_domain(self):
        """get_block_count 应按域名分别计数。"""
        pytest.xfail("等待 Agent E 完成按域名计数实现")

    def test_reset_circuit(self):
        """reset_circuit() 应解除熔断。"""
        pytest.xfail("等待 Agent E 完成 reset_circuit 实现")
```

## 5. 测试执行策略

### 5.1 开发期（Wave 1）

- 大量 `pytest.xfail()` 标记，确保测试可运行但不阻塞
- 使用 `mock` 替代未实现的模块
- 重点测试已有的旧接口不被破坏

### 5.2 集成期（Wave 3）

- 逐步移除 `xfail`，切换为真实实现
- 对齐接口契约，修复接口不一致问题
- 运行全量测试：`pytest tests/ -q`

## 6. 验收命令

```bash
# 1. 全量测试通过
pytest tests/ -q

# 2. 覆盖率报告
pytest tests/ --cov=services --cov=storage --cov=spiders --cov=utils --cov-report=term

# 3. 核心模块覆盖率 ≥ 80%
# 目标模块：services/, storage/, spiders/engine.py, security/, utils/http.py
```

## 7. 注意事项

1. **不修改生产代码**：F 只写测试，不改任何 `*.py` 生产文件
2. **测试使用临时目录**：所有 `tmp_path` fixture，不污染 `data/`
3. **`xfail` 标记策略**：初期全部 xfail，集成后逐步移除
4. **conftest.py 只追加**：不删除现有 fixtures
5. **Mock 策略**：服务层用 mock 调用底层，底层用真实实现测试
