# 模块二：Parser 插件化框架实施指南

> **模块定位**：独立可并行开发｜**依赖接口**：`INTERFACE_SPEC.md` 第 3.3、3.5、6 节｜**可与 Source B 模块同时开工**

---

## 1. 模块目标

将现有 `parsers/` 目录改造为**插件注册制**：新增 parser 只需添加一个文件并注册，无需修改任何调用方代码。

**当前状态**：`parsers/` 可能只有一个 `yzw_major.py`（或尚未创建），缺乏统一入口。

**目标结构**：

```
parsers/
├── __init__.py          # 插件注册表 + 统一入口 dispatch()
├── yzw_major.py         # Source B：研招网专业目录解析（已有/开发中）
├── notice_pdf.py        # Source C：研究生院公示 PDF 解析（未来扩展）
├── notice_html.py       # Source C：研究生院公示 HTML 解析（未来扩展）
└── richtext_notice.py   # Source C：富文本公告解析（未来扩展）
```

---

## 2. 接口契约（必须严格遵守）

### 2.1 每个 Parser 必须实现的函数签名

```python
# 文件：parsers/{name}.py
from typing import List, Dict

def parse(raw_path: str, meta: Dict) -> List[Dict]:
    """
    标准 Parser 接口（INTERFACE_SPEC.md 3.3 节）。

    Args:
        raw_path: 原件文件绝对路径（JSON / HTML / PDF）
        meta: {
            "university": str,          # 学校标准名
            "college": str,             # 学院标准名
            "category": "mechanical" | "automation",
            "year": int,                # 数据年份
            "school_code": str,         # 研招网学校代码（Source B 用，Source C 可为空）
            "template": str,            # 配置中指定的模板名，用于路由
        }

    Returns:
        List[Dict]  # 每项符合 TutorRecord Schema（INTERFACE_SPEC.md 1.1）

    约定：
        - 不抛出异常，解析失败时记录 logger.warning 并返回空列表
        - 必含字段：name, university, college, category, match_status, raw_ref, source_type
        - match_status 统一设为 "partial_notice"（Source B/C 不含完整师资信息）
    """
    ...
```

### 2.2 注册表接口（`parsers/__init__.py`）

```python
# 文件：parsers/__init__.py
from typing import List, Dict, Callable
import logging

logger = logging.getLogger(__name__)

# 注册表：template 名 → parse 函数
_REGISTRY: Dict[str, Callable[[str, Dict], List[Dict]]] = {}


def register(template_name: str):
    """装饰器，注册 parser 函数到注册表"""
    def decorator(func: Callable[[str, Dict], List[Dict]]):
        if template_name in _REGISTRY:
            logger.warning(f"Parser '{template_name}' 已注册，将被覆盖")
        _REGISTRY[template_name] = func
        return func
    return decorator


def dispatch(raw_path: str, meta: Dict) -> List[Dict]:
    """
    统一入口：根据 meta["template"] 路由到对应 parser。

    Args:
        raw_path: 原件文件路径
        meta: 含 template 字段的元数据

    Returns:
        List[Dict] 解析结果

    Raises:
        ValueError: template 未注册
    """
    template = meta.get("template", "")
    if not template:
        raise ValueError(f"meta 中缺少 template 字段: {meta}")
    
    parser_fn = _REGISTRY.get(template)
    if not parser_fn:
        available = ", ".join(sorted(_REGISTRY.keys()))
        raise ValueError(f"未注册的 parser template: '{template}'，可用: {available}")
    
    logger.info(f"Dispatching parser '{template}' for {meta.get('university', '?')}/{meta.get('college', '?')}")
    return parser_fn(raw_path, meta)


def list_registered() -> List[str]:
    """返回所有已注册的 template 名称列表"""
    return sorted(_REGISTRY.keys())
```

### 2.3 各 Parser 注册示例

```python
# 文件：parsers/yzw_major.py
from parsers import register

@register("yzw_major")
def parse(raw_path: str, meta: dict) -> list:
    # 实现逻辑...
    ...
```

```python
# 文件：parsers/notice_pdf.py（未来扩展占位）
from parsers import register

@register("notice_pdf")
def parse(raw_path: str, meta: dict) -> list:
    # PDF 解析逻辑...
    ...
```

---

## 3. `main.py` 调用方集成

调用方只需 import `parsers.dispatch`，无需关心具体 parser：

```python
# main.py 中集成
from parsers import dispatch

def run_source_b(task, session, progress):
    # ... 抓取原件 ...
    raw_path = f"data/raw/{task.university}/{task.year}/yzw/major_{school_code}.json"
    meta = {
        "university": task.university,
        "college": task.college,
        "category": task.category,
        "year": task.year,
        "school_code": school_code,
        "template": "yzw_major"      # 从配置 notice.template 读取
    }
    
    # 统一调用 dispatch，无需 import 具体 parser
    parsed = dispatch(raw_path, meta)
    
    # ... 写入 _notice.jsonl ...
```

---

## 4. Parser 内部公共工具函数

多个 parser 可能共享通用解析逻辑，抽取到 `parsers/utils.py`：

