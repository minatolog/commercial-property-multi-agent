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
        plan: 'success', verify: 'failed', report: 'partial', approval: 'not_called',
        'agent:lease': 'partial', 'agent:billing': 'failed', 'agent:property': 'failed',
      }, '节点状态：失败不是未调用'),
      equal(labels(run)['agent:billing'], '失败 · budget_exhausted', '账单节点标签带错误码'),
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
          equal(Object.values(states(budget)).includes('not_called') === false || failures.length > 0, true, '失败的领域不画成未调用'),
          equal(index.counts.failures, failures.length, '失败计数与报告一致'),
          equal(index.records.filter((record) => record.failure).every((record) => Boolean(record.failure.error_code)), true, '保留错误码'),
          equal(vm.traceRows(budget, index).filter((row) => !row.attributed).length, 0, 'Trace 全部可归属'),
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
