const glyphs = {
  network: '<rect x="8" y="2" width="8" height="6" rx="2"/><rect x="2" y="16" width="7" height="6" rx="2"/><rect x="15" y="16" width="7" height="6" rx="2"/><path d="M12 8v4M5.5 16v-4h13v4"/>',
  dashboard: '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="5" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/><rect x="13" y="10" width="8" height="11" rx="1.5"/>',
  bot: '<rect x="4" y="6" width="16" height="14" rx="4"/><path d="M12 6V3M2 12v3m20-3v3M9 13h.01M15 13h.01"/>',
  tasks: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2h6v2M8.5 10.5l1 1 2-2m2.5 1.5h2m-7.5 5 1 1 2-2m2.5 1.5h2"/>',
  chart: '<path d="M3 3v18h18M7 15l4-5 4 3 5-7"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  activity: '<path d="M2 12h5l3-7 4 14 3-7h5"/>',
  building: '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M9 21v-4h6v4M8 7h.01M12 7h.01M16 7h.01M8 11h.01M12 11h.01M16 11h.01"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/>',
  bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  "chevron-down": '<path d="m6 9 6 6 6-6"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.9M16 3.3a4 4 0 0 1 0 7.4"/><circle cx="9" cy="7" r="4"/>',
  store: '<path d="M3 10l2-6h14l2 6M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0M5 13v7h14v-7m-9 7v-5h4v5"/>',
  megaphone: '<path d="m3 10 4-1 12-5v16L7 15l-4-1v-4zm4 5 2 6h3l-2-5M22 10v4"/>',
  facility: '<path d="m14 7 3 3 4-4a6 6 0 0 1-7.5 7.5L6 21a2.1 2.1 0 0 1-3-3l7.5-7.5A6 6 0 0 1 18 3l-4 4Z"/>',
  shield: '<path d="M12 22c5-2 8-6 8-11V5l-8-3-8 3v6c0 5 3 9 8 11Z"/><path d="m9 12 2 2 4-4"/>',
  bolt: '<path d="m13 2-9 12h7l-1 8 10-12h-7l1-8Z"/>',
  wallet: '<path d="M20 8V6a2 2 0 0 0-2-2H6a3 3 0 0 0 0 6h14a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H6a3 3 0 0 1-3-3V7m19 6h-6a2 2 0 0 0 0 4h6"/>',
  pin: '<path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
  x: '<path d="m6 6 12 12M18 6 6 18"/>',
  menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  warning: '<path d="M10.3 4.5 2.4 18.2A1.9 1.9 0 0 0 4 21h16a1.9 1.9 0 0 0 1.6-2.8L13.7 4.5a2 2 0 0 0-3.4 0ZM12 9v4m0 4h.01"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
};

function icon(name) {
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + glyphs[name] + '</svg>';
}

function hydrateIcons() {
  document.querySelectorAll('[data-icon]:empty').forEach((node) => {
    node.innerHTML = icon(node.dataset.icon);
  });
}

const agents = {
  hub: { name: "运营调度", icon: "network", tone: "blue", role: "统筹全场 · 编排协同任务", description: "汇总业务 Agent 的发现，分配协同任务，向值班经理提交需要审批的现场行动。" },
  traffic: { name: "客流", icon: "users", tone: "blue", role: "监测各区域人流密度", description: "读取区域客流与出入口计数，识别拥挤趋势，向运营调度 Agent 提供异常位置和预测。" },
  merchant: { name: "商户", icon: "store", tone: "violet", role: "跟进商户销售与排队", description: "核对商户营业、销售和排队情况，向营销和调度 Agent 回传商业运营数据。" },
  marketing: { name: "营销", icon: "megaphone", tone: "rose", role: "跟进活动转化与触达", description: "分析活动触达与核销，结合商户反馈拟定活动调整方案。" },
  facility: { name: "设施", icon: "facility", tone: "teal", role: "核查设备与动线冗余", description: "核对扶梯、出入口和设备状态，向协同任务提供可行的替代动线。" },
  safety: { name: "安保", icon: "shield", tone: "amber", role: "待命巡检与现场响应", description: "核对巡逻和人员排班，接收经值班经理审批的现场处置任务，并回传结果。" },
};

