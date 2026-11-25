"""用 LangChain Agent 执行领域内模型与工具循环。

LangChain 调度模型和工具节点。项目负责可信目标、预算、取证及对外结果契约。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import StructuredTool
from langgraph.prebuilt.tool_node import ToolCallRequest
from pydantic import Field

from ..agents.base.contracts import AgentContext, TokenUsage, utcnow
from ..agents.base.errors import AgentError, ErrorCode
from ..config.schema import AgentConfig
from ..llm.langchain_client import to_langchain_message
from ..llm.model_client import ChatMessage, ChatModelClient, ModelToolCall, ModelTurn, ToolSpec
from ..tools.executor import ToolExecutor
from .budget import Budget
from .types import Evidence, ToolExecution

ArgumentPolicy = Callable[
    [str, dict[str, Any]], tuple[dict[str, Any] | None, str | None]
]


class ToolLoopStopReason:
    FINAL_ANSWER = "final_answer"
    MAX_ROUNDS = "max_rounds"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    MODEL_TIMEOUT = "model_timeout"
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


class _AgentStopped(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class _ProjectChatModel(BaseChatModel):
    """Expose the project's real and scripted clients as a LangChain chat model."""

    client: Any = Field(exclude=True, repr=False)
    specs: tuple[ToolSpec, ...]
    tool_aliases: dict[str, str]
    turns: list[ModelTurn] = Field(default_factory=list, exclude=True)

    @property
    def _llm_type(self) -> str:
        return self.client.provider

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> BaseChatModel:
        if {tool.name for tool in tools} != {spec.name for spec in self.specs}:
            raise ValueError("LangChain 工具集与执行授权不一致")
        return self

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        raise NotImplementedError("项目模型客户端只支持异步调用")

    async def _agenerate(
        self, messages: list[BaseMessage], **kwargs: Any
    ) -> ChatResult:
        turn = await self.client.complete(
            [_to_project_message(message) for message in messages], self.specs
        )
        self.turns.append(turn)
        response = AIMessage(
            content=turn.text,
            usage_metadata={
                "input_tokens": turn.usage.prompt_tokens,
                "output_tokens": turn.usage.completion_tokens,
                "total_tokens": turn.usage.total_tokens,
            } if turn.usage else None,
            tool_calls=[
                {
                    "id": call.call_id,
                    "name": self.tool_aliases.get(call.name, call.name),
                    "args": call.arguments,
                }
                for call in turn.tool_calls
            ],
        )
        return ChatResult(generations=[ChatGeneration(message=response)])


def _to_project_message(message: BaseMessage) -> ChatMessage:
    if isinstance(message, AIMessage):
        return ChatMessage(
            role="assistant",
            content=message.text,
            tool_calls=tuple(
                ModelToolCall(
                    call_id=call["id"],
                    name=call["name"],
                    arguments=call["args"],
                    arguments_json=_json(call["args"]),
                )
                for call in message.tool_calls
            ),
        )
    if isinstance(message, ToolMessage):
        return ChatMessage(
            role="tool", content=message.text, tool_call_id=message.tool_call_id
        )
    if isinstance(message, SystemMessage):
        return ChatMessage(role="system", content=message.text)
    if isinstance(message, HumanMessage):
        return ChatMessage(role="user", content=message.text)
    raise TypeError(f"不支持的模型消息类型: {type(message).__name__}")


