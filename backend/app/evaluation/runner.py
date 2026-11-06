"""评测运行器与报告（Task 013）。

报告必须能回答四个问题，且不能混淆：

1. **答对了吗**：`correctness`（自动断言）——路由命中只进 `efficiency`；
2. **代价多少**：延迟、工具调用数、模型调用数、token；离线运行一律 `cost=null`；
3. **哪些没覆盖**：`manual_queue`（人工量表）、`failures`（失败题）；
4. **绑定的是什么**：代码提交、数据集/ fixture 校验和、模型与配置快照、评分规则版本。

历史报告不覆盖：文件名含时间戳与基线名，改变配置后另生成实验。
"""

from __future__ import annotations

import json
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..paths import DEFAULT_FIXTURE_PATH, REPO_ROOT
from .baselines import BASELINES, BaselineResult, build_baseline
from .cases import EvalCase, HELDOUT_CASES, cases_checksum, load_cases
from .scoring import SCORING_VERSION, CaseScore, score_case

__all__ = ["EvaluationReport", "evaluate", "render_markdown"]


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except OSError:  # pragma: no cover - git 不可用
        pass
    return "unknown"


@dataclass
class EvaluationReport:
    baseline: str
    split: str
    cases_path: str
    cases_sha256: str
    fixture_sha256: str
    code_commit: str
    scoring_version: str
    model: dict[str, Any]
    config: dict[str, Any]
    started_at: str
    duration_ms: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "evaluation-report-v1",
            "baseline": self.baseline,
            "split": self.split,
            "bindings": {
                "code_commit": self.code_commit,
                "cases_path": self.cases_path,
                "cases_sha256": self.cases_sha256,
                "fixture_sha256": self.fixture_sha256,
                "scoring_version": self.scoring_version,
                "model": self.model,
                "config": self.config,
            },
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "rows": self.rows,
        }


def _kind_stats(scores: list[CaseScore], kind: str) -> dict[str, Any]:
    """按断言类别分开统计（N6 / Q3）：工具事实、资金结论、金额接地不能相互代表。"""

    outcomes = [
        outcome
        for score in scores
        for outcome in score.outcomes
        if outcome.kind == kind and outcome.passed is not None
    ]
    passed = sum(1 for outcome in outcomes if outcome.passed)
    return {
        "assertions": len(outcomes),
        "passed": passed,
        "failed": len(outcomes) - passed,
        "rate": round(passed / len(outcomes), 4) if outcomes else None,
    }


def _fund_summary(scores: list[CaseScore]) -> dict[str, Any]:
    """资金结论核对的状态分布（Q3）：未验证必须单独可见。"""

    statuses = [
        (score.fund_check or {}).get("status")
        for score in scores
        if score.fund_check is not None
    ]
    counts = {
        status: statuses.count(status)
        for status in ("verified", "mismatch", "unverified", "not_checkable")
    }
    total = sum(counts.values())
    return {
        **counts,
        "cases_checked": total,
        "verified_rate": (
            round(counts["verified"] / total, 4) if total else None
        ),
        "note": (
            "verified=字段金额与工具事实一致；mismatch=结论写错；"
            "unverified=叙述未绑定字段（未验证，不算通过）"
        ),
    }


