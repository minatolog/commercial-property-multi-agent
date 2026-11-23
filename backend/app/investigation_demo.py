"""多 Agent 调查工作流装配（Task 009 / Task 031）。

把 Registry、工具、预算、Trace 与 LangGraph 图接在一处：

- 领域 Agent 只拿到 `tool_registry` / `budget` / `trace_log`；
- Coordinator 只拿到 Registry（按 capability 解析），不认识具体 Agent 类；
- 所有子任务共享同一个 `run_id` 与 `trace_id`，靠 `subtask_id` 区分来源。

Task 031 / 2.5（模型配置真正生效）：领域 Agent 不再共用一个由 `single.yaml`
创建的客户端，而是各自按自己的 YAML 构造：

- `model_provider="offline"` → 确定性引擎，无模型（等价原行为）；
- `"scripted"` → 用 `scripted_client_for_tools` 注入所有 LLM 领域 Agent
  （脚本化模型按各 Agent 可用工具自行过滤调用）；
- `"deepseek"` → 对每个 `engine="llm"` 白名单内的 Agent 配置调用
  `build_model_client_for_config`（共享参数缓存），缺密钥时构造期即失败；
- `client_factory(config)` 是 deepseek 分支的离线测试缝：按每个 YAML 调用它构造
  假客户端，不联网、不需要密钥。

`bundle.agent_models` 记录每个已注册 LLM Agent 实际使用的模型与参数，
供评测报告按 Agent 输出（不是只写一个全局模型）。

Task 034（规划器）：`planner_mode` 省略时读 `app/config/planner.yaml`（默认 `rule`，
行为与之前完全一致）。`llm` / `hybrid` 需要规划模型，来源与领域 Agent 的引擎**分开**：

- `planner_provider="scripted"` → `ScriptedSupervisorModel`（离线，只证明链路）；
- `planner_provider="deepseek"` → 按 `planner.yaml` 的模型参数构造（`planner_client_factory`
  是离线测试缝）；
- 省略时沿用 `model_provider`（offline 下没有可用的规划模型 → 构造期失败）。

分开的原因：真实模型只做规划、领域 Agent 仍用确定性引擎时，成本只有每题 1 次规划调用。
规划调用计入同一个 `Budget`，因此 `max_model_calls` 必须至少为 1。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .agents.base.contracts import AgentContext
from .agents.base.registry import AgentRegistry
from .agents.factory import build_registry, implementations_for
from .config.loader import load_all_agent_configs
from .fixtures.repository import FixtureRepository
from .llm.factory import (
    MODEL_PROVIDERS,
    ModelClientCache,
    build_model_client_for_config,
    describe_agent_model,
    validate_model_config,
)
from .orchestration.investigation import InvestigationResult, Investigator, Planner
from .orchestration.supervisor import PLANNER_MODES, build_planner
from .paths import CONFIG_DIR
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

#: 脚本化模型的默认总结台词（与 CLI / 历史报告保持一致）
DEFAULT_SCRIPTED_SUMMARY = "已按受控工具结果核对；金额与日期均取自工具输出。"


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
    #: 每个注册的 LLM Agent 实际使用的模型（键 = Agent 名；offline 时为空 dict）。
    #: 条目形状：provider / model_name / temperature / max_tokens / timeout_seconds /
    #: api_key_env / api_key_env_present / client_is_shared / config_source。
    agent_models: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Task 034：规划模式与规划模型（`rule` 时 provider/model 为 None）
    planner_mode: str = "rule"
    planner_info: dict[str, Any] = field(default_factory=dict)


def unit_code_resolver(repository: Any) -> Callable[[str], str | None]:
    """可信租约 → 铺位号（供歧义信号判断“问题点名的铺位是否就是可信目标”）。"""

    record = getattr(repository, "record", None)

    def _resolve(lease_id: str) -> str | None:
        if record is None:
            return None
        lease = record(lease_id) or {}
        unit = record(str(lease.get("unit_id") or "")) or {}
        code = unit.get("code")
        return str(code) if code else None

    return _resolve


def _planner_client(
    provider: str | None,
    config: Any,
    *,
    planner_client: Any = None,
    planner_client_factory: Callable[[Any], Any] | None = None,
) -> Any:
    if planner_client is not None:
        return planner_client
    if provider == "scripted":
        from .llm.scripted import ScriptedSupervisorModel

        return ScriptedSupervisorModel()
    if provider == "deepseek":
        validate_model_config(config)
        client = (
            planner_client_factory(config)
            if planner_client_factory is not None
            else build_model_client_for_config(config)
        )
        if client is None:
            raise ValueError("planner.yaml 的 model_provider 为 offline，不能作为规划模型")
        return client
    raise ValueError(
        "规划模式 llm/hybrid 需要规划模型：请指定 --planner-provider scripted|deepseek，"
        "或使用 --model-provider scripted|deepseek"
    )


def _llm_agent_names(configs: dict[str, Any]) -> list[str]:
    """配置文件里属于 llm 引擎白名单的 Agent 名（保持文件名顺序）。"""

    allowed = implementations_for("llm")
    return [name for name in configs if name in allowed]


def _shared_by_identity(clients: dict[str, Any]) -> dict[str, bool]:
    """按对象身份判断"是否与别的 Agent 共用同一个客户端实例"。"""

    counts: dict[int, int] = {}
    for client in clients.values():
        counts[id(client)] = counts.get(id(client), 0) + 1
    return {name: counts[id(client)] > 1 for name, client in clients.items()}


def _models_for(configs: dict[str, Any], clients: dict[str, Any]) -> dict[str, dict[str, Any]]:
    shared = _shared_by_identity(clients)
    return {
        name: describe_agent_model(
            configs[name],
            client=clients[name],
            client_is_shared=shared[name],
            config_source=f"{name}.yaml",
        )
        for name in clients
    }


def _scripted_clients(
    configs: dict[str, Any], names: list[str], scripted_calls: Iterable[tuple[str, dict[str, Any]]] | None
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    from .llm.scripted import scripted_client_for_tools

    client = scripted_client_for_tools(
        list(scripted_calls or ()), summary=DEFAULT_SCRIPTED_SUMMARY
    )
    clients = {name: client for name in names}
    return clients, _models_for(configs, clients)


def _deepseek_clients(
    configs: dict[str, Any],
    names: list[str],
    *,
    client_factory: Callable[[Any], Any] | None = None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """按每个 Agent 自己的 YAML 构造真实客户端；参数相同者共享缓存实例。"""

    cache = ModelClientCache() if client_factory is None else None
    clients: dict[str, Any] = {}
    for name in names:
        config = configs[name]
        # 先校验：非法配置在构造任何客户端之前就失败，错误信息带上 Agent 名
        validate_model_config(config)
        if client_factory is not None:
            client = client_factory(config)
            if client is None:
                raise ValueError(
                    f"client_factory 为 Agent {name!r} 返回了 None；"
                    "deepseek 路径要求每个 Agent 都有可用客户端"
                )
        else:
            client = build_model_client_for_config(config, cache=cache)
            if client is None:
                raise ValueError(
                    f"Agent {name!r} 的配置声明 model_provider='offline'，"
                    "不能装配到 deepseek 模型路径；请修 YAML 或改用 offline 模式"
                )
        clients[name] = client
    return clients, _models_for(configs, clients)


def _injected_clients(
    configs: dict[str, Any], names: list[str], client: Any
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """兼容既有 `engine="llm", model_client=...` 调用：同一个客户端注入所有 Agent。"""

    clients = {name: client for name in names}
    return clients, _models_for(configs, clients)


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
    engine: str | None = None,
    model_client: Any = None,
    model_provider: str = "offline",
    scripted_calls: Iterable[tuple[str, dict[str, Any]]] | None = None,
    config_dir: str | Path | None = None,
    client_factory: Callable[[Any], Any] | None = None,
    planner_mode: str | None = None,
    planner_provider: str | None = None,
    hybrid_multi_domain: str | None = None,
    planner_client: Any = None,
    planner_client_factory: Callable[[Any], Any] | None = None,
    planner_config_path: str | Path | None = None,
) -> InvestigationBundle:
    """装配一次调查所需的全部依赖。

    `run_id` / `trace_id` 可由调用方注入（Task 016 / S4）：
    API 的公开 run_id、checkpoint 的 context.run_id、每条 ToolTrace 的 run_id
    必须是**同一个值**，否则"这次运行"在三个地方有三个身份。

    模型路径（Task 018 / Task 031）：
    - `engine` 省略时由 `model_provider` / 注入客户端推导：有模型 → `"llm"`，
      否则 `"deterministic"`；
    - 显式 `engine="deterministic"` 与任何模型输入同时出现是冲突组合，直接 `ValueError`
      （静默忽略模型输入会让报告把离线结果当成真实调用）；
    - `engine="llm"` 却没有模型输入同样失败（不再静默回退到确定性实现）；
    - 既有 `engine="llm", model_client=...` 调用保持兼容（脚本化/测试注入）。
    """

    if engine is not None and engine not in ("deterministic", "llm"):
        raise ValueError(f"未知引擎: {engine!r}（可选 deterministic / llm）")
    if model_provider not in MODEL_PROVIDERS:
        raise ValueError(
            f"未知模型 provider: {model_provider!r}（可选 {list(MODEL_PROVIDERS)}）"
        )
    if model_client is not None and model_provider != "offline":
        raise ValueError(
            "model_provider 与 model_client 不能同时使用："
            "前者按各 Agent YAML 构造客户端，后者是显式单实例注入（脚本化/测试）"
        )
    if client_factory is not None and model_provider != "deepseek":
        raise ValueError(
            "client_factory 只作为 model_provider='deepseek' 的离线测试缝使用"
        )

    has_model_input = (
        model_provider in ("scripted", "deepseek")
        or model_client is not None
        or client_factory is not None
    )
    effective_engine = (
        engine if engine is not None else ("llm" if has_model_input else "deterministic")
    )
    if effective_engine == "deterministic" and has_model_input:
        raise ValueError(
            "冲突组合：engine='deterministic' 不接受模型输入"
            "（model_provider/model_client/client_factory）；确定性引擎不使用模型"
        )
    if effective_engine == "llm" and not has_model_input:
        raise ValueError(
            "engine='llm' 必须同时注入模型：model_provider='scripted'/'deepseek'，"
            "或显式 model_client（脚本化/测试），或 client_factory"
        )
    if backend not in ("fixture", "sqlite"):
        raise ValueError(f"未知 backend: {backend!r}（可选 fixture / sqlite）")

    directory = Path(config_dir) if config_dir is not None else CONFIG_DIR

    model_clients: dict[str, Any] = {}
    agent_models: dict[str, dict[str, Any]] = {}
    bundle_provider = model_provider
    bundle_model_name = "none"

    if effective_engine == "llm":
        configs = load_all_agent_configs(directory)
        names = _llm_agent_names(configs)
        if not names:
            raise ValueError(
                f"配置目录 {directory} 中没有属于 llm 引擎白名单的 Agent 配置"
            )
        if model_provider == "deepseek":
            model_clients, agent_models = _deepseek_clients(
                configs, names, client_factory=client_factory
            )
            bundle_model_name = ",".join(
                sorted({entry["model_name"] for entry in agent_models.values()})
            )
        elif model_provider == "scripted":
            model_clients, agent_models = _scripted_clients(
                configs, names, scripted_calls
            )
            bundle_model_name = next(iter(model_clients.values())).model_name
        else:  # 兼容既有显式注入
            model_clients, agent_models = _injected_clients(
                configs, names, model_client
            )
            bundle_provider = getattr(model_client, "provider", "offline")
            bundle_model_name = getattr(model_client, "model_name", "none")

    if backend == "fixture":
        repository = FixtureRepository.load(None, variant=variant)
    else:
        if variant is not None:
            raise ValueError("sqlite 后端暂不支持 fixture 变体（变体仅用于 fixture 对比）")
        from .db.bootstrap import build_sqlite_repository

        _, repository = build_sqlite_repository()

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

    # Task 034：规划器。显式传入 Planner 实例时原样使用（既有调用方/测试）。
    from .config.loader import load_planner_config

    planner_config = load_planner_config(planner_config_path)
    effective_mode = planner_mode or planner_config.mode
    if effective_mode not in PLANNER_MODES:
        raise ValueError(f"未知规划模式 {effective_mode!r}（可选 {list(PLANNER_MODES)}）")
    planner_info: dict[str, Any] = {
        "mode": effective_mode if planner is None else "custom",
        "provider": None,
        "model_name": None,
        "hybrid_multi_domain": hybrid_multi_domain or planner_config.hybrid_multi_domain,
        "max_domains": planner_config.max_domains,
        "config_source": "planner.yaml",
    }
    if planner is not None and planner_mode is not None:
        raise ValueError("planner 与 planner_mode 不能同时指定")
    if planner is None and effective_mode != "rule":
        resolved_provider = planner_provider or (
            model_provider if model_provider != "offline" else None
        )
        client = _planner_client(
            resolved_provider,
            planner_config,
            planner_client=planner_client,
            planner_client_factory=planner_client_factory,
        )
        if (max_model_calls or 0) < 1:
            raise ValueError(
                f"规划模式 {effective_mode!r} 会调用规划模型，max_model_calls 至少为 1"
                "（规划调用与 Agent 共享模型调用预算）"
            )
        planner = build_planner(
            effective_mode,
            config=planner_config,
            model_client=client,
            budget=budget,
            unit_code_of=unit_code_resolver(repository),
            hybrid_multi_domain=hybrid_multi_domain,
        )
        planner_info["provider"] = getattr(client, "provider", resolved_provider)
        planner_info["model_name"] = getattr(client, "model_name", None)

    report = build_registry(
        directory,
        tool_registry=tool_registry,
        budget=budget,
        trace_log=trace_log,
        engine=effective_engine,
        model_clients=model_clients or None,
        model_client=model_client if not model_clients else None,
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
        engine=effective_engine,
        model_provider=bundle_provider,
        model_name=bundle_model_name,
        agent_models=agent_models,
        planner_mode=planner_info["mode"],
        planner_info=planner_info,
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
