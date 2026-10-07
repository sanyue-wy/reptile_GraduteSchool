#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Processor 插件状态诊断脚本"""

import json
import inspect
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from plugin_manager import loader
from plugins.base import ParserPlugin, RecordProcessorPlugin


def main():
    print("=" * 60)
    print("Processor 插件诊断报告")
    print("=" * 60)

    # 1. plugins/processors 目录是否存在；若存在，列出所有子目录
    print("\n[1] plugins/processors 目录结构:")
    processors_dir = Path("plugins/processors")
    if processors_dir.exists():
        print(f"  目录存在: {processors_dir}")
        subdirs = [d.name for d in processors_dir.iterdir() if d.is_dir() and not d.name.startswith("_")]
        print(f"  子目录 ({len(subdirs)} 个): {sorted(subdirs)}")
    else:
        print(f"  目录不存在: {processors_dir}")
        subdirs = []

    # 2. inspect.signature(loader.scan_plugin_dirs) 的签名
    print("\n[2] loader.scan_plugin_dirs 签名:")
    sig = inspect.signature(loader.scan_plugin_dirs)
    print(f"  {sig}")

    # 3. 用 loader.scan_plugin_dirs("plugins") 扫描出的 processor 数量与每个的 name / version / min_core_version / license
    print("\n[3] loader.scan_plugin_dirs 扫描结果:")
    descriptors, warnings, errors = loader.scan_plugin_dirs(Path("plugins"))

    processor_descs = [d for d in descriptors if d.plugin_type == "processor"]
    print(f"  识别为 processor 的插件数量: {len(processor_descs)}")

    for desc in sorted(processor_descs, key=lambda x: x.name):
        print(f"  - {desc.name}: version={desc.version}, min_core_version={desc.min_core_version}, license={desc.license or '(空)'}, input_schema={desc.input_schema}, output_schema={desc.output_schema}, entry_point={desc.entry_point}")

    if warnings:
        print(f"  告警 ({len(warnings)} 条):")
        for w in warnings:
            print(f"    - {w}")
    if errors:
        print(f"  错误 ({len(errors)} 条):")
        for e in errors:
            print(f"    - {e}")

    # 4. 兜底：遍历 plugins/**/metadata.json，统计 plugin_type == "processor" 的条目
    print("\n[4] 兜底扫描: 遍历所有 metadata.json 中 plugin_type == processor 的条目:")
    metadata_processors = []
    for meta_path in Path("plugins").rglob("metadata.json"):
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if data.get("plugin_type") == "processor":
                metadata_processors.append((meta_path, data))
        except Exception as e:
            print(f"  读取失败 {meta_path}: {e}")

    print(f"  metadata.json 中声明为 processor 的条目: {len(metadata_processors)}")
    for meta_path, data in sorted(metadata_processors, key=lambda x: x[1].get("name", "")):
        print(f"  - {meta_path.parent.name}: name={data.get('name')}, version={data.get('version')}, plugin_type={data.get('plugin_type')}, input_schema={data.get('input_schema')}, output_schema={data.get('output_schema')}, entry_point={data.get('entry_point')}")

    # 5. 对每个 processor 插件，打印其类的 MRO 前 3 项，确认是否继承 ParserPlugin / RecordProcessorPlugin
    print("\n[5] MRO 继承链检查 (每个 processor 插件的类 MRO 前 3 项):")
    for desc in sorted(processor_descs, key=lambda x: x.name):
        entry = desc.entry_point
        if ":" in entry:
            module_path, class_name = entry.split(":", 1)
            try:
                module = __import__(module_path, fromlist=[class_name])
                cls = getattr(module, class_name)
                mro = cls.__mro__[:3]
                mro_names = [c.__name__ for c in mro]
                # 检查是否继承了 ParserPlugin 或 RecordProcessorPlugin
                inherits_parser = ParserPlugin in cls.__mro__
                inherits_record_processor = RecordProcessorPlugin in cls.__mro__
                inherits_base = mro_names[0] != "object"  # 非空
                status = []
                if inherits_parser:
                    status.append("ParserPlugin")
                if inherits_record_processor:
                    status.append("RecordProcessorPlugin")
                if not inherits_parser and not inherits_record_processor:
                    status.append("❌ 未继承中间基类 (仅 BasePlugin 或 object)")
                print(f"  - {desc.name}: MRO={mro_names} -> {' / '.join(status)}")
            except Exception as e:
                print(f"  - {desc.name}: 导入失败 - {e}")

    # 额外：检查 metadata.json 中声明为 processor 但 loader 未识别的
    print("\n[6] 对比: metadata.json 声明为 processor 但 loader 未识别的插件:")
    loader_names = {d.name for d in processor_descs}
    meta_names = {data.get("name") for _, data in metadata_processors}
    missed = meta_names - loader_names
    if missed:
        for name in sorted(missed):
            print(f"  - {name}: loader 未识别 (可能 plugin_type 与目录不匹配、entry_point 无效等)")
    else:
        print("  无遗漏")

    print("\n" + "=" * 60)
    print("诊断完成")
    print("=" * 60)

    return {
        "processor_dirs": subdirs,
        "loader_processor_count": len(processor_descs),
        "metadata_processor_count": len(metadata_processors),
        "loader_names": sorted([d.name for d in processor_descs]),
        "metadata_names": sorted([data.get("name") for _, data in metadata_processors]),
    }


if __name__ == "__main__":
    main()