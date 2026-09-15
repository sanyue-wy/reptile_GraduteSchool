# 模块五：测试体系与工程化实施指南

> **模块定位**：独立可并行开发｜**依赖接口**：`INTERFACE_SPEC.md` 全文｜**贯穿所有模块开发周期**

---

## 1. 模块目标

为整个项目建立**完整的测试体系和工程化基础**，确保各模块并行开发后能顺利集成。

| 维度 | 现状 | 目标 |
|------|------|------|
| 单元测试 | 无 | 各模块核心函数 ≥80% 行覆盖率 |
| 集成测试 | 无 | Source A → 合并 → 导出 端到端跑通 |
| Mock 体系 | 无 | HTTP 响应、文件系统、配置均可 Mock |
| CI/CD | 无 | `pytest` 一键运行，Lint 检查 |
| 日志规范 | 散乱 print | 统一 logging，分级输出 |
| 错误追踪 | 无 | `failures.json` 结构化记录 |

---

## 2. 测试目录结构

```
tests/
├── __init__.py
├── conftest.py                  # 全局 fixtures（session、tmp_dir、mock_data）
├── fixtures/                    # 测试数据文件
│   ├── html/
│   │   ├── faculty_list_static.html    # 静态列表页 Mock
│   │   ├── faculty_list_ajax.json      # AJAX 列表页 Mock
│   │   └── detail_me.html              # 详情页 Mock（模板 me）
│   ├── json/
│   │   ├── yzw_major_sample.json       # 研招网专业目录 Mock
│   │   └── progress_sample.json        # 进度文件 Mock
│   └── config/
│       └── test_schools.json           # 测试用配置
│
├── test_spiders_static.py       # spiders/static_list.py 单测
├── test_spiders_ajax.py         # spiders/ajax_api.py 单测
├── test_spiders_detail.py       # spiders/detail_parser.py 单测
├── test_yzw.py                  # spiders/yzw_api.py + parsers/yzw_major.py 单测
├── test_parsers.py              # parsers/__init__.py 注册表 + dispatch 单测
├── test_config.py               # config/ 全模块单测
├── test_merge.py                # pipelines/merge.py 单测
├── test_export.py               # pipelines/export.py 单测
├── test_http.py                 # utils/http.py 单测
├── test_cache.py                # utils/cache.py 单测
├── test_progress.py             # utils/progress.py 单测
├── test_api.py                  # api/server.py 集成测试
└── test_integration.py          # 端到端集成测试
```

---

## 3. 全局 Fixtures（`tests/conftest.py`）

