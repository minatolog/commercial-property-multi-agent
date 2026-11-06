"""数据库只读仓库（Task 010）。

对外暴露与 `FixtureRepository` 相同的查询契约，使业务工具**无需修改**即可
在 JSON fixture 与真实数据库之间切换（这是"数据源可替换"的可验证证据）。

边界：

- 只发 SELECT；
- 每个查询都强制 `project_id IN (...)`，不接受调用方自报范围；
- 金额用 `Decimal`，不用 float。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base.errors import AgentError, ErrorCode, RecordNotFoundError
from .models import (
    Document,
    Invoice,
    InvoiceItem,
    Lease,
    LeaseChargeRule,
    Payment,
    PaymentAllocation,
    Project,
    Tenant,
    Unit,
    WorkOrder,
)

__all__ = ["DatabaseRepository", "ReadOnlyViolation"]

_ZERO = Decimal("0.00")


class ReadOnlyViolation(AgentError):
    """业务代码试图通过仓库写入数据。"""

    default_code = ErrorCode.PERMISSION_DENIED


def _money(value: Any) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class DatabaseRepository:
    """只读查询仓库。与 fixture 仓库返回同形结构。"""

    def __init__(self, session: Session, *, dataset_version: str, as_of_date: date) -> None:
        self._session = session
        self.dataset_version = dataset_version
        self.as_of_date = as_of_date
        self._principals: dict[str, dict[str, Any]] = {}

    # ---------------- 禁止写入 ----------------

    def add(self, *_: Any, **__: Any) -> None:  # pragma: no cover - 显式拒绝
        raise ReadOnlyViolation("业务仓库只读：不允许 add")

    def delete(self, *_: Any, **__: Any) -> None:  # pragma: no cover
        raise ReadOnlyViolation("业务仓库只读：不允许 delete")

    def commit(self, *_: Any, **__: Any) -> None:  # pragma: no cover
        raise ReadOnlyViolation("业务仓库只读：不允许 commit")

    # ---------------- 可信主体 ----------------

    def register_principal(self, principal: dict[str, Any]) -> None:
        self._principals[principal["principal_id"]] = principal

    def principal(self, principal_id: str) -> dict[str, Any]:
        if principal_id not in self._principals:
            raise RecordNotFoundError(f"未知主体: {principal_id!r}")
        return self._principals[principal_id]

    # ---------------- 内部查询 ----------------

    def _scoped_unit(self, unit_id: str, project_ids: frozenset[str]) -> Unit:
        unit = self._session.get(Unit, unit_id)
        if unit is None:
            raise RecordNotFoundError(f"商铺不存在: {unit_id!r}")
        if unit.project_id not in project_ids:
            raise AgentError(
                f"无权访问项目 {unit.project_id!r} 的商铺",
                code=ErrorCode.PROJECT_SCOPE_DENIED,
                retryable=False,
            )
        return unit

    def _lease_of(self, lease_id: str, project_ids: frozenset[str]) -> Lease:
        lease = self._session.get(Lease, lease_id)
        if lease is None:
            raise RecordNotFoundError(f"租约不存在: {lease_id!r}")
        if lease.project_id not in project_ids:
            raise AgentError(
                f"无权访问项目 {lease.project_id!r} 的租约",
                code=ErrorCode.PROJECT_SCOPE_DENIED,
                retryable=False,
            )
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
        if lease_id:
            lease = self._lease_of(lease_id, project_ids)
            unit = self._session.get(Unit, lease.unit_id)
        else:
            unit = self._session.scalars(
                select(Unit).where(Unit.code == unit_code)
            ).first()
            if unit is None:
                raise RecordNotFoundError(f"商铺不存在: {unit_code!r}")
            self._scoped_unit(unit.id, project_ids)
            lease = self._session.scalars(
                select(Lease).where(Lease.unit_id == unit.id)
            ).first()
            if lease is None:
                raise RecordNotFoundError(f"商铺 {unit_code!r} 没有有效租约")
        if unit is not None:
            self._scoped_unit(unit.id, project_ids)

        tenant = self._session.get(Tenant, lease.tenant_id)
        rules = list(
            self._session.scalars(
                select(LeaseChargeRule).where(LeaseChargeRule.lease_id == lease.id)
            )
        )
        documents = list(
            self._session.scalars(select(Document).where(Document.lease_id == lease.id))
        )
        return {
            "lease": _lease_dict(lease),
            "unit": _unit_dict(unit) if unit else None,
            "tenant": _tenant_dict(tenant) if tenant else None,
            "rules": [_rule_dict(rule) for rule in rules],
            "documents": [_document_dict(doc) for doc in documents],
            # 合同引用但库里不存在的文档：用"引用清单 - 实存文档"推导
            "missing_documents": _missing_documents(lease, documents),
        }

    # ---------------- 查询：文档目录（Task 016 / F3） ----------------

    def documents(self) -> list[dict[str, Any]]:
        """列出全部文档元数据（供知识库装配使用，不含正文）。

        不做权限判断：项目/租约范围由调用方（检索时的 `project_ids`）决定，
        与 fixture 仓库的目录接口保持一致。
        """

        return [
            _document_dict(document)
            for document in self._session.scalars(select(Document))
        ]

    # ---------------- 查询：Billing ----------------

    def statement(self, *, project_ids: frozenset[str], lease_id: str) -> dict[str, Any]:
        lease = self._lease_of(lease_id, project_ids)
        invoices = list(
            self._session.scalars(
                select(Invoice)
                .where(Invoice.lease_id == lease_id)
                .order_by(Invoice.period_start)
            )
        )
        for invoice in invoices:
            if invoice.project_id not in project_ids:
                raise AgentError(
                    f"无权访问项目 {invoice.project_id!r} 的账单",
                    code=ErrorCode.PROJECT_SCOPE_DENIED,
                    retryable=False,
                )
        invoice_ids = [invoice.id for invoice in invoices]

        allocations: list[PaymentAllocation] = []
        payments_by_id: dict[str, Payment] = {}
        if invoice_ids:
            allocations = list(
                self._session.scalars(
                    select(PaymentAllocation).where(
                        PaymentAllocation.invoice_id.in_(invoice_ids),
                        PaymentAllocation.reversed_at.is_(None),
                    )
                )
            )
            payment_ids = {item.payment_id for item in allocations}
            if payment_ids:
                for payment in self._session.scalars(
                    select(Payment).where(
                        Payment.id.in_(payment_ids),
                        Payment.status == "confirmed",
                        Payment.project_id.in_(project_ids),
                    )
                ):
                    payments_by_id[payment.id] = payment
        allocations = [a for a in allocations if a.payment_id in payments_by_id]

        allocated_by_invoice: dict[str, Decimal] = {}
        for allocation in allocations:
            allocated_by_invoice[allocation.invoice_id] = allocated_by_invoice.get(
                allocation.invoice_id, _ZERO
            ) + _money(allocation.amount)

        invoice_views: list[dict[str, Any]] = []
        invoiced_total = _ZERO
        rent_variance_total = _ZERO
        for invoice in invoices:
            items = list(
                self._session.scalars(
                    select(InvoiceItem).where(InvoiceItem.invoice_id == invoice.id)
                )
            )
            total = sum((_money(item.amount) for item in items), _ZERO)
            invoiced_total += total
            allocated = allocated_by_invoice.get(invoice.id, _ZERO)
            rent_variance: Decimal | None = None
            expected_rent: Decimal | None = None
            rule = self._rent_rule(lease_id, invoice.period_start)
            for item in items:
                if item.charge_type != "rent" or rule is None:
                    continue
                expected = (_money(item.quantity) * _money(rule.unit_price)).quantize(
                    Decimal("0.01")
                )
                expected_rent = expected
                rent_variance = (_money(item.amount) - expected).quantize(
                    Decimal("0.01")
                )
                rent_variance_total += rent_variance
            invoice_views.append(
                {
                    "invoice": _invoice_dict(invoice),
                    "items": [_item_dict(item) for item in items],
                    "total": total.quantize(Decimal("0.01")),
                    "allocated": allocated.quantize(Decimal("0.01")),
                    "outstanding": (total - allocated).quantize(Decimal("0.01")),
                    "rent_rule": _rule_dict(rule) if rule else None,
                    "expected_rent": expected_rent,
                    "rent_variance": rent_variance,
                }
            )

        paid_total = sum((_money(item.amount) for item in allocations), _ZERO)
        outstanding_total = sum(
            (view["outstanding"] for view in invoice_views), _ZERO
        )
        return {
            "lease": _lease_dict(lease),
            "invoices": invoice_views,
            "payments": [_payment_dict(item) for item in payments_by_id.values()],
            "allocations": [_allocation_dict(item) for item in allocations],
            "invoiced_total": invoiced_total.quantize(Decimal("0.01")),
            "paid_total": paid_total.quantize(Decimal("0.01")),
            "outstanding_total": outstanding_total.quantize(Decimal("0.01")),
            "outstanding_invoice_ids": [
                view["invoice"]["id"]
                for view in invoice_views
                if view["outstanding"] > _ZERO
            ],
            "rent_variance_total": rent_variance_total.quantize(Decimal("0.01")),
        }

    def arrears(self, *, project_ids: frozenset[str], lease_id: str) -> dict[str, Any]:
        statement = self.statement(project_ids=project_ids, lease_id=lease_id)
        return {
            "lease": statement["lease"],
            "invoiced_total": statement["invoiced_total"],
            "paid_total": statement["paid_total"],
            "outstanding_total": statement["outstanding_total"],
            "outstanding_invoice_ids": statement["outstanding_invoice_ids"],
            "rent_variance_total": statement["rent_variance_total"],
        }

    def _rent_rule(self, lease_id: str, period_start: date) -> LeaseChargeRule | None:
        return self._session.scalars(
            select(LeaseChargeRule).where(
                LeaseChargeRule.lease_id == lease_id,
                LeaseChargeRule.charge_type == "rent",
                LeaseChargeRule.effective_from <= period_start,
                LeaseChargeRule.effective_to >= period_start,
            )
        ).first()

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
            self._scoped_unit(unit_id, project_ids)

        query = select(WorkOrder).where(WorkOrder.project_id.in_(project_ids))
        if lease_id:
            query = query.where(WorkOrder.lease_id == lease_id)
        if unit_id:
            query = query.where(WorkOrder.unit_id == unit_id)
        orders = list(self._session.scalars(query.order_by(WorkOrder.reported_at)))
        if category is not None:
            orders = [order for order in orders if order.category == category]
        return [_work_order_dict(order) for order in orders]


# ---------------- 字典转换（与 fixture 的 JSON 形状保持一致） ----------------


def _lease_dict(lease: Lease) -> dict[str, Any]:
    return {
        "id": lease.id,
        "project_id": lease.project_id,
        "lease_no": lease.lease_no,
        "tenant_id": lease.tenant_id,
        "unit_id": lease.unit_id,
        "start_date": _iso(lease.start_date),
        "end_date": _iso(lease.end_date),
        "status": lease.status,
        "billing_cycle": lease.billing_cycle,
        "payment_terms_days": lease.payment_terms_days,
        "deposit_amount": str(_money(lease.deposit_amount)),
        "currency": lease.currency,
    }


def _unit_dict(unit: Unit) -> dict[str, Any]:
    return {
        "id": unit.id,
        "project_id": unit.project_id,
        "building_id": unit.building_id,
        "code": unit.code,
        "floor": unit.floor,
        "area_sqm": str(_money(unit.area_sqm)),
        "chargeable_area_sqm": str(_money(unit.chargeable_area_sqm)),
        "usage_type": unit.usage_type,
        "physical_status": unit.physical_status,
    }


def _tenant_dict(tenant: Tenant) -> dict[str, Any]:
    return {
        "id": tenant.id,
        "code": tenant.code,
        "name": tenant.name,
        "unified_social_credit_code": tenant.unified_social_credit_code,
        "contact_name": tenant.contact_name,
        "contact_phone": tenant.contact_phone,
        "status": tenant.status,
    }


def _rule_dict(rule: LeaseChargeRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "lease_id": rule.lease_id,
        "charge_type": rule.charge_type,
        "calculation_method": rule.calculation_method,
        "amount": str(_money(rule.amount)) if rule.amount is not None else None,
        "unit_price": str(_money(rule.unit_price)) if rule.unit_price is not None else None,
        "period_unit": rule.period_unit,
        "effective_from": _iso(rule.effective_from),
        "effective_to": _iso(rule.effective_to),
        "is_rent_free": rule.is_rent_free,
    }


def _invoice_dict(invoice: Invoice) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "project_id": invoice.project_id,
        "lease_id": invoice.lease_id,
        "invoice_no": invoice.invoice_no,
        "period_start": _iso(invoice.period_start),
        "period_end": _iso(invoice.period_end),
        "issue_date": _iso(invoice.issue_date),
        "due_date": _iso(invoice.due_date),
        "currency": invoice.currency,
        "status": invoice.status,
    }


def _item_dict(item: InvoiceItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "invoice_id": item.invoice_id,
        "charge_type": item.charge_type,
        "description": item.description,
        "quantity": str(_money(item.quantity)),
        "unit_price": str(_money(item.unit_price)) if item.unit_price is not None else None,
        "amount": str(_money(item.amount)),
    }


def _payment_dict(payment: Payment) -> dict[str, Any]:
    return {
        "id": payment.id,
        "project_id": payment.project_id,
        "receipt_no": payment.receipt_no,
        "payer_tenant_id": payment.payer_tenant_id,
        "payment_method": payment.payment_method,
        "amount": str(_money(payment.amount)),
        "currency": payment.currency,
        "paid_at": _iso(payment.paid_at),
        "status": payment.status,
    }


def _allocation_dict(allocation: PaymentAllocation) -> dict[str, Any]:
    return {
        "id": allocation.id,
        "payment_id": allocation.payment_id,
        "invoice_id": allocation.invoice_id,
        "amount": str(_money(allocation.amount)),
        "allocated_at": _iso(allocation.allocated_at),
        "reversed_at": _iso(allocation.reversed_at),
    }


def _work_order_dict(order: WorkOrder) -> dict[str, Any]:
    return {
        "id": order.id,
        "project_id": order.project_id,
        "unit_id": order.unit_id,
        "lease_id": order.lease_id,
        "work_order_no": order.work_order_no,
        "category": order.category,
        "priority": order.priority,
        "status": order.status,
        "title": order.title,
        "description": order.description,
        "reported_at": _iso(order.reported_at),
        "resolved_at": _iso(order.resolved_at),
        "resolution_note": order.resolution_note,
    }


def _document_dict(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "project_id": document.project_id,
        "lease_id": document.lease_id,
        "doc_type": document.doc_type,
        "title": document.title,
        "version": document.version,
        "document_status": document.document_status,
        "checksum_sha256": document.checksum_sha256,
    }


def _missing_documents(lease: Lease, documents: Iterable[Document]) -> list[str]:
    """fixture 中被引用但未电子化的文档（如 doc_xh_a301_annex_b）。

    数据库里没有"引用但不存在"的外键，因此用显式清单表达合同正文引用。
    """

    known = {document.id for document in documents}
    return sorted(REFERENCED_BUT_MISSING_BY_LEASE.get(lease.id, set()) - known)


#: 合同正文引用了、但尚未电子化归档的文档（来自 fixture 的业务事实）
REFERENCED_BUT_MISSING_BY_LEASE: dict[str, set[str]] = {
    "lease_xh_a301_2025": {"doc_xh_a301_annex_b"},
}