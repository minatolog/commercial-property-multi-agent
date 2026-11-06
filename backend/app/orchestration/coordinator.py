"""Coordinator 契约。

Coordinator 只做四件事：拆解任务、按能力选择 Agent、分配与回收、聚合结果。
它**不导入任何具体 Agent**，只通过 AgentRegistry 按 capability 取实例，
因此删除或替换一个 Agent 不需要修改 Coordinator。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from ..agents.base.contracts import (
    AgentContext,
    AgentRequest,
    AgentResult,
    TaskStatus,
)
from ..agents.base.errors import AgentDisabledError, CapabilityUnavailableError
from ..agents.base.registry import AgentRegistry
from .state import SubTask


class UnavailableCapabilityPolicy(StrEnum):
    """能力不可用时的处理方式。默认降级，但必须留下可见记录。"""

    FAIL_FAST = "fail_fast"
    DEGRADE = "degrade"
    ESCALATE_TO_HUMAN = "escalate_to_human"


@dataclass(frozen=True)
class CoordinatorPolicy:
    unavailable_capability: UnavailableCapabilityPolicy = (
        UnavailableCapabilityPolicy.DEGRADE
    )
    allow_partial_results: bool = True
    max_parallel_subtasks: int = 4


@dataclass(frozen=True)
class CapabilityPlan:
    """计划可行性检查结果，用于在执行前暴露缺口，而不是跑到一半才失败。"""

    available: dict[str, str] = field(default_factory=dict)  # capability -> agent name
    disabled: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = ()

    @property
    def feasible(self) -> bool:
        return not self.disabled and not self.missing


def check_plan_feasibility(registry: AgentRegistry, plan: list[SubTask]) -> CapabilityPlan:
    """在执行前判断每个子任务的能力是否真的有人提供。

    禁止"悄悄跳过"：缺失与禁用必须分别记录，交给上层决定失败、降级还是转人工。
    """
    available: dict[str, str] = {}
    disabled: dict[str, str] = {}
    missing: list[str] = []

    for subtask in plan:
        capability = subtask["capability"]
        try:
            agent = registry.require_capability(capability)
        except CapabilityUnavailableError:
            if capability not in missing:
                missing.append(capability)
            continue
        except AgentDisabledError:
            owner = registry.agent_for_capability(capability, enabled_only=False)
            disabled[capability] = owner.descriptor.name if owner else "<unknown>"
            continue
        available[capability] = agent.descriptor.name

    return CapabilityPlan(available=available, disabled=disabled, missing=tuple(missing))


@runtime_checkable
class CoordinatorProtocol(Protocol):
    async def build_plan(
        self, request: AgentRequest, context: AgentContext
    ) -> list[SubTask]: ...

    async def run(self, request: AgentRequest, context: AgentContext) -> AgentResult: ...


def summarize_results(
    results: list[AgentResult], *, allow_partial: bool
) -> TaskStatus:
    """聚合节点使用的状态判定，保持"部分成功"可见。

    K4/K5 修复后的语义（穷尽且单调）：

    | 全部结果的状态          | allow_partial=True | allow_partial=False |
    |---|---|---|
    | 空集                    | FAILED | FAILED |
    | 全部 SUCCESS            | SUCCESS | SUCCESS |
    | 全部 FAILED             | FAILED | FAILED |
    | 全部 SKIPPED            | FAILED（K5） | FAILED |
    | 其余（含 PARTIAL/SKIPPED 混合） | PARTIAL | FAILED（K4） |

    选择"全 SKIPPED → FAILED"而不是 PARTIAL：没有任何子任务产出成功结果时，
    把它报告为"部分成功"会掩盖"这一轮什么都没做成"，下游会把 FAILED 当缺口处理。
    """
    if not results:
        return TaskStatus.FAILED

    statuses = [result.status for result in results]
    if all(status is TaskStatus.SUCCESS for status in statuses):
        return TaskStatus.SUCCESS
    if all(status is TaskStatus.FAILED for status in statuses):
        return TaskStatus.FAILED
    if all(status is TaskStatus.SKIPPED for status in statuses):
        return TaskStatus.FAILED
    if not allow_partial:
        return TaskStatus.FAILED
    return TaskStatus.PARTIAL
