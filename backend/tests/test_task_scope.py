"""Task 021 / N2、N3、N5：可信目标、文档范围与筛选条件必须由装配层决定。

三条缺陷同源：确定性 Agent 把目标写死在代码里，换成模型选工具后这条保证消失。

- N2：模型可以调用**有权限但错实体**的工具（A-301 的调查取回 B-101 的账单）；
- N3：模型可以省略 `document_ids`，让检索扩大到整个项目（A-302 合同进 A-301 报告）；
- N5：planner 没把原问题与 `category` 传给子 Agent，模型只能猜。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from app.agents.base.contracts import AgentRequest, TaskStatus
from app.agents.base.errors import ErrorCode
from app.agents.base.scope import TaskScope
from app.agents.factory import build_registry
from app.config.loader import load_agent_config
from app.fixtures.repository import FixtureRepository
from app.llm.model_client import ModelToolCall, ModelTurn
from app.orchestration.investigation import RuleBasedPlanner
from app.paths import CONFIG_DIR
from app.rag.catalog import DocumentMeta, StaticDocumentCatalog
from app.rag.library import build_knowledge_library
from app.rag.pdf_builder import build_pdf
from app.runtime.budget import Budget
from app.runtime.types import TraceLog, TrustedContext
from app.tools.fixture_tools import build_fixture_tools
from app.tools.knowledge_tools import DocumentSearchTool
from app.tools.registry import ToolRegistry

LEASE_A301 = "lease_xh_a301_2025"
LEASE_JL = "lease_jl_b101_2025"


class _ToolThenAnswer:
    """按脚本调用一个工具，然后给出固定文本。"""

    provider = "fake"
    model_name = "one-tool"

    def __init__(self, tool_name: str, arguments: dict[str, Any]) -> None:
        self._name = tool_name
        self._args = arguments
        self.calls = 0

    async def complete(self, messages, tools):  # noqa: ANN001
        self.calls += 1
        if any(message.tool_calls for message in messages):
            return ModelTurn(text="已核对。", finish_reason="stop")
        exposed = {spec.tool_name: spec.name for spec in tools}
        name = exposed.get(self._name)
        if name is None:
            return ModelTurn(text="没有可用工具。", finish_reason="stop")
        return ModelTurn(
            text="",
            tool_calls=(
                ModelToolCall(
                    call_id="c1",
                    name=name,
                    arguments=dict(self._args),
                    arguments_json=json.dumps(self._args, ensure_ascii=False),
                ),
            ),
        )


def _registry() -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(FixtureRepository.load()):
        registry.register(tool)
    return registry


def _context(*projects: str) -> Any:
    trusted = TrustedContext(
        trace_id="trace_scope",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset(projects),
        permissions=frozenset({"billing.read", "lease.read", "property.read"}),
    )
    return trusted.to_agent_context(run_id="run_scope")


def _billing_agent(client: Any, budget: Budget):
    config = load_agent_config(CONFIG_DIR / "billing.yaml")
    report = build_registry(
        tool_registry=_registry(),
        budget=budget,
        trace_log=TraceLog(),
        engine="llm",
        model_client=client,
    )
    return report.registry.require_capability("billing.statement"), config


class TestTaskScope(unittest.TestCase):
    def test_omitted_fields_are_injected_not_widened(self) -> None:
        scope = TaskScope(lease_id=LEASE_A301, filters={"category": "hvac"})
        final, reason = scope.apply_arguments(
            "property.work_orders.read", {"lease_id", "category"}, {"lease_id": ""}
        )
        self.assertIsNone(reason)
        self.assertEqual(final, {"lease_id": LEASE_A301, "category": "hvac"})

    def test_foreign_lease_is_rejected(self) -> None:
        scope = TaskScope(lease_id=LEASE_A301)
        final, reason = scope.apply_arguments(
            "billing.statement.read", {"lease_id"}, {"lease_id": LEASE_JL}
        )
        self.assertIsNone(final)
        self.assertIn("超出本次任务范围", reason or "")

    def test_output_from_other_lease_is_rejected(self) -> None:
        scope = TaskScope(lease_id=LEASE_A301)
        self.assertIsNone(scope.accepts_output("billing.statement.read", {"lease_id": LEASE_A301}))
        self.assertIsNotNone(
            scope.accepts_output("billing.statement.read", {"lease_id": LEASE_JL})
        )

    def test_no_scope_does_not_constrain(self) -> None:
        scope = TaskScope()
        final, reason = scope.apply_arguments(
            "billing.statement.read", {"lease_id"}, {"lease_id": LEASE_JL}
        )
        self.assertIsNone(reason)
        self.assertEqual(final["lease_id"], LEASE_JL)


class TestN2WrongEntityIsBlocked(unittest.TestCase):
    def _run(self, client: Any, *, projects: tuple[str, ...], payload: dict[str, Any]):
        budget = Budget(max_tool_calls=8, max_model_calls=8, max_total_tokens=2000)
        agent, _ = _billing_agent(client, budget)
        request = AgentRequest(task_id="n2", capability="billing.statement", payload=payload)
        return asyncio.run(agent.handle(request, _context(*projects)))

    def test_model_cannot_switch_target_lease(self) -> None:
        """回归 N2：主体两个项目都有权限，但任务目标是 A-301。"""

        client = _ToolThenAnswer("billing.statement.read", {"lease_id": LEASE_JL})
        result = self._run(
            client,
            projects=("prj_xinghui", "prj_jinlan"),
            payload={"lease_id": LEASE_A301, "question": "A-301 欠多少"},
        )
        # 越界调用被拒 → 没拿到任何 A-301 事实 → 按 N4 契约判"证据不足失败"，
        # 既不会拿金鹭数据冒充 A-301，也不会返回一个"成功但空"的结论。
        self.assertIs(result.status, TaskStatus.FAILED, result.output)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        details = result.error.details or {}
        self.assertIn("violations", details)
        self.assertTrue(
            any("被拒绝" in item for item in details.get("warnings", [])),
            f"应记录拒绝原因: {details}",
        )
        self.assertNotIn("18036.00", json.dumps(details, ensure_ascii=False))

    def test_model_omitting_lease_is_injected_from_scope(self) -> None:
        client = _ToolThenAnswer("billing.statement.read", {})
        result = self._run(
            client,
            projects=("prj_xinghui",),
            payload={"lease_id": LEASE_A301, "question": "欠多少"},
        )
        data = result.output or {}
        self.assertEqual(data.get("lease_id"), LEASE_A301)
        self.assertEqual(data.get("facts", {}).get("outstanding_total"), "18036.00")

    def test_correct_target_still_works(self) -> None:
        client = _ToolThenAnswer("billing.statement.read", {"lease_id": LEASE_A301})
        result = self._run(
            client,
            projects=("prj_xinghui",),
            payload={"lease_id": LEASE_A301, "question": "欠多少"},
        )
        self.assertEqual((result.output or {}).get("lease_id"), LEASE_A301)


class TestN3DocumentScope(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name)
        build_pdf(
            base / "a301.pdf",
            (("第五条 租金及调整", "5.2 自第二个租赁年度起，租金每十二（12）个月递增百分之五（5%）。"),),
            title="A301 合同",
        )
        build_pdf(
            base / "a302.pdf",
            (("第五条 租金及调整", "5.2 自第二个租赁年度起，租金每十二（12）个月递增百分之二十（20%）；仅适用于 A302。"),),
            title="A302 合同",
        )
        catalog = StaticDocumentCatalog(
            [
                DocumentMeta(
                    document_id="doc_xh_a301_contract",
                    project_id="prj_xinghui",
                    version=1,
                    lease_id=LEASE_A301,
                    filename="a301.pdf",
                ),
                DocumentMeta(
                    document_id="doc_xh_a302_contract",
                    project_id="prj_xinghui",
                    version=1,
                    lease_id="lease_xh_a302_2025",
                    filename="a302.pdf",
                ),
                DocumentMeta(
                    document_id="doc_xh_property_policy",
                    project_id="prj_xinghui",
                    version=1,
                    lease_id=None,
                    filename="a301.pdf",
                ),
            ]
        )
        self.library = build_knowledge_library(catalog, document_dir=base)
        self.tool = DocumentSearchTool(self.library.service, library=self.library)

    def _ids(self, **kwargs: Any) -> list[str]:
        invocation = asyncio.run(
            self.tool.invoke(
                self.tool.input_model(query="租金递增百分之二十", top_k=5, **kwargs),
                _context("prj_xinghui"),
            )
        )
        return sorted({item["document_id"] for item in invocation.data["results"]})

    def test_lease_scope_wins_over_missing_document_ids(self) -> None:
        """回归 N3：模型省略 document_ids 时，不得扩大到整个项目。"""

        ids = self._ids(lease_id=LEASE_A301)
        self.assertIn("doc_xh_a301_contract", ids)
        self.assertNotIn("doc_xh_a302_contract", ids)

    def test_model_cannot_name_another_lease_document(self) -> None:
        ids = self._ids(
            lease_id=LEASE_A301, document_ids=["doc_xh_a302_contract"]
        )
        self.assertEqual(ids, [], "点名别的租约的合同必须被交集挡掉")

    def test_controlled_call_without_any_scope_is_denied(self) -> None:
        self.assertEqual(self._ids(), [], "受控调用没有可信范围时应默认拒绝")

    def test_cli_interactive_search_still_unscoped(self) -> None:
        loose = DocumentSearchTool(
            self.library.service, library=self.library, require_scope=False
        )
        invocation = asyncio.run(
            loose.invoke(
                loose.input_model(query="租金递增百分之二十", top_k=5),
                _context("prj_xinghui"),
            )
        )
        ids = {item["document_id"] for item in invocation.data["results"]}
        self.assertIn("doc_xh_a302_contract", ids, "人工检索仍允许全库搜索")

    def test_project_policy_is_excluded_when_not_requested(self) -> None:
        invocation = asyncio.run(
            self.tool.invoke(
                self.tool.input_model(
                    query="租金递增",
                    top_k=5,
                    lease_id=LEASE_A301,
                    include_project_documents=False,
                ),
                _context("prj_xinghui"),
            )
        )
        ids = {item["document_id"] for item in invocation.data["results"]}
        self.assertNotIn("doc_xh_property_policy", ids)


class TestN5PlannerPassesQuestionAndFilters(unittest.TestCase):
    def test_every_subtask_receives_the_original_question(self) -> None:
        question = "只查询 A-301 空调维修工单，并核对租金"
        subtasks, _ = RuleBasedPlanner().plan(question, {"lease_id": LEASE_A301})
        self.assertTrue(subtasks)
        for subtask in subtasks:
            self.assertEqual(
                subtask["payload"].get("question"),
                question,
                f"{subtask['subtask_id']} 必须收到原问题",
            )

    def test_property_filter_is_carried_as_hard_condition(self) -> None:
        subtasks, _ = RuleBasedPlanner().plan(
            "只查询 A-301 空调维修工单", {"lease_id": LEASE_A301}
        )
        property_task = next(
            item for item in subtasks if item["capability"] == "property.work_orders"
        )
        self.assertEqual(property_task["payload"].get("category"), "hvac")

    def test_scope_injects_category_into_tool_arguments(self) -> None:
        """模型丢掉 category 时，调用前仍会被注入（不能只写在提示词里）。"""

        scope = TaskScope(lease_id=LEASE_A301, filters={"category": "hvac"})
        final, reason = scope.apply_arguments(
            "property.work_orders.read", {"lease_id", "category"}, {}
        )
        self.assertIsNone(reason)
        self.assertEqual(final.get("category"), "hvac")


if __name__ == "__main__":
    unittest.main()
