// Toast 提示组件 — 全页面共享
// 用法：<script src="components/toast.js"></script> 后直接调用 showToast(msg, type, ms)

function showToast(message, type = "info", duration = 3000) {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => toast.classList.add("show"), 10);
    setTimeout(() => {
        toast.classList.remove("show");
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// 全局错误拦截 — 业务错误（err.code）自动 Toast
window.addEventListener("unhandledrejection", (event) => {
    const err = event.reason;
    if (err && err.code) {
        showToast(err.message, "error");
    }
});
