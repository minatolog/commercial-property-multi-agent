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
import uuid
from dataclasses import dataclass, field, replace
from typing import Annotated, Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from ..agents.base.contracts import AgentContext, AgentRequest, TaskStatus, utcnow
from ..agents.base.errors import (
    AgentDisabledError,
    AgentError,
    CapabilityUnavailableError,
    ErrorCode,
)
from ..agents.base.registry import AgentRegistry
from ..fixtures.repository import FixtureRepository
from .approval import (
    DEFAULT_APPROVAL_RULE,
    ApprovalRequest,
    ApprovalRule,
    ApprovalRequestNotFoundError,
    ApprovalValidationError,
    build_approval_request,
)

__all__ = [
    "DEFAULT_CAPABILITIES",
    "InvestigationResult",
    "InvestigationState",
    "Investigator",
    "Planner",
    "RuleBasedPlanner",
    "ThreadIdentityConflictError",
    "build_investigation_graph",
    "build_reduction_draft",
    "verify_results",
]


class ThreadIdentityConflictError(AgentError):
    """同一 `thread_id` 被不同运行/主体/租约复用。

    checkpoint 里的 `results`/`failures` 是追加通道，新一次 `investigate` 传入空列表
    并不能清掉旧结果；如果还允许换主体或换租约复用同一线索，旧结果会把本次
    越权或失败"补齐"成成功（审查 R1）。因此这里直接拒绝，而不是做静默合并。
    """

    default_code = ErrorCode.INVALID_CONTEXT


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
    #: Task 012：持久线索标识，恢复靠它（checkpoint 按 thread_id 存取）
    thread_id: str
    route: str
    plan: list[dict[str, Any]]
    expected_subtasks: list[str]
    results: Annotated[list[dict[str, Any]], operator.add]
    failures: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]
    #: verify 每轮**重新计算**当前冲突与缺口，因此是"覆盖"语义（不是追加）。
    #: 用追加会让补查成功后仍残留上一轮的 missing（审查 F4）。
    conflicts: list[dict[str, Any]]
    missing: list[str]
    revision: int
    #: 补查时只重跑这些子任务（空表示"按原计划全部执行"）
    retry_subtasks: list[str]
    verdict: str
    report: dict[str, Any]
    #: Task 012：审批门相关通道
    approval_request: dict[str, Any]
    approval_status: str
    approved_draft: dict[str, Any]


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
    thread_id: str = ""
    approval_status: str = ""
    approval_request: dict[str, Any] | None = None
    approved_draft: dict[str, Any] | None = None


def approved_draft_payload(request: ApprovalRequest) -> dict[str, Any]:
    """已批准草案的唯一构造点（图节点与 `resume()` 共用，避免两处口径不一）。

    注意：这里**只**产出草案状态，不含任何业务副作用。
    """

    return {
        "draft_id": request.draft_id,
        "draft_version": request.draft_version,
        "action_type": request.action_type,
        "amount": request.amount,
        "currency": request.currency,
        "project_id": request.project_id,
        "target": request.payload.get("target", {}),
        "evidence_ids": list(request.evidence_ids),
        "status": "approved_draft_only",
        "executed_side_effects": [],
        "request_id": request.request_id,
        "approved_stages": [
            {"role": stage.role, "decided_by": stage.decided_by, "decided_at": stage.decided_at}
            for stage in request.stages
            if stage.status == "approved"
        ],
    }


def _safe_snapshot(repository: Any) -> dict[str, Any]:
    """fixture 仓库有 `snapshot()`；只读数据库仓库没有。

    审批规则与草案都来自 fixture 元数据，因此数据库后端下这两项自然缺失——
    缺失就"没有可审批草案"，而不是报错。
    """

    accessor = getattr(repository, "snapshot", None)
    if not callable(accessor):
        return {}
    return accessor() or {}


