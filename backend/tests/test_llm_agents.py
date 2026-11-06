"""Task 018：模型驱动装配测试（LLM 引擎、B/C 真实运行入口、provider 语义）。

验证边界：

- 用 `ScriptedToolModel` 证明**装配**是对的（白名单、预算、Trace、事实提取、错误码）；
- 不证明模型质量，也不假装跑过真实 DeepSeek（无 `DEEPSEEK_API_KEY`）；
- `deepseek` provider 缺密钥时必须**明确失败**，不能静默降级成离线。
"""

from __future__ import annotations

import asyncio
import json
import unittest

from app.agents.base.contracts import AgentContext, AgentRequest, TaskStatus
from app.agents.base.errors import AgentError, ErrorCode, MissingApiKeyError
from app.agents.base.facts import facts_of_executions, facts_from_tool_output
from app.agents.base.llm_agent import LLMToolAgent
from app.agents.factory import build_registry
from app.config.loader import load_agent_config
from app.evaluation.baselines import (
    MultiAgentBaseline,
    SingleAgentBaseline,
    build_baseline,
)
from app.evaluation.cases import load_cases
from app.fixtures.repository import FixtureRepository
from app.investigation_demo import build_investigation_bundle
from app.llm.factory import MODEL_PROVIDERS, build_model_client
from app.llm.scripted import ScriptedToolModel, scripted_client_for_tools
from app.paths import CONFIG_DIR
from app.runtime.budget import Budget
from app.runtime.types import TraceLog, TrustedContext
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry

LEASE = "lease_xh_a301_2025"
QUESTION = (
    "商铺 A-301 投诉租金金额不一致，同时空调多次维修未解决，"
    "请核对合同、账单和工单。"
)


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _context() -> AgentContext:
    trusted = TrustedContext(
        trace_id="trace_llm",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset({"prj_xinghui"}),
        permissions=frozenset({"lease.read", "billing.read", "property.read"}),
    )
    return trusted.to_agent_context(run_id="run_llm")


def _config(name: str):
    return load_agent_config(CONFIG_DIR / f"{name}.yaml")


def _scripted() -> ScriptedToolModel:
    return scripted_client_for_tools(
        [
            ("lease.lookup", {"lease_id": LEASE}),
            ("billing.statement.read", {"lease_id": LEASE}),
            ("property.work_orders.read", {"lease_id": LEASE}),
        ],
        summary="已按工具结果核对。",
    )


class TestFactExtraction(unittest.TestCase):
    """事实只能来自工具输出，键名必须与评分器契约一致。"""

    def test_billing_facts_are_exact_strings(self) -> None:
        facts = facts_from_tool_output(
            "billing.statement.read",
            {
                "invoiced_total": "52596.00",
                "paid_total": "34560.00",
                "outstanding_total": "18036.00",
                "rent_variance_total": "756.00",
            },
        )
        self.assertEqual(facts["invoiced_total"], "52596.00")
        self.assertEqual(facts["outstanding_total"], "18036.00")
        self.assertEqual(facts["rent_variance_total"], "756.00")

    def test_lease_facts_include_missing_documents(self) -> None:
        facts = facts_from_tool_output(
            "lease.lookup",
            {
                "start_date": "2025-01-01",
                "end_date": "2027-12-31",
                "status": "active",
                "unit_code": "A-301",
                "lease_id": LEASE,
                "missing_document_ids": ["doc_xh_a301_annex_b"],
            },
        )
        self.assertEqual(facts["lease_period"], "2025-01-01 至 2027-12-31")
        self.assertEqual(facts["missing_document_ids"], ["doc_xh_a301_annex_b"])

    def test_unknown_tool_yields_no_facts(self) -> None:
        self.assertEqual(facts_from_tool_output("unknown.tool", {"x": 1}), {})