```python
# 文件：tests/conftest.py
import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def tmp_dir():
    """临时目录，测试结束自动清理"""
    d = tempfile.mkdtemp()
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def mock_session():
    """Mock PoliteSession，不发起真实 HTTP 请求"""
    session = MagicMock()
    session.get.return_value = MagicMock(
        status_code=200,
        text="<html></html>",
        content=b"<html></html>",
        headers={"Content-Type": "text/html"},
        url="http://test.edu.cn",
        encoding="utf-8",
    )
    session.post.return_value = MagicMock(
        status_code=200,
        text='{"data": []}',
        content=b'{"data": []}',
        headers={"Content-Type": "application/json"},
        url="http://test.edu.cn/api",
        json=lambda: {"data": []},
    )
    session.save_raw.return_value = "/tmp/test_raw.html"
    return session


@pytest.fixture
def mock_cache(tmp_dir):
    """测试用 CrawlCache，指向临时目录"""
    from utils.cache import CrawlCache
    return CrawlCache(cache_dir=str(tmp_dir / "cache"), max_age_days=7)


@pytest.fixture
def mock_progress(tmp_dir):
    """测试用 ProgressTracker，指向临时目录"""
    from utils.progress import ProgressTracker
    return ProgressTracker(data_dir=str(tmp_dir / "output"))


@pytest.fixture
def sample_config():
    """单校测试配置"""
    return {
        "university": "测试大学",
        "level": "985",
        "categories": [
            {
                "college": "机械工程学院",
                "category": "mechanical",
                "faculty": {
                    "list_url": "http://test.edu.cn/faculty",
                    "list_type": "static_html",
                    "list_item_selector": "li a",
                    "list_research_selector": "p.desc",
                    "detail_selectors": {
                        "name": ".name",
                        "title": ".title",
                        "email_re": r"[\w.]+@[\w.]+",
                    },
                    "api_params": {},
                    "referer": "",
                },
                "notice": {
                    "enabled": True,
                    "entry_url": "https://yz.chsi.com.cn/zsml/",
                    "school_code": "99999",
                    "major_codes": {},
                    "title_pattern": "",
                    "template": "yzw_major",
                },
            }
        ],
    }


@pytest.fixture
def sample_faculty_html():
    """Mock 师资列表页 HTML"""
    return """
    <html><body>
    <ul class="faculty-list">
        <li><a href="/teacher/1">张三</a><p class="desc">研究方向：智能制造</p></li>
        <li><a href="/teacher/2">李四</a><p class="desc">研究方向：机器人学</p></li>
        <li><a href="/teacher/3">王五</a><p class="desc">研究方向：自动化控制</p></li>
    </ul>
    </body></html>
    """


@pytest.fixture
def sample_yzw_json():
    """Mock 研招网专业目录 JSON"""
    return {
        "total": 2,
        "data": [
            {
                "dwmc": "测试大学",
                "dwdm": "99999",
                "zymc": "机械工程",
                "zydm": "085501",
                "yjfxmc": "智能制造",
                "zdjs": "张三 李四",
                "xxfs": "1",
                "nzsrsstr": "3",
                "kskm": "101 政治 201 英语一 301 数学一 801 机械原理",
            },
            {
                "dwmc": "测试大学",
                "dwdm": "99999",
                "zymc": "车辆工程",
                "zydm": "085502",
                "yjfxmc": "新能源汽车",
                "zdjs": "王五",
                "xxfs": "1",
                "nzsrsstr": "2",
                "kskm": "101 政治 201 英语一 301 数学一 802 汽车理论",
            },
        ],
    }
```

---

## 4. 各模块单测规范

### 4.1 HTTP 工具（`tests/test_http.py`）

```python
class TestPoliteSession:
    def test_rate_limiting(self):
        """两次请求间隔不低于 min_delay"""
        ...
    
    def test_ua_rotation(self):
        """连续请求 User-Agent 不同"""
        ...
    
    def test_retry_on_500(self, mock_session):
        """500 错误自动重试 max_retries 次"""
        ...
    
    def test_blocked_cooldown(self):
        """403/429 触发冷却期"""
        ...
    
    def test_save_raw(self, tmp_dir):
        """原始响应正确落盘"""
        ...
```

### 4.2 缓存（`tests/test_cache.py`）

```python
class TestCrawlCache:
    def test_cache_hit(self, mock_cache):
        """缓存命中返回原始内容"""
        ...
    
    def test_cache_miss(self, mock_cache):
        """缓存未命中返回 None"""
        ...
    
    def test_cache_expired(self, mock_cache):
        """过期缓存视为 miss"""
        ...
    
    def test_inflight_dedup(self, mock_cache):
        """并发相同 URL 只发出一次请求"""
        ...
    
    def test_thread_safety(self, mock_cache):
        """多线程并发写入无数据损坏"""
        ...
```

### 4.3 进度追踪（`tests/test_progress.py`）

```python
class TestProgressTracker:
    def test_update_and_get(self, mock_progress):
        """更新状态后能正确读取"""
        ...
    
    def test_atomic_write(self, mock_progress):
        """写入过程中断不会损坏文件"""
        ...
    
    def test_overview_stats(self, mock_progress):
        """统计概览数据正确"""
        ...
    
    def test_concurrent_update(self, mock_progress):
        """多线程并发更新无数据竞争"""
        ...
```

