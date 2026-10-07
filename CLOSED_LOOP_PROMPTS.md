# 闭环补全 · 并行窗口任务书（G1–G5）

> 用途：把 V3.0「合并签字后仍未闭环」的工作，拆成 **5 个互不重叠写集** 的窗口提示词。
> 每个窗口把对应小节整段复制进新窗口即可开工，**不需要读完整对话历史**。
>
> 生成时间：2026-10-01 · 基线提交 `7880629`（本地）· 分支 `Refactoring_code`

---

## 0. 为什么这样拆（解耦原理）

这 5 个窗口的**可写文件集合两两不相交**：

| 窗口 | 可写范围 | 与其他窗口的交集 |
|------|----------|------------------|
| G1 | `tests/browser/**`、`pytest.ini` | 无 |
| G2 | `api/server.py` | 无 |
| G3 | `.github/**`、`.gitignore` | 无 |
| G4 | `docs/**`（除 `INTERFACES.md`）、`CHANGELOG.md` | 无 |
| G5 | **不写任何生产代码**（只读 + 出报告） | 无 |

因此 5 个窗口可以**同时开工、同时提交、任意顺序合并**，不需要任何窗口等另一个窗口。
唯一的跨窗口依赖（G1 的测试要等 G2 的端点存在才全绿）由 **G5 独立验收**在最后统一裁决，
不阻塞前 4 个窗口各自的交付与提交。

> ⚠️ 本文件 `CLOSED_LOOP_PROMPTS.md` 对所有窗口**只读**，任何窗口不得修改。

---

## 1. 通用前言（复制到每个 G 窗口的开头）

