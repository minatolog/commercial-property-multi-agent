"""Task 031 / Z2：失败的工具调用不能算作取证。

原始反例（`docs/reviews/2026-11-07_q1_q3_acceptance_review.md` §3 Z2）：

    有明确目标 A-301（mode=targeted、requires_evidence=true）时，模型调用
    billing.statement.read，参数除合法 lease_id 外含未知字段 unexpected；
    ToolExecutor 正确返回 error（attempts=0）；模型随后说"已经核对，没有问题"。
    旧实现：status=success、error=null、facts={}、evidence=0，而 tool_calls 里却有 error。

根因：`accepted` 只看 `scope.accepts_output`，失败 `ToolExecution` 的 data 是 None/{}，
实体校验发现不了；最低取证判断又只看 `not accepted`。

本文件守住的边界：

1. `accepted` 只允许"执行成功（execution.ok）且输出属于本次目标"的调用；
   失败/被拒绝/超时/预算耗尽/非法参数只进 `failed_tool_calls` 审计，
   不进 facts、不进 evidence、不进最终证据集；
2. 有目标的请求零事实必须失败（`insufficient_evidence`），纯说明任务不受此限；
3. **合法的零结果**（0 条工单、条款检索无命中）必须保留为成功事实；
4. SingleToolAgent（B 基线）与 LLMToolAgent（领域 LLM 引擎）两条路径口径一致。
"""

from __future__ import annotations

import asyncio
import json
import unittest
from typing import Any, Sequence

from app.agents.base.contracts import AgentRequest, TaskStatus
from app.agents.base.errors import ErrorCode
from app.agents.base.registry import AgentRegistry
from app.agents.factory import build_registry
from app.agents.single.agent import SingleToolAgent
from app.config.loader import load_agent_config
from app.fixtures.repository import FixtureRepository
from app.llm.model_client import FakeChatModelClient, ModelToolCall, ModelTurn
from app.paths import CONFIG_DIR
from app.rag.library import build_knowledge_library, fixture_catalog
from app.runtime.agent_runtime import AgentRuntime
from app.runtime.budget import Budget
from app.runtime.types import RuntimeResult, TraceLog, TrustedContext
from app.tools.fixture_tools import (
    BillingStatementInput,
    BillingStatementTool,
    build_fixture_tools,
)
from app.tools.knowledge_tools import DocumentSearchTool
from app.tools.registry import ToolRegistry

LEASE_A301 = "lease_xh_a301_2025"
LEASE_A302 = "lease_xh_a302_2025"
LEASE_B101 = "lease_jl_b101_2025"

_REPOSITORY = FixtureRepository.load()
_KNOWLEDGE: dict[str, Any] = {}


# --------------------------------------------------------------------------- #
# 工具替身与装配辅助
# --------------------------------------------------------------------------- #


class _SlowBillingStatementTool(BillingStatementTool):
    """超时反例：声明 0.01s 超时，实际睡 0.2s。"""

    timeout_seconds = 0.01
    max_attempts = 1

    async def invoke(self, payload: BillingStatementInput, context: Any):  # noqa: ANN001
        await asyncio.sleep(0.2)
        return await super().invoke(payload, context)


class _ForeignEntityBillingTool(BillingStatementTool):
    """范围反例：执行成功，但返回的是同项目另一个租约（A-302）的数据。

    用于证明"成功执行 + 输出越界"的调用也不能成为本次目标的证据
    （旧实现会把它的 evidence 漏进最终证据集）。
    """

    async def invoke(self, payload: BillingStatementInput, context: Any):  # noqa: ANN001
        return await super().invoke(BillingStatementInput(lease_id=LEASE_A302), context)


def _knowledge_library() -> Any:
    """索引 fixture 对应的真实 PDF（只建一次，避免每个用例重复解析）。"""

    if "library" not in _KNOWLEDGE:
        _KNOWLEDGE["library"] = build_knowledge_library(
            fixture_catalog(_REPOSITORY), as_of_date=_REPOSITORY.as_of_date
        )
    return _KNOWLEDGE["library"]


