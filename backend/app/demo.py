"""离线演示：Scripted Tool-Calling Agent + Runtime 端到端接线。

重要边界：这里**没有模型调用**。`ScriptedToolAgent` 是 Fake Agent，
只用于证明 Runtime → Agent → ToolExecutor → FixtureRepository 的调用边界、
权限、预算与 Trace 确实生效；不得据此声称已接入 DeepSeek 或真实 Tool Calling。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from .agents.base import AgentContext, AgentOutput, AgentRequest, BaseAgent
from .agents.base.errors import AgentError
from .agents.base.registry import AgentRegistry
from .config.schema import AgentConfig
from .fixtures.repository import FixtureRepository
from .runtime.agent_runtime import AgentRuntime
from .runtime.budget import Budget
from .runtime.types import Evidence, RuntimeResult, ToolExecution, TraceLog, TrustedContext
from .tools.executor import ToolExecutor
from .tools.fixture_tools import build_fixture_tools
from .tools.registry import ToolRegistry

__all__ = [
    "DEMO_CAPABILITY",
    "DEMO_TOOLS",
    "DEFAULT_SCRIPT",
    "DemoBundle",
    "ScriptedToolAgent",
    "build_demo_bundle",
    "build_demo_agent_config",
]

DEMO_CAPABILITY = "runtime.demo"

#: 演示用 Fake Agent 在配置中允许调用的工具（模拟 Agent YAML 的 allowed_tools）
DEMO_TOOLS: tuple[str, ...] = (
    "lease.lookup",
    "billing.statement.read",
    "billing.arrears.calculate",
    "property.work_orders.read",
)

#: 默认演示脚本：租约事实 → 欠费金额 → HVAC 工单
DEFAULT_SCRIPT: tuple[tuple[str, dict[str, Any]], ...] = (
    ("lease.lookup", {"lease_id": "lease_xh_a301_2025"}),
    ("billing.arrears.calculate", {"lease_id": "lease_xh_a301_2025"}),
    ("property.work_orders.read", {"lease_id": "lease_xh_a301_2025", "category": "hvac"}),
)


def build_demo_agent_config(**overrides: Any) -> AgentConfig:
    """构造演示 Agent 配置（不落盘、不进 YAML，避免污染 3 个正式 Agent）。"""

    data: dict[str, Any] = {
        "name": ScriptedToolAgent.name,
        "version": ScriptedToolAgent.version,
        "enabled": True,
        "description": ScriptedToolAgent.description,
        "capabilities": [DEMO_CAPABILITY],
        "model_provider": "fake",
        "model_name": "fake-offline",
        "temperature": None,
        "max_tokens": None,
        "api_key_env": None,
        "timeout_seconds": 10.0,
        "max_retries": 0,
        "prompt_path": "app/agents/lease/prompts/system.md",
        "allowed_tools": list(DEMO_TOOLS),
        "log_level": "WARNING",
    }
    data.update(overrides)
    return AgentConfig(**data)


class ScriptedToolAgent(BaseAgent):
    """Fake Agent：按脚本依次调用受控工具，不调用任何模型。"""

    name = "scripted_tool_agent"
    version = "0.1.0"
    description = "演示用确定性 Fake Agent（不调用模型，仅验证 Runtime 与工具边界）"
    capabilities = frozenset({DEMO_CAPABILITY})

    def __init__(
        self,
        config: AgentConfig,
        executor: ToolExecutor,
        script: Iterable[tuple[str, dict[str, Any]]] = DEFAULT_SCRIPT,
    ) -> None:
        super().__init__(config)
        self._executor = executor
        self._script: tuple[tuple[str, dict[str, Any]], ...] = tuple(script)
        self.last_executions: list[ToolExecution] = []

    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        calls = request.payload.get("calls")
        script = (
            tuple((call["tool"], dict(call.get("payload", {}))) for call in calls)
            if calls
            else self._script
        )
        self.last_executions = []
        results: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        for tool_name, payload in script:
            execution = await self._executor.execute(
                tool_name,
                payload,
                context=context,
                agent_config=self.config,
            )
            self.last_executions.append(execution)
            if not execution.ok:
                assert execution.error is not None
                raise AgentError(
                    execution.error.message,
                    code=execution.error.code,
                    retryable=False,
                    details={"call_id": execution.call_id, **execution.error.details},
                )
            results.append(
                {
                    "tool": tool_name,
                    "call_id": execution.call_id,
                    "attempts": execution.attempts,
                    "data": execution.data,
                }
            )
            evidence.extend(item.model_dump(mode="json") for item in execution.evidence)

        return AgentOutput(
            data={
                "tool_results": results,
                "evidence": evidence,
                "evidence_count": len({item["evidence_id"] for item in evidence}),
            }
        )


@dataclass
class DemoBundle:
    """一次演示所需的全部对象，便于测试复用。"""

    repository: FixtureRepository
    tool_registry: ToolRegistry
    budget: Budget
    trace_log: TraceLog
    executor: ToolExecutor
    registry: AgentRegistry
    agent: ScriptedToolAgent
    runtime: AgentRuntime
    trusted: TrustedContext
    request: AgentRequest


def build_demo_bundle(
    *,
    principal_id: str = "principal_ops_xinghui",
    variant: str | None = None,
    script: Iterable[tuple[str, dict[str, Any]]] = DEFAULT_SCRIPT,
    max_tool_calls: int = 10,
    fixture_path: str | None = None,
) -> DemoBundle:
    repository = FixtureRepository.load(fixture_path, variant=variant)

    tool_registry = ToolRegistry()
    for tool in build_fixture_tools(repository):
        tool_registry.register(tool)

    budget = Budget(max_tool_calls=max_tool_calls)
    trace_log = TraceLog()
    executor = ToolExecutor(tool_registry, budget, trace_log=trace_log)

    config = build_demo_agent_config()
    agent = ScriptedToolAgent(config, executor, script)

    registry = AgentRegistry()
    registry.register(agent)

    runtime = AgentRuntime(registry, budget, trace_log=trace_log)
    principal = repository.principal(principal_id)
    trusted = TrustedContext.from_principal(
        principal, trace_id=f"trace_{uuid.uuid4().hex[:12]}"
    )
    request = AgentRequest(
        task_id="task-demo",
        capability=DEMO_CAPABILITY,
        payload={},
    )
    return DemoBundle(
        repository=repository,
        tool_registry=tool_registry,
        budget=budget,
        trace_log=trace_log,
        executor=executor,
        registry=registry,
        agent=agent,
        runtime=runtime,
        trusted=trusted,
        request=request,
    )


async def run_demo(bundle: DemoBundle) -> RuntimeResult:
    return await bundle.runtime.run(bundle.request, bundle.trusted)


def summarize_evidence(evidence: Iterable[Evidence]) -> list[dict[str, Any]]:
    """把证据压成 CLI 可读的简短清单（不含全部字段）。"""

    return [
        {
            "evidence_id": item.evidence_id,
            "entity": item.entity,
            "project_id": item.project_id,
            "tool": item.source_tool,
            "call_id": item.tool_call_id,
        }
        for item in evidence
    ]
