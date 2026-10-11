from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence

from .exceptions import ValidationError
from .models import DamageSeverity, Money


CENT = Decimal("0.01")
ZERO = Decimal("0")
ONE = Decimal("1")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, ROUND_HALF_UP)


def rental_days(start_date: date, end_date: date) -> int:
    if end_date < start_date:
        raise ValidationError("Дата окончания не может быть раньше даты начала")
    return (end_date - start_date).days + 1


def periods_overlap(
    first_start: date,
    first_end: date,
    second_start: date,
    second_end: date,
) -> bool:
    if first_end < first_start or second_end < second_start:
        raise ValidationError("Границы периода указаны неверно")
    return first_start <= second_end and first_end >= second_start


def calculate_loyalty_discount(completed_rentals: int) -> Decimal:
    if completed_rentals < 0:
        raise ValidationError("Количество аренд не может быть отрицательным")
    if completed_rentals >= 10:
        return Decimal("0.10")
    if completed_rentals >= 5:
        return Decimal("0.05")
    return ZERO


def calculate_duration_discount(days: int) -> Decimal:
    if days <= 0:
        raise ValidationError("Срок аренды должен быть положительным")
    if days >= 14:
        return Decimal("0.07")
    if days >= 7:
        return Decimal("0.03")
    return ZERO


def combine_discounts(
    discounts: Iterable[Decimal],
    maximum: Decimal = Decimal("0.20"),
) -> Decimal:
    if maximum < ZERO or maximum > ONE:
        raise ValidationError("Ограничение скидки должно быть от 0 до 1")
    total = ZERO
    for discount in discounts:
        if discount < ZERO or discount > ONE:
            raise ValidationError("Скидка должна быть от 0 до 1")
        total += discount
    return min(total, maximum)


@dataclass(frozen=True)
class ToolPricingInput:
    tool_id: str
    daily_rate: Money
    purchase_price: Money
    deposit_rate: Decimal
    max_rental_days: int


@dataclass(frozen=True)
class QuoteLine:
    tool_id: str
    days: int
    daily_rate: Money
    raw_charge: Money
    deposit: Money


@dataclass(frozen=True)
class RentalQuote:
    lines: tuple[QuoteLine, ...]
    discount_rate: Decimal
    raw_charge: Money
    final_charge: Money
    required_deposit: Money


def make_quote_line(item: ToolPricingInput, days: int) -> QuoteLine:
    if not item.tool_id:
        raise ValidationError("Инструмент должен иметь идентификатор")
    if item.daily_rate <= ZERO or item.purchase_price <= ZERO:
        raise ValidationError("Стоимость инструмента и тариф должны быть положительными")
    if not ZERO <= item.deposit_rate <= ONE:
        raise ValidationError("Доля залога должна быть от 0 до 1")
    if days > item.max_rental_days:
        raise ValidationError(
            f"Для инструмента {item.tool_id} разрешено не более "
            f"{item.max_rental_days} дней"
        )
    return QuoteLine(
        tool_id=item.tool_id,
        days=days,
        daily_rate=item.daily_rate,
        raw_charge=money(item.daily_rate * days),
        deposit=money(item.purchase_price * item.deposit_rate),
    )


def calculate_rental_quote(
    items: Sequence[ToolPricingInput],
    start_date: date,
    end_date: date,
    completed_rentals: int,
) -> RentalQuote:
    if not items:
        raise ValidationError("Нельзя рассчитать пустую аренду")
    days = rental_days(start_date, end_date)
    lines = tuple(make_quote_line(item, days) for item in items)
    discount = combine_discounts(
        (
            calculate_loyalty_discount(completed_rentals),
            calculate_duration_discount(days),
        )
    )
    raw_charge = sum((line.raw_charge for line in lines), ZERO)
    deposit = sum((line.deposit for line in lines), ZERO)
    return RentalQuote(
        lines=lines,
        discount_rate=discount,
        raw_charge=money(raw_charge),
        final_charge=money(raw_charge * (ONE - discount)),
        required_deposit=money(deposit),
    )


def calculate_extended_charge(
    daily_rates: Iterable[Money],
    start_date: date,
    new_due_date: date,
    discount_rate: Decimal,
) -> Money:
    if not ZERO <= discount_rate <= ONE:
        raise ValidationError("Скидка должна быть от 0 до 1")
    days = rental_days(start_date, new_due_date)
    raw_charge = sum((rate * days for rate in daily_rates), ZERO)
    return money(raw_charge * (ONE - discount_rate))


