"""Task 031 返修 R2：报告必须区分"配置模型名"与"服务端实际应答模型"。

背景：DeepSeek 官方公告 `deepseek-chat` 已于 2026-07-24 下线（下线前路由到
`deepseek-v4-flash`），但本项目 2026-11-06 的真实模型报告以该名字调用成功。报告里的
`model_name` 只是配置值，服务端实际由哪个模型应答从未记录。

本文件全部用伪造的响应对象，**不调用任何付费接口**。
"""

from __future__ import annotations

import asyncio
import unittest

from langchain_core.messages import AIMessage

from app.agents.base.contracts import AgentRequest, TaskStatus
from app.agents.base.registry import AgentRegistry
from app.agents.single.agent import SingleToolAgent
from app.config.loader import load_agent_config
from app.evaluation.baselines import BaselineResult, _merge_served_models
from app.evaluation.runner import _models_by_agent_of, _served_cell
from app.fixtures.repository import FixtureRepository
from app.llm.langchain_client import _to_model_turn
from app.llm.model_client import (
    FakeChatModelClient,
    ModelToolCall,
    ModelTurn,
    describe_served_models,
    served_models_of,
)
from app.paths import CONFIG_DIR
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.budget import Budget
from app.runtime.types import TraceLog, TrustedContext
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry

LEASE_A301 = "lease_xh_a301_2025"


class TestServedModelFromResponseMetadata(unittest.TestCase):
    def test_reads_model_name_from_response_metadata(self) -> None:
        response = AIMessage(
            content="应收 52596.00。",
            response_metadata={
                "finish_reason": "stop",
                "model_name": "deepseek-v4-flash",
                "model_provider": "openai",
            },
        )
        turn = _to_model_turn(response)
        self.assertEqual(turn.served_model, "deepseek-v4-flash")
        self.assertEqual(turn.finish_reason, "stop")

    def test_falls_back_to_model_key(self) -> None:
        response = AIMessage(content="ok", response_metadata={"model": "deepseek-v4-pro"})
        self.assertEqual(_to_model_turn(response).served_model, "deepseek-v4-pro")

    def test_missing_metadata_is_none_not_config_name(self) -> None:
        self.assertIsNone(_to_model_turn(AIMessage(content="ok")).served_model)
        self.assertIsNone(
            _to_model_turn(AIMessage(content="ok", response_metadata={"model_name": "  "})).served_model
        )

    def test_describe_marks_mismatch_and_unknown(self) -> None:
        self.assertEqual(
            describe_served_models("deepseek-chat", ["deepseek-v4-flash"]),
            {"served_models": ["deepseek-v4-flash"], "served_model_mismatch": True},
        )
        self.assertEqual(
            describe_served_models("deepseek-chat", ["deepseek-chat"])["served_model_mismatch"],
            False,
        )
        # 没有记录 ≠ 一致
        self.assertIsNone(describe_served_models("deepseek-chat", [])["served_model_mismatch"])

    def test_served_models_of_dedupes_in_order(self) -> None:
        turns = [
            ModelTurn(served_model="b"),
            ModelTurn(served_model=None),
            ModelTurn(served_model="a"),
            ModelTurn(served_model="b"),
        ]
        self.assertEqual(served_models_of(turns), ["b", "a"])


class TestAgentOutputCarriesServedModel(unittest.TestCase):
    def test_single_agent_reports_configured_and_served(self) -> None:
        repository = FixtureRepository.load()
        registry = ToolRegistry()
        for tool in build_fixture_tools(repository):
            registry.register(tool)
        budget = Budget(max_tool_calls=4, max_model_calls=4, max_total_tokens=4000)
        trace_log = TraceLog()
        turns = [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="c1",
                        name="billing.statement.read",
                        arguments={"lease_id": LEASE_A301},
                        arguments_json='{"lease_id": "lease_xh_a301_2025"}',
                    ),
                ),
                served_model="deepseek-v4-flash",
            ),
            ModelTurn(
                text="应收 52596.00、已收 34560.00、未收 18036.00。",
                finish_reason="stop",
                served_model="deepseek-v4-flash",
            ),
        ]
        # 脚本客户端，模拟"配置名 deepseek-chat"的 provider
        client = FakeChatModelClient(turns, provider="deepseek", model_name="deepseek-chat")
        agent = SingleToolAgent(
            load_agent_config(CONFIG_DIR / "single.yaml"),
            model_client=client,
            tool_registry=registry,
            budget=budget,
            trace_log=trace_log,
        )
        agents = AgentRegistry()
        agents.register(agent)
        runtime = AgentRuntime(agents, budget, trace_log=trace_log)
        result = asyncio.run(
            runtime.run(
                AgentRequest(
                    task_id="t_r2",
                    capability="single.investigate",
                    payload={"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
                ),
                TrustedContext(
                    trace_id="trace_r2",
                    principal_id="principal_ops_xinghui",
                    project_ids=frozenset({"prj_xinghui"}),
                    permissions=frozenset({"billing.read", "lease.read", "property.read"}),
                ),
            )
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        model = (result.output or {})["model"]
        self.assertEqual(model["name"], "deepseek-chat")
        self.assertEqual(model["served_models"], ["deepseek-v4-flash"])
        self.assertIs(model["served_model_mismatch"], True)


class TestEvaluationModelsByAgent(unittest.TestCase):
    @staticmethod
    def _result(case_id: str, served: list[str]) -> BaselineResult:
        result = BaselineResult(
            baseline="B_single_agent",
            case_id=case_id,
            status="ok",
            answer="",
            route="single_agent",
            models_by_agent={"single": {"provider": "deepseek", "model_name": "deepseek-chat"}},
        )
        _merge_served_models(result.models_by_agent, "single", served)
        _merge_served_models(result.models_by_agent, "unknown_agent", served)  # 不新增条目
        return result

    def test_merge_across_cases_and_flag_mismatch(self) -> None:
        merged = _models_by_agent_of(
            [
                self._result("H01", ["deepseek-v4-flash"]),
                self._result("H02", []),
                self._result("H03", ["deepseek-v4-flash", "deepseek-v4-pro"]),
            ]
        )
        self.assertEqual(list(merged), ["single"])
        entry = merged["single"]
        self.assertEqual(entry["model_name"], "deepseek-chat", "model_name 保持配置名")
        self.assertEqual(entry["served_models"], ["deepseek-v4-flash", "deepseek-v4-pro"])
        self.assertIs(entry["served_model_mismatch"], True)
        self.assertIn("与配置名不一致", _served_cell(entry))

    def test_unrecorded_is_unknown_not_consistent(self) -> None:
        merged = _models_by_agent_of([self._result("H01", [])])
        self.assertEqual(merged["single"]["served_models"], [])
        self.assertIsNone(merged["single"]["served_model_mismatch"])
        self.assertEqual(_served_cell(merged["single"]), "未记录")

    def test_consistent_names(self) -> None:
        merged = _models_by_agent_of([self._result("H01", ["deepseek-chat"])])
        self.assertIs(merged["single"]["served_model_mismatch"], False)
        self.assertEqual(_served_cell(merged["single"]), "deepseek-chat")


if __name__ == "__main__":
    unittest.main()
