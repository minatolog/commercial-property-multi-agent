/**
 * 案件页签与节点详情（Task 027 → Task 032 改版）
 *
 * 只读渲染后端字段与只读展示元数据；缺失值一律写「未提供 / 待核实」，
 * 不做业务计算，也不从自然语言里猜金额。主视图不出现英文枚举、内部字段名或 ID，
 * 这些只出现在「技术视图」（调用记录与原始 JSON）里。
 */

import * as vm from '../view-model.js';
import * as cs from '../case-status.js';
import { term, describeMissingItem, localizeErrorCodes } from '../i18n.js';
import { formatMoney, formatVariance, formatDate, formatPeriod, formatNumber } from '../format.js';
import {
  el, clear, statusBadge, emptyState, sectionTitle, paragraph, copyButton, kvList,
} from '../dom.js';

/* ------------------------------------------------------------ 小部件 */

const LEASE_STATUS = { active: '生效中', terminated: '已终止', expired: '已到期', draft: '草拟中' };

/** 后端陈述里的少量英文状态 / 金额做展示转换（纯字符串处理，不改含义） */
export function localizeStatement(text) {
  return localizeErrorCodes(vm.formatAmountsInText(String(text || '')))
    .replace(/状态\s+([a-z_]+)/g, (match, status) => `状态 ${LEASE_STATUS[status] || term('documentStatus', status)}`);
}

function section(title, count, children) {
  return el('section', { class: 'wb-summary-section' }, [
    el('h3', { class: 'wb-section-title' }, [
      title,
      count !== undefined && count !== null ? el('span', { class: 'wb-count', text: String(count) }) : null,
    ]),
    ...children,
  ]);
}

function item(kind, statement, meta) {
  return el('div', { class: 'wb-finding', dataset: { kind } }, [
    el('div', { class: 'wb-finding-statement', text: statement }),
    meta ? el('div', { class: 'wb-finding-meta', text: meta }) : null,
  ]);
}

function stateText(terminal) {
  return {
    success: '已完成',
    partial: '部分完成',
    failed: '失败',
    unknown: '信息不足',
    not_called: '本次未调用',
  }[terminal] || '未知';
}

function tracesTable(rows, { showAgent = false } = {}) {
  const header = [el('th', { text: '#' }), el('th', { text: '工具' }), el('th', { text: '子任务' })];
  if (showAgent) header.push(el('th', { text: 'Agent' }));
  header.push(el('th', { text: '状态' }), el('th', { text: '尝试' }), el('th', { text: '耗时' }));

  const body = el('tbody', {}, rows.map((row) => {
    const cells = [
      el('td', { text: String(row.index) }),
      el('td', {}, [el('span', { class: 'wb-mono', text: row.tool })]),
      el('td', {}, [el('span', { class: 'wb-mono', text: row.subtask || '未提供' })]),
    ];
    if (showAgent) {
      cells.push(el('td', {
        class: row.attributed === false ? 'text-secondary' : '',
        text: row.agentLabel || row.agent || '未关联',
      }));
    }
    cells.push(
      el('td', { text: row.status }),
      el('td', { text: row.attempt }),
      el('td', { text: row.duration }),
    );
    return el('tr', {}, cells);
  }));
  return el('div', { class: 'wb-table-wrap' }, [
    el('table', { class: 'table table-sm table-vcenter wb-table' }, [el('thead', {}, [el('tr', {}, header)]), body]),
  ]);
}


/* ------------------------------------------------------------ 案件摘要 */

/**
 * 事实 / 推断 / 缺失三段式（保持后端已有的区分）：
 * - 事实 = findings（取自业务数据、工具核算或合同条款）；
 * - 推断 = 证据结论与 conflicts（核验阶段得出的判断）；
 * - 缺失 = missing_information 与当前未解决的失败。
 */
