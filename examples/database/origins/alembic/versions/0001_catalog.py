"""Step 1: what the shop sells.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    """Create categories and products."""
    op.create_table(
        "categories",
        sa.Column("id", sa.Integer, sa.Identity(always=True), primary_key=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("categories.id", ondelete="CASCADE")),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False, unique=True),
        comment="Categories of products, as a tree.",
    )
    op.create_table(
        "products",
        sa.Column("id", sa.Integer, sa.Identity(always=True), primary_key=True),
        sa.Column("sku", sa.Text, nullable=False, unique=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id"), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.CheckConstraint("price >= 0", name="products_price_check"),
        comment="What the shop sells.",
    )


def downgrade() -> None:
    """Drop products and categories."""
    op.drop_table("products")
    op.drop_table("categories")