def _registry(*, custom: Sequence[Any] = (), with_documents: bool = False) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in build_fixture_tools(_REPOSITORY):
        registry.register(tool)
    if with_documents:
        library = _knowledge_library()
        registry.register(DocumentSearchTool(library.service, library=library))
    for tool in custom:
        registry.register(tool, replace=True)
    return registry


def _trusted(*projects: str) -> TrustedContext:
    return TrustedContext(
        trace_id="trace_z2",
        principal_id="principal_ops_xinghui",
        project_ids=frozenset(projects or ("prj_xinghui",)),
        permissions=frozenset({"billing.read", "lease.read", "property.read"}),
    )


def _tool_turn(tool: str, arguments: dict[str, Any], call_id: str = "c1") -> ModelTurn:
    return ModelTurn(
        text="",
        tool_calls=(
            ModelToolCall(
                call_id=call_id,
                name=tool,
                arguments=dict(arguments),
                arguments_json=json.dumps(arguments, ensure_ascii=False),
            ),
        ),
    )


def _invalid_call(call_id: str = "c_bad") -> ModelTurn:
    """schema 错误：billing.statement.read 不接受未知字段 unexpected。"""

    return _tool_turn("billing.statement.read", {"unexpected": "x"}, call_id)


def _answer(text: str = "已经核对，没有问题。") -> ModelTurn:
    return ModelTurn(text=text, finish_reason="stop")


def _single_config(*, allowed_tools: Sequence[str] | None = None) -> Any:
    config = load_agent_config(CONFIG_DIR / "single.yaml")
    if allowed_tools is not None:
        config = config.model_copy(update={"allowed_tools": tuple(allowed_tools)})
    return config


def _run_single(
    turns: Sequence[ModelTurn],
    payload: dict[str, Any],
    *,
    projects: Sequence[str] = ("prj_xinghui",),
    budget: Budget | None = None,
    custom: Sequence[Any] = (),
    with_documents: bool = False,
    allowed_tools: Sequence[str] | None = None,
) -> RuntimeResult:
    """走与 Runtime 一致的入口：SingleToolAgent → AgentRegistry → AgentRuntime。"""

    budget = budget or Budget(max_tool_calls=6, max_model_calls=6, max_total_tokens=4000)
    trace_log = TraceLog()
    agent = SingleToolAgent(
        _single_config(allowed_tools=allowed_tools),
        model_client=FakeChatModelClient(list(turns)),
        tool_registry=_registry(custom=custom, with_documents=with_documents),
        budget=budget,
        trace_log=trace_log,
    )
    agents = AgentRegistry()
    agents.register(agent)
    runtime = AgentRuntime(agents, budget, trace_log=trace_log)
    request = AgentRequest(
        task_id="t_z2", capability="single.investigate", payload=dict(payload)
    )
    return asyncio.run(runtime.run(request, _trusted(*projects)))


def _run_llm(
    capability: str,
    turns: Sequence[ModelTurn],
    payload: dict[str, Any],
    *,
    projects: Sequence[str] = ("prj_xinghui",),
    budget: Budget | None = None,
    custom: Sequence[Any] = (),
    with_documents: bool = False,
) -> RuntimeResult:
    budget = budget or Budget(max_tool_calls=8, max_model_calls=8, max_total_tokens=4000)
    trace_log = TraceLog()
    report = build_registry(
        tool_registry=_registry(custom=custom, with_documents=with_documents),
        budget=budget,
        trace_log=trace_log,
        engine="llm",
        model_client=FakeChatModelClient(list(turns)),
    )
    runtime = AgentRuntime(report.registry, budget, trace_log=trace_log)
    request = AgentRequest(task_id="t_z2", capability=capability, payload=dict(payload))
    return asyncio.run(runtime.run(request, _trusted(*projects)))


def _details(result: RuntimeResult) -> dict[str, Any]:
    return dict(result.error.details or {}) if result.error is not None else {}


def _failed_audit(result: RuntimeResult) -> list[dict[str, Any]]:
    """失败时审计在 error.details，成功时在 output（两条路径都要能取到）。"""

    if result.output is not None:
        return list(result.output.get("failed_tool_calls") or ())
    return list(_details(result).get("failed_tool_calls") or ())


