# 模块三：配置去重、校验与标准化实施指南

> **模块定位**：独立可并行开发｜**依赖接口**：`INTERFACE_SPEC.md` 第 4 节｜**不依赖其他模块开发进度**

---

## 1. 模块目标

| 问题 | 现状 | 目标 |
|------|------|------|
| 配置重复 | 147 校中约 30 个校名重复条目（东南大学×2、北京交通大学×2 等） | 去重合并为每校唯一条目 |
| 字段缺失 | 部分校缺 `notice`、`level`、`list_url` 等必填字段 | 全量补全，无空必填字段 |
| 代码混乱 | `config/schools.py` 1245 行手工维护 | 拆分为数据文件 + 加载器，支持 API 在线编辑 |
| 无校验 | 运行时才发现配置错误 | 启动时全量校验，错误立即报告 |

**产出**：
- `config/schools.py` 重构为加载器 + 配置数据分离
- `config/school_data.json`（或 `.yaml`）配置数据文件
- `config/validator.py` 配置校验器
- `config/major_mapping.py` 专业代码映射表

---

## 2. 接口契约

### 2.1 配置加载器（`config/loader.py`）

```python
# 文件：config/loader.py
from typing import Dict, List, Optional

def load_schools_config(path: Optional[str] = None) -> List[Dict]:
    """
    加载全量学校配置。

    Args:
        path: 配置文件路径，默认 config/school_data.json

    Returns:
        List[Dict]  # 每项符合 INTERFACE_SPEC.md 第 4 节配置结构
        必含字段：university, categories[{college, category, faculty, notice}]

    行为：
        1. 读取配置文件
        2. 自动填充 level（从 school_level_raw 推导）
        3. 验证必填字段（调用 validate_school_config）
        4. 验证失败的条目记录 warning 但不中断加载
    """
    ...


def get_school_config(university: str) -> Optional[Dict]:
    """
    按校名查找单校配置。

    Returns:
        Dict | None  # 符合 INTERFACE_SPEC.md 4 节结构，未找到返回 None
    """
    ...


def save_school_config(university: str, config: Dict) -> bool:
    """
    保存单校配置（API `/api/config/schools/{name}` PUT 调用）。

    Args:
        university: 学校标准名
        config: 完整校配置对象

    Returns:
        bool: 是否保存成功

    行为：
        1. 校验 config 合法性
        2. 更新内存缓存
        3. 原子写入配置文件
    """
    ...


def reload_config() -> int:
    """
    重新加载配置文件（API `/api/config/global` PUT 后调用）。

    Returns:
        int: 加载的学校数量
    """
    ...
```

### 2.2 配置校验器（`config/validator.py`）

```python
# 文件：config/validator.py
from typing import Dict, List

class ConfigError:
    """单条配置校验错误"""
    def __init__(self, university: str, college: str, field: str, message: str, level: str = "error"):
        self.university = university
        self.college = college
        self.field = field
        self.message = message
        self.level = level  # "error" | "warning"
    
    def __str__(self):
        return f"[{self.level.upper()}] {self.university}/{self.college} - {self.field}: {self.message}"


def validate_school_config(config: Dict) -> List[ConfigError]:
    """
    校验单校配置是否符合 INTERFACE_SPEC.md 第 4 节规范。

    Args:
        config: 单校配置字典

    Returns:
        List[ConfigError]  # 空列表表示校验通过

    校验规则：
        - university: 非空字符串
        - categories: 非空列表
        - 每个 category 必含: college(非空), category("mechanical"|"automation")
        - faculty.list_url: 非空（静默跳过的需显式标记 enabled=false）
        - faculty.list_type: "static_html" | "ajax_api"
        - notice.enabled: bool
        - notice.template: 非空（当 notice.enabled=true）
        - notice.school_code: 非空（当 notice.enabled=true 且 template="yzw_major"）
    """
    ...


def validate_all_configs(configs: List[Dict]) -> Dict[str, List[ConfigError]]:
    """
    校验全量配置。

    Returns:
        {
            "errors": [ConfigError, ...],     # 必须修复
            "warnings": [ConfigError, ...],   # 建议修复
            "summary": {"total": N, "errors": N, "warnings": N, "ok": N}
        }
    """
    ...
```

