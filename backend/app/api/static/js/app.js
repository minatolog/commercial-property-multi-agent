/**
 * 工作台协调层（Task 027）
 *
 * 职责：加载 meta / 运行列表、提交调查、选择运行、渲染各视图、处理节点与审批交互。
 * 并发约束：详情请求用「序号 + AbortController」双保险，快速切换时旧响应不会覆盖新选中任务；
 * 事件只在启动时绑定一次，不在每次渲染后重复绑定。
 */

import { apiCalls, ApiError } from './api.js';
import * as vm from './view-model.js';
import { renderGraph, initGraphResize } from './components/graph.js';
import {
  renderSummary, renderEvidence, renderCalls, renderApproval, renderRaw, renderNodeDetail,
} from './components/report.js';
import { el, clear } from './dom.js';

const $ = (id) => document.getElementById(id);

const dom = {
  refreshBtn: $('refresh-btn'),
  newRunBtn: $('new-run-btn'),
  headerPretitle: $('header-pretitle'),
  headerTitle: $('header-title'),
  headerSub: $('header-sub'),
  runStatusBadge: $('run-status-badge'),
  pageAlert: $('page-alert'),

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

  statStatus: $('stat-status'),
  statStatusNote: $('stat-status-note'),
  statVerdict: $('stat-verdict'),
  statVerdictNote: $('stat-verdict-note'),
  statConflicts: $('stat-conflicts'),
  statConflictsNote: $('stat-conflicts-note'),
  statApproval: $('stat-approval'),
  statApprovalNote: $('stat-approval-note'),

  graphCanvas: $('graph-canvas'),
  graphLinks: $('graph-links'),
  nodeDetail: $('node-detail'),
  nodeDetailBody: $('node-detail-body'),
  nodeDetailClose: $('node-detail-close'),

  reportMeta: $('report-meta'),
  paneSummary: $('pane-summary'),
  paneEvidence: $('pane-evidence'),
  paneCalls: $('pane-calls'),
  paneApproval: $('pane-approval'),
  paneRaw: $('pane-raw'),
};

const state = {
  meta: null,
  runs: [],
  currentRunId: null,
  currentRun: null,
  previousRun: null,
  pending: false,
  selectedNode: null,
  listSeq: 0,
  detailSeq: 0,
  detailAbort: null,
  submitting: false,
  refreshing: false,
  noticeTimer: null,
};

/* ------------------------------------------------------------- 提示区 */

function showPageAlert(kind, message, traceId) {
  if (!dom.pageAlert) return;
  dom.pageAlert.className = `alert alert-${kind}`;
  clear(dom.pageAlert);
  dom.pageAlert.appendChild(el('div', { text: message }));
  if (traceId) {
    dom.pageAlert.appendChild(el('div', { class: 'small mt-1' }, [
      '服务端 trace_id：',
      el('span', { class: 'wb-mono', text: traceId }),
    ]));
  }
  if (state.noticeTimer) window.clearTimeout(state.noticeTimer);
  if (kind === 'success' || kind === 'info') {
    state.noticeTimer = window.setTimeout(() => dom.pageAlert.classList.add('d-none'), 5000);
  }
}

function clearPageAlert() {
  if (!dom.pageAlert) return;
  dom.pageAlert.className = 'alert d-none';
  clear(dom.pageAlert);
}

function showFormAlert(message, traceId) {
  dom.formAlert.className = 'alert alert-danger mt-3 mb-0';
  clear(dom.formAlert);
  dom.formAlert.appendChild(el('div', { text: message }));
  if (traceId) {
    dom.formAlert.appendChild(el('div', { class: 'small mt-1' }, [
      '服务端 trace_id：',
      el('span', { class: 'wb-mono', text: traceId }),
    ]));
  }
}

function clearFormAlert() {
  dom.formAlert.className = 'alert alert-danger mt-3 mb-0 d-none';
  clear(dom.formAlert);
}

/* --------------------------------------------------------------- 顶栏 */

function renderHeader() {
  if (state.pending) {
    dom.headerPretitle.textContent = '新调查执行中';
    dom.headerTitle.textContent = vm.shorten(dom.question.value, 96) || '等待后端返回结果';
    dom.headerSub.textContent = '请求尚未返回：节点状态待返回，本页不推测各 Agent 的进度。';
    setStatusBadge(dom.runStatusBadge, 'pending', '调查执行中');
    return;
  }
  if (!state.currentRun) {
    dom.headerPretitle.textContent = '尚未选择运行';
    dom.headerTitle.textContent = '选择历史运行，或提交一次新的调查';
    dom.headerSub.textContent = '身份由服务端注入；本页只呈现事实、证据与审批状态，不执行调账或派单。';
    setStatusBadge(dom.runStatusBadge, 'idle', '未选择运行');
    return;
  }
  const run = state.currentRun;
  const statusMeta = vm.runStatusMeta(run.status, { reportError: Boolean(vm.reportErrorOf(run)) });
  dom.headerPretitle.textContent = `租约 ${vm.textOr(run.lease_id, '未提供')} · ${vm.textOr(run.run_id, '未提供')}`;
  dom.headerTitle.textContent = vm.shorten(run.question, 96) || '（问题未提供）';
  dom.headerSub.textContent = `${statusMeta.label} · ${statusMeta.note} · 创建于 ${vm.formatTimestamp(run.created_at)}`;
  setStatusBadge(dom.runStatusBadge, statusMeta.state, statusMeta.label);
}

