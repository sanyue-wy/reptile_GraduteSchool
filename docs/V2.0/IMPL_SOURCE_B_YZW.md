# Source B：研招网专业目录爬虫实施指南

> **模块定位**：独立可并行开发｜**依赖接口**：`INTERFACE_SPEC.md` 第 3.1、3.3、3.4、4 节｜**产出**：`data/output/{uni}_{college}_notice.jsonl`

---

## 1. 模块边界与职责

| 职责 | 归属文件 | 说明 |
|------|----------|------|
| HTTP 请求、限速、重试、缓存 | `utils/http.py` + `utils/cache.py` | **复用现有，不重写** |
| 研招网 API 参数构造、分页、学校代码查找 | `spiders/yzw_api.py` | **本模块核心** |
| 原件落盘（JSON） | `spiders/yzw_api.py` | 复用 `PoliteSession.save_raw` 逻辑 |
| 原件解析 → 统一 Schema | `parsers/yzw_major.py` | **本模块核心**，实现 `parse(raw_path, meta)` |
| 任务编排入口 | `main.py:run_source_b()` | 调用上述两文件，写入 `_notice.jsonl` |
| 合并管道 | `pipelines/merge.py` | **复用现有**，自动读取 `_notice.jsonl` |

> **严禁**：在 `yzw_api.py` 中 import `pipelines/`、`api/`、`main.py` 业务逻辑

---

## 2. 接口契约（必须严格遵守）

### 2.1 `spiders/yzw_api.py` 对外函数

```python
# 文件：spiders/yzw_api.py
from typing import Optional, List, Dict
from utils.http import PoliteSession
from utils.cache import CrawlCache

class YzwClient:
    BASE_URL = "https://yz.chsi.com.cn"
    
    def __init__(self, session: PoliteSession, cache: Optional[CrawlCache] = None):
        self.session = session
        self.cache = cache
        self._school_code_cache: Dict[str, str] = {}
    
    def get_school_code(self, university: str) -> Optional[str]:
        """查找研招网学校代码，优先读缓存，无则请求 /zsml/querySchAction.do"""
        ...
    
    def fetch_major_directory(
        self,
        school_code: str,
        year: int,
        major_codes: Optional[List[str]] = None,  # None 表示全专业
    ) -> List[Dict]:
        """
        抓取专业目录完整数据（含 zdjs 指导教师字段）。
        
        返回：研招网原始记录列表（每项含 dwmc, yjfxmc, zdjs, zydm, nzsrsstr, kskm 等字段）
        原件自动落盘至 data/raw/{university}/{year}/yzw/major_{school_code}.json
        """
        ...
```

### 2.2 `parsers/yzw_major.py` 对外函数

```python
# 文件：parsers/yzw_major.py
from typing import List, Dict

def parse(raw_path: str, meta: Dict) -> List[Dict]:
    """
    标准 Parser 接口（符合 INTERFACE_SPEC.md 3.3）。
    
    Args:
        raw_path: 原件 JSON 文件路径
        meta: {
            "university": str,
            "college": str,
            "category": "mechanical" | "automation",
            "year": int,
            "school_code": str,
            "template": "yzw_major"
        }
    
    Returns:
        List[Dict]  # 每项符合 INTERFACE_SPEC.md 1.1 TutorRecord Schema
        必含字段：name, university, college, category, enrollment, match_status="partial_notice", raw_ref, source_type
    """
    ...
```

### 2.3 `main.py:run_source_b()` 集成逻辑

