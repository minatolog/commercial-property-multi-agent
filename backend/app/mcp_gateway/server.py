"""MCP 网关服务（Task 033B）：low-level `Server`、处理器与 stdio 入口。

协议外壳只做四件事：

1. `tools/list`：把**当前档案允许的只读工具**映射成下划线别名，同时给出
   `input_model` 的 JSON Schema 与 033A 的统一结果信封 Schema；
2. `tools/call`：保留键拦截 → 别名映射回原名 → 从**会话身份**构造
   `AgentContext` → `ToolExecutor.execute()` → 033A 的 `CallToolResult`；
3. **一个连接一个会话**：每个 MCP 连接（`Server.run` 的一次 lifespan）拥有
   独立的 `Budget` / `ToolExecutor` / `TraceLog`，额度来自客户端档案；
4. 失败绝不伪装成功：保留键、未知工具、身份错误与未预期异常都返回
   `isError=True` 的信封；未预期异常只在 stderr 记录堆栈，不把 Python
   堆栈返回给客户端。

Trace 来源靠命名区分，不改执行器：`identity.create_session` 生成的会话 ID
形如 `mcp_<档案名>_<随机串>`，`resolve_context` 把它写进 `run_id`，因此
Trace 里同时能看到 `entrypoint=mcp`（前缀）与 `client=<档案名>`（第二段）。

本模块不直接调用任何工具的 `invoke`：执行入口只有 `ToolExecutor.execute()`。
"""

from __future__ import annotations

import sys
import traceback
import uuid
from collections import deque
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mcp_types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server

from ..agents.base.contracts import AgentErrorDetail
from ..agents.base.errors import AgentConfigError, AgentError, ErrorCode
from ..config.schema import AgentConfig
from ..fixtures.repository import FixtureRepository
from ..rag.library import build_knowledge_library, fixture_catalog
from ..runtime.budget import Budget
from ..runtime.types import RESERVED_PAYLOAD_KEYS, ToolExecution, ToolStatus, TraceLog
from ..tools.executor import ToolExecutor
from ..tools.fixture_tools import build_fixture_tools
from ..tools.knowledge_tools import DocumentSearchTool
from ..tools.registry import ToolRegistry
from .identity import SessionIdentity, create_session, resolve_context
from .profiles import (
    READ_ONLY_TOOLS,
    ClientProfile,
    load_profile,
    to_agent_config,
)
from .results import envelope_output_schema, to_call_tool_result

__all__ = [
    "GATEWAY_NAME",
    "GATEWAY_VERSION",
    "GatewayServer",
    "McpSession",
    "alias_for",
    "build_gateway",
    "build_registry",
    "load_gateway",
]

GATEWAY_NAME = "commercial-property-mcp-gateway"
GATEWAY_VERSION = "0.1.0"

#: 诊断用会话快照的上限
_SESSION_HISTORY = 32


def alias_for(tool_name: str) -> str:
    """注册名 → 下划线别名（`billing.statement.read` → `billing_statement_read`）。"""

    return tool_name.replace(".", "_")


@dataclass(frozen=True)
class McpSession:
    """一个 MCP 连接（会话）的独立运行状态。"""

    identity: SessionIdentity
    agent_config: AgentConfig
    budget: Budget
    executor: ToolExecutor
    trace_log: TraceLog


def build_registry(
    *,
    repository: FixtureRepository | None = None,
    document_dir: str | Path | None = None,
) -> ToolRegistry:
    """与 CLI `search` 一致的只读工具集合（含条款检索）。

    即使 PDF 索引为空也注册 `document.search`：档案校验只关心工具“已注册”，
    空索引下该工具返回零结果，不会伪造证据。
    """

    repo = FixtureRepository.load() if repository is None else repository
    registry = ToolRegistry()
    for tool in build_fixture_tools(repo):
        registry.register(tool)
    library = build_knowledge_library(
        fixture_catalog(repo),
        as_of_date=repo.as_of_date,
        document_dir=document_dir,
    )
    registry.register(DocumentSearchTool(library.service, library=library))
    return registry


def _build_call_names(registry: ToolRegistry) -> dict[str, str]:
    """别名/原名 → 注册名；任何冲突都在构建期失败。

    冲突有两种：

    - **别名之间**：`billing.statement.read` 与 `billing.statement_read`
      都会折叠成 `billing_statement_read`；
    - **别名与原名**：理论上只有当注册名不含点号时才可能发生；注册表要求
      名称至少含一个点号，因此这一项是防御性检查，防止将来放宽命名规则。

    冲突时无法判断客户端想调哪个工具，静默覆盖会变成安全问题，所以直接
    在构建 `Server` 时抛 `AgentConfigError`。
    """

    names = registry.names()
    alias_owner: dict[str, str] = {}
    for name in names:
        alias = alias_for(name)
        previous = alias_owner.get(alias)
        if previous is not None:
            raise AgentConfigError(
                f"工具名别名冲突: {previous!r} 与 {name!r} 都会映射为 {alias!r}"
            )
        alias_owner[alias] = name

    overlap = sorted(set(alias_owner) & set(names))
    if overlap:
        details = "; ".join(
            f"{alias!r}（{alias_owner[alias]!r} 的别名）与同名的已注册工具" for alias in overlap
        )
        raise AgentConfigError(f"工具名别名与原名冲突: {details}")

    mapping: dict[str, str] = dict(alias_owner)
    for name in names:
        mapping[name] = name
    return mapping


