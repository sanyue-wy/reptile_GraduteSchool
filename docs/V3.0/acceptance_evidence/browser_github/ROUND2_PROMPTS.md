# V3.0「闭环补全」第二轮修复 —— 窗口提示词集

> 依据：`docs/V3.0/acceptance_evidence/browser_github/G5_ACCEPTANCE_REPORT.md`（G5 证伪结论 ❌ 不通过）
> 生成时间：2026-10-01
> 用法：每个代码块整体复制，粘进一个独立新窗口开工。第一波 4 个窗口可同时开工。

---

## ⚠️ 派发前必读：三条会毁掉这一轮的前提

**1. 955 基线是「声明」，不是「实测」。**
G5 因工具限流**没能跑成任何 pytest**，`pytest tests/ -q --ignore=tests/integration → 955 passed`
这条从未被 G5 验证过。**所有窗口禁止把它当既成事实引用。**
任何窗口若要引用回归数字，必须自己跑一遍并贴真实输出。

**2. 四个窗口共享同一个工作树，并行跑 pytest 会互相污染。**
已按职责切分测试归属以规避：

| 窗口 | 只许跑 |
|---|---|
| H1 | `pytest tests/ -q --ignore=tests/integration --ignore=tests/browser` |
| H2 | `pytest tests/browser/ -q` |
| H3 | ci.yml 里的 compileall / mkdocs，**不跑 pytest** |
| H4 | **不跑测试** |

若 H1 与 H2 的运行出现数据串味（如 `data/runs/` 下互相覆盖），
**记录下来并串行复跑**，不要把污染结果当结论。

**3. Bash 可能被工具侧限流**（G5 全程遭遇 `rate-limited`）。
短命令偶尔放行、长命令常被挡。**遇阻就重试或改用短命令拆开跑，
不要因为跑不通就把结论降级成「代码看起来对」**——G5 职责 3 明确写了这条红线。

---

## 共享事实（各窗口直接采信，不必重新验证）

以下每条都由 G5 实测或逐行核对代码得出：

1. `git ls-files infra` 只返回 8 个文件，索引里仍是旧的 `infra/errors.py`；
   取代它的 `infra/errors/` 包（`__init__.py` + `plugin_error.py`）**未入库**。
2. `git ls-files tools .github` → **返回空**。CI workflow 自己没入库；
   `tools/` 没入库会让 ci.yml 的 syntax job 的 `compileall … tools …` 失败。
3. `git ls-files data/domain_kb.json plugins/__init__.py plugin_manager/error_reporter.py
   plugin_manager/registry_snapshot.json plugins/plugin_manifest.py` → **返回空**。
4. `git ls-files templates/registry.json` → **已入库**。
5. 磁盘上真实错误记录 `data/output/plugin_errors/stage_acquire_test_source_20260920_235000_000001.json`
   的 `plugin_type = "pipeline"`、`plugin_name = "stage:acquire:test_source"`。
6. `.gitignore:15` 的 `*preview.png` **未锚定**，命中 `templates/*/preview.png`（20 个文件）。
   G3 已把 `/*.png` 锚定到根目录，但漏了这条。
7. `plugins/base.py:210` 的 `ParserPlugin.plugin_type = "parser"`，
   而 `plugin_manager/loader.py:20` 的 `PLUGIN_TYPES` 无 `"parser"`，
   `plugin_manager/validator.py:34` 的 `PLUGIN_BASE_CLASSES` 亦无该键。
8. `contracts/` 与 `docs/V3.0/INTERFACES.md` 是**冻结契约**，任何窗口不得修改。

---

# 第一波（4 窗口并行开工）

## H1 · 后端端点窗口

