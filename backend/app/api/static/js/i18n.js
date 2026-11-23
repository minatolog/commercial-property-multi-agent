/**
 * 集中术语映射（Task 032）
 *
 * 主视图里不出现英文枚举、内部字段名或 ID：所有状态与字段都经这里转换。
 * 映射缺失时返回“未知状态（原值）”，不能留空，也不能猜一个相近的词。
 */

const TERMS = {
  runStatus: {
    completed: '已完成',
    awaiting_approval: '待审批',
    failed: '失败',
    running: '调查执行中',
    pending: '调查执行中',
  },
  verdict: {
    supported: '证据一致',
    conflicting: '存在冲突',
    insufficient: '证据不足',
    needs_clarification: '需要补充信息',
  },
  completeness: {
    complete: '调查完整',
    partial: '部分完成',
    not_executed: '未执行调查',
  },
  route: {
    deterministic: '单领域查询',
    fanout: '多领域分派',
    clarification: '需要补充信息',
  },
  capability: {
    'lease.query': '合同查询',
    'lease.renewal_evaluation': '续租评估',
    'billing.statement': '账单核对',
    'billing.arrears_check': '欠费检查',
    'property.work_orders': '工单查询',
  },
  domain: {
    lease: '合同',
    billing: '账单',
    property: '物业工单',
  },
  role: {
    property_manager: '物业管理部门',
    finance: '财务部门',
  },
  approvalStatus: {
    not_required: '本次无需审批',
    unavailable: '审批通道未接入',
    ready: '草案已就绪，待发起审批',
    pending_approval: '待审批',
    pending_next_stage: '待下一级审批',
    pending: '待审批',
    approved: '已批准（仅草案）',
    rejected: '已驳回',
    expired: '草案已过期',
    superseded: '已被新版本替代',
    blocked_budget: '预算耗尽，无法发起审批',
  },
  stageStatus: {
    pending: '待处理',
    approved: '已批准',
    rejected: '已驳回',
  },
  conflictType: {
    rent_variance: '账单租金与合同计费规则不一致',
  },
  conflictShort: {
    rent_variance: '租金差异',
  },
  basis: {
    'lease.charge_rule': '合同计费规则',
    'invoice_item.unit_price': '账单明细单价',
  },
  actionType: {
    rent_reduction_draft: '租金减免草案',
  },
  derivation: {
    direct: '直接取自业务数据',
    computed: '由只读工具核算',
    document_clause: '合同条款摘录',
  },
  errorCode: {
    budget_exhausted: '预算耗尽',
    timeout: '调用超时',
    permission_denied: '权限不足',
    project_scope_denied: '超出项目范围',
    insufficient_evidence: '证据不足',
    internal_error: '内部错误',
    model_error: '模型调用失败',
    capability_unavailable: '能力不可用',
    invalid_request: '请求无效',
    // 以下与后端 ErrorCode 枚举对齐（Task 032 复查 P3-1），由 test_task032_display 守护
    invalid_context: '调用上下文无效',
    capability_not_declared: '能力未声明',
    agent_not_enabled: '该领域未启用',
    agent_not_registered: '该领域未注册',
    tool_not_allowed: '工具不在允许范围',
    tool_not_found: '工具不存在',
    invalid_tool_arguments: '查询参数无效',
    invalid_tool_result: '查询结果格式无效',
    tool_timeout: '查询超时',
    record_not_found: '未找到记录',
    deadline_exceeded: '超过时限',
    upstream_error: '上游服务错误',
    not_implemented: '功能未实现',
  },
  workOrderStatus: {
    open: '待处理',
    in_progress: '处理中',
    closed: '已关闭',
    resolved: '已解决',
  },
  workOrderCategory: {
    hvac: '空调暖通',
    electrical: '电气',
    plumbing: '给排水',
  },
  invoiceStatus: {
    issued: '已开具',
    paid: '已结清',
    void: '已作废',
  },
  paymentStatus: {
    confirmed: '已到账',
    pending: '待确认',
  },
  chargeType: {
    rent: '租金',
    property_fee: '物业费',
    deposit: '押金',
  },
  planSource: {
    rule: '规则规划',
    llm: '模型规划',
    fallback_rule: '模型不可用，已回退规则规划',
    fallback_clarification: '模型不可用，已改为回问',
  },
  documentStatus: {
    signed: '已签署',
    draft: '草稿',
  },
};

/**
 * 术语转换。`kind` 是 TERMS 的分组名；值缺失返回 `未提供`，映射缺失返回 `未知状态（原值）`。
 */
export function term(kind, value, { missing = '未提供' } = {}) {
  if (value === null || value === undefined || String(value).trim() === '') return missing;
  const table = TERMS[kind];
  const key = String(value);
  if (table && Object.prototype.hasOwnProperty.call(table, key)) return table[key];
  // 未映射的错误码不把英文原值带进主视图（Task 032 复查 P3-1），原值只在技术视图里看
  if (kind === 'errorCode') return '其他错误（原始代码见技术视图）';
  return `未知状态（${key}）`;
}

/**
 * 后端告警 / 说明文本里夹带的英文错误码转中文（Task 032 复查 P2-1）。
 * - 括号内：只替换**已知**错误码；括号里的其它英文词（如合同摘录里的 `(pending)`）原样保留，
 *   不能被误标成“其他错误”（Task 032 返修复查 P3-1）。
 * - “失败:” 之后：这个位置只会是错误码，未映射的也按 `term` 显示“其他错误”，不带英文原值。
 */
export function localizeErrorCodes(text) {
  return String(text || '')
    .replace(/（([a-z][a-z_]*)）|\(([a-z][a-z_]*)\)/g, (match, a, b) => {
      const code = a || b;
      return hasTerm('errorCode', code) ? `（${term('errorCode', code)}）` : match;
    })
    .replace(/(失败[:：]\s*)([a-z][a-z_]*)\b/g, (match, prefix, code) => `${prefix}${term('errorCode', code)}`);
}

/** 是否有映射（测试与降级显示用） */
export function hasTerm(kind, value) {
  const table = TERMS[kind];
  return Boolean(table) && Object.prototype.hasOwnProperty.call(table, String(value));
}

/** 失败说明：`子任务 st_2_billing 失败: budget_exhausted` → `账单核对失败：预算耗尽` */
export function describeMissingItem(text, { documents = {} } = {}) {
  const raw = String(text || '');
  const failure = /子任务\s+st_\d+_([a-z]+)\s+失败:\s*([a-z_]+)/.exec(raw);
  if (failure) {
    return `${term('domain', failure[1], { missing: '某领域' })}查询失败：${term('errorCode', failure[2])}`;
  }
  const unreturned = /未获得子任务结果:\s*st_\d+_([a-z]+)/.exec(raw);
  if (unreturned) return `${term('domain', unreturned[1], { missing: '某领域' })}查询未返回结果`;
  const doc = /(doc_[a-z0-9_]+)/.exec(raw);
  if (doc) {
    const info = documents[doc[1]];
    if (info && info.note) return info.note;
    if (info && info.title) return `${info.title}${info.digitized === false ? '（未电子化）' : ''}`;
    return '合同引用的一份文档尚未电子化（名称未提供）';
  }
  // 其它说明里夹带的错误码（如“条款检索不可用（budget_exhausted）”）转成中文
  return raw ? localizeErrorCodes(raw) : '未提供';
}

export { TERMS };
