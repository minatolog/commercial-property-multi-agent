"""Task 024 / Q1：token 预算耗尽后必须**拦住下一次物理模型请求**。

历史缺陷（Task 022 复查 Q1）：超额用量能被记录，但 `reserve_model_call` 只看模型调用
次数、不看 token 剩余量。于是首次响应超出 token 上限后，图补查仍能预留下一次请求，
直到第二次响应返回才再次发现"已经耗尽"——两次真实请求、20 tokens、超出 15。

这套测试固定四条不变量：

1. 零额度（`max_total_tokens=0`）时一次请求都不发；
2. 首次响应造成的不可预知超额只发生一次，之后物理调用次数不再增长；
3. 模型调用次数还有余额时，也不能绕过已耗尽的 token 预算；
4. 顺序调用、并发共享预算、Agent 重试、图补查看到的是同一个闸门。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, Sequence

from app.agents.base.contracts import AgentRequest, TaskStatus, TokenUsage
from app.agents.base.errors import BudgetExhaustedError, ErrorCode
from app.agents.factory import build_registry
from app.config.loader import load_agent_config
from app.fixtures.repository import FixtureRepository
from app.investigation_demo import build_investigation_bundle, run_investigation
from app.llm.model_client import (
    ChatMessage,
    InvalidToolCallRecord,
    ModelToolCall,
    ModelTurn,
    ToolSpec,
)
from app.paths import CONFIG_DIR
from app.runtime.budget import Budget
from app.runtime.tool_loop import ToolLoopStopReason, run_tool_loop
from app.runtime.types import TraceLog, TrustedContext
from app.tools.executor import ToolExecutor
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry

LEASE = "lease_xh_a301_2025"
QUESTION = "商铺 A-301 还欠多少钱，顺便看下空调工单"


def _usage(tokens: int) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=tokens // 2,
        completion_tokens=tokens - tokens // 2,
        total_tokens=tokens,
    )


class _CountingModel:
    """每次响应固定消耗 N tokens，并如实统计物理请求次数。"""

    provider = "fake"
    model_name = "counting"

    def __init__(self, tokens: int = 10, text: str = "已核对。") -> None:
        self._tokens = tokens
        self._text = text
        self.calls = 0

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        self.calls += 1
        return ModelTurn(
            text=self._text, finish_reason="stop", usage=_usage(self._tokens)
        )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _context(run_id: str = "run_gate") -> Any:
    trusted = TrustedContext(
        trace_id="trace_gate",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=frozenset({"billing.read", "lease.read", "property.read"}),
    )
    return trusted.to_agent_context(run_id=run_id)


def _gather_all(worker: Any) -> Any:
    """在同一个事件循环里并发跑 6 个 worker（`gather` 必须在协程内创建）。"""

    async def runner() -> list[str]:
        return list(await asyncio.gather(*(worker(index) for index in range(6))))

    return runner()


class TestBudgetTokenGate(unittest.TestCase):
    """预算对象本身：闸门就在"预留一次物理请求"这一步，且在锁内判定。"""

    def test_zero_token_allowance_blocks_the_first_request(self) -> None:
        budget = Budget(max_tool_calls=4, max_model_calls=10, max_total_tokens=0)
        with self.assertRaises(BudgetExhaustedError):
            asyncio.run(budget.reserve_model_call("mc_1"))
        snapshot = budget.snapshot()
        self.assertEqual(snapshot.used_model_calls, 0)
        self.assertTrue(snapshot.tokens_exhausted)

    def test_unconfigured_token_budget_does_not_block(self) -> None:
        """`None` = 未配置上限（确定性路径），不应被误当成零额度。"""

        budget = Budget(max_tool_calls=4, max_model_calls=4)
        asyncio.run(budget.reserve_model_call("mc_1"))
        self.assertFalse(budget.snapshot().tokens_exhausted)

    def test_exhausted_tokens_beat_remaining_model_calls(self) -> None:
        """回归 Q1：请求次数还有 9 次余额，token 已耗尽则一律拒绝。"""

        budget = Budget(max_tool_calls=4, max_model_calls=10, max_total_tokens=5)
        asyncio.run(budget.reserve_model_call("mc_1"))
        asyncio.run(budget.settle("mc_1"))
        asyncio.run(budget.record_unbudgeted_tokens(10))

        snapshot = budget.snapshot()
        self.assertEqual(snapshot.used_model_calls, 1)
        self.assertEqual(snapshot.used_total_tokens, 10)
        self.assertEqual(snapshot.exceeded_tokens, 5)
        self.assertTrue(snapshot.tokens_exhausted)
        with self.assertRaises(BudgetExhaustedError):
            asyncio.run(budget.reserve_model_call("mc_2"))
        self.assertEqual(budget.snapshot().used_model_calls, 1)

    def test_concurrent_reservations_only_let_one_through(self) -> None:
        """并发共享同一预算：一个任务耗尽 token 后，其余任务同一刻被拦。"""

        budget = Budget(max_tool_calls=4, max_model_calls=10, max_total_tokens=5)
        physical = 0

        async def worker(index: int) -> str:
            nonlocal physical
            call_id = f"mc_worker_{index}"
            try:
                await budget.reserve_model_call(call_id)
            except BudgetExhaustedError:
                return "blocked"
            await budget.settle(call_id)
            physical += 1
            await budget.record_unbudgeted_tokens(10)
            return "called"

        outcomes = asyncio.run(_gather_all(worker))
        self.assertEqual(physical, 1, f"物理请求应只有 1 次: {outcomes}")
        self.assertEqual(outcomes.count("called"), 1)
        self.assertEqual(outcomes.count("blocked"), 5)

    def test_in_flight_usage_is_still_settled(self) -> None:
        """已经发生的用量必须如实入账（不是"因为超限就不记"）。"""

        budget = Budget(max_tool_calls=4, max_model_calls=4, max_total_tokens=5)
        asyncio.run(budget.reserve_model_call("mc_1"))
        asyncio.run(budget.record_unbudgeted_tokens(12))
        snapshot = budget.snapshot()
        self.assertEqual(snapshot.used_total_tokens, 12)
        self.assertEqual(snapshot.exceeded_tokens, 7)


class TestToolLoopTokenGate(unittest.TestCase):
    def _run(self, client: Any, budget: Budget) -> Any:
        registry = _registry()
        config = load_agent_config(CONFIG_DIR / "billing.yaml")
        executor = ToolExecutor(registry, budget, trace_log=TraceLog())
        from app.llm.model_client import ToolSpecBuilder

        context = _context()
        return asyncio.run(
            run_tool_loop(
                client=client,
                messages=(ChatMessage(role="user", content="A-301 还欠多少"),),
                tools=ToolSpecBuilder.build(
                    registry,
                    allowed_tools=config.allowed_tools,
                    permissions=context.permissions,
                ),
                executor=executor,
                context=context,
                agent_config=config,
                budget=budget,
                max_rounds=3,
            )
        )

    def test_zero_token_allowance_sends_no_request(self) -> None:
        client = _CountingModel()
        budget = Budget(max_tool_calls=4, max_model_calls=10, max_total_tokens=0)
        outcome = self._run(client, budget)
        self.assertEqual(client.calls, 0, "零额度时不得发出任何请求")
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.BUDGET_EXHAUSTED)
        self.assertEqual(budget.snapshot().used_model_calls, 0)

    def test_second_round_is_blocked_after_first_overshoot(self) -> None:
        """回归 Q1：上限 5、单次响应 10 tokens，只允许发生一次物理请求。"""

        client = _CountingModel(tokens=10)
        budget = Budget(max_tool_calls=4, max_model_calls=10, max_total_tokens=5)
        outcome = self._run(client, budget)
        snapshot = budget.snapshot()
        self.assertEqual(client.calls, 1)
        self.assertEqual(snapshot.used_model_calls, 1)
        self.assertEqual(snapshot.used_total_tokens, 10)
        self.assertEqual(snapshot.exceeded_tokens, 5)
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.BUDGET_EXHAUSTED)

    def test_exact_limit_still_blocks_the_next_round(self) -> None:
        """额度刚好用尽（没有超额）也必须停：再发一次只会继续超。"""

        client = _CountingModel(tokens=5)
        budget = Budget(max_tool_calls=4, max_model_calls=10, max_total_tokens=5)
        self._run(client, budget)
        self.assertEqual(client.calls, 1)
        self.assertEqual(budget.snapshot().exceeded_tokens, 0)
        self.assertTrue(budget.snapshot().tokens_exhausted)


class TestAgentRetryRespectsGate(unittest.TestCase):
    """Agent 重试不能绕过闸门：一次超额后不得再发第二次物理请求。"""

    def _agent(self, client: Any, budget: Budget) -> Any:
        report = build_registry(
            tool_registry=_registry(),
            budget=budget,
            trace_log=TraceLog(),
            engine="llm",
            model_client=client,
        )
        return report.registry.require_capability("billing.statement")

    def test_retry_after_model_error_does_not_send_another_request(self) -> None:
        class _InvalidFirstTurn:
            provider = "fake"
            model_name = "invalid-first"

            def __init__(self) -> None:
                self.calls = 0

            async def complete(self, messages, tools):  # noqa: ANN001
                self.calls += 1
                if self.calls == 1:
                    # 非法工具调用 → MODEL_ERROR（可重试），并消耗 10 tokens
                    return ModelTurn(
                        text="",
                        invalid_tool_calls=(
                            InvalidToolCallRecord(
                                name="billing.statement.read", error="bad args"
                            ),
                        ),
                        usage=_usage(10),
                    )
                return ModelTurn(text="未收 18036.00", finish_reason="stop", usage=_usage(10))

        client = _InvalidFirstTurn()
        budget = Budget(max_tool_calls=4, max_model_calls=10, max_total_tokens=5)
        agent = self._agent(client, budget)
        result = asyncio.run(
            agent.handle(
                AgentRequest(
                    task_id="t_retry",
                    capability="billing.statement",
                    payload={"lease_id": LEASE, "question": "欠多少"},
                ),
                _context("run_retry"),
            )
        )
        self.assertEqual(client.calls, 1, "首次超额后重试不得再发请求")
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.BUDGET_EXHAUSTED)


class TestGraphRevisionRespectsGate(unittest.TestCase):
    def test_revision_does_not_issue_a_second_request(self) -> None:
        """回归 Q1 的原始反例：图补查阶段物理调用仍为 1 次。"""

        client = _CountingModel(tokens=10)
        bundle = build_investigation_bundle(
            engine="llm",
            model_client=client,
            max_model_calls=10,
            max_total_tokens=5,
            max_revisions=1,
        )
        result = asyncio.run(
            run_investigation(bundle, question=QUESTION, lease_id=LEASE)
        )
        snapshot = bundle.budget.snapshot()
        self.assertEqual(client.calls, 1, "补查不得再发物理请求")
        self.assertEqual(snapshot.used_model_calls, 1)
        self.assertEqual(snapshot.used_total_tokens, 10)
        self.assertEqual(snapshot.exceeded_tokens, 5)
        self.assertEqual(result.verdict, "insufficient")
        codes = {failure["error_code"] for failure in result.failures}
        self.assertIn(ErrorCode.BUDGET_EXHAUSTED.value, codes)


class TestReportedUsageIsHonest(unittest.TestCase):
    """报告/快照里的数字与真实发生量一致（不能因闸门而少记）。"""

    def test_tokens_still_reported_after_gate(self) -> None:
        client = _CountingModel(tokens=10)
        bundle = build_investigation_bundle(
            engine="llm",
            model_client=client,
            max_model_calls=10,
            max_total_tokens=5,
        )
        asyncio.run(run_investigation(bundle, question=QUESTION, lease_id=LEASE))
        payload = bundle.budget.snapshot().model_dump()
        self.assertEqual(payload["used_total_tokens"], 10)
        self.assertEqual(payload["exceeded_tokens"], 5)
        self.assertTrue(payload["tokens_exhausted"])
        json.dumps(payload)  # 必须可序列化进报告


if __name__ == "__main__":
    unittest.main()
