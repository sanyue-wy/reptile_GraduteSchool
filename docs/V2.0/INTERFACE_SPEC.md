# 模块接口规范文档

> **核心原则**：所有模块间通信仅通过**文件系统（JSONL/JSON）**和**标准 Python 函数签名**，禁止直接 import 业务逻辑、禁止共享可变全局状态。接口一旦确定，**不得随意变更**，新增字段必须向后兼容。

---

## 1. 统一数据 Schema（v1 定稿）

### 1.1 导师基础记录（Source A 产出 / Source B 部分产出 / 合并后最终形态）

```python
# 文件：schemas/tutor_v1.py （建议单独维护，所有模块 from schemas.tutor_v1 import TutorRecord）
from typing import TypedDict, Literal, Optional, List

class EnrollmentDirection(TypedDict):
    code: str                    # 专业代码，如 "085501"
    name: str                    # 专业名称，如 "机械工程"
    research_direction: str      # 研究方向（研招网 yjfxmc），可为空

class EnrollmentData(TypedDict):
    in_roster: bool              # 是否在招生名单中
    degree_types: List[str]      # ["学术型硕士", "专业型硕士", "博士"]
    directions: List[EnrollmentDirection]
    planned_count: Optional[int] # 拟招生人数
    exam_subjects: List[str]     # 考试科目列表
    source_url: str              # 来源 URL（研招网详情页 / 公示页）
    notice_year: int             # 数据年份

class RawRef(TypedDict):
    faculty: str                 # data/raw/.../faculty_xxx.html
    notice: str                  # data/raw/.../notice_xxx.json

class SourceType(TypedDict):
    faculty: str                 # "官网师资页" / ""
    notice: str                  # "研招网专业目录" / "研究生院公示" / ""

class TutorRecord(TypedDict):
    schema_version: Literal[1]
    name: str                    # 姓名（归一化后）
    university: str              # 学校标准名
    college: str                 # 学院标准名
    category: Literal["mechanical", "automation"]
    title: str                   # 职称：教授/副教授/讲师/研究员/助理研究员
    advisor_level: str           # "博导" / "硕导" / "博导/硕导" / ""
    email: str                   # 邮箱
    profile_url: str             # 个人主页 URL
    research_areas: List[str]    # 研究方向列表（来自官网详情页）
    enrollment: Optional[EnrollmentData]  # 仅 Source B 有数据时非空
    match_status: Literal["merged", "partial_faculty", "partial_notice"]
    raw_ref: RawRef
    source_type: SourceType
```

### 1.2 中间态文件 Schema（各 Source 产出，供合并管道读取）

**Source A 产出：`{university}_{college}_faculty.jsonl`**
```json
{
  "name": "张三",
  "university": "东南大学",
  "college": "机械工程学院",
  "category": "mechanical",
  "title": "教授",
  "advisor_level": "博导/硕导",
  "email": "zhangsan@seu.edu.cn",
  "profile_url": "http://me.seu.edu.cn/xxx",
  "research_areas": ["智能制造", "机器人学"],
  "raw_ref": "data/raw/东南大学/me.seu.edu.cn/20260914_list.html",
  "source_type": "官网师资页"
}
```

**Source B 产出：`{university}_{college}_notice.jsonl`**
```json
{
  "name": "张三",
  "university": "东南大学",
  "college": "机械工程学院",
  "category": "mechanical",
  "title": "",
  "advisor_level": "",
  "email": "",
  "profile_url": "",
  "research_areas": [],
  "enrollment": {
    "in_roster": true,
    "degree_types": ["学术型硕士", "博士"],
    "directions": [{"code": "085501", "name": "机械工程", "research_direction": "智能制造"}],
    "planned_count": 3,
    "exam_subjects": ["101 政治", "201 英语一", "301 数学一", "801 机械原理"],
    "source_url": "https://yz.chsi.com.cn/zsml/...",
    "notice_year": 2026
  },
  "raw_ref": "data/raw/东南大学/2026/yzw/major_085501.json",
  "source_type": "研招网专业目录"
}
```

