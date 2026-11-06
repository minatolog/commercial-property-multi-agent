"""LangGraph 调查工作流（Task 009）。

图结构（真实条件分支 + 并发扇出 + 限次补查）：

```text
START → plan ─┬─(单能力/确定性)→ deterministic_answer → report → END
              └─(多能力)→ dispatch ══Send══> run_subtask(并发 N 个) → verify
                                                          verify ─┬─ supported → report → END
                                                                  ├─ revise（≤1 次）→ dispatch
                                                                  └─ insufficient → report → END
```

设计约束：

1. **Coordinator 不 import 任何具体 Agent**：按 capability 从 Registry 解析。
2. **State 只放跨节点信息**：子任务结果按 `subtask_id` 归并，重放/补查不会重复计数。
3. **合流必须等齐**：`verify` 依据计划中的预期子任务集合判定缺口，缺一即记 `MISSING_SUBTASK_RESULT`。
4. **补查有硬上限**：`max_revisions = 1`，超过直接转报告并要求人工处理。
"""

from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..agents.base.contracts import AgentContext, AgentRequest, TaskStatus, utcnow
from ..agents.base.errors import (
    AgentDisabledError,
    AgentError,
    CapabilityUnavailableError,
    ErrorCode,
)
from ..agents.base.registry import AgentRegistry
from ..fixtures.repository import FixtureRepository

__all__ = [
    "DEFAULT_CAPABILITIES",
    "InvestigationResult",
    "InvestigationState",
    "Investigator",
    "Planner",
    "RuleBasedPlanner",
    "build_investigation_graph",
    "verify_results",
]


DEFAULT_CAPABILITIES: tuple[str, ...] = (
    "lease.query",
    "billing.statement",
    "property.work_orders",
)


class InvestigationState(TypedDict, total=False):
    question: str
    lease_id: str
    unit_id: str
    #: 可信执行上下文（权限/项目范围/run_id）。必须声明为 channel，
    #: 否则 `Send` 传递的 payload 会被状态 schema 过滤掉。
    context: AgentContext
    route: str
    plan: list[dict[str, Any]]
    expected_subtasks: list[str]
    results: Annotated[list[dict[str, Any]], operator.add]
    failures: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]
    conflicts: Annotated[list[dict[str, Any]], operator.add]
    missing: Annotated[list[str], operator.add]
    revision: int
    verdict: str
    report: dict[str, Any]


