from datetime import date
from decimal import Decimal
import unittest

from tool_rental.calculations import (
    ReturnLineInput,
    ToolPricingInput,
    calculate_damage_charge,
    calculate_duration_discount,
    calculate_extended_charge,
    calculate_loyalty_discount,
    calculate_rental_quote,
    calculate_return_line,
    classify_damage,
    combine_discounts,
    money,
    most_popular_key,
    overdue_days,
    periods_overlap,
    rental_days,
    requires_maintenance,
    summarize_return,
)
from tool_rental.exceptions import ValidationError
from tool_rental.models import DamageSeverity


class DateCalculationTests(unittest.TestCase):
    def test_rental_days_include_both_boundaries(self) -> None:
        self.assertEqual(1, rental_days(date(2026, 1, 1), date(2026, 1, 1)))
        self.assertEqual(3, rental_days(date(2026, 1, 1), date(2026, 1, 3)))

    def test_rental_days_reject_reversed_period(self) -> None:
        with self.assertRaises(ValidationError):
            rental_days(date(2026, 1, 2), date(2026, 1, 1))

    def test_periods_overlap_on_boundary(self) -> None:
        self.assertTrue(
            periods_overlap(
                date(2026, 1, 1),
                date(2026, 1, 3),
                date(2026, 1, 3),
                date(2026, 1, 5),
            )
        )

    def test_periods_do_not_overlap_when_adjacent(self) -> None:
        self.assertFalse(
            periods_overlap(
                date(2026, 1, 1),
                date(2026, 1, 3),
                date(2026, 1, 4),
                date(2026, 1, 5),
            )
        )

    def test_overdue_days_never_negative(self) -> None:
        self.assertEqual(0, overdue_days(date(2026, 1, 5), date(2026, 1, 3)))
        self.assertEqual(2, overdue_days(date(2026, 1, 5), date(2026, 1, 7)))


class DiscountCalculationTests(unittest.TestCase):
    def test_loyalty_levels(self) -> None:
        self.assertEqual(Decimal("0"), calculate_loyalty_discount(0))
        self.assertEqual(Decimal("0.05"), calculate_loyalty_discount(5))
        self.assertEqual(Decimal("0.10"), calculate_loyalty_discount(10))

    def test_negative_completed_rentals_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_loyalty_discount(-1)

    def test_duration_levels(self) -> None:
        self.assertEqual(Decimal("0"), calculate_duration_discount(6))
        self.assertEqual(Decimal("0.03"), calculate_duration_discount(7))
        self.assertEqual(Decimal("0.07"), calculate_duration_discount(14))

    def test_combine_discounts_applies_cap(self) -> None:
        self.assertEqual(
            Decimal("0.20"),
            combine_discounts([Decimal("0.15"), Decimal("0.10")]),
        )

    def test_invalid_discount_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            combine_discounts([Decimal("1.1")])


class QuoteCalculationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.item = ToolPricingInput(
            tool_id="tool-1",
            daily_rate=Decimal("650"),
            purchase_price=Decimal("24000"),
            deposit_rate=Decimal("0.25"),
            max_rental_days=21,
        )

    def test_quote_without_discount(self) -> None:
        quote = calculate_rental_quote(
            [self.item], date(2026, 1, 1), date(2026, 1, 3), 0
        )
        self.assertEqual(Decimal("1950.00"), quote.raw_charge)
        self.assertEqual(Decimal("1950.00"), quote.final_charge)
        self.assertEqual(Decimal("6000.00"), quote.required_deposit)

    def test_quote_with_combined_discount(self) -> None:
        quote = calculate_rental_quote(
            [self.item], date(2026, 1, 1), date(2026, 1, 14), 10
        )
        self.assertEqual(Decimal("0.17"), quote.discount_rate)
        self.assertEqual(Decimal("7553.00"), quote.final_charge)

    def test_quote_keeps_input_unchanged(self) -> None:
        original = self.item
        calculate_rental_quote(
            [self.item], date(2026, 1, 1), date(2026, 1, 2), 0
        )
        self.assertEqual(original, self.item)

    def test_empty_quote_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_rental_quote([], date(2026, 1, 1), date(2026, 1, 2), 0)

    def test_maximum_duration_is_checked(self) -> None:
        with self.assertRaises(ValidationError):
            calculate_rental_quote(
                [self.item], date(2026, 1, 1), date(2026, 1, 22), 0
            )

    def test_extended_charge_uses_existing_discount(self) -> None:
        charge = calculate_extended_charge(
            [Decimal("500"), Decimal("650")],
            date(2026, 1, 1),
            date(2026, 1, 4),
            Decimal("0.10"),
        )
        self.assertEqual(Decimal("4140.00"), charge)


