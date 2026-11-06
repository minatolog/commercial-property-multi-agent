"""任务可信约束（Task 021 N2/N3/N5，Task 024 Q2）：模型不能扩大目标或丢掉筛选条件。

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
3. 确定性引擎与 LLM 引擎、单 Agent 与多 Agent **共用同一套** `TaskScope`
   （`TaskScope.from_payload` + `scope_arguments_hook`），避免多份规则各自漂移。

三种任务形态（Task 024 / Q2）：

| 形态 | 判定 | 约束 |
|---|---|---|
| `targeted` | payload 带 `lease_id` 或 `unit_id` | 注入/拒绝目标，校验输出归属；有目标业务查询必须有取证 |
| `compare` | payload 带多个 `lease_ids` | 只允许集合内的租约；模型必须自己点名，不能猜 |
| `explain` | 三者都没有 | 不设目标约束（纯说明任务允许不取数） |
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

__all__ = [
    "TaskScope",
    "SCOPE_GUARDED_FIELDS",
    "scope_arguments_hook",
]


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
    #: 显式多目标比较：允许的租约集合。非空且多于一个时进入 `compare` 形态。
    lease_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        """单一目标也要落到 `lease_ids`：否则"输出归属校验"会有两条取值路径。"""

        if self.lease_id and not self.lease_ids:
            object.__setattr__(self, "lease_ids", frozenset({self.lease_id}))

    # ---------------- 构造 ----------------

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "TaskScope":
        """从**可信 payload**（planner / 装配层）构造范围。

        这是唯一的构造入口：领域 Agent、单 Agent 与 B 基线都用它，
        因此"模型能改哪些字段"只有一份定义。
        """

        data: Mapping[str, Any] = payload or {}
        filters: dict[str, str] = {}
        for key in ("category", "status"):
            value = str(data.get(key) or "").strip()
            if value:
                filters[key] = value

        lease_ids = frozenset(
            str(item).strip()
            for item in (data.get("lease_ids") or ())
            if str(item).strip()
        )
        lease_id = str(data.get("lease_id") or "").strip() or None
        if lease_id and not lease_ids:
            lease_ids = frozenset({lease_id})
        return cls(
            lease_id=lease_id,
            unit_id=str(data.get("unit_id") or "").strip() or None,
            filters=filters,
            question=str(data.get("question") or data.get("query") or "").strip(),
            lease_ids=lease_ids,
        )

    # ---------------- 形态 ----------------

    @property
    def mode(self) -> str:
        if len(self.lease_ids) > 1:
            return "compare"
        if self.lease_id or self.unit_id:
            return "targeted"
        return "explain"

    @property
    def requires_evidence(self) -> bool:
        """有目标的业务查询必须取数；纯说明任务允许只解释。"""

        return self.mode in {"targeted", "compare"}

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

        # 多目标比较：不能靠猜。模型必须点名集合内的某个目标，
        # 省略时无法"注入"（哪个才是本次要的？），因此拒绝并列出可选值。
        if self.mode == "compare" and "lease_id" in input_fields:
            given = str(final.get("lease_id") or "").strip()
            if not given:
                return None, (
                    f"这是多租约比较任务，必须显式指定 lease_id（可选 "
                    f"{sorted(self.lease_ids)}）；工具 {tool_name} 的调用已被拒绝"
                )
            if given not in self.lease_ids:
                return None, (
                    f"参数 lease_id={given!r} 超出本次比较范围（可选 "
                    f"{sorted(self.lease_ids)}）；工具 {tool_name} 的调用已被拒绝"
                )
        return final, None

    # ---------------- 结果约束 ----------------

    def accepts_output(self, tool_name: str, data: Mapping[str, Any]) -> str | None:
        """校验工具输出是否仍属于本次任务的目标；返回拒绝原因或 None。"""

        allowed = self.lease_ids
        if allowed and data.get("lease_id"):
            if str(data["lease_id"]) not in allowed:
                return (
                    f"工具 {tool_name} 返回了租约 {data['lease_id']!r} 的数据，"
                    f"但本次任务的目标是 {sorted(allowed)}"
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
            "mode": self.mode,
            "lease_id": self.lease_id,
            "lease_ids": sorted(self.lease_ids),
            "unit_id": self.unit_id,
            "filters": dict(self.filters),
            "requires_evidence": self.requires_evidence,
        }


def scope_arguments_hook(
    registry: Any, scope: TaskScope
) -> Callable[[str, dict[str, Any]], tuple[dict[str, Any] | None, str | None]]:
    """构造 `run_tool_loop` 的 `prepare_arguments` 钩子（领域 Agent 与单 Agent 共用）。

    工具不在注册表里时不做参数约束（它会因"未注册"被拒绝，那是另一道闸），
    这样钩子本身不会替工具注册表做决定。
    """

    def prepare(
        tool_name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str | None]:
        try:
            tool = registry.get(tool_name)
        except Exception:  # noqa: BLE001 - 未注册交给 ToolExecutor 报错
            return dict(arguments), None
        fields = set(tool.input_model.model_fields)
        return scope.apply_arguments(tool_name, fields, arguments)

    return prepare