```python
def run_source_b(task: CrawlTask, session: PoliteSession, progress: ProgressTracker) -> List[Dict]:
    # 1. 读取配置
    notice_cfg = task.config.get("notice", {})
    if not notice_cfg.get("enabled", False):
        return []
    
    # 2. 实例化客户端（复用现有缓存）
    from spiders.yzw_api import YzwClient
    from utils.cache import CrawlCache
    cache = CrawlCache(max_age_days=7)
    client = YzwClient(session, cache=cache)
    
    # 3. 获取学校代码（配置优先，无则自动查找）
    school_code = notice_cfg.get("school_code") or client.get_school_code(task.university)
    if not school_code:
        raise ValueError(f"无法获取 {task.university} 研招网学校代码")
    
    # 4. 抓取专业目录
    major_codes = notice_cfg.get("major_codes", {}).get(task.category, None)
    raw_records = client.fetch_major_directory(school_code, task.year, major_codes)
    
    # 5. 解析为统一 Schema
    from parsers.yzw_major import parse
    meta = {
        "university": task.university,
        "college": task.college,
        "category": task.category,
        "year": task.year,
        "school_code": school_code,
        "template": "yzw_major"
    }
    # 原件已在 fetch_major_directory 内落盘，此处直接传路径
    raw_path = f"data/raw/{task.university}/{task.year}/yzw/major_{school_code}.json"
    parsed = parse(raw_path, meta)
    
    # 6. 写入中间态文件（供合并管道读取）
    notice_path = Path(f"data/output/{task.university}_{task.college}_notice.jsonl")
    notice_path.parent.mkdir(parents=True, exist_ok=True)
    with open(notice_path, "w", encoding="utf-8") as f:
        for r in parsed:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    # 7. 更新进度
    progress.update_school_status(task.university, task.college, source_b="done")
    
    return parsed
```

---

## 3. 研招网 API 细节（实现参考）

### 3.1 核心端点

| 步骤 | 端点 | 方法 | 关键参数 | 说明 |
|------|------|------|----------|------|
| 1. 校代码查找 | `/zsml/querySchAction.do` | GET | `dwmc=学校名称` | 返回列表，匹配名称获取 `dwdm` |
| 2. 专业目录 | `/zsml/rs/dws.do` | POST | 见下表 | 核心数据源，含 `zdjs` |
| 3. 考试科目(可选) | `/zsml/kskm.do` | POST | `dwdm`, `zydm` | 补充 `exam_subjects` |

### 3.2 `/zsml/rs/dws.do` 请求参数

```python
params = {
    "dwmc": university,           # 学校名称
    "dwdm": school_code,          # 学校代码
    "mldm": "08",                 # 门类：08 工学
    "mlmc": "工学",
    "yjxkdm": "0855",             # 一级学科代码（按 category 映射）
    "zymc": "",                   # 专业名称（空=全专业）
    "xxfs": "1",                  # 学习方式：1全日制
    "tydxs": "",                  # 统考/推免（空=全部）
    "jsggjh": "",                 # 接收推免计划
    "start": 0,                   # 分页起始
    "pageSize": 500,              # 页大小
}
```

**一级学科映射**（配置化，建议写在 `config/major_mapping.py`）：

```python
MAJOR_MAPPING = {
    "mechanical": ["0855", "0802", "0824"],      # 机械、机械工程、兵器
    "automation": ["0854", "0811", "0839", "0810"],  # 电子信息、控制、网络空间、信息通信
}
```

### 3.3 响应结构（参考 `freecho/yzw/data/entity.py`）

```json
{
  "total": 123,
  "data": [
    {
      "dwmc": "东南大学",
      "dwdm": "10213",
      "ssdm": "32",
      "zymc": "机械工程",
      "zydm": "085501",
      "yjfxmc": "智能制造",
      "zdjs": "张三 李四 王五",           // 核心：指导教师姓名，空格/分号分隔
      "xxfs": "1",
      "nzsrsstr": "3",                   // 拟招生人数
      "kskm": "101 政治 201 英语一 301 数学一 801 机械原理",
      "jsggjh": "0"
    }
  ]
}
```

---

## 4. Parser 核心逻辑（`parsers/yzw_major.py`）

### 4.1 `zdjs` 字段拆分规则