def build_reduction_draft(
    *,
    repository: FixtureRepository,
    lease_id: str,
    amount: str,
    evidence_ids: list[str],
) -> dict[str, Any] | None:
    """从 fixture 里挑出**当前有效**的减免草案（同 draft_id 取最高版本）。

    为什么从数据里挑而不是现场生成：草案是业务产物，金额与目标必须可审计；
    Agent 只负责"发现差额并把草案送审批"，不凭空捏造金额。
    """

    drafts = _safe_snapshot(repository).get("approval_drafts", {})
    candidates = [
        draft
        for draft in drafts.values()
        if (draft.get("target") or {}).get("lease_id") == lease_id
        and draft.get("status") == "awaiting_approval"
    ]
    if not candidates:
        return None
    latest = max(candidates, key=lambda item: int(item.get("draft_version", 0)))
    return {
        "draft_id": latest["draft_id"],
        "draft_version": int(latest["draft_version"]),
        "action_type": latest["action_type"],
        "project_id": latest["project_id"],
        "target": latest.get("target", {}),
        "amount": str(latest.get("amount")),
        "currency": latest.get("currency", "CNY"),
        "expires_at": latest.get("expires_at"),
        "evidence_ids": list(dict.fromkeys([*evidence_ids, *latest.get("evidence_ids", [])])),
        "computed_variance": amount,
    }