class _Governance(AgentMiddleware):
    """将一次标准 Agent 调用接入本地预算与受控工具执行。"""

    def __init__(
        self,
        model: _ProjectChatModel,
        executor: ToolExecutor,
        context: AgentContext,
        agent_config: AgentConfig | None,
        budget: Budget,
        max_rounds: int,
        prepare_arguments: ArgumentPolicy | None,
    ) -> None:
        self.model = model
        self.executor = executor
        self.context = context
        self.agent_config = agent_config
        self.budget = budget
        self.max_rounds = max_rounds
        self.prepare_arguments = prepare_arguments
        self.executions: list[ToolExecution] = []
        self.warnings: list[str] = []
        self.rounds = 0
        # 保持同一子任务的工具顺序和旧路径的预算语义。
        self.tool_lock = asyncio.Lock()

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Any],
    ) -> ModelResponse:
        deadline = self.context.deadline_at
        remaining = (deadline - utcnow()).total_seconds() if deadline else None
        if remaining is not None and remaining <= 0:
            raise _AgentStopped(ToolLoopStopReason.DEADLINE_EXCEEDED, "调查时限已到")
        if self.rounds >= self.max_rounds:
            raise _AgentStopped(
                ToolLoopStopReason.MAX_ROUNDS, f"达到最大轮次 {self.max_rounds}，未得到最终答案"
            )
        call_id = f"mc_{uuid4().hex}"
        try:
            await self.budget.reserve_model_call(call_id)
        except AgentError as exc:
            raise _AgentStopped(ToolLoopStopReason.BUDGET_EXHAUSTED, str(exc)) from exc

        self.rounds += 1
        try:
            async with asyncio.timeout(remaining):
                response = await handler(request)
        except TimeoutError as exc:
            raise _AgentStopped(ToolLoopStopReason.DEADLINE_EXCEEDED, "模型请求超出调查时限") from exc
        except AgentError as exc:
            if exc.code is ErrorCode.TIMEOUT:
                raise _AgentStopped(ToolLoopStopReason.MODEL_TIMEOUT, "模型服务请求超时") from exc
            raise _AgentStopped(ToolLoopStopReason.MODEL_ERROR, f"模型调用失败: {exc.code.value}") from exc
        except Exception as exc:
            raise _AgentStopped(
                ToolLoopStopReason.MODEL_ERROR, f"模型调用失败: {type(exc).__name__}"
            ) from exc
        finally:
            await self.budget.settle(call_id)

        turn = self.model.turns[-1]
        if turn.usage is not None and turn.usage.total_tokens:
            token_id = f"{call_id}_tok"
            try:
                await self.budget.reserve_tokens(token_id, turn.usage.total_tokens)
            except AgentError as exc:
                await self.budget.record_unbudgeted_tokens(turn.usage.total_tokens)
                raise _AgentStopped(
                    ToolLoopStopReason.BUDGET_EXHAUSTED, "token 预算已耗尽，停止继续调用模型"
                ) from exc
            await self.budget.settle(token_id)

        call_ids = {call.call_id for call in turn.tool_calls}
        if turn.invalid_tool_calls or len(call_ids) != len(turn.tool_calls):
            raise _AgentStopped(ToolLoopStopReason.MODEL_ERROR, "模型返回非法工具调用")
        if turn.tool_calls and not self.model.specs:
            raise _AgentStopped(ToolLoopStopReason.MODEL_ERROR, "该 Agent 没有可用工具")
        if not turn.tool_calls:
            if (turn.finish_reason or "").lower() in {"length", "max_tokens"}:
                raise _AgentStopped(ToolLoopStopReason.MODEL_ERROR, "模型输出被截断")
            if not turn.text.strip():
                raise _AgentStopped(ToolLoopStopReason.MODEL_ERROR, "模型最终回合没有给出任何回答文本")
        return response

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Callable[[ToolCallRequest], Any]
    ) -> ToolMessage:
        call_id = request.tool_call["id"]
        call = next(item for item in self.model.turns[-1].tool_calls if item.call_id == call_id)
        if call.parse_error:
            self.warnings.append(f"工具 {call.name} 参数不合法: {call.parse_error}")
            return ToolMessage(
                content=_error_content(ErrorCode.INVALID_TOOL_ARGUMENTS, call.parse_error),
                tool_call_id=call_id,
                status="error",
            )
        if request.tool is None:
            if self.agent_config is None:
                return ToolMessage(
                    content=_error_content(ErrorCode.TOOL_NOT_ALLOWED, "本次模型调用不允许使用工具"),
                    tool_call_id=call_id,
                    status="error",
                )
            # 记下未注册或未授权的尝试。空白名单确保只审计、绝不执行。
            denied_config = self.agent_config.model_copy(update={"allowed_tools": ()})
            execution = await self.executor.execute(
                call.name, call.arguments, context=self.context, agent_config=denied_config
            )
            self.executions.append(execution)
            return ToolMessage(
                content=_tool_result_content(execution),
                tool_call_id=call_id,
                status="error",
            )
        async with self.tool_lock:
            return await handler(request)

    def tool(self, spec: ToolSpec) -> StructuredTool:
        if self.agent_config is None:
            raise ValueError("有业务工具的 Agent 必须提供 AgentConfig")
        config = self.agent_config

        async def invoke(**arguments: Any) -> str:
            if self.prepare_arguments is not None:
                prepared, reason = self.prepare_arguments(spec.tool_name, arguments)
                if prepared is None:
                    self.warnings.append(f"工具 {spec.name} 调用被拒绝: {reason}")
                    return _error_content(ErrorCode.INVALID_TOOL_ARGUMENTS, str(reason))
                arguments = prepared
            execution = await self.executor.execute(
                spec.tool_name, arguments, context=self.context, agent_config=config
            )
            self.executions.append(execution)
            return _tool_result_content(execution)

        return StructuredTool(
            name=spec.name, description=spec.description, args_schema=spec.parameters,
            coroutine=invoke,
        )


