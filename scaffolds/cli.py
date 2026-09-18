# -*- coding: utf-8 -*-
"""Scaffolds CLI — 生成插件包骨架。

用法：
    python -m scaffolds.cli new spider <name>
    python -m scaffolds.cli new processor <name>
    python -m scaffolds.cli new storage <name>
    python -m scaffolds.cli new presenter <name>
    python -m scaffolds.cli new ui <name>
    python -m scaffolds.cli new template <name>
"""

import argparse
import sys
from pathlib import Path

from scaffolds.generator import (
    generate_plugin,
    VALID_KINDS,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scaffolds.cli",
        description="V3.0 插件脚手架生成器",
    )
    sub = parser.add_subparsers(dest="command")

    new_parser = sub.add_parser("new", help="生成新插件包")
    new_parser.add_argument(
        "kind",
        choices=VALID_KINDS,
        help="插件类型: spider|processor|storage|presenter|ui|template",
    )
    new_parser.add_argument("name", help="插件名称 (snake_case)")
    new_parser.add_argument(
        "--output-dir",
        "-o",
        default=None,
        help="输出目录 (默认: tests/fixtures/generated_plugin/<name>)",
    )
    new_parser.add_argument(
        "--author",
        default="developer",
        help="作者名 (默认: developer)",
    )

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "new":
        try:
            result = generate_plugin(
                kind=args.kind,
                name=args.name,
                output_dir=args.output_dir,
                author=args.author,
            )
            print(f"[OK] 已生成 {args.kind} 插件: {args.name}")
            print(f"  目录: {result['output_dir']}")
            print(f"  文件: {', '.join(result['files'])}")
            return 0
        except ValueError as e:
            print(f"错误: {e}", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"意外错误: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
