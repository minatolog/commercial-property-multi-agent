# -*- coding: utf-8 -*-
"""生成本目录下的三张架构图（Pillow 手绘，不依赖 graphviz / mermaid / 网络）。

用法（任意目录）：
    python docs/architecture/diagrams/build_diagrams.py [overview|workflow|tree ...]
不加参数则三张全部重绘。需要 Pillow 与中文字体（默认 Windows 微软雅黑）。

输出：
    01_overview.png      系统分层总览
    02_workflow.png      一次调查的 LangGraph 工作流
    03_directories.png   仓库目录结构
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent
ROOT = OUT_DIR.parents[2]

FONT_REG = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

INK = (31, 41, 51)
INK_SOFT = (75, 85, 99)
INK_FAINT = (138, 148, 160)
ARROW = (88, 104, 126)
DASH = (152, 165, 182)
WHITE = (255, 255, 255)
BAND_FILL = (247, 249, 252)
BAND_LINE = (219, 227, 236)


class Tone:
    def __init__(self, fill, border, title):
        self.fill = fill
        self.border = border
        self.title = title


ENTRY = Tone((232, 240, 254), (47, 95, 191), (23, 55, 107))
SERVICE = Tone((238, 243, 250), (74, 111, 165), (30, 58, 95))
ORCH = Tone((255, 244, 229), (201, 122, 22), (122, 66, 10))
AGENT = Tone((232, 245, 233), (46, 125, 50), (24, 90, 32))
RUNTIME = Tone((241, 235, 250), (106, 63, 181), (67, 36, 124))
TOOL = Tone((253, 234, 234), (179, 38, 30), (120, 25, 20))
DATA = Tone((227, 242, 244), (0, 112, 124), (0, 77, 86))
EVAL = Tone((240, 240, 242), (95, 99, 104), (52, 55, 59))
CTRL = Tone((255, 250, 235), (176, 124, 16), (110, 75, 5))
MUTED = Tone((246, 246, 247), (170, 176, 184), (90, 96, 104))

_FONTS: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (size, bold)
    if key not in _FONTS:
        _FONTS[key] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    return _FONTS[key]


def line_h(f: ImageFont.FreeTypeFont) -> int:
    ascent, descent = f.getmetrics()
    return ascent + descent + 3


_TOKEN = re.compile(r"[A-Za-z0-9_\.\-/<>=+|·%]+|\s+|.", re.S)


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    lines: list[str] = []
    cur = ""
    for tok in _TOKEN.findall(text):
        cand = cur + tok
        if f.getlength(cand) <= max_w or not cur:
            cur = cand
            continue
        if tok.isspace():
            lines.append(cur.rstrip())
            cur = ""
        else:
            lines.append(cur.rstrip())
            cur = tok
    if cur.strip():
        lines.append(cur.rstrip())
    return lines or [""]


def measure_card(title: str, subs: list[str], w: int, *, ts: int = 20, bs: int = 14,
                 pad: int = 15, gap: int = 7) -> int:
    tf, bf = font(ts, True), font(bs)
    inner = w - 2 * pad
    tl = wrap(title, tf, inner)
    sl: list[str] = []
    for s in subs:
        sl.extend(wrap(s, bf, inner))
    return pad * 2 + len(tl) * line_h(tf) + (gap + len(sl) * line_h(bf) if sl else 0)


def draw_card(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, title: str,
              subs: list[str], tone: Tone, *, ts: int = 20, bs: int = 14,
              pad: int = 15, gap: int = 7) -> None:
    d.rounded_rectangle([x, y, x + w, y + h], radius=13, fill=tone.fill,
                        outline=tone.border, width=2)
    tf, bf = font(ts, True), font(bs)
    inner = w - 2 * pad
    tl = wrap(title, tf, inner)
    sl: list[str] = []
    for s in subs:
        sl.extend(wrap(s, bf, inner))
    total = len(tl) * line_h(tf) + (gap + len(sl) * line_h(bf) if sl else 0)
    cy = y + (h - total) / 2
    for line in tl:
        d.text((x + w / 2, cy), line, font=tf, fill=tone.title, anchor="ma")
        cy += line_h(tf)
    cy += gap
    for line in sl:
        d.text((x + w / 2, cy), line, font=bf, fill=INK_SOFT, anchor="ma")
        cy += line_h(bf)


def dashed_line(d: ImageDraw.ImageDraw, x1: float, y1: float, x2: float, y2: float,
                fill, width: int = 3, dash: int = 9, space: int = 7) -> None:
    length = math.hypot(x2 - x1, y2 - y1)
    if length == 0:
        return
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    pos = 0.0
    while pos < length:
        end = min(pos + dash, length)
        d.line([(x1 + ux * pos, y1 + uy * pos), (x1 + ux * end, y1 + uy * end)],
               fill=fill, width=width)
        pos = end + space


def arrow(d: ImageDraw.ImageDraw, x1: float, y1: float, x2: float, y2: float, *,
          color=ARROW, width: int = 3, head: int = 13, dashed: bool = False) -> None:
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    ex, ey = x2 - ux * head * 0.85, y2 - uy * head * 0.85
    if dashed:
        dashed_line(d, x1, y1, ex, ey, color, width)
    else:
        d.line([(x1, y1), (ex, ey)], fill=color, width=width)
    lx, ly = x2 - ux * head + uy * head * 0.55, y2 - uy * head - ux * head * 0.55
    rx, ry = x2 - ux * head - uy * head * 0.55, y2 - uy * head + ux * head * 0.55
    d.polygon([(x2, y2), (lx, ly), (rx, ry)], fill=color)


def edge_label(d: ImageDraw.ImageDraw, cx: float, cy: float, text: str, *,
               size: int = 14, color=INK_SOFT, bg=WHITE, pad: int = 5) -> None:
    f = font(size)
    tw = f.getlength(text)
    h = line_h(f)
    d.rounded_rectangle([cx - tw / 2 - pad, cy - h / 2 - 2, cx + tw / 2 + pad, cy + h / 2 + 2],
                        radius=7, fill=bg, outline=(226, 232, 240), width=1)
    d.text((cx, cy - 1), text, font=f, fill=color, anchor="mm")


def pill(d: ImageDraw.ImageDraw, cx: int, cy: int, text: str, *, fill, outline,
         color=WHITE, size: int = 18, pad_x: int = 18, pad_y: int = 8) -> tuple[float, float, float, float]:
    f = font(size, True)
    tw = f.getlength(text)
    h = line_h(f) + pad_y * 2
    w = tw + pad_x * 2
    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    d.rounded_rectangle(box, radius=h / 2, fill=fill, outline=outline, width=2)
    d.text((cx, cy - 1), text, font=f, fill=color, anchor="mm")
    return box


def band(d: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, name: str,
         tone: Tone, idx: str) -> None:
    d.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=BAND_FILL,
                        outline=BAND_LINE, width=2)
    sx, sw = x + 12, 124
    d.rounded_rectangle([sx, y + 12, sx + sw, y + h - 12], radius=13, fill=WHITE,
                        outline=tone.border, width=2)
    d.rounded_rectangle([sx, y + 12, sx + 6, y + h - 12], radius=3, fill=tone.border)
    label_f = font(19, True)
    lines = wrap(name, label_f, sw - 26)
    idx_f = font(12, True)
    total = line_h(idx_f) + sum(line_h(label_f) for _ in lines)
    cy = y + h / 2 - total / 2
    d.text((sx + sw / 2 + 2, cy), idx, font=idx_f, fill=INK_FAINT, anchor="ma")
    cy += line_h(idx_f) + 2
    for line in lines:
        d.text((sx + sw / 2 + 2, cy), line, font=label_f, fill=tone.title, anchor="ma")
        cy += line_h(label_f)


def title_block(d: ImageDraw.ImageDraw, x: int, y: int, w: int, title: str, subtitle: str,
                tag: str) -> None:
    d.text((x, y), title, font=font(32, True), fill=(20, 32, 48), anchor="la")
    d.text((x, y + 48), subtitle, font=font(15), fill=INK_SOFT, anchor="la")
    f = font(13, True)
    tw = f.getlength(tag)
    d.rounded_rectangle([x + w - tw - 26, y + 6, x + w, y + 32], radius=13,
                        fill=(240, 244, 250), outline=(203, 213, 225), width=1)
    d.text((x + w - 13, y + 19), tag, font=f, fill=(70, 86, 110), anchor="rm")


class Row:
    """一行卡片。每项为 (标题, 副文本, 权重)；宽度按权重分配并填满整行。"""

    def __init__(self, *items: tuple[str, list[str], int], gap: int = 18) -> None:
        self.items = items
        self.gap = gap

    def widths(self, total_w: int) -> list[int]:
        n = len(self.items)
        usable = total_w - self.gap * (n - 1)
        weight = sum(w for _, _, w in self.items)
        return [int(usable * w / weight) for _, _, w in self.items]

    def height(self, total_w: int, *, ts: int = 20, bs: int = 14) -> int:
        return max(measure_card(t, s, w, ts=ts, bs=bs)
                   for (t, s, _), w in zip(self.items, self.widths(total_w)))

    def draw(self, d: ImageDraw.ImageDraw, x: int, y: int, total_w: int, h: int,
             tone: Tone, *, ts: int = 20, bs: int = 14) -> None:
        cx = x
        for (t, s, _), w in zip(self.items, self.widths(total_w)):
            draw_card(d, int(cx), y, w, h, t, s, tone, ts=ts, bs=bs)
            cx += w + self.gap


# --------------------------------------------------------------------------- #
# 图 1：系统分层总览
# --------------------------------------------------------------------------- #

BANDS = [
    dict(idx="01", name="入口 / 交互", tone=ENTRY, full=True, gap=34, rows=[
        Row(("CLI 命令行", ["backend/app/cli.py",
                            "tools · check · demo · ask · investigate",
                            "search · approve · pending · evaluate"], 1),
            ("演示 API（FastAPI）", ["backend/app/api/app.py",
                                    "7 个 HTTP 路由：runs / traces / approvals",
                                    "身份由服务端注入，请求不能自报"], 1),
            ("协作工作台页面", ["backend/app/api/static/",
                               "同源 HTML + JS + CSS · Tabler 1.7.4 本地化",
                               "经 DisplayBuilder 只读投影"], 1)),
    ]),
    dict(idx="02", name="服务 / 装配", tone=SERVICE, full=True, gap=34, rows=[
        Row(("WorkflowService", ["api/service.py", "展示层唯一入口", "RunIndex 只是投影"], 1),
            ("装配与演示", ["investigation_demo.py", "single_demo.py · demo.py",
                          "建图 / 建 Registry / 注入模型"], 1),
            ("配置与校验", ["config/ 5 个 Agent YAML", "planner.yaml · Pydantic Schema",
                          "拒绝密钥与未实现能力"], 1),
            ("环境与路径", ["env.py · paths.py", ".env 读取（环境变量优先）",
                          "data/ 与 docs/ 路径解析"], 1)),
    ]),
    dict(idx="03", name="编排层", tone=ORCH, full=False, gap=34, rows=[
        Row(("LangGraph 调查图", ["orchestration/investigation.py", "9 节点 · 真实条件分支",
                                "Send 并发扇出 · 合流等齐"], 1),
            ("规划层", ["RuleBasedPlanner（默认 rule）", "LLM Supervisor / 混合规划",
                      "submit_plan 结构化 · 失败回退"], 1),
            ("确定性核验", ["verify_results", "冲突 / 缺失 / 完整性", "补查硬上限 ≤ 1 次"], 1),
            ("审批门", ["orchestration/approval.py", "两级串行 · 版本绑定 · 幂等",
                      "只出 approved_draft"], 1)),
    ]),
    dict(idx="04", name="Agent 层", tone=AGENT, full=False, gap=34, rows=[
        Row(("AgentRegistry + Factory", ["按 capability 解析，不耦合具体类",
                                         "静态白名单 + 依赖注入"], 1),
            ("共享契约 agents/base/", ["contracts · scope · evidence",
                                    "facts · conclusions · narrative"], 1),
            ("Single Agent", ["single.investigate", "B 基线"], 1),
            ("Compliance Agent", ["默认禁用", "业务未实现"], 1)),
        Row(("Lease Agent", ["lease.query · lease.renewal_evaluation", "确定性 + LLM 双实现"], 1),
            ("Billing Agent", ["billing.statement · billing.arrears_check", "确定性 + LLM 双实现"], 1),
            ("Property Agent", ["property.work_orders", "确定性 + LLM 双实现"], 1)),
    ]),
    dict(idx="05", name="Runtime / 模型", tone=RUNTIME, full=False, gap=34, rows=[
        Row(("AgentRuntime + ToolLoop", ["runtime/ 有限轮次（single 上限 3）",
                                         "失败 / 越界即停，不追加"], 1),
            ("共享预算", ["runtime/budget.py", "模型按物理请求计", "工具按逻辑调用计"], 1),
            ("可信上下文与 Trace", ["runtime/types.py", "TrustedContext · Evidence",
                              "ToolTrace · TraceLog"], 1),
            ("模型适配", ["llm/ 工厂 + 缓存", "LangChain/DeepSeek · Fake · scripted",
                      "逐 Agent 配置 · 记 served_models"], 1)),
    ]),
    dict(idx="06", name="工具层", tone=TOOL, full=False, gap=34, rows=[
        Row(("ToolRegistry", ["tools/registry.py", "只收实例 · domain.action", "重名拒绝"], 1),
            ("ToolExecutor（唯一入口）", ["tools/executor.py", "白名单 → 权限 → Schema → 预算",
                                    "→ 超时/重试 → 结果与范围 → Trace"], 2),
            ("5 个只读工具", ["lease.lookup · billing.statement.read",
                         "billing.arrears.calculate",
                         "property.work_orders.read · document.search"], 2)),
    ]),
    dict(idx="07", name="数据 / 知识", tone=DATA, full=False, gap=34, rows=[
        Row(("Fixture 只读仓库", ["fixtures/repository.py", "合成 JSON · Decimal 金额",
                              "项目范围过滤 · 变体 overlay"], 1),
            ("SQLAlchemy 只读层", ["db/ 12 张表 + Alembic 0001", "装配期 PRAGMA query_only=1",
                               "SQLite 已验 / PostgreSQL 未验"], 1),
            ("RAG（BM25）", ["rag/ 合成 PDF → 逐页分块 → BM25", "L1/L2 引用核验 · 按租约限版本",
                          "无向量 / rerank（未实现）"], 1)),
    ]),
    dict(idx="08", name="评测 / 回归", tone=EVAL, full=True, gap=34, rows=[
        Row(("三基线评测", ["evaluation/baselines.py", "A_deterministic · B_single_agent",
                        "C_multi_agent（同一执行器）"], 1),
            ("评分与用例", ["scoring.py · scoring-v3.3", "smoke_v1（8）· heldout_v3（32）",
                        "字段绑定 · Decimal 到分"], 1),
            ("规划层评测", ["planner_suite.py", "planner_paraphrase_v1 / v2",
                        "rule · llm · hybrid 对照"], 1),
            ("回归与契约", ["backend/tests/ 28 个测试模块", "约 610 项（032/034 返修后）",
                        "70 项契约自检"], 1)),
    ]),
]

CTRL_CARDS = [
    ("checkpoint", ["data/checkpoints/graph.sqlite", "AsyncSqliteSaver", "调查图每节点落盘"], CTRL),
    ("审批台账", ["data/control/approval.sqlite", "与 checkpoint 分离", "两级串行 + 审计意见"], CTRL),
    ("运行索引", ["data/api/runs.sqlite", "列表 / 详情投影", "权威状态仍看 checkpoint"], CTRL),
    ("证据与 Trace", ["每条 trace 带 run_id 与主体", "source_tool 由执行器写入", "文档正文按不可信数据处理"], CTRL),
    ("安全不变量", ["不提供任意 SQL / Shell 工具", "审批只出草案，不调账派单", "密钥只在环境变量 / .env"], CTRL),
    ("数据边界", ["业务数据只读", "控制面正常持久化", "API 不提供业务写接口"], MUTED),
]

ARROW_LABELS = ["HTTP / CLI 调用", "建图 + 注入依赖", "按 capability 解析",
                "模型与工具调用", "受控执行", "只读查询", "同一执行器，不绕过控制"]


def build_overview(path: Path) -> None:
    W = 1860
    M = 40
    band_x = M
    band_w = W - 2 * M
    label_w = 148
    content_offset = label_w + 16
    x_full = band_x + content_offset
    w_full = band_w - content_offset - 18
    w_narrow = 1180
    gap_band = 40

    heights = [30 + sum(r.height(w_full if b["full"] else w_narrow) for r in b["rows"])
               + 15 * (len(b["rows"]) - 1) for b in BANDS]

    title_h = 112
    total = title_h + sum(heights) + gap_band * (len(heights) - 1) + 46 + 46
    img = Image.new("RGB", (W, total), WHITE)
    d = ImageDraw.Draw(img)

    title_block(d, M + 6, 26, band_w - 12,
                "商业地产多 Agent 争议调查系统 · 结构总览",
                "模块化单体 · 离线优先 · 业务数据只读 / 控制面可写　｜　"
                "依据 main @ 3be785e + Task 032 / 034 未提交改动（2026-11-22）",
                "当前结构")

    y = title_h
    boxes: list[tuple[int, int, int, int]] = []
    for i, b in enumerate(BANDS):
        h = heights[i]
        w = band_w if b["full"] else w_narrow + content_offset + 18
        band(d, band_x, y, w, h, b["name"], b["tone"], b["idx"])
        cw = w_full if b["full"] else w_narrow
        cy = y + 15
        for row in b["rows"]:
            rh = row.height(cw)
            row.draw(d, x_full, cy, cw, rh, b["tone"])
            cy += rh + 15
        boxes.append((band_x, y, band_x + w, y + h))
        y += h + gap_band

    for i in range(len(boxes) - 1):
        top = boxes[i][3]
        bottom = boxes[i + 1][1]
        cx = x_full + 300
        arrow(d, cx, top + 4, cx, bottom - 4, width=3, head=11)
        edge_label(d, cx + 168, (top + bottom) / 2, ARROW_LABELS[i], size=13)

    # 控制面竖栏（与业务只读数据分离）
    ctrl_top, ctrl_bottom = boxes[2][1], boxes[6][3]
    ctrl_x = boxes[2][2] + 44
    ctrl_w = W - M - ctrl_x
    d.rounded_rectangle([ctrl_x, ctrl_top, ctrl_x + ctrl_w, ctrl_bottom], radius=18,
                        fill=(253, 250, 244), outline=(228, 212, 180), width=2)
    d.text((ctrl_x + ctrl_w / 2, ctrl_top + 16), "控制面（可写）", font=font(19, True),
           fill=(110, 75, 5), anchor="ma")
    d.text((ctrl_x + ctrl_w / 2, ctrl_top + 44), "业务只读 · 状态与审计可写", font=font(12),
           fill=INK_FAINT, anchor="ma")
    inner_w = ctrl_w - 34
    chs = [measure_card(t, s, inner_w, ts=18, bs=13) for t, s, _ in CTRL_CARDS]
    start = ctrl_top + 66
    avail = (ctrl_bottom - 62) - start
    step = min(58.0, max(20.0, (avail - sum(chs)) / (len(chs) - 1)))
    cy = start
    for (t, s, tone), ch in zip(CTRL_CARDS, chs):
        draw_card(d, ctrl_x + 17, int(cy), inner_w, ch, t, s, tone, ts=18, bs=13, pad=14, gap=5)
        cy += ch + step
    d.text((ctrl_x + ctrl_w / 2, ctrl_bottom - 40),
           "运行期状态，已排除入库", font=font(12), fill=INK_FAINT, anchor="ma")
    d.text((ctrl_x + ctrl_w / 2, ctrl_bottom - 22),
           "权威状态：checkpoint + 审批台账", font=font(12), fill=INK_FAINT, anchor="ma")
    link_y = start + chs[0] / 2
    arrow(d, boxes[2][2] - 2, link_y, ctrl_x + 2, link_y, color=DASH, width=2,
          head=9, dashed=True)

    ly = total - 40
    d.line([(M + 4, ly), (M + 40, ly)], fill=ARROW, width=3)
    d.text((M + 50, ly - 9), "调用 / 依赖", font=font(13), fill=INK_SOFT)
    dashed_line(d, M + 168, ly, M + 204, ly, DASH, 2)
    d.text((M + 214, ly - 9), "持久化 / 投影", font=font(13), fill=INK_SOFT)
    d.rounded_rectangle([M + 348, ly - 8, M + 366, ly + 8], radius=4, fill=MUTED.fill,
                        outline=MUTED.border, width=2)
    d.text((M + 374, ly - 9), "未实现 / 禁用", font=font(13), fill=INK_SOFT)
    d.text((W - M, ly - 9), "docs/architecture/diagrams/build_diagrams.py 生成", font=font(12),
           fill=INK_FAINT, anchor="ra")

    img.save(path)


# --------------------------------------------------------------------------- #
# 图 2：LangGraph 工作流
# --------------------------------------------------------------------------- #

def build_workflow(path: Path) -> None:
    W = 1660
    CX = 720                      # 主干中线
    spine_x, spine_w = 460, 520   # plan / dispatch / verify / report / approval
    clar_x, clar_w = 56, 330
    det_x, det_w = 1180, 440
    sub_w, sub_gap = 300, 26
    sub_x0 = CX - (3 * sub_w + 2 * sub_gap) / 2

    plan = ("plan", ["RuleBasedPlanner（默认 mode: rule）", "LLM Supervisor / Hybrid",
                     "零命中 → needs_clarification"], ORCH)
    clar = ("clarification", ["回问用户：route=clarification", "零工具调用 · 不进入审批"], ORCH)
    det = ("deterministic_answer", ["单能力时直答", "金额全部来自工具"], ORCH)
    disp = ("dispatch", ["Send 并发扇出", "子任务来自计划，不来自模型"], ORCH)
    ver = ("verify（确定性核验）", ["冲突 / 缺失子任务 / 完整性 / 金额接地", "不选边、不猜结论"], ORCH)
    rev = ("revise（≤ 1 次）", ["有缺口且未补查", "超限直接转报告"], ORCH)
    rep = ("report", ["结论 + 证据页码 + 冲突 + 缺失资料", "始终写 routing_reason"], ORCH)
    appr = ("approval（人工审批门）",
            ["interrupt 暂停 → 两级串行批准", "approved_draft_only · executed_side_effects=[]"], ORCH)
    subtasks = [
        ("run_subtask · lease.query", ["Lease Agent", "lease.lookup + document.search"]),
        ("run_subtask · billing.statement", ["Billing Agent", "billing.statement.read"]),
        ("run_subtask · property.work_orders", ["Property Agent", "property.work_orders.read"]),
    ]
    ck = ("checkpoint（SQLite）", ["每节点落盘，可恢复", "一条 thread 只承载一次运行"], CTRL)
    ledger = ("审批台账（独立 SQLite）", ["版本绑定 · 幂等 · 意见落库", "批准后仍不产生业务副作用"], CTRL)

    def h(item, w, ts=20, bs=14):
        return measure_card(item[0], item[1], w, ts=ts, bs=bs)

    h1 = max(h(plan, spine_w), h(clar, clar_w), h(det, det_w))
    h2 = h(disp, spine_w)
    h3 = max(measure_card(t, s, sub_w, ts=18, bs=13) for t, s in subtasks)
    h4 = max(h(ver, spine_w), h(rev, 300))
    h5 = max(h(rep, spine_w), h(ck, det_w, ts=18, bs=13))
    h6 = max(h(appr, spine_w), h(ledger, det_w, ts=18, bs=13))

    y1 = 188
    y2 = y1 + h1 + 54
    y3 = y2 + h2 + 76
    y4 = y3 + h3 + 74
    y5 = y4 + h4 + 46
    y6 = y5 + h5 + 46
    y_end = y6 + h6 + 34
    H = int(y_end + 46)

    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    title_block(d, 44, 22, W - 88,
                "一次调查的运行结构 · LangGraph 9 节点",
                "plan 先决定路由：零命中回问 / 单能力直答 / 多能力并发扇出；verify 只做确定性核验，补查最多 1 次",
                "orchestration/investigation.py")

    pill(d, CX, 150, "START", fill=(30, 58, 95), outline=(30, 58, 95))
    arrow(d, CX, 172, CX, y1 - 4, width=3)

    draw_card(d, spine_x, y1, spine_w, h1, *plan)
    draw_card(d, clar_x, y1, clar_w, h1, *clar)
    draw_card(d, det_x, y1, det_w, h1, *det)
    draw_card(d, spine_x, y2, spine_w, h2, *disp)
    draw_card(d, spine_x, y4, spine_w, h4, *ver)
    draw_card(d, 56, y4, 300, h4, *rev)
    draw_card(d, spine_x, y5, spine_w, h5, *rep)
    draw_card(d, spine_x, y6, spine_w, h6, *appr)
    draw_card(d, det_x, y5, det_w, h5, *ck, ts=18, bs=13)
    draw_card(d, det_x, y6, det_w, h6, *ledger, ts=18, bs=13)

    # plan → dispatch / clarification / deterministic_answer
    arrow(d, CX, y1 + h1 + 1, CX, y2 - 4, width=3)
    edge_label(d, CX + 54, (y1 + h1 + y2) / 2, "多能力", size=13)
    mid1 = y1 + h1 / 2
    arrow(d, spine_x - 2, mid1, clar_x + clar_w + 3, mid1, width=3)
    edge_label(d, (spine_x + clar_x + clar_w) / 2, mid1 - 20, "零命中", size=13)
    arrow(d, spine_x + spine_w + 2, mid1, det_x - 3, mid1, width=3)
    edge_label(d, (spine_x + spine_w + det_x) / 2, mid1 - 20, "单能力", size=13)

    # clarification → END
    clar_cx = clar_x + clar_w / 2
    end1 = pill(d, int(clar_cx), int(y1 + h1 + 36), "END", fill=(90, 96, 104),
                outline=(90, 96, 104), size=15)
    arrow(d, clar_cx, y1 + h1 + 1, clar_cx, end1[1] - 4, width=3)

    # dispatch ══ Send ══> 三个子任务 → 合流到 verify
    bus1 = y2 + h2 + 36
    d.line([(CX, y2 + h2 + 1), (CX, bus1)], fill=ARROW, width=3)
    centers = [sub_x0 + i * (sub_w + sub_gap) + sub_w / 2 for i in range(3)]
    d.line([(centers[0], bus1), (centers[-1], bus1)], fill=ARROW, width=3)
    for i, (t, s) in enumerate(subtasks):
        draw_card(d, int(sub_x0 + i * (sub_w + sub_gap)), y3, sub_w, h3, t, s, AGENT,
                  ts=18, bs=13)
        arrow(d, centers[i], bus1, centers[i], y3 - 4, width=3, head=11)
    bus2 = y3 + h3 + 34
    for i in range(3):
        d.line([(centers[i], y3 + h3 + 1), (centers[i], bus2)], fill=ARROW, width=3)
    d.line([(centers[0], bus2), (centers[-1], bus2)], fill=ARROW, width=3)
    arrow(d, CX, bus2, CX, y4 - 4, width=3, head=13)

    # deterministic_answer → verify（右侧下行折线）
    elbow_x = det_x + det_w / 2
    d.line([(elbow_x, y1 + h1 + 1), (elbow_x, y4 + h4 / 2)], fill=ARROW, width=3)
    arrow(d, elbow_x, y4 + h4 / 2, spine_x + spine_w + 3, y4 + h4 / 2, width=3)
    edge_label(d, (elbow_x + spine_x + spine_w) / 2 + 40, y4 + h4 / 2 - 18,
               "直答同样进核验", size=13)

    # verify ↔ revise，revise → dispatch
    arrow(d, spine_x - 2, y4 + h4 / 2, 356 + 3, y4 + h4 / 2, width=3)
    loop_x = 136
    d.line([(loop_x, y4 - 1), (loop_x, y2 + h2 / 2)], fill=ARROW, width=3)
    arrow(d, loop_x, y2 + h2 / 2, spine_x - 2, y2 + h2 / 2, width=3)
    edge_label(d, (loop_x + spine_x) / 2, y2 + h2 / 2 - 19, "补查回到 dispatch（≤ 1 次）", size=13)

    # verify → report → approval → END
    arrow(d, CX, y4 + h4 + 1, CX, y5 - 4, width=3)
    edge_label(d, CX + 138, (y4 + h4 + y5) / 2, "supported / insufficient", size=13)
    arrow(d, CX, y5 + h5 + 1, CX, y6 - 4, width=3)
    end2 = pill(d, CX, int(y_end), "END", fill=(90, 96, 104), outline=(90, 96, 104), size=15)
    arrow(d, CX, y6 + h6 + 1, CX, end2[1] - 4, width=3)

    # 控制面（虚线）
    arrow(d, spine_x + spine_w + 3, y5 + h5 / 2, det_x - 3, y5 + h5 / 2,
          color=DASH, width=2, head=9, dashed=True)
    arrow(d, spine_x + spine_w + 3, y6 + h6 / 2, det_x - 3, y6 + h6 / 2,
          color=DASH, width=2, head=9, dashed=True)

    d.text((56, H - 30), "实线：图内流转　｜　虚线：控制面持久化（业务数据不写入）",
           font=font(12), fill=INK_FAINT)
    img.save(path)


# --------------------------------------------------------------------------- #
# 图 3：目录结构
# --------------------------------------------------------------------------- #

TREE = [
    (0, "commercial-property-multi-agent/", "仓库根：源码 + 文档 + 控制面数据", "root"),
    (1, "README.md", "总览 / 快速开始 / 评测表 / 已知限制", "file"),
    (1, ".env.example", "环境变量模板（只含键名）", "file"),
    (1, "backend/", "唯一源码包：Python 3.11 · 模块化单体", "dir"),
    (2, "pyproject.toml", "依赖与入口 commercial-agent", "file"),
    (2, "app/", "", "dir"),
    (3, "cli.py", "CLI：9 个子命令，退出码 0/1/2/3", "py"),
    (3, "api/", "FastAPI 适配层 + 同源工作台", "dir"),
    (4, "app.py · service.py", "7 个路由 / WorkflowService + RunIndex", "py"),
    (4, "display.py", "只读展示投影（内部 ID → 中文名）", "py"),
    (4, "static/", "index.html + js/ + css/ + Tabler 1.7.4", "dir"),
    (3, "agents/", "Agent 契约、实现与装配", "dir"),
    (4, "base/", "contracts · registry · scope · evidence · conclusions", "py"),
    (4, "factory.py", "配置 → 实例的静态白名单 + 依赖注入", "py"),
    (4, "lease/ billing/ property/", "领域 Agent（确定性 + LLM 双实现）", "dir"),
    (4, "single/  compliance/", "单 Agent 基线 / 默认禁用且未实现", "dir"),
    (3, "orchestration/", "编排、规划、审批与持久化", "dir"),
    (4, "investigation.py", "LangGraph 调查图（9 节点）+ 确定性核验", "py"),
    (4, "supervisor.py", "LLM Supervisor / 混合规划（Task 034）", "py"),
    (4, "approval.py · checkpointing.py", "两级审批台账 / AsyncSqliteSaver", "py"),
    (4, "vocabulary.py · prompts/", "领域词表唯一来源 / Supervisor 提示词", "py"),
    (3, "runtime/", "AgentRuntime · 预算 · Trace · 可信上下文", "dir"),
    (3, "llm/", "模型工厂与缓存 · LangChain/DeepSeek · Fake · scripted", "dir"),
    (3, "tools/", "ToolRegistry · ToolExecutor · 5 个只读工具", "dir"),
    (3, "rag/", "PDF 生成 · 分块 · BM25 · 引用核验 · 文档目录", "dir"),
    (3, "fixtures/  db/", "JSON 只读仓库 / 12 表 SQLAlchemy + 种子", "dir"),
    (3, "config/", "5 个 Agent YAML + planner.yaml + Schema", "dir"),
    (3, "evaluation/", "三基线 · 评分 v3.3 · 用例 · 规划评测", "dir"),
    (3, "env.py · paths.py · *_demo.py", "环境 / 路径 / 装配入口", "py"),
    (2, "migrations/  scripts/", "Alembic 0001 初始 schema / 用例生成脚本", "dir"),
    (2, "tests/", "28 个测试模块（约 610 项）+ 70 项契约", "dir"),
    (1, "data/", "运行期控制面（已忽略入库）", "dir"),
    (2, "checkpoints/graph.sqlite", "LangGraph checkpoint", "db"),
    (2, "control/approval.sqlite", "审批台账（与 checkpoint 分离）", "db"),
    (2, "api/runs.sqlite · preview/", "运行索引投影 / 本地预览日志", "db"),
    (1, "docs/", "契约、任务存档与证据（全部带日期 / 版本）", "dir"),
    (2, "architecture/", "当前基线 · 系统 / Agent / Runtime 契约 · 词表", "dir"),
    (2, "decisions/  product/", "ADR-005 / ADR-006 · 范围与路线图", "dir"),
    (2, "evaluation/", "cases · fixtures · documents · 75 份报告", "dir"),
    (2, "prompts/ 01–06/", "36 份任务存档（原始 Prompt + 实施 + 验证）", "dir"),
    (2, "reviews/  demo/", "107 份复查与截图证据 / 演示脚本", "dir"),
    (2, "handoffs/  checkpoints/", "交接记录 / 里程碑与标签参考", "dir"),
    (2, "development_logs/  issues/  lessons_learned/", "开发日志 / 问题根因 / 知识笔记", "dir"),
    (1, "tools/flowise/", "独立 Flowise 3.1.4 沙箱（未接本项目）", "dir"),
    (1, "output/  tmp/", "导出物（PDF）/ 临时文件", "dir"),
    (1, ".claude/  .vscode/  .gitattributes", "本地工具配置与换行规范", "file"),
]

TREE_COLORS = {
    "root": (20, 32, 48),
    "dir": (30, 58, 95),
    "py": (24, 90, 32),
    "file": (75, 85, 99),
    "db": (110, 75, 5),
}


def build_tree(path: Path) -> None:
    row_h, step = 31, 26
    W = 1700
    top = 138
    H = top + len(TREE) * row_h + 56
    img = Image.new("RGB", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    title_block(d, 44, 22, W - 88,
                "仓库目录结构 · 当前实现",
                "backend/app 是唯一源码包；docs/ 承载契约与证据；data/ 是运行期控制面（不入库）",
                f"{len(TREE)} 项")

    base_x = 56
    note_x = 660
    f, fc = font(16), font(14)

    stack: list[bool] = []
    for i, (depth, name, note, kind) in enumerate(TREE):
        y = top + i * row_h
        color = TREE_COLORS.get(kind, INK)
        if depth == 0:
            stack = []
            node_x = base_x
        else:
            nxt = TREE[i + 1][0] if i + 1 < len(TREE) else -1
            is_last = nxt < depth
            # 祖先竖线
            for k in range(depth - 1):
                if k < len(stack) and stack[k]:
                    x = base_x + (k + 1) * step - 12
                    d.line([(x, y), (x, y + row_h)], fill=(198, 208, 220), width=2)
            node_x = base_x + depth * step
            elbow_x = node_x - 12
            if is_last:
                d.line([(elbow_x, y), (elbow_x, y + row_h / 2)], fill=(198, 208, 220), width=2)
            else:
                d.line([(elbow_x, y), (elbow_x, y + row_h)], fill=(198, 208, 220), width=2)
            d.line([(elbow_x, y + row_h / 2), (node_x - 3, y + row_h / 2)],
                   fill=(198, 208, 220), width=2)
            stack = stack[: depth - 1] + [not is_last]
        d.text((node_x, y + 5), name, font=f, fill=color)
        if note:
            d.text((note_x, y + 8), note, font=fc, fill=INK_FAINT)

    d.text((56, H - 36),
           "说明：按实际目录列举，未展开 .git、node_modules 与 .runtime；计数以 2026-11-22 工作区为准。",
           font=font(12), fill=INK_FAINT)
    img.save(path)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = {
        "overview": OUT_DIR / "01_overview.png",
        "workflow": OUT_DIR / "02_workflow.png",
        "tree": OUT_DIR / "03_directories.png",
    }
    which = set(sys.argv[1:]) or set(targets)
    for key, path in targets.items():
        if key not in which:
            continue
        {"overview": build_overview, "workflow": build_workflow, "tree": build_tree}[key](path)
        print("wrote", path.relative_to(ROOT))


if __name__ == "__main__":
    main()
