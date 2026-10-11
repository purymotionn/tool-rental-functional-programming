from datetime import date, datetime
from decimal import Decimal
import unittest

from tool_rental.constructors import (
    make_category,
    make_customer,
    make_payment,
    make_reservation,
    make_tool,
)
from tool_rental.exceptions import ValidationError
from tool_rental.models import CustomerStatus, ReservationStatus, ToolStatus
from tool_rental.transformations import (
    add_element_last,
    add_text_line,
    change_customer_status,
    change_reservation_status,
    change_tool_status,
)


class ConstructorTests(unittest.TestCase):
    def test_category_constructor_normalizes_text(self) -> None:
        category = make_category(
            " drills ",
            " Дрели ",
            " Описание ",
            Decimal("500"),
            Decimal("0.2"),
        )
        self.assertEqual("drills", category.id)
        self.assertEqual("Дрели", category.name)

    def test_category_constructor_validates_data(self) -> None:
        with self.assertRaises(ValidationError):
            make_category("x", "X", "", Decimal("-1"), Decimal("0.2"))

    def test_tool_constructor_normalizes_inventory_number(self) -> None:
        tool = make_tool(
            " t-1 ",
            " inv-001 ",
            " Дрель ",
            " drills ",
            Decimal("10000"),
            date(2026, 1, 1),
        )
        self.assertEqual("t-1", tool.id)
        self.assertEqual("INV-001", tool.inventory_number)
        self.assertEqual("drills", tool.category_id)

    def test_customer_constructor_normalizes_fields(self) -> None:
        customer = make_customer(
            " c-1 ",
            " Иван   Петров ",
            " +7-900 ",
            " USER@EXAMPLE.RU ",
            datetime(2026, 1, 1),
        )
        self.assertEqual("c-1", customer.id)
        self.assertEqual("Иван Петров", customer.full_name)
        self.assertEqual("user@example.ru", customer.email)

    def test_reservation_constructor_copies_tool_list(self) -> None:
        tool_ids = ["t-1"]
        reservation = make_reservation(
            "r-1",
            "c-1",
            tool_ids,
            date(2026, 1, 1),
            date(2026, 1, 2),
            datetime(2025, 12, 20),
            Decimal("1000"),
            Decimal("2000"),
        )
        tool_ids.append("t-2")
        self.assertEqual(["t-1"], reservation.tool_ids)

    def test_payment_constructor_validates_kind(self) -> None:
        with self.assertRaises(ValidationError):
            make_payment(
                "p-1",
                "r-1",
                Decimal("100"),
                "unknown",
                datetime(2026, 1, 1),
            )


class TransformationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.customer = make_customer(
            "c-1",
            "Иван Петров",
            "+7-900",
            "user@example.ru",
            datetime(2026, 1, 1),
        )
        self.tool = make_tool(
            "t-1",
            "INV-001",
            "Дрель",
            "drills",
            Decimal("10000"),
            date(2026, 1, 1),
        )
        self.reservation = make_reservation(
            "r-1",
            "c-1",
            ["t-1"],
            date(2026, 2, 1),
            date(2026, 2, 2),
            datetime(2026, 1, 20),
            Decimal("1000"),
            Decimal("2000"),
            "Исходный комментарий",
        )

    def test_add_element_last_does_not_mutate_source(self) -> None:
        source = ["first"]
        result = add_element_last(source, "second")
        self.assertEqual(["first"], source)
        self.assertEqual(["first", "second"], result)
        self.assertIsNot(source, result)

    def test_add_text_line_handles_empty_text(self) -> None:
        self.assertEqual("Строка", add_text_line("", "Строка"))
        self.assertEqual("Первая\nВторая", add_text_line("Первая", "Вторая"))

    def test_customer_status_is_changed_in_copy(self) -> None:
        updated = change_customer_status(
            self.customer,
            CustomerStatus.BLOCKED,
            "Блокировка: нарушение",
        )
        self.assertIsNot(self.customer, updated)
        self.assertEqual(CustomerStatus.ACTIVE, self.customer.status)
        self.assertEqual(CustomerStatus.BLOCKED, updated.status)
        self.assertEqual([], self.customer.notes)
        self.assertEqual(["Блокировка: нарушение"], updated.notes)

    def test_tool_status_is_changed_in_copy(self) -> None:
        updated = change_tool_status(self.tool, ToolStatus.RENTED)
        self.assertIsNot(self.tool, updated)
        self.assertEqual(ToolStatus.AVAILABLE, self.tool.status)
        self.assertEqual(ToolStatus.RENTED, updated.status)

    def test_reservation_status_is_changed_in_copy(self) -> None:
        updated = change_reservation_status(
            self.reservation,
            ReservationStatus.CANCELLED,
            "Отмена: планы изменились",
        )
        self.assertIsNot(self.reservation, updated)
        self.assertEqual(ReservationStatus.PENDING, self.reservation.status)
        self.assertEqual(ReservationStatus.CANCELLED, updated.status)
        self.assertEqual("Исходный комментарий", self.reservation.comment)
        self.assertIn("Отмена:", updated.comment)

    def test_nested_tool_list_is_copied(self) -> None:
        updated = change_reservation_status(
            self.reservation,
            ReservationStatus.CONFIRMED,
        )
        updated.tool_ids.append("t-2")
        self.assertEqual(["t-1"], self.reservation.tool_ids)


if __name__ == "__main__":
    unittest.main()

