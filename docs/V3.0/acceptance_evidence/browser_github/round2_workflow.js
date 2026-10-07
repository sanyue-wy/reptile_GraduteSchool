export const meta = {
  name: 'v3-round2-fix-and-verify',
  description: 'V3.0 第二轮：并行修复 G5 的 3 个阻断项，再逐项派独立证伪者复验',
  phases: [
    { title: 'Fix', detail: 'H1-H4 并行修复，可写范围互不重叠' },
    { title: 'Verify', detail: '每个修复配一个独立证伪者，尝试推翻其结论' },
    { title: 'Regression', detail: '全量回归+证伪测试 / 安全实测+干净克隆演练' },
  ],
}

const REPO = 'c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool'

const FACTS = `
【共享事实 — 已实测或逐行核对，直接采信，不要重新验证】
1. git ls-files infra 只返回 infra/cache.py, context.py, errors.py, http.py, storage/*。
   索引里仍是旧的 infra/errors.py；取代它的 infra/errors/ 包（__init__.py + plugin_error.py）未入库。
2. git ls-files tools .github → 返回空（两者都未入库）。
3. git ls-files data/domain_kb.json plugins/__init__.py plugin_manager/error_reporter.py
   plugin_manager/registry_snapshot.json plugins/plugin_manifest.py → 返回空。
4. git ls-files templates/registry.json → 已入库。
5. 磁盘上真实错误记录 data/output/plugin_errors/stage_acquire_test_source_20260920_235000_000001.json
   的 plugin_type = "pipeline"，plugin_name = "stage:acquire:test_source"。
6. .gitignore 第 15 行的 *preview.png 未锚定，命中 templates/*/preview.png（20 个文件）。
7. plugins/base.py:210 的 ParserPlugin.plugin_type = "parser"，
   而 plugin_manager/loader.py:20 的 PLUGIN_TYPES 无 "parser"，
   plugin_manager/validator.py:34 的 PLUGIN_BASE_CLASSES 亦无该键。
8. contracts/ 与 docs/V3.0/INTERFACES.md 是冻结契约，任何窗口不得修改。
9. 回归基线「955 passed」从未被实测验证过。禁止把它当既成事实引用。
10. 本机 Bash 可能被工具侧限流（rate-limited）。遇阻请重试或拆成短命令；
    重试仍失败就如实写 COULD NOT RUN，严禁用「代码看起来对」冒充「已验证」。
`

const REDLINES = `
【通用红线】
- 严禁 git add / commit / push / checkout / clean / stash 等写操作。只读 git 可以。
- 严禁修改自己可写范围之外的任何文件（看到了也只报告，不动手）。
- 严禁为了让测试变绿而弱化断言、skip 用例、或往 try/except 里塞 AssertionError。
- 交付必须在报告里贴真实命令输出。没跑过的命令不许写成「已验证」。
- 仓库根目录：${REPO}
- 你的产出写到 docs/V3.0/acceptance_evidence/browser_github/ 下的报告文件。
`

const FIXER_SCHEMA = {
  type: 'object',
  properties: {
    window: { type: 'string' },
    status: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    findings: { type: 'array', items: { type: 'string' } },
    commands: {
      type: 'array',
      items: {
        type: 'object',
        properties: { cmd: { type: 'string' }, result: { type: 'string' } },
        required: ['cmd', 'result'],
      },
    },
    unresolved: { type: 'array', items: { type: 'string' } },
    acceptance_met: { type: 'boolean' },
  },
  required: ['window', 'status', 'files_changed', 'findings', 'commands', 'unresolved', 'acceptance_met'],
}

const VERIFIER_SCHEMA = {
  type: 'object',
  properties: {
    window: { type: 'string' },
    verdict: { type: 'string', enum: ['confirmed', 'refuted', 'inconclusive'] },
    evidence: { type: 'array', items: { type: 'string' } },
    defects_found: { type: 'array', items: { type: 'string' } },
  },
  required: ['window', 'verdict', 'evidence', 'defects_found'],
}

const REG_SCHEMA = {
  type: 'object',
  properties: {
    area: { type: 'string' },
    results: { type: 'array', items: { type: 'string' } },
    blockers: { type: 'array', items: { type: 'string' } },
    verdicts: { type: 'array', items: { type: 'string' } },
  },
  required: ['area', 'results', 'blockers', 'verdicts'],
}