```
【窗口代号】H1
【可写范围】api/server.py、tests/test_api_closed_loop_g2.py
            除此之外一律只读。看到别人的问题写进报告，不动手。

【时机】立即开工。与 H2/H3/H4 同时进行，互不等待。

【职责 1】修 B-1：/templates/registry.json 必现 404
  现象：dashboard/console/output-config.html:127 抓 '/templates/registry.json'，
        而 api/server.py:1898-1910 的 catch-all 路由白名单只有
        (.html .css .js .png .jpg .jpeg .svg .ico)，不含 .json，直接 abort(404)。
        即使在白名单里，static_folder 是 dashboard/，dashboard/templates/registry.json 也不存在。
  连带后果一：tests/browser/test_api_contract.py::test_non_api_static_fetches_are_served
        断言 status==200，**这条用例现在必红**。
  连带后果二（真实产品缺陷）：输出配置页的模板下拉框恒为空，
        前端走 `r.ok ? r.json() : { templates: [] }` 静默回退。
  修法：加一条**精确路由** @app.route("/templates/registry.json")，
        只 send_file 仓库根 templates/registry.json 这一个文件。
        **不要**把仓库根整体挂出去——那是安全决策，不在本窗口授权内。
        文件已入库（git ls-files 确认），不要复制副本。
  验收：起服务实打实请求一次，贴 status + body 头部。

【职责 2】修 B-2：插件错误中心的分组键与前端查找键永不相交（这是本轮最实质的缺陷）
  两侧键空间（都已实测）：
    后端 api/server.py:1377  按 f"{plugin_type}:{plugin_name}" 分组
    真实记录               plugin_type="pipeline", plugin_name="stage:acquire[:source_id]"
    前端 plugins.html:267   按 (p.plugin_type || p.kind || '') + ':' + (p.name || p.id || '')
    /api/plugins 的 item   由 config/plugins.py:672-693 的 list_plugins() 产出，
                           **只有 kind 字段，没有 plugin_type**
  即：后端产 "pipeline:stage:acquire"，前端只会查 "processor:dedup"、"fetcher:static_html"。
     **两侧永不相交** → 每个插件卡片 errorCount 恒 0，状态徽章恒正常，
     按钮恒显示「配置」而非「查看错误」，抽屉恒显示「暂无错误记录」。
  根因语义：插件错误中心是**按插件归因**的，而唯一写入方
     pipeline/engine.py:510-516 把错误记成了**按 stage 归因**。
  推荐修法（可偏离，但必须在报告里论证）：
  ⚠️ 动手前必读（这条会决定你的修法，别走错路）：
     contracts/result.py:197 的 ErrorDTO **没有任何插件身份字段**，
     只有 code / message / stage / task_id / source_id / retryable / diagnostics。
     而 contracts/ 是**冻结契约，不得修改**。
     所以「让 stage error 自己带上插件身份」这条路走不通——别去动 ErrorDTO，那会违反红线。
     可行方向只有两条，选一条并论证：
     (a)【推荐，可行性已核实】在 engine 的归因处补身份：
         _report_stage_errors 虽然只收到 result，但它是 engine 的方法，
         self.definition.sources 可达（AcquirePlan 列表，带 source_id 与 parse_instances），
         而 ErrorDTO 里有 source_id。
         用 source_id 匹配 plan，取出实际失败的插件实例名，
         用该实例的 kind（V3 五类之一）作 plugin_type、实例名作 plugin_name 落盘，
         键空间即与前端的 (p.kind||p.plugin_type)+':'+(p.name||p.id) 对齐。
         注意 /api/plugins/errors 读取时**不再做映射**，它直接拿记录里的
         plugin_type 字符串分组；而前端看到的是 list_plugins() 已映射过的 legacy kind。
         所以必须直接落 legacy 值。对照 config/plugins.py:630 的 _registry_to_legacy_kind：
             spider → fetcher / processor → processor / storage → exporter
             presenter → presenter / ui → presenter
         即：写 "spider" 是错的（前端那边叫 "fetcher"），必须写 "fetcher" 才命中。
         改动落在 pipeline/engine.py —— 若超出你的可写范围，**不要越界**，
         在报告里写清需要哪个文件的哪些行，由用户裁决后再开工。
     (b) 承认「stage 错误不是插件错误」：前端 plugins.html 改为不按插件卡片挂错误，
         改独立的全局错误列表。这需要前端同步改（属 H2 范围）——
         选这条就在报告里写明 H2 需要配合什么，然后报告给用户。
     两条都不做而只改分组字符串，**不算修复**（那只是把不相交换成另一种不相交）。
  验收（必须新增这条断言，这是能抓住本 bug 的唯一形态）：
     写盘一条**真实写入方会产出的形态**的记录，然后断言
     GET /api/plugins/errors 返回的 keys
     与 GET /api/plugins 返回的 items 逐个算出的 key **存在交集**。
     交集非空才算修好。
  ⚠️ 严禁沿用 tests/test_api_closed_loop_g2.py:59-71 那种
     手写 plugin_type="processor" 的合成记录——真实写入方从不产出该值，
     这正是本 bug 逃过 G2 测试的原因。

【职责 3】硬化 G2 遗留的测试
  把上述交集断言补进 tests/test_api_closed_loop_g2.py。
  严禁为了让测试变绿而弱化断言、跳过用例、或往 try/except 里塞 AssertionError。

【验收命令】
  python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser
  （这是你唯一该跑的全量；浏览器套件归 H2）

【产出】
  写入 docs/V3.0/acceptance_evidence/browser_github/H1_REPORT.md，
  必须贴真实命令输出。没跑过的命令不许写成「已验证」。
```