export function renderSummary(container, run) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择案件', '在左侧选择案件，或新建一次调查。'));
    return;
  }
  const report = run.report || null;
  if (!report) {
    container.appendChild(emptyState('后端未返回报告', '该案件没有报告内容，可能未完成收集。'));
    return;
  }
  if (report.error) {
    container.appendChild(el('div', { class: 'wb-alert wb-alert-danger' }, [
      el('div', { class: 'wb-strong', text: `本次调查失败：${term('errorCode', report.error.code, { missing: '原因未提供' })}` }),
      el('div', { text: vm.textOr(report.error.message, '未提供错误说明') }),
      el('div', { class: 'wb-muted', text: '报告只包含错误信息，没有事实、冲突与结论；本页不据此推断调查结论。原始错误码见技术视图。' }),
    ]));
    return;
  }
  if (report.verdict === 'needs_clarification') {
    const clarification = report.clarification || {};
    container.appendChild(el('div', { class: 'wb-alert wb-alert-warning' }, [
      el('div', { class: 'wb-strong', text: '需要补充信息：本次没有执行调查' }),
      el('div', { text: vm.textOr(clarification.message, '无法判断这个问题属于哪一类事项。') }),
      el('div', { class: 'wb-strong wb-mt-8', text: `请补充：${vm.textOr(clarification.question, '要核实的是合同、账单还是物业工单？')}` }),
      el('div', { class: 'wb-muted', text: '没有调用任何工具，也没有产生证据或审批。' }),
    ]));
    return;
  }

  const interp = cs.interpretVerification(run);
  const { records } = cs.displayOf(run);

  const findings = vm.asArray(report.findings);
  container.appendChild(section('已核实事实', findings.length, findings.length
    ? findings.map((finding) => {
      const source = finding.source;
      const meta = [
        term('derivation', finding.derivation, { missing: '来源未提供' }),
        source && source.document_id
          ? `${vm.textOr((records[source.document_id] || {}).title, '合同')} 第 ${vm.textOr(source.page, '?')} 页 · 第 ${vm.textOr(source.clause_id, '?')} 条`
          : null,
      ].filter(Boolean).join(' · ');
      return item('note', localizeStatement(finding.statement), meta);
    })
    : [paragraph('报告没有列出已核实事实。', 'wb-muted')]));

  const conflicts = vm.asArray(report.conflicts).filter((entry) => entry && typeof entry === 'object');
  const inference = [
    item(interp.state === 'success' ? 'note' : 'conflict', interp.headline, interp.note),
    ...conflicts.map((conflict) => {
      const variance = formatVariance(conflict.amount, conflict.currency || 'CNY');
      return item('conflict', `${term('conflictType', conflict.type)}：账单${variance.label} ${variance.text}`,
        `依据：${term('basis', conflict.expected_basis)} 对照 ${term('basis', conflict.observed_basis)}；明细见「冲突对照」`);
    }),
  ];
  container.appendChild(section('判断与冲突', conflicts.length, inference));

  const missing = vm.asArray(report.missing_information);
  const failures = vm.asArray(report.failures);
  const gaps = [
    ...missing.map((entry) => item('missing', describeMissingItem(entry, { documents: records }))),
    ...failures.map((failure) => item('failure',
      `${term('capability', failure.capability, { missing: '某领域' })}失败：${term('errorCode', failure.error_code)}`,
      vm.textOr(failure.message, ''))),
  ];
  // 字段缺失 / 类型异常不能显示成 0 或“没有缺口”（Task 032 复查 P2-2，U3-A 同类）
  const invalidGapFields = [
    Array.isArray(report.missing_information) ? null : '资料缺口',
    Array.isArray(report.failures) ? null : '失败记录',
  ].filter(Boolean);
  const gapNotice = invalidGapFields.length
    ? item('missing', `报告未提供${invalidGapFields.join('、')}字段（或格式异常），无法判断是否缺失，待核实`)
    : null;
  let gapChildren;
  if (gapNotice) gapChildren = [gapNotice, ...gaps];
  else if (gaps.length) gapChildren = gaps;
  else gapChildren = [paragraph('报告没有列出资料缺口或失败。', 'wb-muted')];
  container.appendChild(section('缺失与失败', gapNotice ? '待核实' : gaps.length, gapChildren));

  const warnings = vm.asArray(report.warnings);
  if (warnings.length) {
    container.appendChild(section('系统提醒', warnings.length,
      warnings.map((warning) => item('note', localizeStatement(warning)))));
  }

  container.appendChild(el('div', { class: 'wb-alert wb-alert-info wb-mt-16' }, [
    el('div', { class: 'wb-strong', text: '处置建议：暂未生成' }),
    el('div', { text: '系统只输出事实、冲突与审批草案，不生成经营或减免建议，也不执行任何调账。' }),
  ]));
  if (report.disclaimer) container.appendChild(paragraph(report.disclaimer, 'wb-muted wb-mt-8'));
}

/* ------------------------------------------------------------ 冲突对照 */

/**
 * 冲突对照（Task 032 / 3.5-2）：每个冲突一行，左“合同约定”、右“账单实际”、中间差额。
 * 只展示冲突本身引用的记录（按 evidence_ids 查展示元数据），字段原样展示；
 * 中间的差额就是后端 conflicts[].amount，不在前端用两侧数值相减。
 */
