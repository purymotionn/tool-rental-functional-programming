from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from .exceptions import ValidationError


Money = Decimal


class ToolStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    RENTED = "rented"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"


class CustomerStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"


class ReservationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    CONVERTED = "converted"
    EXPIRED = "expired"


class RentalStatus(str, Enum):
    ACTIVE = "active"
    OVERDUE = "overdue"
    COMPLETED = "completed"


class MaintenanceStatus(str, Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DamageSeverity(str, Enum):
    COSMETIC = "cosmetic"
    MINOR = "minor"
    MAJOR = "major"
    IRREPARABLE = "irreparable"


@dataclass
class ToolCategory:
    id: str
    name: str
    description: str
    daily_rate: Money
    deposit_rate: Decimal
    late_fee_multiplier: Decimal = Decimal("1.5")
    maintenance_interval_days: int = 90
    max_rental_days: int = 30

    def validate(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValidationError("Идентификатор и название категории обязательны")
        if self.daily_rate <= 0:
            raise ValidationError("Суточный тариф должен быть положительным")
        if not Decimal("0") <= self.deposit_rate <= Decimal("1"):
            raise ValidationError("Доля залога должна находиться между 0 и 1")
        if self.late_fee_multiplier < 1:
            raise ValidationError("Множитель просрочки не может быть меньше 1")
        if self.maintenance_interval_days <= 0 or self.max_rental_days <= 0:
            raise ValidationError("Интервалы должны быть положительными")


@dataclass
class Tool:
    id: str
    inventory_number: str
    name: str
    category_id: str
    purchase_price: Money
    purchased_on: date
    status: ToolStatus = ToolStatus.AVAILABLE
    condition_score: int = 100
    total_rental_days: int = 0
    last_maintenance_on: date | None = None
    notes: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.id.strip() or not self.inventory_number.strip():
            raise ValidationError("У инструмента должны быть идентификаторы")
        if not self.name.strip() or not self.category_id.strip():
            raise ValidationError("Название и категория инструмента обязательны")
        if self.purchase_price <= 0:
            raise ValidationError("Закупочная стоимость должна быть положительной")
        if not 0 <= self.condition_score <= 100:
            raise ValidationError("Состояние оценивается от 0 до 100")

    def is_operational(self) -> bool:
        return self.status not in {ToolStatus.MAINTENANCE, ToolStatus.RETIRED}


@dataclass
class Customer:
    id: str
    full_name: str
    phone: str
    email: str
    registered_at: datetime
    status: CustomerStatus = CustomerStatus.ACTIVE
    completed_rentals: int = 0
    overdue_returns: int = 0
    total_spent: Money = Decimal("0")
    notes: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.id.strip() or not self.full_name.strip():
            raise ValidationError("Идентификатор и имя клиента обязательны")
        if not self.phone.strip():
            raise ValidationError("Телефон клиента обязателен")
        if "@" not in self.email:
            raise ValidationError("Некорректный адрес электронной почты")

    def can_rent(self) -> bool:
        return self.status == CustomerStatus.ACTIVE


@dataclass
class Reservation:
    id: str
    customer_id: str
    tool_ids: list[str]
    start_date: date
    end_date: date
    created_at: datetime
    status: ReservationStatus = ReservationStatus.PENDING
    estimated_price: Money = Decimal("0")
    required_deposit: Money = Decimal("0")
    comment: str = ""

    def validate(self) -> None:
        if not self.tool_ids:
            raise ValidationError("Бронь должна содержать хотя бы один инструмент")
        if self.end_date < self.start_date:
            raise ValidationError("Дата окончания не может быть раньше даты начала")

    @property
    def rental_days(self) -> int:
        return (self.end_date - self.start_date).days + 1


@dataclass
class RentalLine:
    tool_id: str
    daily_rate: Money
    deposit: Money
    issued_condition: int
    returned_condition: int | None = None
    damage_charge: Money = Decimal("0")


@dataclass
class Rental:
    id: str
    customer_id: str
    lines: list[RentalLine]
    start_date: date
    due_date: date
    issued_at: datetime
    status: RentalStatus = RentalStatus.ACTIVE
    discount_rate: Decimal = Decimal("0")
    deposit_paid: Money = Decimal("0")
    returned_at: datetime | None = None
    base_charge: Money = Decimal("0")
    late_charge: Money = Decimal("0")
    damage_charge: Money = Decimal("0")
    final_charge: Money = Decimal("0")
    deposit_refund: Money = Decimal("0")

    def validate(self) -> None:
        if not self.lines:
            raise ValidationError("Аренда должна содержать хотя бы одну позицию")
        if self.due_date < self.start_date:
            raise ValidationError("Срок возврата не может предшествовать выдаче")
        if not Decimal("0") <= self.discount_rate <= Decimal("1"):
            raise ValidationError("Скидка должна находиться между 0 и 1")

    @property
    def planned_days(self) -> int:
        return (self.due_date - self.start_date).days + 1


@dataclass
class DamageReport:
    id: str
    rental_id: str
    tool_id: str
    severity: DamageSeverity
    description: str
    estimated_repair_cost: Money
    reported_at: datetime
    resolved: bool = False

    def validate(self) -> None:
        if not self.description.strip():
            raise ValidationError("Повреждение должно иметь описание")
        if self.estimated_repair_cost < 0:
            raise ValidationError("Стоимость ремонта не может быть отрицательной")


@dataclass
class MaintenanceRecord:
    id: str
    tool_id: str
    reason: str
    planned_on: date
    status: MaintenanceStatus = MaintenanceStatus.PLANNED
    started_on: date | None = None
    completed_on: date | None = None
    cost: Money = Decimal("0")
    result_note: str = ""

    def validate(self) -> None:
        if not self.reason.strip():
            raise ValidationError("Необходимо указать причину обслуживания")
        if self.cost < 0:
            raise ValidationError("Стоимость обслуживания не может быть отрицательной")


@dataclass
class Payment:
    id: str
    rental_id: str
    amount: Money
    kind: str
    created_at: datetime
    comment: str = ""

    def validate(self) -> None:
        if self.amount <= 0:
            raise ValidationError("Сумма платежа должна быть положительной")
        if self.kind not in {"deposit", "charge", "refund"}:
            raise ValidationError("Неизвестный тип платежа")
