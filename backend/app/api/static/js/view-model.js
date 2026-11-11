/**
 * 只读展示映射（Task 027 / 返修 Task 029）
 *
 * 纯函数：把后端实际返回的字段翻译成中文标签与节点状态，不发起请求、不写 DOM、不改事实。
 * 任何字段缺失一律输出「未提供 / 待核实」，不默认成功、不默认 0。
 *
 * 真实性约束：
 * - `run.status = completed` 只表示执行结束，不等于争议已解决；
 * - 一个领域是否参与，由 `report.agent_results`（有终态结果）、`report.failures`（当前未解决失败）
 *   与该子任务的 `traces` 共同判定，不能只看 `agent_results`；
 * - 无法确认终态时不猜成功或失败，标为「信息不足」；
 * - `report.error` 表示报告未生成，规划 / 核验 / 报告不得显示为成功；
 * - 规划 / 核验 / 报告节点没有独立实时事件，按返回结果回顾，不推断耗时或并发时刻。
 */

export const AGENT_DEFS = [
  {
    key: 'lease',
    capability: 'lease.query',
    // 该 Agent 在配置里声明的全部能力（见 app/config/agents/lease.yaml）
    capabilities: ['lease.query', 'lease.renewal_evaluation'],
    agentName: 'lease',
    nodeId: 'agent:lease',
    title: '合同 Agent',
    duty: '租约、条款、版本与来源',
    domain: 'lease',
  },
  {
    key: 'billing',
    capability: 'billing.statement',
    capabilities: ['billing.statement', 'billing.arrears_check'],
    agentName: 'billing',
    nodeId: 'agent:billing',
    title: '账单 Agent',
    duty: '账单、付款、欠费及差异',
    domain: 'billing',
  },
  {
    key: 'property',
    capability: 'property.work_orders',
    capabilities: ['property.work_orders'],
    agentName: 'property',
    nodeId: 'agent:property',
    title: '物业 Agent',
    duty: '维修记录、未关闭工单',
    domain: 'property',
  },
];

/** 全部已知能力 → Agent key（静态表，来自 Agent 配置，不依赖返回顺序） */
const CAPABILITY_AGENTS = new Map(
  AGENT_DEFS.flatMap((definition) =>
    (definition.capabilities || [definition.capability]).map((capability) => [capability, definition.key])),
);

const AGENT_NAMES = new Map(AGENT_DEFS.map((definition) => [definition.agentName, definition.key]));

export const ROLE_LABELS = {
  property_manager: '物业管理部门',
  finance: '财务部门',
};

const RUN_STATUS = {
  completed: { state: 'success', label: '已完成', note: '执行已结束，不代表争议已解决' },
  awaiting_approval: { state: 'warning', label: '待审批', note: '草案等待人工审批，未结案' },
  failed: { state: 'failed', label: '失败', note: '运行未产出可用结论' },
  running: { state: 'pending', label: '调查执行中', note: '等待后端返回结果' },
  pending: { state: 'pending', label: '调查执行中', note: '等待后端返回结果' },
  unknown: { state: 'idle', label: '状态未知', note: '后端未提供可识别的状态' },
};

const VERDICT = {
  supported: { label: '证据一致', note: '证据之间未发现冲突' },
  conflicting: { label: '存在冲突', note: '证据相互矛盾，需人工复核' },
  insufficient: { label: '证据不足', note: '证据不足，不能给出结论' },
};

const APPROVAL_STATUS = {
  not_required: { label: '本次无审批请求', state: 'not_called' },
  unavailable: { label: '审批通道未接入', state: 'warning' },
  ready: { label: '草案已就绪，待发起审批', state: 'warning' },
  pending_approval: { label: '待审批', state: 'pending' },
  pending_next_stage: { label: '待下一级审批', state: 'pending' },
  pending: { label: '待审批', state: 'pending' },
  approved: { label: '已批准（仅草案）', state: 'success' },
  rejected: { label: '已驳回', state: 'failed' },
  expired: { label: '草案已过期', state: 'failed' },
  superseded: { label: '已被新版本替代', state: 'warning' },
  blocked_budget: { label: '预算耗尽，无法发起审批', state: 'failed' },
};

const STAGE_STATUS = {
  pending: { label: '待处理', state: 'pending' },
  approved: { label: '已批准', state: 'success' },
  rejected: { label: '已驳回', state: 'failed' },
};

/**
 * 运行状态（列表 / 详情共用）。
 *
 * `reportError` 为真时（后端把 AgentError 持久化成 `report.error`），
 * 即使 `status` 字段缺失或写成 completed，也不能显示为正常完成。
 */
export function runStatusMeta(status, { reportError = false } = {}) {
  if (reportError) {
    return { raw: status || '', state: 'failed', label: '失败', note: '运行异常，未生成报告' };
  }
  if (!status) return { raw: '', ...RUN_STATUS.unknown };
  return { raw: status, ...(RUN_STATUS[status] || RUN_STATUS.unknown) };
}