export function renderConflicts(container, run) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择案件', '选择案件后查看合同约定与账单实际的对照。'));
    return;
  }
  const report = run.report || {};
  if (report.error) {
    container.appendChild(emptyState('报告未生成', '本次调查失败，没有可对照的冲突。'));
    return;
  }
  if (!Array.isArray(report.conflicts)) {
    container.appendChild(emptyState('冲突信息未提供', '报告缺少冲突字段，无法判断是否存在冲突。'));
    return;
  }
  const conflicts = report.conflicts.filter((item) => item && typeof item === 'object');
  if (!conflicts.length) {
    container.appendChild(emptyState('未发现冲突', '报告没有列出合同与账单之间的冲突。'));
    return;
  }
  const { records } = cs.displayOf(run);

  for (const conflict of conflicts) {
    const ids = [...new Set(vm.asArray(conflict.evidence_ids).map(String))];
    const rules = ids.map((id) => ({ id, record: records[id] }))
      .filter((item) => item.record && item.record.kind === 'charge_rule');
    const ruleIds = new Set(rules.map((item) => item.id));
    const items = ids.map((id) => ({ id, record: records[id] }))
      .filter((item) => item.record && item.record.kind === 'invoice_item'
        && (!ruleIds.size || ruleIds.has(String(item.record.charge_rule_id))));
    const variance = formatVariance(conflict.amount, conflict.currency || 'CNY');

    const left = el('div', { class: 'wb-compare-side', dataset: { side: 'expected' } }, [
      el('div', { class: 'wb-compare-label', text: `合同约定 · ${term('basis', conflict.expected_basis)}` }),
      ...(rules.length
        ? rules.map(({ record }) => el('div', { class: 'wb-compare-line' }, [
          el('span', { text: `${record.charge_type_label || '计费'}单价` }),
          el('span', { class: 'wb-num', text: `${formatMoney(record.unit_price)} / ㎡·月` }),
          el('span', { class: 'wb-muted', text: `${vm.textOr(record.effective_from, '?')} 至 ${vm.textOr(record.effective_to, '?')}` }),
        ]))
        : [el('div', { class: 'wb-muted', text: '冲突未引用可展示的计费规则' })]),
    ]);

    const right = el('div', { class: 'wb-compare-side', dataset: { side: 'observed' } }, [
      el('div', { class: 'wb-compare-label', text: `账单实际 · ${term('basis', conflict.observed_basis)}` }),
      ...(items.length
        ? items.map(({ record }) => {
          const invoice = records[record.invoice_id] || null;
          return el('div', { class: 'wb-compare-line' }, [
            el('span', { text: vm.textOr(record.description, '账单明细') }),
            el('span', { class: 'wb-num', text: `${formatMoney(record.unit_price)} / ㎡·月` }),
            el('span', { class: 'wb-muted', text: `金额 ${formatMoney(record.amount)}${invoice && invoice.invoice_no ? ` · 账单 ${invoice.invoice_no}` : ''}` }),
          ]);
        })
        : [el('div', { class: 'wb-muted', text: '冲突未引用可展示的账单明细' })]),
    ]);

    const middle = el('div', { class: 'wb-compare-mid', dataset: { direction: variance.direction } }, [
      el('div', { class: 'wb-compare-mid-label', text: '差额' }),
      el('div', { class: 'wb-compare-mid-value wb-num', text: variance.text }),
      el('div', { class: 'wb-compare-mid-note', text: variance.direction === 'unknown' ? '金额待核实' : `账单${variance.label}` }),
    ]);

    container.appendChild(el('section', { class: 'wb-compare' }, [
      el('h3', { class: 'wb-compare-title', text: term('conflictType', conflict.type) }),
      el('div', { class: 'wb-compare-row' }, [left, middle, right]),
      el('p', { class: 'wb-muted wb-compare-foot', text: '差额取自后端核算结果（账单金额 − 合同应收），页面不做两侧相减；两侧只列出冲突引用的记录。' }),
    ]));
  }
}


/* ---------------------------------------------------------------- 证据 */

/**
 * 按合同 / 账单 / 工单分组（Task 032 / 3.5-3）：
 * 合同显示条款号、页码与原文摘录；账单用表格；工单用时间线。
 * 记录字段来自只读展示元数据，原样展示；无法展示的引用只计数，原始 ID 在技术视图。
 */
