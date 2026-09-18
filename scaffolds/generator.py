# -*- coding: utf-8 -*-
"""Scaffolds Generator — 从模板生成插件包骨架。

生成物与 W3 loader_protocol 完全一致：
- metadata.json 包含所有 REQUIRED_METADATA_FIELDS
- entry_point 格式: module.path:ClassName
- 插件继承对应基类的最小可运行骨架（业务逻辑处留 TODO，正文 ≤30 行）
- 每个包含 test_plugin.py 一个必过用例
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scaffolds.loader_protocol import (
    REQUIRED_METADATA_FIELDS,
    PLUGIN_TYPE_TO_DIR,
    PLUGIN_TYPE_SCHEMAS,
)

VALID_KINDS = ("spider", "processor", "storage", "presenter", "ui", "template")

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ── 默认输出目录 ──
DEFAULT_OUTPUT_BASE = Path("tests/fixtures/generated_plugin")


# ── Kind → 生成配置映射 ──

KIND_CONFIGS: dict[str, dict[str, Any]] = {
    "spider": {
        "base_class": "SpiderPlugin",
        "base_import": "from plugins.spiders import SpiderPlugin",
        "input_type": "TaskConfigDTO",
        "output_type": "RawDataBatch",
        "input_import": "from contracts.task import TaskConfigDTO",
        "output_import": "from contracts.raw import RawDataBatch",
        "input_schema": "TaskConfigDTO.v1",
        "output_schema": "RawDataBatch.v1",
        "execute_body": (
            "        # TODO: 实现采集逻辑\n"
            "        # 使用 context.http 发起请求，解析页面，构建 RawDataBatch\n"
            "        cfg = data.config_snapshot\n"
            "        return RawDataBatch(\n"
            "            schema_version=\"1\",\n"
            "            task_id=context.task_id,\n"
            "            items=[],\n"
            "            pagination_complete=True,\n"
            "            fetched_at=datetime.now(timezone.utc).isoformat(),\n"
            "        )"
        ),
        "extra_imports": "from datetime import datetime, timezone",
    },
    "processor": {
        "base_class": "BasePlugin[RawDataBatch, RecordBatch]",
        "base_import": "from plugins.base import BasePlugin",
        "input_type": "RawDataBatch",
        "output_type": "RecordBatch",
        "input_import": "from contracts.raw import RawDataBatch",
        "output_import": "from contracts.record import RecordBatch, NormalizedRecordDTO",
        "input_schema": "RawDataBatch.v1",
        "output_schema": "RecordBatch.v1",
        "execute_body": (
            "        # TODO: 实现解析/处理逻辑\n"
            "        # 从 data.items 提取字段，构建 RecordBatch\n"
            "        return RecordBatch(\n"
            "            schema_version=\"1\",\n"
            "            records=[],\n"
            "            stats={\"processed\": len(data.items) if data.items else 0},\n"
            "        )"
        ),
        "extra_imports": "",
    },
    "storage": {
        "base_class": "BasePlugin[StoreRequest, StoreReceipt]",
        "base_import": "from plugins.base import BasePlugin",
        "input_type": "StoreRequest",
        "output_type": "StoreReceipt",
        "input_import": "from contracts.result import StoreRequest, StoreReceipt",
        "output_import": "",
        "input_schema": "StoreRequest.v1",
        "output_schema": "StoreReceipt.v1",
        "execute_body": (
            "        # TODO: 实现存储逻辑\n"
            "        # 原子写入，返回 StoreReceipt\n"
            "        return StoreReceipt(\n"
            "            target_id=data.target_id,\n"
            "            written=0,\n"
            "            skipped=0,\n"
            "            failed=0,\n"
            "            records_written=0,\n"
            "            output_ref=\"\",\n"
            "            created_at=datetime.now(timezone.utc).isoformat(),\n"
            "        )"
        ),
        "extra_imports": "from datetime import datetime, timezone",
    },
    "presenter": {
        "base_class": "PresenterPlugin",
        "base_import": "from plugins.base import PresenterPlugin",
        "input_type": "PresentationRequest",
        "output_type": "RenderedOutputDTO",
        "input_import": "from contracts.output import PresentationRequest, RenderedOutputDTO",
        "output_import": "",
        "input_schema": "PresentationRequest.v1",
        "output_schema": "RenderedOutputDTO.v1",
        "execute_body": (
            "        # TODO: 实现渲染逻辑\n"
            "        # 或覆盖 render() 方法\n"
            "        return RenderedOutputDTO(\n"
            "            output_id=uuid4().hex,\n"
            "            output_format=\"text\",\n"
            "            path=\"output.txt\",\n"
            "        )"
        ),
        "extra_imports": "from uuid import uuid4",
    },
    "ui": {
        "base_class": "BasePlugin[ViewModel, UIComponentDTO]",
        "base_import": "from plugins.base import BasePlugin",
        "input_type": "ViewModel",
        "output_type": "UIComponentDTO",
        "input_import": "from contracts.ui import ViewModel, UIComponentDTO",
        "output_import": "",
        "input_schema": "ViewModel.v1",
        "output_schema": "UIComponentDTO.v1",
        "execute_body": (
            "        # TODO: 实现组件描述生成\n"
            "        return UIComponentDTO(\n"
            "            component_id=uuid4().hex,\n"
            "            component_type=\"custom\",\n"
            "            renderer_id=self.name,\n"
            "            payload={},\n"
            "            created_at=datetime.now(timezone.utc).isoformat(),\n"
            "        )"
        ),
        "extra_imports": "from uuid import uuid4\nfrom datetime import datetime, timezone",
    },
}


def _to_class_name(snake: str) -> str:
    """snake_case → PascalCase + Plugin suffix (避免重复)。"""
    parts = snake.split("_")
    base = "".join(p.capitalize() for p in parts)
    if base.endswith("Plugin"):
        return base
    return base + "Plugin"


def _generate_plugin_py(kind: str, name: str) -> str:
    """生成 plugin.py 源码。"""
    cfg = KIND_CONFIGS[kind]
    class_name = _to_class_name(name)

    lines = [
        f'# -*- coding: utf-8 -*-',
        f'"""',
        f'{class_name}',
        f'{"=" * len(class_name)}',
        f'Auto-generated {kind} plugin scaffold.',
        f'Fill in the TODO sections with your business logic.',
        f'"""',
        f'',
        f'import logging',
    ]

    if cfg["extra_imports"]:
        for line in cfg["extra_imports"].split("\n"):
            lines.append(line)

    lines.extend([
        f'',
        f'{cfg["input_import"]}',
    ])
    if cfg["output_import"]:
        lines.append(cfg["output_import"])
    lines.extend([
        f'{cfg["base_import"]}',
        f'from plugins.base import PluginContext',
        f'',
        f'logger = logging.getLogger(__name__)',
        f'',
        f'',
        f'class {class_name}({cfg["base_class"]}):',
        f'    """{kind.capitalize()} plugin: {name}."""',
        f'',
        f'    name = "{name}"',
        f'    version = "1.0.0"',
        f'    plugin_type = "{kind}"',
        f'    input_schema = "{cfg["input_schema"]}"',
        f'    output_schema = "{cfg["output_schema"]}"',
        f'',
        f'    def setup(self, context: PluginContext) -> None:',
        f'        self._config = context.config_snapshot.get("plugins", {{}}).get("{name}", {{}})',
        f'',
        f'    def execute(self, data: {cfg["input_type"]}, context: PluginContext) -> {cfg["output_type"]}:',
        cfg["execute_body"],
        f'',
        f'    def close(self) -> None:',
        f'        pass',
    ])

    return "\n".join(lines) + "\n"