const FIXERS = [
  {
    key: 'H1',
    scope: 'api/server.py、tests/test_api_closed_loop_g2.py（此外一律只读）',
    duties: `
【职责 1】修 B-1：/templates/registry.json 必现 404
  dashboard/console/output-config.html:127 抓 '/templates/registry.json'，
  而 api/server.py:1898-1910 的 catch-all 路由白名单只有
  (.html .css .js .png .jpg .jpeg .svg .ico)，不含 .json，直接 abort(404)。
  即使在白名单里，static_folder 是 dashboard/，dashboard/templates/registry.json 也不存在。
  连带后果一：tests/browser/test_api_contract.py::test_non_api_static_fetches_are_served
  断言 status==200，这条用例现在必红。
  连带后果二（真实产品缺陷）：输出配置页的模板下拉框恒为空，
  前端走「r.ok ? r.json() : { templates: [] }」静默回退。
  修法：加一条精确路由，只 send_file 仓库根 templates/registry.json 这一个文件。
  不要把仓库根整体挂出去——那是安全决策，不在本窗口授权内。
  文件已入库，不要复制副本。
  验收：起服务实打实请求一次，贴 status + body 头部。

【职责 2】修 B-2：插件错误中心的分组键与前端查找键永不相交（本轮最实质的缺陷）
  后端 api/server.py:1377 按 f"{plugin_type}:{plugin_name}" 分组；
  真实记录 plugin_type="pipeline"（见共享事实 5）；
  前端 dashboard/console/plugins.html:267 按
    (p.plugin_type || p.kind || '') + ':' + (p.name || p.id || '')
  查找；而 /api/plugins 的 item 由 config/plugins.py:672-693 的 list_plugins() 产出，
  只有 kind 字段，没有 plugin_type。
  即后端产 "pipeline:stage:acquire"，前端只会查 "processor:dedup"、"fetcher:static_html"，
  两侧永不相交 → 每个插件卡片 errorCount 恒 0，按钮恒显示「配置」而非「查看错误」，
  抽屉恒显示「暂无错误记录」。
  根因语义：插件错误中心是按插件归因的，而唯一写入方
  pipeline/engine.py:510-516 把错误记成了按 stage 归因。

  ⚠️ 动手前必读（这条会决定你的修法，别走错路）：
  contracts/result.py:197 的 ErrorDTO **没有任何插件身份字段**，
  只有 code / message / stage / task_id / source_id / retryable / diagnostics。
  而 contracts/ 是**冻结契约，不得修改**。
  所以「让 stage error 自己带上插件身份」这条路是**走不通的**——
  别去动 ErrorDTO，那会违反红线。
  可行方向只有这两条，请选一条并论证：
  (a) **在 engine 的归因处补身份（推荐，可行性已核实）**：
      _report_stage_errors 虽然只收到 result，但它是 engine 的方法，
      因此 self.definition.sources 可达；那里是 AcquirePlan 列表，带 source_id
      与 parse_instances。而 ErrorDTO 里有 source_id。
      即：用 source_id 匹配 plan，取出实际失败的插件实例名，
      再用该实例的 kind（V3 五类之一）作为 plugin_type、实例名作为 plugin_name 落盘，
      键空间就与前端的 (p.kind||p.plugin_type)+':'+(p.name||p.id) 对齐了。
      ⚠️ 但别直接写 V3 的 plugin_type 原值——/api/plugins/errors 读取时**不再做映射**，
         它直接拿记录里的 plugin_type 字符串分组；而前端看到的是 list_plugins()
         已经映射过的 legacy kind。所以必须直接落 legacy 值。对照 config/plugins.py:630
         的 _registry_to_legacy_kind：
             spider → fetcher
             processor → processor
             storage → exporter
             presenter → presenter
             ui → presenter
         即：写 "spider" 是错的（前端那边叫 "fetcher"），必须写 "fetcher" 才命中。
      改动落在 pipeline/engine.py —— 若那超出你的可写范围，
      **不要越界**，在报告里写清需要哪个文件的哪些行，由用户裁决后再开工。
  (b) **承认「stage 错误不是插件错误」**：前端 plugins.html 改成不按插件卡片挂错误，
      改为独立的全局错误列表。但这需要前端同步改，属 H2 范围——
      若你选这条，在报告里写明 H2 需要配合什么，然后报告给用户。
  两条都不做而只是改分组字符串，**不算修复**（那只是把不相交换成另一种不相交）。

  验收（必须新增这条断言，这是能抓住本 bug 的唯一形态）：
    写盘一条真实写入方会产出的形态的记录，然后断言
    GET /api/plugins/errors 返回的 keys 与 GET /api/plugins 返回的 items
    逐个算出的 key 存在交集。交集非空才算修好。
  严禁沿用 tests/test_api_closed_loop_g2.py:59-71 那种手写
  plugin_type="processor" 的合成记录——真实写入方从不产出该值，
  这正是本 bug 逃过 G2 测试的原因。

【职责 3】把上述交集断言补进 tests/test_api_closed_loop_g2.py。
  若职责 2 的修法需要改到 pipeline/engine.py，而那超出你的可写范围，
  **不要越界**——在报告里写清需要哪个文件的哪些行，由用户裁决后再开工。

【验收命令】
  python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser
  这是你唯一该跑的全量；浏览器套件归 H2，不要跑。
`,
  },
  {
    key: 'H2',
    scope: 'dashboard/**、tests/browser/**（绝不碰 api/server.py，归 H1）',
    duties: `
【背景】G5 的结论：tests/browser/ 目前是红的。
  G1 自己在 tests/browser/conftest.py:15-16 写明「现在仍在报的三条是
  dashboard/tasks.html 与 dashboard/console/failures.html 的真实前端缺陷」。
  G5 另经逐行核对确认第四条必然红：test_non_api_static_fetches_are_served
  —— /templates/registry.json 404（根因在后端，由 H1 修，你不要改后端）。

【职责 1】先测量，再动手
  跑 python -m pytest tests/browser/ -q，贴真实输出与全部失败用例 id + 断言信息。
  确认红灯清单是否就是上述 4 条。若多于 4 条，逐条定位根因后写进报告。

【职责 2】修 dashboard/tasks.html 与 dashboard/console/failures.html 的前端缺陷
  对每条红灯：定位 → 修前端 → 重跑该条 → 贴前后对比输出。
  原则：页面必须真的渲染出内容，不是把异常藏进 catch 里静默回退到假数据；
  严禁弱化断言、skip 用例来让它变绿；
  若某条红灯根因在后端，报告给用户，不要越界改 api/server.py。

【职责 3】补一条「不许静默假数据」的守护用例
  现存多处「r.ok ? r.json() : { templates: [] }」形态的回退，
  会把后端故障伪装成「本来就没数据」。挑最关键的一处补断言。

【验收命令】
  python -m pytest tests/browser/ -q
`,
  },
  {
    key: 'H3',
    scope: '.gitignore、.github/**（只读 git 可以）',
    duties: `
【职责 1】修 .gitignore 第 15 行的 *preview.png
  该规则未锚定，命中 templates/*/preview.png（20 个文件），导致模板预览图永不入库。
  此前已把 /*.png 锚定到根目录并写了注释说明理由，但漏了这条。
  改成锚定形式。注意不要误伤将来放进 docs/ 的正式插图，
  改完用 git check-ignore -v 逐个确认 templates/*/preview.png 的新归属。

【职责 2】产出「干净克隆必须入库清单」（本窗口最重要的交付）
  当前 infra/errors/、infra/retry/、infra/state_tracker.py、plugins/__init__.py、
  plugins/plugin_manifest.py、plugin_manager/error_reporter.py、
  plugin_manager/registry_snapshot.json、plugins/processors/{domain_rewriter,
  error_analyzer,parser_fallback,url_normalizer}/、plugins/spiders/url_prober/、
  data/domain_kb.json、tools/、.github/、dashboard/console/{api.js,failures.html,style.css}、
  tests/browser/、tests/test_api_closed_loop_g2.py、tests/test_dashboard_frontend.py
  全部 untracked。
  其中 infra/errors/ 与 infra/retry/ 是致命的：被删除的 infra/errors.py 正是被
  infra/errors/ 包取代的，而 pipeline/stages/{acquire,present,process,store}.py
  与 infra/http.py:23 都在模块级 import 它们。干净克隆漏掉任何一个，
  整个包无法导入，测试大面积 error。
  逐条用 git check-ignore -v 确认它们未被 ignore（否则 git add -A 也带不上），
  把命令输出贴进报告。

【职责 3】做一次「等同干净克隆」的演练
  1) 把工作树复制到 /tmp/clean（排除 .git），模拟「全部已入库」的干净克隆；
  2) 在 /tmp/clean 里按 .github/workflows/ci.yml 的顺序跑：
       python -m compileall -q api infra pipeline plugin_manager plugins
         contracts converters scaffolds tests tools main.py
       python -m mkdocs build --strict
     （mkdocs 若未安装，如实写 COULD NOT RUN，不要伪造输出。
       不要在 /tmp/clean 里跑 pytest，会与他人冲突。）
  3) 每条的退出码与输出贴进报告。
  这一步会真实暴露「本地过、干净克隆挂」。

【职责 4】复核 ci.yml 本身
  三个 job 的依赖缓存路径、Python 版本、排除项是否自洽。
  特别确认 syntax job 里 compileall 的每个目录在干净克隆中都存在。

【验收命令】见职责 3。不跑全量 pytest（归 H1）。
`,
  },
  {
    key: 'H4',
    scope: 'docs/**（排除 contracts/ 与 docs/V3.0/INTERFACES.md，冻结契约）、CHANGELOG.md。不跑测试。',
    duties: `
【重要边界】本窗口只修「与本批其他窗口无关的既有失真」。
  H1/H2/H3 正在改的东西一律不要写进文档——你看不到他们的结果，写了就是编造。
  他们产出之后的文档收口留给下一轮。

【职责 1】修正 acceptance.md 中已被证伪的证据表述
  a) acceptance.md:103 称「20 个模板目录均存在且各含 4 个文件
     (layout.html, style.css, variables.json, preview.png)」。
     但 preview.png 被 .gitignore 的 *preview.png 命中，永不入库（H3 正在修），
     干净克隆上该证据不成立，须改写表述并注明测量环境。
  b) acceptance.md 的 L3 回归数字（949/955 之类）须标注测量口径：
     该数字是否包含 tests/browser/？由谁、什么时候测的？
     G5 未能验证任何 pytest 结果，此数字目前来源不明。
     在核实前标注为「未复验」，不要沿用为既成事实。

【职责 2】登记「文档承诺 vs 代码实现」的偏差（只登记，不改冻结契约）
  docs/V3.0/INTERFACES.md:599（§12.4）称「若插件声明 depends_on:["domain_kb"]，
  加载时校验 data/domain_kb.json 存在且 schema 合法」。
  实测：validate_domain_kb() 在全仓没有任何调用方
  （只有 plugin_manager/validator.py 内的定义与 __all__ 导出）。
  即该契约承诺的能力代码里根本没接线。
  INTERFACES.md 是冻结契约不得修改 → 在 acceptance.md 或 progress.md
  登记为已知偏差，写明证据。

【职责 3】复核 G4 声称已修的 5 项阻断项是否已如实写进 acceptance.md
  G5 已逐条回代码核对，结论是全部属实（含 G4 主动自曝的 B1 遗留与 B4 未接线）。
  你要核对的是这些结论是否完整记录、没有被粉饰成闭环。

【职责 4】补 CHANGELOG
  核对 09-18 之后实际发生但未记录的工作（控制台、presenters、processors 新增、
  domain_kb、错误上报、本批 G1-G5）。保持 Keep a Changelog 格式与现有中英混排风格。

【职责 5】找出文档里其他「引用了不存在的文件」的链接
  acceptance.md 曾记录过此类问题，说明这是个反复出现的坑，值得再扫一遍。

【验收命令】不跑测试。
`,
  },
]

