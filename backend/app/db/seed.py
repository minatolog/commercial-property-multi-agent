"""把合成 fixture 导入数据库（Task 010）。

只用于本地/测试库：数据源仍是 `docs/evaluation/fixtures/agent_first_v1.json`，
不引入第二份事实源。写入通过 `seed_from_fixture`，业务工具本身没有写权限。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..paths import DEFAULT_FIXTURE_PATH
from .models import (
    Base,
    Building,
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


def _d(value: str) -> date:
    return date.fromisoformat(value)


def _t(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _m(value: Any) -> Decimal:
    return Decimal(str(value))


def create_schema(engine) -> None:
    Base.metadata.create_all(engine)


def seed_from_fixture(session: Session, fixture_path: str | Path | None = None) -> dict[str, int]:
    data = json.loads(Path(fixture_path or DEFAULT_FIXTURE_PATH).read_text(encoding="utf-8"))

    for item in data["projects"]:
        session.add(
            Project(
                id=item["id"],
                code=item["code"],
                name=item["name"],
                city=item.get("city"),
                timezone=item.get("timezone", "Asia/Shanghai"),
                status=item.get("status", "active"),
            )
        )
    for item in data["buildings"]:
        session.add(
            Building(
                id=item["id"],
                project_id=item["project_id"],
                code=item["code"],
                name=item["name"],
            )
        )
    for item in data["units"]:
        session.add(
            Unit(
                id=item["id"],
                project_id=item["project_id"],
                building_id=item["building_id"],
                code=item["code"],
                floor=item.get("floor"),
                area_sqm=_m(item["area_sqm"]),
                chargeable_area_sqm=_m(item["chargeable_area_sqm"]),
                usage_type=item.get("usage_type"),
                physical_status=item.get("physical_status", "normal"),
            )
        )
    for item in data["tenants"]:
        session.add(
            Tenant(
                id=item["id"],
                code=item["code"],
                name=item["name"],
                unified_social_credit_code=item.get("unified_social_credit_code"),
                contact_name=item.get("contact_name"),
                contact_phone=item.get("contact_phone"),
                status=item.get("status", "active"),
            )
        )
    for item in data["leases"]:
        session.add(
            Lease(
                id=item["id"],
                project_id=item["project_id"],
                lease_no=item["lease_no"],
                tenant_id=item["tenant_id"],
                unit_id=item["unit_id"],
                start_date=_d(item["start_date"]),
                end_date=_d(item["end_date"]),
                status=item["status"],
                billing_cycle=item.get("billing_cycle", "monthly"),
                payment_terms_days=item.get("payment_terms_days", 30),
                deposit_amount=_m(item.get("deposit_amount", "0")),
                currency=item.get("currency", "CNY"),
            )
        )
    for item in data["lease_charge_rules"]:
        session.add(
            LeaseChargeRule(
                id=item["id"],
                lease_id=item["lease_id"],
                charge_type=item["charge_type"],
                calculation_method=item["calculation_method"],
                amount=_m(item["amount"]) if item.get("amount") is not None else None,
                unit_price=_m(item["unit_price"]) if item.get("unit_price") is not None else None,
                period_unit=item.get("period_unit", "month"),
                effective_from=_d(item["effective_from"]),
                effective_to=_d(item["effective_to"]),
                is_rent_free=bool(item.get("is_rent_free", False)),
            )
        )
    for item in data["invoices"]:
        session.add(
            Invoice(
                id=item["id"],
                project_id=item["project_id"],
                lease_id=item["lease_id"],
                invoice_no=item["invoice_no"],
                period_start=_d(item["period_start"]),
                period_end=_d(item["period_end"]),
                issue_date=_d(item["issue_date"]),
                due_date=_d(item["due_date"]),
                currency=item.get("currency", "CNY"),
                status=item.get("status", "draft"),
            )
        )
    for item in data["invoice_items"]:
        session.add(
            InvoiceItem(
                id=item["id"],
                invoice_id=item["invoice_id"],
                charge_rule_id=item.get("charge_rule_id"),
                charge_type=item["charge_type"],
                description=item.get("description", ""),
                quantity=_m(item.get("quantity", "1")),
                unit_price=_m(item["unit_price"]) if item.get("unit_price") is not None else None,
                amount=_m(item["amount"]),
            )
        )
    for item in data["payments"]:
        session.add(
            Payment(
                id=item["id"],
                project_id=item["project_id"],
                receipt_no=item["receipt_no"],
                payer_tenant_id=item.get("payer_tenant_id"),
                payment_method=item.get("payment_method", "bank_transfer"),
                amount=_m(item["amount"]),
                currency=item.get("currency", "CNY"),
                paid_at=_t(item["paid_at"]),
                status=item.get("status", "pending_confirmation"),
            )
        )
    for item in data["payment_allocations"]:
        session.add(
            PaymentAllocation(
                id=item["id"],
                payment_id=item["payment_id"],
                invoice_id=item["invoice_id"],
                amount=_m(item["amount"]),
                allocated_at=_t(item["allocated_at"]),
                allocated_by=item.get("allocated_by"),
                reversed_at=_t(item["reversed_at"]) if item.get("reversed_at") else None,
            )
        )
    for item in data["work_orders"]:
        session.add(
            WorkOrder(
                id=item["id"],
                project_id=item["project_id"],
                unit_id=item.get("unit_id"),
                lease_id=item.get("lease_id"),
                work_order_no=item["work_order_no"],
                category=item.get("category", "other"),
                priority=item.get("priority", "normal"),
                status=item.get("status", "open"),
                title=item["title"],
                description=item.get("description"),
                reported_at=_t(item["reported_at"]),
                resolved_at=_t(item["resolved_at"]) if item.get("resolved_at") else None,
                resolution_note=item.get("resolution_note"),
            )
        )
    for item in data["documents"]:
        session.add(
            Document(
                id=item["id"],
                project_id=item["project_id"],
                lease_id=item.get("lease_id"),
                doc_type=item["doc_type"],
                title=item["title"],
                version=item.get("version", 1),
                document_status=item.get("document_status", "signed"),
                checksum_sha256=item.get("checksum_sha256", ""),
            )
        )

    session.flush()
    counts = {
        "projects": len(data["projects"]),
        "buildings": len(data["buildings"]),
        "units": len(data["units"]),
        "tenants": len(data["tenants"]),
        "leases": len(data["leases"]),
        "lease_charge_rules": len(data["lease_charge_rules"]),
        "invoices": len(data["invoices"]),
        "invoice_items": len(data["invoice_items"]),
        "payments": len(data["payments"]),
        "payment_allocations": len(data["payment_allocations"]),
        "work_orders": len(data["work_orders"]),
        "documents": len(data["documents"]),
    }
    return counts