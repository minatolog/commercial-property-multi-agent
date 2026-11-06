"""Agent 输入输出契约。

所有 Agent 只通过这里的类型与外界交互，不得暴露内部实现类型。
改动本文件的任何字段都属于**破坏性变更**，必须同步检查全部 Agent 与工作流。
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import ErrorCode

CAPABILITY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AgentDescriptor(BaseModel):
    """Agent 的自我描述。Registry 与 Coordinator 只依赖这个结构做发现与选择。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1, max_length=32)
    description: str = ""
    capabilities: frozenset[str] = Field(min_length=1)
    enabled: bool = True

    @field_validator("capabilities")
    @classmethod
    def _validate_capabilities(cls, value: frozenset[str]) -> frozenset[str]:
        invalid = sorted(c for c in value if not CAPABILITY_PATTERN.match(c))
        if invalid:
            raise ValueError(
                f"capability 必须形如 '<domain>.<action>'，非法值: {invalid}"
            )
        return value


class AgentContext(BaseModel):
    """单次调用的执行上下文。

    与 payload 分离存放，使 Agent 只关心业务输入，而权限、多租户、超时等
    横切关注点由上层统一注入。

    任务 007 增量（全部有默认值，向后兼容）：`principal_id` 与 `project_ids`
    是**可信上下文**的一部分，只能由 Runtime 从已认证会话/可信主体注入，
    绝不允许从 `AgentRequest.payload` 或模型输出推导。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    trace_id: str = Field(min_length=1)
    run_id: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    permissions: frozenset[str] = frozenset()
    principal_id: str | None = None
    project_ids: frozenset[str] = frozenset()
    #: Task 009：图中并发子任务的标识，仅用于 Trace 归属与结果归并
    subtask_id: str | None = None
    deadline_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID = Field(default_factory=uuid4)
    task_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("capability")
    @classmethod
    def _validate_capability(cls, value: str) -> str:
        if not CAPABILITY_PATTERN.match(value):
            raise ValueError(f"capability 必须形如 '<domain>.<action>'，收到: {value!r}")
        return value


class AgentOutput(BaseModel):
    """Agent 内部 `_execute` 的返回值。

    Agent 只负责产出业务数据，元数据（延迟、模型、trace）由 BaseAgent 统一填充，
    避免每个 Agent 各写一套可观测性逻辑。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    data: dict[str, Any] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    token_usage: TokenUsage | None = None


class AgentErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: ErrorCode
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    agent_name: str
    agent_version: str
    trace_id: str
    model_provider: str | None = None
    model_name: str | None = None
    latency_ms: float = 0.0
    attempt: int = 1
    token_usage: TokenUsage | None = None
    started_at: datetime
    finished_at: datetime


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    request_id: UUID
    status: TaskStatus
    output: dict[str, Any] | None = None
    error: AgentErrorDetail | None = None
    warnings: tuple[str, ...] = ()
    metadata: ExecutionMetadata

    @property
    def ok(self) -> bool:
        return self.status is TaskStatus.SUCCESS
