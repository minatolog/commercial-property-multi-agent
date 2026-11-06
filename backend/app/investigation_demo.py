"""多 Agent 调查工作流装配（Task 009）。

把 Registry、工具、预算、Trace 与 LangGraph 图接在一处：

- 领域 Agent 只拿到 `tool_registry` / `budget` / `trace_log`；
- Coordinator 只拿到 Registry（按 capability 解析），不认识具体 Agent 类；
- 所有子任务共享同一个 `run_id` 与 `trace_id`，靠 `subtask_id` 区分来源。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from .agents.base.contracts import AgentContext
from .agents.base.registry import AgentRegistry
from .agents.factory import build_registry
from .fixtures.repository import FixtureRepository
from .orchestration.investigation import InvestigationResult, Investigator, Planner
from .runtime.budget import Budget
from .runtime.types import TraceLog, TrustedContext
from .tools.fixture_tools import build_fixture_tools
from .tools.registry import ToolRegistry

__all__ = ["InvestigationBundle", "build_investigation_bundle", "run_investigation"]


@dataclass
class InvestigationBundle:
    repository: FixtureRepository
    tool_registry: ToolRegistry
    budget: Budget
    trace_log: TraceLog
    registry: AgentRegistry
    investigator: Investigator
    trusted: TrustedContext
    context: AgentContext


def build_investigation_bundle(
    *,
    principal_id: str = "principal_ops_xinghui",
    variant: str | None = None,
    max_tool_calls: int = 12,
    max_model_calls: int = 0,
    max_total_tokens: int = 0,
    max_revisions: int = 1,
    planner: Planner | None = None,
    backend: str = "fixture",
) -> InvestigationBundle:
    if backend == "fixture":
        repository = FixtureRepository.load(None, variant=variant)
    elif backend == "sqlite":
        if variant is not None:
            raise ValueError("sqlite 后端暂不支持 fixture 变体（变体仅用于 fixture 对比）")
        from .db.bootstrap import build_sqlite_repository

        _, repository = build_sqlite_repository()
    else:
        raise ValueError(f"未知 backend: {backend!r}（可选 fixture / sqlite）")

    tool_registry = ToolRegistry()
    for tool in build_fixture_tools(repository):
        tool_registry.register(tool)

    budget = Budget(
        max_tool_calls=max_tool_calls,
        max_model_calls=max_model_calls,
        max_total_tokens=max_total_tokens,
    )
    trace_log = TraceLog()

    report = build_registry(
        tool_registry=tool_registry,
        budget=budget,
        trace_log=trace_log,
    )
    investigator = Investigator(
        registry=report.registry,
        repository=repository,
        max_revisions=max_revisions,
        planner=planner,
    )

    principal = repository.principal(principal_id)
    trusted = TrustedContext.from_principal(
        principal, trace_id=f"trace_{uuid.uuid4().hex[:12]}"
    )
    context = trusted.to_agent_context(run_id=f"run_{uuid.uuid4().hex[:12]}")
    return InvestigationBundle(
        repository=repository,
        tool_registry=tool_registry,
        budget=budget,
        trace_log=trace_log,
        registry=report.registry,
        investigator=investigator,
        trusted=trusted,
        context=context,
    )


async def run_investigation(
    bundle: InvestigationBundle, *, question: str, lease_id: str
) -> InvestigationResult:
    return await bundle.investigator.investigate(
        question=question, lease_id=lease_id, context=bundle.context
    )
