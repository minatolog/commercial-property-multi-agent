"""LangGraph 共享状态契约。

设计约束：
1. 共享 State 只保存**跨节点**需要的信息。Agent 内部的中间变量必须是局部变量，
   不要往 State 里塞。
2. 所有可被并发更新的字段都必须是 `Annotated[..., reducer]`，由 LangGraph 在合并
   并发写入时调用 reducer；没有 reducer 的字段在并发下会抛冲突，属于有意的保护。
3. 本模块**不导入 langgraph**，只定义类型，因此可以在依赖安装前被导入与测试。

注意：未安装 langgraph 时 `Annotated` 的 reducer 不会被解释，仅作类型声明使用。
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class SubTask(TypedDict):
    """Coordinator 拆解出的最小执行单元。"""

    subtask_id: str
    capability: str
    payload: dict[str, Any]
    depends_on: list[str]


class WorkflowState(TypedDict, total=False):
    # --- 只读上下文 ---
    task_id: str
    trace_id: str
    tenant_id: str | None
    user_request: dict[str, Any]

    # --- 计划阶段产出 ---
    plan: list[SubTask]

    # --- 执行阶段：并发节点只追加，绝不覆盖 ---
    # 元素为 AgentResult.model_dump(mode="json")，保证可被 checkpointer 序列化
    results: Annotated[list[dict[str, Any]], operator.add]
    warnings: Annotated[list[str], operator.add]
    failures: Annotated[list[dict[str, Any]], operator.add]

    # --- 汇总阶段：只允许在单点（聚合节点）写入，避免并发覆盖 ---
    final_output: dict[str, Any] | None


# 合并策略说明（供实现时遵守，不是可执行代码）：
# - results / warnings / failures：`operator.add`，追加式合并，天然无冲突。
# - plan / final_output：只在单一节点写入，不做并发合并。
# - 同一 subtask 重复出现时，以 subtask_id 去重，保留最后一次成功结果；
#   该去重必须在聚合节点显式实现，不能依赖 reducer 的隐式行为。
MERGE_POLICY = {
    "results": "append",
    "warnings": "append",
    "failures": "append",
    "plan": "exclusive-writer",
    "final_output": "exclusive-writer",
}
