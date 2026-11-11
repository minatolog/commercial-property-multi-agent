/**
 * 报告、证据、调用记录、审批与节点详情（Task 027）
 *
 * 只读渲染后端字段；缺失值一律写「未提供 / 待核实」，不做业务计算，
 * 也不从自然语言里猜金额。
 */

import * as vm from '../view-model.js';
import {
  el, clear, statusBadge, emptyState, sectionTitle, paragraph, codeChip, copyButton, kvList,
} from '../dom.js';

/* ------------------------------------------------------------ 小部件 */

const DERIVATION_LABELS = {
  direct: '直接取自结构化数据',
  computed: '由只读工具计算',
  document_clause: '合同条款摘录',
};

function derivationLabel(value) {
  if (!value) return '来源未提供';
  return DERIVATION_LABELS[value] || String(value);
}

function findingItem(finding) {
  const ids = vm.asArray(finding.evidence_ids);
  const children = [
    el('div', { class: 'wb-finding-statement', text: vm.textOr(finding.statement, '未提供陈述') }),
    el('div', { class: 'wb-finding-meta', text: `${derivationLabel(finding.derivation)} · 证据 ${ids.length} 条` }),
  ];
  const source = finding.source;
  if (source && source.document_id) {
    children.push(el('div', { class: 'wb-finding-meta' }, [
      '条款出处：',
      el('span', {
        class: 'wb-mono',
        text: `${source.document_id} v${vm.textOr(source.document_version, '?')} · 第 ${vm.textOr(source.page, '?')} 页 · 条款 ${vm.textOr(source.clause_id, '未提供')}`,
      }),
    ]));
  }
  return el('div', { class: 'wb-finding', dataset: { kind: 'note' } }, children);
}

function conflictItem(conflict) {
  const children = [
    el('div', { class: 'wb-finding-statement' }, [
      `冲突类型 ${vm.textOr(conflict.type, '未提供')}`,
      conflict.amount ? ` · 差额 ${conflict.amount}` : '',
      conflict.currency ? ` ${conflict.currency}` : '',
    ]),
    el('div', { class: 'wb-finding-meta', text: `期望依据 ${vm.textOr(conflict.expected_basis, '未提供')} · 实际来源 ${vm.textOr(conflict.observed_basis, '未提供')}` }),
  ];
  if (conflict.subtask_id) {
    children.push(el('div', { class: 'wb-finding-meta', text: `来源子任务 ${conflict.subtask_id}` }));
  }
  const ids = vm.asArray(conflict.evidence_ids);
  if (ids.length) {
    children.push(el('div', { class: 'wb-finding-meta', text: `关联证据 ${ids.length} 条（见「证据」标签页）` }));
  }
  return el('div', { class: 'wb-finding', dataset: { kind: 'conflict' } }, children);
}

function stringItem(text, kind) {
  return el('div', { class: 'wb-finding', dataset: { kind } }, [
    el('div', { class: 'wb-finding-statement', text: vm.textOr(text, '未提供内容') }),
  ]);
}

