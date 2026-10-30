"""Step 2: customers and their orders.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    """Create customers, orders and order_items."""
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("email", sa.Text, nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        comment="People who buy at the shop.",
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("customer_id", sa.BigInteger, sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default="draft"),
        sa.Column("placed_at", sa.DateTime(timezone=True)),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.CheckConstraint("status IN ('draft', 'placed', 'paid', 'shipped', 'cancelled')", name="orders_status_check"),
        comment="An order of a customer.",
    )
    op.create_table(
        "order_items",
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("line", sa.SmallInteger, primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("quantity > 0", name="order_items_quantity_check"),
        comment="The lines of an order.",
    )


def downgrade() -> None:
    """Drop the sales tables."""
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("customers")
