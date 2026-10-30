#!/usr/bin/env bash
# doctracker_reader reads everything and can change nothing, in both databases.
set -euo pipefail
for db in acme acme_warehouse; do
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<'SQL'
GRANT pg_read_all_data TO doctracker_reader;
ALTER ROLE doctracker_reader SET default_transaction_read_only = on;
SQL
done
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname acme <<'SQL'
GRANT USAGE ON SCHEMA sales, catalog TO acme_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA sales, catalog TO acme_app;
SQL
