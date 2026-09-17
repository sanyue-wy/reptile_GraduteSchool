#!/usr/bin/env python3
"""Local browser acceptance only: private files and synthetic HTTP transport.

python scripts/offline_preview.py --port 5099
No production configuration/data is copied. Stop with Ctrl-C to remove workspace.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def configure(root):
    os.chdir(root)
    for directory in ("config", "data/output", "data/raw", "data/cache", "data/candidates"):
        Path(directory).mkdir(parents=True, exist_ok=True)
    import config.loader as loader
    import config.plugins as plugins
    import storage.config_store as config_store
    import utils.progress as progress
    config = [{"university": "测试大学", "level": "双一流", "categories": [{
        "college": "机械学院", "category": "mechanical", "faculty": {
            "list_url": "https://offline.invalid/faculty", "list_type": "static_html",
            "list_item_selector": "li a", "list_name_selector": "title"},
        "notice": {"enabled": True, "school_code": "99999",
                   "entry_url": "https://yz.chsi.com.cn/zsml/", "template": "yzw_major", "major_codes": {}}}]}]
    school_path = Path(root) / "config/school_data.json"
    school_path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    loader.DEFAULT_CONFIG_PATH = loader._config_path = config_store.DEFAULT_CONFIG_PATH = school_path
    loader._config_cache = None
    plugins.PLUGIN_CONFIG_PATH = Path(root) / "config/plugins.json"
    plugins.EXT_PLUGIN_DIR = Path(root) / "plugins_ext"
    plugins._EXTERNAL_CACHE = {}
    progress._progress_tracker = None

    import requests
    def transport(self, method, url, **kwargs):
        if url == "https://offline.invalid/faculty":
            body = '<ul><li><a href="/teacher/1" title="张三">张三</a></li></ul>'
        elif url == "https://offline.invalid/teacher/1":
            body = '<div class="carrer"><div class="title"><span class="jsbt">张三</span>教授 博士生导师</div></div>'
        elif url == "https://yz.chsi.com.cn/zsml/rs/dws.do":
            items = [] if kwargs.get("data", {}).get("yjxkdm") != "0802" else [{
                "zdjs": "张三", "zydm": "080200", "zymc": "机械工程", "yjfxmc": "机器人", "nzsrsstr": "3", "xxfs": "1"}]
            body = json.dumps({"total": len(items), "data": items}, ensure_ascii=False)
        else:
            raise requests.ConnectionError("Offline preview refuses unregistered URL: " + url)
        response = requests.Response()
        response.url, response.status_code, response.encoding = url, 200, "utf-8"
        response._content = body.encode("utf-8")
        return response
    requests.Session.request = transport
    def denied(*args, **kwargs):
        raise RuntimeError("Outbound networking disabled in offline preview")
    # The server only accepts incoming connections. No crawler socket may connect.
    socket.create_connection = denied
    socket.socket.connect = denied
    socket.socket.connect_ex = denied
    socket.socket.sendto = denied
    from requests.adapters import HTTPAdapter
    HTTPAdapter.send = denied

    import api.server as server
    server.GLOBAL_CONFIG_PATH = Path(root) / "config/global.json"
    server._tasks.clear()
    # Browser/PDF plugins must never launch independent external networking here.
    from spiders import SPIDER_ENGINE_REGISTRY
    for name in ("js_render", "pdf_list"):
        SPIDER_ENGINE_REGISTRY[name].fetch = denied
    from pipelines.export import add_failure, export_failures
    export_failures([add_failure("preview-failure", "测试大学", "机械学院", "Source A",
                                "timeout", "离线演示失败记录", "https://offline.invalid/faculty")])
    return server.app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=5099)
    args = parser.parse_args()
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="crawler-browser-preview-") as root:
        try:
            app = configure(root)
            print("PRIVATE_WORKSPACE=" + root, flush=True)
            print(f"OFFLINE_PREVIEW=http://127.0.0.1:{args.port}", flush=True)
            app.run(host="127.0.0.1", port=args.port, threaded=True, use_reloader=False)
        finally:
            os.chdir(original_cwd)


if __name__ == "__main__":
    main()