const taskStatus = {
  approval: ["模拟待审批", "approval"],
  running: ["协同中", "running"],
  done: ["已完成", "done"],
  dismissed: ["已驳回", "dismissed"],
};

const templates = {
  crowd: {
    name: "中庭客流疏导", area: "L1 中庭", icon: "warning", tone: "amber",
    summary: "客流 Agent 发现中庭密度达到 82%，预计 15 分钟内接近预警上限。设施 Agent 已核查东侧通道可用。",
    recommendation: "将部分客流引导至东侧通道，并由安保 Agent 通知现场值守人员，跟进疏导后的区域密度。",
    steps: [["traffic", "发现中庭密度上升，提交 15 分钟趋势预警。"], ["facility", "确认东侧通道与扶梯可用，回传替代动线。"], ["hub", "整合现场数据，提交疏导方案供值班经理审批。"], ["safety", "执行疏导，回传现场反馈与疏导结果。"]],
  },
  campaign: {
    name: "调整餐饮券投放", area: "L3 餐饮区", icon: "megaphone", tone: "violet",
    summary: "营销 Agent 发现餐饮券午后核销低于预期。商户 Agent 已确认两家轻食门店仍有可用接待能力。",
    recommendation: "将部分餐饮券调整至轻食门店，在 16:00–18:00 分批触达。",
    steps: [["marketing", "发现午后券核销低于预期，拟定轻食分时投放方案。"], ["merchant", "核对各门店接待能力与券库存。"], ["hub", "向值班经理提交调整方案。"], ["marketing", "更新券包投放并复核核销变化。"]],
  },
  equipment: {
    name: "东区扶梯巡检", area: "L2 东区", icon: "facility", tone: "teal",
    summary: "设施 Agent 收到扶梯运行监测提醒，安保 Agent 正协同确认巡检期间的通行动线。",
    recommendation: "完成扶梯现场复核后，由设施 Agent 登记检查结果。",
    steps: [["facility", "读取设备运行记录并创建巡检事项。"], ["hub", "协调设施与安保 Agent 核对巡检时段。"], ["safety", "确认巡检期间的备用通行动线。"], ["facility", "复核设备并回传状态。"]],
  },
  sales: {
    name: "核验午间销售波动", area: "L2 零售区", icon: "store", tone: "blue",
    summary: "商户 Agent 与客流 Agent 已核验午间销售增长，主要来自服饰门店活动客流。",
    recommendation: "保留当前活动配置，持续跟踪订单转化。",
    steps: [["merchant", "发现午间订单量变化。"], ["traffic", "对照同一时间段的入店客流。"], ["hub", "汇总销售与客流变化，归档结论。"]],
  },
  store: {
    name: "商铺运营核查", area: "所选商铺", icon: "store", tone: "blue",
    summary: "值班人员从 3D 商场视图选定商铺，发起运营核查。",
    recommendation: "由商户和设施 Agent 核对商铺运营信息与报修记录，将待处理事项回传调度 Agent。",
    steps: [["merchant", "核对商铺运营状态和已登记事项。"], ["facility", "核对商铺设备和报修记录。"], ["hub", "合并核查结果并提交值班经理审批。"], ["merchant", "跟进待处理事项并回传结果。"]],
  },
};

const initialTasks = [
  { id: "crowd", type: "crowd", title: "L1 中庭客流密度预警", time: "14:32", status: "approval" },
  { id: "equipment", type: "equipment", title: "L2 东区扶梯巡检", time: "14:28", status: "running" },
  { id: "sales", type: "sales", title: "午间销售波动核验", time: "14:21", status: "done" },
  { id: "campaign", type: "campaign", title: "L3 餐饮券投放调整", time: "14:08", status: "approval" },
];

