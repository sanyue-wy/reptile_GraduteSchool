# W5 任务卡：处理器插件（解析 / 归一 / 合并 / 统计）

## 角色

处理开发者。交付 processor 组插件包：parse 阶段（RawDataBatch→RecordBatch）与 post 阶段（RecordBatch→RecordBatch），复用 V2.2 已验收的归一/去重/合并算法，不重写匹配规则。

## 必读（只读这些）

- [README.md](README.md)
- `docs/V3.0/INTERFACES.md`（重点：NormalizedRecordDTO/RecordBatch、ParserPlugin 与 RecordProcessorPlugin 协议、education profile schema v1、record_id/provenance 规则）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §4.2、§5.1
- 现状代码：processors/__init__.py（register/dispatch + normalize_records/deduplicate_records/merge_records——**merge 是兼容占位**，实际多源合并在 services/merge_service.py）、parsers/yzw_major.py（研招解析模板）、services/merge_service.py（exact→strip→fuzzy 三阶匹配及既有 fixture 阈值）

## 可写范围（独占）

```text
plugins/processors/**              # faculty_parser/ yzw_major_parser/ normalize/ dedup/ education_merge/ statistics/
tests/test_processor_plugins.py
tests/fixtures/expected_records/** # 解析期望记录（与 W4 共享 tests/fixtures/raw_pages/ 原始文件，只读）
```

**禁止修改**：processors/（旧目录保留，dispatch 兼容视图由 W1 集成时接）、services/merge_service.py（复用其函数，import 调用；要改行为 → 走仲裁）、contracts/、pipeline/、其他 plugins 子目录。

## 交付清单（六个插件包，每个含 plugin.py + metadata.json，plugin_type=processor）

1. **faculty_parser**（parse 阶段，静态 HTML）：RawDataBatch → RecordBatch。从 static_html 插件产出的原始 HTML assets 中抽取教育字段（university/college/category/year/name/title/研究方向等，按 education profile v1 校验）；媒体引用（头像/图片 URL）写入 media_refs，保持可追踪。**纯解析，不发任何网络请求**。选择器参数来自实例 params（profile: education.tutor.v1）。
2. **yzw_major_parser**（parse 阶段，研招 JSON）：迁移 parsers/yzw_major.py 逻辑到插件包；输入 zyw_api 批次的 JSON assets；输出同 profile 的记录。
3. **normalize**（post 阶段）：复用 processors.normalize_records 算法（文本规范化、空值处理），包装为 RecordBatch→RecordBatch；不得原地改共享批次，返回新对象。
4. **dedup**（post 阶段）：复用 deduplicate_records；去重键规则随 profile 声明。
5. **education_merge**（post 阶段）：**真正的多源合并**——调用 services.merge_service 的 exact→strip→fuzzy 匹配（阈值与字段优先级用既有 fixture 固定，不得重新发明）；分组键 group_by=[university, college, year]，跨学校/学院绝不匹配；合并后 record_id 按 INTERFACES.md 自然键规则稳定生成，provenance 保留全部来源。单来源运行允许部分来源记录通过，不等待未选来源。
6. **statistics**（post 阶段）：group_by 分组计数/分布，结果写入 RecordBatch.stats（统计不改变主数据 records）。

### 通用要求

- 每插件 metadata 声明 input_schema/output_schema（parse 类：RawDataBatch.v1→RecordBatch.v1；post 类：RecordBatch.v1→RecordBatch.v1），与类属性一致。
- 字段损失、未知 schema 版本必须产出 ErrorDTO 明确诊断，不以宽松 dict 掩盖。
- 媒体能力（OCR/音频分析/转码）**只预留协议位**：metadata 加 capabilities 声明字段，本期实现留 NotImplemented 并文档标注"预留"，不宣称具备生产级处理能力。

## 验收命令

```bash
python -m pytest tests/test_processor_plugins.py -q
python -m pytest tests/integration/test_static_slice.py -q    # Wave 1a（需 W2/W4/W6 就位）
```

关键用例：
- faculty_parser 对 w4_ 前缀 fixture 页面解析出的记录与 expected_records golden 逐字段一致。
- education_merge 双源合并：同名导师 fuzzy 命中、跨学院同名不合并、合并记录 provenance 含两个 source_id（沿用 V2.2 merge fixture 阈值断言）。
- 空批次合法通过；非法 schema_id 在执行前拒绝。
- post 链顺序执行（normalize→dedup→merge→statistics）与乱序配置时的预检报错（后者由 W2 引擎负责，你提供 schema 声明使其可检）。

## 特别注意

- 旧 `pipelines/merge.py` 的调用方门面归 W1 集成期处理，你不要动 pipelines/ 目录。
- 旧 processors.dispatch 兼容视图最终从你的插件注册表派生（W1 接线），期间旧 dispatch 保持可用。
- "不得只包装旧已解析记录充当完成"同样适用于你：parser 类插件必须能从 W4 的**原始** RawDataBatch 工作，测试直接喂 raw_pages fixture，不喂已解析 list[dict]。
- 覆盖率 ≥80%。