export function renderEvidence(container, run) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择案件', '选择案件后按合同 / 账单 / 工单查看证据。'));
    return;
  }
  const report = run.report || {};
  if (report.error || report.verdict === 'needs_clarification') {
    container.appendChild(emptyState('本次没有证据', report.error ? '调查失败，报告未生成。' : '本次未执行调查，没有产生证据。'));
    return;
  }
  const { records } = cs.displayOf(run);
  const model = vm.evidenceModel(run);
  const ids = new Set(model.groups.flatMap((group) => group.items.map((entry) => entry.id)));
  for (const text of vm.asArray(report.missing_information)) {
    const match = /(doc_[a-z0-9_]+)/.exec(String(text));
    if (match) ids.add(match[1]);
  }
  const byKind = (kind) => [...ids].map((id) => ({ id, record: records[id] }))
    .filter((entry) => entry.record && entry.record.kind === kind);

  // ---------------- 合同 ----------------
  const clauses = vm.asArray(report.findings).filter((finding) => finding && finding.source && finding.source.document_id);
  const documents = byKind('document');
  const snippets = byKind('snippet');
  const contract = [];
  for (const entry of documents) {
    contract.push(el('div', { class: 'wb-doc-line', dataset: { digitized: entry.record.digitized ? 'yes' : 'no' } }, [
      el('span', { class: 'wb-strong', text: vm.textOr(entry.record.title, entry.record.digitized ? '文档名称未提供' : '未电子化的合同附件') }),
      el('span', { class: 'wb-muted', text: entry.record.digitized
        ? `${term('documentStatus', entry.record.document_status, { missing: '状态未提供' })} · 第 ${vm.textOr(entry.record.version, '?')} 版`
        : `未电子化：${vm.textOr(entry.record.note, '原因未提供')}` }),
    ]));
  }
  for (const finding of clauses) {
    const source = finding.source;
    contract.push(el('figure', { class: 'wb-quote' }, [
      el('figcaption', { text: `第 ${vm.textOr(source.page, '?')} 页 · 第 ${vm.textOr(source.clause_id, '?')} 条` }),
      el('blockquote', { text: String(vm.textOr(finding.statement, '')).replace(/^合同第\s*\d+\s*页\s*[\d.]+\s*条：/, '') }),
    ]));
  }
  for (const entry of snippets) {
    contract.push(el('figure', { class: 'wb-quote' }, [
      el('figcaption', { text: `第 ${vm.textOr(entry.record.page, '?')} 页 · 第 ${vm.textOr(entry.record.clause_id, '?')} 条` }),
      el('blockquote', { text: vm.textOr(entry.record.text, '') }),
    ]));
  }
  const rules = byKind('charge_rule');
  if (rules.length) {
    contract.push(evidenceTable(['计费规则', '单价（元/㎡·月）', '生效期间'], rules.map(({ record }) => [
      record.charge_type_label || term('chargeType', record.charge_type),
      { text: formatNumber(record.unit_price), num: true },
      `${vm.textOr(record.effective_from, '?')} 至 ${vm.textOr(record.effective_to, '?')}`,
    ])));
  }

  // ---------------- 账单 ----------------
  const items = byKind('invoice_item');
  const payments = byKind('payment');
  const billing = [];
  if (items.length) {
    billing.push(evidenceTable(['账单号', '账期', '科目', '单价', '金额'], items.map(({ record }) => {
      const invoice = records[record.invoice_id] || {};
      return [
        vm.textOr(invoice.invoice_no, '未提供'),
        formatPeriod(invoice.period_start),
        record.charge_type_label || vm.textOr(record.description, '未提供'),
        { text: formatNumber(record.unit_price), num: true },
        { text: formatMoney(record.amount), num: true },
      ];
    })));
  }
  if (payments.length) {
    billing.push(el('h4', { class: 'wb-subtitle', text: '收款记录' }));
    billing.push(evidenceTable(['收据号', '到账时间', '金额', '状态'], payments.map(({ record }) => [
      vm.textOr(record.receipt_no, '未提供'),
      formatDate(record.paid_at),
      { text: formatMoney(record.amount, record.currency || 'CNY'), num: true },
      term('paymentStatus', record.status),
    ])));
  }

  // ---------------- 工单 ----------------
  const orders = byKind('work_order').sort((a, b) => String(a.record.reported_at || '').localeCompare(String(b.record.reported_at || '')));
  const property = orders.length
    ? [el('ol', { class: 'wb-timeline' }, orders.map(({ record }) => el('li', {
      class: 'wb-timeline-item',
      dataset: { status: record.status === 'closed' || record.status === 'resolved' ? 'done' : 'open' },
    }, [
      el('div', { class: 'wb-timeline-time', text: formatDate(record.reported_at) }),
      el('div', { class: 'wb-timeline-body' }, [
        el('div', { class: 'wb-strong' }, [
          vm.textOr(record.title, '工单标题未提供'),
          el('span', { class: 'wb-status', dataset: { status: record.status === 'closed' || record.status === 'resolved' ? 'success' : 'partial' }, text: term('workOrderStatus', record.status) }),
        ]),
        el('div', { class: 'wb-muted', text: [
          `${vm.textOr(record.work_order_no, '工单号未提供')} · ${term('workOrderCategory', record.category)}`,
          record.resolved_at ? `${formatDate(record.resolved_at)} 处理完毕：${vm.textOr(record.resolution_note, '处理说明未提供')}` : '尚未处理完毕',
        ].join(' · ') }),
      ]),
    ])))]
    : [];

  const groups = [
    ['合同', contract, '合同文书、条款摘录与计费规则'],
    ['账单', billing, '账单明细与收款'],
    ['物业工单', property, '报修与处理时间线'],
  ];
  let shown = 0;
  for (const [title, children, note] of groups) {
    if (!children.length) continue;
    shown += 1;
    container.appendChild(el('section', { class: 'wb-evidence-group' }, [
      el('h3', { class: 'wb-section-title wb-mt-0', text: title }),
      el('div', { class: 'wb-muted wb-mb-8', text: note }),
      ...children,
    ]));
  }
  const presented = new Set([
    ...documents, ...snippets, ...rules, ...items, ...payments, ...orders,
  ].map((entry) => entry.id));
  const rest = [...ids].filter((id) => !presented.has(id));
  if (!shown) {
    container.appendChild(emptyState('报告未包含可展示的证据', '证据引用为空，或引用的记录不在可展示范围内。'));
  }
  if (rest.length) {
    container.appendChild(paragraph(`另有 ${rest.length} 条证据引用（如租约、铺位、核销记录）未单独展开，原始编号见技术视图。`, 'wb-muted'));
  }
}

function evidenceTable(headers, rows) {
  return el('div', { class: 'wb-table-wrap' }, [
    el('table', { class: 'wb-table' }, [
      el('thead', {}, [el('tr', {}, headers.map((header, index) => el('th', {
        class: rows.some((row) => row[index] && typeof row[index] === 'object' && row[index].num) ? 'is-num' : '',
        text: header,
      })))]),
      el('tbody', {}, rows.map((row) => el('tr', {}, row.map((cell) => (cell && typeof cell === 'object'
        ? el('td', { class: cell.num ? 'is-num' : '', text: cell.text })
        : el('td', { text: cell })))))),
    ]),
  ]);
}

