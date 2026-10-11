from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from .exceptions import (
    InsufficientDepositError,
    InvalidStateError,
    ToolUnavailableError,
    ValidationError,
)
from .models import (
    Customer,
    CustomerStatus,
    DamageReport,
    DamageSeverity,
    MaintenanceRecord,
    MaintenanceStatus,
    Payment,
    Rental,
    RentalLine,
    RentalStatus,
    Reservation,
    ReservationStatus,
    Tool,
    ToolCategory,
    ToolStatus,
)
from .repository import InMemoryRepository


CENT = Decimal("0.01")


class RentalService:
    def __init__(self, repository: InMemoryRepository | None = None) -> None:
        self.repository = repository or InMemoryRepository()
        self.current_date = date.today()
        self.current_time = datetime.now()

    def set_clock(self, current_time: datetime) -> None:
        self.current_time = current_time
        self.current_date = current_time.date()

    def _new_id(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:8]}"

    def register_category(
        self,
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
            id=category_id,
            name=name,
            description=description,
            daily_rate=daily_rate,
            deposit_rate=deposit_rate,
            late_fee_multiplier=late_fee_multiplier,
            maintenance_interval_days=maintenance_interval_days,
            max_rental_days=max_rental_days,
        )
        category.validate()
        return self.repository.add_category(category)

    def register_tool(
        self,
        tool_id: str,
        inventory_number: str,
        name: str,
        category_id: str,
        purchase_price: Decimal,
        purchased_on: date,
    ) -> Tool:
        self.repository.get_category(category_id)
        if any(
            tool.inventory_number == inventory_number
            for tool in self.repository.tools.values()
        ):
            raise ValidationError("Инвентарный номер уже используется")
        tool = Tool(
            id=tool_id,
            inventory_number=inventory_number,
            name=name,
            category_id=category_id,
            purchase_price=purchase_price,
            purchased_on=purchased_on,
        )
        tool.validate()
        return self.repository.add_tool(tool)

    def register_customer(
        self,
        customer_id: str,
        full_name: str,
        phone: str,
        email: str,
    ) -> Customer:
        if any(customer.phone == phone for customer in self.repository.customers.values()):
            raise ValidationError("Клиент с таким телефоном уже зарегистрирован")
        customer = Customer(
            id=customer_id,
            full_name=full_name,
            phone=phone,
            email=email,
            registered_at=self.current_time,
        )
        customer.validate()
        return self.repository.add_customer(customer)

    def block_customer(self, customer_id: str, reason: str) -> Customer:
        customer = self.repository.get_customer(customer_id)
        if customer.status == CustomerStatus.BLOCKED:
            raise InvalidStateError("Клиент уже заблокирован")
        if any(
            rental.customer_id == customer_id and rental.status != RentalStatus.COMPLETED
            for rental in self.repository.rentals.values()
        ):
            raise InvalidStateError("Нельзя заблокировать клиента с активной арендой")
        customer.status = CustomerStatus.BLOCKED
        customer.notes.append(f"Блокировка: {reason}")
        return customer

    def unblock_customer(self, customer_id: str, comment: str = "") -> Customer:
        customer = self.repository.get_customer(customer_id)
        if customer.status != CustomerStatus.BLOCKED:
            raise InvalidStateError("Клиент не заблокирован")
        customer.status = CustomerStatus.ACTIVE
        if comment:
            customer.notes.append(f"Разблокировка: {comment}")
        return customer

    def find_available_tools(
        self,
        start_date: date,
        end_date: date,
        category_id: str | None = None,
    ) -> list[Tool]:
        if end_date < start_date:
            raise ValidationError("Некорректный период поиска")
        result: list[Tool] = []
        for tool in self.repository.tools.values():
            if category_id is not None and tool.category_id != category_id:
                continue
            if not tool.is_operational():
                continue
            occupied = False
            for reservation in self.repository.reservations.values():
                if tool.id not in reservation.tool_ids:
                    continue
                if reservation.status not in {
                    ReservationStatus.PENDING,
                    ReservationStatus.CONFIRMED,
                }:
                    continue
                if start_date <= reservation.end_date and end_date >= reservation.start_date:
                    occupied = True
                    break
            if occupied:
                continue
            for rental in self.repository.rentals.values():
                if rental.status == RentalStatus.COMPLETED:
                    continue
                if not any(line.tool_id == tool.id for line in rental.lines):
                    continue
                if start_date <= rental.due_date and end_date >= rental.start_date:
                    occupied = True
                    break
            if not occupied:
                result.append(tool)
        return result

    def create_reservation(
        self,
        customer_id: str,
        tool_ids: list[str],
        start_date: date,
        end_date: date,
        comment: str = "",
    ) -> Reservation:
        customer = self.repository.get_customer(customer_id)
        if not customer.can_rent():
            raise InvalidStateError("Заблокированный клиент не может бронировать")
        if start_date < self.current_date:
            raise ValidationError("Нельзя оформить бронь в прошлом")
        if not tool_ids or len(set(tool_ids)) != len(tool_ids):
            raise ValidationError("Список инструментов пуст или содержит повторы")
        days = (end_date - start_date).days + 1
        if days <= 0:
            raise ValidationError("Некорректный срок аренды")

        available_ids = {
            tool.id for tool in self.find_available_tools(start_date, end_date)
        }
        price = Decimal("0")
        deposit = Decimal("0")
        for tool_id in tool_ids:
            tool = self.repository.get_tool(tool_id)
            category = self.repository.get_category(tool.category_id)
            if tool_id not in available_ids:
                raise ToolUnavailableError(f"Инструмент {tool_id} недоступен")
            if days > category.max_rental_days:
                raise ValidationError(
                    f"Для категории {category.name} разрешено не более "
                    f"{category.max_rental_days} дней"
                )
            price += category.daily_rate * days
            deposit += tool.purchase_price * category.deposit_rate

        discount = Decimal("0")
        if customer.completed_rentals >= 10:
            discount = Decimal("0.10")
        elif customer.completed_rentals >= 5:
            discount = Decimal("0.05")
        if days >= 14:
            discount += Decimal("0.07")
        elif days >= 7:
            discount += Decimal("0.03")
        discount = min(discount, Decimal("0.20"))
        price = (price * (Decimal("1") - discount)).quantize(CENT, ROUND_HALF_UP)
        deposit = deposit.quantize(CENT, ROUND_HALF_UP)

        reservation = Reservation(
            id=self._new_id("res"),
            customer_id=customer_id,
            tool_ids=list(tool_ids),
            start_date=start_date,
            end_date=end_date,
            created_at=self.current_time,
            estimated_price=price,
            required_deposit=deposit,
            comment=comment,
        )
        reservation.validate()
        return self.repository.add_reservation(reservation)

    def confirm_reservation(self, reservation_id: str) -> Reservation:
        reservation = self.repository.get_reservation(reservation_id)
        if reservation.status != ReservationStatus.PENDING:
            raise InvalidStateError("Подтвердить можно только ожидающую бронь")
        reservation.status = ReservationStatus.CONFIRMED
        for tool_id in reservation.tool_ids:
            tool = self.repository.get_tool(tool_id)
            if reservation.start_date == self.current_date:
                tool.status = ToolStatus.RESERVED
        return reservation

    def cancel_reservation(self, reservation_id: str, reason: str) -> Reservation:
        reservation = self.repository.get_reservation(reservation_id)
        if reservation.status not in {
            ReservationStatus.PENDING,
            ReservationStatus.CONFIRMED,
        }:
            raise InvalidStateError("Эту бронь уже нельзя отменить")
        reservation.status = ReservationStatus.CANCELLED
        reservation.comment = f"{reservation.comment}\nОтмена: {reason}".strip()
        for tool_id in reservation.tool_ids:
            tool = self.repository.get_tool(tool_id)
            if tool.status == ToolStatus.RESERVED:
                tool.status = ToolStatus.AVAILABLE
        return reservation

    def expire_reservations(self) -> list[Reservation]:
        expired: list[Reservation] = []
        for reservation in self.repository.reservations.values():
            if reservation.status not in {
                ReservationStatus.PENDING,
                ReservationStatus.CONFIRMED,
            }:
                continue
            if reservation.end_date >= self.current_date:
                continue
            reservation.status = ReservationStatus.EXPIRED
            for tool_id in reservation.tool_ids:
                tool = self.repository.get_tool(tool_id)
                if tool.status == ToolStatus.RESERVED:
                    tool.status = ToolStatus.AVAILABLE
            expired.append(reservation)
        return expired

    def issue_reservation(
        self,
        reservation_id: str,
        deposit_paid: Decimal,
    ) -> Rental:
        reservation = self.repository.get_reservation(reservation_id)
        if reservation.status != ReservationStatus.CONFIRMED:
            raise InvalidStateError("Для выдачи бронь должна быть подтверждена")
        if self.current_date < reservation.start_date:
            raise InvalidStateError("Дата начала аренды ещё не наступила")
        if self.current_date > reservation.end_date:
            raise InvalidStateError("Срок бронирования уже истёк")
        if deposit_paid < reservation.required_deposit:
            raise InsufficientDepositError("Внесён недостаточный залог")

        customer = self.repository.get_customer(reservation.customer_id)
        if not customer.can_rent():
            raise InvalidStateError("Клиент заблокирован")
        lines: list[RentalLine] = []
        discount = Decimal("0")
        raw_price = Decimal("0")
        for tool_id in reservation.tool_ids:
            tool = self.repository.get_tool(tool_id)
            category = self.repository.get_category(tool.category_id)
            if tool.status in {ToolStatus.RENTED, ToolStatus.MAINTENANCE, ToolStatus.RETIRED}:
                raise ToolUnavailableError(f"Инструмент {tool_id} нельзя выдать")
            tool.status = ToolStatus.RENTED
            line_deposit = tool.purchase_price * category.deposit_rate
            lines.append(
                RentalLine(
                    tool_id=tool.id,
                    daily_rate=category.daily_rate,
                    deposit=line_deposit.quantize(CENT, ROUND_HALF_UP),
                    issued_condition=tool.condition_score,
                )
            )
            raw_price += category.daily_rate * reservation.rental_days
        if raw_price > 0:
            discount = Decimal("1") - reservation.estimated_price / raw_price

        rental = Rental(
            id=self._new_id("rent"),
            customer_id=customer.id,
            lines=lines,
            start_date=reservation.start_date,
            due_date=reservation.end_date,
            issued_at=self.current_time,
            discount_rate=discount.quantize(Decimal("0.0001")),
            deposit_paid=deposit_paid,
            base_charge=reservation.estimated_price,
        )
        rental.validate()
        self.repository.add_rental(rental)
        reservation.status = ReservationStatus.CONVERTED
        self.repository.add_payment(
            Payment(
                id=self._new_id("pay"),
                rental_id=rental.id,
                amount=deposit_paid,
                kind="deposit",
                created_at=self.current_time,
            )
        )
        return rental

    def extend_rental(self, rental_id: str, new_due_date: date) -> Rental:
        rental = self.repository.get_rental(rental_id)
        if rental.status == RentalStatus.COMPLETED:
            raise InvalidStateError("Завершённую аренду нельзя продлить")
        if new_due_date <= rental.due_date:
            raise ValidationError("Новый срок должен быть позже текущего")
        total_days = (new_due_date - rental.start_date).days + 1
        for line in rental.lines:
            tool = self.repository.get_tool(line.tool_id)
            category = self.repository.get_category(tool.category_id)
            if total_days > category.max_rental_days:
                raise ValidationError("Превышен максимальный срок аренды")
        for reservation in self.repository.reservations.values():
            if reservation.status not in {
                ReservationStatus.PENDING,
                ReservationStatus.CONFIRMED,
            }:
                continue
            if not set(reservation.tool_ids) & {line.tool_id for line in rental.lines}:
                continue
            if rental.due_date < reservation.start_date <= new_due_date:
                raise ToolUnavailableError("Инструмент забронирован другим клиентом")
        rental.due_date = new_due_date
        base = sum(line.daily_rate * total_days for line in rental.lines)
        rental.base_charge = (
            base * (Decimal("1") - rental.discount_rate)
        ).quantize(CENT, ROUND_HALF_UP)
        return rental

    def mark_overdue_rentals(self) -> list[Rental]:
        overdue: list[Rental] = []
        for rental in self.repository.rentals.values():
            if rental.status == RentalStatus.ACTIVE and rental.due_date < self.current_date:
                rental.status = RentalStatus.OVERDUE
                overdue.append(rental)
        return overdue

    def return_rental(
        self,
        rental_id: str,
        returned_conditions: dict[str, int],
    ) -> Rental:
        rental = self.repository.get_rental(rental_id)
        if rental.status == RentalStatus.COMPLETED:
            raise InvalidStateError("Аренда уже завершена")
        expected_ids = {line.tool_id for line in rental.lines}
        if set(returned_conditions) != expected_ids:
            raise ValidationError("Необходимо указать состояние каждого инструмента")

        late_charge = Decimal("0")
        overdue_days = max(0, (self.current_date - rental.due_date).days)
        damage_charge = Decimal("0")
        for line in rental.lines:
            returned_condition = returned_conditions[line.tool_id]
            if not 0 <= returned_condition <= 100:
                raise ValidationError("Состояние должно находиться между 0 и 100")
            tool = self.repository.get_tool(line.tool_id)
            category = self.repository.get_category(tool.category_id)
            line.returned_condition = returned_condition
            if overdue_days:
                late_charge += line.daily_rate * overdue_days * category.late_fee_multiplier
            condition_loss = line.issued_condition - returned_condition
            if condition_loss > 0:
                if condition_loss >= 50:
                    severity = DamageSeverity.IRREPARABLE
                    line.damage_charge = tool.purchase_price
                elif condition_loss >= 25:
                    severity = DamageSeverity.MAJOR
                    line.damage_charge = tool.purchase_price * Decimal("0.40")
                elif condition_loss >= 10:
                    severity = DamageSeverity.MINOR
                    line.damage_charge = tool.purchase_price * Decimal("0.15")
                else:
                    severity = DamageSeverity.COSMETIC
                    line.damage_charge = tool.purchase_price * Decimal("0.03")
                line.damage_charge = line.damage_charge.quantize(CENT, ROUND_HALF_UP)
                damage = DamageReport(
                    id=self._new_id("damage"),
                    rental_id=rental.id,
                    tool_id=tool.id,
                    severity=severity,
                    description=f"Состояние снизилось на {condition_loss} пунктов",
                    estimated_repair_cost=line.damage_charge,
                    reported_at=self.current_time,
                )
                self.repository.add_damage(damage)
                damage_charge += line.damage_charge
                tool.status = (
                    ToolStatus.RETIRED
                    if severity == DamageSeverity.IRREPARABLE
                    else ToolStatus.MAINTENANCE
                )
            else:
                tool.status = ToolStatus.AVAILABLE
            tool.condition_score = returned_condition
            tool.total_rental_days += (self.current_date - rental.start_date).days + 1

        rental.late_charge = late_charge.quantize(CENT, ROUND_HALF_UP)
        rental.damage_charge = damage_charge.quantize(CENT, ROUND_HALF_UP)
        rental.final_charge = (
            rental.base_charge + rental.late_charge + rental.damage_charge
        ).quantize(CENT, ROUND_HALF_UP)
        rental.deposit_refund = max(
            Decimal("0"), rental.deposit_paid - rental.final_charge
        ).quantize(CENT, ROUND_HALF_UP)
        rental.returned_at = self.current_time
        rental.status = RentalStatus.COMPLETED

        customer = self.repository.get_customer(rental.customer_id)
        customer.completed_rentals += 1
        customer.total_spent += rental.final_charge
        if overdue_days:
            customer.overdue_returns += 1
        if rental.final_charge > 0:
            self.repository.add_payment(
                Payment(
                    id=self._new_id("pay"),
                    rental_id=rental.id,
                    amount=rental.final_charge,
                    kind="charge",
                    created_at=self.current_time,
                )
            )
        if rental.deposit_refund > 0:
            self.repository.add_payment(
                Payment(
                    id=self._new_id("pay"),
                    rental_id=rental.id,
                    amount=rental.deposit_refund,
                    kind="refund",
                    created_at=self.current_time,
                )
            )
        return rental

    def schedule_maintenance(
        self,
        tool_id: str,
        reason: str,
        planned_on: date,
    ) -> MaintenanceRecord:
        tool = self.repository.get_tool(tool_id)
        if tool.status in {ToolStatus.RENTED, ToolStatus.RETIRED}:
            raise InvalidStateError("Инструмент нельзя отправить на обслуживание")
        record = MaintenanceRecord(
            id=self._new_id("mnt"),
            tool_id=tool_id,
            reason=reason,
            planned_on=planned_on,
        )
        record.validate()
        return self.repository.add_maintenance(record)

    def start_maintenance(self, record_id: str) -> MaintenanceRecord:
        record = self.repository.get_maintenance(record_id)
        if record.status != MaintenanceStatus.PLANNED:
            raise InvalidStateError("Начать можно только запланированное обслуживание")
        tool = self.repository.get_tool(record.tool_id)
        if tool.status == ToolStatus.RENTED:
            raise InvalidStateError("Выданный инструмент нельзя обслуживать")
        record.status = MaintenanceStatus.IN_PROGRESS
        record.started_on = self.current_date
        tool.status = ToolStatus.MAINTENANCE
        return record

    def complete_maintenance(
        self,
        record_id: str,
        cost: Decimal,
        restored_condition: int,
        result_note: str,
    ) -> MaintenanceRecord:
        record = self.repository.get_maintenance(record_id)
        if record.status != MaintenanceStatus.IN_PROGRESS:
            raise InvalidStateError("Обслуживание ещё не начато")
        if cost < 0 or not 0 <= restored_condition <= 100:
            raise ValidationError("Некорректный результат обслуживания")
        tool = self.repository.get_tool(record.tool_id)
        record.status = MaintenanceStatus.COMPLETED
        record.completed_on = self.current_date
        record.cost = cost
        record.result_note = result_note
        tool.condition_score = restored_condition
        tool.last_maintenance_on = self.current_date
        tool.status = ToolStatus.AVAILABLE
        tool.notes.append(f"Обслуживание {record.id}: {result_note}")
        for damage in self.repository.damages.values():
            if damage.tool_id == tool.id and not damage.resolved:
                damage.resolved = True
        return record

    def tools_requiring_maintenance(self) -> list[Tool]:
        result: list[Tool] = []
        for tool in self.repository.tools.values():
            if tool.status in {ToolStatus.RENTED, ToolStatus.RETIRED}:
                continue
            category = self.repository.get_category(tool.category_id)
            reference = tool.last_maintenance_on or tool.purchased_on
            elapsed = (self.current_date - reference).days
            if elapsed >= category.maintenance_interval_days or tool.condition_score < 70:
                result.append(tool)
        return result

    def rental_statistics(self) -> dict[str, object]:
        completed = [
            rental
            for rental in self.repository.rentals.values()
            if rental.status == RentalStatus.COMPLETED
        ]
        revenue = sum((rental.final_charge for rental in completed), Decimal("0"))
        overdue_count = sum(1 for rental in completed if rental.late_charge > 0)
        category_days: dict[str, int] = {}
        for rental in completed:
            actual_end = rental.returned_at.date() if rental.returned_at else rental.due_date
            days = (actual_end - rental.start_date).days + 1
            for line in rental.lines:
                tool = self.repository.get_tool(line.tool_id)
                category_days[tool.category_id] = category_days.get(tool.category_id, 0) + days
        popular_category = (
            max(category_days, key=category_days.get) if category_days else None
        )
        return {
            "completed_rentals": len(completed),
            "active_rentals": sum(
                rental.status != RentalStatus.COMPLETED
                for rental in self.repository.rentals.values()
            ),
            "revenue": revenue.quantize(CENT, ROUND_HALF_UP),
            "overdue_count": overdue_count,
            "popular_category_id": popular_category,
            "registered_customers": len(self.repository.customers),
            "tools_total": len(self.repository.tools),
        }
