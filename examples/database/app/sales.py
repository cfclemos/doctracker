"""The shop's sales through the SQLAlchemy models: each use of a model reaches its table."""

from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from origins.sqlalchemy.models import Customer, Order, OrderItem


def customer_by_email(session: Session, email: str) -> Customer | None:
    """Find a customer by their email."""
    return session.scalars(select(Customer).where(Customer.email == email)).first()


def open_orders(session: Session, customer: Customer) -> list[Order]:
    """The orders of a customer not paid yet."""
    query = select(Order).where(Order.customer_id == customer.id, Order.status.in_(["draft", "placed"]))
    return list(session.scalars(query))


def order_total(order: Order) -> Decimal:
    """Add up the lines of an order."""
    return sum((item.quantity * item.unit_price for item in order.items), Decimal(0))


def mark_paid(session: Session, order_id: int) -> None:
    """Mark an order as paid."""
    session.execute(update(Order).where(Order.id == order_id).values(status="paid"))


def add_line(session: Session, order: Order, product_id: int, quantity: int, price: Decimal) -> OrderItem:
    """Add a line to an order."""
    item = OrderItem(order_id=order.id, line=len(order.items) + 1, product_id=product_id, quantity=quantity, unit_price=price)
    session.add(item)
    return item
