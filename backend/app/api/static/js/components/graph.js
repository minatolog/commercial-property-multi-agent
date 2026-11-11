/**
 * Agent 协作画布（Task 027）
 *
 * 视觉组织参考 Langflow 的「节点 + 端口 + 有向连线 + 详情面板」，
 * 代码为本项目自写：节点来自 index.html 的固定职责图，连线由本模块按实际布局绘制。
 *
 * 画布只表达「谁负责什么、本次谁真的参与了」，不是可拖拽的通用编排器；
 * 也没有任何按定时器推进的假进度。
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

const EDGES = [
  ['plan', 'agent:lease'],
  ['plan', 'agent:billing'],
  ['plan', 'agent:property'],
  ['verify', 'report'],
  ['report', 'approval'],
];

const AGENT_NODES = ['agent:lease', 'agent:billing', 'agent:property'];

/**
 * 该节点是否「真的走到」：idle=还没运行，pending=等待结果，not_called=本次未参与，
 * unknown=缺少可判定的终态信息（不推断为已执行）。
 */
function reached(stateKey) {
  return Boolean(stateKey)
    && stateKey !== 'idle'
    && stateKey !== 'pending'
    && stateKey !== 'not_called'
    && stateKey !== 'unknown';
}

let currentModel = null;

export function renderGraph(canvas, svg, model) {
  currentModel = model;
  for (const node of canvas.querySelectorAll('.wb-node')) {
    const id = node.dataset.node;
    const info = (model && model.nodes && model.nodes[id]) || { state: 'idle', label: '等待运行' };
    node.dataset.state = info.state;
    const badge = node.querySelector('.wb-status');
    if (badge) {
      badge.dataset.status = info.state;
      badge.textContent = info.label;
    }
  }
  window.requestAnimationFrame(() => drawLinks(canvas, svg, model));
}

export function initGraphResize(canvas, svg) {
  const redraw = () => {
    if (currentModel) drawLinks(canvas, svg, currentModel);
  };
  if (typeof ResizeObserver === 'function') {
    new ResizeObserver(redraw).observe(canvas);
  }
  window.addEventListener('resize', redraw);
  window.addEventListener('load', redraw);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(redraw).catch(() => {});
}

function marker(svg, id, color) {
  const defs = svg.querySelector('defs') || svg.appendChild(document.createElementNS(SVG_NS, 'defs'));
  const existing = svg.querySelector(`#${id}`);
  if (existing) return;
  const mark = document.createElementNS(SVG_NS, 'marker');
  mark.setAttribute('id', id);
  mark.setAttribute('viewBox', '0 0 10 10');
  mark.setAttribute('refX', '8');
  mark.setAttribute('refY', '5');
  mark.setAttribute('markerWidth', '6');
  mark.setAttribute('markerHeight', '6');
  mark.setAttribute('orient', 'auto-start-reverse');
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
  path.setAttribute('fill', color);
  mark.appendChild(path);
  defs.appendChild(mark);
}