### 2.3 专业代码映射（`config/major_mapping.py`）

```python
# 文件：config/major_mapping.py

MAJOR_MAPPING = {
    "mechanical": {
        "name": "机械工程",
        "first_level_codes": ["0855", "0802", "0824"],     # 一级学科代码
        "detail_codes": ["085501", "085502", "080201", "080202", "080203", "080204"],  # 二级学科代码
    },
    "automation": {
        "name": "控制科学与工程",
        "first_level_codes": ["0854", "0811", "0839", "0810"],
        "detail_codes": ["085400", "081100", "081101", "081102", "081103", "081104", "083900", "081000"],
    },
}


def get_major_codes(category: str, level: str = "detail") -> list:
    """
    获取指定类别的专业代码列表。

    Args:
        category: "mechanical" | "automation"
        level: "first_level" | "detail"（默认 detail）

    Returns:
        List[str] 专业代码列表
    """
    info = MAJOR_MAPPING.get(category)
    if not info:
        return []
    return info.get(f"{level}_codes", info.get("detail_codes", []))
```

---

## 3. 配置去重方案

### 3.1 去重规则

```
规则 1：university + category 唯一
  → 同一学校同一类别只能有一条配置
  → 例：东南大学 mechanical 只保留一条

规则 2：保留字段更完整的条目
  → 两条配置合并：字段取非空值，数组取并集

规则 3：categories 列表合并
  → 同校不同 category 的条目合并到同一 university 的 categories 列表中
```

### 3.2 去重算法（`config/dedup.py`）

```python
# 文件：config/dedup.py
from typing import List, Dict

def deduplicate_schools(configs: List[Dict]) -> tuple[List[Dict], List[str]]:
    """
    去重学校配置。

    Args:
        configs: 原始配置列表（可能含重复）

    Returns:
        (deduped, logs)
        - deduped: 去重后的配置列表
        - logs: 去重操作日志列表，每条描述合并详情

    处理流程：
        1. 按 university 分组
        2. 同校内按 (university, category) 去重
        3. 合并冲突字段（非空优先，数组并集）
        4. 输出去重日志
    """
    merged: Dict[str, Dict] = {}
    logs: List[str] = []
    
    for cfg in configs:
        uni = cfg.get("university", "").strip()
        if not uni:
            logs.append(f"跳过空 university 条目")
            continue
        
        if uni not in merged:
            merged[uni] = cfg.copy()
            merged[uni]["categories"] = list(cfg.get("categories", []))
            continue
        
        # 合并 categories
        existing_cats = {
            (c.get("category"), c.get("college")): c
            for c in merged[uni].get("categories", [])
        }
        
        for cat in cfg.get("categories", []):
            key = (cat.get("category"), cat.get("college"))
            if key in existing_cats:
                # 合并：字段取非空值
                existing = existing_cats[key]
                merged_cat = merge_category(existing, cat)
                existing_cats[key] = merged_cat
                logs.append(f"合并 {uni}/{key[1]} ({key[0]}) 重复配置")
            else:
                existing_cats[key] = cat
                logs.append(f"新增 {uni}/{cat.get('college')} ({cat.get('category')})")
        
        merged[uni]["categories"] = list(existing_cats.values())
    
    return list(merged.values()), logs


def merge_category(a: Dict, b: Dict) -> Dict:
    """合并两个同类配置，非空优先，数组并集"""
    result = a.copy()
    for key, val_b in b.items():
        if key in ("faculty", "notice"):
            # 子字典递归合并
            if isinstance(val_b, dict) and isinstance(result.get(key), dict):
                result[key] = merge_dicts(result[key], val_b)
            elif val_b and not result.get(key):
                result[key] = val_b
        elif isinstance(val_b, list):
            # 列表取并集
            existing = set(str(x) for x in result.get(key, []))
            for item in val_b:
                if str(item) not in existing:
                    result[key] = result.get(key, []) + [item]
                    existing.add(str(item))
        elif val_b and not result.get(key):
            result[key] = val_b
    return result


def merge_dicts(a: Dict, b: Dict) -> Dict:
    """合并两个字典，非空优先"""
    result = a.copy()
    for k, v in b.items():
        if v and not result.get(k):
            result[k] = v
    return result
```

