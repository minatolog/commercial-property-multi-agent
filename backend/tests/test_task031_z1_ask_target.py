"""Task 031 / 2.1（Z1）回归：`ask` 必须携带可信目标。

原始反例（Task 025 独立复查）：`ask "A301现在还欠多少"` 走真实 CLI/装配/Runtime 路径，
模型调用 B-101 账单并回答"A301 应收 0、已收 0、未收 0，已经结清"，结果仍是
`exit=0、status=success`。根因：默认 `build_single_bundle` 只传 `question`，没有
`lease_id`/`unit_id`，`TaskScope` 进入 `explain` 形态，目标约束完全失效。

本文件全部经由 `app.cli.main(...)`（真实参数解析 → 目标解析 → 装配 → Runtime → 摘要），
只替换模型响应，不手工构造带 `lease_id` 的 `AgentRequest`。
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

LEASE_A301 = "lease_xh_a301_2025"
LEASE_A302 = "lease_xh_a302_2025"
LEASE_B101 = "lease_jl_b101_2025"

_PRINCIPAL_ENV = {"DEMO_PRINCIPAL_ID": "principal_ops_xinghui"}


def _tool_turn(name: str, arguments: dict) -> ModelTurn:
    return ModelTurn(
        text="",
        tool_calls=(
            ModelToolCall(
                call_id=f"call_{name.replace('.', '_')}",
                name=name,
                arguments=dict(arguments),
                arguments_json=json.dumps(arguments, ensure_ascii=False),
            ),
        ),
    )


def _run(argv: list[str], *, turns: list[ModelTurn] | None = None) -> tuple[int, str, str]:
    """执行 CLI；`turns` 非空时替换模型客户端（其余路径全部为真实实现）。"""

    stdout, stderr = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, _PRINCIPAL_ENV, clear=False):
        with redirect_stdout(stdout), redirect_stderr(stderr):
            if turns is None:
                code = cli.main(argv)
            else:
                client = FakeChatModelClient(turns, provider="fake", model_name="test-fake")
                with patch("app.single_demo._build_model_client", return_value=client):
                    code = cli.main(argv)
    return code, stdout.getvalue(), stderr.getvalue()


def _payload(text: str) -> dict:
    return json.loads(text)


class TestZ1OriginalCounterexample(unittest.TestCase):
    def test_wrong_target_billing_call_cannot_succeed(self) -> None:
        """Z1 原始反例：问题 A-301，模型却去查 B-101。"""

        code, out, err = _run(
            ["ask", "A301现在还欠多少", "--provider", "fake"],
            turns=[
                _tool_turn("billing.statement.read", {"lease_id": LEASE_B101}),
                ModelTurn(text="A301 应收 0.00、已收 0.00、未收 0.00，已经结清。"),
            ],
        )
        self.assertEqual(code, cli.EXIT_BUSINESS_FAILURE, out + err)
        payload = _payload(out)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "insufficient_evidence")
        # 目标来自问题文本解析（不是模型），并且被注入到可信范围
        self.assertEqual(payload["target"]["mode"], "targeted")
        self.assertEqual(payload["target"]["lease_id"], LEASE_A301)
        self.assertEqual(payload["target"]["unit_code"], "A-301")
        self.assertEqual(payload["target"]["source"], "question_parse")
        # 失败的跨目标调用不得成为证据，也不得产生可信资金结论
        self.assertEqual(payload["evidence_count"], 0)
        self.assertEqual(payload["trusted_conclusion"]["source"], "none")
        # 旧参数仍可用，但必须向 stderr 明示弃用
        self.assertIn("已弃用", err)

    def test_foreign_lease_is_denied_and_never_becomes_facts(self) -> None:
        code, out, _ = _run(
            ["ask", "A-301 还欠多少？"],
            turns=[
                _tool_turn("billing.statement.read", {"lease_id": LEASE_B101}),
                ModelTurn(text="已核对，没有问题。"),
            ],
        )
        self.assertEqual(code, cli.EXIT_BUSINESS_FAILURE)
        payload = _payload(out)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "insufficient_evidence")
        # 跨项目调用在工具边界就被拒绝，不会产生任何 ToolExecution
        self.assertEqual(payload["tool_calls"], [])
        failed = payload["failed_tool_calls"]
        self.assertTrue(failed, payload)
        self.assertEqual(failed[0]["status"], "rejected_arguments")
        self.assertIn("超出本次任务范围", failed[0]["message"])
        self.assertEqual(payload["evidence_count"], 0)


class TestZ1TargetCannotBeChanged(unittest.TestCase):
    def test_model_requesting_another_same_project_lease_is_rejected(self) -> None:
        """同项目、有权限，但目标不同：也必须拒绝（这是 Z1 与 Q2 的交界）。"""

        code, out, _ = _run(
            ["ask", "A-301 还欠多少？"],
            turns=[
                _tool_turn("billing.statement.read", {"lease_id": LEASE_A302}),
                ModelTurn(text="A-301 应收 0.00、已收 0.00、未收 0.00，已经结清。"),
            ],
        )
        self.assertEqual(code, cli.EXIT_BUSINESS_FAILURE)
        payload = _payload(out)
        self.assertEqual(payload["status"], "failed")
        self.assertTrue(
            any("超出本次任务范围" in item["message"] for item in payload["failed_tool_calls"]),
            payload["failed_tool_calls"],
        )
        self.assertEqual(payload["evidence_count"], 0)

    def test_tool_output_of_another_lease_is_not_accepted(self) -> None:
        """模型用 unit_code 绕过参数注入时，仍必须失败且不得产生证据。"""

        code, out, _ = _run(
            ["ask", "A-301 的租约情况如何？"],
            turns=[
                _tool_turn("lease.lookup", {"unit_code": "A-302"}),
                ModelTurn(text="A-301 租约状态 active。"),
            ],
        )
        self.assertEqual(code, cli.EXIT_BUSINESS_FAILURE)
        payload = _payload(out)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["error"]["code"], "insufficient_evidence")
        self.assertEqual(payload["evidence_count"], 0)
        self.assertTrue(payload["failed_tool_calls"], payload["failed_tool_calls"])
        self.assertEqual(payload["target"]["lease_id"], LEASE_A301)


class TestZ1OmittedTargetIsInjected(unittest.TestCase):
    def test_omitted_lease_id_is_filled_from_trusted_flag(self) -> None:
        code, out, _ = _run(
            ["ask", "A-301 还欠多少？", "--lease", LEASE_A301],
            turns=[
                _tool_turn("billing.statement.read", {}),
                ModelTurn(text="应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
        )
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = _payload(out)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["target"]["source"], "cli_flag")
        self.assertEqual(payload["target"]["lease_id"], LEASE_A301)
        conclusion = payload["trusted_conclusion"]["fund_conclusion"]
        self.assertEqual(conclusion["outstanding_total"], "18036.00")
        self.assertEqual(payload["trusted_conclusion"]["check_status"], "verified")
        self.assertEqual(payload["narrative_discrepancies"], [])

    def test_unit_flag_resolves_lease(self) -> None:
        code, out, _ = _run(
            ["ask", "现在还欠多少钱？", "--unit", "A-301"],
            turns=[
                _tool_turn("billing.statement.read", {}),
                ModelTurn(text="应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
        )
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = _payload(out)
        self.assertEqual(payload["target"]["source"], "cli_flag")
        self.assertEqual(payload["target"]["lease_id"], LEASE_A301)
        self.assertEqual(payload["target"]["unit_id"], "unit_xh_a301")


class TestZ1BusinessQuestionCannotBecomeExplain(unittest.TestCase):
    def test_business_question_without_target_is_usage_error(self) -> None:
        code, out, err = _run(["ask", "现在一共欠多少钱？"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertEqual(out.strip(), "")
        self.assertIn("可信目标", err)

    def test_question_mentioning_unknown_unit_is_usage_error(self) -> None:
        code, _, err = _run(["ask", "C-999 还欠多少？"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("无法解析", err)

    def test_explicit_target_conflicting_with_question_is_rejected(self) -> None:
        code, _, err = _run(
            ["ask", "A-301 还欠多少？", "--lease", LEASE_A302]
        )
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("不一致", err)

    def test_unknown_lease_flag_is_rejected(self) -> None:
        code, _, err = _run(["ask", "还欠多少钱？", "--lease", "lease_does_not_exist"])
        self.assertEqual(code, cli.EXIT_USAGE)
        self.assertIn("不可用", err)

    def test_pure_explain_question_without_target_still_works(self) -> None:
        """纯说明问题（没有业务领域词）允许无目标执行，但必须是 explain 形态。"""

        code, out, _ = _run(["ask", "请解释一下什么是尽职调查。"])
        self.assertEqual(code, cli.EXIT_OK, out)
        payload = _payload(out)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["target"]["mode"], "explain")
        self.assertEqual(payload["target"]["source"], "none")
        self.assertEqual(payload["trusted_conclusion"]["source"], "none")


if __name__ == "__main__":
    unittest.main()
