"""Step 3, one branch: more about customers.

Revision ID: 0003a
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003a"
down_revision = "0002"
branch_labels = ("customers",)


def upgrade() -> None:
    """Add the CPF and the phone."""
    op.add_column("customers", sa.Column("cpf", sa.CHAR(14), unique=True))
    op.add_column("customers", sa.Column("phone", sa.Text))


def downgrade() -> None:
    """Drop the CPF and the phone."""
    op.drop_column("customers", "phone")
    op.drop_column("customers", "cpf")
