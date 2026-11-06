"""Agent 基础设施：接口、契约、注册表。

业务 Agent 只需 import 本包，不要 import 具体实现模块。
"""

from .base_agent import BaseAgent
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
from .errors import ErrorCode
from .protocol import AgentProtocol
from .registry import AgentRegistry

__all__ = [
    "AgentContext",
    "AgentDescriptor",
    "AgentErrorDetail",
    "AgentOutput",
    "AgentProtocol",
    "AgentRegistry",
    "AgentRequest",
    "AgentResult",
    "BaseAgent",
    "ErrorCode",
    "ExecutionMetadata",
    "TaskStatus",
    "TokenUsage",
    "utcnow",
]
