#!/usr/bin/env bash
# The rest of what the Postgres catalog can describe: row-level security, rules, an event trigger,
# extended statistics, a collation, a text search configuration, an operator and a cast, aggregate and
# window-friendly functions, SECURITY DEFINER, more index methods, views with options, a tablespace,
# replication (a publication and a subscription that does not connect).
set -euo pipefail
mkdir -p /var/lib/postgresql/archive_space
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname acme <<'SQL'
CREATE TABLESPACE archive_space LOCATION '/var/lib/postgresql/archive_space';
COMMENT ON TABLESPACE archive_space IS 'Where old, rarely read data lives.';

-- Row-level security: a seller sees only the orders they sold.
ALTER TABLE sales.orders ENABLE ROW LEVEL SECURITY;
CREATE POLICY orders_own_sales ON sales.orders FOR SELECT TO acme_app
    USING (sold_by = nullif(current_setting('acme.employee_id', true), '')::integer);
COMMENT ON POLICY orders_own_sales ON sales.orders IS 'A seller sees only the orders they sold.';

-- A rule: deleting a customer marks it instead (a view-less rewrite).
CREATE TABLE sales.customer_deletions (customer_id bigint PRIMARY KEY, deleted_at timestamptz NOT NULL DEFAULT now())
    TABLESPACE archive_space;
COMMENT ON TABLE sales.customer_deletions IS 'Customers asked to be forgotten (kept in the archive tablespace).';
CREATE RULE customers_soft_delete AS ON DELETE TO sales.customers
    DO INSTEAD INSERT INTO sales.customer_deletions (customer_id) VALUES (OLD.id) ON CONFLICT DO NOTHING;
COMMENT ON RULE customers_soft_delete ON sales.customers IS 'Deleting a customer records the request instead.';

-- An event trigger: DDL is written to the audit log.
CREATE TABLE audit.ddl_log (happened_at timestamptz NOT NULL DEFAULT now(), command text NOT NULL, object text);
COMMENT ON TABLE audit.ddl_log IS 'Every change of structure, written by an event trigger.';
CREATE FUNCTION audit.log_ddl() RETURNS event_trigger LANGUAGE plpgsql AS $$
DECLARE r record;
BEGIN
    FOR r IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
        INSERT INTO audit.ddl_log (command, object) VALUES (r.command_tag, r.object_identity);
    END LOOP;
END
$$;
COMMENT ON FUNCTION audit.log_ddl() IS 'Writes each DDL command to audit.ddl_log.';
CREATE EVENT TRIGGER ddl_audit ON ddl_command_end EXECUTE FUNCTION audit.log_ddl();
COMMENT ON EVENT TRIGGER ddl_audit IS 'Logs every change of structure.';

-- Extended statistics: city and state go together.
CREATE STATISTICS sales.orders_status_seller (dependencies, ndistinct) ON status, sold_by FROM sales.orders;
COMMENT ON STATISTICS sales.orders_status_seller IS 'Status and seller depend on each other.';

-- A collation, a text search configuration, an operator and a cast of our own.
CREATE COLLATION catalog.pt_br_ci (provider = icu, locale = 'pt-BR-u-ks-level1', deterministic = false);
COMMENT ON COLLATION catalog.pt_br_ci IS 'Portuguese, ignoring case and accents.';
CREATE TEXT SEARCH CONFIGURATION catalog.products_search (COPY = portuguese);
COMMENT ON TEXT SEARCH CONFIGURATION catalog.products_search IS 'Search over product names, in Portuguese.';
CREATE FUNCTION sales.address_city_equals(a sales.address, b sales.address) RETURNS boolean
    LANGUAGE sql IMMUTABLE AS $$ SELECT (a).city = (b).city $$;
CREATE OPERATOR sales.=~ (LEFTARG = sales.address, RIGHTARG = sales.address, FUNCTION = sales.address_city_equals);
COMMENT ON OPERATOR sales.=~ (sales.address, sales.address) IS 'Two addresses in the same city.';
CREATE FUNCTION sales.address_text(a sales.address) RETURNS text
    LANGUAGE sql IMMUTABLE AS $$ SELECT concat_ws(', ', (a).street || ' ' || (a).number, (a).city, (a).state) $$;
CREATE CAST (sales.address AS text) WITH FUNCTION sales.address_text(sales.address);
COMMENT ON CAST (sales.address AS text) IS 'An address as one line.';

-- An aggregate of our own, and a SECURITY DEFINER function.
CREATE FUNCTION catalog.price_max_step(state numeric, value numeric) RETURNS numeric
    LANGUAGE sql IMMUTABLE AS $$ SELECT greatest(state, value) $$;
CREATE AGGREGATE catalog.highest_price(numeric) (SFUNC = catalog.price_max_step, STYPE = numeric);
COMMENT ON AGGREGATE catalog.highest_price(numeric) IS 'The highest of the prices given.';
CREATE FUNCTION hr.payroll_total() RETURNS numeric LANGUAGE sql STABLE SECURITY DEFINER SET search_path = hr AS $$
    SELECT sum(salary) FROM hr.employees
$$;
COMMENT ON FUNCTION hr.payroll_total() IS 'The payroll, readable by whoever may call it without reading the salaries.';
REVOKE ALL ON FUNCTION hr.payroll_total() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION hr.payroll_total() TO acme_app;

-- More index methods: BRIN, hash, GiST, a covering index (INCLUDE).
CREATE INDEX movements_moved_brin ON inventory.movements_2025 USING brin (moved_at);
CREATE INDEX customers_email_hash ON sales.customers USING hash (email);
CREATE INDEX price_history_period ON catalog.price_history USING gist (valid_during);
CREATE INDEX orders_customer_covering ON sales.orders (customer_id) INCLUDE (status, total);

-- Views with options: a check option and a security barrier.
CREATE VIEW catalog.active_products WITH (security_barrier) AS
SELECT id, sku, name, category_id, price FROM catalog.products WHERE active
WITH CASCADED CHECK OPTION;
COMMENT ON VIEW catalog.active_products IS 'Products on sale; rows written through it must stay active.';

-- Replication: what the shop publishes, and a subscription that is created without connecting.
CREATE PUBLICATION acme_catalog FOR TABLE catalog.categories, catalog.products;
COMMENT ON PUBLICATION acme_catalog IS 'The catalog, for the read replicas.';
CREATE SUBSCRIPTION warehouse_feed CONNECTION 'host=postgres dbname=acme_warehouse user=nobody'
    PUBLICATION warehouse_shipments WITH (connect = false, enabled = false, create_slot = false, slot_name = NONE);
COMMENT ON SUBSCRIPTION warehouse_feed IS 'Shipments from the warehouse (disabled in the test bed).';
SQL
