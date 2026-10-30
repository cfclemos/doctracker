"""Tests of `doctracker.databases`: discovery, the read-only check of statements, and the connection store.

They need no database server: SQLite files are made in a temporary folder, and the store runs
without the system's vault (master password).
"""

import sqlite3
from pathlib import Path

import pytest

from doctracker.databases import ConnectionStore, Locked, is_read_only
from doctracker.databases import test_connection as check_connection  # not collected as a test
from doctracker.databases.discovery import HIDDEN, discover, resolve


def write(root: Path, file: str, text: str) -> None:
    """Write a project file, creating its folders."""
    path = root / file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def found(root: Path) -> dict[str, dict]:
    """The connections discovered in a project, by name."""
    return {c.name: c.public() for c in discover(root)}


def test_env_url_and_groups(tmp_path):
    write(tmp_path, ".env", "DATABASE_URL=postgresql://app:s3cret@db:5433/shop\nMYSQL_ROOT_PASSWORD=x\nMYSQL_PORT=3307\n")
    connections = found(tmp_path)
    assert {"kind": "postgresql", "host": "db", "port": "5433", "database": "shop", "user": "app",
            "password": "${DATABASE_URL}"}.items() <= connections["DATABASE_URL"].items()
    assert connections["MYSQL"]["user"] == "root" and connections["MYSQL"]["password"] == "${MYSQL_ROOT_PASSWORD}"


def test_password_written_in_a_file_is_hidden(tmp_path):
    write(tmp_path, "alembic.ini", "[alembic]\nsqlalchemy.url = postgresql://u:plain@localhost/app\n")
    connection = found(tmp_path)["app"]
    assert connection["password"] == HIDDEN
    assert "plain" not in str(connection)


def test_templates_and_placeholders_are_left_out(tmp_path):
    write(tmp_path, ".env.example", "DATABASE_URL=postgresql://u:p@h/db\n")
    write(tmp_path, "alembic.ini", "sqlalchemy.url = driver://user:pass@localhost/dbname\n")
    write(tmp_path, "app.py", 'engine = create_engine("sqlite://")\n')
    assert found(tmp_path) == {}


def test_django_settings_read_without_importing(tmp_path):
    write(tmp_path, "site/settings.py", "import os\nraise SystemExit\nDATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', "
                                        "'NAME': 'shop', 'USER': 'web', 'PASSWORD': os.environ['DB_PASSWORD'], 'HOST': 'pg'}}\n")
    connection = found(tmp_path)["Django default"]
    assert (connection["kind"], connection["host"], connection["password"]) == ("postgresql", "pg", "${DB_PASSWORD}")


def test_compose_services_with_a_published_port(tmp_path):
    write(tmp_path, "compose.yaml", """services:
  db:
    image: postgres:17
    environment:
      POSTGRES_USER: shop
      POSTGRES_PASSWORD: ${PGPASS}
    ports:
      - "127.0.0.1:${PG_PORT:-55432}:5432"
  tools:
    image: mcr.microsoft.com/mssql-tools
""")
    connections = found(tmp_path)
    assert list(connections) == ["db (Compose)"]
    assert {"host": "127.0.0.1", "port": "${PG_PORT:-55432}", "user": "shop", "database": "shop",
            "password": "${PGPASS}"}.items() <= connections["db (Compose)"].items()
    assert resolve("${PG_PORT:-55432}", {}) == "55432" and resolve("${PG_PORT:-55432}", {"PG_PORT": "1"}) == "1"


def test_prisma_and_sqlite_files(tmp_path):
    write(tmp_path, "prisma/schema.prisma", 'datasource db {\n  provider = "mysql"\n  url = env("SHOP_URL")\n}\n')
    sqlite3.connect(tmp_path / "data.sqlite").execute("CREATE TABLE t (x INT)").connection.commit()
    connections = found(tmp_path)
    assert connections["Prisma (SHOP_URL)"]["url_variable"] == "SHOP_URL"
    assert connections["data.sqlite"]["kind"] == "sqlite"


@pytest.mark.parametrize("sql, kind, reads", [
    ("SELECT 1", "postgresql", True),
    ("SHOW transaction_read_only", "postgresql", True),
    ("PRAGMA query_only", "sqlite", True),
    ("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x", "postgresql", False),
    ("SELECT * INTO copy FROM t", "mssql", False),
    ("SELECT 1; DELETE FROM t", "mysql", False),
    ("PRAGMA query_only = 0", "sqlite", False),
    ("CALL p()", "mysql", False),
    ("not sql at all (", "postgresql", False),
])
def test_only_reads_pass(sql, kind, reads):
    assert is_read_only(sql, kind) is reads


def test_sqlite_test_is_read_only(tmp_path):
    database = tmp_path / "shop.sqlite"
    sqlite3.connect(database).execute("CREATE TABLE t (x INT)").connection.commit()
    result = check_connection({"kind": "sqlite", "host": str(database)})
    assert result["ok"] and result["write_refused"] and result["read_only_session"]
    assert sqlite3.connect(database).execute("SELECT name FROM sqlite_master").fetchall() == [("t",)]


def no_vault(root: Path) -> ConnectionStore:
    """A store that behaves as on a system without a vault."""
    store = ConnectionStore(root)
    store.has_vault = lambda: False
    return store


def test_store_keeps_passwords_encrypted_and_consent(tmp_path):
    write(tmp_path, ".env", "SHOP_PASSWORD=from-env\nDATABASE_URL=postgresql://u:p@h/db\n")
    store = no_vault(tmp_path)
    with pytest.raises(Locked):
        store.save({"name": "a", "kind": "postgresql", "host": "h", "user": "u"}, "typed")
    store.unlock("master")
    typed = store.save({"name": "a", "kind": "postgresql", "host": "h", "user": "u"}, "typed")
    by_reference = store.save({"name": "b", "kind": "mysql", "host": "h", "user": "u"}, "${SHOP_PASSWORD}")
    assert store.spec(typed["id"])["password"] == "typed"
    assert store.spec(by_reference["id"])["password"] == "from-env"
    stored = (tmp_path / "doc/connections/connections.json").read_text(encoding="utf-8")
    assert "typed" not in stored and (tmp_path / "doc/connections/.gitignore").read_text() == "*\n"

    declared = next(c for c in store.connections() if c["source"] == ".env")
    assert not declared["allowed"]
    with pytest.raises(ValueError):
        store.spec(declared["id"])
    store.allow(declared["id"])
    assert store.spec(declared["id"])["host"] == "h"

    again = no_vault(tmp_path)
    with pytest.raises(ValueError):
        again.unlock("wrong")
    again.unlock("master")
    again.remove(typed["id"])
    assert [c["name"] for c in again.connections() if c["source"] == "entered"] == ["b"]
