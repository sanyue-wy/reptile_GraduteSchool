# -*- coding: utf-8 -*-
"""闭环补全批次 G2 的接口回归测试。

覆盖三条已确认的缺陷/缺失：
  1. GET /api/plugins/errors  —— 后端原本完全缺失（必现 404）
  2. GET /api/outputs/serve  —— 后端原本完全缺失（必现 404），且涉及路径穿越
  3. GET /api/failures/grouped —— 默认 status="active"，而 failures.json 里
     记录全部为 "resolved"，导致分组视图对真实数据恒为空（HTTP 200，前端回退分支
     永不触发）。本文件锁住"默认不过滤"的语义。
"""

import json
from pathlib import Path

import pytest

import api.server as server
from api.server import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def stable_preview_secret(monkeypatch):
    """令牌密钥固定，签发与校验在同一用例内自洽。"""
    monkeypatch.setitem(app.config, "PREVIEW_TOKEN_SECRET", "g2-test-secret")


def _write_plugin_error(name: str, payload: dict) -> Path:
    errors_dir = Path("data/output/plugin_errors")
    errors_dir.mkdir(parents=True, exist_ok=True)
    path = errors_dir / f"{name}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


# ------------------------------------------------------------------
# 1. GET /api/plugins/errors
# ------------------------------------------------------------------

class TestPluginErrorsEndpoint:

    def test_empty_data_returns_empty_object_not_404(self, client):
        """无数据时返回空对象，前端 Object.keys() 得 0，不会误判为有错误。"""
        response = client.get("/api/plugins/errors")

        assert response.status_code == 200
        body = response.get_json()
        assert body["errors"] == {}
        assert body["total"] == 0

    def test_errors_map_is_top_level_not_wrapped(self, client):
        """前端写死 `data.errors || data || {}`，errors 必须在顶层。"""
        _write_plugin_error("dedup", {
            "plugin_name": "dedup",
            "plugin_type": "processor",
            "error_type": "ValidationError",
            "error_message": "字段缺失",
            "traceback": "Traceback...",
            "timestamp": "2026-10-01T10:00:00+00:00",
        })

        body = client.get("/api/plugins/errors").get_json()

        assert isinstance(body["errors"], dict)
        assert "processor:dedup" in body["errors"]

    def test_error_fields_match_frontend_destructuring(self, client):
        """前端读 created_at/timestamp、code、message/error、suggestion/advice、traceback。"""
        _write_plugin_error("dedup", {
            "plugin_name": "dedup",
            "plugin_type": "processor",
            "error_type": "ValidationError",
            "error_message": "字段缺失",
            "traceback": "Traceback...",
            "timestamp": "2026-10-01T10:00:00+00:00",
        })

        entry = client.get("/api/plugins/errors").get_json()["errors"]["processor:dedup"][0]

        # 前端回退链 e.created_at || e.timestamp
        assert entry["created_at"] == "2026-10-01T10:00:00+00:00"
        assert entry["timestamp"] == "2026-10-01T10:00:00+00:00"
        # 前端 e.code || 'UNKNOWN' —— 后端原字段名是 error_type
        assert entry["code"] == "ValidationError"
        # 前端 e.message || e.error —— 后端原字段名是 error_message
        assert entry["message"] == "字段缺失"
        assert entry["error"] == "字段缺失"
        assert entry["traceback"] == "Traceback..."

    def test_name_filter_and_limit(self, client):
        _write_plugin_error("dedup", {
            "plugin_name": "dedup", "plugin_type": "processor",
            "error_type": "E", "error_message": "m", "timestamp": "t",
        })
        _write_plugin_error("stats", {
            "plugin_name": "stats", "plugin_type": "processor",
            "error_type": "E", "error_message": "m", "timestamp": "t",
        })

        body = client.get("/api/plugins/errors?name=dedup").get_json()

        assert list(body["errors"]) == ["processor:dedup"]

        limited = client.get("/api/plugins/errors?limit=1").get_json()
        assert all(len(v) <= 1 for v in limited["errors"].values())


    def test_error_keys_intersect_with_plugins_list(self, client):
        """
        验收断言：/api/plugins/errors 的分组键必须与 /api/plugins 列表项的键存在交集。

        这是抓住 B-2 bug 的唯一形态：
        - 真实写入方 pipeline/engine.py 产出的记录 plugin_type="pipeline"、plugin_name="stage:acquire:..."
        - 但前端按 (p.kind||p.plugin_type)+':'+(p.name||p.id) 查找
        - /api/plugins 的 item 只有 kind 字段（legacy kind: fetcher/processor/exporter/presenter...）
        - 修复后，engine 应写入 legacy kind（fetcher/processor/exporter/presenter）和实例名，
          使得 errors 的键能与 plugins 列表的键对齐。

        本用例写入一条 engine 修复后会产出的形态记录（legacy kind + 实例名），
        验证 /api/plugins/errors 的分组键能与 /api/plugins 列表对齐。
        """
        # 写入一条 engine 修复后会产出的形态记录（legacy kind + 实例名）
        _write_plugin_error("fetcher_static_html", {
            "plugin_name": "static_html",
            "plugin_type": "fetcher",
            "error_type": "FetchError",
            "error_message": "Connection timeout",
            "traceback": "Traceback...",
            "timestamp": "2026-10-01T10:00:00+00:00",
        })

        # 获取 errors 分组键
        errors_body = client.get("/api/plugins/errors").get_json()
        error_keys = set(errors_body.get("errors", {}).keys())

        # 获取 plugins 列表并按前端逻辑计算键
        plugins_body = client.get("/api/plugins").get_json()
        plugins_items = plugins_body.get("items", [])
        plugin_keys = set()
        for p in plugins_items:
            kind = p.get("kind") or p.get("plugin_type") or ""
            name = p.get("name") or p.get("id") or ""
            if kind and name:
                plugin_keys.add(f"{kind}:{name}")

        # 交集必须非空——这是修复生效的唯一标志
        intersection = error_keys & plugin_keys
        assert intersection, (
            f"errors keys {sorted(error_keys)} 与 plugins keys {sorted(plugin_keys)} "
            f"交集为空。需在 pipeline/engine.py:_report_stage_errors 中补齐插件身份，"
            f"写入 legacy kind (fetcher/processor/exporter/presenter) 与实例名。"
        )


