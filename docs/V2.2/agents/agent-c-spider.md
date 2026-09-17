# Agent C 指导书：统一爬虫引擎接口

> 对应阶段：阶段三 P2  
> 波次：Wave 1  
> 预计工作量：2-3 天

## 1. 目标

用 `SpiderEngine` 抽象基类统一 5 个爬虫引擎，降低 `spiders/` 间直接依赖，为未来插件化爬虫打基础。

## 2. 可写文件

| 操作 | 文件路径 |
|---|---|
| 新建 | `spiders/engine.py` |
| 修改 | `spiders/static_list.py`（149 行） |
| 修改 | `spiders/ajax_api.py`（141 行） |
| 修改 | `spiders/yzw_api.py`（285 行） |
| 修改 | `spiders/detail_parser.py`（290 行） |
| 修改 | `spiders/js_render.py`（130 行） |
| 修改 | `spiders/pdf_list.py`（282 行） |

**禁止修改**：`main.py`、`api/server.py`、`utils/**`、`config/**`

## 3. 冻结接口契约

```python
# spiders/engine.py
from abc import ABC, abstractmethod

class SpiderEngine(ABC):
    """爬虫引擎抽象基类。"""
    name: str                           # 引擎名称，如 "static_list"
    supported_source: str               # 对应数据源，如 "source_a" / "source_b"

    @abstractmethod
    def fetch(self, url: str, session, **kwargs) -> list[dict]:
        """抓取并解析，返回教师/专业记录列表。"""

    @abstractmethod
    def parse(self, html: str, selectors: dict, **kwargs) -> list[dict]:
        """解析 HTML/JSON，返回记录列表。"""
```

## 4. 现有代码分析

### 4.1 各 Spider 模块现状

| 模块 | 核心函数 | 类型 | 行数 |
|---|---|---|---|
| `static_list.py` | `fetch_faculty_list()` + `parse_faculty_html()` | Source A 静态 HTML | 149 |
| `ajax_api.py` | `fetch_faculty_via_api()` | Source A AJAX API | 141 |
| `yzw_api.py` | `YzwClient` 类 | Source B 研招网 | 285 |
| `detail_parser.py` | `fetch_detail()` | Source A 详情页 | 290 |
| `js_render.py` | JS 渲染（Playwright） | Source A JS 页面 | 130 |
| `pdf_list.py` | PDF 师资名单解析 | Source A PDF | 282 |

### 4.2 当前调用链

```
main.py::run_source_a()
  → spiders.static_list.fetch_faculty_list(session, url, selectors, cache, force)
  → spiders.ajax_api.fetch_faculty_via_api(session, url, site_id, ...)
  → spiders.detail_parser.fetch_detail(session, url, selectors, cache, force)

main.py::run_source_b()
  → spiders.yzw_api.YzwClient(session, cache)
    → client.get_school_code(university)
    → client.fetch_major_directory(school_code, year, ...)
```

### 4.3 各模块的函数签名

**`static_list.py`**:
```python
def fetch_faculty_list(session, list_url, selectors, base_url=None, cache=None, force=False) -> list[dict]
def parse_faculty_html(soup, selectors, base_url) -> list[dict]
```

**`ajax_api.py`**:
```python
def fetch_faculty_via_api(session, api_url, site_id, referer, extra_params, cache=None, force=False) -> list[dict]
```

**`yzw_api.py`**:
```python
class YzwClient:
    def __init__(self, session, cache=None)
    def get_school_code(self, university) -> Optional[str]
    def fetch_major_directory(self, school_code, year, major_codes, category, university) -> List[Dict]
```

**`detail_parser.py`**:
```python
def fetch_detail(session, profile_url, detail_type="auto", selectors=None, cache=None, force=False) -> dict
```

## 5. 实施步骤

### Step 1：创建 `spiders/engine.py`

```python
"""爬虫引擎抽象基类。"""
from abc import ABC, abstractmethod
from typing import Optional

from utils.http import PoliteSession
from utils.cache import CrawlCache


class SpiderEngine(ABC):
    """所有爬虫引擎的基类。"""

    name: str = ""
    supported_source: str = ""  # "source_a" / "source_b"

    def __init__(self, session: PoliteSession, cache: Optional[CrawlCache] = None):
        self.session = session
        self.cache = cache

    @abstractmethod
    def fetch(self, url: str, **kwargs) -> list[dict]:
        """抓取数据。kwargs 传递引擎特定参数。"""

    @abstractmethod
    def parse(self, html: str, selectors: dict, **kwargs) -> list[dict]:
        """解析 HTML/JSON 为记录列表。"""

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"


# 引擎注册表
ENGINE_REGISTRY: dict[str, type[SpiderEngine]] = {}


def register_engine(cls: type[SpiderEngine]) -> type[SpiderEngine]:
    """注册引擎到全局注册表。"""
    ENGINE_REGISTRY[cls.name] = cls
    return cls
```

### Step 2：改造 `spiders/static_list.py`

