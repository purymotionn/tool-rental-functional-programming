from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from .models import (
    Customer,
    DamageReport,
    DamageSeverity,
    MaintenanceRecord,
    Payment,
    Rental,
    RentalLine,
    Reservation,
    Tool,
    ToolCategory,
)


def make_category(
    category_id: str,
    name: str,
    description: str,
    daily_rate: Decimal,
    deposit_rate: Decimal,
    late_fee_multiplier: Decimal = Decimal("1.5"),
    maintenance_interval_days: int = 90,
    max_rental_days: int = 30,
) -> ToolCategory:
    category = ToolCategory(
        id=category_id.strip(),
        name=name.strip(),
        description=description.strip(),
        daily_rate=daily_rate,
        deposit_rate=deposit_rate,
        late_fee_multiplier=late_fee_multiplier,
        maintenance_interval_days=maintenance_interval_days,
        max_rental_days=max_rental_days,
    )
    category.validate()
    return category


def make_tool(
    tool_id: str,
    inventory_number: str,
    name: str,
    category_id: str,
    purchase_price: Decimal,
    purchased_on: date,
) -> Tool:
    tool = Tool(
        id=tool_id.strip(),
        inventory_number=inventory_number.strip().upper(),
        name=name.strip(),
        category_id=category_id.strip(),
        purchase_price=purchase_price,
        purchased_on=purchased_on,
    )
    tool.validate()
    return tool


def make_customer(
    customer_id: str,
    full_name: str,
    phone: str,
    email: str,
    registered_at: datetime,
) -> Customer:
    customer = Customer(
        id=customer_id.strip(),
        full_name=" ".join(full_name.split()),
        phone=phone.strip(),
        email=email.strip().lower(),
        registered_at=registered_at,
    )
    customer.validate()
    return customer


def make_reservation(
    reservation_id: str,
    customer_id: str,
    tool_ids: Sequence[str],
    start_date: date,
    end_date: date,
    created_at: datetime,
    estimated_price: Decimal,
    required_deposit: Decimal,
    comment: str = "",
) -> Reservation:
    reservation = Reservation(
        id=reservation_id,
        customer_id=customer_id,
        tool_ids=list(tool_ids),
        start_date=start_date,
        end_date=end_date,
        created_at=created_at,
        estimated_price=estimated_price,
        required_deposit=required_deposit,
        comment=comment.strip(),
    )
    reservation.validate()
    return reservation


def make_rental_line(
    tool_id: str,
    daily_rate: Decimal,
    deposit: Decimal,
    issued_condition: int,
) -> RentalLine:
    return RentalLine(
        tool_id=tool_id,
        daily_rate=daily_rate,
        deposit=deposit,
        issued_condition=issued_condition,
    )


def make_rental(
    rental_id: str,
    customer_id: str,
    lines: Sequence[RentalLine],
    start_date: date,
    due_date: date,
    issued_at: datetime,
    discount_rate: Decimal,
    deposit_paid: Decimal,
    base_charge: Decimal,
) -> Rental:
    rental = Rental(
        id=rental_id,
        customer_id=customer_id,
        lines=list(lines),
        start_date=start_date,
        due_date=due_date,
        issued_at=issued_at,
        discount_rate=discount_rate,
        deposit_paid=deposit_paid,
        base_charge=base_charge,
    )
    rental.validate()
    return rental


def make_damage_report(
    report_id: str,
    rental_id: str,
    tool_id: str,
    severity: DamageSeverity,
    condition_loss: int,
    estimated_repair_cost: Decimal,
    reported_at: datetime,
) -> DamageReport:
    report = DamageReport(
        id=report_id,
        rental_id=rental_id,
        tool_id=tool_id,
        severity=severity,
        description=f"Состояние снизилось на {condition_loss} пунктов",
        estimated_repair_cost=estimated_repair_cost,
        reported_at=reported_at,
    )
    report.validate()
    return report


def make_maintenance_record(
    record_id: str,
    tool_id: str,
    reason: str,
    planned_on: date,
) -> MaintenanceRecord:
    record = MaintenanceRecord(
        id=record_id,
        tool_id=tool_id,
        reason=reason.strip(),
        planned_on=planned_on,
    )
    record.validate()
    return record


def make_payment(
    payment_id: str,
    rental_id: str,
    amount: Decimal,
    kind: str,
    created_at: datetime,
    comment: str = "",
) -> Payment:
    payment = Payment(
        id=payment_id,
        rental_id=rental_id,
        amount=amount,
        kind=kind,
        created_at=created_at,
        comment=comment.strip(),
    )
    payment.validate()
    return payment