# ------------------------------------------------------------------
# 2. GET /api/outputs/serve
# ------------------------------------------------------------------

class TestOutputsServeEndpoint:

    @staticmethod
    def _make_output(run_id: str, name: str = "report.html") -> Path:
        target = Path("data/runs") / run_id / "outputs" / "out_1" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("<html><body>ok</body></html>", encoding="utf-8")
        return target

    def test_missing_path_returns_400(self, client):
        assert client.get("/api/outputs/serve").status_code == 400

    def test_valid_token_serves_managed_output(self, client):
        target = self._make_output("run_ok")
        token = server.mint_preview_token("run_ok")

        response = client.get(
            f"/api/outputs/serve?path={target}&token={token}"
        )

        assert response.status_code == 200
        assert b"ok" in response.data
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_missing_or_wrong_token_returns_403(self, client):
        target = self._make_output("run_auth")

        assert client.get(f"/api/outputs/serve?path={target}").status_code == 403
        assert client.get(
            f"/api/outputs/serve?path={target}&token=garbage"
        ).status_code == 403

    def test_token_bound_to_one_run_cannot_read_another(self, client):
        target = self._make_output("run_secret")
        foreign_token = server.mint_preview_token("run_other")

        response = client.get(f"/api/outputs/serve?path={target}&token={foreign_token}")

        assert response.status_code == 403

    def test_expired_token_returns_403(self, client):
        target = self._make_output("run_expired")
        expired = server.mint_preview_token("run_expired", ttl_seconds=-10)

        response = client.get(f"/api/outputs/serve?path={target}&token={expired}")

        assert response.status_code == 403
        assert server.verify_preview_token(expired, "run_expired") is False

    def test_tampered_signature_returns_403(self, client):
        target = self._make_output("run_tamper")
        body, signature = server.mint_preview_token("run_tamper").split(".")

        response = client.get(
            f"/api/outputs/serve?path={target}&token={body}.{'0' * len(signature)}"
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("raw_path", [
        "../../../config/school_data.json",
        "data/raw/leak.txt",
        "C:/Windows/win.ini",
        "/etc/passwd",
    ])
    def test_paths_outside_managed_outputs_are_rejected(self, client, raw_path):
        """越界路径 403，且响应体不回显真实文件系统路径。"""
        token = server.mint_preview_token("run_traverse")

        response = client.get(f"/api/outputs/serve?path={raw_path}&token={token}")

        assert response.status_code == 403
        body = response.get_data(as_text=True)
        assert "runs" not in body and "config" not in body

    def test_run_store_dir_is_rejected(self, client):
        """runs/<run_id>/store/ 与 outputs/ 同级，不属于成品目录。"""
        leak = Path("data/runs/run_store/store/x.html")
        leak.parent.mkdir(parents=True, exist_ok=True)
        leak.write_text("secret", encoding="utf-8")
        token = server.mint_preview_token("run_store")

        response = client.get(f"/api/outputs/serve?path={leak}&token={token}")

        assert response.status_code == 403

    def test_symlink_escaping_outputs_is_rejected(self, client):
        """符号链接指向目录外时，resolve() 后必须仍被拒绝。"""
        target = self._make_output("run_link")
        outside = Path("data/output/outside.html")
        outside.parent.mkdir(parents=True, exist_ok=True)
        outside.write_text("outside", encoding="utf-8")
        link = target.parent / "link.html"
        try:
            link.symlink_to(outside.resolve())
        except (OSError, NotImplementedError):
            pytest.skip("当前平台不支持创建符号链接")
        token = server.mint_preview_token("run_link")

        response = client.get(f"/api/outputs/serve?path={link}&token={token}")

        assert response.status_code == 403

    def test_unsupported_type_returns_403(self, client):
        target = Path("data/runs/run_bin/outputs/out_1/payload.exe")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"MZ")
        token = server.mint_preview_token("run_bin")

        response = client.get(f"/api/outputs/serve?path={target}&token={token}")

        assert response.status_code == 403

    def test_missing_file_returns_404(self, client):
        token = server.mint_preview_token("run_missing")

        response = client.get(
            f"/api/outputs/serve?path=data/runs/run_missing/outputs/o/gone.html&token={token}"
        )

        assert response.status_code == 404


