/**
 * 争议案件处理台协调层（Task 027 → Task 032 改版）
 *
 * 职责：加载 meta / 案件列表、提交调查、选择案件、渲染各视图、处理节点与审批交互。
 * 并发约束：详情请求用「序号 + AbortController」双保险，快速切换时旧响应不会覆盖新选中案件；
 * 事件只在启动时绑定一次。
 * 真实性：请求进行中只显示“调查执行中”，不伪造逐节点进度；状态全部来自后端字段。
 */

import { apiCalls, ApiError } from './api.js';
import * as vm from './view-model.js';
import * as cs from './case-status.js';
import { renderGraph, initGraphResize } from './components/graph.js';
import { renderSteps, renderCards } from './components/case-head.js';
import {
  renderSummary, renderConflicts, renderEvidence, renderCalls, renderApproval, renderRaw, renderNodeDetail,
} from './components/report.js';
import { el, clear } from './dom.js';
import { formatDate } from './format.js';

const $ = (id) => document.getElementById(id);

const dom = {
  shell: $('wb-shell'),
  sidebarToggle: $('sidebar-toggle'),
  refreshBtn: $('refresh-btn'),
  newRunBtn: $('new-run-btn'),
  roleLabel: $('role-label'),
  headerPretitle: $('header-pretitle'),
  headerTitle: $('header-title'),
  headerIssue: $('header-issue'),
  headerQuestion: $('header-question'),
  headerSub: $('header-sub'),
  runStatusBadge: $('run-status-badge'),
  pageAlert: $('page-alert'),
  steps: $('progress-steps'),
  cards: $('conclusion-cards'),

  drawer: $('new-run-drawer'),
  drawerClose: $('drawer-close'),
  form: $('run-form'),
  question: $('question'),
  leaseId: $('lease-id'),
  withApproval: $('with-approval'),
  submitBtn: $('submit-btn'),
  submitLabel: $('submit-label'),
  submitSpinner: $('submit-spinner'),
  formStatus: $('form-status'),
  formAlert: $('form-alert'),

  search: $('run-search'),
  filter: $('run-filter'),
  runsList: $('runs-list'),
  runsEmpty: $('runs-empty'),
  runsLoading: $('runs-loading'),
  runsCount: $('runs-count'),

  graphCanvas: $('graph-canvas'),
  graphLinks: $('graph-links'),
  nodeDetail: $('node-detail'),
  nodeDetailBody: $('node-detail-body'),
  nodeDetailClose: $('node-detail-close'),

  reportMeta: $('report-meta'),
  paneSummary: $('pane-summary'),
  paneConflicts: $('pane-conflicts'),
  paneEvidence: $('pane-evidence'),
  paneApproval: $('pane-approval'),
  paneCalls: $('pane-calls'),
  paneRaw: $('pane-raw'),
};

const state = {
  meta: null,
  runs: [],
  currentRunId: null,
  currentRun: null,
  previousRun: null,
  pending: false,
  pendingQuestion: '',
  selectedNode: null,
  listSeq: 0,
  detailSeq: 0,
  detailAbort: null,
  submitting: false,
  refreshing: false,
  noticeTimer: null,
  activeTab: 'summary',
};

/* ------------------------------------------------------------- 提示区 */

function showPageAlert(kind, message, traceId) {
  dom.pageAlert.className = `wb-alert wb-alert-${kind}`;
  clear(dom.pageAlert);
  dom.pageAlert.appendChild(el('div', { text: message }));
  if (traceId) {
    dom.pageAlert.appendChild(el('div', { class: 'wb-muted' }, [
      '服务端追踪号：',
      el('span', { class: 'wb-mono', text: traceId }),
    ]));
  }
  if (state.noticeTimer) window.clearTimeout(state.noticeTimer);
  if (kind === 'success' || kind === 'info') {
    state.noticeTimer = window.setTimeout(() => dom.pageAlert.classList.add('d-none'), 5000);
  }
}

function clearPageAlert() {
  dom.pageAlert.className = 'wb-alert d-none';
  clear(dom.pageAlert);
}

function showFormAlert(message, traceId) {
  dom.formAlert.className = 'wb-alert wb-alert-danger';
  clear(dom.formAlert);
  dom.formAlert.appendChild(el('div', { text: message }));
  if (traceId) {
    dom.formAlert.appendChild(el('div', { class: 'wb-muted' }, [
      '服务端追踪号：',
      el('span', { class: 'wb-mono', text: traceId }),
    ]));
  }
}

