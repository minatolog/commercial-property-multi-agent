/**
 * 案件概览与流程步骤。
 *
 * 只渲染 case-status.js 给出的模型；不在这里做任何判断，也不计算金额。
 * 全部用 textContent 写入（经 dom.el）。
 */

import { el, clear } from '../dom.js';

/** 每种状态都同时有文字和图标，不只靠颜色 */
const STEP_ICON = {
  done: '✓',
  current: '●',
  waiting: '○',
  warning: '!',
  failed: '✕',
  unknown: '?',
  not_involved: '–',
  skipped: '–',
};

const STEP_STATE_TEXT = {
  done: '已完成',
  current: '进行中',
  waiting: '待开始',
  warning: '需关注',
  failed: '失败 / 驳回',
  unknown: '未知',
  not_involved: '本次不涉及',
  skipped: '未进行',
};

export function renderSteps(container, steps) {
  clear(container);
  steps.forEach((item, index) => {
    container.appendChild(el('li', {
      class: 'wb-step',
      dataset: { state: item.state },
      attrs: { 'aria-current': item.state === 'current' ? 'step' : null },
    }, [
      el('span', { class: 'wb-step-marker', attrs: { 'aria-hidden': 'true' }, text: STEP_ICON[item.state] || '?' }),
      el('span', { class: 'wb-step-text' }, [
        el('span', { class: 'wb-step-title' }, [
          el('span', { class: 'wb-step-index', text: `${index + 1}` }),
          item.title,
        ]),
        el('span', { class: 'wb-step-detail', text: item.detail || STEP_STATE_TEXT[item.state] || '' }),
        el('span', { class: 'visually-hidden', text: `（${STEP_STATE_TEXT[item.state] || '未知'}）` }),
      ]),
    ]));
  });
}

export function renderOverview(container, [verdict, amount, gaps, next]) {
  const showAmount = amount.direction || (amount.tone === 'unknown' && verdict.tone === 'warning');
  const gapText = gaps.tone === 'warning' || gaps.value === '待核实'
    ? `资料缺口 ${gaps.value}`
    : '';
  const actionText = next.tone === 'warning' || next.tone === 'failed' ? next.value : '';
  const context = [gapText, actionText].filter(Boolean).join(' · ');

  container.appendChild(el('div', { class: 'wb-overview-copy' }, [
    el('div', { class: 'wb-overview-label', text: '调查结论' }),
    el('h2', { class: 'wb-overview-title', text: verdict.value }),
    verdict.note ? el('p', { class: 'wb-overview-note', text: verdict.note }) : null,
    context ? el('p', { class: 'wb-overview-context', text: context }) : null,
  ]));
  if (showAmount) {
    container.appendChild(el('div', { class: 'wb-overview-amount' }, [
      el('div', { class: 'wb-overview-label', text: amount.label || amount.title }),
      el('div', { class: 'wb-overview-value', dataset: { direction: amount.direction || '' }, text: amount.value }),
      amount.note ? el('p', { class: 'wb-overview-note', text: amount.note }) : null,
    ]));
  }
}