### 4.4 合并管道（`tests/test_merge.py`）

```python
class TestMergeSources:
    def test_exact_name_match(self, tmp_dir):
        """姓名完全匹配正确合并"""
        ...
    
    def test_fuzzy_name_match(self, tmp_dir):
        """姓名近似匹配（difflib ≥0.85）正确合并"""
        ...
    
    def test_whitespace_normalize(self, tmp_dir):
        """姓名含全角空格等正确归一化匹配"""
        ...
    
    def test_only_faculty(self, tmp_dir):
        """仅有 Source A 时，全部标记 partial_faculty"""
        ...
    
    def test_only_notice(self, tmp_dir):
        """仅有 Source B 时，全部标记 partial_notice"""
        ...
    
    def test_empty_files(self, tmp_dir):
        """两个空文件输入不报错"""
        ...
    
    def test_statistics(self, tmp_dir):
        """返回统计摘要含 total/merged/partial_faculty/partial_notice"""
        ...
```

### 4.5 导出管道（`tests/test_export.py`）

```python
class TestExport:
    def test_export_merged_jsonl(self, tmp_dir):
        """输出 JSONL 每行可解析，字段完整"""
        ...
    
    def test_export_summary_excel(self, tmp_dir):
        """summary.xlsx 可打开，含正确列头和数据行"""
        ...
    
    def test_export_failures_json(self, tmp_dir):
        """failures.json 可解析，结构符合规范"""
        ...
```

### 4.6 API 集成测试（`tests/test_api.py`）

```python
import pytest
from api.server import app

@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

class TestApiOverview:
    def test_overview_success(self, client):
        resp = client.get("/api/overview")
        data = resp.get_json()
        assert data["code"] == 0
        assert "total_schools" in data["data"]
    
    def test_overview_has_all_fields(self, client):
        data = client.get("/api/overview").get_json()["data"]
        required = ["total_schools", "total_tutors", "matched_count", "failures_count"]
        for field in required:
            assert field in data, f"缺少字段: {field}"

class TestApiSchools:
    def test_list_schools(self, client):
        resp = client.get("/api/schools")
        data = resp.get_json()
        assert data["code"] == 0
        assert "items" in data["data"]
    
    def test_filter_by_category(self, client):
        resp = client.get("/api/schools?category=mechanical")
        data = resp.get_json()
        assert data["code"] == 0
    
    def test_pagination(self, client):
        resp = client.get("/api/schools?page=1&page_size=5")
        data = resp.get_json()
        assert data["code"] == 0
        assert len(data["data"]["items"]) <= 5

class TestApiTutors:
    def test_list_tutors(self, client):
        resp = client.get("/api/tutors")
        data = resp.get_json()
        assert data["code"] == 0

class TestApiFailures:
    def test_list_failures(self, client):
        resp = client.get("/api/failures")
        data = resp.get_json()
        assert data["code"] == 0

class TestApiConfig:
    def test_get_config(self, client):
        resp = client.get("/api/config")
        data = resp.get_json()
        assert data["code"] == 0
        assert "schools" in data["data"]
    
    def test_save_school_config(self, client):
        cfg = {"university": "测试", "categories": []}
        resp = client.put("/api/config/schools/测试大学", json=cfg)
        assert resp.get_json()["code"] in (0, 40001)  # 通过或校验失败

class TestErrorHandling:
    def test_404_endpoint(self, client):
        resp = client.get("/api/nonexistent")
        assert resp.status_code == 404
    
    def test_error_response_format(self, client):
        """错误响应包含 code 和 message"""
        resp = client.get("/api/schools/不存在的大学999")
        data = resp.get_json()
        assert "code" in data
        assert "message" in data
```

---

## 5. 端到端集成测试（`tests/test_integration.py`）