const zones = [
  { id: "dining", floor: "L3", label: "L3 餐饮区", x: 67, y: 30, type: "campaign", note: "餐饮区整体客流平稳，营销 Agent 有一条餐饮券调整建议。", status: "正常", color: "#58e0ba" },
  { id: "atrium", floor: "L1", label: "L1 中庭 · 客流预警", x: 51, y: 59, type: "crowd", note: "中庭客流密度达到 82%。运营调度 Agent 已汇总客流预测和可用疏导路线。", status: "需关注", color: "#ffc079" },
  { id: "east", floor: "L2", label: "L2 东区 · 巡检", x: 79, y: 47, type: "equipment", note: "设施 Agent 和安保 Agent 正协同跟进东区扶梯巡检。", status: "协同中", color: "#a5baff" },
  { id: "entry", floor: "L1", label: "L1 西侧入口", x: 24, y: 46, type: "", note: "西侧入口客流平稳，客流 Agent 正监测各入口计数。", status: "正常", color: "#58e0ba" },
];

const metricData = [
  { title: "今日客流", yesterdayTitle: "昨日客流", icon: "users", tone: "blue", today: ["28,462", "人次", "+12.8%", "较昨日同期"], yesterday: ["25,233", "人次", "+6.4%", "较前日同期"], trend: "0,26 12,21 22,24 34,13 46,17 58,9 68,13 83,4" },
  { title: "今日销售额", yesterdayTitle: "昨日销售额", icon: "wallet", tone: "violet", today: ["186.4", "万元", "+8.3%", "较昨日同期"], yesterday: ["172.1", "万元", "+3.2%", "较前日同期"], trend: "0,26 12,23 23,25 35,16 46,19 58,10 68,12 83,4" },
  { title: "在营商户", icon: "store", tone: "teal", today: ["168", "家", "98.2%", "营业率"], yesterday: ["166", "家", "97.1%", "营业率"], trend: "0,26 12,20 24,23 36,15 48,17 59,10 72,12 83,6" },
  { title: "待关注事件", icon: "bolt", tone: "amber", today: ["03", "项", "2 项待审批", "需运营介入"], yesterday: ["02", "项", "1 项待审批", "同一统计时点"], trend: "0,27 12,18 22,23 36,12 48,23 60,14 71,20 83,9" },
];

const storageKey = "xinghui-ops-demo-v1";
function readTasks() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (Array.isArray(saved) && saved.every((task) => templates[task.type] && taskStatus[task.status])) return saved;
  } catch { /* Continue with the sample tasks when storage is unavailable. */ }
  return structuredClone(initialTasks);
}

let tasks = readTasks();
let floor = "all";
let taskFilter = "all";
let toastTimer;
let currentDetail;
const dialog = document.querySelector("#detail-dialog");
const content = document.querySelector("#dialog-content");
const menu = document.querySelector("#menu-toggle");
const sidebar = document.querySelector("#sidebar");
const byId = (id) => document.getElementById(id);
const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
const agentName = (id) => agents[id].name + " Agent";
const findTask = (id) => tasks.find((task) => task.id === id);
const openCount = () => tasks.filter((task) => task.status === "approval" || task.status === "running").length;
const approvalCount = () => tasks.filter((task) => task.status === "approval").length;
const iconBox = (name, classes = "") => '<span class="' + classes + '" data-icon="' + name + '"></span>';
const statePill = (label, style) => '<span class="status-pill ' + style + '"><i></i>' + label + '</span>';
const taskPill = (task) => statePill(...taskStatus[task.status]);

function nextDemoTime() {
  const [hours, minutes] = (tasks[0]?.time || "14:32").split(":").map(Number);
  const total = (hours * 60 + minutes + 1) % (24 * 60);
  return [Math.floor(total / 60), total % 60].map((part) => String(part).padStart(2, "0")).join(":");
}