def _audit_codes(result: RuntimeResult) -> list[str | None]:
    return [item.get("error_code") for item in _failed_audit(result)]


def _evidence_ids(result: RuntimeResult) -> set[str]:
    return {
        str(item.get("evidence_id"))
        for item in (result.output or {}).get("evidence") or ()
        if item.get("evidence_id")
    }


# --------------------------------------------------------------------------- #
# Z2 原始反例：失败工具调用不得算作取证（SingleToolAgent 路径）
# --------------------------------------------------------------------------- #


class TestZ2SingleAgentFailedCallsAreNotEvidence(unittest.TestCase):
    def test_original_counterexample_schema_error_is_failure(self) -> None:
        """原始反例逐条：schema 错误 + "已经核对，没有问题" 不能成功。"""

        result = _run_single(
            [_invalid_call(), _answer("已经核对，没有问题。")],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertIsNotNone(result.error)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(result.output)
        self.assertEqual(result.evidence, ())
        audit = _failed_audit(result)
        self.assertEqual(len(audit), 1, audit)
        self.assertEqual(audit[0]["tool"], "billing.statement.read")
        self.assertEqual(audit[0]["status"], "error")
        self.assertEqual(audit[0]["error_code"], ErrorCode.INVALID_TOOL_ARGUMENTS.value)
        self.assertIn("targeted", _details(result)["task_scope"]["mode"])

    def test_timeout_call_is_not_evidence(self) -> None:
        result = _run_single(
            [_tool_turn("billing.statement.read", {}, "c1"), _answer()],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
            custom=(_SlowBillingStatementTool(_REPOSITORY),),
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.evidence, ())
        audit = _failed_audit(result)
        self.assertEqual([item["status"] for item in audit], ["timeout"], audit)
        self.assertEqual(audit[0]["error_code"], ErrorCode.TOOL_TIMEOUT.value)

    def test_budget_exhausted_tool_call_is_not_evidence(self) -> None:
        """工具预算为 0：调用在预算闸被拒，仍不能算取证。"""

        result = _run_single(
            [_tool_turn("billing.statement.read", {}, "c1"), _answer()],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
            # 模型调用预算必须给足，否则先停在“模型预算不足”，测不到工具预算闸
            budget=Budget(max_tool_calls=0, max_model_calls=6, max_total_tokens=None),
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        audit = _failed_audit(result)
        self.assertEqual([item["status"] for item in audit], ["budget_exhausted"], audit)
        self.assertEqual(audit[0]["error_code"], ErrorCode.BUDGET_EXHAUSTED.value)

    def test_scope_denied_call_is_not_evidence(self) -> None:
        """A-301 任务调用 B-101 租约：调用前被可信范围拒绝 → 失败 + 审计。"""

        result = _run_single(
            [_tool_turn("billing.statement.read", {"lease_id": LEASE_B101}, "c1"), _answer()],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
            projects=("prj_xinghui", "prj_jinlan"),
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.evidence, ())
        audit = _failed_audit(result)
        self.assertEqual(len(audit), 1, audit)
        self.assertEqual(audit[0]["tool"], "billing.statement.read")
        self.assertEqual(audit[0]["status"], "rejected_arguments")
        self.assertEqual(audit[0]["error_code"], ErrorCode.INVALID_TOOL_ARGUMENTS.value)
        self.assertNotIn("18036.00", json.dumps(_details(result), ensure_ascii=False))

    def test_parse_error_call_is_audited_not_evidence(self) -> None:
        """模型参数不是合法 JSON：从未执行，但必须留在审计里。"""

        bad = ModelToolCall(
            call_id="c_bad_json",
            name="billing.statement.read",
            arguments_json="{not json",
            parse_error="参数不是合法 JSON",
        )
        result = _run_single(
            [ModelTurn(text="", tool_calls=(bad,)), _answer()],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        audit = _failed_audit(result)
        self.assertEqual(len(audit), 1, audit)
        self.assertEqual(audit[0]["tool"], "billing.statement.read")
        self.assertEqual(audit[0]["status"], "rejected_arguments")

    def test_all_calls_failing_then_confident_text_is_failure(self) -> None:
        result = _run_single(
            [
                _invalid_call("c1"),
                _tool_turn("billing.statement.read", {"unexpected2": "y"}, "c2"),
                _answer("账单没有问题，已经全部结清。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertEqual(len(_failed_audit(result)), 2)

    def test_failure_then_legal_correction_still_succeeds(self) -> None:
        """失败一次后模型自行纠正：应当成功，且失败仍留在审计里。"""

        result = _run_single(
            [
                _invalid_call("c1"),
                _tool_turn("billing.statement.read", {"lease_id": LEASE_A301}, "c2"),
                _answer("应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIn(result.status, {TaskStatus.SUCCESS, TaskStatus.PARTIAL}, result.error)
        data = result.output or {}
        self.assertEqual(data["facts"]["outstanding_total"], "18036.00")
        # tool_calls 保留全部调用（含失败），failed_tool_calls 给出明细
        statuses = [item["status"] for item in data["tool_calls"]]
        self.assertEqual(statuses, ["error", "ok"])
        audit = _failed_audit(result)
        self.assertEqual(len(audit), 1, audit)
        self.assertNotIn(
            audit[0]["call_id"],
            {item.tool_call_id for item in result.evidence},
            "失败调用的 call_id 不能出现在最终证据来源里",
        )

    def test_failed_call_does_not_enter_facts_when_another_call_succeeds(self) -> None:
        """问两个领域、账单调用失败、合同调用成功：只能是 PARTIAL（R1）。

        Task 031 原用例接受 SUCCESS/PARTIAL，放过了"用户问的欠款没有取到却判成功"。
        返修后：失败工具不得贡献事实，且 warnings 必须写明缺了 billing 领域。
        """

        result = _run_single(
            [
                _tool_turn("billing.statement.read", {"unexpected": "x"}, "c1"),
                _tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c2"),
                _answer("租期已核对。"),
            ],
            {"question": "A-301 租期和欠款？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.PARTIAL, result.error)
        data = result.output or {}
        self.assertIn("lease_period", data["facts"])
        self.assertNotIn("outstanding_total", data["facts"])
        self.assertNotIn("billing.statement.read", data["tool_outputs"])
        self.assertEqual(len(_failed_audit(result)), 1)
        self.assertEqual(
            data["domain_coverage"],
            {"asked": ["lease", "billing"], "covered": ["lease"], "missing": ["billing"]},
        )
        missing_warnings = [item for item in result.warnings if "部分取证" in item]
        self.assertEqual(len(missing_warnings), 1, result.warnings)
        self.assertIn("billing", missing_warnings[0])
        self.assertNotIn("lease（", missing_warnings[0])

    def test_two_domains_both_succeed_is_success(self) -> None:
        """对照（R1）：两个领域都取到事实、没有失败调用 → SUCCESS，不产生缺领域告警。"""

        result = _run_single(
            [
                _tool_turn("billing.statement.read", {"lease_id": LEASE_A301}, "c1"),
                _tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c2"),
                _answer("租期已核对；应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 租期和欠款？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, (result.error, result.warnings))
        data = result.output or {}
        self.assertIn("lease_period", data["facts"])
        self.assertEqual(data["facts"]["outstanding_total"], "18036.00")
        self.assertEqual(data["domain_coverage"]["missing"], [])
        self.assertEqual(_failed_audit(result), [])

    def test_two_domains_failure_then_correction_is_success(self) -> None:
        """对照（R1）：账单先失败、随后纠正成功 → 两个领域都有事实 → SUCCESS（失败仍在审计）。"""

        result = _run_single(
            [
                _tool_turn("billing.statement.read", {"unexpected": "x"}, "c1"),
                # 纠正与合同查询放在同一回合（single.yaml 的 max_tool_rounds=3）
                ModelTurn(
                    text="",
                    tool_calls=(
                        *_tool_turn(
                            "billing.statement.read", {"lease_id": LEASE_A301}, "c2"
                        ).tool_calls,
                        *_tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c3").tool_calls,
                    ),
                ),
                _answer("租期已核对；应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 租期和欠款？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, (result.error, result.warnings))
        self.assertEqual((result.output or {})["domain_coverage"]["missing"], [])
        self.assertEqual(len(_failed_audit(result)), 1)

    def test_only_asked_domain_failed_unrelated_tool_succeeded_is_failure(self) -> None:
        """只问欠款、账单调用失败、模型另查了合同（成功）→ FAILED / insufficient_evidence。

        为什么不是 PARTIAL：PARTIAL 表示"回答了问题的一部分"。这里问题只涉及 billing，
        合同事实回答不了它的任何部分，本质与"零事实"相同，只是被无关事实掩盖了；
        判 PARTIAL 会让调用方把租期当成对"还欠多少"的部分回答展示出来。
        """

        result = _run_single(
            [
                _tool_turn("billing.statement.read", {"unexpected": "x"}, "c1"),
                _tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c2"),
                _answer("已经核对，没有问题。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertIsNone(result.output)
        self.assertEqual(result.evidence, ())
        details = _details(result)
        self.assertEqual(details["domain_coverage"]["asked"], ["billing"])
        self.assertEqual(details["domain_coverage"]["missing"], ["billing"])
        self.assertEqual(len(details["failed_tool_calls"]), 1)

    def test_unrelated_extra_tool_without_failures_is_unchanged(self) -> None:
        """没有失败调用时 R1 不介入：行为与 Task 031 一致（不因"多查了一个工具"降级）。"""

        result = _run_single(
            [
                _tool_turn("billing.statement.read", {"lease_id": LEASE_A301}, "c1"),
                _tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c2"),
                _answer("应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, (result.error, result.warnings))
        self.assertEqual(
            (result.output or {})["domain_coverage"],
            {"asked": ["billing"], "covered": ["lease", "billing"], "missing": []},
        )

    def test_scope_rejected_success_output_does_not_enter_evidence(self) -> None:
        """执行成功但返回别的实体：输出被拒，其证据不得进入最终证据集。"""

        result = _run_single(
            [
                _tool_turn("billing.statement.read", {}, "c1"),
                _tool_turn("billing.arrears.calculate", {"lease_id": LEASE_A301}, "c2"),
                _answer("应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
            custom=(_ForeignEntityBillingTool(_REPOSITORY),),
        )
        self.assertIn(result.status, {TaskStatus.SUCCESS, TaskStatus.PARTIAL}, result.error)
        data = result.output or {}
        self.assertTrue(data["rejected_outputs"], "越界输出必须留下拒绝原因")
        self.assertNotIn("lease_xh_a302_2025", _evidence_ids(result))
        self.assertEqual(
            {item.source_tool for item in result.evidence},
            {"billing.arrears.calculate"},
            "只有 accepted 执行的证据能进入最终证据集（含 RuntimeResult.evidence）",
        )

    def test_explain_task_may_succeed_without_evidence(self) -> None:
        """纯说明任务不受“零事实必须失败”限制（回归保护）。"""

        result = _run_single(
            [_answer("免租期通常在合同中单列条款约定。")],
            {"question": "免租期一般怎么约定？"},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        self.assertEqual((result.output or {})["task_scope"]["mode"], "explain")


class TestZ2LegalZeroResults(unittest.TestCase):
    """合法零结果必须保留为成功事实，不能和失败混为一谈。"""

    def test_zero_work_orders_is_a_success(self) -> None:
        result = _run_single(
            [_tool_turn("property.work_orders.read", {}, "c1"), _answer("A-302 没有未关闭工单。")],
            {"question": "A-302 有哪些工单？", "lease_id": LEASE_A302},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        data = result.output or {}
        self.assertEqual(data["facts"]["work_order_count"], "0")
        self.assertEqual(data["facts"]["open_count"], "0")
        self.assertEqual(data["tool_calls"][0]["status"], "ok")
        self.assertEqual(_failed_audit(result), [])

    def test_zero_document_hits_is_a_success(self) -> None:
        """条款检索无命中：facts 为“未检索到匹配条款”，不是零事实。"""

        base_allowed = _single_config().allowed_tools
        result = _run_single(
            [
                _tool_turn("document.search", {"query": "qqqqzzzz", "top_k": 3}, "c1"),
                _answer("未检索到相关条款。"),
            ],
            {"question": "A-301 合同里量子纠缠条款怎么约定的？", "lease_id": LEASE_A301},
            with_documents=True,
            allowed_tools=(*base_allowed, "document.search"),
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        data = result.output or {}
        self.assertEqual(data["facts"]["clause_ref"], "未检索到匹配条款")
        self.assertEqual(data["tool_calls"][0]["status"], "ok")
        self.assertEqual(_failed_audit(result), [])


# --------------------------------------------------------------------------- #
# LLMToolAgent 路径：同一口径（失败只审计、越界证据过滤、零结果成功）
# --------------------------------------------------------------------------- #


class TestZ2LLMPath(unittest.TestCase):
    def test_llm_failed_call_is_audited_not_evidence(self) -> None:
        """LLM 领域 Agent 原有 check_capability_output 契约保留，同时补上失败审计。"""

        result = _run_llm(
            "billing.statement",
            [_invalid_call("c1"), _answer("已经核对，没有问题。")],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIs(result.status, TaskStatus.FAILED)
        self.assertEqual(result.error.code, ErrorCode.INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.evidence, ())
        details = _details(result)
        self.assertTrue(details.get("violations"), "原有能力契约不能被放松")
        audit = details.get("failed_tool_calls") or []
        self.assertEqual(len(audit), 1, audit)
        self.assertEqual(audit[0]["error_code"], ErrorCode.INVALID_TOOL_ARGUMENTS.value)

    def test_llm_domain_agent_judges_only_its_capability(self) -> None:
        """R1 对 LLM 领域 Agent 不适用：它只负责一个 capability，按能力契约判定。

        问题是"租期和欠款"，但 lease.query 子任务只对合同负责；欠款由 billing 子任务
        负责，该子任务失败时由 Coordinator 汇总为 PARTIAL（coordinator.py 的状态表）。
        如果在这里按问题领域判缺失，lease 子任务会因 billing 的事被错误降级。
        """

        result = _run_llm(
            "lease.query",
            [
                _tool_turn("billing.statement.read", {"unexpected": "x"}, "c1"),
                _tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c2"),
                _answer("租期已核对。"),
            ],
            {"question": "A-301 租期和欠款？", "lease_id": LEASE_A301},
        )
        self.assertIn(result.status, {TaskStatus.SUCCESS, TaskStatus.PARTIAL}, result.error)
        data = result.output or {}
        self.assertIn("lease_period", data["facts"])
        self.assertNotIn("outstanding_total", data["facts"])
        self.assertEqual(len(_failed_audit(result)), 1)
        self.assertFalse([item for item in result.warnings if "部分取证" in item])

    def test_llm_failure_then_legal_correction_succeeds_with_audit(self) -> None:
        result = _run_llm(
            "billing.statement",
            [
                _invalid_call("c1"),
                _tool_turn("billing.statement.read", {"lease_id": LEASE_A301}, "c2"),
                _answer("应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
        )
        self.assertIn(result.status, {TaskStatus.SUCCESS, TaskStatus.PARTIAL}, result.error)
        data = result.output or {}
        self.assertEqual(data["facts"]["outstanding_total"], "18036.00")
        self.assertEqual([item["status"] for item in data["tool_calls"]], ["error", "ok"])
        audit = _failed_audit(result)
        self.assertEqual(len(audit), 1, audit)
        self.assertNotIn(
            audit[0]["call_id"],
            {item.tool_call_id for item in result.evidence},
        )

    def test_llm_scope_rejected_success_evidence_is_filtered(self) -> None:
        """成功执行但输出越界：其 evidence 不能漏进 output / RuntimeResult。"""

        result = _run_llm(
            "billing.statement",
            [
                _tool_turn("billing.statement.read", {}, "c1"),
                _tool_turn("billing.arrears.calculate", {"lease_id": LEASE_A301}, "c2"),
                _answer("应收 52596.00、已收 34560.00、未收 18036.00。"),
            ],
            {"question": "A-301 还欠多少？", "lease_id": LEASE_A301},
            custom=(_ForeignEntityBillingTool(_REPOSITORY),),
        )
        self.assertIn(result.status, {TaskStatus.SUCCESS, TaskStatus.PARTIAL}, result.error)
        data = result.output or {}
        self.assertTrue(data["rejected_outputs"], "越界输出必须留下拒绝原因")
        self.assertNotIn("lease_xh_a302_2025", _evidence_ids(result))
        self.assertEqual(
            {item.source_tool for item in result.evidence},
            {"billing.arrears.calculate"},
        )

    def test_llm_zero_work_orders_is_a_success(self) -> None:
        result = _run_llm(
            "property.work_orders",
            [_tool_turn("property.work_orders.read", {}, "c1"), _answer("没有未关闭工单。")],
            {"question": "A-302 有哪些工单？", "lease_id": LEASE_A302},
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        data = result.output or {}
        self.assertEqual(data["work_order_count"], 0)
        self.assertEqual(data["facts"]["work_order_count"], "0")
        self.assertEqual(_failed_audit(result), [])

    def test_llm_zero_document_hits_is_a_success(self) -> None:
        """租约视图取自 lease.lookup；条款零命中只影响条款，不否定整体成功。"""

        result = _run_llm(
            "lease.query",
            [
                _tool_turn("lease.lookup", {"lease_id": LEASE_A301}, "c1"),
                _tool_turn("document.search", {"query": "qqqqzzzz", "top_k": 3}, "c2"),
                _answer("租约有效，未检索到相关条款。"),
            ],
            {"question": "A-301 合同里的量子纠缠条款？", "lease_id": LEASE_A301},
            with_documents=True,
        )
        self.assertIs(result.status, TaskStatus.SUCCESS, result.error)
        data = result.output or {}
        self.assertEqual(data["facts"]["clause_ref"], "未检索到匹配条款")
        self.assertEqual(data["clauses"], [])
        self.assertEqual(_failed_audit(result), [])


class TestR1DomainCoverageHelpers(unittest.TestCase):
    """R1 的领域口径全部复用既有定义：工具命名空间 / required_permissions / 词表。"""

    def test_tool_domain_by_namespace_and_permissions(self) -> None:
        from app.agents.base.evidence import tool_domain

        self.assertEqual(tool_domain("lease.lookup"), "lease")
        self.assertEqual(tool_domain("billing.arrears.calculate"), "billing")
        self.assertEqual(tool_domain("property.work_orders.read"), "property")
        # 命名空间不是领域 → 按工具声明的权限归属（DocumentSearchTool 需要 lease.read）
        self.assertEqual(
            tool_domain("document.search", DocumentSearchTool.required_permissions), "lease"
        )
        self.assertIsNone(tool_domain("document.search"))
        # 权限跨多个领域时不猜
        self.assertIsNone(tool_domain("x.y", frozenset({"lease.read", "billing.read"})))

    def test_missing_domain_outcome_requires_failed_calls(self) -> None:
        from app.agents.base.evidence import domain_coverage, missing_domain_outcome

        coverage = domain_coverage(
            "A-301 租期和欠款？", {"lease.lookup": {"lease_period": "2025-01-01 至 2027-12-31"}}
        )
        self.assertEqual(coverage["missing"], ["billing"])
        self.assertEqual(missing_domain_outcome(coverage, []), (None, None))
        reason, warning = missing_domain_outcome(coverage, [{"tool": "billing.statement.read"}])
        self.assertIsNone(reason)
        self.assertIn("billing", warning or "")

    def test_legal_zero_result_counts_as_covered(self) -> None:
        from app.agents.base.evidence import domain_coverage

        coverage = domain_coverage(
            "A-302 有哪些工单？",
            {"property.work_orders.read": {"work_order_count": "0", "open_count": "0"}},
        )
        self.assertEqual(coverage["missing"], [])


if __name__ == "__main__":
    unittest.main()
