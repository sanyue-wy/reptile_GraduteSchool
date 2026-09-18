#!/usr/bin/env python3
"""Configuration migration script: V2.2 plugins.json → V3.0 pipeline.yaml + plugins.yaml.

Usage:
    python scripts/migrate_config.py --dry-run --report /tmp/migrate_report.txt
    python scripts/migrate_config.py --apply --backup-dir /tmp/backup
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


# 旧 kind → 新归属映射 (计划书 §6.1)
KIND_MAPPING = {
    "source": {"v3_category": "config", "note": "数据源/profile配置，describe结果转为来源配置"},
    "fetcher": {"v3_category": "spider", "note": "static_html 与旧 static_list 类名建立明确别名"},
    "parser": {"v3_category": "processor.parse", "note": "旧 raw_path/meta 接口经适配转换"},
    "processor": {"v3_category": "processor.post", "note": "旧 records/ctx 转换为批次协议"},
    "exporter": {"v3_category": "storage", "note": "jsonl/xlsx ID 和返回形状兼容"},
    "presenter": {"v3_category": "ui", "note": "旧页面导航另保留；组件与整页不是同一概念"},
    "utility": {"v3_category": "infra", "note": "受管基础服务或批准的 legacy 扩展"},
}


# 旧插件名称 → 新插件名称/实例映射
PLUGIN_NAME_MAPPING = {
    # fetcher → spider
    "static_list": {"new_name": "static_html", "v3_type": "spider", "params": {"max_pages": 20}},
    "ajax_api": {"new_name": "ajax_api", "v3_type": "spider", "params": {"max_pages": 20}},
    "js_render": {"new_name": "js_render", "v3_type": "spider", "params": {"max_pages": 10, "headless": True}},
    "pdf_list": {"new_name": "pdf_list", "v3_type": "spider", "params": {"max_pages": 20}},
    "yzw_api": {"new_name": "yzw_api", "v3_type": "spider", "params": {"max_pages": 50}},
    # parser → processor.parse
    "faculty_parser": {"new_name": "faculty_parser", "v3_type": "processor", "params": {"profile": "education.tutor.v1"}},
    "yzw_major_parser": {"new_name": "yzw_major_parser", "v3_type": "processor", "params": {"profile": "education.major.v1"}},
    # processor → processor.post
    "normalize": {"new_name": "normalize", "v3_type": "processor", "params": {}},
    "education_merge": {"new_name": "education_merge", "v3_type": "processor", "params": {"group_by": ["university", "college", "year"]}},
    "statistics": {"new_name": "statistics", "v3_type": "processor", "params": {"group_by": ["university"]}},
    # exporter → storage
    "jsonl_store": {"new_name": "jsonl_store", "v3_type": "storage", "params": {"format": "legacy_education_v1", "output_dir": "data/output"}},
    "xlsx_store": {"new_name": "xlsx_store", "v3_type": "storage", "params": {"format": "legacy_education_v1", "output_dir": "data/output"}},
    # presenter → ui/presenter
    "table_component": {"new_name": "table_component", "v3_type": "ui", "params": {}},
    "chart_component": {"new_name": "chart_component", "v3_type": "ui", "params": {}},
    "card_component": {"new_name": "card_component", "v3_type": "ui", "params": {}},
    "filter_component": {"new_name": "filter_component", "v3_type": "ui", "params": {}},
}


def load_old_plugins(json_path: Path) -> dict[str, Any]:
    """Load old plugins.json configuration."""
    if not json_path.exists():
        return {}
    with json_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def analyze_mapping(old_config: dict[str, Any]) -> dict[str, Any]:
    """Analyze old config and produce mapping report."""
    report = {
        "timestamp": datetime.now().isoformat(),
        "source_file": str(json_path) if "json_path" in locals() else "unknown",
        "mappings": [],
        "conflicts": [],
        "unmapped": [],
        "warnings": [],
    }

    plugins = old_config.get("plugins", [])
    for plugin in plugins:
        old_name = plugin.get("name", "")
        old_kind = plugin.get("kind", "")
        enabled = plugin.get("enabled", True)
        params = plugin.get("params", {})

        if not enabled:
            report["warnings"].append(f"Plugin {old_name} is disabled, skipping")
            continue

        mapping = PLUGIN_NAME_MAPPING.get(old_name)
        if mapping:
            report["mappings"].append({
                "old_name": old_name,
                "old_kind": old_kind,
                "new_name": mapping["new_name"],
                "v3_type": mapping["v3_type"],
                "params": {**mapping["params"], **params},  # new params as base, old params override
                "note": KIND_MAPPING.get(old_kind, {}).get("note", ""),
            })
        else:
            report["unmapped"].append({
                "old_name": old_name,
                "old_kind": old_kind,
                "params": params,
            })

    # Check for conflicts (duplicate new names)
    new_names = [m["new_name"] for m in report["mappings"]]
    seen = set()
    for name in new_names:
        if name in seen:
            report["conflicts"].append(f"Duplicate new plugin name: {name}")
        seen.add(name)

    return report


def generate_pipeline_yaml(report: dict[str, Any]) -> dict[str, Any]:
    """Generate pipeline.yaml from mapping report."""
    # Determine which processors are mapped
    processors = [m for m in report["mappings"] if m["v3_type"] == "processor"]
    spiders = [m for m in report["mappings"] if m["v3_type"] == "spider"]
    storages = [m for m in report["mappings"] if m["v3_type"] == "storage"]
    uis = [m for m in report["mappings"] if m["v3_type"] == "ui"]

    # Build sources - assume source_a uses first spider, source_b uses yzw if present
    sources = {}
    parse_steps = []

    # Find static_html spider for source_a
    static_spider = next((s for s in spiders if s["new_name"] == "static_html"), None)
    if static_spider:
        sources["source_a"] = {
            "acquire": "static_fetch",
            "parse": ["faculty_parse"],
            "required": True,
        }
        parse_steps.append("faculty_parse")

    # Find yzw_api spider for source_b
    yzw_spider = next((s for s in spiders if s["new_name"] == "yzw_api"), None)
    if yzw_spider:
        sources["source_b"] = {
            "acquire": "yzw_fetch",
            "parse": ["yzw_major_parse"],
            "required": False,
        }
        parse_steps.append("yzw_major_parse")

    # Build process steps
    process_steps = ["normalize_records", "merge_records", "statistics"]
    # Only include steps that have mappings
    available_processor_names = {p["new_name"] for p in processors}
    process_steps = [s for s in process_steps if s in available_processor_names]

    # Build store targets
    store_targets = []
    for storage in storages:
        store_targets.append({
            "instance": storage["new_name"] + "_output",
            "required": storage["new_name"] == "jsonl_store",
        })

    # Build present components
    present_components = [ui["new_name"] for ui in uis]

    return {
        "schema_version": 1,
        "pipeline": {
            "id": "education_default",
            "sources": sources,
            "process": {"steps": process_steps},
            "store": {"targets": store_targets},
            "present": {
                "required": False,
                "components": present_components,
            },
        },
    }


def generate_plugins_yaml(report: dict[str, Any]) -> dict[str, Any]:
    """Generate plugins.yaml from mapping report."""
    instances = {}

    for mapping in report["mappings"]:
        old_name = mapping["old_name"]
        new_name = mapping["new_name"]
        v3_type = mapping["v3_type"]
        params = mapping["params"]

        # Determine instance name
        if v3_type == "spider":
            instance_name = f"{new_name}_fetch" if new_name != "media_downloader" else "media_downloader"
        elif v3_type == "processor":
            instance_name = new_name
        elif v3_type == "storage":
            instance_name = f"{new_name}_output"
        elif v3_type == "ui":
            instance_name = new_name.replace("_component", "_view")
        else:
            instance_name = new_name

        # Plugin reference format: type:name
        plugin_ref = f"{v3_type}:{new_name}"

        instances[instance_name] = {
            "plugin": plugin_ref,
            "enabled": True,
            "params": params,
        }

    return {
        "schema_version": 1,
        "instances": instances,
    }


def write_yaml_atomic(path: Path, data: dict[str, Any]) -> None:
    """Write YAML atomically using tempfile + os.replace."""
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".yaml", delete=False, dir=path.parent
    ) as tmp:
        yaml.dump(data, tmp, allow_unicode=True, sort_keys=False, indent=2)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def main():
    parser = argparse.ArgumentParser(description="Migrate V2.2 plugins.json to V3.0 YAML configs")
    parser.add_argument("--source", default="config/plugins.json", help="Source plugins.json path")
    parser.add_argument("--pipeline-out", default="config/pipeline.yaml", help="Output pipeline.yaml path")
    parser.add_argument("--plugins-out", default="config/plugins.yaml", help="Output plugins.yaml path")
    parser.add_argument("--dry-run", action="store_true", help="Only analyze and report, don't write files")
    parser.add_argument("--report", help="Write migration report to this file")
    parser.add_argument("--apply", action="store_true", help="Apply migration (write YAML files)")
    parser.add_argument("--backup-dir", help="Backup directory for old configs")
    parser.add_argument("--force", action="store_true", help="Overwrite existing YAML files")

    args = parser.parse_args()

    global json_path
    json_path = Path(args.source)

    if not json_path.exists():
        print(f"Error: Source file not found: {json_path}", file=sys.stderr)
        return 1

    old_config = load_old_plugins(json_path)
    report = analyze_mapping(old_config)

    # Print summary
    print(f"Migration Analysis Report")
    print(f"=========================")
    print(f"Source: {json_path}")
    print(f"Mapped: {len(report['mappings'])} plugins")
    print(f"Unmapped: {len(report['unmapped'])} plugins")
    print(f"Conflicts: {len(report['conflicts'])}")
    print(f"Warnings: {len(report['warnings'])}")

    if report["unmapped"]:
        print("\nUnmapped plugins:")
        for u in report["unmapped"]:
            print(f"  - {u['old_name']} ({u['old_kind']})")

    if report["conflicts"]:
        print("\nConflicts:")
        for c in report["conflicts"]:
            print(f"  - {c}")

    if report["warnings"]:
        print("\nWarnings:")
        for w in report["warnings"]:
            print(f"  - {w}")

    # Write report if requested
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\nReport written to: {report_path}")

    if args.dry_run:
        print("\n--- DRY RUN: No files written ---")
        # Show generated YAML
        pipeline_yaml = generate_pipeline_yaml(report)
        plugins_yaml = generate_plugins_yaml(report)
        print("\n--- Generated pipeline.yaml ---")
        print(yaml.dump(pipeline_yaml, allow_unicode=True, sort_keys=False, indent=2))
        print("\n--- Generated plugins.yaml ---")
        print(yaml.dump(plugins_yaml, allow_unicode=True, sort_keys=False, indent=2))
        return 0

    if not args.apply:
        print("\nUse --apply to write files, or --dry-run for analysis only.")
        return 0

    # Check for existing files
    pipeline_out = Path(args.pipeline_out)
    plugins_out = Path(args.plugins_out)

    if pipeline_out.exists() and not args.force:
        print(f"Error: {pipeline_out} exists. Use --force to overwrite.", file=sys.stderr)
        return 1
    if plugins_out.exists() and not args.force:
        print(f"Error: {plugins_out} exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    # Backup old configs if requested
    if args.backup_dir:
        backup_dir = Path(args.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(json_path, backup_dir / f"plugins.json.{timestamp}.bak")
        if pipeline_out.exists():
            shutil.copy2(pipeline_out, backup_dir / f"pipeline.yaml.{timestamp}.bak")
        if plugins_out.exists():
            shutil.copy2(plugins_out, backup_dir / f"plugins.yaml.{timestamp}.bak")
        print(f"Backed up to: {backup_dir}")

    # Write new configs
    pipeline_yaml = generate_pipeline_yaml(report)
    plugins_yaml = generate_plugins_yaml(report)

    write_yaml_atomic(pipeline_out, pipeline_yaml)
    write_yaml_atomic(plugins_out, plugins_yaml)

    print(f"\nWritten: {pipeline_out}")
    print(f"Written: {plugins_out}")
    print("\nMigration complete. Next steps:")
    print("  1. Review generated YAML files")
    print("  2. Run: python -m pytest tests/ -q")
    print("  3. Test with: python scripts/migrate_config.py --dry-run --report /tmp/report.txt")

    return 0


if __name__ == "__main__":
    sys.exit(main())