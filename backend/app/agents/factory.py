"""Agent 工厂：配置 -> 实例 的唯一入口。

安全设计：`AGENT_IMPLEMENTATIONS` 是**代码内的静态白名单**。
YAML 中的 `name` 只能在这个字典里查找，因此即使配置文件被篡改，
也不会触发任意模块导入或代码执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from ..config.loader import load_all_agent_configs
from ..config.schema import AgentConfig
from .base.base_agent import BaseAgent
from .base.errors import AgentConfigMismatchError, AgentNotRegisteredError
from .base.registry import AgentRegistry
from .billing.agent import BillingAgent
from .compliance.agent import ComplianceAgent
from .lease.agent import LeaseAgent
from .property.agent import PropertyAgent
from .single.agent import SingleToolAgent

AGENT_IMPLEMENTATIONS: Final[dict[str, type[BaseAgent]]] = {
    "lease": LeaseAgent,
    "billing": BillingAgent,
    "compliance": ComplianceAgent,
    "property": PropertyAgent,
    "single": SingleToolAgent,
}


@dataclass(frozen=True)
class RegistryBuildReport:
    registry: AgentRegistry
    registered: tuple[str, ...] = ()
    skipped: tuple[str, ...] = field(default=())


def build_agent(config: AgentConfig, **deps: Any) -> BaseAgent:
    implementation = AGENT_IMPLEMENTATIONS.get(config.name)
    if implementation is None:
        raise AgentNotRegisteredError(
            f"配置 {config.name!r} 没有已授权的实现；"
            f"已授权: {sorted(AGENT_IMPLEMENTATIONS)}。"
            "新增 Agent 需要在 AGENT_IMPLEMENTATIONS 中显式登记。"
        )
    _assert_descriptor_matches_config(implementation, config)
    if not deps:
        return implementation(config)
    # 只注入实现真正声明的依赖：每个 Agent 需要什么由它自己的构造函数决定，
    # 无关 Agent 不必被迫接受用不到的参数。
    accepted = _accepted_kwargs(implementation)
    filtered = {key: value for key, value in deps.items() if key in accepted}
    return implementation(config, **filtered)


#: Runtime 允许注入的依赖白名单（配置字符串永远无法扩大这个集合）
AGENT_DEPENDENCY_NAMES: Final[tuple[str, ...]] = (
    "model_client",
    "tool_registry",
    "budget",
    "trace_log",
)


def _accepted_kwargs(implementation: type[BaseAgent]) -> set[str]:
    import inspect

    parameters = inspect.signature(implementation.__init__).parameters
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return set(AGENT_DEPENDENCY_NAMES)
    return {
        name
        for name, param in parameters.items()
        if name not in {"self", "config"}
        and param.kind
        in {inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    }


def _assert_descriptor_matches_config(
    implementation: type[BaseAgent], config: AgentConfig
) -> None:
    """K2：配置声明的 version/capabilities 必须与实现类的类属性一致。

    否则改 YAML 的 version 或 capabilities 会被静默忽略，实际生效的仍是类属性，
    "改配置即生效"的可配置性主张就是假的。这里选择启动期直接失败（fail fast）。
    """
    mismatches: list[str] = []
    if implementation.version != config.version:
        mismatches.append(
            f"version 配置={config.version!r} 实现={implementation.version!r}"
        )
    declared = frozenset(implementation.capabilities)
    configured = frozenset(config.capabilities)
    if declared != configured:
        mismatches.append(
            "capabilities 仅配置="
            f"{sorted(configured - declared)} 仅实现={sorted(declared - configured)}"
        )
    if mismatches:
        raise AgentConfigMismatchError(
            f"Agent {config.name!r} 的配置与实现不一致（{'；'.join(mismatches)}）；"
            "请同步 YAML 与类属性，不允许静默忽略配置"
        )


def build_registry(
    config_dir: str | Path | None = None, *, strict: bool = False, **deps: Any
) -> RegistryBuildReport:
    from ..paths import CONFIG_DIR

    directory = Path(config_dir) if config_dir is not None else CONFIG_DIR
    configs = load_all_agent_configs(directory)

    registry = AgentRegistry()
    registered: list[str] = []
    skipped: list[str] = []

    for name, config in configs.items():
        if name not in AGENT_IMPLEMENTATIONS:
            if strict:
                raise AgentNotRegisteredError(f"配置 {name!r} 没有已授权的实现")
            skipped.append(name)
            continue
        registry.register(build_agent(config, **deps))
        registered.append(name)

    return RegistryBuildReport(
        registry=registry,
        registered=tuple(registered),
        skipped=tuple(skipped),
    )