phase('Fix')
log(`并行启动 ${FIXERS.length} 个修复窗口，可写范围互不重叠`)

const fixes = await parallel(
  FIXERS.map((f) => () =>
    agent(
      `你是独立工作窗口 ${f.key}，隶属 V3.0「闭环补全」第二批修复。

【可写范围】${f.scope}
除此之外一律只读。看到了也只报告，不动手。

【时机】立即开工。四个窗口同时进行，互不等待，不需要与任何人通信。

${FACTS}
${REDLINES}
${f.duties}

【产出】
把完整报告写入 docs/V3.0/acceptance_evidence/browser_github/${f.key}_REPORT.md，
必须贴真实命令输出。然后按 schema 返回结构化摘要。`,
      { label: `fix:${f.key}`, phase: 'Fix', schema: FIXER_SCHEMA },
    ),
  ),
)

const okFixes = fixes.filter(Boolean)
log(`修复阶段完成：${okFixes.length}/${FIXERS.length} 个窗口返回`)

phase('Verify')

const VERIFY_DUTY = {
  H1: `
复核 H1 对 B-1 与 B-2 的修复。**你的默认立场是 H1 在撒谎或只做了一半。**
1) B-1：起服务实打实请求 /templates/registry.json，贴 status + body 头部。
   确认它是精确路由而非把仓库根整体暴露（检查有没有引入任意文件读取面）。
2) B-2（最关键）：**不要相信 H1 的测试，自己独立构造。**
   用 pipeline/engine.py 的 _report_stage_errors 真实落一条错误记录到
   data/output/plugin_errors/，然后请求 /api/plugins/errors，
   把返回的 keys 与 /api/plugins 返回的 items 逐个算出的 key 求交集，打印交集是否非空。
   再检查 H1 新增的断言：如果它又是手写 plugin_type="processor" 的合成记录，
   那它没有修复任何东西，判 refuted。
3) 跑 H1 的验收命令，贴真实汇总行。
4) 检查 H1 是否弱化了任何既有断言（对比是否删改/跳过/skip 标记）。`,
  H2: `
复核 H2 的浏览器套件修复。**你的默认立场是红灯只是被藏起来了，不是被修好了。**
1) 跑 python -m pytest tests/browser/ -q，贴真实输出与失败清单。
2) 逐条核对每个红灯页面的**主容器真的有文本内容**：
   主容器子元素数 > 0 且 textContent 非空。若某页是把异常吞进 catch 后
   回退到假数据（形如「r.ok ? r.json() : {templates: []}」或写死 Mock），
   那是把缺陷藏起来，判 refuted。
3) 确认 H2 没有删/跳过任何既有断言，没有加 pytest.mark.skip。
4) 确认 /templates/registry.json 那条现在真的转绿了（依赖 H1 的路由）。`,
  H3: `
复核 H3 的 gitignore 与干净克隆结论。**你的默认立场是清单不完整或有遗漏项。**
1) 亲自跑 git check-ignore -v 验证 H3 声称改好的 templates/*/preview.png 新归属，
   并确认没有误伤 docs/ 下的正式插图。
2) 亲自跑 git ls-files 复核 H3 的「必须入库清单」是否完整：
   特别确认 infra/errors/、infra/retry/ 这两个致命项是否都被点到，
   以及是否还有 H3 漏掉的其他「被已入库代码 import 但未入库」的模块。
   做法：grep 全仓的 import 语句，找出所有指向 untracked 路径的依赖。
3) 自己再做一次干净克隆演练（复制到另一个 /tmp 目录，排除 .git），
   跑 compileall 与 mkdocs build --strict，贴退出码。`,
  H4: `
复核 H4 的文档修正。**你的默认立场是文档说了「已修复」而代码里没有。**
1) 抽查 acceptance.md 里每一处「已修复 / PASS / 验证通过」的断言，
   回到代码里核对是否属实。特别确认那 5 项 acceptance 阻断声明。
2) 确认 H4 遵守了边界：没有描述 H1/H2/H3 正在做的改动（那些结果它看不到，
   写了就是编造）；没有修改冻结契约 contracts/ 与 docs/V3.0/INTERFACES.md。
3) 确认 §12.4 的 domain_kb 偏差已登记为已知偏差而非被悄悄删掉。
4) 确认回归数字已被标注为「未复验」而非继续当既成事实引用。
5) 文档说「已修复」而代码里没有 = 直接判 refuted。`,
}

