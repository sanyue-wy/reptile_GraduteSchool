// 状态标签组件 — 全页面共享
// 用法：<script src="components/badge.js"></script> 后调用 renderBadge(status)

const STATUS_MAP = {
    "merged":          { text: "已合并",        color: "#10b981", bg: "#dcfce7" },
    "partial_faculty": { text: "仅官网",        color: "#f59e0b", bg: "#fef3c7" },
    "partial_notice":  { text: "仅研招网",      color: "#3b82f6", bg: "#dbeafe" },
    "done":            { text: "已完成",         color: "#10b981", bg: "#dcfce7" },
    "running":         { text: "采集中",         color: "#3b82f6", bg: "#dbeafe" },
    "failed":          { text: "失败",           color: "#ef4444", bg: "#fee2e2" },
    "idle":            { text: "待采集",         color: "#6b7280", bg: "#f3f4f6" },
    "pending":         { text: "待重试",         color: "#f59e0b", bg: "#fef3c7" },
    "ignored":         { text: "已忽略",         color: "#6b7280", bg: "#f3f4f6" },
    "resolved":        { text: "已解决",         color: "#10b981", bg: "#dcfce7" },
};

function renderBadge(status) {
    /** 返回状态标签 HTML 字符串 */
    const info = STATUS_MAP[status] || { text: status || "未知", color: "#6b7280", bg: "#f3f4f6" };
    return `<span class="badge" style="background:${info.bg};color:${info.color}">${info.text}</span>`;
}

// 院校层次标签
const LEVEL_MAP = {
    "985":       { text: "985",     color: "#ef4444", bg: "#fee2e2" },
    "211":       { text: "211",     color: "#f59e0b", bg: "#fef3c7" },
    "双一流":     { text: "双一流",    color: "#3b82f6", bg: "#dbeafe" },
    "985/211":   { text: "985/211", color: "#ef4444", bg: "#fee2e2" },
};

function renderLevelBadge(level) {
    const info = LEVEL_MAP[level] || { text: level || "—", color: "#6b7280", bg: "#f3f4f6" };
    return `<span class="badge" style="background:${info.bg};color:${info.color}">${info.text}</span>`;
}

// 导师级别标签
const ADVISOR_LEVEL_BADGE = {
    "博导":  { color: "#7c3aed", bg: "#f3e8ff" },
    "硕导":  { color: "#059669", bg: "#dcfce7" },
};

function renderLevelLabel(level) {
    const info = ADVISOR_LEVEL_BADGE[level];
    if (info) {
        return `<span class="badge" style="background:${info.bg};color:${info.color}">${level}</span>`;
    }
    return level || "—";
}
