"""LangChain 模型客户端：把 DeepSeek（OpenAI 兼容）接到 `ChatModelClient`。

要点：

1. **复用已有适配层**：模型名、temperature、max_tokens、密钥来源仍由
   `app/llm/adapter.py` 决定，这里只做 LangChain 侧的类型转换。
2. **不在客户端内重试**：重试归属统一交给 Tool Executor / Graph（Runtime contracts §10.2），
   `max_retries=0` 显式关闭 LangChain 的隐式重试，避免与上层重试相乘。
3. **不发网络请求就能构造**：`build_chat_client` 只在真正调用 `complete()` 时才联网，
   因此无密钥环境下也能用 `--dry-run` 校验配置。
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from ..agents.base.contracts import TokenUsage
from ..agents.base.errors import AgentError
from ..config.schema import AgentConfig
from .adapter import get_adapter
from .model_client import (
    ChatMessage,
    ModelInvocationError,
    ModelToolCall,
    ModelTurn,
    ToolSpec,
    parse_tool_call,
)

__all__ = ["LangChainChatModelClient", "build_chat_client", "DEEPSEEK_BASE_URL"]

#: DeepSeek 的 OpenAI 兼容端点
DEEPSEEK_BASE_URL = "https://api.deepseek.com"

_PROVIDER_BASE_URLS: dict[str, str] = {
    "deepseek": DEEPSEEK_BASE_URL,
}


class LangChainChatModelClient:
    """基于 `langchain_openai.ChatOpenAI` 的通用 OpenAI 兼容客户端。"""

    def __init__(self, *, provider: str, model_name: str, chat_model: Any) -> None:
        self.provider = provider
        self.model_name = model_name
        self._chat_model = chat_model

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        lc_messages = [_to_langchain_message(message) for message in messages]
        bound = self._chat_model
        if tools:
            bound = bound.bind_tools([_to_openai_tool(spec) for spec in tools])

        try:
            response = await bound.ainvoke(lc_messages)
        except AgentError:
            raise
        except Exception as exc:  # 厂商 SDK 的异常类型不稳定，统一收敛为 MODEL_ERROR
            raise ModelInvocationError(
                f"模型调用失败: {type(exc).__name__}: {exc}",
                details={"provider": self.provider, "model": self.model_name},
            ) from exc

        return _to_model_turn(response)


def build_chat_client(config: AgentConfig) -> LangChainChatModelClient:
    """按 Agent 配置构造真实模型客户端。

    缺少密钥时抛 `MissingApiKeyError`（不是静默降级）——调用方必须显式选择
    离线 Fake 路径，才不会被误认为"真实调用成功"。
    """

    adapter = get_adapter(config.model_provider)
    api_key = adapter.resolve_api_key(config)
    params = adapter.build_request_params(config)

    base_url = _PROVIDER_BASE_URLS.get(config.model_provider)
    if base_url is None:
        raise ModelInvocationError(
            f"provider {config.model_provider!r} 未配置 LangChain base_url",
            details={"provider": config.model_provider},
        )

    from langchain_openai import ChatOpenAI

    chat_model = ChatOpenAI(
        model=params["model"],
        api_key=api_key,
        base_url=base_url,
        temperature=params.get("temperature"),
        max_tokens=params.get("max_tokens"),
        timeout=config.timeout_seconds,
        max_retries=0,
    )
    return LangChainChatModelClient(
        provider=config.model_provider,
        model_name=config.model_name,
        chat_model=chat_model,
    )


def _to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }


def _to_langchain_message(message: ChatMessage) -> Any:
    from langchain_core.messages import (
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )

    if message.role == "system":
        return SystemMessage(content=message.content)
    if message.role == "user":
        return HumanMessage(content=message.content)
    if message.role == "assistant":
        if message.tool_calls:
            return AIMessage(
                content=message.content,
                tool_calls=[
                    {
                        "name": call.name,
                        "args": call.arguments,
                        "id": call.call_id,
                    }
                    for call in message.tool_calls
                ],
            )
        return AIMessage(content=message.content)
    return ToolMessage(
        content=message.content,
        tool_call_id=message.tool_call_id or "",
    )


def _to_model_turn(response: Any) -> ModelTurn:
    text = _text_of(response)
    tool_calls: list[ModelToolCall] = []
    for raw in getattr(response, "tool_calls", None) or []:
        name = str(raw.get("name") or "").strip()
        if not name:
            continue
        call_id = str(raw.get("id") or "").strip() or f"call_{uuid.uuid4().hex[:12]}"
        args = raw.get("args")
        if isinstance(args, dict):
            tool_calls.append(
                ModelToolCall(
                    call_id=call_id,
                    name=name,
                    arguments=args,
                    arguments_json=_dump_args(args),
                )
            )
        else:
            # 少数 Provider 会把 args 以字符串返回：走统一解析，避免两条路径语义不同
            tool_calls.append(
                parse_tool_call(
                    call_id=call_id,
                    name=name,
                    arguments_json=args if isinstance(args, str) else _dump_args(args),
                )
            )

    usage = _usage_of(response)
    finish_reason = None
    metadata = getattr(response, "response_metadata", None) or {}
    if isinstance(metadata, dict):
        finish_reason = metadata.get("finish_reason")
    return ModelTurn(
        text=text,
        tool_calls=tuple(tool_calls),
        usage=usage,
        finish_reason=str(finish_reason) if finish_reason else None,
    )


def _text_of(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    # LangChain 1.x 可能返回内容块列表；只拼接文本块，忽略其它模态
    parts: list[str] = []
    for block in content or []:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _usage_of(response: Any) -> TokenUsage | None:
    raw = getattr(response, "usage_metadata", None)
    if not isinstance(raw, dict):
        return None
    prompt = int(raw.get("input_tokens") or 0)
    completion = int(raw.get("output_tokens") or 0)
    total = int(raw.get("total_tokens") or (prompt + completion))
    return TokenUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total)


def _dump_args(args: Any) -> str:
    import json

    try:
        return json.dumps(args, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        return str(args)
