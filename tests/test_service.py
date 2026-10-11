from datetime import date, datetime
from decimal import Decimal
import unittest

from tool_rental.exceptions import (
    InsufficientDepositError,
    InvalidStateError,
    ToolUnavailableError,
    ValidationError,
)
from tool_rental.models import (
    CustomerStatus,
    DamageSeverity,
    MaintenanceStatus,
    RentalStatus,
    ReservationStatus,
    ToolStatus,
)
from tool_rental.sample_data import create_demo_service


class ServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = create_demo_service(datetime(2026, 10, 11, 9, 0))

    def reserve(
        self,
        tool_ids: list[str] | None = None,
        start: date = date(2026, 10, 12),
        end: date = date(2026, 10, 14),
        customer_id: str = "customer-001",
    ):
        return self.service.create_reservation(
            customer_id,
            tool_ids or ["tool-001"],
            start,
            end,
            "Тестовая бронь",
        )

    def issue(self, reservation=None, paid: Decimal | None = None):
        reservation = reservation or self.reserve(
            start=date(2026, 10, 11), end=date(2026, 10, 13)
        )
        self.service.confirm_reservation(reservation.id)
        return self.service.issue_reservation(
            reservation.id,
            paid if paid is not None else reservation.required_deposit,
        )


class RegistrationTests(ServiceTestCase):
    def test_demo_data_contains_expected_entities(self) -> None:
        self.assertEqual(4, len(self.service.repository.categories))
        self.assertEqual(7, len(self.service.repository.tools))
        self.assertEqual(3, len(self.service.repository.customers))

    def test_register_category_validates_rate(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.register_category(
                "bad", "Некорректная", "", Decimal("0"), Decimal("0.2")
            )

    def test_register_tool_requires_existing_category(self) -> None:
        with self.assertRaises(Exception):
            self.service.register_tool(
                "new", "INV-X", "Инструмент", "missing", Decimal("100"), date.today()
            )

    def test_inventory_number_must_be_unique(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.register_tool(
                "new",
                "INV-2026-001",
                "Другой инструмент",
                "drills",
                Decimal("10000"),
                date(2026, 10, 1),
            )

    def test_phone_must_be_unique(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.register_customer(
                "new", "Новый клиент", "+7-900-100-20-30", "new@example.ru"
            )

    def test_customer_email_is_validated(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.register_customer("new", "Клиент", "+7-1", "invalid")

    def test_block_and_unblock_customer(self) -> None:
        customer = self.service.block_customer("customer-001", "Документы просрочены")
        self.assertEqual(CustomerStatus.BLOCKED, customer.status)
        self.assertIn("Документы", customer.notes[-1])
        customer = self.service.unblock_customer("customer-001", "Документы обновлены")
        self.assertEqual(CustomerStatus.ACTIVE, customer.status)

    def test_cannot_block_customer_with_active_rental(self) -> None:
        self.issue()
        with self.assertRaises(InvalidStateError):
            self.service.block_customer("customer-001", "Проверка")


class AvailabilityTests(ServiceTestCase):
    def test_all_operational_tools_are_initially_available(self) -> None:
        tools = self.service.find_available_tools(
            date(2026, 10, 12), date(2026, 10, 13)
        )
        self.assertEqual(7, len(tools))

    def test_filter_by_category(self) -> None:
        tools = self.service.find_available_tools(
            date(2026, 10, 12), date(2026, 10, 13), "saws"
        )
        self.assertEqual({"tool-003", "tool-004"}, {tool.id for tool in tools})

    def test_overlapping_reservation_hides_tool(self) -> None:
        self.reserve(start=date(2026, 10, 12), end=date(2026, 10, 15))
        tools = self.service.find_available_tools(
            date(2026, 10, 14), date(2026, 10, 16)
        )
        self.assertNotIn("tool-001", {tool.id for tool in tools})

    def test_adjacent_non_overlapping_period_is_available(self) -> None:
        self.reserve(start=date(2026, 10, 12), end=date(2026, 10, 15))
        tools = self.service.find_available_tools(
            date(2026, 10, 16), date(2026, 10, 17)
        )
        self.assertIn("tool-001", {tool.id for tool in tools})

    def test_cancelled_reservation_does_not_hide_tool(self) -> None:
        reservation = self.reserve()
        self.service.cancel_reservation(reservation.id, "Передумал")
        tools = self.service.find_available_tools(
            date(2026, 10, 12), date(2026, 10, 14)
        )
        self.assertIn("tool-001", {tool.id for tool in tools})

    def test_maintenance_tool_is_not_available(self) -> None:
        record = self.service.schedule_maintenance(
            "tool-001", "Регламент", date(2026, 10, 11)
        )
        self.service.start_maintenance(record.id)
        tools = self.service.find_available_tools(
            date(2026, 10, 12), date(2026, 10, 14)
        )
        self.assertNotIn("tool-001", {tool.id for tool in tools})


class ReservationTests(ServiceTestCase):
    def test_create_reservation_calculates_price_and_deposit(self) -> None:
        reservation = self.reserve(["tool-001", "tool-005"])
        self.assertEqual(Decimal("3450.00"), reservation.estimated_price)
        self.assertEqual(Decimal("11075.00"), reservation.required_deposit)
        self.assertEqual(ReservationStatus.PENDING, reservation.status)

    def test_week_discount_is_applied(self) -> None:
        reservation = self.reserve(
            ["tool-001"], date(2026, 10, 12), date(2026, 10, 18)
        )
        self.assertEqual(Decimal("4413.50"), reservation.estimated_price)

    def test_loyal_customer_gets_discount(self) -> None:
        self.service.repository.get_customer("customer-001").completed_rentals = 10
        reservation = self.reserve()
        self.assertEqual(Decimal("1755.00"), reservation.estimated_price)

    def test_discounts_are_limited(self) -> None:
        customer = self.service.repository.get_customer("customer-001")
        customer.completed_rentals = 100
        reservation = self.reserve(
            ["tool-001"], date(2026, 10, 12), date(2026, 10, 25)
        )
        self.assertGreaterEqual(reservation.estimated_price, Decimal("7280"))

    def test_cannot_reserve_in_past(self) -> None:
        with self.assertRaises(ValidationError):
            self.reserve(start=date(2026, 10, 10), end=date(2026, 10, 12))

    def test_cannot_reserve_duplicate_tool(self) -> None:
        with self.assertRaises(ValidationError):
            self.reserve(["tool-001", "tool-001"])

    def test_cannot_reserve_for_too_long(self) -> None:
        with self.assertRaises(ValidationError):
            self.reserve(
                ["tool-003"], date(2026, 10, 12), date(2026, 10, 27)
            )

    def test_blocked_customer_cannot_reserve(self) -> None:
        self.service.block_customer("customer-001", "Нарушение правил")
        with self.assertRaises(InvalidStateError):
            self.reserve()

    def test_same_tool_cannot_be_reserved_twice(self) -> None:
        self.reserve()
        with self.assertRaises(ToolUnavailableError):
            self.reserve(start=date(2026, 10, 13), end=date(2026, 10, 16))

    def test_confirm_reservation(self) -> None:
        reservation = self.reserve(start=date(2026, 10, 11))
        result = self.service.confirm_reservation(reservation.id)
        self.assertEqual(ReservationStatus.CONFIRMED, result.status)
        self.assertEqual(ToolStatus.RESERVED, self.service.repository.get_tool("tool-001").status)

    def test_cannot_confirm_twice(self) -> None:
        reservation = self.reserve()
        self.service.confirm_reservation(reservation.id)
        with self.assertRaises(InvalidStateError):
            self.service.confirm_reservation(reservation.id)

    def test_cancel_reservation(self) -> None:
        reservation = self.reserve(start=date(2026, 10, 11))
        self.service.confirm_reservation(reservation.id)
        result = self.service.cancel_reservation(reservation.id, "Изменились планы")
        self.assertEqual(ReservationStatus.CANCELLED, result.status)
        self.assertEqual(ToolStatus.AVAILABLE, self.service.repository.get_tool("tool-001").status)

    def test_expire_old_reservations(self) -> None:
        reservation = self.reserve(
            start=date(2026, 10, 11), end=date(2026, 10, 12)
        )
        self.service.set_clock(datetime(2026, 10, 13, 9, 0))
        expired = self.service.expire_reservations()
        self.assertEqual([reservation.id], [item.id for item in expired])
        self.assertEqual(ReservationStatus.EXPIRED, reservation.status)


class IssueAndExtensionTests(ServiceTestCase):
    def test_issue_changes_tool_and_reservation_states(self) -> None:
        reservation = self.reserve(
            start=date(2026, 10, 11), end=date(2026, 10, 13)
        )
        rental = self.issue(reservation)
        self.assertEqual(RentalStatus.ACTIVE, rental.status)
        stored = self.service.repository.get_reservation(reservation.id)
        self.assertEqual(ReservationStatus.CONVERTED, stored.status)
        self.assertEqual(ReservationStatus.PENDING, reservation.status)
        self.assertEqual(ToolStatus.RENTED, self.service.repository.get_tool("tool-001").status)
        self.assertEqual(1, len(self.service.repository.payments))

    def test_insufficient_deposit_is_rejected(self) -> None:
        reservation = self.reserve(
            start=date(2026, 10, 11), end=date(2026, 10, 13)
        )
        self.service.confirm_reservation(reservation.id)
        with self.assertRaises(InsufficientDepositError):
            self.service.issue_reservation(
                reservation.id, reservation.required_deposit - Decimal("1")
            )

    def test_cannot_issue_unconfirmed_reservation(self) -> None:
        reservation = self.reserve(start=date(2026, 10, 11))
        with self.assertRaises(InvalidStateError):
            self.service.issue_reservation(reservation.id, Decimal("100000"))

    def test_extend_rental_recalculates_base_charge(self) -> None:
        rental = self.issue()
        result = self.service.extend_rental(rental.id, date(2026, 10, 15))
        self.assertEqual(date(2026, 10, 15), result.due_date)
        self.assertEqual(Decimal("3250.00"), result.base_charge)

    def test_cannot_shorten_rental_with_extend(self) -> None:
        rental = self.issue()
        with self.assertRaises(ValidationError):
            self.service.extend_rental(rental.id, date(2026, 10, 12))

    def test_future_reservation_prevents_extension(self) -> None:
        rental = self.issue()
        self.reserve(start=date(2026, 10, 15), end=date(2026, 10, 16))
        with self.assertRaises(ToolUnavailableError):
            self.service.extend_rental(rental.id, date(2026, 10, 15))

    def test_mark_overdue(self) -> None:
        rental = self.issue()
        self.service.set_clock(datetime(2026, 10, 14, 9, 0))
        marked = self.service.mark_overdue_rentals()
        self.assertEqual([rental.id], [item.id for item in marked])
        self.assertEqual(RentalStatus.OVERDUE, rental.status)


class ReturnTests(ServiceTestCase):
    def test_return_without_delay_or_damage(self) -> None:
        rental = self.issue()
        self.service.set_clock(datetime(2026, 10, 13, 15, 0))
        result = self.service.return_rental(rental.id, {"tool-001": 100})
        self.assertEqual(RentalStatus.COMPLETED, result.status)
        self.assertEqual(Decimal("0.00"), result.late_charge)
        self.assertEqual(Decimal("0.00"), result.damage_charge)
        self.assertEqual(Decimal("1950.00"), result.final_charge)
        self.assertEqual(ToolStatus.AVAILABLE, self.service.repository.get_tool("tool-001").status)

    def test_return_calculates_late_charge(self) -> None:
        rental = self.issue()
        self.service.set_clock(datetime(2026, 10, 15, 15, 0))
        result = self.service.return_rental(rental.id, {"tool-001": 100})
        self.assertEqual(Decimal("1950.00"), result.late_charge)
        self.assertEqual(1, self.service.repository.get_customer("customer-001").overdue_returns)

    def test_cosmetic_damage_is_recorded(self) -> None:
        rental = self.issue()
        result = self.service.return_rental(rental.id, {"tool-001": 95})
        self.assertEqual(Decimal("720.00"), result.damage_charge)
        damage = next(iter(self.service.repository.damages.values()))
        self.assertEqual(DamageSeverity.COSMETIC, damage.severity)
        self.assertEqual(ToolStatus.MAINTENANCE, self.service.repository.get_tool("tool-001").status)

    def test_major_damage_is_recorded(self) -> None:
        rental = self.issue()
        result = self.service.return_rental(rental.id, {"tool-001": 70})
        self.assertEqual(Decimal("9600.00"), result.damage_charge)
        damage = next(iter(self.service.repository.damages.values()))
        self.assertEqual(DamageSeverity.MAJOR, damage.severity)

    def test_irreparable_tool_is_retired(self) -> None:
        rental = self.issue()
        self.service.return_rental(rental.id, {"tool-001": 40})
        self.assertEqual(ToolStatus.RETIRED, self.service.repository.get_tool("tool-001").status)

    def test_missing_condition_is_rejected(self) -> None:
        reservation = self.reserve(
            ["tool-001", "tool-005"], date(2026, 10, 11), date(2026, 10, 13)
        )
        rental = self.issue(reservation)
        with self.assertRaises(ValidationError):
            self.service.return_rental(rental.id, {"tool-001": 100})

    def test_return_updates_customer_statistics(self) -> None:
        rental = self.issue()
        result = self.service.return_rental(rental.id, {"tool-001": 100})
        customer = self.service.repository.get_customer("customer-001")
        self.assertEqual(1, customer.completed_rentals)
        self.assertEqual(result.final_charge, customer.total_spent)

    def test_cannot_return_twice(self) -> None:
        rental = self.issue()
        self.service.return_rental(rental.id, {"tool-001": 100})
        with self.assertRaises(InvalidStateError):
            self.service.return_rental(rental.id, {"tool-001": 100})


class MaintenanceTests(ServiceTestCase):
    def test_schedule_start_and_complete(self) -> None:
        record = self.service.schedule_maintenance(
            "tool-001", "Замена щёток", date(2026, 10, 12)
        )
        self.assertEqual(MaintenanceStatus.PLANNED, record.status)
        self.service.start_maintenance(record.id)
        self.assertEqual(MaintenanceStatus.IN_PROGRESS, record.status)
        self.assertEqual(ToolStatus.MAINTENANCE, self.service.repository.get_tool("tool-001").status)
        self.service.complete_maintenance(
            record.id, Decimal("1200"), 97, "Щётки заменены"
        )
        self.assertEqual(MaintenanceStatus.COMPLETED, record.status)
        self.assertEqual(ToolStatus.AVAILABLE, self.service.repository.get_tool("tool-001").status)

    def test_rented_tool_cannot_be_scheduled(self) -> None:
        self.issue()
        with self.assertRaises(InvalidStateError):
            self.service.schedule_maintenance(
                "tool-001", "Регламент", date(2026, 10, 12)
            )

    def test_old_tool_requires_maintenance(self) -> None:
        tools = self.service.tools_requiring_maintenance()
        self.assertIn("tool-001", {tool.id for tool in tools})

    def test_low_condition_requires_maintenance(self) -> None:
        self.service.repository.get_tool("tool-006").condition_score = 60
        tools = self.service.tools_requiring_maintenance()
        self.assertIn("tool-006", {tool.id for tool in tools})

    def test_completed_maintenance_resolves_damage(self) -> None:
        rental = self.issue()
        self.service.return_rental(rental.id, {"tool-001": 80})
        record = self.service.schedule_maintenance(
            "tool-001", "Ремонт повреждений", date(2026, 10, 12)
        )
        self.service.start_maintenance(record.id)
        self.service.complete_maintenance(record.id, Decimal("1000"), 95, "Готово")
        self.assertTrue(all(item.resolved for item in self.service.repository.damages.values()))


class StatisticsTests(ServiceTestCase):
    def test_empty_statistics(self) -> None:
        result = self.service.rental_statistics()
        self.assertEqual(0, result["completed_rentals"])
        self.assertEqual(Decimal("0.00"), result["revenue"])
        self.assertIsNone(result["popular_category_id"])

    def test_completed_rental_appears_in_statistics(self) -> None:
        rental = self.issue()
        self.service.return_rental(rental.id, {"tool-001": 100})
        result = self.service.rental_statistics()
        self.assertEqual(1, result["completed_rentals"])
        self.assertEqual(Decimal("1950.00"), result["revenue"])
        self.assertEqual("drills", result["popular_category_id"])


if __name__ == "__main__":
    unittest.main()
