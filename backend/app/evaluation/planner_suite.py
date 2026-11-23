"""规划层评测（Task 034）：在 planner_paraphrase_v1 / v2 上对比 rule / llm / hybrid。

只运行规划器（`aplan_detailed`），不执行领域 Agent：本评测的指标全在规划层
（派哪些领域、是否回问、是否越权、规划花了多少模型调用），而且真实模型对照时
每题只花 1 次规划调用。判分规则写在 `docs/evaluation/planner_paraphrase_v1.md` 第 3 节，
用例冻结后不改。

离线 `scripted` 规划模型不做推理（按词表命中给计划），因此离线结果只能证明
代码路径与回退逻辑正确，**不能**证明模型规划质量；报告会写明。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from ..orchestration.vocabulary import DOMAIN_CAPABILITIES, DOMAINS

__all__ = [
    "PLANNER_CASE_FILES",
    "PLANNER_CONFIGS",
    "PlannerEvalReport",
    "evaluate_planner",
    "load_planner_cases",
    "render_planner_markdown",
    "score_plan",
    "write_planner_report",
]

PLANNER_CASE_FILES: dict[str, str] = {
    "v1": "planner_paraphrase_v1.jsonl",
    "v2": "planner_paraphrase_v2.jsonl",
}

#: 对照组：名字 → (planner_mode, hybrid_multi_domain)
PLANNER_CONFIGS: dict[str, tuple[str, str | None]] = {
    "rule": ("rule", None),
    "llm": ("llm", None),
    "hybrid": ("hybrid", "llm"),
    "hybrid_multi_rule": ("hybrid", "rule"),
}

_CAPABILITY_DOMAIN = {capability: domain for domain, capability in DOMAIN_CAPABILITIES.items()}
_ALLOWED_PAYLOAD_KEYS = frozenset({"question", "query", "lease_id", "unit_id", "category"})


def load_planner_cases(version: str = "v1") -> tuple[Path, list[dict[str, Any]]]:
    from ..paths import CASES_DIR

    if version not in PLANNER_CASE_FILES:
        raise ValueError(f"未知规划评测集版本 {version!r}（可选 {list(PLANNER_CASE_FILES)}）")
    path = CASES_DIR / PLANNER_CASE_FILES[version]
    cases = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return path, cases


# ---------------------------------------------------------------- 判分


def _matches(expected: dict[str, Any], decision: str, domains: list[str]) -> bool:
    if expected.get("decision") == "clarify":
        return decision == "clarify"
    if decision != "dispatch":
        return False
    required = set(expected.get("domains") or ())
    optional = set(expected.get("optional_domains") or ())
    planned = set(domains)
    return required <= planned <= required | optional


def over_privilege(
    subtasks: list[dict[str, Any]], *, trusted_lease: str, trusted_unit: str = ""
) -> list[str]:
    """越权检查（硬性）：能力不在领域映射里、目标不是可信目标、payload 带了额外键。"""

    problems: list[str] = []
    for subtask in subtasks:
        capability = subtask.get("capability")
        if capability not in _CAPABILITY_DOMAIN:
            problems.append(f"{subtask.get('subtask_id')}: 未授权能力 {capability!r}")
        payload = dict(subtask.get("payload") or {})
        extra = sorted(set(payload) - _ALLOWED_PAYLOAD_KEYS)
        if extra:
            problems.append(f"{subtask.get('subtask_id')}: payload 含额外键 {extra}")
        lease = str(payload.get("lease_id") or "")
        if lease and lease != trusted_lease:
            problems.append(f"{subtask.get('subtask_id')}: 目标租约 {lease!r} 不是可信目标")
        unit = str(payload.get("unit_id") or "")
        if unit and unit != trusted_unit:
            problems.append(f"{subtask.get('subtask_id')}: 目标铺位 {unit!r} 不是可信目标")
    return problems


def score_plan(case: dict[str, Any], decision: str, domains: list[str]) -> dict[str, Any]:
    expected = case["expected"]
    alternatives = list(case.get("acceptable_alternatives") or ())
    primary = _matches(expected, decision, domains)
    alternative = any(_matches(alt, decision, domains) for alt in alternatives)
    correct = primary or alternative
    outcome: dict[str, Any] = {
        "correct": correct,
        "matched": "expected" if primary else ("alternative" if alternative else None),
        "missing_domains": [],
        "extra_domains": [],
        "partial": False,
    }
    if expected.get("decision") == "dispatch" and decision == "dispatch" and not correct:
        required = set(expected.get("domains") or ())
        optional = set(expected.get("optional_domains") or ())
        planned = set(domains)
        outcome["missing_domains"] = [d for d in DOMAINS if d in required - planned]
        outcome["extra_domains"] = [d for d in DOMAINS if d in planned - (required | optional)]
        outcome["partial"] = bool(planned & required)
    return outcome


# ---------------------------------------------------------------- 运行


@dataclass
class PlannerEvalReport:
    config_name: str
    planner_mode: str
    hybrid_multi_domain: str | None
    cases_version: str
    cases_path: str
    cases_sha256: str
    code_commit: str
    code_worktree: str
    provider: str | None
    model_name: str | None
    started_at: str
    duration_ms: int
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "planner-eval-report-v1",
            "config_name": self.config_name,
            "planner_mode": self.planner_mode,
            "hybrid_multi_domain": self.hybrid_multi_domain,
            "bindings": {
                "cases_version": self.cases_version,
                "cases_path": self.cases_path,
                "cases_sha256": self.cases_sha256,
                "code_commit": self.code_commit,
                # dirty = 被测代码含未提交改动，code_commit 不能单独复现（复查 P3-2）
                "code_worktree": self.code_worktree,
                "planner_provider": self.provider,
                "planner_model": self.model_name,
                "note": _provider_note(self.planner_mode, self.provider),
            },
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "rows": self.rows,
        }


def _provider_note(mode: str, provider: str | None) -> str:
    if mode == "rule":
        return "规则规划：零模型调用，结果可复现"
    if provider == "scripted":
        return (
            "脚本化规划模型（按词表命中给计划，不做推理）：只能证明 Supervisor 的装配、"
            "预算与回退链路正确，不能证明模型规划质量，不可用于质量对照结论"
        )
    return "真实模型规划：token 与延迟来自实际调用"


def _domains_of(subtasks: list[dict[str, Any]]) -> list[str]:
    planned = {_CAPABILITY_DOMAIN.get(str(item.get("capability"))) for item in subtasks}
    return [domain for domain in DOMAINS if domain in planned]


async def evaluate_planner(
    config_name: str,
    *,
    cases_version: str = "v1",
    provider: str | None = "scripted",
    client_factory: Callable[[], Any] | None = None,
    max_model_calls: int = 2,
    max_total_tokens: int | None = 4000,
) -> PlannerEvalReport:
    """在冻结的规划评测集上运行一种规划配置。

    `client_factory()` 每题返回一个规划模型客户端（测试 / 真实模型注入用）；
    省略时按 `provider` 构造（scripted → `ScriptedSupervisorModel`；deepseek → planner.yaml）。
    """

    from ..config.loader import load_planner_config
    from ..fixtures.repository import FixtureRepository
    from ..investigation_demo import unit_code_resolver
    from ..llm.factory import build_model_client_for_config
    from ..orchestration.supervisor import build_planner
    from ..paths import REPO_ROOT
    from ..runtime.budget import Budget
    from .runner import _git_commit, _git_worktree_state

    if config_name not in PLANNER_CONFIGS:
        raise ValueError(f"未知规划配置 {config_name!r}（可选 {list(PLANNER_CONFIGS)}）")
    mode, multi = PLANNER_CONFIGS[config_name]
    path, cases = load_planner_cases(cases_version)
    planner_config = load_planner_config()
    repository = FixtureRepository.load()
    unit_code_of = unit_code_resolver(repository)

    def _client() -> Any:
        if mode == "rule":
            return None
        if client_factory is not None:
            return client_factory()
        if provider == "scripted":
            from ..llm.scripted import ScriptedSupervisorModel

            return ScriptedSupervisorModel()
        if provider == "deepseek":
            return build_model_client_for_config(planner_config)
        raise ValueError(f"规划模式 {mode!r} 需要规划模型（provider=scripted|deepseek）")

    started = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    rows: list[dict[str, Any]] = []
    provider_label: str | None = None
    model_label: str | None = None
    for case in cases:
        client = _client()
        if client is not None:
            provider_label = str(getattr(client, "provider", provider))
            model_label = str(getattr(client, "model_name", None))
        budget = Budget(
            max_tool_calls=0,
            max_model_calls=max_model_calls if mode != "rule" else 0,
            max_total_tokens=max_total_tokens if mode != "rule" else None,
        )
        planner = build_planner(
            mode,
            config=planner_config,
            model_client=client,
            budget=budget,
            unit_code_of=unit_code_of,
            hybrid_multi_domain=multi,
        )
        payload = {"lease_id": case["lease_id"], "question": case["user_input"]}
        case_t0 = time.perf_counter()
        detail = await planner.aplan_detailed(case["user_input"], payload)
        latency_ms = int((time.perf_counter() - case_t0) * 1000)
        decision = "clarify" if detail.route == "clarification" else "dispatch"
        domains = _domains_of(detail.subtasks)
        outcome = score_plan(case, decision, domains)
        violations = over_privilege(detail.subtasks, trusted_lease=case["lease_id"])
        planning = dict(detail.planning or {})
        snapshot = budget.snapshot()
        rows.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "domain_group": case.get("domain_group"),
                "user_input": case["user_input"],
                "expected": case["expected"],
                "acceptable_alternatives": case.get("acceptable_alternatives") or [],
                "decision": decision,
                "domains": domains,
                "capabilities": [item["capability"] for item in detail.subtasks],
                **outcome,
                "over_privilege": violations,
                "plan_source": planning.get("plan_source"),
                "fallback_reason": planning.get("fallback_reason"),
                "escalation_reason": planning.get("escalation_reason"),
                "ambiguity_signals": planning.get("ambiguity_signals") or [],
                "rule_domains": planning.get("rule_domains") or [],
                "supervisor_plan": planning.get("supervisor_plan"),
                "planner_warnings": planning.get("warnings") or [],
                # 复查 P2-1：配置名与服务端实际应答模型并列；规则直达为 None
                "planner_model": planning.get("planner_model"),
                "clarification_question": (detail.clarification or {}).get("question"),
                "model_calls": snapshot.used_model_calls,
                "total_tokens": snapshot.used_total_tokens,
                "latency_ms": latency_ms,
            }
        )

    return PlannerEvalReport(
        config_name=config_name,
        planner_mode=mode,
        hybrid_multi_domain=multi,
        cases_version=cases_version,
        cases_path=path.relative_to(REPO_ROOT).as_posix(),
        cases_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        code_commit=_git_commit(),
        code_worktree=_git_worktree_state(),
        provider=provider_label if mode != "rule" else None,
        model_name=model_label if mode != "rule" else None,
        started_at=started.isoformat(timespec="seconds"),
        duration_ms=int((time.perf_counter() - t0) * 1000),
        rows=rows,
        summary=summarise_planner_rows(rows),
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _group_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row["correct"])
    return {"total": total, "correct": correct, "accuracy": _ratio(correct, total)}


def summarise_planner_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    dispatch_rows = [row for row in rows if row["expected"].get("decision") == "dispatch"]
    clarify_rows = [row for row in rows if row["expected"].get("decision") == "clarify"]
    # “不该问的没问”只统计回问**不**在可接受替代里的派发题
    strict_dispatch = [
        row
        for row in dispatch_rows
        if not any(alt.get("decision") == "clarify" for alt in row["acceptable_alternatives"])
    ]
    model_calls = [row["model_calls"] for row in rows]
    by_category: dict[str, list[dict[str, Any]]] = {}
    by_group: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_category.setdefault(row["category"], []).append(row)
        if row.get("domain_group"):
            by_group.setdefault(row["domain_group"], []).append(row)
    sources: dict[str, int] = {}
    fallbacks: dict[str, int] = {}
    for row in rows:
        sources[str(row["plan_source"])] = sources.get(str(row["plan_source"]), 0) + 1
        if row["fallback_reason"]:
            fallbacks[row["fallback_reason"]] = fallbacks.get(row["fallback_reason"], 0) + 1
    violations = [row["case_id"] for row in rows if row["over_privilege"]]
    served: dict[str, int] = {}
    mismatch_cases: list[str] = []
    unknown_served_cases: list[str] = []
    for row in rows:
        model = row.get("planner_model")
        if not row["model_calls"] or not isinstance(model, dict):
            continue
        for name in model.get("served_models") or []:
            served[name] = served.get(name, 0) + 1
        if model.get("served_model_mismatch") is True:
            mismatch_cases.append(row["case_id"])
        elif model.get("served_model_mismatch") is None:
            unknown_served_cases.append(row["case_id"])
    return {
        "total": len(rows),
        "correct": sum(1 for row in rows if row["correct"]),
        "accuracy": _ratio(sum(1 for row in rows if row["correct"]), len(rows)),
        "domain_exact": _group_stats(dispatch_rows),
        "domain_partial": sum(1 for row in dispatch_rows if row["partial"]),
        "domain_missing_cases": sum(1 for row in dispatch_rows if row["missing_domains"]),
        "domain_extra_cases": sum(1 for row in dispatch_rows if row["extra_domains"]),
        "dispatch_expected_but_clarified": sum(
            1 for row in strict_dispatch if row["decision"] == "clarify"
        ),
        "clarify": {
            "should_clarify": len(clarify_rows),
            "did_clarify": sum(1 for row in clarify_rows if row["decision"] == "clarify"),
            "should_not_clarify": len(strict_dispatch),
            "did_not_clarify": sum(1 for row in strict_dispatch if row["decision"] != "clarify"),
        },
        "over_privilege_cases": violations,
        "over_privilege_free": not violations,
        "model_calls_total": sum(model_calls),
        "zero_model_call_ratio": _ratio(sum(1 for item in model_calls if item == 0), len(rows)),
        "total_tokens": sum(row["total_tokens"] for row in rows),
        "latency_ms_total": sum(row["latency_ms"] for row in rows),
        "plan_sources": sources,
        "fallback_reasons": fallbacks,
        # 有模型调用的题：服务端实际应答模型计数；mismatch / 未知分别列出（复查 P2-1）
        "served_models": served,
        "served_model_mismatch_cases": mismatch_cases,
        "served_model_unknown_cases": unknown_served_cases,
        "by_category": {name: _group_stats(items) for name, items in by_category.items()},
        "by_domain_group": {name: _group_stats(items) for name, items in by_group.items()},
    }


def write_planner_report(report: PlannerEvalReport, *, out_dir: str | Path | None = None) -> Path:
    from ..paths import REPORT_DIR

    directory = Path(out_dir) if out_dir is not None else REPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = report.started_at.replace(":", "").replace("-", "")[:15]
    target = directory / f"{stamp}_planner_{report.cases_version}_{report.config_name}.json"
    target.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return target


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_planner_markdown(reports: Iterable[PlannerEvalReport]) -> str:
    reports = list(reports)
    first = reports[0]
    lines = [
        f"# 规划层评测（planner_paraphrase_{first.cases_version}）",
        "",
        f"- 用例：`{first.cases_path}`（SHA-256 `{first.cases_sha256}`）",
        f"- 代码：`{first.code_commit}`（工作区 {first.code_worktree}）",
        "- 判分规则：`docs/evaluation/planner_paraphrase_v1.md` 第 3 节（冻结后不改）",
        "",
    ]
    for report in reports:
        lines.append(f"- `{report.config_name}`：{_provider_note(report.planner_mode, report.provider)}")
    lines += [
        "",
        "## 汇总",
        "",
        "| 配置 | 总正确 | 领域完全正确 | 部分正确 | 漏选题 | 多选题 | 该问已问 | 不该问没问 | 越权 | 模型调用 | 零调用比例 | 回退 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for report in reports:
        s = report.summary
        clarify = s["clarify"]
        lines.append(
            "| {name} | {c}/{t} ({acc}) | {de}/{dt} | {dp} | {miss} | {extra} | {dc}/{sc} | {dnc}/{snc} | {op} | {mc} | {zr} | {fb} |".format(
                name=report.config_name,
                c=s["correct"],
                t=s["total"],
                acc=_fmt(s["accuracy"]),
                de=s["domain_exact"]["correct"],
                dt=s["domain_exact"]["total"],
                dp=s["domain_partial"],
                miss=s["domain_missing_cases"],
                extra=s["domain_extra_cases"],
                dc=clarify["did_clarify"],
                sc=clarify["should_clarify"],
                dnc=clarify["did_not_clarify"],
                snc=clarify["should_not_clarify"],
                op="**" + ", ".join(s["over_privilege_cases"]) + "**" if s["over_privilege_cases"] else "0",
                mc=s["model_calls_total"],
                zr=_fmt(s["zero_model_call_ratio"]),
                fb=", ".join(f"{k}={v}" for k, v in s["fallback_reasons"].items()) or "-",
            )
        )
    categories = sorted({name for report in reports for name in report.summary["by_category"]})
    lines += ["", "## 按类别", "", "| 类别 | " + " | ".join(r.config_name for r in reports) + " |",
              "|---|" + "---|" * len(reports)]
    for name in categories:
        cells = []
        for report in reports:
            stats = report.summary["by_category"].get(name)
            cells.append(f"{stats['correct']}/{stats['total']}" if stats else "-")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    groups = sorted({name for report in reports for name in report.summary["by_domain_group"]})
    if groups:
        lines += ["", "## 实习场景分组", "", "| 组 | " + " | ".join(r.config_name for r in reports) + " |",
                  "|---|" + "---|" * len(reports)]
        for name in groups:
            cells = []
            for report in reports:
                stats = report.summary["by_domain_group"].get(name)
                cells.append(f"{stats['correct']}/{stats['total']}" if stats else "-")
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines += ["", "## 逐题", "", "| 题号 | 期望 | " + " | ".join(r.config_name for r in reports) + " |",
              "|---|---|" + "---|" * len(reports)]
    by_case = [{row["case_id"]: row for row in report.rows} for report in reports]
    for row in reports[0].rows:
        expected = row["expected"]
        exp = (
            "回问"
            if expected.get("decision") == "clarify"
            else "+".join(expected.get("domains") or ())
        )
        cells = []
        for index in by_case:
            item = index[row["case_id"]]
            got = "回问" if item["decision"] == "clarify" else "+".join(item["domains"])
            mark = "✓" if item["correct"] else "✗"
            source = item["plan_source"] or ""
            cells.append(f"{mark} {got}（{source}）")
        lines.append(f"| {row['case_id']} | {exp} | " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def run_planner_suite(
    configs: Iterable[str],
    *,
    cases_version: str,
    provider: str | None,
    out_dir: str | Path | None = None,
    client_factory: Callable[[], Any] | None = None,
) -> tuple[list[PlannerEvalReport], list[str]]:
    from ..paths import REPORT_DIR

    async def _run_all() -> list[PlannerEvalReport]:
        # 所有配置必须在**同一个事件循环**里跑：langchain-openai 的异步 HTTP 客户端是进程级缓存，
        # 绑定在首次使用它的事件循环上；每种配置各开一次 asyncio.run 会在第二种配置时
        # 报 “Event loop is closed”（真实模型冒烟时发现，scripted 客户端不受影响）。
        return [
            await evaluate_planner(
                name,
                cases_version=cases_version,
                provider=provider,
                client_factory=client_factory,
            )
            for name in configs
        ]

    reports = asyncio.run(_run_all())
    written = [str(write_planner_report(report, out_dir=out_dir)) for report in reports]
    directory = Path(out_dir) if out_dir is not None else REPORT_DIR
    stamp = reports[0].started_at.replace(":", "").replace("-", "")[:15]
    summary_path = directory / f"{stamp}_planner_{cases_version}_summary.md"
    summary_path.write_text(render_planner_markdown(reports), encoding="utf-8", newline="\n")
    written.append(str(summary_path))
    return reports, written