function failureItem(failure) {
  return el('div', { class: 'wb-finding', dataset: { kind: 'failure' } }, [
    el('div', { class: 'wb-finding-statement', text: `子任务 ${vm.textOr(failure.subtask_id, '未提供')} 失败` }),
    el('div', { class: 'wb-finding-meta', text: `错误码 ${vm.textOr(failure.error_code, '未提供')}${failure.message ? ` · ${failure.message}` : ''}` }),
  ]);
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

function failureBlock(failure, options = {}) {
  if (!failure) return null;
  const code = vm.textOr(failure.error_code, '未提供错误码');
  const message = vm.textOr(failure.message, '');
  return el('div', { class: 'alert alert-danger py-2 mb-2' }, [
    el('div', { class: 'fw-bold small', text: options.title || `子任务失败：${code}` }),
    message ? el('div', { class: 'small', text: message }) : null,
    el('div', { class: 'wb-finding-meta' }, [
      '子任务 ',
      el('span', { class: 'wb-mono', text: vm.textOr(failure.subtask_id, '未提供') }),
      ` · 错误码 ${code}`,
    ]),
  ]);
}

/* ------------------------------------------------------------ 调查摘要 */

export function renderSummary(container, run) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择运行', '在左侧选择历史运行，或提交一次新的调查。'));
    return;
  }
  const report = run.report || null;
  if (!report) {
    container.appendChild(emptyState('后端未返回报告', '该运行记录没有 report 字段，可能未完成收集。'));
    return;
  }
  if (report.error) {
    container.appendChild(el('div', { class: 'alert alert-danger' }, [
      el('div', { class: 'fw-bold', text: '本次运行失败：报告未生成' }),
      el('div', { class: 'small', text: `错误码 ${vm.textOr(report.error.code, '未提供')} · ${vm.textOr(report.error.message, '未提供错误说明')}` }),
      el('div', { class: 'small mt-1', text: '报告对象只包含错误信息，没有 findings / verdict / 冲突等字段；本页不据此推断调查结论。' }),
    ]));
    container.appendChild(kvList([
      ['问题', vm.textOr(run.question, '')],
      ['租约', vm.textOr(run.lease_id, '未提供')],
      ['运行', el('span', { class: 'wb-mono', text: vm.textOr(run.run_id, '未提供') })],
      ['执行状态', vm.runStatusMeta(run.status, { reportError: true }).label],
    ]));
    return;
  }

  const statusMeta = vm.runStatusMeta(run.status);

  const verdict = vm.verdictMeta(report.verdict);
  const completeness = vm.completenessMeta(report.completeness);

  container.appendChild(kvList([
    ['问题', vm.textOr(report.question || run.question, '')],
    ['租约', vm.textOr(run.lease_id, '未提供')],
    ['运行', el('span', { class: 'wb-mono', text: vm.textOr(run.run_id, '未提供') })],
    ['线程', el('span', { class: 'wb-mono', text: vm.textOr(run.thread_id, '未提供') })],
    ['执行状态', `${statusMeta.label}（${statusMeta.note}）`],
    ['证据结论', `${verdict.label}（${verdict.note}）`],
    ['完整度', `${completeness.label}（${completeness.note}）`],
    ['路由', vm.textOr(report.route, '未提供')],
    ['需要人工复核', report.requires_human_review === true ? '是' : report.requires_human_review === false ? '否' : '未提供'],
  ]));

  container.appendChild(el('hr', { class: 'my-3' }));
  container.appendChild(sectionTitle('金额核对'));
  const amounts = vm.asArray(report.authoritative_amounts);
  if (amounts.length) {
    for (const item of amounts) {
      const conclusion = item.conclusion && typeof item.conclusion === 'object'
        ? Object.entries(item.conclusion).map(([key, value]) => `${key}=${value}`).join(' · ')
        : '';
      container.appendChild(el('div', { class: 'wb-finding', dataset: { kind: 'note' } }, [
        el('div', { class: 'wb-finding-statement', text: vm.textOr(item.rendered, conclusion || '未提供渲染结果') }),
        el('div', { class: 'wb-finding-meta', text: `字段核对 ${vm.textOr(item.check_status, '未提供')} · 子任务 ${vm.textOr(item.subtask_id, '未提供')} · 能力 ${vm.textOr(item.capability, '未提供')}` }),
      ]));
    }
  } else {
    const computed = vm.asArray(report.findings).find((finding) => finding.derivation === 'computed');
    if (computed) {
      container.appendChild(el('div', { class: 'wb-finding', dataset: { kind: 'note' } }, [
        el('div', { class: 'wb-finding-statement', text: vm.textOr(computed.statement, '未提供') }),
        el('div', { class: 'wb-finding-meta', text: '报告未提供 authoritative_amounts，以上金额取自工具计算的 finding 文本，本页不做减免后余额等运算。' }),
      ]));
    }
    container.appendChild(paragraph(
      '暂无结构化金额（authoritative_amounts 为空）。本页不会把缺失金额填成 0。',
      'text-secondary small mb-0',
    ));
  }

  container.appendChild(sectionTitle('已核实事实', el('span', { class: 'text-secondary small', text: `${vm.asArray(report.findings).length} 条` })));
  const findings = vm.asArray(report.findings);
  if (findings.length) findings.forEach((finding) => container.appendChild(findingItem(finding)));
  else container.appendChild(paragraph('报告未包含 findings。', 'text-secondary small mb-0'));

  const attribution = vm.findingsAttribution(run);
  if (attribution.crossDomain.length || attribution.unassociated.length) {
    container.appendChild(sectionTitle(
      '跨领域 / 未关联发现',
      el('span', { class: 'text-secondary small', text: `${attribution.crossDomain.length + attribution.unassociated.length} 条` }),
    ));
    container.appendChild(paragraph(
      '这些发现无法可靠归属到单一 Agent（跨领域证据、无证据或前缀无法归类），因此不并入任何 Agent 节点，在此单列。',
      'text-secondary small',
    ));
    for (const entry of attribution.crossDomain) {
      container.appendChild(el('div', { class: 'wb-finding', dataset: { kind: 'note' } }, [
        el('div', { class: 'wb-finding-statement', text: vm.textOr(entry.finding.statement, '未提供陈述') }),
        el('div', { class: 'wb-finding-meta', text: `跨领域 · ${entry.attribution.detail}` }),
      ]));
    }
    for (const entry of attribution.unassociated) {
      container.appendChild(el('div', { class: 'wb-finding', dataset: { kind: 'missing' } }, [
        el('div', { class: 'wb-finding-statement', text: vm.textOr(entry.finding.statement, '未提供陈述') }),
        el('div', { class: 'wb-finding-meta', text: `未关联 · ${entry.attribution.detail}` }),
      ]));
    }
  }

  const conflicts = vm.asArray(report.conflicts);
  const conflictsProvided = Array.isArray(report.conflicts);
  container.appendChild(sectionTitle('冲突', el('span', { class: 'text-secondary small', text: conflictsProvided ? `${conflicts.length} 条` : '未提供' })));
  if (conflicts.length) conflicts.forEach((conflict) => container.appendChild(conflictItem(conflict)));
  else if (conflictsProvided) container.appendChild(paragraph('报告 conflicts 为空数组：本次未列出冲突。', 'text-secondary small mb-0'));
  else container.appendChild(paragraph('报告未提供 conflicts 字段，无法判断是否存在冲突。', 'text-secondary small mb-0'));

  const missing = vm.asArray(report.missing_information);
  const missingProvided = Array.isArray(report.missing_information);
  container.appendChild(sectionTitle('资料缺失', el('span', { class: 'text-secondary small', text: missingProvided ? `${missing.length} 条` : '未提供' })));
  if (missing.length) missing.forEach((item) => container.appendChild(stringItem(item, 'missing')));
  else if (missingProvided) container.appendChild(paragraph('报告 missing_information 为空数组：本次未列出资料缺失。', 'text-secondary small mb-0'));
  else container.appendChild(paragraph('报告未提供 missing_information 字段。', 'text-secondary small mb-0'));

  const failures = vm.asArray(report.failures);
  if (failures.length) {
    container.appendChild(sectionTitle('失败子任务', el('span', { class: 'text-secondary small', text: `${failures.length} 个` })));
    failures.forEach((failure) => container.appendChild(failureItem(failure)));
  }

  const discrepancies = vm.asArray(report.narrative_discrepancies);
  if (discrepancies.length) {
    container.appendChild(sectionTitle('叙述与字段差异', el('span', { class: 'text-secondary small', text: `${discrepancies.length} 条` })));
    discrepancies.forEach((item) => container.appendChild(el('div', { class: 'wb-finding', dataset: { kind: 'failure' } }, [
      el('div', { class: 'wb-finding-statement', text: `子任务 ${vm.textOr(item.subtask_id, '未提供')} 的模型叙述与工具字段不一致` }),
      el('div', { class: 'wb-finding-meta', text: `类型 ${vm.textOr(item.kind, '未提供')} · 核对状态 ${vm.textOr(item.status, '未提供')}` }),
    ])));
  }

  container.appendChild(sectionTitle('处置建议'));
  container.appendChild(el('div', { class: 'alert alert-secondary mb-3' }, [
    el('div', { class: 'fw-bold', text: '暂未生成处置建议' }),
    el('div', { class: 'small', text: '当前后端只输出事实、冲突与审批草案，没有生成经营或减免建议的字段。本页不编造处置决定。' }),
  ]));

  const warnings = vm.asArray(report.warnings);
  if (warnings.length) {
    container.appendChild(sectionTitle('后端提醒'));
    warnings.forEach((warning) => container.appendChild(stringItem(warning, 'note')));
  }

  if (report.disclaimer) {
    container.appendChild(paragraph(report.disclaimer, 'text-secondary small mt-2 mb-0'));
  }
}

