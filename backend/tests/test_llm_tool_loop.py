"""Task 008：LangChain 适配层与单 Agent 工具调用闭环测试。

全部离线：模型用 `FakeChatModelClient`，数据用 fixture，不访问网络。
真实 DeepSeek 调用需要 `DEEPSEEK_API_KEY`，本文件只验证"缺密钥时明确失败"。
"""

from __future__ import annotations

import asyncio
import json
import os
import unittest
from decimal import Decimal

from app.agents.base import AgentRequest
from app.agents.base.errors import AgentError, ErrorCode, MissingApiKeyError
from app.config.loader import load_agent_config
from app.llm.model_client import (
    ChatMessage,
    FakeChatModelClient,
    ModelToolCall,
    ModelTurn,
    ToolSpec,
    ToolSpecBuilder,
    parse_tool_call,
)
from app.paths import CONFIG_DIR
from app.runtime.budget import Budget
from app.runtime.tool_loop import ToolLoopStopReason, run_tool_loop
from app.runtime.types import TraceLog
from app.single_demo import SINGLE_CAPABILITY, build_single_bundle, run_single
from app.tools.executor import ToolExecutor
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry
from app.fixtures.repository import FixtureRepository


def _tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _config(**overrides):
    base = load_agent_config(CONFIG_DIR / "single.yaml")
    return base.model_copy(update=overrides) if overrides else base


def _turn(text="", *, tool_name=None, arguments=None, call_id="call_1") -> ModelTurn:
    if tool_name is None:
        return ModelTurn(text=text)
    args = dict(arguments or {})
    return ModelTurn(
        text=text,
        tool_calls=(
            ModelToolCall(
                call_id=call_id,
                name=tool_name,
                arguments=args,
                arguments_json=json.dumps(args),
            ),
        ),
    )


class TestInvalidModelResponses(unittest.TestCase):
    """回归 F6：非法/异常模型响应不得被当成"成功回答"。

    这些用例走**真实**的 LangChain 响应转换（`_to_model_turn`），
    而不是只构造 Fake 的 ModelTurn——否则测不到 provider 适配层丢数据的问题。
    """

    def _loop(self, model):
        return _loop_run(model)

    def test_invalid_tool_call_is_not_treated_as_final_answer(self) -> None:
        from app.llm.langchain_client import _to_model_turn

        class _Msg:
            content = ""
            tool_calls = []
            invalid_tool_calls = [
                {"name": "billing.statement.read", "args": "{bad json", "id": "c1",
                 "error": "Failed to parse tool arguments"}
            ]
            response_metadata = {"finish_reason": "tool_calls"}
            usage_metadata = None

        turn = _to_model_turn(_Msg())
        self.assertEqual(turn.tool_calls, ())
        self.assertEqual(len(turn.invalid_tool_calls), 1)

        class _Model(_SingleTurnModel):
            def _next(self, messages):  # noqa: ANN001
                return turn

        outcome = self._loop(_Model())
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.MODEL_ERROR)
        self.assertTrue(any("非法工具调用" in item for item in outcome.warnings))

    def test_truncated_output_is_not_final_answer(self) -> None:
        class _Model(_SingleTurnModel):
            def _next(self, messages):  # noqa: ANN001
                return ModelTurn(text="应收 52596.00，", finish_reason="length")

        outcome = self._loop(_Model())
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.MODEL_ERROR)
        self.assertTrue(any("截断" in item for item in outcome.warnings))

    def test_empty_output_without_evidence_is_not_success(self) -> None:
        class _Model(_SingleTurnModel):
            def _next(self, messages):  # noqa: ANN001
                return ModelTurn(text="")

        outcome = self._loop(_Model())
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.MODEL_ERROR)

    def test_normal_final_answer_still_succeeds(self) -> None:
        class _Model(_SingleTurnModel):
            def _next(self, messages):  # noqa: ANN001
                return ModelTurn(text="未收 18036.00", finish_reason="stop")

        outcome = self._loop(_Model())
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.FINAL_ANSWER)
        self.assertIn("18036.00", outcome.answer)

    def test_empty_answer_after_tool_calls_is_not_success(self) -> None:
        """回归 R5：调过工具不等于完成了问答，空最终文本不能标成 final_answer。"""

        class _Model(_SingleTurnModel):
            def __init__(self) -> None:
                self.calls = 0

            def _next(self, messages):  # noqa: ANN001
                self.calls += 1
                if self.calls == 1:
                    return _turn(
                        tool_name="billing.statement.read",
                        arguments={"lease_id": "lease_xh_a301_2025"},
                    )
                return ModelTurn(text="")

        model = _Model()
        outcome = self._loop(model)
        self.assertEqual(model.calls, 2, "第一轮应真的调用了工具")
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.MODEL_ERROR)
        self.assertTrue(outcome.tool_executions, "工具确实执行过")
        self.assertTrue(outcome.evidence, "工具确实产出过证据")
        self.assertTrue(any("没有给出任何回答文本" in item for item in outcome.warnings))

    def test_failed_tool_then_empty_answer_is_not_success(self) -> None:
        class _Model(_SingleTurnModel):
            def __init__(self) -> None:
                self.calls = 0

            def _next(self, messages):  # noqa: ANN001
                self.calls += 1
                if self.calls == 1:
                    return _turn(
                        tool_name="billing.statement.read",
                        arguments={"lease_id": "lease_jl_b101_2025"},
                    )
                return ModelTurn(text="")

        outcome = self._loop(_Model())
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.MODEL_ERROR)

    def test_answer_after_tool_calls_still_succeeds(self) -> None:
        class _Model(_SingleTurnModel):
            def __init__(self) -> None:
                self.calls = 0

            def _next(self, messages):  # noqa: ANN001
                self.calls += 1
                if self.calls == 1:
                    return _turn(
                        tool_name="billing.statement.read",
                        arguments={"lease_id": "lease_xh_a301_2025"},
                    )
                return ModelTurn(text="未收 18036.00", finish_reason="stop")

        outcome = self._loop(_Model())
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.FINAL_ANSWER)
        self.assertIn("18036.00", outcome.answer)