/* ------------------------------------------------------------ 调用记录 */

export function renderCalls(container, run) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择运行', '选择运行后查看工具调用记录。'));
    return;
  }
  const rows = vm.traceRows(run);
  const report = run.report || {};
  const budget = report.budget || null;

  if (!rows.length) {
    container.appendChild(emptyState('本次运行没有工具调用记录', 'traces 为空：可能未进入执行阶段。'));
    return;
  }

  const agents = Array.from(new Set(rows.map((row) => row.agent).filter(Boolean)));
  const optionLabel = (key) => {
    const definition = vm.agentDefinitionByKey(key);
    return definition ? definition.title : key;
  };
  const select = el('select', { class: 'form-select form-select-sm', attrs: { id: 'calls-agent-filter', 'aria-label': '按 Agent 筛选工具调用' } }, [
    el('option', { value: 'all', text: '全部 Agent' }),
    ...agents.map((agent) => el('option', { value: agent, text: optionLabel(agent) })),
    el('option', { value: '__none__', text: '未关联子任务' }),
  ]);

  const unattributed = rows.filter((row) => !row.attributed).length;
  const tableHost = el('div');
  const paint = () => {
    clear(tableHost);
    const value = select.value;
    const filtered = rows.filter((row) => {
      if (value === 'all') return true;
      if (value === '__none__') return !row.agent;
      return row.agent === value;
    });
    if (!filtered.length) {
      tableHost.appendChild(emptyState('没有匹配的工具调用', '调整筛选条件。'));
      return;
    }
    tableHost.appendChild(tracesTable(filtered, { showAgent: true }));
  };

  select.addEventListener('change', paint);
  container.appendChild(el('div', { class: 'row g-2 align-items-center mb-2' }, [
    el('div', { class: 'col-12 col-sm-5' }, [
      el('label', { class: 'form-label mb-1', text: '按 Agent 筛选', attrs: { for: 'calls-agent-filter' } }),
      select,
    ]),
    el('div', { class: 'col-12 col-sm-7 text-secondary small' }, [
      budget
        ? `工具调用计数 ${vm.textOr(budget.used_tool_calls, '未提供')} / ${vm.textOr(budget.max_tool_calls, '未提供')}（报告 budget 字段）`
        : '报告未提供 budget 字段',
      unattributed ? ` · ${unattributed} 条记录无法关联到子任务` : '',
    ]),
  ]));
  container.appendChild(tableHost);
  paint();

  container.appendChild(paragraph(
    'Agent 归属由 traces[].subtask_id 经子任务索引（capability → Agent）解析，不看结果数组顺序；索引里没有的记录标为「未关联」。'
    + 'duration_ms 是单次工具调用的耗时；不同工具事件不是 Agent 对话，也不能相加当作任务总耗时。'
    + 'Trace 未记录开始时间，列表顺序不作为因果时间线。',
    'text-secondary small mt-2 mb-0',
  ));
}


/* ---------------------------------------------------------------- 审批单 */

/**
 * 审批单（Task 032 / 3.5-4）：草案摘要、金额（标注为预设草案）、两级审批时间线。
 * 只有当前轮到的审批角色显示“批准 / 驳回”按钮与意见框；审批人只从服务端白名单中选，
 * 权限仍由服务端判定。归档后醒目提示“已批准草案 · 未执行任何调账或减免”。
 */