def overdue_days(due_date: date, return_date: date) -> int:
    return max(0, (return_date - due_date).days)


def classify_damage(condition_loss: int) -> DamageSeverity | None:
    if condition_loss <= 0:
        return None
    if condition_loss >= 50:
        return DamageSeverity.IRREPARABLE
    if condition_loss >= 25:
        return DamageSeverity.MAJOR
    if condition_loss >= 10:
        return DamageSeverity.MINOR
    return DamageSeverity.COSMETIC


def calculate_damage_charge(
    purchase_price: Money,
    severity: DamageSeverity | None,
) -> Money:
    if purchase_price <= ZERO:
        raise ValidationError("Стоимость инструмента должна быть положительной")
    rates = {
        None: ZERO,
        DamageSeverity.COSMETIC: Decimal("0.03"),
        DamageSeverity.MINOR: Decimal("0.15"),
        DamageSeverity.MAJOR: Decimal("0.40"),
        DamageSeverity.IRREPARABLE: ONE,
    }
    return money(purchase_price * rates[severity])


@dataclass(frozen=True)
class ReturnLineInput:
    tool_id: str
    daily_rate: Money
    late_fee_multiplier: Decimal
    purchase_price: Money
    issued_condition: int
    returned_condition: int


@dataclass(frozen=True)
class ReturnLineResult:
    tool_id: str
    condition_loss: int
    severity: DamageSeverity | None
    late_charge: Money
    damage_charge: Money


def calculate_return_line(item: ReturnLineInput, days_overdue: int) -> ReturnLineResult:
    if days_overdue < 0:
        raise ValidationError("Просрочка не может быть отрицательной")
    if not 0 <= item.issued_condition <= 100:
        raise ValidationError("Исходное состояние должно быть от 0 до 100")
    if not 0 <= item.returned_condition <= 100:
        raise ValidationError("Состояние при возврате должно быть от 0 до 100")
    if item.late_fee_multiplier < ONE:
        raise ValidationError("Множитель просрочки не может быть меньше 1")
    loss = item.issued_condition - item.returned_condition
    severity = classify_damage(loss)
    return ReturnLineResult(
        tool_id=item.tool_id,
        condition_loss=max(0, loss),
        severity=severity,
        late_charge=money(
            item.daily_rate * days_overdue * item.late_fee_multiplier
        ),
        damage_charge=calculate_damage_charge(item.purchase_price, severity),
    )


@dataclass(frozen=True)
class ReturnSummary:
    base_charge: Money
    late_charge: Money
    damage_charge: Money
    final_charge: Money
    deposit_refund: Money


def summarize_return(
    base_charge: Money,
    deposit_paid: Money,
    lines: Sequence[ReturnLineResult],
) -> ReturnSummary:
    if base_charge < ZERO or deposit_paid < ZERO:
        raise ValidationError("Денежные значения не могут быть отрицательными")
    late_charge = sum((line.late_charge for line in lines), ZERO)
    damage_charge = sum((line.damage_charge for line in lines), ZERO)
    final_charge = money(base_charge + late_charge + damage_charge)
    return ReturnSummary(
        base_charge=money(base_charge),
        late_charge=money(late_charge),
        damage_charge=money(damage_charge),
        final_charge=final_charge,
        deposit_refund=money(max(ZERO, deposit_paid - final_charge)),
    )


def requires_maintenance(
    reference_date: date,
    current_date: date,
    interval_days: int,
    condition_score: int,
    condition_threshold: int = 70,
) -> bool:
    if current_date < reference_date:
        raise ValidationError("Текущая дата не может быть раньше контрольной")
    if interval_days <= 0:
        raise ValidationError("Интервал обслуживания должен быть положительным")
    if not 0 <= condition_score <= 100:
        raise ValidationError("Состояние должно быть от 0 до 100")
    elapsed = (current_date - reference_date).days
    return elapsed >= interval_days or condition_score < condition_threshold


def most_popular_key(weights: Mapping[str, int]) -> str | None:
    if not weights:
        return None
    if any(value < 0 for value in weights.values()):
        raise ValidationError("Вес не может быть отрицательным")
    return min(weights, key=lambda key: (-weights[key], key))
