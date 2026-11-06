"""多 Agent 调查工作流装配（Task 009）。

把 Registry、工具、预算、Trace 与 LangGraph 图接在一处：

- 领域 Agent 只拿到 `tool_registry` / `budget` / `trace_log`；
- Coordinator 只拿到 Registry（按 capability 解析），不认识具体 Agent 类；
- 所有子任务共享同一个 `run_id` 与 `trace_id`，靠 `subtask_id` 区分来源。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from .agents.base.contracts import AgentContext
from .agents.base.registry import AgentRegistry
from .agents.factory import build_registry
from .fixtures.repository import FixtureRepository
from .orchestration.investigation import InvestigationResult, Investigator, Planner
from .rag.library import KnowledgeLibrary, build_knowledge_library, fixture_catalog
from .runtime.budget import Budget
from .runtime.types import TraceLog, TrustedContext
from .tools.fixture_tools import build_fixture_tools
from .tools.knowledge_tools import DocumentSearchTool
from .tools.registry import ToolRegistry

__all__ = [
    "InvestigationBundle",
    "build_investigation_bundle",
    "resume_investigation",
    "run_investigation",
]


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
    knowledge: KnowledgeLibrary | None = None
    #: 本次装配使用的引擎与模型（审计用；`offline` 表示没有模型参与）
    engine: str = "deterministic"
    model_provider: str = "offline"
    model_name: str = "none"


def build_investigation_bundle(
    *,
    principal_id: str = "principal_ops_xinghui",
    variant: str | None = None,
    max_tool_calls: int = 12,
    max_model_calls: int = 0,
    max_total_tokens: int | None = None,
    max_revisions: int = 1,
    planner: Planner | None = None,
    backend: str = "fixture",
    document_dir: str | Path | None = None,
    enable_documents: bool = True,
    control_plane: Any = None,
    run_id: str | None = None,
    trace_id: str | None = None,
    engine: str = "deterministic",
    model_client: Any = None,
) -> InvestigationBundle:
    """装配一次调查所需的全部依赖。

    `run_id` / `trace_id` 可由调用方注入（Task 016 / S4）：
    API 的公开 run_id、checkpoint 的 context.run_id、每条 ToolTrace 的 run_id
    必须是**同一个值**，否则"这次运行"在三个地方有三个身份。

    `engine` / `model_client`（Task 018）：`engine="llm"` 时领域 Agent 改由模型
    决定调用哪个工具，但事实仍取自工具输出；没有注入 `model_client` 会直接失败，
    而不是悄悄回退到确定性实现。
    """

    if engine not in ("deterministic", "llm"):
        raise ValueError(f"未知引擎: {engine!r}（可选 deterministic / llm）")
    if engine == "llm" and model_client is None:
        raise ValueError("engine='llm' 必须同时注入 model_client")
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

    knowledge: KnowledgeLibrary | None = None
    if enable_documents:
        knowledge = build_knowledge_library(
            fixture_catalog(repository),
            as_of_date=repository.as_of_date,
            document_dir=document_dir,
        )
        # 一份文档都没索引到时不注册工具：避免留下一个只能返回空结果的工具，
        # 让"文档缺失"体现在 missing_documents 里，而不是伪装成"检索过了但没有" 。
        if knowledge.indexed:
            tool_registry.register(
                DocumentSearchTool(knowledge.service, library=knowledge)
            )

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
        engine=engine,
        model_client=model_client,
    )
    investigator = Investigator(
        registry=report.registry,
        repository=repository,
        max_revisions=max_revisions,
        planner=planner,
        approval_store=getattr(control_plane, "approval_store", None),
        checkpointer=getattr(control_plane, "checkpointer", None),
        budget_snapshot=budget.snapshot,
    )

    principal = repository.principal(principal_id)
    effective_run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
    trusted = TrustedContext.from_principal(
        principal, trace_id=trace_id or f"trace_{uuid.uuid4().hex[:12]}"
    )
    context = trusted.to_agent_context(run_id=effective_run_id)
    return InvestigationBundle(
        repository=repository,
        tool_registry=tool_registry,
        budget=budget,
        trace_log=trace_log,
        registry=report.registry,
        investigator=investigator,
        trusted=trusted,
        context=context,
        knowledge=knowledge,
        engine=engine,
        model_provider=getattr(model_client, "provider", "offline"),
        model_name=getattr(model_client, "model_name", "none"),
    )


async def run_investigation(
    bundle: InvestigationBundle,
    *,
    question: str,
    lease_id: str,
    thread_id: str | None = None,
) -> InvestigationResult:
    return await bundle.investigator.investigate(
        question=question,
        lease_id=lease_id,
        context=bundle.context,
        thread_id=thread_id,
    )


async def resume_investigation(
    bundle: InvestigationBundle,
    *,
    request_id: str,
    decision: str,
    draft_version: int,
    principal_id: str,
) -> InvestigationResult:
    return await bundle.investigator.resume(
        request_id=request_id,
        decision=decision,
        draft_version=draft_version,
        principal_id=principal_id,
    )
