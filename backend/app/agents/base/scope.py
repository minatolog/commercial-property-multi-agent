"""任务可信约束（Task 021 / N2、N3、N5）：模型不能扩大目标或丢掉筛选条件。

问题背景：确定性 Agent 把目标写死在代码里，所以"给 A-301 的调查不会拿 B-101 的数据"
是结构性的。换成模型选工具后，这条保证消失了：

- 模型可以调用**有权限但错实体**的工具（N2）；
- 模型可以省略 `document_ids`，让检索扩大到整个项目（N3）；
- 模型可以丢掉 planner 给出的 `category` 等硬筛选条件（N5）。

这里的做法：把 `TaskScope` 作为**可信输入**（来自 planner / 装配层），在工具调用边界
强制执行，而不是只写进提示词求模型遵守。

三条规则：

1. 目标（lease/unit）与硬筛选条件由 scope 决定：模型给错 → 拒绝该次调用并反馈错误；
   模型省略 → 直接注入，而不是"放行成不限"；
2. 结果归并前再校验一次实体归属（纵深防御，且能发现工具实现自身的不一致）；
3. 确定性引擎与 LLM 引擎共用同一套 `TaskScope`，避免两套规则各自漂移。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

__all__ = ["TaskScope", "SCOPE_GUARDED_FIELDS"]


#: 由 scope 强制管理的参数名：出现这些字段的工具，其取值必须来自可信计划。
SCOPE_GUARDED_FIELDS: tuple[str, ...] = ("lease_id", "unit_id", "category")


@dataclass(frozen=True)
class TaskScope:
    """一次子任务允许的目标与筛选条件。"""

    lease_id: str | None = None
    unit_id: str | None = None
    #: 硬筛选条件（如 `{"category": "hvac"}`）：模型不能丢弃，也不能改写
    filters: Mapping[str, str] = field(default_factory=dict)
    #: 原问题/领域子问题：让模型知道"在回答什么"，而不是只看能力名
    question: str = ""

    # ---------------- 参数约束 ----------------

    def apply_arguments(
        self, tool_name: str, input_fields: set[str], arguments: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        """返回 (最终参数, 拒绝原因)。拒绝原因非空表示这次调用不应执行。"""

        final = dict(arguments)
        expected: dict[str, str] = {}
        if "lease_id" in input_fields and self.lease_id:
            expected["lease_id"] = self.lease_id
        if "unit_id" in input_fields and self.unit_id:
            expected["unit_id"] = self.unit_id
        for key, value in self.filters.items():
            if key in input_fields:
                expected[key] = str(value)

        for key, wanted in expected.items():
            given = final.get(key)
            if given is None or given == "":
                # 模型省略 → 注入可信值（不是"不限"）
                final[key] = wanted
                continue
            if str(given) != wanted:
                return None, (
                    f"参数 {key}={given!r} 超出本次任务范围（应为 {wanted!r}）；"
                    f"工具 {tool_name} 的调用已被拒绝"
                )
        return final, None

    # ---------------- 结果约束 ----------------

    def accepts_output(self, tool_name: str, data: Mapping[str, Any]) -> str | None:
        """校验工具输出是否仍属于本次任务的目标；返回拒绝原因或 None。"""

        if self.lease_id and data.get("lease_id"):
            if str(data["lease_id"]) != self.lease_id:
                return (
                    f"工具 {tool_name} 返回了租约 {data['lease_id']!r} 的数据，"
                    f"但本次任务的目标是 {self.lease_id!r}"
                )
        if self.unit_id and data.get("unit_id"):
            if str(data["unit_id"]) != self.unit_id:
                return (
                    f"工具 {tool_name} 返回了商铺 {data['unit_id']!r} 的数据，"
                    f"但本次任务的目标是 {self.unit_id!r}"
                )
        return None

    def describe(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "unit_id": self.unit_id,
            "filters": dict(self.filters),
        }
