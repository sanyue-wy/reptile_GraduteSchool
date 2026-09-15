// 分页组件 — 全页面共享
// 用法：<script src="components/pagination.js"></script> 后调用 renderPagination(container, page, totalPages, cb)

function renderPagination(container, currentPage, totalPages, onPageChange) {
    /**
     * @param {HTMLElement} container  容器元素
     * @param {number} currentPage     当前页（1-based）
     * @param {number} totalPages      总页数
     * @param {function} onPageChange  翻页回调 (page: number) => void
     */
    container.innerHTML = "";

    const createBtn = (label, disabled, active, onClick) => {
        const btn = document.createElement("button");
        btn.textContent = label;
        btn.className = "page-btn" + (active ? " active" : "");
        btn.disabled = disabled;
        btn.onclick = onClick;
        return btn;
    };

    // 上一页
    container.appendChild(createBtn(
        "‹", currentPage <= 1, false,
        () => onPageChange(currentPage - 1)
    ));

    // 页码按钮（当前页前后各 2 页）
    const start = Math.max(1, currentPage - 2);
    const end = Math.min(totalPages, currentPage + 2);

    // 第一页 + 省略号（当 start > 2 时）
    if (start > 1) {
        container.appendChild(createBtn("1", false, false, () => onPageChange(1)));
        if (start > 2) {
            container.appendChild(createBtn("…", true, false, null));
        }
    }

    for (let p = start; p <= end; p++) {
        container.appendChild(createBtn(p, false, p === currentPage, () => onPageChange(p)));
    }

    // 最后一页 + 省略号（当 end < totalPages - 1 时）
    if (end < totalPages) {
        if (end < totalPages - 1) {
            container.appendChild(createBtn("…", true, false, null));
        }
        container.appendChild(createBtn(String(totalPages), false, false, () => onPageChange(totalPages)));
    }

    // 下一页
    container.appendChild(createBtn(
        "›", currentPage >= totalPages, false,
        () => onPageChange(currentPage + 1)
    ));
}
