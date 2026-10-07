## 变更内容

<!-- 一两句说明这个 PR 做了什么。 -->

## 关联事项

<!-- 关联 issue / 任务卡编号，例如：Closes #12、docs/V3.0/tasks/W6_xxx.md -->

## 验证方式

<!-- 列出你实际跑过的命令与关键输出。 -->

- [ ] `python -m pytest tests/ -q --ignore=tests/integration --ignore=tests/browser`
- [ ] `python -m mkdocs build --strict`（若改了文档）
- [ ] 其他：

## 检查清单

- [ ] 未改动冻结契约：`contracts/` 与 `docs/V3.0/INTERFACES.md`
- [ ] 新增/修改的插件已同步 `metadata.json`，且与 `plugin_manager/registry_snapshot.json` 一致
- [ ] 测试未通过 skip / xfail / 删除用例的方式变绿；断言未弱化
- [ ] 若新增依赖，已写入 `requirements.txt` 并说明用途
- [ ] 文档与代码一致（不声称未完成的修复已完成）

## 风险与回滚

<!-- 这个改动可能影响什么？出问题时怎么回滚？ -->