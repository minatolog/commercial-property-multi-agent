/**
 * view-model 行为回归用例（Task 029）
 *
 * 在真实浏览器里执行 `js/view-model.js` 的实际代码，覆盖 Task 028 的 U1–U3
 * 以及返修 Prompt 第 6 节列出的语义场景。
 *
 * 数据来源分两类，报告中必须区分：
 * - `fixture`：按后端真实输出契约构造的结构化反例（例如 report.error、权限拒绝）；
 * - `real`：由 Python 侧用隔离控制面实际调用 `POST /api/runs` 得到的返回体，
 *   通过 `/__tests__/real-runs.json` 注入。
 */

import * as vm from '../js/view-model.js';
import * as cs from '../js/case-status.js';
import { formatMoney, formatVariance } from '../js/format.js';
import { term, describeMissingItem, localizeErrorCodes, TERMS } from '../js/i18n.js';
import { renderSummary } from '../js/components/report.js';

/** 渲染真实的「案件摘要」组件，返回页面文本（Task 032 复查：断言真实渲染路径，不只测 helper） */
function summaryText(run) {
  const host = document.createElement('div');
  renderSummary(host, run);
  return host.textContent;
}

/** 后端 ErrorCode 枚举的全部取值（与 backend/app/agents/base/errors.py 同步，Python 测试守护） */
const BACKEND_ERROR_CODES = [
  'invalid_request', 'invalid_context', 'capability_not_declared', 'capability_unavailable',
  'agent_not_enabled', 'agent_not_registered', 'tool_not_allowed', 'tool_not_found',
  'invalid_tool_arguments', 'invalid_tool_result', 'insufficient_evidence', 'tool_timeout',
  'budget_exhausted', 'permission_denied', 'project_scope_denied', 'record_not_found',
  'deadline_exceeded', 'timeout', 'model_error', 'upstream_error', 'not_implemented', 'internal_error',
];

/** 主视图文本里残留的英文错误码 */
function leakedErrorCodes(text) {
  return BACKEND_ERROR_CODES.filter((code) => new RegExp(`(^|[^a-z_])${code}([^a-z_]|$)`).test(text));
}

/* ------------------------------------------------------------ 断言工具 */

function equal(actual, expected, label) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  return { label, actual, expected, ok: a === b };
}

function states(run) {
  const nodes = vm.buildGraphModel(run).nodes;
  const out = {};
  for (const key of Object.keys(nodes)) out[key] = nodes[key].state;
  return out;
}

function stateOf(run, nodeId) {
  return vm.buildGraphModel(run).nodes[nodeId].state;
}

function labels(run) {
  const nodes = vm.buildGraphModel(run).nodes;
  const out = {};
  for (const key of Object.keys(nodes)) out[key] = nodes[key].label;
  return out;
}

/* -------------------------------------------------------------- fixtures */

const COMPLEX_QUESTION = '商铺 A-301 投诉最近三个月租金金额不一致，同时声称空调多次维修未解决，并要求减免费用。请核对合同、账单、付款和工单。';

const LEASE_FINDING = {
  statement: '租期 2025-01-01 至 2027-12-31，状态 active',
  evidence_ids: ['lease_xh_a301_2025', 'unit_xh_a301', 'ten_xh_yunduan', 'rule_xh_a301_rent_2026', 'doc_xh_a301_contract'],
  derivation: 'direct',
};

const CLAUSE_FINDINGS = [
  {
    statement: '合同第 10 页 5.1.1 条：月租金金额按建筑面积乘以当期租金单价计算',
    evidence_ids: ['doc_xh_a301_contract#v1#p10#5.1.1'],
    derivation: 'document_clause',
    source: { document_id: 'doc_xh_a301_contract', document_version: 1, document_status: 'signed', page: 10, clause_id: '5.1.1', chunk_id: 'doc_xh_a301_contract#v1#p10#5.1.1' },
  },
  {
    statement: '合同第 23 页 9.1 条：乙方逾期支付租金超过三十日的，甲方有权解除合同',
    evidence_ids: ['doc_xh_a301_contract#v1#p23#9.1'],
    derivation: 'document_clause',
    source: { document_id: 'doc_xh_a301_contract', document_version: 1, document_status: 'signed', page: 23, clause_id: '9.1', chunk_id: 'doc_xh_a301_contract#v1#p23#9.1' },
  },
  {
    statement: '合同第 1 页 1.1 条：甲方将星汇广场 A 座 A-301 商铺出租给乙方使用',
    evidence_ids: ['doc_xh_a301_contract#v1#p1#1.1'],
    derivation: 'document_clause',
    source: { document_id: 'doc_xh_a301_contract', document_version: 1, document_status: 'signed', page: 1, clause_id: '1.1', chunk_id: 'doc_xh_a301_contract#v1#p1#1.1' },
  },
];

const BILLING_FINDING = {
  statement: '账单应收 52596.00、已收 34560.00、未收 18036.00',
  evidence_ids: ['lease_xh_a301_2025', 'inv_2026_08', 'itm_inv08_rent', 'pay_2026_08_28', 'alloc_001'],
  derivation: 'computed',
};

const PROPERTY_FINDING = {
  statement: '相关工单 3 条，未关闭 1 条',
  evidence_ids: ['wo_2026_07_12', 'wo_2026_08_18', 'wo_2026_09_25'],
  derivation: 'direct',
};

