# V2.1 Bug 修复指导索引

**版本**：V2.1
**创建日期**：2026-09-15
**背景**：对 `测试大学 · 机械学院` DNS 错误事件的全链路诊断，共发现 5 个代码缺陷。

---

## 修复清单（可并行执行）

| # | 文件 | 严重度 | 状态 |
|---|------|--------|------|
| 1 | [FIX_01_retry_dedup.md](FIX_01_retry_dedup.md) | 🔴 严重 | 待修复 |
| 2 | [FIX_02_return_arity.md](FIX_02_return_arity.md) | 🔴 严重 | 待修复 |
| 3 | [FIX_03_circuit_breaker_dns.md](FIX_03_circuit_breaker_dns.md) | 🟡 中等 | 待修复 |
| 4 | [FIX_04_dashboard_error_map.md](FIX_04_dashboard_error_map.md) | 🟡 中等 | 待修复 |
| 5 | [FIX_05_dashboard_stats_card.md](FIX_05_dashboard_stats_card.md) | 🟡 中等 | 待修复 |

> **各修复之间零耦合**，可分配给不同人同步进行。
> 每份文档包含：问题描述、涉及文件、具体修改指令、验证方法。
