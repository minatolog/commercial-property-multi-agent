"""统一 Tool Executor。

所有工具调用必须经过这里；Agent 不得直接调用工具实现。执行顺序固定为：

1. 工具已注册（白名单）         -> `TOOL_NOT_FOUND`
2. Agent 的 `allowed_tools` 允许 -> `TOOL_NOT_ALLOWED`
3. 可信上下文具备所需权限       -> `PERMISSION_DENIED`
4. payload 不含保留键且通过 Schema -> `INVALID_TOOL_ARGUMENTS`
5. 预算预留（原子、并发安全）   -> `BUDGET_EXHAUSTED`
6. 受 `min(工具超时, 剩余 deadline)` 约束执行，可有限重试 -> `TOOL_TIMEOUT`
7. 输出 Schema 校验 + 项目范围校验 -> `INVALID_TOOL_RESULT` / `PERMISSION_DENIED`

预算按**逻辑调用**计一次：重试不重复扣减（`call_id` 幂等），失败也计一次。
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from ..agents.base.contracts import AgentContext, AgentErrorDetail
from ..agents.base.errors import (
    AgentError,
    BudgetExhaustedError,
    ErrorCode,
    InvalidToolArgumentsError,
    InvalidToolResultError,
    PermissionDeniedError,
    ProjectScopeDeniedError,
    ToolNotFoundError,
    ToolNotAllowedError,
    ToolTimeoutError,
)
from ..config.schema import AgentConfig
from ..runtime.budget import Budget
from ..runtime.types import (
    RESERVED_PAYLOAD_KEYS,
    Evidence,
    ToolExecution,
    ToolStatus,
    ToolTrace,
    TraceLog,
    canonical_json,
)
from .base import BaseTool, ToolInvocation, assert_permissions, assert_tool_allowed
from .registry import ToolRegistry

__all__ = ["ToolExecutor"]

_DENIED_CODES = frozenset(
    {
        ErrorCode.TOOL_NOT_FOUND,
        ErrorCode.TOOL_NOT_ALLOWED,
        ErrorCode.PERMISSION_DENIED,
        ErrorCode.PROJECT_SCOPE_DENIED,
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _status_for(code: ErrorCode) -> str:
    if code in _DENIED_CODES:
        return ToolStatus.DENIED
    if code is ErrorCode.BUDGET_EXHAUSTED:
        return ToolStatus.BUDGET_EXHAUSTED
    if code is ErrorCode.TOOL_TIMEOUT:
        return ToolStatus.TIMEOUT
    return ToolStatus.ERROR


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
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

    async def execute(
        self,
        tool_name: str,
        payload: dict[str, Any],
        *,
        context: AgentContext,
        agent_config: AgentConfig,
    ) -> ToolExecution:
        call_id = f"tc_{uuid.uuid4().hex[:12]}"
        started_at = _utcnow()
        started_perf = time.perf_counter()
        args_digest = hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()[:16]
        traces: list[ToolTrace] = []

        def record(status: str, attempt: int, error_code: ErrorCode | None = None) -> None:
            trace = ToolTrace(
                call_id=call_id,
                trace_id=context.trace_id,
                run_id=context.run_id,
                tool_name=tool_name,
                args_digest=args_digest,
                status=status,
                error_code=error_code.value if error_code is not None else None,
                attempt=attempt,
                duration_ms=round((time.perf_counter() - started_perf) * 1000, 2),
                started_at=started_at,
            )
            traces.append(trace)
            self._trace_log.add(trace)

        def failure(
            code: ErrorCode,
            message: str,
            *,
            attempt: int = 0,
            details: dict[str, Any] | None = None,
            retryable: bool = False,
        ) -> ToolExecution:
            record(_status_for(code), attempt, code)
            return ToolExecution(
                call_id=call_id,
                tool_name=tool_name,
                status=_status_for(code),
                error=AgentErrorDetail(
                    code=code,
                    message=message,
                    retryable=retryable,
                    details=details or {},
                ),
                attempts=attempt,
                duration_ms=round((time.perf_counter() - started_perf) * 1000, 2),
                traces=tuple(traces),
            )

        # 1-4：静态检查（都不消耗预算，也不触发工具执行）
        if RESERVED_PAYLOAD_KEYS & set(payload):
            return failure(
                ErrorCode.INVALID_TOOL_ARGUMENTS,
                "payload 含保留键，权限/项目范围/预算只能由可信上下文提供",
                details={"reserved": sorted(RESERVED_PAYLOAD_KEYS & set(payload))},
            )

        try:
            tool = self._registry.get(tool_name)
        except ToolNotFoundError as exc:
            return failure(exc.code, exc.message, details=exc.details)

        try:
            assert_tool_allowed(agent_config, tool.name)
            assert_permissions(tool, context)
        except (ToolNotAllowedError, PermissionDeniedError) as exc:
            return failure(exc.code, exc.message, details=exc.details)

        try:
            parsed = tool.input_model.model_validate(payload)
        except ValidationError as exc:
            return failure(
                ErrorCode.INVALID_TOOL_ARGUMENTS,
                f"工具 {tool_name!r} 参数校验失败",
                details={
                    "errors": [
                        {"loc": list(err["loc"]), "msg": err["msg"]}
                        for err in exc.errors()
                    ]
                },
            )

        # 5：预算预留（原子；失败不消耗）
        try:
            await self._budget.reserve_tool_call(call_id)
        except BudgetExhaustedError as exc:
            return failure(exc.code, exc.message, details=exc.details)

        reserved = True
        try:
            return await self._run_with_retry(
                tool=tool,
                parsed=parsed,
                context=context,
                call_id=call_id,
                record=record,
                failure=failure,
                traces=traces,
            )
        finally:
            if reserved:
                await self._budget.settle(call_id)

    async def _run_with_retry(
        self,
        *,
        tool: BaseTool,
        parsed: Any,
        context: AgentContext,
        call_id: str,
        record,
        failure,
        traces: list[ToolTrace],
    ) -> ToolExecution:
        last_error: AgentError | None = None
        for attempt in range(1, tool.max_attempts + 1):
            remaining = self._remaining_seconds(context)
            if remaining is not None and remaining <= 0:
                return failure(
                    ErrorCode.DEADLINE_EXCEEDED,
                    "上游 deadline 已到，工具调用中止",
                    attempt=attempt - 1,
                    details={"attempts": attempt - 1},
                )
            timeout = (
                tool.timeout_seconds
                if remaining is None
                else min(tool.timeout_seconds, remaining)
            )
            try:
                invocation = await asyncio.wait_for(
                    tool.invoke(parsed, context), timeout=max(timeout, 0.001)
                )
            except asyncio.TimeoutError:
                last_error = ToolTimeoutError(
                    f"工具 {tool.name!r} 第 {attempt} 次调用超时（{timeout:.3f}s）",
                    details={"attempt": attempt, "timeout_seconds": round(timeout, 3)},
                )
                if self._should_retry(attempt, tool, context):
                    record(ToolStatus.TIMEOUT, attempt, ErrorCode.TOOL_TIMEOUT)
                    continue
                return failure(
                    ErrorCode.TOOL_TIMEOUT,
                    last_error.message,
                    attempt=attempt,
                    details=last_error.details,
                    retryable=False,
                )
            except AgentError as exc:
                last_error = exc
                if self._should_retry(attempt, tool, context) and exc.retryable:
                    record(_status_for(exc.code), attempt, exc.code)
                    continue
                return failure(
                    exc.code,
                    exc.message,
                    attempt=attempt,
                    details=exc.details,
                    retryable=exc.retryable,
                )
            except Exception as exc:  # 工具内部未收敛异常：不吞，转稳定错误码
                return failure(
                    ErrorCode.INTERNAL_ERROR,
                    f"工具 {tool.name!r} 抛出未处理异常: {type(exc).__name__}: {exc}",
                    attempt=attempt,
                )

            return self._finish_success(
                tool=tool,
                invocation=invocation,
                context=context,
                call_id=call_id,
                attempt=attempt,
                record=record,
                failure=failure,
                traces=traces,
            )

        # 理论不可达：循环内一定会 return
        return failure(
            ErrorCode.TOOL_TIMEOUT,
            last_error.message if last_error else "工具调用失败",
            attempt=tool.max_attempts,
        )

    def _finish_success(
        self,
        *,
        tool: BaseTool,
        invocation: ToolInvocation,
        context: AgentContext,
        call_id: str,
        attempt: int,
        record,
        failure,
        traces: list[ToolTrace],
    ) -> ToolExecution:
        try:
            validated = tool.output_model.model_validate(invocation.data)
        except ValidationError as exc:
            return failure(
                ErrorCode.INVALID_TOOL_RESULT,
                f"工具 {tool.name!r} 输出未通过 Schema 校验",
                attempt=attempt,
                details={
                    "errors": [
                        {"loc": list(err["loc"]), "msg": err["msg"]}
                        for err in exc.errors()
                    ]
                },
            )

        evidence: list[Evidence] = []
        for draft in invocation.evidence:
            if draft.project_id not in context.project_ids:
                return failure(
                    ErrorCode.PERMISSION_DENIED,
                    f"工具 {tool.name!r} 返回了项目范围外的证据: {draft.evidence_id!r}",
                    attempt=attempt,
                    details={"evidence_id": draft.evidence_id, "project_id": draft.project_id},
                )
            evidence.append(
                Evidence.materialize(
                    draft,
                    source_tool=tool.name,
                    tool_call_id=call_id,
                )
            )

        record(ToolStatus.OK, attempt)
        return ToolExecution(
            call_id=call_id,
            tool_name=tool.name,
            status=ToolStatus.OK,
            data=validated.model_dump(mode="json"),
            evidence=tuple(evidence),
            attempts=attempt,
            duration_ms=traces[-1].duration_ms if traces else 0.0,
            traces=tuple(traces),
        )

    @staticmethod
    def _remaining_seconds(context: AgentContext) -> float | None:
        if context.deadline_at is None:
            return None
        return (context.deadline_at - _utcnow()).total_seconds()

    @classmethod
    def _should_retry(cls, attempt: int, tool: BaseTool, context: AgentContext) -> bool:
        if attempt >= tool.max_attempts:
            return False
        remaining = cls._remaining_seconds(context)
        return remaining is None or remaining > 0