/** 运行是否以 `report.error` 结束（报告未生成） */
export function reportErrorOf(run) {
  return (run && run.report && run.report.error) || null;
}


export function verdictMeta(verdict) {
  if (!verdict) return { raw: '', label: '未提供', note: '后端未提供 verdict' };
  const known = VERDICT[verdict];
  if (!known) return { raw: verdict, label: '未识别的结论', note: verdict };
  return { raw: verdict, ...known };
}

export function completenessMeta(completeness) {
  if (completeness === 'complete') return { label: '调查完整', note: '子任务与资料均已返回' };
  if (completeness === 'partial') return { label: '部分完成', note: '存在失败子任务或资料缺口' };
  return { label: '未提供', note: '后端未进入报告阶段' };
}

export function approvalStatusMeta(status) {
  if (!status) return { raw: '', label: '未提供', state: 'idle' };
  return { raw: status, ...(APPROVAL_STATUS[status] || { label: `未识别状态: ${status}`, state: 'warning' }) };
}

/**
 * 列表项上的审批徽章：只在真正进入审批流时显示，
 * `not_required` / `unavailable` 不算审批事件，避免每条记录都挂一个橙色提示。
 */
export function approvalMetaFor(run) {
  const status = run && run.approval_status;
  if (!status) return null;
  if (status === 'not_required' || status === 'unavailable') return null;
  const meta = approvalStatusMeta(status);
  return { state: meta.state, label: meta.label };
}

export function stageStatusMeta(status) {
  return STAGE_STATUS[status] || { label: `未识别状态: ${status || '未提供'}`, state: 'idle' };
}

export function roleLabel(role) {
  return ROLE_LABELS[role] || role || '未提供角色';
}

/* ------------------------------------------------------------------ 工具 */

export function asArray(value) {
  return Array.isArray(value) ? value : [];
}

export function textOr(value, fallback = '未提供') {
  if (value === null || value === undefined) return fallback;
  const text = String(value).trim();
  return text ? text : fallback;
}