def verify_results(
    *,
    plan: list[dict[str, Any]],
    results: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    expected_subtasks: list[str] | None = None,
) -> tuple[str, list[dict[str, Any]], list[str]]:
    """确定性证据核验。

    返回 (verdict, conflicts, missing)：

    - `insufficient`：有**未解决**的子任务失败、或租约引用的文档缺失；
    - `conflicting`：账单租金与合同规则存在差额（必须并列呈现，不得擅自选边）；
    - `supported`：上述都不成立。

    Task 016（F4）：补查成功后，"历史尝试"不应继续被当成当前失败。

    - 期望集合用 `expected_subtasks`（**原始**计划），不受补查后 plan 收缩影响；
    - 失败的判定改为"该 `subtask_id` 没有任何结果"：一旦重跑成功，历史失败自动失效，
      但仍可从 trace 审计（trace 是 append-only，不会被清掉）。
    """

    conflicts: list[dict[str, Any]] = []
    missing: list[str] = []

    expected = set(expected_subtasks or [item["subtask_id"] for item in plan])
    completed = {item["subtask_id"] for item in results}
    for subtask_id in sorted(expected - completed):
        missing.append(f"未获得子任务结果: {subtask_id}")

    unresolved = [
        failure
        for failure in failures
        if failure.get("subtask_id") not in completed
    ]
    for failure in {item.get("subtask_id"): item for item in unresolved}.values():
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
    approval_rule: ApprovalRule | None = None,
    #: 创建/读取审批请求：返回**权威**请求（已存在则返回既有记录，不新建 ID）
    approval_hook: Callable[[ApprovalRequest], ApprovalRequest] | None = None,
    #: 按 ID 读取权威请求（恢复后回读台账状态）
    approval_reader: Callable[[str], ApprovalRequest | None] | None = None,
    draft_resolver: Callable[[InvestigationState, list[dict[str, Any]]], dict[str, Any] | None]
    | None = None,
    budget_snapshot: Callable[[], Any] | None = None,
    checkpointer: Any = None,
) -> Any:
    """编译调查图。节点通过 capability 解析 Agent，不引用具体类。

    `draft_resolver` 决定"是否需要人工审批"并给出草案；
    `approval_hook` 在审批门触发时被调用（写入审批台账），返回 `pending` 或其它阻塞状态。
    两者都不传时（单测/纯离线演示）审批门只标记状态，不 `interrupt`。
    """

    planner = planner or RuleBasedPlanner()
    rule = approval_rule or DEFAULT_APPROVAL_RULE

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
        retry = set(state.get("retry_subtasks") or ())
        subtasks = [
            subtask
            for subtask in state.get("plan", [])
            if not retry or subtask["subtask_id"] in retry
        ]
        return [
            Send("run_subtask", {**state, "subtask": subtask}) for subtask in subtasks
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
                        "run_id": context.run_id,
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
                        "run_id": context.run_id,
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
            "run_id": context.run_id,
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
                        "run_id": context.run_id,
                    }
                ]
            }
        return {"results": [payload], "warnings": list(result.warnings)}

    async def deterministic_answer(state: InvestigationState) -> dict[str, Any]:
        """单能力路径：直接调用一次，不经过扇出节点。"""

        return await run_subtask({**state, "subtask": state["plan"][0]})

    def _run_id(state: InvestigationState) -> str | None:
        context = state.get("context")
        return getattr(context, "run_id", None)

    def verify_node(state: InvestigationState) -> dict[str, Any]:
        run_id = _run_id(state)
        verdict, conflicts, missing = verify_results(
            plan=state.get("plan", []),
            results=_latest_by_subtask(_scoped_by_run(state.get("results", []), run_id)),
            failures=_scoped_by_run(state.get("failures", []), run_id),
            expected_subtasks=state.get("expected_subtasks") or None,
        )
        return {"verdict": verdict, "conflicts": conflicts, "missing": missing}

    def route_after_verify(state: InvestigationState) -> str:
        run_id = _run_id(state)
        # 只有"子任务失败"才值得补查；文档缺失无法通过重跑补齐，重跑只是浪费预算。
        # Task 017（R6）：可恢复性按**未解决的可重试子任务**判断，不看总体 verdict——
        # 账单差额会把 verdict 提升为 conflicting，若用它当闸门，其它领域的超时
        # 就再也得不到补查机会。冲突本身仍然保留在报告里。
        resolved = {
            item["subtask_id"]
            for item in _scoped_by_run(state.get("results", []), run_id)
        }
        retryable = [
            failure
            for failure in _scoped_by_run(state.get("failures", []), run_id)
            if failure.get("subtask_id") not in resolved
        ]
        if retryable and state.get("revision", 0) < max_revisions:
            return "revise"
        return "report"

    def revise_node(state: InvestigationState) -> dict[str, Any]:
        """补查：只补"计划内但没有结果"的子任务，不新增未计划的能力。

        `plan` 保持**原始**计划不变（供核验与报告引用完整任务集），
        真正需要重跑的子任务放进 `retry_subtasks`。
        """

        run_id = _run_id(state)
        completed = {
            item["subtask_id"]
            for item in _scoped_by_run(state.get("results", []), run_id)
        }
        pending = [
            subtask["subtask_id"]
            for subtask in state.get("plan", [])
            if subtask["subtask_id"] not in completed
        ]
        return {
            "retry_subtasks": pending,
            "revision": state.get("revision", 0) + 1,
            "warnings": [f"触发第 {state.get('revision', 0) + 1} 次补查"],
        }

    def report_node(state: InvestigationState) -> dict[str, Any]:
        run_id = _run_id(state)
        results = _latest_by_subtask(_scoped_by_run(state.get("results", []), run_id))
        findings = _build_findings(results)
        draft = draft_resolver(state, findings) if draft_resolver is not None else None
        completed = {item["subtask_id"] for item in results}
        failures = _scoped_by_run(state.get("failures", []), run_id)
        # 同一子任务可能失败多次（首轮 + 补查）；报告只保留**最后一次**失败，
        # 否则"一个子任务挂了"会被读成"两个子任务挂了"。
        unresolved = list(
            {
                failure.get("subtask_id"): failure
                for failure in failures
                if failure.get("subtask_id") not in completed
            }.values()
        )
        expected = set(
            state.get("expected_subtasks")
            or [item["subtask_id"] for item in state.get("plan", [])]
        )
        missing = sorted(
            set(state.get("missing", []))
            | {f"未获得子任务结果: {item}" for item in expected - completed}
        )
        report = {
            "question": state.get("question"),
            "lease_id": state.get("lease_id"),
            "verdict": state.get("verdict", "insufficient"),
            "route": state.get("route"),
            "revision": state.get("revision", 0),
            "findings": findings,
            # conflicts/missing 是 append 通道，补查会让同一结论重复出现，报告必须去重
            "conflicts": _dedupe(list(state.get("conflicts", []))),
            "missing_information": missing,
            # verdict 回答"证据是否自相矛盾"，completeness 回答"调查是否跑全"。
            # 两个维度必须分开：既有真实冲突又有子任务失败时，只报一个会丢掉另一半信息。
            # Task 016（F4）：补查成功后 unresolved 应为空，不再残留"历史失败"。
            "completeness": "partial" if unresolved or missing else "complete",
            "agent_results": [
                {
                    "subtask_id": item["subtask_id"],
                    "capability": item["capability"],
                    "agent": item["agent"],
                    "status": item["status"],
                }
                for item in results
            ],
            # 报告只列**当前未解决**的失败；历史尝试保留在 trace 中供审计
            "failures": unresolved,
            "resolved_failures": [
                failure
                for failure in {
                    item.get("subtask_id"): item
                    for item in failures
                    if item.get("subtask_id") in completed
                }.values()
            ],
            "requires_human_review": state.get("verdict") != "supported",
            "disclaimer": "本报告只陈述事实与冲突，不构成减免/调账决定",
        }
        if draft is not None:
            report["proposed_draft"] = draft
        return {"report": report, "approval_status": "not_required" if draft is None else "ready"}

    def approval_node(state: InvestigationState) -> dict[str, Any]:
        """审批门：独立节点，只负责"发起审批 / 记录结论"，绝不执行业务动作。

        没有审批钩子（例如纯离线演示、单测）时不 `interrupt`，只把状态标成
        `unavailable`，让调用方明确知道"这里需要人工，但本进程没接审批"。
        """

        draft = (state.get("report") or {}).get("proposed_draft")
        if draft is None:
            return {"approval_status": "not_required"}

        budget = budget_snapshot() if budget_snapshot is not None else None
        if budget is not None:
            snapshot = (
                budget.model_dump() if hasattr(budget, "model_dump") else dict(budget)
            )
            limit = int(snapshot.get("max_tool_calls") or 0)
            used = int(snapshot.get("used_tool_calls") or 0)
            if limit > 0 and used >= limit:
                return {
                    "approval_status": "blocked_budget",
                    "warnings": ["预算耗尽：无法发起人工审批"],
                }

        if approval_hook is None:
            return {
                "approval_status": "unavailable",
                "warnings": ["未配置审批通道：草案仅停留在报告中，未进入审批"],
            }

        context = state["context"]
        candidate = build_approval_request(
            draft=draft,
            rule=rule,
            thread_id=state.get("thread_id") or context.run_id or "thread_unknown",
            run_id=context.run_id or "run_unknown",
            trace_id=context.trace_id,
            requested_by=context.principal_id or "principal_unknown",
        )
        # Task 016（F5）：钩子返回**权威**请求。恢复时节点会重新执行，
        # 若沿用新构造的随机 request_id，报告引用的审批记录在台账里根本不存在。
        request = approval_hook(candidate)

        if request.status != "pending":
            return {
                "approval_status": request.status,
                "approval_request": request.as_dict(),
                "approved_draft": (
                    approved_draft_payload(request)
                    if request.status == "approved"
                    else None
                ),
            }

        decision = interrupt(
            {
                "type": "approval_required",
                "request_id": request.request_id,
                "draft_id": request.draft_id,
                "draft_version": request.draft_version,
                "amount": request.amount,
                "currency": request.currency,
                "stages": [item.as_dict() for item in request.stages],
                "expires_at": request.expires_at,
            }
        )
        outcome = decision if isinstance(decision, dict) else {}
        # 恢复后以**台账**为准，而不是以恢复载荷为准：载荷只用于传递 request_id
        authoritative = (
            approval_reader(str(outcome.get("request_id") or request.request_id))
            if approval_reader is not None
            else None
        )
        if authoritative is not None:
            status = authoritative.status
            approved = (
                approved_draft_payload(authoritative)
                if status == "approved"
                else None
            )
            return {
                "approval_status": status,
                "approval_request": authoritative.as_dict(),
                "approved_draft": approved,
            }
        status = str(outcome.get("status", "unknown"))
        approved = outcome.get("approved_draft")
        return {
            "approval_status": status,
            "approval_request": request.as_dict(),
            "approved_draft": approved if isinstance(approved, dict) else None,
        }

    graph = StateGraph(InvestigationState)
    graph.add_node("plan", plan_node)
    graph.add_node("dispatch", lambda state: {})
    graph.add_node("run_subtask", run_subtask)
    graph.add_node("deterministic_answer", deterministic_answer)
    graph.add_node("verify", verify_node)
    graph.add_node("revise", revise_node)
    graph.add_node("report", report_node)
    graph.add_node("approval", approval_node)

    graph.add_edge(START, "plan")
    graph.add_conditional_edges(
        "plan", route_after_plan, {"deterministic_answer": "deterministic_answer", "dispatch": "dispatch"}
    )
    graph.add_conditional_edges("dispatch", dispatch, ["run_subtask"])
    graph.add_edge("run_subtask", "verify")
    graph.add_edge("deterministic_answer", "verify")
    graph.add_conditional_edges("verify", route_after_verify, {"revise": "revise", "report": "report"})
    graph.add_edge("revise", "dispatch")
    graph.add_edge("report", "approval")
    graph.add_edge("approval", END)

    return graph.compile(checkpointer=checkpointer)