class _SingleTurnModel:
    """最小模型桩：只实现 `complete`（异步），供上面的用例使用。"""

    provider = "fake"
    model_name = "single-turn"

    async def complete(self, messages, tools):  # noqa: ANN001
        return self._next(messages)

    def _next(self, messages):  # noqa: ANN001, pragma: no cover - 由子类实现
        raise NotImplementedError


def _context() -> object:
    from app.runtime.types import TrustedContext

    trusted = TrustedContext(
        trace_id="trace_f6",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=frozenset({"lease.read", "billing.read", "property.read"}),
    )
    return trusted.to_agent_context(run_id="run_f6")


def _loop_run(model: object):
    registry = _tool_registry()
    budget = Budget(max_tool_calls=4, max_model_calls=4)
    executor = ToolExecutor(registry, budget, trace_log=TraceLog())
    context = _context()
    return asyncio.run(
        run_tool_loop(
            client=model,
            messages=(ChatMessage(role="user", content="A-301 还欠多少？"),),
            tools=ToolSpecBuilder.build(
                registry,
                allowed_tools=_config().allowed_tools,
                permissions=context.permissions,  # type: ignore[attr-defined]
            ),
            executor=executor,
            context=context,
            agent_config=_config(),
            budget=budget,
            max_rounds=2,
        )
    )


class TestToolSpecBuilder(unittest.TestCase):
    def test_only_allowed_and_permitted_tools_are_exposed(self) -> None:
        registry = _tool_registry()
        config = _config()

        all_specs = ToolSpecBuilder.build(
            registry,
            allowed_tools=config.allowed_tools,
            permissions=frozenset({"lease.read", "billing.read", "property.read"}),
        )
        self.assertEqual(
            {spec.name for spec in all_specs},
            set(config.allowed_tools),
        )

        read_only_billing = ToolSpecBuilder.build(
            registry,
            allowed_tools=config.allowed_tools,
            permissions=frozenset({"billing.read"}),
        )
        self.assertEqual(
            {spec.name for spec in read_only_billing},
            {"billing.statement.read", "billing.arrears.calculate"},
        )

    def test_unimplemented_declared_tool_is_not_exposed(self) -> None:
        registry = _tool_registry()
        specs = ToolSpecBuilder.build(
            registry,
            allowed_tools=("lease.lookup", "lease.term_extract"),
            permissions=frozenset({"lease.read"}),
        )
        self.assertEqual({spec.name for spec in specs}, {"lease.lookup"})

    def test_spec_parameters_come_from_input_schema(self) -> None:
        registry = _tool_registry()
        specs = ToolSpecBuilder.build(
            registry,
            allowed_tools=("lease.lookup",),
            permissions=frozenset({"lease.read"}),
        )
        schema = specs[0].parameters
        self.assertEqual(schema.get("type"), "object")
        self.assertIn("properties", schema)