# ------------------------------------------------------------------
# 3. GET /api/failures/grouped 默认 status 的回归锁
# ------------------------------------------------------------------

class TestFailuresGroupedDefaultStatus:

    @pytest.fixture
    def resolved_only_failures(self, monkeypatch):
        """真实数据形态：failures.json 里 2330 条 status 全为 resolved。"""
        records = [
            {"id": f"f{i}", "status": "resolved", "error_type": "http_error",
             "url": f"https://a{i % 2}.edu.cn/x", "school": f"大学{i}",
             "occurred_at": f"2026-09-{i + 1:02d}T00:00:00"}
            for i in range(4)
        ]
        monkeypatch.setattr(server, "load_failures", lambda: list(records))
        return records

    def test_default_has_no_status_filter(self, client, resolved_only_failures):
        """不传 status 时必须返回全部记录，而不是恒空。"""
        response = client.get("/api/failures/grouped")

        assert response.status_code == 200
        data = response.get_json()["data"]
        assert data["total"] == len(resolved_only_failures)
        assert data["grouped"], "全部为 resolved 的真实数据下分组视图不得为空"
        assert data["group_count"] == 2  # a0.edu.cn / a1.edu.cn 两个域名

    def test_explicit_status_filter_still_works(self, client, resolved_only_failures):
        """显式过滤能力保留：只看 active 应为空，只看 resolved 应全量。"""
        active = client.get("/api/failures/grouped?status=active").get_json()["data"]
        resolved = client.get("/api/failures/grouped?status=resolved").get_json()["data"]

        assert active["total"] == 0
        assert active["grouped"] == []
        assert resolved["total"] == len(resolved_only_failures)
        assert resolved["grouped"]

    def test_group_shape_matches_frontend(self, client, resolved_only_failures):
        """console/failures.html 按 key/label/error_type/domain/count 等字段渲染。"""
        group = client.get("/api/failures/grouped").get_json()["data"]["grouped"][0]

        for field in ("key", "label", "error_type", "domain", "count",
                      "first_seen", "last_seen", "sample_url", "sample_schools"):
            assert field in group


# ------------------------------------------------------------------
# 4. 预览链路：运行状态需投影 outputs 并签发令牌
# ------------------------------------------------------------------