```
你是一个独立工作窗口，代号 <G1|G2|G3|G4>，隶属 V3.0「闭环补全」批次。
你不了解本批次其他窗口的工作内容，也不需要知道——你们的可写文件集合互不重叠。

【仓库】c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool
【平台】Windows 11 / Git Bash / Python 3.12.7 / 分支 Refactoring_code

【项目】V3.0 通用网络数据采集平台，插件化架构（spider → processor → storage → presenter 四阶段）。
仓库有两套前端页面：
  A) 主面板 dashboard/{index,schools,failures,tutors,tasks,config}.html  + dashboard/api.js
  B) 管理台 dashboard/console/{index,plugins,failures,task-config,output-config}.html
     + dashboard/console/api.js
     + dashboard/runtime/preview.html

【已核实的环境事实——不要重新验证，直接采信】
1. 测试基线：python -m pytest tests/ -q --ignore=tests/integration  →  955 passed, 3 skipped, 0 failed
   ⚠️ 任何窗口都不许把这条数字弄低。改完必须重跑并贴出真实输出。
2. Playwright 1.62 已安装，Chromium 已下载且可无头启动。验证方式：
     from playwright.sync_api import sync_playwright
     with sync_playwright() as p: b=p.chromium.launch(); pg=b.new_page(); ...
3. 启动 Flask：python -m api.server --port <端口>   （static_folder 就是 dashboard/ 目录）
   每个窗口必须用自己的独立端口，避免互相抢占。
4. `python -m api.server --port 5000` 已实测可用；`/?view=console` 返回 200。
5. main.py 没有 --ui 参数（实测确认）。只有：
   --school --category --source --year --workers --force --resume --retry-failed --delay
   --max-retries --timeout --cooldown-threshold --cooldown-seconds --raw-dir --no-cache
   --cache-days --clear-cache --circuit-break-threshold --circuit-break-window --engine
6. contracts/ 与 docs/V3.0/INTERFACES.md 是**冻结契约**，任何窗口不得修改。

【通用红线】
- 严禁 git commit / git push / git checkout 等写操作。只读 git 可以。
- 严禁修改自己可写范围之外的任何文件（看到了也只报告，不动手）。
- 严禁为了让测试变绿而弱化断言、跳过用例、或往 try/except 里塞 AssertionError。
- 发现问题写进交付报告，不要顺手改别人的地盘。
- 交付时必须在报告里贴**真实命令输出**。没跑过的命令不许写成"已验证"。

【共享发现命令（只读，所有窗口跑同一条，得到同一份清单）】
这条命令枚举前端调用的全部 API 并与 Flask url_map 比对。各窗口靠它对齐口径，
**不需要彼此通信**——这是本批次解耦的关键机制。

python -c "
import re, glob, api.server as s
calls = {}
for f in glob.glob('dashboard/**/*.html', recursive=True) + glob.glob('dashboard/**/*.js', recursive=True):
    t = open(f, encoding='utf-8').read()
    for m in re.findall(r'''[\'\"](/api/[A-Za-z0-9_/<>.\$-]*)''', t):
        calls.setdefault(m, set()).add(f)
routes = set(r.rule for r in s.app.url_map.iter_rules())
missing = []
for url in sorted(calls):
    base = url.split('?')[0].rstrip('/')
    if '<' in base or base in routes: continue
    if any(r.startswith(base + '/<') for r in routes): continue
    missing.append((url, sorted(calls[url])))
print('scanned', len(calls), 'distinct calls; MISSING:', len(missing))
for url, files in missing: print('  ', url, '<-', files)
"

实测输出（2026-10-01，作为基准）：
scanned 20 distinct calls; MISSING: 2
   /api/outputs/serve <- ['dashboard\\runtime\\preview.html']
   /api/plugins/errors <- ['dashboard\\console\\plugins.html']
```
```

---

## 2. G1 · 浏览器验收套件

```
【窗口代号】G1
【可写范围】tests/browser/**  和  pytest.ini（仅允许追加一个 browser marker）
            除此之外一律只读。看到 api/server.py 有 bug 就报告，不要动。

【目标】把 docs/V3.0/tasks/progress.md 里挂了两个多月的两条「未完成」项真正关掉：
  1) W7 未完成：「浏览器验收（Playwright）：待启动临时 Flask 实例 + fixture 数据验证四组件渲染」
  2) W7 未完成：「HTML 成品 file:// 独立打开截图验证」
  交付一套常驻的 Playwright 验收测试，让这两项以后不会再退回未完成状态。

【交付物】
tests/browser/conftest.py
  - session 级 fixture：用 werkzeug 启动真实 app（api.server:app）在空闲端口，
    轮询 /api/healthz 直到 200 再放行，session 结束关闭。
    注意：data/output/ 是 gitignore 的，全新克隆时可能是空的，fixture 不得假设有采集结果。
  - page fixture：挂 console/pageerror/requestfailed/response 监听器，
    收集「未捕获 JS 异常」和「同源 >=400 的响应」，在 teardown 里断言为空。
    ★ 这是整套测试里价值最高的一条断言——G2 要修的两个 404 正是靠它发现的。
    必须证明它真的会失败（见下方「必须自证」）。
  - Playwright 未安装 / Chromium 未下载时 clean skip 并给出可操作提示，
    绝不能让整套测试在没有浏览器的机器上 error。

tests/browser/test_console_pages.py
  管理台 5 页 + 主面板 6 页各一个冒烟+契约测试。
  断言：加载成功、title 非空、无未捕获 JS 异常、无同源 4xx/5xx、
        页面主容器确实渲染出了子节点（空壳不算通过）。
  全部打 @pytest.mark.browser。

tests/browser/test_api_contract.py
  对前端调用的每一个端点断言它在 app.url_map 里存在、且返回非 5xx。
  ★ 必须读 url_map，不能只靠发请求——这样端点被删时测试才会失败。
  必含 /api/plugins/errors 与 /api/outputs/serve（当前后端都没有，是已知的红灯）。

tests/browser/test_responsive.py
  375x812 与 1440x900 两个视口跑主页面，断言无横向溢出；
  溢出时报告是哪个元素（逐子元素量 scrollWidth）。

tests/browser/test_rendered_output.py
  关掉第 2 条未完成项：用 html_presenter 插件 + 仓库自带 fixture 渲染一个真实 HTML 成品，
  写到 tmp_path，用 file:// 载入 Chromium，断言无 console 错误且预期内容在 DOM 里。
  优先复用 tests/test_presentation_plugins.py 的 fixture 构造方式，不要另起炉灶。

pytest.ini
  在 markers 下追加：browser: 需要 Playwright 浏览器的端到端测试
  使 `pytest -m "not browser"` 能干净地跳过。

【验收命令（必须贴真实输出）】
python -m pytest tests/browser/ -q
python -m pytest tests/ -q --ignore=tests/integration      # 仍须 >= 955 passed

【必须自证（不给这步交付不算完成）】
故意弄坏一处（用 add_init_script 注入一个 JS 错误，或把某页指向不存在的端点），
贴出「套件失败」的输出，然后还原。套件不能失败 = 没有套件。
```

---

## 3. G2 · API 契约缺口修复

```
【窗口代号】G2
【可写范围】api/server.py  —— 只有这一个文件。其余一律只读。

【背景】浏览器审计 + 共享发现命令确认：前端调了 2 个后端根本不存在的端点，
两者都是必现 404，都会让对应功能静默失效。你要按前端**实际解构的形状**把它们补上。

【任务 1】GET /api/plugins/errors —— 后端完全缺失
  调用方：dashboard/console/plugins.html:125（ERRORS_API）、:245（fetch）
  前端实际消费方式（照抄，不要臆造）：
    pluginErrors = data.errors || data || {};
    顶层是一个对象，key 格式为  (plugin_type || kind) + ':' + (name || id)
    例：  "processor:dedup": [ ...错误数组... ]
    每个错误对象前端会读这些字段（括号内是回退链）：
      created_at || timestamp     时间
      code || 'UNKNOWN'           错误码
      message || error            描述
      suggestion || advice        修复建议
      以及一个 traceback 类字段（:330 附近渲染完整堆栈，需自行确认字段名）
  可用的后端能力（已核实存在，直接接上，不要另造轮子）：
    config/plugins.py 的 get_plugin_errors(plugin_name, limit)
    plugin_manager/error_reporter.py 的 get_recent_errors(name, limit) 与 aggregate()
  要求：支持可选 query 参数 name=<插件名> 与 limit=<条数>；无数据时返回空对象而非 404。

【任务 2】GET /api/outputs/serve —— 后端完全缺失
  调用方：dashboard/runtime/preview.html:86
    /api/outputs/serve?path=<urlencoded>&token=<urlencoded>
  影响：W7 在 progress.md 中登记为已交付的「E. 运行时预览」整条链路目前是死的——
        iframe 永远加载不出来。
  ★ 安全要求（这条是路径穿越，必须做对）：
    - path 必须限制在受管 outputs 目录内（参考 pipeline/stages/present.py 里
      「成品路径须落在受管 outputs 目录下」的既有做法，保持一致）
    - token 必须校验，非法 token 返回 403（preview.html 自己签发临时只读令牌，
      先读该文件搞清楚 token 从哪来，别假设）
    - 非法 / 越界路径返回 400 或 403，绝不能回显真实文件系统路径

【任务 3】修掉一个已确认的逻辑缺陷（不是 404，是「永远为空」）
  /api/failures/grouped（api/server.py:747）默认 status="active"，
  而 data/output/failures.json 里 2330 条记录的 status **全部是 "resolved"**。
  结果：console/failures.html 调用它（不传 query）拿到空 grouped，
        fetch 是 200 所以前端那条 fallback 分支**永远不会触发**，
        分组视图对真实数据恒为空。
  请判断正确修法（是默认不带 status 过滤？还是显式接受空状态？还是对齐字段缺失的语义？），
  选定后在报告里说明理由，并补一个能锁住这个行为的测试。

【任务 4】顺带核对（发现即修，修不了就报告）
  用共享发现命令之外的方式，逐个核对前端消费的其余 18 个端点的**响应形状**
  是否与前端解构一致——返回 200 但字段名/嵌套对不上，和 404 一样是坏。
  已知 /api/failures 返回 {code:0,data:{total,summary,items}} 与前端匹配，
  /api/failures/grouped 返回 {key,label,error_type,domain,count,first_seen,
  last_seen,sample_url,sample_schools} 也与前端匹配，这两个不用动。

【路由冲突自检（必做）】
api/server.py 已有 /api/plugins/<path:plugin_key>（PUT/DELETE）这类通配路由。
新增 GET 路由后，必须用 app.url_map 确认 Werkzeug 没有把新端点被通配规则吃掉。
贴出验证输出，不要凭直觉下结论。

【验收命令（必须贴真实输出）】
python -m pytest tests/ -q --ignore=tests/integration      # 仍须 >= 955 passed
另需启动服务，逐个 curl 新端点，贴出真实 status + response body。

【禁止】
- 不许加「万能 404 兜底」或大范围 try/except 来掩盖问题。
- 如果某个已有测试断言了「某端点返回 404」这种旧行为，不要默默改测试来迁就——
  在报告里明确指出来交给 G5 裁决。
```

---

## 4. G3 · GitHub 工程化

```
【窗口代号】G3
【可写范围】.github/**  和  .gitignore  —— 只有这两个。
            其他一切只读（包括 CHANGELOG.md 和 docs/，那是 G4 的地盘）。

【背景事实（已核实）】
- 仓库从来没有过 .github/ 目录：无 CI、无 issue 模板、无 PR 模板。
- 本地领先 origin/Refactoring_code 共 12 个 commit，且 v3.0.0 tag **从未推送**
  （git ls-remote --tags origin 返回空）。
- 另有约 81 个未提交文件，其中混着真交付物和垃圾。已初步判定（需你复核）：
  真交付物：infra/errors/ infra/retry/ infra/state_tracker.py
            plugin_manager/error_reporter.py plugin_manager/registry_snapshot.json
            plugins/plugin_manifest.py plugins/__init__.py
            plugins/processors/{domain_rewriter,error_analyzer,parser_fallback,url_normalizer}/
            plugins/spiders/url_prober/ data/domain_kb.json
            dashboard/console/{api.js,failures.html,style.css}
            CHANGELOG.md tests/test_dashboard_frontend.py tools/
  疑似垃圾：根目录散落的 *.png 截图、*-network.json（playwright 网络转储）、
            site_build/（mkdocs 构建产物）、memory/（本地草稿）、
            scripts/_diagnose_*.py（一次性诊断脚本）
- 现有 .gitignore 里有 `*preview.png`，所以 templates/*/preview.png 从不入库。
- SSH 推送可用（已认证为 sanyue-wy）；本机**没有安装 gh CLI**，只能走 git 协议。

