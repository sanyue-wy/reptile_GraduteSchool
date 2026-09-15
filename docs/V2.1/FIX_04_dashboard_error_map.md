# FIX 04 — Dashboard ERROR_TYPE_MAP 补全

**严重度**：🟡 中等
**问题根因**：`dashboard/failures.html` 中的 `ERROR_TYPE_MAP` 缺少 `connection_error`、`blocked`、`http_error` 三种错误类型，这些类型出现时前端 fallback 为灰色「未知错误」标签。
**涉及文件**：`dashboard/failures.html`
**依赖**：无（独立修改，纯前端）

---

## 问题详解

后端 `utils/errors.py` 的 `classify_error()` 实际可产出 6 种错误类型：

| error_type | 含义 | 前端是否覆盖 |
|---|---|---|
| `dns_error` | DNS 解析失败 | ✅ 已有 |
| `timeout` | 连接/读取超时 | ✅ 已有 |
| `parse_error` | 页面解析失败 | ✅ 已有 |
| `http_403` | 反爬封禁 | ✅ 已有（但后端实际产出 `blocked`） |
| `http_404` | 页面不存在 | ✅ 已有（但后端不产出此类型） |
| `connection_error` | 连接被重置/断开 | ❌ **缺失** |
| `blocked` | 反爬冷却 | ❌ **缺失** |
| `http_error` | HTTP 5xx | ❌ **缺失** |

注意：前端有 `http_403` / `http_404` 但后端从未产出过这两个值，属于前后端类型名不对齐。

---

## 修改指令

### 步骤 1：替换 `ERROR_TYPE_MAP`（约第 128-136 行）

```javascript
// 修改前
const ERROR_TYPE_MAP = {
  "http_403": { label: "反爬封禁",   color: "#ef4444", bg: "#fee2e2" },
  "http_404": { label: "页面不存在", color: "#f59e0b", bg: "#fffbeb" },
  "timeout":   { label: "连接超时",  color: "#f59e0b", bg: "#fffbeb" },
  "dns_error": { label: "DNS 错误",  color: "#3b82f6", bg: "#dbeafe" },
  "parse_error": { label: "解析失败", color: "#8b5cf6", bg: "#f3e8ff" },
};
```

改为（对齐 `utils/errors.py` 的 `ERROR_TYPES` 枚举）：

```javascript
// 修改后：与后端 classify_error() 产出的 6 种类型完全对齐
const ERROR_TYPE_MAP = {
  "dns_error":       { label: "DNS 错误",   color: "#3b82f6", bg: "#dbeafe" },
  "connection_error": { label: "连接断开",   color: "#f59e0b", bg: "#fffbeb" },
  "timeout":         { label: "请求超时",    color: "#f59e0b", bg: "#fffbeb" },
  "blocked":         { label: "反爬封禁",    color: "#ef4444", bg: "#fee2e2" },
  "http_error":      { label: "服务端错误",  color: "#ef4444", bg: "#fee2e2" },
  "parse_error":     { label: "解析失败",    color: "#8b5cf6", bg: "#f3e8ff" },
  // 兼容旧数据
  "http_403":        { label: "反爬封禁(旧)", color: "#ef4444", bg: "#fee2e2" },
  "http_404":        { label: "页面不存在(旧)", color: "#f59e0b", bg: "#fffbeb" },
};
```

保留 `http_403` / `http_404` 的兼容项，避免历史数据中的旧类型显示为「未知错误」。

---

## 验证方法

1. 用浏览器打开 `dashboard/failures.html`
2. 检查现有失败记录的标签是否从「未知错误」变为对应中文标签
3. 在浏览器控制台手动测试：
```javascript
console.log(getErrorTypeInfo("connection_error"));
// 应输出 { label: "连接断开", color: "#f59e0b", bg: "#fffbeb" }
```

---

## 影响范围

仅修改 `dashboard/failures.html` 中一个 JS 对象，纯前端变更，不影响后端逻辑。