export function formatTimestamp(iso) {
  if (!iso) return '未提供';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return String(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatDuration(ms) {
  if (ms === null || ms === undefined || ms === '') return '未提供';
  const value = Number(ms);
  if (!Number.isFinite(value)) return String(ms);
  if (value < 1) return `${value.toFixed(2)} ms`;
  if (value < 1000) return `${value.toFixed(value < 10 ? 2 : 0)} ms`;
  return `${(value / 1000).toFixed(2)} s`;
}

export function shorten(text, max = 80) {
  const value = textOr(text, '');
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

/* -------------------------------------------------------- Agent / 节点 */

/** capability → 领域 Agent key（来自 Agent 定义表，不看数组顺序） */
export function capabilityAgentKey(capability) {
  const value = textOr(capability, '');
  if (!value) return '';
  return CAPABILITY_AGENTS.get(value) || '';
}

/** 结果记录的 agent 字段 → 领域 Agent key（Agent 定义表里的名字） */
export function agentNameKey(agentName) {
  const value = textOr(agentName, '');
  if (!value) return '';
  return AGENT_NAMES.get(value) || '';
}

export function agentDefinitionByKey(key) {
  return AGENT_DEFS.find((item) => item.key === key) || null;
}

const RESULT_STATE = {
  success: 'success',
  partial: 'partial',
  failed: 'failed',
  skipped: 'unknown',
};

const STATE_PRIORITY = ['failed', 'partial', 'unknown', 'success'];

const STATE_LABELS = {
  success: '已完成',
  partial: '部分完成',
  failed: '失败',
  unknown: '信息不足',
  not_called: '本次未调用',
  idle: '等待运行',
};

/**
 * 单次运行里所有子任务的统一索引（Task 029 / U1）。
 *
 * 数据来源按协议实际字段合并，不看数组先后：
 * - `report.agent_results[]`：有终态结果（`subtask_id` / `capability` / `agent` / `status`）；
 * - `report.failures[]`：**当前未解决**的失败（有 `capability`，没有 `agent`）；
 * - `report.resolved_failures[]`：补查后已恢复的历史失败（仅审计）；
 * - `run.traces[]`：工具尝试（`subtask_id` / `tool` / `status` / `attempt`）。
 *
 * Agent 归属只用 `capability` 对照 Agent 定义表；仅凭 Agent 名字段兜底。
 * 既没有 capability 也没有 agent 的记录保持「未知」，不按下标或字符串猜测。
 */
export function buildSubtaskIndex(run) {
  const report = (run && run.report) || {};
  const records = new Map();
  const unattributedTraces = [];

  const ensure = (rawId) => {
    const id = textOr(rawId, '');
    if (!id) return null;
    if (!records.has(id)) {
      records.set(id, {
        subtaskId: id,
        capability: '',
        agentKey: '',
        agentName: '',
        agentBasis: '',
        resultStatus: '',
        failure: null,
        resolvedFailures: [],
        traces: [],
        sources: [],
      });
    }
    return records.get(id);
  };
  const note = (record, source) => {
    if (record && !record.sources.includes(source)) record.sources.push(source);
  };
  const bindAgent = (record) => {
    // 结果记录自带 agent 名字段（协议字段），优先于 capability 推断
    const byName = agentNameKey(record.agentName);
    if (byName) {
      record.agentKey = byName;
      record.agentBasis = 'agent_name';
      return;
    }
    const byCapability = capabilityAgentKey(record.capability);
    if (byCapability) {
      record.agentKey = byCapability;
      record.agentBasis = 'capability';
    }
  };

  for (const item of asArray(report.agent_results)) {
    if (!item || typeof item !== 'object') continue;
    const record = ensure(item.subtask_id);
    if (!record) continue;
    record.capability = record.capability || textOr(item.capability, '');
    record.agentName = record.agentName || textOr(item.agent, '');
    record.resultStatus = textOr(item.status, '');
    bindAgent(record);
    note(record, 'result');
  }

  for (const failure of asArray(report.failures)) {
    if (!failure || typeof failure !== 'object') continue;
    const record = ensure(failure.subtask_id);
    if (!record) continue;
    record.capability = record.capability || textOr(failure.capability, '');
    record.failure = failure;
    bindAgent(record);
    note(record, 'failure');
  }

  for (const failure of asArray(report.resolved_failures)) {
    if (!failure || typeof failure !== 'object') continue;
    const record = ensure(failure.subtask_id);
    if (!record) continue;
    record.capability = record.capability || textOr(failure.capability, '');
    record.resolvedFailures.push(failure);
    bindAgent(record);
    note(record, 'resolved_failure');
  }

  for (const trace of asArray(run && run.traces)) {
    if (!trace || typeof trace !== 'object') continue;
    // 工具记录只能挂到报告里已有的子任务上；不凭 trace 自造子任务记录，
    // 无法关联的原始记录单列，由「调用记录」以「未关联」展示。
    const record = trace.subtask_id ? records.get(String(trace.subtask_id)) : null;
    if (!record) {
      unattributedTraces.push(trace);
      continue;
    }
    record.traces.push(trace);
    note(record, 'trace');
  }

  for (const record of records.values()) {
    record.terminal = resolveTerminalState(record);
    record.toolAttempts = record.traces.length;
  }

  const ordered = [...records.values()].sort((a, b) =>
    String(a.subtaskId).localeCompare(String(b.subtaskId), 'en', { numeric: true }));

  return {
    records: ordered,
    byId: records,
    unattributedTraces,
    counts: {
      subtasks: ordered.length,
      results: ordered.filter((item) => item.sources.includes('result')).length,
      failures: ordered.filter((item) => Boolean(item.failure)).length,
      resolvedFailures: ordered.filter((item) => item.resolvedFailures.length > 0).length,
      traces: ordered.reduce((sum, item) => sum + item.traces.length, 0),
    },
  };
}

/**
 * 单个子任务的终态。有结果就用结果状态；否则当前失败即失败；
 * 只有工具记录或只有历史失败时无法判定终态，返回 `unknown`（不猜）。
 */
function resolveTerminalState(record) {
  const status = record.resultStatus;
  if (status) return RESULT_STATE[status] || 'unknown';
  if (record.failure) return 'failed';
  if (record.traces.length || record.resolvedFailures.length) return 'unknown';
  return 'not_called';
}

function worstState(states) {
  for (const state of STATE_PRIORITY) {
    if (states.includes(state)) return state;
  }
  return 'not_called';
}

/**
 * 该领域在本次运行中的参与情况。
 *
 * 返回的 `subtasks` 保留该领域**所有**子任务（含失败与已恢复的历史失败），
 * 不再只取第一条结果；`state` 按最严重终态聚合。
 */
export function agentParticipation(run, definition, index) {
  const subtaskIndex = index || buildSubtaskIndex(run);
  const records = subtaskIndex.records.filter((record) => record.agentKey === definition.key);
  const unattributedTraces = subtaskIndex.unattributedTraces.length;

  if (!records.length) {
    return {
      participated: false,
      subtasks: [],
      primary: null,
      subtaskId: '',
      state: 'not_called',
      label: STATE_LABELS.not_called,
      rawStatus: '',
      failure: null,
      traces: [],
      unattributedTraces,
    };
  }

  const state = worstState(records.map((record) => record.terminal));
  const failures = records.filter((record) => record.failure);
  let label = STATE_LABELS[state] || state;
  if (state === 'failed' && failures.length === 1) {
    const code = textOr(failures[0].failure && failures[0].failure.error_code, '');
    if (code) label = `失败 · ${code}`;
  }
  const primary = records.find((record) => record.failure) || records[0];
  return {
    participated: true,
    subtasks: records,
    primary,
    subtaskId: primary.subtaskId,
    state,
    label,
    rawStatus: primary.resultStatus || (primary.failure ? 'failed' : ''),
    failure: failures.length === 1 ? failures[0].failure : null,
    failureCount: failures.length,
    traces: records.flatMap((record) => record.traces),
    unattributedTraces,
  };
}

/** 该领域所有子任务的冲突（按 `conflicts[].subtask_id` 精确匹配） */
export function conflictsForAgent(run, definition, index) {
  const subtaskIndex = index || buildSubtaskIndex(run);
  const ids = new Set(
    subtaskIndex.records
      .filter((record) => record.agentKey === definition.key)
      .map((record) => record.subtaskId),
  );
  const report = (run && run.report) || {};
  return asArray(report.conflicts).filter((conflict) => ids.has(textOr(conflict && conflict.subtask_id, '')));
}

/* -------------------------------------------------------------- 证据分组 */

/**
 * 证据 ID 前缀 → 展示分组。
 *
 * 这是**展示分组**，不是后端的分类字段，也不等于 Agent 归属：
 * `documents`（合同文书）与 `work_orders`（工单）分别由合同 / 物业能力产出，
 * 两者到 Agent 的对应关系集中在 `DOMAIN_TO_AGENT` 里定义。
 */
const EVIDENCE_PREFIX_GROUPS = [
  { domain: 'documents', prefixes: ['doc_', 'snip_'] },
  { domain: 'billing', prefixes: ['inv_', 'itm_', 'pay_', 'alloc_'] },
  { domain: 'work_orders', prefixes: ['wo_'] },
  { domain: 'lease', prefixes: ['lease_', 'unit_', 'ten_', 'rule_'] },
];

export const EVIDENCE_GROUPS = [
  { key: 'lease', title: '合同与租约', note: '租约、单元、租户与计费规则引用' },
  { key: 'documents', title: '合同文书与条款', note: '文档 ID、版本、页码与条款' },
  { key: 'billing', title: '账单与付款', note: '账单、账单明细、付款与核销' },
  { key: 'work_orders', title: '物业工单', note: '维修工单与未关闭项' },
  { key: 'unknown', title: '其他 / 未分类证据', note: 'ID 前缀无法归类，原样保留，不并入其他分组' },
];

/**
 * 证据展示分组 → 领域 Agent。（展示推断：合同文书与条款由 `lease.query` 产出，
 * 工单由 `property.work_orders` 产出，账单/付款由 `billing.statement` 产出。）
 */
const DOMAIN_TO_AGENT = {
  lease: 'lease',
  documents: 'lease',
  billing: 'billing',
  work_orders: 'property',
};

/** 具有领域指向性的分组：用于判断 finding 的主要来源域 */
const PRIMARY_DOMAINS = ['documents', 'billing', 'work_orders'];

export function evidenceDomain(id) {
  const value = String(id || '');
  if (!value) return 'unknown';
  const group = EVIDENCE_PREFIX_GROUPS.find((item) =>
    item.prefixes.some((prefix) => value.startsWith(prefix)));
  return group ? group.domain : 'unknown';
}

/**
 * 把报告中的证据引用按分组展开。
 * 条款类证据带上报告里真实存在的 page / clause / 摘录；没有就只给 ID。
 */
export function evidenceModel(run) {
  const report = (run && run.report) || {};
  const findings = asArray(report.findings);
  const conflicts = asArray(report.conflicts);
  const draft = report.proposed_draft || null;
  const request = report.approval_request || null;

  const clauseNotes = new Map();
  for (const finding of findings) {
    const source = finding && finding.source;
    if (!source || !source.document_id) continue;
    const firstId = asArray(finding.evidence_ids)[0];
    const id = firstId || `${source.document_id}#v${source.document_version}#p${source.page}`;
    clauseNotes.set(String(id), {
      documentId: source.document_id,
      version: source.document_version,
      status: source.document_status,
      page: source.page,
      clause: source.clause_id,
      excerpt: textOr(finding.statement, ''),
    });
  }

  const buckets = new Map(EVIDENCE_GROUPS.map((group) => [group.key, []]));
  const seen = new Set();
  const push = (rawId) => {
    const id = textOr(rawId, '');
    if (!id || seen.has(id)) return;
    seen.add(id);
    const domain = evidenceDomain(id);
    const note = clauseNotes.get(id) || null;
    if (!buckets.has(domain)) buckets.set(domain, []);
    buckets.get(domain).push({ id, note, domain });
  };

  for (const finding of findings) asArray(finding.evidence_ids).forEach(push);
  for (const conflict of conflicts) asArray(conflict.evidence_ids).forEach(push);
  if (draft) asArray(draft.evidence_ids).forEach(push);
  if (request) asArray(request.evidence_ids).forEach(push);

  const groups = EVIDENCE_GROUPS.map((group) => ({
    ...group,
    items: buckets.get(group.key) || [],
  })).filter((group) => group.items.length > 0);

  return { groups, total: seen.size };
}

/**
 * 单条 finding 的来源归属（Task 029 / U2）。
 *
 * 判定顺序：
 * 1. 报告自带 `source.document_id` → 合同条款，归 `lease`；
 * 2. 证据分组里有**唯一**领域指向（documents / billing / work_orders）→ 对应 Agent；
 * 3. 有多个领域指向 → `cross_domain`，不归任何单一 Agent，也不复制到各节点；
 * 4. 只有租约核心实体（lease / unit / ten / rule）→ `lease`；
 * 5. 含无法归类前缀、无证据或其它情况 → 未关联，单独展示。
 */
export function attributeFinding(finding) {
  const source = finding && finding.source;
  if (source && source.document_id) {
    return {
      agentKey: 'lease',
      basis: 'source',
      detail: `报告提供的条款来源字段（${textOr(source.document_id, '未提供')}）`,
    };
  }
  const ids = asArray(finding && finding.evidence_ids).map((id) => String(id));
  if (!ids.length) {
    return { agentKey: '', basis: 'no_evidence', detail: '报告未提供 evidence_ids' };
  }
  const domains = new Set(ids.map(evidenceDomain));
  const primary = PRIMARY_DOMAINS.filter((domain) => domains.has(domain));
  if (primary.length === 1) {
    return {
      agentKey: DOMAIN_TO_AGENT[primary[0]],
      basis: 'evidence',
      detail: `引用的证据集中在「${evidenceGroupTitle(primary[0])}」分组`,
    };
  }
  if (primary.length > 1) {
    const agents = [...new Set(primary.map((domain) => DOMAIN_TO_AGENT[domain]))];
    return {
      agentKey: '',
      basis: 'cross_domain',
      agents,
      domains: primary,
      detail: `同时引用 ${primary.map((domain) => evidenceGroupTitle(domain)).join(' / ')}，跨 ${agents.length} 个领域`,
    };
  }
  if (domains.has('unknown')) {
    return { agentKey: '', basis: 'unknown_prefix', detail: '证据 ID 前缀无法归类' };
  }
  if (domains.has('lease')) {
    return { agentKey: 'lease', basis: 'evidence', detail: '仅引用租约核心实体' };
  }
  return { agentKey: '', basis: 'unattributed', detail: '证据无法按分组归类' };
}

export function evidenceGroupTitle(domain) {
  const group = EVIDENCE_GROUPS.find((item) => item.key === domain);
  return group ? group.title : domain;
}

/**
 * 一次运行里所有 finding 的归属结果：按 Agent 分组 + 跨领域 + 未关联。
 * 每条 finding 只出现一次，不为了凑数复制到多个节点。
 */
export function findingsAttribution(run) {
  const report = (run && run.report) || {};
  const byAgent = Object.fromEntries(AGENT_DEFS.map((definition) => [definition.key, []]));
  const crossDomain = [];
  const unassociated = [];

  for (const finding of asArray(report.findings)) {
    if (!finding || typeof finding !== 'object') continue;
    const attribution = attributeFinding(finding);
    if (attribution.agentKey && byAgent[attribution.agentKey]) {
      byAgent[attribution.agentKey].push({ finding, attribution });
    } else if (attribution.basis === 'cross_domain') {
      crossDomain.push({ finding, attribution });
    } else {
      unassociated.push({ finding, attribution });
    }
  }

  return {
    total: asArray(report.findings).length,
    byAgent,
    crossDomain,
    unassociated,
  };
}

export function findingsForAgent(run, definition, attribution) {
  const model = attribution || findingsAttribution(run);
  return (model.byAgent[definition.key] || []).map((entry) => entry.finding);
}


/* ------------------------------------------------------------ 节点模型 */

/** 数组字段的三态：缺失 / 类型无效 / 明确数组（可为空） */
function fieldInfo(value) {
  if (value === undefined || value === null) return { status: 'missing', length: 0 };
  if (Array.isArray(value)) return { status: 'array', length: value.length };
  return { status: 'invalid', length: 0 };
}

function textField(value) {
  if (typeof value !== 'string') return { status: value === undefined || value === null ? 'missing' : 'invalid', value: '' };
  const trimmed = value.trim();
  return { status: trimmed ? 'ok' : 'missing', value: trimmed };
}

function planNode(run, index) {
  if (!run || !run.report) return { state: 'idle', label: '等待运行' };
  const report = run.report;
  if (report.error) {
    return { state: 'unknown', label: '规划信息未提供', note: '报告未生成（运行异常），无法回顾规划结果' };
  }
  const counts = index.counts;
  const route = textField(report.route);
  if (route.status !== 'ok') {
    return {
      state: 'unknown',
      label: '规划信息未提供',
      note: '报告未提供可用的 route 字段',
      ...counts,
    };
  }
  const label = route.value === 'deterministic' ? '单领域'
    : route.value === 'fanout' ? '多领域分流'
      : `路由 ${route.value}`;
  return { state: 'success', label, route: route.value, ...counts };
}

function sinkBasics(run, index) {
  const report = (run && run.report) || {};
  return {
    verdict: textOr(report.verdict, ''),
    completeness: textOr(report.completeness, ''),
    conflicts: asArray(report.conflicts).length,
    missing: asArray(report.missing_information).length,
    failures: index.counts.failures,
    discrepancies: asArray(report.narrative_discrepancies).length,
  };
}

function verifyNode(run, index) {
  if (!run || !run.report) return { state: 'idle', label: '等待运行' };
  const report = run.report;
  if (report.error) {
    return { state: 'unknown', label: '核验信息未提供', note: '报告未生成（运行异常），无法核验' };
  }

  const verdict = textField(report.verdict);
  const conflicts = fieldInfo(report.conflicts);
  const missing = fieldInfo(report.missing_information);
  const failures = fieldInfo(report.failures);
  const discrepancies = fieldInfo(report.narrative_discrepancies);

  const incomplete = [];
  if (verdict.status !== 'ok' || !VERDICT[verdict.value]) incomplete.push('verdict');
  if (conflicts.status !== 'array') incomplete.push('conflicts');
  if (missing.status !== 'array') incomplete.push('missing_information');
  if (incomplete.length) {
    return {
      state: 'unknown',
      label: '核验字段不完整',
      note: `缺少或类型异常：${incomplete.join('、')}；不能据此宣称未发现冲突`,
      incomplete,
    };
  }

  const basics = sinkBasics(run, index);
  if (failures.status === 'array' && failures.length > 0) {
    return { state: 'failed', label: `存在失败子任务 · ${failures.length} 个`, ...basics };
  }
  if (discrepancies.status === 'array' && discrepancies.length > 0) {
    return { state: 'partial', label: '叙述与字段不一致', ...basics };
  }
  if (basics.verdict === 'conflicting') {
    return { state: 'partial', label: '发现冲突 · 需复核', ...basics };
  }
  if (basics.verdict === 'insufficient') {
    return { state: 'partial', label: '证据不足 · 需复核', ...basics };
  }
  if (basics.missing > 0) {
    return { state: 'partial', label: '存在资料缺口', ...basics };
  }

  const completeness = textField(report.completeness);
  if (completeness.status !== 'ok') {
    return { state: 'unknown', label: '完整度未提供', note: '报告未提供 completeness，无法确认调查是否完整', ...basics };
  }
  if (completeness.value !== 'complete') {
    return { state: 'partial', label: '调查未完整但未发现冲突', ...basics };
  }
  if (report.requires_human_review === true) {
    return { state: 'partial', label: '未发现冲突 · 需人工复核', ...basics };
  }
  if (report.requires_human_review === undefined) {
    return { state: 'unknown', label: '复核标记未提供', note: '报告未提供 requires_human_review', ...basics };
  }
  return { state: 'success', label: '证据核验通过', ...basics };
}

function reportNode(run) {
  if (!run || !run.report) return { state: 'idle', label: '等待运行' };
  const report = run.report;
  if (report.error) {
    const code = textOr(report.error.code, '未提供错误码');
    return {
      state: 'failed',
      label: '报告未生成',
      note: `运行异常：${code}`,
      error: report.error,
      findings: 0,
      warnings: 0,
      disclaimer: '',
    };
  }
  const findings = fieldInfo(report.findings);
  const verdict = textField(report.verdict);
  const base = {
    findings: findings.status === 'array' ? findings.length : 0,
    warnings: asArray(report.warnings).length,
    disclaimer: textOr(report.disclaimer, ''),
  };
  if (verdict.status !== 'ok' || !VERDICT[verdict.value]) {
    return { state: 'unknown', label: '报告字段不完整', note: '报告未提供可用的 verdict', ...base };
  }
  if (findings.status !== 'array') {
    return {
      state: 'unknown',
      label: '报告字段不完整',
      note: `findings ${findings.status === 'missing' ? '未提供' : '类型异常'}`,
      ...base,
    };
  }
  if (verdict.value === 'insufficient') {
    // 报告文档生成成功，但结论未被证据支持：不能给绿灯
    return { state: 'partial', label: '报告已生成 · 证据不足', note: '结论未获证据支持，需人工复核', ...base };
  }
  if (verdict.value === 'conflicting') {
    return { state: 'partial', label: '报告已生成 · 存在冲突', note: '冲突并列呈现，需人工复核', ...base };
  }
  if (report.requires_human_review === true) {
    return { state: 'partial', label: '报告已生成 · 需人工复核', ...base };
  }
  if (report.requires_human_review === undefined) {
    return { state: 'unknown', label: '报告已生成 · 复核标记未提供', note: '报告未提供 requires_human_review', ...base };
  }
  return { state: 'success', label: '报告已生成 · 证据一致', ...base };
}

function approvalNode(run) {
  if (!run) return { state: 'idle', label: '等待运行' };
  const report = run.report || {};
  const request = report.approval_request || null;
  const status = textOr(report.approval_status, textOr(run.approval_status, ''));
  if (!request) {
    const meta = approvalStatusMeta(status);
    if (report.error) {
      return { state: 'unknown', label: '审批状态未提供', status, request: null, note: '报告未生成（运行异常）' };
    }
    if (status === 'unavailable') {
      return { state: 'warning', label: '审批通道未接入', status, request: null };
    }
    if (status === 'not_required' || !status) {
      return { state: 'not_called', label: '本次无审批请求', status, request: null };
    }
    return { state: meta.state, label: meta.label, status, request: null };
  }
  const meta = approvalStatusMeta(request.status === 'pending' && status === 'pending_next_stage'
    ? 'pending_next_stage'
    : request.status);
  return { state: meta.state, label: meta.label, status, request };
}

/** 画布节点状态：idle / pending / success / partial / failed / unknown / not_called */
export function buildGraphModel(run) {
  if (!run) {
    return {
      pending: false,
      nodes: {
        plan: { state: 'idle', label: '等待运行' },
        'agent:lease': { state: 'idle', label: '等待运行' },
        'agent:billing': { state: 'idle', label: '等待运行' },
        'agent:property': { state: 'idle', label: '等待运行' },
        verify: { state: 'idle', label: '等待运行' },
        report: { state: 'idle', label: '等待运行' },
        approval: { state: 'idle', label: '等待运行' },
      },
    };
  }
  const index = buildSubtaskIndex(run);
  const nodes = {
    plan: planNode(run, index),
    verify: verifyNode(run, index),
    report: reportNode(run),
    approval: approvalNode(run),
  };
  for (const definition of AGENT_DEFS) {
    const participation = agentParticipation(run, definition, index);
    nodes[definition.nodeId] = {
      state: participation.state,
      label: participation.label,
      subtaskId: participation.subtaskId,
      rawStatus: participation.rawStatus,
      subtaskIds: participation.subtasks.map((record) => record.subtaskId),
      failureCount: participation.failureCount || 0,
    };
  }
  return { pending: false, nodes };
}


/** 请求未完成时的统一等待态：所有节点「状态待返回」，不伪造逐节点进度 */
export function buildPendingGraphModel() {
  const nodes = {
    plan: { state: 'pending', label: '状态待返回' },
    verify: { state: 'pending', label: '状态待返回' },
    report: { state: 'pending', label: '状态待返回' },
    approval: { state: 'pending', label: '状态待返回' },
  };
  for (const definition of AGENT_DEFS) {
    nodes[definition.nodeId] = { state: 'pending', label: '状态待返回' };
  }
  return { pending: true, nodes };
}

/* ------------------------------------------------------------- 审批视图 */

export function approvalModel(run) {
  const report = (run && run.report) || {};
  const request = report.approval_request || null;
  const approvalStatus = textOr(report.approval_status, textOr(run && run.approval_status, ''));
  const statusMeta = approvalStatusMeta(approvalStatus);
  const draft = report.proposed_draft || null;
  const approvedDraft = report.approved_draft || null;

  const stages = asArray(request && request.stages)
    .slice()
    .sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0))
    .map((stage) => {
      const meta = stageStatusMeta(stage.status);
      return {
        seq: stage.seq,
        role: textOr(stage.role, ''),
        roleLabel: roleLabel(stage.role),
        status: textOr(stage.status, ''),
        statusLabel: meta.label,
        state: meta.state,
        decidedBy: textOr(stage.decided_by, ''),
        decidedAt: textOr(stage.decided_at, ''),
        reason: textOr(stage.reason, ''),
      };
    });

  const nextStage = stages.find((stage) => stage.status === 'pending') || null;
  const canDecide = Boolean(request) && textOr(request.status, '') === 'pending';

  return {
    hasRequest: Boolean(request),
    approvalStatus,
    statusMeta,
    request,
    stages,
    nextStage,
    canDecide,
    draft,
    approvedDraft,
    variance: draft ? textOr(draft.computed_variance, '') : '',
    requestStatus: request ? textOr(request.status, '') : '',
    warnings: asArray(report.approval_warnings),
  };
}

/** 服务端白名单里与该阶段角色匹配的审批人（仅做预选，权限仍由服务端判定） */
export function actorForStage(allowlist, stage) {
  const actors = asArray(allowlist).map((item) => String(item));
  if (!stage || !stage.role) return actors[0] || '';
  const needle = stage.role;
  const match = actors.find((actor) => actor.includes(needle));
  return match || actors[0] || '';
}

/* --------------------------------------------------------- 调用记录表 */

/**
 * Trace 行。Agent / 能力归属来自子任务索引（`subtask_id` → capability → Agent），
 * 不看结果数组顺序；索引里没有该子任务时标为「未关联」并保留原始记录。
 */
export function traceRows(run, index) {
  const subtaskIndex = index || buildSubtaskIndex(run);
  return asArray(run && run.traces).map((trace, position) => {
    const subtask = textOr(trace && trace.subtask_id, '');
    const record = subtask ? subtaskIndex.byId.get(subtask) || null : null;
    const definition = record && record.agentKey ? agentDefinitionByKey(record.agentKey) : null;
    return {
      index: position + 1,
      subtask,
      agent: definition ? definition.key : '',
      agentLabel: definition ? definition.title : '未关联',
      attributed: Boolean(definition),
      capability: record ? record.capability : '',
      subtaskState: record ? record.terminal : 'unknown',
      tool: textOr(trace && trace.tool, '未提供'),
      status: textOr(trace && trace.status, '未提供'),
      attempt: trace && trace.attempt !== undefined ? String(trace.attempt) : '未提供',
      duration: formatDuration(trace && trace.duration_ms),
      runId: textOr(trace && trace.run_id, ''),
    };
  });
}

/* ------------------------------------------------------------- 历史筛选 */

export function filterRuns(runs, { query = '', status = 'all' } = {}) {
  const needle = String(query || '').trim().toLowerCase();
  return asArray(runs).filter((run) => {
    if (status !== 'all' && String(run.status) !== status) return false;
    if (!needle) return true;
    const haystack = [run.question, run.run_id, run.lease_id]
      .map((value) => String(value || '').toLowerCase())
      .join(' ');
    return haystack.includes(needle);
  });
}

/* --------------------------------------------------------------- 概况 */

export function summaryModel(run) {
  if (!run) {
    return {
      status: { state: 'idle', label: '等待运行', note: '尚未选择运行' },
      verdict: { value: '—', note: 'verdict / completeness', tone: '' },
      conflicts: { value: '—', note: '待结果返回后统计', tone: '' },
      approval: { value: '—', note: '等待运行', tone: '' },
    };
  }
  const report = run.report || {};
  const statusMeta = runStatusMeta(run.status, { reportError: Boolean(report.error) });
  if (report.error) {
    return {
      status: { state: statusMeta.state, label: statusMeta.label, note: statusMeta.note },
      verdict: { value: '未产出结论', note: 'report.error', tone: 'is-danger' },
      conflicts: { value: '—', note: '报告未生成', tone: 'is-danger' },
      approval: { value: '—', note: '报告未生成，无审批记录', tone: '' },
    };
  }
  const verdict = verdictMeta(report.verdict);

  const completeness = completenessMeta(report.completeness);
  const conflicts = asArray(report.conflicts).length;
  const missing = asArray(report.missing_information).length;
  const failures = asArray(report.failures).length;
  const approval = approvalModel(run);

  let conflictTone = '';
  if (failures > 0) conflictTone = 'is-danger';
  else if (conflicts > 0 || missing > 0) conflictTone = 'is-warn';

  const requestOpen = approval.hasRequest && approval.requestStatus === 'pending';
  const approvalNote = approval.hasRequest
    ? [
      `request ${approval.requestStatus || '未提供'}`,
      requestOpen && approval.nextStage
        ? `下一级：${approval.nextStage.roleLabel}`
        : '无待处理阶段',
    ].join(' · ')
    : (approval.approvalStatus || '后端未提供 approval_status');

  return {
    status: {
      state: statusMeta.state,
      label: statusMeta.label,
      note: statusMeta.note,
    },
    verdict: {
      value: verdict.label,
      note: `${report.verdict ? report.verdict : '未提供'} · ${completeness.label}`,
      tone: report.verdict === 'conflicting' ? 'is-warn' : '',
    },
    conflicts: {
      value: `${conflicts} 冲突 · ${missing} 缺口`,
      note: failures > 0 ? `${failures} 个子任务失败` : '来自报告 conflicts / missing_information',
      tone: conflictTone,
    },
    approval: {
      value: approval.statusMeta.label,
      note: approvalNote,
      tone: ''
    },
  };
}
