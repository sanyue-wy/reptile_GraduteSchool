// Console API Utilities
// V3.0 控制台 API 辅助工具

(function(win) {
    'use strict';

    var API = '/api';

    // ============================================
    // Run State Polling Hook (useRunState)
    // ============================================

    var runStateCallbacks = [];  // 注册的回调函数列表
    var runStateIntervalId = null;
    var runStateResumeTime = null;
    var lastRunState = null;

    // 订阅 run_state 变化
    // callback: function(state: RunStateDTO) - 当有新数据时调用
    // 返回: unsubscribe function
    win.useRunState = function(callback) {
        runStateCallbacks.push(callback);
        return function() {  // 返回取消订阅函数
            runStateCallbacks = runStateCallbacks.filter(function(cb) { return cb !== callback; });
        };
    };

    // 开始轮询（可选 run_id，默认使用当前页面 active run）
    win.startRunStatePolling = function(run_id) {
        stopRunStatePolling();  // 先停止旧的

        run_id = run_id || getActiveRunId();
        if (!run_id) return;

        runStateResumeTime = new Date();

        function poll() {
            fetch(API + '/pipeline/runs/' + run_id, { credentials: 'same-origin' })
                .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
                .then(function(data) {
                    var state = data.data || data;
                    if (state && hasStateChanged(state)) {
                        lastRunState = state;
                        runStateCallbacks.forEach(function(cb) { try { cb(state); } catch(e) { console.error('callback error:', e); } });
                    }
                })
                .catch(function(e) { console.debug('run state poll error:', e); });
        }

        // 初始拉一次
        poll();

        // 确定轮询间隔：运行中 2 秒，未运行 10 秒
        function scheduleNext(isRunning) {
            var interval = isRunning ? 2000 : 10000;
            setTimeout(poll, interval);
        }

        // 可在回调中修改 scheduleNext
        runStateIntervalId = setInterval(function() {
            fetch(API + '/pipeline/runs/' + run_id, { credentials: 'same-origin' })
                .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
                .then(function(data) {
                    var state = data.data || data;
                    if (state && hasStateChanged(state)) {
                        lastRunState = state;
                        runStateCallbacks.forEach(function(cb) { try { cb(state); } catch(e) { console.error('callback error:', e); } });
                    }
                    scheduleNext(isInRunningState(state));
                })
                .catch(function(e) { console.debug('run state poll error:', e); scheduleNext(false); });
        }, 2000);  // 默认 2 秒，后续根据状态调整
    };

    // 停止轮询
    win.stopRunStatePolling = function() {
        if (runStateIntervalId) {
            clearInterval(runStateIntervalId);
            runStateIntervalId = null;
        }
    };

    // 检查状态是否有变化
    function hasStateChanged(newState) {
        if (!lastRunState) return true;
        return JSON.stringify(newState) !== JSON.stringify(lastRunState);
    }

    // 检查是否处于运行中状态
    function isInRunningState(state) {
        return state && (state.status === 'running' || state.stats?.running > 0);
    }

    // 获取当前活动的 run_id
    function getActiveRunId() {
        var match = window.location.search.match(/run_id=([^/&]+)/);
        return match ? match[1] : null;
    }

    // 隐藏/显示元素
    win.show = function(selector, show) {
        var el = document.querySelector(selector);
        if (el) el.style.display = show ? '' : 'none';
    };

    // 显示成功/错误消息（toast）
    var toastContainer = null;
    win.showToast = function(message, isError, duration) {
        duration = duration || 3000;
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;';
            document.body.appendChild(toastContainer);
        }
        var toast = document.createElement('div');
        toast.textContent = message;
        toast.style.cssText = 'padding:12px 16px;margin:8px 0;border-radius:6px;font-size:14px;z-index:10000;' +
            (isError ? 'background:#f8d7da;color:#721c24;' : 'background:#d4edda;color:#155724;');
        toastContainer.appendChild(toast);
        setTimeout(function() {
            toastContainer.removeChild(toast);
        }, duration);
    };

    // ============================================
    // 窗口可见性监听
    // ============================================

    document.addEventListener('visibilitychange', function() {
        if (document.hidden) {
            // 切换到后台，暂停轮询
            stopRunStatePolling();
        } else {
            // 切回前台，立即拉一次
            var activeRunId = getActiveRunId();
            if (activeRunId) {
                fetch(API + '/pipeline/runs/' + activeRunId, { credentials: 'same-origin' })
                    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
                    .then(function(data) {
                        var state = data.data || data;
                        if (state) {
                            runStateCallbacks.forEach(function(cb) { try { cb(state); } catch(e) {} });
                        }
                    })
                    .catch(function(e) { console.debug('visibility refresh error:', e); });
            }
        }
    });

    // ============================================
    // 工具函数
    // ============================================

    win.escapeHtml = function(str) {
        if (str === null || str === undefined) return '';
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    };

    win.formatDate = function(ts) {
        if (!ts) return 'Unknown';
        try { return new Date(ts).toLocaleString(); } catch { return ts; }
    };

})(window);