```python
import re

def split_advisor_names(zdjs: str) -> List[str]:
    """拆分指导教师字段为姓名列表"""
    if not zdjs or zdjs in ("不区分导师", "请登录各学院网站查看", "--"):
        return []
    # 分隔符：空格、中英文分号、逗号、顿号
    names = re.split(r"[\s;；,，、]+", zdjs.strip())
    return [n.strip() for n in names if n.strip() and len(n.strip()) >= 2]
```

### 4.2 记录构造模板

```python
def build_tutor_record(name: str, raw_item: Dict, meta: Dict) -> Dict:
    """构造符合 TutorRecord Schema 的单条记录"""
    directions = [{
        "code": raw_item.get("zydm", ""),
        "name": raw_item.get("zymc", ""),
        "research_direction": raw_item.get("yjfxmc", "")
    }]
    
    # 考试科目拆分
    kskm = raw_item.get("kskm", "")
    exam_subjects = re.split(r"\s+", kskm.strip()) if kskm else []
    
    enrollment = {
        "in_roster": True,
        "degree_types": ["学术型硕士"] if raw_item.get("xxfs") == "1" else ["专业型硕士"],
        "directions": directions,
        "planned_count": int(raw_item.get("nzsrsstr", 0)) if raw_item.get("nzsrsstr") else None,
        "exam_subjects": exam_subjects,
        "source_url": f"https://yz.chsi.com.cn/zsml/...",  # 可构造详情页 URL
        "notice_year": meta["year"],
    }
    
    return {
        "schema_version": 1,
        "name": name,
        "university": meta["university"],
        "college": meta["college"],
        "category": meta["category"],
        "title": "",
        "advisor_level": "",
        "email": "",
        "profile_url": "",
        "research_areas": [],
        "enrollment": enrollment,
        "match_status": "partial_notice",
        "raw_ref": {"faculty": "", "notice": meta.get("raw_ref", "")},
        "source_type": {"faculty": "", "notice": "研招网专业目录"},
    }
```

### 4.3 完整 `parse()` 实现骨架

```python
def parse(raw_path: str, meta: Dict) -> List[Dict]:
    import json
    from pathlib import Path
    
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    raw_items = data.get("data", [])
    results = []
    
    for item in raw_items:
        # 专业代码过滤（若配置了 major_codes）
        major_code = item.get("zydm", "")
        if meta.get("major_codes") and major_code not in meta["major_codes"]:
            continue
        
        names = split_advisor_names(item.get("zdjs", ""))
        if not names:
            # 无具体导师名：生成一条空名记录，靠专业+学校匹配
            results.append(build_tutor_record("", item, meta))
        else:
            for name in names:
                results.append(build_tutor_record(name, item, meta))
    
    return results
```

---

## 5. 配置扩展（`config/schools.py`）

每校 `categories[i].notice` 新增字段：

```python
"notice": {
    "enabled": True,
    "entry_url": "https://yz.chsi.com.cn/zsml/",
    "school_code": "10213",           # 必填：研招网学校代码
    "major_codes": {                  # 可选：专业代码白名单
        "mechanical": ["085501", "085502", "080201"],
        "automation": ["085400", "081100", "083900"]
    },
    "title_pattern": "",              # 研招网模式不使用
    "template": "yzw_major"           # 固定值，路由到 parsers/yzw_major.py
}
```

> 学校代码获取方式：运行一次 `YzwClient.get_school_code("东南大学")` 打印结果，写入配置。

---

## 6. 依赖与环境

| 依赖 | 版本 | 来源 |
|------|------|------|
| `requests` | >=2.31 | requirements.txt 已有 |
| `beautifulsoup4` | >=4.12 | requirements.txt 已有 |
| `pdfplumber` | >=0.10 | requirements.txt 已有（后续 PDF parser 用） |

**无新增运行时依赖**。参考代码 `freecho/yzw` 仅作本地调研，不加入依赖。

---

## 7. 单元测试规范（`tests/test_yzw.py`）

