"""Step 3, the other branch: the cost of each product.

Revision ID: 0003b
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003b"
down_revision = "0002"
branch_labels = ("catalog",)


def upgrade() -> None:
    """Add the cost."""
    op.add_column("products", sa.Column("cost", sa.Numeric(12, 2)))


def downgrade() -> None:
    """Drop the cost."""
    op.drop_column("products", "cost")