/* ---------------------------------------------------------------- 证据 */

export function renderEvidence(container, run) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择运行', '选择运行后按合同 / 账单 / 工单分组查看证据。'));
    return;
  }
  const model = vm.evidenceModel(run);
  if (!model.total) {
    container.appendChild(emptyState('报告未包含证据引用', 'evidence_ids 为空或本次运行未产出报告。'));
    return;
  }
  container.appendChild(paragraph(
    `共 ${model.total} 条证据引用。此处的分组按证据 ID 前缀（doc_ / snip_ → 合同文书，inv_ / itm_ / pay_ / alloc_ → 账单付款，`
    + 'wo_ → 物业工单，lease_ / unit_ / ten_ / rule_ → 合同与租约，其余 → 未分类）仅用于**展示归类**，'
    + '后端未提供分类字段；它不同于 finding 的 Agent 归属，后者见各节点详情中的「归属依据」。',
    'text-secondary small',
  ));

  for (const group of model.groups) {
    const items = group.items.map((item) => {
      const row = el('div', { class: 'd-flex align-items-start justify-content-between gap-2 mb-2' }, [
        el('div', { class: 'min-w-0' }, [
          codeChip(item.id),
          item.note
            ? el('div', { class: 'wb-finding-meta', text: `文档 ${item.note.documentId} · 版本 ${vm.textOr(item.note.version, '未提供')} · 第 ${vm.textOr(item.note.page, '?')} 页 · 条款 ${vm.textOr(item.note.clause, '未提供')}` })
            : null,
          item.note && item.note.excerpt
            ? el('div', { class: 'wb-finding-meta', text: `摘录：${item.note.excerpt}` })
            : null,
        ]),
        copyButton(item.id, '复制 ID'),
      ]);
      return row;
    });
    container.appendChild(el('div', { class: 'wb-evidence-group' }, [
      el('h4', { text: `${group.title}（${group.items.length}）` }),
      el('div', { class: 'text-secondary small mb-2', text: group.note }),
      ...items,
    ]));
  }

  container.appendChild(paragraph(
    '页面只提供复制 ID；当前没有可直接访问的合同 PDF 下载接口，因此不放置会失败的文件按钮。',
    'text-secondary small mb-0',
  ));
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

