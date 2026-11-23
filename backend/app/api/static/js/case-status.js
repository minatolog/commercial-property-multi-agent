/**
 * 案件状态解释（Task 032）
 *
 * 一处定义、多处复用：核验节点、报告节点、结论卡、流程步骤条、摘要都从这里取结论，
 * 不允许各写一套判断（U3-B）。
 *
 * 真实性规则：
 * - 必需字段缺失或类型异常 → “待核实 / 未知”，不能默认成功或 0（U3-A：布尔字段必须真的是 boolean）；
 * - 区分“报告文档已生成”与“结论可信”：有失败、冲突、叙述差异、资料缺口或字段无效时，不能显示“证据一致”；
 * - 步骤状态只从真实字段推导；推导不出就是“未知”，没走到的是“本次不涉及 / 未进行”。
 */

import { term, describeMissingItem } from './i18n.js';
import { formatVariance, formatMoney, formatPeriod } from './format.js';

const KNOWN_VERDICTS = new Set(['supported', 'conflicting', 'insufficient', 'needs_clarification']);

function arrayField(value) {
  if (value === undefined || value === null) return { status: 'missing', items: [] };
  if (Array.isArray(value)) return { status: 'array', items: value };
  return { status: 'invalid', items: [] };
}

function stringField(value) {
  if (value === undefined || value === null) return { status: 'missing', value: '' };
  if (typeof value !== 'string') return { status: 'invalid', value: '' };
  const trimmed = value.trim();
  return { status: trimmed ? 'ok' : 'missing', value: trimmed };
}

/**
 * 核验解释。返回：
 * - `state`：success / partial / failed / unknown / warning（需要补充信息）/ idle；
 * - `label`：核验节点文案；`reportLabel`：报告节点文案（同一判断，不同措辞）；
 * - `headline`：结论卡与摘要用的业务短句；
 * - `incomplete`：缺失或类型异常的字段名；`reportGenerated`：报告文档是否生成。
 */
