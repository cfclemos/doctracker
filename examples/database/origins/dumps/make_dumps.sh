#!/usr/bin/env bash
# Write the schema dumps of the test databases (structure only, no data) next to this script, and one
# pg_dumpall of the PostgreSQL server (several databases in one file).
# Run from examples/database with the containers up. SQL Server has no dump tool in its image: its
# schema is mssql/acme.sql. pg_dump writes the user mappings with their passwords: they are replaced
# by a placeholder before the file is written.
set -euo pipefail
hide() { sed -E "s/(password[[:space:]]+)'[^']*'/\1'change-me'/g"; }
here="$(cd "$(dirname "$0")" && pwd)"
set -a; . ./.env; set +a
docker compose exec -T postgres pg_dump --schema-only --no-owner -U "$POSTGRES_ADMIN_USER" acme | hide > "$here/postgres-acme.sql"
docker compose exec -T postgres pg_dump --schema-only --no-owner -U "$POSTGRES_ADMIN_USER" acme_warehouse | hide > "$here/postgres-acme_warehouse.sql"
docker compose exec -T mysql sh -c 'exec mysqldump --no-data --routines --triggers --events -uroot -p"$MYSQL_ROOT_PASSWORD" acme' 2>/dev/null > "$here/mysql-acme.sql"
# iterdump() writes a virtual table (FTS5) as an INSERT INTO sqlite_schema: kept; only the rows are dropped.
python3 -c "import sqlite3, sys; db = sqlite3.connect('sqlite/acme.sqlite'); sys.stdout.write(''.join(l + '\n' for l in db.iterdump() if not l.startswith('INSERT INTO \"')))" > "$here/sqlite-acme.sql"
# The whole test server at once (every database but acme_large, the large one), its roles without passwords.
docker compose exec -T postgres pg_dumpall --schema-only --no-owner --no-role-passwords --exclude-database=acme_large -U "$POSTGRES_ADMIN_USER" | hide > "$here/postgres-cluster.sql"
echo "Dumps written in $here"