function clearFormAlert() {
  dom.formAlert.className = 'wb-alert wb-alert-danger d-none';
  clear(dom.formAlert);
}

/* --------------------------------------------------------------- 案件头 */

function setStatusBadge(node, stateKey, label) {
  node.dataset.status = stateKey;
  node.textContent = label;
}

function principalLabel(principalId) {
  const principals = (state.meta && state.meta.principals) || {};
  const entry = principals[principalId];
  return entry && entry.label ? entry.label : '角色名称未提供';
}

function renderHeader() {
  if (state.pending) {
    dom.headerPretitle.textContent = '新调查执行中';
    dom.headerTitle.textContent = '等待后端返回结果';
    dom.headerIssue.classList.add('d-none');
    dom.headerQuestion.textContent = vm.shorten(state.pendingQuestion, 120);
    dom.headerSub.textContent = '请求尚未返回：本页不推测各领域的进度，结果返回后一次性展示。';
    setStatusBadge(dom.runStatusBadge, 'pending', '调查执行中');
    return;
  }
  const run = state.currentRun;
  if (!run) {
    dom.headerPretitle.textContent = '尚未选择案件';
    dom.headerTitle.textContent = '选择左侧案件，或新建一次调查';
    dom.headerIssue.classList.add('d-none');
    dom.headerQuestion.textContent = '';
    dom.headerSub.textContent = '本页只呈现事实、证据与审批状态，不执行调账、减免或派单。';
    setStatusBadge(dom.runStatusBadge, 'idle', '未选择');
    return;
  }
  const { lease } = cs.displayOf(run);
  const statusMeta = vm.runStatusMeta(run.status, {
    reportError: Boolean(vm.reportErrorOf(run)),
    verdict: vm.textOr(run.report && run.report.verdict, vm.textOr(run.verdict, '')),
    approvalStatus: vm.textOr(run.approval_status, ''),
  });
  const place = lease
    ? [lease.project_name, lease.building_name, lease.floor ? `${lease.floor} 层` : '']
      .filter(Boolean).join(' · ')
    : '项目与楼层信息未提供';
  dom.headerPretitle.textContent = place;
  dom.headerTitle.textContent = cs.caseTitle(run);
  dom.headerIssue.textContent = cs.caseIssueType(run);
  dom.headerIssue.classList.remove('d-none');
  dom.headerQuestion.textContent = vm.textOr(run.question, '（问题未提供）');
  dom.headerQuestion.title = vm.textOr(run.question, '');
  dom.headerSub.textContent = `受理于 ${formatDate(run.created_at)} · 最近更新 ${formatDate(run.updated_at)}${lease && lease.lease_no ? ` · 合同编号 ${lease.lease_no}` : ''}`;
  setStatusBadge(dom.runStatusBadge, statusMeta.state, statusMeta.label);
}

function renderCaseOverview() {
  if (state.pending) {
    renderSteps(dom.steps, cs.STEP_DEFS.map((def, index) => ({
      key: def.key,
      title: def.title,
      state: index === 0 ? 'done' : 'waiting',
      detail: index === 0 ? '已提交' : '等待结果',
    })));
    renderCards(dom.cards, [
      { key: 'verdict', title: '争议结论', tone: 'idle', value: '调查执行中', note: '结果返回后展示' },
      { key: 'amount', title: '金额差异', tone: 'idle', value: '—', note: '' },
      { key: 'gaps', title: '资料缺口', tone: 'idle', value: '—', note: '' },
      { key: 'next', title: '下一步', tone: 'idle', value: '等待调查结果', note: '' },
    ]);
    return;
  }
  renderSteps(dom.steps, cs.progressModel(state.currentRun, { meta: state.meta }));
  renderCards(dom.cards, cs.conclusionCards(state.currentRun, { meta: state.meta }));
}

/* ------------------------------------------------------------ 案件列表 */

