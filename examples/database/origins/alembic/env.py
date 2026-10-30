"""Run the acme migrations against the database named by ACME_DATABASE_URL."""

import os

from alembic import context
from sqlalchemy import create_engine

engine = create_engine(os.environ["ACME_DATABASE_URL"])
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
