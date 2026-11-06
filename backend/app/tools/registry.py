"""工具白名单注册表。

安全设计：只接受**已经构造好的 `BaseTool` 实例**，拒绝任何模块路径字符串，
因此配置/数据里写什么都不会触发动态导入。重复工具名一律拒绝（不静默覆盖）。
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from ..agents.base.errors import (
    DuplicateToolError,
    IncompatibleToolError,
    ToolNotFoundError,
)
from .base import BaseTool

#: 工具名形如 `domain.action` 或 `domain.action.subaction`
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

__all__ = ["TOOL_NAME_PATTERN", "ToolRegistry"]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def register(self, tool: BaseTool, *, replace: bool = False) -> BaseTool:
        validated = _validated_tool(tool)
        tools = dict(self._tools)
        if validated.name in tools and not replace:
            raise DuplicateToolError(
                f"工具名重复: {validated.name!r}（替换必须显式传 replace=True）"
            )
        tools[validated.name] = validated
        # 原子发布：校验全部通过后才替换映射
        self._tools = tools
        return validated

    def unregister(self, name: str) -> None:
        tools = dict(self._tools)
        tools.pop(name, None)
        self._tools = tools

    def get(self, name: str) -> BaseTool:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotFoundError(
                f"工具未注册: {name!r}",
                details={"registered": sorted(self._tools)},
            )
        return tool

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._tools))

    def descriptors(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "name": tool.name,
                "version": tool.version,
                "description": tool.description,
                "required_permissions": sorted(tool.required_permissions),
                "timeout_seconds": tool.timeout_seconds,
                "max_attempts": tool.max_attempts,
            }
            for tool in (self._tools[name] for name in self.names())
        )


def _validated_tool(tool: Any) -> BaseTool:
    if not isinstance(tool, BaseTool):
        raise IncompatibleToolError(
            f"{type(tool).__name__} 不是 BaseTool 子类；工具必须显式继承 BaseTool"
        )
    if not TOOL_NAME_PATTERN.match(tool.name or ""):
        raise IncompatibleToolError(
            f"工具名必须形如 '<domain>.<action>'，收到: {tool.name!r}"
        )
    if not (tool.version or "").strip():
        raise IncompatibleToolError(f"工具 {tool.name!r} 缺少 version")
    if not isinstance(tool.required_permissions, frozenset):
        raise IncompatibleToolError(
            f"工具 {tool.name!r} 的 required_permissions 必须是 frozenset[str]"
        )
    if not all(isinstance(item, str) for item in tool.required_permissions):
        raise IncompatibleToolError(f"工具 {tool.name!r} 的权限项必须是字符串")
    if tool.timeout_seconds <= 0:
        raise IncompatibleToolError(f"工具 {tool.name!r} 的 timeout_seconds 必须 > 0")
    if not 1 <= tool.max_attempts <= 5:
        raise IncompatibleToolError(
            f"工具 {tool.name!r} 的 max_attempts 必须在 1..5 之间，收到 {tool.max_attempts}"
        )
    for attr in ("input_model", "output_model"):
        model = getattr(tool, attr, None)
        if not (isinstance(model, type) and issubclass(model, BaseModel)):
            raise IncompatibleToolError(
                f"工具 {tool.name!r} 的 {attr} 必须是 pydantic BaseModel 子类"
            )
    if not callable(getattr(tool, "invoke", None)):
        raise IncompatibleToolError(f"工具 {tool.name!r} 缺少可调用的 invoke 方法")
    return tool