---

## 2. 文件系统契约（数据流转标准）

| 阶段 | 文件路径 | 产出方 | 消费方 | 格式 |
|------|----------|--------|--------|------|
| 原件落盘 | `data/raw/{domain}/{timestamp}_{tail}.html\|.json` | `utils/http.py:PoliteSession` | 所有 Spider/Parser | 原始响应 |
| 页面缓存 | `data/cache/{domain}/{tail}.html\|.json` | `utils/cache.py:CrawlCache` | 所有 Spider | 缓存文本 |
| Source A 中间态 | `data/output/{uni}_{college}_faculty.jsonl` | `spiders/*` → `main.py` | `pipelines/merge.py` | JSONL |
| Source B 中间态 | `data/output/{uni}_{college}_notice.jsonl` | `spiders/yzw_api.py` + `parsers/yzw_major.py` | `pipelines/merge.py` | JSONL |
| 合并结果 | `data/output/{uni}_{college}.jsonl` | `pipelines/merge.py` | `pipelines/export.py`、API | JSONL |
| 全量汇总 | `data/output/summary.xlsx` | `pipelines/export.py` | 前端导出、人工查阅 | Excel |
| 失败记录 | `data/output/failures.json` | `main.py`、API | `main.py --retry-failed`、前端 | JSON |
| 进度追踪 | `data/output/progress.json` | `utils/progress.py` | CLI、API、Dashboard | JSON |

> **约定**：所有 JSONL 文件**逐行完整 JSON**，UTF-8 编码，无 BOM。目录不存在时由写入方 `mkdir(parents=True, exist_ok=True)`。

---

## 3. 函数接口契约（Python 签名标准）

### 3.1 Spider 层（列表页 → 教师基础信息列表）

```python
# 统一签名：所有列表页爬虫必须实现
def fetch_faculty_list(
    session: PoliteSession,
    list_url: str,
    selectors: dict,                    # 见下方选择器规范
    base_url: Optional[str] = None,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> List[dict]:
    """
    返回：[{"name": str, "profile_url": str, "research_areas_raw": str, "research_areas": List[str], ...}, ...]
    必含字段：name, profile_url
    选填：research_areas, title, advisor_level 等列表页可直接获得的字段
    """

# AJAX API 模式（SudyCMS/WebPlus）
def fetch_faculty_via_api(
    session: PoliteSession,
    api_url: str,
    site_id: str,
    referer: str,
    extra_params: Optional[dict] = None,
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> List[dict]:
    """
    返回：[{"name": str, "title": str, "degree": str, "advisor_tags_raw": str, "advisor_level": str, "profile_url": str, "photo_url": str}, ...]
    必含字段：name, profile_url, advisor_level
    """
```

### 3.2 Detail Parser 层（详情页 → 完整字段）

```python
def fetch_detail(
    session: PoliteSession,
    profile_url: str,
    detail_type: str = "auto",          # "me" | "auto_type" | "generic" | "auto"
    selectors: Optional[dict] = None,   # 覆盖默认选择器
    cache: Optional[CrawlCache] = None,
    force: bool = False,
) -> dict:
    """
    返回：完整字段字典
    必含：name, profile_url
    选含：title, advisor_level, email, research_areas, sections, degree, phone, office, department...
    约定：不抛出异常，解析失败字段置空，记录 warning 日志
    """
```

### 3.3 Parser 插件层（公示/专业目录原件 → 统一记录）

```python
# 所有 parser 必须实现此签名（注册表模式）
def parse(raw_path: str, meta: dict) -> List[dict]:
    """
    Args:
        raw_path: 原件文件绝对路径
        meta: {
            "university": str,
            "college": str,
            "category": "mechanical" | "automation",
            "year": int,
            "school_code": str,         # 研招网学校代码（Source B 用）
            "template": str,            # 配置中指定的模板名
        }
    Returns:
        List[TutorRecord]  # 符合 1.1 Schema 的记录列表
    """
```