function complexRun(overrides = {}) {
  return {
    run_id: 'run_fixture_complex',
    thread_id: 'thread_fixture_complex',
    lease_id: 'lease_xh_a301_2025',
    question: COMPLEX_QUESTION,
    status: 'awaiting_approval',
    verdict: 'conflicting',
    approval_status: 'pending_approval',
    created_at: '2026-11-10T06:47:43+00:00',
    updated_at: '2026-11-10T06:47:43+00:00',
    report: {
      question: COMPLEX_QUESTION,
      lease_id: 'lease_xh_a301_2025',
      verdict: 'conflicting',
      route: 'fanout',
      revision: 0,
      findings: [LEASE_FINDING, ...CLAUSE_FINDINGS, BILLING_FINDING, PROPERTY_FINDING],
      conflicts: [
        {
          type: 'rent_variance',
          amount: '756.00',
          expected_basis: 'lease.charge_rule',
          observed_basis: 'invoice_item.unit_price',
          subtask_id: 'st_2_billing',
          evidence_ids: ['inv_2026_08', 'itm_inv08_rent'],
        },
      ],
      missing_information: ['合同引用但未电子化的文档: doc_xh_a301_annex_b'],
      completeness: 'partial',
      agent_results: [
        { subtask_id: 'st_1_lease', capability: 'lease.query', agent: 'lease', status: 'success' },
        { subtask_id: 'st_2_billing', capability: 'billing.statement', agent: 'billing', status: 'partial' },
        { subtask_id: 'st_3_property', capability: 'property.work_orders', agent: 'property', status: 'partial' },
      ],
      failures: [],
      resolved_failures: [],
      narrative_discrepancies: [],
      authoritative_amounts: [],
      requires_human_review: true,
      disclaimer: '本报告只陈述事实与冲突，不构成减免/调账决定',
      warnings: ['账单租金与合同规则存在差额: 756.00'],
    },
    traces: [
      { subtask_id: 'st_1_lease', tool: 'lease.lookup', status: 'ok', attempt: 1, duration_ms: 0.65 },
      { subtask_id: 'st_2_billing', tool: 'billing.statement.read', status: 'ok', attempt: 1, duration_ms: 0.83 },
      { subtask_id: 'st_3_property', tool: 'property.work_orders.read', status: 'ok', attempt: 1, duration_ms: 0.93 },
      { subtask_id: 'st_1_lease', tool: 'document.search', status: 'ok', attempt: 1, duration_ms: 0.73 },
    ],
    ...overrides,
  };
}

function budgetFailureRun() {
  return {
    run_id: 'run_fixture_budget',
    thread_id: 'thread_fixture_budget',
    lease_id: 'lease_xh_a301_2025',
    question: COMPLEX_QUESTION,
    status: 'failed',
    verdict: 'insufficient',
    approval_status: 'not_required',
    created_at: '2026-11-10T07:00:00+00:00',
    updated_at: '2026-11-10T07:00:00+00:00',
    report: {
      question: COMPLEX_QUESTION,
      verdict: 'insufficient',
      route: 'fanout',
      revision: 1,
      findings: [LEASE_FINDING],
      conflicts: [],
      missing_information: [
        '子任务 st_2_billing 失败: budget_exhausted',
        '子任务 st_3_property 失败: budget_exhausted',
      ],
      completeness: 'partial',
      agent_results: [
        { subtask_id: 'st_1_lease', capability: 'lease.query', agent: 'lease', status: 'partial' },
      ],
      failures: [
        { subtask_id: 'st_2_billing', capability: 'billing.statement', error_code: 'budget_exhausted', message: '预算不足：工具调用已达 1，预算 0', run_id: 'run_fixture_budget' },
        { subtask_id: 'st_3_property', capability: 'property.work_orders', error_code: 'budget_exhausted', message: '预算不足：工具调用已达 1，预算 0', run_id: 'run_fixture_budget' },
      ],
      resolved_failures: [],
      narrative_discrepancies: [],
      authoritative_amounts: [],
      requires_human_review: true,
      disclaimer: '本报告只陈述事实与冲突，不构成减免/调账决定',
      warnings: [],
    },
    traces: [
      { subtask_id: 'st_2_billing', tool: 'billing.statement.read', status: 'budget_exhausted', attempt: 1, duration_ms: 0 },
      { subtask_id: 'st_3_property', tool: 'property.work_orders.read', status: 'budget_exhausted', attempt: 1, duration_ms: 0 },
      { subtask_id: 'st_1_lease', tool: 'lease.lookup', status: 'ok', attempt: 1, duration_ms: 0.5 },
      { subtask_id: 'st_2_billing', tool: 'billing.statement.read', status: 'budget_exhausted', attempt: 2, duration_ms: 0 },
    ],
  };
}

function reportErrorRun() {
  return {
    run_id: 'run_fixture_error',
    thread_id: 'thread_fixture_error',
    lease_id: 'lease_xh_a301_2025',
    question: COMPLEX_QUESTION,
    status: 'failed',
    verdict: null,
    approval_status: null,
    created_at: '2026-11-10T07:10:00+00:00',
    updated_at: '2026-11-10T07:10:00+00:00',
    report: { error: { code: 'internal_error', message: 'injected test error' } },
    traces: [],
  };
}

function withReport(patch, base = complexRun()) {
  return { ...base, report: { ...base.report, ...patch } };
}

/* ---------------------------------------------------------------- 用例 */