export function renderApproval(container, run, ctx = {}) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择案件', '选择案件后查看审批单。'));
    return;
  }
  const report = run.report || {};
  const model = vm.approvalModel(run);
  const principals = (ctx.meta && ctx.meta.principals) || {};
  const who = (id) => (id && principals[id] && principals[id].label) || (id ? '审批人（角色名称未提供）' : '');
  const { records } = cs.displayOf(run);

  if (!model.hasRequest) {
    let title = '本次无需审批';
    let text = '本次调查没有生成需要审批的草案。';
    let kind = 'info';
    if (report.error) { title = '没有审批记录'; text = '调查失败，报告未生成。'; kind = 'danger'; }
    else if (report.verdict === 'needs_clarification') { title = '没有审批记录'; text = '本次未执行调查。'; }
    else if (model.approvalStatus === 'unavailable') { title = '审批通道未接入'; text = '草案只停留在报告中，没有发起审批。新建调查时勾选“启用人工审批”可走审批流程。'; kind = 'warning'; }
    else if (model.approvalStatus === 'blocked_budget') { title = '预算耗尽，无法发起审批'; text = '调查预算已用完，草案没有进入审批。'; kind = 'danger'; }
    else if (model.approvalStatus && model.approvalStatus !== 'not_required') { title = '审批状态待核实'; text = `后端返回了审批状态（${term('approvalStatus', model.approvalStatus)}），但没有审批单内容。`; kind = 'warning'; }
    container.appendChild(el('div', { class: `wb-alert wb-alert-${kind}` }, [
      el('div', { class: 'wb-strong', text: title }),
      el('div', { text }),
    ]));
    if (model.draft) container.appendChild(draftSummary(model.draft, records));
    return;
  }

  const request = model.request;
  const status = vm.textOr(request.status, '');
  if (status === 'approved' && model.approvedDraft) {
    container.appendChild(el('div', { class: 'wb-banner', dataset: { tone: 'success' } }, [
      el('span', { class: 'wb-banner-icon', attrs: { 'aria-hidden': 'true' }, text: '✓' }),
      el('div', {}, [
        el('div', { class: 'wb-strong', text: '已批准草案 · 未执行任何调账或减免' }),
        el('div', { text: '草案已归档。如需实际调账，须按线下业务流程另行处理。' }),
      ]),
    ]));
  } else if (status === 'rejected') {
    container.appendChild(el('div', { class: 'wb-banner', dataset: { tone: 'failed' } }, [
      el('span', { class: 'wb-banner-icon', attrs: { 'aria-hidden': 'true' }, text: '✕' }),
      el('div', {}, [
        el('div', { class: 'wb-strong', text: '草案已被驳回' }),
        el('div', { text: '驳回意见见下方审批记录；可补充资料后重新发起调查。' }),
      ]),
    ]));
  } else if (status === 'expired') {
    container.appendChild(el('div', { class: 'wb-banner', dataset: { tone: 'failed' } }, [
      el('span', { class: 'wb-banner-icon', attrs: { 'aria-hidden': 'true' }, text: '✕' }),
      el('div', { class: 'wb-strong', text: '草案已过期，不能再审批' }),
    ]));
  }

  const sheet = el('section', { class: 'wb-sheet' }, [
    el('div', { class: 'wb-sheet-head' }, [
      el('h3', { class: 'wb-sheet-title', text: `${term('actionType', request.action_type)} 审批单` }),
      el('span', { class: 'wb-status', dataset: { status: model.statusMeta.state }, text: model.statusMeta.label }),
    ]),
    draftSummary(model.draft || request, records, request),
  ]);
  container.appendChild(sheet);

  const allowlist = vm.asArray(ctx.meta && ctx.meta.approver_allowlist);
  const timeline = el('ol', { class: 'wb-approval-steps' });
  for (const stage of model.stages) {
    const isCurrent = model.canDecide && model.nextStage && stage.seq === model.nextStage.seq;
    const decision = stage.status === 'approved' ? '批准' : stage.status === 'rejected' ? '驳回' : isCurrent ? '待审批' : '未开始';
    const row = el('li', { class: 'wb-approval-step', dataset: { status: stage.status, current: isCurrent ? 'yes' : 'no' } }, [
      el('span', { class: 'wb-stage-index', text: String(stage.seq) }),
      el('div', { class: 'wb-approval-body' }, [
        el('div', { class: 'wb-approval-row' }, [
          el('span', { class: 'wb-strong', text: `${stage.roleLabel}审批` }),
          statusBadge(stage.state === 'pending' && !isCurrent ? 'not_called' : stage.state, decision),
        ]),
        stage.decidedBy
          ? el('div', { class: 'wb-muted', text: `${who(stage.decidedBy)} · ${formatDate(stage.decidedAt)}` })
          : el('div', { class: 'wb-muted', text: isCurrent ? '等待该部门审批' : '待前一级完成后开始' }),
        stage.reason ? el('div', { class: 'wb-approval-reason', text: `意见：${stage.reason}` }) : null,
      ]),
    ]);
    if (isCurrent) {
      const actor = vm.actorForStage(allowlist, stage);
      const actorMatches = actor && actor.includes(stage.role);
      row.querySelector('.wb-approval-body').appendChild(actorMatches
        ? decisionForm(actor, who(actor), request, ctx)
        : el('div', { class: 'wb-alert wb-alert-warning wb-mt-8', text: '服务端审批人白名单中没有该角色的审批人，页面不提供审批按钮。' }));
    }
    timeline.appendChild(row);
  }
  sheet.appendChild(el('h4', { class: 'wb-subtitle', text: '两级审批（物业 → 财务，串行）' }));
  sheet.appendChild(timeline);
  if (model.warnings.length) {
    sheet.appendChild(paragraph(`审批提醒：${model.warnings.map(localizeStatement).join('；')}`, 'wb-muted'));
  }
  sheet.appendChild(paragraph('同一人不能连签两级；批准只改变草案状态，不执行任何调账、减免或派单。', 'wb-muted wb-mt-8'));
}

