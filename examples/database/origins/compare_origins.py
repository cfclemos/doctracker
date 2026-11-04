"""Load every origin of the acme core schema into a database of its own and compare what comes out.

Run from examples/database with the containers up and the project's environment (SQLAlchemy, pg8000,
Alembic, Django; Node for Prisma): `python origins/compare_origins.py`. Each origin gets a fresh
database `origin_<name>` on the test Postgres (Django: an SQLite file, its Postgres driver being LGPL),
loaded by the origin's own tool where it has one — Flyway and golang-migrate run from their official
images, so the databases hold their history tables as a real project's would;
the schemas are then compared by name with the Flyway one: tables, columns, keys, uniques, checks,
indexes. Nothing touches the acme databases.
"""

import os
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect

HERE = Path(__file__).parent
ENV = dotenv_values(HERE.parent / ".env")
ADMIN = f"postgresql+pg8000://{ENV['POSTGRES_ADMIN_USER']}:{urllib.parse.quote(ENV['POSTGRES_ADMIN_PASSWORD'], safe='')}@localhost:{ENV['POSTGRES_PORT']}"
"""The test server, as its administrator (the origins are loaded with DDL)."""

SKIPPED = {"alembic_version", "django_migrations", "_prisma_migrations", "flyway_schema_history", "schema_migrations"}
"""Bookkeeping tables of the tools, left out of the comparison."""


def psql(database: str, sql: str) -> None:
    """Run SQL in a database of the test server, stopping at the first error."""
    subprocess.run(["docker", "compose", "exec", "-T", "postgres", "psql", "-q", "-v", "ON_ERROR_STOP=1",
                    "-U", ENV["POSTGRES_ADMIN_USER"], "-d", database], input=sql, text=True, check=True,
                   cwd=HERE.parent, stdout=subprocess.DEVNULL)


NETWORK = "doctracker-testbed_testbed"
"""The test bed's Docker network: the migration tools' containers reach the server there as `postgres`."""

FLYWAY_IMAGE = "flyway/flyway:11.14.1"
"""Flyway Community (Apache-2.0), only to load the test bed."""

MIGRATE_IMAGE = "migrate/migrate:v4.19.0"
"""golang-migrate (MIT), only to load the test bed."""


def tool(image: str, folder: Path, *args: str) -> None:
    """Run a migration tool's container on the test bed's network, the origin's folder mounted read only."""
    subprocess.run(["docker", "run", "--rm", "--network", NETWORK, "-v", f"{folder}:/migrations:ro", image, *args],
                   check=True, stdout=subprocess.DEVNULL)


def fresh(name: str) -> str:
    """Create an empty database `origin_<name>` and give its SQLAlchemy URL."""
    psql("postgres", f"DROP DATABASE IF EXISTS origin_{name} WITH (FORCE); CREATE DATABASE origin_{name};")
    return f"{ADMIN}/origin_{name}"


def load_all() -> dict[str, str]:
    """Load each origin; give the URL of each database."""
    urls = {}
    user, password = ENV["POSTGRES_ADMIN_USER"], ENV["POSTGRES_ADMIN_PASSWORD"]
    urls["flyway"] = fresh("flyway")
    tool(FLYWAY_IMAGE, HERE / "flyway", "-url=jdbc:postgresql://postgres:5432/origin_flyway", f"-user={user}",
         f"-password={password}", "-locations=filesystem:/migrations", "migrate")
    urls["golang-migrate"] = fresh("golang_migrate")
    tool(MIGRATE_IMAGE, HERE / "golang-migrate", "-path=/migrations", "-database",
         f"postgres://{urllib.parse.quote(user, safe='')}:{urllib.parse.quote(password, safe='')}@postgres:5432/origin_golang_migrate?sslmode=disable", "up")
    urls["alembic"] = fresh("alembic")
    subprocess.run([sys.executable, "-m", "alembic", "-c", str(HERE / "alembic/alembic.ini"), "upgrade", "heads"],
                   env={**os.environ, "ACME_DATABASE_URL": urls["alembic"]}, check=True)
    urls["sqlalchemy"] = fresh("sqlalchemy")
    sys.path.insert(0, str(HERE / "sqlalchemy"))
    from models import Base  # noqa: PLC0415 - the example's models, found only now
    Base.metadata.create_all(create_engine(urls["sqlalchemy"]))
    urls["prisma"] = fresh("prisma")
    script = subprocess.run(["npx", "--yes", "prisma@6.19.0", "migrate", "diff", "--from-empty", "--to-schema-datamodel",
                             str(HERE / "prisma/schema.prisma"), "--script"], capture_output=True, text=True, check=True,
                            env={**os.environ, "ACME_DATABASE_URL": "postgresql://unused@localhost/unused"})
    psql("origin_prisma", script.stdout)
    sqlite = Path(tempfile.gettempdir()) / "origin_django.sqlite"
    sqlite.unlink(missing_ok=True)
    subprocess.run([sys.executable, "manage.py", "migrate", "-v", "0"], cwd=HERE / "django", check=True,
                   env={**os.environ, "ACME_DATABASE": str(sqlite)})
    urls["django (sqlite)"] = f"sqlite:///{sqlite}"
    return urls


def describe(url: str) -> dict[str, set[str]]:
    """What a database holds, by name only, so that different tools and engines compare."""
    insp = inspect(create_engine(url))
    found: dict[str, set[str]] = {k: set() for k in ("tables", "columns", "nullable", "primary keys", "foreign keys",
                                                      "uniques", "checks", "indexes")}
    for table in sorted(set(insp.get_table_names()) - SKIPPED):
        found["tables"].add(table)
        for column in insp.get_columns(table):
            found["columns"].add(f"{table}.{column['name']}")
            if column["nullable"]: found["nullable"].add(f"{table}.{column['name']}")
        found["primary keys"].add(f"{table}({','.join(sorted(insp.get_pk_constraint(table)['constrained_columns']))})")
        for fk in insp.get_foreign_keys(table):
            found["foreign keys"].add(f"{table}({','.join(fk['constrained_columns'])})->{fk['referred_table']}")
        for unique in insp.get_unique_constraints(table):
            found["uniques"].add(f"{table}({','.join(unique['column_names'])})")
        for index in insp.get_indexes(table):
            (found["uniques"] if index["unique"] else found["indexes"]).add(f"{table}({','.join(map(str, index['column_names']))})")
        found["checks"] |= {f"{table}:{len(insp.get_check_constraints(table))} checks"}
    return found


if __name__ == "__main__":
    urls = load_all()
    seen = {name: describe(url) for name, url in urls.items()}
    reference = seen["flyway"]
    names = list(seen)
    print("| | " + " | ".join(names) + " |\n|---|" + "---|" * len(names))
    for kind in reference:
        print(f"| {kind} | " + " | ".join(str(len(seen[n][kind])) for n in names) + " |")
    for name in names[1:]:
        for kind, items in reference.items():
            missing, extra = items - seen[name][kind], seen[name][kind] - items
            if missing or extra:
                print(f"- {name}, {kind}: missing {sorted(missing) or '-'}; more {sorted(extra) or '-'}")