```python
@register_engine
class StaticListEngine(SpiderEngine):
    name = "static_list"
    supported_source = "source_a"

    def fetch(self, url: str, *, selectors: dict, base_url=None, force=False, **kwargs) -> list[dict]:
        """抓取静态师资列表页。"""
        # 内部调用现有 fetch_faculty_list() 逻辑
        ...

    def parse(self, html: str, selectors: dict, *, base_url="", **kwargs) -> list[dict]:
        """解析 HTML 教师列表。"""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        return parse_faculty_html(soup, selectors, base_url)


# 旧接口兼容
def fetch_faculty_list(session, list_url, selectors, base_url=None, cache=None, force=False):
    engine = StaticListEngine(session, cache)
    return engine.fetch(list_url, selectors=selectors, base_url=base_url, force=force)
```

### Step 3：改造 `spiders/ajax_api.py`

```python
@register_engine
class AjaxApiEngine(SpiderEngine):
    name = "ajax_api"
    supported_source = "source_a"

    def fetch(self, url: str, *, site_id, referer, extra_params, force=False, **kwargs) -> list[dict]:
        """抓取 AJAX API 师资数据。"""
        ...

    def parse(self, html: str, selectors: dict, **kwargs) -> list[dict]:
        """AJAX 返回的是 JSON，直接解析。"""
        ...


# 旧接口兼容
def fetch_faculty_via_api(session, api_url, site_id, referer, extra_params, cache=None, force=False):
    engine = AjaxApiEngine(session, cache)
    return engine.fetch(api_url, site_id=site_id, referer=referer, extra_params=extra_params, force=force)
```

### Step 4：改造 `spiders/yzw_api.py`

```python
@register_engine
class YzwEngine(SpiderEngine):
    name = "yzw_api"
    supported_source = "source_b"

    def __init__(self, session, cache=None):
        super().__init__(session, cache)
        self._client = YzwClient(session, cache)

    def fetch(self, url: str = "", *, school_code, year, major_codes=None, category=None, university=None, **kwargs) -> list[dict]:
        """抓取研招网专业目录。"""
        return self._client.fetch_major_directory(school_code, year, major_codes, category, university)

    def parse(self, html: str, selectors: dict, **kwargs) -> list[dict]:
        """研招网数据由 parsers.yzw_major.parse() 处理，此处为空实现。"""
        return []


# YzwClient 类保持不变，YzwEngine 只是封装
```

### Step 5：改造 `spiders/detail_parser.py`

```python
@register_engine
class DetailParserEngine(SpiderEngine):
    name = "detail_parser"
    supported_source = "source_a"

    def fetch(self, url: str, *, detail_type="auto", selectors=None, force=False, **kwargs) -> list[dict]:
        """抓取教师详情页。返回单条记录的列表。"""
        detail = fetch_detail(self.session, url, detail_type, selectors, cache=self.cache, force=force)
        return [detail] if detail else []

    def parse(self, html: str, selectors: dict, **kwargs) -> list[dict]:
        """解析详情页 HTML。"""
        ...


# 旧接口兼容
def fetch_detail(session, profile_url, detail_type="auto", selectors=None, cache=None, force=False):
    # 保持原有实现不变
    ...
```

### Step 6：改造 `spiders/js_render.py` 和 `spiders/pdf_list.py`

同样的模式：创建 Engine 子类，保留旧函数作为兼容层。

### Step 7：在 `spiders/__init__.py` 导出注册表

```python
from .engine import SpiderEngine, ENGINE_REGISTRY, register_engine

__all__ = ["SpiderEngine", "ENGINE_REGISTRY", "register_engine"]
```

## 6. 同步点

| 依赖 | 接口 | 说明 |
|---|---|---|
| Agent A | `main.py` 调用 `fetch_faculty_list()` 等 | C 保留旧函数名，A 不受影响 |
| Agent E | `utils/http.py` 的 `PoliteSession` | C 只使用，不修改 |
| Agent F | 测试覆盖 | F 按 `SpiderEngine` 接口写测试 |

## 7. 验收命令

```bash
# 1. 抽象基类导入
python -c "from spiders.engine import SpiderEngine; print('OK')"

# 2. 注册表检查
python -c "
from spiders import ENGINE_REGISTRY
print('已注册引擎:', sorted(ENGINE_REGISTRY.keys()))
assert 'static_list' in ENGINE_REGISTRY
assert 'ajax_api' in ENGINE_REGISTRY
assert 'yzw_api' in ENGINE_REGISTRY
print('OK')
"

# 3. 旧接口兼容
pytest tests/test_spiders_static.py -q
pytest tests/test_spiders_ajax.py -q
pytest tests/test_spiders_detail.py -q

# 4. 新接口测试
pytest tests/test_engine_abstraction.py -q
```

## 8. 注意事项

1. **旧函数名必须保留**：`fetch_faculty_list()`、`fetch_faculty_via_api()`、`fetch_detail()` 等继续导出
2. **`YzwClient` 类不删除**：`YzwEngine` 内部组合 `YzwClient`，而非继承
3. **`ENGINE_REGISTRY` 用装饰器自动注册**：避免手动维护
4. **不改 `main.py` 和 `api/server.py`**：Agent A 的服务层后续可切换到 Engine
5. **`parse()` 的默认实现**：对于纯 fetcher（如 yzw_api），`parse()` 可返回空列表
