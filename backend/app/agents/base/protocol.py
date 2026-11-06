"""Agent 统一接口定义。

这是整个系统唯一的 Agent 契约。新增 Agent 只需实现本协议，
不需要修改任何已有 Agent；Coordinator 与 Registry 也只面向本协议编程。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import AgentContext, AgentDescriptor, AgentRequest, AgentResult


@runtime_checkable
class AgentProtocol(Protocol):
    """所有 Agent 必须满足的结构化接口。"""

    @property
    def descriptor(self) -> AgentDescriptor:
        """Agent 标识与能力描述，供 Registry 发现与选择。"""
        ...

    def supports(self, capability: str) -> bool:
        """是否声明支持某个 capability。"""
        ...

    async def handle(self, request: AgentRequest, context: AgentContext) -> AgentResult:
        """唯一对外入口。禁止让外部直接调用 Agent 的内部方法。"""
        ...
