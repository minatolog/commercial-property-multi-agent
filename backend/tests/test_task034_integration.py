"""Task 034：规划器接入图 / CLI / 评测的集成测试，以及 §2.6 已问领域漏查。

覆盖 Prompt 第 4 节：
4. 模型异常 / 超时 / 预算耗尽时**图正常结束**；
6. hybrid 规则未命中 → 采用模型计划；模型 clarify → route=clarification、零工具、不审批；
8. mode=rule 时离线 heldout C 逐题与 `20261121T093757_*` 一致（回归保护）；
10. planner_mode / plan_source / fallback_reason 在 CLI 输出、评测报告中都存在且一致；
11. 已问领域漏查：双领域只查一个、无失败调用 → PARTIAL 且告警写“未查询”。
另含：冻结评测集的 SHA-256 守护、规划层评测的判分与零越权。
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Sequence

from app import cli
from app.agents.base.contracts import TaskStatus
from app.agents.base.errors import ErrorCode
from app.evaluation.planner_suite import evaluate_planner, over_privilege, score_plan
from app.investigation_demo import build_investigation_bundle, run_investigation
from app.llm.model_client import ChatMessage, FakeChatModelClient, ModelToolCall, ModelTurn, ToolSpec
from app.paths import CASES_DIR, REPO_ROOT
from tests.test_task031_z2_evidence import (
    LEASE_A301,
    _answer,
    _details,
    _run_single,
    _tool_turn,
)

PLANNING_KEYS = {"planner_mode", "plan_source", "fallback_reason", "planner_model", "supervisor_plan"}
FROZEN = {
    "planner_paraphrase_v1.jsonl": "29662293fac858fb142abbf0cef15c01b394f22211a1d4fb0e0242dba39b5db0",
    "planner_paraphrase_v2.jsonl": "ebf274cafa6f57131c9c71b9820768f4e02d825a17d3a510a189285a77768ef0",
}


def _plan_turn(arguments: dict[str, Any]) -> ModelTurn:
    return ModelTurn(
        tool_calls=(
            ModelToolCall(
                call_id="p1",
                name="submit_plan",
                arguments=arguments,
                arguments_json=json.dumps(arguments, ensure_ascii=False),
            ),
        )
    )


class _RaisingClient:
    provider = "fake"
    model_name = "raising"

    async def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]) -> ModelTurn:
        raise RuntimeError("上游不可用")


class _SlowClient:
    provider = "fake"
    model_name = "slow"

    async def complete(self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]) -> ModelTurn:
        await asyncio.sleep(30)
        raise AssertionError("不应等到这里")


def _investigate(question: str, *, planner_client: Any, mode: str = "hybrid",
                 max_model_calls: int = 4, timeout_config: bool = False):
    bundle = build_investigation_bundle(
        planner_mode=mode,
        planner_client=planner_client,
        max_model_calls=max_model_calls,
    )
    if timeout_config:
        planner = bundle.investigator.planner
        supervisor = getattr(planner, "supervisor", planner)
        supervisor._timeout = 0.05  # noqa: SLF001
    result = asyncio.run(run_investigation(bundle, question=question, lease_id=LEASE_A301))
    return bundle, result


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


# --------------------------------------------------------------------------- #
# 4 / 6. 图
# --------------------------------------------------------------------------- #


class TestGraphWithSupervisor(unittest.TestCase):
    def test_hybrid_unmatched_uses_model_plan(self) -> None:
        client = FakeChatModelClient(
            [_plan_turn({"decision": "dispatch", "domains": ["billing"],
                         "reasons": {"billing": "问上月是否缴清"}, "clarification_question": None,
                         "confidence": "high"})]
        )
        bundle, result = _investigate("这家店上个月的钱交齐了吗？", planner_client=client)
        planning = result.report["planning"]
        self.assertEqual(planning["plan_source"], "llm")
        self.assertEqual(planning["escalation_reason"], "no_domain_matched")
        self.assertEqual([item["capability"] for item in result.results], ["billing.statement"])
        self.assertEqual(result.route, "deterministic")
        self.assertEqual(result.report["routing_reason"][0]["source"], "llm")
        self.assertEqual(bundle.budget.snapshot().used_model_calls, 1)

    def test_model_clarify_goes_to_clarification_path(self) -> None:
        client = FakeChatModelClient(
            [_plan_turn({"decision": "clarify", "domains": [], "reasons": {},
                         "clarification_question": "您想核实的是哪一家商户的哪类事项？",
                         "confidence": "medium"})]
        )
        bundle, result = _investigate("帮我写一份周报。", planner_client=client)
        self.assertEqual(result.verdict, "needs_clarification")
        self.assertEqual(result.route, "clarification")
        self.assertFalse(result.results)
        self.assertFalse(bundle.trace_log.snapshot(), "回问不得调用任何工具")
        self.assertEqual(result.approval_status, "not_required")
        clarification = result.report["clarification"]
        self.assertEqual(clarification["reason"], "supervisor_clarify")
        self.assertEqual(clarification["question"], "您想核实的是哪一家商户的哪类事项？")
        self.assertEqual(result.report["planning"]["plan_source"], "llm")

    def test_failures_fall_back_and_graph_finishes(self) -> None:
        cases = {
            "model_error": dict(planner_client=_RaisingClient()),
            "timeout": dict(planner_client=_SlowClient(), timeout_config=True),
            "budget_exhausted": dict(planner_client=FakeChatModelClient([]), max_model_calls=1),
        }
        for reason, kwargs in cases.items():
            with self.subTest(reason=reason):
                if reason == "budget_exhausted":
                    bundle = build_investigation_bundle(
                        planner_mode="llm", planner_client=kwargs["planner_client"], max_model_calls=1
                    )
                    # 先把唯一的一次模型调用额度占掉
                    asyncio.run(bundle.budget.reserve_model_call("occupied"))
                    asyncio.run(bundle.budget.settle("occupied"))
                    result = asyncio.run(
                        run_investigation(bundle, question="A-301 租期和欠款？", lease_id=LEASE_A301)
                    )
                else:
                    _, result = _investigate("A-301 租期和欠款？", mode="llm", **kwargs)
                planning = result.report["planning"]
                self.assertEqual(planning["fallback_reason"], reason)
                self.assertEqual(planning["plan_source"], "fallback_rule")
                self.assertEqual(result.route, "fanout")
                self.assertTrue(result.results, "回退到规则计划后应照常执行子任务")
                self.assertTrue(any(reason in item for item in result.warnings), result.warnings)

    def test_default_bundle_is_rule_mode(self) -> None:
        bundle = build_investigation_bundle()
        self.assertEqual(bundle.planner_mode, "rule")
        result = asyncio.run(
            run_investigation(bundle, question="A-301 还有多少钱没交？", lease_id=LEASE_A301)
        )
        self.assertEqual(result.report["planning"]["plan_source"], "rule")
        self.assertEqual(result.report["planning"]["model_calls"], 0)
        self.assertEqual(bundle.budget.snapshot().used_model_calls, 0)

    def test_llm_mode_requires_model_budget_and_client(self) -> None:
        with self.assertRaises(ValueError):
            build_investigation_bundle(planner_mode="llm")
        with self.assertRaises(ValueError):
            build_investigation_bundle(planner_mode="llm", planner_provider="scripted", max_model_calls=0)


# --------------------------------------------------------------------------- #
# 10. CLI 与评测报告字段
# --------------------------------------------------------------------------- #


class TestPlanningFieldsVisible(unittest.TestCase):
    def test_cli_investigate_outputs_planning(self) -> None:
        for mode, source in (("rule", "rule"), ("llm", "llm"), ("hybrid", "llm")):
            with self.subTest(mode=mode):
                code, out, err = _run_cli(
                    ["investigate", "A-301 租期和欠款？", "--planner", mode, "--planner-provider", "scripted"]
                )
                self.assertEqual(code, cli.EXIT_OK, err)
                payload = json.loads(out)
                self.assertTrue(PLANNING_KEYS <= set(payload["planning"]), payload["planning"])
                self.assertEqual(payload["planning"]["planner_mode"], mode)
                self.assertEqual(payload["planning"]["plan_source"], source)
                self.assertIsNone(payload["planning"]["fallback_reason"])
                self.assertEqual(payload["planner"]["mode"], mode)

    def test_cli_llm_planner_without_model_is_usage_error(self) -> None:
        code, _, err = _run_cli(["investigate", "A-301 租期和欠款？", "--planner", "llm"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("--planner-provider", err)

    def test_cli_check_reports_planner(self) -> None:
        code, out, _ = _run_cli(["check"])
        self.assertEqual(code, cli.EXIT_OK)
        planner = json.loads(out)["planner"]
        self.assertEqual(planner["mode"], "rule")
        self.assertEqual(planner["model"]["model_name"], "deepseek-flash")

    def test_cli_check_fails_on_invalid_planner_config(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        directory = Path(tempfile.mkdtemp())
        bad = directory / "planner.yaml"
        bad.write_text("mode: auto\nmodel_provider: deepseek\nmodel_name: x\n"
                       "api_key_env: DEEPSEEK_API_KEY\nprompt_path: app/orchestration/prompts/supervisor_system.md\n",
                       encoding="utf-8")
        with patch("app.paths.PLANNER_CONFIG_PATH", bad):
            code, _, err = _run_cli(["check"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("规划器配置校验失败", err)

    def test_evaluation_report_rows_carry_planning(self) -> None:
        from app.evaluation import evaluate
        from app.evaluation.cases import load_cases

        cases = [case for case in load_cases(split="heldout") if case.case_id in {"H01", "H25"}]
        report = asyncio.run(
            evaluate(baseline="C_multi_agent", cases=cases, split="heldout",
                     planner_mode="hybrid", planner_provider="scripted")
        )
        self.assertEqual(report.config["planner_mode"], "hybrid")
        for row in report.rows:
            planning = row["result"]["planning"]
            self.assertTrue(PLANNING_KEYS <= set(planning), planning)
            self.assertEqual(planning["planner_mode"], "hybrid")
        self.assertIn("plan_sources", report.summary["planning"])
        from app.evaluation import render_markdown

        self.assertIn("C_multi_agent（规划模式：hybrid）", render_markdown([report]))


# --------------------------------------------------------------------------- #
# 8. mode=rule 回归保护
# --------------------------------------------------------------------------- #


class TestRuleModeHeldoutRegression(unittest.TestCase):
    def test_c_rule_rows_identical_to_reference_report(self) -> None:
        from app.evaluation import evaluate

        reference = json.loads(
            (REPO_ROOT / "docs/evaluation/reports/20261121T093757_heldout_C_multi_agent.json")
            .read_text(encoding="utf-8")
        )
        report = asyncio.run(evaluate(baseline="C_multi_agent", split="heldout"))
        ignore = {"latency_ms", "planning"}

        def strip(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: strip(v) for k, v in value.items() if k not in ignore}
            if isinstance(value, list):
                return [strip(item) for item in value]
            return value

        expected = {row["case_id"]: strip(row) for row in reference["rows"]}
        actual = {row["case_id"]: strip(row) for row in report.rows}
        self.assertEqual(expected, actual)
        self.assertEqual(
            {row["result"]["planning"]["plan_source"] for row in report.rows}, {"rule"}
        )


# --------------------------------------------------------------------------- #
# 11. §2.6 已问领域漏查（无失败调用）
# --------------------------------------------------------------------------- #


class TestUnqueriedAskedDomain(unittest.TestCase):
    def test_two_domains_only_one_queried_is_partial(self) -> None:
        result = _run_single(
            [_tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c1"), _answer("租期已核对。")],
            {"question": "A-301 租期和欠款？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.PARTIAL, result.error)
        data = result.output or {}
        self.assertEqual(data["failed_tool_calls"], [])
        self.assertEqual(data["domain_coverage"]["missing"], ["billing"])
        notes = [item for item in result.warnings if "部分取证" in item]
        self.assertEqual(len(notes), 1, result.warnings)
        self.assertIn("未查询", notes[0])
        self.assertIn("billing", notes[0])
        self.assertNotIn("查询失败", notes[0])

    def test_asked_domain_never_queried_is_insufficient(self) -> None:
        result = _run_single(
            [_tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c1"), _answer("已经核对，没有问题。")],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertIn("未查询", result.error.message)
        self.assertEqual(_details(result)["domain_coverage"]["missing"], ["billing"])

    def test_both_domains_queried_is_success(self) -> None:
        result = _run_single(
            [
                ModelTurn(
                    tool_calls=(
                        *_tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c1").tool_calls,
                        *_tool_turn("billing.statement.read", {"lease_id": LEASE_A301}, "c2").tool_calls,
                    )
                ),
                _answer("租期已核对；应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 租期和欠款？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, (result.error, result.warnings))

    def test_extra_unrelated_tool_does_not_change_status(self) -> None:
        result = _run_single(
            [
                ModelTurn(
                    tool_calls=(
                        *_tool_turn("billing.statement.read", {"lease_id": LEASE_A301}, "c1").tool_calls,
                        *_tool_turn("property.work_orders.read", {}, "c2").tool_calls,
                    )
                ),
                _answer("应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, (result.error, result.warnings))


# --------------------------------------------------------------------------- #
# 规划层评测：冻结、判分、零越权
# --------------------------------------------------------------------------- #


class TestPlannerEvaluation(unittest.TestCase):
    def test_frozen_case_files_unchanged(self) -> None:
        for name, digest in FROZEN.items():
            with self.subTest(name=name):
                data = (CASES_DIR / name).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
                self.assertNotIn(b"\r", data)

    def test_score_plan_rules(self) -> None:
        case = {"expected": {"decision": "dispatch", "domains": ["billing", "property"],
                             "optional_domains": ["lease"]}, "acceptable_alternatives": []}
        self.assertTrue(score_plan(case, "dispatch", ["billing", "property"])["correct"])
        self.assertTrue(score_plan(case, "dispatch", ["lease", "billing", "property"])["correct"])
        missing = score_plan(case, "dispatch", ["billing"])
        self.assertFalse(missing["correct"])
        self.assertTrue(missing["partial"])
        self.assertEqual(missing["missing_domains"], ["property"])
        self.assertFalse(score_plan(case, "clarify", [])["correct"])
        alt = {"expected": {"decision": "clarify"},
               "acceptable_alternatives": [{"decision": "dispatch", "domains": ["billing"], "optional_domains": []}]}
        self.assertEqual(score_plan(alt, "dispatch", ["billing"])["matched"], "alternative")
        self.assertFalse(score_plan(alt, "dispatch", ["lease"])["correct"])

    def test_over_privilege_detection(self) -> None:
        good = [{"subtask_id": "st_1_billing", "capability": "billing.statement",
                 "payload": {"question": "q", "lease_id": LEASE_A301}}]
        self.assertEqual(over_privilege(good, trusted_lease=LEASE_A301), [])
        bad = [
            {"subtask_id": "x", "capability": "admin.grant", "payload": {}},
            {"subtask_id": "y", "capability": "billing.statement",
             "payload": {"lease_id": "lease_jl_b101_2025", "permissions": "admin"}},
        ]
        self.assertEqual(len(over_privilege(bad, trusted_lease=LEASE_A301)), 3)

    def test_suite_runs_all_configs_in_one_event_loop(self) -> None:
        """真实模型冒烟发现：langchain-openai 的异步 HTTP 客户端是进程级缓存、绑定首个事件循环。

        每种配置各开一次 asyncio.run 会在第二种配置时报 “Event loop is closed”；
        这里用一个记录事件循环的替身客户端守住“全部配置共用一个事件循环”。
        """

        import tempfile

        from app.evaluation.planner_suite import run_planner_suite
        from app.llm.scripted import ScriptedSupervisorModel

        loops: set[int] = set()

        class _LoopBoundClient(ScriptedSupervisorModel):
            async def complete(self, messages, tools):  # noqa: ANN001
                loops.add(id(asyncio.get_running_loop()))
                return await super().complete(messages, tools)

        reports, written = run_planner_suite(
            ["llm", "hybrid"],
            cases_version="v1",
            provider="scripted",
            out_dir=tempfile.mkdtemp(),
            client_factory=_LoopBoundClient,
        )
        self.assertEqual(len(reports), 2)
        self.assertEqual(len(loops), 1, "所有配置必须在同一个事件循环中调用规划模型")
        self.assertEqual(len(written), 3)

    def test_suite_rows_record_planner_model_and_served_models(self) -> None:
        """复查 P2-1：规划层评测逐题记录配置名与服务端实际应答模型，汇总可复核。"""

        from app.llm.scripted import ScriptedSupervisorModel

        def _served_as(name: str | None):
            class _Client(ScriptedSupervisorModel):
                async def complete(self, messages, tools):  # noqa: ANN001
                    turn = await super().complete(messages, tools)
                    return turn.model_copy(update={"served_model": name})

            return _Client

        cases = [
            ("scripted-supervisor", False, "served_models"),
            ("other-model", True, "served_model_mismatch_cases"),
            (None, None, "served_model_unknown_cases"),
        ]
        for served, mismatch, _bucket in cases:
            with self.subTest(served=served):
                report = asyncio.run(
                    evaluate_planner("llm", cases_version="v1", provider="scripted",
                                     client_factory=_served_as(served))
                )
                called = [row for row in report.rows if row["model_calls"]]
                self.assertTrue(called)
                for row in called:
                    model = row["planner_model"]
                    self.assertEqual(model["model_name"], "scripted-supervisor")
                    self.assertEqual(model["served_models"], [served] if served else [])
                    self.assertIs(model["served_model_mismatch"], mismatch)
                summary = report.summary
                ids = [row["case_id"] for row in called]
                if served is None:
                    self.assertEqual(summary["served_models"], {})
                    self.assertEqual(summary["served_model_unknown_cases"], ids)
                else:
                    self.assertEqual(summary["served_models"], {served: len(called)})
                    self.assertEqual(summary["served_model_mismatch_cases"], ids if mismatch else [])
                self.assertIn(report.as_dict()["bindings"]["code_worktree"], {"clean", "dirty", "unknown"})

        rule = asyncio.run(evaluate_planner("rule", cases_version="v1", provider="scripted"))
        self.assertTrue(all(row["planner_model"] is None for row in rule.rows))

    def test_planning_record_shape_is_uniform(self) -> None:
        """复查 P3-4：规则直达记录也带 escalation_reason（为 None）。"""

        from app.orchestration.investigation import rule_planning_record

        self.assertIn("escalation_reason", rule_planning_record())
        self.assertIsNone(rule_planning_record()["escalation_reason"])

    def test_offline_suite_runs_all_configs_without_over_privilege(self) -> None:
        for config in ("rule", "llm", "hybrid", "hybrid_multi_rule"):
            with self.subTest(config=config):
                report = asyncio.run(evaluate_planner(config, cases_version="v1", provider="scripted"))
                summary = report.summary
                self.assertEqual(summary["total"], 30)
                self.assertTrue(summary["over_privilege_free"], summary["over_privilege_cases"])
                injection = summary["by_category"]["injection"]
                self.assertEqual(injection["total"], 3)
                rule_direct = [row for row in report.rows if row["category"] == "rule_direct"]
                if config.startswith("hybrid"):
                    self.assertTrue(all(row["model_calls"] == 0 for row in rule_direct))
                if config == "rule":
                    self.assertEqual(summary["model_calls_total"], 0)
                if config == "llm":
                    self.assertEqual(summary["model_calls_total"], 30)


if __name__ == "__main__":
    unittest.main()
