"""工具驱动的 Agent 基类（Task 009）。

领域 Agent（Lease / Billing / Property）本身**不做推断**：它们只负责
"把业务问题翻译成一次受控工具调用，并把结构化结果 + 证据返回"。

这样做的原因：

- 金额、日期、状态必须来自确定性工具，不能由 LLM 生成；
- Agent 与工具解耦：Agent 不知道 fixture / 数据库的实现，只认工具契约；
- 每个 Agent 可独立测试（注入 ToolRegistry 即可，不需要图、模型或数据库）。
"""

from __future__ import annotations

from typing import Any

from .base_agent import BaseAgent
from ..base.errors import AgentError, ErrorCode
from ...config.schema import AgentConfig
from ...runtime.budget import Budget
from ...runtime.types import TraceLog, ToolExecution
from ...tools.executor import ToolExecutor
from ...tools.registry import ToolRegistry


class ToolBackedAgent(BaseAgent):
    """提供 `_invoke_tool()` 的领域 Agent 基类。"""

    def __init__(
        self,
        config: AgentConfig,
        *,
        tool_registry: ToolRegistry | None = None,
        budget: Budget | None = None,
        trace_log: TraceLog | None = None,
    ) -> None:
        super().__init__(config)
        self._tool_registry = tool_registry
        self._budget = budget
        self._trace_log = trace_log if trace_log is not None else TraceLog()

    async def _invoke_tool(
        self, tool_name: str, payload: dict[str, Any], context: Any
    ) -> ToolExecution:
        if self._tool_registry is None:
            raise AgentError(
                f"{type(self).__name__} 未注入 tool_registry",
                code=ErrorCode.INVALID_CONTEXT,
                retryable=False,
            )
        executor = ToolExecutor(
            self._tool_registry,
            self._budget if self._budget is not None else Budget(max_tool_calls=0),
            trace_log=self._trace_log,
        )
        execution = await executor.execute(
            tool_name, payload, context=context, agent_config=self.config
        )
        if not execution.ok:
            assert execution.error is not None
            raise AgentError(
                execution.error.message,
                code=execution.error.code,
                retryable=False,
                details={"call_id": execution.call_id, **execution.error.details},
            )
        return execution

    @staticmethod
    def _evidence_payload(execution: ToolExecution) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in execution.evidence]