---

## H2 · 前端与浏览器红灯窗口

```
【窗口代号】H2
【可写范围】dashboard/**、tests/browser/**
            绝不碰 api/server.py（归 H1）。看到后端问题写报告，不动手。

【时机】立即开工。与 H1/H3/H4 同时进行，互不等待。

【背景】G5 的结论：tests/browser/ 目前是**红的**。
  G1 自己在 tests/browser/conftest.py:15-16 写明「现在仍在报的三条是
  dashboard/tasks.html 与 dashboard/console/failures.html 的真实前端缺陷」。
  G5 另经逐行核对确认第四条必然红：
     test_non_api_static_fetches_are_served
     —— /templates/registry.json 404（根因在后端，由 H1 修）

【职责 1】先测量，再动手
  跑 `python -m pytest tests/browser/ -q`，贴**真实**输出与全部失败用例 id + 断言信息。
  确认红灯清单是否就是上述 4 条。若多于 4 条，逐条定位根因后写进报告。

【职责 2】修 dashboard/tasks.html 与 dashboard/console/failures.html 的前端缺陷
  对每条红灯：定位 → 修前端 → 重跑该条 → 贴前后对比输出。
  原则：
    - 页面必须真的渲染出内容，不是把异常藏进 catch 里静默回退到假数据。
    - 严禁弱化断言、skip 用例来让它变绿。
    - 若某条红灯的根因在后端，**报告**给用户，不要越界改 api/server.py。

【职责 3】确认 /templates/registry.json 那条转绿
  H1 加路由后重跑该用例并贴输出。若仍红，说明 H1 没修好，报告给用户。

【职责 4】补一条「不许静默假数据」的守护用例
  现存多处 `r.ok ? r.json() : { templates: [] }` 形态的回退，
  会把后端故障伪装成「本来就没数据」。挑最关键的一处补断言。

【验收命令】
  python -m pytest tests/browser/ -q

【产出】
  写入 docs/V3.0/acceptance_evidence/browser_github/H2_REPORT.md，
  必须贴真实命令输出。
```

---

## H3 · CI 与仓库卫生窗口