def _summarise(
    scores: list[CaseScore],
    results: list[BaselineResult],
    cases: list[EvalCase],
    *,
    model_used: bool = False,
) -> dict[str, Any]:
    total = len(scores)
    applicable = [score for score in scores if score.applicable]
    passed = sum(1 for score in applicable if score.passed)
    correctness = [
        score.correctness_rate for score in applicable if score.correctness_rate is not None
    ]
    route_hits = [
        score.efficiency.get("route_in_allowed")
        for score in scores
        if score.efficiency.get("route_in_allowed") is not None
    ]
    latencies = sorted(result.latency_ms for result in results)
    tokens = sum(result.total_tokens for result in results)
    model_calls = sum(result.model_calls for result in results)
    tool_calls = sum(result.tool_calls for result in results)
    failures = [
        {"case_id": score.case_id, "errors": result.errors}
        for score, result in zip(scores, results)
        if score.applicable and not score.passed
    ]
    not_scored = [score.case_id for score in scores if not score.applicable]
    manual = sum(len(score.manual_queue) for score in scores)
    return {
        "cases": total,
        "cases_scored": len(applicable),
        "cases_not_scored": not_scored,
        "cases_passed": passed,
        "pass_rate": round(passed / len(applicable), 4) if applicable else None,
        "correctness_rate_mean": (
            round(sum(correctness) / len(correctness), 4) if correctness else None
        ),
        "correctness_note": "自动断言通过率；不含 rubric（人工量表）与路由效率",
        # N6 / Q3：把"内部工具事实对不对"、"资金结论对不对"、"金额是否接地"拆开报告，
        # 避免用任何一项替另一项背书；`unverified` 永远单独计数。
        "by_kind": {
            "tool_facts": _kind_stats(scores, "facts"),
            "fund_conclusions": _kind_stats(scores, "fund"),
            "answer_grounding": _kind_stats(scores, "answer"),
            "evidence": _kind_stats(scores, "evidence"),
            "outcome": _kind_stats(scores, "outcome"),
            "approval": _kind_stats(scores, "approval"),
        },
        "fund_conclusions": _fund_summary(scores),
        "by_kind_note": (
            "tool_facts=内部事实字段；fund_conclusions=最终答案里应收/已收/未收与可信值是否一致；"
            "answer_grounding=辅助检查（金额是否都有工具来源）；三者不可互相代替"
        ),
        "routing": {
            "cases_with_expectation": len(route_hits),
            "route_in_allowed": sum(1 for hit in route_hits if hit),
            "note": "仅效率指标，不参与 correctness",
        },
        "cost": {
            "latency_ms_total": sum(latencies),
            "latency_ms_p50": latencies[len(latencies) // 2] if latencies else 0,
            "latency_ms_max": latencies[-1] if latencies else 0,
            "tool_calls": tool_calls,
            "model_calls": model_calls,
            "total_tokens": tokens,
            "cost_amount": None,
            "cost_basis": (
                "unavailable_no_pricing" if model_used else "unavailable_offline_no_pricing"
            ),
            "note": (
                "真实调用已产生 token，但项目未内置价格表，因此不换算金额"
                if model_used
                else "离线运行不产生真实 token/费用；不得作为真实模型成本引用"
            ),
        },
        "manual_queue_count": manual,
        "failed_cases": failures,
        "by_case_count": len(cases),
    }


async def evaluate(
    *,
    baseline: str,
    cases: Iterable[EvalCase] | None = None,
    cases_path: Path | None = None,
    split: str = "dev",
    max_tool_calls: int = 12,
    model_client: Any = None,
) -> EvaluationReport:
    from ..paths import CASES_DIR

    selected = list(cases) if cases is not None else load_cases(cases_path, split=split)
    source = Path(cases_path) if cases_path is not None else (
        CASES_DIR / ("smoke_v1.jsonl" if split == "dev" else HELDOUT_CASES.name)
    )
    runner = build_baseline(
        baseline, max_tool_calls=max_tool_calls, model_client=model_client
    )
    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()

    results: list[BaselineResult] = []
    scores: list[CaseScore] = []
    for case in selected:
        result = await runner.run(case=case)
        results.append(result)
        scores.append(score_case(case, result))

    report = EvaluationReport(
        baseline=baseline,
        split=split,
        cases_path=str(source.relative_to(REPO_ROOT)) if source.is_absolute() else str(source),
        cases_sha256=cases_checksum(source),
        fixture_sha256=cases_checksum(DEFAULT_FIXTURE_PATH),
        code_commit=_git_commit(),
        scoring_version=SCORING_VERSION,
        model=_model_binding(model_client),
        config={
            "max_tool_calls": max_tool_calls,
            "max_total_tokens": runner.max_total_tokens,
            "baselines": list(BASELINES),
            "tool_permissions": "由 fixture principal 决定；三基线使用同一套只读工具",
        },
        started_at=started.isoformat(),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        rows=[
            {**score.as_dict(), "result": result.as_dict()}
            for score, result in zip(scores, results)
        ],
        summary=_summarise(
            scores, results, selected, model_used=model_client is not None
        ),
    )
    return report


def _model_binding(model_client: Any) -> dict[str, str]:
    """如实描述本次评测用了什么模型（Task 020）。

    以前这里硬编码 `offline_deterministic`，于是接入真实模型后报告仍然写着
    "无 DEEPSEEK_API_KEY、未调用真实模型"——报告与事实相反，比数据错误更糟。
    """

    if model_client is None:
        return {
            "provider": "offline_deterministic",
            "model_name": "none",
            "note": "本报告未调用任何模型（确定性规则路径）；token/成本不适用",
        }
    provider = str(getattr(model_client, "provider", "unknown"))
    model_name = str(getattr(model_client, "model_name", "unknown"))
    if provider == "scripted":
        note = (
            "脚本化模型（非真实推理）：只能证明装配与工具链路正确，"
            "不代表模型质量，不可用于质量对照结论"
        )
    else:
        note = (
            f"真实模型调用（{provider}/{model_name}）：token 与延迟来自实际调用；"
            "成本未内置定价，故不换算金额"
        )
    return {"provider": provider, "model_name": model_name, "note": note}


def render_markdown(reports: list[EvaluationReport]) -> str:
    lines: list[str] = []
    lines.append("# 评测报告")
    lines.append("")
    if reports:
        first = reports[0]
        lines.append(f"- 数据切分：`{first.split}`")
        lines.append(f"- 用例文件：`{first.cases_path}`（sha256 `{first.cases_sha256[:16]}…`）")
        lines.append(f"- fixture sha256：`{first.fixture_sha256[:16]}…`")
        lines.append(f"- 代码提交：`{first.code_commit}`")
        lines.append(f"- 评分规则：`{first.scoring_version}`")
        lines.append(f"- 模型：`{first.model['provider']}` / `{first.model['model_name']}`")
        lines.append(f"- 生成时间：`{first.started_at}`")
        lines.append("")
        lines.append(f"> {first.model['note']}")
        lines.append("")

    lines.append("## 汇总")
    lines.append("")
    lines.append(
        "| 基线 | 用例 | 通过 | 通过率 | 自动断言通过率 | 路由命中（效率） | 工具调用 | 模型调用 | token | 成本 | P50 延迟(ms) |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for report in reports:
        summary = report.summary
        routing = summary["routing"]
        cost = summary["cost"]
        lines.append(
            "| {b} | {c} | {p} | {pr} | {cr} | {rh}/{re} | {tc} | {mc} | {tk} | {cost} | {lat} |".format(
                b=report.baseline,
                c=summary["cases"],
                p=f"{summary['cases_passed']}/{summary['cases_scored']}",
                pr=summary["pass_rate"],
                cr=summary["correctness_rate_mean"],
                rh=routing["route_in_allowed"],
                re=routing["cases_with_expectation"],
                tc=cost["tool_calls"],
                mc=cost["model_calls"],
                tk=cost["total_tokens"],
                cost=(
                    "n/a（未内置定价）"
                    if cost["cost_basis"] == "unavailable_no_pricing"
                    else "n/a（离线）"
                ),
                lat=cost["latency_ms_p50"],
            )
        )
    lines.append("")
    lines.append("> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。")
    lines.append("")

    lines.append("## 指标分解（工具事实 / 资金结论 / 金额接地）")
    lines.append("")
    lines.append(
        "| 基线 | 工具事实断言 | 工具事实通过率 | 资金结论断言 | 资金结论通过率 | "
        "未验证题 | 金额接地（辅助） |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for report in reports:
        by_kind = report.summary.get("by_kind") or {}
        facts = by_kind.get("tool_facts") or {}
        fund = by_kind.get("fund_conclusions") or {}
        grounding = by_kind.get("answer_grounding") or {}
        fund_summary = report.summary.get("fund_conclusions") or {}
        lines.append(
            "| {b} | {fa} | {fr} | {ua} | {ur} | {uv} | {ga}/{gt} |".format(
                b=report.baseline,
                fa=facts.get("assertions", 0),
                fr=facts.get("rate"),
                ua=fund.get("assertions", 0),
                ur=fund.get("rate"),
                uv=fund_summary.get("unverified", 0),
                ga=grounding.get("passed", 0),
                gt=grounding.get("assertions", 0),
            )
        )
    lines.append("")
    lines.append(
        "> 工具事实准确率回答\"取数对不对\"；资金结论通过率回答\"用户读到的应收/已收/未收对不对\"；"
        "未验证题表示叙述没有把金额绑定到字段（**不算通过**）；金额接地是辅助检查，不能单独证明答案准确。"
    )
    lines.append("")

    for report in reports:
        lines.append(f"## {report.baseline}")
        lines.append("")
        lines.append("| 用例 | 通过 | 自动断言 | 路由 | 延迟(ms) | 工具调用 | 失败原因 |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in report.rows:
            result = row["result"]
            lines.append(
                "| {c} | {p} | {cp}/{ct} | {r} | {l} | {tc} | {e} |".format(
                    c=row["case_id"],
                    p="✅" if row["passed"] else ("❌" if row["applicable"] else "—"),
                    cp=row["correctness_passed"],
                    ct=row["correctness_total"],
                    r=result["route"] or "-",
                    l=result["latency_ms"],
                    tc=result["tool_calls"],
                    e="; ".join(result["errors"])[:80] or "-",
                )
            )
        manual = [
            f"- {row['case_id']}: {item}"
            for row in report.rows
            for item in row["manual_queue"]
        ]
        if manual:
            lines.append("")
            lines.append("人工量表待评：")
            lines.append("")
            lines.extend(manual)
        lines.append("")
    return "\n".join(lines)


def write_report(report: EvaluationReport, *, out_dir: str | Path | None = None) -> Path:
    from ..paths import REPORT_DIR

    directory = Path(out_dir) if out_dir is not None else REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.started_at.replace(":", "").replace("-", "")[:15]
    target = directory / f"{stamp}_{report.split}_{report.baseline}.json"
    target.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