class DamageCalculationTests(unittest.TestCase):
    def test_damage_boundaries(self) -> None:
        self.assertIsNone(classify_damage(0))
        self.assertEqual(DamageSeverity.COSMETIC, classify_damage(1))
        self.assertEqual(DamageSeverity.MINOR, classify_damage(10))
        self.assertEqual(DamageSeverity.MAJOR, classify_damage(25))
        self.assertEqual(DamageSeverity.IRREPARABLE, classify_damage(50))

    def test_damage_charge_rates(self) -> None:
        price = Decimal("10000")
        self.assertEqual(Decimal("0.00"), calculate_damage_charge(price, None))
        self.assertEqual(
            Decimal("300.00"),
            calculate_damage_charge(price, DamageSeverity.COSMETIC),
        )
        self.assertEqual(
            Decimal("1500.00"),
            calculate_damage_charge(price, DamageSeverity.MINOR),
        )
        self.assertEqual(
            Decimal("4000.00"),
            calculate_damage_charge(price, DamageSeverity.MAJOR),
        )
        self.assertEqual(
            Decimal("10000.00"),
            calculate_damage_charge(price, DamageSeverity.IRREPARABLE),
        )

    def test_return_line_combines_late_and_damage_charges(self) -> None:
        result = calculate_return_line(
            ReturnLineInput(
                tool_id="tool-1",
                daily_rate=Decimal("650"),
                late_fee_multiplier=Decimal("1.5"),
                purchase_price=Decimal("24000"),
                issued_condition=100,
                returned_condition=80,
            ),
            2,
        )
        self.assertEqual(DamageSeverity.MINOR, result.severity)
        self.assertEqual(Decimal("1950.00"), result.late_charge)
        self.assertEqual(Decimal("3600.00"), result.damage_charge)

    def test_return_line_is_immutable(self) -> None:
        input_data = ReturnLineInput(
            "tool-1", Decimal("100"), Decimal("1.5"), Decimal("1000"), 100, 99
        )
        result = calculate_return_line(input_data, 0)
        with self.assertRaises(Exception):
            result.damage_charge = Decimal("0")

    def test_return_summary(self) -> None:
        line = calculate_return_line(
            ReturnLineInput(
                "tool-1", Decimal("100"), Decimal("1.5"), Decimal("1000"), 100, 90
            ),
            2,
        )
        summary = summarize_return(Decimal("300"), Decimal("1000"), [line])
        self.assertEqual(Decimal("300.00"), summary.late_charge)
        self.assertEqual(Decimal("150.00"), summary.damage_charge)
        self.assertEqual(Decimal("750.00"), summary.final_charge)
        self.assertEqual(Decimal("250.00"), summary.deposit_refund)


class OtherCalculationTests(unittest.TestCase):
    def test_money_rounds_half_up(self) -> None:
        self.assertEqual(Decimal("10.01"), money(Decimal("10.005")))

    def test_maintenance_by_date(self) -> None:
        self.assertTrue(
            requires_maintenance(date(2026, 1, 1), date(2026, 4, 1), 90, 100)
        )

    def test_maintenance_by_condition(self) -> None:
        self.assertTrue(
            requires_maintenance(date(2026, 3, 1), date(2026, 3, 2), 90, 69)
        )

    def test_recent_healthy_tool_needs_no_maintenance(self) -> None:
        self.assertFalse(
            requires_maintenance(date(2026, 3, 1), date(2026, 3, 2), 90, 90)
        )

    def test_most_popular_key(self) -> None:
        self.assertEqual("saws", most_popular_key({"saws": 10, "drills": 5}))
        self.assertIsNone(most_popular_key({}))

    def test_most_popular_key_has_stable_tie_breaker(self) -> None:
        self.assertEqual("drills", most_popular_key({"saws": 10, "drills": 10}))


if __name__ == "__main__":
    unittest.main()