export function interpretVerification(run) {
  if (!run || !run.report) {
    return { state: 'idle', label: '等待运行', reportLabel: '等待运行', headline: '尚未运行', incomplete: [], reportGenerated: false };
  }
  const report = run.report;
  if (report.error) {
    const code = term('errorCode', report.error && report.error.code, { missing: '未提供错误码' });
    return {
      state: 'failed',
      verifyState: 'unknown',
      label: '核验信息未提供',
      reportLabel: '报告未生成',
      headline: `调查失败：${code}`,
      note: '运行异常，报告未生成，无法核验',
      incomplete: [],
      reportGenerated: false,
      error: report.error,
    };
  }

  const verdict = stringField(report.verdict);
  if (verdict.value === 'needs_clarification') {
    return {
      state: 'warning',
      label: '未执行核验 · 需要补充信息',
      reportLabel: '未生成调查报告 · 需要补充信息',
      headline: '需要补充信息：未执行调查',
      note: '问题无法确定要查哪一类事项，本次没有调用任何工具',
      incomplete: [],
      reportGenerated: false,
      clarification: true,
    };
  }

  const conflicts = arrayField(report.conflicts);
  const missing = arrayField(report.missing_information);
  const failures = arrayField(report.failures);
  const discrepancies = arrayField(report.narrative_discrepancies);
  const findings = arrayField(report.findings);

  const incomplete = [];
  if (verdict.status !== 'ok' || !KNOWN_VERDICTS.has(verdict.value)) incomplete.push('verdict');
  if (conflicts.status !== 'array') incomplete.push('conflicts');
  if (missing.status !== 'array') incomplete.push('missing_information');
  if (failures.status !== 'array') incomplete.push('failures');
  if (discrepancies.status !== 'array') incomplete.push('narrative_discrepancies');

  const counts = {
    conflicts: conflicts.items.length,
    missing: missing.items.length,
    failures: failures.items.length,
    discrepancies: discrepancies.items.length,
    findings: findings.items.length,
  };
  const base = { incomplete, counts, verdict: verdict.value, reportGenerated: findings.status === 'array' };

  if (incomplete.length) {
    return {
      ...base,
      state: 'unknown',
      label: '核验字段不完整',
      reportLabel: '报告字段不完整',
      headline: '结论待核实：报告字段不完整',
      note: `缺少或类型异常：${incomplete.join('、')}；不能据此宣称未发现冲突`,
    };
  }
  if (findings.status !== 'array') {
    return {
      ...base,
      state: 'unknown',
      label: '核验字段不完整',
      reportLabel: '报告字段不完整',
      headline: '结论待核实：报告字段不完整',
      note: `findings ${findings.status === 'missing' ? '未提供' : '类型异常'}`,
      incomplete: ['findings'],
    };
  }

  const make = (state, label, reportLabel, headline, note) => ({
    ...base, state, label, reportLabel, headline, note,
  });

  if (counts.failures > 0) {
    return make('failed', `存在失败子任务 · ${counts.failures} 个`, '报告已生成 · 存在失败子任务',
      `调查不完整：${counts.failures} 个领域查询失败`, '失败领域的结论缺失，需排查后重新调查');
  }
  if (counts.discrepancies > 0) {
    return make('partial', '叙述与字段不一致', '报告已生成 · 叙述与字段不一致',
      '需复核：模型叙述与工具字段不一致', '以结构化字段为准，叙述需人工核对');
  }
  if (verdict.value === 'conflicting' || counts.conflicts > 0) {
    return make('partial', '发现冲突 · 需复核', '报告已生成 · 存在冲突',
      `存在冲突：${conflictHeadline(report)}`, '冲突并列呈现，需人工复核');
  }
  if (verdict.value === 'insufficient') {
    return make('partial', '证据不足 · 需复核', '报告已生成 · 证据不足',
      '证据不足：结论未获证据支持', '需补充资料或人工复核');
  }
  if (counts.missing > 0) {
    return make('partial', '存在资料缺口', '报告已生成 · 存在资料缺口',
      `存在资料缺口：${counts.missing} 项`, '缺失资料可能影响结论');
  }
  const completeness = stringField(report.completeness);
  if (completeness.status !== 'ok') {
    return make('unknown', '完整度未提供', '报告已生成 · 完整度待核实',
      '结论待核实：完整度未提供', '报告未提供 completeness，无法确认调查是否完整');
  }
  if (completeness.value !== 'complete') {
    return make('partial', '调查未完整但未发现冲突', '报告已生成 · 调查未完整',
      '调查未完整：未发现冲突', '部分子任务未完成，不能视为结论成立');
  }
  if (report.requires_human_review === true) {
    return make('partial', '未发现冲突 · 需人工复核', '报告已生成 · 需人工复核',
      '未发现冲突：仍需人工复核', '后端要求人工复核');
  }
  if (report.requires_human_review !== false) {
    // U3-A：null / "true" / 1 / 缺失都不是 false，不能当作“无需复核”
    return make('unknown', '复核标记待核实', '报告已生成 · 复核标记待核实',
      '结论待核实：复核标记缺失或类型异常', 'requires_human_review 必须是布尔值');
  }
  return make('success', '证据核验通过', '报告已生成 · 证据一致',
    '证据一致：未发现冲突', '各领域证据之间未发现冲突');
}

function conflictHeadline(report) {
  const conflicts = arrayField(report.conflicts).items.filter((item) => item && typeof item === 'object');
  if (!conflicts.length) return '报告结论为存在冲突';
  const first = conflicts[0];
  const text = term('conflictType', first.type, { missing: '冲突类型未提供' });
  return conflicts.length > 1 ? `${text}等 ${conflicts.length} 项` : text;
}

/* ------------------------------------------------------------ 显示信息 */

export function displayOf(run) {
  const display = (run && run.display && typeof run.display === 'object') ? run.display : {};
  const records = display.records && typeof display.records === 'object' ? display.records : {};
  return { lease: display.lease || null, records };
}

/** 案件名：`云端咖啡（合成租户）· A-301`；缺失时用中性描述，不显示 ID */
export function caseTitle(run, summaryDisplay) {
  const lease = (summaryDisplay !== undefined ? summaryDisplay : displayOf(run).lease) || null;
  const tenant = lease && lease.tenant_name;
  const unit = lease && lease.unit_code;
  if (tenant && unit) return `${tenant} · ${unit}`;
  if (unit) return `铺位 ${unit}（租户名称未提供）`;
  if (tenant) return `${tenant}（铺位未提供）`;
  return '租户与铺位信息未提供';
}

