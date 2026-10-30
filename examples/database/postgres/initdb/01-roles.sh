#!/usr/bin/env bash
# The read-only user doctracker connects with, and the second database of the server.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname acme -v reader_password="$READER_PASSWORD" <<'SQL'
CREATE ROLE doctracker_reader LOGIN PASSWORD :'reader_password';
COMMENT ON ROLE doctracker_reader IS 'Read-only user doctracker documents the databases with.';
CREATE ROLE acme_app NOLOGIN;
COMMENT ON ROLE acme_app IS 'Role of the shop application: reads and writes the sales and catalog schemas.';
CREATE DATABASE acme_warehouse;
COMMENT ON DATABASE acme_warehouse IS 'The warehouse system: shipments, read from acme through postgres_fdw.';
SQL