function renderRuns() {
  const filtered = vm.filterRuns(state.runs, {
    query: dom.search.value,
    status: dom.filter.value,
  });
  dom.runsCount.textContent = state.runs.length ? `${filtered.length} / ${state.runs.length}` : '0';

  clear(dom.runsList);
  for (const run of filtered) {
    const statusMeta = vm.runStatusMeta(run.status, {
      verdict: vm.textOr(run.verdict, ''),
      approvalStatus: vm.textOr(run.approval_status, ''),
    });
    const active = run.run_id === state.currentRunId;
    const item = el('button', {
      type: 'button',
      class: `wb-case-item${active ? ' is-active' : ''}`,
      dataset: { run: run.run_id },
      attrs: { role: 'listitem', 'aria-current': active ? 'true' : 'false', title: vm.textOr(run.question, '') },
    }, [
      el('span', { class: 'wb-case-item-title', text: cs.caseTitle(null, run.display || null) }),
      el('span', { class: 'wb-case-item-question', text: vm.textOr(run.question, '（问题未提供）') }),
      el('span', { class: 'wb-case-item-meta' }, [
        el('span', { class: 'wb-status', dataset: { status: statusMeta.state }, text: statusMeta.label }),
        el('span', { class: 'wb-case-item-time', text: formatDate(run.created_at) }),
      ]),
    ]);
    dom.runsList.appendChild(item);
  }

  const empty = filtered.length === 0;
  dom.runsEmpty.classList.toggle('d-none', !empty);
  if (empty) {
    const title = dom.runsEmpty.querySelector('.wb-empty-title');
    if (title) title.textContent = state.runs.length ? '没有匹配的案件' : '还没有案件';
  }
}

/* ------------------------------------------------------------ 整体渲染 */

function renderViews() {
  renderHeader();
  renderCaseOverview();

  const run = state.pending ? null : state.currentRun;
  const graphModel = state.pending ? vm.buildPendingGraphModel() : vm.buildGraphModel(run);
  renderGraph(dom.graphCanvas, dom.graphLinks, graphModel, state.pending ? {} : vm.nodeHighlights(run));

  if (state.pending) {
    const message = () => el('div', { class: 'wb-muted wb-pending-note' }, [
      el('span', { class: 'wb-spinner', attrs: { 'aria-hidden': 'true' } }),
      '调查执行中，等待后端返回结果。',
    ]);
    [dom.paneSummary, dom.paneConflicts, dom.paneEvidence, dom.paneApproval, dom.paneCalls, dom.paneRaw]
      .forEach((pane) => { clear(pane); pane.appendChild(message()); });
    dom.reportMeta.textContent = '';
  } else {
    renderSummary(dom.paneSummary, run, { meta: state.meta });
    renderConflicts(dom.paneConflicts, run);
    renderEvidence(dom.paneEvidence, run);
    renderApproval(dom.paneApproval, run, { meta: state.meta, onDecide: handleDecide });
    renderCalls(dom.paneCalls, run);
    renderRaw(dom.paneRaw, run);
    dom.reportMeta.textContent = run ? `更新于 ${formatDate(run.updated_at)}` : '';
  }

  renderNodeSelection();
}

/** 只刷新节点选中态与详情面板，避免重新渲染时清掉审批输入框内容 */
function renderNodeSelection() {
  for (const node of dom.graphCanvas.querySelectorAll('.wb-node')) {
    node.setAttribute('aria-pressed', node.dataset.node === state.selectedNode ? 'true' : 'false');
  }
  if (!state.selectedNode) {
    dom.nodeDetail.classList.add('d-none');
    return;
  }
  const run = state.pending ? null : state.currentRun;
  dom.nodeDetail.classList.remove('d-none');
  renderNodeDetail(dom.nodeDetailBody, run, state.selectedNode, { meta: state.meta });
}

/* ------------------------------------------------------------ 页签 */

function selectTab(name) {
  state.activeTab = name;
  for (const tab of document.querySelectorAll('.wb-tab')) {
    const on = tab.id === `tab-${name}`;
    tab.classList.toggle('is-active', on);
    tab.setAttribute('aria-selected', on ? 'true' : 'false');
    tab.tabIndex = on ? 0 : -1;
  }
  for (const pane of document.querySelectorAll('.wb-pane')) {
    pane.classList.toggle('d-none', pane.id !== `pane-${name}`);
  }
}

/* ------------------------------------------------------------ 选中案件 */