/** 案件类型：有冲突取冲突类型；否则按参与领域 */
export function caseIssueType(run) {
  const report = (run && run.report) || {};
  const conflicts = arrayField(report.conflicts).items.filter((item) => item && typeof item === 'object');
  if (conflicts.length) return term('conflictShort', conflicts[0].type, { missing: '争议' });
  if (report.verdict === 'needs_clarification') return '待明确的咨询';
  const domains = arrayField(report.routing_reason).items
    .map((item) => item && item.domain)
    .filter(Boolean);
  if (domains.length === 1) return `${term('domain', domains[0])}查询`;
  if (domains.length > 1) return '跨系统调查';
  return '调查';
}

/* ------------------------------------------------------------ 流程步骤 */

export const STEP_DEFS = [
  { key: 'intake', title: '受理' },
  { key: 'dispatch', title: '分派调查' },
  { key: 'verify', title: '证据核验' },
  { key: 'report', title: '形成报告' },
  { key: 'stage:property_manager', title: '物业审批', role: 'property_manager' },
  { key: 'stage:finance', title: '财务审批', role: 'finance' },
  { key: 'archive', title: '草案归档' },
];

/** 步骤状态：done / current / waiting / warning / failed / unknown / not_involved / skipped */
function step(def, state, detail) {
  return { key: def.key, title: def.title, state, detail };
}

function stageInfo(request, role) {
  if (!request || !Array.isArray(request.stages)) return null;
  return request.stages.find((stage) => stage && stage.role === role) || null;
}

export function progressModel(run, { meta = null } = {}) {
  if (!run) return STEP_DEFS.map((def) => step(def, 'waiting', '尚未选择案件'));
  const report = run.report || null;
  const interp = interpretVerification(run);
  const principals = (meta && meta.principals) || {};
  const out = [];
  const [intake, dispatch, verify, reportDef, pmDef, finDef, archiveDef] = STEP_DEFS;

  out.push(step(intake, run.run_id ? 'done' : 'unknown', run.run_id ? '已受理' : '受理信息未提供'));

  if (!report) {
    STEP_DEFS.slice(1).forEach((def) => out.push(step(def, 'unknown', '后端未返回报告')));
    return out;
  }
  if (report.error) {
    out.push(step(dispatch, 'failed', `调查失败：${term('errorCode', report.error.code, { missing: '未提供错误码' })}`));
    out.push(step(verify, 'skipped', '未进行'));
    out.push(step(reportDef, 'failed', '报告未生成'));
    [pmDef, finDef, archiveDef].forEach((def) => out.push(step(def, 'skipped', '未进行')));
    return out;
  }
  if (interp.clarification) {
    out.push(step(dispatch, 'warning', '需要补充信息，未分派'));
    [verify, reportDef, pmDef, finDef, archiveDef].forEach((def) => out.push(step(def, 'not_involved', '本次不涉及')));
    return out;
  }

  const results = arrayField(report.agent_results).items.length;
  const failures = arrayField(report.failures).items.length;
  if (results + failures === 0) {
    out.push(step(dispatch, 'unknown', '未记录子任务'));
  } else if (failures && !results) {
    out.push(step(dispatch, 'failed', `${failures} 个领域全部失败`));
  } else if (failures) {
    out.push(step(dispatch, 'warning', `${results + failures} 个领域，失败 ${failures} 个`));
  } else {
    out.push(step(dispatch, 'done', `${results} 个领域`));
  }

  const verifyState = {
    success: 'done', partial: 'warning', failed: 'failed', unknown: 'unknown',
  }[interp.state] || 'unknown';
  out.push(step(verify, verifyState, interp.label));
  out.push(step(reportDef, interp.reportGenerated ? 'done' : 'unknown',
    interp.reportGenerated ? '报告已生成' : '报告字段不完整'));

  const request = report.approval_request && typeof report.approval_request === 'object'
    ? report.approval_request : null;
  const approvalStatus = String(report.approval_status || run.approval_status || '');
  if (!request) {
    let state = 'unknown';
    let detail = '审批状态未提供';
    if (approvalStatus === 'not_required') { state = 'not_involved'; detail = '本次不涉及'; }
    else if (approvalStatus === 'unavailable') { state = 'warning'; detail = '审批通道未接入'; }
    else if (approvalStatus === 'blocked_budget') { state = 'failed'; detail = '预算耗尽，无法发起审批'; }
    out.push(step(pmDef, state, detail));
    out.push(step(finDef, state, detail));
    out.push(step(archiveDef, state === 'not_involved' ? 'not_involved' : 'skipped',
      state === 'not_involved' ? '本次不涉及' : '未进行'));
    return out;
  }

  const requestStatus = String(request.status || '');
  let blocked = false;
  for (const def of [pmDef, finDef]) {
    const stage = stageInfo(request, def.role);
    if (!stage) { out.push(step(def, 'unknown', '审批阶段未提供')); continue; }
    const who = stage.decided_by
      ? ((principals[stage.decided_by] && principals[stage.decided_by].label) || '审批人')
      : '';
    if (stage.status === 'approved') {
      out.push(step(def, 'done', who ? `已批准 · ${who}` : '已批准'));
    } else if (stage.status === 'rejected') {
      out.push(step(def, 'failed', who ? `已驳回 · ${who}` : '已驳回'));
      blocked = true;
    } else if (stage.status === 'pending') {
      if (blocked || requestStatus === 'rejected' || requestStatus === 'expired') {
        out.push(step(def, 'skipped', '未进行'));
      } else if (requestStatus === 'pending' && !out.some((item) => item.state === 'current')) {
        out.push(step(def, 'current', `等待${term('role', def.role)}审批`));
      } else {
        out.push(step(def, 'waiting', '待前序审批'));
      }
    } else {
      out.push(step(def, 'unknown', `阶段状态未知（${stage.status}）`));
    }
  }
  const approved = requestStatus === 'approved' && report.approved_draft;
  if (approved) out.push(step(archiveDef, 'done', '已归档（草案，未执行调账）'));
  else if (requestStatus === 'rejected') out.push(step(archiveDef, 'skipped', '未归档（已驳回）'));
  else if (requestStatus === 'expired') out.push(step(archiveDef, 'failed', '草案已过期'));
  else if (requestStatus === 'pending') out.push(step(archiveDef, 'waiting', '待审批完成'));
  else out.push(step(archiveDef, 'unknown', '归档状态未知'));
  return out;
}

