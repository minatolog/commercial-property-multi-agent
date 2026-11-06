"""业务工具契约。

确定性计算（收费、账期、风险规则）必须是普通 Python 代码，不能交给 LLM 自由生成。
工具与 Agent 分离：Agent 只负责决策与调用，工具负责可测试的确定性执行。

任务 007 增量：新增 `BaseTool`（带严格输入/输出 Schema、权限、超时与重试上限）
与 `ToolInvocation`（工具产出 = 业务数据 + 证据草稿）。既有 `ToolProtocol`
与 `assert_*` 辅助函数保持兼容，旧调用方无需修改。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..agents.base.contracts import AgentContext
from ..agents.base.errors import PermissionDeniedError, ToolNotAllowedError
from ..config.schema import AgentConfig
from ..runtime.types import EvidenceDraft


@runtime_checkable
class ToolProtocol(Protocol):
    name: ClassVar[str]
    description: ClassVar[str]
    required_permissions: ClassVar[frozenset[str]]

    async def invoke(self, payload: dict[str, Any], context: AgentContext) -> dict[str, Any]: ...


class ToolInvocation(BaseModel):
    """工具执行产出：业务数据 + 证据草稿。

    证据的来源字段（工具名、调用 ID、采集时刻、合成标记）由执行器补齐，
    工具只声明"引用了哪条记录、依赖哪些字段"。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    data: dict[str, Any] = Field(default_factory=dict)
    evidence: tuple[EvidenceDraft, ...] = ()


class BaseTool(ABC):
    """只读业务工具基类。

    子类只声明元数据、输入/输出模型与 `invoke()`；
    白名单、权限、参数校验、超时、重试、预算与 Trace 全部由 `ToolExecutor` 统一处理。
    """

    name: ClassVar[str] = ""
    version: ClassVar[str] = "1.0.0"
    description: ClassVar[str] = ""
    required_permissions: ClassVar[frozenset[str]] = frozenset()
    timeout_seconds: ClassVar[float] = 5.0
    max_attempts: ClassVar[int] = 1

    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    async def invoke(self, payload: BaseModel, context: AgentContext) -> ToolInvocation:
        """执行只读查询。不得写文件/数据库/网络，不得返回 ORM 或连接对象。"""


def assert_tool_allowed(config: AgentConfig, tool_name: str) -> None:
    """Agent 只能调用自己 YAML 中 allowed_tools 显式列出的工具。"""
    if tool_name not in config.allowed_tools:
        raise ToolNotAllowedError(
            f"Agent {config.name!r} 未被授权调用工具 {tool_name!r}",
            details={"allowed_tools": list(config.allowed_tools)},
        )


def assert_permissions(tool: ToolProtocol, context: AgentContext) -> None:
    missing = sorted(tool.required_permissions - context.permissions)
    if missing:
        raise PermissionDeniedError(
            f"工具 {tool.name!r} 需要权限 {missing}，当前调用方不具备",
            details={"required": sorted(tool.required_permissions)},
        )


def assert_tool_invocable(
    config: AgentConfig, tool: ToolProtocol, context: AgentContext
) -> None:
    assert_tool_allowed(config, tool.name)
    assert_permissions(tool, context)


__all__ = [
    "BaseTool",
    "ToolInvocation",
    "ToolProtocol",
    "assert_permissions",
    "assert_tool_allowed",
    "assert_tool_invocable",
]
