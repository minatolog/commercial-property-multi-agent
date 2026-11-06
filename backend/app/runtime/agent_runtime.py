"""Agent Runtime：可信上下文边界与结构化结果。

本层只做四件事：

1. 拒绝"把权限写进 payload"的请求（可信上下文只能来自已认证入口）；
2. 按 capability 从 Registry 解析 Agent（禁用/缺失分别报告）；
3. 把 `TrustedContext` 转成既有 `AgentContext` 后调用 `Agent.handle()`；
4. 汇总证据、Trace 与预算用量，返回 `RuntimeResult`。

不实现模型调用、图编排或审批恢复（Task 008+）。
"""

from __future__ import annotations

import uuid
from typing import Any

from ..agents.base.contracts import (
    AgentContext,
    AgentErrorDetail,
    AgentRequest,
    TaskStatus,
)
from ..agents.base.errors import (
    AgentDisabledError,
    CapabilityUnavailableError,
    ErrorCode,
)
from ..agents.base.registry import AgentRegistry
from .budget import Budget
from .types import (
    RESERVED_PAYLOAD_KEYS,
    Evidence,
    RuntimeResult,
    ToolTrace,
    TraceLog,
    TrustedContext,
)

__all__ = ["AgentRuntime"]


class AgentRuntime:
    def __init__(
        self,
        registry: AgentRegistry,
        budget: Budget,
        *,
        trace_log: TraceLog | None = None,
    ) -> None:
        self._registry = registry
        self._budget = budget
        self._trace_log = trace_log if trace_log is not None else TraceLog()

    @property
    def trace_log(self) -> TraceLog:
        return self._trace_log

    async def run(self, request: AgentRequest, trusted: TrustedContext) -> RuntimeResult:
        run_id = f"run_{uuid.uuid4().hex[:12]}"

        reserved = RESERVED_PAYLOAD_KEYS & set(request.payload)
        if reserved:
            return self._failure(
                run_id=run_id,
                trusted=trusted,
                code=ErrorCode.INVALID_REQUEST,
                message="payload 含保留键；权限、项目范围与预算只能由可信上下文提供",
                details={"reserved": sorted(reserved)},
            )

        try:
            agent = self._registry.require_capability(request.capability)
        except CapabilityUnavailableError as exc:
            return self._failure(
                run_id=run_id,
                trusted=trusted,
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                message=str(exc),
            )
        except AgentDisabledError as exc:
            return self._failure(
                run_id=run_id,
                trusted=trusted,
                code=ErrorCode.AGENT_NOT_ENABLED,
                message=str(exc),
            )

        context: AgentContext = trusted.to_agent_context(run_id=run_id)
        result = await agent.handle(request, context)

        evidence: list[Evidence] = []
        warnings: list[str] = list(result.warnings)
        for raw in (result.output or {}).get("evidence", []) or []:
            try:
                evidence.append(Evidence.model_validate(raw))
            except Exception as exc:  # 证据结构不合法：不静默丢弃，记告警
                warnings.append(f"忽略结构非法的证据: {type(exc).__name__}")

        return RuntimeResult(
            run_id=run_id,
            trace_id=trusted.trace_id,
            status=result.status,
            output=result.output,
            evidence=tuple(evidence),
            tool_traces=self._traces_for_run(run_id),
            warnings=tuple(warnings),
            error=result.error,
            budget=self._budget.snapshot(),
            agent_result=result,
        )

    def _failure(
        self,
        *,
        run_id: str,
        trusted: TrustedContext,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> RuntimeResult:
        return RuntimeResult(
            run_id=run_id,
            trace_id=trusted.trace_id,
            status=TaskStatus.FAILED,
            output=None,
            evidence=(),
            tool_traces=self._traces_for_run(run_id),
            warnings=(),
            error=AgentErrorDetail(
                code=code,
                message=message,
                retryable=False,
                details=details or {},
            ),
            budget=self._budget.snapshot(),
            agent_result=None,
        )

    def _traces_for_run(self, run_id: str) -> tuple[ToolTrace, ...]:
        """只取本次 run 的 Trace。

        共享 TraceLog 仍是 append-only 的全局日志（并发 run 都往里追加），
        这里按 run_id 过滤，而不是清空共享日志——清空会让并发 run 丢数据（F2）。
        """

        return tuple(
            trace for trace in self._trace_log.snapshot() if trace.run_id == run_id
        )