def _generate_metadata_json(kind: str, name: str, author: str) -> str:
    """生成 metadata.json。"""
    cfg = KIND_CONFIGS[kind]
    metadata = {
        "name": name,
        "version": "1.0.0",
        "author": author,
        "plugin_type": kind,
        "input_schema": cfg["input_schema"],
        "output_schema": cfg["output_schema"],
        "entry_point": f"plugins.{PLUGIN_TYPE_TO_DIR[kind]}.{name}.plugin:{_to_class_name(name)}",
        "dependencies": [],
        "min_core_version": "3.0.0",
        "config_schema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "license": "MIT",
    }
    return json.dumps(metadata, indent=2, ensure_ascii=False) + "\n"


def _generate_test_py(kind: str, name: str) -> str:
    """生成 test_plugin.py 单测（一个必过用例）。"""
    class_name = _to_class_name(name)
    cfg = KIND_CONFIGS[kind]

    return f'''# -*- coding: utf-8 -*-
"""{class_name} — 自动生成的单测。"""

import json
from pathlib import Path

import pytest


def test_metadata_self_consistent():
    """metadata.json 字段自洽且 plugin 类可导入。"""
    meta_path = Path(__file__).parent / "metadata.json"
    assert meta_path.exists(), "metadata.json 不存在"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    # 必须字段
    required = {list(REQUIRED_METADATA_FIELDS)}
    for key in required:
        assert key in meta, f"metadata.json 缺少 {{key}}"

    assert meta["plugin_type"] == "{kind}"
    assert meta["input_schema"] == "{cfg["input_schema"]}"
    assert meta["output_schema"] == "{cfg["output_schema"]}"

    # entry_point 可解析
    module_path, class_name_str = meta["entry_point"].split(":")
    assert module_path.endswith(".plugin")
    assert class_name_str == "{class_name}"
'''


