"""Task 021 / N1：模型预算必须按**物理请求**记账。

核心不变量：`budget.used_model_calls == 客户端实际被调用次数`。

历史缺陷：预算 ID 只有 run/subtask/round。`BaseAgent` 重试或图补查时 round 重新从 1 开始，
新的真实请求复用了已结算的 ID，于是"客户端调了 2 次、账本记 1 次"，
`max_model_calls` 的上限形同虚设，失败重试的 token 成本也被低估。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, Sequence

from app.agents.base.contracts import AgentRequest, TokenUsage
from app.agents.factory import build_registry
from app.config.loader import load_agent_config
from app.llm.model_client import (
    ChatMessage,
    InvalidToolCallRecord,
    ModelToolCall,
    ModelTurn,
    ToolSpec,
)
from app.paths import CONFIG_DIR
from app.runtime.budget import Budget
from app.runtime.types import TraceLog, TrustedContext
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry
from app.fixtures.repository import FixtureRepository

LEASE = "lease_xh_a301_2025"


class _ScriptedPhysicalModel:
    """按脚本返回响应，并**如实统计物理调用次数**（这是本文件的判据）。"""

    provider = "fake"
    model_name = "scripted-physical"

    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = list(turns)
        self.calls = 0

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        self.calls += 1
        index = min(self.calls - 1, len(self._turns) - 1)
        return self._turns[index]


def _usage(tokens: int) -> TokenUsage:
    return TokenUsage(
        prompt_tokens=tokens // 2, completion_tokens=tokens - tokens // 2, total_tokens=tokens
    )


def _invalid(text: str = "", tokens: int = 10) -> ModelTurn:
    return ModelTurn(
        text=text,
        invalid_tool_calls=(
            InvalidToolCallRecord(name="billing.statement.read", error="bad args"),
        ),
        usage=_usage(tokens),
    )


def _answer(text: str = "未收 18036.00", tokens: int = 20) -> ModelTurn:
    return ModelTurn(text=text, finish_reason="stop", usage=_usage(tokens))


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _context(permissions: frozenset[str]) -> Any:
    trusted = TrustedContext(
        trace_id="trace_n1",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=permissions,
    )
    return trusted.to_agent_context(run_id="run_n1")


def _agent(*, budget: Budget, client: Any, max_retries: int = 1):
    config = load_agent_config(CONFIG_DIR / "billing.yaml").model_copy(
        update={"max_retries": max_retries}
    )
    report = build_registry(
        tool_registry=_registry(),
        budget=budget,
        trace_log=TraceLog(),
        engine="llm",
        model_client=client,
    )
    agent = report.registry.require_capability("billing.statement")
    return agent, config


class TestPhysicalModelCallAccounting(unittest.TestCase):
    def _run_agent(self, *, client: Any, budget: Budget, max_retries: int = 1):
        agent, _ = _agent(budget=budget, client=client, max_retries=max_retries)
        request = AgentRequest(
            task_id="n1",
            capability="billing.statement",
            payload={"lease_id": LEASE, "question": "A-301 还欠多少"},
        )
        result = asyncio.run(agent.handle(request, _context(frozenset({"billing.read"}))))
        return result, budget.snapshot()

    def test_retry_after_model_error_counts_every_physical_request(self) -> None:
        """回归 N1：修复前 physical=2 而账本=1、tokens 只记 10（实际 30）。"""

        client = _ScriptedPhysicalModel([_invalid(tokens=10), _answer(tokens=20)])
        budget = Budget(max_tool_calls=8, max_model_calls=10, max_total_tokens=1000)
        result, snapshot = self._run_agent(client=client, budget=budget)

        self.assertEqual(client.calls, 2, "首轮非法调用应触发一次重试")
        self.assertEqual(snapshot.used_model_calls, client.calls, "账本必须等于物理调用次数")
        self.assertEqual(snapshot.used_total_tokens, 30, "两次响应的 token 都要计入")
        self.assertEqual(result.metadata.attempt, 2)

    def test_failed_attempt_still_records_its_tokens(self) -> None:
        client = _ScriptedPhysicalModel([_invalid(tokens=10), _invalid(tokens=10)])
        budget = Budget(max_tool_calls=8, max_model_calls=10, max_total_tokens=1000)
        _, snapshot = self._run_agent(client=client, budget=budget, max_retries=1)
        self.assertEqual(snapshot.used_model_calls, 2)
        self.assertEqual(snapshot.used_total_tokens, 20, "失败尝试的 token 也是真实消耗")

    def test_max_model_calls_one_blocks_the_second_request(self) -> None:
        """验收要求：上限为 1 时不得发出第二个物理请求。"""

        client = _ScriptedPhysicalModel([_invalid(tokens=10), _answer(tokens=20)])
        budget = Budget(max_tool_calls=8, max_model_calls=1, max_total_tokens=1000)
        result, snapshot = self._run_agent(client=client, budget=budget)

        self.assertEqual(client.calls, 1, "预算耗尽后不得真正发请求")
        self.assertEqual(snapshot.used_model_calls, 1)
        self.assertEqual(snapshot.used_total_tokens, 10)
        self.assertIsNotNone(result.error)

    def test_token_overflow_is_recorded_not_dropped(self) -> None:
        """验收要求：token 超限后的真实消耗必须记录（不能少记）。"""

        client = _ScriptedPhysicalModel([_invalid(tokens=900), _answer(tokens=900)])
        budget = Budget(max_tool_calls=8, max_model_calls=10, max_total_tokens=1000)
        result, snapshot = self._run_agent(client=client, budget=budget)
        # token 只能事后知道：第一次请求无法事前拦截，第二次在本轮结束后才会被拦住
        self.assertEqual(client.calls, 2)
        self.assertEqual(snapshot.used_total_tokens, 1800, "两次真实消耗都必须入账")
        self.assertEqual(snapshot.exceeded_tokens, 800, "超出上限的部分单独标记")
        self.assertIsNotNone(result.error)

    def test_success_path_counts_each_request(self) -> None:
        """成功路径同样逐次记账：先调一次工具，再产出最终答案。"""

        class _ToolThenAnswer(_ScriptedPhysicalModel):
            async def complete(self, messages, tools):  # noqa: ANN001
                self.calls += 1
                if any(message.tool_calls for message in messages):
                    return _answer("未收 18036.00", tokens=20)
                exposed = {spec.tool_name: spec.name for spec in tools}
                return ModelTurn(
                    text="",
                    tool_calls=(
                        ModelToolCall(
                            call_id="c1",
                            name=exposed["billing.statement.read"],
                            arguments={"lease_id": LEASE},
                            arguments_json=json.dumps({"lease_id": LEASE}),
                        ),
                    ),
                    usage=_usage(10),
                )

        client = _ToolThenAnswer([])
        budget = Budget(max_tool_calls=8, max_model_calls=10, max_total_tokens=1000)
        result, snapshot = self._run_agent(client=client, budget=budget)
        self.assertEqual(client.calls, 2)
        self.assertEqual(snapshot.used_model_calls, 2)
        self.assertEqual(snapshot.used_total_tokens, 30)
        self.assertIsNotNone(result.output)
        self.assertEqual((result.output or {}).get("facts", {}).get("outstanding_total"), "18036.00")


class TestGraphRevisionAccounting(unittest.TestCase):
    """图补查（revision）会重跑子任务：每轮都是新的物理请求，必须逐次记账。"""

    def test_revision_counts_each_physical_request(self) -> None:
        from app.investigation_demo import build_investigation_bundle

        question = "A-301 租金和空调工单都对一下"

        class _RevisionModel:
            provider = "fake"
            model_name = "revision-model"

            def __init__(self) -> None:
                self.calls = 0

            async def complete(self, messages, tools):  # noqa: ANN001
                self.calls += 1
                exposed = {spec.tool_name: spec.name for spec in tools}
                called = {
                    call.name
                    for message in messages
                    for call in (message.tool_calls or ())
                }
                if not called:
                    # 首轮就返回非法调用，让本次子任务失败以触发补查
                    return _invalid(tokens=5)
                return _answer("已完成核对", tokens=7)

        client = _RevisionModel()
        bundle = build_investigation_bundle(
            engine="llm",
            model_client=client,
            max_tool_calls=8,
            max_model_calls=32,
            max_total_tokens=5000,
            max_revisions=1,
        )
        result = asyncio.run(
            bundle.investigator.investigate(
                question=question, lease_id=LEASE, context=bundle.context
            )
        )
        snapshot = bundle.budget.snapshot()
        self.assertEqual(
            snapshot.used_model_calls,
            client.calls,
            f"账本 {snapshot.used_model_calls} 必须等于物理调用 {client.calls}",
        )
        self.assertGreater(client.calls, len(result.results), "补查应产生额外物理请求")


if __name__ == "__main__":
    unittest.main()