【任务 1】.gitignore 卫生
补齐上面那些「疑似垃圾」的类别。要特别小心：
  - 不要把任何真交付物误伤进去。改完必须跑
      git status --porcelain
    确认未跟踪清单里**没有**任何交付物凭空消失。
  - 每个新增规则用 git check-ignore -v <path> 逐条验证真的生效了。
  - 思考 site_build/ 该不该入库：它是构建产物，通常应忽略；但要确认
    mkdocs.yml 不会在 CI 里依赖它已存在。

【任务 2】.github/workflows/ci.yml
  - 触发：push + pull_request，覆盖 Refactoring_code 与 main
  - Python 3.12；pip 缓存 + concurrency（同一 ref 的旧 run 自动取消）
  - 测试：python -m pytest tests/ -q --ignore=tests/integration
    （tests/integration 是**故意排除**的，注释里写清楚原因）
  - 语法门禁：python -m compileall -q（无新依赖，安全）
  - 文档构建：mkdocs 1.6.1 + material + mkdocstrings 本机已装，
    所以 `mkdocs build --strict` 是一个合法 job。
    先在本机跑通并贴出真实输出；确认它不会把 site_build/ 产物提交回仓库。
  - ⚠️ 不要加 ruff / black / mypy job——本机没装，CI 首次运行必红。
  - ⚠️ 不要加 Playwright 浏览器 job——Chromium 下载慢且这里无法验证。
  - 本地跑一遍 workflow 里的每条命令，按顺序贴真实输出。

