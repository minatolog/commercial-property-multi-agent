/**
 * 案件头、流程步骤条、结论卡（Task 032）
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

const TONE_ICON = {
  success: '✓',
  warning: '!',
  failed: '✕',
  unknown: '?',
  idle: '·',
};

export function renderCards(container, cards) {
  clear(container);
  for (const card of cards) {
    const value = el('div', { class: 'wb-card-value' }, [
      el('span', { text: card.value }),
    ]);
    if (card.key === 'amount' && card.direction && card.direction !== 'unknown') {
      value.dataset.direction = card.direction;
    }
    container.appendChild(el('article', { class: 'wb-card', dataset: { tone: card.tone || 'unknown', key: card.key } }, [
      el('div', { class: 'wb-card-head' }, [
        el('span', { class: 'wb-card-icon', attrs: { 'aria-hidden': 'true' }, text: TONE_ICON[card.tone] || '?' }),
        el('h3', { class: 'wb-card-title', text: card.title }),
        card.label ? el('span', { class: 'wb-card-tag', text: card.label }) : null,
      ]),
      value,
      card.note ? el('div', { class: 'wb-card-note', text: card.note }) : null,
      card.draft ? el('div', { class: 'wb-card-draft', text: card.draft }) : null,
    ]));
  }
}