### 3.4 合并管道

```python
def merge_sources(
    faculty_path: str,          # Source A 中间态路径（可为空串）
    notice_path: str,           # Source B 中间态路径（可为空串）
    output_path: str,           # 合并结果输出路径
    fuzzy_threshold: float = 0.85,
) -> dict:
    """
    返回统计摘要：{"total": N, "merged": N, "partial_faculty": N, "partial_notice": N}
    同时写出 output_path（JSONL，每行 TutorRecord）
    """
```

### 3.5 导出管道

```python
def export_merged(merged_records: List[dict], output_dir: Path) -> dict:
    """按学校+学院分组写出 JSONL，返回 {"files_written": N, "total_records": M}"""

def export_summary(merged_records: List[dict], output_path: Path) -> int:
    """生成 summary.xlsx，返回行数"""

def export_failures(failures: List[dict], output_path: Path) -> int:
    """写出 failures.json，返回记录数"""
```

### 3.6 进度追踪

```python
class ProgressTracker:
    def get_school_status(self, university: str, college: str) -> dict:
        """返回 {"source_a": status, "source_b": status, "merged": status, "tutor_count": int, "last_crawl_at": str}"""
    
    def update_school_status(self, university: str, college: str, **kwargs) -> None:
        """kwargs 可含：source_a, source_b, merged, tutor_count"""
    
    def get_overview_stats(self) -> dict:
        """返回首页统计卡片数据"""
    
    def add_log(self, level: str, msg: str) -> None:
        """追加运行日志到 crawl.log"""
```

---

## 4. 配置数据结构契约（`config/schools.py`）

```python
# 单校配置标准结构
{
    "university": "东南大学",                    # 必填，标准校名
    "level": "985/211/双一流",                 # 选填，自动从 school_level_raw 推导
    "categories": [
        {
            "college": "机械工程学院",           # 必填，学院标准名
            "category": "mechanical",            # 必填，"mechanical" | "automation"
            "faculty": {                         # Source A 配置
                "list_url": "http://me.seu.edu.cn/xscz/list.htm",
                "list_type": "static_html",      # "static_html" | "ajax_api"
                "list_item_selector": "li > a[title=姓名]",
                "list_research_selector": ".research",
                "detail_selectors": {
                    "name": ".carrer .jsbt",
                    "title": ".carrer .title",
                    "email_re": "邮箱:([^\\s<]+)"
                },
                # ajax_api 专用
                "api_params": {
                    "siteId": "338",
                    "rows": "999"
                },
                "referer": "https://automation.seu.edu.cn/32668/list.htm"
            },
            "notice": {                          # Source B/C 配置
                "enabled": true,
                "entry_url": "https://yz.chsi.com.cn/zsml/",
                "school_code": "10213",          # 研招网学校代码
                "major_codes": {                 # 专业代码白名单（可选）
                    "mechanical": ["085501", "085502"],
                    "automation": ["085400", "081100"]
                },
                "title_pattern": r"(硕士|博士).*(导师|指导教师).*名单",
                "template": "yzw_major"          # parser 模板名
            }
        }
    ]
}
```

---

## 5. API 接口契约（前后端分离标准）

所有接口统一响应格式：

```json
// 成功
{ "code": 0, "data": {...} }

// 失败
{ "code": 40001, "message": "错误描述", "detail": "可选详情" }
```

| 错误码范围 | 含义 |
|------------|------|
| 0 | 成功 |
| 40001-40099 | 参数校验错误 |
| 40401-40499 | 资源不存在 |
| 40901 | 任务冲突（重复采集） |
| 50001-50099 | 服务器内部错误 |

**核心端点**（前端仅依赖这些）：