```python
class TestEndToEnd:
    """
    集成测试：使用 Mock HTTP，验证完整数据流。
    不依赖真实网络，CI 环境可运行。
    """
    
    def test_source_a_pipeline(self, tmp_dir, mock_session, sample_config, sample_faculty_html):
        """
        Source A 完整流程：
        抓取列表 → 详情页解析 → 写入 _faculty.jsonl
        """
        # 1. Mock HTTP 响应
        mock_session.get.return_value.text = sample_faculty_html
        
        # 2. 调用静态列表爬虫
        from spiders.static_list import fetch_faculty_list
        tutors = fetch_faculty_list(
            session=mock_session,
            list_url="http://test.edu.cn/faculty",
            selectors=sample_config["categories"][0]["faculty"],
        )
        assert len(tutors) > 0
        
        # 3. 写入 JSONL
        import json
        output_path = tmp_dir / "测试大学_机械工程学院_faculty.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for t in tutors:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        
        # 4. 验证文件可读
        with open(output_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == len(tutors)
    
    def test_merge_pipeline(self, tmp_dir):
        """
        合并管道完整流程：
        读取 _faculty.jsonl + _notice.jsonl → 输出合并 .jsonl
        """
        import json
        
        # 构造 faculty 数据
        faculty_data = [
            {"name": "张三", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "教授", "advisor_level": "博导",
             "email": "z@test.edu.cn", "profile_url": "http://test.edu.cn/1",
             "research_areas": ["智能制造"], "raw_ref": "", "source_type": "官网师资页"},
            {"name": "李四", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "副教授", "advisor_level": "硕导",
             "email": "l@test.edu.cn", "profile_url": "http://test.edu.cn/2",
             "research_areas": ["机器人学"], "raw_ref": "", "source_type": "官网师资页"},
        ]
        
        # 构造 notice 数据（张三重名匹配，新名赵六）
        notice_data = [
            {"name": "张三", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "", "advisor_level": "",
             "email": "", "profile_url": "", "research_areas": [],
             "enrollment": {"in_roster": True, "directions": [{"code": "085501", "name": "机械工程"}],
                            "planned_count": 3, "exam_subjects": [], "source_url": "", "notice_year": 2026},
             "raw_ref": "", "source_type": "研招网专业目录"},
            {"name": "赵六", "university": "测试大学", "college": "机械学院",
             "category": "mechanical", "title": "", "advisor_level": "",
             "email": "", "profile_url": "", "research_areas": [],
             "enrollment": {"in_roster": True, "directions": [{"code": "085502", "name": "车辆工程"}],
                            "planned_count": 2, "exam_subjects": [], "source_url": "", "notice_year": 2026},
             "raw_ref": "", "source_type": "研招网专业目录"},
        ]
        
        # 写入中间态文件
        faculty_path = tmp_dir / "faculty.jsonl"
        notice_path = tmp_dir / "notice.jsonl"
        output_path = tmp_dir / "merged.jsonl"
        
        for path, data in [(faculty_path, faculty_data), (notice_path, notice_data)]:
            with open(path, "w", encoding="utf-8") as f:
                for d in data:
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
        
        # 调用合并
        from pipelines.merge import merge_sources
        stats = merge_sources(str(faculty_path), str(notice_path), str(output_path))
        
        # 验证
        assert stats["total"] == 3  # 张三(merged) + 李四(partial_faculty) + 赵六(partial_notice)
        assert stats["merged"] == 1
        assert stats["partial_faculty"] == 1
        assert stats["partial_notice"] == 1
        
        # 验证输出文件
        with open(output_path, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
        assert len(records) == 3
        assert any(r["name"] == "张三" and r["match_status"] == "merged" for r in records)
```

---

## 6. 日志规范

### 6.1 统一日志配置

```python
# 文件：utils/logging_config.py
import logging
import sys
from pathlib import Path

def setup_logging(level: str = "INFO", log_file: str = "data/output/crawl.log"):
    """
    统一日志配置。
    
    输出：
        - 控制台：INFO 及以上，简洁格式
        - 文件：DEBUG 及以上，含时间戳和模块名
    """
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 控制台
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper()))
    console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    
    # 文件
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(console)
    root.addHandler(file_handler)
    
    # 降低第三方库日志级别
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
```

