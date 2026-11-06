"""BaseAgent：把横切关注点收敛到一处，子类只写业务。

子类需要做的事只有两件：
1. 声明类属性 name / version / capabilities / description。
2. 实现 _execute()，返回 AgentOutput。

超时、重试、错误映射、耗时统计、日志字段全部由基类处理，
因此任意两个 Agent 的可观测性字段天然一致。
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

from .contracts import (
    AgentContext,
    AgentDescriptor,
    AgentErrorDetail,
    AgentOutput,
    AgentRequest,
    AgentResult,
    ExecutionMetadata,
    TaskStatus,
    TokenUsage,
    utcnow,
)
from .errors import AgentError, ErrorCode, IncompatibleAgentError, PromptPathError

if TYPE_CHECKING:
    from ...config.schema import AgentConfig


class BaseAgent(ABC):
    name: ClassVar[str] = ""
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = ""
    capabilities: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, config: "AgentConfig") -> None:
        if not self.name:
            raise IncompatibleAgentError(f"{type(self).__name__} 未声明 name")
        if not self.capabilities:
            raise IncompatibleAgentError(f"{type(self).__name__} 未声明 capabilities")
        self._config = config
        self._logger = logging.getLogger(f"agent.{self.name}")
        self._prompt_cache: str | None = None

    @property
    def config(self) -> "AgentConfig":
        return self._config

    @property
    def prompt_text(self) -> str:
        """按 config.prompt_path 惰性加载 Prompt。

        Prompt 与代码分离存放，改 Prompt 不需要改 Python 文件，
        也不会影响其他 Agent 的 Prompt。
        """
        if self._prompt_cache is None:
            from ...paths import resolve_project_path

            path = resolve_project_path(self._config.prompt_path)
            if not path.is_file():
                raise PromptPathError(f"Prompt 文件不存在: {path}")
            self._prompt_cache = path.read_text(encoding="utf-8")
        return self._prompt_cache

    @property
    def descriptor(self) -> AgentDescriptor:
        return AgentDescriptor(
            name=self.name,
            version=self.version,
            description=self.description,
            capabilities=frozenset(self.capabilities),
            enabled=self._config.enabled,
        )

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    async def handle(self, request: AgentRequest, context: AgentContext) -> AgentResult:
        started_at = utcnow()
        started_perf = time.perf_counter()

        if not self._config.enabled:
            return self._failure(
                request,
                context,
                AgentError(
                    f"Agent {self.name!r} 在配置中已被禁用",
                    code=ErrorCode.AGENT_NOT_ENABLED,
                    retryable=False,
                ),
                started_at,
                started_perf,
                attempt=0,
            )

        if not self.supports(request.capability):
            return self._failure(
                request,
                context,
                AgentError(
                    f"Agent {self.name!r} 未声明能力 {request.capability!r}",
                    code=ErrorCode.CAPABILITY_NOT_DECLARED,
                    retryable=False,
                    details={"declared": sorted(self.capabilities)},
                ),
                started_at,
                started_perf,
                attempt=0,
            )

        attempt = 0
        last_error: AgentError | None = None

        # K3：单次执行必须受 min(配置超时, 剩余 deadline) 约束；重试也不得越过 deadline。
        while attempt <= self._config.max_retries:
            remaining = self._remaining_seconds(context)
            if remaining is not None and remaining <= 0:
                last_error = AgentError(
                    "上游给定的截止时间已过",
                    code=ErrorCode.DEADLINE_EXCEEDED,
                    retryable=False,
                    details={
                        "deadline_at": context.deadline_at.isoformat()
                        if context.deadline_at is not None
                        else None
                    },
                )
                break

            attempt += 1
            timeout = (
                self._config.timeout_seconds
                if remaining is None
                else min(self._config.timeout_seconds, remaining)
            )
            try:
                output = await asyncio.wait_for(
                    self._execute(request, context),
                    timeout=max(timeout, 0.001),
                )
                return self._success(request, context, output, started_at, started_perf, attempt)
            except asyncio.TimeoutError:
                deadline_left = self._remaining_seconds(context)
                if deadline_left is not None and deadline_left <= 0:
                    last_error = AgentError(
                        "执行在上游截止时间处被中止",
                        code=ErrorCode.DEADLINE_EXCEEDED,
                        retryable=False,
                        details={"attempt": attempt},
                    )
                    break
                last_error = AgentError(
                    f"执行超过 {timeout:.3f}s",
                    code=ErrorCode.TIMEOUT,
                    retryable=True,
                    details={"attempt": attempt, "timeout_seconds": round(timeout, 3)},
                )
            except AgentError as exc:
                last_error = exc
                if not exc.retryable:
                    break
            except Exception as exc:  # 子类未捕获的异常一律收敛，避免拖垮整条工作流
                self._logger.exception(
                    "agent 执行抛出未处理异常",
                    extra=self._log_fields(context, attempt, started_perf),
                )
                last_error = AgentError(
                    f"{type(exc).__name__}: {exc}",
                    code=ErrorCode.INTERNAL_ERROR,
                    retryable=False,
                )
                break

        return self._failure(
            request,
            context,
            last_error or AgentError("未知错误", code=ErrorCode.INTERNAL_ERROR),
            started_at,
            started_perf,
            attempt,
        )

    @abstractmethod
    async def _execute(self, request: AgentRequest, context: AgentContext) -> AgentOutput:
        """子类实现业务逻辑。只返回业务产出，不构造 AgentResult。"""

    def _remaining_seconds(self, context: AgentContext) -> float | None:
        """距上游 deadline 的剩余秒数；无 deadline 时返回 None。"""
        if context.deadline_at is None:
            return None
        return (context.deadline_at - utcnow()).total_seconds()

    def _assert_deadline(self, context: AgentContext) -> None:
        remaining = self._remaining_seconds(context)
        if remaining is not None and remaining <= 0:
            raise AgentError(
                "上游给定的截止时间已过",
                code=ErrorCode.DEADLINE_EXCEEDED,
                retryable=False,
                details={"deadline_at": context.deadline_at.isoformat()},
            )

    def _log_fields(
        self, context: AgentContext, attempt: int, started_perf: float
    ) -> dict[str, object]:
        return {
            "agent_name": self.name,
            "agent_version": self.version,
            "model_provider": self._config.model_provider,
            "model_name": self._config.model_name,
            "trace_id": context.trace_id,
            "tenant_id": context.tenant_id,
            "attempt": attempt,
            "latency_ms": round((time.perf_counter() - started_perf) * 1000, 2),
        }

    def _metadata(
        self,
        context: AgentContext,
        started_at,
        started_perf: float,
        attempt: int,
        token_usage: TokenUsage | None = None,
    ) -> ExecutionMetadata:
        return ExecutionMetadata(
            agent_name=self.name,
            agent_version=self.version,
            trace_id=context.trace_id,
            model_provider=self._config.model_provider,
            model_name=self._config.model_name,
            latency_ms=round((time.perf_counter() - started_perf) * 1000, 2),
            attempt=attempt,
            token_usage=token_usage,
            started_at=started_at,
            finished_at=utcnow(),
        )

    def _success(
        self,
        request: AgentRequest,
        context: AgentContext,
        output: AgentOutput,
        started_at,
        started_perf: float,
        attempt: int,
    ) -> AgentResult:
        metadata = self._metadata(context, started_at, started_perf, attempt, output.token_usage)
        self._logger.info(
            "agent 执行成功",
            extra=self._log_fields(context, attempt, started_perf),
        )
        return AgentResult(
            request_id=request.request_id,
            status=TaskStatus.PARTIAL if output.warnings else TaskStatus.SUCCESS,
            output=output.data,
            warnings=output.warnings,
            metadata=metadata,
        )

    def _failure(
        self,
        request: AgentRequest,
        context: AgentContext,
        error: AgentError,
        started_at,
        started_perf: float,
        attempt: int,
    ) -> AgentResult:
        metadata = self._metadata(context, started_at, started_perf, attempt)
        self._logger.warning(
            "agent 执行失败",
            extra={**self._log_fields(context, attempt, started_perf), "error_code": error.code},
        )
        return AgentResult(
            request_id=request.request_id,
            status=TaskStatus.FAILED,
            error=AgentErrorDetail(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                details=error.details,
            ),
            metadata=metadata,
        )