function renderMetrics() {
  const period = byId("period").value;
  byId("metrics").innerHTML = metricData.map((item, index) => {
    let [value, unit, trend, caption] = item[period];
    if (period === "today" && index === 3) {
      value = String(openCount()).padStart(2, "0");
      trend = approvalCount() ? approvalCount() + " 项待审批" : "无待审批";
      caption = approvalCount() ? "需运营介入" : "当前状态";
    }
    const baseTitle = period === "yesterday" ? item.yesterdayTitle || item.title : item.title;
    const title = baseTitle + "（模拟数据）";
    const points = item.trend;
    return '<article class="metric ' + item.tone + '"><div class="metric-top">' + iconBox(item.icon, "metric-icon") + title
      + '</div><div class="metric-value">' + value + '<small>' + unit + '</small></div><div class="metric-note"><strong class="' + (index === 3 ? "attention" : "") + '">' + trend
      + '</strong><span>' + caption + '</span></div><svg class="sparkline" viewBox="0 0 83 36" aria-hidden="true"><defs><linearGradient id="fade-' + index
      + '" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox"><stop stop-color="currentColor" stop-opacity=".19"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs><polygon points="' + points
      + ' 83,36 0,36" fill="url(#fade-' + index + ')"/><polyline points="' + points + '" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></article>';
  }).join("");
}

function zoneView(zone) {
  const related = tasks.filter((item) => item.type === zone.type);
  const task = related.find((item) => ["running", "approval"].includes(item.status)) || related[0];
  if (zone.id === "atrium" && task?.status === "running") {
    return { ...zone, task, label: "L1 中庭 · 疏导中", status: "协同中", color: "#a5baff", note: "疏导方案已审批，安保 Agent 正跟进东侧通道引导。" };
  }
  if ((zone.id === "east" || zone.id === "atrium") && task?.status === "done") {
    return { ...zone, task, label: zone.floor + (zone.id === "east" ? " 东区 · 巡检完成" : " 中庭 · 疏导完成"), status: "正常", color: "#58e0ba", note: zone.id === "east" ? "设施 Agent 已完成东区扶梯巡检并回传结果。" : "安保 Agent 已回传疏导结果，客流密度回落至 61%。" };
  }
  if (zone.id === "atrium" && task?.status === "dismissed") {
    return { ...zone, task, note: "中庭仍处于客流预警状态。当前疏导方案已驳回。" };
  }
  return { ...zone, task };
}

function renderMap() {
  byId("map-points").innerHTML = zones.filter((zone) => floor === "all" || zone.floor === floor).map(zoneView).map((zone) =>
    '<button class="map-event" data-zone="' + zone.id + '" data-state="' + zone.status + '">'
    + iconBox(zone.status === "需关注" ? "warning" : "pin") + zone.label + '</button>').join("");
}

function agentState(id) {
  if (id === "hub") return ["模拟在线", "done", agents[id].role];
  const working = tasks.find((task) => task.status === "running" && templates[task.type].steps.at(-1)[0] === id);
  if (working) return ["协同中", "running", working.title];
  const handedOff = tasks.find((task) => task.status === "approval" && templates[task.type].steps[0][0] === id);
  if (handedOff) return ["已上报", "warning", handedOff.title];
  const supporting = tasks.find((task) => task.status === "running" && templates[task.type].steps.at(-2)[0] === id);
  if (supporting) return ["协助中", "running", supporting.title];
  if (id === "safety") return ["待命", "idle", agents[id].role];
  return ["模拟在线", "done", agents[id].role];
}

function renderAgents() {
  byId("agent-tree").innerHTML = Object.entries(agents).filter(([id]) => id !== "hub").map(([id, agent]) => {
    const [status, color, note] = agentState(id);
    return '<button class="agent-row" data-agent="' + id + '">' + iconBox(agent.icon, "agent-icon " + agent.tone) + '<span class="agent-content"><strong>' + agentName(id)
      + '</strong><small>' + escape(note) + '</small></span>' + statePill(status, color) + '</button>';
  }).join("");
  byId("agent-directory").innerHTML = Object.entries(agents).map(([id, agent]) => {
    const [status, color, note] = agentState(id);
    return '<button class="panel directory-card ' + (id === "hub" ? "is-hub" : "") + '" data-agent="' + id + '"><div class="directory-title">'
      + iconBox(agent.icon, "agent-icon " + agent.tone) + '<strong>' + agentName(id) + '</strong>' + statePill(status, color)
      + '</div><p>' + agent.description + '</p><small>' + escape(note) + '</small></button>';
  }).join("");
}

