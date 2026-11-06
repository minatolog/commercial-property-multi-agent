"""Single Agent + Tools：单 Agent 基线的实现（Task 008）。

设计要点：

1. **依赖注入而非全局单例**：模型客户端、工具注册表、预算全部由调用方注入，
   因此同一份 Agent 代码可以在离线 Fake 与真实 Provider 之间切换，也能独立测试。
2. **不含任何业务计算**：Agent 只负责"要不要调用工具、调用哪个"，金额由工具与
   `Decimal` 决定。
3. **失败必须可见**：模型错误、预算耗尽、deadline 超时都返回明确的错误码，
   不把"没答完"包装成成功。
"""

from __future__ import annotations

import json
from typing import Any

from ...agents.base import AgentContext, AgentOutput, AgentRequest, BaseAgent
from ...agents.base.contracts import TokenUsage
from ...agents.base.errors import AgentError, ErrorCode
from ...agents.base.facts import facts_of_executions, outputs_of_executions
from ...agents.base.conclusions import (
    build_fund_conclusion,
    check_fund_statements,
    render_fund_conclusion,
)
from ...agents.base.narrative import amounts_in_payload, check_answer_consistency
from ...agents.base.scope import TaskScope, scope_arguments_hook
from ...config.schema import AgentConfig
from ...llm.model_client import ChatMessage, ChatModelClient, ToolSpecBuilder
from ...runtime.budget import Budget
from ...runtime.tool_loop import ToolLoopStopReason, run_tool_loop
from ...runtime.types import TraceLog
from ...tools.executor import ToolExecutor
from ...tools.registry import ToolRegistry

__all__ = ["SingleToolAgent"]

_STOP_REASON_ERRORS: dict[str, ErrorCode] = {
    ToolLoopStopReason.MODEL_ERROR: ErrorCode.MODEL_ERROR,
    ToolLoopStopReason.BUDGET_EXHAUSTED: ErrorCode.BUDGET_EXHAUSTED,
    ToolLoopStopReason.DEADLINE_EXCEEDED: ErrorCode.DEADLINE_EXCEEDED,
}