/* ---------------------------------------------------------------- 审批 */

export function renderApproval(container, run, ctx = {}) {
  clear(container);
  if (!run) {
    container.appendChild(emptyState('尚未选择运行', '选择运行后查看审批草案与两级审批状态。'));
    return;
  }
  const model = vm.approvalModel(run);
  const report = run.report || {};

  container.appendChild(el('div', { class: 'd-flex flex-wrap align-items-center gap-2 mb-3' }, [
    el('span', { class: 'text-secondary small', text: '运行级审批状态：' }),
    statusBadge(model.statusMeta.state, model.statusMeta.label),
    el('span', { class: 'wb-mono text-secondary small', text: model.approvalStatus || '未提供' }),
  ]));

  if (model.draft) {
    const draftNote = `来自报告 proposed_draft（v${vm.textOr(model.draft.draft_version, '?')}、${vm.textOr(model.draft.action_type, '未提供')}）`;
    const variance = model.variance;
    container.appendChild(el('div', { class: 'wb-amount-pair mb-3' }, [
      el('div', { class: 'wb-amount-box' }, [
        el('div', { class: 'label', text: '审批草案金额' }),
        el('div', { class: 'value', text: `${vm.textOr(model.draft.amount, '未提供')} ${vm.textOr(model.draft.currency, '')}`.trim() }),
        el('div', { class: 'note', text: `${draftNote}；这是预设草案金额，不是差额的计算结论。` }),
      ]),
      el('div', { class: 'wb-amount-box' }, [
        el('div', { class: 'label', text: '账单核算差额 computed_variance' }),
        el('div', { class: 'value', text: variance || '未提供' }),
        el('div', { class: 'note', text: variance
          ? '来自报告 computed_variance，按字段原样展示，仅作对照。'
          : '报告未提供 computed_variance，不可推断为 0。' }),
      ]),
    ]));
  }

  if (!model.hasRequest) {
    if (report.error) {
      container.appendChild(el('div', { class: 'alert alert-danger' }, [
        el('div', { class: 'fw-bold', text: '报告未生成，没有审批记录' }),
        el('div', { class: 'small', text: `运行以 report.error 结束（${vm.textOr(report.error.code, '未提供错误码')}），本页不推测审批状态。` }),
      ]));
    } else if (model.approvalStatus === 'unavailable') {
      container.appendChild(el('div', { class: 'alert alert-warning' }, [
        el('div', { class: 'fw-bold', text: '本次运行没有接入审批通道' }),
        el('div', { class: 'small', text: '后端返回 approval_status = unavailable：草案只停留在报告中，未发起审批。可勾选「启用人工审批」后重新提交。' }),
      ]));
    } else if (model.approvalStatus === 'not_required' || !model.approvalStatus) {
      container.appendChild(el('div', { class: 'alert alert-secondary' }, [
        el('div', { class: 'fw-bold', text: '本次运行未要求人工审批' }),
        el('div', { class: 'small', text: '报告中没有 approval_request，approval_status 为 not_required 或未提供。' }),
      ]));
    } else {
      container.appendChild(el('div', { class: 'alert alert-warning' }, [
        el('div', { class: 'fw-bold', text: '审批状态存在但缺少请求对象' }),
        el('div', { class: 'small', text: `approval_status = ${model.approvalStatus}，但 report.approval_request 为空；本页不推测审批细节。` }),
      ]));
    }
    return;
  }

  const request = model.request;
  container.appendChild(kvList([
    ['请求', el('span', { class: 'wb-mono', text: vm.textOr(request.request_id, '未提供') })],
    ['动作类型', vm.textOr(request.action_type, '未提供')],
    ['草案', `v${vm.textOr(request.draft_version, '?')} · ${vm.textOr(request.draft_id, '未提供')}`],
    ['请求状态', `${vm.textOr(request.status, '未提供')}（request.status）`],
    ['创建时间', vm.formatTimestamp(request.created_at)],
    ['有效期至', vm.formatTimestamp(request.expires_at)],
    ['申请人', vm.textOr(request.requested_by, '未提供')],
  ]));

  container.appendChild(sectionTitle('两级串行审批', el('span', { class: 'text-secondary small', text: '物业 → 财务' })));
  for (const stage of model.stages) {
    container.appendChild(el('div', { class: 'wb-stage', dataset: { status: stage.status } }, [
      el('span', { class: 'wb-stage-index', text: String(stage.seq) }),
      el('div', { class: 'flex-fill min-w-0' }, [
        el('div', { class: 'd-flex flex-wrap align-items-center gap-2' }, [
          el('span', { class: 'fw-bold small', text: stage.roleLabel }),
          statusBadge(stage.state, stage.statusLabel),
          stage.decidedBy ? el('span', { class: 'text-secondary small', text: `审批人 ${stage.decidedBy}` }) : null,
        ]),
        stage.decidedAt ? el('div', { class: 'text-secondary small', text: `决定时间 ${vm.formatTimestamp(stage.decidedAt)}` }) : null,
        stage.reason ? el('div', { class: 'wb-finding-meta', text: `意见：${stage.reason}` }) : null,
      ]),
    ]));
  }

  if (model.approvedDraft) {
    const approved = model.approvedDraft;
    const effects = vm.asArray(approved.executed_side_effects);
    container.appendChild(el('div', { class: 'alert alert-success mt-3' }, [
      el('div', { class: 'fw-bold', text: `已批准草案（${vm.textOr(approved.status, '状态未提供')}）` }),
      el('div', { class: 'small', text: `业务副作用列表：${effects.length ? effects.join('、') : '空'}；批准不会执行真实调账。` }),
    ]));
    container.appendChild(el('details', { class: 'mb-3' }, [
      el('summary', { class: 'text-secondary small', text: '已批准草案 JSON' }),
      el('pre', { class: 'wb-pre mt-2', text: JSON.stringify(approved, null, 2) }),
    ]));
  }

  if (!model.canDecide) {
    container.appendChild(el('div', { class: 'alert alert-secondary mt-3 mb-0' }, [
      el('div', { class: 'fw-bold', text: '该审批请求当前不再接受操作' }),
      el('div', { class: 'small', text: `request.status = ${vm.textOr(model.requestStatus, '未提供')}。页面只保留状态与意见记录。` }),
    ]));
    return;
  }

  const allowlist = vm.asArray(ctx.meta && ctx.meta.approver_allowlist);
  if (!allowlist.length) {
    container.appendChild(el('div', { class: 'alert alert-warning mt-3 mb-0' }, [
      el('div', { class: 'fw-bold', text: '未取得审批人白名单' }),
      el('div', { class: 'small', text: 'GET /api/meta 未返回 approver_allowlist，页面不提供审批按钮，以免提交必然失败的请求。' }),
    ]));
    return;
  }
  const actorSelect = el('select', { class: 'form-select', attrs: { id: 'approval-actor' } },
    allowlist.map((actor) => el('option', { value: actor, text: actor })));
  if (model.nextStage) actorSelect.value = vm.actorForStage(allowlist, model.nextStage);

  const reasonInput = el('textarea', {
    class: 'form-control',
    rows: '2',
    attrs: { id: 'approval-reason', maxlength: '1000', placeholder: '审批意见会写入审批台账（可选）' },
  });

  const message = el('div', { class: 'mt-2 d-none', attrs: { role: 'alert' } });
  const approveBtn = el('button', { type: 'button', class: 'btn btn-primary', text: '批准' });
  const rejectBtn = el('button', { type: 'button', class: 'btn btn-outline-danger', text: '驳回' });

  let busy = false;
  const send = async (decision) => {
    if (busy) return;
    busy = true;
    approveBtn.disabled = true;
    rejectBtn.disabled = true;
    message.className = 'alert alert-info mt-2';
    message.textContent = decision === 'approve' ? '正在提交批准…' : '正在提交驳回…';
    try {
      await ctx.onDecide({
        decision,
        actor: actorSelect.value,
        reason: reasonInput.value.trim(),
        draftVersion: Number(request.draft_version),
      });
    } catch (error) {
      message.className = 'alert alert-danger mt-2';
      message.textContent = error && error.message ? error.message : '审批提交失败';
      const trace = error && error.traceId ? `（trace ${error.traceId}）` : '';
      if (trace) message.textContent += trace;
      busy = false;
      approveBtn.disabled = false;
      rejectBtn.disabled = false;
    }
  };
  approveBtn.addEventListener('click', () => send('approve'));
  rejectBtn.addEventListener('click', () => send('reject'));

  container.appendChild(el('div', { class: 'border-top mt-3 pt-3' }, [
    el('div', { class: 'row g-2' }, [
      el('div', { class: 'col-12 col-sm-6' }, [
        el('label', { class: 'form-label', attrs: { for: 'approval-actor' } }, [
          '审批人（服务端白名单）',
          model.nextStage ? el('span', { class: 'text-secondary small', text: ` · 当前阶段：${model.nextStage.roleLabel}` }) : null,
        ]),
        actorSelect,
      ]),
      el('div', { class: 'col-12 col-sm-6' }, [
        el('label', { class: 'form-label', attrs: { for: 'approval-reason' }, text: '审批意见' }),
        reasonInput,
      ]),
    ]),
    el('div', { class: 'btn-list mt-2' }, [approveBtn, rejectBtn]),
    message,
    el('div', { class: 'text-secondary small mt-2', text: '双角色串行：物业 → 财务，同一人不能连签两段；批准只产生草案状态，不执行真实调账。' }),
  ]));
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

  const subtaskIds = participation.subtasks.map((record) => record.subtaskId);
  nodes.push(kvList([
    ['角色', definition.title],
    ['职责', definition.duty],
    ['能力', definition.capability],
    ['子任务', subtaskIds.length ? subtaskIds.join('、') : '未提供'],
    ['状态', participation.participated
      ? `${participation.label}（${participation.subtasks.map((record) => record.terminal).join(' / ')}）`
      : '本次未参与'],
  ]));

  if (!participation.participated) {
    nodes.push(paragraph(
      '该 Agent 在本次运行的子任务记录（report.agent_results 与 report.failures）中都没有出现，'
      + '也没有可归属到它的工具记录。这是「未参与」，不是「执行成功」。',
      'text-secondary small',
    ));
    if (participation.unattributedTraces) {
      nodes.push(paragraph(
        `另有 ${participation.unattributedTraces} 条工具记录无法关联到任何子任务，未归入本节点（见「调用记录」）。`,
        'text-secondary small mb-0',
      ));
    }
    return nodes;
  }

  nodes.push(sectionTitle('子任务终态', el('span', { class: 'text-secondary small', text: `${participation.subtasks.length} 个` })));
  for (const record of participation.subtasks) {
    const stateLabel = record.terminal === 'success' ? '已完成'
      : record.terminal === 'partial' ? '部分完成'
        : record.terminal === 'failed' ? '失败'
          : record.terminal === 'unknown' ? '信息不足（无终态结果）' : '未参与';
    nodes.push(el('div', { class: 'wb-stage', dataset: { status: record.terminal } }, [
      el('span', { class: 'wb-stage-index', text: record.toolAttempts ? String(record.toolAttempts) : '·' }),
      el('div', { class: 'flex-fill min-w-0' }, [
        el('div', { class: 'd-flex flex-wrap align-items-center gap-2' }, [
          el('span', { class: 'wb-mono small', text: record.subtaskId }),
          statusBadge(record.terminal, stateLabel),
          record.capability ? el('span', { class: 'text-secondary small', text: record.capability }) : null,
        ]),
        el('div', { class: 'wb-finding-meta', text: `Agent 归属：${record.agentBasis === 'capability' ? '由 capability 对照 Agent 定义表' : record.agentBasis === 'agent_name' ? '由结果记录的 agent 字段' : '未提供可判定字段'} · 工具尝试 ${record.toolAttempts} 次 · 来源 ${record.sources.join(' / ') || '未提供'}` }),
        record.resolvedFailures.length
          ? el('div', { class: 'wb-finding-meta', text: `历史失败 ${record.resolvedFailures.length} 条（已被后续成功结果覆盖，仍可从 Trace 审计）：${record.resolvedFailures.map((item) => vm.textOr(item.error_code, '未提供')).join('、')}` })
          : null,
      ]),
    ]));
  }

  for (const record of participation.subtasks.filter((item) => item.failure)) {
    nodes.push(failureBlock(record.failure, { title: `子任务 ${record.subtaskId} 失败：${vm.textOr(record.failure.error_code, '未提供错误码')}` }));
  }

  const traces = participation.traces;
  nodes.push(sectionTitle('该 Agent 的工具调用', el('span', { class: 'text-secondary small', text: `${traces.length} 条` })));
  if (traces.length) {
    nodes.push(tracesTable(traces.map((trace, position) => ({
      index: position + 1,
      tool: vm.textOr(trace.tool, '未提供'),
      subtask: vm.textOr(trace.subtask_id, ''),
      status: vm.textOr(trace.status, '未提供'),
      attempt: trace.attempt === undefined ? '未提供' : String(trace.attempt),
      duration: vm.formatDuration(trace.duration_ms),
    }))));
  } else {
    nodes.push(paragraph('该领域的子任务没有工具调用记录（失败也可能发生在工具执行前）。', 'text-secondary small mb-0'));
  }

  if (conflicts.length) {
    nodes.push(sectionTitle('该领域的冲突', el('span', { class: 'text-secondary small', text: `${conflicts.length} 条` })));
    conflicts.forEach((conflict) => nodes.push(conflictItem(conflict)));
  }

  if (findings.length) {
    const bases = new Set(findings.map((entry) => entry.attribution.detail));
    nodes.push(sectionTitle('该领域的发现', el('span', { class: 'text-secondary small', text: `${findings.length} 条` })));
    nodes.push(paragraph(`归属依据：${[...bases].join('；')}`, 'text-secondary small'));
    findings.forEach((entry) => nodes.push(findingItem(entry.finding)));
  }

  return nodes;
}


