# 模块四：前端 API 对接与页面完善实施指南

> **模块定位**：独立可并行开发｜**依赖接口**：`INTERFACE_SPEC.md` 第 5 节 API 端点｜**可在后端开发前独立推进**

---

## 1. 模块目标

将现有 `dashboard/` 下的前端页面从**Mock 数据**改为**真实 API 调用**，补齐缺失页面，完善交互。

| 页面 | 现状 | 目标 |
|------|------|------|
| `index.html` 总览 | Chart.js + 硬编码 Mock 数据 | 调用 `/api/overview`，实时数据 |
| `schools.html` 学校列表 | 不存在或空壳 | 完整实现：列表 + 筛选 + 分页 + 一键采集 |
| `tutors.html` 导师列表 | 不存在或空壳 | 完整实现：列表 + 多维筛选 + 详情弹窗 |
| `failures.html` 失败记录 | 不存在或空壳 | 完整实现：列表 + 重试 + 忽略 |
| `config.html` 配置管理 | 不存在或空壳 | 完整实现：在线编辑 + 测试连接 |

---

## 2. 接口契约（INTERFACE_SPEC.md 第 5 节）

### 2.1 统一响应格式

```javascript
// 成功响应
{ code: 0, data: {...} }

// 失败响应
{ code: 40001, message: "错误描述", detail: "可选详情" }
```

### 2.2 前端调用封装（`dashboard/api.js`）

```javascript
// 文件：dashboard/api.js
// 全局 API 封装，所有页面共用

const API_BASE = window.location.origin;

async function apiCall(endpoint, options = {}) {
    /**
     * 统一 API 调用封装
     * @param {string} endpoint - 如 "/api/overview"
     * @param {object} options - fetch 选项（method, body, headers 等）
     * @returns {object} data 字段内容
     * @throws {Error} 非 0 code 时抛出
     */
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: { "Content-Type": "application/json" },
        ...options,
    };
    
    try {
        const resp = await fetch(url, config);
        const json = await resp.json();
        
        if (json.code !== 0) {
            const err = new Error(json.message || "请求失败");
            err.code = json.code;
            err.detail = json.detail;
            throw err;
        }
        
        return json.data;
    } catch (err) {
        if (err.code) throw err;  // 业务错误
        throw new Error(`网络错误: ${err.message}`);
    }
}


// ========== 高层封装 ==========

const api = {
    // 总览
    overview: () => apiCall("/api/overview"),
    
    // 学校列表
    schools: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return apiCall(`/api/schools?${qs}`);
    },
    
    schoolDetail: (id) => apiCall(`/api/schools/${id}`),
    
    // 采集任务
    startCrawl: (params) => apiCall("/api/crawl", {
        method: "POST",
        body: JSON.stringify(params),
    }),
    
    taskProgress: (taskId) => apiCall(`/api/tasks/${taskId}`),
    
    // 导师列表
    tutors: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return apiCall(`/api/tutors?${qs}`);
    },
    
    tutorDetail: (school, name) => apiCall(`/api/tutors/${encodeURIComponent(school)}/${encodeURIComponent(name)}`),
    
    // 导出
    exportData: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        window.open(`${API_BASE}/api/tutors/export?${qs}`, "_blank");
    },
    
    // 失败记录
    failures: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return apiCall(`/api/failures?${qs}`);
    },
    
    retryFailures: (ids) => apiCall("/api/failures/retry", {
        method: "POST",
        body: JSON.stringify({ failure_ids: ids }),
    }),
    
    ignoreFailure: (id) => apiCall(`/api/failures/${id}/ignore`, { method: "POST" }),
    
    // 配置
    getConfig: () => apiCall("/api/config"),
    getSchoolConfig: (name) => apiCall(`/api/config/schools/${encodeURIComponent(name)}`),
    saveSchoolConfig: (name, data) => apiCall(`/api/config/schools/${encodeURIComponent(name)}`, {
        method: "PUT",
        body: JSON.stringify(data),
    }),
    saveGlobalConfig: (data) => apiCall("/api/config/global", {
        method: "PUT",
        body: JSON.stringify(data),
    }),
    testConnection: (params) => apiCall("/api/config/test", {
        method: "POST",
        body: JSON.stringify(params),
    }),
    
    // 原件查看
    rawFile: (path) => `${API_BASE}/api/raw/${encodeURIComponent(path)}`,
};
```

