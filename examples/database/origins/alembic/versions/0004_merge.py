"""Join the two branches of step 3.

Revision ID: 0004
Revises: 0003a, 0003b
"""

revision = "0004"
down_revision = ("0003a", "0003b")


def upgrade() -> None:
    """Nothing to change: only the history joins."""


def downgrade() -> None:
    """Nothing to change: only the history splits."""
