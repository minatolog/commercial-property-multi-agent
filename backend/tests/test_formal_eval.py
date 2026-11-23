"""正式真实评测的重复运行与汇总（app.evaluation.formal）。

不调用任何模型：汇总逻辑用构造的报告测试；运行器只测冻结 / 续跑这两道保护。
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.evaluation import formal


def _report(passed: dict[str, bool], *, tokens: int = 100, served: list[str] | None = None,
            mismatch: bool | None = None, manual: dict[str, list[str]] | None = None) -> dict:
    rows = [
        {
            "case_id": cid,
            "applicable": True,
            "passed": ok,
            "manual_queue": (manual or {}).get(cid, []),
            "result": {"status": "ok" if ok else "failed"},
        }
        for cid, ok in passed.items()
    ]
    rows.append({"case_id": "H99", "applicable": False, "passed": False, "manual_queue": [], "result": {"status": "ok"}})
    scored = len(passed)
    return {
        "summary": {
            "cases_scored": scored,
            "pass_rate": sum(passed.values()) / scored,
            "correctness_rate_mean": 0.5,
            "cost": {"total_tokens": tokens, "model_calls": 3, "latency_ms_p50": 10},
            "models_by_agent": {
                "billing": {"model_name": "deepseek-flash", "served_models": served or [],
                            "served_model_mismatch": mismatch},
            },
        },
        "rows": rows,
    }


def _write_rep(out: Path, rep: int, reports: dict[str, dict]) -> None:
    names = {"A_deterministic": ("a", "A_deterministic"), "B_single_agent": ("main", "B_single_agent"),
             "C_rule": ("main", "C_multi_agent"), "C_hybrid": ("hybrid", "C_multi_agent")}
    for group, data in reports.items():
        sub, suffix = names[group]
        target = out / f"rep{rep}" / sub
        target.mkdir(parents=True, exist_ok=True)
        (target / f"20261123T00000{rep}_heldout_{suffix}.json").write_text(json.dumps(data), encoding="utf-8")


class TestSummarize(unittest.TestCase):
    def test_groups_flaky_cases_tokens_and_served_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            for rep, h2 in ((1, True), (2, False), (3, True)):
                _write_rep(out, rep, {
                    "A_deterministic": _report({"H01": True, "H02": False}, tokens=0),
                    "B_single_agent": _report({"H01": True, "H02": h2}, tokens=100 * rep,
                                              served=["deepseek-flash"], mismatch=False),
                    "C_rule": _report({"H01": True, "H02": True}),
                    "C_hybrid": _report({"H01": False, "H02": True}, served=["deepseek-v4-pro"], mismatch=True,
                                        manual={"H02": ["H02-FN: 需人工核对"]}),
                })
            summary = formal.summarize(formal.collect(out))

        groups = summary["groups"]
        self.assertEqual(list(groups), list(formal.GROUPS))
        b = groups["B_single_agent"]
        self.assertEqual(b["reps"], 3)
        self.assertEqual(b["per_case_passes"], {"H01": 3, "H02": 2})
        self.assertEqual(b["flaky"], ["H02"])
        self.assertEqual(b["always_pass"], ["H01"])
        self.assertAlmostEqual(b["pass_rate"]["mean"], (1 + 0.5 + 1) / 3, places=4)
        self.assertEqual((b["pass_rate"]["min"], b["pass_rate"]["max"]), (0.5, 1.0))
        self.assertEqual(b["total_tokens_sum"], 600)
        self.assertEqual(b["served_models"], ["deepseek-flash"])
        self.assertIs(b["served_model_mismatch"], False)
        # 不计分的题（applicable=False）不进入逐题统计
        self.assertNotIn("H99", b["per_case_passes"])
        self.assertEqual(groups["A_deterministic"]["never_pass"], ["H02"])
        self.assertIs(groups["C_hybrid"]["served_model_mismatch"], True)
        # 与配置不一致的实际应答模型必须原样报告，不能被配置名掩盖
        self.assertEqual(groups["C_hybrid"]["served_models"], ["deepseek-v4-pro"])


    def test_manual_queue_merges_repeats(self) -> None:
        reports = [
            formal.GroupReport("C_rule", rep, _report({"H01": True}, manual={"H01": ["H01-AN: 人工"]}))
            for rep in (1, 2, 3)
        ]
        rows = formal.manual_queue_rows(reports)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reps"], "1,2,3")
        self.assertEqual(rows[0]["score_0_2"], "")

    def test_render_markdown_reports_unknown_served_model_as_na(self) -> None:
        summary = formal.summarize([formal.GroupReport("A_deterministic", 1, _report({"H01": True}, tokens=0))])
        text = formal.render_markdown(summary, None)
        self.assertIn("| A_deterministic | 1 |", text)
        self.assertIn("n/a", text)
        self.assertIn("不换算金额", text)


class TestRunGuards(unittest.TestCase):
    def test_dirty_worktree_is_refused(self) -> None:
        with mock.patch.object(formal, "_git", side_effect=lambda *a: " M backend/app/cli.py" if a[0] == "status" else "abc"):
            with self.assertRaises(SystemExit) as ctx:
                formal.freeze_manifest()
        self.assertIn("未提交", str(ctx.exception))

    def test_changed_freeze_refuses_to_continue_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "freeze.json").write_text(
                json.dumps({"code_commit": "old", "files": {}, "reps": 5}), encoding="utf-8"
            )
            fresh = {"code_commit": "new", "files": {}, "worktree": "clean", "frozen_at": "x"}
            with mock.patch.object(formal, "freeze_manifest", return_value=fresh), \
                    mock.patch.object(formal.subprocess, "run") as runner:
                with self.assertRaises(SystemExit) as ctx:
                    formal.run(reps=5, out=out)
            runner.assert_not_called()
        self.assertIn("不一致", str(ctx.exception))

    def test_completed_reps_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            _write_rep(out, 1, {"A_deterministic": _report({"H01": True}), "C_rule": _report({"H01": True}),
                                "C_hybrid": _report({"H01": True})})
            fresh = {"code_commit": "c", "files": {}, "worktree": "clean", "frozen_at": "x"}
            with mock.patch.object(formal, "freeze_manifest", return_value=fresh), \
                    mock.patch.object(formal.subprocess, "run") as runner:
                formal.run(reps=1, out=out)
            runner.assert_not_called()
            self.assertTrue((out / "freeze.json").exists())

    def test_missing_offline_a_is_not_treated_as_complete(self) -> None:
        """A 由单独的离线命令产出；只有 B / C 报告时这一次重复不算完成。"""

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            _write_rep(out, 1, {"C_rule": _report({"H01": True}), "C_hybrid": _report({"H01": True})})
            self.assertFalse(formal._rep_complete(out / "rep1"))
            commands = [label for label, _ in formal._commands("heldout", out / "rep1")]
            self.assertEqual(commands, ["a", "main", "hybrid"])
            a_cmd = dict(formal._commands("heldout", out / "rep1"))["a"]
            self.assertNotIn("deepseek", a_cmd, "A 必须走离线路径，不调用模型")


if __name__ == "__main__":
    unittest.main()