def _latest_by_subtask(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 `subtask_id` 归并：补查重跑时保留最后一次，避免重复计数。"""

    latest: dict[str, dict[str, Any]] = {}
    for item in results:
        latest[item["subtask_id"]] = item
    return [latest[key] for key in sorted(latest)]


def _scoped_by_run(items: list[dict[str, Any]], run_id: str | None) -> list[dict[str, Any]]:
    """只保留属于当前运行的结果/失败。

    纵深防御（审查 R1）：即使某条 thread 上残留了别的运行写入的条目，也不能用它们
    消除本次运行的失败或冒充本次运行的结果。没有 `run_id` 的旧条目在"有当前运行"
    时一律丢弃；当前运行没有 `run_id`（无 checkpointer 的直连路径）时不过滤。
    """

    if not run_id:
        return list(items)
    return [item for item in items if item.get("run_id") == run_id]


def _chunk_ids_for_clause(
    clause: dict[str, Any], evidence_ids: list[str]
) -> list[str]:
    """回退路径：按复合键（文档 + 版本 + 页 + 条款号）重建 chunk_id 精确匹配。

    只在调用方没有直接给出 `chunk_id` 时使用；绝不退回"条款号子串"匹配。
    """

    document_id = clause.get("document_id")
    version = clause.get("document_version")
    page = clause.get("page")
    clause_id = clause.get("clause_id")
    if None in (document_id, version, page, clause_id):
        return []
    expected = f"{document_id}#v{version}#p{page}#{clause_id}"
    return [evidence_id for evidence_id in evidence_ids if evidence_id == expected]


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
                chunk_id = clause.get("chunk_id")
                # Task 017（R7）：证据必须与"这一条 finding 具体引用的那一段"精确对应。
                # 用 `clause_id in evidence_id` 做子串匹配会把同条号的其他版本、
                # 甚至 5.1 与 5.1.1 混进来，审计时无法判定哪份原文支持哪个结论。
                clause_ids = (
                    [chunk_id] if chunk_id else _chunk_ids_for_clause(clause, clause_evidence_ids)
                )
                draft = str(clause.get("document_status", "signed")) != "signed"
                findings.append(
                    {
                        "statement": (
                            f"{'【未签署草案，不得作为生效依据】' if draft else ''}"
                            f"合同第 {clause.get('page')} 页 {clause.get('clause_id')} 条："
                            f"{_truncate(clause.get('excerpt'))}"
                        ),
                        "evidence_ids": clause_ids,
                        "derivation": "document_draft" if draft else "document_clause",
                        "source": {
                            "document_id": clause.get("document_id"),
                            "document_version": clause.get("document_version"),
                            "document_status": clause.get("document_status", "signed"),
                            "page": clause.get("page"),
                            "clause_id": clause.get("clause_id"),
                            "chunk_id": chunk_id,
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
    """Coordinator 门面：构造上下文、运行图、以及（可选）暂停/恢复。

    审批与持久化的接线是**可选**的：不传 `approval_store` / `checkpointer` 时，
    行为与 Task 009 完全一致（无 interrupt、无持久化），保证既有调用方零改动。
    """

    registry: AgentRegistry
    repository: FixtureRepository
    max_revisions: int = 1
    planner: Planner | None = None
    approval_store: Any = None
    checkpointer: Any = None
    approval_rule: ApprovalRule | None = None
    budget_snapshot: Callable[[], dict[str, Any]] | None = None
    _graph: Any = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        hook = None
        reader = None
        if self.approval_store is not None:
            store = self.approval_store

            def hook(request: ApprovalRequest) -> ApprovalRequest:
                # create() 对 (thread, draft, version) 幂等：恢复时返回既有记录
                return store.create(request)

            def reader(request_id: str) -> ApprovalRequest | None:
                return store.get(request_id)

        rule = self.approval_rule or self._rule_from_fixture()
        self._graph = build_investigation_graph(
            registry=self.registry,
            planner=self.planner,
            max_revisions=self.max_revisions,
            approval_rule=rule,
            approval_hook=hook,
            approval_reader=reader,
            draft_resolver=self._resolve_draft,
            budget_snapshot=self.budget_snapshot,
            checkpointer=self.checkpointer,
        )

    def _rule_from_fixture(self) -> ApprovalRule | None:
        rules = _safe_snapshot(self.repository).get("approval_role_rules") or {}
        if not rules:
            return None
        action_type = next(iter(rules))
        return ApprovalRule.from_fixture(action_type, rules[action_type])

    def _resolve_draft(
        self, state: InvestigationState, findings: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """只有"存在真实金额冲突"时才生成待审批草案。

        没有差额就没有需要审批的减免，硬造一份草案等于凭空制造业务动作。
        """

        conflicts = _dedupe(list(state.get("conflicts", [])))
        variance = next(
            (
                str(item.get("amount"))
                for item in conflicts
                if item.get("type") == "rent_variance"
            ),
            None,
        )
        if variance is None:
            return None
        evidence_ids = [
            evidence_id for finding in findings for evidence_id in finding["evidence_ids"]
        ]
        return build_reduction_draft(
            repository=self.repository,
            lease_id=str(state.get("lease_id") or ""),
            amount=variance,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
        )

    async def investigate(
        self,
        *,
        question: str,
        lease_id: str,
        context: AgentContext,
        thread_id: str | None = None,
    ) -> InvestigationResult:
        """开始一次**新运行**。

        `thread_id` 指向一条持久线索；若该线索上已有状态（上一次运行的 checkpoint
        或等待审批的中断），本次调用会被拒绝（审查 R1）：

        - 追加型通道（`results`/`failures`）不会被传入的空列表清空，旧结果会
          混进本次结论；
        - 换主体/换租约复用同一线索时，旧结果甚至会把本次的越权失败"补齐"成功。

        恢复已有任务请用 `resume()`；需要新任务请换一个 `thread_id`。
        """

        effective_thread = thread_id or f"thread_{context.run_id or uuid.uuid4().hex[:12]}"
        await self._assert_thread_is_new(effective_thread, context, lease_id)
        payload: dict[str, Any] = {
            "question": question,
            "lease_id": lease_id,
            "context": context,
            "thread_id": effective_thread,
            "results": [],
            "failures": [],
            "warnings": [],
            "conflicts": [],
            "missing": [],
            "revision": 0,
        }
        state = await self._ainvoke(payload, thread_id=effective_thread)
        return await self._to_result(state, effective_thread)

    async def _assert_thread_is_new(
        self, thread_id: str, context: AgentContext, lease_id: str
    ) -> None:
        """同一线索只允许承载一次运行；身份不一致时给出可操作的错误。"""

        existing = await self._current_state(thread_id)
        if not existing:
            return
        previous = existing.get("context")
        previous_run = getattr(previous, "run_id", None)
        previous_principal = getattr(previous, "principal_id", None)
        previous_lease = existing.get("lease_id")
        # 先报最具体的越界（主体/租约），再报"线索已被别的运行占用"，
        # 这样错误信息能直接指出是哪一类身份冲突。
        if previous_principal and previous_principal != context.principal_id:
            raise ThreadIdentityConflictError(
                (
                    f"thread_id={thread_id!r} 属于主体 {previous_principal}，"
                    f"不能由 {context.principal_id} 复用"
                ),
                details={
                    "thread_id": thread_id,
                    "previous_principal_id": previous_principal,
                    "requested_principal_id": context.principal_id,
                },
            )
        if previous_lease and previous_lease != lease_id:
            raise ThreadIdentityConflictError(
                (
                    f"thread_id={thread_id!r} 属于租约 {previous_lease}，"
                    f"不能用于租约 {lease_id}"
                ),
                details={
                    "thread_id": thread_id,
                    "previous_lease_id": previous_lease,
                    "requested_lease_id": lease_id,
                },
            )
        if previous_run and context.run_id and previous_run != context.run_id:
            raise ThreadIdentityConflictError(
                (
                    f"thread_id={thread_id!r} 已被运行 {previous_run} 占用，"
                    "不能用于新运行；请换一个 thread_id（恢复请用 resume）"
                ),
                details={
                    "thread_id": thread_id,
                    "previous_run_id": previous_run,
                    "requested_run_id": context.run_id,
                },
            )
        # 身份完全相同也拒绝：重复 investigate 只会把同一批子任务再追加一遍，
        # 而"恢复/重放"的语义属于 resume()。
        raise ThreadIdentityConflictError(
            f"thread_id={thread_id!r} 上已有运行状态，不能再次 investigate；恢复请用 resume",
            details={"thread_id": thread_id, "previous_run_id": previous_run},
        )

    async def resume(
        self,
        *,
        request_id: str,
        decision: str,
        draft_version: int,
        principal_id: str,
        reason: str | None = None,
        dry_run: bool = False,
    ) -> InvestigationResult:
        """人工决定后恢复被中断的图。

        三重保护：
        1. 校验通过才允许恢复（权限/版本/过期/阶段顺序，见 `ApprovalStore.decide`）；
        2. `resume_ledger` 以 `request_id` 唯一，重复恢复直接返回首次结果，不重放节点；
        3. 恢复后只产出 `approved_draft`，不执行任何业务写操作。

        Task 016：`reason` 会写入审批审计；恢复后 `approval_request` 一律回读台账，
        保证返回的 request_id / version / status / stages 与持久记录一致（F5）。
        """

        if self.approval_store is None:
            raise ApprovalValidationError("未配置审批台账，无法恢复审批流程")
        store = self.approval_store
        request = store.get(request_id)
        if request is None:
            raise ApprovalRequestNotFoundError(f"审批请求不存在: {request_id}")

        principal = self.repository.principal(principal_id)
        outcome = store.decide(
            request_id,
            principal_id=principal_id,
            decision=decision,
            draft_version=draft_version,
            principal=principal,
            reason=reason,
        )
        updated = outcome.request

        if updated.status == "pending":
            # 串行审批：还有下一阶段，图保持中断态
            snapshot = await self._current_state(updated.thread_id) or {}
            return InvestigationResult(
                verdict=str(snapshot.get("verdict", "")),
                report=snapshot.get("report", {}) or {},
                thread_id=updated.thread_id,
                approval_status="pending_next_stage",
                approval_request=updated.as_dict(),
            )

        previous = store.previous_resume(request_id)
        if previous is not None:
            return self._result_from_snapshot(previous)

        approved_draft = (
            approved_draft_payload(updated) if updated.status == "approved" else None
        )
        if dry_run:
            return InvestigationResult(
                verdict="dry_run",
                report={"status": updated.status, "approved_draft": approved_draft},
                thread_id=updated.thread_id,
                approval_status=updated.status,
                approval_request=updated.as_dict(),
                approved_draft=approved_draft,
            )

        state = await self._ainvoke(
            Command(
                resume={
                    "status": updated.status,
                    "request_id": request_id,
                    "approved_draft": approved_draft,
                    "decided_by": principal_id,
                }
            ),
            thread_id=updated.thread_id,
        )
        result = await self._to_result(state, updated.thread_id)
        # F5：恢复结果的审批请求一律以台账为准，避免出现"报告引用不存在的请求"
        authoritative = store.get(request_id) or updated
        result = replace(
            result,
            approval_request=authoritative.as_dict(),
            approval_status=authoritative.status,
        )
        store.record_resume(
            request_id,
            updated.thread_id,
            {
                "verdict": result.verdict,
                "approval_status": result.approval_status,
                "approval_request": result.approval_request,
                "approved_draft": result.approved_draft,
                "report": result.report,
                "thread_id": result.thread_id,
            },
        )
        return result

    # ---------------- 内部 ----------------

    async def _ainvoke(
        self, payload: Any, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        if self.checkpointer is None:
            return await self._graph.ainvoke(payload)
        target = thread_id or "thread_unknown"
        return await self._graph.ainvoke(
            payload, {"configurable": {"thread_id": target}}
        )

    async def _pending_approval(self, thread_id: str) -> dict[str, Any] | None:
        """图被 `interrupt` 暂停时，节点写入的 state 尚未提交，需从 checkpoint 取。"""

        if self.checkpointer is None or self.approval_store is None:
            return None
        requests = [
            item
            for item in self.approval_store.find_by_thread(thread_id)
            if item.status == "pending"
        ]
        if not requests:
            return None
        snapshot = await self._graph.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )
        if snapshot is None or not snapshot.next:
            return None
        return requests[-1].as_dict()

    async def _current_state(self, thread_id: str) -> dict[str, Any] | None:
        if self.checkpointer is None:
            return None
        snapshot = await self._graph.aget_state(
            {"configurable": {"thread_id": thread_id}}
        )
        return dict(snapshot.values) if snapshot else None

    async def _to_result(
        self, state: dict[str, Any], thread_id: str
    ) -> InvestigationResult:
        report = state.get("report", {}) or {}
        context = state.get("context")
        run_id = getattr(context, "run_id", None)
        results = tuple(
            _latest_by_subtask(_scoped_by_run(state.get("results", []), run_id))
        )
        verdict = report.get("verdict", state.get("verdict", "insufficient"))
        approval_status = str(state.get("approval_status", ""))
        approval_request = state.get("approval_request")
        if approval_status == "ready":
            pending = await self._pending_approval(thread_id)
            if pending is not None:
                approval_status = "pending_approval"
                approval_request = approval_request or pending
        return InvestigationResult(
            verdict=verdict,
            report=report,
            results=results,
            # 报告里的 `failures` 只含**未解决**的失败；历史尝试见 `resolved_failures`
            failures=tuple(
                report["failures"]
                if "failures" in report
                else _scoped_by_run(state.get("failures", []), run_id)
            ),
            # 以报告中的去重结果为准：conflicts 是 append 通道，补查会重复
            conflicts=tuple(report.get("conflicts", [])),
            missing=tuple(sorted(set(state.get("missing", [])))),
            revision=int(state.get("revision", 0)),
            route=str(state.get("route", "")),
            warnings=tuple(state.get("warnings", [])),
            thread_id=thread_id,
            approval_status=approval_status,
            approval_request=approval_request,
            approved_draft=state.get("approved_draft"),
        )

    def _result_from_snapshot(self, snapshot: dict[str, Any]) -> InvestigationResult:
        return InvestigationResult(
            verdict=str(snapshot.get("verdict", "insufficient")),
            report=snapshot.get("report", {}) or {},
            thread_id=str(snapshot.get("thread_id", "")),
            approval_status=str(snapshot.get("approval_status", "")),
            approval_request=snapshot.get("approval_request"),
            approved_draft=snapshot.get("approved_draft"),
            warnings=("重复恢复：返回首次恢复结果，未再次执行节点",),
        )
