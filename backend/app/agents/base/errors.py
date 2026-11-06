"""Agent 错误约定。

每个错误都必须能回答两个问题：属于哪一类、能不能重试。
Coordinator 依赖这两点决定重试、降级还是转人工，而不是靠字符串匹配。
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_CONTEXT = "invalid_context"
    CAPABILITY_NOT_DECLARED = "capability_not_declared"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    AGENT_NOT_ENABLED = "agent_not_enabled"
    AGENT_NOT_REGISTERED = "agent_not_registered"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    TOOL_NOT_FOUND = "tool_not_found"
    INVALID_TOOL_ARGUMENTS = "invalid_tool_arguments"
    INVALID_TOOL_RESULT = "invalid_tool_result"
    TOOL_TIMEOUT = "tool_timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    PERMISSION_DENIED = "permission_denied"
    PROJECT_SCOPE_DENIED = "project_scope_denied"
    RECORD_NOT_FOUND = "record_not_found"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    TIMEOUT = "timeout"
    MODEL_ERROR = "model_error"
    UPSTREAM_ERROR = "upstream_error"
    NOT_IMPLEMENTED = "not_implemented"
    INTERNAL_ERROR = "internal_error"


RETRYABLE_CODES: frozenset[ErrorCode] = frozenset(
    {ErrorCode.TIMEOUT, ErrorCode.TOOL_TIMEOUT, ErrorCode.MODEL_ERROR, ErrorCode.UPSTREAM_ERROR}
)


class AgentError(Exception):
    """Agent 执行期统一异常。BaseAgent 会把它转换为结构化的失败结果。

    子类通过覆盖 `default_code` 获得专属错误码，因此调用时第一个位置参数
    始终是 message：`ToolNotAllowedError("工具未授权")`。
    """

    default_code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        message: str = "",
        *,
        code: ErrorCode | None = None,
        retryable: bool | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code or self.default_code
        self.message = message or self.code.value
        super().__init__(self.message)
        self.retryable = self.code in RETRYABLE_CODES if retryable is None else retryable
        self.details: dict[str, Any] = dict(details or {})

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ConfigError(Exception):
    """配置层错误。与 AgentError 分开，因为配置错误属于启动期问题，不应被重试掩盖。"""


class AgentConfigError(ConfigError):
    pass


class AgentConfigMismatchError(AgentConfigError):
    """配置声明的版本/能力与该 Agent 实现类的类属性不一致（K2）。"""


class PromptPathError(AgentConfigError):
    pass


class RegistryError(Exception):
    pass


class DuplicateAgentError(RegistryError):
    pass


class CapabilityConflictError(RegistryError):
    pass


class IncompatibleAgentError(RegistryError):
    pass


class AgentNotRegisteredError(RegistryError):
    pass


class CapabilityUnavailableError(RegistryError):
    """能力没有任何 Agent 声明。"""


class AgentDisabledError(RegistryError):
    """能力有 Agent 声明，但该 Agent 被配置禁用。"""


class ToolNotAllowedError(AgentError):
    default_code = ErrorCode.TOOL_NOT_ALLOWED


class PermissionDeniedError(AgentError):
    default_code = ErrorCode.PERMISSION_DENIED


class UnsupportedProviderError(ConfigError):
    pass


class MissingApiKeyError(ConfigError):
    pass


class ToolNotFoundError(AgentError):
    """工具未在 ToolRegistry 注册。"""

    default_code = ErrorCode.TOOL_NOT_FOUND


class ToolTimeoutError(AgentError):
    default_code = ErrorCode.TOOL_TIMEOUT


class InvalidToolArgumentsError(AgentError):
    default_code = ErrorCode.INVALID_TOOL_ARGUMENTS


class InvalidToolResultError(AgentError):
    default_code = ErrorCode.INVALID_TOOL_RESULT


class BudgetExhaustedError(AgentError):
    default_code = ErrorCode.BUDGET_EXHAUSTED


class ProjectScopeDeniedError(AgentError):
    """请求的数据属于当前可信上下文未授权的项目。"""

    default_code = ErrorCode.PROJECT_SCOPE_DENIED


class RecordNotFoundError(AgentError):
    default_code = ErrorCode.RECORD_NOT_FOUND


class ToolRegistryError(Exception):
    """工具注册期错误，与执行期 AgentError 分开。"""


class DuplicateToolError(ToolRegistryError):
    pass


class IncompatibleToolError(ToolRegistryError):
    pass
