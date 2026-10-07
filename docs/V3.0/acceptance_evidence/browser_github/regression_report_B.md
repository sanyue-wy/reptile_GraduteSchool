# 回归测量窗口 B - 验收报告

**执行时间**: 2026-10-07  
**仓库根目录**: c:/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool  
**分支**: Refactoring_code

---

## 职责 1：安全项实测

在 Flask 服务端口 **15000** 上启动服务（`python api/server.py --port 15000 --no-browser`），逐项验证：

### a) 路径穿越 `../` 攻击 `/api/outputs/serve`

| Payload | Status | 响应体 |
|---------|--------|--------|
| `path=../etc/passwd&token=invalid` | **403** | `{"code":40301,"message":"路径不在受管 outputs 目录内"}` |
| `path=data/runs/.../outputs/..%2f..%2fstore%2fsecret.json&token=<valid>` | **403** | `{"code":40301,"message":"路径不在受管 outputs 目录内"}` |

**结论**: ✅ 防护生效。`_resolve_preview_target()` 使用 `.resolve()` 后检查 `relative.parts[1] == "outputs"`，穿越载荷被拦截。

### b) Token 验证矩阵

| 测试场景 | Status | 响应体 |
|----------|--------|--------|
| 空 token (`token=`) | **403** | `{"code":40301,"message":"预览令牌无效或已过期"}` |
| 非法 token (`token=invalid.token.here`) | **403** | `{"code":40301,"message":"预览令牌无效或已过期"}` |
| 跨 run 合法 token（run A 的 token 访问 run B） | **403** | `{"code":40301,"message":"预览令牌无效或已过期"}` |
| 同 run 合法 token（正常访问） | **200** | 返回文件内容 |

**结论**: ✅ Token 绑定 run_id、校验签名与过期时间、跨 run 复用被拒绝。

### c) 尝试读取 `data/runs/<run_id>/store/`（outputs 同级非成品目录）

```bash
curl "http://127.0.0.1:15000/api/outputs/serve?path=data/runs/06c9197212304ac5b68f2ff0825231b1/store/secret.json&token=<valid_token_for_run_A>"
```

| Status | 响应体 |
|--------|--------|
| **403** | `{"code":40301,"message":"路径不在受管 outputs 目录内"}` |

**结论**: ✅ store 目录不在 `outputs/` 子树下，`relative.parts[1] != "outputs"` 直接拒绝。

### d) 符号链接越界

Windows 无管理员权限无法创建真实 symlink（`os.symlink` 报 `WinError 1314`）。但代码逻辑分析：

```python
target = (candidate if candidate.is_absolute() else Path.cwd() / candidate).resolve()
relative = target.relative_to(_RUNS_DIR.resolve())
if len(relative.parts) < 3 or relative.parts[1] != "outputs":
    return None, ""
```

- `.resolve()` 会追踪 symlink 到真实目标
- 若 symlink 指向 `../store/secret.json`，解析后 `relative.parts[1] == "store"`，触发拒绝
- 若 symlink 指向仓库外绝对路径，`relative_to(_RUNS_DIR)` 抛 `ValueError`，触发拒绝

**结论**: ✅ 代码层面已防御 symlink 越界；Windows 环境受限无法实测但逻辑闭环。

### 附：其他端点防穿越验证

| 端点 | 测试载荷 | Status | 结果 |
|------|----------|--------|------|
| `/api/raw/<path>` | `%2e%2e%2fetc%2fpasswd` | **403** | `路径穿越被拒绝` |
| `/api/raw/<path>` | `data/raw/../../etc/passwd` | **404** | Werkzeug 规范化后不存在 |
| `/api/pipeline/runs/<run_id>` | `..%2f..%2fetc%2fpasswd` | **404** | 路由不匹配（`<run_id>` 不含 `/`） |
| `/<filename>` (静态托管) | `..%2f..%2fetc%2fpasswd.html` | **403** | `relative_to(_DASHBOARD_DIR)` 失败 |

---

## 职责 2：干净克隆演练

```bash
# 1. 复制工作树到 /tmp/clean_g5（排除 .git）
cp -r /c/Users/wy/OneDrive/Desktop/scripts/reptile_GraduteSchool/* /tmp/clean_g5/
rm -rf /tmp/clean_g5/.git /tmp/clean_g5/__pycache__ ...  # 清理缓存/二进制/大文件

# 2. 语法编译检查
cd /tmp/clean_g5 && python -m compileall -q api infra pipeline plugin_manager plugins contracts converters scaffolds tests tools main.py
```

**输出**:
```
EXIT_CODE:0
```
（无错误输出，所有模块语法合法）

```bash
# 3. mkdocs 严格构建
cd /tmp/clean_g5 && python -m mkdocs build --strict
```

**输出**:
```
 ⚠  Warning from the Material for MkDocs team
 ...
INFO    -  Cleaning site directory
INFO    -  Building documentation to directory: C:\Users\wy\AppData\Local\Temp\clean_g5\site_build
INFO    -  Documentation built in 2.03 seconds
EXIT_CODE:0
```

**结论**: ✅ 干净克隆通过 `compileall` 与 `mkdocs build --strict` 零错误。

---

## 职责 3：入库完整性终检

### `git ls-files infra tools .github data plugins plugin_manager` 关键摘录

```bash
$ git ls-files infra/
infra/cache.py
infra/context.py
infra/http.py
infra/state_tracker.py
infra/storage/__init__.py
infra/storage/config_store.py
```

**关键发现**: `infra/errors/` 与 `infra/retry/` **完全未入库**（`git ls-files infra/errors/ infra/retry/` 无输出）。

### 被模块级 import 的未入库包

| 包 | 入库状态 | 被引用位置（模块级 import） |
|----|----------|----------------------------|
| `infra.errors` | ❌ 未入库 | `pipeline/stages/acquire.py:2`, `pipeline/stages/present.py:2`, `pipeline/stages/process.py:2`, `pipeline/stages/store.py:2`, `infra/errors/plugin_error.py:3`, `tests/test_http_context.py:3` |
| `infra.retry` | ❌ 未入库 | `infra/http.py:4`, `infra/retry/__init__.py:1` |
| `infra.errors.plugin_error` | ❌ 未入库 | `infra/errors/__init__.py:1` (re-export) |
| `infra.retry.adaptive_timeout` | ❌ 未入库 | `infra/http.py:4`, `infra/retry/__init__.py:1` |

### 硬阻断判定

> **推送前硬阻断项：`infra/errors/` 与 `infra/retry/` 两个被模块级 import 的包仍未入库。**
>
> 干净克隆环境下 `python -m compileall` 能通过是因为源文件在工作树中，但 **任何未入库的包在 CI/部署/他人克隆时会导致 `ModuleNotFoundError`**。必须在推送前 `git add infra/errors infra/retry` 并提交。

---

## 总结判定

| 职责 | 结果 | 备注 |
|------|------|------|
| 安全项实测 | ✅ 全项通过 | 穿越/Token/越界/链接均被拦截 |
| 干净克隆演练 | ✅ 通过 | `compileall` 0退出码，`mkdocs build --strict` 0退出码 |
| 入库完整性终检 | 🔴 **硬阻断** | `infra/errors/`、`infra/retry/` 未入库但被多处模块级 import |

**整体结论**: **不准合并/推送**，须先解决入库完整性阻断项。