def _generate_init_py() -> str:
    return '# -*- coding: utf-8 -*-\n'


def _generate_readme(kind: str, name: str) -> str:
    class_name = _to_class_name(name)
    return f"""# {class_name}

Auto-generated {kind} plugin scaffold.

## 安装

将此目录放入 `plugins/{PLUGIN_TYPE_TO_DIR[kind]}/` 即可。

## 配置

在 `config/plugins.yaml` 中添加实例：

```yaml
instances:
  {name}:
    plugin: {kind}:{name}
    enabled: true
    params: {{}}
```

## 测试

```bash
python -m pytest tests/fixtures/generated_plugin/{name}/ -q
```
"""


def generate_plugin(
    kind: str,
    name: str,
    output_dir: str | None = None,
    author: str = "developer",
) -> dict[str, Any]:
    """生成插件包骨架。

    Args:
        kind: 插件类型 (spider/processor/storage/presenter/ui/template)
        name: 插件名称 (snake_case)
        output_dir: 输出目录 (默认: tests/fixtures/generated_plugin/<name>)
        author: 作者名

    Returns:
        {"output_dir": str, "files": [str, ...]}

    Raises:
        ValueError: kind 或 name 不合法
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"无效的插件类型: {kind!r}，可选: {', '.join(VALID_KINDS)}")

    if not name or not name.replace("_", "").isalnum():
        raise ValueError(f"插件名称必须是 snake_case: {name!r}")

    if kind == "template":
        return _generate_template(name, output_dir, author)

    out = Path(output_dir) if output_dir else DEFAULT_OUTPUT_BASE / name
    out.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    # __init__.py
    init_path = out / "__init__.py"
    init_path.write_text(_generate_init_py(), encoding="utf-8")
    files_written.append("__init__.py")

    # plugin.py
    plugin_path = out / "plugin.py"
    plugin_path.write_text(_generate_plugin_py(kind, name), encoding="utf-8")
    files_written.append("plugin.py")

    # metadata.json
    meta_path = out / "metadata.json"
    meta_path.write_text(_generate_metadata_json(kind, name, author), encoding="utf-8")
    files_written.append("metadata.json")

    # test_plugin.py
    test_path = out / "test_plugin.py"
    test_path.write_text(_generate_test_py(kind, name), encoding="utf-8")
    files_written.append("test_plugin.py")

    # README.md
    readme_path = out / "README.md"
    readme_path.write_text(_generate_readme(kind, name), encoding="utf-8")
    files_written.append("README.md")

    return {"output_dir": str(out), "files": files_written}


def _generate_template(name: str, output_dir: str | None, author: str) -> dict[str, Any]:
    """生成 HTML 模板四件套骨架。"""
    out = Path(output_dir) if output_dir else DEFAULT_OUTPUT_BASE / name
    out.mkdir(parents=True, exist_ok=True)

    files_written: list[str] = []

    # layout.html
    layout = out / "layout.html"
    layout.write_text(
        f'<!DOCTYPE html>\n<html lang="zh-CN">\n<head>\n'
        f'  <meta charset="UTF-8">\n'
        f'  <title>{{{{ page.title | default("{name}") }}}}</title>\n'
        f'  <link rel="stylesheet" href="style.css">\n'
        f'</head>\n<body>\n'
        f'  <header>{{{{ page.header | default("") }}}}</header>\n'
        f'  <main>{{{{ content }}}}</main>\n'
        f'  <footer>{{{{ page.footer | default("") }}}}</footer>\n'
        f'</body>\n</html>\n',
        encoding="utf-8",
    )
    files_written.append("layout.html")

    # style.css
    style = out / "style.css"
    style.write_text(
        f'/* {name} template styles */\n'
        f':root {{\n  --primary: #3b82f6;\n  --bg: #ffffff;\n  --text: #1f2937;\n}}\n'
        f'body {{ font-family: system-ui, sans-serif; margin: 0; padding: 2rem; '
        f'background: var(--bg); color: var(--text); }}\n'
        f'main {{ max-width: 960px; margin: 0 auto; }}\n',
        encoding="utf-8",
    )
    files_written.append("style.css")

    # variables.json
    variables = out / "variables.json"
    variables.write_text(
        json.dumps({
            "name": name,
            "author": author,
            "version": "1.0.0",
            "description": f"{name} template",
            "variables": {
                "primary_color": {"type": "color", "default": "#3b82f6"},
                "font_family": {"type": "string", "default": "system-ui, sans-serif"},
            },
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    files_written.append("variables.json")

    # preview.png placeholder (empty file; real preview generated by build)
    preview = out / "preview.png"
    if not preview.exists():
        preview.write_bytes(b"")
    files_written.append("preview.png")

    return {"output_dir": str(out), "files": files_written}


def validate_scaffold(output_dir: str | Path) -> dict[str, Any]:
    """校验脚手架生成物是否满足 W3 loader_protocol 规范。

    Returns:
        {"valid": bool, "errors": [str, ...], "warnings": [str, ...]}
    """
    out = Path(output_dir)
    errors: list[str] = []
    warnings: list[str] = []

    # metadata.json 存在性
    meta_path = out / "metadata.json"
    if not meta_path.exists():
        errors.append("metadata.json 不存在")
        return {"valid": False, "errors": errors, "warnings": warnings}

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"metadata.json JSON 解析失败: {e}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    # 必须字段
    for field in REQUIRED_METADATA_FIELDS:
        if field not in meta:
            errors.append(f"metadata.json 缺少必须字段: {field}")

    # plugin_type 合法性
    if meta.get("plugin_type") not in PLUGIN_TYPE_TO_DIR:
        errors.append(f"无效的 plugin_type: {meta.get('plugin_type')}")

    # entry_point 格式
    ep = meta.get("entry_point", "")
    if ":" not in ep:
        errors.append(f"entry_point 格式错误（应为 module.path:ClassName）: {ep}")

    # plugin.py 存在性
    if not (out / "plugin.py").exists():
        warnings.append("plugin.py 不存在")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