function draftSummary(draft, records, request = null) {
  const target = (draft && draft.target) || {};
  const invoice = records[target.invoice_id] || null;
  const line = records[target.invoice_item_id] || null;
  const variance = draft && draft.computed_variance;
  return el('div', { class: 'wb-sheet-grid' }, [
    el('div', { class: 'wb-amount-box' }, [
      el('div', { class: 'label', text: '草案金额' }),
      el('div', { class: 'value', text: formatMoney(draft && draft.amount, (draft && draft.currency) || 'CNY') }),
      el('div', { class: 'note', text: '预设草案金额，非计算结论' }),
    ]),
    el('div', { class: 'wb-amount-box' }, [
      el('div', { class: 'label', text: '账单核算差额（仅作对照）' }),
      el('div', { class: 'value', text: variance ? formatVariance(variance).text : '未提供' }),
      el('div', { class: 'note', text: variance ? '来自报告核算结果；与草案金额不是因果关系' : '报告未提供核算差额，不能推断为 0' }),
    ]),
    kvList([
      ['草案类型', term('actionType', draft && draft.action_type)],
      ['关联账单', invoice
        ? `${vm.textOr(invoice.invoice_no, '未提供')}（${formatPeriod(invoice.period_start)}）${line ? ` · ${vm.textOr(line.description, '')}` : ''}`
        : '未提供'],
      ['草案版本', `第 ${vm.textOr(draft && draft.draft_version, '?')} 版`],
      ['有效期至', formatDate((request && request.expires_at) || (draft && draft.expires_at))],
      request ? ['发起时间', formatDate(request.created_at)] : null,
    ].filter(Boolean)),
  ]);
}

function decisionForm(actor, actorLabel, request, ctx) {
  const reason = el('textarea', {
    class: 'wb-input',
    rows: '2',
    attrs: { id: 'approval-reason', maxlength: '1000', placeholder: '审批意见（可选，会写入审批台账）', 'aria-label': '审批意见' },
  });
  const message = el('div', { class: 'wb-alert d-none', attrs: { role: 'alert' } });
  const approve = el('button', { type: 'button', class: 'wb-btn wb-btn-primary', text: '批准' });
  const reject = el('button', { type: 'button', class: 'wb-btn wb-btn-danger', text: '驳回' });
  let busy = false;
  const send = async (decision) => {
    if (busy) return;
    busy = true;
    approve.disabled = true;
    reject.disabled = true;
    message.className = 'wb-alert wb-alert-info wb-mt-8';
    message.textContent = decision === 'approve' ? '正在提交批准…' : '正在提交驳回…';
    try {
      await ctx.onDecide({
        decision,
        actor,
        reason: reason.value.trim(),
        draftVersion: Number(request.draft_version),
      });
    } catch (error) {
      message.className = 'wb-alert wb-alert-danger wb-mt-8';
      message.textContent = `${error && error.message ? error.message : '审批提交失败'}${error && error.traceId ? `（追踪号 ${error.traceId}）` : ''}`;
      busy = false;
      approve.disabled = false;
      reject.disabled = false;
    }
  };
  approve.addEventListener('click', () => send('approve'));
  reject.addEventListener('click', () => send('reject'));
  return el('div', { class: 'wb-decision' }, [
    el('div', { class: 'wb-muted', text: `以 ${actorLabel} 身份审批（服务端白名单）` }),
    reason,
    el('div', { class: 'wb-decision-actions' }, [approve, reject]),
    message,
  ]);
}

/* ------------------------------------------------------------ 原始数据 */

export function renderRaw(container, run) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择运行', '原始 JSON 只在需要排查时查看。'));
    return;
  }
  const view = {
    run_id: run.run_id,
    thread_id: run.thread_id,
    lease_id: run.lease_id,
    status: run.status,
    verdict: run.verdict,
    approval_status: run.approval_status,
    created_at: run.created_at,
    updated_at: run.updated_at,
    report: run.report || null,
    traces: run.traces || [],
  };
  const text = JSON.stringify(view, null, 2);
  container.appendChild(el('div', { class: 'd-flex align-items-center justify-content-between gap-2 mb-2' }, [
    el('span', { class: 'text-secondary small', text: 'GET /api/runs/{run_id} 的返回内容（开发排查用）' }),
    copyButton(text, '复制 JSON'),
  ]));
  container.appendChild(el('details', { open: '' }, [
    el('summary', { class: 'text-secondary small', text: '展开原始 JSON' }),
    el('pre', { class: 'wb-pre mt-2', text }),
  ]));
}


/* ------------------------------------------------------------ 节点详情 */

function agentSummarySection(run, definition) {
  const index = vm.buildSubtaskIndex(run);
  const participation = vm.agentParticipation(run, definition, index);
  const attribution = vm.findingsAttribution(run);
  const findings = attribution.byAgent[definition.key] || [];
  const conflicts = vm.conflictsForAgent(run, definition, index);
  const nodes = [];

  nodes.push(kvList([
    ['职责', definition.duty],
    ['本次状态', participation.participated ? participation.label : '本次未调用'],
    ['查询次数', participation.participated ? `${participation.traces.length} 次` : '0 次'],
  ]));

  if (!participation.participated) {
    nodes.push(paragraph('本次调查没有分派到这个领域，也没有它的查询记录。这是“未调用”，不是“执行成功”。', 'wb-muted'));
    return nodes;
  }

  for (const record of participation.subtasks.filter((entry) => entry.failure)) {
    nodes.push(el('div', { class: 'wb-alert wb-alert-danger' }, [
      el('div', { class: 'wb-strong', text: `查询失败：${term('errorCode', record.failure.error_code)}` }),
      el('div', { text: vm.textOr(record.failure.message, '未提供失败说明') }),
    ]));
  }
  for (const record of participation.subtasks.filter((entry) => entry.resolvedFailures.length)) {
    nodes.push(paragraph(`曾失败 ${record.resolvedFailures.length} 次，补查后已恢复（失败记录保留在技术视图）。`, 'wb-muted'));
  }

  if (conflicts.length) {
    nodes.push(sectionTitle('该领域的冲突'));
    conflicts.forEach((conflict) => {
      const variance = formatVariance(conflict.amount, conflict.currency || 'CNY');
      nodes.push(item('conflict', `${term('conflictType', conflict.type)}：账单${variance.label} ${variance.text}`));
    });
  }
  if (findings.length) {
    nodes.push(sectionTitle('该领域的发现'));
    findings.forEach((entry) => nodes.push(item('note', localizeStatement(entry.finding.statement),
      term('derivation', entry.finding.derivation, { missing: '' }))));
  } else {
    nodes.push(paragraph('该领域没有可归属的发现。', 'wb-muted'));
  }
  return nodes;
}

