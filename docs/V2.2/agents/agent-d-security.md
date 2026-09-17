# Agent D 指导书：插件安全检查标准化

> 对应阶段：阶段四 P2  
> 波次：Wave 1  
> 预计工作量：1-2 天

## 1. 目标

把 `config/plugins.py`（549 行）中分散的安全检查提取到 `security/plugin_validator.py`，提升可测试性，同时保持插件配置接口完全不变。

## 2. 可写文件

| 操作 | 文件路径 |
|---|---|
| 新建 | `security/__init__.py` |
| 新建 | `security/plugin_validator.py` |
| 修改 | `config/plugins.py` |

**禁止修改**：`main.py`、`api/server.py`、`spiders/**`

## 3. 冻结接口契约

```python
# security/plugin_validator.py
@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]

def validate_plugin_source(source: str) -> ValidationResult: ...
def validate_plugin_file(path) -> ValidationResult: ...
```

## 4. 现有代码分析

### 4.1 `config/plugins.py` 中的安全检查代码

| 行范围 | 函数/常量 | 职责 |
|---|---|---|
| L44 | `BLOCKED_MODULES` | 受限模块集合：`os, subprocess, shutil, socket, ctypes, sys` |
| L45 | `BLOCKED_CALLS` | 受限函数集合：`eval, exec, compile, input, __import__` |
| L261-283 | `_check_import_safety(source)` | AST 遍历检查 import 和函数调用 |
| L286-320 | `_validate_plugin_source(source, kind, filename)` | 完整校验：安全检查 + 语法检查 + META 检查 + 接口检查 |

### 4.2 `_check_import_safety()` 当前实现

```python
def _check_import_safety(source: str) -> list[str]:
    warnings: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_MODULES:
                    warnings.append(f"插件引入了受限模块 {root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BLOCKED_MODULES:
                warnings.append(f"插件引入了受限模块 {root}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in BLOCKED_CALLS:
                warnings.append(f"插件调用了受限函数 {name}")
    return warnings
```

### 4.3 `_validate_plugin_source()` 当前实现

该函数做 4 件事：
1. 调用 `_check_import_safety()` 检查安全
2. `ast.parse()` 检查语法
3. 查找 `PLUGIN_META` 赋值节点，验证字段完整性
4. 检查接口函数是否实现（如 `fetch`、`parse`、`process` 等）

### 4.4 调用点分析

| 调用方 | 调用的函数 | 位置 |
|---|---|---|
| `upload_plugin()` | `_validate_plugin_source()` | L482 |
| `discover_external_plugins()` | `_validate_plugin_source()` | L348 |
| `api/server.py` 的 `api_plugin_upload()` | 通过 `upload_plugin()` 间接调用 | L1137-1156 |

## 5. 实施步骤

### Step 1：创建 `security/__init__.py`

```python
"""安全检查模块：插件验证、权限控制。"""
from .plugin_validator import ValidationResult, validate_plugin_source, validate_plugin_file

__all__ = ["ValidationResult", "validate_plugin_source", "validate_plugin_file"]
```

### Step 2：创建 `security/plugin_validator.py`

```python
"""插件安全验证器。

检查用户上传的插件 Python 源码是否安全：
1. 不引入受限模块（os, subprocess, shutil, socket, ctypes, sys）
2. 不调用受限函数（eval, exec, compile, input, __import__）
3. 语法正确
4. 包含合法的 PLUGIN_META
5. 实现了必要的接口函数
"""

import ast
from dataclasses import dataclass, field

BLOCKED_MODULES = {"os", "subprocess", "shutil", "socket", "ctypes", "sys"}
BLOCKED_CALLS = {"eval", "exec", "compile", "input", "__import__"}


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_plugin_source(source: str, kind: str = "", filename: str = "") -> ValidationResult:
    """验证插件源码安全性。

    Args:
        source: Python 源码字符串
        kind: 插件类型（source/fetcher/parser/processor/exporter/presenter/utility）
        filename: 插件文件名

    Returns:
        ValidationResult 包含 ok、errors、warnings
    """
    errors = []
    warnings = []

    # 1. 语法检查
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return ValidationResult(ok=False, errors=[f"语法错误: {exc.msg}"])

    # 2. 安全检查（import + 调用）
    safety_issues = _check_import_safety(tree)
    warnings.extend(safety_issues)

    # 3. PLUGIN_META 检查（如果指定了 kind）
    if kind:
        meta_errors = _check_plugin_meta(tree, kind)
        errors.extend(meta_errors)

        # 4. 接口函数检查
        from config.plugins import PLUGIN_INTERFACES
        interface_name = PLUGIN_INTERFACES.get(kind, "")
        if interface_name:
            if not _has_function(tree, interface_name):
                errors.append(f"缺少接口函数 {interface_name}()")

    ok = len(errors) == 0
    return ValidationResult(ok=ok, errors=errors, warnings=warnings)


def validate_plugin_file(path) -> ValidationResult:
    """验证插件文件。"""
    try:
        source = open(path, "r", encoding="utf-8").read()
    except Exception as e:
        return ValidationResult(ok=False, errors=[f"无法读取文件: {e}"])
    return validate_plugin_source(source)


def _check_import_safety(tree: ast.AST) -> list[str]:
    """AST 遍历检查 import 和函数调用。"""
    warnings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BLOCKED_MODULES:
                    warnings.append(f"引入了受限模块 {root}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in BLOCKED_MODULES:
                warnings.append(f"引入了受限模块 {root}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in BLOCKED_CALLS:
                warnings.append(f"调用了受限函数 {name}")
    return warnings


def _check_plugin_meta(tree: ast.AST, kind: str) -> list[str]:
    """检查 PLUGIN_META 字典。"""
    from config.plugins import PLUGIN_META_FIELDS

    errors = []
    meta_node = None
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(isinstance(t, ast.Name) and t.id == "PLUGIN_META" for t in targets):
                meta_node = node.value
                break

    if meta_node is None:
        return ["缺少 PLUGIN_META 字典"]

    try:
        meta = ast.literal_eval(meta_node)
    except (ValueError, TypeError):
        return ["PLUGIN_META 必须是字面量字典"]

    if not isinstance(meta, dict):
        return ["PLUGIN_META 必须是字典"]

    missing = [f for f in PLUGIN_META_FIELDS if not meta.get(f)]
    if missing:
        errors.append(f"PLUGIN_META 缺少字段: {', '.join(missing)}")

    if meta.get("kind") != kind:
        errors.append(f"PLUGIN_META.kind 必须是 {kind!r}")

    return errors


def _has_function(tree: ast.AST, func_name: str) -> bool:
    """检查模块顶层是否定义了指定函数。"""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            return True
    return False
```

