"""Fixture 只读仓库。

职责边界：

- 只读取 `docs/evaluation/fixtures/agent_first_v1.json`，不复制成第二份事实源；
- 所有金额在这里转成 `Decimal`，工具层不得用 float 做财务计算；
- **项目范围**由调用方的可信上下文决定：查询前校验记录归属，
  越权项目直接抛 `ProjectScopeDeniedError`，不能靠猜参数读到别家数据；
- 支持把 fixture 中已定义的 overlay 变体在内存中应用（只读副本），
  用于验证"数据更正后结论随之变化"（如 `v_oct_rent_corrected`）。
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..agents.base.errors import (
    AgentError,
    ErrorCode,
    ProjectScopeDeniedError,
    RecordNotFoundError,
)
from ..paths import DEFAULT_FIXTURE_PATH

_ENTITY_KEYS = (
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
    "work_notes",
)

_ZERO = Decimal("0.00")


def money(value: Any) -> Decimal:
    """把 fixture 中的十进制字符串转成 `Decimal`（拒绝 float 输入）。"""

    if isinstance(value, float):
        raise TypeError("金额不得由 float 构造；fixture 必须是十进制字符串")
    return Decimal(str(value))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


class FixtureRepository:
    def __init__(self, data: dict[str, Any], *, source: str = "<memory>") -> None:
        self._data = data
        self._source = source
        self._by_id: dict[str, dict[str, Any]] = {}
        for key in _ENTITY_KEYS:
            for record in data.get(key, []):
                record_id = record.get("id")
                if record_id:
                    self._by_id[record_id] = record
        self.dataset_version: str = data["dataset_version"]
        self.as_of_date: date = date.fromisoformat(data["as_of_date"])
        self.synthetic: bool = bool(data.get("synthetic", True))

    # ---------------- 装载 ----------------

    @classmethod
    def load(cls, path: str | Path | None = None, *, variant: str | None = None) -> "FixtureRepository":
        fixture_path = Path(path) if path is not None else DEFAULT_FIXTURE_PATH
        if not fixture_path.is_file():
            raise FileNotFoundError(f"fixture 不存在: {fixture_path}")
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
        if variant is not None:
            data = cls._apply_variant(data, variant)
        return cls(data, source=str(fixture_path))

    @staticmethod
    def _apply_variant(data: dict[str, Any], variant: str) -> dict[str, Any]:
        """在深拷贝上应用 variant overlay（只读语义，与评测计划 §2.3 一致）。"""

        registry = data.get("variant_registry", {})
        if variant not in registry:
            raise AgentError(
                f"未知数据变体: {variant!r}",
                code=ErrorCode.INVALID_CONTEXT,
                retryable=False,
                details={"known": sorted(registry)},
            )
        copied = json.loads(json.dumps(data))
        overlay = registry[variant].get("overlay", {})
        for document in overlay.get("add_documents", []):
            copied["documents"].append(document)
        for snippet in overlay.get("add_document_snippets", []):
            copied["document_snippets"].append(snippet)
        for patch in overlay.get("patch_invoice_items", []):
            for item in copied["invoice_items"]:
                if item["id"] == patch["invoice_item_id"]:
                    item.update(patch["set"])
        return copied

    # ---------------- 基础索引 ----------------

    def record(self, record_id: str) -> dict[str, Any] | None:
        return self._by_id.get(record_id)

    def principal(self, principal_id: str) -> dict[str, Any]:
        principals = self._data.get("principals", {})
        if principal_id not in principals:
            raise RecordNotFoundError(
                f"可信主体不存在: {principal_id!r}",
                details={"known": sorted(principals)},
            )
        return principals[principal_id]

    def _scoped(self, record: dict[str, Any], project_ids: frozenset[str], *, what: str) -> None:
        project_id = record.get("project_id")
        if project_id not in project_ids:
            raise ProjectScopeDeniedError(
                f"无权访问{what}（项目 {project_id!r} 不在可信上下文的项目范围内）",
                details={
                    "record_id": record.get("id"),
                    "required_project": project_id,
                    "allowed_projects": sorted(project_ids),
                },
            )

    def _lease_of(self, lease_id: str, project_ids: frozenset[str]) -> dict[str, Any]:
        lease = self._by_id.get(lease_id)
        if lease is None or "lease_no" not in lease:
            raise RecordNotFoundError(f"租约不存在: {lease_id!r}")
        self._scoped(lease, project_ids, what="租约")
        return lease

    # ---------------- 查询：Lease ----------------

    def lease_facts(
        self,
        *,
        project_ids: frozenset[str],
        lease_id: str | None = None,
        unit_code: str | None = None,
    ) -> dict[str, Any]:
        if not lease_id and not unit_code:
            raise AgentError(
                "必须提供 lease_id 或 unit_code 之一",
                code=ErrorCode.INVALID_TOOL_ARGUMENTS,
                retryable=False,
            )
        lease: dict[str, Any] | None = None
        unit: dict[str, Any] | None = None
        if lease_id:
            lease = self._lease_of(lease_id, project_ids)
            unit = self._by_id.get(lease["unit_id"])
        else:
            unit = next(
                (u for u in self._data["units"] if u["code"] == unit_code),
                None,
            )
            if unit is None:
                raise RecordNotFoundError(f"商铺不存在: {unit_code!r}")
            self._scoped(unit, project_ids, what="商铺")
            lease = next((l for l in self._data["leases"] if l["unit_id"] == unit["id"]), None)
        if lease is None:
            raise RecordNotFoundError(
                f"商铺 {unit_code!r} 没有有效租约" if unit_code else f"租约不存在: {lease_id!r}"
            )
        self._scoped(lease, project_ids, what="租约")
        if unit is not None:
            self._scoped(unit, project_ids, what="商铺")

        tenant = self._by_id.get(lease["tenant_id"])
        rules = [
            rule for rule in self._data["lease_charge_rules"] if rule["lease_id"] == lease["id"]
        ]
        referenced = lease.get("referenced_document_ids", [])
        documents = [doc for doc in (self._by_id.get(doc_id) for doc_id in referenced) if doc]
        documents = [doc for doc in documents if doc.get("project_id") in project_ids]
        missing_documents = [
            doc_id for doc_id in referenced if doc_id not in self._by_id
        ]
        return {
            "lease": lease,
            "unit": unit,
            "tenant": tenant,
            "rules": rules,
            "documents": documents,
            "missing_documents": missing_documents,
        }

    # ---------------- 查询：Billing ----------------

    def statement(self, *, project_ids: frozenset[str], lease_id: str) -> dict[str, Any]:
        lease = self._lease_of(lease_id, project_ids)
        invoices = [inv for inv in self._data["invoices"] if inv["lease_id"] == lease_id]
        invoices.sort(key=lambda inv: inv["period_start"])
        # F1：付款/核销必须限定在**当前租约自己的账单**上。
        # 只按 project_ids 过滤会把同项目其他租约的付款算进本租约，导致未收被错误扣减。
        invoice_ids = {invoice["id"] for invoice in invoices}

        confirmed_payments = {
            payment["id"]
            for payment in self._data["payments"]
            if payment["status"] == "confirmed" and payment["project_id"] in project_ids
        }
        allocations = [
            alloc
            for alloc in self._data["payment_allocations"]
            if alloc["payment_id"] in confirmed_payments
            and alloc.get("reversed_at") is None
            and alloc["invoice_id"] in invoice_ids
        ]
        # 只返回真正核销到本租约的已确认收款（无核销的付款不参与本租约已收额）
        allocated_payment_ids = {alloc["payment_id"] for alloc in allocations}
        valid_payments = [
            payment
            for payment in self._data["payments"]
            if payment["id"] in allocated_payment_ids
        ]

        invoice_views: list[dict[str, Any]] = []
        invoiced_total = _ZERO
        allocated_by_invoice: dict[str, Decimal] = {}
        for alloc in allocations:
            allocated_by_invoice[alloc["invoice_id"]] = (
                allocated_by_invoice.get(alloc["invoice_id"], _ZERO) + money(alloc["amount"])
            )

        rent_variance_total = _ZERO
        for invoice in invoices:
            self._scoped(invoice, project_ids, what="账单")
            items = [item for item in self._data["invoice_items"] if item["invoice_id"] == invoice["id"]]
            total = _quantize(sum((money(item["amount"]) for item in items), _ZERO))
            invoiced_total += total
            rent_variance: Decimal | None = None
            expected_rent: Decimal | None = None
            for item in items:
                if item["charge_type"] != "rent":
                    continue
                rule = self._rent_rule(lease_id, invoice["period_start"])
                if rule is None:
                    continue
                expected = _quantize(money(item["quantity"]) * money(rule["unit_price"]))
                expected_rent = expected
                rent_variance = _quantize(money(item["amount"]) - expected)
                rent_variance_total += rent_variance
            invoice_views.append(
                {
                    "invoice": invoice,
                    "items": items,
                    "total": total,
                    "allocated": _quantize(allocated_by_invoice.get(invoice["id"], _ZERO)),
                    "outstanding": _quantize(total - allocated_by_invoice.get(invoice["id"], _ZERO)),
                    "rent_rule": self._rent_rule(lease_id, invoice["period_start"]),
                    "expected_rent": expected_rent,
                    "rent_variance": rent_variance,
                }
            )

        # 已收额必须按**核销到本租约账单的金额**累计，而不是按付款整笔金额。
        # 一笔付款可能拆分核销到不同租约的账单（同项目），按付款金额累计会把
        # 他租约的部分算成本租约已收，导致未收被少算（F1 同类缺陷的隐蔽形式）。
        paid_total = _quantize(sum((money(alloc["amount"]) for alloc in allocations), _ZERO))
        outstanding_total = _quantize(
            sum((view["outstanding"] for view in invoice_views), _ZERO)
        )
        outstanding_invoices = [
            view["invoice"]["id"] for view in invoice_views if view["outstanding"] > _ZERO
        ]
        return {
            "lease": lease,
            "invoices": invoice_views,
            "payments": valid_payments,
            "allocations": allocations,
            "invoiced_total": _quantize(invoiced_total),
            "paid_total": paid_total,
            "outstanding_total": outstanding_total,
            "outstanding_invoice_ids": outstanding_invoices,
            "rent_variance_total": _quantize(rent_variance_total),
        }

    def _rent_rule(self, lease_id: str, period_start: str) -> dict[str, Any] | None:
        for rule in self._data["lease_charge_rules"]:
            if (
                rule["lease_id"] == lease_id
                and rule["charge_type"] == "rent"
                and rule["effective_from"] <= period_start <= rule["effective_to"]
            ):
                return rule
        return None

    def arrears(self, *, project_ids: frozenset[str], lease_id: str) -> dict[str, Any]:
        statement = self.statement(project_ids=project_ids, lease_id=lease_id)
        return {
            "lease": statement["lease"],
            "invoiced_total": statement["invoiced_total"],
            "paid_total": statement["paid_total"],
            "outstanding_total": statement["outstanding_total"],
            "outstanding_invoice_ids": statement["outstanding_invoice_ids"],
            "invoices": statement["invoices"],
            "payments": statement["payments"],
            "allocations": statement["allocations"],
        }

    # ---------------- 查询：Property ----------------

    def work_orders(
        self,
        *,
        project_ids: frozenset[str],
        lease_id: str | None = None,
        unit_id: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        if not lease_id and not unit_id:
            raise AgentError(
                "必须提供 lease_id 或 unit_id 之一",
                code=ErrorCode.INVALID_TOOL_ARGUMENTS,
                retryable=False,
            )
        if lease_id:
            self._lease_of(lease_id, project_ids)
        if unit_id:
            unit = self._by_id.get(unit_id)
            if unit is None:
                raise RecordNotFoundError(f"商铺不存在: {unit_id!r}")
            # 即使该商铺没有工单，也必须先做范围校验，避免"猜 ID 探测存在性"
            self._scoped(unit, project_ids, what="商铺")
        orders = [
            order
            for order in self._data["work_orders"]
            if (lease_id is None or order["lease_id"] == lease_id)
            and (unit_id is None or order["unit_id"] == unit_id)
        ]
        for order in orders:
            self._scoped(order, project_ids, what="维修工单")
        if category is not None:
            orders = [order for order in orders if order["category"] == category]
        orders.sort(key=lambda order: order["reported_at"])
        return orders

    def documents(self, *, project_ids: frozenset[str], document_ids: list[str]) -> list[dict[str, Any]]:
        result = []
        for doc_id in document_ids:
            doc = self._by_id.get(doc_id)
            if doc is None:
                continue
            self._scoped(doc, project_ids, what="文档")
            result.append(doc)
        return result
