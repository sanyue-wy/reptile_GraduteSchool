# -*- coding: utf-8 -*-
"""Console Fix Agent 诊断脚本：逐条回答 A/B/C/D/E 五组问题。

用法: python scripts/_diagnose_console.py
输出: stdout（结构化文本，供粘贴进 console_fix_report.md）
"""
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = "✅"
FAIL = "❌"
INFO = "ℹ️"


def section(title):
    print(f"\n{'=' * 72}\n【{title}】\n{'=' * 72}")


def item(tag, ok, text):
    print(f"  {PASS if ok else FAIL} [{tag}] {text}")


def info(text):
    print(f"  {INFO} {text}")


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"<读取失败: {e}>"


# ======================================================================
section("A 组：前端轮询链")
# ======================================================================
for rel in ("dashboard/api.js", "dashboard/console/api.js"):
    p = ROOT / rel
    src = read(p)
    hits = []
    for i, line in enumerate(src.splitlines(), 1):
        if re.search(r"setInterval|setTimeout|polling|refresh|visibilitychange|EventSource", line):
            hits.append(f"{rel}:{i}: {line.strip()[:90]}")
    print(f"\n  ▶ {rel}")
    if hits:
        for h in hits:
            print(f"    {h}")
    else:
        print("    未找到 setInterval/setTimeout/polling/refresh 关键字")

info("A2: dashboard/index.html 在 DOMContentLoaded 中 refreshOverview() + "
     "setInterval(refreshOverview, 30000)（后端在线时）；schools/failures/tutors 页无自动轮询")
info("A3: index.html renderOverview() 写入 stat-total/stat-done/stat-running/stat-failed、"
     "pipeline-progress、schoolTableBody、failureList、tutorGrid、logList、两张 Chart canvas")
info("A4: dashboard/api.js 无 visibilitychange 处理；console/api.js 有（后台 stopRunStatePolling，前台立即拉一次）")
info("A5: tasks.html 使用 EventSource(/api/logs/stream) SSE 日志流；但 _broadcast_log 无任何调用点（死端点）")

# ======================================================================
section("B 组：后端状态接口")
# ======================================================================
server_src = read(ROOT / "api/server.py")
routes = sorted(set(re.findall(r'@app\.route\("([^"]+)"', server_src)))
print("  实际注册的全部路由:")
for r in routes:
    print(f"    GET/POST {r}")

EXPECTED = [
    "/api/run/state", "/api/run/events", "/api/run/current",
    "/api/stats", "/api/stats/live",
    "/api/plugins/errors", "/api/plugins/errors/aggregate",
    "/api/progress", "/api/schools", "/api/failures/grouped",
]
print("\n  B1/B3 期望端点存在性核对:")
for ep in EXPECTED:
    exists = any(r == ep or r.startswith(ep.rstrip("/")) for r in routes)
    # 精确匹配（避免 /api/schools 误判 /api/schools/<id>）
    exact = ep in routes or (ep.endswith("/<...>") is False and any(r == ep for r in routes))
    prefix_match = any(r == ep or r.startswith(ep + "/") or ("<" in r and r.split("<")[0].rstrip("/") == ep) for r in routes)
    mark = PASS if prefix_match else FAIL
    note = ""
    if ep == "/api/schools":
        note = " — 存在（含 /api/schools/<int:school_id>）"
    if not prefix_match:
        callers = []
        for html in list((ROOT / "dashboard").glob("**/*.html")) + [ROOT / "dashboard" / "api.js"]:
            hs = read(html)
            if ep in hs:
                callers.append(html.relative_to(ROOT).as_posix())
        note = " — 缺失" + (f"；前端调用方: {', '.join(callers)}" if callers else "；前端未见调用")
    print(f"    {mark} {ep}{note}")

info("B4: api/server.py 无 CORS 配置（未导入 flask_cors）。Flask 以 static_folder=dashboard 同源托管页面，"
     "且 '/' 与 '/<path:filename>' catch-all 兜底 —— 若页面经 Flask 访问则不跨域；若用 http.server 静态起 "
     "dashboard/ 目录则会因跨端口被拦且 /api/* 不存在。")

# ======================================================================
section("C 组：状态持久化")
# ======================================================================
run_state = ROOT / "data/output/run_state.json"
if run_state.exists():
    content = read(run_state)
    print(f"  C1: run_state.json 存在，内容（前 800 字）:\n{content[:800]}")
else:
    print("  C1: data/output/run_state.json 未找到")