async function selectRun(runId, { silent = false } = {}) {
  if (!runId) return;
  const seq = ++state.detailSeq;
  if (state.detailAbort) state.detailAbort.abort();
  const controller = new AbortController();
  state.detailAbort = controller;
  if (!silent) clearPageAlert();

  try {
    const run = await apiCalls.getRun(runId, controller.signal);
    if (seq !== state.detailSeq) return;
    state.currentRun = run;
    state.currentRunId = run.run_id || runId;
    state.pending = false;
    renderViews();
    renderRuns();
  } catch (error) {
    if (error && error.name === 'AbortError') return;
    if (seq !== state.detailSeq) return;
    showPageAlert('danger', `读取案件详情失败：${error.message}`, error.traceId);
  }
}

function beginPending(previousRun, question) {
  state.detailSeq += 1;
  if (state.detailAbort) state.detailAbort.abort();
  state.previousRun = previousRun || null;
  state.pending = true;
  state.pendingQuestion = question;
  state.currentRun = null;
  state.currentRunId = null;
  state.selectedNode = null;
  renderViews();
  renderRuns();
}

function restoreAfterFailure() {
  state.pending = false;
  state.detailSeq += 1;
  if (state.detailAbort) state.detailAbort.abort();
  if (state.previousRun) {
    state.currentRun = state.previousRun;
    state.currentRunId = state.previousRun.run_id;
  }
  renderViews();
  renderRuns();
}

/* ------------------------------------------------------------ 列表加载 */

async function loadRuns({ resetSelectionOnEmpty = false } = {}) {
  const seq = ++state.listSeq;
  dom.runsLoading.classList.remove('d-none');
  try {
    const data = await apiCalls.listRuns(50);
    if (seq !== state.listSeq) return;
    state.runs = vm.asArray(data && data.runs);
    renderRuns();
    if (!state.runs.length && resetSelectionOnEmpty) {
      state.currentRun = null;
      state.currentRunId = null;
      renderViews();
    }
  } catch (error) {
    if (seq !== state.listSeq) return;
    showPageAlert('danger', `读取案件列表失败：${error.message}`, error.traceId);
  } finally {
    if (seq === state.listSeq) dom.runsLoading.classList.add('d-none');
  }
}

async function loadMeta() {
  try {
    state.meta = await apiCalls.meta();
    const principal = state.meta && state.meta.trusted_principal;
    dom.roleLabel.textContent = principal ? principalLabel(principal) : '角色未提供';
    dom.roleLabel.title = '当前登录角色（由服务端注入，页面不能自报身份）';
  } catch (error) {
    dom.roleLabel.textContent = '角色未知';
    showPageAlert('danger', `读取服务信息失败：${error.message}`, error.traceId);
  }
}

/* --------------------------------------------------------------- 提交 */

function setSubmitting(busy) {
  state.submitting = busy;
  dom.submitBtn.disabled = busy;
  dom.submitSpinner.classList.toggle('d-none', !busy);
  dom.submitLabel.textContent = busy ? '调查执行中…' : '提交调查';
  dom.formStatus.textContent = busy ? '正在等待后端返回完整结果' : '';
}

function openDrawer() {
  clearFormAlert();
  if (typeof dom.drawer.showModal === 'function') dom.drawer.showModal();
  else dom.drawer.setAttribute('open', '');
  dom.question.focus();
}

function closeDrawer() {
  if (typeof dom.drawer.close === 'function') dom.drawer.close();
  else dom.drawer.removeAttribute('open');
  dom.newRunBtn.focus();
}

async function handleSubmit(event) {
  event.preventDefault();
  if (state.submitting) return;

  const question = dom.question.value.trim();
  const leaseId = dom.leaseId.value.trim();
  clearFormAlert();
  if (!question) {
    showFormAlert('请填写调查问题。');
    dom.question.focus();
    return;
  }
  if (!leaseId) {
    showFormAlert('请填写租约编号。');
    dom.leaseId.focus();
    return;
  }

  setSubmitting(true);
  const previousRun = state.currentRun;
  try {
    beginPending(previousRun, question);
    const created = await apiCalls.submit({
      question,
      lease_id: leaseId,
      with_approval: dom.withApproval.checked,
    });
    closeDrawer();
    await loadRuns();
    await selectRun(created.run_id);
    showPageAlert('success', '调查已完成，结果已一次性返回。');
  } catch (error) {
    restoreAfterFailure();
    showFormAlert(`提交失败：${error.message}`, error.traceId);
    dom.formStatus.textContent = '';
  } finally {
    setSubmitting(false);
  }
}