```
【窗口代号】H3
【可写范围】.gitignore、.github/**
            只读 git 可以；**严禁 git add / commit / push / checkout / clean / stash**。

【时机】立即开工。与 H1/H2/H4 同时进行，互不等待。

【已实测的硬事实】
  git ls-files tools .github            → 返回空（两者都未入库）
  git ls-files infra                    → 仅 8 个旧文件，infra/errors/ 包未入库
  git ls-files data/domain_kb.json plugins/__init__.py
      plugin_manager/error_reporter.py
      plugin_manager/registry_snapshot.json
      plugins/plugin_manifest.py        → 返回空
  git ls-files templates/registry.json  → 已入库

【职责 1】修 .gitignore:15 的 *preview.png
  该规则未锚定，命中 templates/*/preview.png（20 个文件），导致模板预览图永不入库。
  G3 此前已把 /*.png 锚定到根目录并写了注释说明理由，但漏了这条。
  改成锚定形式。注意：**不要**误伤将来放进 docs/ 的正式插图，
  改完用 `git check-ignore -v` 逐个确认 templates/*/preview.png 的新归属。

【职责 2】产出「干净克隆必须入库清单」
  这是本窗口最重要的交付。当前 infra/errors/、infra/retry/、infra/state_tracker.py、
  plugins/__init__.py、plugins/plugin_manifest.py、plugin_manager/error_reporter.py、
  plugin_manager/registry_snapshot.json、plugins/processors/{domain_rewriter,
  error_analyzer,parser_fallback,url_normalizer}/、plugins/spiders/url_prober/、
  data/domain_kb.json、tools/、.github/、dashboard/console/{api.js,failures.html,style.css}、
  tests/browser/、tests/test_api_closed_loop_g2.py、tests/test_dashboard_frontend.py
  全部 untracked。
  其中 **infra/errors/ 与 infra/retry/ 是致命的**：
  被删除的 infra/errors.py 正是被 infra/errors/ 包取代的，
  而 pipeline/stages/{acquire,present,process,store}.py 与 infra/http.py:23
  都在**模块级** import 它们。干净克隆漏掉任何一个，整个包无法导入，测试大面积 error。
  逐条用 `git check-ignore -v` 确认它们**未被 ignore**（否则 git add -A 也带不上），
  把命令输出贴进报告。

【职责 3】做一次「等同干净克隆」的演练
  绕过限流直接验证 CI 的文件前置条件：
    1) 把工作树复制到 /tmp/clean（**排除 .git**），模拟「全部已入库」的干净克隆；
    2) 在 /tmp/clean 里按 .github/workflows/ci.yml 的顺序逐条跑：
         python -m compileall -q api infra pipeline plugin_manager plugins \
           contracts converters scaffolds tests tools main.py
         python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser
         python -m mkdocs build --strict
       （mkdocs 若未安装，如实说明「COULD NOT RUN」，不要伪造输出）
    3) 把每条的退出码与输出贴进报告。
  这一步会真实暴露「本地过、干净克隆挂」。

【职责 4】复核 ci.yml 本身
  三个 job 的依赖缓存路径、Python 版本、排除项是否自洽。
  特别确认 syntax job 里 compileall 的每个目录在干净克隆中都存在。

【验收命令】
  见职责 3。不跑全量 pytest（归 H1）。

【产出】
  写入 docs/V3.0/acceptance_evidence/browser_github/H3_REPORT.md。
  报告末尾必须有一段「收尾人工步骤」，逐条列出推送前需要 git add 的路径。
  必须贴真实命令输出。
```

---

## H4 · 文档失真修正窗口

```
【窗口代号】H4
【可写范围】docs/**（**排除 contracts/ 与 docs/V3.0/INTERFACES.md，那是冻结契约**）、CHANGELOG.md
            只读其他一切。**不跑测试。**

【时机】立即开工。与 H1/H2/H3 同时进行，互不等待。

【重要边界】本窗口**只修「与本批其他窗口无关的既有失真」**。
  H1/H2/H3 正在改的东西一律不要写进文档——你看不到他们的结果，
  写了就是编造。他们产出之后的文档收口留给第二轮。

【职责 1】修正 acceptance.md 中已被证伪的证据表述
  a) acceptance.md:103 称「20 个模板目录均存在且各含 4 个文件
     (layout.html, style.css, variables.json, preview.png)」。
     但 preview.png 被 .gitignore 的 *preview.png 命中，永不入库
     （H3 正在修）。干净克隆上该证据不成立，须改写表述并注明测量环境。
  b) acceptance.md 的 L3 回归数字（949/955 之类）须标注**测量口径**：
     该数字是否包含 tests/browser/？由谁、什么时候测的？
     G5 未能验证任何 pytest 结果（工具限流），此数字目前来源不明。
     在核实前，标注为「未复验」，不要沿用为既成事实。

【职责 2】登记「文档承诺 vs 代码实现」的偏差（只登记，不改冻结契约）
  docs/V3.0/INTERFACES.md:599（§12.4）称「若插件声明 depends_on:["domain_kb"]，
  加载时校验 data/domain_kb.json 存在且 schema 合法」。
  实测：`validate_domain_kb()` 在全仓**没有任何调用方**
  （只有 validator.py 内的定义与 __all__ 导出）。
  即该契约承诺的能力**代码里根本没接线**。
  INTERFACES.md 是冻结契约不得修改 → 在 acceptance.md 或 progress.md
  登记为已知偏差，写明证据。

【职责 3】复核 G4 自己声称已修的 5 项阻断项是否属实
  G5 已逐条回代码核对，结论是**全部属实**（含 G4 主动自曝的 B1 遗留与 B4 未接线）。
  你要做的是：核对这些结论是否**已如实写进 acceptance.md**，
  尤其是 B1 的两处遗留与 B4 的「配置未接线」是否被完整记录、没有粉饰成闭环。

【职责 4】补 CHANGELOG
  核对 09-18 之后实际发生但未记录的工作（控制台、presenters、processors 新增、
  domain_kb、错误上报、本批 G1–G5）。保持 Keep a Changelog 格式与现有中英混排风格。

【职责 5】找出文档里其他「引用了不存在的文件」的链接
  acceptance.md 曾记录过此类问题，说明这是个反复出现的坑，值得再扫一遍。

【产出】
  写入 docs/V3.0/acceptance_evidence/browser_github/H4_REPORT.md，
  列出每处改了哪个文件的哪一行、为什么。没核实的不要写。
```

