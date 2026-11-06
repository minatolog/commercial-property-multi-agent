"""由 **LLM 决定调什么工具** 的领域 Agent 基类（Task 018）。

与 `ToolBackedAgent` 的分工：

| | `ToolBackedAgent`（默认） | `LLMToolAgent`（本模块） |
|---|---|---|
| 谁决定调用哪个工具 | 代码里的固定映射 | 模型（受 `allowed_tools` + 权限白名单约束） |
| 事实来源 | 工具输出 | **仍然是**工具输出（`facts_from_tool_output`） |
| 可复现性 | 完全确定 | 取决于模型；离线用 `FakeChatModelClient` 脚本化 |

三条硬约束：

1. **金额不由模型生成**：`facts` 一律从工具结构化输出提取，模型只负责选工具与组织叙述；
2. **权限与预算不放松**：仍然走 `ToolExecutor`（六道闸）与共享 `Budget`；
3. **失败必须可见**：模型非法调用、空回答、预算耗尽都映射成明确错误码。

这样"换成真实模型"只是换一个 `model_client`，输入输出契约与评测口径都不变。
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

from .base_agent import BaseAgent
from .contracts import AgentContext, AgentOutput, AgentRequest, TokenUsage
from .errors import AgentError, ErrorCode
from .conclusions import (
    build_fund_conclusion,
    check_fund_statements,
    render_fund_conclusion,
)
from .evidence import check_capability_output
from .facts import facts_of_executions, outputs_of_executions
from .narrative import amounts_in_payload, check_answer_consistency
from .scope import TaskScope, scope_arguments_hook
from ...config.schema import AgentConfig
from ...llm.model_client import ChatMessage, ChatModelClient, ToolSpecBuilder
from ...runtime.budget import Budget
from ...runtime.tool_loop import ToolLoopStopReason, run_tool_loop
from ...runtime.types import TraceLog, ToolExecution
from ...tools.executor import ToolExecutor
from ...tools.registry import ToolRegistry

__all__ = ["LLMToolAgent"]

_STOP_REASON_ERRORS: dict[str, ErrorCode] = {
    ToolLoopStopReason.MODEL_ERROR: ErrorCode.MODEL_ERROR,
    ToolLoopStopReason.BUDGET_EXHAUSTED: ErrorCode.BUDGET_EXHAUSTED,
    ToolLoopStopReason.DEADLINE_EXCEEDED: ErrorCode.DEADLINE_EXCEEDED,
}


class LLMToolAgent(BaseAgent):
    """子类只需声明身份与"这个能力允许哪些工具前缀"。"""

    #: 该能力只能看到这些工具前缀（例如 `billing.`），空表示不额外限制
    tool_prefixes: ClassVar[tuple[str, ...]] = ()

    def __init__(
        self,
        config: AgentConfig,
        *,
        model_client: ChatModelClient | None = None,
        tool_registry: ToolRegistry | None = None,
        budget: Budget | None = None,
        trace_log: TraceLog | None = None,
    ) -> None:
        super().__init__(config)
        self._model_client = model_client
        self._tool_registry = tool_registry
        self._budget = budget
        self._trace_log = trace_log if trace_log is not None else TraceLog()

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        if self._model_client is None:
            raise AgentError(
                f"{self.name} 的 LLM 引擎需要注入 model_client",
                code=ErrorCode.INVALID_CONTEXT,
                retryable=False,
            )
        if self._tool_registry is None:
            raise AgentError(
                f"{self.name} 的 LLM 引擎需要注入 tool_registry",
                code=ErrorCode.INVALID_CONTEXT,
                retryable=False,
            )

        allowed = self._scoped_tools()
        specs = ToolSpecBuilder.build(
            self._tool_registry,
            allowed_tools=allowed,
            permissions=context.permissions,
        )
        if not specs:
            raise AgentError(
                "当前 Agent 没有任何可用工具；检查 allowed_tools 与调用方权限",
                code=ErrorCode.PERMISSION_DENIED,
                retryable=False,
                details={"allowed_tools": list(allowed)},
            )

        budget = self._budget if self._budget is not None else Budget(max_tool_calls=0)
        executor = ToolExecutor(self._tool_registry, budget, trace_log=self._trace_log)
        scope = self._task_scope(request)
        messages = (
            ChatMessage(role="system", content=self.prompt_text),
            ChatMessage(
                role="user",
                content=json.dumps(
                    {
                        "capability": request.capability,
                        "question": scope.question
                        or request.payload.get("question")
                        or request.payload.get("query")
                        or "",
                        "lease_id": scope.lease_id,
                        "unit_id": scope.unit_id,
                        "filters": dict(scope.filters),
                        "instruction": "只使用给定工具取数；金额与日期必须来自工具输出，不要自行计算",
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        outcome = await run_tool_loop(
            client=self._model_client,
            messages=messages,
            tools=specs,
            executor=executor,
            context=context,
            agent_config=self.config,
            budget=budget,
            max_rounds=self.config.max_tool_rounds,
            prepare_arguments=lambda tool_name, args: self._scope_arguments(
                scope, tool_name, args
            ),
        )

        error_code = _STOP_REASON_ERRORS.get(outcome.stop_reason)
        if error_code is not None:
            raise AgentError(
                f"工具调用循环未完成: {outcome.stop_reason}",
                code=error_code,
                retryable=error_code is ErrorCode.MODEL_ERROR,
                details={
                    "stop_reason": outcome.stop_reason,
                    "rounds": outcome.rounds,
                    "warnings": list(outcome.warnings),
                    "last_answer": outcome.answer,
                },
            )

        # 纵深防御（N2）：即使工具被绕过、或工具自身返回了别的实体，也不能把它
        # 绑进当前报告。只对"目标一致"的执行结果做后续事实提取。
        accepted: list[Any] = []
        rejected: list[str] = []
        for execution in outcome.tool_executions:
            reason = scope.accepts_output(execution.tool_name, execution.data or {})
            if reason is None:
                accepted.append(execution)
            else:
                rejected.append(reason)
        facts, per_tool = facts_of_executions(tuple(accepted))
        outputs = outputs_of_executions(tuple(accepted))
        # 统一输出契约：领域视图（lease/billing/property 字段）+ LLM 附加信息。
        # 图与报告只依赖这份领域视图，因此换模型不会改变下游语义。
        view = _domain_view(request.capability, outputs, outcome.evidence)
        # N4：没有取到事实就不算完成。模型可以"看起来很确定"，但契约只认工具字段。
        violations = check_capability_output(request.capability, view)
        if violations:
            raise AgentError(
                "模型未取得该能力要求的事实，本次子任务不能算完成",
                code=ErrorCode.INSUFFICIENT_EVIDENCE,
                retryable=False,
                details={
                    "capability": request.capability,
                    "violations": violations,
                    "tool_calls": len(outcome.tool_executions),
                    "rejected_outputs": list(rejected),
                    "warnings": list(outcome.warnings),
                    "answer_chars": len(outcome.answer or ""),
                },
            )
        # N6：内部事实正确 ≠ 用户看到的金额正确。
        # 可信金额集合 = 事实契约里的金额 + 工具输出里出现过的金额（账单明细等）。
        verified_amounts = amounts_in_payload(outputs)
        answer_check = check_answer_consistency(
            outcome.answer, facts, extra_amounts=verified_amounts
        )
        # Q3：资金结论结构化 + 字段级校验（应收/已收/未收不能被写反）。
        fund_conclusion = build_fund_conclusion(facts)
        fund_check = check_fund_statements(outcome.answer, fund_conclusion)
        warnings = list(outcome.warnings) + list(rejected)
        if not answer_check.ok:
            warnings.append(
                "模型叙述与工具事实不一致，已标记为待人工核对: " + answer_check.detail
            )
        if fund_check.status == "mismatch":
            warnings.append(
                "资金结论与工具事实矛盾，已标记为待人工核对: " + fund_check.detail
            )
        return AgentOutput(
            data={
                **view,
                "capability": request.capability,
                "engine": "llm",
                "answer": outcome.answer,
                "facts": facts,
                "tool_facts": per_tool,
                "tool_calls": [
                    {
                        "call_id": execution.call_id,
                        "tool": execution.tool_name,
                        "status": execution.status,
                        "attempts": execution.attempts,
                    }
                    for execution in outcome.tool_executions
                ],
                "evidence": [item.model_dump(mode="json") for item in outcome.evidence],
                "usage": outcome.usage.model_dump(mode="json"),
                "model": {
                    "provider": self._model_client.provider,
                    "name": self._model_client.model_name,
                },
                "task_scope": scope.describe(),
                "rejected_outputs": rejected,
                "answer_check": answer_check.as_dict(),
                "verified_amounts": sorted(f"{item:.2f}" for item in verified_amounts),
                # 结构化资金结论与"用户可见金额"：金额由可信字段渲染，不经模型
                "fund_conclusion": (
                    fund_conclusion.as_dict() if fund_conclusion is not None else None
                ),
                "authoritative_answer": render_fund_conclusion(fund_conclusion),
                "fund_check": fund_check.as_dict(),
            },
            warnings=tuple(warnings),
            token_usage=_usage_or_none(outcome.usage),
        )

    def _scoped_tools(self) -> tuple[str, ...]:
        allowed = self.config.allowed_tools
        if not self.tool_prefixes:
            return tuple(allowed)
        return tuple(
            name for name in allowed if name.startswith(self.tool_prefixes)
        )

    # ---------------- 可信约束（Task 021 / Task 024 Q2） ----------------

    @staticmethod
    def _task_scope(request: AgentRequest) -> TaskScope:
        """从**可信 payload**（planner 生成）构造本次任务范围。模型无法修改它。"""

        return TaskScope.from_payload(request.payload)

    def _scope_arguments(
        self, scope: TaskScope, tool_name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        if self._tool_registry is None:
            return dict(arguments), None
        return scope_arguments_hook(self._tool_registry, scope)(tool_name, arguments)


def _domain_view(
    capability: str,
    outputs: dict[str, dict[str, Any]],
    evidence: tuple[Any, ...],
) -> dict[str, Any]:
    """把工具输出映射成与确定性 Agent **相同**的领域视图。

    为什么必须有这一步：图和报告（核验、冲突、缺失、finding）读的是
    `output["lease"]` / `output["rent_variance_total"]` 这类字段。如果 LLM 引擎
    只输出 `facts`，换模型就等于换了输出契约，冲突检测会静默失效。
    """

    if capability.startswith("billing."):
        for name in ("billing.statement.read", "billing.arrears.calculate"):
            if name in outputs:
                return dict(outputs[name])
        return {}

    if capability in {"lease.query", "lease.renewal_evaluation"}:
        data = outputs.get("lease.lookup", {})
        search = outputs.get("document.search", {})
        results = search.get("results") or []
        clauses = [
            {
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "document_version": item.get("document_version"),
                "document_scope": item.get("document_scope", "unknown"),
                "document_status": item.get("document_status", "signed"),
                "page": item.get("page"),
                "clause_id": item.get("clause_id"),
                "excerpt": item.get("excerpt"),
            }
            for item in results
        ]
        # 与确定性 `LeaseAgent` 的 `lease` 子集保持一致（图与报告读这些字段）
        lease = {
            key: data.get(key)
            for key in (
                "lease_id",
                "lease_no",
                "project_id",
                "unit_id",
                "unit_code",
                "tenant_id",
                "currency",
                "deposit_amount",
                "start_date",
                "end_date",
                "status",
            )
        }
        return {
            "lease": lease,
            "rules": data.get("rules", []),
            "documents": data.get("document_ids", []),
            "signed_documents": data.get("signed_document_ids", []),
            "draft_documents": data.get("draft_document_ids", []),
            "missing_documents": data.get("missing_document_ids", []),
            "clauses": clauses,
            "clause_evidence": [
                item.model_dump(mode="json")
                for item in evidence
                if getattr(item, "kind", None) == "document_clause"
            ],
        }

    if capability == "property.work_orders":
        data = dict(outputs.get("property.work_orders.read", {}))
        open_orders = [
            item for item in data.get("work_orders", []) if item.get("status") != "closed"
        ]
        return {
            **data,
            "open_work_order_ids": [item["work_order_id"] for item in open_orders],
            "open_work_order_count": len(open_orders),
        }

    return {}


def _usage_or_none(usage: TokenUsage) -> TokenUsage | None:
    return (
        usage
        if usage.total_tokens or usage.prompt_tokens or usage.completion_tokens
        else None
    )
