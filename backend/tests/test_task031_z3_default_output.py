"""Task 031 / 2.3（Z3）回归：`ask` 与 `investigate` 的默认摘要必须展示可信资金结论。

原始反例（Task 025 独立复查）：Agent 内部已有 `fund_conclusion` / `authoritative_answer`
/ `fund_check`，但 CLI 默认摘要只投影原始模型答案；调查报告里有 `authoritative_amounts`
却不出现在默认输出。于是用户默认看到的是**模型自由叙述**，核验状态不可见。

本文件验证的是**默认用户路径**（`app.cli.main(...)`）：
- 可信结论（工具事实渲染）与模型原话分栏；
- 核验状态（verified / mismatch / unverified / not_checkable）可见；
- 不一致时出现差异提示（复用 `narrative_discrepancies` / `fund_check.problems`）。
"""

from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from app import cli
from app.llm.model_client import FakeChatModelClient, ModelToolCall, ModelTurn

_PRINCIPAL_ENV = {"DEMO_PRINCIPAL_ID": "principal_ops_xinghui"}
LEASE_A301 = "lease_xh_a301_2025"
CORRECT_AMOUNTS = "应收 52596.00、已收 34560.00、未收 18036.00。"


def _tool_turn(name: str, arguments: dict) -> ModelTurn:
    return ModelTurn(
        text="",
        tool_calls=(
            ModelToolCall(
                call_id="c1",
                name=name,
                arguments=dict(arguments),
                arguments_json=json.dumps(arguments, ensure_ascii=False),
            ),
        ),
    )


def _run_cli(
    argv: list[str],
    *,
    turns: list[ModelTurn] | None = None,
    bundle_builder=None,
) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, _PRINCIPAL_ENV, clear=False):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            if bundle_builder is None and turns is None:
                code = cli.main(argv)
            elif bundle_builder is not None:
                with patch(
                    "app.investigation_demo.build_investigation_bundle",
                    side_effect=bundle_builder,
                ):
                    code = cli.main(argv)
            else:
                client = FakeChatModelClient(turns, provider="fake", model_name="test-fake")
                with patch("app.single_demo._build_model_client", return_value=client):
                    code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


class _WrongAmountModel:
    """先调用本 Agent 可用的第一个工具，再故意把三个金额写反/声称结清。"""

    provider = "fake"
    model_name = "wrong-amounts"

    async def complete(self, messages, tools):  # noqa: ANN001
        already_called = any(getattr(message, "tool_calls", ()) for message in messages)
        if not already_called and tools:
            spec = next(
                (item for item in tools if item.tool_name == "billing.statement.read"),
                tools[0],
            )
            return ModelTurn(
                text="",
                tool_calls=(
                    ModelToolCall(
                        call_id="c1",
                        name=spec.name,
                        arguments={},
                        arguments_json="{}",
                    ),
                ),
            )
        return ModelTurn(
            text="应收 0.00、已收 0.00、未收 0.00，已经全部结清。",
            finish_reason="stop",
        )


class TestAskDefaultSummary(unittest.TestCase):
    def test_trusted_conclusion_and_narrative_are_separate(self) -> None:
        code, out, _ = _run_cli(
            ["ask", "A-301 还欠多少？"],
            turns=[
                _tool_turn("billing.statement.read", {}),
                ModelTurn(text=CORRECT_AMOUNTS),
            ],
        )
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = json.loads(out)
        trusted = payload["trusted_conclusion"]
        self.assertEqual(trusted["source"], "tool_facts")
        self.assertEqual(trusted["fund_conclusion"]["invoiced_total"], "52596.00")
        self.assertEqual(trusted["fund_conclusion"]["paid_total"], "34560.00")
        self.assertEqual(trusted["fund_conclusion"]["outstanding_total"], "18036.00")
        self.assertEqual(trusted["check_status"], "verified")
        self.assertIn("未收 18036.00", trusted["rendered"])
        # 模型原话单独一栏，不与可信结论混在一起
        self.assertEqual(payload["model_narrative"]["answer"], CORRECT_AMOUNTS)
        self.assertEqual(payload["narrative_discrepancies"], [])

    def test_mismatching_narrative_is_flagged_not_hidden(self) -> None:
        wrong = "应收 34560.00、已收 18036.00、未收 52596.00。"
        code, out, _ = _run_cli(
            ["ask", "A-301 还欠多少？"],
            turns=[_tool_turn("billing.statement.read", {}), ModelTurn(text=wrong)],
        )
        # 金额写反是"有业务结果 + 明确警告"，不是静默成功
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = json.loads(out)
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["trusted_conclusion"]["check_status"], "mismatch")
        self.assertEqual(
            payload["trusted_conclusion"]["fund_conclusion"]["outstanding_total"], "18036.00"
        )
        self.assertEqual(payload["model_narrative"]["answer"], wrong)
        kinds = {item["kind"] for item in payload["narrative_discrepancies"]}
        self.assertIn("fund", kinds)
        self.assertTrue(
            any("未收" in problem or "outstanding" in problem
                for item in payload["narrative_discrepancies"]
                for problem in item.get("problems", [])),
            payload["narrative_discrepancies"],
        )


