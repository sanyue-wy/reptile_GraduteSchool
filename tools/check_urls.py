# -*- coding: utf-8 -*-
"""URL 预检脚本：验证 school_data.json 中所有 list_url 的域名可解析。

用法：python tools/check_urls.py
对每个 URL 做 DNS 解析（IDN → punycode），报告无法解析的条目。
在正式采集前运行，可提前发现 domain_kb 缺失或 URL 配置错误。
"""

import json
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def resolve(host: str) -> bool:
    """解析主机名（自动处理 IDN → punycode）。"""
    try:
        host.encode("idna")
    except (UnicodeError, UnicodeDecodeError):
        pass  # 已是 ASCII 或 idna 编码失败，直接尝试原始值
    try:
        socket.getaddrinfo(host, 443)
        return True
    except socket.gaierror:
        return False


def main() -> int:
    with open(ROOT / "config" / "school_data.json", encoding="utf-8") as f:
        school_data = json.load(f)

    bad = []
    total = 0
    for school in school_data:
        for cat in school["categories"]:
            fac = cat.get("faculty", {})
            url = fac.get("list_url", "")
            if not url or not fac.get("enabled", True):
                continue
            total += 1
            host = urlparse(url).hostname or ""
            if not host:
                bad.append((school["university"], cat["college"], url, "no hostname"))
                continue
            if any(ord(c) > 127 for c in host):
                bad.append((school["university"], cat["college"], url, "contains non-ASCII (needs domain_kb mapping)"))
            elif not resolve(host):
                bad.append((school["university"], cat["college"], url, "DNS resolution failed"))

    print(f"Checked {total} enabled URLs")
    if bad:
        print(f"\n{len(bad)} problems found:")
        for uni, college, url, reason in bad:
            print(f"  [{reason}] {uni} / {college}\n    {url}")
        return 1
    print("All URLs OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
