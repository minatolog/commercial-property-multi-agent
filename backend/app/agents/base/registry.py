"""Agent Registry。

职责：注册、查找、按能力发现、启用状态判定、拒绝重复与不兼容接口。

安全约束：Registry 只接受**已经构造好的 Agent 实例**，绝不接受模块路径字符串。
从配置到实例的映射放在 `app.agents.factory`，使用**静态白名单字典**，
因此 YAML 里写任何路径都不会触发动态导入。
"""

from __future__ import annotations

from .contracts import AgentDescriptor
from .errors import (
    AgentDisabledError,
    AgentNotRegisteredError,
    CapabilityConflictError,
    CapabilityUnavailableError,
    DuplicateAgentError,
    IncompatibleAgentError,
)
from .protocol import AgentProtocol


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentProtocol] = {}
        self._capability_index: dict[str, str] = {}

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: object) -> bool:
        return name in self._agents

    def register(self, agent: AgentProtocol, *, replace: bool = False) -> AgentDescriptor:
        """注册 Agent。

        K1 修复：先在**副本**上计算新索引，全部成功后才一次性发布；
        任何异常（接口不兼容、描述符非法、冲突）都发生在发布之前，
        因此失败时 Registry 保持原状，不会出现"旧已删、新未加"的残缺状态。
        """
        descriptor = _validated_descriptor(agent)

        agents = dict(self._agents)
        index = dict(self._capability_index)

        if descriptor.name in agents and not replace:
            raise DuplicateAgentError(
                f"Agent 名称重复: {descriptor.name!r}（如需覆盖请显式传 replace=True）"
            )

        conflicts = sorted(
            capability
            for capability in descriptor.capabilities
            if capability in index and index[capability] != descriptor.name
        )
        if conflicts and not replace:
            raise CapabilityConflictError(
                f"能力已被其他 Agent 占用: {conflicts} "
                f"（当前所有者: {[index[c] for c in conflicts]}）"
            )

        if replace:
            displaced = {descriptor.name}
            displaced.update(index[capability] for capability in conflicts)
            for owner in sorted(displaced):
                old = agents.pop(owner, None)
                if old is None:
                    continue
                for capability in old.descriptor.capabilities:
                    if index.get(capability) == owner:
                        index.pop(capability, None)

        agents[descriptor.name] = agent
        for capability in descriptor.capabilities:
            index[capability] = descriptor.name

        # 原子发布：只做两次引用赋值，中间不存在可观察的残缺状态。
        self._agents = agents
        self._capability_index = index
        return descriptor

    def unregister(self, name: str) -> None:
        agent = self._agents.pop(name, None)
        if agent is None:
            return
        for capability in agent.descriptor.capabilities:
            if self._capability_index.get(capability) == name:
                del self._capability_index[capability]

    def get(self, name: str) -> AgentProtocol:
        agent = self._agents.get(name)
        if agent is None:
            raise AgentNotRegisteredError(f"Agent 未注册: {name!r}")
        return agent

    def agent_for_capability(
        self, capability: str, *, enabled_only: bool = True
    ) -> AgentProtocol | None:
        name = self._capability_index.get(capability)
        if name is None:
            return None
        agent = self._agents[name]
        if enabled_only and not agent.descriptor.enabled:
            return None
        return agent

    def require_capability(self, capability: str) -> AgentProtocol:
        """取能力对应的 Agent；缺失与禁用必须能被调用方区分开。"""
        name = self._capability_index.get(capability)
        if name is None:
            raise CapabilityUnavailableError(
                f"没有 Agent 提供能力 {capability!r}；"
                f"当前可用能力: {sorted(self.available_capabilities())}"
            )
        agent = self._agents[name]
        if not agent.descriptor.enabled:
            raise AgentDisabledError(
                f"能力 {capability!r} 由 Agent {name!r} 提供，但该 Agent 已被配置禁用"
            )
        return agent

    def available_capabilities(self, *, enabled_only: bool = True) -> frozenset[str]:
        if not enabled_only:
            return frozenset(self._capability_index)
        return frozenset(
            capability
            for capability, name in self._capability_index.items()
            if self._agents[name].descriptor.enabled
        )

    def disabled_capabilities(self) -> frozenset[str]:
        return frozenset(self._capability_index) - self.available_capabilities()

    def descriptors(self, *, enabled_only: bool = True) -> tuple[AgentDescriptor, ...]:
        items = (agent.descriptor for agent in self._agents.values())
        if enabled_only:
            items = (d for d in items if d.enabled)
        return tuple(sorted(items, key=lambda d: d.name))

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._agents))


def _validated_descriptor(agent: AgentProtocol) -> AgentDescriptor:
    descriptor = getattr(agent, "descriptor", None)
    if not isinstance(descriptor, AgentDescriptor):
        raise IncompatibleAgentError(
            f"{type(agent).__name__} 的 descriptor 不是 AgentDescriptor，接口不兼容"
        )
    if not callable(getattr(agent, "handle", None)):
        raise IncompatibleAgentError(f"{type(agent).__name__} 缺少可调用的 handle 方法")
    if not callable(getattr(agent, "supports", None)):
        raise IncompatibleAgentError(f"{type(agent).__name__} 缺少可调用的 supports 方法")
    return descriptor