class SingleToolAgent(BaseAgent):
    name = "single"
    version = "1.0.0"
    description = "单 Agent + 受控工具调用（基线实现）"
    capabilities = frozenset({"single.investigate"})

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
        # 必须与 Runtime 共享同一个 TraceLog，否则 Runtime 看不到本次工具调用，
        # 结果会出现"调用了工具但 tool_traces 为空"的假象。
        self._trace_log = trace_log if trace_log is not None else TraceLog()

    @property
    def model_client(self) -> ChatModelClient | None:
        return self._model_client

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        if self._model_client is None:
            raise AgentError(
                "未注入模型客户端；SingleToolAgent 需要 model_client 才能执行",
                code=ErrorCode.INVALID_CONTEXT,
                retryable=False,
            )
        if self._tool_registry is None:
            raise AgentError(
                "未注入工具注册表；SingleToolAgent 需要 tool_registry 才能执行",
                code=ErrorCode.INVALID_CONTEXT,
                retryable=False,
            )

        question = _question_of(request.payload)
        tools = ToolSpecBuilder.build(
            self._tool_registry,
            allowed_tools=self.config.allowed_tools,
            permissions=context.permissions,
        )
        if not tools:
            raise AgentError(
                "当前 Agent 没有任何可用工具；检查 allowed_tools 与调用方权限",
                code=ErrorCode.PERMISSION_DENIED,
                retryable=False,
                details={"allowed_tools": list(self.config.allowed_tools)},
            )

        executor = ToolExecutor(
            self._tool_registry,
            self._budget if self._budget is not None else Budget(max_tool_calls=0),
            trace_log=self._trace_log,
        )
        # Task 024 / Q2：单 Agent 与领域 Agent 共用同一份可信范围策略。
        # 目标/筛选条件由 payload 决定，在工具边界注入或拒绝；不再让模型自己声明目标。
        scope = TaskScope.from_payload(request.payload)
        messages = (
            ChatMessage(role="system", content=self.prompt_text),
            ChatMessage(
                role="user",
                content=json.dumps(
                    {
                        "question": question,
                        "lease_id": scope.lease_id,
                        "unit_id": scope.unit_id,
                        "filters": dict(scope.filters),
                        "mode": scope.mode,
                        "instruction": "只使用给定工具取数；金额与日期必须来自工具输出，不要自行计算",
                    },
                    ensure_ascii=False,
                ),
            ),
        )

        outcome = await run_tool_loop(
            client=self._model_client,
            messages=messages,
            tools=tools,
            executor=executor,
            context=context,
            agent_config=self.config,
            budget=self._budget if self._budget is not None else Budget(max_tool_calls=0),
            max_rounds=self.config.max_tool_rounds,
            prepare_arguments=scope_arguments_hook(self._tool_registry, scope),
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

        # N2/Q2 纵深防御：工具返回了别的实体的数据时不得并入事实。
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
        # N6：单 Agent 路径同样要核对"用户看到的金额"与"工具事实"，不能只看 facts。
        verified_amounts = amounts_in_payload(outputs)
        answer_check = check_answer_consistency(
            outcome.answer, facts, extra_amounts=verified_amounts
        )
        # Q3：结构化资金结论 + 字段级校验（与领域 Agent 共用同一实现）。
        fund_conclusion = build_fund_conclusion(facts)
        fund_check = check_fund_statements(outcome.answer, fund_conclusion)
        warnings = [*outcome.warnings, *rejected]
        if not answer_check.ok:
            warnings.append(
                "模型叙述与工具事实不一致，已标记为待人工核对: " + answer_check.detail
            )
        if fund_check.status == "mismatch":
            warnings.append(
                "资金结论与工具事实矛盾，已标记为待人工核对: " + fund_check.detail
            )
        # Q2：有目标的业务查询必须取到**本次目标**的数据；纯说明任务不受此限。
        if scope.requires_evidence and not accepted:
            raise AgentError(
                "这是有目标的业务查询，但没有取得任何属于本次目标的工具事实",
                code=ErrorCode.INSUFFICIENT_EVIDENCE,
                retryable=False,
                details={
                    "task_scope": scope.describe(),
                    "tool_calls": len(outcome.tool_executions),
                    "rejected_outputs": rejected,
                    "warnings": warnings,
                },
            )
        return AgentOutput(
            data={
                "answer": outcome.answer,
                "stop_reason": outcome.stop_reason,
                "rounds": outcome.rounds,
                # 事实来自工具输出（Task 018）：B 基线接入真实模型后仍可被同一评分器判定
                "facts": facts,
                "tool_facts": per_tool,
                "tool_outputs": outputs,
                "tool_calls": [
                    {
                        "call_id": execution.call_id,
                        "tool": execution.tool_name,
                        "status": execution.status,
                        "attempts": execution.attempts,
                    }
                    for execution in outcome.tool_executions
                ],
                "evidence": [
                    item.model_dump(mode="json") for item in outcome.evidence
                ],
                "usage": outcome.usage.model_dump(mode="json"),
                "model": {
                    "provider": self._model_client.provider,
                    "name": self._model_client.model_name,
                },
                "answer_check": answer_check.as_dict(),
                "verified_amounts": sorted(f"{item:.2f}" for item in verified_amounts),
                "task_scope": scope.describe(),
                "rejected_outputs": rejected,
                # 结构化资金结论与"用户可见金额"：由可信字段渲染，不经模型
                "fund_conclusion": (
                    fund_conclusion.as_dict() if fund_conclusion is not None else None
                ),
                "authoritative_answer": render_fund_conclusion(fund_conclusion),
                "fund_check": fund_check.as_dict(),
            },
            warnings=tuple(warnings),
            token_usage=_usage_or_none(outcome.usage),
        )


def _question_of(payload: dict[str, Any]) -> str:
    raw = payload.get("question") or payload.get("query") or ""
    question = str(raw).strip()
    if not question:
        raise AgentError(
            "payload 缺少 question",
            code=ErrorCode.INVALID_REQUEST,
            retryable=False,
        )
    return question


def _usage_or_none(usage: TokenUsage) -> TokenUsage | None:
    return usage if usage.total_tokens or usage.prompt_tokens or usage.completion_tokens else None