class Planner:
    """把用户问题转成受控子任务计划。"""

    def plan(self, question: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        raise NotImplementedError


class RuleBasedPlanner(Planner):
    """确定性规划器（P0 默认）。

    用显式关键词规则决定能力集合，理由：

    - 无模型凭据时也能跑通整条图，且结果可复现；
    - "简单问题不要拆多 Agent"这条纪律必须可被程序断言，规则比模型更可靠。

    复杂度判定采用"至少命中两类领域"的保守策略。
    """

    _LEASE_HINTS = ("合同", "租约", "条款", "递增", "免租", "押金", "续租", "租期")
    _BILLING_HINTS = ("账单", "租金", "费用", "欠费", "付款", "核销", "多收", "少收", "金额", "发票")
    _PROPERTY_HINTS = ("空调", "维修", "工单", "报修", "故障", "投诉", "漏水", "电梯")

    def plan(self, question: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
        text = question
        domains = {
            "lease": any(hint in text for hint in self._LEASE_HINTS),
            "billing": any(hint in text for hint in self._BILLING_HINTS),
            "property": any(hint in text for hint in self._PROPERTY_HINTS),
        }
        selected = [name for name, hit in domains.items() if hit]
        if not selected:
            selected = ["billing"]
        # 单纯问"欠多少"这类同质问题：只保留一个领域，避免无意义扇出
        if len(selected) > 1 and _is_pure_arrears_question(text):
            selected = ["billing"]

        lease_id = str(payload.get("lease_id") or "").strip()
        unit_id = str(payload.get("unit_id") or "").strip()

        subtasks: list[dict[str, Any]] = []
        for index, domain in enumerate(selected, start=1):
            capability = {
                "lease": "lease.query",
                "billing": "billing.statement",
                "property": "property.work_orders",
            }[domain]
            task_payload: dict[str, Any] = {}
            if lease_id:
                task_payload["lease_id"] = lease_id
            if unit_id:
                task_payload["unit_id"] = unit_id
            if domain == "property" and _mentions_hvac(text):
                task_payload["category"] = "hvac"
            if domain == "lease":
                # 条款检索需要原始问题作为查询依据；由 Planner 显式下发，
                # Agent 不应自己去猜"该查什么条款"。
                task_payload["query"] = text
            subtasks.append(
                {
                    "subtask_id": f"st_{index}_{domain}",
                    "capability": capability,
                    "payload": task_payload,
                }
            )
        route = "deterministic" if len(subtasks) == 1 else "fanout"
        return subtasks, route


def _is_pure_arrears_question(text: str) -> bool:
    pure_markers = ("欠多少", "欠费多少", "还有多少钱没交", "未收多少", "余额多少")
    return any(marker in text for marker in pure_markers)


def _mentions_hvac(text: str) -> bool:
    return "空调" in text


@dataclass(frozen=True)
class InvestigationResult:
    verdict: str
    report: dict[str, Any]
    results: tuple[dict[str, Any], ...] = ()
    failures: tuple[dict[str, Any], ...] = ()
    conflicts: tuple[dict[str, Any], ...] = ()
    missing: tuple[str, ...] = ()
    revision: int = 0
    route: str = ""
    warnings: tuple[str, ...] = ()


def verify_results(
    *,
    plan: list[dict[str, Any]],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """确定性证据核验。

    返回 (verdict, conflicts, missing)：

    - `insufficient`：有子任务失败、或租约引用的文档缺失；
    - `conflicting`：账单租金与合同规则存在差额（必须并列呈现，不得擅自选边）；
    - `supported`：上述都不成立。
    """

    conflicts: list[dict[str, Any]] = []
    missing: list[str] = []

    expected = {item["subtask_id"] for item in plan}
    completed = {item["subtask_id"] for item in results}
    for subtask_id in sorted(expected - completed):
        missing.append(f"未获得子任务结果: {subtask_id}")

    for failure in failures:
        missing.append(
            f"子任务 {failure.get('subtask_id')} 失败: {failure.get('error_code')}"
        )

    for item in results:
        output = item.get("output") or {}
        documents = output.get("missing_documents") or []
        for doc_id in documents:
            missing.append(f"合同引用但未电子化的文档: {doc_id}")
        variance = output.get("rent_variance_total")
        if variance not in (None, "", "0.00", 0):
            conflicts.append(
                {
                    "type": "rent_variance",
                    "amount": str(variance),
                    "expected_basis": "lease.charge_rule",
                    "observed_basis": "invoice_item.unit_price",
                    "subtask_id": item.get("subtask_id"),
                    "evidence_ids": [
                        evidence_id
                        for evidence_id in _evidence_ids(output)
                    ],
                }
            )

    # 冲突优先级高于"资料缺失"：真实存在的金额矛盾必须被看见，
    # 缺失资料作为并列的待办项输出，而不是掩盖冲突。
    if conflicts:
        return "conflicting", _dedupe(conflicts), sorted(set(missing))
    if missing:
        return "insufficient", [], sorted(set(missing))
    return "supported", [], []


def _evidence_ids(output: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for item in output.get("evidence", []) or []:
        if isinstance(item, dict) and item.get("evidence_id"):
            ids.append(str(item["evidence_id"]))
    return ids


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        key = (str(item.get("type")), str(item.get("amount")))
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def build_investigation_graph(
    *,
    registry: AgentRegistry,
    planner: Planner | None = None,
    max_revisions: int = 1,
) -> Any:
    """编译调查图。节点通过 capability 解析 Agent，不引用具体类。"""

    planner = planner or RuleBasedPlanner()

    def plan_node(state: InvestigationState) -> dict[str, Any]:
        subtasks, route = planner.plan(state["question"], dict(state))
        return {
            "plan": subtasks,
            "route": route,
            "expected_subtasks": [item["subtask_id"] for item in subtasks],
            "revision": state.get("revision", 0),
        }

    def route_after_plan(state: InvestigationState) -> str:
        return "deterministic_answer" if state.get("route") == "deterministic" else "dispatch"

    def dispatch(state: InvestigationState) -> list[Send]:
        return [
            Send("run_subtask", {**state, "subtask": subtask})
            for subtask in state.get("plan", [])
        ]

    async def run_subtask(state: dict[str, Any]) -> dict[str, Any]:
        subtask = state["subtask"]
        context = state["context"]
        assert isinstance(context, AgentContext)
        sub_context = context.model_copy(update={"subtask_id": subtask["subtask_id"]})
        request = AgentRequest(
            task_id=context.metadata.get("task_id", "task-investigation"),
            capability=subtask["capability"],
            payload=dict(subtask.get("payload") or {}),
        )
        try:
            agent = registry.require_capability(subtask["capability"])
        except CapabilityUnavailableError as exc:
            return {
                "failures": [
                    {
                        "subtask_id": subtask["subtask_id"],
                        "capability": subtask["capability"],
                        "error_code": ErrorCode.CAPABILITY_UNAVAILABLE.value,
                        "message": str(exc),
                    }
                ]
            }
        except AgentDisabledError as exc:
            return {
                "failures": [
                    {
                        "subtask_id": subtask["subtask_id"],
                        "capability": subtask["capability"],
                        "error_code": ErrorCode.AGENT_NOT_ENABLED.value,
                        "message": str(exc),
                    }
                ]
            }

        result = await agent.handle(request, sub_context)
        payload = {
            "subtask_id": subtask["subtask_id"],
            "capability": subtask["capability"],
            "agent": agent.descriptor.name,
            "agent_version": agent.descriptor.version,
            "status": result.status.value,
            "output": result.output,
            "warnings": list(result.warnings),
        }
        if result.status is TaskStatus.FAILED:
            error = result.error
            return {
                "failures": [
                    {
                        "subtask_id": subtask["subtask_id"],
                        "capability": subtask["capability"],
                        "error_code": error.code.value if error else ErrorCode.INTERNAL_ERROR.value,
                        "message": error.message if error else "",
                    }
                ]
            }
        return {"results": [payload], "warnings": list(result.warnings)}

    async def deterministic_answer(state: InvestigationState) -> dict[str, Any]:
        """单能力路径：直接调用一次，不经过扇出节点。"""

        return await run_subtask({**state, "subtask": state["plan"][0]})

    def verify_node(state: InvestigationState) -> dict[str, Any]:
        verdict, conflicts, missing = verify_results(
            plan=state.get("plan", []),
            results=_latest_by_subtask(state.get("results", [])),
            failures=state.get("failures", []),
        )
        return {"verdict": verdict, "conflicts": conflicts, "missing": missing}

    def route_after_verify(state: InvestigationState) -> str:
        # 只有"子任务失败"才值得补查；文档缺失无法通过重跑补齐，重跑只是浪费预算
        if (
            state.get("verdict") == "insufficient"
            and state.get("failures")
            and state.get("revision", 0) < max_revisions
        ):
            return "revise"
        return "report"

    def revise_node(state: InvestigationState) -> dict[str, Any]:
        """补查：只补"计划内但没有结果"的子任务，不新增未计划的能力。"""

        completed = {item["subtask_id"] for item in state.get("results", [])}
        pending = [
            subtask
            for subtask in state.get("plan", [])
            if subtask["subtask_id"] not in completed
        ]
        return {
            "plan": pending or state.get("plan", []),
            "revision": state.get("revision", 0) + 1,
            "warnings": [f"触发第 {state.get('revision', 0) + 1} 次补查"],
        }

    def report_node(state: InvestigationState) -> dict[str, Any]:
        results = _latest_by_subtask(state.get("results", []))
        findings = _build_findings(results)
        report = {
            "question": state.get("question"),
            "lease_id": state.get("lease_id"),
            "verdict": state.get("verdict", "insufficient"),
            "route": state.get("route"),
            "revision": state.get("revision", 0),
            "findings": findings,
            # conflicts/missing 是 append 通道，补查会让同一结论重复出现，报告必须去重
            "conflicts": _dedupe(list(state.get("conflicts", []))),
            "missing_information": sorted(set(state.get("missing", []))),
            # verdict 回答"证据是否自相矛盾"，completeness 回答"调查是否跑全"。
            # 两个维度必须分开：既有真实冲突又有子任务失败时，只报一个会丢掉另一半信息。
            "completeness": (
                "partial" if state.get("failures") or state.get("missing") else "complete"
            ),
            "agent_results": [
                {
                    "subtask_id": item["subtask_id"],
                    "capability": item["capability"],
                    "agent": item["agent"],
                    "status": item["status"],
                }
                for item in results
            ],
            "failures": state.get("failures", []),
            "requires_human_review": state.get("verdict") != "supported",
            "disclaimer": "本报告只陈述事实与冲突，不构成减免/调账决定",
        }
        return {"report": report}

    graph = StateGraph(InvestigationState)
    graph.add_node("plan", plan_node)
    graph.add_node("dispatch", lambda state: {})
    graph.add_node("run_subtask", run_subtask)
    graph.add_node("deterministic_answer", deterministic_answer)
    graph.add_node("verify", verify_node)
    graph.add_node("revise", revise_node)
    graph.add_node("report", report_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges(
        "plan", route_after_plan, {"deterministic_answer": "deterministic_answer", "dispatch": "dispatch"}
    )
    graph.add_conditional_edges("dispatch", dispatch, ["run_subtask"])
    graph.add_edge("run_subtask", "verify")
    graph.add_edge("deterministic_answer", "verify")
    graph.add_conditional_edges("verify", route_after_verify, {"revise": "revise", "report": "report"})
    graph.add_edge("revise", "dispatch")
    graph.add_edge("report", END)

    return graph.compile()


def _latest_by_subtask(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 `subtask_id` 归并：补查重跑时保留最后一次，避免重复计数。"""

    latest: dict[str, dict[str, Any]] = {}
    for item in results:
        latest[item["subtask_id"]] = item
    return [latest[key] for key in sorted(latest)]


def _truncate(text: Any, limit: int = 60) -> str:
    value = "" if text is None else str(text).replace("\n", " ").strip()
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _build_findings(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in results:
        output = item.get("output") or {}
        evidence_ids = _evidence_ids(output)
        if not evidence_ids:
            continue
        if item["capability"] == "billing.statement":
            findings.append(
                {
                    "statement": (
                        f"账单应收 {output.get('invoiced_total')}、"
                        f"已收 {output.get('paid_total')}、未收 {output.get('outstanding_total')}"
                    ),
                    "evidence_ids": evidence_ids,
                    "derivation": "computed",
                }
            )
        elif item["capability"] == "lease.query":
            lease = output.get("lease") or {}
            findings.append(
                {
                    "statement": (
                        f"租期 {lease.get('start_date')} 至 {lease.get('end_date')}，"
                        f"状态 {lease.get('status')}"
                    ),
                    "evidence_ids": evidence_ids,
                    "derivation": "direct",
                }
            )
            clauses = output.get("clauses") or []
            clause_evidence_ids = _evidence_ids({"evidence": output.get("clause_evidence", [])})
            for clause in clauses:
                findings.append(
                    {
                        "statement": (
                            f"合同第 {clause.get('page')} 页 {clause.get('clause_id')} 条："
                            f"{_truncate(clause.get('excerpt'))}"
                        ),
                        "evidence_ids": [
                            evidence_id
                            for evidence_id in clause_evidence_ids
                            if clause.get("clause_id") in evidence_id
                        ]
                        or clause_evidence_ids,
                        "derivation": "document_clause",
                        "source": {
                            "document_id": clause.get("document_id"),
                            "document_version": clause.get("document_version"),
                            "page": clause.get("page"),
                            "clause_id": clause.get("clause_id"),
                        },
                    }
                )
        elif item["capability"] == "property.work_orders":
            findings.append(
                {
                    "statement": (
                        f"相关工单 {output.get('work_order_count', 0)} 条，"
                        f"未关闭 {output.get('open_count', 0)} 条"
                    ),
                    "evidence_ids": evidence_ids,
                    "derivation": "direct",
                }
            )
    return findings


@dataclass
class Investigator:
    """Coordinator 门面：构造上下文并运行图。"""

    registry: AgentRegistry
    repository: FixtureRepository
    max_revisions: int = 1
    planner: Planner | None = None
    _graph: Any = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self._graph = build_investigation_graph(
            registry=self.registry,
            planner=self.planner,
            max_revisions=self.max_revisions,
        )

    async def investigate(
        self, *, question: str, lease_id: str, context: AgentContext
    ) -> InvestigationResult:
        state = await self._graph.ainvoke(
            {
                "question": question,
                "lease_id": lease_id,
                "context": context,
                "results": [],
                "failures": [],
                "warnings": [],
                "conflicts": [],
                "missing": [],
                "revision": 0,
            }
        )
        report = state.get("report", {})
        results = tuple(_latest_by_subtask(state.get("results", [])))
        verdict = report.get("verdict", state.get("verdict", "insufficient"))
        return InvestigationResult(
            verdict=verdict,
            report=report,
            results=results,
            failures=tuple(state.get("failures", [])),
            # 以报告中的去重结果为准：conflicts 是 append 通道，补查会重复
            conflicts=tuple(report.get("conflicts", [])),
            missing=tuple(sorted(set(state.get("missing", [])))),
            revision=int(state.get("revision", 0)),
            route=str(state.get("route", "")),
            warnings=tuple(state.get("warnings", [])),
        )