---

## 3. 各页面实现规范

### 3.1 总览页（`index.html`）

**数据源**：`GET /api/overview`

**响应结构**：
```json
{
  "code": 0,
  "data": {
    "total_schools": 147,
    "total_tutors": 5234,
    "matched_count": 4102,
    "partial_count": 876,
    "failures_count": 256,
    "crawl_status": "idle",
    "recent_activity": [
      {"time": "2026-09-14 10:30", "action": "东南大学机械完成", "status": "success"}
    ],
    "category_distribution": {
      "mechanical": 2800,
      "automation": 2434
    },
    "match_rate_trend": [
      {"date": "2026-09-01", "rate": 0.72},
      {"date": "2026-09-14", "rate": 0.78}
    ]
  }
}
```

**页面元素**：

| 组件 | 数据字段 | 交互 |
|------|----------|------|
| 统计卡片（4张） | total_schools, total_tutors, matched_count, failures_count | 点击跳转对应列表页 |
| 匹配率饼图 | category_distribution | Chart.js doughnut |
| 匹配趋势折线图 | match_rate_trend | Chart.js line |
| 最近活动列表 | recent_activity | 滚动列表，每条显示图标+文字 |
| 全局采集按钮 | - | 点击打开采集参数弹窗 |

### 3.2 学校列表页（`schools.html`）

**数据源**：`GET /api/schools?q=&status=&category=&page=1&page_size=20`

**响应结构**：
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "university": "东南大学",
        "level": "985",
        "categories": [
          {
            "college": "机械工程学院",
            "category": "mechanical",
            "tutor_count": 45,
            "matched_count": 38,
            "last_crawl": "2026-09-14T10:30:00",
            "status": "done"
          }
        ],
        "failure_count": 2
      }
    ],
    "total": 147,
    "page": 1,
    "page_size": 20
  }
}
```

**页面元素**：

| 组件 | 功能 |
|------|------|
| 搜索框 | 按校名模糊搜索（q 参数） |
| 筛选栏 | 学校级别（985/211/双一流）、类别（mechanical/automation）、状态（done/running/idle/failed） |
| 学校表格 | 校名、级别、学院数、导师总数、匹配数、失败数、最后采集时间、操作按钮 |
| 操作按钮 | "采集"（POST /api/crawl）、"查看"（跳转详情）、"配置"（打开配置弹窗） |
| 分页组件 | 上一页/下一页 + 页码显示 |

### 3.3 导师列表页（`tutors.html`）

**数据源**：`GET /api/tutors?q=&school=&college=&level=&match=&page=1&page_size=20`

**响应结构**：
```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "name": "张三",
        "university": "东南大学",
        "college": "机械工程学院",
        "category": "mechanical",
        "title": "教授",
        "advisor_level": "博导/硕导",
        "research_areas": ["智能制造", "机器人学"],
        "match_status": "merged",
        "enrollment": {
          "in_roster": true,
          "planned_count": 3,
          "directions": [{"code": "085501", "name": "机械工程"}]
        }
      }
    ],
    "total": 5234,
    "page": 1,
    "page_size": 20
  }
}
```

**页面元素**：

| 组件 | 功能 |
|------|------|
| 搜索框 | 按姓名/研究方向搜索 |
| 筛选栏 | 学校、学院、类别、职称、导师级别、匹配状态 |
| 导师卡片/表格 | 姓名、学校、学院、职称、导师级别、研究方向、匹配状态标签 |
| 详情弹窗 | 点击卡片展开：完整信息 + 招生详情 + 原件链接 |
| 导出按钮 | 下载 Excel/JSON（GET /api/tutors/export） |

### 3.4 失败记录页（`failures.html`）

**数据源**：`GET /api/failures?status=&source=&page=1&page_size=20`

**页面元素**：

| 组件 | 功能 |
|------|------|
| 筛选栏 | 状态（pending/ignored/retrying）、来源（source_a/source_b） |
| 失败列表 | URL、错误信息、发生时间、来源、操作 |
| 操作按钮 | "重试"（POST /api/failures/retry）、"忽略"（POST /api/failures/{id}/ignore） |
| 批量操作 | 全选 + 批量重试 |

### 3.5 配置管理页（`config.html`）

**数据源**：`GET /api/config`、`PUT /api/config/schools/{name}`

**页面元素**：

| 组件 | 功能 |
|------|------|
| 左侧学校树 | 按学校名折叠展开，显示每个学院配置 |
| 右侧配置表单 | 学校名、学院、类别、list_url、list_type、选择器、notice 配置 |
| 测试连接按钮 | POST /api/config/test，显示响应状态码和耗时 |
| 保存按钮 | PUT /api/config/schools/{name}，保存后 Toast 提示 |
| 导入/导出按钮 | POST /api/config/import、GET /api/config/export |

---

## 4. 公共组件（`dashboard/components/`）

### 4.1 Toast 提示（`components/toast.js`）

```javascript
// 文件：dashboard/components/toast.js

