"""从**工具输出**提取可评分事实（Task 018）。

为什么放在 Agent 层而不是评测层：

- 事实必须来自确定性工具结果，不能由模型文本生成；Agent 与评测都需要这条规则；
- 评测层如果自己实现一份，两边的"事实口径"会慢慢分叉，报告就不可比了。

这里只做"字段搬运"：不计算、不推断、不改写。任何派生指标（应收/已收/未收）
都必须在工具里用 `Decimal` 算好，本模块只负责取值。
"""

from __future__ import annotations

from typing import Any

__all__ = ["facts_from_tool_output", "facts_of_executions", "outputs_of_executions"]


def facts_from_tool_output(tool: str, data: dict[str, Any]) -> dict[str, str]:
    """把某个工具的输出映射成标准事实键（键名与评分器的基线契约一致）。"""

    if tool in {"billing.statement.read", "billing.arrears.calculate"}:
        facts: dict[str, str] = {
            "invoiced_total": str(data.get("invoiced_total")),
            "paid_total": str(data.get("paid_total")),
            "outstanding_total": str(data.get("outstanding_total")),
        }
        if data.get("rent_variance_total") is not None:
            facts["rent_variance_total"] = str(data["rent_variance_total"])
        return facts
    if tool == "lease.lookup":
        return {
            "lease_period": f"{data.get('start_date')} 至 {data.get('end_date')}",
            "lease_status": str(data.get("status")),
            "unit_code": str(data.get("unit_code") or ""),
            "lease_id": str(data.get("lease_id") or ""),
            "missing_document_ids": [
                str(item) for item in data.get("missing_document_ids") or []
            ],
        }
    if tool == "property.work_orders.read":
        return {
            "work_order_count": str(data.get("work_order_count", 0)),
            "open_count": str(data.get("open_count", 0)),
        }
    if tool == "document.search":
        results = data.get("results") or []
        if not results:
            return {"clause_ref": "未检索到匹配条款"}
        top = results[0]
        return {"clause_ref": f"合同第 {top.get('page')} 页 {top.get('clause_id')} 条"}
    return {}


def facts_of_executions(
    executions: Any,
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """按调用顺序合并工具事实；同一工具多次调用以最后一次为准。"""

    merged: dict[str, str] = {}
    per_tool: dict[str, dict[str, str]] = {}
    for execution in executions or ():
        if not getattr(execution, "ok", False):
            continue
        data = execution.data or {}
        if not isinstance(data, dict):
            continue
        facts = facts_from_tool_output(execution.tool_name, data)
        per_tool[execution.tool_name] = facts
        merged.update(facts)
    return merged, per_tool


def outputs_of_executions(executions: Any) -> dict[str, dict[str, Any]]:
    """成功的工具原始输出，按工具名索引（同一工具以最后一次为准）。"""

    outputs: dict[str, dict[str, Any]] = {}
    for execution in executions or ():
        if getattr(execution, "ok", False) and isinstance(execution.data, dict):
            outputs[execution.tool_name] = dict(execution.data)
    return outputs
