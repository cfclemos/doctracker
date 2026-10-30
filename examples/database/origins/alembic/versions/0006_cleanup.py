"""Step 5: a destructive change, a rename and an index (what a migration lint must flag).

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    """Drop the description, rename the customer's name, index the orders by customer."""
    op.drop_column("products", "description")
    op.alter_column("customers", "name", new_column_name="full_name")
    op.create_index("orders_customer", "orders", ["customer_id"])


def downgrade() -> None:
    """Undo the cleanup (the descriptions are lost)."""
    op.drop_index("orders_customer", "orders")
    op.alter_column("customers", "full_name", new_column_name="name")
    op.add_column("products", sa.Column("description", sa.Text))