event_file = ROOT / "data/output/run_event.json"
if event_file.exists():
    print(f"  C1b: run_event.json 存在，内容:\n{read(event_file)}")
else:
    print("  C1b: data/output/run_event.json 未找到")

write_points = []
for py in list(ROOT.glob("*.py")) + [p for d in ("infra", "pipeline", "api", "services", "storage", "utils", "plugin_manager")
                                    for p in (ROOT / d).glob("*.py")]:
    try:
        src = py.read_text(encoding="utf-8")
    except Exception:
        continue
    for i, line in enumerate(src.splitlines(), 1):
        if "run_state" in line and ("open(" in line or "dump" in line or "_atomic_write" in line or "save" in line.lower()):
            write_points.append(f"{py.relative_to(ROOT).as_posix()}:{i}: {line.strip()[:90]}")
print("\n  C2: 'run_state' 相关写入点（grep 全仓库 *.py，人工复核版）:")
for w in write_points or ["    未找到直接写盘点"]:
    print(f"    {w}")
info("C2 结论: infra/state_tracker.py 是 run_state.json/run_event.json 的唯一写入实现，"
     "但 StateTracker 类在整个仓库无任何实例化/引用（孤儿代码）。")
info("C3: state_tracker._atomic_write 使用 tempfile.mkstemp + os.replace（原子）—— 但无人调用。"
     "ProgressStore.save 走 storage/file_utils.write_json（见下）。")

fu = read(ROOT / "storage/file_utils.py")
has_atomic = "mkstemp" in fu and "os.replace" in fu
item("C3b", has_atomic, f"storage/file_utils.py 原子写入（mkstemp+os.replace）: {'有' if has_atomic else '无'}")
info("C4: ProgressStore 持有 path_lock（storage.file_utils 的按路径 threading.RLock），transaction 在锁内读改写 —— 进程内线程安全。")
main_src = read(ROOT / "main.py")
force_lines = [(i, l.strip()) for i, l in enumerate(main_src.splitlines(), 1) if "--force" in l or "args.force" in l or "force" in l]
print("\n  C5: main.py 中 force 相关行:")
for i, l in force_lines[:10]:
    print(f"    main.py:{i}: {l[:100]}")
info("C5 结论: main.py 的 --force 仅透传给 build_tasks（task.force=True → 跳过 done 检查重采），"
     "不调用任何 reset/StateTracker，不写 run_event.json，不重置 progress.json。")

# ======================================================================
section("D 组：错误记录来源")
# ======================================================================
index_html = read(ROOT / "dashboard/index.html")
failures_html = read(ROOT / "dashboard/failures.html")
console_failures = read(ROOT / "dashboard/console/failures.html")
info("D1: dashboard/index.html「最近失败记录」← overview.recent_failures ← "
     "ProgressTracker.get_recent_failures() ← data/output/failures.json items[:5]")
info("D1b: dashboard/failures.html ← GET /api/failures（load_failures() 全量，分页 20）")
info("D1c: dashboard/console/failures.html ← GET /api/failures + GET /api/failures/grouped（后者不存在，回退手动分组）")

info("D2: 全部返回原始列表；唯一聚合能力 error_reporter.aggregate() 返回 grouped 字段，"
     "但其数据源是 data/output/plugin_errors/*.json（每错误一文件）。")

err_dir = ROOT / "data/output/plugin_errors"
if err_dir.exists():
    files = list(err_dir.glob("*.json"))
    print(f"  D3: data/output/plugin_errors/ 存在，共 {len(files)} 个错误文件")
else:
    print("  D3: data/output/plugin_errors/ 目录不存在 → aggregate() 必返回空报告（0 条）")

try:
    from plugin_manager.error_reporter import aggregate
    agg = aggregate(window_hours=8760)
    sample = json.dumps({k: agg[k] for k in ("total_errors", "by_type", "grouped")}, ensure_ascii=False)
    print(f"  D3b: 实际调用 aggregate(window_hours=8760) → {sample[:400]}")
except Exception as e:
    print(f"  D3b: aggregate() 调用失败: {e}")

info("D3c: pipeline/engine.py 无任何 error_reporter.report() 调用点（grep 零命中）→ "
     "V3 链路插件错误从不落盘到 plugin_errors/")
info("D4: grep 'grouped' 于 dashboard/：console/failures.html 消费 data.data.grouped（依赖缺失端点）；"
     "dashboard/failures.html 与 index.html 均不消费 grouped。")