function team(task) {
  return [...new Set(templates[task.type].steps.map(([id]) => id))].map((id) => agents[id].name).join(" · ");
}

function handoff(task) {
  const { steps } = templates[task.type];
  if (task.status === "dismissed") return "值班经理 · 已驳回 " + agentName("hub") + " 提交的建议。";
  const index = task.status === "approval" ? steps.length - 2 : steps.length - 1;
  const note = task.status === "done" ? "已回传结果，运营调度 Agent 已归档。" : steps[index][1];
  return agentName(steps[index - 1][0]) + " → " + agentName(steps[index][0]) + " · " + note;
}

function renderActivity() {
  byId("event-list").innerHTML = tasks.slice(0, 3).map((task) =>
    '<button class="event-row" data-task="' + task.id + '"><span class="event-time">' + task.time + '</span><span class="event-dot ' + templates[task.type].tone
    + '"></span><span class="event-detail"><strong>' + escape(task.title) + '</strong><small>' + handoff(task) + '</small></span>' + taskPill(task) + '</button>').join("");
  const pending = tasks.filter((task) => task.status === "approval");
  byId("action-count").textContent = pending.length;
  byId("action-list").innerHTML = pending.length ? pending.slice(0, 2).map((task) => {
    const sample = templates[task.type];
    return '<button class="action-row" data-task="' + task.id + '">' + iconBox(sample.icon, "action-icon " + sample.tone)
      + '<span class="action-body"><strong>' + escape(task.id === task.type ? sample.name : task.title) + '</strong><small>' + sample.area + ' · ' + agentName(sample.steps[0][0])
      + ' 发起</small></span><span class="text-link">查看演示</span></button>';
  }).join("") : '<p class="empty">当前没有模拟待审批的建议。</p>';
  byId("nav-count").textContent = openCount();
}

function taskRecord(task) {
  const sample = templates[task.type];
  return '<button class="record" data-task="' + task.id + '">' + iconBox(sample.icon,"agent-icon " + sample.tone)
    + '<span class="record-main"><strong>' + escape(task.title) + '</strong><small>' + sample.area + ' · ' + team(task)
    + '</small></span><span class="record-time">' + task.time + '</span>' + taskPill(task) + '</button>';
}

function renderRecords() {
  const filtered = tasks.filter((task) => taskFilter === "all" || task.status === taskFilter);
  byId("task-list").innerHTML = filtered.map(taskRecord).join("") || '<p class="empty">此状态暂无任务。</p>';
  const insights = tasks.filter((task) => task.type === "crowd" || task.type === "campaign");
  byId("insight-list").innerHTML = insights.map(taskRecord).join("") || '<p class="empty">暂无运营建议。</p>';
}

function render() {
  renderMetrics();
  renderMap();
  renderAgents();
  renderActivity();
  renderRecords();
  hydrateIcons();
}

function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(tasks)); } catch { /* The current session still retains the changes. */ }
  render();
}

function closeMenu() {
  sidebar.classList.remove("open");
  menu.setAttribute("aria-expanded", "false");
  menu.setAttribute("aria-label", "打开导航");
}

function navigate() {
  const key = location.hash.slice(1);
  if (key === "main") return;
  const page = ["overview", "agents", "tasks", "insights"].includes(key) ? key : "overview";
  document.querySelectorAll(".page").forEach((node) => { node.hidden = node.id !== "page-" + page; });
  document.querySelectorAll("[data-page]").forEach((node) => {
    if (node.dataset.page === page) node.setAttribute("aria-current", "page");
    else node.removeAttribute("aria-current");
  });
  const title = byId("page-" + page).querySelector("h1").textContent;
  document.title = title + " · 星汇运营中枢";
  closeMenu();
  window.scrollTo(0, 0);
}

function showDialog(title, eyebrow, markup, detail) {
  byId("dialog-heading").innerHTML = '<span class="dialog-eyebrow">' + eyebrow + '</span><h2 id="dialog-title">' + escape(title) + '</h2>';
  content.innerHTML = markup;
  currentDetail = detail;
  hydrateIcons();
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
}

