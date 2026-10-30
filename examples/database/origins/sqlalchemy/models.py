"""The acme core schema as SQLAlchemy models: the state after the five migration steps."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CHAR, BigInteger, CheckConstraint, ForeignKey, Identity, Index, Numeric, SmallInteger, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """The models of the shop."""


class Category(Base):
    """Categories of products, as a tree."""

    __tablename__ = "categories"
    __table_args__ = {"comment": "Categories of products, as a tree."}

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text)
    slug: Mapped[str] = mapped_column(Text, unique=True)

    parent: Mapped["Category | None"] = relationship(remote_side=[id])


class Product(Base):
    """What the shop sells."""

    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price >= 0", name="products_price_check"), {"comment": "What the shop sells."})

    id: Mapped[int] = mapped_column(Identity(always=True), primary_key=True)
    sku: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    active: Mapped[bool] = mapped_column(server_default="true")
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))

    category: Mapped[Category] = relationship()


class Customer(Base):
    """People who buy at the shop."""

    __tablename__ = "customers"
    __table_args__ = {"comment": "People who buy at the shop."}

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    full_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    cpf: Mapped[str | None] = mapped_column(CHAR(14), unique=True)
    phone: Mapped[str | None] = mapped_column(Text)


class Order(Base):
    """An order of a customer."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'placed', 'paid', 'shipped', 'cancelled')", name="orders_status_check"),
        Index("orders_customer", "customer_id"),
        {"comment": "An order of a customer."},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(Text, server_default="draft")
    placed_at: Mapped[datetime | None]
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), server_default="0")

    customer: Mapped[Customer] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    """The lines of an order."""

    __tablename__ = "order_items"
    __table_args__ = (CheckConstraint("quantity > 0", name="order_items_quantity_check"), {"comment": "The lines of an order."})

    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)
    line: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()


class Payment(Base):
    """Money received for an order."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="payments_amount_check"),
        CheckConstraint("method IN ('pix', 'card', 'boleto')", name="payments_method_check"),
        {"comment": "Money received for an order."},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    paid_at: Mapped[datetime]
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    method: Mapped[str] = mapped_column(Text)

    order: Mapped[Order] = relationship()