class TestLLMDomainAgent(unittest.TestCase):
    """Lease/Billing/Property 的 LLM 引擎：领域视图与确定性实现保持一致。"""

    def _run(self, name: str, capability: str, payload: dict, client=None):
        agent_config = _config(name)
        registry = _registry()
        budget = Budget(max_tool_calls=8, max_model_calls=8)
        report = build_registry(
            tool_registry=registry,
            budget=budget,
            trace_log=TraceLog(),
            engine="llm",
            model_client=client or _scripted(),
        )
        agent = report.registry.require_capability(capability)
        request = AgentRequest(
            task_id="task_llm", capability=capability, payload=payload
        )
        return agent, asyncio.run(agent.handle(request, _context()))

    def test_billing_agent_reports_tool_facts(self) -> None:
        _, result = self._run(
            "billing", "billing.statement", {"lease_id": LEASE, "question": QUESTION}
        )
        self.assertIs(result.status, TaskStatus.SUCCESS)
        data = result.output
        self.assertEqual(data["engine"], "llm")
        self.assertEqual(data["facts"]["invoiced_total"], "52596.00")
        # 领域视图必须与确定性 Agent 一致：图靠这些字段做冲突检测
        self.assertEqual(data["rent_variance_total"], "756.00")
        self.assertEqual(data["model"]["provider"], "scripted")

    def test_lease_agent_keeps_nested_lease_view(self) -> None:
        _, result = self._run(
            "lease", "lease.query", {"lease_id": LEASE, "question": QUESTION}
        )
        data = result.output
        self.assertEqual(data["lease"]["status"], "active")
        self.assertEqual(data["missing_documents"], ["doc_xh_a301_annex_b"])
        self.assertIn("doc_xh_a301_contract", data["documents"])

    def test_property_agent_counts_open_orders(self) -> None:
        client = scripted_client_for_tools(
            [("property.work_orders.read", {"lease_id": LEASE})], summary="工单已核对。"
        )
        _, result = self._run(
            "property",
            "property.work_orders",
            {"lease_id": LEASE, "question": QUESTION},
            client=client,
        )
        data = result.output
        self.assertEqual(data["work_order_count"], 4)
        self.assertEqual(data["open_work_order_count"], 1)

    def test_model_cannot_call_tool_outside_whitelist(self) -> None:
        """脚本里写了越权工具时，它不会被真正执行（工具集由配置+权限决定）。"""

        client = scripted_client_for_tools(
            [("billing.statement.read", {"lease_id": LEASE})], summary="不该发生。"
        )
        agent, result = self._run(
            "property",
            "property.work_orders",
            {"lease_id": LEASE, "question": QUESTION},
            client=client,
        )
        called = {call["tool"] for call in (result.output or {}).get("tool_calls", [])}
        self.assertNotIn("billing.statement.read", called)

    def test_empty_model_answer_is_a_failure(self) -> None:
        class _EmptyAfterTool(ScriptedToolModel):
            async def complete(self, messages, tools):  # noqa: ANN001
                self.calls.append((tuple(messages), tuple(tools)))
                if any(message.tool_calls for message in messages):
                    from app.llm.model_client import ModelTurn

                    return ModelTurn(text="")
                return await super().complete(messages, tools)

        agent, _ = self._run(
            "billing",
            "billing.statement",
            {"lease_id": LEASE, "question": QUESTION},
            client=_EmptyAfterTool(
                [("billing.statement.read", {"lease_id": LEASE})], summary="x"
            ),
        )
        request = AgentRequest(
            task_id="task_empty",
            capability="billing.statement",
            payload={"lease_id": LEASE, "question": QUESTION},
        )
        result = asyncio.run(agent.handle(request, _context()))
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, ErrorCode.MODEL_ERROR)


class TestInvestigationEngine(unittest.TestCase):
    """`build_investigation_bundle(engine="llm")` 的装配契约。"""

    def test_engine_requires_model_client(self) -> None:
        with self.assertRaises(ValueError):
            build_investigation_bundle(engine="llm")

    def test_unknown_engine_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_investigation_bundle(engine="magic")

    def test_llm_engine_produces_same_report_shape(self) -> None:
        bundle = build_investigation_bundle(
            engine="llm",
            model_client=_scripted(),
            max_tool_calls=12,
            max_model_calls=12,
        )
        self.assertEqual(bundle.engine, "llm")
        self.assertEqual(bundle.model_provider, "scripted")
        result = asyncio.run(
            bundle.investigator.investigate(
                question=QUESTION, lease_id=LEASE, context=bundle.context
            )
        )
        # 与确定性引擎同样的判定口径：差额 → conflicting，附件缺失 → partial
        self.assertEqual(result.verdict, "conflicting")
        self.assertEqual(result.report["completeness"], "partial")
        self.assertTrue(any(c["type"] == "rent_variance" for c in result.conflicts))
        self.assertTrue(
            any("doc_xh_a301_annex_b" in item for item in result.missing)
        )
        self.assertEqual(len(result.results), 3)
        self.assertEqual({item["agent"] for item in result.results}, {"lease", "billing", "property"})
        self.assertTrue(
            all((item["output"] or {}).get("engine") == "llm" for item in result.results)
        )
        traces = bundle.trace_log.snapshot()
        self.assertEqual(
            {trace.tool_name for trace in traces},
            {"lease.lookup", "billing.statement.read", "property.work_orders.read"},
        )
        # 预算真的被记账（不是"看起来调用了"）
        self.assertEqual(bundle.budget.snapshot().used_tool_calls, 3)
        self.assertGreaterEqual(bundle.budget.snapshot().used_model_calls, 2)

    def test_deterministic_engine_has_no_model(self) -> None:
        bundle = build_investigation_bundle()
        self.assertEqual(bundle.engine, "deterministic")
        self.assertEqual(bundle.model_provider, "offline")


