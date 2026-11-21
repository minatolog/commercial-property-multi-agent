"""Task 031 离线 heldout 评测前后逐题对比（只读已有报告，不改任何用例/评分）。

运行（仓库根）：

    python docs/reviews/task031_evidence/compare_evaluation.py <before_dir> <after_dir>
"""

from __future__ import annotations

import glob
import json
import sys
from pathlib import Path


def load(directory: str) -> dict[str, dict]:
    reports: dict[str, dict] = {}
    for path in sorted(glob.glob(f"{directory}/*_heldout_*.json")):
        data = json.load(open(path, encoding="utf-8"))
        reports[data["baseline"]] = data
    return reports


def main() -> int:
    before_dir = sys.argv[1] if len(sys.argv) > 1 else "docs/reviews/task031_evidence/before/reports"
    after_dir = sys.argv[2] if len(sys.argv) > 2 else "docs/evaluation/reports"
    before = load(before_dir)
    after = load(after_dir)
    if not before or not after:
        print(f"missing reports: before={sorted(before)} after={sorted(after)}")
        return 1

    lines: list[str] = []
    for baseline in ("A_deterministic", "B_single_agent", "C_multi_agent"):
        b = before[baseline]["summary"]
        a = after[baseline]["summary"]
        lines.append(
            f"{baseline}: passed {b['cases_passed']}/{b['cases_scored']} -> "
            f"{a['cases_passed']}/{a['cases_scored']} | "
            f"pass_rate {b['pass_rate']} -> {a['pass_rate']} | "
            f"correctness_mean {b['correctness_rate_mean']} -> {a['correctness_rate_mean']} | "
            f"fund verified/unverified/not_checkable "
            f"{b['fund_conclusions']['verified']}/{b['fund_conclusions']['unverified']}/{b['fund_conclusions']['not_checkable']}"
            f" -> "
            f"{a['fund_conclusions']['verified']}/{a['fund_conclusions']['unverified']}/{a['fund_conclusions']['not_checkable']} | "
            f"route_hits {b['routing']['route_in_allowed']}/{b['routing']['cases_with_expectation']}"
            f" -> {a['routing']['route_in_allowed']}/{a['routing']['cases_with_expectation']} | "
            f"models_by_agent={sorted(a.get('models_by_agent') or {})}"
        )
        bmap = {row["case_id"]: row for row in before[baseline]["rows"]}
        amap = {row["case_id"]: row for row in after[baseline]["rows"]}
        for case_id in sorted(amap):
            rb, ra = bmap[case_id], amap[case_id]
            if (
                rb["passed"] != ra["passed"]
                or rb["correctness_passed"] != ra["correctness_passed"]
                or rb["correctness_total"] != ra["correctness_total"]
            ):
                lines.append(
                    f"  {baseline} {case_id}: passed {rb['passed']} -> {ra['passed']} | "
                    f"cp {rb['correctness_passed']}/{rb['correctness_total']} -> "
                    f"{ra['correctness_passed']}/{ra['correctness_total']} | "
                    f"route {rb['efficiency'].get('route')} -> {ra['efficiency'].get('route')} | "
                    f"errors {ra['result'].get('errors')}"
                )
            elif rb["efficiency"].get("route") != ra["efficiency"].get("route"):
                lines.append(
                    f"  {baseline} {case_id}: route only {rb['efficiency'].get('route')} -> "
                    f"{ra['efficiency'].get('route')} (只影响效率指标)"
                )
    lines.append("")
    lines.append(
        "cases_sha256: "
        f"{before['C_multi_agent']['bindings']['cases_sha256']} -> "
        f"{after['C_multi_agent']['bindings']['cases_sha256']} | identical="
        f"{before['C_multi_agent']['bindings']['cases_sha256'] == after['C_multi_agent']['bindings']['cases_sha256']}"
    )
    lines.append(
        "fixture_sha256 identical="
        f"{before['C_multi_agent']['bindings']['fixture_sha256'] == after['C_multi_agent']['bindings']['fixture_sha256']} | "
        f"scoring {before['C_multi_agent']['bindings']['scoring_version']} -> "
        f"{after['C_multi_agent']['bindings']['scoring_version']}"
    )
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