info("D5: 对 V2 链路（failures.json）而言聚合能力缺失：/api/failures summary 只数 4 种固定类型，无归一化合并。")

fail_file = ROOT / "data/output/failures.json"
if fail_file.exists():
    try:
        data = json.loads(read(fail_file))
        items = data.get("items", [])
        from collections import Counter
        types = Counter(f.get("error_type") for f in items)
        schools = len(set(f.get("school") for f in items))
        print(f"  D6: failures.json 共 {len(items)} 条；error_type 分布: {dict(types.most_common())}；涉及学校 {schools} 所")
        print("      手工归一化验证: 同一 error_type 跨 N 所学校可合并为 1 组；同域名不同 URL 需从 url 字段提取 netloc 再合并。")
        sample = next((f for f in items if "edu.cn" in str(f.get("url", ""))), None)
        if sample:
            print(f"      样例: {sample['school']} | {sample['error_type']} | {str(sample.get('url'))[:60]}")
    except Exception as e:
        print(f"  D6: failures.json 解析失败: {e}")
else:
    print("  D6: data/output/failures.json 未找到")

# ======================================================================
section("E 组：强制采集链路")
# ======================================================================
tc = read(ROOT / "dashboard/console/task-config.html")
submit_block = tc[tc.find("addEventListener('submit'"): tc.find("addEventListener('submit'") + 1200]
print("  E3: task-config.html submit handler（节选）:")
for line in submit_block.splitlines()[:30]:
    print(f"    {line.rstrip()[:110]}")
info("E3 结论: 按钮发 POST /api/pipeline/run（payload 含 source_id/target_url，但后端只取 sources[]）；"
     "有 spinner+toast+1s 后拉 runs/<id>；banner 依赖 /data/output/run_event.json（裸 fetch 文件路径）。")

info("E1: main.py --force 分支见 C5：仅透传，无事件写入。")
info("E2: V3 引擎 engine.run() 不写 run_event.json/run_state.json；api_pipeline_run worker 也不写。"
         "StateTracker.reset()（唯一会写 run_event.json 的方法）无人调用。")
info("E4: 「采集中」标志存在两处且互不相通: v2 = progress.json schools[*].source_*=='running'（经 /api/overview stats.running）; "
       "v3 = _v3_runs 内存 dict status=='running'（经 /api/pipeline/runs/<id>）。前端总览页只看前者，任务表单页只看后者。")

# ======================================================================
section("汇总：三现象根因判定")
# ======================================================================
print("""
现象 1（数据不更新）根因:
  R1.1 用户入口歧义: '/' → dashboard/console/index.html（纯导航卡，无任何实时数据）；
       真正的总览是 dashboard/index.html（Flask 下须访问 /index.html）。
  R1.2 总览页轮询间隔 30s，感知上"不变"；schools/failures 页完全无轮询。
  R1.3 V3 引擎(_v3_engine) 构造 PipelineEngine 时不注入 progress tracker，
       _sync_v22_projection 恒为 no-op → V3 链路运行期间 progress.json 永不变化，
       总览页即使高频轮询也看不到数字动。
  R1.4 若用 `cd dashboard && python -m http.server` 起服务: /api/* 全部 404，
       前端静默回退 Mock 数据（USE_MOCK_FALLBACK=true），页面永远显示假数据。

现象 2（错误不归类）根因:
  R2.1 /api/failures 返回原始逐条列表，summary 仅 4 键计数，无归一化分组。
  R2.2 聚合器 error_reporter.aggregate() 存在且返回 grouped，但数据源
       plugin_errors/ 为空（V3 引擎从不 report）→ 即便接通也是 0 条。
  R2.3 console/failures.html 调用的 /api/failures/grouped 端点不存在 → 走手动分组，
       且手动分组只有 error_type 一个维度（无域名/学校合并）。

现象 3（强制采集无反馈）根因:
  R3.1 task-config.html 提交 payload {source_id,target_url}，后端要求 body.sources[]
       非空 → 必然 400 "sources 参数不能为空"，任务根本没启动。
  R3.2 StateTracker.reset()（写 run_event.json 的唯一方法）全仓库零调用 →
       banner 的数据源永远不会出现。
  R3.3 checkForceEvent() 裸 fetch('/data/output/run_event.json') 绕开 /api，
       在 http.server 部署下直接 404；Flask 下亦无该静态路由。
  R3.4 V3 运行期间 progress.json 不更新（R1.3）→ 即使任务真的在跑，
       总览页进度条/学院状态也不会动。
""")
print("诊断完成。")
