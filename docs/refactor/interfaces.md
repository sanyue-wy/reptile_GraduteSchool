# V2.2 接口变更登记与实施计划

## 已批准范围

2026-09-17：按 docs/V2.2/agents/README.md 及 A–G 指导书完整实施，以下契约纠正文档示例与现有实现的冲突。保留当前分支、已有工作区改动，不自动提交。所有测试使用临时文件及模拟网络；不以全量真实采集作为自动验收。

## 冻结契约

- CrawlTask 保留 university, college, category, source, year, force=False, config；追加 execution_state='pending', retry_count=0, last_attempt_at=None；key() 保持大学|学院|source，可提供 school 属性别名。
- CrawlerService(config, cache, progress, session_factory)：config 为学校配置列表（None 才加载默认配置）；工厂无参，服务获取会话；build_tasks(args) 支持 argparse 的 school/category/source/year/force/resume/retry_failed 属性。
- 服务 run_source_a/b、execute_task 返回 CrawlResult(task_id,status,records,failures,error_message=None,error_type='none')。旧 main.run_source_a/b 返回列表；main.execute_task 保持三元组；main.build_tasks 七参数和 run_merge 四参数兼容。不要创建模块全局 patch 同步桥。
- CrawlerService.run_merge(tasks) 按大学/学院去重合并。输出目录可显式注入，默认 data/output；失败读写使用同目录。MergeService.merge_sources 接收两组记录，返回 schema v1 列表；match_records(a,b) 返回匹配布尔值及 exact/strip/fuzzy/none 原因。复用现有分组匹配算法，不跨大学/学院匹配。
- ExportService 封装现有导出与处理插件链，旧 pipeline 接口返回值不变。
- JSONLStore(path).read_all(), write_all(records,atomic=True), append(record)。空路径读取为空；格式错误行跳过；原子写入 tempfile.mkstemp + os.replace，异常清理临时文件。
- ProgressStore(path,cache_ttl=1.0) 提供 load/save、update_school_status(university,college='',**kwargs)、read_all_schools；保留 version=1 和学校|学院键。读改写必须整体加锁；ProgressTracker 公开接口兼容，保留线程锁，新增 cache_ttl 可选参数。
- ConfigStore(config_path=None,global_path=None) 提供 load_schools/save_school/load_global/save_global，并提供 save_schools 用于整表导入；保持学校配置 JSON 列表和全局 JSON 对象。底层不得循环依赖 config.loader。
- SpiderEngine(session,cache=None).fetch(url,**kwargs)/parse(html,selectors,**kwargs) 为抽象方法。spiders.engine.ENGINE_REGISTRY 为类注册表；spiders.ENGINE_REGISTRY 保留旧函数表；包级 SPIDER_ENGINE_REGISTRY 指向新表。旧 static_html 配置不变；新静态类名 static_list。
- PoliteSession 新增 is_blocked(domain=None), get_block_count(domain=None), tripped_domains, reset_circuit(domain)。构造追加 circuit_threshold=5,circuit_window=3600,timeout=30；clear_cooldown 仅清理目标域名冷却。DNS 立即熔断，其他同因错误按窗口计数；不额外长时间 sleep。旧 CircuitBreaker 仅可作兼容适配，生产 CLI/API 不运行第二套熔断状态。
- CrawlCache 新增 read_many(urls), get_hit_rate()；保留锁，修复 inflight 代际清理，不允许旧请求删除新请求条目。
- ValidationResult(ok,errors,warnings)；validate_plugin_source(source,kind='',filename=''), validate_plugin_file(path)。受限导入/调用是错误，必须拒绝；可同时保留诊断 warnings，但不能仅警告放行。AST 检查不是安全沙箱，不扩大本次检查范围。

## 文件所有权与实施顺序

- [x] C：spiders/engine.py、六个引擎模块及 spiders/__init__.py；先完成基类，再适配所有引擎，保留旧调用。
- [x] D：security/**、config/plugins.py；提取现有静态校验，不降级上传/发现拒绝策略。
- [x] E：utils/http.py、utils/cache.py；按域熔断及缓存并发。
- [x] B：storage/**、pipelines/merge.py、pipelines/export.py、utils/progress.py；存储封装及原子读改写。
- [x] A：services/**、main.py、api/server.py；使用新底层契约，修正 retry-failed 空任务问题。
- [x] F：tests/**（基类测试创建期间不碰 test_engine_abstraction.py）；隔离真实配置/数据，迁移内部 mock 到服务依赖点，新增真实契约测试，无等待实现 xfail。
- [ ] G：代码集成与 scripts/acceptance.py、scripts/offline_preview.py 已完成；中文验收报告由最终交接返回，docs/refactor/acceptance.md 待主会话落盘，真实浏览器闭环待主会话验收。

每项执行：先写对应失败测试 → 运行确认失败 → 实现 → 针对性测试 → 交接。共享工作区并行仅修改独占文件，不切分支。C/D/E/B 完成后 A 接入，F 最后运行完整套件；G 按 C→D→E→B→A→F 核对集成。

## G 集成进度（尚未最终验收）

- A 原交付缺失，G 已补 services 三服务及 CLI/API 接入；修复 retry-failed 构建范围和嵌套 enrollment 丢失。
- 最近一次完整通过：523 passed、1 skipped；该次核心 services/storage/spiders.engine/security/utils.http 各文件均超过 80%。此结果早于最终 loader/API 存储委托、session.close 和 PDF 职称修复，不代表最终工作区通过。
- 可选引擎最终专项：8 passed；js_render 91%、pdf_list 88%。
- 已创建跨平台 scripts/acceptance.py；尚未执行。最新全量复验及 git diff --check 请求被权限系统拒绝，需要用户审核后继续；A/F/G 暂不勾选完成。
- 不运行真实采集、真实网站验证或进攻测试。未创建最终验收报告；不得将阶段结果作为最终 PASS。

## 验收

基线：405 passed,1 skipped（旧套件存在真实路径写入问题，该结果不是隔离保证）。先修复测试隔离，后运行 python -m pytest tests/ -q；新模块导入、CLI --help、Flask test client、模拟双源并发、resume/retry、JSONL/Excel 输出、原子写失败和跨线程更新均须测试。覆盖率目标核心模块至少80%；记录实际结果，不用 xfail 或缩减范围掩盖缺口。真实网站及真实采集未运行时明确标记未验证。
