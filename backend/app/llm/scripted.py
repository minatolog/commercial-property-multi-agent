"""脚本化模型客户端（Task 018）：在没有真实密钥时验证"模型驱动"的装配。

它解决的是一个具体的验证缺口：报告要求"真实模型注入、B/C 运行入口可以先在无密钥时
用 Fake/适配器测试开发"。`FakeChatModelClient` 是纯脚本列表，评测/调查一次要跑多个
子任务时不好预先写死轮次；本模块按**意图**生成"先调工具、再总结"的两轮脚本。

明确的边界：

- 这里的"模型"不做任何推理，只是按规则选工具。它能证明**装配接好了**
  （工具白名单、预算、Trace、事实提取、错误码都走真实链路），
  **不能**证明模型质量，也不能用于质量对照结论。
- 报告里的 `provider` 会写成 `scripted`，与 `deepseek` 明确区分。
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

from .model_client import (
    ChatMessage,
    FakeChatModelClient,
    ModelToolCall,
    ModelTurn,
    ToolSpec,
)

__all__ = ["ScriptedToolModel", "scripted_client_for_tools"]


class ScriptedToolModel(FakeChatModelClient):
    """按"当前对话里已经调过哪些工具"决定下一步的模型桩。

    为什么不用固定轮次脚本：调查工作流的三个子 Agent 是**并发**执行的，共享一个
    有状态的轮次队列会互相抢（A 拿到 B 的脚本）。真实模型客户端是无状态的，
    所以按上下文决策才是与生产一致的形状。
    """

    def __init__(
        self,
        calls: Sequence[tuple[str, dict[str, Any]]],
        *,
        summary: str | None = None,
        model_name: str = "scripted-tool-model",
    ) -> None:
        self._planned = [(name, dict(args)) for name, args in calls]
        self._summary = summary or "已根据工具结果完成核对。"
        # 父类只借用其 `calls` 记录能力；轮次由本类自己决定
        super().__init__([], provider="scripted", model_name=model_name)

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        self.calls.append((tuple(messages), tuple(tools)))
        # 脚本用**内部名**书写（`lease.lookup`），返回给循环的必须是暴露名（`lease__lookup`）
        exposed = {spec.original_name: spec.name for spec in tools}
        if not _called_tools(messages):
            # 第一轮就把所有"能用且计划内"的工具一次调用掉（并行 tool calls）。
            # 这样在 `max_tool_rounds=3` 之下仍然留得出总结轮，与真实模型的行为一致。
            planned: list[ModelToolCall] = []
            for index, (internal, args) in enumerate(self._planned, start=1):
                spec_name = exposed.get(internal)
                if spec_name is None:
                    continue
                planned.append(
                    ModelToolCall(
                        call_id=f"scripted_{index}",
                        name=spec_name,
                        arguments=args,
                        arguments_json=json.dumps(args, ensure_ascii=False),
                    )
                )
            if planned:
                return ModelTurn(text="", tool_calls=tuple(planned))
        return ModelTurn(text=self._summary, finish_reason="stop")


def _called_tools(messages: Sequence[ChatMessage]) -> set[str]:
    """从工具返回消息里反推已经调用过的工具名。

    `tool_loop` 会把工具结果以 `role="tool"` 追加进对话；工具名不在 tool 消息里，
    因此用"assistant 声明的 tool_calls 名"来统计更可靠。
    """

    called: set[str] = set()
    for message in messages:
        for call in message.tool_calls or ():
            called.add(call.name)
    return called


def scripted_client_for_tools(
    calls: Iterable[tuple[str, dict[str, Any]]],
    *,
    summary: str | None = None,
    model_name: str = "scripted-tool-model",
) -> ScriptedToolModel:
    return ScriptedToolModel(list(calls), summary=summary, model_name=model_name)