export function buildCases() {
  const cases = [];
  const addCase = (name, source, fn) => cases.push({ name, source, fn });

  addCase('LangChain 调查：摘要显示模型回答、用量与有据建议', 'fixture', () => {
    const run = withReport({
      execution: { engine: 'llm', provider: 'deepseek' },
      budget: { used_model_calls: 7, used_total_tokens: 123 },
      agent_analyses: [{
        capability: 'billing.statement', answer: '模型已核对账单。',
        model: { served_models: ['model-from-response'] },
        evidence_ids: ['inv_2026_08'],
      }],
      synthesis: {
        status: 'completed', facts: [BILLING_FINDING], conflicts: [], gaps: [],
        next_steps: ['请财务核对账单。'],
      },
    });
    const text = summaryText(run);
    return [
      equal(text.includes('模型已核对账单。'), true, '显示领域回答'),
      equal(text.includes('model-from-response'), true, '显示响应模型'),
      equal(text.includes('模型请求 7 次 · 已记账 123 tokens'), true, '显示真实预算字段'),
      equal(text.includes('请财务核对账单。'), true, '显示综合建议'),
      equal(summaryText(withReport({ synthesis: { status: 'budget_exhausted' } })).includes('模型预算已用尽'), true, '解释综合分析中止'),
    ];
  });

  addCase('正常单领域：只标记真实参与的能力', 'fixture', () => {
    const run = {
      run_id: 'run_fixture_simple',
      status: 'completed',
      lease_id: 'lease_xh_a301_2025',
      question: 'A-301 现在还有多少钱没交？',
      report: {
        verdict: 'conflicting',
        route: 'deterministic',
        completeness: 'complete',
        findings: [BILLING_FINDING],
        conflicts: [],
        missing_information: [],
        failures: [],
        narrative_discrepancies: [],
        requires_human_review: true,
        agent_results: [{ subtask_id: 'st_1_billing', capability: 'billing.statement', agent: 'billing', status: 'partial' }],
      },
      traces: [{ subtask_id: 'st_1_billing', tool: 'billing.statement.read', status: 'ok', attempt: 1, duration_ms: 0.4 }],
    };
    const index = vm.buildSubtaskIndex(run);
    return [
      equal(states(run), {
        plan: 'success', verify: 'partial', report: 'partial', approval: 'not_called',
        'agent:lease': 'not_called', 'agent:billing': 'partial', 'agent:property': 'not_called',
      }, '节点状态：只高亮账单'),
      equal(index.counts, { subtasks: 1, results: 1, failures: 0, resolvedFailures: 0, traces: 1 }, '子任务计数'),
      equal(vm.findingsAttribution(run).byAgent.billing.length, 1, '账单发现归属'),
    ];
  });

  addCase('正常多领域：Agent / 计数 / 发现 / Trace 归属一致', 'fixture', () => {
    const run = complexRun();
    const index = vm.buildSubtaskIndex(run);
    const attribution = vm.findingsAttribution(run);
    const rows = vm.traceRows(run, index);
    return [
      equal(states(run), {
        plan: 'success', verify: 'partial', report: 'partial', approval: 'pending',
        'agent:lease': 'success', 'agent:billing': 'partial', 'agent:property': 'partial',
      }, '节点状态'),
      equal(index.counts, { subtasks: 3, results: 3, failures: 0, resolvedFailures: 0, traces: 4 }, '子任务计数（按 subtask_id 去重）'),
      equal(
        [attribution.byAgent.lease.length, attribution.byAgent.billing.length, attribution.byAgent.property.length],
        [4, 1, 1],
        '发现归属：租约 1 + 条款 3、账单 1、工单 1',
      ),
      equal(attribution.total, 6, '发现总数不丢失'),
      equal(attribution.crossDomain.length + attribution.unassociated.length, 0, '无跨领域 / 未关联'),
      equal(rows.map((row) => row.agent), ['lease', 'billing', 'property', 'lease'], 'Trace 的 Agent 归属'),
      equal(labels(run).plan, '多领域分流', '规划标签'),
    ];
  });

  addCase('工具预算耗尽：失败可见，保留错误码与工具尝试', 'fixture', () => {
    const run = budgetFailureRun();
    const index = vm.buildSubtaskIndex(run);
    const rows = vm.traceRows(run, index);
    const billing = index.byId.get('st_2_billing');
    const plan = vm.buildGraphModel(run).nodes.plan;
    return [
      equal(states(run), {
        plan: 'success', verify: 'failed', report: 'failed', approval: 'not_called',
        'agent:lease': 'partial', 'agent:billing': 'failed', 'agent:property': 'failed',
      }, '节点状态：失败不是未调用；报告节点与核验节点一致（Task 032 / U3-B，原为 partial）'),
      equal(labels(run)['agent:billing'], '失败 · 预算耗尽', '账单节点标签带错误原因（Task 032：经术语表转成中文）'),
      equal(billing.terminal, 'failed', '子任务终态'),
      equal(billing.failure.message.includes('预算不足'), true, '保留后端错误信息'),
      equal(billing.failure.error_code, 'budget_exhausted', '保留错误码'),
      equal(billing.traces.length, 2, '保留工具尝试记录'),
      equal([plan.failures, plan.results, plan.subtasks], [2, 1, 3], '规划计数使用真实子任务'),
      equal([rows[0].agent, rows[1].agent], ['billing', 'property'], '失败子任务的 Trace 仍有 Agent 归属'),
      equal(rows.filter((row) => !row.attributed).length, 0, '无未关联 Trace'),
    ];
  });

  addCase('权限拒绝 / 超时：不显示未调用，失败历史保留', 'fixture', () => {
    const run = {
      run_id: 'run_fixture_denied',
      status: 'failed',
      question: 'B-101 的租期是什么时候？',
      report: {
        verdict: 'insufficient',
        route: 'fanout',
        completeness: 'partial',
        findings: [],
        conflicts: [],
        missing_information: ['子任务 st_1_lease 失败: project_scope_denied'],
        failures: [
          { subtask_id: 'st_1_lease', capability: 'lease.query', error_code: 'project_scope_denied', message: '项目范围不允许访问 B-101' },
          { subtask_id: 'st_2_billing', capability: 'billing.statement', error_code: 'timeout', message: '工具调用超时' },
        ],
        narrative_discrepancies: [],
        requires_human_review: true,
        agent_results: [],
      },
      traces: [{ subtask_id: 'st_2_billing', tool: 'billing.statement.read', status: 'timeout', attempt: 1, duration_ms: 20000 }],
    };
    const index = vm.buildSubtaskIndex(run);
    return [
      equal([stateOf(run, 'agent:lease'), stateOf(run, 'agent:billing')], ['failed', 'failed'], '两个领域都是失败而非未调用'),
      equal(index.records.map((record) => record.terminal), ['failed', 'failed'], '失败记录终态'),
      equal(index.byId.get('st_1_lease').failure.error_code, 'project_scope_denied', '权限错误码保留'),
      equal(index.byId.get('st_2_billing').traces.length, 1, '超时子任务保留工具记录'),
      equal(stateOf(run, 'agent:property'), 'not_called', '未涉及的领域仍是未调用'),
      equal(stateOf(run, 'verify'), 'failed', '核验节点不掩盖失败'),
    ];
  });

  addCase('补查成功 + 多子任务：当前终态准确、旧失败可审计', 'fixture', () => {
    const run = withReport({
      verdict: 'supported',
      completeness: 'complete',
      findings: [LEASE_FINDING],
      conflicts: [],
      missing_information: [],
      failures: [],
      resolved_failures: [
        { subtask_id: 'st_1_lease', capability: 'lease.query', error_code: 'timeout', message: '首次尝试超时' },
      ],
      requires_human_review: false,
      agent_results: [
        { subtask_id: 'st_1_lease', capability: 'lease.query', agent: 'lease', status: 'success' },
        { subtask_id: 'st_2_lease', capability: 'lease.renewal_evaluation', agent: 'lease', status: 'partial' },
      ],
    });
    const index = vm.buildSubtaskIndex(run);
    const lease = vm.agentParticipation(run, vm.agentDefinitionByKey('lease'), index);
    return [
      equal(lease.state, 'partial', '同一领域多子任务取最严重终态'),
      equal(lease.subtasks.map((record) => record.subtaskId), ['st_1_lease', 'st_2_lease'], '不丢弃其它子任务'),
      equal(index.byId.get('st_1_lease').resolvedFailures.length, 1, '历史失败仍可审计'),
      equal(index.byId.get('st_1_lease').terminal, 'success', '补查成功后终态为成功'),
      equal(index.counts.failures, 0, '历史失败不计入当前失败'),
    ];
  });

  addCase('发现归属：租约 / 条款 / 账单 / 工单全覆盖', 'fixture', () => {
    const attribution = vm.findingsAttribution(complexRun());
    const leaseStatements = attribution.byAgent.lease.map((entry) => entry.finding.statement);
    return [
      equal(leaseStatements.length, 4, '合同节点显示租约 + 3 条条款'),
      equal(leaseStatements.filter((text) => text.startsWith('合同第')).length, 3, '三条条款在合同节点'),
      equal(attribution.byAgent.property.length, 1, '物业节点显示工单发现'),
      equal(attribution.byAgent.billing.length, 1, '账单节点显示账单发现'),
      equal(attribution.byAgent.lease[1].attribution.basis, 'source', '条款优先用 source 字段归属'),
      equal(attribution.byAgent.billing[0].attribution.basis, 'evidence', '账单按证据分组归属'),
    ];
  });

  addCase('跨领域 / 未知前缀 / 无证据：不误归且可见', 'fixture', () => {
    const run = withReport({
      findings: [
        LEASE_FINDING,
        { statement: '跨领域发现', evidence_ids: ['doc_xh_a301_contract#v1#p10#5.1.1', 'wo_2026_07_12'] },
        { statement: '未知前缀发现', evidence_ids: ['misc_ref_001'] },
        { statement: '无证据发现', evidence_ids: [] },
      ],
    });
    const attribution = vm.findingsAttribution(run);
    return [
      equal(attribution.total, 4, '总数不丢失'),
      equal(attribution.byAgent.lease.length, 1, '跨领域/未知/无证据不并入合同节点'),
      equal(attribution.byAgent.billing.length + attribution.byAgent.property.length, 0, '不复制到其它节点'),
      equal(attribution.crossDomain.map((entry) => entry.finding.statement), ['跨领域发现'], '跨领域单列'),
      equal(attribution.crossDomain[0].attribution.agents, ['lease', 'property'], '跨领域列出涉及领域'),
      equal(attribution.unassociated.map((entry) => entry.attribution.basis), ['unknown_prefix', 'no_evidence'], '未关联原因'),
    ];
  });

  addCase('report.error：规划 / 核验 / 报告均不给绿灯', 'fixture', () => {
    const run = reportErrorRun();
    const summary = vm.summaryModel(run);
    return [
      equal(states(run), {
        plan: 'unknown', verify: 'unknown', report: 'failed', approval: 'unknown',
        'agent:lease': 'not_called', 'agent:billing': 'not_called', 'agent:property': 'not_called',
      }, '异常报告不显示成功'),
      equal(Object.values(states(run)).includes('success'), false, '没有任何节点被判成功'),
      equal(summary.status.state, 'failed', '概况条执行状态'),
      equal(vm.runStatusMeta('completed', { reportError: true }).state, 'failed', 'report.error 覆盖 completed'),
      equal(vm.runStatusMeta('failed').state, 'failed', '普通失败状态不变'),
    ];
  });

  addCase('旧记录缺字段：显示未知而不是成功', 'fixture', () => {
    const run = { run_id: 'run_fixture_legacy', status: 'completed', report: { findings: [LEASE_FINDING] } };
    return [
      equal(states(run), {
        plan: 'unknown', verify: 'unknown', report: 'unknown', approval: 'not_called',
        'agent:lease': 'not_called', 'agent:billing': 'not_called', 'agent:property': 'not_called',
      }, '缺 verdict / route 时不给成功'),
      equal(Object.values(states(run)).includes('success'), false, '没有虚假成功'),
    ];
  });

  addCase('字段类型异常：不崩溃、不宣称无冲突', 'fixture', () => {
    const run = withReport({ conflicts: 'oops', missing_information: { a: 1 }, verdict: 'supported' });
    const nodes = vm.buildGraphModel(run).nodes;
    return [
      equal(nodes.verify.state, 'unknown', '核验状态：信息不足'),
      equal((nodes.verify.incomplete || []).slice().sort(), ['conflicts', 'missing_information'], '列出异常字段'),
      equal(nodes.report.state !== 'success', true, '报告节点不给绿灯'),
      equal(typeof nodes.verify.label, 'string', '渲染不抛异常'),
    ];
  });

  addCase('insufficient：报告已生成但证据不足', 'fixture', () => {
    const run = withReport({ verdict: 'insufficient', conflicts: [], missing_information: ['未获得子任务结果: st_3_property'], failures: [], findings: [LEASE_FINDING] });
    const nodes = vm.buildGraphModel(run).nodes;
    return [
      equal(nodes.verify.state, 'partial', '核验 partial'),
      equal(nodes.verify.label, '证据不足 · 需复核', '核验文案'),
      equal(nodes.report.state, 'partial', '报告不给绿灯'),
      equal(nodes.report.label, '报告已生成 · 证据不足', '报告文案区分“已生成”与“结论成立”'),
    ];
  });

  addCase('conflicting：冲突并列、需复核', 'fixture', () => {
    const run = withReport({ verdict: 'conflicting' });
    const nodes = vm.buildGraphModel(run).nodes;
    return [
      equal(nodes.verify.state, 'partial', '核验 partial'),
      equal(nodes.verify.label, '发现冲突 · 需复核', '核验文案'),
      equal(nodes.report.label, '报告已生成 · 存在冲突', '报告文案'),
    ];
  });

  addCase('叙述与字段不一致：核验降级', 'fixture', () => {
    const run = withReport({
      verdict: 'supported',
      conflicts: [],
      missing_information: [],
      failures: [],
      completeness: 'complete',
      narrative_discrepancies: [{ subtask_id: 'st_2_billing', kind: 'fund', status: 'mismatch' }],
      requires_human_review: true,
    });
    return [
      equal(stateOf(run, 'verify'), 'partial', '核验不因 verdict=supported 而绿灯'),
      equal(labels(run).verify.includes('叙述'), true, '文案指出叙述不一致'),
    ];
  });

  addCase('supported 且字段完整：可以显示成功', 'fixture', () => {
    const run = withReport({
      verdict: 'supported',
      conflicts: [],
      missing_information: [],
      failures: [],
      narrative_discrepancies: [],
      completeness: 'complete',
      requires_human_review: false,
    });
    const summary = vm.summaryModel(run);
    return [
      equal(stateOf(run, 'verify'), 'success', '核验成功'),
      equal(labels(run).verify, '证据核验通过', '核验文案'),
      equal(stateOf(run, 'report'), 'success', '报告成功'),
      equal(labels(run).report, '报告已生成 · 证据一致', '报告文案'),
      equal(summary.verdict.value, '证据一致', '概况条结论'),
    ];
  });

  addCase('Trace 归属：子任务缺失或未知时不猜', 'fixture', () => {
    const run = complexRun({
      traces: [
        { subtask_id: 'st_9_unknown', tool: 'lease.lookup', status: 'ok', attempt: 1, duration_ms: 0.1 },
        { tool: 'billing.statement.read', status: 'ok', attempt: 1, duration_ms: 0.2 },
        { subtask_id: 'st_2_billing', tool: 'billing.statement.read', status: 'ok', attempt: 1, duration_ms: 0.3 },
      ],
    });
    const index = vm.buildSubtaskIndex(run);
    const rows = vm.traceRows(run, index);
    return [
      equal(index.unattributedTraces.length, 2, '无法关联的记录单列'),
      equal(rows.map((row) => row.agent), ['', '', 'billing'], '不按下标或字符串猜 Agent'),
      equal(rows.map((row) => row.attributed), [false, false, true], 'attributed 标记'),
      equal(rows[0].agentLabel, '未关联', '未关联展示文案'),
    ];
  });


  /* ---------------------------------------------- Task 032：U3 参数化反例 */

  // 正常基线：supported、complete、冲突/缺口/失败/叙述差异均为空、requires_human_review=false
  const baseline = () => withReport({
    verdict: 'supported',
    conflicts: [],
    missing_information: [],
    failures: [],
    narrative_discrepancies: [],
    completeness: 'complete',
    requires_human_review: false,
  });
  const verdictOf = (run) => {
    const nodes = vm.buildGraphModel(run).nodes;
    return {
      verify: nodes.verify.state,
      report: nodes.report.state,
      summary: vm.summaryModel(run).verification.state,
      card: cs.conclusionCards(run)[0].tone,
    };
  };
  const cardTone = { success: 'success', partial: 'warning', failed: 'failed', unknown: 'unknown' };

  addCase('U3 基线：完整 supported 报告显示成功，四处一致', 'fixture', () => {
    const run = baseline();
    return [
      equal(verdictOf(run), { verify: 'success', report: 'success', summary: 'success', card: 'success' }, '核验 / 报告 / 摘要 / 结论卡均为成功'),
      equal(vm.buildGraphModel(run).nodes.report.label, '报告已生成 · 证据一致', '报告文案'),
    ];
  });

  const u3Rows = [
    // U3-A：布尔字段必须真的是 boolean；缺失 / 类型异常不能当 false
    ['U3-A requires_human_review=null', { requires_human_review: null }, 'unknown'],
    ['U3-A requires_human_review="true"', { requires_human_review: 'true' }, 'unknown'],
    ['U3-A requires_human_review=1', { requires_human_review: 1 }, 'unknown'],
    ['U3-A 删除 requires_human_review', { requires_human_review: undefined }, 'unknown'],
    ['U3-A 删除 failures', { failures: undefined }, 'unknown'],
    ['U3-A failures="invalid"', { failures: 'invalid' }, 'unknown'],
    ['U3-A 删除 narrative_discrepancies', { narrative_discrepancies: undefined }, 'unknown'],
    ['U3-A narrative_discrepancies 为对象', { narrative_discrepancies: { a: 1 } }, 'unknown'],
    // U3-B：任何一类负面事实都不能显示“证据一致”，且核验 / 报告 / 摘要一致
    ['U3-B failures 含 timeout', { failures: [{ subtask_id: 'st_2_billing', capability: 'billing.statement', error_code: 'timeout' }] }, 'failed'],
    ['U3-B narrative_discrepancies 含 mismatch', { narrative_discrepancies: [{ subtask_id: 'st_2_billing', kind: 'fund', status: 'mismatch' }] }, 'partial'],
    ['U3-B missing_information 非空', { missing_information: ['合同引用但未电子化的文档: doc_xh_a301_annex_b'] }, 'partial'],
    ['U3-B completeness=partial', { completeness: 'partial' }, 'partial'],
    ['U3-B conflicts 非空（verdict 仍为 supported）', { conflicts: [{ type: 'rent_variance', amount: '756.00' }] }, 'partial'],
    ['U3-B conflicts 缺失', { conflicts: undefined }, 'unknown'],
    ['U3-B conflicts 类型异常', { conflicts: 'oops' }, 'unknown'],
  ];
  for (const [name, patch, expected] of u3Rows) {
    addCase(name, 'fixture', () => {
      const run = withReport(patch, baseline());
      const got = verdictOf(run);
      return [
        equal(got, { verify: expected, report: expected, summary: expected, card: cardTone[expected] }, '核验 / 报告 / 摘要 / 结论卡一致，且不是成功'),
        equal(vm.buildGraphModel(run).nodes.report.label.includes('证据一致'), false, '报告节点不显示“证据一致”'),
      ];
    });
  }

  /* ------------------------- Task 032 复查：真实 renderSummary 渲染路径 */

  addCase('复查 P2-2：摘要“缺失与失败”在 failures 缺失 / 类型异常时显示待核实，不显示 0', 'fixture', () => {
    const out = [];
    for (const [label, patch] of [
      ['删除 failures', { failures: undefined }],
      ['failures="invalid"', { failures: 'invalid' }],
      ['删除 missing_information', { missing_information: undefined }],
      ['missing_information 为对象', { missing_information: { a: 1 } }],
    ]) {
      const text = summaryText(withReport(patch, baseline()));
      out.push(equal(text.includes('报告没有列出资料缺口或失败'), false, `${label}：不显示“没有缺口”`));
      out.push(equal(text.includes('缺失与失败待核实'), true, `${label}：计数显示“待核实”而不是 0`));
    }
    const ok = summaryText(baseline());
    out.push(equal(ok.includes('报告没有列出资料缺口或失败'), true, '基线：两个字段都是空数组时才显示“没有缺口”'));
    out.push(equal(ok.includes('缺失与失败0'), true, '基线：计数为 0'));
    return out;
  });

  addCase('复查 P2-1：摘要“系统提醒”里的错误码转成中文', 'fixture', () => {
    const run = budgetFailureRun();
    run.report.warnings = [
      '条款检索不可用（budget_exhausted），本次结论不含合同条款证据',
      '条款检索不可用(tool_timeout)',
      '账单查询失败: upstream_error',
    ];
    const text = summaryText(run);
    return [
      equal(leakedErrorCodes(text), [], '摘要页签不出现英文错误码'),
      equal(text.includes('条款检索不可用（预算耗尽），本次结论不含合同条款证据'), true, '告警措辞保留，只替换错误码'),
      equal(text.includes('账单查询失败: 上游服务错误'), true, '冒号后的错误码也转换'),
    ];
  });

  addCase('复查 P3-1：后端全部 ErrorCode 均有中文映射，未映射码不带英文进主视图', 'fixture', () => [
    equal(BACKEND_ERROR_CODES.filter((code) => !Object.prototype.hasOwnProperty.call(TERMS.errorCode, code)), [], '全部错误码有映射'),
    equal(term('errorCode', 'some_future_code'), '其他错误（原始代码见技术视图）', '未映射错误码不显示原值'),
    equal(localizeErrorCodes('查询失败：some_future_code'), '查询失败：其他错误（原始代码见技术视图）', '文本中的未映射错误码'),
    // 返修复查 P3-1：括号里的普通英文词不是错误码，不能被改写
    equal(localizeErrorCodes('本次检查（pending）'), '本次检查（pending）', '括号内未知词原样保留（全角）'),
    equal(localizeErrorCodes('合同状态(draft)待确认'), '合同状态(draft)待确认', '括号内未知词原样保留（半角）'),
    equal(localizeErrorCodes('条款检索不可用(tool_timeout)'), '条款检索不可用（查询超时）', '括号内已知错误码仍转换'),
  ]);

  /* -------------------------------------------- Task 032：格式化与术语 */

  addCase('金额格式化：只做字符串处理', 'fixture', () => [
    equal(formatMoney('18036.00'), '¥18,036.00', '18036.00'),
    equal(formatMoney('0.00'), '¥0.00', '0.00'),
    equal(formatMoney('-756.00'), '-¥756.00', '-756.00'),
    equal(formatMoney('1234567.5'), '¥1,234,567.50', '1234567.5'),
    equal(formatMoney(''), '未提供', '空字符串'),
    equal(formatMoney(null), '未提供', 'null'),
    equal(formatMoney('12abc'), '金额格式异常（12abc）', '非法字符串'),
    equal(formatMoney('0.1000000000000000055511151231257827'), '¥0.1000000000000000055511151231257827', '超长小数不经浮点、不四舍五入'),
    equal(formatMoney('99999999999999999.99'), '¥99,999,999,999,999,999.99', '超出浮点精度的整数部分原样保留'),
    equal(formatVariance('756.00'), { text: '+¥756.00', direction: 'over', label: '多计' }, '正差额 = 多计'),
    equal(formatVariance('-756.00'), { text: '−¥756.00', direction: 'under', label: '少计' }, '负差额 = 少计'),
    equal(formatVariance('0.00').direction, 'none', '零差额'),
  ]);

  addCase('术语映射：缺失映射显示原值，不留空', 'fixture', () => [
    equal(term('verdict', 'conflicting'), '存在冲突', '已知枚举'),
    equal(term('verdict', 'weird_value'), '未知状态（weird_value）', '未知枚举'),
    equal(term('verdict', null), '未提供', '缺失'),
    equal(term('capability', 'lease.query'), '合同查询', '能力名不出现在主视图'),
    equal(describeMissingItem('子任务 st_2_billing 失败: budget_exhausted'), '账单查询失败：预算耗尽', '失败说明'),
    equal(describeMissingItem('条款检索不可用（budget_exhausted），本次结论不含合同条款证据'), '条款检索不可用（预算耗尽），本次结论不含合同条款证据', '说明中夹带的错误码'),
    equal(
      describeMissingItem('合同引用但未电子化的文档: doc_xh_a301_annex_b', { documents: { doc_xh_a301_annex_b: { note: '合同附件B 尚未电子化' } } }),
      '合同附件B 尚未电子化',
      '缺失文档用业务描述',
    ),
  ]);

  /* ------------------------------------------- Task 032：流程步骤与结论卡 */

  const stepStates = (run) => cs.progressModel(run).map((item) => `${item.key}:${item.state}`);

  addCase('步骤条：复杂调查待物业审批', 'fixture', () => {
    const run = complexRun({
      report: {
        ...complexRun().report,
        approval_status: 'pending_approval',
        approval_request: {
          request_id: 'apr_x', status: 'pending', draft_version: 2, amount: '700.00', currency: 'CNY',
          stages: [
            { role: 'property_manager', seq: 1, status: 'pending' },
            { role: 'finance', seq: 2, status: 'pending' },
          ],
        },
      },
    });
    return [
      equal(stepStates(run), [
        'intake:done', 'dispatch:done', 'verify:warning', 'report:done',
        'stage:property_manager:current', 'stage:finance:waiting', 'archive:waiting',
      ], '只有物业审批是当前步骤'),
      equal(cs.nextActionModel(run).text, '等待物业管理部门审批', '下一步'),
    ];
  });

  addCase('步骤条：两级批准后归档', 'fixture', () => {
    const run = complexRun({
      status: 'completed',
      report: {
        ...complexRun().report,
        approval_status: 'approved',
        approved_draft: { status: 'approved_draft_only', executed_side_effects: [] },
        approval_request: {
          request_id: 'apr_x', status: 'approved', draft_version: 2,
          stages: [
            { role: 'property_manager', seq: 1, status: 'approved', decided_by: 'principal_property_manager_xinghui' },
            { role: 'finance', seq: 2, status: 'approved', decided_by: 'principal_finance_xinghui' },
          ],
        },
      },
    });
    const steps = cs.progressModel(run, { meta: { principals: { principal_finance_xinghui: { label: '星汇广场财务部门审批人（合成）' } } } });
    return [
      equal(steps.slice(4).map((item) => item.state), ['done', 'done', 'done'], '两级批准 + 归档'),
      equal(steps[5].detail, '已批准 · 星汇广场财务部门审批人（合成）', '审批人显示中文角色名'),
      equal(cs.nextActionModel(run).text, '已归档（草案，未执行调账）', '归档不等于已调账'),
    ];
  });

  addCase('步骤条：物业驳回后财务与归档未进行', 'fixture', () => {
    const run = complexRun({
      status: 'completed',
      report: {
        ...complexRun().report,
        approval_status: 'rejected',
        approval_request: {
          request_id: 'apr_x', status: 'rejected', draft_version: 2,
          stages: [
            { role: 'property_manager', seq: 1, status: 'rejected', decided_by: 'principal_property_manager_xinghui' },
            { role: 'finance', seq: 2, status: 'pending' },
          ],
        },
      },
    });
    return [
      equal(stepStates(run).slice(4), ['stage:property_manager:failed', 'stage:finance:skipped', 'archive:skipped'], '驳回位置明确'),
      equal(cs.nextActionModel(run).tone, 'failed', '下一步为驳回提示'),
    ];
  });

  addCase('步骤条：简单查询无审批显示本次不涉及', 'fixture', () => {
    const run = {
      run_id: 'run_simple', status: 'completed',
      report: {
        verdict: 'supported', route: 'deterministic', completeness: 'complete',
        findings: [BILLING_FINDING], conflicts: [], missing_information: [], failures: [],
        narrative_discrepancies: [], requires_human_review: false, approval_status: 'not_required',
        agent_results: [{ subtask_id: 'st_1_billing', capability: 'billing.statement', agent: 'billing', status: 'success' }],
      },
    };
    return [
      equal(stepStates(run), [
        'intake:done', 'dispatch:done', 'verify:done', 'report:done',
        'stage:property_manager:not_involved', 'stage:finance:not_involved', 'archive:not_involved',
      ], '审批相关步骤为本次不涉及'),
    ];
  });

  addCase('步骤条：report.error 与预算耗尽不显示已完成', 'fixture', () => {
    const error = stepStates(reportErrorRun());
    const budget = stepStates(budgetFailureRun());
    return [
      equal(error, ['intake:done', 'dispatch:failed', 'verify:skipped', 'report:failed', 'stage:property_manager:skipped', 'stage:finance:skipped', 'archive:skipped'], '报告未生成'),
      equal(budget.slice(1, 3), ['dispatch:warning', 'verify:failed'], '预算耗尽：分派部分失败、核验失败'),
    ];
  });

  addCase('回问运行：API 记为 completed，界面显示需要补充信息', 'fixture', () => {
    const run = {
      run_id: 'run_clarify', status: 'completed', verdict: 'needs_clarification',
      report: {
        verdict: 'needs_clarification', route: 'clarification', completeness: 'not_executed',
        findings: [], conflicts: [], missing_information: [], failures: [], narrative_discrepancies: [],
        agent_results: [], requires_human_review: true, approval_status: 'not_required',
        clarification: { reason: 'no_domain_matched', question: '请说明要核实的是哪一类' },
      },
    };
    const meta = vm.runStatusMeta(run.status, { verdict: run.report.verdict });
    return [
      equal([meta.state, meta.label], ['warning', '需要补充信息'], '不是“已完成”'),
      equal(stepStates(run).slice(1, 3), ['dispatch:warning', 'verify:not_involved'], '步骤条停在分派'),
      equal(vm.buildGraphModel(run).nodes.plan.label, '需要补充信息', '规划节点不显示英文路由'),
      equal(states(run).verify, 'not_called', '核验节点未执行'),
    ];
  });

  addCase('运行状态：审批结束不显示笼统的“已完成”', 'fixture', () => [
    equal(vm.runStatusMeta('completed', { approvalStatus: 'rejected' }).label, '已驳回', '驳回'),
    equal(vm.runStatusMeta('completed', { approvalStatus: 'approved' }).label, '已批准（草案）', '批准仅为草案'),
    equal(vm.runStatusMeta('completed', { verdict: 'supported', approvalStatus: 'not_required' }).label, '已完成', '无审批且结论 supported 时为已完成'),
    equal(vm.runStatusMeta('completed', { approvalStatus: 'not_required' }).label, '已完成 · 需复核', '返修复查 P3-3：结论缺失不显示绿色'),
    equal(vm.runStatusMeta('completed', { verdict: '  ' }).state, 'warning', '返修复查 P3-3：结论为空串不显示绿色'),
    equal(vm.runStatusMeta('completed', { verdict: 'supported' }).state, 'success', 'supported 才是绿色已完成'),
    equal(
      [vm.runStatusMeta('completed', { verdict: 'conflicting' }).state, vm.runStatusMeta('completed', { verdict: 'conflicting' }).label],
      ['warning', '已完成 · 存在冲突'],
      '复查 P3-2：completed + conflicting 不是绿色',
    ),
    equal(vm.runStatusMeta('completed', { verdict: 'insufficient' }).label, '已完成 · 证据不足', 'completed + insufficient'),
    equal(vm.runStatusMeta('completed', { verdict: 'weird' }).state, 'warning', '未知结论不显示绿色'),
    equal(vm.runStatusMeta('completed', { verdict: 'conflicting', approvalStatus: 'approved' }).label, '已批准（草案）', '审批结论优先'),
  ]);

  addCase('结论卡：有领域失败时不宣称“未发现金额差异”', 'fixture', () => {
    const cards = cs.conclusionCards(budgetFailureRun());
    return [
      equal([cards[1].tone, cards[1].value], ['unknown', '待核实'], '账单查询失败 → 金额待核实'),
      equal(cards[0].tone, 'failed', '争议结论为失败'),
    ];
  });

  addCase('结论卡：回问运行不显示绿色“无差额 / 无缺口”', 'fixture', () => {
    const run = {
      run_id: 'run_clarify', status: 'completed',
      report: {
        verdict: 'needs_clarification', route: 'clarification', completeness: 'not_executed',
        findings: [], conflicts: [], missing_information: [], failures: [], narrative_discrepancies: [],
        agent_results: [], requires_human_review: true, approval_status: 'not_required',
      },
    };
    const cards = cs.conclusionCards(run);
    return [
      equal(cards.map((card) => card.tone), ['warning', 'idle', 'idle', 'warning'], '没有任何绿色结论'),
      equal([cards[1].value, cards[2].value], ['未执行调查', '未执行调查'], '金额与缺口都写“未执行调查”'),
      equal(cards[0].note.includes('人工复核'), false, '回问不提示人工复核'),
    ];
  });

  addCase('结论卡：差额与草案金额分开，不暗示因果', 'fixture', () => {
    const run = complexRun({
      display: { records: { inv_2026_08: { kind: 'invoice', period_start: '2026-08-01' } } },
      report: {
        ...complexRun().report,
        proposed_draft: { amount: '700.00', currency: 'CNY', computed_variance: '756.00' },
      },
    });
    const cards = cs.conclusionCards(run);
    const amount = cards[1];
    return [
      equal(cards.map((card) => card.key), ['verdict', 'amount', 'gaps', 'next'], '四张卡'),
      equal(amount.value, '+¥756.00', '差额取自冲突结构化字段'),
      equal(amount.label, '账单多计', '方向文字'),
      equal(amount.note.includes('涉及账期 2026-08'), true, '账期来自展示元数据'),
      equal(amount.draft, '预设草案金额 ¥700.00，非计算结论', '草案金额单独标注'),
      equal(amount.value.includes('700'), false, '差额卡主数字不含草案金额'),
      equal(cards[2].value, '1 项', '资料缺口数量'),
    ];
  });

  return cases;
}