---

# 第二波（等第一波 4 个窗口全部完成后才开工）

## H5 · 复验与签字窗口

```
【窗口代号】H5
【可写范围】docs/V3.0/acceptance_evidence/browser_github/ 下的证据文件。
            你不写任何生产代码、测试或配置。
            你的价值是**证伪**，不是建设。

【时机】H1–H4 全部提交后运行。你是唯一有资格宣布「这批可以推 GitHub」的窗口。

【职责 1】两条验收命令必须真跑
  python -m pytest tests/ -q --ignore=tests/integration
  python -m pytest tests/browser/ -q
  贴真实输出。注意：基线 955 从未被 G5 验证过，**你要自己测出真实数字**，
  并说明该数字是否含 tests/browser/（G1 之前没有这个目录，口径可能不可比）。

【职责 2】浏览器套件必须真绿
  逐条确认：G1 自曝的 3 条 + G5 发现的 /templates/registry.json 那条，
  现在是否全绿。若仍红，直接判 FAIL。
  另外做**证伪测试**确认套件有牙：写一个 /tmp 下的 pytest 插件，
  用 autouse fixture 把 "/api/plugins/errors" 规则从 app.url_map 摘掉，
  再跑 tests/browser/test_api_contract.py -q -p <该插件>，
  确认 test_known_missing_endpoint_is_registered 确实转红。
  **套件不能失败就是没价值。**

【职责 3】B-2 的交集断言是否真的成立
  跑 H1 新增的那条断言，确认它是**用真实写入方产出的记录形态**写的，
  而不是又合成了一条 plugin_type="processor"。
  自己再手工构造一次：用 pipeline/engine.py 的 _report_stage_errors 落一条记录，
  然后请求 /api/plugins/errors，验证 keys 与 /api/plugins 的 items 计算出的 key 有交集。
  返回 200 但前端查不到，等于还是坏的。

【职责 4】安全项必须实测
  启动服务，构造 ../ 穿越 payload 与非法 token，请求 /api/outputs/serve，
  贴 status + body。**不接受「代码看起来对」。**
  再确认 tokens/<run_id>/store/ 与符号链接越界都被拒。

【职责 5】干净克隆真的能跑
  把工作树复制到 /tmp/clean（排除 .git），按 ci.yml 顺序跑三条命令，贴退出码。
  再用 `git ls-files` 逐条确认 H3 清单里的路径已入库。
  重点：infra/errors/、infra/retry/ 任一缺失都会让 pipeline 包无法导入。

【职责 6】文档现在说真话了吗
  抽查 H4 声称已修正的条目。特别确认那 5 项 acceptance 阻断声明在代码里确实为真。
  **文档说「已修复」而代码里没有 = 严重问题，直接判 FAIL。**

【产出】
  写入 docs/V3.0/acceptance_evidence/browser_github/ 的验收报告，
  结论必须是三选一：✅ 通过 / ⚠️ 有条件通过（列明条件）/ ❌ 不通过（列明阻断项）。
  报告末尾附「收尾人工步骤」：推送前需要 git add 的路径清单 + git commit 命令模板。
  不要为了让流程走完而给通过——宁可打回。
```