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
- `tests/test_pipeline_engine.py` — pipeline 引擎测试（25 passed）

## 离线模拟网络

禁止在测试中发起真实 HTTP 请求。使用 fixture 提供的离线数据：

```python
@pytest.fixture
def mock_html():
    """提供离线 HTML fixture。"""
    return Path("tests/fixtures/raw_pages/w4_static_sample.html").read_text(encoding="utf-8")
```

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
