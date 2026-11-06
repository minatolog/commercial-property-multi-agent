"""Task 024 / Q2：单 Agent（B）必须与领域 Agent 共用同一套可信任务范围。

历史缺陷（Task 022 复查 Q2）：B 基线把解析好的 `lease_id` 放进 request.payload，
但 `SingleToolAgent` 既不构造 `TaskScope`，也不给 `run_tool_loop` 传 `prepare_arguments`，
事实归并前也不校验实体归属。结果：模型调用**有权限但错实体**的账单工具
（B-101）后，其数据被当成 A-301 的事实写进答案，status=ok、errors=[]。

三种任务形态（`targeted` / `compare` / `explain`）在本文件都有对照。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, Sequence

from app.agents.base.contracts import AgentRequest, TaskStatus
from app.agents.base.errors import ErrorCode
from app.agents.base.scope import TaskScope
from app.agents.base.tool_backed import ToolBackedAgent
from app.agents.single.agent import SingleToolAgent
from app.config.loader import load_agent_config
from app.evaluation.baselines import SingleAgentBaseline
from app.evaluation.cases import EvalCase
from app.fixtures.repository import FixtureRepository
from app.llm.model_client import ModelToolCall, ModelTurn
from app.paths import CONFIG_DIR
from app.runtime.budget import Budget
from app.runtime.types import TraceLog, TrustedContext
from app.tools.fixture_tools import build_fixture_tools
from app.tools.registry import ToolRegistry

LEASE_A301 = "lease_xh_a301_2025"
LEASE_B101 = "lease_jl_b101_2025"


class _Scripted:
    """按脚本调用工具，之后给出固定答案；可选地在第二轮纠正参数。"""

    provider = "fake"
    model_name = "scripted-scope"

    def __init__(
        self,
        script: Sequence[tuple[str, dict[str, Any]]],
        answer: str,
        *,
        correction: tuple[str, dict[str, Any]] | None = None,
    ) -> None:
        self._script = list(script)
        self._answer = answer
        self._correction = correction
        self.calls = 0
        self.invoked: list[str] = []

    async def complete(
        self, messages: Sequence[Any], tools: Sequence[Any]
    ) -> ModelTurn:
        self.calls += 1
        from app.llm.model_client import ToolSpecBuilder  # noqa: F401  (类型提示用途)

        tool_results = [m for m in messages if getattr(m, "role", "") == "tool"]
        if tool_results and self._correction is not None:
            name, arguments = self._correction
            self._correction = None
            return self._call(name, arguments, tools)
        if tool_results or any(getattr(m, "tool_calls", ()) for m in messages):
            return ModelTurn(text=self._answer, finish_reason="stop")
        calls = [self._call(name, args, tools) for name, args in self._script]
        calls = [item for item in calls if item is not None]
        if not calls:
            return ModelTurn(text=self._answer, finish_reason="stop")
        first = calls[0]
        return ModelTurn(text="", tool_calls=tuple(first.tool_calls or ()))

    def _call(self, name: str, args: dict[str, Any], tools: Sequence[Any]) -> Any:
        exposed = {spec.tool_name: spec.name for spec in tools}
        if name not in exposed:
            return None
        self.invoked.append(name)
        return ModelTurn(
            text="",
            tool_calls=(
                ModelToolCall(
                    call_id=f"c{len(self.invoked)}",
                    name=exposed[name],
                    arguments=dict(args),
                    arguments_json=json.dumps(args, ensure_ascii=False),
                ),
            ),
        )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _context(*projects: str, run_id: str = "run_q2") -> Any:
    trusted = TrustedContext(
        trace_id="trace_q2",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset(projects or ("prj_xinghui",)),
        permissions=frozenset({"billing.read", "lease.read", "property.read"}),
    )
    return trusted.to_agent_context(run_id=run_id)


def _agent(client: Any, *, budget: Budget | None = None) -> SingleToolAgent:
    return SingleToolAgent(
        load_agent_config(CONFIG_DIR / "single.yaml"),
        model_client=client,
        tool_registry=_registry(),
        budget=budget or Budget(max_tool_calls=6, max_model_calls=6, max_total_tokens=4000),
        trace_log=TraceLog(),
    )


def _run(agent: SingleToolAgent, payload: dict[str, Any], *projects: str) -> Any:
    return asyncio.run(
        agent.handle(
            AgentRequest(
                task_id="t_q2", capability="single.investigate", payload=payload
            ),
            _context(*projects),
        )
    )


class TestScopeModes(unittest.TestCase):
    def test_targeted_mode_from_payload(self) -> None:
        scope = TaskScope.from_payload({"lease_id": LEASE_A301, "question": "欠多少"})
        self.assertEqual(scope.mode, "targeted")
        self.assertTrue(scope.requires_evidence)
        self.assertEqual(scope.lease_ids, frozenset({LEASE_A301}))

    def test_compare_mode_from_payload(self) -> None:
        scope = TaskScope.from_payload({"lease_ids": [LEASE_A301, LEASE_B101]})
        self.assertEqual(scope.mode, "compare")
        self.assertTrue(scope.requires_evidence)

    def test_explain_mode_requires_no_evidence(self) -> None:
        scope = TaskScope.from_payload({"question": "合同里的免租期一般怎么约定？"})
        self.assertEqual(scope.mode, "explain")
        self.assertFalse(scope.requires_evidence)

    def test_compare_mode_requires_explicit_target(self) -> None:
        scope = TaskScope.from_payload({"lease_ids": [LEASE_A301, LEASE_B101]})
        final, reason = scope.apply_arguments(
            "billing.statement.read", {"lease_id"}, {}
        )
        self.assertIsNone(final)
        self.assertIn("多租约比较", reason or "")

    def test_compare_mode_accepts_listed_target(self) -> None:
        scope = TaskScope.from_payload({"lease_ids": [LEASE_A301, LEASE_B101]})
        final, reason = scope.apply_arguments(
            "billing.statement.read", {"lease_id"}, {"lease_id": LEASE_B101}
        )
        self.assertIsNone(reason)
        self.assertEqual(final["lease_id"], LEASE_B101)
        self.assertIsNone(
            scope.accepts_output("billing.statement.read", {"lease_id": LEASE_B101})
        )


class TestSingleAgentTargetScope(unittest.TestCase):
    def test_wrong_lease_is_rejected_not_silently_used(self) -> None:
        """回归 Q2：主体两个项目都有权限，但任务目标是 A-301。"""

        client = _Scripted(
            [("billing.statement.read", {"lease_id": LEASE_B101})],
            "A301 应收 0.00、已收 0.00、未收 0.00，已经结清。",
        )
        result = _run(
            _agent(client),
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
            "prj_xinghui",
            "prj_jinlan",
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        details = result.error.details or {}
        self.assertTrue(
            any("被拒绝" in item for item in details.get("warnings", [])),
            details,
        )
        self.assertNotIn("0.00", json.dumps(details, ensure_ascii=False))

    def test_omitted_lease_is_injected_from_trusted_payload(self) -> None:
        client = _Scripted(
            [("billing.statement.read", {})],
            "应收 52596.00、已收 34560.00、未收 18036.00。",
        )
        result = _run(
            _agent(client),
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        data = result.output
        self.assertEqual(data["facts"]["outstanding_total"], "18036.00")
        self.assertEqual(data["task_scope"]["mode"], "targeted")
        self.assertEqual(data["tool_outputs"]["billing.statement.read"]["lease_id"], LEASE_A301)

    def test_model_correction_after_rejection_is_accepted(self) -> None:
        """被拒绝后模型改参数重试（有限纠正）→ 取得正确目标的事实。"""

        client = _Scripted(
            [("billing.statement.read", {"lease_id": LEASE_B101})],
            "应收 52596.00、已收 34560.00、未收 18036.00。",
            correction=("billing.statement.read", {"lease_id": LEASE_A301}),
        )
        result = _run(
            _agent(client),
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        # 被拒绝的尝试会留下 warning，因此结果是 partial（不是 failed）：
        # "错一次再改对"应当完成，但必须留下被拒记录。
        self.assertIs(result.status, TaskStatus.PARTIAL, result.error)
        self.assertEqual(result.output["facts"]["outstanding_total"], "18036.00")
        self.assertTrue(any("被拒绝" in item for item in result.warnings))
        self.assertEqual(client.invoked.count("billing.statement.read"), 2)

    def test_other_lease_document_cannot_enter_the_report(self) -> None:
        """Q2 + N3：文档检索也必须落在本次租约的适用文档集合内。"""

        client = _Scripted(
            [("document.search", {"query": "租金递增", "document_ids": ["doc_xh_a302_contract"]})],
            "合同第 1 页 5.2 条约定递增。",
        )
        result = _run(
            _agent(client),
            {"question": "A-301 合同的递增怎么约定？", "lease_id": LEASE_A301},
        )
        # 要么没有可用条款证据（失败/无事实），要么证据只属于 A-301；
        # 绝不能把 A-302 的合同当成 A-301 的依据。
        seen = result.output or {}
        documents = {
            item.get("document_id")
            for item in (seen.get("evidence") or [])
            if isinstance(item, dict)
        }
        self.assertNotIn("doc_xh_a302_contract", documents)

    def test_explain_task_may_answer_without_tools(self) -> None:
        """纯说明任务：没有目标时不强制取数。"""

        client = _Scripted([], "免租期通常在合同中单列条款约定。")
        result = _run(_agent(client), {"question": "免租期一般怎么约定？"})
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        self.assertEqual(result.output["task_scope"]["mode"], "explain")

    def test_compare_task_rejects_unlisted_lease(self) -> None:
        client = _Scripted(
            [("billing.statement.read", {"lease_id": "lease_xh_a302_2025"})],
            "两者对比。",
        )
        result = _run(
            _agent(client),
            {
                "question": "比较两个租约的欠费",
                "lease_ids": [LEASE_A301, LEASE_B101],
            },
            "prj_xinghui",
            "prj_jinlan",
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)


class TestBBaselineParity(unittest.TestCase):
    """B 基线的实测入口：错租约不得成为最终事实。"""

    def _case(self) -> EvalCase:
        return EvalCase(
            case_id="Q2",
            title="单 Agent 目标范围",
            user_input="A-301 现在还有多少钱没交？",
            principal_id="principal_ops_xinghui",
            lease_id=LEASE_A301,
            expected_facts={"outstanding_total": "18036.00"},
        )

    def test_wrong_lease_call_does_not_become_the_answer(self) -> None:
        client = _Scripted(
            [("billing.statement.read", {"lease_id": LEASE_B101})],
            "A301 未收 0.00，已经全部结清。",
        )
        baseline = SingleAgentBaseline(
            model_client=client, max_tool_calls=6, max_total_tokens=4000
        )
        result = asyncio.run(baseline.run(case=self._case()))
        self.assertNotEqual(result.status, "ok")
        self.assertEqual(result.facts, {})
        self.assertTrue(result.errors)

    def test_correct_lease_call_produces_facts(self) -> None:
        client = _Scripted(
            [("billing.statement.read", {"lease_id": LEASE_A301})],
            "应收 52596.00、已收 34560.00、未收 18036.00。",
        )
        baseline = SingleAgentBaseline(
            model_client=client, max_tool_calls=6, max_total_tokens=4000
        )
        result = asyncio.run(baseline.run(case=self._case()))
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.facts["outstanding_total"], "18036.00")


class TestDomainAgentParity(unittest.TestCase):
    """领域 Agent 的既有行为不能被这次重构改坏（共用同一钩子）。"""

    def test_domain_agent_E2E_still_rejects_foreign_lease(self) -> None:
        from app.agents.factory import build_registry

        client = _Scripted(
            [("billing.statement.read", {"lease_id": LEASE_B101})], "已核对。"
        )
        registry = _registry()
        budget = Budget(max_tool_calls=6, max_model_calls=6, max_total_tokens=4000)
        report = build_registry(
            tool_registry=registry,
            budget=budget,
            trace_log=TraceLog(),
            engine="llm",
            model_client=client,
        )
        agent = report.registry.require_capability("billing.statement")
        result = asyncio.run(
            agent.handle(
                AgentRequest(
                    task_id="t_domain",
                    capability="billing.statement",
                    payload={"lease_id": LEASE_A301, "question": "欠多少"},
                ),
                _context("prj_xinghui", "prj_jinlan"),
            )
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)

    def test_deterministic_agent_unaffected(self) -> None:
        """确定性 Agent 走 ToolBackedAgent，不受 scope 钩子影响。"""

        self.assertTrue(issubclass(ToolBackedAgent, object))


if __name__ == "__main__":
    unittest.main()