function showToast(message, type = "info", duration = 3000) {
    /**
     * 全局 Toast 提示
     * @param {string} message - 提示内容
     * @param {string} type - "success" | "error" | "warning" | "info"
     * @param {number} duration - 显示时长（ms）
     */
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add("show"), 10);
    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// 全局错误拦截
window.addEventListener("unhandledrejection", (event) => {
    const err = event.reason;
    if (err?.code) {
        showToast(err.message, "error");
    }
});
```

### 4.2 分页组件（`components/pagination.js`）

```javascript
// 文件：dashboard/components/pagination.js

function renderPagination(container, currentPage, totalPages, onPageChange) {
    /**
     * 渲染分页组件
     * @param {HTMLElement} container - 容器元素
     * @param {number} currentPage - 当前页（1-based）
     * @param {number} totalPages - 总页数
     * @param {function} onPageChange - 翻页回调 (page: number) => void
     */
    container.innerHTML = "";
    
    // 上一页
    const prevBtn = document.createElement("button");
    prevBtn.textContent = "上一页";
    prevBtn.disabled = currentPage <= 1;
    prevBtn.onclick = () => onPageChange(currentPage - 1);
    container.appendChild(prevBtn);
    
    // 页码（显示当前页前后各2页）
    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);
    for (let p = start; p <= end; p++) {
        const btn = document.createElement("button");
        btn.textContent = p;
        btn.className = p === currentPage ? "active" : "";
        btn.onclick = () => onPageChange(p);
        container.appendChild(btn);
    }
    
    // 下一页
    const nextBtn = document.createElement("button");
    nextBtn.textContent = "下一页";
    nextBtn.disabled = currentPage >= totalPages;
    nextBtn.onclick = () => onPageChange(currentPage + 1);
    container.appendChild(nextBtn);
}
```

### 4.3 状态标签（`components/badge.js`）

```javascript
// 文件：dashboard/components/badge.js

const STATUS_MAP = {
    "merged":        { text: "已匹配", color: "#10b981" },
    "partial_faculty": { text: "仅官网", color: "#f59e0b" },
    "partial_notice":  { text: "仅公示", color: "#3b82f6" },
    "done":          { text: "已完成", color: "#10b981" },
    "running":       { text: "采集中", color: "#3b82f6" },
    "failed":        { text: "失败", color: "#ef4444" },
    "idle":          { text: "待采集", color: "#6b7280" },
    "pending":       { text: "待重试", color: "#f59e0b" },
    "ignored":       { text: "已忽略", color: "#6b7280" },
};

function renderBadge(status) {
    /** 返回状态标签 HTML 字符串 */
    const info = STATUS_MAP[status] || { text: status, color: "#6b7280" };
    return `<span class="badge" style="background:${info.color}">${info.text}</span>`;
}
```

---

## 5. 样式规范（`dashboard/style.css` 统一）

```css
/* 文件：dashboard/style.css */