export function renderNodeDetail(container, run, nodeId, ctx = {}) {
  clear(container);
  const title = document.getElementById('node-detail-title');
  const sub = document.getElementById('node-detail-sub');
  const kicker = document.getElementById('node-detail-kicker');
  if (!run) {
    container.appendChild(paragraph('请先选择一个案件。', 'wb-muted'));
    return;
  }
  const report = run.report || {};
  const graph = vm.buildGraphModel(run).nodes;
  const highlights = vm.nodeHighlights(run);
  const nodes = [];

  if (nodeId === 'plan') {
    if (kicker) kicker.textContent = '流程 · 规划';
    if (title) title.textContent = '任务规划';
    if (sub) sub.textContent = highlights.plan || '';
    const planning = report.planning && typeof report.planning === 'object' ? report.planning : {};
    const index = vm.buildSubtaskIndex(run);
    nodes.push(kvList([
      ['规划方式', term('planSource', planning.plan_source, { missing: '未提供' })],
      ['分派方式', term('route', report.route)],
      ['分派领域', index.records.length
        ? index.records.map((record) => `${term('capability', record.capability, { missing: '未知领域' })}（${stateText(record.terminal)}）`).join('、')
        : '无'],
      ['补查次数', report.revision === undefined ? '未提供' : `${report.revision} 次`],
    ]));
    const reasons = vm.asArray(report.routing_reason);
    if (reasons.length) {
      nodes.push(sectionTitle('为什么分派到这些领域'));
      reasons.forEach((reason) => nodes.push(item('note',
        `${vm.textOr(reason.label, term('domain', reason.domain))}`,
        reason.source === 'llm'
          ? `模型理由：${vm.textOr(reason.reason, '未提供')}`
          : `问题中出现：${vm.asArray(reason.matched).join('、') || '未提供'}`)));
    }
  } else if (nodeId.startsWith('agent:')) {
    const definition = vm.AGENT_DEFS.find((entry) => entry.nodeId === nodeId);
    if (!definition) return;
    if (kicker) kicker.textContent = '调查领域';
    if (title) title.textContent = definition.title.replace(' Agent', '');
    if (sub) sub.textContent = highlights[nodeId] || '';
    nodes.push(...agentSummarySection(run, definition));
  } else if (nodeId === 'verify') {
    if (kicker) kicker.textContent = '流程 · 核验';
    if (title) title.textContent = '证据核验';
    if (sub) sub.textContent = graph.verify.label;
    const interp = cs.interpretVerification(run);
    nodes.push(item(interp.state === 'success' ? 'note' : 'conflict', interp.headline, interp.note));
    if (interp.incomplete && interp.incomplete.length) {
      nodes.push(paragraph('报告缺少或类型异常的字段较多，不能据此宣称未发现冲突（字段名见技术视图）。', 'wb-muted'));
    }
    if (interp.counts) {
      nodes.push(kvList([
        ['冲突', `${interp.counts.conflicts} 项`],
        ['资料缺口', `${interp.counts.missing} 项`],
        ['失败领域', `${interp.counts.failures} 个`],
        ['叙述与字段不一致', `${interp.counts.discrepancies} 处`],
        ['需人工复核', report.requires_human_review === true ? '是' : report.requires_human_review === false ? '否' : '待核实'],
      ]));
    }
  } else if (nodeId === 'report') {
    if (kicker) kicker.textContent = '流程 · 报告';
    if (title) title.textContent = '调查报告';
    if (sub) sub.textContent = graph.report.label;
    nodes.push(paragraph(highlights.report || '', 'wb-finding-statement'));
    nodes.push(paragraph('报告只陈述事实、冲突与缺失，不构成减免或调账决定。完整内容见下方「案件摘要」。', 'wb-muted'));
  } else if (nodeId === 'approval') {
    if (kicker) kicker.textContent = '流程 · 审批';
    if (title) title.textContent = '人工审批';
    if (sub) sub.textContent = highlights.approval || '';
    nodes.push(paragraph('审批单、审批记录与操作按钮在下方「审批单」页签。', 'wb-muted'));
  }
  nodes.filter(Boolean).forEach((node) => container.appendChild(node));
}
