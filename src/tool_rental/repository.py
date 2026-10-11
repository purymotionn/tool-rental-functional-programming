from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar

from .exceptions import EntityNotFoundError, ValidationError
from .models import (
    Customer,
    DamageReport,
    MaintenanceRecord,
    Payment,
    Rental,
    Reservation,
    Tool,
    ToolCategory,
)


T = TypeVar("T")


@dataclass
class InMemoryRepository:
    categories: dict[str, ToolCategory] = field(default_factory=dict)
    tools: dict[str, Tool] = field(default_factory=dict)
    customers: dict[str, Customer] = field(default_factory=dict)
    reservations: dict[str, Reservation] = field(default_factory=dict)
    rentals: dict[str, Rental] = field(default_factory=dict)
    damages: dict[str, DamageReport] = field(default_factory=dict)
    maintenance: dict[str, MaintenanceRecord] = field(default_factory=dict)
    payments: dict[str, Payment] = field(default_factory=dict)

    def _add(self, collection: dict[str, T], entity: T, entity_id: str) -> T:
        if entity_id in collection:
            raise ValidationError(f"Объект с идентификатором {entity_id} уже существует")
        collection[entity_id] = entity
        return entity

    def _get(self, collection: dict[str, T], entity_id: str, kind: str) -> T:
        try:
            return collection[entity_id]
        except KeyError as error:
            raise EntityNotFoundError(f"{kind} {entity_id} не найден") from error

    def add_category(self, category: ToolCategory) -> ToolCategory:
        return self._add(self.categories, category, category.id)

    def add_tool(self, tool: Tool) -> Tool:
        return self._add(self.tools, tool, tool.id)

    def add_customer(self, customer: Customer) -> Customer:
        return self._add(self.customers, customer, customer.id)

    def add_reservation(self, reservation: Reservation) -> Reservation:
        return self._add(self.reservations, reservation, reservation.id)

    def add_rental(self, rental: Rental) -> Rental:
        return self._add(self.rentals, rental, rental.id)

    def add_damage(self, damage: DamageReport) -> DamageReport:
        return self._add(self.damages, damage, damage.id)

    def add_maintenance(self, record: MaintenanceRecord) -> MaintenanceRecord:
        return self._add(self.maintenance, record, record.id)

    def add_payment(self, payment: Payment) -> Payment:
        return self._add(self.payments, payment, payment.id)

    def get_category(self, entity_id: str) -> ToolCategory:
        return self._get(self.categories, entity_id, "Категория")

    def get_tool(self, entity_id: str) -> Tool:
        return self._get(self.tools, entity_id, "Инструмент")

    def get_customer(self, entity_id: str) -> Customer:
        return self._get(self.customers, entity_id, "Клиент")

    def get_reservation(self, entity_id: str) -> Reservation:
        return self._get(self.reservations, entity_id, "Бронирование")

    def get_rental(self, entity_id: str) -> Rental:
        return self._get(self.rentals, entity_id, "Аренда")

    def get_maintenance(self, entity_id: str) -> MaintenanceRecord:
        return self._get(self.maintenance, entity_id, "Обслуживание")