:root {
    --primary: #3b82f6;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --bg: #f8fafc;
    --text: #1e293b;
    --text-secondary: #64748b;
    --border: #e2e8f0;
    --radius: 8px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); }

.card { background: white; border-radius: var(--radius); padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.btn { padding: 8px 16px; border-radius: var(--radius); border: none; cursor: pointer; font-size: 14px; }
.btn-primary { background: var(--primary); color: white; }
.btn-success { background: var(--success); color: white; }
.btn-danger { background: var(--danger); color: white; }
.badge { padding: 2px 8px; border-radius: 12px; color: white; font-size: 12px; }
.toast { position: fixed; top: 20px; right: 20px; padding: 12px 20px; border-radius: var(--radius); color: white; transform: translateX(120%); transition: transform 0.3s; z-index: 9999; }
.toast.show { transform: translateX(0); }
.toast-success { background: var(--success); }
.toast-error { background: var(--danger); }
.toast-warning { background: var(--warning); }
.toast-info { background: var(--primary); }

table { width: 100%; border-collapse: collapse; }
th, td { padding: 12px; text-align: left; border-bottom: 1px solid var(--border); }
th { background: #f1f5f9; font-weight: 600; }
.filter-bar { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.filter-bar input, .filter-bar select { padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--radius); }
```

---

## 6. 采集任务交互流程

```
用户点击"采集"按钮
    ↓
打开参数弹窗（学校/类别/数据源/年份/是否强制重抓）
    ↓
POST /api/crawl {schools: [...], categories: [...], sources: ["source_a", "source_b"], year: 2026}
    ↓
返回 {task_id: "abc123"}
    ↓
前端轮询 GET /api/tasks/abc123（每 3 秒）
    ↓
响应 {status: "running", progress: {"completed": 5, "total": 10, "current_school": "东南大学"}}
    ↓
进度条实时更新
    ↓
响应 {status: "completed"} 或 {status: "failed", message: "..."}
    ↓
Toast 提示"采集完成"/"采集失败"
    ↓
自动刷新当前页面数据
```

---

## 7. 文件结构

```
dashboard/
├── index.html              # 总览页（改造）
├── schools.html            # 学校列表页（新建）
├── tutors.html             # 导师列表页（新建）
├── failures.html           # 失败记录页（新建）
├── config.html             # 配置管理页（新建）
├── api.js                  # API 封装（新建）
├── style.css               # 统一样式（新建/改造）
├── components/
│   ├── toast.js            # Toast 提示
│   ├── pagination.js       # 分页组件
│   └── badge.js            # 状态标签
└── assets/
    └── favicon.ico
```

---

## 8. 验收标准

| 检查项 | 通过标准 |
|--------|----------|
| API 调用 | 所有页面使用 `api.js` 封装，无直接 fetch 硬编码 URL |
| 错误处理 | 非 0 code 统一 Toast 提示，不阻断页面 |
| 总览页 | 统计卡片数据来自 `/api/overview`，图表用真实数据 |
| 学校列表 | 筛选 + 分页 + 采集按钮功能完整 |
| 导师列表 | 多维筛选 + 详情弹窗 + 导出按钮功能完整 |
| 失败记录 | 列表 + 重试/忽略功能完整 |
| 配置管理 | 左右布局 + 在线编辑 + 测试连接功能完整 |
| 响应式 | 页面宽度 ≥768px 正常显示，<768px 单列布局 |
| 无后端依赖 | 前端可独立启动（用 Mock 数据 fallback），后端未就绪时不崩溃 |

---

## 9. 交付清单

- [ ] `dashboard/api.js`：API 封装
- [ ] `dashboard/style.css`：统一样式
- [ ] `dashboard/components/`：toast.js、pagination.js、badge.js
- [ ] `dashboard/index.html`：总览页改造（真实 API）
- [ ] `dashboard/schools.html`：学校列表页
- [ ] `dashboard/tutors.html`：导师列表页
- [ ] `dashboard/failures.html`：失败记录页
- [ ] `dashboard/config.html`：配置管理页
- [ ] 各页面在后端未启动时显示友好错误提示而非白屏