async def run_tool_loop(
    *,
    client: ChatModelClient,
    messages: Sequence[ChatMessage],
    tools: Sequence[ToolSpec],
    executor: ToolExecutor,
    context: AgentContext,
    agent_config: AgentConfig | None,
    budget: Budget,
    max_rounds: int,
    prepare_arguments: ArgumentPolicy | None = None,
) -> ToolLoopOutcome:
    """Run a LangChain Agent and return the existing project's outcome contract."""
    model = _ProjectChatModel(
        client=client, specs=tuple(tools), cache=False,
        tool_aliases={spec.tool_name: spec.name for spec in tools},
    )
    governance = _Governance(
        model, executor, context, agent_config, budget, max_rounds, prepare_arguments
    )
    agent = create_agent(
        model=model, tools=[governance.tool(spec) for spec in tools],
        middleware=[governance], checkpointer=False,
    )
    try:
        await agent.ainvoke(
            {"messages": [to_langchain_message(message) for message in messages]},
            # Each round has at most a model and a tool node. The budget middleware stops it.
            config={"recursion_limit": 2 * max_rounds + 8},
        )
        stop_reason = ToolLoopStopReason.FINAL_ANSWER
    except _AgentStopped as exc:
        stop_reason = exc.reason
        governance.warnings.append(str(exc))

    turns = model.turns
    usages = [turn.usage for turn in turns if turn.usage is not None]
    answer = turns[-1].text if turns else ""
    if not answer and stop_reason != ToolLoopStopReason.MODEL_ERROR:
        answer = next((turn.text for turn in reversed(turns) if turn.text.strip()), "")
    return ToolLoopOutcome(
        answer=answer,
        stop_reason=stop_reason,
        turns=tuple(turns),
        tool_executions=tuple(governance.executions),
        evidence=tuple(item for call in governance.executions for item in call.evidence),
        usage=TokenUsage(
            prompt_tokens=sum(item.prompt_tokens for item in usages),
            completion_tokens=sum(item.completion_tokens for item in usages),
            total_tokens=sum(item.total_tokens for item in usages),
        ),
        warnings=tuple(governance.warnings),
        rounds=governance.rounds,
    )


def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def _error_content(code: ErrorCode, message: str) -> str:
    return _json({"status": "error", "error_code": code.value, "message": message})


def _tool_result_content(execution: ToolExecution) -> str:
    if execution.ok:
        return _json({
            "status": "ok", "tool": execution.tool_name, "call_id": execution.call_id,
            "data": execution.data, "evidence_ids": [item.evidence_id for item in execution.evidence],
        })
    return _json({
        "status": "error", "tool": execution.tool_name, "call_id": execution.call_id,
        "error_code": execution.error.code.value if execution.error else ErrorCode.INTERNAL_ERROR.value,
        "message": execution.error.message if execution.error else "",
    })
