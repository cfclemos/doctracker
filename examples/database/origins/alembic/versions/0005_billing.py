"""Step 4: payments of the orders.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    """Create payments."""
    op.create_table(
        "payments",
        sa.Column("id", sa.BigInteger, sa.Identity(always=True), primary_key=True),
        sa.Column("order_id", sa.BigInteger, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.CheckConstraint("amount > 0", name="payments_amount_check"),
        sa.CheckConstraint("method IN ('pix', 'card', 'boleto')", name="payments_method_check"),
        comment="Money received for an order.",
    )


def downgrade() -> None:
    """Drop payments."""
    op.drop_table("payments")
