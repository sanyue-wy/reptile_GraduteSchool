// dashboard/api.js — 统一 API 封装
// 所有页面通过 <script src="api.js"></script> + <script src="components/toast.js"></script> 加载
// 在后端未启动时自动回退到 Mock 数据，确保页面不崩溃

const API_BASE = window.location.origin;
const USE_MOCK_FALLBACK = true;

// ------------------------------------------------------------------
// Mock 数据 — 与 /api/server.py 响应结构保持一致
// ------------------------------------------------------------------
const MOCK = {
    overview: {
        stats: { total_schools: 147, done: 38, running: 6, failed: 3, partial: 12, pending: 88 },
        progress: {
            source_a: { completed: 44, total: 147 },
            source_b: { completed: 100, total: 147 },
            merged:   { completed: 38, total: 147 },
        },
        source_breakdown: { matched: 6200, notice_only: 1800, faculty_only: 950, unmatched: 340 },
        recent_tutors: [
            { name: "张三", title: "教授", level: "博导", school: "东南大学", college: "机械工程学院", areas: ["智能制造", "机器人学"] },
            { name: "李四", title: "副教授", level: "硕导", school: "东南大学", college: "机械工程学院", areas: ["精密加工", "表面工程"] },
            { name: "王五", title: "教授", level: "博导", school: "东南大学", college: "自动化学院", areas: ["控制理论与控制工程"] },
            { name: "钱七", title: "副教授", level: "硕导", school: "东南大学", college: "机械工程学院", areas: ["车辆工程", "新能源汽车"] },
            { name: "孙八", title: "教授",   level: "博导",   school: "清华大学", college: "机械工程系", areas: ["微纳制造", "增材制造"] },
        ],
        recent_failures: [
            { school: "北京航空航天大学", college: "机械工程及自动化学院", source: "Source A", error: "HTTP 403 Forbidden", time: "2026-09-14T14:23:05" },
            { school: "同济大学", college: "自动化学院", source: "Source A", error: "连接超时 (30s)", time: "2026-09-14T14:20:18" },
            { school: "东南大学", college: "研究生院", source: "Source B", error: "域名不可达", time: "2026-09-14T13:45:33" },
        ],
        logs: [
            { time: "2026-09-14 16:02:31", level: "INFO",  msg: "东南大学/机械工程学院 Source A 完成，获取 196 条导师记录" },
            { time: "2026-09-14 16:02:28", level: "INFO",  msg: "东南大学/机械工程学院 详情页解析：196/196 成功" },
            { time: "2026-09-14 16:01:55", level: "WARN",  msg: "东南大学/机械工程学院 详情页 陶毅 字段大量为空，已标记 partial" },
            { time: "2026-09-14 16:01:12", level: "INFO",  msg: "东南大学/自动化学院 API 请求成功，返回 115 条记录" },
            { time: "2026-09-14 16:00:45", level: "INFO",  msg: "清华大学/机械工程学院 Source A 完成，获取 89 条导师记录" },
            { time: "2026-09-14 16:00:22", level: "ERROR", msg: "北京航空航天大学/机械工程及自动化学院 列表页返回 HTTP 403" },
            { time: "2026-09-14 15:59:58", level: "INFO",  msg: "浙江大学/自动化学院 详情页解析：78/82 成功，4 条字段缺失" },
            { time: "2026-09-14 15:59:30", level: "WARN",  msg: "同济大学/自动化学院 连接超时，已记入 failures.json" },
            { time: "2026-09-14 15:58:44", level: "INFO",  msg: "华中科技大学/机械工程学院 Source B 研招网数据匹配：merged 142 / partial 23" },
            { time: "2026-09-14 15:58:22", level: "INFO",  msg: "西安交通大学 配置已加载，等待调度..." },
        ],
    },

    schools: () => ({
        total: 20,
        page: 1,
        page_size: 20,
        items: [
            { id: 1, name: "东南大学", level: "985", mech_college: "机械工程学院", auto_college: "自动化学院", source_a_status: "done", source_b_status: "done", tutor_count: 311, match_rate: 95, status: "done" },
            { id: 2, name: "清华大学", level: "985", mech_college: "机械工程系", auto_college: "自动化系", source_a_status: "done", source_b_status: "done", tutor_count: 186, match_rate: 92, status: "done" },
            { id: 3, name: "浙江大学", level: "985", mech_college: "机械工程学院", auto_college: "控制科学与工程学院", source_a_status: "done", source_b_status: "running", tutor_count: 142, match_rate: 88, status: "partial" },
            { id: 4, name: "上海交通大学", level: "985", mech_college: "机械与动力工程学院", auto_college: "自动化系", source_a_status: "done", source_b_status: "running", tutor_count: 135, match_rate: 85, status: "partial" },
            { id: 5, name: "哈尔滨工业大学", level: "985", mech_college: "机电工程学院", auto_college: "航天学院(控制)", source_a_status: "running", source_b_status: "pending", tutor_count: 0, match_rate: 0, status: "running" },
            { id: 6, name: "华中科技大学", level: "985", mech_college: "机械科学与工程学院", auto_college: "人工智能与自动化学院", source_a_status: "done", source_b_status: "done", tutor_count: 220, match_rate: 91, status: "done" },
            { id: 7, name: "西安交通大学", level: "985", mech_college: "机械工程学院", auto_college: "自动化科学与工程学院", source_a_status: "pending", source_b_status: "pending", tutor_count: 0, match_rate: 0, status: "pending" },
            { id: 8, name: "北京航空航天大学", level: "985", mech_college: "机械工程及自动化学院", auto_college: "自动化科学与电气工程学院", source_a_status: "failed", source_b_status: "pending", tutor_count: 0, match_rate: 0, status: "failed" },
            { id: 9, name: "天津大学", level: "985", mech_college: "机械工程学院", auto_college: "电气自动化与信息工程学院", source_a_status: "done", source_b_status: "done", tutor_count: 178, match_rate: 90, status: "done" },
            { id: 10, name: "大连理工大学", level: "985", mech_college: "机械工程学院", auto_college: "控制科学与工程学院", source_a_status: "running", source_b_status: "pending", tutor_count: 0, match_rate: 0, status: "running" },
            { id: 11, name: "同济大学", level: "985", mech_college: "机械与能源工程学院", auto_college: "电子与信息工程学院", source_a_status: "done", source_b_status: "failed", tutor_count: 95, match_rate: 72, status: "partial" },
            { id: 12, name: "中南大学", level: "985", mech_college: "机电工程学院", auto_college: "自动化学院", source_a_status: "pending", source_b_status: "pending", tutor_count: 0, match_rate: 0, status: "pending" },
        ],
        summary: { done: 4, partial: 3, running: 3, pending: 2, failed: 1 },
    }),

    tutors: {
        total: 15,
        page: 1,
        page_size: 20,
        items: [
            { name: "张三", school: "东南大学", college: "机械工程学院", title: "教授", level: "博导", email: "zhangsan@seu.edu.cn", profile_url: "https://me.seu.edu.cn/zhangsan", areas: ["智能制造", "机器人学", "数控技术"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["学术型硕士"], source_url: "https://yz.chsi.com.cn" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "李四", school: "东南大学", college: "机械工程学院", title: "副教授", level: "硕导", email: "lisi@seu.edu.cn", profile_url: "https://me.seu.edu.cn/lisi", areas: ["精密加工", "表面工程"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["学术型硕士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "王五", school: "东南大学", college: "自动化学院", title: "教授", level: "博导", email: "", profile_url: "https://automation.seu.edu.cn/wangwu", areas: ["控制理论与控制工程", "智能系统"], enrollment: null, match_status: "partial_faculty", source_type: { faculty: "官网师资页", notice: "" } },
            { name: "赵六", school: "东南大学", college: "自动化学院", title: "教授", level: "博导", email: "zhaoliu@seu.edu.cn", profile_url: "https://automation.seu.edu.cn/zhaoliu", areas: ["模式识别", "深度学习", "计算机视觉"], enrollment: null, match_status: "partial_faculty", source_type: { faculty: "官网师资页", notice: "" } },
            { name: "孙八", school: "清华大学", college: "机械工程系", title: "教授", level: "博导", email: "sunba@tsinghua.edu.cn", profile_url: "https://www.mee.tsinghua.edu.cn/sunba", areas: ["微纳制造", "增材制造"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["博士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "周九", school: "清华大学", college: "机械工程学院", title: "副教授", level: "博导", email: "", profile_url: "", areas: ["机器人学", "仿生学"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["学术型硕士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "吴十", school: "浙江大学", college: "机械工程学院", title: "教授", level: "博导", email: "wushi@zju.edu.cn", profile_url: "https://me.zju.edu.cn/wushi", areas: ["流体传动", "机电控制"], enrollment: null, match_status: "partial_faculty", source_type: { faculty: "官网师资页", notice: "" } },
            { name: "郑十一", school: "浙江大学", college: "控制科学与工程学院", title: "副教授", level: "硕导", email: "", profile_url: "", areas: ["过程控制", "工业互联网"], enrollment: { in_roster: true, directions: [{ code: "081100", name: "控制科学与工程" }], degree_types: ["学术型硕士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "陈十二", school: "华中科技大学", college: "机械科学与工程学院", title: "教授", level: "博导", email: "chen12@hust.edu.cn", profile_url: "https://mse.hust.edu.cn/chen12", areas: ["数字制造", "智能装备"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["学术型硕士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "林十三", school: "华中科技大学", college: "人工智能与自动化学院", title: "教授", level: "博导", email: "", profile_url: "", areas: ["强化学习", "多智能体系统"], enrollment: { in_roster: true, directions: [{ code: "081104", name: "模式识别与智能系统" }], degree_types: ["博士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "黄十四", school: "上海交通大学", college: "机械与动力工程学院", title: "教授", level: "博导", email: "huang14@sjtu.edu.cn", profile_url: "", areas: ["薄壁结构", "航天制造"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["学术型硕士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "刘十五", school: "北京理工大学", college: "机械与车辆学院", title: "教授", level: "博导", email: "", profile_url: "", areas: ["无人车辆", "智能交通"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["学术型硕士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
            { name: "杨十六", school: "天津大学", college: "机械工程学院", title: "副教授", level: "硕导", email: "yang16@tju.edu.cn", profile_url: "", areas: ["焊接技术", "增材制造"], enrollment: null, match_status: "partial_faculty", source_type: { faculty: "官网师资页", notice: "" } },
            { name: "徐十七", school: "东南大学", college: "自动化学院", title: "教授", level: "硕导", email: "", profile_url: "", areas: ["导航制导", "惯性技术"], enrollment: { in_roster: true, directions: [{ code: "081105", name: "导航、制导与控制" }], degree_types: ["学术型硕士"], source_url: "" }, match_status: "partial_notice", source_type: { faculty: "", notice: "研招网" } },
            { name: "梅十八", school: "同济大学", college: "机械与能源工程学院", title: "教授", level: "博导", email: "mei18@tongji.edu.cn", profile_url: "https://www.mee.tongji.edu.cn/mei18", areas: ["机床技术", "先进制造"], enrollment: { in_roster: true, directions: [{ code: "085501", name: "机械工程" }], degree_types: ["博士"], source_url: "" }, match_status: "merged", source_type: { faculty: "官网师资页", notice: "研招网" } },
        ],
    },

    failures: {
        total: 5,
        summary: { http_error: 2, timeout: 1, parse_error: 1, dns_error: 1 },
        items: [
            { id: "fail_001", school: "北京航空航天大学", college: "机械工程及自动化学院", source: "Source A", error_type: "http_403", error_message: "HTTP 403 Forbidden — 触发反爬冷却机制，域名 buaa.edu.cn 已暂停 30 分钟", url: "https://mea.buaa.edu.cn/szdw/list.htm", occurred_at: "2026-09-14T14:23:05", retry_count: 3, status: "active" },
            { id: "fail_002", school: "同济大学", college: "自动化学院", source: "Source A", error_type: "timeout", error_message: "requests.exceptions.ConnectTimeout: 连接超时 (timeout=30s) — tongji.edu.cn", url: "https://see.tongji.edu.cn/szdw/szml1.htm", occurred_at: "2026-09-14T14:20:18", retry_count: 3, status: "active" },
            { id: "fail_003", school: "东南大学", college: "研究生院", source: "Source B", error_type: "dns_error", error_message: "seugs.seu.edu.cn 当前网络不可达 — 待正常网络环境补验", url: "https://seugs.seu.edu.cn/", occurred_at: "2026-09-14T13:45:33", retry_count: 1, status: "active" },
            { id: "fail_004", school: "湖南大学", college: "机械与运载工程学院", source: "Source A", error_type: "parse_error", error_message: "parsers.table_html.ParseError: 未知的 HTML 结构 — 已存入 unknown_format 队列，待人工核查", url: "https://me.hnu.edu.cn/info/1084/2356.htm", occurred_at: "2026-09-14T13:32:11", retry_count: 0, status: "active" },
            { id: "fail_005", school: "华中科技大学", college: "人工智能与自动化学院", source: "Source A", error_type: "dns_error", error_message: "临时 DNS 解析失败，第二次请求即恢复", url: "https://www.iii.hust.edu.cn/", occurred_at: "2026-09-14T12:15:09", retry_count: 1, status: "resolved" },
        ],
    },

    config: {
        global: { delay_range: [1.0, 3.0], max_retries: 3, timeout: 30, cooldown_threshold: 5, cooldown_seconds: 1800, workers: 4, year: 2026, fuzzy_threshold: 0.85, user_agents: ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"] },
        schools: [
            { university: "东南大学", categories: [{ college: "机械工程学院", category: "mechanical", faculty: { list_url: "http://me.seu.edu.cn/xscz/list.htm", list_type: "static_html", list_item_selector: "li > a[title=姓名]", detail_selectors: { name: ".carrer .jsbt" } } }, { college: "自动化学院", category: "automation", faculty: { list_url: "https://automation.seu.edu.cn/_wp3services/generalQuery?queryObj=teacherHome", list_type: "ajax_api" } }], tutor_count: 311, verified: true },
            { university: "清华大学", categories: [{ college: "机械工程系", category: "mechanical", faculty: { list_url: "https://www.mee.tsinghua.edu.cn/szdw/js.htm", list_type: "static_html" } }], tutor_count: 186, verified: true },
            { university: "北京航空航天大学", categories: [{ college: "机械工程及自动化学院", category: "mechanical", faculty: { list_url: "", list_type: "static_html" } }], tutor_count: 0, verified: false },
        ],
    },
};

/**
 * Mock 数据提取器 — 模拟服务端分页 / 筛选
 */
function _mockFilter(items, q, fields) {
    if (!q) return items;
    q = q.toLowerCase();
    return items.filter((item) =>
        fields.some((f) => String(item[f] || "").toLowerCase().includes(q))
    );
}

function _mockPaginate(items, page, pageSize) {
    const total = items.length;
    const start = (page - 1) * pageSize;
    return { items: items.slice(start, start + pageSize), total, page, page_size: pageSize };
}

function _getMockData(endpoint) {
    const url = endpoint.split("?")[0];
    if (url === "/api/overview") return MOCK.overview;

    if (url === "/api/schools") {
        const params = new URLSearchParams(endpoint.split("?")[1] || "");
        let items = MOCK.schools().items;
        const q = params.get("q") || "";
        const status = params.get("status") || "";
        const category = params.get("category") || "";
        items = _mockFilter(items, q, ["name"]);
        if (status) items = items.filter((i) => i.status === status);
        if (category) items = items.filter((i) => i.category === category);
        const p = Math.max(1, +params.get("page") || 1);
        const ps = Math.min(100, Math.max(1, +params.get("page_size") || 20));
        const paged = _mockPaginate(items, p, ps);
        const summary = MOCK.schools().summary;
        return { ...paged, summary };
    }

    if (url.startsWith("/api/schools/")) {
        const id = parseInt(url.split("/").pop(), 10);
        return MOCK.config.schools[id - 1] || {};
    }

    if (url === "/api/tutors") {
        const params = new URLSearchParams(endpoint.split("?")[1] || "");
        let items = MOCK.tutors.items;
        const q = params.get("q") || "";
        const school = params.get("school") || "";
        const college = params.get("college") || "";
        const level = params.get("level") || "";
        const match = params.get("match") || "";
        items = _mockFilter(items, q, ["name", "areas"]);
        if (school) items = items.filter((i) => i.school === school);
        if (college) items = items.filter((i) => i.college === college);
        if (level) items = items.filter((i) => i.level === level);
        if (match) items = items.filter((i) => i.match_status === match);
        const p = Math.max(1, +params.get("page") || 1);
        const ps = Math.min(100, Math.max(1, +params.get("page_size") || 20));
        return _mockPaginate(items, p, ps);
    }

    if (url.startsWith("/api/tutors/")) {
        // /api/tutors/{school}/{name}
        const parts = url.split("/");
        const school = decodeURIComponent(parts[3]);
        const name = decodeURIComponent(parts[4]);
        const found = MOCK.tutors.items.find((t) => t.school === school && t.name === name);
        return found || { ...MOCK.tutors.items[0], raw_ref: { faculty: "", notice: "" } };
    }

    if (url === "/api/failures") {
        const params = new URLSearchParams(endpoint.split("?")[1] || "");
        let items = MOCK.failures.items;
        const status = params.get("status") || "";
        const source = params.get("source") || "";
        if (status) items = items.filter((i) => i.status === status);
        if (source) items = items.filter((i) => i.source === source);
        const p = Math.max(1, +params.get("page") || 1);
        const ps = Math.min(100, Math.max(1, +params.get("page_size") || 20));
        const paged = _mockPaginate(items, p, ps);
        return { ...paged, summary: MOCK.failures.summary };
    }

    if (url === "/api/config") return MOCK.config;

    // crawl / retry / ignore / test / save / import / export — 模拟成功
    return { task_id: "mock_task_" + Date.now(), status: "queued", message: "模拟任务已加入队列" };
}

// ------------------------------------------------------------------
// 统一 API 调用封装
// ------------------------------------------------------------------

let _mockToastShown = false;

async function apiCall(endpoint, options = {}) {
    /**
     * @param {string} endpoint  如 "/api/overview"
     * @param {object} options   fetch 选项
     * @returns {object}         data 字段内容
     * @throws {Error}           业务错误（code !== 0）时抛出
     */
    const url = `${API_BASE}${endpoint}`;
    const isWrite = options.method && options.method !== "GET";
    const config = {
        headers: { "Content-Type": "application/json" },
        ...options,
    };

    try {
        const resp = await fetch(url, { ...config, signal: config.signal || AbortSignal.timeout(10000) });

        // 非正常 HTTP 状态 — 回退到 Mock
        if (!resp.ok && !isWrite) {
            if (!_mockToastShown) {
                showToast("后端服务不可用，显示模拟数据", "warning", 5000);
                _mockToastShown = true;
            }
            return _getMockData(endpoint);
        }

        const json = await resp.json();

        if (json.code !== 0) {
            const err = new Error(json.message || "请求失败");
            err.code = json.code;
            err.detail = json.detail;
            throw err;
        }

        _mockToastShown = false; // 后端恢复，重置标记
        return json.data;
    } catch (err) {
        if (err.code) throw err; // 业务错误 — 由调用方捕获并 Toast

        // 网络错误 — 回退到 Mock
        if (USE_MOCK_FALLBACK && !isWrite) {
            if (!_mockToastShown) {
                showToast("后端服务不可用，显示模拟数据", "warning", 5000);
                _mockToastShown = true;
            }
            return _getMockData(endpoint);
        }
        throw new Error(`网络错误: ${err.message}`);
    }
}


// ------------------------------------------------------------------
// 高层 API 封装 — 所有页面通过 api.* 调用，绝不直接 fetch
// ------------------------------------------------------------------

const api = {
    // 总览
    overview: () => apiCall("/api/overview"),

    // 学校列表
    schools: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return apiCall(`/api/schools${qs ? "?" + qs : ""}`);
    },
    schoolDetail: (id) => apiCall(`/api/schools/${encodeURIComponent(id)}`),

    // 采集任务
    startCrawl: (params) => apiCall("/api/crawl", {
        method: "POST",
        body: JSON.stringify(params),
    }),
    taskProgress: (taskId) => apiCall(`/api/tasks/${encodeURIComponent(taskId)}`),

    // 导师列表
    tutors: (params = {}) => {
        const qs = new URLSearchParams(params).toString();
        return apiCall(`/api/tutors${qs ? "?" + qs : ""}`);
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
        return apiCall(`/api/failures${qs ? "?" + qs : ""}`);
    },
    retryFailures: (ids) => apiCall("/api/failures/retry", {
        method: "POST",
        body: JSON.stringify({ failure_ids: ids }),
    }),
    retryAllFailures: () => apiCall("/api/failures/retry", {
        method: "POST",
        body: JSON.stringify({ retry_all: true }),
    }),
    ignoreFailure: (id) => apiCall(`/api/failures/${encodeURIComponent(id)}/ignore`, {
        method: "POST",
    }),

    // 配置
    getConfig: () => apiCall("/api/config"),
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
    importConfig: (formData) => fetch(`${API_BASE}/api/config/import`, {
        method: "POST",
        body: formData,
    }).then((r) => r.json()).then((json) => {
        if (json.code !== 0) {
            const err = new Error(json.message || "导入失败");
            err.code = json.code;
            throw err;
        }
        return json.data;
    }),
    exportConfig: () => {
        window.open(`${API_BASE}/api/config/export`, "_blank");
    },

    // 原件查看
    rawFile: (path) => `${API_BASE}/api/raw/${encodeURIComponent(path)}`,
};
