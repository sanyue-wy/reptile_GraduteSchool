# W2 任务卡：主干管道（pipeline / infra / 入口）

## 角色

主干开发者。实现 acquire→process→store→present 四阶段引擎、PipelineContext、受管基建，并把新端点接入 CLI/API（旧入口保持默认不变）。

## 必读（只读这些）

- [README.md](README.md)
- `docs/V3.0/INTERFACES.md`（W1 冻结契约；**未冻结前**只按本卡"契约摘要"搭建纯新增骨架，先做不依赖具体 DTO 字段的部分）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §3、§4.4、§5、§8.2
- 现状代码：spiders/engine.py（SpiderEngine/register_engine）、utils/http.py（PoliteSession）、utils/cache.py（CrawlCache）、services/（V2.2 三服务，Wave 2 才改造成门面，本期不动其内部）、main.py、api/server.py（现有 @app.route 清单即兼容面）

## 可写范围（独占）

```text
pipeline/**                          # engine.py + stages/{acquire,process,store,present}.py
infra/context.py                     # PipelineContext
infra/http.py                        # 对 PoliteSession 的受管包装（委托，不复制熔断逻辑）
infra/cache.py                       # 对 CrawlCache 的受管包装
infra/errors.py                      # 错误码 → ErrorDTO 映射
converters/request_converter.py      # schema_editor 产物/旧参数 → TaskConfigDTO + OutputSpec
converters/view_converter.py         # RecordBatch + StoreReceipt[] + OutputSpec + RunState → PresentationRequest
main.py                              # 只加 --v3-pipeline 类开关或子命令，旧参数行为零变化
api/server.py                        # 只加新端点（见交付 6），旧端点零变化
tests/test_pipeline_engine.py
tests/test_http_context.py
tests/integration/test_static_slice.py   # 与 W4/W5/W6/W7 共建的集成测试（各窗口贡献自己插件的用例段）
```

**禁止修改**：contracts/、plugins/base.py、utils/http.py、utils/cache.py、utils/progress.py（后三者是 V2.2 已验收实现，你只在 infra/ 里包装；确需改动 → 走 progress.md 仲裁）、plugin_manager/、各 plugins 子目录。

## 契约摘要（W1 冻结前先行用，以 INTERFACES.md 最终版为准）

- PipelineContext 注入：http（每任务独立会话）、cache、progress、受管存储句柄、日志、允许路径集合、取消令牌、配置快照（只读）、registry_revision、task_id/run_id。跨任务的限速/缓存/按域熔断共享状态必须显式共享且加锁——直接复用 V2.2 PoliteSession/CrawlCache 实例，**不得新建第二套熔断器**。
- 每任务独立 HTTP 会话与插件实例；setup 失败/execute 异常/取消均在 finally 关闭资源。
- 状态机：pending → running → succeeded/failed/partial/cancelled；命中有效检查点 pending → skipped。对外旧接口映射回 V2.2 枚举（done/success 等），不透传新枚举给旧前端。

## 交付清单

1. **pipeline/engine.py**：读取 pipeline.yaml/plugins.yaml（经 W1 的配置加载协议）→ 构建四阶段执行计划 → ThreadPoolExecutor 有界并发（默认 4 线程）→ 阶段间经 DTO 传递 → 产出 RunResult。无 DAG、无 asyncio。
2. **stages/acquire.py**：调用 SpiderPlugin.execute(TaskConfigDTO)；列表发现/分页/详情 fan-out 的调度约束在这里落地（最大页数、请求去重、每域并发、取消检查点）；输出 RawDataBatch → raw_converter（W4 提供，先 stub）归一。
3. **stages/process.py**：parse 链（RawDataBatch→RecordBatch）+ post 链（RecordBatch→RecordBatch，多步顺序执行）；每来源独立 parse 链，完成后按 dataset+profile 分组汇聚（教育分组含 university/college/year）。处理器只处理已取得材料，不发网络请求。
4. **stages/store.py**：同一 RecordBatch 向多个 storage 目标 fan-out，分别构造 StoreRequest；收集 StoreReceipt[]；required 目标失败 → run failed，可选目标失败 → partial。
5. **stages/present.py**：view_converter → PresentationRequest → PresenterPlugin.execute → RenderedOutputDTO；成品写 `data/runs/<run_id>/outputs/<output_id>/`（临时根下同理）；present 默认 optional，失败只重建展示不重抓。
6. **api/server.py 新端点**（计划书 §8.2 中标"拟新增"者）：POST /api/pipeline/validate（预检不执行插件）、POST /api/pipeline/run（返回 run_id，后台受控运行）、GET /api/pipeline/runs/<id>（状态/阶段结果/回执）、批准/版本激活端点（管理员权限，状态机完整，不只加按钮）。旧端点全部保持。
7. **main.py**：新增触发新链路的入口（如 `--engine v3` 或子命令），默认仍走 V2.2 服务；旧参数全集（school/category/source/year/workers/force/resume/retry-failed/delay/max-retries/timeout 及缓存/冷却/raw-dir/熔断参数）行为零变化，用 `--help` 快照对照验证。
8. **运行安全**：输出根目录进程锁（同根第二进程启动即拒）；Windows 下测锁释放、句柄关闭、replace 失败；原子 replace 之外，同规范化路径读改写整体加锁（与 W6 的锁协作协议在 INTERFACES.md 约定，你负责引擎侧持有）。

## 验收命令

```bash
python -m pytest tests/test_pipeline_engine.py tests/test_http_context.py -q
python main.py --help > /tmp/help_v3.txt && python main.py --help | findstr /c:"resume" /c:"retry-failed"   # 旧参数仍在
python -m pytest tests/integration/test_static_slice.py -q    # Wave 1a：需 W4/W5/W6/W7 的 static_html/faculty_parse/jsonl_store/table 就位
```

静态切片退出条件：离线 fixture 经真实插件（非全链 mock）跑通 acquire→process→store→present；JSONL 输出与旧格式逐行一致；取消令牌在安全检查点停止派发。

## 特别注意

- 迁移双轨：本期（对应计划书 Wave 1）旧 CLI/API 继续走 V2.2 服务，新链路仅离线独立运行；"切换"（旧服务改门面）属于后续集成期，由 W1 发起，你配合。
- 重试纪律：HTTP 层单请求重试归 PoliteSession；管道默认不整任务自动重试；总尝试预算要可观测，禁止两层循环相乘放大。
- 空结果是否合法由来源契约定义，引擎不擅自判失败。
- 所有测试用临时根目录 + 模拟网络；Flask 用 test client。