export function renderNodeDetail(container, run, nodeId, ctx = {}) {
  clear(container);
  if (!run) {
    container.appendChild(paragraph('请选择一个运行节点。', 'text-secondary small mb-0'));
    return;
  }
  const report = run.report || {};
  const title = document.getElementById('node-detail-title');
  const sub = document.getElementById('node-detail-sub');
  const kicker = document.getElementById('node-detail-kicker');
  const nodes = [];

  if (nodeId === 'plan') {
    if (kicker) kicker.textContent = '流程结构 · 规划';
    if (title) title.textContent = '任务规划';
    const index = vm.buildSubtaskIndex(run);
    const counts = index.counts;
    if (sub) sub.textContent = `${report.route ? `路由 ${report.route} · ` : ''}已记录 ${counts.subtasks} 个子任务`;
    nodes.push(paragraph(
      '规划节点没有独立的可观测事件，以下信息来自返回报告中的 route 与 agent_results / failures，'
      + '按真实 subtask_id 去重；报告未提供原始计划数组，因此这里是「已记录子任务」而不是规划总数。',
      'text-secondary small',
    ));
    nodes.push(kvList([
      ['路由 route', vm.textOr(report.route, '未提供')],
      ['修订次数 revision', report.revision === undefined ? '未提供' : String(report.revision)],
      ['已记录子任务', `${counts.subtasks} 个（有终态结果 ${counts.results} · 当前未解决失败 ${counts.failures}）`],
      ['工具尝试', `${counts.traces} 次`],
      ['规划器', '确定性规则匹配（根据问题关键词选择领域）'],
    ]));
    if (!counts.subtasks) {
      nodes.push(paragraph('报告没有子任务记录（可能未进入执行阶段）。', 'text-secondary small mb-0'));
    }
    for (const record of index.records) {
      const definition = record.agentKey ? vm.agentDefinitionByKey(record.agentKey) : null;
      nodes.push(el('div', { class: 'wb-finding', dataset: { kind: record.terminal === 'failed' ? 'failure' : 'note' } }, [
        el('div', { class: 'wb-finding-statement' }, [
          el('span', { class: 'wb-mono', text: record.subtaskId }),
          ` · ${vm.textOr(record.capability, '能力未提供')}`,
          ` · ${definition ? definition.title : 'Agent 未确定'}`,
        ]),
        el('div', { class: 'wb-finding-meta', text: `终态 ${record.terminal}${record.failure ? ` · 错误码 ${vm.textOr(record.failure.error_code, '未提供')}` : ''} · 工具尝试 ${record.toolAttempts} 次` }),
      ]));
    }
  } else if (nodeId.startsWith('agent:')) {

    const key = nodeId.slice('agent:'.length);
    const definition = vm.AGENT_DEFS.find((item) => item.key === key);
    if (!definition) {
      container.appendChild(paragraph('未知节点。', 'text-secondary small mb-0'));
      return;
    }
    if (kicker) kicker.textContent = '领域 Agent 详情';
    if (title) title.textContent = definition.title;
    if (sub) sub.textContent = definition.duty;
    nodes.push(...agentSummarySection(run, definition));
  } else if (nodeId === 'verify') {
    if (kicker) kicker.textContent = '结果回顾 · 核验';
    if (title) title.textContent = '证据核验';
    if (sub) sub.textContent = '来自报告的 verdict / conflicts / missing_information / failures';
    nodes.push(paragraph('核验节点同样没有独立实时事件，以下内容按返回报告回顾。', 'text-secondary small'));
    if (report.error) {
      nodes.push(el('div', { class: 'alert alert-danger mb-0' }, [
        el('div', { class: 'fw-bold small', text: '报告未生成，无法核验' }),
        el('div', { class: 'small', text: `报告只包含 error 字段：${vm.textOr(report.error.code, '未提供错误码')}` }),
      ]));
    } else {
      const verdict = vm.verdictMeta(report.verdict);
      const completeness = vm.completenessMeta(report.completeness);
      const index = vm.buildSubtaskIndex(run);
      const provided = (value) => (Array.isArray(value) ? `${value.length} 条` : '未提供');
      nodes.push(kvList([
        ['证据结论', `${verdict.label}（${vm.textOr(report.verdict, '未提供')}）`],
        ['完整度', `${completeness.label}（${vm.textOr(report.completeness, '未提供')}）`],
        ['冲突 conflicts', provided(report.conflicts)],
        ['资料缺失 missing_information', provided(report.missing_information)],
        ['叙述与字段差异', provided(report.narrative_discrepancies)],
        ['当前未解决失败', `${index.counts.failures} 个（按 subtask_id 去重）`],
        ['需要人工复核', report.requires_human_review === true ? '是' : report.requires_human_review === false ? '否' : '未提供'],
      ]));
      const conflicts = vm.asArray(report.conflicts);
      if (conflicts.length) {
        nodes.push(sectionTitle('冲突明细'));
        conflicts.forEach((conflict) => nodes.push(conflictItem(conflict)));
      }
      const missing = vm.asArray(report.missing_information);
      if (missing.length) {
        nodes.push(sectionTitle('资料缺失'));
        missing.forEach((item) => nodes.push(stringItem(item, 'missing')));
      }
      const failures = vm.asArray(report.failures);
      if (failures.length) {
        nodes.push(sectionTitle('失败子任务'));
        failures.forEach((failure) => nodes.push(failureItem(failure)));
      }
      const amounts = vm.asArray(report.authoritative_amounts);
      if (amounts.length) {
        nodes.push(sectionTitle('结构化金额'));
        amounts.forEach((item) => nodes.push(el('div', { class: 'wb-finding', dataset: { kind: 'note' } }, [
          el('div', { class: 'wb-finding-statement', text: vm.textOr(item.rendered, '未提供渲染结果') }),
          el('div', { class: 'wb-finding-meta', text: `字段核对 ${vm.textOr(item.check_status, '未提供')}` }),
        ])));
      }
    }
  } else if (nodeId === 'report') {
    if (kicker) kicker.textContent = '结果回顾 · 报告';
    if (title) title.textContent = '调查报告';
    if (sub) sub.textContent = '事实、冲突与缺失的汇总结果';
    if (report.error) {
      nodes.push(el('div', { class: 'alert alert-danger mb-0' }, [
        el('div', { class: 'fw-bold small', text: '报告未生成' }),
        el('div', { class: 'small', text: `错误码 ${vm.textOr(report.error.code, '未提供')} · ${vm.textOr(report.error.message, '未提供错误说明')}` }),
      ]));
    } else {
      nodes.push(kvList([
        ['发现数量', String(vm.asArray(report.findings).length)],
        ['冲突数量', Array.isArray(report.conflicts) ? String(report.conflicts.length) : '未提供'],
        ['缺失数量', Array.isArray(report.missing_information) ? String(report.missing_information.length) : '未提供'],
        ['提醒数量', String(vm.asArray(report.warnings).length)],
        ['声明', vm.textOr(report.disclaimer, '未提供')],
      ]));
    }
    if (report.proposed_draft) {
      nodes.push(el('div', { class: 'alert alert-warning mt-2 mb-0' }, [
        el('div', { class: 'fw-bold small', text: '报告附带一份审批草案' }),
        el('div', { class: 'small', text: `草案金额 ${vm.textOr(report.proposed_draft.amount, '未提供')} ${vm.textOr(report.proposed_draft.currency, '')}，见下方「审批」标签页；草案金额不是差额计算结论。` }),

      ]));
    }
    nodes.push(paragraph('完整的发现、证据与原始 JSON 在下方「调查报告与证据」卡片中。', 'text-secondary small mt-2 mb-0'));
  } else if (nodeId === 'approval') {
    if (kicker) kicker.textContent = '人工审批';
    if (title) title.textContent = '人工审批';
    const model = vm.approvalModel(run);
    if (sub) sub.textContent = model.statusMeta.label;
    if (!model.hasRequest) {
      nodes.push(paragraph(report.error
        ? '报告未生成，后端没有产生审批状态。'
        : model.approvalStatus === 'unavailable'
          ? '本次运行没有接入审批通道（approval_status = unavailable），草案只停留在报告中。'
          : `本次运行没有审批请求（approval_status = ${vm.textOr(model.approvalStatus, '未提供')}）。`, 'text-secondary small mb-0'));
    } else {
      nodes.push(kvList([
        ['请求', el('span', { class: 'wb-mono', text: vm.textOr(model.request.request_id, '未提供') })],
        ['请求状态', vm.textOr(model.requestStatus, '未提供')],
        ['草案版本', `v${vm.textOr(model.request.draft_version, '?')}`],
        ['草案金额', `${vm.textOr(model.request.amount, '未提供')} ${vm.textOr(model.request.currency, '')}`],
        ['核算差额', model.variance || '未提供'],
        ['下一级', model.nextStage ? model.nextStage.roleLabel : '无待处理阶段'],
      ]));
      for (const stage of model.stages) {
        nodes.push(el('div', { class: 'wb-stage', dataset: { status: stage.status } }, [
          el('span', { class: 'wb-stage-index', text: String(stage.seq) }),
          el('div', { class: 'flex-fill' }, [
            el('div', { class: 'd-flex flex-wrap align-items-center gap-2' }, [
              el('span', { class: 'fw-bold small', text: stage.roleLabel }),
              statusBadge(stage.state, stage.statusLabel),
            ]),
            stage.decidedBy ? el('div', { class: 'text-secondary small', text: `审批人 ${stage.decidedBy} · ${vm.formatTimestamp(stage.decidedAt)}` }) : null,
            stage.reason ? el('div', { class: 'wb-finding-meta', text: `意见：${stage.reason}` }) : null,
          ]),
        ]));
      }
      nodes.push(paragraph('审批操作在下方「审批」标签页完成。', 'text-secondary small mt-2 mb-0'));
    }
  }

  nodes.filter(Boolean).forEach((node) => container.appendChild(node));
}