### 6.2 各模块 logger 使用规范

```python
# 每个模块顶部
import logging
logger = logging.getLogger(__name__)

# 使用规范
logger.info("开始抓取 %s/%s", university, college)
logger.debug("响应状态码: %d, 耗时: %.2fs", resp.status_code, elapsed)
logger.warning("解析失败，跳过: %s, 原因: %s", url, str(e))
logger.error("严重错误，%s: %s", context, str(e))
```

---

## 7. 运行与 CI

### 7.1 pytest 配置（`pytest.ini`）

```ini
# 文件：pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short --strict-markers
markers =
    slow: 需要较长时间运行的测试
    integration: 集成测试（需完整环境）
```

### 7.2 运行命令

```bash
# 运行全部测试
pytest

# 只运行单元测试（排除集成）
pytest -m "not integration and not slow"

# 只运行集成测试
pytest -m integration

# 显示覆盖率
pytest --cov=. --cov-report=term-missing

# 运行特定模块测试
pytest tests/test_merge.py -v
pytest tests/test_config.py -v
```

### 7.3 requirements-dev.txt

```
# 文件：requirements-dev.txt
pytest>=7.4
pytest-cov>=4.1
black>=23.0
flake8>=6.0
isort>=5.12
mypy>=1.5
```

---

## 8. 代码质量工具

### 8.1 格式化与 Lint

```bash
# 格式化（black）
black . --line-length 120

# Import 排序（isort）
isort . --profile black

# Lint（flake8）
flake8 . --max-line-length 120 --ignore E501,W503

# 类型检查（mypy，可选）
mypy . --ignore-missing-imports
```

### 8.2 Pre-commit Hook（可选）

```yaml
# 文件：.pre-commit-config.yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
  - repo: https://github.com/pycqa/flake8
    rev: 6.1.0
    hooks:
      - id: flake8
```

---

## 9. 验收标准

| 检查项 | 通过标准 |
|--------|----------|
| 测试目录 | `tests/` 含上述全部测试文件，conftest.py 含全部 fixtures |
| 覆盖率 | 核心模块（spiders、parsers、pipelines、utils）行覆盖率 ≥80% |
| 全绿运行 | `pytest -m "not integration"` 全部通过 |
| 集成测试 | `pytest -m integration` 端到端跑通 |
| 日志规范 | 无 `print()` 调试输出，全部使用 `logging` |
| 代码格式 | `black --check .` 无格式差异 |
| 无副作用 | 测试不修改 `data/` 下真实数据，全部使用 tmp_dir |

---

## 10. 交付清单

- [ ] `tests/conftest.py`：全局 fixtures
- [ ] `tests/fixtures/`：Mock 数据文件
- [ ] `tests/test_http.py`：PoliteSession 单测
- [ ] `tests/test_cache.py`：CrawlCache 单测
- [ ] `tests/test_progress.py`：ProgressTracker 单测
- [ ] `tests/test_spiders_static.py`：静态列表爬虫单测
- [ ] `tests/test_spiders_ajax.py`：AJAX 爬虫单测
- [ ] `tests/test_spiders_detail.py`：详情页解析单测
- [ ] `tests/test_yzw.py`：研招网爬虫 + parser 单测
- [ ] `tests/test_parsers.py`：Parser 注册表单测
- [ ] `tests/test_config.py`：配置模块单测
- [ ] `tests/test_merge.py`：合并管道单测
- [ ] `tests/test_export.py`：导出管道单测
- [ ] `tests/test_api.py`：API 集成测试
- [ ] `tests/test_integration.py`：端到端集成测试
- [ ] `utils/logging_config.py`：统一日志配置
- [ ] `pytest.ini`：pytest 配置
- [ ] `requirements-dev.txt`：开发依赖
- [ ] `pytest` 运行全绿