---

## 4. 配置数据文件格式（`config/school_data.json`）

从现有 `schools.py` 提取数据，转为标准 JSON：

```json
[
  {
    "university": "东南大学",
    "level": "985",
    "categories": [
      {
        "college": "机械工程学院",
        "category": "mechanical",
        "faculty": {
          "list_url": "http://me.seu.edu.cn/szdw/szgk.htm",
          "list_type": "static_html",
          "list_item_selector": "li a[href*='info']",
          "list_research_selector": "p.research",
          "detail_selectors": {
            "name": ".carrer .jsbt",
            "title": ".carrer .title",
            "email_re": "邮箱:([^\\s<]+)"
          },
          "api_params": {},
          "referer": ""
        },
        "notice": {
          "enabled": true,
          "entry_url": "https://yz.chsi.com.cn/zsml/",
          "school_code": "10213",
          "major_codes": {},
          "title_pattern": "",
          "template": "yzw_major"
        }
      },
      {
        "college": "自动化学院",
        "category": "automation",
        "faculty": { "...": "..." },
        "notice": { "...": "..." }
      }
    ]
  }
]
```

---

## 5. `school_level_raw.py` 校验与修正

### 5.1 现有问题

| 问题类型 | 示例 | 修正方式 |
|----------|------|----------|
| 遗漏 | 某些 985 校未标记 211 | 自动补全（985 ⊂ 211） |
| 冗余 | 同一校名重复出现在多个列表中 | 去重 |
| 名称不一致 | "国防科技大学" vs "中国人民解放军国防科技大学" | 统一为标准名 |

### 5.2 修正函数

```python
# 文件：config/school_level_raw.py 顶部
def validate_and_fix_levels():
    """
    校验并修正学校级别数据。

    规则：
        1. 985 校必然同时是 211 和双一流
        2. 211 校必然同时是双一流
        3. 无名重复（去重后统计）
    """
    # 自动补全：985 → 211 + 双一流
    for name in SCHOOLS_985:
        if name not in SCHOOLS_211:
            SCHOOLS_211.add(name)
        if name not in SCHOOLS_DOUBLE_FIRST_CLASS:
            SCHOOLS_DOUBLE_FIRST_CLASS.add(name)
    
    # 211 → 双一流
    for name in SCHOOLS_211:
        if name not in SCHOOLS_DOUBLE_FIRST_CLASS:
            SCHOOLS_DOUBLE_FIRST_CLASS.add(name)
```

---

## 6. 集成方式

### 6.1 `main.py` 改造

```python
# main.py 顶部
from config.loader import load_schools_config, get_school_config
from config.validator import validate_all_configs

def main():
    # 启动时加载并校验配置
    configs = load_schools_config()
    report = validate_all_configs(configs)
    
    if report["summary"]["errors"] > 0:
        logger.error(f"配置校验发现 {report['summary']['errors']} 个错误：")
        for err in report["errors"]:
            logger.error(f"  {err}")
        sys.exit(1)
    
    if report["summary"]["warnings"] > 0:
        for warn in report["warnings"]:
            logger.warning(f"  {warn}")
    
    logger.info(f"配置加载完成：{report['summary']['ok']} 校通过校验")
```

### 6.2 `api/server.py` 改造

```python
# api/server.py 中
from config.loader import get_school_config, save_school_config, reload_config
from config.validator import validate_school_config

@app.route("/api/config/schools/<name>", methods=["GET"])
def api_get_school_config(name):
    cfg = get_school_config(name)
    if not cfg:
        return jsonify({"code": 40401, "message": f"未找到学校: {name}"})
    return jsonify({"code": 0, "data": cfg})

@app.route("/api/config/schools/<name>", methods=["PUT"])
def api_save_school_config(name):
    data = request.get_json()
    errors = validate_school_config(data)
    if errors:
        return jsonify({"code": 40001, "message": "配置校验失败", "detail": [str(e) for e in errors]})
    save_school_config(name, data)
    return jsonify({"code": 0, "data": {"message": "保存成功"}})
```

