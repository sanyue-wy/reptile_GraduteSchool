/**
 * Table Renderer v1.0.0
 * Plain HTML table implementation with sorting, pagination, and row selection.
 * No external dependencies (Chart.js NOT needed).
 *
 * Usage:
 *   const renderer = new TableRenderer(containerElement, componentDTO);
 *   renderer.render(data);
 */

(function (global) {
    'use strict';

    /**
     * Default column formatter functions
     */
    const FORMATTERS = {
        'date': (value) => {
            if (!value) return '';
            const d = new Date(value);
            return isNaN(d.getTime()) ? value : d.toLocaleDateString();
        },
        'datetime': (value) => {
            if (!value) return '';
            const d = new Date(value);
            return isNaN(d.getTime()) ? value : d.toLocaleString();
        },
        'number': (value) => {
            if (value === null || value === undefined) return '';
            const n = Number(value);
            return isNaN(n) ? value : n.toLocaleString();
        },
        'currency': (value) => {
            if (value === null || value === undefined) return '';
            const n = Number(value);
            return isNaN(n) ? value : '¥' + n.toLocaleString(undefined, { minimumFractionDigits: 2 });
        },
        'boolean': (value) => {
            if (value === true || value === 'true' || value === 1) return '是';
            if (value === false || value === 'false' || value === 0) return '否';
            return value;
        },
        'truncate': (value, maxLength = 50) => {
            if (!value) return '';
            const str = String(value);
            return str.length > maxLength ? str.slice(0, maxLength) + '…' : str;
        },
    };

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * TableRenderer class
     */
    class TableRenderer {
        /**
         * @param {HTMLElement} container - Container element to render table into
         * @param {Object} componentDTO - UIComponentDTO with payload configuration
         */
        constructor(container, componentDTO) {
            if (!(container instanceof HTMLElement)) {
                throw new Error('TableRenderer: container must be an HTMLElement');
            }
            this.container = container;
            this.componentDTO = componentDTO;
            this.payload = componentDTO.payload || {};
            this.columns = this.payload.columns || [];
            this.data = [];
            this.currentPage = 1;
            this.pageSize = this.payload.page_size || 50;
            this.sortColumn = null;
            this.sortDirection = 'asc';
            this.selectedRows = new Set();
            this.totalCount = 0;

            // Bind event handlers
            this._handleSort = this._handleSort.bind(this);
            this._handlePageChange = this._handlePageChange.bind(this);
            this._handlePageSizeChange = this._handlePageSizeChange.bind(this);
            this._handleRowClick = this._handleRowClick.bind(this);
            this._handleHeaderClick = this._handleHeaderClick.bind(this);

            this._init();
        }

        /**
         * Initialize the renderer DOM structure
         */
        _init() {
            this.container.innerHTML = '';
            this.container.classList.add('table-renderer');

            // Create wrapper for responsive scrolling
            this.wrapper = document.createElement('div');
            this.wrapper.className = 'table-wrapper';
            this.container.appendChild(this.wrapper);

            // Create table element
            this.table = document.createElement('table');
            this.table.className = 'data-table';
            if (this.payload.striped) this.table.classList.add('striped');
            if (this.payload.hoverable) this.table.classList.add('hoverable');
            if (this.payload.bordered) this.table.classList.add('bordered');
            this.wrapper.appendChild(this.table);

            // Create thead
            this.thead = document.createElement('thead');
            this.table.appendChild(this.thead);

            // Create tbody
            this.tbody = document.createElement('tbody');
            this.table.appendChild(this.tbody);

            // Create pagination controls if enabled
            if (this.payload.pagination) {
                this._createPaginationControls();
            }

            // Render header
            this._renderHeader();
        }

        /**
         * Create pagination controls
         */
        _createPaginationControls() {
            this.paginationContainer = document.createElement('div');
            this.paginationContainer.className = 'table-pagination';
            this.container.appendChild(this.paginationContainer);

            // Page size selector
            const pageSizeLabel = document.createElement('label');
            pageSizeLabel.className = 'page-size-selector';
            pageSizeLabel.innerHTML = `
                <span>每页:</span>
                <select class="page-size-select">
                    <option value="10">10</option>
                    <option value="25">25</option>
                    <option value="50" selected>50</option>
                    <option value="100">100</option>
                </select>
            `;
            this.pageSizeSelect = pageSizeLabel.querySelector('.page-size-select');
            this.pageSizeSelect.value = this.pageSize;
            this.pageSizeSelect.addEventListener('change', (e) => this._handlePageSizeChange(parseInt(e.target.value, 10)));
            this.paginationContainer.appendChild(pageSizeLabel);

            // Page navigation
            this.pageNav = document.createElement('div');
            this.pageNav.className = 'page-navigation';
            this.paginationContainer.appendChild(this.pageNav);

            // Page info
            this.pageInfo = document.createElement('div');
            this.pageInfo.className = 'page-info';
            this.paginationContainer.appendChild(this.pageInfo);
        }

        /**
         * Render table header
         */
        _renderHeader() {
            this.thead.innerHTML = '';
            const headerRow = document.createElement('tr');

            this.columns.forEach((col, index) => {
                const th = document.createElement('th');
                th.dataset.field = col.field;
                th.dataset.index = index;
                th.style.textAlign = col.align || 'left';
                if (col.width) {
                    th.style.width = typeof col.width === 'number' ? col.width + 'px' : col.width;
                }

                // Column label with sort indicator
                const labelSpan = document.createElement('span');
                labelSpan.className = 'column-label';
                labelSpan.textContent = col.label;
                th.appendChild(labelSpan);

                // Sort indicator
                if (this.payload.sortable && col.sortable !== false) {
                    const sortIcon = document.createElement('span');
                    sortIcon.className = 'sort-indicator';
                    sortIcon.innerHTML = ' ⇅';
                    th.appendChild(sortIcon);
                    th.classList.add('sortable');
                    th.addEventListener('click', this._handleHeaderClick);
                }

                headerRow.appendChild(th);
            });

            this.thead.appendChild(headerRow);
        }

        /**
         * Render table body with current data
         */
        _renderBody() {
            this.tbody.innerHTML = '';

            if (this.data.length === 0) {
                const emptyRow = document.createElement('tr');
                const emptyCell = document.createElement('td');
                emptyCell.colSpan = this.columns.length;
                emptyCell.className = 'empty-state';
                emptyCell.textContent = '暂无数据';
                emptyRow.appendChild(emptyCell);
                this.tbody.appendChild(emptyRow);
                return;
            }

            this.data.forEach((row, rowIndex) => {
                const tr = document.createElement('tr');
                tr.dataset.rowIndex = rowIndex;

                // Check if row is selected
                if (this.selectedRows.has(rowIndex)) {
                    tr.classList.add('selected');
                }

                // Row click handler
                tr.addEventListener('click', (e) => this._handleRowClick(e, row, rowIndex));

                this.columns.forEach((col) => {
                    const td = document.createElement('td');
                    td.style.textAlign = col.align || 'left';

                    let value = row[col.field];

                    // Apply formatter if specified
                    if (col.formatter && FORMATTERS[col.formatter]) {
                        value = FORMATTERS[col.formatter](value);
                    } else if (col.type && FORMATTERS[col.type]) {
                        value = FORMATTERS[col.type](value);
                    }

                    // Escape HTML for safety
                    td.innerHTML = escapeHtml(value !== null && value !== undefined ? value : '');

                    tr.appendChild(td);
                });

                this.tbody.appendChild(tr);
            });
        }

        /**
         * Render pagination controls
         */
        _renderPagination() {
            if (!this.payload.pagination || !this.paginationContainer) return;

            const totalPages = Math.ceil(this.totalCount / this.pageSize);
            const currentPage = Math.min(this.currentPage, totalPages) || 1;

            // Update page info
            const start = (currentPage - 1) * this.pageSize + 1;
            const end = Math.min(currentPage * this.pageSize, this.totalCount);
            this.pageInfo.textContent = `显示 ${start}-${end} 共 ${this.totalCount} 条`;

            // Render page navigation
            this.pageNav.innerHTML = '';

            if (totalPages <= 1) return;

            // Previous button
            const prevBtn = document.createElement('button');
            prevBtn.className = 'page-btn';
            prevBtn.textContent = '‹ 上一页';
            prevBtn.disabled = currentPage <= 1;
            prevBtn.addEventListener('click', () => this._handlePageChange(currentPage - 1));
            this.pageNav.appendChild(prevBtn);

            // Page numbers
            const maxVisiblePages = 5;
            let startPage = Math.max(1, currentPage - Math.floor(maxVisiblePages / 2));
            let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);

            if (endPage - startPage + 1 < maxVisiblePages) {
                startPage = Math.max(1, endPage - maxVisiblePages + 1);
            }

            if (startPage > 1) {
                const firstBtn = document.createElement('button');
                firstBtn.className = 'page-btn';
                firstBtn.textContent = '1';
                firstBtn.addEventListener('click', () => this._handlePageChange(1));
                this.pageNav.appendChild(firstBtn);

                if (startPage > 2) {
                    const ellipsis = document.createElement('span');
                    ellipsis.className = 'page-ellipsis';
                    ellipsis.textContent = '…';
                    this.pageNav.appendChild(ellipsis);
                }
            }

            for (let i = startPage; i <= endPage; i++) {
                const pageBtn = document.createElement('button');
                pageBtn.className = 'page-btn' + (i === currentPage ? ' active' : '');
                pageBtn.textContent = i;
                pageBtn.addEventListener('click', () => this._handlePageChange(i));
                this.pageNav.appendChild(pageBtn);
            }

            if (endPage < totalPages) {
                if (endPage < totalPages - 1) {
                    const ellipsis = document.createElement('span');
                    ellipsis.className = 'page-ellipsis';
                    ellipsis.textContent = '…';
                    this.pageNav.appendChild(ellipsis);
                }

                const lastBtn = document.createElement('button');
                lastBtn.className = 'page-btn';
                lastBtn.textContent = totalPages;
                lastBtn.addEventListener('click', () => this._handlePageChange(totalPages));
                this.pageNav.appendChild(lastBtn);
            }

            // Next button
            const nextBtn = document.createElement('button');
            nextBtn.className = 'page-btn';
            nextBtn.textContent = '下一页 ›';
            nextBtn.disabled = currentPage >= totalPages;
            nextBtn.addEventListener('click', () => this._handlePageChange(currentPage + 1));
            this.pageNav.appendChild(nextBtn);
        }

        /**
         * Handle column header click for sorting
         */
        _handleHeaderClick(e) {
            if (!this.payload.sortable) return;

            const th = e.currentTarget;
            const field = th.dataset.field;
            const column = this.columns.find(c => c.field === field);
            if (!column || column.sortable === false) return;

            // Toggle sort direction
            if (this.sortColumn === field) {
                this.sortDirection = this.sortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                this.sortColumn = field;
                this.sortDirection = 'asc';
            }

            // Update sort indicators
            this.thead.querySelectorAll('th.sortable').forEach(h => {
                h.classList.remove('sort-asc', 'sort-desc');
                const indicator = h.querySelector('.sort-indicator');
                if (indicator) indicator.innerHTML = ' ⇅';
            });
            th.classList.add(this.sortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
            const indicator = th.querySelector('.sort-indicator');
            if (indicator) indicator.innerHTML = this.sortDirection === 'asc' ? ' ↑' : ' ↓';

            // Sort data locally if small dataset, otherwise emit event for server-side sort
            if (this.data.length <= this.pageSize && this.totalCount <= this.pageSize) {
                this._sortData();
                this._renderBody();
            } else {
                this._emitEvent('sort', { column: field, direction: this.sortDirection });
            }
        }

        /**
         * Sort data array in place
         */
        _sortData() {
            const col = this.columns.find(c => c.field === this.sortColumn);
            const type = col?.type || 'string';

            this.data.sort((a, b) => {
                let valA = a[this.sortColumn];
                let valB = b[this.sortColumn];

                // Handle null/undefined
                if (valA === null || valA === undefined) return this.sortDirection === 'asc' ? 1 : -1;
                if (valB === null || valB === undefined) return this.sortDirection === 'asc' ? -1 : 1;

                let comparison = 0;
                if (type === 'number' || type === 'integer') {
                    comparison = Number(valA) - Number(valB);
                } else if (type === 'date' || type === 'datetime') {
                    comparison = new Date(valA).getTime() - new Date(valB).getTime();
                } else if (type === 'boolean') {
                    comparison = String(valA).localeCompare(String(valB));
                } else {
                    comparison = String(valA).localeCompare(String(valB), undefined, { numeric: true });
                }

                return this.sortDirection === 'asc' ? comparison : -comparison;
            });
        }

        /**
         * Handle page change
         */
        _handlePageChange(page) {
            if (page < 1) return;
            const totalPages = Math.ceil(this.totalCount / this.pageSize);
            if (page > totalPages) return;

            this.currentPage = page;
            this._emitEvent('page_change', { page });
        }

        /**
         * Handle page size change
         */
        _handlePageSizeChange(pageSize) {
            this.pageSize = pageSize;
            this.currentPage = 1;
            this._emitEvent('page_size_change', { page_size: pageSize });
        }

        /**
         * Handle row click
         */
        _handleRowClick(e, rowData, rowIndex) {
            // Don't select if clicking on interactive elements
            if (e.target.tagName === 'BUTTON' || e.target.tagName === 'A' || e.target.tagName === 'INPUT') {
                return;
            }

            // Toggle selection
            if (this.selectedRows.has(rowIndex)) {
                this.selectedRows.delete(rowIndex);
            } else {
                // Single selection by default (can be changed to multi-select)
                this.selectedRows.clear();
                this.selectedRows.add(rowIndex);
            }

            // Update visual selection
            this.tbody.querySelectorAll('tr').forEach((tr, idx) => {
                tr.classList.toggle('selected', this.selectedRows.has(idx));
            });

            this._emitEvent('row_click', {
                row_index: rowIndex,
                row_data: rowData,
                selected: this.selectedRows.has(rowIndex),
            });
        }

        /**
         * Emit event to registered handlers
         */
        _emitEvent(eventName, params) {
            const events = this.componentDTO.events || [];
            const handler = events.find(e => e.event === eventName);
            if (handler && typeof global[handler.action] === 'function') {
                try {
                    global[handler.action](...(handler.params.map(p => params[p]) || []));
                } catch (err) {
                    console.error(`TableRenderer: Error in event handler ${handler.action}:`, err);
                }
            }

            // Also emit as CustomEvent for external listeners
            this.container.dispatchEvent(new CustomEvent(`table:${eventName}`, {
                detail: { componentId: this.componentDTO.component_id, ...params },
                bubbles: true,
            }));
        }

        /**
         * Render data into the table
         * @param {Array} data - Array of row objects
         * @param {number} totalCount - Total record count (for pagination)
         */
        render(data, totalCount) {
            this.data = Array.isArray(data) ? data : [];
            this.totalCount = typeof totalCount === 'number' ? totalCount : this.data.length;

            // Reset to first page on new data
            this.currentPage = 1;

            // Apply local sort if active
            if (this.sortColumn) {
                this._sortData();
            }

            this._renderBody();
            this._renderPagination();
        }

        /**
         * Append data (for infinite scroll or incremental loading)
         */
        appendData(data, totalCount) {
            const newData = Array.isArray(data) ? data : [];
            this.data = this.data.concat(newData);
            this.totalCount = typeof totalCount === 'number' ? totalCount : this.data.length;
            this._renderBody();
            this._renderPagination();
        }

        /**
         * Update a single row
         */
        updateRow(rowIndex, rowData) {
            if (rowIndex >= 0 && rowIndex < this.data.length) {
                this.data[rowIndex] = { ...this.data[rowIndex], ...rowData };
                const tr = this.tbody.querySelector(`tr[data-row-index="${rowIndex}"]`);
                if (tr) {
                    this.columns.forEach((col) => {
                        const td = tr.querySelector(`td:nth-child(${this.columns.indexOf(col) + 1})`);
                        if (td) {
                            let value = this.data[rowIndex][col.field];
                            if (col.formatter && FORMATTERS[col.formatter]) {
                                value = FORMATTERS[col.formatter](value);
                            } else if (col.type && FORMATTERS[col.type]) {
                                value = FORMATTERS[col.type](value);
                            }
                            td.innerHTML = escapeHtml(value !== null && value !== undefined ? value : '');
                        }
                    });
                }
            }
        }

        /**
         * Get selected row data
         */
        getSelectedRows() {
            return Array.from(this.selectedRows).map(idx => ({
                index: idx,
                data: this.data[idx],
            }));
        }

        /**
         * Clear selection
         */
        clearSelection() {
            this.selectedRows.clear();
            this.tbody.querySelectorAll('tr.selected').forEach(tr => tr.classList.remove('selected'));
        }

        /**
         * Destroy renderer and clean up
         */
        destroy() {
            this.container.innerHTML = '';
            this.container.classList.remove('table-renderer');
            this.data = [];
            this.selectedRows.clear();
        }
    }

    // Export for module systems
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { TableRenderer, FORMATTERS };
    } else {
        global.TableRenderer = TableRenderer;
        global.TableFormatters = FORMATTERS;
    }

})(typeof window !== 'undefined' ? window : global);