class TestToolCallParsing(unittest.TestCase):
    def test_valid_json_object_parses(self) -> None:
        call = parse_tool_call(
            call_id="c1", name="lease.lookup", arguments_json='{"lease_id": "x"}'
        )
        self.assertIsNone(call.parse_error)
        self.assertEqual(call.arguments, {"lease_id": "x"})

    def test_invalid_json_yields_parse_error_not_exception(self) -> None:
        call = parse_tool_call(call_id="c1", name="lease.lookup", arguments_json="{oops")
        self.assertIsNotNone(call.parse_error)
        self.assertEqual(call.arguments, {})

    def test_non_object_json_is_rejected(self) -> None:
        call = parse_tool_call(call_id="c1", name="lease.lookup", arguments_json="[1,2]")
        self.assertIsNotNone(call.parse_error)

    def test_empty_arguments_are_allowed(self) -> None:
        call = parse_tool_call(call_id="c1", name="lease.lookup", arguments_json="")
        self.assertIsNone(call.parse_error)
        self.assertEqual(call.arguments, {})


class TestFakeClient(unittest.TestCase):
    def test_records_calls_and_exhausts(self) -> None:
        client = FakeChatModelClient(["a", "b"])
        first = asyncio.run(client.complete([], []))
        self.assertEqual(first.text, "a")
        self.assertEqual(client.remaining, 1)
        asyncio.run(client.complete([], []))
        with self.assertRaises(AgentError):
            asyncio.run(client.complete([], []))


