# FIX 05 — Dashboard 统计卡片区添加 DNS 错误计数

**严重度**：🟡 中等
**问题根因**：`dashboard/failures.html` 统计卡片区只有 4 张（总失败数、HTTP 错误、超时、解析错误），缺少 DNS 错误统计卡，`dns_error=1` 时数据无处显示。
**涉及文件**：`dashboard/failures.html`
**依赖**：无（独立修改，纯前端）

---

## 问题详解

后端 `GET /api/failures` 返回的 `summary` 包含 `dns_error` 字段，但前端没有对应 DOM 元素和 JS 逻辑。当前效果：`dns_error=1` 时，仅「总失败数」显示 1，其余 3 张卡片全部为 0，误导用户以为无具体错误。

---

## 修改指令

### 步骤 1：在 HTML 统计卡片区添加第 5 张卡片

定位 `dashboard/failures.html` 中的 `<div class="error-summary" id="error-summary">` 区域（约第 63 行），在「解析错误」卡片之后添加：

```html
<div class="error-stat"><h3 style="color:#3b82f6">0</h3><p>DNS 错误</p></div>
```

修改后完整结构：
```html
<div class="error-summary" id="error-summary">
  <div class="error-stat"><h3 style="color:var(--danger)">0</h3><p>总失败数</p></div>
  <div class="error-stat"><h3 style="color:var(--warning)">0</h3><p>HTTP 错误</p></div>
  <div class="error-stat"><h3 style="color:var(--warning)">0</h3><p>超时</p></div>
  <div class="error-stat"><h3 style="color:var(--warning)">0</h3><p>解析错误</p></div>
  <div class="error-stat"><h3 style="color:#3b82f6">0</h3><p>DNS 错误</p></div>  <!-- 新增 -->
</div>
```

### 步骤 2：在 `updateStats()` JS 函数中添加 DNS 计数

找到 `updateStats` 函数（约第 188 行），在 `stats[3].textContent = parseCount;` 之后添加：

```javascript
// 新增：DNS 错误统计
const dnsCount = items.filter(f => f.error_type === "dns_error").length;
stats[4].textContent = dnsCount;
```

`stats` 由 `document.querySelectorAll(".error-stat h3")` 返回，新增第 5 个 `<h3>` 后索引自动变为 0-4，无需额外修改查询语句。

---

## 验证方法

1. 浏览器打开 `dashboard/failures.html`
2. 确认统计区显示 5 张卡片，最后一张为「DNS 错误」
3. 当前 `failures.json` 中 `dns_error=1`，预期布局：

```
[总失败数: 1] [HTTP错误: 0] [超时: 0] [解析错误: 0] [DNS错误: 1]
```

4. 可临时在浏览器控制台模拟：
```javascript
updateStats([
  {error_type: "dns_error"}, {error_type: "timeout"}, {error_type: "dns_error"}
]);
// 预期：总失败数3, HTTP0, 超时1, 解析0, DNS2
```

---

## 影响范围

仅修改 `dashboard/failures.html` 的 HTML 结构和 JS，纯前端变更，不影响后端。
