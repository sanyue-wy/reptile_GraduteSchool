# 10 - 测试与验收

> **状态**：初稿
> **读者**：所有插件开发者

## Fixture 约定

所有测试使用**临时根目录** + **模拟网络**，禁止污染 `data/`、`config/` 真实内容。

```python
import pytest
from pathlib import Path

@pytest.fixture
def tmp_workspace(tmp_path):
    """创建临时工作空间。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace
```

参考现有测试模式：
- `tests/test_spider_plugins.py` — spider 插件测试（49 passed）
- `tests/test_processor_plugins.py` — processor 插件测试（34 passed）
- `tests/test_pipeline_engine.py` — pipeline 引擎测试（23 passed；2026-10-01 G4 实测更正，原文写 25）

## 离线模拟网络

禁止在测试中发起真实 HTTP 请求。使用 fixture 提供的离线数据：

```python
@pytest.fixture
def mock_html():
    """提供离线 HTML fixture。"""
    return Path("tests/fixtures/raw_pages/w4_static_list_page.html").read_text(encoding="utf-8")
```

> ⚠️ 更正（2026-10-01，G4）：原文写 `w4_static_sample.html`，该文件**不存在**，
> 照抄会 `FileNotFoundError`。实际文件名为 `w4_static_list_page.html`。
> 该目录下真实样本请先 `ls tests/fixtures/raw_pages/` 确认，勿凭记忆书写。

Fixture 文件位置：
- `tests/fixtures/raw_pages/` — 原始页面样本
- `tests/fixtures/expected_records/` — 期望输出记录
- `tests/fixtures/generated_plugin/` — 脚手架生成的测试插件

## 覆盖率要求

| 模块 | 最低覆盖率 |
|---|---|
| contracts/ | ≥90% |
| plugins/base.py | ≥90% |
| 各插件包核心路径 | 100% |

检查覆盖率：

```bash
python -m pytest tests/ --cov=plugins --cov-report=term-missing
```

## 测试分类

| 目录/文件 | 类型 | 说明 |
|---|---|---|
| tests/test_contracts.py | 契约测试 | DTO 签名、字段校验 |
| tests/test_spider_plugins.py | 插件单测 | 采集插件 |
| tests/test_processor_plugins.py | 插件单测 | 处理器插件 |
| tests/test_schema_editor.py | 工具单测 | schema_editor |
| tests/test_scaffolds.py | 工具单测 | 脚手架 CLI |
| tests/integration/ | 集成测试 | 离线 fixture 四阶段贯穿 |

## 脚手架生成物测试

```bash
# 生成并测试
python -m scaffolds.cli new spider test_probe
python -m pytest tests/fixtures/generated_plugin/test_probe -v
```

生成的 `test_plugin.py` 包含一个必过用例：元数据自洽性检查。

## 进度登记规范

完成测试后在 `docs/V3.0/tasks/progress.md` 登记：

```markdown
## Wn 窗口名

- 已完成：
  - 验收命令实测：
    - `python -m pytest tests/test_xxx.py -q` → N passed in Xs
- 未完成：
- 阻塞/问题：
```

**红线**："完成"必须有验收命令的实际输出佐证；没跑过的写"未验证"。

## 不运行真实学校采集

```bash
# 禁止
python main.py --school "某某大学"    # 不要这样做

# 允许
python -m pytest tests/ -q           # 全部离线
```

## 许可证合规

仓库根目录的 `NOTICE` 列出了本项目借鉴的开源项目及其许可证。`LICENSE` 文件声明本项目采用 MIT 许可证。

### 新增依赖时的检查清单

添加第三方包到 `requirements.txt` 前，确认以下事项：

1. **许可证兼容性**：该包的许可证与 MIT 是否兼容？常见兼容许可证：
   - MIT, BSD-2, BSD-3, Apache-2.0, ISC, HPND — 通常兼容
   - GPL, AGPL — 传染性，**不兼容**，需要特殊评估
2. **归属要求**：Apache-2.0 要求保留 NOTICE 文件；BSD 要求保留版权声明。直接在 `NOTICE` 中追加该包信息即可。
3. **版本锁定**：在 `requirements.txt` 中使用 `==` 固定版本，避免上游许可证变更引入风险。

### 在插件中使用第三方代码

插件目录下若有独立的第三方代码片段（非通过 pip 引入），必须在该插件的 `README.md` 中注明来源和许可证，例如：

```markdown
## 许可证声明

本插件的 template_parser 模块包含来自 ExampleLib (BSD-3-Clause) 的代码，
原作者：xxx，URL：https://github.com/xxx/example-lib
```

### NOTICE 文件维护

`NOTICE` 文件记录项目的借鉴来源，不随依赖变化。仅在设计上新增重要借鉴对象时才需更新。

## 命名 / 版本 / 依赖 / 错误处理 清单

### 命名规范

| 规则 | 示例 | 说明 |
|---|---|---|
| 插件目录名 | `static_html`, `jsonl_store` | 小写 + 下划线 |
| 类名 | `StaticHtmlSpiderPlugin`, `JsonlStorePlugin` | PascalCase + 对应后缀 |
| entry_point | `plugins.spiders.static_html.plugin:StaticHtmlSpiderPlugin` | `module.path:ClassName` 格式 |
| schema ID | `TaskConfigDTO.v1` | `<DTO名>.v<版本>` |

**反面示例**：
```python
# 错误：类名双后缀
class MyPluginPlugin(BasePlugin): ...
entry_point: "plugins.spiders.my_plugin.plugin:MyPluginPlugin"
```

**修复后**：
```python
# 正确：类名无双后缀
class MyPlugin(BasePlugin): ...
entry_point: "plugins.spiders.my_plugin.plugin:MyPlugin"
```

### 版本控制

| 场景 | 版本号 |
|---|---|
| 初始插件 | `1.0.0` |
| 小幅修复 | `1.0.1`, `1.0.2` |
| 功能增量 | `1.1.0`, `1.2.0` |
| 大版本破坏 | `2.0.0` |

**red line**：`entry_point` 中的类名变更后，`metadata.json` 中 `entry_point` 必同步更新。

### 依赖声明

| 字段 | 必填 | 说明 |
|---|---|---|
| `dependencies` | 否 | 运行时依赖列表 |
| `min_core_version` | 否 | 最低平台版本 |
| `license` | 否 | 插件许可证 |

**错误清单**：
1. `dependencies` 遗漏运行时必需库 → 部署失败
2. `min_core_version` 填太低 → 接口不兼容
3. `license` 填 GPL 类 → 触发警告，要求特殊评估

### 错误处理模式

```python
from contracts.result import ErrorDTO

error = ErrorDTO(
    code="VALIDATION_MISSING_REQUIRED",
    message="字段 title 必填",
    stage="process",
    retryable=False,
)
```

| 常见错误码 | 可重试 | 原因 |
|---|---|---|
| HTTP_TIMEOUT | 是 | 网络波动 |
| PARSE_FAILED | 否 | 内容结构变化 |
| VALIDATION_SCHEMA_MISMATCH | 否 | schema 版本不匹配 |
| PIPELINE_CONFIG_INVALID | 否 | 配置错误 |

**调试建议**：
- 检查 `stage` 字段定位问题阶段
- 查看 `diagnostics`（脱敏后）辅助定位
- `retryable=True` 时注意重试次数上限