/* ------------------------------------------------------- 真实 API 用例 */

export function buildRealCases(realRuns) {
  if (!realRuns || !realRuns.runs) return [];
  const cases = [];

  const complex = realRuns.runs.complex_approval;
  if (complex && complex.report) {
    cases.push({
      name: '真实 API：A-301 复杂调查',
      source: 'real',
      fn: () => {
        const index = vm.buildSubtaskIndex(complex);
        const attribution = vm.findingsAttribution(complex);
        const rows = vm.traceRows(complex, index);
        return [
          equal(index.counts.failures, 0, '无当前失败'),
          equal(index.counts.subtasks, (complex.report.agent_results || []).length, '子任务计数等于结果数'),
          equal(
            ['lease', 'billing', 'property'].map((key) => stateOf(complex, `agent:${key}`)),
            ['success', 'partial', 'partial'],
            '三个领域都参与（不是未调用）',
          ),
          equal(
            [attribution.byAgent.lease.length, attribution.byAgent.billing.length, attribution.byAgent.property.length],
            [4, 1, 1],
            '发现归属：租约 1 + 条款 3、账单 1、工单 1',
          ),
          equal(attribution.total, (complex.report.findings || []).length, '发现总数与报告一致'),
          equal(rows.filter((row) => !row.attributed).length, 0, '全部工具记录都有 Agent 归属'),
          equal(new Set(rows.map((row) => row.subtask)).size, index.counts.subtasks, 'Trace 覆盖全部子任务'),
        ];
      },
    });
  }

  const budget = realRuns.runs.budget_fail;
  if (budget && budget.report) {
    cases.push({
      name: '真实 API：工具预算耗尽',
      source: 'real',
      fn: () => {
        const index = vm.buildSubtaskIndex(budget);
        const failures = (budget.report.failures || []).map((item) => item.subtask_id).sort();
        const failingNodes = failures.map((id) => {
          const record = index.byId.get(id);
          return record && record.agentKey ? stateOf(budget, `agent:${record.agentKey}`) : 'unknown';
        });
        return [
          equal(failures.length > 0, true, '真实返回包含失败子任务'),
          equal(failingNodes.every((state) => state === 'failed'), true, '每个失败子任务的领域节点是失败'),
          equal(index.counts.failures, failures.length, '失败计数与报告一致'),
          equal(index.records.filter((record) => record.failure).every((record) => Boolean(record.failure.error_code)), true, '保留错误码'),
          equal(vm.traceRows(budget, index).filter((row) => !row.attributed).length, 0, 'Trace 全部可归属'),
          equal(leakedErrorCodes(summaryText(budget)), [], '真实预算耗尽运行：摘要页签不出现英文错误码（复查 P2-1）'),
        ];
      },
    });
  }

  return cases;
}

/* --------------------------------------------------------------- 运行器 */

export function runAll(realRuns) {
  const results = [];
  const cases = [...buildCases(), ...buildRealCases(realRuns)];
  for (const testCase of cases) {
    const entry = { name: testCase.name, source: testCase.source, failures: [], assertions: 0 };
    try {
      const assertions = testCase.fn();
      entry.assertions = assertions.length;
      for (const assertion of assertions) {
        if (!assertion.ok) {
          entry.failures.push({ label: assertion.label, actual: assertion.actual, expected: assertion.expected });
        }
      }
    } catch (error) {
      entry.failures.push({ label: 'case threw', actual: String(error && error.stack ? error.stack : error), expected: 'no throw' });
    }
    results.push(entry);
  }
  return {
    cases: results,
    totalCases: results.length,
    failedCases: results.filter((entry) => entry.failures.length > 0).length,
    totalAssertions: results.reduce((sum, entry) => sum + entry.assertions, 0),
    realCases: results.filter((entry) => entry.source === 'real').length,
    fixtureCases: results.filter((entry) => entry.source === 'fixture').length,
  };
}
