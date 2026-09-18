# W6 任务卡：存储插件（JSONL / Excel / SQLite / 进度 / 媒体）

## 角色

存储开发者。把 V2.2 已验收的 JSONL/Excel 导出与进度存储升级为 storage 组插件包，新增 SQLite 与媒体存储，保证幂等、回执、原子写与路径锁语义。

## 必读（只读这些）

- [README.md](README.md)
- `docs/V3.0/INTERFACES.md`（重点：StoreRequest/StoreReceipt、StoragePlugin 协议、路径锁协作协议、output_ref 命名空间规则）
- [../PLUGIN_CONFIG_PLAN.md](../PLUGIN_CONFIG_PLAN.md) §4.1、§5.3–5.4
- 现状代码：storage/jsonl_store.py（write_all/append，tempfile.mkstemp+os.replace）、storage/file_utils.py（原子 I/O 工具）、storage/progress_store.py（加锁读改写）、exporters/__init__.py（jsonl/xlsx dispatch）、utils/progress.py（ProgressTracker 门面）

## 可写范围（独占）

```text
plugins/storage/**                 # jsonl_store/ xlsx_store/ sql_store/ progress_store/ media_store/
infra/storage/**                   # 原子 I/O、媒体引用解析、受管输出工作区（引擎侧进程锁归 W2，你提供同路径文件锁）
utils/progress.py                  # 只允许"加不改行为"：新接口追加；既有公开方法与锁零变化
tests/test_storage_plugins.py
```

**禁止修改**：storage/（旧目录保留，你的插件先委托其实现再逐步接管内部）、contracts/、pipeline/、其他 plugins 子目录。

## 交付清单（五个插件包，每个含 plugin.py + metadata.json，plugin_type=storage）

通用约束：显式副作用、每目标独立 StoreReceipt(target_id, written/skipped/failed, records_written, output_ref, error)；幂等键来自 StoreRequest，重跑不产生重复副作用；不承诺跨文件/SQLite 全局事务——报告哪些目标成功即可。

1. **jsonl_store**：包装 storage/jsonl_store.py；params: {format: legacy_education_v1|generic_record, output_dir}。legacy 模式输出与旧 data/output JSONL 逐行一致（golden 对照）；generic 模式按 NormalizedRecordDTO 全字段。**与 jsonl_presenter（W7）可共享序列化器函数，但写不同命名空间**：store 写 data/output（兼容）或 runs 下的 store 区，presenter 写 runs/<run_id>/outputs/<output_id>/。
2. **xlsx_store**：包装 exporters 的 xlsx 逻辑；列集与旧 Excel 一致（用 openpyxl 读回断言单元格/列，不比较 ZIP 二进制）。
3. **sql_store**（新增）：SQLite；稳定自然键 UPSERT（record_id 唯一约束）；事务内完成批量写入；schema 迁移脚本随插件包（schemas/init.sql）；故障注入测试验证无半库状态。
4. **progress_store**（快照导出）：把 ProgressTracker 当前状态导出为快照文件（可选 enabled）；注意边界——运行状态管理由引擎经 infra.progress 持续保存，本插件只做**导出**，禁用它不能丢失运行状态。
5. **media_store**（新增）：MediaAsset/AssetRef 落盘到受管媒体目录（runs/<run_id>/media/），文件名 = 内容摘要前缀防冲突；记录 ref→路径映射表；超限流式拷贝不全量读内存；引用路径解析必须限制在允许目录内。

### infra/storage/

- 原子 I/O：复用并下沉 storage/file_utils 的实现（同一实现、同一缓存/熔断状态，勿复制第二套）。
- **同规范化路径文件锁**：跨存储实例共享的锁注册表（模块级单例 + threading.Lock），读改写整体加锁；Windows 下测锁释放与句柄关闭。与 W2 的输出根**进程锁**是两层不同机制，协作协议写进 INTERFACES.md（走仲裁流程登记）。
- 受管输出工作区：runs/<run_id>/{store,media,outputs} 布局创建与清理策略。

## 验收命令

```bash
python -m pytest tests/test_storage_plugins.py -q
python -m pytest tests/integration/test_static_slice.py -q    # Wave 1a：jsonl golden 对照在此切片中执行
```

关键用例：
- 幂等：同一 StoreRequest 执行两次 → 第二次 skipped 计数正确，文件内容不变。
- 原子性：replace 失败/中途 kill → 无半文件、临时文件被清理。
- 并发：四线程对同一路径读改写无丢失更新（这是文件锁的用例，不是多进程证据）。
- SQLite：故障注入（写入中异常）后重放 → UPSERT 结果一致。
- 回归：utils/progress.py 既有公开接口测试全部保持通过（V2.2 基线用例不得改）。

## 特别注意

- 旧 exporters/pipelines/export.py 的门面转发由 W1 集成期接线，期间旧 dispatch("jsonl"/"xlsx") 保持可用。
- 必需目标失败 vs 可选目标失败的 run 级判定由 W2 引擎做，你只需如实填 StoreReceipt.error。
- 覆盖率 ≥80%；sql_store/media_store 为新代码要求更严，建议 ≥85%。