function setStatusBadge(node, stateKey, label) {
  if (!node) return;
  node.dataset.status = stateKey;
  node.textContent = label;
}

/* ------------------------------------------------------------ 概况条 */

function renderSummaryStrip() {
  const model = state.pending
    ? {
      status: { state: 'pending', label: '调查执行中', note: '等待结果，不显示逐节点进度' },
      verdict: { value: '待返回', note: 'verdict / completeness', tone: '' },
      conflicts: { value: '待返回', note: '结果返回后统计', tone: '' },
      approval: { value: '待返回', note: '审批状态随结果返回', tone: '' },
    }
    : vm.summaryModel(state.currentRun);

  dom.statStatus.textContent = model.status.label;
  dom.statStatusNote.textContent = model.status.note;
  dom.statVerdict.textContent = model.verdict.value;
  dom.statVerdictNote.textContent = model.verdict.note;
  dom.statConflicts.textContent = model.conflicts.value;
  dom.statConflictsNote.textContent = model.conflicts.note;
  dom.statApproval.textContent = model.approval.value;
  dom.statApprovalNote.textContent = model.approval.note;

  dom.statVerdictNote.className = `wb-stat-note ${model.verdict.tone || ''}`.trim();
  dom.statConflictsNote.className = `wb-stat-note ${model.conflicts.tone || ''}`.trim();
}

/* ------------------------------------------------------------ 历史列表 */

function renderRuns() {
  const filtered = vm.filterRuns(state.runs, {
    query: dom.search.value,
    status: dom.filter.value,
  });
  dom.runsCount.textContent = state.runs.length
    ? `${filtered.length} / ${state.runs.length}`
    : '0';

  clear(dom.runsList);
  for (const run of filtered) {
    const statusMeta = vm.runStatusMeta(run.status);
    const approval = vm.approvalMetaFor(run);
    // 运行状态本身已经是「待审批」时不再重复挂一个同文案的审批徽章
    const showApproval = approval
      && !(run.status === 'awaiting_approval' && run.approval_status === 'pending_approval');
    const item = el('button', {
      type: 'button',
      class: `wb-run-item${run.run_id === state.currentRunId ? ' is-active' : ''}`,
      dataset: { run: run.run_id },
      attrs: {
        role: 'listitem',
        'aria-current': run.run_id === state.currentRunId ? 'true' : 'false',
      },
    }, [
      el('span', { class: 'wb-run-question', text: vm.textOr(run.question, '（问题未提供）') }),
      el('span', { class: 'wb-run-meta' }, [
        badge(statusMeta.state, statusMeta.label),
        showApproval ? badge(approval.state, approval.label) : null,
        el('span', { class: 'wb-mono', text: vm.textOr(run.run_id, '') }),
        el('span', { text: vm.formatTimestamp(run.created_at) }),
      ]),
    ]);
    dom.runsList.appendChild(item);
  }

  const empty = filtered.length === 0;
  dom.runsEmpty.classList.toggle('d-none', !empty);
  if (empty) {
    const title = dom.runsEmpty.querySelector('.empty-title');
    if (title) {
      title.textContent = state.runs.length ? '没有匹配的运行' : '还没有运行记录';
    }
    const subtitle = dom.runsEmpty.querySelector('.empty-subtitle');
    if (subtitle) {
      subtitle.textContent = state.runs.length
        ? '调整筛选条件，或提交一次新的调查。'
        : '提交一次新的调查后，这里会显示最近 50 条运行。';
    }
  }
}

function badge(stateKey, label) {
  return el('span', { class: 'badge wb-status', dataset: { status: stateKey }, text: label });
}

/* ------------------------------------------------------------ 整体渲染 */

function renderViews() {
  renderHeader();
  renderSummaryStrip();

  const graphModel = state.pending ? vm.buildPendingGraphModel() : vm.buildGraphModel(state.currentRun);
  renderGraph(dom.graphCanvas, dom.graphLinks, graphModel);

  const run = state.pending ? null : state.currentRun;
  if (state.pending) {
    const message = el('div', { class: 'd-flex align-items-center gap-2 text-secondary small py-2' }, [
      el('span', { class: 'spinner-border spinner-border-sm', attrs: { 'aria-hidden': 'true' } }),
      '调查执行中，等待后端返回结果。规划 / 核验 / 报告节点没有独立实时事件，返回后按实际结果回顾。',
    ]);
    [dom.paneSummary, dom.paneEvidence, dom.paneCalls, dom.paneApproval, dom.paneRaw].forEach((pane) => {
      clear(pane);
      pane.appendChild(message.cloneNode(true));
    });
    dom.reportMeta.textContent = '等待本次运行结果';
  } else {
    renderSummary(dom.paneSummary, run);
    renderEvidence(dom.paneEvidence, run);
    renderCalls(dom.paneCalls, run);
    renderApproval(dom.paneApproval, run, {
      meta: state.meta,
      onDecide: handleDecide,
    });
    renderRaw(dom.paneRaw, run);
    dom.reportMeta.textContent = run
      ? `${vm.textOr(run.run_id, '')} · ${vm.formatTimestamp(run.updated_at)}`
      : '尚未选择运行';
  }

  if (state.selectedNode) {
    dom.nodeDetail.classList.remove('d-none');
    renderNodeDetail(dom.nodeDetailBody, run, state.selectedNode, { meta: state.meta });
  } else {
    dom.nodeDetail.classList.add('d-none');
  }

  for (const node of dom.graphCanvas.querySelectorAll('.wb-node')) {
    node.setAttribute('aria-pressed', node.dataset.node === state.selectedNode ? 'true' : 'false');
  }
}

