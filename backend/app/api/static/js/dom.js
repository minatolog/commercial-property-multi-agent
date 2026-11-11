/**
 * 极小的 DOM 构建工具（Task 027）
 *
 * 全站只用 `textContent` 写入用户/后端文本，不拼 innerHTML，
 * 因此问题原文、证据摘录和错误信息都不会被当作 HTML 执行。
 */

export function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') node.className = value;
    else if (key === 'text') node.textContent = String(value);
    else if (key === 'dataset') Object.assign(node.dataset, value);
    else if (key === 'on') {
      for (const [event, handler] of Object.entries(value)) node.addEventListener(event, handler);
    } else if (key === 'attrs') {
      for (const [name, attrValue] of Object.entries(value)) {
        if (attrValue === null || attrValue === undefined || attrValue === false) continue;
        node.setAttribute(name, String(attrValue));
      }
    } else {
      node.setAttribute(key, String(value));
    }
  }
  return append(node, children);
}

export function append(node, children) {
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(
      typeof child === 'string' || typeof child === 'number'
        ? document.createTextNode(String(child))
        : child,
    );
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

export function statusBadge(state, label) {
  return el('span', { class: 'badge wb-status', dataset: { status: state }, text: label });
}

export function emptyState(title, subtitle) {
  return el('div', { class: 'empty py-3' }, [
    el('div', { class: 'empty-title', text: title }),
    subtitle ? el('div', { class: 'empty-subtitle text-secondary small', text: subtitle }) : null,
  ]);
}

export function sectionTitle(text, extra) {
  return el('div', { class: 'd-flex align-items-center justify-content-between gap-2 mt-1 mb-2' }, [
    el('h4', { class: 'mb-0', attrs: { style: 'font-size:13px' }, text }),
    extra || null,
  ]);
}

export function paragraph(text, className = 'text-secondary small mb-2') {
  return el('p', { class: className, text });
}

export function codeChip(text) {
  return el('span', { class: 'wb-chip', text });
}

/** 可访问的复制按钮：失败时明确提示，不假装成功 */
export function copyButton(value, label = '复制') {
  const button = el('button', {
    type: 'button',
    class: 'btn btn-sm btn-ghost-secondary',
    text: label,
    attrs: { 'aria-label': `${label}: ${String(value).slice(0, 60)}` },
  });
  button.addEventListener('click', async () => {
    const ok = await copyText(String(value));
    const original = label;
    button.textContent = ok ? '已复制' : '复制失败';
    button.disabled = true;
    window.setTimeout(() => {
      button.textContent = original;
      button.disabled = false;
    }, 1400);
  });
  return button;
}

async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* 回退到 execCommand */
  }
  try {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', 'readonly');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}

export function kvList(entries) {
  const dl = el('dl', { class: 'wb-kv' });
  for (const [label, value] of entries) {
    if (value === null || value === undefined) continue;
    dl.appendChild(el('dt', { text: label }));
    dl.appendChild(typeof value === 'string' || typeof value === 'number'
      ? el('dd', { text: String(value) })
      : el('dd', {}, [value]));
  }
  return dl;
}