```python
# 文件：parsers/utils.py
import re
from typing import List

def split_names(raw: str, separators: str = r"[\s;；,，、]+") -> List[str]:
    """通用姓名拆分（供研招网、公示 PDF 等复用）"""
    if not raw or raw.strip() in ("不区分导师", "请登录各学院网站查看", "--", "无"):
        return []
    names = re.split(separators, raw.strip())
    return [n.strip() for n in names if n.strip() and len(n.strip()) >= 2]


def normalize_whitespace(text: str) -> str:
    """归一化空白字符（全角→半角、连续空格→单空格）"""
    if not text:
        return ""
    text = text.replace("　", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def build_raw_ref(meta: dict, source_type: str) -> dict:
    """构造 raw_ref 结构（INTERFACE_SPEC.md 1.1）"""
    return {
        "faculty": meta.get("faculty_raw_ref", ""),
        "notice": f"data/raw/{meta.get('university', '')}/{meta.get('year', '')}/{source_type}/"
    }


def build_source_type(faculty: str = "", notice: str = "") -> dict:
    """构造 source_type 结构（INTERFACE_SPEC.md 1.1）"""
    return {"faculty": faculty, "notice": notice}
```

---

## 5. 错误处理策略（INTERFACE_SPEC.md 第 6 节）

| 场景 | 处理方式 |
|------|----------|
| `template` 未注册 | `dispatch()` 抛出 `ValueError`，`main.py` 捕获写入 `failures.json` |
| 原件文件不存在 | `parse()` 记录 `logger.error`，返回空列表 `[]` |
| 原件格式异常（JSON 无法解析） | `parse()` 捕获 `json.JSONDecodeError`，记录 `logger.warning`，返回空列表 |
| 单条记录字段缺失 | 使用 `.get()` 取值，缺失字段置空/默认值，**不中断**整批解析 |
| 所有记录解析失败 | 返回空列表，`main.py` 记录到 `failures.json` |

---

## 6. 配置路由逻辑（`config/schools.py` 中的 `template` 字段）

配置决定使用哪个 parser，**无需硬编码**：

```python
# config/schools.py 中
"notice": {
    "enabled": True,
    "template": "yzw_major",        # 路由到 parsers/yzw_major.py
    ...
}

# 未来扩展
"notice": {
    "enabled": True,
    "template": "notice_pdf",       # 路由到 parsers/notice_pdf.py
    ...
}
```

---

## 7. 单元测试规范（`tests/test_parsers.py`）

```python
import pytest
from parsers import dispatch, list_registered, _REGISTRY

class TestParserRegistry:
    def test_registered_parsers(self):
        """验证所有预期 parser 已注册"""
        registered = list_registered()
        assert "yzw_major" in registered
    
    def test_dispatch_unknown_template(self):
        """未知 template 应抛出 ValueError"""
        with pytest.raises(ValueError, match="未注册"):
            dispatch("dummy.json", {"template": "nonexistent"})
    
    def test_dispatch_missing_template(self):
        """meta 缺少 template 应抛出 ValueError"""
        with pytest.raises(ValueError, match="缺少 template"):
            dispatch("dummy.json", {"university": "测试"})


class TestParserUtils:
    def test_split_names_normal(self):
        from parsers.utils import split_names
        assert split_names("张三 李四") == ["张三", "李四"]
    
    def test_split_names_empty(self):
        from parsers.utils import split_names
        assert split_names("") == []
        assert split_names("不区分导师") == []
    
    def test_normalize_whitespace(self):
        from parsers.utils import normalize_whitespace
        assert normalize_whitespace("  hello   world  ") == "hello world"
        assert normalize_whitespace("hello　world") == "hello world"
```

---

## 8. 依赖与开发顺序

| 依赖 | 说明 |
|------|------|
| `INTERFACE_SPEC.md` 1.1 | TutorRecord Schema 定义 |
| `INTERFACE_SPEC.md` 3.3 | `parse(raw_path, meta)` 签名 |
| `INTERFACE_SPEC.md` 6 | 错误处理契约 |
| `schemas/tutor_v1.py` | TypedDict 定义（若已创建） |

**开发顺序**：
1. 创建 `parsers/__init__.py`（注册表 + dispatch）
2. 创建 `parsers/utils.py`（公共工具函数）
3. 各 parser 文件自行开发，只需 `@register("template_name")` 装饰

---

## 9. 验收标准

| 检查项 | 通过标准 |
|--------|----------|
| 注册表 | `list_registered()` 返回所有已创建 parser 的 template 名 |
| 路由正确 | `dispatch("test.json", {"template": "yzw_major"})` 正确调用对应函数 |
| 未知 template | 抛出 `ValueError`，错误信息含可用列表 |
| 签名合规 | 所有 parser 函数签名 `(raw_path: str, meta: Dict) -> List[Dict]` |
| 错误不抛出 | 原件不存在时返回空列表，不抛异常 |
| 无循环依赖 | `parsers/` 不 import `spiders/`、`pipelines/`、`api/`、`main.py` |
| 单测通过 | `pytest tests/test_parsers.py -v` 全绿 |

---

## 10. 交付清单

- [ ] `parsers/__init__.py`：注册表 + `dispatch()` + `list_registered()`
- [ ] `parsers/utils.py`：`split_names()`、`normalize_whitespace()`、`build_raw_ref()`、`build_source_type()`
- [ ] `parsers/yzw_major.py`：实现 `@register("yzw_major")` 的 `parse()`（可与 Source B 模块同步开发）
- [ ] `tests/test_parsers.py`：注册表 + dispatch + utils 测试
- [ ] `main.py`：改为 `from parsers import dispatch` 调用，移除直接 import 具体 parser