class TestToolLoop(unittest.TestCase):
    def _run(self, client, *, max_rounds=3, budget=None, context=None, messages=None):
        registry = _tool_registry()
        budget = budget or Budget(max_tool_calls=5, max_model_calls=5, max_total_tokens=1000)
        executor = ToolExecutor(registry, budget, trace_log=TraceLog())
        from app.runtime.types import TrustedContext

        trusted = TrustedContext(
            trace_id="trace_test",
            principal_id="principal_ops_xinghui",
            project_ids=frozenset({"prj_xinghui"}),
            permissions=frozenset({"lease.read", "billing.read", "property.read"}),
        )
        agent_context = context or trusted.to_agent_context(run_id="run_test")
        tools = ToolSpecBuilder.build(
            registry,
            allowed_tools=_config().allowed_tools,
            permissions=agent_context.permissions,
        )
        return asyncio.run(
            run_tool_loop(
                client=client,
                messages=messages or (ChatMessage(role="user", content="q"),),
                tools=tools,
                executor=executor,
                context=agent_context,
                agent_config=_config(),
                budget=budget,
                max_rounds=max_rounds,
            )
        )

    def test_single_tool_call_then_final_answer(self) -> None:
        client = FakeChatModelClient(
            [
                _turn(tool_name="billing.arrears.calculate", arguments={"lease_id": "lease_xh_a301_2025"}),
                ModelTurn(text="未收 18036.00"),
            ]
        )
        outcome = self._run(client)
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.FINAL_ANSWER)
        self.assertEqual(outcome.rounds, 2)
        self.assertEqual(len(outcome.tool_executions), 1)
        execution = outcome.tool_executions[0]
        self.assertTrue(execution.ok)
        self.assertEqual(Decimal(execution.data["outstanding_total"]), Decimal("18036.00"))
        self.assertTrue(outcome.evidence)

        # 工具结果确实回传给了模型：第二次调用里存在 tool 角色消息且含金额
        second_messages = client.calls[1][0]
        tool_messages = [m for m in second_messages if m.role == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("18036.00", tool_messages[0].content)
        self.assertEqual(tool_messages[0].tool_call_id, "call_1")

        # 模型第一次调用时拿到了工具清单
        self.assertTrue(len(client.calls[0][1]) >= 1)
        self.assertIn(
            "billing.arrears.calculate", {spec.name for spec in client.calls[0][1]}
        )

    def test_max_rounds_is_enforced(self) -> None:
        # 模型永远只调工具、不给答案
        turns = [
            _turn(tool_name="lease.lookup", arguments={"lease_id": "lease_xh_a301_2025"}, call_id=f"c{i}")
            for i in range(5)
        ]
        client = FakeChatModelClient(turns)
        outcome = self._run(client, max_rounds=3)
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.MAX_ROUNDS)
        self.assertEqual(outcome.rounds, 3)
        self.assertEqual(len(outcome.tool_executions), 3)
        self.assertTrue(any("最大轮次" in warning for warning in outcome.warnings))

    def test_invalid_arguments_feed_back_without_executing_tool(self) -> None:
        bad_call = ModelToolCall(
            call_id="bad1",
            name="lease.lookup",
            arguments_json="{not json",
            parse_error="参数不是合法 JSON",
        )
        client = FakeChatModelClient(
            [ModelTurn(text="", tool_calls=(bad_call,)), ModelTurn(text="已修正")]
        )
        outcome = self._run(client)
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.FINAL_ANSWER)
        self.assertEqual(len(outcome.tool_executions), 0)  # 未执行工具
        tool_messages = [m for m in client.calls[1][0] if m.role == "tool"]
        self.assertIn("invalid_tool_arguments", tool_messages[0].content)

    def test_tool_denied_is_fed_back_not_raised(self) -> None:
        client = FakeChatModelClient(
            [
                _turn(tool_name="billing.arrears.calculate", arguments={"lease_id": "lease_jl_b101_2025"}),
                ModelTurn(text="无权访问"),
            ]
        )
        outcome = self._run(client)
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.FINAL_ANSWER)
        execution = outcome.tool_executions[0]
        self.assertFalse(execution.ok)
        self.assertEqual(execution.error.code, ErrorCode.PROJECT_SCOPE_DENIED)
        self.assertIsNone(execution.data)

    def test_model_error_stops_with_explicit_reason(self) -> None:
        client = FakeChatModelClient([])  # 第一次调用即耗尽 -> ModelInvocationError
        outcome = self._run(client)
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.MODEL_ERROR)
        self.assertFalse(outcome.completed)
        self.assertTrue(any("模型调用失败" in w for w in outcome.warnings))

    def test_model_budget_exhaustion_stops(self) -> None:
        budget = Budget(max_tool_calls=5, max_model_calls=1, max_total_tokens=0)
        # 第一轮要求工具调用 -> 需要第二次模型调用 -> 预算不足必须明确停止
        client = FakeChatModelClient(
            [
                _turn(tool_name="lease.lookup", arguments={"lease_id": "lease_xh_a301_2025"}),
                ModelTurn(text="y"),
            ]
        )
        outcome = self._run(client, budget=budget)
        self.assertEqual(outcome.stop_reason, ToolLoopStopReason.BUDGET_EXHAUSTED)
        self.assertEqual(budget.snapshot().used_model_calls, 1)

    def test_usage_is_accumulated(self) -> None:
        from app.agents.base.contracts import TokenUsage

        client = FakeChatModelClient(
            [
                ModelTurn(
                    text="",
                    tool_calls=(
                        ModelToolCall(
                            call_id="c1",
                            name="lease.lookup",
                            arguments={"lease_id": "lease_xh_a301_2025"},
                            arguments_json='{"lease_id": "lease_xh_a301_2025"}',
                        ),
                    ),
                    usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                ),
                ModelTurn(
                    text="done",
                    usage=TokenUsage(prompt_tokens=20, completion_tokens=5, total_tokens=25),
                ),
            ]
        )
        outcome = self._run(client)
        self.assertEqual(outcome.usage.total_tokens, 40)
        self.assertEqual(outcome.usage.prompt_tokens, 30)


