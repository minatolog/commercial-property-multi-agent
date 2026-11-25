"""Task 038R：独立复查返修的回归测试（每个用例都能杀死对应变异）。

覆盖：

- 关闭 SDK 隐式重试：一次 `complete()` 只对应一次物理 HTTP 请求，且预算账本
  与物理请求数相等（复查 P2-2）；
- 同一轮的多个 tool_call 串行执行，顺序与 tool_call 顺序一致（复查 P3-1）；
- 模型超时的错误码仍是 TIMEOUT，但可重试；重试仍走同一个 Budget（复查 P3-3）；
- 综合节点使用注入的假客户端，不构造真实客户端（复查 P3-8）。

全部离线：HTTP 用 `httpx.MockTransport`，模型用脚本客户端，不调用付费接口。
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from typing import Any, Sequence
from unittest.mock import patch

import httpx

from app.agents.base import AgentRequest
from app.agents.base.errors import ErrorCode
from app.agents.base.llm_agent import LLMToolAgent
from app.config.loader import load_agent_config
from app.fixtures.repository import FixtureRepository
from app.llm.langchain_client import DEEPSEEK_BASE_URL, build_chat_client
from app.llm.model_client import (
    ChatMessage,
    FakeChatModelClient,
    ModelInvocationError,
    ModelToolCall,
    ModelTurn,
    ToolSpecBuilder,
)
from app.paths import CONFIG_DIR
from app.runtime.budget import Budget
from app.runtime.tool_loop import ToolLoopStopReason, run_tool_loop
from app.runtime.types import ToolExecution, ToolStatus, TraceLog, TrustedContext
from app.tools.executor import ToolExecutor
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry

LEASE = "lease_xh_a301_2025"
_PERMISSIONS = frozenset({"lease.read", "billing.read", "property.read"})


def _config():
    return load_agent_config(CONFIG_DIR / "single.yaml")


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _context():
    trusted = TrustedContext(
        trace_id="trace_task038r",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=_PERMISSIONS,
    )
    return trusted.to_agent_context(run_id="run_task038r")


# ---------------------------------------------------------------------------
# §2.1 SDK 重试关闭，物理请求 = 账本（P2-2）
# ---------------------------------------------------------------------------


def _chat_completion(content: str = "已核对") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-task038r",
            "object": "chat.completion",
            "created": 0,
            "model": "deepseek-flash",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


class _PhysicalRequestCounter:
    """可计数的假传输：正常 / 服务端 500 / 读超时。"""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.mode == "error":
            return httpx.Response(
                500, json={"error": {"message": "server exploded", "type": "server_error"}}
            )
        if self.mode == "timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        return _chat_completion()


def _client_with_mock_transport(counter: _PhysicalRequestCounter) -> Any:
    """用生产构造路径建 `ChatOpenAI`，只把底层 HTTP 传输换成 MockTransport。"""

    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key-not-used"}):
        client = build_chat_client(_config())
    chat_model = client._chat_model
    # 直接把 openai SDK 的 httpx 客户端换成 MockTransport：max_retries 等参数
    # 仍来自 `build_chat_client` 的构造结果，变异后即可观察到 SDK 自带重试。
    chat_model.root_async_client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(counter)
    )
    return client


def _run_model_only(client: Any, budget: Budget) -> Any:
    return asyncio.run(
        run_tool_loop(
            client=client,
            messages=(ChatMessage(role="user", content="A-301 还欠多少？"),),
            tools=(),
            executor=ToolExecutor(_registry(), budget, trace_log=TraceLog()),
            context=_context(),
            agent_config=_config(),
            budget=budget,
            max_rounds=1,
        )
    )


class TestSdkRetryIsDisabled(unittest.TestCase):
    def test_each_complete_is_exactly_one_physical_request(self) -> None:
        cases = (
            ("ok", ToolLoopStopReason.FINAL_ANSWER),
            ("error", ToolLoopStopReason.MODEL_ERROR),
            ("timeout", ToolLoopStopReason.MODEL_TIMEOUT),
        )
        for mode, expected in cases:
            with self.subTest(mode=mode):
                counter = _PhysicalRequestCounter(mode)
                client = _client_with_mock_transport(counter)
                budget = Budget(max_tool_calls=0, max_model_calls=5)
                outcome = _run_model_only(client, budget)

                self.assertEqual(outcome.stop_reason, expected)
                self.assertEqual(
                    len(counter.requests),
                    1,
                    f"{mode}: 一次 handler 调用只允许 1 次物理 HTTP 请求",
                )
                self.assertEqual(
                    budget.snapshot().used_model_calls,
                    len(counter.requests),
                    f"{mode}: 账本模型调用数必须等于物理请求数",
                )

        # 变异 `max_retries=0` → `2` 时，500/超时的物理请求数会变成 3，
        # 上面的等值断言失败（实测见 038 §10.3）。


# ---------------------------------------------------------------------------
# §2.3 工具串行锁（P3-1）
# ---------------------------------------------------------------------------


class _SlowExecutor(ToolExecutor):
    """记录并发峰值与起止顺序的假执行器。"""

    def __init__(self, budget: Budget) -> None:
        super().__init__(_registry(), budget, trace_log=TraceLog())
        self.events: list[str] = []
        self.active = 0
        self.peak = 0

    async def execute(  # type: ignore[override]
        self, tool_name: str, payload: dict[str, Any], *, context: Any, agent_config: Any
    ) -> ToolExecution:
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.events.append(f"start:{tool_name}")
        try:
            await asyncio.sleep(0.05)
        finally:
            self.active -= 1
        self.events.append(f"end:{tool_name}")
        return ToolExecution(
            call_id=f"tc_{len(self.events)}",
            tool_name=tool_name,
            status=ToolStatus.OK,
            data={},
            attempts=1,
        )


class TestToolCallsAreSerialized(unittest.TestCase):
    def test_two_tool_calls_in_one_round_run_sequentially_in_order(self) -> None:
        arguments = {"lease_id": LEASE}
        arguments_json = json.dumps(arguments)
        calls = (
            ModelToolCall(
                call_id="call_a",
                name="billing.statement.read",
                arguments=arguments,
                arguments_json=arguments_json,
            ),
            ModelToolCall(
                call_id="call_b",
                name="billing.arrears.calculate",
                arguments=arguments,
                arguments_json=arguments_json,
            ),
        )
        client = FakeChatModelClient(
            [ModelTurn(text="", tool_calls=calls), ModelTurn(text="已完成")]
        )
        budget = Budget(max_tool_calls=5, max_model_calls=5)
        executor = _SlowExecutor(budget)
        context = _context()
        specs = ToolSpecBuilder.build(
            _registry(),
            allowed_tools=_config().allowed_tools,
            permissions=context.permissions,
        )
        outcome = asyncio.run(
            run_tool_loop(
                client=client,
                messages=(ChatMessage(role="user", content="q"),),
                tools=specs,
                executor=executor,
                context=context,
                agent_config=_config(),
                budget=budget,
                max_rounds=3,
            )
        )

        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.FINAL_ANSWER)
        self.assertEqual(executor.peak, 1, "同一轮的多个 tool_call 必须串行执行")
        self.assertEqual(
            executor.events,
            [
                "start:billing.statement.read",
                "end:billing.statement.read",
                "start:billing.arrears.calculate",
                "end:billing.arrears.calculate",
            ],
            "执行顺序必须与 tool_call 顺序一致",
        )


# ---------------------------------------------------------------------------
# §3.1 模型超时可重试（P3-3）
# ---------------------------------------------------------------------------


class _ProbeAgent(LLMToolAgent):
    """最小 LLM Agent：只验证模型超时的重试/预算语义，不涉及领域契约。"""

    name = "task038r-probe"
    version = "1.0.0"
    description = "Task 038R 超时重试探针"
    capabilities = frozenset({"probe.run"})


class _TimeoutThenAnswer:
    provider = "fake"
    model_name = "timeout-then-answer"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[Any]
    ) -> ModelTurn:
        self.calls += 1
        if self.calls == 1:
            raise ModelInvocationError("模拟模型超时", code=ErrorCode.TIMEOUT)
        return ModelTurn(text="已完成", finish_reason="stop")


def _run_probe(client: Any, budget: Budget) -> Any:
    config = _config().model_copy(
        update={"max_retries": 1, "allowed_tools": ["billing.statement.read"]}
    )
    agent = _ProbeAgent(
        config,
        model_client=client,
        tool_registry=_registry(),
        budget=budget,
        trace_log=TraceLog(),
    )
    request = AgentRequest(task_id="task038r", capability="probe.run", payload={})
    return asyncio.run(agent.handle(request, _context())), budget.snapshot()


class TestModelTimeoutRetrySemantics(unittest.TestCase):
    def test_first_timeout_then_success_retries_and_counts_each_call(self) -> None:
        client = _TimeoutThenAnswer()
        result, snapshot = _run_probe(client, Budget(max_tool_calls=4, max_model_calls=10))

        self.assertTrue(result.ok, result.error)
        self.assertEqual(client.calls, 2, "第一次超时后应重试一次")
        self.assertEqual(snapshot.used_model_calls, 2, "每次重试都计入模型调用账本")
        self.assertEqual(result.metadata.attempt, 2)

    def test_budget_of_one_prevents_retry_and_fails_clearly(self) -> None:
        client = _TimeoutThenAnswer()
        result, snapshot = _run_probe(client, Budget(max_tool_calls=4, max_model_calls=1))

        self.assertFalse(result.ok)
        self.assertEqual(client.calls, 1, "预算只够 1 次时不得发出第二个物理请求")
        self.assertEqual(snapshot.used_model_calls, 1)
        self.assertEqual(result.error.code, ErrorCode.BUDGET_EXHAUSTED)


# ---------------------------------------------------------------------------
# §3.2 综合节点使用注入的客户端（P3-8）
# ---------------------------------------------------------------------------


class TestSynthesisUsesInjectedClient(unittest.TestCase):
    def test_injected_client_is_used_and_no_real_client_is_built(self) -> None:
        from app.investigation_demo import build_investigation_bundle

        synthesis = FakeChatModelClient(
            [
                '{"facts":[0],"conflicts":[],"gaps":[],'
                '"actions":["communicate_verified_facts"]}'
            ]
        )

        def domain_factory(config: Any) -> Any:
            return FakeChatModelClient([], model_name="fake-domain")

        saved = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            with patch(
                "app.investigation_demo.build_model_client_for_config",
                side_effect=AssertionError("不应构造任何真实模型客户端"),
            ) as builder:
                bundle = build_investigation_bundle(
                    model_provider="deepseek",
                    client_factory=domain_factory,
                    planner_client=synthesis,
                    enable_synthesis=True,
                    max_model_calls=8,
                    max_total_tokens=1000,
                )
        finally:
            if saved is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved

        self.assertFalse(builder.called, "注入客户端时不得调用真实客户端构造")
        synthesizer = bundle.investigator.synthesizer
        self.assertIsNotNone(synthesizer)
        self.assertIs(synthesizer.client, synthesis)

        report = {
            "question": "A-301 欠款核对",
            "findings": [{"statement": "未收 18036.00"}],
            "conflicts": [],
            "missing_information": [],
            "verdict": "clear",
        }
        selection = asyncio.run(synthesizer(report, bundle.context))
        self.assertEqual(selection["status"], "completed")
        self.assertEqual(selection["provider"], "fake")
        self.assertEqual(len(synthesis.calls), 1, "综合节点实际使用的必须是注入的假客户端")


if __name__ == "__main__":
    unittest.main()