def _validate_allowed_tools(profile: ClientProfile, registry: ToolRegistry) -> None:
    """档案只能开放已注册的只读工具（与 `load_profile` 同一约束，再校验一次）。"""

    for name in profile.allowed_tools:
        if name not in READ_ONLY_TOOLS:
            raise AgentConfigError(
                f"客户端档案 {profile.name!r} 试图开放非只读工具: {name!r}；"
                f"本版本只允许 {sorted(READ_ONLY_TOOLS)}"
            )
        if name not in registry:
            raise AgentConfigError(
                f"客户端档案 {profile.name!r} 列出未注册的工具: {name!r}"
            )


def _failure(
    tool_name: str,
    code: ErrorCode,
    message: str,
    *,
    status: ToolStatus = ToolStatus.ERROR,
) -> ToolExecution:
    """网关在进入执行器之前拒绝时，构造一个与执行器同形的失败结果。"""

    return ToolExecution(
        call_id=f"tc_gw_{uuid.uuid4().hex[:12]}",
        tool_name=tool_name,
        status=status,
        error=AgentErrorDetail(code=code, message=message),
    )


def _log_unexpected(tool_name: str) -> None:
    """未预期异常的堆栈只写 stderr（stdout 留给 MCP 协议）。"""

    print(
        f"[mcp-gateway] 处理工具调用 {tool_name!r} 时发生未预期异常，"
        "堆栈仅写入 stderr:",
        file=sys.stderr,
    )
    traceback.print_exc(file=sys.stderr)


