#!/usr/bin/env bash
# The second database (acme_warehouse) and its link from acme through postgres_fdw.
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname acme_warehouse <<'SQL'
CREATE SCHEMA logistics;
COMMENT ON SCHEMA logistics IS 'Shipments leaving the warehouse.';
CREATE TABLE logistics.carriers (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE
);
COMMENT ON TABLE logistics.carriers IS 'Companies that carry the parcels.';
CREATE TABLE logistics.shipments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL,
    carrier_id smallint NOT NULL REFERENCES logistics.carriers (id),
    tracking_code text UNIQUE,
    shipped_at timestamptz NOT NULL
);
COMMENT ON TABLE logistics.shipments IS 'A parcel sent for an order of the shop (order_id refers to acme.sales.orders, another database).';
INSERT INTO logistics.carriers (name) VALUES ('Correios'), ('Jadlog'), ('Loggi');
INSERT INTO logistics.shipments (order_id, carrier_id, tracking_code, shipped_at)
SELECT n * 4 - 1, 1 + n % 3, 'BR' || lpad(n::text, 9, '0') || 'BR', timestamptz '2025-02-01' + n * interval '2 days'
FROM generate_series(1, 150) AS n;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname acme \
     -v admin_user="$POSTGRES_USER" -v admin_password="$POSTGRES_PASSWORD" -v reader_password="$READER_PASSWORD" <<'SQL'
CREATE SERVER warehouse FOREIGN DATA WRAPPER postgres_fdw OPTIONS (host '/var/run/postgresql', dbname 'acme_warehouse');  -- the socket: the only door open while the image initialises
COMMENT ON SERVER warehouse IS 'The warehouse database, on the same server.';
CREATE USER MAPPING FOR CURRENT_USER SERVER warehouse OPTIONS (user :'admin_user', password :'admin_password');
-- The reader sees the warehouse as itself (read only there too).
CREATE USER MAPPING FOR doctracker_reader SERVER warehouse OPTIONS (user 'doctracker_reader', password :'reader_password');
CREATE SCHEMA warehouse;
COMMENT ON SCHEMA warehouse IS 'Tables of acme_warehouse seen from the shop (foreign tables).';
IMPORT FOREIGN SCHEMA logistics FROM SERVER warehouse INTO warehouse;
-- Afterwards over the container's own address, where passwords are checked (the image trusts the socket
-- and 127.0.0.1): postgres_fdw lets a non-superuser such as the reader in only so.
ALTER SERVER warehouse OPTIONS (SET host 'postgres');
SQL