### Step 3：改造 `config/plugins.py`

1. 删除 `BLOCKED_MODULES`、`BLOCKED_CALLS` 常量（移入 `security/plugin_validator.py`）
2. 删除 `_check_import_safety()` 函数
3. 修改 `_validate_plugin_source()` 内部委托 `security.plugin_validator.validate_plugin_source()`：
   ```python
   from security.plugin_validator import validate_plugin_source as _validate_source

   def _validate_plugin_source(source: str, kind: str, filename: str) -> tuple[dict, list[str]]:
       result = _validate_source(source, kind, filename)
       if not result.ok:
           raise ValueError("；".join(result.errors))
       # 提取 meta（从 AST 重新解析，因为 validator 只返回 ValidationResult）
       tree = ast.parse(source)
       meta_node = None
       for node in tree.body:
           if isinstance(node, (ast.Assign, ast.AnnAssign)):
               targets = node.targets if isinstance(node, ast.Assign) else [node.target]
               if any(isinstance(t, ast.Name) and t.id == "PLUGIN_META" for t in targets):
                   meta_node = node.value
       meta = ast.literal_eval(meta_node)
       return meta, result.warnings
   ```
4. 保留 `config/plugins.py` 的所有公开函数签名不变：
   - `load_plugin_config()`
   - `save_plugin_config()`
   - `list_plugins()`
   - `get_plugin()`
   - `is_enabled()`
   - `plugin_config()`
   - `upload_plugin()`
   - `delete_plugin()`
   - `reload_plugin()`
   - `update_plugin()`
   - `update_pipeline()`

## 6. 同步点

| 依赖 | 接口 | 说明 |
|---|---|---|
| Agent A | `api/server.py` 调用 `upload_plugin()` 等 | D 保持 `config/plugins.py` 接口不变 |
| Agent F | 安全检查测试 | F 按 `ValidationResult` 接口写测试 |

## 7. 验收命令

```bash
# 1. 导入检查
python -c "from security.plugin_validator import validate_plugin_source, ValidationResult; print('OK')"

# 2. 功能测试
pytest tests/test_plugin_security.py -q

# 3. 现有插件测试不破坏
pytest tests/test_plugins.py -q

# 4. 验证 config/plugins.py 公开接口完整
python -c "
from config.plugins import (
    load_plugin_config, save_plugin_config, list_plugins, get_plugin,
    is_enabled, plugin_config, upload_plugin, delete_plugin, reload_plugin,
    update_plugin, update_pipeline
)
print('所有公开接口可用')
"
```

## 8. 注意事项

1. **`PLUGIN_INTERFACES` 和 `PLUGIN_META_FIELDS` 留在 `config/plugins.py`**：validator 通过 import 引用，避免循环依赖
2. **`ValidationResult` 是新接口**：用 `dataclass` 而非 `tuple`，更清晰
3. **`validate_plugin_source()` 的 `kind` 参数可选**：不传时只做安全检查，不检查 META 和接口
4. **`_validate_plugin_source()` 保留为 `config/plugins.py` 的私有函数**：对外不暴露 AST 解析细节
5. **不改 `config/plugins.py` 的公开 API**：所有 `__all__` 中的函数签名不变