/* ------------------------------------------------------------ 结论卡 */

function invoicePeriods(evidenceIds, records) {
  const periods = new Set();
  for (const id of evidenceIds || []) {
    const record = records[id];
    if (record && record.kind === 'invoice' && record.period_start) periods.add(formatPeriod(record.period_start));
  }
  const sorted = [...periods].sort();
  if (!sorted.length) return '';
  return sorted.length === 1 ? sorted[0] : `${sorted[0]} 至 ${sorted[sorted.length - 1]}`;
}

export function nextActionModel(run, { meta = null } = {}) {
  if (!run) return { tone: 'idle', text: '选择或新建一个案件' };
  const steps = progressModel(run, { meta });
  const interp = interpretVerification(run);
  const current = steps.find((item) => item.state === 'current');
  if (current) return { tone: 'warning', text: current.detail, note: '审批只产出草案，不执行调账或减免' };
  if (interp.clarification) return { tone: 'warning', text: '请补充要核实的事项后重新提交', note: '本次未调用任何工具' };
  if (run.report && run.report.error) return { tone: 'failed', text: '排查失败原因后重新调查', note: '报告未生成' };
  const archive = steps.find((item) => item.key === 'archive');
  if (archive && archive.state === 'done') return { tone: 'success', text: '已归档（草案，未执行调账）', note: '如需调账，须走线下业务流程' };
  const rejected = steps.find((item) => item.state === 'failed' && item.key.startsWith('stage:'));
  if (rejected) return { tone: 'failed', text: `草案已被${rejected.title.replace('审批', '')}驳回`, note: '可修改后重新发起调查' };
  if (interp.state === 'failed') return { tone: 'failed', text: '补查失败领域后重新调查', note: interp.headline };
  if (interp.state === 'partial' || interp.state === 'unknown') return { tone: 'warning', text: '人工复核调查报告', note: interp.headline };
  if (interp.state === 'success') return { tone: 'success', text: '无需进一步处理', note: '证据一致，未发现冲突' };
  return { tone: 'unknown', text: '下一步待核实', note: '状态无法从返回字段确定' };
}

