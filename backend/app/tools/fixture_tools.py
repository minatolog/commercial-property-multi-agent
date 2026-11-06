"""Lease / Billing / Property 三个域的只读 fixture 工具。

全部通过 `FixtureRepository` 查询唯一事实源，不复制数据、不写回。
返回的 `EvidenceDraft` 只声明引用记录与依赖字段；来源字段由执行器补齐。
金额一律 `Decimal`。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..agents.base.contracts import AgentContext
from ..fixtures.repository import FixtureRepository
from ..runtime.types import EvidenceDraft
from .base import BaseTool, ToolInvocation

__all__ = [
    "BillingArrearsTool",
    "BillingStatementInput",
    "BillingStatementTool",
    "LeaseLookupInput",
    "LeaseLookupTool",
    "PropertyWorkOrdersTool",
    "build_fixture_tools",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------- 输入 ----------------

class LeaseLookupInput(_StrictModel):
    lease_id: str | None = Field(default=None, min_length=1, max_length=64)
    unit_code: str | None = Field(default=None, min_length=1, max_length=16)

    @model_validator(mode="after")
    def _exactly_one(self) -> "LeaseLookupInput":
        if bool(self.lease_id) == bool(self.unit_code):
            raise ValueError("lease_id 与 unit_code 必须且只能提供一个")
        return self


class BillingStatementInput(_StrictModel):
    lease_id: str = Field(min_length=1, max_length=64)


class BillingArrearsInput(_StrictModel):
    lease_id: str = Field(min_length=1, max_length=64)


class PropertyWorkOrdersInput(_StrictModel):
    lease_id: str | None = Field(default=None, min_length=1, max_length=64)
    unit_id: str | None = Field(default=None, min_length=1, max_length=64)
    category: str | None = Field(default=None, min_length=1, max_length=32)

    @model_validator(mode="after")
    def _at_least_one(self) -> "PropertyWorkOrdersInput":
        if not self.lease_id and not self.unit_id:
            raise ValueError("lease_id 与 unit_id 至少提供一个")
        return self


# ---------------- 输出 ----------------

class LeaseRuleOut(_StrictModel):
    rule_id: str
    charge_type: str
    calculation_method: str
    unit_price: Decimal
    effective_from: str
    effective_to: str


class LeaseLookupOutput(_StrictModel):
    lease_id: str
    lease_no: str
    project_id: str
    unit_id: str
    unit_code: str
    tenant_id: str
    currency: str
    deposit_amount: Decimal
    start_date: str
    end_date: str
    status: str
    rules: list[LeaseRuleOut]
    #: 租约引用的全部文档（含草案），保留给审计
    document_ids: list[str]
    #: 已签署生效文档（默认检索范围，Task 017 / R4）
    signed_document_ids: list[str] = []
    #: 未签署草案（只能作为草案证据单列，不得当作生效依据）
    draft_document_ids: list[str] = []
    missing_document_ids: list[str]


class InvoiceItemOut(_StrictModel):
    item_id: str
    charge_type: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class InvoiceOut(_StrictModel):
    invoice_id: str
    period_start: str
    period_end: str
    total: Decimal
    outstanding: Decimal
    expected_rent: Decimal | None = None
    rent_variance: Decimal | None = None
    items: list[InvoiceItemOut]


class PaymentOut(_StrictModel):
    payment_id: str
    amount: Decimal
    paid_at: str
    status: str


class StatementOutput(_StrictModel):
    lease_id: str
    currency: str
    invoiced_total: Decimal
    paid_total: Decimal
    outstanding_total: Decimal
    outstanding_invoice_ids: list[str]
    rent_variance_total: Decimal
    invoices: list[InvoiceOut]
    payments: list[PaymentOut]


class ArrearsOutput(_StrictModel):
    lease_id: str
    currency: str
    invoiced_total: Decimal
    paid_total: Decimal
    outstanding_total: Decimal
    outstanding_invoice_ids: list[str]


class WorkOrderOut(_StrictModel):
    work_order_id: str
    category: str
    status: str
    priority: str
    title: str
    reported_at: str
    resolved_at: str | None = None


class WorkOrdersOutput(_StrictModel):
    lease_id: str | None
    unit_id: str | None
    work_order_count: int
    open_count: int
    work_orders: list[WorkOrderOut]


# ---------------- 证据辅助 ----------------

def _m(value: Any) -> str:
    """金额一律以十进制字符串进入证据字段，避免 JSON 浮点。"""

    return str(Decimal(str(value)))


def _draft(
    repository: FixtureRepository,
    *,
    record: dict[str, Any],
    entity: str,
    project_id: str,
    fields: dict[str, Any],
) -> EvidenceDraft:
    return EvidenceDraft(
        evidence_id=record["id"],
        entity=entity,
        project_id=project_id,
        dataset_version=repository.dataset_version,
        as_of_date=repository.as_of_date,
        record_id=record["id"],
        fields=fields,
    )


# ---------------- 工具实现 ----------------

class LeaseLookupTool(BaseTool):
    name = "lease.lookup"
    version = "1.0.0"
    description = "按租约或商铺代码查询租约条款、收费规则与引用文档（只读）"
    required_permissions = frozenset({"lease.read"})
    timeout_seconds = 5.0
    max_attempts = 1
    input_model = LeaseLookupInput
    output_model = LeaseLookupOutput

    def __init__(self, repository: FixtureRepository) -> None:
        self._repository = repository

    async def invoke(self, payload: LeaseLookupInput, context: AgentContext) -> ToolInvocation:
        facts = self._repository.lease_facts(
            project_ids=context.project_ids,
            lease_id=payload.lease_id,
            unit_code=payload.unit_code,
        )
        lease = facts["lease"]
        unit = facts["unit"]
        tenant = facts["tenant"]
        project_id = lease["project_id"]

        evidence: list[EvidenceDraft] = [
            _draft(
                self._repository,
                record=lease,
                entity="lease",
                project_id=project_id,
                fields={
                    "lease_no": lease["lease_no"],
                    "unit_id": lease["unit_id"],
                    "tenant_id": lease["tenant_id"],
                    "start_date": lease["start_date"],
                    "end_date": lease["end_date"],
                    "status": lease["status"],
                    "deposit_amount": _m(lease["deposit_amount"]),
                },
            )
        ]
        if unit is not None:
            evidence.append(
                _draft(
                    self._repository,
                    record=unit,
                    entity="unit",
                    project_id=project_id,
                    fields={
                        "code": unit["code"],
                        "area_sqm": _m(unit["area_sqm"]),
                        "chargeable_area_sqm": _m(unit["chargeable_area_sqm"]),
                        "usage_type": unit["usage_type"],
                    },
                )
            )
        if tenant is not None:
            evidence.append(
                EvidenceDraft(
                    evidence_id=tenant["id"],
                    entity="tenant",
                    project_id=project_id,
                    dataset_version=self._repository.dataset_version,
                    as_of_date=self._repository.as_of_date,
                    record_id=tenant["id"],
                    fields={"code": tenant["code"], "name": tenant["name"], "status": tenant["status"]},
                )
            )
        for rule in facts["rules"]:
            evidence.append(
                _draft(
                    self._repository,
                    record=rule,
                    entity="lease_charge_rule",
                    project_id=project_id,
                    fields={
                        "charge_type": rule["charge_type"],
                        "calculation_method": rule["calculation_method"],
                        "unit_price": _m(rule["unit_price"]),
                        "period_unit": rule["period_unit"],
                        "effective_from": rule["effective_from"],
                        "effective_to": rule["effective_to"],
                    },
                )
            )
        for document in facts["documents"]:
            evidence.append(
                _draft(
                    self._repository,
                    record=document,
                    entity="document",
                    project_id=document["project_id"],
                    fields={
                        "doc_type": document["doc_type"],
                        "version": document["version"],
                        "document_status": document["document_status"],
                    },
                )
            )

        data = LeaseLookupOutput(
            lease_id=lease["id"],
            lease_no=lease["lease_no"],
            project_id=project_id,
            unit_id=lease["unit_id"],
            unit_code=unit["code"] if unit else "",
            tenant_id=lease["tenant_id"],
            currency=lease["currency"],
            deposit_amount=Decimal(lease["deposit_amount"]),
            start_date=lease["start_date"],
            end_date=lease["end_date"],
            status=lease["status"],
            rules=[
                LeaseRuleOut(
                    rule_id=rule["id"],
                    charge_type=rule["charge_type"],
                    calculation_method=rule["calculation_method"],
                    unit_price=Decimal(rule["unit_price"]),
                    effective_from=rule["effective_from"],
                    effective_to=rule["effective_to"],
                )
                for rule in facts["rules"]
            ],
            document_ids=[doc["id"] for doc in facts["documents"]],
            signed_document_ids=[
                doc["id"]
                for doc in facts["documents"]
                if str(doc.get("document_status", "signed")) == "signed"
            ],
            draft_document_ids=[
                doc["id"]
                for doc in facts["documents"]
                if str(doc.get("document_status", "signed")) != "signed"
            ],
            missing_document_ids=facts["missing_documents"],
        )
        return ToolInvocation(data=data.model_dump(), evidence=tuple(evidence))


class BillingStatementTool(BaseTool):
    name = "billing.statement.read"
    version = "1.0.0"
    description = "读取账单、明细、有效付款与核销，并计算应收/已收/未收（只读）"
    required_permissions = frozenset({"billing.read"})
    timeout_seconds = 5.0
    max_attempts = 2
    input_model = BillingStatementInput
    output_model = StatementOutput

    def __init__(self, repository: FixtureRepository) -> None:
        self._repository = repository

    async def invoke(self, payload: BillingStatementInput, context: AgentContext) -> ToolInvocation:
        statement = self._repository.statement(
            project_ids=context.project_ids, lease_id=payload.lease_id
        )
        lease = statement["lease"]
        project_id = lease["project_id"]
        evidence: list[EvidenceDraft] = [
            _draft(
                self._repository,
                record=lease,
                entity="lease",
                project_id=project_id,
                fields={"lease_no": lease["lease_no"], "status": lease["status"]},
            )
        ]
        invoices_out: list[InvoiceOut] = []
        for view in statement["invoices"]:
            invoice = view["invoice"]
            evidence.append(
                _draft(
                    self._repository,
                    record=invoice,
                    entity="invoice",
                    project_id=project_id,
                    fields={
                        "invoice_no": invoice["invoice_no"],
                        "period_start": invoice["period_start"],
                        "period_end": invoice["period_end"],
                        "status": invoice["status"],
                        "total": _m(view["total"]),
                    },
                )
            )
            items_out: list[InvoiceItemOut] = []
            for item in view["items"]:
                evidence.append(
                    _draft(
                        self._repository,
                        record=item,
                        entity="invoice_item",
                        project_id=project_id,
                        fields={
                            "invoice_id": item["invoice_id"],
                            "charge_type": item["charge_type"],
                            "quantity": _m(item["quantity"]),
                            "unit_price": _m(item["unit_price"]),
                            "amount": _m(item["amount"]),
                        },
                    )
                )
                items_out.append(
                    InvoiceItemOut(
                        item_id=item["id"],
                        charge_type=item["charge_type"],
                        quantity=Decimal(item["quantity"]),
                        unit_price=Decimal(item["unit_price"]),
                        amount=Decimal(item["amount"]),
                    )
                )
            if view["rent_rule"] is not None:
                evidence.append(
                    _draft(
                        self._repository,
                        record=view["rent_rule"],
                        entity="lease_charge_rule",
                        project_id=project_id,
                        fields={
                            "charge_type": view["rent_rule"]["charge_type"],
                            "unit_price": _m(view["rent_rule"]["unit_price"]),
                            "effective_from": view["rent_rule"]["effective_from"],
                            "effective_to": view["rent_rule"]["effective_to"],
                        },
                    )
                )
            invoices_out.append(
                InvoiceOut(
                    invoice_id=invoice["id"],
                    period_start=invoice["period_start"],
                    period_end=invoice["period_end"],
                    total=view["total"],
                    outstanding=view["outstanding"],
                    expected_rent=view["expected_rent"],
                    rent_variance=view["rent_variance"],
                    items=items_out,
                )
            )

        payments_out: list[PaymentOut] = []
        for payment in statement["payments"]:
            evidence.append(
                _draft(
                    self._repository,
                    record=payment,
                    entity="payment",
                    project_id=project_id,
                    fields={
                        "receipt_no": payment["receipt_no"],
                        "amount": _m(payment["amount"]),
                        "status": payment["status"],
                        "paid_at": payment["paid_at"],
                    },
                )
            )
            payments_out.append(
                PaymentOut(
                    payment_id=payment["id"],
                    amount=Decimal(payment["amount"]),
                    paid_at=payment["paid_at"],
                    status=payment["status"],
                )
            )
        for allocation in statement["allocations"]:
            evidence.append(
                _draft(
                    self._repository,
                    record=allocation,
                    entity="payment_allocation",
                    project_id=project_id,
                    fields={
                        "payment_id": allocation["payment_id"],
                        "invoice_id": allocation["invoice_id"],
                        "amount": _m(allocation["amount"]),
                        "reversed_at": allocation["reversed_at"],
                    },
                )
            )

        data = StatementOutput(
            lease_id=lease["id"],
            currency=lease["currency"],
            invoiced_total=statement["invoiced_total"],
            paid_total=statement["paid_total"],
            outstanding_total=statement["outstanding_total"],
            outstanding_invoice_ids=statement["outstanding_invoice_ids"],
            rent_variance_total=statement["rent_variance_total"],
            invoices=invoices_out,
            payments=payments_out,
        )
        return ToolInvocation(data=data.model_dump(), evidence=tuple(evidence))


class BillingArrearsTool(BaseTool):
    name = "billing.arrears.calculate"
    version = "1.0.0"
    description = "按账单与有效核销计算应收、已收、未收（只读，Decimal）"
    required_permissions = frozenset({"billing.read"})
    timeout_seconds = 5.0
    max_attempts = 1
    input_model = BillingArrearsInput
    output_model = ArrearsOutput

    def __init__(self, repository: FixtureRepository) -> None:
        self._repository = repository

    async def invoke(self, payload: BillingArrearsInput, context: AgentContext) -> ToolInvocation:
        arrears = self._repository.arrears(
            project_ids=context.project_ids, lease_id=payload.lease_id
        )
        lease = arrears["lease"]
        project_id = lease["project_id"]
        evidence: list[EvidenceDraft] = []
        for view in arrears["invoices"]:
            invoice = view["invoice"]
            evidence.append(
                _draft(
                    self._repository,
                    record=invoice,
                    entity="invoice",
                    project_id=project_id,
                    fields={
                        "invoice_no": invoice["invoice_no"],
                        "period_start": invoice["period_start"],
                        "total": _m(view["total"]),
                        "outstanding": _m(view["outstanding"]),
                    },
                )
            )
            for item in view["items"]:
                evidence.append(
                    _draft(
                        self._repository,
                        record=item,
                        entity="invoice_item",
                        project_id=project_id,
                        fields={
                            "invoice_id": item["invoice_id"],
                            "charge_type": item["charge_type"],
                            "amount": _m(item["amount"]),
                        },
                    )
                )
        for payment in arrears["payments"]:
            evidence.append(
                _draft(
                    self._repository,
                    record=payment,
                    entity="payment",
                    project_id=project_id,
                    fields={"amount": _m(payment["amount"]), "status": payment["status"]},
                )
            )
        for allocation in arrears["allocations"]:
            evidence.append(
                _draft(
                    self._repository,
                    record=allocation,
                    entity="payment_allocation",
                    project_id=project_id,
                    fields={
                        "payment_id": allocation["payment_id"],
                        "invoice_id": allocation["invoice_id"],
                        "amount": _m(allocation["amount"]),
                    },
                )
            )

        data = ArrearsOutput(
            lease_id=lease["id"],
            currency=lease["currency"],
            invoiced_total=arrears["invoiced_total"],
            paid_total=arrears["paid_total"],
            outstanding_total=arrears["outstanding_total"],
            outstanding_invoice_ids=arrears["outstanding_invoice_ids"],
        )
        return ToolInvocation(data=data.model_dump(), evidence=tuple(evidence))


class PropertyWorkOrdersTool(BaseTool):
    name = "property.work_orders.read"
    version = "1.0.0"
    description = "读取维修工单时间线（只读）"
    required_permissions = frozenset({"property.read"})
    timeout_seconds = 5.0
    max_attempts = 1
    input_model = PropertyWorkOrdersInput
    output_model = WorkOrdersOutput

    def __init__(self, repository: FixtureRepository) -> None:
        self._repository = repository

    async def invoke(self, payload: PropertyWorkOrdersInput, context: AgentContext) -> ToolInvocation:
        orders = self._repository.work_orders(
            project_ids=context.project_ids,
            lease_id=payload.lease_id,
            unit_id=payload.unit_id,
            category=payload.category,
        )
        evidence = tuple(
            _draft(
                self._repository,
                record=order,
                entity="work_order",
                project_id=order["project_id"],
                fields={
                    "category": order["category"],
                    "status": order["status"],
                    "priority": order["priority"],
                    "reported_at": order["reported_at"],
                    "resolved_at": order["resolved_at"],
                },
            )
            for order in orders
        )
        data = WorkOrdersOutput(
            lease_id=payload.lease_id,
            unit_id=payload.unit_id,
            work_order_count=len(orders),
            open_count=sum(1 for order in orders if order["status"] != "closed"),
            work_orders=[
                WorkOrderOut(
                    work_order_id=order["id"],
                    category=order["category"],
                    status=order["status"],
                    priority=order["priority"],
                    title=order["title"],
                    reported_at=order["reported_at"],
                    resolved_at=order["resolved_at"],
                )
                for order in orders
            ],
        )
        return ToolInvocation(data=data.model_dump(), evidence=evidence)


def build_fixture_tools(repository: FixtureRepository) -> tuple[BaseTool, ...]:
    """静态工具白名单：新增工具必须在此显式登记。"""

    return (
        LeaseLookupTool(repository),
        BillingStatementTool(repository),
        BillingArrearsTool(repository),
        PropertyWorkOrdersTool(repository),
    )
