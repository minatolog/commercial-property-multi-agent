"""模型调用抽象层。

把"Agent 如何思考"与"具体厂商 SDK"隔开：

- `ChatModelClient` 是 Runtime 唯一认识的接口，只吃我们的 `ChatMessage` / `ToolSpec`，
  吐 `ModelTurn`（文本 + 工具调用 + token 用量）；
- `FakeChatModelClient` 让全部离线测试零网络、确定性；
- 真实 Provider（LangChain / DeepSeek）在 `langchain_client.py` 里，仅通过工厂注入。

这样替换模型不需要改 Agent、工具或图：只改 YAML 的 provider/model，或换一个实现。
"""

from __future__ import annotations

import json
from typing import Any, Literal, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..agents.base.contracts import TokenUsage
from ..agents.base.errors import AgentError, ErrorCode

__all__ = [
    "ChatMessage",
    "ChatModelClient",
    "FakeChatModelClient",
    "ModelInvocationError",
    "ModelToolCall",
    "InvalidToolCallRecord",
    "ModelTurn",
    "ToolSpec",
    "ToolSpecBuilder",
]


class ModelInvocationError(AgentError):
    """模型调用失败（网络、鉴权、限流、返回结构异常）。"""

    default_code = ErrorCode.MODEL_ERROR


class ChatMessage(BaseModel):
    """与厂商无关的消息。

    `tool_calls` / `tool_call_id` 只在工具循环内部使用，用于把工具结果回传给模型。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple["ModelToolCall", ...] = ()
    tool_call_id: str | None = None


class ModelToolCall(BaseModel):
    """模型请求的一次工具调用。

    `arguments_json` 保留模型原始输出，`arguments` 是解析后的结果；
    解析失败时 `arguments` 为空且 `parse_error` 非空，调用方必须把
    "参数不合法"回传给模型而不是静默重试。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_json: str = ""
    parse_error: str | None = None


class InvalidToolCallRecord(BaseModel):
    """模型返回的**非法**工具调用（Task 016 / F6）。

    典型来源：JSON 参数解析失败、缺少工具名、空 id。它们不能被静默丢弃，
    否则"模型想调工具但调错了"会被误当成"模型给出了最终答案"。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    call_id: str = ""
    name: str = ""
    arguments_json: str = ""
    error: str = ""


class ModelTurn(BaseModel):
    """一次模型响应。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = ""
    tool_calls: tuple[ModelToolCall, ...] = ()
    #: 被拒绝的非法调用；调用方必须显式处理（反馈错误或失败），不得当作正常结束
    invalid_tool_calls: tuple[InvalidToolCallRecord, ...] = ()
    usage: TokenUsage | None = None
    finish_reason: str | None = None


class ToolSpec(BaseModel):
    """提供给模型的工具声明（JSON Schema 由工具自己的输入模型生成）。

    两个名字必须分开（Task 020）：

    - `name`：**暴露给模型**的名字。多数 provider 只接受 `^[a-zA-Z0-9_-]+$`，
      所以内部名 `lease.lookup` 必须转成 `lease__lookup`；
    - `tool_name`：内部注册名，真正执行时用。

    为什么不是"把内部工具改名叫下划线"：`.` 分隔是项目内 capability/tool 的命名约定，
    改全局命名会影响配置、Trace、审计与既有契约；在边界处做映射代价最小。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    #: 内部注册名；默认与 `name` 相同（兼容不经过映射的调用）
    tool_name: str = ""

    def model_post_init(self, __context: Any) -> None:  # noqa: D105 - pydantic hook
        if not self.tool_name:
            object.__setattr__(self, "tool_name", self.name)

    @property
    def original_name(self) -> str:
        return self.tool_name or self.name


def provider_safe_name(name: str) -> str:
    """把内部工具名转成 provider 允许的函数名（`lease.lookup` → `lease__lookup`）。

    用 `__` 而不是 `_`：`a.b_c` 与 `a_b.c` 会撞成同一个名字，双下划线能显著降低歧义，
    仍由 `ToolSpecBuilder` 做最终唯一性校验。
    """

    return name.replace(".", "__")


@runtime_checkable
class ChatModelClient(Protocol):
    provider: str
    model_name: str

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn: ...


class ToolSpecBuilder:
    """从 ToolRegistry + Agent 授权范围构造模型可见的工具清单。"""

    @staticmethod
    def build(
        registry: Any,
        *,
        allowed_tools: Sequence[str],
        permissions: frozenset[str],
    ) -> tuple[ToolSpec, ...]:
        specs: list[ToolSpec] = []
        seen: dict[str, str] = {}
        for name in allowed_tools:
            if name not in registry:
                # 配置声明了但项目未实现的工具：不暴露给模型，避免它调一个必然失败的名字
                continue
            tool = registry.get(name)
            if not tool.required_permissions <= permissions:
                # 权限不足的工具不下发，模型根本不会尝试（越权在第一道闸就被挡掉）
                continue
            exposed = provider_safe_name(tool.name)
            if exposed in seen and seen[exposed] != tool.name:
                raise ValueError(
                    f"工具名映射冲突：{seen[exposed]!r} 与 {tool.name!r} 都映射为 {exposed!r}"
                )
            seen[exposed] = tool.name
            specs.append(
                ToolSpec(
                    name=exposed,
                    description=tool.description,
                    parameters=_tool_parameters(tool),
                    tool_name=tool.name,
                )
            )
        return tuple(specs)


def _tool_parameters(tool: Any) -> dict[str, Any]:
    schema = tool.input_model.model_json_schema()
    schema.pop("title", None)
    # 模型不需要看到 pydantic 的 $defs 噪音时也保持原样：JSON Schema 需自洽
    return schema


class FakeChatModelClient:
    """脚本化模型：按顺序返回预设响应，并记录收到的消息与工具。

    只用于离线测试与演示；它证明的是"工具循环接好了"，**不能**证明模型质量。
    """

    def __init__(
        self,
        turns: Sequence[ModelTurn | str],
        *,
        provider: str = "fake",
        model_name: str = "fake-scripted",
    ) -> None:
        self.provider = provider
        self.model_name = model_name
        self._turns: list[ModelTurn] = [
            turn if isinstance(turn, ModelTurn) else ModelTurn(text=turn) for turn in turns
        ]
        self._index = 0
        self.calls: list[tuple[tuple[ChatMessage, ...], tuple[ToolSpec, ...]]] = []

    @property
    def remaining(self) -> int:
        return max(0, len(self._turns) - self._index)

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        self.calls.append((tuple(messages), tuple(tools)))
        if self._index >= len(self._turns):
            raise ModelInvocationError(
                f"FakeChatModelClient 脚本已用尽（第 {self._index + 1} 次调用无预设响应）"
            )
        turn = self._turns[self._index]
        self._index += 1
        return turn


def parse_tool_call(
    *, call_id: str, name: str, arguments_json: str
) -> ModelToolCall:
    """把模型给出的原始参数解析成结构化调用；失败不抛异常，交由循环回传。"""

    try:
        parsed = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError as exc:
        return ModelToolCall(
            call_id=call_id,
            name=name,
            arguments_json=arguments_json,
            parse_error=f"参数不是合法 JSON: {exc.msg}",
        )
    if not isinstance(parsed, dict):
        return ModelToolCall(
            call_id=call_id,
            name=name,
            arguments_json=arguments_json,
            parse_error=f"参数必须是 JSON 对象，收到 {type(parsed).__name__}",
        )
    return ModelToolCall(
        call_id=call_id, name=name, arguments=parsed, arguments_json=arguments_json
    )