function showTask(task) {
  const sample = templates[task.type];
  const steps = sample.steps.map(([id, note], index) => {
    const last = index === sample.steps.length - 1;
    const active = last && task.status === "running";
    const pending = last && ["approval", "dismissed"].includes(task.status);
    const status = pending ? (task.status === "dismissed" ? "已取消" : "模拟待审批") : active ? "执行中" : "已完成";
    const text = last && task.status === "done" ? "已回传结果并归档。" : note;
    return '<li class="flow-step ' + (pending ? "pending" : "") + '">' + iconBox(agents[id].icon, "agent-icon " + agents[id].tone)
      + '<div><strong>' + agentName(id) + ' <span class="inline-status ' + (active ? "running" : pending ? "warning" : "") + '">' + status
      + '</span></strong><p>' + text + '</p></div></li>';
  }).join("");
  const actions = {
    approval: '<button class="primary-button" data-action="approve">' + iconBox("check") + '模拟批准并派单</button><button class="secondary-button" data-action="dismiss">模拟驳回</button>',
    running: '<button class="primary-button" data-action="complete">' + iconBox("check") + '模拟回传结果</button>',
    done: "", dismissed: "",
  };
  const result = task.status === "done" ? '<section><h3>演示执行回执</h3><p>' + (task.type === "crowd" ? "安保 Agent 已回传疏导结果，中庭客流密度由 82% 回落至 61%。" : "负责执行的 Agent 已回传处理结果，运营调度 Agent 已归档。") + '</p></section>' : "";
  showDialog(task.title, "协同任务 · " + sample.area, '<div class="dialog-summary">' + taskPill(task) + '<time>' + task.time
    + '</time><span>' + team(task) + '</span></div><p>' + sample.summary + '</p><section><h3>处理建议</h3><p>'
    + sample.recommendation + '</p></section><section><h3>Agent 交接记录</h3><ol class="flow">' + steps + '</ol></section>' + result
    + '<div class="dialog-actions">' + actions[task.status] + '</div>', { type: "task", id: task.id });
}

function showAgent(id) {
  const agent = agents[id];
  const [status, color, note] = agentState(id);
  const related = tasks.filter((task) => templates[task.type].steps.some(([stepId]) => stepId === id));
  showDialog(agentName(id), "Agent 工作台", '<div class="dialog-summary">' + iconBox(agent.icon, "agent-icon " + agent.tone) + statePill(status, color)
    + '<span>' + escape(note) + '</span></div><p>' + agent.description + '</p><section><h3>参与的协同任务</h3>'
    + (related.map(taskRecord).join("") || '<p>当前暂无协同任务。</p>') + '</section>', { type: "agent", id });
}

function showZone(id) {
  const zone = zoneView(zones.find((item) => item.id === id));
  const color = { "正常": "done", "需关注": "warning", "协同中": "running" };
  showDialog(zone.label, "商场态势 · " + zone.floor, '<div class="dialog-summary">' + statePill(zone.status, color[zone.status])
    + '</div><p>' + zone.note + '</p><section><h3>相关' + (zone.task ? "任务" : " Agent") + '</h3>'
    + (zone.task ? taskRecord(zone.task) : '<button class="secondary-button" data-agent="traffic">查看客流 Agent</button>') + '</section>', { type: "zone", id });
}

function showNotifications() {
  byId("unread-dot").hidden = true;
  const pending = tasks.filter((task) => task.status === "approval");
  showDialog("消息通知", "运营工作台", '<p>' + (pending.length ? "待你查看的模拟 Agent 建议" : "当前没有模拟待审批的建议。") + '</p>'
    + (pending.length ? '<section>' + pending.map(taskRecord).join("") + '</section>' : ""), { type: "notifications" });
}

function templatePreview(type) {
  return '<h3>预计协同顺序</h3><ol class="flow">' + templates[type].steps.map(([id, note]) =>
    '<li class="flow-step">' + iconBox(agents[id].icon, "agent-icon " + agents[id].tone) + '<div><strong>' + agentName(id) + '</strong><p>' + note + '</p></div></li>').join("") + '</ol>';
}

