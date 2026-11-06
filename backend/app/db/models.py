"""PostgreSQL 只读业务模型（Task 010）。

只实现 P0 工具真正查询的字段子集；完整 14 表设计见
`docs/architecture/database_design.md`，本文件不宣称实现全部设计。

金额使用 `Money` 类型：PostgreSQL 上是 `NUMERIC(14,2)`（精确十进制），
SQLite（仅用于离线测试）没有十进制类型，退化为 TEXT 存储并转换回 `Decimal`，
避免浮点误差污染财务计算。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


class Base(DeclarativeBase):
    pass


class Money(TypeDecorator):
    """精确金额列。

    - PostgreSQL：原生 `NUMERIC(14,2)`；
    - SQLite：TEXT，绑定/读取时转 `Decimal`（SQLite 的 NUMERIC 会退化为 REAL）。
    """

    impl = Numeric(14, 2)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(Text())
        return dialect.type_descriptor(Numeric(14, 2))

    def process_bind_param(self, value: Any, dialect):
        if value is None:
            return None
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
        return str(amount) if dialect.name == "sqlite" else amount

    def process_result_value(self, value: Any, dialect):
        if value is None:
            return None
        return Decimal(str(value)).quantize(Decimal("0.01"))


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    city: Mapped[str | None] = mapped_column(String(64))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_buildings_project_code"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)


class Unit(Base):
    __tablename__ = "units"
    __table_args__ = (UniqueConstraint("building_id", "code", name="uq_units_building_code"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    building_id: Mapped[str] = mapped_column(ForeignKey("buildings.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    floor: Mapped[str | None] = mapped_column(String(16))
    area_sqm: Mapped[Decimal] = mapped_column(Money, nullable=False)
    chargeable_area_sqm: Mapped[Decimal] = mapped_column(Money, nullable=False)
    usage_type: Mapped[str | None] = mapped_column(String(32))
    physical_status: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    unified_social_credit_code: Mapped[str | None] = mapped_column(String(32), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(64))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class Lease(Base):
    __tablename__ = "leases"
    __table_args__ = (UniqueConstraint("project_id", "lease_no", name="uq_leases_project_no"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    lease_no: Mapped[str] = mapped_column(String(32), nullable=False)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    unit_id: Mapped[str] = mapped_column(ForeignKey("units.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    billing_cycle: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    payment_terms_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    deposit_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")


class LeaseChargeRule(Base):
    __tablename__ = "lease_charge_rules"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lease_id: Mapped[str] = mapped_column(ForeignKey("leases.id"), nullable=False)
    charge_type: Mapped[str] = mapped_column(String(24), nullable=False)
    calculation_method: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Money)
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    period_unit: Mapped[str] = mapped_column(String(8), nullable=False, default="month")
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date] = mapped_column(Date, nullable=False)
    is_rent_free: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("project_id", "invoice_no", name="uq_invoices_project_no"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    lease_id: Mapped[str] = mapped_column(ForeignKey("leases.id"), nullable=False)
    invoice_no: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="draft")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    charge_rule_id: Mapped[str | None] = mapped_column(ForeignKey("lease_charge_rules.id"))
    charge_type: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    quantity: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("1"))
    unit_price: Mapped[Decimal | None] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("project_id", "receipt_no", name="uq_payments_project_no"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    receipt_no: Mapped[str] = mapped_column(String(32), nullable=False)
    payer_tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenants.id"))
    payment_method: Mapped[str] = mapped_column(String(20), nullable=False, default="bank_transfer")
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="CNY")
    paid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending_confirmation")


class PaymentAllocation(Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint("payment_id", "invoice_id", name="uq_allocations_payment_invoice"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.id"), nullable=False)
    invoice_id: Mapped[str] = mapped_column(ForeignKey("invoices.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    allocated_by: Mapped[str | None] = mapped_column(String(64))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        UniqueConstraint("project_id", "work_order_no", name="uq_work_orders_project_no"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    unit_id: Mapped[str | None] = mapped_column(ForeignKey("units.id"))
    lease_id: Mapped[str | None] = mapped_column(ForeignKey("leases.id"))
    work_order_no: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default="other")
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    lease_id: Mapped[str | None] = mapped_column(ForeignKey("leases.id"))
    doc_type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    document_status: Mapped[str] = mapped_column(String(24), nullable=False, default="signed")
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)