const verifications = await parallel(
  FIXERS.map((f) => () =>
    agent(
      `你是独立证伪窗口，负责尝试**推翻** ${f.key} 的结论。你不修复任何东西。
你可以读任何文件、跑任何只读命令、跑测试，但**不要修改仓库里的任何文件**
（你唯一的可写位置是 docs/V3.0/acceptance_evidence/browser_github/ 下的报告）。

${REDLINES}
${VERIFY_DUTY[f.key]}

被复核窗口的自述如下（**不可信，需你独立验证**）：
${JSON.stringify(okFixes.find((x) => x && x.window === f.key) || {}, null, 2)}

【产出】把复核报告写入 docs/V3.0/acceptance_evidence/browser_github/${f.key}_VERIFICATION.md，
贴真实命令输出。verdict 三选一：
- confirmed：修复属实且真的解决了原缺陷
- refuted：修复不完整、被绕过、或只是把问题藏起来了
- inconclusive：因限流等原因无法验证（说明卡在哪一条命令）`,
      { label: `verify:${f.key}`, phase: 'Verify', schema: VERIFIER_SCHEMA },
    ),
  ),
)

const okVerifications = verifications.filter(Boolean)
log(`证伪阶段完成：${okVerifications.length}/${FIXERS.length} 份裁决`)