| 端点 | 方法 | 用途 | 关键参数 |
|------|------|------|----------|
| `/api/overview` | GET | 总览面板数据 | 无 |
| `/api/schools` | GET | 学校列表（分页/筛选） | q, status, category, page, page_size |
| `/api/schools/{id}` | GET | 单校详情 | - |
| `/api/crawl` | POST | 触发采集任务 | schools[], categories[], sources[], force, year |
| `/api/tasks/{task_id}` | GET | 任务进度轮询 | - |
| `/api/tutors` | GET | 导师列表（分页/筛选） | q, school, college, level, match, page, page_size |
| `/api/tutors/{school}/{name}` | GET | 导师详情 | - |
| `/api/tutors/export` | GET | 导出数据 | format=excel\|json, school, college |
| `/api/failures` | GET | 失败记录 | status, source, page, page_size |
| `/api/failures/retry` | POST | 重试失败项 | failure_ids[], retry_all |
| `/api/failures/{id}/ignore` | POST | 忽略失败项 | - |
| `/api/raw/{path}` | GET | 查看原件 | path (相对 data/raw) |
| `/api/config` | GET | 获取全量配置 | - |
| `/api/config/schools/{name}` | PUT | 保存单校配置 | 完整校配置对象 |
| `/api/config/global` | PUT | 保存全局配置 | 全局配置对象 |
| `/api/config/test` | POST | 测试连接 | url, method, headers |
| `/api/config/import` | POST | 导入配置文件 | file (multipart) |
| `/api/config/export` | GET | 导出配置文件 | - |

---

## 6. 异常处理契约

| 层级 | 策略 |
|------|------|
| **Spider/Parser** | 捕获所有异常，记录 `logger.warning/error`，返回**部分结果**（不抛出），失败记录由调用方写入 `failures.json` |
| **主流程 (`main.py`)** | 捕获 `BlockedError`/`MaxRetriesExceeded`/通用 `Exception`，统一生成失败记录，更新进度为 `failed`，**不中断其他任务** |
| **API 层** | Flask `@app.errorhandler` 统一包装为标准错误响应，记录完整堆栈到日志 |
| **前端** | `fetch` 统一拦截 `code != 0`，Toast 提示 `message`，`detail` 可选展开 |

---

## 7. 并发与线程安全契约

| 共享资源 | 保护机制 | 使用方 |
|----------|----------|--------|
| `progress.json` | `threading.Lock` + 原子写临时文件 rename | `ProgressTracker` 单例 |
| `failures.json` | `threading.Lock` + 原子写 | `export_failures` 等函数 |
| `CrawlCache` 写入 | 文件级 `os.replace` 原子替换 + `inflight` 去重 | `CrawlCache` 内部 |
| `PoliteSession` 请求 | 实例不共享，**每线程各自创建** | `main.py` 线程池每 worker 独立实例 |

---

## 8. 版本演进规则

1. **Schema 版本号** 在 `TutorRecord.schema_version` 中体现，升级时**必须**提供向后兼容读取逻辑
2. **配置结构** 新增字段默认可选，旧配置无需修改即可运行
3. **API 接口** 新增字段只加不减，`code`/`message` 语义不变
4. **文件路径** 格式不变，仅在 `data/raw/` 下新增子目录

---

## 9. 接口验收清单（开发前自检）

- [ ] 所有 Spider 实现 `fetch_faculty_list` / `fetch_faculty_via_api` 标准签名
- [ ] `fetch_detail` 支持 `detail_type="auto"` 自动检测模板
- [ ] 所有 Parser 实现 `parse(raw_path, meta) -> List[dict]` 标准签名
- [ ] `merge_sources` 能处理任意一方为空的情况
- [ ] 导出函数不依赖全局状态，纯函数式
- [ ] 配置结构与 `INTERFACE_SPEC.md` 4 节完全一致
- [ ] API 响应格式符合 `code`/`data`/`message`/`detail` 标准
- [ ] 无循环 import（`spiders/` 不 import `pipelines/`，`parsers/` 不 import `spiders/` 等）

---

> **此文档为接口基线，后续所有模块开发必须严格遵守。如需变更，需在本文档更新并同步通知所有相关模块负责人。**