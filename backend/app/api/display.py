"""只读展示元数据（Task 032）。

界面主视图不能直接显示内部 ID（`lease_xh_a301_2025`、`principal_finance_xinghui`），
而要显示“云端咖啡（合成租户）· A-301 · 星汇广场”“星汇广场财务部门审批人（合成）”。
这些名字都已经在只读仓库里，本模块只做**查表**：

- 不计算任何金额、不推断任何结论，记录字段原样搬运（金额保持十进制字符串）；
- 只返回报告**实际引用**的记录，不额外枚举数据；
- 只返回可信主体项目范围内的记录，范围外的 ID 一律省略（不泄露存在性）；
- 不改变权限语义，也不新增写接口。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

__all__ = ["DisplayBuilder", "principal_display"]

_DOC_ID = re.compile(r"\bdoc_[a-z0-9_]+")

_CHARGE_TYPES = {"rent": "租金", "property_fee": "物业费", "deposit": "押金"}


def _records(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key) or []
    if isinstance(value, dict):
        return [item for item in value.values() if isinstance(item, dict)]
    return [item for item in value if isinstance(item, dict)]


def principal_display(repository: Any, principal_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """主体 → 中文角色名（取自 fixture 的 `role` 字段）。只返回调用方给定的主体。"""

    principals = (repository.snapshot().get("principals") or {}) if repository else {}
    out: dict[str, dict[str, Any]] = {}
    for principal_id in principal_ids:
        record = principals.get(principal_id) if isinstance(principals, dict) else None
        if not isinstance(record, dict):
            continue
        out[principal_id] = {"label": str(record.get("role") or "")}
    return out


class DisplayBuilder:
    """按可信项目范围查表。`project_ids` 为空 → 什么都不返回（默认拒绝）。"""

    def __init__(self, repository: Any, project_ids: Iterable[str]) -> None:
        data = repository.snapshot() if repository is not None else {}
        self._scope = frozenset(project_ids or ())
        self._by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for kind in (
            "projects",
            "buildings",
            "units",
            "tenants",
            "leases",
            "lease_charge_rules",
            "invoices",
            "invoice_items",
            "payments",
            "payment_allocations",
            "work_orders",
            "documents",
            "document_snippets",
        ):
            for record in _records(data, kind):
                if record.get("id"):
                    self._by_id[str(record["id"])] = (kind, record)
        self._notes_by_document: dict[str, str] = {}
        for note in _records(data, "work_notes"):
            related = note.get("related_document_id")
            if related and self._in_scope(note.get("project_id")):
                self._notes_by_document[str(related)] = str(note.get("text") or "")
        # 租户记录没有 project_id：按引用它的租约确定项目（任一在范围内的租约即可）
        self._tenant_projects: dict[str, set[str]] = {}
        for _, record in self._iter("leases"):
            if record.get("tenant_id") and record.get("project_id"):
                self._tenant_projects.setdefault(str(record["tenant_id"]), set()).add(
                    str(record["project_id"])
                )
        self._referenced_documents: set[str] = set()
        for _, record in self._iter("leases"):
            if self._in_scope(record.get("project_id")):
                self._referenced_documents.update(
                    str(item) for item in record.get("referenced_document_ids") or ()
                )

    # ---------------- 范围 ----------------

    def _iter(self, kind: str):
        return ((rid, record) for rid, (k, record) in self._by_id.items() if k == kind)

    def _in_scope(self, project_id: Any) -> bool:
        return bool(project_id) and str(project_id) in self._scope

    def _get(self, record_id: Any) -> tuple[str, dict[str, Any]] | None:
        found = self._by_id.get(str(record_id or ""))
        if found is None:
            return None
        if found[0] == "tenants":
            projects = self._tenant_projects.get(str(found[1].get("id")), set())
            return found if projects & self._scope else None
        return found if self._in_scope(self._project_of(*found)) else None

    def _project_of(self, kind: str, record: dict[str, Any]) -> str | None:
        if record.get("project_id"):
            return str(record["project_id"])
        if kind == "projects":
            return str(record.get("id"))
        for parent_key in ("lease_id", "invoice_id", "payment_id", "document_id"):
            parent = self._by_id.get(str(record.get(parent_key) or ""))
            if parent is not None and parent[1] is not record:
                return self._project_of(*parent)
        return None

    def _name(self, record_id: Any, field: str = "name") -> str | None:
        found = self._get(record_id)
        return str(found[1].get(field) or "") or None if found else None

    # ---------------- 记录 ----------------

    def lease(self, lease_id: str) -> dict[str, Any] | None:
        found = self._get(lease_id)
        if found is None or found[0] != "leases":
            return None
        lease = found[1]
        unit = self._get(lease.get("unit_id"))
        unit_record = unit[1] if unit else {}
        return {
            "lease_id": lease.get("id"),
            "lease_no": lease.get("lease_no"),
            "tenant_name": self._name(lease.get("tenant_id")),
            "unit_code": unit_record.get("code"),
            "floor": unit_record.get("floor"),
            "building_name": self._name(unit_record.get("building_id")),
            "project_name": self._name(lease.get("project_id")),
            "start_date": lease.get("start_date"),
            "end_date": lease.get("end_date"),
            "status": lease.get("status"),
        }

    def record(self, record_id: str) -> dict[str, Any] | None:
        """单条记录的展示字段（字段原样搬运，不计算）。范围外或未知 → None。"""

        if record_id in self._referenced_documents or record_id in self._notes_by_document:
            if record_id not in self._by_id:
                return {
                    "kind": "document",
                    "title": None,
                    "digitized": False,
                    "note": self._notes_by_document.get(record_id),
                }
        found = self._get(record_id)
        if found is None:
            return None
        kind, r = found
        if kind == "leases":
            return {"kind": "lease", **(self.lease(record_id) or {})}
        if kind == "units":
            return {"kind": "unit", "unit_code": r.get("code"), "floor": r.get("floor")}
        if kind == "tenants":
            return {"kind": "tenant", "name": r.get("name")}
        if kind == "lease_charge_rules":
            return {
                "kind": "charge_rule",
                "charge_type": r.get("charge_type"),
                "charge_type_label": _CHARGE_TYPES.get(str(r.get("charge_type")), None),
                "calculation_method": r.get("calculation_method"),
                "unit_price": r.get("unit_price"),
                "effective_from": r.get("effective_from"),
                "effective_to": r.get("effective_to"),
                "is_rent_free": r.get("is_rent_free"),
            }
        if kind == "invoices":
            return {
                "kind": "invoice",
                "invoice_no": r.get("invoice_no"),
                "period_start": r.get("period_start"),
                "period_end": r.get("period_end"),
                "due_date": r.get("due_date"),
                "status": r.get("status"),
                "currency": r.get("currency"),
            }
        if kind == "invoice_items":
            return {
                "kind": "invoice_item",
                "invoice_id": r.get("invoice_id"),
                "charge_rule_id": r.get("charge_rule_id"),
                "charge_type": r.get("charge_type"),
                "charge_type_label": _CHARGE_TYPES.get(str(r.get("charge_type")), None),
                "description": r.get("description"),
                "quantity": r.get("quantity"),
                "unit_price": r.get("unit_price"),
                "amount": r.get("amount"),
            }
        if kind == "payments":
            return {
                "kind": "payment",
                "receipt_no": r.get("receipt_no"),
                "paid_at": r.get("paid_at"),
                "amount": r.get("amount"),
                "currency": r.get("currency"),
                "status": r.get("status"),
            }
        if kind == "payment_allocations":
            return {
                "kind": "allocation",
                "payment_id": r.get("payment_id"),
                "invoice_id": r.get("invoice_id"),
                "amount": r.get("amount"),
                "allocated_at": r.get("allocated_at"),
                "reversed_at": r.get("reversed_at"),
            }
        if kind == "work_orders":
            return {
                "kind": "work_order",
                "work_order_no": r.get("work_order_no"),
                "title": r.get("title"),
                "category": r.get("category"),
                "status": r.get("status"),
                "reported_at": r.get("reported_at"),
                "resolved_at": r.get("resolved_at"),
                "resolution_note": r.get("resolution_note"),
            }
        if kind == "documents":
            return {
                "kind": "document",
                "title": r.get("title"),
                "version": r.get("version"),
                "document_status": r.get("document_status"),
                "digitized": True,
                "note": self._notes_by_document.get(record_id),
            }
        if kind == "document_snippets":
            return {
                "kind": "snippet",
                "document_id": r.get("document_id"),
                "page": r.get("page"),
                "clause_id": r.get("clause_id"),
                "text": r.get("text"),
            }
        return None

    # ---------------- 运行 ----------------

    def for_run(self, run: dict[str, Any]) -> dict[str, Any]:
        """一次运行的展示元数据：目标租约 + 报告实际引用的记录。"""

        report = run.get("report") if isinstance(run.get("report"), dict) else {}
        ids: dict[str, None] = {}

        def add(values: Any) -> None:
            for value in values or ():
                if isinstance(value, str) and value:
                    ids.setdefault(value, None)

        for finding in report.get("findings") or ():
            if isinstance(finding, dict):
                add(finding.get("evidence_ids"))
        for conflict in report.get("conflicts") or ():
            if isinstance(conflict, dict):
                add(conflict.get("evidence_ids"))
        for key in ("proposed_draft", "approval_request"):
            item = report.get(key)
            if isinstance(item, dict):
                add(item.get("evidence_ids"))
                target = item.get("target")
                if isinstance(target, dict):
                    add(target.values())
        for text in report.get("missing_information") or ():
            add(_DOC_ID.findall(str(text)))
        records: dict[str, Any] = {}
        for record_id in ids:
            shown = self.record(record_id)
            if shown is not None:
                records[record_id] = shown
        return {
            "lease": self.lease(str(run.get("lease_id") or "")),
            "records": records,
            "note": "只读展示元数据：取自可信项目范围内的只读仓库，字段原样搬运，不含计算结果",
        }

    def summary(self, lease_id: str) -> dict[str, Any] | None:
        lease = self.lease(lease_id)
        if lease is None:
            return None
        return {
            "tenant_name": lease.get("tenant_name"),
            "unit_code": lease.get("unit_code"),
            "project_name": lease.get("project_name"),
        }
