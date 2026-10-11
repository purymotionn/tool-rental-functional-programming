from __future__ import annotations

from dataclasses import replace
from datetime import date
from typing import TypeVar

from .models import (
    Customer,
    CustomerStatus,
    Rental,
    Reservation,
    ReservationStatus,
    Tool,
    ToolStatus,
)


T = TypeVar("T")


def add_element_last(items: list[T], element: T) -> list[T]:
    return [*items, element]


def add_text_line(text: str, line: str) -> str:
    values = [value for value in (text.strip(), line.strip()) if value]
    return "\n".join(values)


def change_customer_status(
    customer: Customer,
    status: CustomerStatus,
    note: str = "",
) -> Customer:
    notes = customer.notes if not note else add_element_last(customer.notes, note)
    return replace(customer, status=status, notes=notes)


def change_tool_status(tool: Tool, status: ToolStatus) -> Tool:
    return replace(tool, status=status, notes=list(tool.notes))


def add_tool_note(tool: Tool, note: str) -> Tool:
    return replace(tool, notes=add_element_last(tool.notes, note))


def change_reservation_status(
    reservation: Reservation,
    status: ReservationStatus,
    comment_line: str = "",
) -> Reservation:
    comment = (
        add_text_line(reservation.comment, comment_line)
        if comment_line
        else reservation.comment
    )
    return replace(
        reservation,
        status=status,
        tool_ids=list(reservation.tool_ids),
        comment=comment,
    )


def extend_rental_copy(
    rental: Rental,
    new_due_date: date,
    new_base_charge,
) -> Rental:
    return replace(
        rental,
        due_date=new_due_date,
        base_charge=new_base_charge,
        lines=[replace(line) for line in rental.lines],
    )