class TestConcurrentBudgetAccounting(unittest.TestCase):
    """回归（Task 018）：并发子 Agent 的模型调用必须**逐次**记账，不能被 ID 去重吞掉。"""

    def test_parallel_subtasks_count_every_model_call(self) -> None:
        bundle = build_investigation_bundle(
            engine="llm",
            model_client=_scripted(),
            max_tool_calls=12,
            max_model_calls=32,
        )
        asyncio.run(
            bundle.investigator.investigate(
                question=QUESTION, lease_id=LEASE, context=bundle.context
            )
        )
        snapshot = bundle.budget.snapshot()
        # 3 个子任务各 2 轮模型调用（批量工具调用 + 总结）
        self.assertEqual(snapshot.used_model_calls, 6, snapshot)
        # 脚本只计划了 3 个工具，因此工具调用恰好 3 次
        self.assertEqual(snapshot.used_tool_calls, 3, snapshot)

    def test_model_budget_is_enforced_across_subtasks(self) -> None:
        """预算上限必须真的被并发子任务共同消耗，否则"限额"只是文案。"""

        bundle = build_investigation_bundle(
            engine="llm",
            model_client=_scripted(),
            max_tool_calls=12,
            max_model_calls=3,
        )
        result = asyncio.run(
            bundle.investigator.investigate(
                question=QUESTION, lease_id=LEASE, context=bundle.context
            )
        )
        snapshot = bundle.budget.snapshot()
        self.assertLessEqual(snapshot.used_model_calls, 3)
        # 预算不足必须显式体现为不完整，而不是静默成功
        self.assertEqual(result.report["completeness"], "partial")


class TestBaselineModelPaths(unittest.TestCase):
    """B/C 的真实运行入口：同一题在离线与模型路径下都要能评分。"""

    def _case(self):
        cases = load_cases(split="heldout")
        return next(case for case in cases if case.case_id == "H01")

    def test_baseline_rejects_model_client_for_deterministic(self) -> None:
        with self.assertRaises(ValueError):
            build_baseline("A_deterministic", model_client=_scripted())

    def test_single_agent_baseline_uses_model_when_injected(self) -> None:
        case = self._case()
        baseline = SingleAgentBaseline(model_client=_scripted())
        self.assertEqual(baseline.engine, "llm")
        result = asyncio.run(baseline.run(case=case))
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.facts, "模型路径也必须产出可评分事实")
        self.assertGreater(result.model_calls, 0)
        self.assertEqual(result.answer, "已按工具结果核对。")

    def test_multi_agent_baseline_uses_model_when_injected(self) -> None:
        case = self._case()
        baseline = MultiAgentBaseline(model_client=_scripted())
        result = asyncio.run(baseline.run(case=case))
        self.assertGreater(result.model_calls, 0)
        self.assertTrue(result.facts)
        self.assertNotIn("（本次没有取到可用事实）", result.answer)

    def test_offline_baselines_unchanged(self) -> None:
        case = self._case()
        offline = asyncio.run(SingleAgentBaseline().run(case=case))
        self.assertEqual(offline.model_calls, 0)
        self.assertEqual(SingleAgentBaseline().engine, "deterministic")


class TestModelProviderFactory(unittest.TestCase):
    def test_providers_are_explicit(self) -> None:
        self.assertEqual(list(MODEL_PROVIDERS), ["offline", "scripted", "deepseek"])

    def test_offline_returns_none(self) -> None:
        self.assertIsNone(build_model_client("offline"))

    def test_scripted_returns_scripted_client(self) -> None:
        client = build_model_client("scripted", scripted_calls=[])
        self.assertIsNotNone(client)
        self.assertEqual(client.provider, "scripted")

    def test_deepseek_without_key_fails_loudly(self) -> None:
        import os

        if os.environ.get("DEEPSEEK_API_KEY"):
            self.skipTest("本机已配置 DEEPSEEK_API_KEY，跳过缺密钥用例")
        with self.assertRaises(MissingApiKeyError):
            build_model_client("deepseek")

    def test_unknown_provider_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_model_client("openai")


if __name__ == "__main__":
    unittest.main()