【任务 3】模板文件
  .github/ISSUE_TEMPLATE/bug_report.yml
  .github/pull_request_template.md
  —— 简短实用，用中文，与项目文档语言一致。

【交付报告里必须包含】一段给 G5 的「推送清单」：
  该 git add 哪些路径、该忽略哪些、以及推 Refactoring_code 分支与 v3.0.0 tag 的命令，
  以及每一步可能失败在哪。**但你不要执行推送**——推送由协调者统一做。
```

---

## 5. G4 · 文档真实性校准

```
【窗口代号】G4
【可写范围】docs/**（但 docs/V3.0/INTERFACES.md 是冻结契约，只读）
            CHANGELOG.md
            以及 README.md（协调者已修过一部分，见下方「已完成」）
            其他一切只读。

【背景】这个项目的文档写得非常具体，因此会产生「文档声称已修复、代码里其实没有」的风险。
你的职责是让文档只说真话，并把仍未闭环的事项如实标注出来。

【已完成，不要重做】
协调者已修复 README.md 两处死链：
  docs/plugin_dev_guide/01_quickstart.md  →  实为 01_platform_overview.md
  docs/INTERFACES.md                      →  实为 docs/V3.0/INTERFACES.md
并新增了「两套面板与正确启动方式」一节（含 python -m http.server 会导致全部 /api/* 404 的警告）。
请复核这些修改是否准确，必要时补正，但不要推倒重来。

【任务 1】逐条核对 acceptance.md 的 5 项阻断修复声明（这是最高优先级）
  声明说这些都已修复。去代码里验证真伪，任何一条为假都是严重问题：
    (a) plugins/base.py 真有 ParserPlugin / RecordProcessorPlugin / StoragePlugin / UIPlugin
    (b) PresenterPlugin 真声明 input_schema='PresentationRequest.v1'
                                  output_schema='RenderedOutputDTO.v1'
    (c) contracts/raw.py 的 RawDataDTO.v1_schema() 的 required 真含 'assets'
    (d) pipeline/stages/present.py 真有 _FORMAT_FALLBACK，且 markdown_presenter 插件真实存在
    (e) plugins/presenters/pdf_presenter/plugin.py 真用 html.escape，不再是那个
        `value.replace('&','&')` 的 no-op
  逐条给出 PASS/FAIL + 你实际跑的命令。为假的写清楚「文档说了什么 vs 代码实际是什么」。

【任务 2】修 progress.md 与 merge_report.md 里的数字与事实
  - 两者都声称全量回归「956 passed」。实测当前是 **955 passed, 3 skipped**。
    不要盲目改成 955——先确认为何差 1（找出是哪个用例、为什么），
    在报告里说明，然后把文档改成经得起复算的数字。
  - progress.md 的 **W6 区段整段是空的**（分支/已完成/阻塞 三栏全空），
    而 acceptance.md §6 承认 W6 的代码存在且功能完整。补齐 W6 的登记
    （代码位置、验收命令与真实输出），或明确写「未登记，原因 X」。
  - progress.md 与 console_fix_report.md 里有约 5 处把
    `python main.py --ui` 当作控制台验收命令。**main.py 没有 --ui 参数**，
    该命令会直接报错。全部改成实测可用的 `python -m api.server --port 5000`。
  - progress.md 的 W7「未完成」区里那两条浏览器验收项，在本批次结束后会被 G1 关掉。
    本窗口**先不要**把它们标成已完成——G5 验收后由协调者统一收口。

【任务 3】核对 CHANGELOG.md
  - 它声明的 [v3.0.0] 日期是 2026-09-18，但 progress.md/merge_report.md 记录的
    合并签字时间是 2026-09-22，且 09-18 之后显然还有大量产出。
  - 核对它列的插件数量与实际扫描结果是否一致：
      python -c "from plugin_manager.loader import scan_plugin_dirs; d,_,_=scan_plugin_dirs(); ..."
  - 补上 09-18 之后实际发生但完全没记录的工作（控制台、presenters、
    processors 新增、domain_kb、错误上报等）。保持 Keep a Changelog 格式与现有中英混排风格。

【任务 4】找出文档里其他「引用了不存在的文件」的链接
  （acceptance.md 曾记录过 10_testing.md 引用不存在的 fixture、
    09_template_dev.md 引用不存在的 scripts/build_template_previews.py——自己全面查一遍）

【红线】
- 不要为了让文档好看而夸大完成度。宁可写「未完成」，也不要写一个假的「已完成」。
- INTERFACES.md 只读。要改的诉求写进报告，不要动手。
```

---

## 6. G5 · 独立验收（不写生产代码）

```
【窗口代号】G5
【可写范围】无。你不写任何生产代码、测试或配置。
            只允许在 docs/V3.0/acceptance_evidence/browser_github/ 下放证据文件。
            你的价值是**证伪**，不是建设。

【时机】G1–G4 全部提交后运行。你是唯一有资格宣布「这批可以推 GitHub」的窗口。

【职责 1】前端未捕获异常与 404 门禁
  python -m pytest tests/browser/ -q
  贴真实输出。特别确认：当 api/server.py 里删掉 /api/plugins/errors 路由时，
  test_api_contract.py 确实会失败。套件不能失败就是没价值。

【职责 2】全量回归不破
  python -m pytest tests/ -q --ignore=tests/integration
  必须 >= 955 passed。若 G1/G2 导致下跌，精确定位是哪些用例、为什么。

【职责 3】G2 的端点真修好了吗
  启动服务，实打实请求新端点，贴 status + body。
  然后**读前端代码**，逐字段比对返回的 JSON 与前端解构的结构是否一致——
  返回 200 但形状不对，等于还是坏的，这是最可能出问题的地方。
  另：确认 /api/outputs/serve 的路径穿越与 token 校验真的有效，
  构造一个 ../ 穿越 payload 和一个非法 token 实测被拒（安全项，必须实测，不接受"代码看起来对"）。

【职责 4】G3 的 CI 在干净克隆上真能跑
  本地全绿不等于 CI 绿。逐条排查：workflow 用到的每个文件是否**已入库或至少未被 ignore**？
  特别检查测试 fixture、data/domain_kb.json、config/*.yaml、templates/ 的 git 跟踪状态
  （git check-ignore -v + git ls-files）。
  "本地过、干净克隆挂，因为某个 fixture 从没提交过"是经典翻车点，重点找。
  然后在 workflow 里的每条命令都按顺序跑一遍，贴输出。

【职责 5】G4 的文档现在说真话了吗
  抽查 G4 声称已修正的条目。特别确认那 5 项 acceptance 阻断声明
  在代码里确实为真。文档说「已修复」而代码里没有 = 严重问题，直接判 FAIL。

【验收命令】
python -m pytest tests/ -q --ignore=tests/integration
python -m pytest tests/browser/ -q

【产出】
写入 docs/V3.0/acceptance_evidence/browser_github/ 的验收报告，
结论必须是三选一：✅ 通过 / ⚠️ 有条件通过（列明条件）/ ❌ 不通过（列明阻断项）。
不要为了让流程走完而给通过——宁可打回。
```

---

## 7. 编排说明（给协调者，不发给窗口）

**启动**：G1、G2、G3、G4 同时启动，互不等待。G5 等四个都提交后再启动。

**合入顺序**：G3（.gitignore）→ G4（文档）→ G2（API）→ G1（测试）→ G5（验收）
理由：G3 先落地可以让后续窗口少看见一堆垃圾未跟踪文件；
G1 的测试依赖 G2 的端点，所以 G2 先合、G5 再跑全量。

**推送 GitHub（协调者执行，窗口一律不许 push）**：
1. 先按 G3 的 `.gitignore` + 推送清单 `git add`（只 add 真交付物）
2. 提交 G1–G4 的产出
3. `git push origin Refactoring_code`（12 个历史 commit 一并推上去）
4. `git push origin v3.0.0`（tag 目前只在本地）
5. **不要**动 `main`：本地 main 落后 13 个 commit，是 `Refactoring_code` 的祖先，
   是否把 main 快进到 v3.0.0 属于发布决策，应由项目负责人决定，不要顺手做掉。

**已知遗留**（本批次不处理，登记备查）：
- `docs/V3.0/acceptance.md` §6.3 的 5 项非阻断待办（DTO required 缺失、
  RecordBatch.group_key 类型、jsonl_presenter 返回类型等）仍未修。
- 本机无 `gh` CLI，GitHub Release / Issue 无法自动创建，只能推 git 引用。
- 合并报告称「当前主分支可发布」，但严格说 `main` 还没动过——措辞需要 G4 校正。