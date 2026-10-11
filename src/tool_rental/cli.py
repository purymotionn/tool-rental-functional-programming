from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Callable

from .exceptions import RentalError
from .models import RentalStatus, ReservationStatus, ToolStatus
from .sample_data import create_demo_service
from .service import RentalService


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))} руб."


def _read_date(prompt: str) -> date:
    while True:
        raw = input(prompt).strip()
        try:
            return date.fromisoformat(raw)
        except ValueError:
            print("Введите дату в формате ГГГГ-ММ-ДД.")


def _read_decimal(prompt: str) -> Decimal:
    while True:
        raw = input(prompt).strip().replace(",", ".")
        try:
            return Decimal(raw)
        except InvalidOperation:
            print("Введите корректное число.")


def _pause() -> None:
    input("\nНажмите Enter, чтобы продолжить...")


class ConsoleApplication:
    def __init__(self, service: RentalService) -> None:
        self.service = service
        self.running = True
        self.commands: dict[str, tuple[str, Callable[[], None]]] = {
            "1": ("Показать инструменты", self.show_tools),
            "2": ("Найти свободные инструменты", self.find_tools),
            "3": ("Показать клиентов", self.show_customers),
            "4": ("Создать бронирование", self.create_reservation),
            "5": ("Показать бронирования", self.show_reservations),
            "6": ("Подтвердить бронирование", self.confirm_reservation),
            "7": ("Выдать инструменты", self.issue_tools),
            "8": ("Показать аренды", self.show_rentals),
            "9": ("Вернуть инструменты", self.return_tools),
            "10": ("Показать статистику", self.show_statistics),
            "11": ("Сменить текущую дату", self.change_date),
            "0": ("Выход", self.stop),
        }

    def run(self) -> None:
        print("Система аренды строительных инструментов")
        while self.running:
            print(f"\nТекущая дата: {self.service.current_date:%d.%m.%Y}")
            for key, (title, _) in self.commands.items():
                print(f" {key:>2}. {title}")
            command = input("Выберите действие: ").strip()
            entry = self.commands.get(command)
            if entry is None:
                print("Неизвестная команда.")
                continue
            try:
                entry[1]()
            except RentalError as error:
                print(f"Ошибка: {error}")
                _pause()

    def stop(self) -> None:
        self.running = False
        print("Работа завершена.")

    def show_tools(self) -> None:
        print("\nИНСТРУМЕНТЫ")
        print("-" * 82)
        print(f"{'ID':<12} {'Наименование':<34} {'Состояние':<14} {'Износ':>7}")
        print("-" * 82)
        for tool in sorted(self.service.repository.tools.values(), key=lambda item: item.id):
            print(
                f"{tool.id:<12} {tool.name[:33]:<34} "
                f"{tool.status.value:<14} {tool.condition_score:>6}%"
            )
        _pause()

    def find_tools(self) -> None:
        start = _read_date("Дата начала: ")
        end = _read_date("Дата окончания: ")
        category = input("ID категории (пусто — любая): ").strip() or None
        tools = self.service.find_available_tools(start, end, category)
        if not tools:
            print("Подходящих инструментов нет.")
        else:
            for tool in tools:
                rate = self.service.repository.get_category(tool.category_id).daily_rate
                print(f"{tool.id}: {tool.name} — {_money(rate)} в сутки")
        _pause()

    def show_customers(self) -> None:
        print("\nКЛИЕНТЫ")
        for customer in self.service.repository.customers.values():
            print(
                f"{customer.id}: {customer.full_name}; {customer.status.value}; "
                f"аренд: {customer.completed_rentals}; потрачено: {_money(customer.total_spent)}"
            )
        _pause()

    def create_reservation(self) -> None:
        customer_id = input("ID клиента: ").strip()
        tool_ids = [item.strip() for item in input("ID инструментов через запятую: ").split(",")]
        start = _read_date("Дата начала: ")
        end = _read_date("Дата окончания: ")
        comment = input("Комментарий: ").strip()
        reservation = self.service.create_reservation(
            customer_id, tool_ids, start, end, comment
        )
        print(f"Создана бронь {reservation.id}.")
        print(f"Стоимость: {_money(reservation.estimated_price)}")
        print(f"Залог: {_money(reservation.required_deposit)}")
        _pause()

    def show_reservations(self) -> None:
        print("\nБРОНИРОВАНИЯ")
        reservations = self.service.repository.reservations.values()
        for reservation in reservations:
            tools = ", ".join(reservation.tool_ids)
            print(
                f"{reservation.id}: {reservation.status.value}; клиент "
                f"{reservation.customer_id}; {reservation.start_date}—{reservation.end_date}; "
                f"[{tools}]; {_money(reservation.estimated_price)}"
            )
        _pause()

    def confirm_reservation(self) -> None:
        reservation_id = input("ID бронирования: ").strip()
        reservation = self.service.confirm_reservation(reservation_id)
        print(f"Бронирование {reservation.id} подтверждено.")
        _pause()

    def issue_tools(self) -> None:
        reservation_id = input("ID подтверждённого бронирования: ").strip()
        reservation = self.service.repository.get_reservation(reservation_id)
        print(f"Требуемый залог: {_money(reservation.required_deposit)}")
        paid = _read_decimal("Внесено: ")
        rental = self.service.issue_reservation(reservation_id, paid)
        print(f"Оформлена аренда {rental.id}, возврат до {rental.due_date}.")
        _pause()

    def show_rentals(self) -> None:
        print("\nАРЕНДЫ")
        for rental in self.service.repository.rentals.values():
            tools = ", ".join(line.tool_id for line in rental.lines)
            print(
                f"{rental.id}: {rental.status.value}; клиент {rental.customer_id}; "
                f"до {rental.due_date}; [{tools}]; начислено {_money(rental.final_charge)}"
            )
        _pause()

    def return_tools(self) -> None:
        rental_id = input("ID аренды: ").strip()
        rental = self.service.repository.get_rental(rental_id)
        conditions: dict[str, int] = {}
        for line in rental.lines:
            conditions[line.tool_id] = int(
                input(f"Состояние {line.tool_id} при возврате (0–100): ")
            )
        result = self.service.return_rental(rental_id, conditions)
        print(f"Аренда {result.id} завершена.")
        print(f"Базовая стоимость: {_money(result.base_charge)}")
        print(f"Просрочка: {_money(result.late_charge)}")
        print(f"Повреждения: {_money(result.damage_charge)}")
        print(f"Итого: {_money(result.final_charge)}")
        print(f"Возврат залога: {_money(result.deposit_refund)}")
        _pause()

    def show_statistics(self) -> None:
        statistics = self.service.rental_statistics()
        print("\nСТАТИСТИКА")
        print(f"Инструментов: {statistics['tools_total']}")
        print(f"Клиентов: {statistics['registered_customers']}")
        print(f"Активных аренд: {statistics['active_rentals']}")
        print(f"Завершённых аренд: {statistics['completed_rentals']}")
        print(f"С просрочкой: {statistics['overdue_count']}")
        print(f"Выручка: {_money(statistics['revenue'])}")
        print(f"Популярная категория: {statistics['popular_category_id'] or 'нет данных'}")
        _pause()

    def change_date(self) -> None:
        new_date = _read_date("Новая дата: ")
        self.service.set_clock(datetime.combine(new_date, datetime.min.time()))
        expired = self.service.expire_reservations()
        overdue = self.service.mark_overdue_rentals()
        print(f"Просрочено броней: {len(expired)}, аренд: {len(overdue)}")
        _pause()


def main() -> None:
    ConsoleApplication(create_demo_service()).run()


if __name__ == "__main__":
    main()
