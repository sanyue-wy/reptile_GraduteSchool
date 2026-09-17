# Agent G 指导书：集成、合并与最终验收

> 对应阶段：全部阶段  
> 波次：Wave 0（接口冻结）+ Wave 2（合并集成）+ Wave 3（验收修复）  
> 预计工作量：3-5 天

## 1. 目标

统一合并所有 Agent 分支，解决冲突，跑全量回归，输出验收报告。

## 2. 可写文件

| 阶段 | 可写范围 |
|---|---|
| Wave 0 | 创建分支策略、建立验收脚本、冻结接口契约文档 |
| Wave 2 | 集成阶段可临时修改所有文件 |
| Wave 3 | 修复集成问题，输出验收报告 |

**新建文档**：
- `docs/refactor/interfaces.md` — 接口变更登记
- `docs/refactor/acceptance.md` — 最终验收报告

## 3. 合并顺序

```
1. Agent C  →  spiders/engine.py + spiders/*
2. Agent D  →  security/ + config/plugins.py
3. Agent E  →  utils/http.py + utils/cache.py
4. Agent B  →  storage/ + pipelines/* + utils/progress.py
5. Agent A  →  services/ + main.py + api/server.py
6. Agent F  →  tests/*
7. Agent G  →  总集成与验收
```

## 4. Wave 0：接口冻结与基础设施

### 4.1 创建分支策略

```bash
# 主开发分支
git checkout -b refactor/v2.2

# 各 Agent 工作分支
git checkout -b refactor/v2.2-agent-a
git checkout -b refactor/v2.2-agent-b
git checkout -b refactor/v2.2-agent-c
git checkout -b refactor/v2.2-agent-d
git checkout -b refactor/v2.2-agent-e
git checkout -b refactor/v2.2-agent-f
```

### 4.2 冻结接口契约文档

创建 `docs/refactor/interfaces.md`，记录所有冻结接口：

```markdown
# 接口变更登记

## 已冻结接口

### services/crawler_service.py
- CrawlTask: dataclass
- CrawlResult: dataclass
- CrawlerService.build_tasks(args) -> list[CrawlTask]
- CrawlerService.run_source_a(task) -> CrawlResult
- ...

### storage/jsonl_store.py
- JSONLStore.read_all() -> list[dict]
- JSONLStore.write_all(records, atomic=True) -> None
- ...

（以下省略，详见各 Agent 指导书）
```

### 4.3 建立 Smoke Test

创建 `tests/test_smoke.py`，作为集成检查的最小测试集：

```python
"""Smoke test：最小集成检查。"""
import pytest

def test_imports():
    """所有新模块可正常导入。"""
    from services.crawler_service import CrawlerService
    from services.merge_service import MergeService
    from services.export_service import ExportService
    from storage.jsonl_store import JSONLStore
    from storage.progress_store import ProgressStore
    from storage.config_store import ConfigStore
    from spiders.engine import SpiderEngine, ENGINE_REGISTRY
    from security.plugin_validator import validate_plugin_source, ValidationResult
    from utils.http import PoliteSession
    assert True

def test_cli_help():
    """CLI --help 不崩溃。"""
    import subprocess
    result = subprocess.run(["python", "main.py", "--help"], capture_output=True)
    assert result.returncode == 0

def test_api_server_import():
    """API 服务可导入。"""
    from api.server import app
    assert app is not None
```

### 4.4 建立验收脚本

创建 `scripts/acceptance.sh`（或 `.bat`）：

```bash
#!/bin/bash
set -e

echo "=== 1. 语法检查 ==="
python -m py_compile main.py
python -m py_compile api/server.py
python -m py_compile services/crawler_service.py
python -m py_compile services/merge_service.py
python -m py_compile services/export_service.py
python -m py_compile storage/jsonl_store.py
python -m py_compile storage/progress_store.py
python -m py_compile storage/config_store.py
python -m py_compile spiders/engine.py
python -m py_compile security/plugin_validator.py
python -m py_compile utils/http.py
python -m py_compile utils/cache.py
python -m py_compile utils/progress.py

echo "=== 2. 全量测试 ==="
pytest tests/ -q

echo "=== 3. 覆盖率 ==="
pytest tests/ --cov=services --cov=storage --cov=spiders --cov=utils \
    --cov=security --cov-report=term

echo "=== 4. Smoke Test ==="
pytest tests/test_smoke.py -v

echo "=== 5. CLI 手动验证 ==="
echo "请手动运行："
echo "  python main.py --school '东南大学' --source source_a --force"
echo "  检查 data/output/ 生成 .jsonl 和 summary.xlsx"

echo "=== 验收完成 ==="
```

