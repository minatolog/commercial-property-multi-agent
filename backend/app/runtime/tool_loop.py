"""有限轮次工具调用循环（单 Agent + Tools 基线的最小实现）。

职责边界：

- 只负责"问模型 → 执行工具 → 把结果回传 → 直到给出最终答案"这一步；
- 不做业务计算、不做权限判断（权限在 ToolExecutor）、不做图编排（Task 009）；
- 一切上限都是显式的：轮次、预算、deadline、单次工具超时。

停止原因必须可见，禁止把"没答完"伪装成成功。
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from ..agents.base.contracts import AgentContext, TokenUsage, utcnow
from ..agents.base.errors import AgentError, ErrorCode
from ..config.schema import AgentConfig
from ..llm.model_client import ChatMessage, ChatModelClient, ModelTurn, ToolSpec
from ..tools.executor import ToolExecutor
from .budget import Budget
from .types import Evidence, ToolExecution

__all__ = ["ToolLoopOutcome", "ToolLoopStopReason", "run_tool_loop"]

#: 物理模型请求的全局序号：保证每次真实发送请求都有唯一预算 ID。
#: 进程内单调递增即可——预算只在单进程内有意义（P0 单进程 Runtime）。
_REQUEST_SEQ = itertools.count(1)


class ToolLoopStopReason:
    FINAL_ANSWER = "final_answer"
    MAX_ROUNDS = "max_rounds"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    MODEL_ERROR = "model_error"


@dataclass(frozen=True)
class ToolLoopOutcome:
    answer: str
    stop_reason: str
    turns: tuple[ModelTurn, ...] = ()
    tool_executions: tuple[ToolExecution, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    usage: TokenUsage = field(default_factory=TokenUsage)
    warnings: tuple[str, ...] = ()
    rounds: int = 0

    @property
    def completed(self) -> bool:
        return self.stop_reason == ToolLoopStopReason.FINAL_ANSWER


async def run_tool_loop(
    *,
    client: ChatModelClient,
    messages: Sequence[ChatMessage],
    tools: Sequence[ToolSpec],
    executor: ToolExecutor,
    context: AgentContext,
    agent_config: AgentConfig,
    budget: Budget,
    max_rounds: int,
    prepare_arguments: Callable[
        [str, dict[str, Any]], tuple[dict[str, Any] | None, str | None]
    ]
    | None = None,
) -> ToolLoopOutcome:
    """执行有界工具循环。

    `messages` 不会被就地修改（返回的新消息只存在于本次循环）。

    `prepare_arguments(tool_name, args)` 是调用前的**可信约束**钩子（Task 021）：
    返回 `(最终参数, None)` 表示可执行；返回 `(None, 原因)` 表示拒绝该次调用，
    原因会作为工具错误回传给模型让它自行纠正。目标/筛选条件因此由装配层决定，
    而不是由模型自觉遵守。
    """

    conversation: list[ChatMessage] = list(messages)
    turns: list[ModelTurn] = []
    executions: list[ToolExecution] = []
    evidence: list[Evidence] = []
    warnings: list[str] = []
    usage = TokenUsage()

    for round_index in range(1, max_rounds + 1):
        if _deadline_passed(context):
            return _outcome(
                answer=_latest_text(turns),
                stop_reason=ToolLoopStopReason.DEADLINE_EXCEEDED,
                turns=turns,
                executions=executions,
                evidence=evidence,
                usage=usage,
                warnings=tuple(warnings),
                rounds=round_index - 1,
            )

        # 预算按"**一次物理模型请求**"计数（Task 021 / N1）：
        # 加上单调递增的请求序号，绝不能让 BaseAgent 的重试或图补查复用同一个 ID——
        # 复用会让新的真实请求被当成"已结算"，账本少记、上限失效。
        agent_scope = context.subtask_id or "root"
        request_seq = next(_REQUEST_SEQ)
        model_call_id = (
            f"mc_{context.run_id or 'norun'}_{agent_scope}_{round_index}_{request_seq}"
        )
        try:
            await budget.reserve_model_call(model_call_id)
        except AgentError as exc:
            warnings.append(f"模型调用预算不足: {exc.code}")
            return _outcome(
                answer=_latest_text(turns),
                stop_reason=ToolLoopStopReason.BUDGET_EXHAUSTED,
                turns=turns,
                executions=executions,
                evidence=evidence,
                usage=usage,
                warnings=tuple(warnings),
                rounds=round_index - 1,
            )

        try:
            turn = await client.complete(conversation, tools)
        except AgentError as exc:
            await budget.settle(model_call_id)
            warnings.append(f"模型调用失败: {exc.code}: {exc.message}")
            return _outcome(
                answer=_latest_text(turns),
                stop_reason=ToolLoopStopReason.MODEL_ERROR,
                turns=turns,
                executions=executions,
                evidence=evidence,
                usage=usage,
                warnings=tuple(warnings),
                rounds=round_index,
            )
        except Exception as exc:  # 客户端实现缺陷也不能让整条工作流崩掉
            await budget.settle(model_call_id)
            warnings.append(f"模型调用异常: {type(exc).__name__}: {exc}")
            return _outcome(
                answer=_latest_text(turns),
                stop_reason=ToolLoopStopReason.MODEL_ERROR,
                turns=turns,
                executions=executions,
                evidence=evidence,
                usage=usage,
                warnings=tuple(warnings),
                rounds=round_index,
            )
        await budget.settle(model_call_id)

        turns.append(turn)
        usage = _add_usage(usage, turn.usage)
        if turn.usage is not None and turn.usage.total_tokens:
            token_id = f"{model_call_id}_tok"
            try:
                await budget.reserve_tokens(token_id, turn.usage.total_tokens)
                await budget.settle(token_id)
            except AgentError:
                # 预留失败说明超限了，但这次响应**已经真实产生** token：
                # 必须如实记账（超限部分单独标记），否则账本低估真实成本。
                await budget.record_unbudgeted_tokens(turn.usage.total_tokens)
                warnings.append("token 预算已耗尽，停止继续调用模型")
                return _outcome(
                    answer=turn.text or _latest_text(turns),
                    stop_reason=ToolLoopStopReason.BUDGET_EXHAUSTED,
                    turns=turns,
                    executions=executions,
                    evidence=evidence,
                    usage=usage,
                    warnings=tuple(warnings),
                    rounds=round_index,
                )

        if not turn.tool_calls:
            # Task 016（F6）：没有任何有效调用时，必须先排除"模型想调工具但调用非法"。
            # 否则空答案会被标成 success / final_answer，等于伪造一次成功回答。
            if turn.invalid_tool_calls:
                detail = "; ".join(
                    f"{item.name or '<无工具名>'}: {item.error}"
                    for item in turn.invalid_tool_calls
                )
                warnings.append(f"模型返回非法工具调用: {detail}")
                return _outcome(
                    answer=turn.text,
                    stop_reason=ToolLoopStopReason.MODEL_ERROR,
                    turns=turns,
                    executions=executions,
                    evidence=evidence,
                    usage=usage,
                    warnings=tuple(warnings),
                    rounds=round_index,
                )
            truncated = (turn.finish_reason or "").lower() in {"length", "max_tokens"}
            if truncated:
                warnings.append(
                    f"模型输出被截断（finish_reason={turn.finish_reason}），不能视为完整回答"
                )
                return _outcome(
                    answer=turn.text,
                    stop_reason=ToolLoopStopReason.MODEL_ERROR,
                    turns=turns,
                    executions=executions,
                    evidence=evidence,
                    usage=usage,
                    warnings=tuple(warnings),
                    rounds=round_index,
                )
            if not turn.text.strip():
                # Task 017（R5）：有工具证据不等于完成了用户问答。只有"确实产出了
                # 面向用户的文本"才算 final_answer；空文本一律按未完成处理，
                # 避免空答案 + 13 条证据被标成 success。
                warnings.append(
                    "模型最终回合没有给出任何回答文本"
                    + ("（已执行工具调用，但没有生成结论）" if executions else "")
                )
                return _outcome(
                    answer="",
                    stop_reason=ToolLoopStopReason.MODEL_ERROR,
                    turns=turns,
                    executions=executions,
                    evidence=evidence,
                    usage=usage,
                    warnings=tuple(warnings),
                    rounds=round_index,
                )
            return _outcome(
                answer=turn.text,
                stop_reason=ToolLoopStopReason.FINAL_ANSWER,
                turns=turns,
                executions=executions,
                evidence=evidence,
                usage=usage,
                warnings=tuple(warnings),
                rounds=round_index,
            )

        conversation.append(
            ChatMessage(role="assistant", content=turn.text, tool_calls=turn.tool_calls)
        )

        for call in turn.tool_calls:
            if call.parse_error is not None:
                # 参数不合法不是异常，而是一次可被模型纠正的失败反馈
                warnings.append(f"工具 {call.name} 参数不合法: {call.parse_error}")
                conversation.append(
                    ChatMessage(
                        role="tool",
                        content=_tool_error_content(
                            call.call_id, ErrorCode.INVALID_TOOL_ARGUMENTS.value, call.parse_error
                        ),
                        tool_call_id=call.call_id,
                    )
                )
                continue

            # 模型看到的是 provider 合法名（`lease__lookup`），执行要用内部名（`lease.lookup`）。
            # 也接受内部名，便于脚本化模型与历史测试直接用原名字。
            spec = _spec_for(tools, call.name)
            tool_name = spec.tool_name if spec is not None else call.name
            arguments = dict(call.arguments)
            if prepare_arguments is not None:
                prepared, reason = prepare_arguments(tool_name, arguments)
                if prepared is None:
                    # 越界参数不执行：把原因回传，让模型在下一轮自行纠正
                    warnings.append(f"工具 {call.name} 调用被拒绝: {reason}")
                    conversation.append(
                        ChatMessage(
                            role="tool",
                            content=_tool_error_content(
                                call.call_id,
                                ErrorCode.INVALID_TOOL_ARGUMENTS.value,
                                str(reason),
                            ),
                            tool_call_id=call.call_id,
                        )
                    )
                    continue
                arguments = prepared
            execution = await executor.execute(
                tool_name,
                arguments,
                context=context,
                agent_config=agent_config,
            )
            executions.append(execution)
            evidence.extend(execution.evidence)
            conversation.append(
                ChatMessage(
                    role="tool",
                    content=_tool_result_content(execution),
                    tool_call_id=call.call_id,
                )
            )

    return _outcome(
        answer=_latest_text(turns),
        stop_reason=ToolLoopStopReason.MAX_ROUNDS,
        turns=turns,
        executions=executions,
        evidence=evidence,
        usage=usage,
        warnings=tuple([*warnings, f"达到最大轮次 {max_rounds}，未得到最终答案"]),
        rounds=max_rounds,
    )


def _spec_for(tools: Sequence[ToolSpec], name: str) -> ToolSpec | None:
    """按暴露名或内部名查工具声明（两者都接受，调用方无需关心映射方向）。"""

    for spec in tools:
        if spec.name == name or spec.tool_name == name:
            return spec
    return None


def _deadline_passed(context: AgentContext) -> bool:
    return context.deadline_at is not None and utcnow() >= context.deadline_at


def _latest_text(turns: Sequence[ModelTurn]) -> str:
    for turn in reversed(turns):
        if turn.text.strip():
            return turn.text
    return ""


def _add_usage(left: TokenUsage, right: TokenUsage | None) -> TokenUsage:
    if right is None:
        return left
    return TokenUsage(
        prompt_tokens=left.prompt_tokens + right.prompt_tokens,
        completion_tokens=left.completion_tokens + right.completion_tokens,
        total_tokens=left.total_tokens + right.total_tokens,
    )


def _tool_result_content(execution: ToolExecution) -> str:
    if execution.ok:
        payload = {
            "status": "ok",
            "tool": execution.tool_name,
            "call_id": execution.call_id,
            "data": execution.data,
            "evidence_ids": [item.evidence_id for item in execution.evidence],
        }
    else:
        error = execution.error
        payload = {
            "status": "error",
            "tool": execution.tool_name,
            "call_id": execution.call_id,
            "error_code": error.code.value if error is not None else ErrorCode.INTERNAL_ERROR.value,
            "message": error.message if error is not None else "",
        }
    import json

    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _tool_error_content(call_id: str, code: str, message: str) -> str:
    import json

    return json.dumps(
        {"status": "error", "call_id": call_id, "error_code": code, "message": message},
        ensure_ascii=False,
        sort_keys=True,
    )


def _outcome(
    *,
    answer: str,
    stop_reason: str,
    turns: Sequence[ModelTurn],
    executions: Sequence[ToolExecution],
    evidence: Sequence[Evidence],
    usage: TokenUsage,
    warnings: tuple[str, ...],
    rounds: int,
) -> ToolLoopOutcome:
    return ToolLoopOutcome(
        answer=answer,
        stop_reason=stop_reason,
        turns=tuple(turns),
        tool_executions=tuple(executions),
        evidence=tuple(evidence),
        usage=usage,
        warnings=warnings,
        rounds=rounds,
    )
