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
from ...agents.base.evidence import (
    domain_coverage,
    evidence_of_executions,
    minimum_evidence_reason,
    missing_domain_outcome,
    parse_error_details,
    partition_tool_executions,
    rejected_argument_detail,
    tool_domain,
)
from ...agents.base.facts import facts_of_executions, outputs_of_executions
from ...agents.base.conclusions import (
    build_fund_conclusion,
    check_fund_statements,
    render_fund_conclusion,
)
from ...agents.base.narrative import amounts_in_payload, check_answer_consistency
from ...agents.base.scope import TaskScope, scope_arguments_hook
from ...config.schema import AgentConfig
from ...llm.model_client import (
    ChatMessage,
    ChatModelClient,
    ToolSpecBuilder,
    describe_served_models,
    served_models_of,
)
from ...runtime.budget import Budget
from ...runtime.tool_loop import ToolLoopStopReason, run_tool_loop
from ...runtime.types import TraceLog
from ...tools.executor import ToolExecutor
from ...tools.registry import ToolRegistry

__all__ = ["SingleToolAgent"]

_STOP_REASON_ERRORS: dict[str, ErrorCode] = {
    ToolLoopStopReason.MODEL_ERROR: ErrorCode.MODEL_ERROR,
    ToolLoopStopReason.MODEL_TIMEOUT: ErrorCode.TIMEOUT,
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

    def _tool_domain(self, tool_name: str) -> str | None:
        """工具所属领域：命名空间优先，其次按注册表里声明的 required_permissions。"""

        permissions: Any = ()
        if self._tool_registry is not None and tool_name in self._tool_registry:
            permissions = self._tool_registry.get(tool_name).required_permissions
        return tool_domain(tool_name, permissions)

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

        # Task 031 / Z2：调用前被可信范围拒绝的调用不会产生 ToolExecution，
        # 但同样必须进入审计（不能因为"没执行"就从记录里消失）。
        argument_rejections: list[dict[str, Any]] = []
        scope_hook = scope_arguments_hook(self._tool_registry, scope)

        def _prepare_arguments(
            tool_name: str, arguments: dict[str, Any]
        ) -> tuple[dict[str, Any] | None, str | None]:
            prepared, reason = scope_hook(tool_name, arguments)
            if prepared is None:
                argument_rejections.append(rejected_argument_detail(tool_name, reason))
            return prepared, reason

        outcome = await run_tool_loop(
            client=self._model_client,
            messages=messages,
            tools=tools,
            executor=executor,
            context=context,
            agent_config=self.config,
            budget=self._budget if self._budget is not None else Budget(max_tool_calls=0),
            max_rounds=self.config.max_tool_rounds,
            prepare_arguments=_prepare_arguments,
        )

        error_code = _STOP_REASON_ERRORS.get(outcome.stop_reason)
        if error_code is not None:
            raise AgentError(
                f"工具调用循环未完成: {outcome.stop_reason}",
                code=error_code,
                # 与领域 Agent 一致：错误码仍报 TIMEOUT，但瞬时超时可重试；
                # 重试受同一个 Budget 约束并逐次记账。
                retryable=error_code in {ErrorCode.MODEL_ERROR, ErrorCode.TIMEOUT},
                details={
                    "stop_reason": outcome.stop_reason,
                    "rounds": outcome.rounds,
                    "warnings": list(outcome.warnings),
                    "last_answer": outcome.answer,
                },
            )

        # N2/Q2/Z2 纵深防御：只有"执行成功 + 输出仍属于本次目标"的调用才算取证。
        # 失败（参数非法/拒绝/超时/预算耗尽）与越界输出只保留审计：
        # 既不能进入 accepted，也不能进入 facts / evidence / 最终证据集。
        accepted, rejected_outputs, failed_executions = partition_tool_executions(
            outcome.tool_executions, scope
        )
        failed_tool_calls = [
            *argument_rejections,
            *parse_error_details(outcome.turns),
            *failed_executions,
        ]
        facts, per_tool = facts_of_executions(accepted)
        outputs = outputs_of_executions(accepted)
        evidence = evidence_of_executions(accepted)
        # N6：单 Agent 路径同样要核对"用户看到的金额"与"工具事实"，不能只看 facts。
        verified_amounts = amounts_in_payload(outputs)
        answer_check = check_answer_consistency(
            outcome.answer, facts, extra_amounts=verified_amounts
        )
        # Q3：结构化资金结论 + 字段级校验（与领域 Agent 共用同一实现）。
        fund_conclusion = build_fund_conclusion(facts)
        fund_check = check_fund_statements(outcome.answer, fund_conclusion)
        warnings = [*outcome.warnings, *rejected_outputs]
        if not answer_check.ok:
            warnings.append(
                "模型叙述与工具事实不一致，已标记为待人工核对: " + answer_check.detail
            )
        if fund_check.status == "mismatch":
            warnings.append(
                "资金结论与工具事实矛盾，已标记为待人工核对: " + fund_check.detail
            )
        # Q2/Z2：有目标的业务查询必须取到**本次目标**的事实；纯说明任务不受此限。
        # 判断依据是 facts 而不是 accepted：执行成功但产出不了事实的调用同样不算取证；
        # 反之，合法零结果（0 条工单 / 未检索到条款）会产生事实键，不会被误判。
        minimum = minimum_evidence_reason(scope, facts)
        # R1：facts 非空 ≠ 问题被回答了。存在失败调用时，按问题涉及的领域逐个核对：
        # 一部分领域没取到事实 → PARTIAL（告警写明缺哪个领域）；
        # 问题涉及的领域一个都没取到（只剩无关领域的事实）→ 与零事实同样处理。
        coverage = domain_coverage(question, per_tool, domain_of=self._tool_domain)
        missing_reason, missing_warning = (
            missing_domain_outcome(coverage, failed_tool_calls)
            if scope.requires_evidence
            else (None, None)
        )
        if minimum is None and missing_reason is not None:
            minimum = missing_reason
        if missing_warning is not None:
            warnings.append(missing_warning)
        if minimum is not None:
            raise AgentError(
                minimum,
                code=ErrorCode.INSUFFICIENT_EVIDENCE,
                retryable=False,
                details={
                    "task_scope": scope.describe(),
                    "tool_calls": len(outcome.tool_executions),
                    "failed_tool_calls": list(failed_tool_calls),
                    "rejected_outputs": list(rejected_outputs),
                    "domain_coverage": coverage,
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
                # Z2：只有 accepted 执行的证据才进入最终证据集
                # （Runtime 会从这里汇总 RuntimeResult.evidence）。
                "evidence": [item.model_dump(mode="json") for item in evidence],
                "failed_tool_calls": list(failed_tool_calls),
                "usage": outcome.usage.model_dump(mode="json"),
                "model": {
                    "provider": self._model_client.provider,
                    "name": self._model_client.model_name,
                    # R2：配置名之外，记录服务端实际声明的应答模型
                    **describe_served_models(
                        self._model_client.model_name, served_models_of(outcome.turns)
                    ),
                },
                "answer_check": answer_check.as_dict(),
                "verified_amounts": sorted(f"{item:.2f}" for item in verified_amounts),
                "task_scope": scope.describe(),
                "rejected_outputs": list(rejected_outputs),
                # R1：问题涉及的领域 / 取得事实的领域 / 缺失的领域（审计用）
                "domain_coverage": coverage,
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