class TestRunStatusPreviewBridge:

    def test_run_status_exposes_outputs_and_preview_token(self, client):
        run_id = "run_preview_bridge"
        output = Path("data/runs") / run_id / "outputs" / "out_1" / "page.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("<html></html>", encoding="utf-8")
        result_file = Path("data/runs") / run_id / "result.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(json.dumps({"run_id": run_id, "status": "succeeded"}), encoding="utf-8")

        data = client.get(f"/api/pipeline/runs/{run_id}").get_json()["data"]

        assert [o["path"] for o in data["outputs"]] == [str(output)]
        assert data["outputs"][0]["output_format"] == "html"
        assert server.verify_preview_token(data["preview_token"], run_id)
        assert data["preview_url"].startswith("/runtime/preview.html?run_id=")

    def test_run_status_rejects_bogus_token(self, client):
        run_id = "run_bogus_token"
        result_file = Path("data/runs") / run_id / "result.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

        assert client.get(
            f"/api/pipeline/runs/{run_id}?token=nonsense"
        ).status_code == 403

    def test_run_status_payload_is_stable_across_polls(self, client):
        """console/api.js 的 hasStateChanged() 用 JSON.stringify 全量比对判断是否有新状态。

        若 preview_token 每次轮询都变，这个判断恒为 true，运行结束后仍每 2 秒触发
        一次全量重渲染。这里锁住"同一 run 的令牌在有效期内不变"。
        """
        run_id = "run_poll_stability"
        result_file = Path("data/runs") / run_id / "result.json"
        result_file.parent.mkdir(parents=True, exist_ok=True)
        result_file.write_text(
            json.dumps({"run_id": run_id, "status": "succeeded"}), encoding="utf-8"
        )

        first = client.get(f"/api/pipeline/runs/{run_id}").get_json()
        second = client.get(f"/api/pipeline/runs/{run_id}").get_json()

        assert first == second

    def test_outputs_are_also_exposed_at_top_level_for_preview_html(self, client):
        """preview.html:60 读 `data.outputs`，不解包 {"code","data"} 信封。

        console/api.js:41 与 task-config.html:221 都写的是 `data.data || data`，
        只有 preview.html 没有。若 outputs 只放在信封内，预览页恒显
        "Output not found in run."，iframe 永远加载不出来。
        """
        run_id = "run_preview_toplevel"
        output = Path("data/runs") / run_id / "outputs" / "out_1" / "page.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("<html></html>", encoding="utf-8")
        result_file = Path("data/runs") / run_id / "result.json"
        result_file.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

        body = client.get(f"/api/pipeline/runs/{run_id}").get_json()

        # preview.html 的读法：data.outputs
        assert [o["path"] for o in body["outputs"]] == [str(output)]
        # console/api.js 的读法：data.data || data
        assert body["data"]["outputs"] == body["outputs"]


# ------------------------------------------------------------------
# 5. 其余端点的响应形状对齐（任务 4 的审计结论）
# ------------------------------------------------------------------

class TestAuditedShapeFixes:

    def test_plugins_list_exposes_top_level_items(self, client):
        """console/plugins.html:234 的解包链会停在 data.data（对象）上。

        `data.plugins || data.items || data.data` —— 只有补上顶层 items 才能让
        allPlugins 拿到数组，否则插件管理页恒显 "No plugins found"。
        """
        body = client.get("/api/plugins").get_json()

        assert isinstance(body["items"], list)
        assert body["items"], "插件列表不应为空"
        # dashboard/api.js 的 apiCall 只取 json.data，该路径不能受影响
        assert body["data"]["items"] == body["items"]

    def test_failures_echoes_pagination_fields(self, client, monkeypatch):
        """dashboard/failures.html:199-204 用 data.page / data.page_size 算分页。

        后端此前只返回 {total, summary, items}，页面会渲染 "显示 NaN-NaN"。
        Mock 分支带这两个键，所以只有连真实后端时才暴露。
        """
        records = [
            {"id": f"f{i}", "status": "resolved", "error_type": "http_error",
             "url": "https://a.edu.cn/x", "occurred_at": "2026-09-01T00:00:00"}
            for i in range(5)
        ]
        monkeypatch.setattr(server, "load_failures", lambda: list(records))

        data = client.get("/api/failures?page=2&page_size=2").get_json()["data"]

        assert data["page"] == 2
        assert data["page_size"] == 2
        assert data["total"] == 5
        assert len(data["items"]) == 2

    def test_run_id_path_traversal_is_rejected(self, client):
        """run_id 参与 data/runs/<run_id>/ 的路径拼接，必须挡掉 ../ 载荷。

        Werkzeug 在路由匹配之后才 unquote 路径段，%2F 会还原成 "/"。
        这里只断言"绝不返回 200 且不回显数据"：具体的 400 / 404 / 重定向取决于
        客户端与 Werkzeug 对 "." 段的归一化时机，不是本测试要锁的语义。
        """
        for payload in ("..", "%2e%2e%2f%2e%2e%2fetc", "a%2fb", "a%2f..%2f..%2fetc"):
            response = client.get(f"/api/pipeline/runs/{payload}")
            assert response.status_code != 200, payload
            assert "items" not in response.get_data(as_text=True), payload