export function conclusionCards(run, { meta = null } = {}) {
  const interp = interpretVerification(run);
  const report = (run && run.report) || {};
  const { records } = displayOf(run);

  const reviewNeeded = !interp.clarification
    && (report.requires_human_review === true || ['partial', 'unknown', 'failed'].includes(interp.state));
  const verdictCard = {
    key: 'verdict',
    title: '争议结论',
    tone: { success: 'success', partial: 'warning', failed: 'failed', unknown: 'unknown', warning: 'warning', idle: 'idle' }[interp.state] || 'unknown',
    value: interp.headline,
    note: interp.state === 'idle' ? '' : (
      reviewNeeded && !String(interp.note || '').includes('复核')
        ? `需人工复核${interp.note ? ` · ${interp.note}` : ''}`
        : interp.note || ''
    ),
  };

  const conflicts = arrayField(report.conflicts).items.filter((item) => item && typeof item === 'object' && item.amount !== undefined);
  let amountCard;
  if (!run || !run.report) {
    amountCard = { key: 'amount', title: '金额差异', tone: 'idle', value: '—', note: '' };
  } else if (report.error) {
    amountCard = { key: 'amount', title: '金额差异', tone: 'unknown', value: '未提供', note: '报告未生成' };
  } else if (interp.clarification) {
    amountCard = { key: 'amount', title: '金额差异', tone: 'idle', value: '未执行调查', note: '本次没有调用任何工具' };
  } else if (!Array.isArray(report.conflicts)) {
    amountCard = { key: 'amount', title: '金额差异', tone: 'unknown', value: '待核实', note: '报告未提供冲突字段' };
  } else if (!conflicts.length && arrayField(report.failures).items.length) {
    // 有领域查询失败时，“没有列出冲突”不等于“没有差额”
    amountCard = { key: 'amount', title: '金额差异', tone: 'unknown', value: '待核实', note: '有领域查询失败，无法确认是否存在金额差异' };
  } else if (!conflicts.length) {
    amountCard = { key: 'amount', title: '金额差异', tone: 'success', value: '未发现金额差异', note: '报告未列出带金额的冲突' };
  } else {
    const first = conflicts[0];
    const variance = formatVariance(first.amount, first.currency || 'CNY');
    const periods = invoicePeriods(first.evidence_ids, records);
    amountCard = {
      key: 'amount',
      title: '金额差异',
      tone: variance.direction === 'unknown' ? 'unknown' : 'warning',
      value: variance.text,
      direction: variance.direction,
      label: variance.direction === 'none' ? '无差额' : `账单${variance.label}`,
      note: `来源：账单核算（${term('basis', first.expected_basis)} vs ${term('basis', first.observed_basis)}）${periods ? ` · 涉及账期 ${periods}` : ''}${conflicts.length > 1 ? ` · 另有 ${conflicts.length - 1} 项` : ''}`,
    };
  }
  const draft = report.proposed_draft && typeof report.proposed_draft === 'object' ? report.proposed_draft : null;
  if (draft && amountCard.key === 'amount') {
    amountCard.draft = `预设草案金额 ${formatMoney(draft.amount, draft.currency || 'CNY')}，非计算结论`;
  }

  const missing = arrayField(report.missing_information);
  let gapCard;
  if (!run || !run.report) gapCard = { key: 'gaps', title: '资料缺口', tone: 'idle', value: '—', note: '' };
  else if (report.error) gapCard = { key: 'gaps', title: '资料缺口', tone: 'unknown', value: '未提供', note: '报告未生成' };
  else if (interp.clarification) gapCard = { key: 'gaps', title: '资料缺口', tone: 'idle', value: '未执行调查', note: '本次没有核对资料' };
  else if (missing.status !== 'array') gapCard = { key: 'gaps', title: '资料缺口', tone: 'unknown', value: '待核实', note: '报告未提供资料缺口字段' };
  else if (!missing.items.length) gapCard = { key: 'gaps', title: '资料缺口', tone: 'success', value: '无', note: '报告未列出缺失资料' };
  else {
    gapCard = {
      key: 'gaps',
      title: '资料缺口',
      tone: 'warning',
      value: `${missing.items.length} 项`,
      note: describeMissingItem(missing.items[0], { documents: records }),
    };
  }

  const next = nextActionModel(run, { meta });
  const nextCard = { key: 'next', title: '下一步', tone: next.tone, value: next.text, note: next.note || '' };

  return [verdictCard, amountCard, gapCard, nextCard];
}
