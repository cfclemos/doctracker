--
-- PostgreSQL database dump
--

\restrict b72sJJqfno4aMtSZU8fxegtufuIKRkmvqFUWfeT4QyRmhaUlkCA9ee55Z6kjto6

-- Dumped from database version 17.6 (Debian 17.6-2.pgdg13+1)
-- Dumped by pg_dump version 17.6 (Debian 17.6-2.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: audit; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA audit;


--
-- Name: SCHEMA audit; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA audit IS 'What changed, when and by whom, written by triggers.';


--
-- Name: billing; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA billing;


--
-- Name: SCHEMA billing; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA billing IS 'Invoices and payments of the orders.';


--
-- Name: catalog; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA catalog;


--
-- Name: SCHEMA catalog; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA catalog IS 'What the shop sells: categories, products, prices.';


--
-- Name: hr; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA hr;


--
-- Name: SCHEMA hr; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA hr IS 'People who work at the shop.';


--
-- Name: inventory; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA inventory;


--
-- Name: SCHEMA inventory; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA inventory IS 'Stock in each store and the movements that change it.';


--
-- Name: sales; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA sales;


--
-- Name: SCHEMA sales; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA sales IS 'Customers, their orders and what each order holds.';


--
-- Name: staging; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA staging;


--
-- Name: SCHEMA staging; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA staging IS 'Raw imports, loose on purpose: no keys, relations only by name.';


--
-- Name: warehouse; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA warehouse;


--
-- Name: SCHEMA warehouse; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA warehouse IS 'Tables of acme_warehouse seen from the shop (foreign tables).';


--
-- Name: pt_br_ci; Type: COLLATION; Schema: catalog; Owner: -
--

CREATE COLLATION catalog.pt_br_ci (provider = icu, deterministic = false, locale = 'pt-BR-u-ks-level1');


--
-- Name: COLLATION pt_br_ci; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLLATION catalog.pt_br_ci IS 'Portuguese, ignoring case and accents.';


--
-- Name: btree_gist; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA public;


--
-- Name: EXTENSION btree_gist; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION btree_gist IS 'support for indexing common datatypes in GiST';


--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: postgres_fdw; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgres_fdw WITH SCHEMA public;


--
-- Name: EXTENSION postgres_fdw; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION postgres_fdw IS 'foreign-data wrapper for remote PostgreSQL servers';


--
-- Name: price; Type: DOMAIN; Schema: catalog; Owner: -
--

CREATE DOMAIN catalog.price AS numeric(12,2)
	CONSTRAINT price_check CHECK ((VALUE >= (0)::numeric));


--
-- Name: DOMAIN price; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON DOMAIN catalog.price IS 'A price in reais, never negative.';


--
-- Name: address; Type: TYPE; Schema: sales; Owner: -
--

CREATE TYPE sales.address AS (
	street text,
	number text,
	city text,
	state character(2),
	postal_code text
);


--
-- Name: TYPE address; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON TYPE sales.address IS 'A postal address.';


--
-- Name: cpf; Type: DOMAIN; Schema: sales; Owner: -
--

CREATE DOMAIN sales.cpf AS text
	CONSTRAINT cpf_check CHECK ((VALUE ~ '^\d{3}\.\d{3}\.\d{3}-\d{2}$'::text));


--
-- Name: DOMAIN cpf; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON DOMAIN sales.cpf IS 'A Brazilian taxpayer number, written 000.000.000-00.';


--
-- Name: order_status; Type: TYPE; Schema: sales; Owner: -
--

CREATE TYPE sales.order_status AS ENUM (
    'draft',
    'placed',
    'paid',
    'shipped',
    'cancelled'
);


--
-- Name: TYPE order_status; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON TYPE sales.order_status IS 'Where an order is in its life.';


--
-- Name: address_text(sales.address); Type: FUNCTION; Schema: sales; Owner: -
--

CREATE FUNCTION sales.address_text(a sales.address) RETURNS text
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT concat_ws(', ', (a).street || ' ' || (a).number, (a).city, (a).state) $$;


--
-- Name: CAST (sales.address AS text); Type: CAST; Schema: -; Owner: -
--

CREATE CAST (sales.address AS text) WITH FUNCTION sales.address_text(sales.address);


--
-- Name: CAST (sales.address AS text); Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON CAST (sales.address AS text) IS 'An address as one line.';


--
-- Name: log_ddl(); Type: FUNCTION; Schema: audit; Owner: -
--

CREATE FUNCTION audit.log_ddl() RETURNS event_trigger
    LANGUAGE plpgsql
    AS $$
DECLARE r record;
BEGIN
    FOR r IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
        INSERT INTO audit.ddl_log (command, object) VALUES (r.command_tag, r.object_identity);
    END LOOP;
END
$$;


--
-- Name: FUNCTION log_ddl(); Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON FUNCTION audit.log_ddl() IS 'Writes each DDL command to audit.ddl_log.';


--
-- Name: write_log(); Type: FUNCTION; Schema: audit; Owner: -
--

CREATE FUNCTION audit.write_log() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_TABLE_SCHEMA = 'sales' THEN
        INSERT INTO audit.sales_log (action, row_data, table_name) VALUES (TG_OP, to_jsonb(coalesce(NEW, OLD)), TG_TABLE_NAME);
    ELSE
        INSERT INTO audit.catalog_log (action, row_data, table_name) VALUES (TG_OP, to_jsonb(coalesce(NEW, OLD)), TG_TABLE_NAME);
    END IF;
    RETURN coalesce(NEW, OLD);
END
$$;


--
-- Name: FUNCTION write_log(); Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON FUNCTION audit.write_log() IS 'Writes a row of the audit log for every change.';


--
-- Name: final_price(catalog.price, numeric); Type: FUNCTION; Schema: catalog; Owner: -
--

CREATE FUNCTION catalog.final_price(base catalog.price, discount numeric DEFAULT 0) RETURNS numeric
    LANGUAGE sql IMMUTABLE
    AS $$
    SELECT round(base * (1 - discount), 2)
$$;


--
-- Name: FUNCTION final_price(base catalog.price, discount numeric); Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON FUNCTION catalog.final_price(base catalog.price, discount numeric) IS 'A price after a discount (0.1 = 10 %).';


--
-- Name: price_max_step(numeric, numeric); Type: FUNCTION; Schema: catalog; Owner: -
--

CREATE FUNCTION catalog.price_max_step(state numeric, value numeric) RETURNS numeric
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT greatest(state, value) $$;


--
-- Name: payroll_total(); Type: FUNCTION; Schema: hr; Owner: -
--

CREATE FUNCTION hr.payroll_total() RETURNS numeric
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'hr'
    AS $$
    SELECT sum(salary) FROM hr.employees
$$;


--
-- Name: FUNCTION payroll_total(); Type: COMMENT; Schema: hr; Owner: -
--

COMMENT ON FUNCTION hr.payroll_total() IS 'The payroll, readable by whoever may call it without reading the salaries.';


--
-- Name: apply_movement(); Type: FUNCTION; Schema: inventory; Owner: -
--

CREATE FUNCTION inventory.apply_movement() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    INSERT INTO inventory.stock (store_id, region, product_id, quantity)
    SELECT NEW.store_id, s.region, NEW.product_id, NEW.quantity FROM inventory.stores s WHERE s.id = NEW.store_id
    ON CONFLICT (store_id, region, product_id) DO UPDATE SET quantity = inventory.stock.quantity + EXCLUDED.quantity;
    RETURN NEW;
END
$$;


--
-- Name: FUNCTION apply_movement(); Type: COMMENT; Schema: inventory; Owner: -
--

COMMENT ON FUNCTION inventory.apply_movement() IS 'Adds a movement to the stock of its store.';


--
-- Name: address_city_equals(sales.address, sales.address); Type: FUNCTION; Schema: sales; Owner: -
--

CREATE FUNCTION sales.address_city_equals(a sales.address, b sales.address) RETURNS boolean
    LANGUAGE sql IMMUTABLE
    AS $$ SELECT (a).city = (b).city $$;


--
-- Name: cancel_stale_drafts(interval); Type: PROCEDURE; Schema: sales; Owner: -
--

CREATE PROCEDURE sales.cancel_stale_drafts(IN older_than interval DEFAULT '30 days'::interval)
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE sales.orders SET status = 'cancelled'
    WHERE status = 'draft' AND id IN (SELECT id FROM sales.orders WHERE status = 'draft')
      AND coalesce(placed_at, now() - older_than - interval '1 day') < now() - older_than;
END
$$;


--
-- Name: PROCEDURE cancel_stale_drafts(IN older_than interval); Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON PROCEDURE sales.cancel_stale_drafts(IN older_than interval) IS 'Cancels the drafts nobody touched for a while.';


--
-- Name: customer_lifetime_value(bigint); Type: FUNCTION; Schema: sales; Owner: -
--

CREATE FUNCTION sales.customer_lifetime_value(customer bigint) RETURNS numeric
    LANGUAGE sql STABLE
    AS $$
    SELECT coalesce(sum(o.total), 0) FROM sales.orders o
    WHERE o.customer_id = customer AND o.status IN ('paid', 'shipped')
$$;


--
-- Name: FUNCTION customer_lifetime_value(customer bigint); Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON FUNCTION sales.customer_lifetime_value(customer bigint) IS 'All a customer has paid, over every order.';


--
-- Name: recompute_total(); Type: FUNCTION; Schema: sales; Owner: -
--

CREATE FUNCTION sales.recompute_total() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    UPDATE sales.orders o
    SET total = (SELECT coalesce(sum(i.quantity * i.unit_price), 0) FROM sales.order_items i WHERE i.order_id = o.id)
    WHERE o.id = coalesce(NEW.order_id, OLD.order_id);
    RETURN NULL;
END
$$;


--
-- Name: FUNCTION recompute_total(); Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON FUNCTION sales.recompute_total() IS 'Keeps sales.orders.total equal to the sum of its items.';


--
-- Name: highest_price(numeric); Type: AGGREGATE; Schema: catalog; Owner: -
--

CREATE AGGREGATE catalog.highest_price(numeric) (
    SFUNC = catalog.price_max_step,
    STYPE = numeric
);


--
-- Name: AGGREGATE highest_price(numeric); Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON AGGREGATE catalog.highest_price(numeric) IS 'The highest of the prices given.';


--
-- Name: =~; Type: OPERATOR; Schema: sales; Owner: -
--

CREATE OPERATOR sales.=~ (
    FUNCTION = sales.address_city_equals,
    LEFTARG = sales.address,
    RIGHTARG = sales.address
);


--
-- Name: OPERATOR =~ (sales.address, sales.address); Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON OPERATOR sales.=~ (sales.address, sales.address) IS 'Two addresses in the same city.';


--
-- Name: products_search; Type: TEXT SEARCH CONFIGURATION; Schema: catalog; Owner: -
--

CREATE TEXT SEARCH CONFIGURATION catalog.products_search (
    PARSER = pg_catalog."default" );

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR asciiword WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR word WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR numword WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR email WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR url WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR host WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR sfloat WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR version WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR hword_numpart WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR hword_part WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR hword_asciipart WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR numhword WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR asciihword WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR hword WITH portuguese_stem;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR url_path WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR file WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR "float" WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR "int" WITH simple;

ALTER TEXT SEARCH CONFIGURATION catalog.products_search
    ADD MAPPING FOR uint WITH simple;


--
-- Name: TEXT SEARCH CONFIGURATION products_search; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TEXT SEARCH CONFIGURATION catalog.products_search IS 'Search over product names, in Portuguese.';


--
-- Name: warehouse; Type: SERVER; Schema: -; Owner: -
--

CREATE SERVER warehouse FOREIGN DATA WRAPPER postgres_fdw OPTIONS (
    dbname 'acme_warehouse',
    host 'postgres'
);


--
-- Name: SERVER warehouse; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SERVER warehouse IS 'The warehouse database, on the same server.';


--
-- Name: USER MAPPING acme_admin SERVER warehouse; Type: USER MAPPING; Schema: -; Owner: -
--

CREATE USER MAPPING FOR acme_admin SERVER warehouse OPTIONS (
    password 'change-me',
    "user" 'acme_admin'
);


--
-- Name: USER MAPPING doctracker_reader SERVER warehouse; Type: USER MAPPING; Schema: -; Owner: -
--

CREATE USER MAPPING FOR doctracker_reader SERVER warehouse OPTIONS (
    password 'change-me',
    "user" 'doctracker_reader'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: log; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.log (
    id bigint NOT NULL,
    happened_at timestamp with time zone DEFAULT now() NOT NULL,
    actor text DEFAULT CURRENT_USER NOT NULL,
    action text NOT NULL,
    row_data jsonb
);


--
-- Name: TABLE log; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON TABLE audit.log IS 'Every change written by the audit triggers.';


--
-- Name: catalog_log; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.catalog_log (
    table_name text NOT NULL
)
INHERITS (audit.log);


--
-- Name: TABLE catalog_log; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON TABLE audit.catalog_log IS 'Changes to the catalog schema.';


--
-- Name: ddl_log; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.ddl_log (
    happened_at timestamp with time zone DEFAULT now() NOT NULL,
    command text NOT NULL,
    object text
);


--
-- Name: TABLE ddl_log; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON TABLE audit.ddl_log IS 'Every change of structure, written by an event trigger.';


--
-- Name: log_id_seq; Type: SEQUENCE; Schema: audit; Owner: -
--

CREATE SEQUENCE audit.log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: log_id_seq; Type: SEQUENCE OWNED BY; Schema: audit; Owner: -
--

ALTER SEQUENCE audit.log_id_seq OWNED BY audit.log.id;


--
-- Name: sales_log; Type: TABLE; Schema: audit; Owner: -
--

CREATE TABLE audit.sales_log (
    table_name text NOT NULL
)
INHERITS (audit.log);


--
-- Name: TABLE sales_log; Type: COMMENT; Schema: audit; Owner: -
--

COMMENT ON TABLE audit.sales_log IS 'Changes to the sales schema.';


--
-- Name: invoices; Type: TABLE; Schema: billing; Owner: -
--

CREATE TABLE billing.invoices (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    issued_on date DEFAULT CURRENT_DATE NOT NULL,
    amount numeric(12,2) NOT NULL,
    access_key character(44)
);


--
-- Name: TABLE invoices; Type: COMMENT; Schema: billing; Owner: -
--

COMMENT ON TABLE billing.invoices IS 'The invoice of an order (one per order).';


--
-- Name: COLUMN invoices.access_key; Type: COMMENT; Schema: billing; Owner: -
--

COMMENT ON COLUMN billing.invoices.access_key IS 'The 44-digit key of the electronic invoice.';


--
-- Name: invoices_id_seq; Type: SEQUENCE; Schema: billing; Owner: -
--

ALTER TABLE billing.invoices ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME billing.invoices_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: open_invoices; Type: VIEW; Schema: billing; Owner: -
--

CREATE VIEW billing.open_invoices AS
SELECT
    NULL::bigint AS id,
    NULL::bigint AS order_id,
    NULL::numeric(12,2) AS amount,
    NULL::numeric AS due;


--
-- Name: VIEW open_invoices; Type: COMMENT; Schema: billing; Owner: -
--

COMMENT ON VIEW billing.open_invoices IS 'Invoices not fully paid, with what is still due.';


--
-- Name: payments; Type: TABLE; Schema: billing; Owner: -
--

CREATE TABLE billing.payments (
    id bigint NOT NULL,
    invoice_id bigint NOT NULL,
    paid_at timestamp with time zone NOT NULL,
    amount numeric(12,2) NOT NULL,
    method text NOT NULL,
    card_last4 character(4),
    gateway_payload jsonb,
    CONSTRAINT payments_amount_check CHECK ((amount > (0)::numeric)),
    CONSTRAINT payments_method_check CHECK ((method = ANY (ARRAY['pix'::text, 'card'::text, 'boleto'::text])))
);


--
-- Name: TABLE payments; Type: COMMENT; Schema: billing; Owner: -
--

COMMENT ON TABLE billing.payments IS 'Money received for an invoice.';


--
-- Name: payments_id_seq; Type: SEQUENCE; Schema: billing; Owner: -
--

ALTER TABLE billing.payments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME billing.payments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: refunds; Type: TABLE; Schema: billing; Owner: -
--

CREATE TABLE billing.refunds (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    line smallint NOT NULL,
    amount numeric(12,2) NOT NULL,
    reason text
);


--
-- Name: TABLE refunds; Type: COMMENT; Schema: billing; Owner: -
--

COMMENT ON TABLE billing.refunds IS 'Money given back for a line of an order.';


--
-- Name: refunds_id_seq; Type: SEQUENCE; Schema: billing; Owner: -
--

ALTER TABLE billing.refunds ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME billing.refunds_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: products; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE catalog.products (
    id integer NOT NULL,
    sku text NOT NULL,
    name text NOT NULL,
    description text,
    category_id integer NOT NULL,
    price catalog.price NOT NULL,
    cost catalog.price,
    margin numeric(12,2) GENERATED ALWAYS AS (((price)::numeric - COALESCE((cost)::numeric, (0)::numeric))) STORED,
    tags text[] DEFAULT '{}'::text[] NOT NULL,
    attributes jsonb DEFAULT '{}'::jsonb NOT NULL,
    active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT products_cost_below_price CHECK (((cost IS NULL) OR ((cost)::numeric <= (price)::numeric)))
);


--
-- Name: TABLE products; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE catalog.products IS 'What the shop sells.';


--
-- Name: COLUMN products.margin; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN catalog.products.margin IS 'Price minus cost, worked out by the database.';


--
-- Name: COLUMN products.attributes; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN catalog.products.attributes IS 'Free attributes: colour, size, weight...';


--
-- Name: active_products; Type: VIEW; Schema: catalog; Owner: -
--

CREATE VIEW catalog.active_products WITH (security_barrier='true') AS
 SELECT id,
    sku,
    name,
    category_id,
    price
   FROM catalog.products
  WHERE active
  WITH CASCADED CHECK OPTION;


--
-- Name: VIEW active_products; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON VIEW catalog.active_products IS 'Products on sale; rows written through it must stay active.';


--
-- Name: order_items; Type: TABLE; Schema: sales; Owner: -
--

CREATE TABLE sales.order_items (
    order_id bigint NOT NULL,
    line smallint NOT NULL,
    product_id integer NOT NULL,
    quantity integer NOT NULL,
    unit_price catalog.price NOT NULL,
    CONSTRAINT order_items_quantity_check CHECK ((quantity > 0))
);


--
-- Name: TABLE order_items; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON TABLE sales.order_items IS 'The lines of an order.';


--
-- Name: best_sellers; Type: MATERIALIZED VIEW; Schema: catalog; Owner: -
--

CREATE MATERIALIZED VIEW catalog.best_sellers AS
 SELECT p.id,
    p.name,
    sum(i.quantity) AS sold,
    sum(((i.quantity)::numeric * (i.unit_price)::numeric)) AS revenue
   FROM (catalog.products p
     JOIN sales.order_items i ON ((i.product_id = p.id)))
  GROUP BY p.id, p.name
  WITH NO DATA;


--
-- Name: MATERIALIZED VIEW best_sellers; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON MATERIALIZED VIEW catalog.best_sellers IS 'Products by units sold; refreshed every night.';


--
-- Name: categories; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE catalog.categories (
    id integer NOT NULL,
    parent_id integer,
    name text NOT NULL,
    slug text NOT NULL
);


--
-- Name: TABLE categories; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE catalog.categories IS 'Categories of products, as a tree.';


--
-- Name: COLUMN categories.parent_id; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON COLUMN catalog.categories.parent_id IS 'The category above; none at the top.';


--
-- Name: categories_id_seq; Type: SEQUENCE; Schema: catalog; Owner: -
--

ALTER TABLE catalog.categories ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME catalog.categories_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: price_history; Type: TABLE; Schema: catalog; Owner: -
--

CREATE TABLE catalog.price_history (
    product_id integer NOT NULL,
    valid_during tstzrange NOT NULL,
    price catalog.price NOT NULL
);


--
-- Name: TABLE price_history; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TABLE catalog.price_history IS 'Every price a product had and when; two periods never overlap.';


--
-- Name: products_id_seq; Type: SEQUENCE; Schema: catalog; Owner: -
--

ALTER TABLE catalog.products ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME catalog.products_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: employees; Type: TABLE; Schema: hr; Owner: -
--

CREATE TABLE hr.employees (
    id integer NOT NULL,
    name text NOT NULL,
    email public.citext NOT NULL,
    manager_id integer,
    hired_on date NOT NULL,
    salary numeric(12,2),
    CONSTRAINT employees_salary_check CHECK ((salary > (0)::numeric))
);


--
-- Name: TABLE employees; Type: COMMENT; Schema: hr; Owner: -
--

COMMENT ON TABLE hr.employees IS 'People who work at the shop; each answers to a manager.';


--
-- Name: COLUMN employees.salary; Type: COMMENT; Schema: hr; Owner: -
--

COMMENT ON COLUMN hr.employees.salary IS 'Monthly salary, sensitive.';


--
-- Name: employees_id_seq; Type: SEQUENCE; Schema: hr; Owner: -
--

ALTER TABLE hr.employees ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME hr.employees_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: movements; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.movements (
    id bigint NOT NULL,
    store_id smallint NOT NULL,
    product_id integer NOT NULL,
    moved_at timestamp with time zone NOT NULL,
    quantity integer NOT NULL
)
PARTITION BY RANGE (moved_at);


--
-- Name: TABLE movements; Type: COMMENT; Schema: inventory; Owner: -
--

COMMENT ON TABLE inventory.movements IS 'Every change of stock, split by year.';


--
-- Name: movements_2025; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.movements_2025 (
    id bigint NOT NULL,
    store_id smallint NOT NULL,
    product_id integer NOT NULL,
    moved_at timestamp with time zone NOT NULL,
    quantity integer NOT NULL
);


--
-- Name: movements_2026; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.movements_2026 (
    id bigint NOT NULL,
    store_id smallint NOT NULL,
    product_id integer NOT NULL,
    moved_at timestamp with time zone NOT NULL,
    quantity integer NOT NULL
);


--
-- Name: movements_id_seq; Type: SEQUENCE; Schema: inventory; Owner: -
--

ALTER TABLE inventory.movements ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME inventory.movements_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: movements_other; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.movements_other (
    id bigint NOT NULL,
    store_id smallint NOT NULL,
    product_id integer NOT NULL,
    moved_at timestamp with time zone NOT NULL,
    quantity integer NOT NULL
);


--
-- Name: stock; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.stock (
    store_id smallint NOT NULL,
    region text NOT NULL,
    product_id integer NOT NULL,
    quantity integer DEFAULT 0 NOT NULL
)
PARTITION BY LIST (region);


--
-- Name: TABLE stock; Type: COMMENT; Schema: inventory; Owner: -
--

COMMENT ON TABLE inventory.stock IS 'How many units of each product each store has, split by region.';


--
-- Name: stock_by_region; Type: MATERIALIZED VIEW; Schema: inventory; Owner: -
--

CREATE MATERIALIZED VIEW inventory.stock_by_region AS
 SELECT region,
    product_id,
    sum(quantity) AS quantity
   FROM inventory.stock
  GROUP BY region, product_id
  WITH NO DATA;


--
-- Name: MATERIALIZED VIEW stock_by_region; Type: COMMENT; Schema: inventory; Owner: -
--

COMMENT ON MATERIALIZED VIEW inventory.stock_by_region IS 'Units of each product per region.';


--
-- Name: stock_east_west; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.stock_east_west (
    store_id smallint NOT NULL,
    region text NOT NULL,
    product_id integer NOT NULL,
    quantity integer DEFAULT 0 NOT NULL
);


--
-- Name: stock_north_south; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.stock_north_south (
    store_id smallint NOT NULL,
    region text NOT NULL,
    product_id integer NOT NULL,
    quantity integer DEFAULT 0 NOT NULL
);


--
-- Name: stores; Type: TABLE; Schema: inventory; Owner: -
--

CREATE TABLE inventory.stores (
    id smallint NOT NULL,
    name text NOT NULL,
    region text NOT NULL,
    CONSTRAINT stores_region_check CHECK ((region = ANY (ARRAY['north'::text, 'south'::text, 'east'::text, 'west'::text])))
);


--
-- Name: TABLE stores; Type: COMMENT; Schema: inventory; Owner: -
--

COMMENT ON TABLE inventory.stores IS 'Physical stores and their region.';


--
-- Name: stores_id_seq; Type: SEQUENCE; Schema: inventory; Owner: -
--

ALTER TABLE inventory.stores ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME inventory.stores_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


SET default_tablespace = archive_space;

--
-- Name: customer_deletions; Type: TABLE; Schema: sales; Owner: -; Tablespace: archive_space
--

CREATE TABLE sales.customer_deletions (
    customer_id bigint NOT NULL,
    deleted_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE customer_deletions; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON TABLE sales.customer_deletions IS 'Customers asked to be forgotten (kept in the archive tablespace).';


SET default_tablespace = '';

--
-- Name: customers; Type: TABLE; Schema: sales; Owner: -
--

CREATE TABLE sales.customers (
    id bigint NOT NULL,
    name text NOT NULL,
    email public.citext NOT NULL,
    cpf sales.cpf,
    phone text,
    password_hash text NOT NULL,
    birth_date date,
    address sales.address,
    referred_by bigint,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: TABLE customers; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON TABLE sales.customers IS 'People who buy at the shop.';


--
-- Name: COLUMN customers.password_hash; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON COLUMN sales.customers.password_hash IS 'The password, hashed with bcrypt (pgcrypto).';


--
-- Name: COLUMN customers.referred_by; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON COLUMN sales.customers.referred_by IS 'The customer who brought this one.';


--
-- Name: customers_id_seq; Type: SEQUENCE; Schema: sales; Owner: -
--

ALTER TABLE sales.customers ALTER COLUMN id ADD GENERATED BY DEFAULT AS IDENTITY (
    SEQUENCE NAME sales.customers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: order_summary; Type: VIEW; Schema: sales; Owner: -
--

CREATE VIEW sales.order_summary AS
SELECT
    NULL::bigint AS id,
    NULL::integer AS number,
    NULL::text AS customer,
    NULL::sales.order_status AS status,
    NULL::timestamp with time zone AS placed_at,
    NULL::numeric(12,2) AS total,
    NULL::bigint AS lines;


--
-- Name: VIEW order_summary; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON VIEW sales.order_summary IS 'Each order with its customer and how many lines it has.';


--
-- Name: customers_in_debt; Type: VIEW; Schema: sales; Owner: -
--

CREATE VIEW sales.customers_in_debt AS
 SELECT s.customer,
    sum(oi.due) AS due
   FROM (sales.order_summary s
     JOIN billing.open_invoices oi ON ((oi.order_id = s.id)))
  GROUP BY s.customer;


--
-- Name: VIEW customers_in_debt; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON VIEW sales.customers_in_debt IS 'Customers with invoices still to pay (a view of two views).';


--
-- Name: orders; Type: TABLE; Schema: sales; Owner: -
--

CREATE TABLE sales.orders (
    id bigint NOT NULL,
    number integer NOT NULL,
    customer_id bigint NOT NULL,
    sold_by integer,
    status sales.order_status DEFAULT 'draft'::sales.order_status NOT NULL,
    placed_at timestamp with time zone,
    shipping_address sales.address,
    total numeric(12,2) DEFAULT 0 NOT NULL,
    CONSTRAINT orders_placed_when_not_draft CHECK (((status = 'draft'::sales.order_status) OR (placed_at IS NOT NULL)))
);


--
-- Name: TABLE orders; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON TABLE sales.orders IS 'An order of a customer.';


--
-- Name: COLUMN orders.total; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON COLUMN sales.orders.total IS 'Sum of the items, kept by a trigger.';


--
-- Name: order_number_seq; Type: SEQUENCE; Schema: sales; Owner: -
--

CREATE SEQUENCE sales.order_number_seq
    START WITH 1000
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_number_seq; Type: SEQUENCE OWNED BY; Schema: sales; Owner: -
--

ALTER SEQUENCE sales.order_number_seq OWNED BY sales.orders.number;


--
-- Name: SEQUENCE order_number_seq; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON SEQUENCE sales.order_number_seq IS 'The numbers printed on the orders.';


--
-- Name: orders_id_seq; Type: SEQUENCE; Schema: sales; Owner: -
--

ALTER TABLE sales.orders ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME sales.orders_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: imported_orders; Type: TABLE; Schema: staging; Owner: -
--

CREATE TABLE staging.imported_orders (
    external_ref text,
    customer_id bigint,
    product_id integer,
    quantity integer,
    raw jsonb,
    loaded_at timestamp with time zone DEFAULT now()
);


--
-- Name: TABLE imported_orders; Type: COMMENT; Schema: staging; Owner: -
--

COMMENT ON TABLE staging.imported_orders IS 'Orders from the marketplace, before they are checked: no key, ids not enforced.';


--
-- Name: session_cache; Type: TABLE; Schema: staging; Owner: -
--

CREATE UNLOGGED TABLE staging.session_cache (
    token text NOT NULL,
    customer_id bigint,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE session_cache; Type: COMMENT; Schema: staging; Owner: -
--

COMMENT ON TABLE staging.session_cache IS 'Web sessions (unlogged: lost on a crash).';


--
-- Name: carriers; Type: FOREIGN TABLE; Schema: warehouse; Owner: -
--

CREATE FOREIGN TABLE warehouse.carriers (
    id smallint NOT NULL,
    name text NOT NULL
)
SERVER warehouse
OPTIONS (
    schema_name 'logistics',
    table_name 'carriers'
);
ALTER FOREIGN TABLE ONLY warehouse.carriers ALTER COLUMN id OPTIONS (
    column_name 'id'
);
ALTER FOREIGN TABLE ONLY warehouse.carriers ALTER COLUMN name OPTIONS (
    column_name 'name'
);


--
-- Name: shipments; Type: FOREIGN TABLE; Schema: warehouse; Owner: -
--

CREATE FOREIGN TABLE warehouse.shipments (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    carrier_id smallint NOT NULL,
    tracking_code text,
    shipped_at timestamp with time zone NOT NULL
)
SERVER warehouse
OPTIONS (
    schema_name 'logistics',
    table_name 'shipments'
);
ALTER FOREIGN TABLE ONLY warehouse.shipments ALTER COLUMN id OPTIONS (
    column_name 'id'
);
ALTER FOREIGN TABLE ONLY warehouse.shipments ALTER COLUMN order_id OPTIONS (
    column_name 'order_id'
);
ALTER FOREIGN TABLE ONLY warehouse.shipments ALTER COLUMN carrier_id OPTIONS (
    column_name 'carrier_id'
);
ALTER FOREIGN TABLE ONLY warehouse.shipments ALTER COLUMN tracking_code OPTIONS (
    column_name 'tracking_code'
);
ALTER FOREIGN TABLE ONLY warehouse.shipments ALTER COLUMN shipped_at OPTIONS (
    column_name 'shipped_at'
);


--
-- Name: movements_2025; Type: TABLE ATTACH; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.movements ATTACH PARTITION inventory.movements_2025 FOR VALUES FROM ('2025-01-01 00:00:00+00') TO ('2026-01-01 00:00:00+00');


--
-- Name: movements_2026; Type: TABLE ATTACH; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.movements ATTACH PARTITION inventory.movements_2026 FOR VALUES FROM ('2026-01-01 00:00:00+00') TO ('2027-01-01 00:00:00+00');


--
-- Name: movements_other; Type: TABLE ATTACH; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.movements ATTACH PARTITION inventory.movements_other DEFAULT;


--
-- Name: stock_east_west; Type: TABLE ATTACH; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.stock ATTACH PARTITION inventory.stock_east_west FOR VALUES IN ('east', 'west');


--
-- Name: stock_north_south; Type: TABLE ATTACH; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.stock ATTACH PARTITION inventory.stock_north_south FOR VALUES IN ('north', 'south');


--
-- Name: catalog_log id; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.catalog_log ALTER COLUMN id SET DEFAULT nextval('audit.log_id_seq'::regclass);


--
-- Name: catalog_log happened_at; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.catalog_log ALTER COLUMN happened_at SET DEFAULT now();


--
-- Name: catalog_log actor; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.catalog_log ALTER COLUMN actor SET DEFAULT CURRENT_USER;


--
-- Name: log id; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.log ALTER COLUMN id SET DEFAULT nextval('audit.log_id_seq'::regclass);


--
-- Name: sales_log id; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.sales_log ALTER COLUMN id SET DEFAULT nextval('audit.log_id_seq'::regclass);


--
-- Name: sales_log happened_at; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.sales_log ALTER COLUMN happened_at SET DEFAULT now();


--
-- Name: sales_log actor; Type: DEFAULT; Schema: audit; Owner: -
--

ALTER TABLE ONLY audit.sales_log ALTER COLUMN actor SET DEFAULT CURRENT_USER;


--
-- Name: orders number; Type: DEFAULT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.orders ALTER COLUMN number SET DEFAULT nextval('sales.order_number_seq'::regclass);


--
-- Name: invoices invoices_access_key_key; Type: CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.invoices
    ADD CONSTRAINT invoices_access_key_key UNIQUE (access_key);


--
-- Name: invoices invoices_order_id_key; Type: CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.invoices
    ADD CONSTRAINT invoices_order_id_key UNIQUE (order_id);


--
-- Name: invoices invoices_pkey; Type: CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (id);


--
-- Name: refunds refunds_pkey; Type: CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.refunds
    ADD CONSTRAINT refunds_pkey PRIMARY KEY (id);


--
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);


--
-- Name: categories categories_slug_key; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.categories
    ADD CONSTRAINT categories_slug_key UNIQUE (slug);


--
-- Name: price_history price_history_no_overlap; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.price_history
    ADD CONSTRAINT price_history_no_overlap EXCLUDE USING gist (product_id WITH =, valid_during WITH &&);


--
-- Name: products products_pkey; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.products
    ADD CONSTRAINT products_pkey PRIMARY KEY (id);


--
-- Name: products products_sku_key; Type: CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.products
    ADD CONSTRAINT products_sku_key UNIQUE (sku);


--
-- Name: employees employees_email_key; Type: CONSTRAINT; Schema: hr; Owner: -
--

ALTER TABLE ONLY hr.employees
    ADD CONSTRAINT employees_email_key UNIQUE (email);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: hr; Owner: -
--

ALTER TABLE ONLY hr.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: movements movements_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.movements
    ADD CONSTRAINT movements_pkey PRIMARY KEY (id, moved_at);


--
-- Name: movements_2025 movements_2025_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.movements_2025
    ADD CONSTRAINT movements_2025_pkey PRIMARY KEY (id, moved_at);


--
-- Name: movements_2026 movements_2026_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.movements_2026
    ADD CONSTRAINT movements_2026_pkey PRIMARY KEY (id, moved_at);


--
-- Name: movements_other movements_other_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.movements_other
    ADD CONSTRAINT movements_other_pkey PRIMARY KEY (id, moved_at);


--
-- Name: stock stock_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.stock
    ADD CONSTRAINT stock_pkey PRIMARY KEY (store_id, region, product_id);


--
-- Name: stock_east_west stock_east_west_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.stock_east_west
    ADD CONSTRAINT stock_east_west_pkey PRIMARY KEY (store_id, region, product_id);


--
-- Name: stock_north_south stock_north_south_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.stock_north_south
    ADD CONSTRAINT stock_north_south_pkey PRIMARY KEY (store_id, region, product_id);


--
-- Name: stores stores_pkey; Type: CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE ONLY inventory.stores
    ADD CONSTRAINT stores_pkey PRIMARY KEY (id);


--
-- Name: customer_deletions customer_deletions_pkey; Type: CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.customer_deletions
    ADD CONSTRAINT customer_deletions_pkey PRIMARY KEY (customer_id);


--
-- Name: customers customers_cpf_key; Type: CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.customers
    ADD CONSTRAINT customers_cpf_key UNIQUE (cpf);


--
-- Name: customers customers_email_key; Type: CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.customers
    ADD CONSTRAINT customers_email_key UNIQUE (email);


--
-- Name: customers customers_pkey; Type: CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.customers
    ADD CONSTRAINT customers_pkey PRIMARY KEY (id);


--
-- Name: order_items order_items_pkey; Type: CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.order_items
    ADD CONSTRAINT order_items_pkey PRIMARY KEY (order_id, line);


--
-- Name: orders orders_number_key; Type: CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.orders
    ADD CONSTRAINT orders_number_key UNIQUE (number);


--
-- Name: orders orders_pkey; Type: CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.orders
    ADD CONSTRAINT orders_pkey PRIMARY KEY (id);


--
-- Name: session_cache session_cache_pkey; Type: CONSTRAINT; Schema: staging; Owner: -
--

ALTER TABLE ONLY staging.session_cache
    ADD CONSTRAINT session_cache_pkey PRIMARY KEY (token);


--
-- Name: best_sellers_id; Type: INDEX; Schema: catalog; Owner: -
--

CREATE UNIQUE INDEX best_sellers_id ON catalog.best_sellers USING btree (id);


--
-- Name: price_history_period; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX price_history_period ON catalog.price_history USING gist (valid_during);


--
-- Name: products_active_category; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX products_active_category ON catalog.products USING btree (category_id) WHERE active;


--
-- Name: products_lower_name; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX products_lower_name ON catalog.products USING btree (lower(name));


--
-- Name: products_name_trgm; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX products_name_trgm ON catalog.products USING gin (name public.gin_trgm_ops);


--
-- Name: products_tags; Type: INDEX; Schema: catalog; Owner: -
--

CREATE INDEX products_tags ON catalog.products USING gin (tags);


--
-- Name: movements_moved_brin; Type: INDEX; Schema: inventory; Owner: -
--

CREATE INDEX movements_moved_brin ON inventory.movements_2025 USING brin (moved_at);


--
-- Name: customers_email_hash; Type: INDEX; Schema: sales; Owner: -
--

CREATE INDEX customers_email_hash ON sales.customers USING hash (email);


--
-- Name: orders_customer; Type: INDEX; Schema: sales; Owner: -
--

CREATE INDEX orders_customer ON sales.orders USING btree (customer_id);


--
-- Name: orders_customer_covering; Type: INDEX; Schema: sales; Owner: -
--

CREATE INDEX orders_customer_covering ON sales.orders USING btree (customer_id) INCLUDE (status, total);


--
-- Name: orders_open; Type: INDEX; Schema: sales; Owner: -
--

CREATE INDEX orders_open ON sales.orders USING btree (placed_at) WHERE (status = ANY (ARRAY['placed'::sales.order_status, 'paid'::sales.order_status]));


--
-- Name: movements_2025_pkey; Type: INDEX ATTACH; Schema: inventory; Owner: -
--

ALTER INDEX inventory.movements_pkey ATTACH PARTITION inventory.movements_2025_pkey;


--
-- Name: movements_2026_pkey; Type: INDEX ATTACH; Schema: inventory; Owner: -
--

ALTER INDEX inventory.movements_pkey ATTACH PARTITION inventory.movements_2026_pkey;


--
-- Name: movements_other_pkey; Type: INDEX ATTACH; Schema: inventory; Owner: -
--

ALTER INDEX inventory.movements_pkey ATTACH PARTITION inventory.movements_other_pkey;


--
-- Name: stock_east_west_pkey; Type: INDEX ATTACH; Schema: inventory; Owner: -
--

ALTER INDEX inventory.stock_pkey ATTACH PARTITION inventory.stock_east_west_pkey;


--
-- Name: stock_north_south_pkey; Type: INDEX ATTACH; Schema: inventory; Owner: -
--

ALTER INDEX inventory.stock_pkey ATTACH PARTITION inventory.stock_north_south_pkey;


--
-- Name: orders_status_seller; Type: STATISTICS; Schema: sales; Owner: -
--

CREATE STATISTICS sales.orders_status_seller (ndistinct, dependencies) ON sold_by, status FROM sales.orders;


--
-- Name: STATISTICS orders_status_seller; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON STATISTICS sales.orders_status_seller IS 'Status and seller depend on each other.';


--
-- Name: open_invoices _RETURN; Type: RULE; Schema: billing; Owner: -
--

CREATE OR REPLACE VIEW billing.open_invoices AS
 SELECT inv.id,
    inv.order_id,
    inv.amount,
    (inv.amount - COALESCE(sum(p.amount), (0)::numeric)) AS due
   FROM (billing.invoices inv
     LEFT JOIN billing.payments p ON ((p.invoice_id = inv.id)))
  GROUP BY inv.id
 HAVING ((inv.amount - COALESCE(sum(p.amount), (0)::numeric)) > (0)::numeric);


--
-- Name: order_summary _RETURN; Type: RULE; Schema: sales; Owner: -
--

CREATE OR REPLACE VIEW sales.order_summary AS
 SELECT o.id,
    o.number,
    c.name AS customer,
    o.status,
    o.placed_at,
    o.total,
    count(i.line) AS lines
   FROM ((sales.orders o
     JOIN sales.customers c ON ((c.id = o.customer_id)))
     LEFT JOIN sales.order_items i ON ((i.order_id = o.id)))
  GROUP BY o.id, c.name;


--
-- Name: customers customers_soft_delete; Type: RULE; Schema: sales; Owner: -
--

CREATE RULE customers_soft_delete AS
    ON DELETE TO sales.customers DO INSTEAD  INSERT INTO sales.customer_deletions (customer_id)
  VALUES (old.id) ON CONFLICT DO NOTHING;


--
-- Name: RULE customers_soft_delete ON customers; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON RULE customers_soft_delete ON sales.customers IS 'Deleting a customer records the request instead.';


--
-- Name: products products_audit; Type: TRIGGER; Schema: catalog; Owner: -
--

CREATE TRIGGER products_audit AFTER UPDATE OF price ON catalog.products FOR EACH ROW WHEN (((old.price)::numeric IS DISTINCT FROM (new.price)::numeric)) EXECUTE FUNCTION audit.write_log();


--
-- Name: TRIGGER products_audit ON products; Type: COMMENT; Schema: catalog; Owner: -
--

COMMENT ON TRIGGER products_audit ON catalog.products IS 'Logs every change of price.';


--
-- Name: movements movements_stock; Type: TRIGGER; Schema: inventory; Owner: -
--

CREATE TRIGGER movements_stock AFTER INSERT ON inventory.movements FOR EACH ROW EXECUTE FUNCTION inventory.apply_movement();


--
-- Name: customers customers_audit; Type: TRIGGER; Schema: sales; Owner: -
--

CREATE TRIGGER customers_audit AFTER INSERT OR DELETE OR UPDATE ON sales.customers FOR EACH ROW EXECUTE FUNCTION audit.write_log();


--
-- Name: order_items order_items_total; Type: TRIGGER; Schema: sales; Owner: -
--

CREATE TRIGGER order_items_total AFTER INSERT OR DELETE OR UPDATE ON sales.order_items FOR EACH ROW EXECUTE FUNCTION sales.recompute_total();


--
-- Name: TRIGGER order_items_total ON order_items; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON TRIGGER order_items_total ON sales.order_items IS 'Recomputes the order total when its items change.';


--
-- Name: invoices invoices_order_id_fkey; Type: FK CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.invoices
    ADD CONSTRAINT invoices_order_id_fkey FOREIGN KEY (order_id) REFERENCES sales.orders(id);


--
-- Name: payments payments_invoice_id_fkey; Type: FK CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.payments
    ADD CONSTRAINT payments_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES billing.invoices(id) ON DELETE CASCADE;


--
-- Name: refunds refunds_order_id_line_fkey; Type: FK CONSTRAINT; Schema: billing; Owner: -
--

ALTER TABLE ONLY billing.refunds
    ADD CONSTRAINT refunds_order_id_line_fkey FOREIGN KEY (order_id, line) REFERENCES sales.order_items(order_id, line) ON DELETE CASCADE;


--
-- Name: categories categories_parent_id_fkey; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.categories
    ADD CONSTRAINT categories_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES catalog.categories(id) ON DELETE CASCADE;


--
-- Name: price_history price_history_product_id_fkey; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.price_history
    ADD CONSTRAINT price_history_product_id_fkey FOREIGN KEY (product_id) REFERENCES catalog.products(id) ON DELETE CASCADE;


--
-- Name: products products_category_id_fkey; Type: FK CONSTRAINT; Schema: catalog; Owner: -
--

ALTER TABLE ONLY catalog.products
    ADD CONSTRAINT products_category_id_fkey FOREIGN KEY (category_id) REFERENCES catalog.categories(id) ON DELETE RESTRICT;


--
-- Name: employees employees_manager_id_fkey; Type: FK CONSTRAINT; Schema: hr; Owner: -
--

ALTER TABLE ONLY hr.employees
    ADD CONSTRAINT employees_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES hr.employees(id);


--
-- Name: movements movements_product_id_fkey; Type: FK CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE inventory.movements
    ADD CONSTRAINT movements_product_id_fkey FOREIGN KEY (product_id) REFERENCES catalog.products(id);


--
-- Name: movements movements_store_id_fkey; Type: FK CONSTRAINT; Schema: inventory; Owner: -
--

ALTER TABLE inventory.movements
    ADD CONSTRAINT movements_store_id_fkey FOREIGN KEY (store_id) REFERENCES inventory.stores(id);


--
-- Name: customers customers_referred_by_fkey; Type: FK CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.customers
    ADD CONSTRAINT customers_referred_by_fkey FOREIGN KEY (referred_by) REFERENCES sales.customers(id) ON DELETE SET NULL;


--
-- Name: order_items order_items_order_id_fkey; Type: FK CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.order_items
    ADD CONSTRAINT order_items_order_id_fkey FOREIGN KEY (order_id) REFERENCES sales.orders(id) ON DELETE CASCADE;


--
-- Name: order_items order_items_product_id_fkey; Type: FK CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.order_items
    ADD CONSTRAINT order_items_product_id_fkey FOREIGN KEY (product_id) REFERENCES catalog.products(id);


--
-- Name: orders orders_customer_id_fkey; Type: FK CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.orders
    ADD CONSTRAINT orders_customer_id_fkey FOREIGN KEY (customer_id) REFERENCES sales.customers(id) ON DELETE RESTRICT;


--
-- Name: orders orders_sold_by_fkey; Type: FK CONSTRAINT; Schema: sales; Owner: -
--

ALTER TABLE ONLY sales.orders
    ADD CONSTRAINT orders_sold_by_fkey FOREIGN KEY (sold_by) REFERENCES hr.employees(id) ON DELETE SET NULL;


--
-- Name: orders; Type: ROW SECURITY; Schema: sales; Owner: -
--

ALTER TABLE sales.orders ENABLE ROW LEVEL SECURITY;

--
-- Name: orders orders_own_sales; Type: POLICY; Schema: sales; Owner: -
--

CREATE POLICY orders_own_sales ON sales.orders FOR SELECT TO acme_app USING ((sold_by = (NULLIF(current_setting('acme.employee_id'::text, true), ''::text))::integer));


--
-- Name: POLICY orders_own_sales ON orders; Type: COMMENT; Schema: sales; Owner: -
--

COMMENT ON POLICY orders_own_sales ON sales.orders IS 'A seller sees only the orders they sold.';


--
-- Name: acme_catalog; Type: PUBLICATION; Schema: -; Owner: -
--

CREATE PUBLICATION acme_catalog WITH (publish = 'insert, update, delete, truncate');


--
-- Name: PUBLICATION acme_catalog; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON PUBLICATION acme_catalog IS 'The catalog, for the read replicas.';


--
-- Name: acme_catalog categories; Type: PUBLICATION TABLE; Schema: catalog; Owner: -
--

ALTER PUBLICATION acme_catalog ADD TABLE ONLY catalog.categories;


--
-- Name: acme_catalog products; Type: PUBLICATION TABLE; Schema: catalog; Owner: -
--

ALTER PUBLICATION acme_catalog ADD TABLE ONLY catalog.products;


--
-- Name: warehouse_feed; Type: SUBSCRIPTION; Schema: -; Owner: -
--

CREATE SUBSCRIPTION warehouse_feed CONNECTION 'host=postgres dbname=acme_warehouse user=nobody' PUBLICATION warehouse_shipments WITH (connect = false, slot_name = NONE);


--
-- Name: SUBSCRIPTION warehouse_feed; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SUBSCRIPTION warehouse_feed IS 'Shipments from the warehouse (disabled in the test bed).';


--
-- Name: SCHEMA catalog; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA catalog TO acme_app;


--
-- Name: SCHEMA sales; Type: ACL; Schema: -; Owner: -
--

GRANT USAGE ON SCHEMA sales TO acme_app;


--
-- Name: FUNCTION payroll_total(); Type: ACL; Schema: hr; Owner: -
--

REVOKE ALL ON FUNCTION hr.payroll_total() FROM PUBLIC;
GRANT ALL ON FUNCTION hr.payroll_total() TO acme_app;


--
-- Name: TABLE products; Type: ACL; Schema: catalog; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE catalog.products TO acme_app;


--
-- Name: TABLE active_products; Type: ACL; Schema: catalog; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE catalog.active_products TO acme_app;


--
-- Name: TABLE order_items; Type: ACL; Schema: sales; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sales.order_items TO acme_app;


--
-- Name: TABLE best_sellers; Type: ACL; Schema: catalog; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE catalog.best_sellers TO acme_app;


--
-- Name: TABLE categories; Type: ACL; Schema: catalog; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE catalog.categories TO acme_app;


--
-- Name: TABLE price_history; Type: ACL; Schema: catalog; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE catalog.price_history TO acme_app;


--
-- Name: TABLE customer_deletions; Type: ACL; Schema: sales; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sales.customer_deletions TO acme_app;


--
-- Name: TABLE customers; Type: ACL; Schema: sales; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sales.customers TO acme_app;


--
-- Name: TABLE order_summary; Type: ACL; Schema: sales; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sales.order_summary TO acme_app;


--
-- Name: TABLE customers_in_debt; Type: ACL; Schema: sales; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sales.customers_in_debt TO acme_app;


--
-- Name: TABLE orders; Type: ACL; Schema: sales; Owner: -
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE sales.orders TO acme_app;


--
-- Name: ddl_audit; Type: EVENT TRIGGER; Schema: -; Owner: -
--

CREATE EVENT TRIGGER ddl_audit ON ddl_command_end
   EXECUTE FUNCTION audit.log_ddl();


--
-- Name: EVENT TRIGGER ddl_audit; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EVENT TRIGGER ddl_audit IS 'Logs every change of structure.';


--
-- PostgreSQL database dump complete
--

\unrestrict b72sJJqfno4aMtSZU8fxegtufuIKRkmvqFUWfeT4QyRmhaUlkCA9ee55Z6kjto6

