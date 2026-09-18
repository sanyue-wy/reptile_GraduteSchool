# -*- coding: utf-8 -*-
"""Schema Editor — 交互式字段定义 CLI 向导。

从数据集名 → 来源选择 → 字段增删改 → profile 选择，产出字段定义 dict。
"""

import json
from pathlib import Path
from typing import Any

PRESETS_DIR = Path(__file__).parent / "presets"


# ── 字段类型 ──

FIELD_TYPES = ("string", "integer", "number", "boolean", "array", "object")


def _prompt(prompt_text: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"{prompt_text}{suffix}: ").strip()
    return val or default


def _confirm(prompt_text: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = input(f"{prompt_text} ({hint}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def _choose(prompt_text: str, options: list[str], default: str = "") -> str:
    print(f"\n{prompt_text}")
    for i, opt in enumerate(options, 1):
        marker = " (default)" if opt == default else ""
        print(f"  {i}. {opt}{marker}")
    while True:
        raw = input("选择编号: ").strip()
        if not raw and default:
            return default
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                return options[idx]
        except ValueError:
            pass
        print("无效输入，请重试")


# ── 字段编辑 ──

def _edit_field(field: dict[str, Any] | None = None) -> dict[str, Any]:
    """交互编辑单个字段。"""
    is_new = field is None
    f = dict(field) if field else {}

    f["name"] = _prompt("字段名", f.get("name", ""))
    if not f["name"]:
        raise ValueError("字段名不能为空")

    f["type"] = _choose("字段类型:", list(FIELD_TYPES), f.get("type", "string"))
    f["required"] = _confirm("是否必填?", f.get("required", False))
    f["description"] = _prompt("字段描述", f.get("description", ""))

    if f["type"] == "string":
        enum_val = _prompt("枚举值(逗号分隔,留空跳过)", "")
        if enum_val:
            f["enum"] = [v.strip() for v in enum_val.split(",")]
    elif f["type"] in ("integer", "number"):
        min_val = _prompt("最小值(留空跳过)", "")
        max_val = _prompt("最大值(留空跳过)", "")
        if min_val:
            f["minimum"] = int(min_val) if f["type"] == "integer" else float(min_val)
        if max_val:
            f["maximum"] = int(max_val) if f["type"] == "integer" else float(max_val)

    return f


def _list_fields(fields: list[dict]) -> None:
    if not fields:
        print("  (无字段)")
        return
    for i, f in enumerate(fields, 1):
        req = "✓" if f.get("required") else " "
        print(f"  {i}. [{req}] {f['name']} ({f['type']}) — {f.get('description', '')}")


# ── Profile 选择 ──

BUILTIN_PROFILES = {
    "education": {
        "id": "education",
        "schema_ids": ["education.tutor.v1", "education.major.v1"],
        "description": "教育领域：导师、专业、招生信息",
        "suggested_fields": [
            {"name": "name", "type": "string", "required": True, "description": "姓名"},
            {"name": "title", "type": "string", "required": False, "description": "职称"},
            {"name": "university", "type": "string", "required": True, "description": "学校"},
            {"name": "college", "type": "string", "required": True, "description": "学院"},
            {"name": "research", "type": "string", "required": False, "description": "研究方向"},
            {"name": "email", "type": "string", "required": False, "description": "邮箱"},
            {"name": "profile_url", "type": "string", "required": False, "description": "个人主页"},
        ],
    },
    "custom": {
        "id": "custom",
        "schema_ids": [],
        "description": "自定义领域",
        "suggested_fields": [],
    },
}


def load_preset(preset_name: str) -> dict[str, Any]:
    """从 presets/ 目录加载预设 YAML。"""
    import yaml

    path = PRESETS_DIR / f"{preset_name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"预设不存在: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_presets() -> list[str]:
    """列出可用预设。"""
    return [p.stem for p in PRESETS_DIR.glob("*.yaml")]


def run_editor(preset: str | None = None) -> dict[str, Any]:
    """运行交互式编辑器向导，返回完整任务配置。"""
    if preset:
        config = load_preset(preset)
        print(f"已加载预设: {preset}")
        print(f"  数据集: {config.get('dataset', 'N/A')}")
        print(f"  来源: {config.get('source_id', 'N/A')}")
        if not _confirm("使用此预设?", True):
            preset = None

    if not preset:
        config = {}
        config["dataset"] = _prompt("数据集名", "my_dataset")
        config["source_id"] = _prompt("来源标识", "source_a")
        config["target_url"] = _prompt("目标 URL", "https://example.edu/faculty")

        # Profile
        profiles = list(BUILTIN_PROFILES.keys())
        profile_id = _choose("选择领域 profile:", profiles, "education")
        config["profile_id"] = profile_id

        # Fields
        profile = BUILTIN_PROFILES[profile_id]
        config["fields"] = list(profile.get("suggested_fields", []))

        print("\n── 字段编辑 ──")
        while True:
            print("\n当前字段:")
            _list_fields(config["fields"])
            action = _choose("操作:", ["完成", "添加字段", "编辑字段", "删除字段"], "完成")
            if action == "完成":
                break
            elif action == "添加字段":
                try:
                    config["fields"].append(_edit_field())
                except ValueError as e:
                    print(f"错误: {e}")
            elif action == "编辑字段" and config["fields"]:
                idx = int(_prompt("编辑第几个字段?", "1")) - 1
                if 0 <= idx < len(config["fields"]):
                    config["fields"][idx] = _edit_field(config["fields"][idx])
            elif action == "删除字段" and config["fields"]:
                idx = int(_prompt("删除第几个字段?", str(len(config["fields"])))) - 1
                if 0 <= idx < len(config["fields"]):
                    removed = config["fields"].pop(idx)
                    print(f"已删除: {removed['name']}")

        # Pipeline plugins (use sensible defaults)
        config.setdefault("plugins", {
            "acquire": "static_html",
            "parse": ["faculty_parser"],
            "post": ["normalize", "dedup", "statistics"],
            "store": ["jsonl_store"],
            "present": [],
        })

    return config


if __name__ == "__main__":
    import sys

    preset_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if preset_arg == "--list":
        for p in list_presets():
            print(p)
    else:
        result = run_editor(preset_arg)
        print("\n── 生成结果 ──")
        print(json.dumps(result, indent=2, ensure_ascii=False))
