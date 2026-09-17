#!/usr/bin/env python3
"""Offline acceptance runner. Prints a Chinese report; never crawls websites.

Run from any directory: python scripts/acceptance.py
All subprocesses run in a private workspace; pytest also installs network and
checked-in data/config write guards in tests/conftest.py.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = ("services", "storage", "spiders.engine", "security", "utils.http")


def snapshot():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for directory in (ROOT / "config", ROOT / "data")
            for p in directory.rglob("*")
            if p.is_file() and p.suffix != ".pyc" and "__pycache__" not in p.parts}


def main():
    before = snapshot()
    failed = False
    with tempfile.TemporaryDirectory(prefix="crawler-acceptance-") as temporary:
        work = Path(temporary)
        env = {**os.environ, "PYTHONPATH": str(ROOT), "PYTHONUTF8": "1",
               "PYTHONPYCACHEPREFIX": str(work / "pycache"),
               "COVERAGE_FILE": str(work / ".coverage")}
        files = [ROOT / "main.py", ROOT / "api/server.py", ROOT / "config/loader.py"]
        for directory in ("services", "storage", "security", "spiders", "utils"):
            files.extend((ROOT / directory).glob("*.py"))
        coverage = work / "coverage.json"
        commands = [
            [sys.executable, "-m", "py_compile", *map(str, files)],
            [sys.executable, str(ROOT / "main.py"), "--help"],
            [sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q", "-p", "no:cacheprovider",
             "-o", "addopts=", *["--cov=" + name for name in CORE],
             "--cov-report=term", "--cov-report=json:" + str(coverage)],
        ]
        print("# 离线集成验收报告\n")
        for command in commands:
            print("实际命令：", subprocess.list2cmdline(command), flush=True)
            result = subprocess.run(command, cwd=work, env=env, text=True,
                                    encoding="utf-8", errors="replace", capture_output=True)
            print(result.stdout)
            print(result.stderr)
            print("结果：", "通过" if result.returncode == 0 else "失败", result.returncode)
            failed |= result.returncode != 0
        if coverage.exists():
            data = json.loads(coverage.read_text(encoding="utf-8"))
            for filename, details in data["files"].items():
                summary = details["summary"]
                percent = summary["percent_covered"]
                print(f"核心模块 {filename}：{percent:.2f}%")
                failed |= percent < 80
        else:
            print("失败：缺少覆盖率文件")
            failed = True
    unchanged = before == snapshot()
    print("真实 config/data 内容检查：", "通过，未改动" if unchanged else "失败，发生改动")
    diff = subprocess.run(["git", "diff", "--check"], cwd=ROOT, capture_output=True, text=True)
    print("git diff --check：", "通过" if diff.returncode == 0 else "失败")
    print(diff.stdout, diff.stderr)
    print("测试总数、失败和跳过理由见 pytest 原始输出；不隐藏失败、不设置 xfail。")
    print("Flask 模拟 API、双源并发、JSONL/Excel、resume/retry 包含在完整测试套件中。")
    print("未跑真实采集、真实网站验证、真实浏览器、真实 PDF 下载及真实 DNS。")
    return int(failed or not unchanged or diff.returncode != 0)


if __name__ == "__main__":
    raise SystemExit(main())