phase('Regression')

const regressions = await parallel([
  () =>
    agent(
      `你是回归测量窗口 A。仓库根：${REPO}

${REDLINES}
注意：不要修改仓库任何文件。pytest 可能产生 data/ 下的副产物，这是允许的。

【职责 1】测出真实基线（此数字从未被验证过）
  cd ${REPO} && python -m pytest tests/ -q --ignore=tests/integration
  贴真实汇总行，说明该数字是否包含 tests/browser/。
  说明：tests/browser/ 是本批新增的目录，早先流传的「955 passed」基线
  很可能不含它，因此与本条命令的口径不可直接比较。

【职责 2】浏览器套件
  cd ${REPO} && python -m pytest tests/browser/ -q
  贴汇总行与全部失败用例 id + 断言信息。

【职责 3】CI 口径
  cd ${REPO} && python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser
  贴汇总行。

【职责 4】证伪测试（确认浏览器套件有牙，不是摆设）
  在 /tmp 下写一个 pytest 插件，用 autouse fixture 把 "/api/plugins/errors"
  规则从 app.url_map 摘掉，然后
  cd ${REPO} && PYTHONPATH=/tmp python -m pytest tests/browser/test_api_contract.py -q -p <插件名>
  确认 test_known_missing_endpoint_is_registered 确实转红。
  套件在该端点被删时不能失败，就是没价值——这是必须验证的一条。
  不要为此修改仓库里的 api/server.py。`,
      { label: 'regression:suites', phase: 'Regression', schema: REG_SCHEMA },
    ),
  () =>
    agent(
      `你是回归测量窗口 B。仓库根：${REPO}

${REDLINES}
你只写 /tmp 下的临时文件，绝不修改仓库任何文件。

【职责 1】安全项实测（不接受「代码看起来对」）
  起 Flask 服务（用你自己的端口，避开 5000），然后：
  a) 构造 ../ 穿越 payload 请求 /api/outputs/serve，贴 status + body；
  b) 构造非法 token / 空 token / 跨 run 的合法签名 token，各贴 status + body；
  c) 尝试读取 data/runs/<run_id>/store/ 下的文件（与 outputs 同级，非成品目录）；
  d) 尝试符号链接越界。
  逐条贴真实 status 与响应体。

【职责 2】干净克隆演练
  把工作树复制到 /tmp/clean_g5（**排除 .git**），模拟「全部已入库」的干净克隆，
  在其中按 .github/workflows/ci.yml 的顺序跑：
    python -m compileall -q api infra pipeline plugin_manager plugins
      contracts converters scaffolds tests tools main.py
    python -m mkdocs build --strict
  贴每条的退出码与输出尾部。mkdocs 未安装就写 COULD NOT RUN，不要伪造。
  不要在 /tmp/clean_g5 里跑 pytest（会与窗口 A 抢资源）。

【职责 3】入库完整性终检
  cd ${REPO} && git ls-files infra tools .github data plugins plugin_manager
  贴真实输出。确认 infra/errors/、infra/retry/ 这些被模块级 import 的包
  是否仍未入库——若仍未入库，这是推送前的硬阻断项。`,
      { label: 'regression:security-clone', phase: 'Regression', schema: REG_SCHEMA },
    ),
])

const okRegressions = regressions.filter(Boolean)

return {
  fixes: okFixes,
  verifications: okVerifications,
  regressions: okRegressions,
  counts: {
    fixers_returned: okFixes.length,
    verifiers_returned: okVerifications.length,
    regressions_returned: okRegressions.length,
  },
}