class TestSingleAgentEndToEnd(unittest.TestCase):
    def test_fake_provider_runs_tool_and_returns_evidence(self) -> None:
        bundle = build_single_bundle(question="A-301 现在还有多少钱没交？")
        result = asyncio.run(run_single(bundle))
        self.assertTrue(result.ok, result.error)
        output = result.output or {}
        self.assertEqual(output["stop_reason"], "final_answer")
        self.assertEqual(output["rounds"], 2)
        self.assertGreaterEqual(len(result.evidence), 1)
        self.assertTrue(all(item.synthetic for item in result.evidence))
        self.assertTrue(all(item.source_tool for item in result.evidence))
        # Trace 必须经共享日志被 Runtime 看到（否则 ask 模式会显示 0 条）
        self.assertEqual(len(result.tool_traces), 1)
        self.assertEqual(result.tool_traces[0].tool_name, "billing.arrears.calculate")

    def test_variant_changes_amount(self) -> None:
        bundle = build_single_bundle(
            question="10 月账单是否多收？", variant="v_oct_rent_corrected"
        )
        result = asyncio.run(run_single(bundle))
        self.assertTrue(result.ok)
        arrears = result.output["tool_calls"]
        self.assertEqual(len(arrears), 1)

    def test_missing_model_client_fails_loudly(self) -> None:
        from app.agents.single.agent import SingleToolAgent

        agent = SingleToolAgent(_config(), tool_registry=_tool_registry())
        context = build_single_bundle(question="q").trusted.to_agent_context(run_id="r")
        request = AgentRequest(
            task_id="t", capability=SINGLE_CAPABILITY, payload={"question": "q"}
        )
        result = asyncio.run(agent.handle(request, context))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ErrorCode.INVALID_CONTEXT)

    def test_empty_question_is_rejected(self) -> None:
        bundle = build_single_bundle(question="   ")
        result = asyncio.run(run_single(bundle))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ErrorCode.INVALID_REQUEST)

    def test_payload_cannot_inject_permissions(self) -> None:
        bundle = build_single_bundle(question="q")
        bundle.request = AgentRequest(
            task_id="t",
            capability=SINGLE_CAPABILITY,
            payload={"question": "q", "permissions": ["lease.read"]},
        )
        result = asyncio.run(run_single(bundle))
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ErrorCode.INVALID_REQUEST)


class TestDeepSeekClientWiring(unittest.TestCase):
    def test_missing_api_key_raises(self) -> None:
        from app.llm.langchain_client import build_chat_client

        saved = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            with self.assertRaises(MissingApiKeyError):
                build_chat_client(_config())
        finally:
            if saved is not None:
                os.environ["DEEPSEEK_API_KEY"] = saved

    def test_client_construction_does_not_require_network(self) -> None:
        from app.llm.langchain_client import LangChainChatModelClient, build_chat_client

        saved = os.environ.get("DEEPSEEK_API_KEY")
        os.environ["DEEPSEEK_API_KEY"] = "placeholder-not-used"
        try:
            client = build_chat_client(_config())
        finally:
            if saved is None:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            else:
                os.environ["DEEPSEEK_API_KEY"] = saved
        self.assertIsInstance(client, LangChainChatModelClient)
        self.assertEqual(client.provider, "deepseek")
        self.assertEqual(client.model_name, "deepseek-chat")

    def test_openai_tool_schema_shape(self) -> None:
        from app.llm.langchain_client import _to_openai_tool

        payload = _to_openai_tool(
            ToolSpec(name="lease.lookup", description="d", parameters={"type": "object"})
        )
        self.assertEqual(payload["type"], "function")
        self.assertEqual(payload["function"]["name"], "lease.lookup")
        self.assertEqual(payload["function"]["parameters"], {"type": "object"})


class TestAgentConfigToolRounds(unittest.TestCase):
    def test_max_tool_rounds_defaults_and_bounds(self) -> None:
        from pydantic import ValidationError

        from app.config.schema import AgentConfig

        config = load_agent_config(CONFIG_DIR / "single.yaml")
        self.assertEqual(config.max_tool_rounds, 3)

        base = config.model_dump(mode="json")
        for bad in (0, 99):
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    AgentConfig.model_validate({**base, "max_tool_rounds": bad})


if __name__ == "__main__":
    unittest.main()