```python
import pytest
from unittest.mock import Mock, patch
from spiders.yzw_api import YzwClient
from parsers.yzw_major import parse, split_advisor_names

class TestSplitAdvisorNames:
    def test_normal(self):
        assert split_advisor_names("张三 李四") == ["张三", "李四"]
    def test_chinese_sep(self):
        assert split_advisor_names("张三；李四") == ["张三", "李四"]
    def test_not_specified(self):
        assert split_advisor_names("不区分导师") == []
    def test_empty(self):
        assert split_advisor_names("") == []

class TestYzwClient:
    @patch("spiders.yzw_api.YzwClient.session")
    def test_get_school_code(self, mock_session):
        # Mock 响应 HTML，验证解析出 dwdm
        ...
    
    @patch("spiders.yzw_api.YzwClient.session")
    def test_fetch_major_directory(self, mock_session):
        # Mock 返回 JSON，验证字段完整性
        ...

class TestYzwMajorParser:
    def test_parse_creates_partial_notice(self, tmp_path):
        # 构造原件 JSON，调用 parse()，验证输出 Schema
        raw = {"data": [{"zydm": "085501", "zymc": "机械工程", "zdjs": "张三", "yjfxmc": "智能制造", "nzsrsstr": "3", "kskm": "101 政治"}]}
        raw_path = tmp_path / "test.json"
        raw_path.write_text(json.dumps(raw), encoding="utf-8")
        
        meta = {"university": "测试大学", "college": "测试学院", "category": "mechanical", "year": 2026, "school_code": "99999"}
        records = parse(str(raw_path), meta)
        
        assert len(records) == 1
        r = records[0]
        assert r["name"] == "张三"
        assert r["match_status"] == "partial_notice"
        assert r["enrollment"]["in_roster"] is True
        assert r["enrollment"]["directions"][0]["code"] == "085501"
```

---

## 8. 验收标准

| 检查项 | 通过标准 |
|--------|----------|
| 接口签名 | `YzwClient`、`parse()` 签名与 `INTERFACE_SPEC.md` 完全一致 |
| 产出文件 | 运行 `python main.py --school 东南大学 --category mechanical --source source_b --year 2026` 产出 `data/output/东南大学_机械工程学院_notice.jsonl` |
| Schema 合规 | 每行 JSON 含 `INTERFACE_SPEC.md 1.1` 所有必填字段 |
| 合并管道 | `pipelines.merge.merge_sources()` 能正确读取 `_notice.jsonl` 并与 `_faculty.jsonl` 匹配 |
| 无循环依赖 | `grep -r "import.*pipelines\|import.*api" spiders/yzw_api.py parsers/yzw_major.py` 无输出 |
| 单测通过 | `pytest tests/test_yzw.py -v` 全绿 |

---

## 9. 常见坑预防清单

| 坑 | 症状 | 预防措施 |
|----|------|----------|
| 学校代码错误 | 返回空数据/404 | 配置写死 `school_code`；首次运行打印校验 |
| `zdjs` 为"不区分导师" | 无法拆分姓名 | 生成空名记录，`match_status="partial_notice"`，合并靠专业+学校 |
| 专业代码年度变更 | 遗漏专业 | 配置 `major_codes` 可选，不填则全专业抓取 |
| 接口限流/验证码 | 403/跳转登录 | 复用 `PoliteSession` 冷却机制；日志记录 `BlockedError` |
| 字段名变动 | KeyError | `.get()` 取值，缺失字段置空不报错 |
| 中文编码乱码 | 文件读写报错 | 全链路 `encoding="utf-8"`，`ensure_ascii=False` |

---

## 10. 交付清单

- [ ] `spiders/yzw_api.py` 实现 `YzwClient` 类
- [ ] `parsers/yzw_major.py` 实现 `parse()` 函数
- [ ] `parsers/__init__.py` 注册 `"yzw_major": parse`
- [ ] `config/schools.py` 东南大学等试点校启用 `notice.enabled=true` 并填 `school_code`
- [ ] `main.py` 导入并集成 `run_source_b()`
- [ ] `tests/test_yzw.py` 单测覆盖核心逻辑
- [ ] 东南大学机械/自动化双学院 Source B 端到端跑通