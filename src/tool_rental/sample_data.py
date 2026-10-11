from datetime import date, datetime
from decimal import Decimal

from .service import RentalService


def create_demo_service(now: datetime | None = None) -> RentalService:
    service = RentalService()
    service.set_clock(now or datetime(2026, 10, 11, 9, 0))

    service.register_category(
        "drills",
        "Дрели и перфораторы",
        "Электроинструмент для сверления и долбления",
        Decimal("650"),
        Decimal("0.25"),
        maintenance_interval_days=60,
        max_rental_days=21,
    )
    service.register_category(
        "saws",
        "Пилы",
        "Дисковые, сабельные и цепные пилы",
        Decimal("800"),
        Decimal("0.30"),
        maintenance_interval_days=45,
        max_rental_days=14,
    )
    service.register_category(
        "measurement",
        "Измерительная техника",
        "Лазерные уровни и дальномеры",
        Decimal("500"),
        Decimal("0.35"),
        maintenance_interval_days=120,
        max_rental_days=30,
    )
    service.register_category(
        "concrete",
        "Оборудование для бетона",
        "Бетономешалки и вибраторы",
        Decimal("1100"),
        Decimal("0.20"),
        late_fee_multiplier=Decimal("1.75"),
        maintenance_interval_days=30,
        max_rental_days=14,
    )

    service.register_tool(
        "tool-001",
        "INV-2026-001",
        "Перфоратор Bosch GBH 2-28",
        "drills",
        Decimal("24000"),
        date(2026, 1, 15),
    )
    service.register_tool(
        "tool-002",
        "INV-2026-002",
        "Дрель Makita HP1640",
        "drills",
        Decimal("9500"),
        date(2026, 3, 10),
    )
    service.register_tool(
        "tool-003",
        "INV-2026-003",
        "Пила дисковая DeWalt DWE560",
        "saws",
        Decimal("18000"),
        date(2026, 5, 3),
    )
    service.register_tool(
        "tool-004",
        "INV-2026-004",
        "Пила сабельная Makita JR3051TK",
        "saws",
        Decimal("17000"),
        date(2026, 8, 20),
    )
    service.register_tool(
        "tool-005",
        "INV-2026-005",
        "Лазерный уровень ADA Cube",
        "measurement",
        Decimal("14500"),
        date(2026, 6, 11),
    )
    service.register_tool(
        "tool-006",
        "INV-2026-006",
        "Лазерный дальномер Bosch GLM 40",
        "measurement",
        Decimal("11000"),
        date(2026, 7, 25),
    )
    service.register_tool(
        "tool-007",
        "INV-2026-007",
        "Бетономешалка Вихрь БМ-180",
        "concrete",
        Decimal("32000"),
        date(2026, 9, 1),
    )

    service.register_customer(
        "customer-001",
        "Алексей Петров",
        "+7-900-100-20-30",
        "petrov@example.ru",
    )
    service.register_customer(
        "customer-002",
        "Марина Волкова",
        "+7-900-200-30-40",
        "volkova@example.ru",
    )
    service.register_customer(
        "customer-003",
        "ООО Ремонт-Профи",
        "+7-900-300-40-50",
        "office@remont-profi.ru",
    )
    return service


def create_completed_demo_rental(service: RentalService) -> str:
    service.set_clock(datetime(2026, 10, 1, 9, 0))
    reservation = service.create_reservation(
        "customer-001",
        ["tool-002", "tool-005"],
        date(2026, 10, 1),
        date(2026, 10, 3),
        "Ремонт квартиры",
    )
    service.confirm_reservation(reservation.id)
    rental = service.issue_reservation(reservation.id, reservation.required_deposit)
    service.set_clock(datetime(2026, 10, 4, 15, 0))
    service.return_rental(rental.id, {"tool-002": 98, "tool-005": 100})
    return rental.id