## 5. Wave 2：按顺序合并

### 5.1 合并 Agent C（spiders/engine.py）

```bash
git merge refactor/v2.2-agent-c --no-ff
```

**预期冲突点**：无（C 只改 spiders/，不影响其他文件）

**验证**：
```bash
python -c "from spiders.engine import SpiderEngine, ENGINE_REGISTRY; print('OK')"
pytest tests/test_engine_abstraction.py -q
```

### 5.2 合并 Agent D（security/）

```bash
git merge refactor/v2.2-agent-d --no-ff
```

**预期冲突点**：`config/plugins.py`（D 修改了内部实现）

**验证**：
```bash
python -c "from security.plugin_validator import validate_plugin_source; print('OK')"
pytest tests/test_plugin_security.py -q
pytest tests/test_plugins.py -q
```

### 5.3 合并 Agent E（utils/http.py, utils/cache.py）

```bash
git merge refactor/v2.2-agent-e --no-ff
```

**预期冲突点**：无

**验证**：
```bash
pytest tests/test_http.py -q
pytest tests/test_cache.py -q
pytest tests/test_http_circuit.py -q
```

### 5.4 合并 Agent B（storage/ + pipelines）

```bash
git merge refactor/v2.2-agent-b --no-ff
```

**预期冲突点**：
- `pipelines/merge.py` — B 修改了内部实现，但保留旧接口
- `pipelines/export.py` — 同上
- `utils/progress.py` — B 修改了内部实现

**验证**：
```bash
pytest tests/test_merge.py -q
pytest tests/test_export.py -q
pytest tests/test_progress.py -q
pytest tests/test_storage_layer.py -q
```

### 5.5 合并 Agent A（services/ + main.py + api/server.py）

```bash
git merge refactor/v2.2-agent-a --no-ff
```

**预期冲突点**（重点！）：
- `main.py` — A 大幅重构，删除 CircuitBreaker，改用服务层
- `api/server.py` — A 修改了 `_run_crawl_task()` 等函数

**解决冲突策略**：
1. `main.py`：以 A 的版本为准，但检查 CLI 参数是否完整保留
2. `api/server.py`：以 A 的版本为准，但检查所有 17 个 API 路由是否保留
3. 检查 A 是否正确使用了 E 的 `PoliteSession.is_blocked()` 和 B 的 `JSONLStore`

**验证**：
```bash
pytest tests/test_integration.py -q
pytest tests/test_crawler_service.py -q
pytest tests/test_merge_service.py -q
```

### 5.6 合并 Agent F（tests/）

```bash
git merge refactor/v2.2-agent-f --no-ff
```

**预期冲突点**：`tests/conftest.py`（追加 fixtures）

**验证**：
```bash
pytest tests/ -q
```

## 6. Wave 3：全量验收

### 6.1 全量测试

```bash
# 1. 全量测试
pytest tests/ -q

# 2. 覆盖率
pytest tests/ --cov=services --cov=storage --cov=spiders --cov=utils \
    --cov=security --cov-report=term
# 目标：核心模块 ≥ 80%

# 3. 集成测试
pytest tests/test_integration.py -v
```

### 6.2 CLI 手动验证

```bash
# 1. Source A 单源采集
python main.py --school "东南大学" --source source_a --force
# 检查 data/output/东南大学_机械工程_faculty.jsonl

# 2. 双源采集 + 并发
python main.py --school "东南大学" --source source_a source_b --workers 4 --year 2026
# 检查 data/output/progress.json 无损坏

# 3. 断点续抓
python main.py --school "东南大学" --source source_a --resume
# 应跳过已完成

# 4. 失败重试
python main.py --retry-failed
# 应只执行失败项

# 5. 全量导出
python main.py --school "__all__" --source source_a --force
# 检查 data/output/summary.xlsx
```