/** 只刷新节点选中态与详情面板，避免重新渲染时会清掉审批输入框内容 */
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

/* ------------------------------------------------------------ 选中运行 */

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
    showPageAlert('danger', `读取运行详情失败：${error.message}`, error.traceId);
  }
}

function beginPending(previousRun) {
  state.detailSeq += 1;
  if (state.detailAbort) state.detailAbort.abort();
  state.previousRun = previousRun || null;
  state.pending = true;
  state.currentRun = null;
  state.currentRunId = null;
  state.selectedNode = null;
  clearFormAlert();
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
    showPageAlert('danger', `读取运行列表失败：${error.message}`, error.traceId);
  } finally {
    if (seq === state.listSeq) dom.runsLoading.classList.add('d-none');
  }
}

async function loadMeta() {
  try {
    state.meta = await apiCalls.meta();
    const principal = vm.textOr(state.meta && state.meta.trusted_principal, '未提供');
    dom.headerSub.textContent = `可信主体 ${principal}（服务端注入）；本页只呈现事实、证据与审批状态，不执行调账或派单。`;
  } catch (error) {
    showPageAlert('danger', `读取服务元数据失败：${error.message}`, error.traceId);
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
    showFormAlert('请填写租约 ID。');
    dom.leaseId.focus();
    return;
  }

  setSubmitting(true);
  const previousRun = state.currentRun;
  beginPending(previousRun);
  try {
    const created = await apiCalls.submit({
      question,
      lease_id: leaseId,
      with_approval: dom.withApproval.checked,
    });
    await loadRuns();
    await selectRun(created.run_id);
    showPageAlert('success', `已创建运行 ${vm.textOr(created.run_id, '')}（后端一次性返回完整结果）。`);
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
  if (!state.currentRunId) throw new ApiError('尚未选择运行', { code: 'no_run' });
  const result = await apiCalls.decide(state.currentRunId, {
    decision,
    actor,
    reason,
    draftVersion,
  });
  await loadRuns();
  await selectRun(state.currentRunId);
  showPageAlert('success',
    decision === 'approve'
      ? '已提交批准。批准只产生草案状态，不执行真实调账。'
      : '已提交驳回。');
  return result;
}

/* ------------------------------------------------------------- 节点详情 */

function selectNode(nodeId) {
  state.selectedNode = state.selectedNode === nodeId ? null : nodeId;
  renderNodeSelection();
}

function closeNodeDetail() {
  state.selectedNode = null;
  renderNodeSelection();
}

/* -------------------------------------------------------------- 事件 */

function bindEvents() {
  dom.form.addEventListener('submit', handleSubmit);

  for (const button of document.querySelectorAll('.wb-example')) {
    button.addEventListener('click', () => {
      dom.question.value = button.dataset.question || '';
      dom.question.focus();
    });
  }

  dom.search.addEventListener('input', renderRuns);
  dom.filter.addEventListener('change', renderRuns);

  dom.runsList.addEventListener('click', (event) => {
    const item = event.target.closest('.wb-run-item');
    if (!item) return;
    selectRun(item.dataset.run);
  });

  dom.graphCanvas.addEventListener('click', (event) => {
    const node = event.target.closest('.wb-node');
    if (!node) return;
    selectNode(node.dataset.node);
  });

  dom.nodeDetailClose.addEventListener('click', closeNodeDetail);

  dom.newRunBtn.addEventListener('click', () => {
    state.selectedNode = null;
    state.currentRun = null;
    state.currentRunId = null;
    state.pending = false;
    renderViews();
    renderRuns();
    dom.question.focus();
    document.getElementById('collab-card').scrollIntoView({ block: 'nearest' });
  });

  dom.refreshBtn.addEventListener('click', async () => {
    if (state.refreshing) return;
    state.refreshing = true;
    const original = dom.refreshBtn.textContent;
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
      dom.refreshBtn.textContent = original;
    }
  });
}

/* --------------------------------------------------------------- 启动 */

async function init() {
  bindEvents();
  initGraphResize(dom.graphCanvas, dom.graphLinks);
  renderViews();
  renderRuns();

  await loadMeta();
  await loadRuns({ resetSelectionOnEmpty: true });
  if (state.runs.length && !state.currentRunId) {
    await selectRun(state.runs[0].run_id, { silent: true });
  }
}

init();
