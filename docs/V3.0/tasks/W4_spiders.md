# W4 任务卡：采集插件（spiders + raw_converter）

## 角色

采集开发者。把现有五个引擎（static_list/ajax_api/js_render/pdf_list/yzw_api，见 spiders/ 目录）迁移为交付**真正原始批次**的 SpiderPlugin 包，新增 media_downloader 示例，并实现 raw_converter。

## 必读（只读这些）

- [README.md](README.md)
- `docs/V3.0/INTERFACES.md`（重点：RawDataDTO/RawDataBatch/MediaAsset、SpiderPlugin 协议、PipelineContext 的 http/cache 注入、错误码）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §2.3、§4.1–4.2、§5.1
- 现状代码：spiders/engine.py（SpiderEngine.fetch/parse、register_engine）、spiders/{static_list,ajax_api,js_render,pdf_list,yzw_api,url_resolver,detail_parser}.py、utils/http.py（PoliteSession：限速/重试/冷却/按域熔断，必须经 context 使用，不得自建 requests.Session 绕过）

## 可写范围（独占）

```text
plugins/spiders/**                 # static_html/ ajax_api/ js_render/ pdf_list/ yzw_api/ media_downloader/
converters/raw_converter.py
tests/test_spider_plugins.py
tests/fixtures/raw_pages/**        # 离线 fixture 页面/JSON/PDF（与 W5 共建解析对照夹具，命名加 w4_ 前缀避免冲突）
```

**禁止修改**：spiders/（旧目录原样保留，迁移期门面由 W1 集成时接转发）、contracts/、pipeline/、utils/http.py、其他 plugins 子目录。

## 交付清单（六个插件包，每个含 plugin.py + metadata.json）

metadata.json 按 INTERFACES.md 格式；plugin_type 均为 spider；entry_point 指向各自入口类；config_schema 用 additionalProperties=false 收紧参数（如 max_pages/delay）。

1. **static_html**（旧 static_list 迁移）：TaskConfigDTO → RawDataBatch。列表页发现 + 分页终止条件 + 详情 fan-out 都在 execute 内完成（受 context.http 管理）；每页/每详情产出一个 RawDataDTO，assets 里是原始 HTML MediaAsset(media_type="text", mime_type="text/html")。选择器来自已校验配置快照，不硬编码学校 URL。
2. **ajax_api**（旧 ajax_api 迁移）：SudyCMS/WebPlus 类 JSON 接口；响应存 assets（mime application/json），分页 token 循环有上限。
3. **js_render**（旧 js_render 迁移）：Playwright 渲染。**可选依赖**：import 失败时插件在预检阶段报"依赖缺失"而非崩溃；测试环境无 Playwright 时该插件用例显式 skip 并在报告中单列，不算通过。
4. **pdf_list**（旧 pdf_list 迁移）：PDF 原文作为 MediaAsset(media_type="document") 入 assets，解析留给 processor 侧或本插件声明的能力位（按 INTERFACES.md 决议）。
5. **yzw_api**（旧 yzw_api 迁移）：研招网 JSON 接口；**必须与静态 HTML 分属不同 parse 链**（配置层保证，你负责让输出 batch 的 schema_id 与之匹配）。
6. **media_downloader**（新增示例）：受控直接媒体 URL 下载——图片/音频/视频/二进制进 MediaAsset（media_type 分别 image/audio/video/binary），带大小限额（默认 10 MiB，超限流式落盘转 AssetRef/raw_ref，不全量读内存）、MIME 嗅探、URL 白名单域检查。这是多媒体契约的首个消费方，写法要成为后续媒体的参照。

### raw_converter.py

- 输入：任意来源的原始批次（含 legacy 形状：content 或 raw_ref 二选一的旧 RawDataDTO、旧引擎 list[dict] 结果经 LegacyRecordBatch 适配）。
- 输出：归一 RawDataBatch（assets 真值、schema_version、trace 完整）。规则：引用路径必须在允许目录内；未知编码明确诊断不静默 utf-8；legacy list[dict] **只能**走记录侧适配，不得伪装成 HTML RawDataBatch。

## 验收命令

```bash
python -m pytest tests/test_spider_plugins.py -q
python -m pytest tests/integration/test_static_slice.py -q    # Wave 1a 静态切片（需 W2 引擎 + W5 faculty_parse + W6 jsonl_store 就位）
```

每个插件必备用例：正常输入→输出 schema 合法；分页/请求去重/取消令牌生效；网络失败产出 ErrorDTO(retryable 正确)而非裸异常；空结果合法通过；js_render 无依赖时优雅降级。全部用离线 fixture + 模拟传输（参考 V2.2 offline_preview 的合成 HTTP 做法）。

## 特别注意

- "迁移"≠"包装"：不得只把旧引擎已解析的记录塞进新 DTO 充当完成——必须交付真正的原始材料批次 + 可独立工作的解析链路（W5 侧）。
- 抓取保持合规限速与站点访问边界；不把反爬绕过/验证绕过写成能力。凭据走受管引用，日志脱敏。
- 与 W5 的分工线：你交付"原料"（RawDataBatch），字段抽取归 W5 的 parser 插件；raw_pages fixture 双方共享同一份原始文件，解析期望各写各的测试。
- 每插件单测覆盖率 ≥80%；js_render/pdf_list 因可选依赖单独报告。
