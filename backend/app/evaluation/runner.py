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


def _summarise(scores: list[CaseScore], results: list[BaselineResult], cases: list[EvalCase]) -> dict[str, Any]:
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
            "cost_basis": "unavailable_offline_no_pricing",
            "note": "离线运行不产生真实 token/费用；不得作为真实模型成本引用",
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
) -> EvaluationReport:
    from ..paths import CASES_DIR

    selected = list(cases) if cases is not None else load_cases(cases_path, split=split)
    source = Path(cases_path) if cases_path is not None else (
        CASES_DIR / ("smoke_v1.jsonl" if split == "dev" else HELDOUT_CASES.name)
    )
    runner = build_baseline(baseline, max_tool_calls=max_tool_calls)
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
        model={
            "provider": "offline_deterministic",
            "model_name": "none",
            "note": "无 DEEPSEEK_API_KEY，三基线均未调用真实模型；token/成本指标不可用于质量结论",
        },
        config={
            "max_tool_calls": max_tool_calls,
            "baselines": list(BASELINES),
            "tool_permissions": "由 fixture principal 决定；三基线使用同一套只读工具",
        },
        started_at=started.isoformat(),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        rows=[
            {**score.as_dict(), "result": result.as_dict()}
            for score, result in zip(scores, results)
        ],
        summary=_summarise(scores, results, selected),
    )
    return report


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
                cost="n/a（离线）",
                lat=cost["latency_ms_p50"],
            )
        )
    lines.append("")
    lines.append("> 路由命中只作效率指标；自动断言通过率不含人工量表（rubric）。")
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