class GatewayServer:
    """绑定一个客户端档案的 MCP 网关。

    构造成功即代表档案可用、别名无冲突；连接建立时（lifespan）才创建会话身份、
    `Budget` 与 `ToolExecutor`，因此每个连接的额度互不影响。
    """

    def __init__(
        self,
        profile: ClientProfile,
        registry: ToolRegistry,
        *,
        repository: FixtureRepository | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        _validate_allowed_tools(profile, registry)
        self._profile = profile
        self._registry = registry
        # 服务端可信主体记录：身份解析只读这里，绝不读调用参数。
        self._repository = (
            FixtureRepository.load() if repository is None else repository
        )
        self._environ = environ
        self._call_names = _build_call_names(registry)
        # 只保留最近的会话快照供测试/诊断，避免长时间运行时随连接数无限增长
        # （复查 P3-2；HTTP 版本多连接时尤其需要）。
        self._sessions: deque[McpSession] = deque(maxlen=_SESSION_HISTORY)
        # 启动期就确认主体存在（复查 P3-4）：否则服务能起来，但每次调用都失败。
        preview = create_session(profile, environ=environ)
        try:
            self._repository.principal(preview.principal_id)
        except AgentError as exc:
            raise AgentConfigError(
                f"客户端档案 {profile.name!r} 的主体 {preview.principal_id!r}"
                f"（来源 {preview.source}）不存在：{exc.message}"
            ) from exc
        self._startup_identity = preview
        self._server: Server[McpSession] = Server(
            name=GATEWAY_NAME,
            version=GATEWAY_VERSION,
            instructions=(
                f"MCP 客户端档案 {profile.name!r}；只开放只读工具；"
                "身份来自服务端会话（开发模式）。"
            ),
            lifespan=self._lifespan,
            on_list_tools=self._on_list_tools,
            on_call_tool=self._on_call_tool,
        )

    # ------------------------------------------------------------------ 属性

    @property
    def profile(self) -> ClientProfile:
        return self._profile

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    @property
    def server(self) -> Server[McpSession]:
        """底层 low-level `Server`（测试用内存客户端直接连接它）。"""

        return self._server

    @property
    def sessions(self) -> tuple[McpSession, ...]:
        """按建立顺序记录的最近会话（最多 `_SESSION_HISTORY` 个，只读快照，供测试/诊断）。"""

        return tuple(self._sessions)

    @property
    def startup_identity(self) -> SessionIdentity:
        """启动时解析出的主体与来源（用于启动提示；每个连接仍各自生成会话 ID）。"""

        return self._startup_identity

    # ------------------------------------------------------------------ 生命周期

    @asynccontextmanager
    async def _lifespan(self, _server: Server[McpSession]) -> AsyncIterator[McpSession]:
        """每个 MCP 连接一个独立会话：身份、预算、执行器、Trace 都不共享。"""

        identity = create_session(self._profile, environ=self._environ)
        trace_log = TraceLog()
        budget = Budget(
            max_tool_calls=self._profile.budget.max_tool_calls_per_session
        )
        session = McpSession(
            identity=identity,
            agent_config=to_agent_config(self._profile),
            budget=budget,
            executor=ToolExecutor(self._registry, budget, trace_log=trace_log),
            trace_log=trace_log,
        )
        self._sessions.append(session)
        yield session

    # ------------------------------------------------------------------ tools/list

    def _describe_tool(self, name: str) -> types.Tool:
        tool = self._registry.get(name)
        return types.Tool(
            name=alias_for(name),
            description=f"{tool.description}（原名: {name}）",
            input_schema=tool.input_model.model_json_schema(),
            output_schema=envelope_output_schema(tool.output_model),
        )

    async def _on_list_tools(
        self,
        _ctx: ServerRequestContext[McpSession],
        _params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        # 只列档案允许的工具；顺序与档案一致，便于人工核对。
        return types.ListToolsResult(
            tools=[self._describe_tool(name) for name in self._profile.allowed_tools]
        )

    # ------------------------------------------------------------------ tools/call

    async def _on_call_tool(
        self,
        ctx: ServerRequestContext[McpSession],
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult:
        session = ctx.lifespan_context
        arguments = dict(params.arguments or {})
        try:
            execution = await self._dispatch(session, params.name, arguments)
        except Exception:  # 网关自身缺陷也不能变成"成功"
            _log_unexpected(params.name)
            execution = _failure(
                params.name,
                ErrorCode.INTERNAL_ERROR,
                "MCP 网关内部错误（详情见服务端 stderr 日志）",
            )
        return to_call_tool_result(execution)

    async def _dispatch(
        self,
        session: McpSession,
        requested_name: str,
        arguments: dict[str, Any],
    ) -> ToolExecution:
        # 1. 保留键：身份/权限/预算只能来自可信上下文，出现在参数里直接拒绝。
        #    执行器对保留键本身返回 invalid_tool_arguments（信封里会落成 error），
        #    而任务要求这里 status=denied；因此用执行器认可的同组拒绝码
        #    permission_denied，让 033A 的 Code→status 映射仍然给出 denied。
        reserved = sorted(RESERVED_PAYLOAD_KEYS & set(arguments))
        if reserved:
            # 预拦截不进执行器、不写业务 Trace、不消耗预算，但安全事件要留痕（复查 P3-3）
            print(
                f"[mcp-gateway] 拒绝：会话 {session.identity.session_id} 调用 "
                f"{requested_name!r} 的参数含保留键 {reserved}",
                file=sys.stderr,
            )
            return _failure(
                requested_name,
                ErrorCode.PERMISSION_DENIED,
                "payload 含保留键，权限/项目范围/预算只能由可信上下文提供",
                status=ToolStatus.DENIED,
            )

        # 2. 别名映射回注册名；未知名称原样交给执行器，让错误码与执行器一致。
        tool_name = self._call_names.get(requested_name, requested_name)

        # 3. 身份只从会话得到；解析失败（例如 DEMO_PRINCIPAL_ID 指向不存在的主体）
        #    也要变成结构化失败，而不是协议错误。
        try:
            context = resolve_context(session.identity, repository=self._repository)
        except AgentError as exc:
            return _failure(tool_name, exc.code, exc.message)

        # 4. 唯一执行入口。
        return await session.executor.execute(
            tool_name,
            arguments,
            context=context,
            agent_config=session.agent_config,
        )

    # ------------------------------------------------------------------ stdio

    async def serve_stdio(self) -> None:
        """在进程 stdin/stdout 上提供 MCP 服务（stdout 只承载协议）。"""

        async with stdio_server() as (read_stream, write_stream):
            await self._server.run(
                read_stream,
                write_stream,
                self._server.create_initialization_options(),
            )


def build_gateway(
    profile: ClientProfile,
    registry: ToolRegistry,
    *,
    repository: FixtureRepository | None = None,
    environ: Mapping[str, str] | None = None,
) -> GatewayServer:
    """用已加载的档案构造网关；档案/别名问题在这里（构建 `Server` 时）失败。"""

    return GatewayServer(
        profile,
        registry,
        repository=repository,
        environ=environ,
    )


def load_gateway(
    client_name: str,
    *,
    registry: ToolRegistry | None = None,
    config_dir: str | Path | None = None,
    repository: FixtureRepository | None = None,
    environ: Mapping[str, str] | None = None,
) -> GatewayServer:
    """按档案名加载并构造网关（CLI 与测试共用入口）。

    档案不存在、被禁用、列出未注册/非只读工具、别名冲突都会在这里抛
    `AgentConfigError`，调用方应在启动服务前以非零退出码结束。
    """

    repo = FixtureRepository.load() if repository is None else repository
    tool_registry = build_registry(repository=repo) if registry is None else registry
    profile = load_profile(client_name, registry=tool_registry, config_dir=config_dir)
    return build_gateway(
        profile,
        tool_registry,
        repository=repo,
        environ=environ,
    )