### 6.3 API 手动验证

```bash
python api/server.py --port 5000 --no-browser
```

检查端点：
- `GET /api/overview` — 返回统计数据
- `GET /api/schools` — 返回学校列表
- `GET /api/schools/1` — 返回学校详情
- `POST /api/crawl` — 启动爬虫任务
- `GET /api/tasks/{task_id}` — 查询任务状态
- `GET /api/tutors` — 返回导师列表
- `GET /api/failures` — 返回失败记录
- `GET /api/config` — 返回配置
- `GET /api/plugins` — 返回插件列表

### 6.4 安全验证

```bash
python -c "
from security.plugin_validator import validate_plugin_source
# 安全插件
result = validate_plugin_source('''
PLUGIN_META = {\"name\": \"test\", \"kind\": \"processor\", \"version\": \"1\", \"author\": \"x\", \"description\": \"x\"}
def process(records, ctx): return records
''', kind='processor')
assert result.ok, f'安全插件应通过: {result.errors}'

# 危险插件
result = validate_plugin_source('import os', kind='processor')
assert not result.ok or result.warnings, '危险 import 应被检测'

print('安全验证通过')
"
```

### 6.5 性能验证

```bash
# 并发 4 任务
python main.py --school "东南大学" "上海交通大学" "中南大学" --source source_a --workers 4 --year 2026 --force
# 检查：
# 1. progress.json 无损坏（JSON 可解析）
# 2. 无死锁（程序正常退出）
# 3. 缓存命中增加（第二次运行明显加速）
```

### 6.6 输出验收报告

创建 `docs/refactor/acceptance.md`：

```markdown
# V2.2 重构验收报告

## 测试结果
- 全量测试：PASS / FAIL (X/Y)
- 集成测试：PASS / FAIL (X/Y)
- 覆盖率：XX%

## 功能验证
- [ ] CLI Source A 采集正常
- [ ] CLI 双源采集 + 并发正常
- [ ] 断点续抓正常
- [ ] 失败重试正常
- [ ] 全量导出 summary.xlsx 正常
- [ ] API 所有端点正常
- [ ] 安全验证通过
- [ ] 并发 4 任务无损坏

## 代码质量
- [ ] services/ 被 main.py 和 api/server.py 使用
- [ ] storage/ 统一 JSONL/进度/配置访问
- [ ] SpiderEngine 统一爬虫引擎
- [ ] security/ 统一插件安全检查
- [ ] PoliteSession.is_blocked() 可用
- [ ] 核心模块覆盖率 ≥ 80%

## 兼容性
- [ ] 旧 CLI 参数完全兼容
- [ ] 旧配置格式完全兼容
- [ ] 旧 JSONL 结构完全兼容

## 未解决问题
（列出遗留问题）

## 回滚方案
1. git revert 到重构前的 commit
2. 恢复 data/output/ 备份
```

## 7. 冲突预防清单

| 文件 | 冲突风险 | 预防措施 |
|---|---|---|
| `main.py` | **高** — A 大幅重构 | A 改完后冻结，其他 Agent 不碰 |
| `api/server.py` | **高** — A 修改服务调用 | A 改完后冻结 |
| `utils/progress.py` | **中** — B 修改内部实现 | B 保留所有公开 API 签名 |
| `utils/http.py` | **中** — E 增加新方法 | E 只增加，不删除 |
| `config/plugins.py` | **中** — D 修改内部实现 | D 保留所有公开 API 签名 |
| `pipelines/merge.py` | **低** — B 修改内部实现 | B 保留旧函数名 |
| `tests/conftest.py` | **低** — F 追加 fixtures | F 只追加，不删除 |

## 8. 回滚方案

1. **单 Agent 回滚**：`git revert <merge-commit>` 回退单个 Agent 的合并
2. **全量回滚**：`git reset --hard refactor/v2.2-base` 回退到重构前
3. **数据安全**：`data/output/` 和 `data/raw/` 不受代码回滚影响
4. **配置安全**：`config/school_data.json` 和 `config/plugins.json` 不在回滚范围内
