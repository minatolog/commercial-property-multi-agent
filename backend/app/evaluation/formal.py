"""正式真实评测：四组 × N 次重复的运行与汇总（路线图工作包 4）。

四组（同一批 heldout 题、同一工具 / 权限 / 预算）：

- ``A_deterministic``：确定性规则基线，不调模型（参照；N 次结果应完全一致）；
- ``B_single_agent``：单 Agent + DeepSeek；
- ``C_rule``：多 Agent，规则规划，领域 Agent 用 DeepSeek；
- ``C_hybrid``：多 Agent，混合规划（规划也用 DeepSeek），领域 Agent 用 DeepSeek。

每次重复执行两条已有的 CLI 命令（不改评测与评分逻辑）::

    python -m app.cli evaluate --split heldout --model-provider deepseek --out <rep>/main
    python -m app.cli evaluate --split heldout --model-provider deepseek \\
        --baseline C_multi_agent --planner hybrid --planner-provider deepseek --out <rep>/hybrid

协议（评测计划 §5）：

- 运行前**冻结**：工作区必须干净（否则拒绝运行），记录提交哈希、配置与 Prompt 文件哈希；
- 重复次数事先固定，同批次不调参；**保存全部运行，不挑最好的一次**；
- 中断后重跑同一命令会跳过已完成的重复（按报告文件判断），已完成的结果不重算。

用法（在 ``backend/`` 下）::

    python -m app.evaluation.formal run --reps 5 --out ../docs/evaluation/reports/formal_<日期>
    python -m app.evaluation.formal summarize --out ../docs/evaluation/reports/formal_<日期>
    python -m app.evaluation.formal run --reps 1 --split dev --out <实验目录>   # 小规模试跑
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..paths import BACKEND_ROOT, REPO_ROOT

GROUPS: tuple[str, ...] = ("A_deterministic", "B_single_agent", "C_rule", "C_hybrid")

#: 冻结时记录哈希的文件（相对 backend/）：Agent / 规划器配置与系统 Prompt
FROZEN_GLOBS: tuple[str, ...] = (
    "app/config/agents/*.yaml",
    "app/config/planner.yaml",
    "app/agents/*/prompts/*.md",
    "app/orchestration/prompts/*.md",
)


# ---------------------------------------------------------------- 冻结


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", check=False
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_manifest(*, allow_dirty: bool = False) -> dict[str, Any]:
    """记录本批次的冻结信息；工作区不干净时拒绝（除非显式允许，仅用于试跑）。"""

    dirty = _git("status", "--porcelain", "--", ".", ":(exclude).claude", ":(exclude)tmp")
    if dirty and not allow_dirty:
        raise SystemExit(
            "工作区有未提交改动，正式评测必须在干净的提交上运行（先提交）：\n" + dirty
        )
    files = sorted(
        {p for pattern in FROZEN_GLOBS for p in BACKEND_ROOT.glob(pattern) if p.is_file()}
    )
    return {
        "frozen_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "code_commit": _git("rev-parse", "HEAD"),
        "worktree": "dirty" if dirty else "clean",
        "files": {p.relative_to(BACKEND_ROOT).as_posix(): _sha256(p) for p in files},
    }


# ---------------------------------------------------------------- 运行


def _commands(split: str, out: Path) -> list[tuple[str, list[str]]]:
    base = [sys.executable, "-m", "app.cli", "evaluate", "--split", split,
            "--model-provider", "deepseek", "--quiet"]
    return [
        ("main", base + ["--out", str(out / "main")]),
        ("hybrid", base + ["--baseline", "C_multi_agent", "--planner", "hybrid",
                           "--planner-provider", "deepseek", "--out", str(out / "hybrid")]),
    ]


def _rep_complete(rep_dir: Path) -> bool:
    main = list((rep_dir / "main").glob("*_C_multi_agent.json"))
    hybrid = list((rep_dir / "hybrid").glob("*_C_multi_agent.json"))
    return bool(main) and bool(hybrid)


def run(*, reps: int, out: Path, split: str = "heldout", allow_dirty: bool = False) -> None:
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "freeze.json"
    manifest = freeze_manifest(allow_dirty=allow_dirty)
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (previous["code_commit"], previous["files"]) != (manifest["code_commit"], manifest["files"]):
            raise SystemExit(
                f"{manifest_path} 记录的冻结状态与当前代码 / 配置不一致：同一批次不能换代码或调参。"
                "要么回到原提交继续，要么换一个新的输出目录重新开始。"
            )
        manifest = previous
    else:
        manifest.update({"reps": reps, "split": split, "groups": list(GROUPS)})
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    env.pop("COMMERCIAL_DB_URL", None)  # migrations/env.py 会优先读它；评测走 fixture
    for rep in range(1, reps + 1):
        rep_dir = out / f"rep{rep}"
        if _rep_complete(rep_dir):
            print(f"[formal] rep{rep} 已完成，跳过", file=sys.stderr)
            continue
        for label, command in _commands(split, rep_dir):
            target = rep_dir / label
            if list(target.glob("*_C_multi_agent.json")):
                print(f"[formal] rep{rep}/{label} 已完成，跳过", file=sys.stderr)
                continue
            target.mkdir(parents=True, exist_ok=True)
            log = target / "run.log"
            print(f"[formal] rep{rep}/{label} 开始", file=sys.stderr)
            with log.open("w", encoding="utf-8") as handle:
                code = subprocess.run(
                    command, cwd=BACKEND_ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT
                ).returncode
            print(f"[formal] rep{rep}/{label} 退出码 {code}", file=sys.stderr)
            if not list(target.glob("*_C_multi_agent.json")):
                raise SystemExit(f"rep{rep}/{label} 没有生成报告（退出码 {code}），见 {log}")


# ---------------------------------------------------------------- 汇总


@dataclass(frozen=True)
class GroupReport:
    group: str
    rep: int
    data: dict[str, Any]


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def collect(out: Path) -> list[GroupReport]:
    """按目录约定找出每次重复的四组报告。"""

    reports: list[GroupReport] = []
    for rep_dir in sorted(out.glob("rep*"), key=lambda p: int(p.name[3:] or 0)):
        rep = int(rep_dir.name[3:])
        for path in (rep_dir / "main").glob("*.json"):
            if path.name.endswith("_A_deterministic.json"):
                reports.append(GroupReport("A_deterministic", rep, _load(path)))
            elif path.name.endswith("_B_single_agent.json"):
                reports.append(GroupReport("B_single_agent", rep, _load(path)))
            elif path.name.endswith("_C_multi_agent.json"):
                reports.append(GroupReport("C_rule", rep, _load(path)))
        for path in (rep_dir / "hybrid").glob("*_C_multi_agent.json"):
            reports.append(GroupReport("C_hybrid", rep, _load(path)))
    return reports


def _stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "min": None, "max": None, "stdev": None}
    return {
        "mean": round(statistics.mean(values), 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "stdev": round(statistics.stdev(values), 4) if len(values) > 1 else 0.0,
    }


def _served_models(report: dict[str, Any]) -> tuple[set[str], bool | None]:
    """runner 已把各 Agent 的服务端实际应答模型合并进 `summary.models_by_agent`。

    返回（实际应答模型集合，是否与配置名不一致）；从未记录到时第二项为 None。
    """

    entries = (report.get("summary") or {}).get("models_by_agent") or (
        report.get("bindings") or {}
    ).get("models_by_agent") or {}
    served: set[str] = set()
    mismatch: bool | None = None
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        served.update(str(m) for m in entry.get("served_models") or () if m)
        flag = entry.get("served_model_mismatch")
        if flag is not None:
            mismatch = bool(mismatch) or bool(flag)
    return served, mismatch


def summarize(reports: Iterable[GroupReport]) -> dict[str, Any]:
    by_group: dict[str, list[GroupReport]] = defaultdict(list)
    for report in reports:
        by_group[report.group].append(report)

    summary: dict[str, Any] = {"groups": {}}
    for group in GROUPS:
        runs = sorted(by_group.get(group, []), key=lambda r: r.rep)
        if not runs:
            continue
        pass_rates, correctness, tokens, model_calls, latency_p50 = [], [], [], [], []
        case_passes: dict[str, int] = defaultdict(int)
        case_scored: dict[str, int] = defaultdict(int)
        status_counts: dict[str, int] = defaultdict(int)
        served: set[str] = set()
        mismatch: bool | None = None
        for run_ in runs:
            s = run_.data["summary"]
            pass_rates.append(s["pass_rate"])
            correctness.append(s.get("correctness_rate_mean") or 0.0)
            cost = s.get("cost") or {}
            tokens.append(cost.get("total_tokens") or 0)
            model_calls.append(cost.get("model_calls") or 0)
            latency_p50.append(cost.get("latency_ms_p50") or 0)
            run_served, run_mismatch = _served_models(run_.data)
            served |= run_served
            if run_mismatch is not None:
                mismatch = bool(mismatch) or run_mismatch
            for row in run_.data["rows"]:
                status_counts[str((row.get("result") or {}).get("status"))] += 1
                if not row.get("applicable", True):
                    continue
                case_scored[row["case_id"]] += 1
                if row.get("passed"):
                    case_passes[row["case_id"]] += 1
        n = len(runs)
        per_case = {cid: case_passes.get(cid, 0) for cid in sorted(case_scored)}
        summary["groups"][group] = {
            "reps": n,
            "rep_ids": [r.rep for r in runs],
            "cases_scored": runs[0].data["summary"].get("cases_scored"),
            "pass_rate": _stats(pass_rates),
            "pass_rate_by_rep": pass_rates,
            "correctness_rate": _stats(correctness),
            "total_tokens": _stats([float(t) for t in tokens]),
            "total_tokens_sum": sum(tokens),
            "model_calls": _stats([float(c) for c in model_calls]),
            "latency_ms_p50": _stats([float(v) for v in latency_p50]),
            "result_status_counts": dict(status_counts),
            "per_case_passes": per_case,
            "always_pass": [c for c, k in per_case.items() if k == case_scored[c]],
            "never_pass": [c for c, k in per_case.items() if k == 0],
            "flaky": [c for c, k in per_case.items() if 0 < k < case_scored[c]],
            "served_models": sorted(served),
            "served_model_mismatch": mismatch,
        }
    return summary


def manual_queue_rows(reports: Iterable[GroupReport]) -> list[dict[str, Any]]:
    """人工量表队列：同组同题同条目在几次重复里出现，合并成一行供人工评分。"""

    seen: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    for report in reports:
        for row in report.data.get("rows", []):
            for item in row.get("manual_queue") or ():
                seen[(report.group, row["case_id"], str(item))].add(report.rep)
    return [
        {"group": g, "case_id": c, "item": item, "reps": ",".join(str(r) for r in sorted(reps)),
         "score_0_2": "", "reviewer": "", "note": ""}
        for (g, c, item), reps in sorted(seen.items())
    ]


def _fmt(stat: dict[str, Any], pct: bool = False) -> str:
    if stat["mean"] is None:
        return "n/a"
    if pct:
        return f"{stat['mean']*100:.1f}%（{stat['min']*100:.1f}–{stat['max']*100:.1f}%，σ {stat['stdev']*100:.1f}）"
    return f"{stat['mean']:,.0f}（{stat['min']:,.0f}–{stat['max']:,.0f}）"


def render_markdown(summary: dict[str, Any], manifest: dict[str, Any] | None) -> str:
    lines = ["# 正式真实评测汇总（四组 × 重复）", ""]
    if manifest:
        lines += [
            f"- 冻结提交：`{manifest.get('code_commit')}`（工作区 {manifest.get('worktree')}），冻结时间 {manifest.get('frozen_at')}",
            f"- 计划重复：{manifest.get('reps')} 次；数据切分：{manifest.get('split')}；冻结文件 {len(manifest.get('files', {}))} 个（哈希见 `freeze.json`）",
        ]
    lines += [
        "- 金额：项目未内置价格表，只报告 token，不换算金额（以 DeepSeek 后台为准）。",
        "- 限制：heldout 题在开发中被反复查看和运行，结论属于回归 / 探索性，不是未曝光的盲测。",
        "",
        "| 组 | 重复 | 通过率 均值（区间，σ） | 断言正确率 | 每次 token | 每次模型调用 | 延迟 p50 ms | 实际应答模型 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for group, g in summary["groups"].items():
        lines.append(
            f"| {group} | {g['reps']} | {_fmt(g['pass_rate'], pct=True)} | {_fmt(g['correctness_rate'], pct=True)} | "
            f"{_fmt(g['total_tokens'])} | {_fmt(g['model_calls'])} | {_fmt(g['latency_ms_p50'])} | "
            f"{', '.join(g['served_models']) or 'n/a'} |"
        )
    lines += ["", "## 逐题稳定性", ""]
    for group, g in summary["groups"].items():
        flaky = ", ".join(f"{c} {g['per_case_passes'][c]}/{g['reps']}" for c in g["flaky"]) or "无"
        never = ", ".join(g["never_pass"]) or "无"
        lines.append(
            f"- **{group}**：始终通过 {len(g['always_pass'])} 题；从未通过 {len(g['never_pass'])} 题"
            f"（{never}）；不稳定 {len(g['flaky'])} 题（{flaky}）；结果状态分布 {g['result_status_counts']}"
        )
    return "\n".join(lines) + "\n"


def write_summary(out: Path) -> Path:
    reports = collect(out)
    if not reports:
        raise SystemExit(f"{out} 下没有找到任何重复的报告")
    summary = summarize(reports)
    manifest_path = out / "freeze.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "summary.md").write_text(render_markdown(summary, manifest), encoding="utf-8")
    rows = manual_queue_rows(reports)
    with (out / "manual_scoring.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["group", "case_id", "item", "reps", "score_0_2", "reviewer", "note"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return out / "summary.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.evaluation.formal", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run_p = sub.add_parser("run", help="按冻结方案执行 N 次重复（会调用真实 DeepSeek）")
    run_p.add_argument("--reps", type=int, required=True)
    run_p.add_argument("--out", type=Path, required=True)
    run_p.add_argument("--split", choices=("heldout", "dev"), default="heldout")
    run_p.add_argument("--allow-dirty", action="store_true", help="只用于试跑：允许工作区不干净")
    sum_p = sub.add_parser("summarize", help="汇总已完成的重复（不调用模型）")
    sum_p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        run(reps=args.reps, out=args.out.resolve(), split=args.split, allow_dirty=args.allow_dirty)
        print(write_summary(args.out.resolve()))
    else:
        print(write_summary(args.out.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