/* --------------------------------------------------------------- 审批 */

async function handleDecide({ decision, actor, reason, draftVersion }) {
  if (!state.currentRunId) throw new ApiError('尚未选择案件', { code: 'no_run' });
  const result = await apiCalls.decide(state.currentRunId, { decision, actor, reason, draftVersion });
  await loadRuns();
  await selectRun(state.currentRunId);
  showPageAlert('success',
    decision === 'approve'
      ? '已提交批准。批准只产生草案状态，不执行任何调账或减免。'
      : '已提交驳回。');
  return result;
}

/* -------------------------------------------------------------- 事件 */

function bindEvents() {
  dom.form.addEventListener('submit', handleSubmit);
  dom.drawerClose.addEventListener('click', closeDrawer);
  dom.drawer.addEventListener('cancel', (event) => {
    if (state.submitting) event.preventDefault();
  });

  for (const button of document.querySelectorAll('.wb-example')) {
    button.addEventListener('click', () => {
      dom.question.value = button.dataset.question || '';
      dom.question.focus();
    });
  }

  dom.search.addEventListener('input', renderRuns);
  dom.filter.addEventListener('change', renderRuns);

  dom.runsList.addEventListener('click', (event) => {
    const item = event.target.closest('.wb-case-item');
    if (!item) return;
    selectRun(item.dataset.run);
    if (window.matchMedia('(max-width: 991px)').matches) setSidebar(false);
  });

  dom.graphCanvas.addEventListener('click', (event) => {
    const node = event.target.closest('.wb-node');
    if (!node) return;
    state.selectedNode = state.selectedNode === node.dataset.node ? null : node.dataset.node;
    renderNodeSelection();
  });
  dom.nodeDetailClose.addEventListener('click', () => {
    state.selectedNode = null;
    renderNodeSelection();
  });

  for (const tab of document.querySelectorAll('.wb-tab')) {
    tab.addEventListener('click', () => selectTab(tab.id.replace('tab-', '')));
    tab.addEventListener('keydown', (event) => {
      if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
      const tabs = [...document.querySelectorAll('.wb-tab')];
      const index = tabs.indexOf(tab);
      const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
      selectTab(next.id.replace('tab-', ''));
      next.focus();
    });
  }

  dom.newRunBtn.addEventListener('click', openDrawer);
  // 窄屏时案件列表默认收起，顶栏另放一个入口，保证随时能新建调查
  document.getElementById('new-run-btn-top').addEventListener('click', openDrawer);
  dom.sidebarToggle.addEventListener('click', () => setSidebar(dom.shell.classList.contains('is-collapsed')));

  dom.refreshBtn.addEventListener('click', async () => {
    if (state.refreshing) return;
    state.refreshing = true;
    dom.refreshBtn.disabled = true;
    dom.refreshBtn.textContent = '刷新中…';
    try {
      await loadMeta();
      await loadRuns();
      if (state.currentRunId) await selectRun(state.currentRunId, { silent: true });
      showPageAlert('info', '已重新读取服务端数据。');
    } finally {
      state.refreshing = false;
      dom.refreshBtn.disabled = false;
      dom.refreshBtn.textContent = '刷新';
    }
  });
}

function setSidebar(open) {
  dom.shell.classList.toggle('is-collapsed', !open);
  dom.sidebarToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}

/* --------------------------------------------------------------- 启动 */

async function init() {
  bindEvents();
  if (window.matchMedia('(max-width: 991px)').matches) setSidebar(false);
  initGraphResize(dom.graphCanvas, dom.graphLinks);
  selectTab('summary');
  renderViews();
  renderRuns();

  await loadMeta();
  await loadRuns({ resetSelectionOnEmpty: true });
  // 可分享的只读定位参数：?run=案件 &tab=页签 &tech=open（不改变任何数据）
  const params = new URLSearchParams(window.location.search);
  const requested = params.get('run');
  const initial = requested || (state.runs.length ? state.runs[0].run_id : null);
  if (initial && !state.currentRunId) await selectRun(initial, { silent: true });
  const tab = params.get('tab');
  if (tab && document.getElementById(`tab-${tab}`)) {
    selectTab(tab);
    if (tab === 'tech' && params.get('tech') === 'open') document.getElementById('tech-details').open = true;
  }
}

init();
