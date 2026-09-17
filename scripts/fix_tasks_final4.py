import re

with open('dashboard/tasks.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the SSE logging section
old_sse = '''// ===== 实时日志流 (SSE) =====
let logSSE = null;
let logAutoScroll = true;

function setupLogStream(taskId) {
  if (logSSE) {
    logSSE.close();
  }

  const url = taskId === "all"
    ? `${API_BASE}/api/logs/stream`
    : `${API_BASE}/api/logs/stream?task_id=${encodeURIComponent(taskId)}`;

  logSSE = new EventSource(url);

  const statusEl = document.getElementById("log-stream-status");
  const logContainer = document.getElementById("logStream");

  logSSE.onopen = () => {
    statusEl.textContent = "🟢 已连接";
    statusEl.style.color = "var(--success)";
  };

  logSSE.onmessage = (event) => {
    try {
      const log = JSON.parse(event.data);
      appendLog(log);
    } catch (e) {
      // 可能是心跳或非JSON
      appendRawLog(event.data);
    }
  };

  logSSE.onerror = () => {
    statusEl.textContent = "🔴 连接断开，5秒后重连...";
    statusEl.style.color = "var(--danger)";
    setTimeout(() => setupLogStream(document.getElementById("log-filter-task").value), 5000);
  };
}

function toggleLogStream() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logSSE) {
    logSSE.close();
    logSSE = null;
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    setupLogStream(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function connectLogStream(taskId) {
  setupLogStream(taskId);
  document.querySelector('#log-stream-status').textContent = "🟢 已连接";
  document.querySelector('button[onclick="toggleLogStream()"]').textContent = "⏸ 暂停";
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

new_polling = '''// ===== 实时日志轮询 =====
let logPollTimer = null;
let logAutoScroll = true;
let lastLogTimestamp = 0;

async function fetchLogs(taskId) {
  try {
    const data = await apiCall(`/api/logs?task_id=${encodeURIComponent(taskId)}&since=${lastLogTimestamp}`);
    return data.logs || [];
  } catch (err) {
    console.error("获取日志失败:", err);
    return [];
  }
}

function startLogPolling(taskId) {
  if (logPollTimer) {
    clearInterval(logPollTimer);
  }

  lastLogTimestamp = 0;
  document.getElementById("log-stream-status").textContent = "🟢 轮询中...";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "⏸ 暂停";

  async function poll() {
    try {
      const logs = await fetchLogs(taskId);
      if (logs.length > 0) {
        logs.forEach(log => appendLog(log));
        lastLogTimestamp = logs[logs.length - 1].timestamp || Date.now();
      }
    } catch (err) {
      console.error("轮询日志失败:", err);
    }
  }

  // 立即执行一次
  await poll();
  // 设置定时器，每3秒轮询一次
  logPollTimer = setInterval(poll, 3000);
}

function stopLogPolling() {
  if (logPollTimer) {
    clearInterval(logPollTimer);
    logPollTimer = null;
  }
  document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "▶ 继续";
}

function toggleLogPolling() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logPollTimer) {
    stopLogPolling();
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    startLogPolling(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

with open('dashboard/tasks.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '''// ===== 实时日志流 (SSE) =====
let logSSE = null;
let logAutoScroll = true;

function setupLogStream(taskId) {
  if (logSSE) {
    logSSE.close();
  }

  const url = taskId === "all"
    ? `${API_BASE}/api/logs/stream`
    : `${API_BASE}/api/logs/stream?task_id=${encodeURIComponent(taskId)}`;

  logSSE = new EventSource(url);

  const statusEl = document.getElementById("log-stream-status");
  const logContainer = document.getElementById("logStream");

  logSSE.onopen = () => {
    statusEl.textContent = "🟢 已连接";
    statusEl.style.color = "var(--success)";
  };

  logSSE.onmessage = (event) => {
    try {
      const log = JSON.parse(event.data);
      appendLog(log);
    } catch (e) {
      // 可能是心跳或非JSON
      appendRawLog(event.data);
    }
  };

  logSSE.onerror = () => {
    statusEl.textContent = "🔴 连接断开，5秒后重连...";
    statusEl.style.color = "var(--danger)";
    setTimeout(() => setupLogStream(document.getElementById("log-filter-task").value), 5000);
  };
}

function toggleLogStream() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logSSE) {
    logSSE.close();
    logSSE = null;
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    setupLogStream(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function connectLogStream(taskId) {
  setupLogStream(taskId);
  document.querySelector('#log-stream-status').textContent = "🟢 已连接";
  document.querySelector('button[onclick="toggleLogStream()"]').textContent = "⏸ 暂停";
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}''', '''// ===== 实时日志轮询 =====
let logPollTimer = null;
let logAutoScroll = true;
let lastLogTimestamp = 0;

async function fetchLogs(taskId) {
  try {
    const data = await apiCall(`/api/logs?task_id=${encodeURIComponent(taskId)}&since=${lastLogTimestamp}`);
    return data.logs || [];
  } catch (err) {
    console.error("获取日志失败:", err);
    return [];
  }
}

function startLogPolling(taskId) {
  if (logPollTimer) {
    clearInterval(logPollTimer);
  }

  lastLogTimestamp = 0;
  document.getElementById("log-stream-status").textContent = "🟢 轮询中...";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "⏸ 暂停";

  async function poll() {
    try {
      const logs = await fetchLogs(taskId);
      if (logs.length > 0) {
        logs.forEach(log => appendLog(log));
        lastLogTimestamp = logs[logs.length - 1].timestamp || Date.now();
      }
    } catch (err) {
      console.error("轮询日志失败:", err);
    }
  }

  // 立即执行一次
  await poll();
  // 设置定时器，每3秒轮询一次
  logPollTimer = setInterval(poll, 3000);
}

function stopLogPolling() {
  if (logPollTimer) {
    clearInterval(logPollTimer);
    logPollTimer = null;
  }
  document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "▶ 继续";
}

function toggleLogPolling() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logPollTimer) {
    stopLogPolling();
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    startLogPolling(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}''', content)

# Also replace toggleLogStream and related functions
old_toggle = '''function toggleLogStream() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logSSE) {
    logSSE.close();
    logSSE = null;
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    setupLogStream(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function connectLogStream(taskId) {
  setupLogStream(taskId);
  document.querySelector('#log-stream-status').textContent = "🟢 已连接";
  document.querySelector('button[onclick="toggleLogStream()"]').textContent = "⏸ 暂停";
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

new_toggle = '''function toggleLogPolling() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logPollTimer) {
    stopLogPolling();
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    startLogPolling(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

with open('dashboard/tasks.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '''// ===== 实时日志流 (SSE) =====
let logSSE = null;
let logAutoScroll = true;

function setupLogStream(taskId) {
  if (logSSE) {
    logSSE.close();
  }

  const url = taskId === "all"
    ? `${API_BASE}/api/logs/stream`
    : `${API_BASE}/api/logs/stream?task_id=${encodeURIComponent(taskId)}`;

  logSSE = new EventSource(url);

  const statusEl = document.getElementById("log-stream-status");
  const logContainer = document.getElementById("logStream");

  logSSE.onopen = () => {
    statusEl.textContent = "🟢 已连接";
    statusEl.style.color = "var(--success)";
  };

  logSSE.onmessage = (event) => {
    try {
      const log = JSON.parse(event.data);
      appendLog(log);
    } catch (e) {
      // 可能是心跳或非JSON
      appendRawLog(event.data);
    }
  };

  logSSE.onerror = () => {
    statusEl.textContent = "🔴 连接断开，5秒后重连...";
    statusEl.style.color = "var(--danger)";
    setTimeout(() => setupLogStream(document.getElementById("log-filter-task").value), 5000);
  };
}

function toggleLogStream() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logSSE) {
    logSSE.close();
    logSSE = null;
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    setupLogStream(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function connectLogStream(taskId) {
  setupLogStream(taskId);
  document.querySelector('#log-stream-status').textContent = "🟢 已连接";
  document.querySelector('button[onclick="toggleLogStream()"]').textContent = "⏸ 暂停";
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}''', '''// ===== 实时日志轮询 =====
let logPollTimer = null;
let logAutoScroll = true;
let lastLogTimestamp = 0;

async function fetchLogs(taskId) {
  try {
    const data = await apiCall(`/api/logs?task_id=${encodeURIComponent(taskId)}&since=${lastLogTimestamp}`);
    return data.logs || [];
  } catch (err) {
    console.error("获取日志失败:", err);
    return [];
  }
}

function startLogPolling(taskId) {
  if (logPollTimer) {
    clearInterval(logPollTimer);
  }

  lastLogTimestamp = 0;
  document.getElementById("log-stream-status").textContent = "🟢 轮询中...";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "⏸ 暂停";

  async function poll() {
    try {
      const logs = await fetchLogs(taskId);
      if (logs.length > 0) {
        logs.forEach(log => appendLog(log));
        lastLogTimestamp = logs[logs.length - 1].timestamp || Date.now();
      }
    } catch (err) {
      console.error("轮询日志失败:", err);
    }
  }

  // 立即执行一次
  await poll();
  // 设置定时器，每3秒轮询一次
  logPollTimer = setInterval(poll, 3000);
}

function stopLogPolling() {
  if (logPollTimer) {
    clearInterval(logPollTimer);
    logPollTimer = null;
  }
  document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "▶ 继续";
}

function toggleLogPolling() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logPollTimer) {
    stopLogPolling();
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    startLogPolling(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}''', content)

# Also replace toggleLogStream and related functions
old_toggle = '''function toggleLogStream() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logSSE) {
    logSSE.close();
    logSSE = null;
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    setupLogStream(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function connectLogStream(taskId) {
  setupLogStream(taskId);
  document.querySelector('#log-stream-status').textContent = "🟢 已连接";
  document.querySelector('button[onclick="toggleLogStream()"]').textContent = "⏸ 暂停";
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

new_toggle = '''function toggleLogPolling() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logPollTimer) {
    stopLogPolling();
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    startLogPolling(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

with open('dashboard/tasks.html', 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace(
    '''// ===== 实时日志流 (SSE) =====
let logSSE = null;
let logAutoScroll = true;

function setupLogStream(taskId) {
  if (logSSE) {
    logSSE.close();
  }

  const url = taskId === "all"
    ? `${API_BASE}/api/logs/stream`
    : `${API_BASE}/api/logs/stream?task_id=${encodeURIComponent(taskId)}`;

  logSSE = new EventSource(url);

  const statusEl = document.getElementById("log-stream-status");
  const logContainer = document.getElementById("logStream");

  logSSE.onopen = () => {
    statusEl.textContent = "🟢 已连接";
    statusEl.style.color = "var(--success)";
  };

  logSSE.onmessage = (event) => {
    try {
      const log = JSON.parse(event.data);
      appendLog(log);
    } catch (e) {
      // 可能是心跳或非JSON
      appendRawLog(event.data);
    }
  };

  logSSE.onerror = () => {
    statusEl.textContent = "🔴 连接断开，5秒后重连...";
    statusEl.style.color = "var(--danger)";
    setTimeout(() => setupLogStream(document.getElementById("log-filter-task").value), 5000);
  };
}

function toggleLogStream() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logSSE) {
    logSSE.close();
    logSSE = null;
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    setupLogStream(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function connectLogStream(taskId) {
  setupLogStream(taskId);
  document.querySelector('#log-stream-status').textContent = "🟢 已连接";
  document.querySelector('button[onclick="toggleLogStream()"]').textContent = "⏸ 暂停";
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}''', '''// ===== 实时日志轮询 =====
let logPollTimer = null;
let logAutoScroll = true;
let lastLogTimestamp = 0;

async function fetchLogs(taskId) {
  try {
    const data = await apiCall(`/api/logs?task_id=${encodeURIComponent(taskId)}&since=${lastLogTimestamp}`);
    return data.logs || [];
  } catch (err) {
    console.error("获取日志失败:", err);
    return [];
  }
}

function startLogPolling(taskId) {
  if (logPollTimer) {
    clearInterval(logPollTimer);
  }

  lastLogTimestamp = 0;
  document.getElementById("log-stream-status").textContent = "🟢 轮询中...";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "⏸ 暂停";

  async function poll() {
    try {
      const logs = await fetchLogs(taskId);
      if (logs.length > 0) {
        logs.forEach(log => appendLog(log));
        lastLogTimestamp = logs[logs.length - 1].timestamp || Date.now();
      }
    } catch (err) {
      console.error("轮询日志失败:", err);
    }
  }

  // 立即执行一次
  await poll();
  // 设置定时器，每3秒轮询一次
  logPollTimer = setInterval(poll, 3000);
}

function stopLogPolling() {
  if (logPollTimer) {
    clearInterval(logPollTimer);
    logPollTimer = null;
  }
  document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  document.querySelector('button[onclick="toggleLogPolling()"]').textContent = "▶ 继续";
}

function toggleLogPolling() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logPollTimer) {
    stopLogPolling();
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    startLogPolling(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}''', content)

# Also replace toggleLogStream and related functions
old_toggle = '''function toggleLogStream() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logSSE) {
    logSSE.close();
    logSSE = null;
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    setupLogStream(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function connectLogStream(taskId) {
  setupLogStream(taskId);
  document.querySelector('#log-stream-status').textContent = "🟢 已连接";
  document.querySelector('button[onclick="toggleLogStream()"]').textContent = "⏸ 暂停";
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

new_toggle = '''function toggleLogPolling() {
  const btn = event.target;
  const taskId = document.getElementById("log-filter-task").value;

  if (logPollTimer) {
    stopLogPolling();
    btn.textContent = "▶ 继续";
    btn.classList.add("btn-warning");
    document.getElementById("log-stream-status").textContent = "⏸ 已暂停";
  } else {
    startLogPolling(document.getElementById("log-filter-task").value);
    btn.textContent = "⏸ 暂停";
    btn.classList.remove("btn-warning");
  }
}

function clearLogStream() {
  document.getElementById("logStream").innerHTML = "";
}'''

content = content.replace(old_toggle, new_toggle)

# Update the initialization
old_init = '''document.addEventListener("DOMContentLoaded", async () => {
  await checkBackend();
  populateSchools();
  loadTasks();
  setupLogStream("all");'''

new_init = '''document.addEventListener("DOMContentLoaded", async () => {
  await checkBackend();
  populateSchools();
  loadTasks();
  startLogPolling("all");'''

content = content.replace(old_init, new_init)

# Update viewTaskLogs function
old_view = '''function viewTaskLogs(taskId) {
  document.getElementById("log-filter-task").value = taskId;
  setupLogStream(taskId);
  document.getElementById("log-stream-status").textContent = "🟢 已连接";'''

new_view = '''function viewTaskLogs(taskId) {
  document.getElementById("log-filter-task").value = taskId;
  startLogPolling(taskId);
  document.getElementById("log-stream-status").textContent = "🟢 已连接";'''

content = content.replace(old_view, new_view)

# Also update the onclick handler
content = content.replace('onclick="toggleLogStream()"', 'onclick="toggleLogPolling()"')

with open('dashboard/tasks.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done')