function drawLinks(canvas, svg, model) {
  const style = window.getComputedStyle(svg);
  if (style.display === 'none') {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    return;
  }
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;

  while (svg.firstChild) svg.removeChild(svg.firstChild);
  svg.setAttribute('viewBox', `0 0 ${Math.round(bounds.width)} ${Math.round(bounds.height)}`);
  marker(svg, 'wb-arrow', '#94a9c4');
  marker(svg, 'wb-arrow-muted', '#cbd5e1');

  const nodes = new Map();
  for (const node of canvas.querySelectorAll('.wb-node')) {
    nodes.set(node.dataset.node, node);
  }

  for (const [fromId, toId] of EDGES) {
    const from = nodes.get(fromId);
    const to = nodes.get(toId);
    if (!from || !to) continue;

    const a = from.getBoundingClientRect();
    const b = to.getBoundingClientRect();
    const stateOf = (id) => (model && model.nodes && model.nodes[id] && model.nodes[id].state) || 'idle';
    // 一条连线只有在「起点和终点都真的走到」时才算本次流程的一部分；
    // 未参与领域的分支保留为虚线，避免把未调用的 Agent 画成已执行。
    const active = !(model && model.pending) && reached(stateOf(fromId)) && reached(stateOf(toId));

    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('class', `wb-link ${active ? 'is-active' : 'is-inactive'}`);
    path.setAttribute('marker-end', `url(#${active ? 'wb-arrow' : 'wb-arrow-muted'})`);

    const sameRow = Math.abs((a.top + a.height / 2) - (b.top + b.height / 2)) < 12 && b.left > a.right - 2;
    if (sameRow) {
      const sx = a.right - bounds.left;
      const sy = a.top - bounds.top + a.height / 2;
      const tx = b.left - bounds.left;
      const ty = b.top - bounds.top + b.height / 2;
      const midX = (sx + tx) / 2;
      path.setAttribute('d', `M ${sx} ${sy} C ${midX} ${sy}, ${midX} ${ty}, ${tx - 2} ${ty}`);
    } else {
      const sx = a.left - bounds.left + a.width / 2;
      const sy = a.bottom - bounds.top;
      const tx = b.left - bounds.left + b.width / 2;
      const ty = b.top - bounds.top;
      const control = Math.max(12, (ty - sy) * 0.55);
      path.setAttribute('d', `M ${sx} ${sy} C ${sx} ${sy + control}, ${tx} ${ty - control}, ${tx} ${ty - 4}`);
    }
    svg.appendChild(path);
  }

  drawMerge(svg, nodes, bounds, model);
}

/**
 * 三个领域 → 证据核验的合并：用「正交母线」表达多对一，
 * 避免三条曲线横穿「各领域结果合并」说明文字。
 */
function drawMerge(svg, nodes, bounds, model) {
  const verify = nodes.get('verify');
  if (!verify) return;
  const stateOf = (id) => (model && model.nodes && model.nodes[id] && model.nodes[id].state) || 'idle';

  const verifyRect = verify.getBoundingClientRect();
  const sources = AGENT_NODES
    .map((id) => ({ id, node: nodes.get(id) }))
    .filter((item) => item.node)
    .map((item) => ({ id: item.id, rect: item.node.getBoundingClientRect(), state: stateOf(item.id) }));

  if (!sources.length) return;
  const bottom = Math.max(...sources.map((item) => item.rect.bottom)) - bounds.top;
  const verifyTop = verifyRect.top - bounds.top;
  const busY = bottom + Math.max(8, (verifyTop - bottom) * 0.4);
  const verifyX = verifyRect.left - bounds.left + verifyRect.width / 2;
  const anyActive = !(model && model.pending) && sources.some((item) => reached(item.state));

  const line = (d, active) => {
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('class', `wb-link ${active ? 'is-active' : 'is-inactive'}`);
    path.setAttribute('d', d);
    svg.appendChild(path);
  };

  for (const source of sources) {
    const x = source.rect.left - bounds.left + source.rect.width / 2;
    const active = !(model && model.pending) && reached(source.state);
    // 未参与的领域只留一小段虚线「支路」，不接到合并母线上
    const end = active ? busY : busY - 10;
    line(`M ${x} ${source.rect.bottom - bounds.top} L ${x} ${end}`, active);
  }

  const activeXs = sources
    .filter((source) => !(model && model.pending) && reached(source.state))
    .map((source) => source.rect.left - bounds.left + source.rect.width / 2);
  if (activeXs.length) {
    const span = [...activeXs, verifyX];
    line(`M ${Math.min(...span)} ${busY} L ${Math.max(...span)} ${busY}`, true);
  }

  const arrow = document.createElementNS(SVG_NS, 'path');
  arrow.setAttribute('class', `wb-link ${anyActive ? 'is-active' : 'is-inactive'}`);
  arrow.setAttribute('marker-end', `url(#${anyActive ? 'wb-arrow' : 'wb-arrow-muted'})`);
  arrow.setAttribute('d', `M ${verifyX} ${busY} L ${verifyX} ${verifyTop - 4}`);
  svg.appendChild(arrow);
}