---

## 7. 单元测试规范（`tests/test_config.py`）

```python
import pytest
from config.loader import load_schools_config, get_school_config
from config.validator import validate_school_config, ConfigError
from config.dedup import deduplicate_schools, merge_category
from config.major_mapping import get_major_codes

class TestConfigLoader:
    def test_load_returns_list(self):
        configs = load_schools_config()
        assert isinstance(configs, list)
        assert len(configs) > 100  # 至少 100 校
    
    def test_get_existing_school(self):
        cfg = get_school_config("东南大学")
        assert cfg is not None
        assert cfg["university"] == "东南大学"
    
    def test_get_nonexistent_school(self):
        assert get_school_config("不存在的大学") is None


class TestConfigValidator:
    def test_valid_config(self):
        cfg = {
            "university": "测试大学",
            "categories": [{
                "college": "测试学院",
                "category": "mechanical",
                "faculty": {"list_url": "http://test.edu.cn", "list_type": "static_html"},
                "notice": {"enabled": False, "template": "yzw_major"}
            }]
        }
        errors = validate_school_config(cfg)
        assert len(errors) == 0
    
    def test_missing_university(self):
        cfg = {"categories": []}
        errors = validate_school_config(cfg)
        assert any(e.field == "university" for e in errors)
    
    def test_invalid_category_type(self):
        cfg = {"university": "测试", "categories": [{"category": "invalid"}]}
        errors = validate_school_config(cfg)
        assert any(e.field == "category" for e in errors)


class TestDedup:
    def test_merge_same_university(self):
        configs = [
            {"university": "测试大学", "categories": [{"college": "A", "category": "mechanical"}]},
            {"university": "测试大学", "categories": [{"college": "B", "category": "automation"}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 1
        assert len(result[0]["categories"]) == 2
        assert len(logs) > 0
    
    def test_no_duplicates(self):
        configs = [
            {"university": "大学A", "categories": [{"category": "mechanical"}]},
            {"university": "大学B", "categories": [{"category": "automation"}]},
        ]
        result, logs = deduplicate_schools(configs)
        assert len(result) == 2


class TestMajorMapping:
    def test_mechanical_codes(self):
        codes = get_major_codes("mechanical")
        assert "085501" in codes
    
    def test_automation_codes(self):
        codes = get_major_codes("automation")
        assert "081100" in codes
    
    def test_unknown_category(self):
        assert get_major_codes("unknown") == []
```

---

## 8. 验收标准

| 检查项 | 通过标准 |
|--------|----------|
| 去重结果 | `config/school_data.json` 中无重复 university + category |
| 校验通过 | `validate_all_configs()` 返回 `errors` 为空列表 |
| level 完整 | 每校都有 `level` 字段，985 校同时标记 211 和双一流 |
| API 兼容 | `get_school_config()` 返回结构与 `INTERFACE_SPEC.md` 第 4 节完全一致 |
| 原子写入 | `save_school_config()` 使用临时文件 + rename 原子写 |
| 无硬编码路径 | 配置文件路径可参数化，默认 `config/school_data.json` |
| 单测通过 | `pytest tests/test_config.py -v` 全绿 |

---

## 9. 交付清单

- [ ] `config/school_data.json`：去重后的配置数据文件（147 校去重后约 117 校）
- [ ] `config/loader.py`：`load_schools_config()`、`get_school_config()`、`save_school_config()`
- [ ] `config/validator.py`：`validate_school_config()`、`validate_all_configs()`
- [ ] `config/dedup.py`：`deduplicate_schools()`（去重脚本，生成 school_data.json）
- [ ] `config/major_mapping.py`：`MAJOR_MAPPING` 字典 + `get_major_codes()`
- [ ] `config/school_level_raw.py`：修正版，含 `validate_and_fix_levels()`
- [ ] `config/schools.py`：改为调用 `loader.py` 的薄封装（向后兼容）
- [ ] `tests/test_config.py`：全量校验测试
- [ ] 运行 `python -m config.dedup` 输出去重日志，确认无误