class TestInvestigateDefaultSummary(unittest.TestCase):
    def test_deterministic_investigate_shows_authoritative_amounts(self) -> None:
        code, out, _ = _run_cli(["investigate"])
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = json.loads(out)
        amounts = payload["authoritative_amounts"]
        self.assertTrue(amounts, payload)
        billing = next(item for item in amounts if item["capability"] == "billing.statement")
        self.assertEqual(billing["source"], "tool_facts")
        self.assertEqual(billing["fund_conclusion"]["invoiced_total"], "52596.00")
        self.assertEqual(billing["fund_conclusion"]["paid_total"], "34560.00")
        self.assertEqual(billing["fund_conclusion"]["outstanding_total"], "18036.00")
        self.assertEqual(billing["check_status"], "not_checkable")
        self.assertIn("未收 18036.00", billing["rendered"])
        # 确定性引擎没有模型叙述：分栏为空，而不是把内部事实伪装成模型答案
        self.assertEqual(payload["model_narratives"], [])
        self.assertEqual(payload["narrative_discrepancies"], [])

    def test_scripted_investigate_marks_narrative_unverified(self) -> None:
        code, out, _ = _run_cli(["investigate", "--model-provider", "scripted"])
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = json.loads(out)
        self.assertTrue(payload["authoritative_amounts"])
        self.assertTrue(payload["model_narratives"], payload)
        billing = next(item for item in payload["authoritative_amounts"] if item["capability"] == "billing.statement")
        # 脚本化模型的总结没有绑定到应收/已收/未收字段 → 未验证（不是"通过"）
        self.assertEqual(billing["check_status"], "unverified")
        # Task 031 / 2.5：按 Agent 列出实际使用的模型（脚本化客户端）
        self.assertTrue(payload["agent_models"], payload)
        self.assertEqual(
            {entry["provider"] for entry in payload["agent_models"].values()}, {"scripted"}
        )

    def test_model_narrative_mismatch_appears_in_discrepancies(self) -> None:
        from app import investigation_demo

        # 先取到真实函数再 patch，否则 builder 内部会调用被 patch 的自身
        real_builder = investigation_demo.build_investigation_bundle
        captured: dict = {}

        def builder(**kwargs):  # noqa: ANN001
            captured.update(kwargs)
            allowed = {
                key: kwargs[key]
                for key in (
                    "principal_id",
                    "variant",
                    "max_tool_calls",
                    "max_revisions",
                    "backend",
                    "control_plane",
                    "run_id",
                    "trace_id",
                )
                if key in kwargs
            }
            return real_builder(
                **allowed,
                engine="llm",
                model_client=_WrongAmountModel(),
                max_model_calls=32,
                max_total_tokens=20000,
            )

        code, out, _ = _run_cli(["investigate"], bundle_builder=builder)
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = json.loads(out)
        billing = next(item for item in payload["authoritative_amounts"] if item["capability"] == "billing.statement")
        self.assertEqual(billing["fund_conclusion"]["outstanding_total"], "18036.00")
        self.assertEqual(billing["check_status"], "mismatch")
        narratives = payload["model_narratives"]
        self.assertTrue(any("已经全部结清" in item["answer"] for item in narratives), narratives)
        diffs = payload["narrative_discrepancies"]
        self.assertTrue(any(item.get("kind") == "fund" for item in diffs), diffs)


if __name__ == "__main__":
    unittest.main()