function showNewTask(shop = null) {
  const selected = shop ? "store" : "crowd";
  const options = ["crowd", "campaign", "equipment", "store"].map((type) => '<option value="' + type + '"' + (type === selected ? " selected" : "") + '>' + templates[type].name + '</option>').join("");
  const title = shop ? shop.id + " " + shop.name + " · 运营核查" : "";
  showDialog("发起协同", "协同任务", '<p>选择运营场景，调度 Agent 将按场景安排业务 Agent 处理。</p><form id="new-task-form">'
    + '<label class="field">运营场景<select name="type" id="new-task-type">' + options + '</select></label>'
    + '<label class="field">任务名称<input name="title" maxlength="40" placeholder="可使用场景默认名称" value="' + escape(title) + '"></label>'
    + '<div class="route-preview" id="route-preview">' + templatePreview(selected) + '</div><div class="dialog-actions">'
    + '<button class="primary-button" type="submit">创建协同任务</button></div></form>', { type: "new" });
}

function toast(message) {
  const region = byId("toast");
  region.textContent = message;
  region.classList.add("visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => region.classList.remove("visible"), 3200);
}

function updateTask(action) {
  const task = currentDetail?.type === "task" ? findTask(currentDetail.id) : null;
  if (!task) return;
  const transitions = { approve: ["approval", "running", "模拟批准：执行 Agent 已接单（演示）"], dismiss: ["approval", "dismissed", "模拟驳回建议"], complete: ["running", "done", "已收到模拟执行回执"] };
  const [from, to, message] = transitions[action];
  if (task.status !== from) return;
  task.status = to;
  task.time = nextDemoTime();
  tasks = [task, ...tasks.filter((item) => item !== task)];
  persist();
  dialog.close();
  toast(message);
}

document.addEventListener("click", (event) => {
  if (!event.target.closest(".sidebar, .menu-toggle")) closeMenu();
  const button = event.target.closest("button");
  if (!button) return;
  const { action, agent, task, zone, filter } = button.dataset;
  if (button === menu) {
    if (sidebar.classList.contains("open")) closeMenu();
    else {
      sidebar.classList.add("open");
      menu.setAttribute("aria-expanded", "true");
      menu.setAttribute("aria-label", "关闭导航");
      sidebar.querySelector('[aria-current="page"]')?.focus();
    }
  } else if (agent) showAgent(agent);
  else if (task) showTask(findTask(task));
  else if (zone) showZone(zone);
  else if (filter) {
    taskFilter = filter;
    byId("task-filters").querySelectorAll("button").forEach((node) => node.setAttribute("aria-pressed", node === button));
    renderRecords();
    hydrateIcons();
  } else if (action === "new") showNewTask();
  else if (action === "notifications") showNotifications();
  else if (action === "close") dialog.close();
  else if (["approve", "dismiss", "complete"].includes(action)) updateTask(action);
});

document.addEventListener("mall-floor-change", (event) => {
  floor = event.detail.floor ? "L" + event.detail.floor : "all";
  renderMap();
  hydrateIcons();
});
document.addEventListener("mall-shop-action", (event) => showNewTask(event.detail));

document.addEventListener("change", (event) => {
  if (event.target.id === "period") renderMetrics();
  if (event.target.id === "new-task-type") byId("route-preview").innerHTML = templatePreview(event.target.value);
  hydrateIcons();
});

document.addEventListener("submit", (event) => {
  if (event.target.id !== "new-task-form") return;
  event.preventDefault();
  const fields = new FormData(event.target);
  const type = fields.get("type");
  if (!templates[type]) return;
  const time = nextDemoTime();
  const task = { id: "task-" + Date.now(), type, title: fields.get("title").trim() || templates[type].name, time, status: "approval" };
  tasks.unshift(task);
  persist();
  showTask(task);
});

dialog.addEventListener("click", (event) => {
  if (event.target === dialog && event.clientX < dialog.getBoundingClientRect().left) dialog.close();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && sidebar.classList.contains("open")) {
    closeMenu();
    menu.focus();
  }
});
window.addEventListener("hashchange", navigate);
navigate();
render();
