--
-- PostgreSQL database dump
--

\restrict p3E6d0wMzjUEsb9juymz1hVuePOU7ZQZsuJPe1MB4ZuKXycxouMGo5fYcrji7Ms

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
-- Data for Name: catalog_log; Type: TABLE DATA; Schema: audit; Owner: -
--

COPY audit.catalog_log (id, happened_at, actor, action, row_data, table_name) FROM stdin;
\.


--
-- Data for Name: ddl_log; Type: TABLE DATA; Schema: audit; Owner: -
--

COPY audit.ddl_log (happened_at, command, object) FROM stdin;
2026-10-30 14:05:26.467939+00	CREATE STATISTICS	sales.orders_status_seller
2026-10-30 14:05:26.469482+00	COMMENT	sales.orders_status_seller
2026-10-30 14:05:26.470245+00	CREATE COLLATION	catalog.pt_br_ci
2026-10-30 14:05:26.476638+00	COMMENT	catalog.pt_br_ci
2026-10-30 14:05:26.477162+00	CREATE TEXT SEARCH CONFIGURATION	catalog.products_search
2026-10-30 14:05:26.478012+00	COMMENT	catalog.products_search
2026-10-30 14:05:26.478656+00	CREATE FUNCTION	sales.address_city_equals(sales.address,sales.address)
2026-10-30 14:05:26.479204+00	CREATE OPERATOR	sales.=~(sales.address,sales.address)
2026-10-30 14:05:26.479983+00	COMMENT	sales.=~(sales.address,sales.address)
2026-10-30 14:05:26.480617+00	CREATE FUNCTION	sales.address_text(sales.address)
2026-10-30 14:05:26.481183+00	CREATE CAST	(sales.address AS pg_catalog.text)
2026-10-30 14:05:26.481847+00	COMMENT	(sales.address AS pg_catalog.text)
2026-10-30 14:05:26.482301+00	CREATE FUNCTION	catalog.price_max_step(numeric,numeric)
2026-10-30 14:05:26.483037+00	CREATE AGGREGATE	catalog.highest_price(numeric)
2026-10-30 14:05:26.48363+00	COMMENT	catalog.highest_price(numeric)
2026-10-30 14:05:26.48425+00	CREATE FUNCTION	hr.payroll_total()
2026-10-30 14:05:26.484798+00	COMMENT	hr.payroll_total()
2026-10-30 14:05:26.485315+00	REVOKE	\N
2026-10-30 14:05:26.486099+00	GRANT	\N
2026-10-30 14:05:26.486584+00	CREATE INDEX	inventory.movements_moved_brin
2026-10-30 14:05:26.487644+00	CREATE INDEX	sales.customers_email_hash
2026-10-30 14:05:26.489405+00	CREATE INDEX	catalog.price_history_period
2026-10-30 14:05:26.490847+00	CREATE INDEX	sales.orders_customer_covering
2026-10-30 14:05:26.492+00	CREATE VIEW	catalog.active_products
2026-10-30 14:05:26.492978+00	COMMENT	catalog.active_products
2026-10-30 14:05:26.493476+00	CREATE PUBLICATION	acme_catalog
2026-10-30 14:05:26.49476+00	COMMENT	acme_catalog
2026-10-30 14:05:26.495276+00	CREATE SUBSCRIPTION	warehouse_feed
2026-10-30 14:05:26.496696+00	COMMENT	warehouse_feed
2026-10-30 14:05:26.570699+00	GRANT	\N
2026-10-30 14:05:26.572212+00	GRANT	\N
\.


--
-- Data for Name: log; Type: TABLE DATA; Schema: audit; Owner: -
--

COPY audit.log (id, happened_at, actor, action, row_data) FROM stdin;
\.


--
-- Data for Name: sales_log; Type: TABLE DATA; Schema: audit; Owner: -
--

COPY audit.sales_log (id, happened_at, actor, action, row_data, table_name) FROM stdin;
1	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 1, "cpf": "919.729.709-01", "name": "Customer 1", "email": "customer1@mail.example", "phone": "+55 11 910007331", "address": {"city": "Recife", "state": "PE", "number": "1", "street": "Rua 1", "postal_code": "00037-000"}, "birth_date": "1987-06-08", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$r4x7Pjpr.PJlWw0yhzYeoukDDtC7Ly/aMEUgbJniscvZvVHQLv2yu"}	customers
2	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 2, "cpf": "838.458.418-02", "name": "Customer 2", "email": "customer2@mail.example", "phone": "+55 11 910014662", "address": {"city": "Curitiba", "state": "PR", "number": "2", "street": "Rua 2", "postal_code": "00074-000"}, "birth_date": "1986-03-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$ByYzQxJmhR7yhDYgrSc6r.g4eQwjOdxL7fn2tC5Tghwv/0cq.PvT."}	customers
3	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 3, "cpf": "757.187.127-03", "name": "Customer 3", "email": "customer3@mail.example", "phone": "+55 11 910021993", "address": {"city": "Belém", "state": "PA", "number": "3", "street": "Rua 3", "postal_code": "00111-000"}, "birth_date": "1990-06-16", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Q/pTXlgfl7FysU2/vWmMG.ioIeD6B20QUybnfOuVaKkq1OOahtTkq"}	customers
4	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 4, "cpf": "676.916.836-04", "name": "Customer 4", "email": "customer4@mail.example", "phone": "+55 11 910029324", "address": {"city": "São Paulo", "state": "SP", "number": "4", "street": "Rua 4", "postal_code": "00148-000"}, "birth_date": "1978-11-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$L5d6rt4fHxREoGU29C8dkejmKvX4LpPN53K.8Ay1nwQ.gQ2WB5Ica"}	customers
5	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 5, "cpf": "595.645.545-05", "name": "Customer 5", "email": "customer5@mail.example", "phone": "+55 11 910036655", "address": {"city": "Recife", "state": "PE", "number": "5", "street": "Rua 5", "postal_code": "00185-000"}, "birth_date": "1994-05-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$VmBTSTT2AUHarciYpEhLFu1OTVz0nCkbtp/s0Ig1JGojP4Y/h07Qi"}	customers
6	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 6, "cpf": "514.374.254-06", "name": "Customer 6", "email": "customer6@mail.example", "phone": "+55 11 910043986", "address": {"city": "Curitiba", "state": "PR", "number": "6", "street": "Rua 6", "postal_code": "00222-000"}, "birth_date": "1967-08-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$IokdaIWG6br8u62AJchWWeBur1EBRWfFVv416BvDh0edQMIrxGWxa"}	customers
7	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 7, "cpf": "433.103.963-07", "name": "Customer 7", "email": "customer7@mail.example", "phone": "+55 11 910051317", "address": {"city": "Belém", "state": "PA", "number": "7", "street": "Rua 7", "postal_code": "00259-000"}, "birth_date": "1975-04-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$gLJVIMDQxakCGoyMBQ/m6u0kK5zSwTy2nHu9sZTfiz0b7cDj4r7u."}	customers
8	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 8, "cpf": "352.832.672-08", "name": "Customer 8", "email": "customer8@mail.example", "phone": "+55 11 910058648", "address": {"city": "São Paulo", "state": "SP", "number": "8", "street": "Rua 8", "postal_code": "00296-000"}, "birth_date": "1986-04-03", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$LVIXga05I.CZ5vq6O2n/oeHEgjQNf7o/q3D1d3tG22J5Av1adfnsi"}	customers
9	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 9, "cpf": "271.561.381-09", "name": "Customer 9", "email": "customer9@mail.example", "phone": "+55 11 910065979", "address": {"city": "Recife", "state": "PE", "number": "9", "street": "Rua 9", "postal_code": "00333-000"}, "birth_date": "1970-06-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$aT9cWkx4cd9m7J4./b9vOOsFBufm6zRRLqYWHb2klvbb.RrgNzwGS"}	customers
10	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 10, "cpf": "190.290.090-10", "name": "Customer 10", "email": "customer10@mail.example", "phone": "+55 11 910073310", "address": {"city": "Curitiba", "state": "PR", "number": "10", "street": "Rua 10", "postal_code": "00370-000"}, "birth_date": "1984-12-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$WWDpBXegYHHqHSnfi0.EdOpizSenS.kbHSi9gqYfmZSMYGNAGngIy"}	customers
11	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 11, "cpf": "109.019.799-11", "name": "Customer 11", "email": "customer11@mail.example", "phone": "+55 11 910080641", "address": {"city": "Belém", "state": "PA", "number": "11", "street": "Rua 11", "postal_code": "00407-000"}, "birth_date": "1977-11-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$GIT0I1hEDtEzyEbTaE5ahuOlgIp/dgAYe3SIHwWIarE7DyF9f.z9S"}	customers
12	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 12, "cpf": "028.748.508-12", "name": "Customer 12", "email": "customer12@mail.example", "phone": "+55 11 910087972", "address": {"city": "São Paulo", "state": "SP", "number": "12", "street": "Rua 12", "postal_code": "00444-000"}, "birth_date": "1963-12-30", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$ZWvllJESsz2gZ/vLngCvjeWgPPVDiwg.26bjgRXlEH.fjeKLNChD2"}	customers
13	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 13, "cpf": "947.477.217-13", "name": "Customer 13", "email": "customer13@mail.example", "phone": "+55 11 910095303", "address": {"city": "Recife", "state": "PE", "number": "13", "street": "Rua 13", "postal_code": "00481-000"}, "birth_date": "1976-01-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$IJSfhB02qnFty1Ssho6NIOWr2bLiy1a3UbzX139XwgeJjrpwDi92m"}	customers
14	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 14, "cpf": "866.206.926-14", "name": "Customer 14", "email": "customer14@mail.example", "phone": "+55 11 910102634", "address": {"city": "Curitiba", "state": "PR", "number": "14", "street": "Rua 14", "postal_code": "00518-000"}, "birth_date": "1992-10-25", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Xr74MpyrxhX59qJspgb8ou/3zLmjUMyprnudIH6Izwlt4mg1vV9Hu"}	customers
15	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 15, "cpf": "785.935.635-15", "name": "Customer 15", "email": "customer15@mail.example", "phone": "+55 11 910109965", "address": {"city": "Belém", "state": "PA", "number": "15", "street": "Rua 15", "postal_code": "00555-000"}, "birth_date": "1969-04-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$IMP6cgtcmz30W3Mhtmu4FeJgk.TIwdsITqM9ssnQWEyIMjXCDsq5."}	customers
16	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 16, "cpf": "704.664.344-16", "name": "Customer 16", "email": "customer16@mail.example", "phone": "+55 11 910117296", "address": {"city": "São Paulo", "state": "SP", "number": "16", "street": "Rua 16", "postal_code": "00592-000"}, "birth_date": "1974-07-24", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$0KiVZo9M.TdebzheOE/6GuGnz7iXdM6U2a4UnoL.dy9ZbWbDwJDQy"}	customers
17	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 17, "cpf": "623.393.053-17", "name": "Customer 17", "email": "customer17@mail.example", "phone": "+55 11 910124627", "address": {"city": "Recife", "state": "PE", "number": "17", "street": "Rua 17", "postal_code": "00629-000"}, "birth_date": "1989-07-31", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$bO/2M.qClJnR44FKPGq2oeHpZDGsoD6o7.HE8wAF6xEJ.j2njmOEK"}	customers
18	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 18, "cpf": "542.122.762-18", "name": "Customer 18", "email": "customer18@mail.example", "phone": "+55 11 910131958", "address": {"city": "Curitiba", "state": "PR", "number": "18", "street": "Rua 18", "postal_code": "00666-000"}, "birth_date": "1960-10-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$3IsiWW6WH6oNNXMVsi1pHuRMZD3FcNsJNm7.u8euhrkPfs0S6PWWW"}	customers
19	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 19, "cpf": "461.851.471-19", "name": "Customer 19", "email": "customer19@mail.example", "phone": "+55 11 910139289", "address": {"city": "Belém", "state": "PA", "number": "19", "street": "Rua 19", "postal_code": "00703-000"}, "birth_date": "1999-08-23", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$KGfg.FjwONn6RqEVW4rIwufTj1oEaT6ZDNUImwSsbTmxqAHD37S52"}	customers
20	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 20, "cpf": "380.580.180-20", "name": "Customer 20", "email": "customer20@mail.example", "phone": "+55 11 910146620", "address": {"city": "São Paulo", "state": "SP", "number": "20", "street": "Rua 20", "postal_code": "00740-000"}, "birth_date": "1999-04-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$mPxJbzVaoF2MsDvUrk.pceIuREkHLv9k5Ba0bDfczYLJCGsjXeTRO"}	customers
21	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 21, "cpf": "299.309.889-21", "name": "Customer 21", "email": "customer21@mail.example", "phone": "+55 11 910153951", "address": {"city": "Recife", "state": "PE", "number": "21", "street": "Rua 21", "postal_code": "00777-000"}, "birth_date": "1981-02-08", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$5T8WjUhag4ESOVA288624eCO35WwgUxOl2G5gIncWJ9cxetiWi.uG"}	customers
22	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 22, "cpf": "218.038.598-22", "name": "Customer 22", "email": "customer22@mail.example", "phone": "+55 11 910161282", "address": {"city": "Curitiba", "state": "PR", "number": "22", "street": "Rua 22", "postal_code": "00814-000"}, "birth_date": "1980-01-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$NjEf86WYZzVawH3b425hIeeRdK45rVY52Ty/eRInNVq2PnOLR48Ha"}	customers
23	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 23, "cpf": "137.767.307-23", "name": "Customer 23", "email": "customer23@mail.example", "phone": "+55 11 910168613", "address": {"city": "Belém", "state": "PA", "number": "23", "street": "Rua 23", "postal_code": "00851-000"}, "birth_date": "1978-12-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$BhPkXumAYOPGWtGup73or..X6N4CU1y5p7r5e3MFEgf837hlAxvxq"}	customers
24	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 24, "cpf": "056.496.016-24", "name": "Customer 24", "email": "customer24@mail.example", "phone": "+55 11 910175944", "address": {"city": "São Paulo", "state": "SP", "number": "24", "street": "Rua 24", "postal_code": "00888-000"}, "birth_date": "1972-10-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$YSGMgrQo6khS0UEfk5Nnu.4eoVhTBl/C1xb2ifOTYdbE9i/pvAezC"}	customers
25	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 25, "cpf": "975.225.725-25", "name": "Customer 25", "email": "customer25@mail.example", "phone": "+55 11 910183275", "address": {"city": "Recife", "state": "PE", "number": "25", "street": "Rua 25", "postal_code": "00925-000"}, "birth_date": "1979-08-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$UNr3FrlFLq46GrgYhJYJkeIafUIaJwyzkVDGBKN9bPJ7E.Xv6yG1C"}	customers
26	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 26, "cpf": "894.954.434-26", "name": "Customer 26", "email": "customer26@mail.example", "phone": "+55 11 910190606", "address": {"city": "Curitiba", "state": "PR", "number": "26", "street": "Rua 26", "postal_code": "00962-000"}, "birth_date": "1995-06-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$/MDd3r/0hga7hoYGO0TBvO8cxraOFUjrJfTdNMlqOnkIHUOgDwTu."}	customers
27	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 27, "cpf": "813.683.143-27", "name": "Customer 27", "email": "customer27@mail.example", "phone": "+55 11 910197937", "address": {"city": "Belém", "state": "PA", "number": "27", "street": "Rua 27", "postal_code": "00999-000"}, "birth_date": "1984-01-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$9eMO3F4UdKX0vfFXixBWKehuNb.4p2ayx92aWD885IsXXicSFnKZq"}	customers
28	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 28, "cpf": "732.412.852-28", "name": "Customer 28", "email": "customer28@mail.example", "phone": "+55 11 910205268", "address": {"city": "São Paulo", "state": "SP", "number": "28", "street": "Rua 28", "postal_code": "01036-000"}, "birth_date": "1978-06-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$skIhaxbIGW62aKkq/iMZTOCwK.lZxqoPxoAwglRPVnEPt.Iz2Hkty"}	customers
29	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 29, "cpf": "651.141.561-29", "name": "Customer 29", "email": "customer29@mail.example", "phone": "+55 11 910212599", "address": {"city": "Recife", "state": "PE", "number": "29", "street": "Rua 29", "postal_code": "01073-000"}, "birth_date": "1977-05-25", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$UMBnVR4Vtk8jlOQqhdHe.u0mef.hYlOzVZpU0irfUqZvKNv6ee/se"}	customers
30	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 30, "cpf": "570.870.270-30", "name": "Customer 30", "email": "customer30@mail.example", "phone": "+55 11 910219930", "address": {"city": "Curitiba", "state": "PR", "number": "30", "street": "Rua 30", "postal_code": "01110-000"}, "birth_date": "1972-04-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$xWII0wz5cl2PeDn2Kg8qMOk4XWOffgKwvUtoaWG2NvlVn615ZFRKu"}	customers
31	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 31, "cpf": "489.599.979-31", "name": "Customer 31", "email": "customer31@mail.example", "phone": "+55 11 910227261", "address": {"city": "Belém", "state": "PA", "number": "31", "street": "Rua 31", "postal_code": "01147-000"}, "birth_date": "1970-04-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$RL0SSfhBOJcZVU1v8n.MWetZyjbBq39HbyNcoUJj9QXyDzMB0uWim"}	customers
32	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 32, "cpf": "408.328.688-32", "name": "Customer 32", "email": "customer32@mail.example", "phone": "+55 11 910234592", "address": {"city": "São Paulo", "state": "SP", "number": "32", "street": "Rua 32", "postal_code": "01184-000"}, "birth_date": "1965-06-16", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$aD3LweebfQ5eFLpCQMTHPukVVsydeZK8RGrPx19RvgaJUVbml.8jK"}	customers
33	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 33, "cpf": "327.057.397-33", "name": "Customer 33", "email": "customer33@mail.example", "phone": "+55 11 910241923", "address": {"city": "Recife", "state": "PE", "number": "33", "street": "Rua 33", "postal_code": "01221-000"}, "birth_date": "1980-05-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$5pbeYPfc5FWkaepANyybwORHI3zIraTpkonDrBMdqMLmX1kEVTBRO"}	customers
34	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 34, "cpf": "246.786.106-34", "name": "Customer 34", "email": "customer34@mail.example", "phone": "+55 11 910249254", "address": {"city": "Curitiba", "state": "PR", "number": "34", "street": "Rua 34", "postal_code": "01258-000"}, "birth_date": "1968-09-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$s.PsTezUCCf.qSJ/PV1hOuqABCQ0WgKPpwGu51ujcGWOYDDMSYP2i"}	customers
35	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 35, "cpf": "165.515.815-35", "name": "Customer 35", "email": "customer35@mail.example", "phone": "+55 11 910256585", "address": {"city": "Belém", "state": "PA", "number": "35", "street": "Rua 35", "postal_code": "01295-000"}, "birth_date": "1996-08-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$5RKlaQHMadS8IEl6XjfCcO.o2k4nrMwcx8i2ZrdUsmniYmPLPNy.K"}	customers
36	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 36, "cpf": "084.244.524-36", "name": "Customer 36", "email": "customer36@mail.example", "phone": "+55 11 910263916", "address": {"city": "São Paulo", "state": "SP", "number": "36", "street": "Rua 36", "postal_code": "01332-000"}, "birth_date": "1998-08-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$xxV2aXV5EyZsFm398jfgMOTMn3K5Ac5iS4vnPglSslpVJjKpbzV3S"}	customers
37	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 37, "cpf": "003.973.233-37", "name": "Customer 37", "email": "customer37@mail.example", "phone": "+55 11 910271247", "address": {"city": "Recife", "state": "PE", "number": "37", "street": "Rua 37", "postal_code": "01369-000"}, "birth_date": "1976-04-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$OiwPSGxDo/ejM.AfH1zae.wXhfrUXE6hfaGQjyEy9d37ahYor5vPa"}	customers
38	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 38, "cpf": "922.702.942-38", "name": "Customer 38", "email": "customer38@mail.example", "phone": "+55 11 910278578", "address": {"city": "Curitiba", "state": "PR", "number": "38", "street": "Rua 38", "postal_code": "01406-000"}, "birth_date": "1982-07-03", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$N4N0yQd07vwQm4398BfWSONG5ket3zjwzKDqxHHOvo/U0j4DB1fE2"}	customers
39	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 39, "cpf": "841.431.651-39", "name": "Customer 39", "email": "customer39@mail.example", "phone": "+55 11 910285909", "address": {"city": "Belém", "state": "PA", "number": "39", "street": "Rua 39", "postal_code": "01443-000"}, "birth_date": "2000-10-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$vw1uP2pJxAKyf6zSwF.R0eWnc8k12MhZ/NMtqiRwv2Ig4hdHlPghi"}	customers
40	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 40, "cpf": "760.160.360-40", "name": "Customer 40", "email": "customer40@mail.example", "phone": "+55 11 910293240", "address": {"city": "São Paulo", "state": "SP", "number": "40", "street": "Rua 40", "postal_code": "01480-000"}, "birth_date": "1994-07-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$bdaeeH0csZwXBt2fqIpkN.7eH/k0e71yMpyBb3zRIoyx3FoolDPZO"}	customers
41	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 41, "cpf": "679.889.069-41", "name": "Customer 41", "email": "customer41@mail.example", "phone": "+55 11 910300571", "address": {"city": "Recife", "state": "PE", "number": "41", "street": "Rua 41", "postal_code": "01517-000"}, "birth_date": "1969-07-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$cYhbkAFAD1yEHu3suCgpl.C6DtIcm0EflFF7hul1HyC/V1JuWv.ae"}	customers
42	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 42, "cpf": "598.618.778-42", "name": "Customer 42", "email": "customer42@mail.example", "phone": "+55 11 910307902", "address": {"city": "Curitiba", "state": "PR", "number": "42", "street": "Rua 42", "postal_code": "01554-000"}, "birth_date": "1962-03-03", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$B5g2plUE90K8h9kwA3hxm.ln1N19Ix2NoDsOknSf6dSpJQsyS.dI2"}	customers
43	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 43, "cpf": "517.347.487-43", "name": "Customer 43", "email": "customer43@mail.example", "phone": "+55 11 910315233", "address": {"city": "Belém", "state": "PA", "number": "43", "street": "Rua 43", "postal_code": "01591-000"}, "birth_date": "2000-05-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$CtQ/Fyd7cUFTvvZJSaER2.yaMjuKM84wVbgQFuvwsaSElQcyGAyVu"}	customers
44	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 44, "cpf": "436.076.196-44", "name": "Customer 44", "email": "customer44@mail.example", "phone": "+55 11 910322564", "address": {"city": "São Paulo", "state": "SP", "number": "44", "street": "Rua 44", "postal_code": "01628-000"}, "birth_date": "1968-11-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$57Azr.ud.O.SMYlkj56yw.MuLTNfKpBVGT5TaMAfxA0HPWvCgZeaG"}	customers
45	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 45, "cpf": "355.805.905-45", "name": "Customer 45", "email": "customer45@mail.example", "phone": "+55 11 910329895", "address": {"city": "Recife", "state": "PE", "number": "45", "street": "Rua 45", "postal_code": "01665-000"}, "birth_date": "1978-10-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$r3pu8FEJ4AziPE80TQsOE.gC97VPapMdAOinxE9v8Rf1KqpUmtQ2e"}	customers
46	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 46, "cpf": "274.534.614-46", "name": "Customer 46", "email": "customer46@mail.example", "phone": "+55 11 910337226", "address": {"city": "Curitiba", "state": "PR", "number": "46", "street": "Rua 46", "postal_code": "01702-000"}, "birth_date": "1998-07-23", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$haoFLUdXUHKnllAaIUqtpu3LiszCyc3SBRZdoh3YRM4/lTB06S6Y."}	customers
47	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 47, "cpf": "193.263.323-47", "name": "Customer 47", "email": "customer47@mail.example", "phone": "+55 11 910344557", "address": {"city": "Belém", "state": "PA", "number": "47", "street": "Rua 47", "postal_code": "01739-000"}, "birth_date": "1962-10-26", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$mz8bHfM7.wNv.KXDspppC.tKZZdJX8XlMV1JYCRDbu2LxE0vl3kLu"}	customers
48	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 48, "cpf": "112.992.032-48", "name": "Customer 48", "email": "customer48@mail.example", "phone": "+55 11 910351888", "address": {"city": "São Paulo", "state": "SP", "number": "48", "street": "Rua 48", "postal_code": "01776-000"}, "birth_date": "1979-05-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$DJ9b10fxwhYuv1LMTLZMWu8Msm5Zcdg6bClCkj0li2Hz96O7UCqty"}	customers
49	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 49, "cpf": "031.721.741-49", "name": "Customer 49", "email": "customer49@mail.example", "phone": "+55 11 910359219", "address": {"city": "Recife", "state": "PE", "number": "49", "street": "Rua 49", "postal_code": "01813-000"}, "birth_date": "1968-02-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$4LkylBejL8jNp3uF6t6PUOXYtrYPNHmrkQJN9xxfnUL1OqVOb2RzG"}	customers
50	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 50, "cpf": "950.450.450-50", "name": "Customer 50", "email": "customer50@mail.example", "phone": "+55 11 910366550", "address": {"city": "Curitiba", "state": "PR", "number": "50", "street": "Rua 50", "postal_code": "01850-000"}, "birth_date": "1961-10-29", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$gXe.pgCGK/Lo7XGm0lDwsOdxr4caBlhB5QmTXx98RjMG1czTqq6pm"}	customers
51	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 51, "cpf": "869.179.159-51", "name": "Customer 51", "email": "customer51@mail.example", "phone": "+55 11 910373881", "address": {"city": "Belém", "state": "PA", "number": "51", "street": "Rua 51", "postal_code": "01887-000"}, "birth_date": "1966-09-30", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Pe55Q5oMdCwfypP11H0LH.JHvr8fYETfPvLtW6za6n3qc4Egtxf5e"}	customers
52	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 52, "cpf": "788.908.868-52", "name": "Customer 52", "email": "customer52@mail.example", "phone": "+55 11 910381212", "address": {"city": "São Paulo", "state": "SP", "number": "52", "street": "Rua 52", "postal_code": "01924-000"}, "birth_date": "1963-01-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$ycYg1Ffm8qSRjjR8SdARducyZ4YBZFFP5kuykDL3LsJCj6r/pQ6zK"}	customers
53	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 53, "cpf": "707.637.577-53", "name": "Customer 53", "email": "customer53@mail.example", "phone": "+55 11 910388543", "address": {"city": "Recife", "state": "PE", "number": "53", "street": "Rua 53", "postal_code": "01961-000"}, "birth_date": "1960-11-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$gJw4qQCpWhB9SE2qbD.sse8NQF9Qnkx17V4RWEWZLgqCYqEoB3CSq"}	customers
54	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 54, "cpf": "626.366.286-54", "name": "Customer 54", "email": "customer54@mail.example", "phone": "+55 11 910395874", "address": {"city": "Curitiba", "state": "PR", "number": "54", "street": "Rua 54", "postal_code": "01998-000"}, "birth_date": "1995-03-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$gMDa3cIYu9EVsKzPAN2RMO3NsUfepUIWajFy2ohrk90YUINwEXyiS"}	customers
55	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 55, "cpf": "545.095.995-55", "name": "Customer 55", "email": "customer55@mail.example", "phone": "+55 11 910403205", "address": {"city": "Belém", "state": "PA", "number": "55", "street": "Rua 55", "postal_code": "02035-000"}, "birth_date": "1968-03-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$6ALe3h0rbhstucXRBQV0petrOfOdQKM8ta1TbQOLabFukVWIwMQIu"}	customers
56	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 56, "cpf": "464.824.704-56", "name": "Customer 56", "email": "customer56@mail.example", "phone": "+55 11 910410536", "address": {"city": "São Paulo", "state": "SP", "number": "56", "street": "Rua 56", "postal_code": "02072-000"}, "birth_date": "1976-03-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$ADP3pZw57jdc2Hs/IBmxAOg4xzsWZEakQ3Bp3C2Leei12DI.z4Hb6"}	customers
57	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 57, "cpf": "383.553.413-57", "name": "Customer 57", "email": "customer57@mail.example", "phone": "+55 11 910417867", "address": {"city": "Recife", "state": "PE", "number": "57", "street": "Rua 57", "postal_code": "02109-000"}, "birth_date": "1967-04-17", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$p5H/nFTuYgXnUbadnnvAZe7nwOMXAuIuEKrLMsFSU36nEpQUuyDuK"}	customers
58	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 58, "cpf": "302.282.122-58", "name": "Customer 58", "email": "customer58@mail.example", "phone": "+55 11 910425198", "address": {"city": "Curitiba", "state": "PR", "number": "58", "street": "Rua 58", "postal_code": "02146-000"}, "birth_date": "1993-05-29", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$cNT9iRcphaESMKxMaryG.uPIFteyRKs1kEn.k2hcE5Mmy4IZDk732"}	customers
59	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 59, "cpf": "221.011.831-59", "name": "Customer 59", "email": "customer59@mail.example", "phone": "+55 11 910432529", "address": {"city": "Belém", "state": "PA", "number": "59", "street": "Rua 59", "postal_code": "02183-000"}, "birth_date": "1995-06-03", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$wdNS4oi/scdMZp0kdQz3Ye6kKLL77N2.3E64Wlhb8sYmfp3N4E2am"}	customers
60	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 60, "cpf": "140.740.540-60", "name": "Customer 60", "email": "customer60@mail.example", "phone": "+55 11 910439860", "address": {"city": "São Paulo", "state": "SP", "number": "60", "street": "Rua 60", "postal_code": "02220-000"}, "birth_date": "1981-01-29", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$CqKDUtiCIfEYEQt89TpkhuUnfBUZm/zSf4teAt3mVW78SDCFFpRfq"}	customers
61	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 61, "cpf": "059.469.249-61", "name": "Customer 61", "email": "customer61@mail.example", "phone": "+55 11 910447191", "address": {"city": "Recife", "state": "PE", "number": "61", "street": "Rua 61", "postal_code": "02257-000"}, "birth_date": "1965-07-08", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$mCmb2bfxD.1XdRhPppTc6OArm04KgAIJqDlZmIaV31.FKMfXQjJ6O"}	customers
62	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 62, "cpf": "978.198.958-62", "name": "Customer 62", "email": "customer62@mail.example", "phone": "+55 11 910454522", "address": {"city": "Curitiba", "state": "PR", "number": "62", "street": "Rua 62", "postal_code": "02294-000"}, "birth_date": "1971-08-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$3x3ufDSNWy6.Ok5gmhvVSuF.1c/UuGp3kZMS4HflVkGRvIcJ3ACp6"}	customers
63	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 63, "cpf": "897.927.667-63", "name": "Customer 63", "email": "customer63@mail.example", "phone": "+55 11 910461853", "address": {"city": "Belém", "state": "PA", "number": "63", "street": "Rua 63", "postal_code": "02331-000"}, "birth_date": "2000-11-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$V5IB0NPjmsd3zS4AISh2euHPi4lf1J1cFRuwgk4XB0ZcpJOyVcaSa"}	customers
64	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 64, "cpf": "816.656.376-64", "name": "Customer 64", "email": "customer64@mail.example", "phone": "+55 11 910469184", "address": {"city": "São Paulo", "state": "SP", "number": "64", "street": "Rua 64", "postal_code": "02368-000"}, "birth_date": "1987-04-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$cxBa5ZSgsTeiXWkCN96XBO/42qMk2fcfWHbYUJqYIgRuem9xpa9oe"}	customers
65	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 65, "cpf": "735.385.085-65", "name": "Customer 65", "email": "customer65@mail.example", "phone": "+55 11 910476515", "address": {"city": "Recife", "state": "PE", "number": "65", "street": "Rua 65", "postal_code": "02405-000"}, "birth_date": "1986-08-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$M3.zwXjYUBXzKfz.nfzBcefH8HUlcyJUS.r/jET/iVJwMmuhc8ybS"}	customers
66	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 66, "cpf": "654.114.794-66", "name": "Customer 66", "email": "customer66@mail.example", "phone": "+55 11 910483846", "address": {"city": "Curitiba", "state": "PR", "number": "66", "street": "Rua 66", "postal_code": "02442-000"}, "birth_date": "1992-06-10", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$D5nAfWhBMFbnO9JlWTLgCu6AgDzhhorgg8GvdpzlLvVWXAJpRaJoO"}	customers
67	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 67, "cpf": "573.843.503-67", "name": "Customer 67", "email": "customer67@mail.example", "phone": "+55 11 910491177", "address": {"city": "Belém", "state": "PA", "number": "67", "street": "Rua 67", "postal_code": "02479-000"}, "birth_date": "1968-05-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$1egs1fJ.n0YMGQCBN/A/quPW0RJNkO2fsQ4Q3/knnQ59VouUjvOa6"}	customers
68	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 68, "cpf": "492.572.212-68", "name": "Customer 68", "email": "customer68@mail.example", "phone": "+55 11 910498508", "address": {"city": "São Paulo", "state": "SP", "number": "68", "street": "Rua 68", "postal_code": "02516-000"}, "birth_date": "1989-04-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$nCtVrht3InOwuZPc6QRG3emBUZzspDfAogDLV2qiDEZeIDgmdmzty"}	customers
69	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 69, "cpf": "411.301.921-69", "name": "Customer 69", "email": "customer69@mail.example", "phone": "+55 11 910505839", "address": {"city": "Recife", "state": "PE", "number": "69", "street": "Rua 69", "postal_code": "02553-000"}, "birth_date": "1981-03-24", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$PFsyYgeuxUaNevcbGwXQwOtiRy0gy54El0dDeKKVYOcJAqtgP8dCq"}	customers
70	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 70, "cpf": "330.030.630-70", "name": "Customer 70", "email": "customer70@mail.example", "phone": "+55 11 910513170", "address": {"city": "Curitiba", "state": "PR", "number": "70", "street": "Rua 70", "postal_code": "02590-000"}, "birth_date": "1972-05-14", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$jJt6qMGOY5TcsxWMICqJ4ODJZJix/9e68X/lRLHazLz5VEVLtb1u2"}	customers
71	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 71, "cpf": "249.759.339-71", "name": "Customer 71", "email": "customer71@mail.example", "phone": "+55 11 910520501", "address": {"city": "Belém", "state": "PA", "number": "71", "street": "Rua 71", "postal_code": "02627-000"}, "birth_date": "1982-08-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$FAbUnaaql8Qqqs524Aw2UuKr3VJ2EGXTjx5AaK5Yz0FwK8NoeM.hm"}	customers
72	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 72, "cpf": "168.488.048-72", "name": "Customer 72", "email": "customer72@mail.example", "phone": "+55 11 910527832", "address": {"city": "São Paulo", "state": "SP", "number": "72", "street": "Rua 72", "postal_code": "02664-000"}, "birth_date": "1966-06-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$LGVrFoSzV81zSvOxRyqhZOQHK1C2YKT0JnvEf9yjiIw1ru9u3KPfO"}	customers
73	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 73, "cpf": "087.217.757-73", "name": "Customer 73", "email": "customer73@mail.example", "phone": "+55 11 910535163", "address": {"city": "Recife", "state": "PE", "number": "73", "street": "Rua 73", "postal_code": "02701-000"}, "birth_date": "1988-12-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Wgf1.2aB5.cXUpaMaVpukuC2vRvPW/RiME9SU81ksf2G2cM.bN.Fq"}	customers
74	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 74, "cpf": "006.946.466-74", "name": "Customer 74", "email": "customer74@mail.example", "phone": "+55 11 910542494", "address": {"city": "Curitiba", "state": "PR", "number": "74", "street": "Rua 74", "postal_code": "02738-000"}, "birth_date": "1980-06-12", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$B1nuypHBbMh1ajPbHsqk5.tCpt1tY1uLwPEb9sPinfqHny.yIgQy6"}	customers
75	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 75, "cpf": "925.675.175-75", "name": "Customer 75", "email": "customer75@mail.example", "phone": "+55 11 910549825", "address": {"city": "Belém", "state": "PA", "number": "75", "street": "Rua 75", "postal_code": "02775-000"}, "birth_date": "1978-08-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$cAqjPc6rK4sabJe99jhTFuGu1ggdfjC/csjzIXlJj53HQdeYLuxyu"}	customers
76	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 76, "cpf": "844.404.884-76", "name": "Customer 76", "email": "customer76@mail.example", "phone": "+55 11 910557156", "address": {"city": "São Paulo", "state": "SP", "number": "76", "street": "Rua 76", "postal_code": "02812-000"}, "birth_date": "1981-08-21", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$f4nXpwAN7Yn2IhCsupuJ7eUs0FfhWnsxfPM0xf.IvQhmtXqvyVYM."}	customers
77	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 77, "cpf": "763.133.593-77", "name": "Customer 77", "email": "customer77@mail.example", "phone": "+55 11 910564487", "address": {"city": "Recife", "state": "PE", "number": "77", "street": "Rua 77", "postal_code": "02849-000"}, "birth_date": "1987-09-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$XNXzP/NIWfHXctn1Z7AbmuMeNlLHRIADeurf0sLIILvCbRo.UMPXW"}	customers
78	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 78, "cpf": "682.862.302-78", "name": "Customer 78", "email": "customer78@mail.example", "phone": "+55 11 910571818", "address": {"city": "Curitiba", "state": "PR", "number": "78", "street": "Rua 78", "postal_code": "02886-000"}, "birth_date": "1983-04-30", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$6fmpRd/Fq42AP/ttUz0SIeQ/pelXtEqN.fMC3wsX/x6theK42/.ay"}	customers
79	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 79, "cpf": "601.591.011-79", "name": "Customer 79", "email": "customer79@mail.example", "phone": "+55 11 910579149", "address": {"city": "Belém", "state": "PA", "number": "79", "street": "Rua 79", "postal_code": "02923-000"}, "birth_date": "1975-10-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$id1Bb2WUozJvkWfRp9Vm7e5uRP9ppC/bWgsm.oFwKAJFJm6Sl7axC"}	customers
80	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 80, "cpf": "520.320.720-80", "name": "Customer 80", "email": "customer80@mail.example", "phone": "+55 11 910586480", "address": {"city": "São Paulo", "state": "SP", "number": "80", "street": "Rua 80", "postal_code": "02960-000"}, "birth_date": "1995-08-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$JIXtI8R7t42O1O5YbGNf3.bnJIXu3j3ZOIvtGikmhGWm2HmMt/MPy"}	customers
81	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 81, "cpf": "439.049.429-81", "name": "Customer 81", "email": "customer81@mail.example", "phone": "+55 11 910593811", "address": {"city": "Recife", "state": "PE", "number": "81", "street": "Rua 81", "postal_code": "02997-000"}, "birth_date": "1960-04-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$8csHOruuNTFDLlItysL8xe8fLoti8Io48zPF5jRgoNJpP5f4yIDMO"}	customers
82	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 82, "cpf": "358.778.138-82", "name": "Customer 82", "email": "customer82@mail.example", "phone": "+55 11 910601142", "address": {"city": "Curitiba", "state": "PR", "number": "82", "street": "Rua 82", "postal_code": "03034-000"}, "birth_date": "1977-09-23", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$NSzzyp2yUS1koHF/9UZSKOo8S0l5pxFRc8l96KOlkB/.6sORIKX8m"}	customers
83	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 83, "cpf": "277.507.847-83", "name": "Customer 83", "email": "customer83@mail.example", "phone": "+55 11 910608473", "address": {"city": "Belém", "state": "PA", "number": "83", "street": "Rua 83", "postal_code": "03071-000"}, "birth_date": "1970-10-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$l94EZpweOgdJJOHyCbEq/eU3wCaCjkjgQ1nPnJRY9ZpE4JfmKM.4S"}	customers
84	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 84, "cpf": "196.236.556-84", "name": "Customer 84", "email": "customer84@mail.example", "phone": "+55 11 910615804", "address": {"city": "São Paulo", "state": "SP", "number": "84", "street": "Rua 84", "postal_code": "03108-000"}, "birth_date": "1970-10-16", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$gfk3jTfpbdS/UOA.GatSWO.k9rbwywcpy9Tqbw7/jsCO55SrVd3OC"}	customers
85	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 85, "cpf": "115.965.265-85", "name": "Customer 85", "email": "customer85@mail.example", "phone": "+55 11 910623135", "address": {"city": "Recife", "state": "PE", "number": "85", "street": "Rua 85", "postal_code": "03145-000"}, "birth_date": "1987-08-14", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$6YQuAlGdDFgId55J.l47Y.OUpfyfIqblrWuqdXcwEeuUE3Xr2LFvm"}	customers
86	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 86, "cpf": "034.694.974-86", "name": "Customer 86", "email": "customer86@mail.example", "phone": "+55 11 910630466", "address": {"city": "Curitiba", "state": "PR", "number": "86", "street": "Rua 86", "postal_code": "03182-000"}, "birth_date": "1960-05-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$kNUldsTAIJ90zcG0yA/6LuOUqCFBg9/8xMiIHgoMQDfqkBgFaqySO"}	customers
87	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 87, "cpf": "953.423.683-87", "name": "Customer 87", "email": "customer87@mail.example", "phone": "+55 11 910637797", "address": {"city": "Belém", "state": "PA", "number": "87", "street": "Rua 87", "postal_code": "03219-000"}, "birth_date": "1985-02-02", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$WRAbQfY6TjGkzNOCO36OXOyF5SubgX5O2/QZG9nsCNasIaxL0cVHC"}	customers
88	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 88, "cpf": "872.152.392-88", "name": "Customer 88", "email": "customer88@mail.example", "phone": "+55 11 910645128", "address": {"city": "São Paulo", "state": "SP", "number": "88", "street": "Rua 88", "postal_code": "03256-000"}, "birth_date": "1977-07-31", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$XBpsgnFWuLauwgYUPt8JrOI0fuSv.1NwHLn9Fr6l4odBBMefty4SG"}	customers
89	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 89, "cpf": "791.881.101-89", "name": "Customer 89", "email": "customer89@mail.example", "phone": "+55 11 910652459", "address": {"city": "Recife", "state": "PE", "number": "89", "street": "Rua 89", "postal_code": "03293-000"}, "birth_date": "1981-02-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Z7j8Ym9taIQ4nvFHwtOLxOAccr6o8qXzdHcaFY2jApocgACJFqrk2"}	customers
90	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 90, "cpf": "710.610.810-90", "name": "Customer 90", "email": "customer90@mail.example", "phone": "+55 11 910659790", "address": {"city": "Curitiba", "state": "PR", "number": "90", "street": "Rua 90", "postal_code": "03330-000"}, "birth_date": "1988-10-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$EMTNsHhqWi/tQZoM5HWjyeMAVdXqOa1yLLcGBzxMj749Gv/9GA17."}	customers
91	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 91, "cpf": "629.339.519-91", "name": "Customer 91", "email": "customer91@mail.example", "phone": "+55 11 910667121", "address": {"city": "Belém", "state": "PA", "number": "91", "street": "Rua 91", "postal_code": "03367-000"}, "birth_date": "1985-02-17", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$fTSITSNGltjNtS4vh7lMAelSps2NpRFCbnqvOEvxYDuPhazdvYjoi"}	customers
92	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 92, "cpf": "548.068.228-92", "name": "Customer 92", "email": "customer92@mail.example", "phone": "+55 11 910674452", "address": {"city": "São Paulo", "state": "SP", "number": "92", "street": "Rua 92", "postal_code": "03404-000"}, "birth_date": "1973-10-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$FaSwQ6Z/lAO.xur9e3zSteyVVd6ZZEeunWfe6RsuJMRIpCQ6uOe6K"}	customers
93	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 93, "cpf": "467.797.937-93", "name": "Customer 93", "email": "customer93@mail.example", "phone": "+55 11 910681783", "address": {"city": "Recife", "state": "PE", "number": "93", "street": "Rua 93", "postal_code": "03441-000"}, "birth_date": "1989-08-19", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$EsxRXphBr7dPcnrpCA0x5eDHIjXHmT9mgjagbi5abrVsjuH93WiTe"}	customers
94	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 94, "cpf": "386.526.646-94", "name": "Customer 94", "email": "customer94@mail.example", "phone": "+55 11 910689114", "address": {"city": "Curitiba", "state": "PR", "number": "94", "street": "Rua 94", "postal_code": "03478-000"}, "birth_date": "1960-05-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$J5eE9Eqx8RRtgCJd8DLTxO2Bd3mBccXW33t6nomZ6Wd5zkuxhaeoa"}	customers
95	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 95, "cpf": "305.255.355-95", "name": "Customer 95", "email": "customer95@mail.example", "phone": "+55 11 910696445", "address": {"city": "Belém", "state": "PA", "number": "95", "street": "Rua 95", "postal_code": "03515-000"}, "birth_date": "1981-07-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$T2mrUEq1u3ojLo.BlTS2IujJuajTElCa76iqfDY84u8soG61MqY1W"}	customers
96	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 96, "cpf": "224.984.064-96", "name": "Customer 96", "email": "customer96@mail.example", "phone": "+55 11 910703776", "address": {"city": "São Paulo", "state": "SP", "number": "96", "street": "Rua 96", "postal_code": "03552-000"}, "birth_date": "1998-10-25", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$aatft2umuGgdB6c2weXLtuwiAAI1280bkNdSju5qJi2BAk.W7JmEy"}	customers
97	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 97, "cpf": "143.713.773-97", "name": "Customer 97", "email": "customer97@mail.example", "phone": "+55 11 910711107", "address": {"city": "Recife", "state": "PE", "number": "97", "street": "Rua 97", "postal_code": "03589-000"}, "birth_date": "1969-07-24", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$tlIrT/MGEqROFqw7fHn16e5DYwXOVAU7SZ2QFKn0Rwh47kJ5uPdQm"}	customers
98	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 98, "cpf": "062.442.482-98", "name": "Customer 98", "email": "customer98@mail.example", "phone": "+55 11 910718438", "address": {"city": "Curitiba", "state": "PR", "number": "98", "street": "Rua 98", "postal_code": "03626-000"}, "birth_date": "1998-09-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$ZvEUhrTmEdB4imL9E7g4Eub474XT18aH.fehoIZKZ9YDCkWW6f1V6"}	customers
99	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 99, "cpf": "981.171.191-99", "name": "Customer 99", "email": "customer99@mail.example", "phone": "+55 11 910725769", "address": {"city": "Belém", "state": "PA", "number": "99", "street": "Rua 99", "postal_code": "03663-000"}, "birth_date": "1972-03-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$38IHqITQmsa7rJaUE/3.fuoKY2AmBXqLfLlT499mTVIgH0A2qcyMK"}	customers
100	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 100, "cpf": "900.900.900-00", "name": "Customer 100", "email": "customer100@mail.example", "phone": "+55 11 910733100", "address": {"city": "São Paulo", "state": "SP", "number": "100", "street": "Rua 100", "postal_code": "03700-000"}, "birth_date": "1998-04-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Xpx3SX7PLgdlgGK3C.HkTetRPVh6b455JEeS.V9Hyto9HQGHTOxH."}	customers
101	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 101, "cpf": "819.629.609-01", "name": "Customer 101", "email": "customer101@mail.example", "phone": "+55 11 910740431", "address": {"city": "Recife", "state": "PE", "number": "101", "street": "Rua 101", "postal_code": "03737-000"}, "birth_date": "1976-12-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$P.8uleuFoWLk6PIajm3blu0u0FqgauQ.D3vLF8L1QNEkkbf0jrktK"}	customers
102	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 102, "cpf": "738.358.318-02", "name": "Customer 102", "email": "customer102@mail.example", "phone": "+55 11 910747762", "address": {"city": "Curitiba", "state": "PR", "number": "102", "street": "Rua 102", "postal_code": "03774-000"}, "birth_date": "1998-08-03", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$33cWb7Ks48nXzl0BX51zGuIFMmMFINf5awpvRLVGICy1GzYrdCDzm"}	customers
103	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 103, "cpf": "657.087.027-03", "name": "Customer 103", "email": "customer103@mail.example", "phone": "+55 11 910755093", "address": {"city": "Belém", "state": "PA", "number": "103", "street": "Rua 103", "postal_code": "03811-000"}, "birth_date": "1979-05-16", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$2IsxAWWmgubCgLb6o3apeO9yUD.DXv3ytmBfpi0wPnArWiYq7cYxO"}	customers
104	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 104, "cpf": "576.816.736-04", "name": "Customer 104", "email": "customer104@mail.example", "phone": "+55 11 910762424", "address": {"city": "São Paulo", "state": "SP", "number": "104", "street": "Rua 104", "postal_code": "03848-000"}, "birth_date": "1994-10-10", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$6DR/G38u3gQ5N6jCCwAM3..O1UWI5ArG/w3RsyjxPmVP0iexD79Gu"}	customers
105	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 105, "cpf": "495.545.445-05", "name": "Customer 105", "email": "customer105@mail.example", "phone": "+55 11 910769755", "address": {"city": "Recife", "state": "PE", "number": "105", "street": "Rua 105", "postal_code": "03885-000"}, "birth_date": "1968-07-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$7E3n13F/1oqydFChgFjUHuAwKsVWQznRDQHI6kToasnUXgZE76W1a"}	customers
106	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 106, "cpf": "414.274.154-06", "name": "Customer 106", "email": "customer106@mail.example", "phone": "+55 11 910777086", "address": {"city": "Curitiba", "state": "PR", "number": "106", "street": "Rua 106", "postal_code": "03922-000"}, "birth_date": "1973-09-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$xIcGYd/8B5KdP.vO5zL9au.VpzpjyQJfIreDNxNj82cuUKfD2K3Um"}	customers
107	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 107, "cpf": "333.003.863-07", "name": "Customer 107", "email": "customer107@mail.example", "phone": "+55 11 910784417", "address": {"city": "Belém", "state": "PA", "number": "107", "street": "Rua 107", "postal_code": "03959-000"}, "birth_date": "1977-10-10", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$s5Qfac15MqDvEsyOUO1iXuMmw5y2O3cQXiQ1uWsPI.2hu8gt1i8gO"}	customers
108	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 108, "cpf": "252.732.572-08", "name": "Customer 108", "email": "customer108@mail.example", "phone": "+55 11 910791748", "address": {"city": "São Paulo", "state": "SP", "number": "108", "street": "Rua 108", "postal_code": "03996-000"}, "birth_date": "1986-07-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$MQZ/K7.GpnGpn3xE2lT6yePiBTTQ6GitWsxtIlQcEA6893Mq4YKni"}	customers
109	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 109, "cpf": "171.461.281-09", "name": "Customer 109", "email": "customer109@mail.example", "phone": "+55 11 910799079", "address": {"city": "Recife", "state": "PE", "number": "109", "street": "Rua 109", "postal_code": "04033-000"}, "birth_date": "1994-03-10", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$DwB6f/a2oKuy.JCL6WU6eu.Ua7DidxK/yywSwH3khAU5.G3F9Bu1e"}	customers
110	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 110, "cpf": "090.190.990-10", "name": "Customer 110", "email": "customer110@mail.example", "phone": "+55 11 910806410", "address": {"city": "Curitiba", "state": "PR", "number": "110", "street": "Rua 110", "postal_code": "04070-000"}, "birth_date": "1971-06-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$PLOTb8OOIdwKmIi9NhQOqeecyE.bdqMjD4WJw57wTZCXgFCdtEfgW"}	customers
111	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 111, "cpf": "009.919.699-11", "name": "Customer 111", "email": "customer111@mail.example", "phone": "+55 11 910813741", "address": {"city": "Belém", "state": "PA", "number": "111", "street": "Rua 111", "postal_code": "04107-000"}, "birth_date": "1973-05-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$jO0QvQ9uxKnmrbd8GXc6/.SsNW0/MqJRxk3C/./Gy3I5rK6Qd1IjW"}	customers
112	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 112, "cpf": "928.648.408-12", "name": "Customer 112", "email": "customer112@mail.example", "phone": "+55 11 910821072", "address": {"city": "São Paulo", "state": "SP", "number": "112", "street": "Rua 112", "postal_code": "04144-000"}, "birth_date": "1981-01-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$KVoi7fUxdyqlciGeOTCTduXjg/M/cLJlKxhKMhttYNnfHTUhaEwYq"}	customers
113	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 113, "cpf": "847.377.117-13", "name": "Customer 113", "email": "customer113@mail.example", "phone": "+55 11 910828403", "address": {"city": "Recife", "state": "PE", "number": "113", "street": "Rua 113", "postal_code": "04181-000"}, "birth_date": "1999-01-17", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$xbRA0ul.p6csjDgvF4eReuLDAna6rpyLab/Cx6GWpd9Q8bpcRqoS2"}	customers
114	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 114, "cpf": "766.106.826-14", "name": "Customer 114", "email": "customer114@mail.example", "phone": "+55 11 910835734", "address": {"city": "Curitiba", "state": "PR", "number": "114", "street": "Rua 114", "postal_code": "04218-000"}, "birth_date": "1984-08-16", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$K2bLEDyjXoaCw1gLIR.lHOrxuT07Fyk2Q7eWTqCuYQdMnjh4.2b0C"}	customers
115	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 115, "cpf": "685.835.535-15", "name": "Customer 115", "email": "customer115@mail.example", "phone": "+55 11 910843065", "address": {"city": "Belém", "state": "PA", "number": "115", "street": "Rua 115", "postal_code": "04255-000"}, "birth_date": "1999-11-08", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$pk/phk5PFF.4yCIgCV5alOULyJP6yKC2qSsPh8H.CPCeZbMrEtMSi"}	customers
116	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 116, "cpf": "604.564.244-16", "name": "Customer 116", "email": "customer116@mail.example", "phone": "+55 11 910850396", "address": {"city": "São Paulo", "state": "SP", "number": "116", "street": "Rua 116", "postal_code": "04292-000"}, "birth_date": "1964-07-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$CxuQe4jWjZXZkQ0WMNQQ8OQr8gjJG3mDWBEhk/Lwm7qE44CnHINKC"}	customers
117	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 117, "cpf": "523.293.953-17", "name": "Customer 117", "email": "customer117@mail.example", "phone": "+55 11 910857727", "address": {"city": "Recife", "state": "PE", "number": "117", "street": "Rua 117", "postal_code": "04329-000"}, "birth_date": "1981-01-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$tCGbbgNKoPDQ7GYReiWRL.ddKi/yUktsxUNU29tfdEZ.cp4j8udMS"}	customers
118	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 118, "cpf": "442.022.662-18", "name": "Customer 118", "email": "customer118@mail.example", "phone": "+55 11 910865058", "address": {"city": "Curitiba", "state": "PR", "number": "118", "street": "Rua 118", "postal_code": "04366-000"}, "birth_date": "1988-03-17", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$tuVbtUsH8dqDl6jQTsXPbOyDkfNOgeWMVOvJ8PHULHlHPrdtxd4iO"}	customers
119	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 119, "cpf": "361.751.371-19", "name": "Customer 119", "email": "customer119@mail.example", "phone": "+55 11 910872389", "address": {"city": "Belém", "state": "PA", "number": "119", "street": "Rua 119", "postal_code": "04403-000"}, "birth_date": "1981-01-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$aI4HUUtn/N9yvFGostAMX.IL.11b5qxi7KDl8eC1LVEm7AispZwlW"}	customers
120	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 120, "cpf": "280.480.080-20", "name": "Customer 120", "email": "customer120@mail.example", "phone": "+55 11 910879720", "address": {"city": "São Paulo", "state": "SP", "number": "120", "street": "Rua 120", "postal_code": "04440-000"}, "birth_date": "1975-12-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Xo5xbQvJciqgX6WHHJ9uYuyPmCm73wRVNONWk7bi4.XkHuSPorBlq"}	customers
121	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 121, "cpf": "199.209.789-21", "name": "Customer 121", "email": "customer121@mail.example", "phone": "+55 11 910887051", "address": {"city": "Recife", "state": "PE", "number": "121", "street": "Rua 121", "postal_code": "04477-000"}, "birth_date": "1987-03-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$VYWdNVsfgJtV5i0oPE6XD.U1kBgykPcy6t2HZW1JgKRcjfsEgGS7G"}	customers
122	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 122, "cpf": "118.938.498-22", "name": "Customer 122", "email": "customer122@mail.example", "phone": "+55 11 910894382", "address": {"city": "Curitiba", "state": "PR", "number": "122", "street": "Rua 122", "postal_code": "04514-000"}, "birth_date": "1978-02-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$WfLZ9Y/ZVqZZ5gxsZa.sQuE0M.K1/CDy9HKNX/L3nNBNjiRHr/RNG"}	customers
123	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 123, "cpf": "037.667.207-23", "name": "Customer 123", "email": "customer123@mail.example", "phone": "+55 11 910901713", "address": {"city": "Belém", "state": "PA", "number": "123", "street": "Rua 123", "postal_code": "04551-000"}, "birth_date": "1966-04-12", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$5YBvOHr5ZghumXdOaEN.pen0PYkAwPOF0M8uIKTHW/P13rr9DOstG"}	customers
124	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 124, "cpf": "956.396.916-24", "name": "Customer 124", "email": "customer124@mail.example", "phone": "+55 11 910909044", "address": {"city": "São Paulo", "state": "SP", "number": "124", "street": "Rua 124", "postal_code": "04588-000"}, "birth_date": "1992-11-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$LQF.8Tv1J.79SGJmCpM74e3evRfqr13DzAuXEYcIB5tAUg1wDsise"}	customers
125	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 125, "cpf": "875.125.625-25", "name": "Customer 125", "email": "customer125@mail.example", "phone": "+55 11 910916375", "address": {"city": "Recife", "state": "PE", "number": "125", "street": "Rua 125", "postal_code": "04625-000"}, "birth_date": "1990-09-30", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$7g9JYBBHsfTfSkPqcQnXOOvc4EuXwalPuxm0o75iXxHGjZN/IsZ1O"}	customers
126	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 126, "cpf": "794.854.334-26", "name": "Customer 126", "email": "customer126@mail.example", "phone": "+55 11 910923706", "address": {"city": "Curitiba", "state": "PR", "number": "126", "street": "Rua 126", "postal_code": "04662-000"}, "birth_date": "1975-12-26", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$4E3VIdzxm8THVj6qCuuUS.9OexHn9xUtLEODYdb4em1PJ1g4WRMGG"}	customers
127	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 127, "cpf": "713.583.043-27", "name": "Customer 127", "email": "customer127@mail.example", "phone": "+55 11 910931037", "address": {"city": "Belém", "state": "PA", "number": "127", "street": "Rua 127", "postal_code": "04699-000"}, "birth_date": "1971-05-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$cfkmgUjbzYZLq7sMvo2vke91AXy0C01Etrt9CpDodeKD1W8fccoyS"}	customers
128	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 128, "cpf": "632.312.752-28", "name": "Customer 128", "email": "customer128@mail.example", "phone": "+55 11 910938368", "address": {"city": "São Paulo", "state": "SP", "number": "128", "street": "Rua 128", "postal_code": "04736-000"}, "birth_date": "1986-11-03", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$hZaUNOZYX/1LKhNDo8IGk.AlJOOfZ93zVG6.amu8865ozx3hNWTF."}	customers
129	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 129, "cpf": "551.041.461-29", "name": "Customer 129", "email": "customer129@mail.example", "phone": "+55 11 910945699", "address": {"city": "Recife", "state": "PE", "number": "129", "street": "Rua 129", "postal_code": "04773-000"}, "birth_date": "2000-11-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$2nLr0dVuMxpGOVUzy9pai.fWpdVWcfRuPvVFVFMVrkBHI47VwPhFW"}	customers
130	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 130, "cpf": "470.770.170-30", "name": "Customer 130", "email": "customer130@mail.example", "phone": "+55 11 910953030", "address": {"city": "Curitiba", "state": "PR", "number": "130", "street": "Rua 130", "postal_code": "04810-000"}, "birth_date": "1993-05-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$HGZiPg60NkbO6Xegy9nXTOPN.0r0HTbpZe1g57F6.0oyo8DuupWTK"}	customers
131	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 131, "cpf": "389.499.879-31", "name": "Customer 131", "email": "customer131@mail.example", "phone": "+55 11 910960361", "address": {"city": "Belém", "state": "PA", "number": "131", "street": "Rua 131", "postal_code": "04847-000"}, "birth_date": "1995-01-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$rJxlJPGOILiCGuNRmqyVOuPZr/n4vhomvknrNblzcc7sBkw6Y5jOO"}	customers
132	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 132, "cpf": "308.228.588-32", "name": "Customer 132", "email": "customer132@mail.example", "phone": "+55 11 910967692", "address": {"city": "São Paulo", "state": "SP", "number": "132", "street": "Rua 132", "postal_code": "04884-000"}, "birth_date": "1999-10-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$JVJBf5xpc5OwaCo89RaGZ.dFm.wP6yjE4rNZmMzv57sbITGYgS5gK"}	customers
133	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 133, "cpf": "227.957.297-33", "name": "Customer 133", "email": "customer133@mail.example", "phone": "+55 11 910975023", "address": {"city": "Recife", "state": "PE", "number": "133", "street": "Rua 133", "postal_code": "04921-000"}, "birth_date": "1975-11-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$e61w9KloAyIugifwKOlhXuAVZMxwbfokClC45SWYn5ZlGBdg7FEoS"}	customers
134	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 134, "cpf": "146.686.006-34", "name": "Customer 134", "email": "customer134@mail.example", "phone": "+55 11 910982354", "address": {"city": "Curitiba", "state": "PR", "number": "134", "street": "Rua 134", "postal_code": "04958-000"}, "birth_date": "1988-08-12", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$CFByGd1WeCD2fucWsYruEub0OiOfeWG82TKjtmOCjFDZJ4etm8cK2"}	customers
135	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 135, "cpf": "065.415.715-35", "name": "Customer 135", "email": "customer135@mail.example", "phone": "+55 11 910989685", "address": {"city": "Belém", "state": "PA", "number": "135", "street": "Rua 135", "postal_code": "04995-000"}, "birth_date": "1995-02-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$bN/z/3OH7MdlHnBF/uxay.LA37pX3/rbmXNKeqFPrrovSq7ZPuqDi"}	customers
136	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 136, "cpf": "984.144.424-36", "name": "Customer 136", "email": "customer136@mail.example", "phone": "+55 11 910997016", "address": {"city": "São Paulo", "state": "SP", "number": "136", "street": "Rua 136", "postal_code": "05032-000"}, "birth_date": "1982-06-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$GRuMNlwXgw0kXWPOamHOb.LlFfaTr1JyY.Kdy82s442XVHJkMM.QW"}	customers
137	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 137, "cpf": "903.873.133-37", "name": "Customer 137", "email": "customer137@mail.example", "phone": "+55 11 911004347", "address": {"city": "Recife", "state": "PE", "number": "137", "street": "Rua 137", "postal_code": "05069-000"}, "birth_date": "1996-09-12", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$oMrqpwmGzZ5HbNgWWA7DteIaCCy/.Bqz4eolbfvuKtq3Uzc0QCGGu"}	customers
138	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 138, "cpf": "822.602.842-38", "name": "Customer 138", "email": "customer138@mail.example", "phone": "+55 11 911011678", "address": {"city": "Curitiba", "state": "PR", "number": "138", "street": "Rua 138", "postal_code": "05106-000"}, "birth_date": "1963-04-12", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$T35xJWui/Pp/qVMKB8/FR.Mux1sIK77K2tspYHQZQF6fL6/9hDgp6"}	customers
139	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 139, "cpf": "741.331.551-39", "name": "Customer 139", "email": "customer139@mail.example", "phone": "+55 11 911019009", "address": {"city": "Belém", "state": "PA", "number": "139", "street": "Rua 139", "postal_code": "05143-000"}, "birth_date": "1999-08-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$ZWt/H5phZth48/0hNWUJDuHDOOBhpsY.fvPLhT8amsgQJrWQoRB/G"}	customers
140	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 140, "cpf": "660.060.260-40", "name": "Customer 140", "email": "customer140@mail.example", "phone": "+55 11 911026340", "address": {"city": "São Paulo", "state": "SP", "number": "140", "street": "Rua 140", "postal_code": "05180-000"}, "birth_date": "1992-04-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$PcQ8LZngzjOjvUWJyr/SuOXfRAqmIEVBcdRM76I2ZjFlYqckR.ZLy"}	customers
141	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 141, "cpf": "579.789.969-41", "name": "Customer 141", "email": "customer141@mail.example", "phone": "+55 11 911033671", "address": {"city": "Recife", "state": "PE", "number": "141", "street": "Rua 141", "postal_code": "05217-000"}, "birth_date": "1960-04-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$EPxCSLCX301DTSnLeDvlMekzUnyi76j.mfLSWJyQohHZmL9G1JSBK"}	customers
142	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 142, "cpf": "498.518.678-42", "name": "Customer 142", "email": "customer142@mail.example", "phone": "+55 11 911041002", "address": {"city": "Curitiba", "state": "PR", "number": "142", "street": "Rua 142", "postal_code": "05254-000"}, "birth_date": "1975-11-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$1KTj1lfzfGyRg28mDWUjW.QZpv.1jbnHU4X/Kh8Sbiguiaw6/GIdy"}	customers
143	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 143, "cpf": "417.247.387-43", "name": "Customer 143", "email": "customer143@mail.example", "phone": "+55 11 911048333", "address": {"city": "Belém", "state": "PA", "number": "143", "street": "Rua 143", "postal_code": "05291-000"}, "birth_date": "1974-03-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$HIB.ivTLOwIKdNnB72KHEuRX7g4O70mRMyhBNJeRGmbAjhXs0wzGK"}	customers
144	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 144, "cpf": "336.976.096-44", "name": "Customer 144", "email": "customer144@mail.example", "phone": "+55 11 911055664", "address": {"city": "São Paulo", "state": "SP", "number": "144", "street": "Rua 144", "postal_code": "05328-000"}, "birth_date": "1992-03-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$dkiq2zijeryRgC4L1tldGeYfdHqnFu8nYvlXJLAfEqZK1TFhjC8Cm"}	customers
145	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 145, "cpf": "255.705.805-45", "name": "Customer 145", "email": "customer145@mail.example", "phone": "+55 11 911062995", "address": {"city": "Recife", "state": "PE", "number": "145", "street": "Rua 145", "postal_code": "05365-000"}, "birth_date": "1966-04-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$LO2i9XcS.w5Y1LfQAAzLMu4Rixx/5.OMpTJ/bE6YJAc1bRiv/PGK."}	customers
146	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 146, "cpf": "174.434.514-46", "name": "Customer 146", "email": "customer146@mail.example", "phone": "+55 11 911070326", "address": {"city": "Curitiba", "state": "PR", "number": "146", "street": "Rua 146", "postal_code": "05402-000"}, "birth_date": "1989-01-29", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$41Ljn4c7taKDp4m2iM7VnuF31ratHfxalg7DYfeWi9jAzasMlbrmu"}	customers
147	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 147, "cpf": "093.163.223-47", "name": "Customer 147", "email": "customer147@mail.example", "phone": "+55 11 911077657", "address": {"city": "Belém", "state": "PA", "number": "147", "street": "Rua 147", "postal_code": "05439-000"}, "birth_date": "1983-01-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$vO6Lrzf/n73Mn0oQ5LoVOOwHjQRVPZCIfkGmndtyQzum3aiVnvIdG"}	customers
148	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 148, "cpf": "012.892.932-48", "name": "Customer 148", "email": "customer148@mail.example", "phone": "+55 11 911084988", "address": {"city": "São Paulo", "state": "SP", "number": "148", "street": "Rua 148", "postal_code": "05476-000"}, "birth_date": "1963-07-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$.kMCLDsx.qVpMiH08pLO2el2c58irr3YjpU3t.E4ZeZwXQFhQnX.y"}	customers
149	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 149, "cpf": "931.621.641-49", "name": "Customer 149", "email": "customer149@mail.example", "phone": "+55 11 911092319", "address": {"city": "Recife", "state": "PE", "number": "149", "street": "Rua 149", "postal_code": "05513-000"}, "birth_date": "1995-07-24", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$4LcxJHWi/Nkq2Kys.x6yoeL9ip9TqaGrT89oX.GtU51Ub6vzT2jp."}	customers
150	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 150, "cpf": "850.350.350-50", "name": "Customer 150", "email": "customer150@mail.example", "phone": "+55 11 911099650", "address": {"city": "Curitiba", "state": "PR", "number": "150", "street": "Rua 150", "postal_code": "05550-000"}, "birth_date": "1978-08-26", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$cQYyIA9o7Cv7hkGczSmkneWWjcvOhc6vMsyNK4bIgEvYxkO/xtfA."}	customers
151	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 151, "cpf": "769.079.059-51", "name": "Customer 151", "email": "customer151@mail.example", "phone": "+55 11 911106981", "address": {"city": "Belém", "state": "PA", "number": "151", "street": "Rua 151", "postal_code": "05587-000"}, "birth_date": "1961-03-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$W0zwUwZ4cICadocBUYMb7eEaLQi9sF/vl9.PYI95Yg1kNVxEJmIOC"}	customers
152	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 152, "cpf": "688.808.768-52", "name": "Customer 152", "email": "customer152@mail.example", "phone": "+55 11 911114312", "address": {"city": "São Paulo", "state": "SP", "number": "152", "street": "Rua 152", "postal_code": "05624-000"}, "birth_date": "1983-07-23", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$nPBMY.TY9VnVw5XBQTssnehIABaf7YCxNd9sL1bLhGdaSQzAjj5mq"}	customers
153	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 153, "cpf": "607.537.477-53", "name": "Customer 153", "email": "customer153@mail.example", "phone": "+55 11 911121643", "address": {"city": "Recife", "state": "PE", "number": "153", "street": "Rua 153", "postal_code": "05661-000"}, "birth_date": "1994-04-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$DkYeCV05Xx0HVpQWzphb3.x/c9bAhRYgoL5BhS.M6N63beCvQutpG"}	customers
154	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 154, "cpf": "526.266.186-54", "name": "Customer 154", "email": "customer154@mail.example", "phone": "+55 11 911128974", "address": {"city": "Curitiba", "state": "PR", "number": "154", "street": "Rua 154", "postal_code": "05698-000"}, "birth_date": "1966-06-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$WKFvRio1WMezNVup2ps.S.L/r64KrdeDGyNVUyD.5ytSVgU.yNTs2"}	customers
155	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 155, "cpf": "445.995.895-55", "name": "Customer 155", "email": "customer155@mail.example", "phone": "+55 11 911136305", "address": {"city": "Belém", "state": "PA", "number": "155", "street": "Rua 155", "postal_code": "05735-000"}, "birth_date": "1967-03-31", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$rE6d7ZiKrqQZcLT8XD0nMuqFEDmevw9iQZSaojI66RKObN0c6C.Qq"}	customers
156	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 156, "cpf": "364.724.604-56", "name": "Customer 156", "email": "customer156@mail.example", "phone": "+55 11 911143636", "address": {"city": "São Paulo", "state": "SP", "number": "156", "street": "Rua 156", "postal_code": "05772-000"}, "birth_date": "1991-12-08", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$.K4XRPQO4L8sTRCIm2/Mn.bZ.E7hCBoP.ZsFzY9GFGNp1qYfmxybG"}	customers
157	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 157, "cpf": "283.453.313-57", "name": "Customer 157", "email": "customer157@mail.example", "phone": "+55 11 911150967", "address": {"city": "Recife", "state": "PE", "number": "157", "street": "Rua 157", "postal_code": "05809-000"}, "birth_date": "1980-08-25", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Scs3NAH90hK1m5AKowOF5ulVrM9CN1qB1xiP3oTKF5onRVS.gDeKG"}	customers
158	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 158, "cpf": "202.182.022-58", "name": "Customer 158", "email": "customer158@mail.example", "phone": "+55 11 911158298", "address": {"city": "Curitiba", "state": "PR", "number": "158", "street": "Rua 158", "postal_code": "05846-000"}, "birth_date": "1989-07-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$YZiHdxIT0oeQJwots4YsFuOlU0ib/KmDwdcj.50zCN0iRh.FamINa"}	customers
159	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 159, "cpf": "121.911.731-59", "name": "Customer 159", "email": "customer159@mail.example", "phone": "+55 11 911165629", "address": {"city": "Belém", "state": "PA", "number": "159", "street": "Rua 159", "postal_code": "05883-000"}, "birth_date": "1998-10-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$XR5rabfNwjno9uxf/hfvpOqP0YOAVJX2Nb.Ct6uYPKQ4hJ0K4dcI6"}	customers
160	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 160, "cpf": "040.640.440-60", "name": "Customer 160", "email": "customer160@mail.example", "phone": "+55 11 911172960", "address": {"city": "São Paulo", "state": "SP", "number": "160", "street": "Rua 160", "postal_code": "05920-000"}, "birth_date": "1972-02-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$DcOirp3mUk0.EKTEcW1ls.YnNaGXQ2TE2IizrV2/UZKi66RRlSxKK"}	customers
161	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 161, "cpf": "959.369.149-61", "name": "Customer 161", "email": "customer161@mail.example", "phone": "+55 11 911180291", "address": {"city": "Recife", "state": "PE", "number": "161", "street": "Rua 161", "postal_code": "05957-000"}, "birth_date": "1961-03-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$nzQI7y7uc2hYvVofecBN8uQV6vAHMzFuf.qjKji6n1Xt8MD8KtrNm"}	customers
162	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 162, "cpf": "878.098.858-62", "name": "Customer 162", "email": "customer162@mail.example", "phone": "+55 11 911187622", "address": {"city": "Curitiba", "state": "PR", "number": "162", "street": "Rua 162", "postal_code": "05994-000"}, "birth_date": "1976-01-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$6dSkQW5Q90ForfB7ztQUde5jKQbwyR33J77ooY8nctksQTIzXNDI2"}	customers
163	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 163, "cpf": "797.827.567-63", "name": "Customer 163", "email": "customer163@mail.example", "phone": "+55 11 911194953", "address": {"city": "Belém", "state": "PA", "number": "163", "street": "Rua 163", "postal_code": "06031-000"}, "birth_date": "1970-08-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$eNvhUySgtZ3FbrmJJkEIV.hFXLfQdOZZQzgyDDh4rQ1fe9/VV2VTq"}	customers
164	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 164, "cpf": "716.556.276-64", "name": "Customer 164", "email": "customer164@mail.example", "phone": "+55 11 911202284", "address": {"city": "São Paulo", "state": "SP", "number": "164", "street": "Rua 164", "postal_code": "06068-000"}, "birth_date": "1991-09-02", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$7fFIPykmdX4Ilg3SUvRRuOEa6eUWLLNt4wC073XmRmK8yEf0NcZ36"}	customers
165	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 165, "cpf": "635.285.985-65", "name": "Customer 165", "email": "customer165@mail.example", "phone": "+55 11 911209615", "address": {"city": "Recife", "state": "PE", "number": "165", "street": "Rua 165", "postal_code": "06105-000"}, "birth_date": "1995-01-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$7jVveAWzATO6I9a10m3aXeB3iKgcaGC.Z7gasneLZlp8Lyg7TJCJW"}	customers
166	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 166, "cpf": "554.014.694-66", "name": "Customer 166", "email": "customer166@mail.example", "phone": "+55 11 911216946", "address": {"city": "Curitiba", "state": "PR", "number": "166", "street": "Rua 166", "postal_code": "06142-000"}, "birth_date": "1966-03-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$NO/mX4bRp5m9b14EPr/4COLRveE7OX9e/BgMynpvK66uINKDvZIEa"}	customers
167	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 167, "cpf": "473.743.403-67", "name": "Customer 167", "email": "customer167@mail.example", "phone": "+55 11 911224277", "address": {"city": "Belém", "state": "PA", "number": "167", "street": "Rua 167", "postal_code": "06179-000"}, "birth_date": "1961-09-03", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$dGgDoTVAtZqiJRyBmcD04OBvQl5OyZPst/8HXpGABdPbROCT8vfkm"}	customers
168	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 168, "cpf": "392.472.112-68", "name": "Customer 168", "email": "customer168@mail.example", "phone": "+55 11 911231608", "address": {"city": "São Paulo", "state": "SP", "number": "168", "street": "Rua 168", "postal_code": "06216-000"}, "birth_date": "1967-05-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$yEYTuCscn2.xyNAzKP9oYeFyRSIVlP4JlPECefpDWMYo4oPbtTp5a"}	customers
169	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 169, "cpf": "311.201.821-69", "name": "Customer 169", "email": "customer169@mail.example", "phone": "+55 11 911238939", "address": {"city": "Recife", "state": "PE", "number": "169", "street": "Rua 169", "postal_code": "06253-000"}, "birth_date": "1974-03-17", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$1zM10njQ4lAUcJo34zwsQuLCc3ZGODusLO285OwB9VLd4NZmtH4F."}	customers
170	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 170, "cpf": "230.930.530-70", "name": "Customer 170", "email": "customer170@mail.example", "phone": "+55 11 911246270", "address": {"city": "Curitiba", "state": "PR", "number": "170", "street": "Rua 170", "postal_code": "06290-000"}, "birth_date": "1964-02-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$T9/mXCi/01ga7WyGMS89fuD3Ii7MX/o8wJF8JmrgHb6NllLEsQByu"}	customers
171	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 171, "cpf": "149.659.239-71", "name": "Customer 171", "email": "customer171@mail.example", "phone": "+55 11 911253601", "address": {"city": "Belém", "state": "PA", "number": "171", "street": "Rua 171", "postal_code": "06327-000"}, "birth_date": "1983-11-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$UIO9qW0Xzo1DkFH/2tc9kuGuDxryu1c31u9DXTYmDeTR3ZBo0ffxK"}	customers
172	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 172, "cpf": "068.388.948-72", "name": "Customer 172", "email": "customer172@mail.example", "phone": "+55 11 911260932", "address": {"city": "São Paulo", "state": "SP", "number": "172", "street": "Rua 172", "postal_code": "06364-000"}, "birth_date": "1978-09-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$p8CHb/TjMAliN1aGWVMFju6pSJffH8qKoYYNCdLRtvF4AbGMi56ny"}	customers
173	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 173, "cpf": "987.117.657-73", "name": "Customer 173", "email": "customer173@mail.example", "phone": "+55 11 911268263", "address": {"city": "Recife", "state": "PE", "number": "173", "street": "Rua 173", "postal_code": "06401-000"}, "birth_date": "1974-07-25", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$0leXPRU4T.Mq8HYinUgl7.yFXEKjJ8njnnH.x/xaYuSHBJFtVxTbe"}	customers
174	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 174, "cpf": "906.846.366-74", "name": "Customer 174", "email": "customer174@mail.example", "phone": "+55 11 911275594", "address": {"city": "Curitiba", "state": "PR", "number": "174", "street": "Rua 174", "postal_code": "06438-000"}, "birth_date": "1998-08-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$ypDWQGBhePkP0/JLJplsrOhoAQf/Jvf0sNnYm6xSTNpWoajH5g336"}	customers
175	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 175, "cpf": "825.575.075-75", "name": "Customer 175", "email": "customer175@mail.example", "phone": "+55 11 911282925", "address": {"city": "Belém", "state": "PA", "number": "175", "street": "Rua 175", "postal_code": "06475-000"}, "birth_date": "1963-03-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$hg4oCV7wRiCpwZDJs7OK/uLSlRTp3tc9ShXQZtUkSfj07zKl86kKG"}	customers
176	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 176, "cpf": "744.304.784-76", "name": "Customer 176", "email": "customer176@mail.example", "phone": "+55 11 911290256", "address": {"city": "São Paulo", "state": "SP", "number": "176", "street": "Rua 176", "postal_code": "06512-000"}, "birth_date": "1999-10-17", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$pJKf.9Rn07YNCtllrkJcfuwh2ovzBYx.DMgPcahiZn5zRTZuQUipG"}	customers
177	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 177, "cpf": "663.033.493-77", "name": "Customer 177", "email": "customer177@mail.example", "phone": "+55 11 911297587", "address": {"city": "Recife", "state": "PE", "number": "177", "street": "Rua 177", "postal_code": "06549-000"}, "birth_date": "1964-04-02", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$FzB7pXMDxOxTtvNnIYbWMOYIURv155pnxfaTp9dJB5FTeRP1HN5kC"}	customers
178	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 178, "cpf": "582.762.202-78", "name": "Customer 178", "email": "customer178@mail.example", "phone": "+55 11 911304918", "address": {"city": "Curitiba", "state": "PR", "number": "178", "street": "Rua 178", "postal_code": "06586-000"}, "birth_date": "1976-08-31", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$mP30BoXRVsmkrxDITDCtMuM6ZfDn0R/v/U5ZsBzk18/7SEIdb2dxG"}	customers
179	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 179, "cpf": "501.491.911-79", "name": "Customer 179", "email": "customer179@mail.example", "phone": "+55 11 911312249", "address": {"city": "Belém", "state": "PA", "number": "179", "street": "Rua 179", "postal_code": "06623-000"}, "birth_date": "2000-10-25", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$RCApgw/ByKVrmusm4Qwyquf74z2E/aw8qvnBH64HIQGo0LybKtlze"}	customers
180	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 180, "cpf": "420.220.620-80", "name": "Customer 180", "email": "customer180@mail.example", "phone": "+55 11 911319580", "address": {"city": "São Paulo", "state": "SP", "number": "180", "street": "Rua 180", "postal_code": "06660-000"}, "birth_date": "1988-09-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$qpom.SKsk8kmbo4eiih69.5NLUpOiG2M1H3Xeu0XmirEdBnLhFJHy"}	customers
181	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 181, "cpf": "339.949.329-81", "name": "Customer 181", "email": "customer181@mail.example", "phone": "+55 11 911326911", "address": {"city": "Recife", "state": "PE", "number": "181", "street": "Rua 181", "postal_code": "06697-000"}, "birth_date": "1982-10-19", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$N4y0OoeBUFxK.QauEfLXoeJe.ci0bq/f/POCqPBcJxGED30hZO.2y"}	customers
182	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 182, "cpf": "258.678.038-82", "name": "Customer 182", "email": "customer182@mail.example", "phone": "+55 11 911334242", "address": {"city": "Curitiba", "state": "PR", "number": "182", "street": "Rua 182", "postal_code": "06734-000"}, "birth_date": "1984-11-19", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$wrjaBQtrX6uxwCLP39/le.Cm.NOLMFI0/F1Ms/lrASCYUVOpTq7o."}	customers
183	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 183, "cpf": "177.407.747-83", "name": "Customer 183", "email": "customer183@mail.example", "phone": "+55 11 911341573", "address": {"city": "Belém", "state": "PA", "number": "183", "street": "Rua 183", "postal_code": "06771-000"}, "birth_date": "1992-01-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$kqMywGn1k/QgHWpes5m74eYERG65zdZcQtetOBBWl6J.Maw7NJGsC"}	customers
184	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 184, "cpf": "096.136.456-84", "name": "Customer 184", "email": "customer184@mail.example", "phone": "+55 11 911348904", "address": {"city": "São Paulo", "state": "SP", "number": "184", "street": "Rua 184", "postal_code": "06808-000"}, "birth_date": "1979-10-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$whlyLscLG/Fh3fDHXjswneuNSI/2tpE47SMFoAx24uYBlPIQ.gon6"}	customers
185	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 185, "cpf": "015.865.165-85", "name": "Customer 185", "email": "customer185@mail.example", "phone": "+55 11 911356235", "address": {"city": "Recife", "state": "PE", "number": "185", "street": "Rua 185", "postal_code": "06845-000"}, "birth_date": "1970-10-30", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Bl9idiUiCGxfT/BbUFOt/e1P5dUDu.E9e7F7nlFRCTgSVUlWYQK1O"}	customers
186	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 186, "cpf": "934.594.874-86", "name": "Customer 186", "email": "customer186@mail.example", "phone": "+55 11 911363566", "address": {"city": "Curitiba", "state": "PR", "number": "186", "street": "Rua 186", "postal_code": "06882-000"}, "birth_date": "1980-02-02", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$mJ3dtYvyf4dd2AcpL/dvgOp/U6oQla96w4I0qKprs8a6PhsU3LghS"}	customers
187	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 187, "cpf": "853.323.583-87", "name": "Customer 187", "email": "customer187@mail.example", "phone": "+55 11 911370897", "address": {"city": "Belém", "state": "PA", "number": "187", "street": "Rua 187", "postal_code": "06919-000"}, "birth_date": "1964-07-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$1V9Ooov..N6PGcDbvnTtE.NgOklNUOJEfYv8yjFpYALlq/d8pleV6"}	customers
188	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 188, "cpf": "772.052.292-88", "name": "Customer 188", "email": "customer188@mail.example", "phone": "+55 11 911378228", "address": {"city": "São Paulo", "state": "SP", "number": "188", "street": "Rua 188", "postal_code": "06956-000"}, "birth_date": "1964-01-26", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$OScCxySnx/XK4DRVdf6mgey.5hJsAihqSjpIaN8I6nmxSaBl1cd1m"}	customers
189	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 189, "cpf": "691.781.001-89", "name": "Customer 189", "email": "customer189@mail.example", "phone": "+55 11 911385559", "address": {"city": "Recife", "state": "PE", "number": "189", "street": "Rua 189", "postal_code": "06993-000"}, "birth_date": "1978-02-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$fPpeBolhZS6zvY1rCRQfiOngY9m0/gbpNWa7kB90lDNXwPtIbEr22"}	customers
190	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 190, "cpf": "610.510.710-90", "name": "Customer 190", "email": "customer190@mail.example", "phone": "+55 11 911392890", "address": {"city": "Curitiba", "state": "PR", "number": "190", "street": "Rua 190", "postal_code": "07030-000"}, "birth_date": "1989-07-10", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Vm3HCHGtZihMrQ8GEGajb.00wrMLFFhZdoHOvFiQjRIk0uxo00rfO"}	customers
191	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 191, "cpf": "529.239.419-91", "name": "Customer 191", "email": "customer191@mail.example", "phone": "+55 11 911400221", "address": {"city": "Belém", "state": "PA", "number": "191", "street": "Rua 191", "postal_code": "07067-000"}, "birth_date": "1981-05-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$xTENDrSjGjXDxbK..xoc/eGd8qGktC2Ds8i3ijF/Mw0yJS2QauoAW"}	customers
192	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 192, "cpf": "448.968.128-92", "name": "Customer 192", "email": "customer192@mail.example", "phone": "+55 11 911407552", "address": {"city": "São Paulo", "state": "SP", "number": "192", "street": "Rua 192", "postal_code": "07104-000"}, "birth_date": "1963-06-12", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$NCJ5g5BY.tWYr.7Kze6ujuvsHEffe1UZ6lTGg3NsnZLgX38VQKlk."}	customers
193	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 193, "cpf": "367.697.837-93", "name": "Customer 193", "email": "customer193@mail.example", "phone": "+55 11 911414883", "address": {"city": "Recife", "state": "PE", "number": "193", "street": "Rua 193", "postal_code": "07141-000"}, "birth_date": "1962-03-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$MkluKRbV2b83QJppyGWYc.j4ZK2xSbUL3D7LtWHnyv8WNF3cetCWq"}	customers
194	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 194, "cpf": "286.426.546-94", "name": "Customer 194", "email": "customer194@mail.example", "phone": "+55 11 911422214", "address": {"city": "Curitiba", "state": "PR", "number": "194", "street": "Rua 194", "postal_code": "07178-000"}, "birth_date": "1962-06-12", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$YIYvUycaR1iFhgYEcgNAAuUcIWKheayJWd.fIhFYVkmx2o9bk61OG"}	customers
195	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 195, "cpf": "205.155.255-95", "name": "Customer 195", "email": "customer195@mail.example", "phone": "+55 11 911429545", "address": {"city": "Belém", "state": "PA", "number": "195", "street": "Rua 195", "postal_code": "07215-000"}, "birth_date": "1983-10-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$cege2nPs9cuEgUfuUm0RhugCp7AFykCM0s0tVUe7L4tUIFaQJqUSW"}	customers
196	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 196, "cpf": "124.884.964-96", "name": "Customer 196", "email": "customer196@mail.example", "phone": "+55 11 911436876", "address": {"city": "São Paulo", "state": "SP", "number": "196", "street": "Rua 196", "postal_code": "07252-000"}, "birth_date": "1977-09-16", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$JNTEP6V.sBsCy1HhOAMg.ewOGAKiuLUDWoFVb6.PjhrbJoZmqFDe6"}	customers
197	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 197, "cpf": "043.613.673-97", "name": "Customer 197", "email": "customer197@mail.example", "phone": "+55 11 911444207", "address": {"city": "Recife", "state": "PE", "number": "197", "street": "Rua 197", "postal_code": "07289-000"}, "birth_date": "1971-05-24", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$gPPUmzenF2ArmqD15SzWjuV/H1k9iTM6h1.kFt/ras17Nk0prUSRi"}	customers
198	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 198, "cpf": "962.342.382-98", "name": "Customer 198", "email": "customer198@mail.example", "phone": "+55 11 911451538", "address": {"city": "Curitiba", "state": "PR", "number": "198", "street": "Rua 198", "postal_code": "07326-000"}, "birth_date": "1990-05-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$Exx1MFoaX0r7DLs5qAdJpuTiEkalraJntvY3tvPY8191OfTfmae3W"}	customers
199	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 199, "cpf": "881.071.091-99", "name": "Customer 199", "email": "customer199@mail.example", "phone": "+55 11 911458869", "address": {"city": "Belém", "state": "PA", "number": "199", "street": "Rua 199", "postal_code": "07363-000"}, "birth_date": "1964-09-16", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$SAcm48dBQDmA.spi/1oVPeIqB1uZy0genDmcOTAHkfBVv8j1mK5Ea"}	customers
200	2026-10-30 14:05:25.941706+00	acme_admin	INSERT	{"id": 200, "cpf": "800.800.800-00", "name": "Customer 200", "email": "customer200@mail.example", "phone": "+55 11 911466200", "address": {"city": "São Paulo", "state": "SP", "number": "200", "street": "Rua 200", "postal_code": "07400-000"}, "birth_date": "1990-01-24", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": null, "password_hash": "$2a$04$rNOp9SCF8jCt70Jg.FN6suOEVhPFy0xK1CY4dvTvNTyGSV74Vkx3m"}	customers
201	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 5, "cpf": "595.645.545-05", "name": "Customer 5", "email": "customer5@mail.example", "phone": "+55 11 910036655", "address": {"city": "Recife", "state": "PE", "number": "5", "street": "Rua 5", "postal_code": "00185-000"}, "birth_date": "1994-05-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 4, "password_hash": "$2a$04$VmBTSTT2AUHarciYpEhLFu1OTVz0nCkbtp/s0Ig1JGojP4Y/h07Qi"}	customers
202	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 10, "cpf": "190.290.090-10", "name": "Customer 10", "email": "customer10@mail.example", "phone": "+55 11 910073310", "address": {"city": "Curitiba", "state": "PR", "number": "10", "street": "Rua 10", "postal_code": "00370-000"}, "birth_date": "1984-12-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 9, "password_hash": "$2a$04$WWDpBXegYHHqHSnfi0.EdOpizSenS.kbHSi9gqYfmZSMYGNAGngIy"}	customers
203	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 15, "cpf": "785.935.635-15", "name": "Customer 15", "email": "customer15@mail.example", "phone": "+55 11 910109965", "address": {"city": "Belém", "state": "PA", "number": "15", "street": "Rua 15", "postal_code": "00555-000"}, "birth_date": "1969-04-06", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 14, "password_hash": "$2a$04$IMP6cgtcmz30W3Mhtmu4FeJgk.TIwdsITqM9ssnQWEyIMjXCDsq5."}	customers
204	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 20, "cpf": "380.580.180-20", "name": "Customer 20", "email": "customer20@mail.example", "phone": "+55 11 910146620", "address": {"city": "São Paulo", "state": "SP", "number": "20", "street": "Rua 20", "postal_code": "00740-000"}, "birth_date": "1999-04-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 19, "password_hash": "$2a$04$mPxJbzVaoF2MsDvUrk.pceIuREkHLv9k5Ba0bDfczYLJCGsjXeTRO"}	customers
205	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 25, "cpf": "975.225.725-25", "name": "Customer 25", "email": "customer25@mail.example", "phone": "+55 11 910183275", "address": {"city": "Recife", "state": "PE", "number": "25", "street": "Rua 25", "postal_code": "00925-000"}, "birth_date": "1979-08-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 24, "password_hash": "$2a$04$UNr3FrlFLq46GrgYhJYJkeIafUIaJwyzkVDGBKN9bPJ7E.Xv6yG1C"}	customers
206	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 30, "cpf": "570.870.270-30", "name": "Customer 30", "email": "customer30@mail.example", "phone": "+55 11 910219930", "address": {"city": "Curitiba", "state": "PR", "number": "30", "street": "Rua 30", "postal_code": "01110-000"}, "birth_date": "1972-04-04", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 29, "password_hash": "$2a$04$xWII0wz5cl2PeDn2Kg8qMOk4XWOffgKwvUtoaWG2NvlVn615ZFRKu"}	customers
207	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 35, "cpf": "165.515.815-35", "name": "Customer 35", "email": "customer35@mail.example", "phone": "+55 11 910256585", "address": {"city": "Belém", "state": "PA", "number": "35", "street": "Rua 35", "postal_code": "01295-000"}, "birth_date": "1996-08-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 34, "password_hash": "$2a$04$5RKlaQHMadS8IEl6XjfCcO.o2k4nrMwcx8i2ZrdUsmniYmPLPNy.K"}	customers
208	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 40, "cpf": "760.160.360-40", "name": "Customer 40", "email": "customer40@mail.example", "phone": "+55 11 910293240", "address": {"city": "São Paulo", "state": "SP", "number": "40", "street": "Rua 40", "postal_code": "01480-000"}, "birth_date": "1994-07-15", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 39, "password_hash": "$2a$04$bdaeeH0csZwXBt2fqIpkN.7eH/k0e71yMpyBb3zRIoyx3FoolDPZO"}	customers
209	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 45, "cpf": "355.805.905-45", "name": "Customer 45", "email": "customer45@mail.example", "phone": "+55 11 910329895", "address": {"city": "Recife", "state": "PE", "number": "45", "street": "Rua 45", "postal_code": "01665-000"}, "birth_date": "1978-10-18", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 44, "password_hash": "$2a$04$r3pu8FEJ4AziPE80TQsOE.gC97VPapMdAOinxE9v8Rf1KqpUmtQ2e"}	customers
210	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 50, "cpf": "950.450.450-50", "name": "Customer 50", "email": "customer50@mail.example", "phone": "+55 11 910366550", "address": {"city": "Curitiba", "state": "PR", "number": "50", "street": "Rua 50", "postal_code": "01850-000"}, "birth_date": "1961-10-29", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 49, "password_hash": "$2a$04$gXe.pgCGK/Lo7XGm0lDwsOdxr4caBlhB5QmTXx98RjMG1czTqq6pm"}	customers
211	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 55, "cpf": "545.095.995-55", "name": "Customer 55", "email": "customer55@mail.example", "phone": "+55 11 910403205", "address": {"city": "Belém", "state": "PA", "number": "55", "street": "Rua 55", "postal_code": "02035-000"}, "birth_date": "1968-03-11", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 54, "password_hash": "$2a$04$6ALe3h0rbhstucXRBQV0petrOfOdQKM8ta1TbQOLabFukVWIwMQIu"}	customers
212	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 60, "cpf": "140.740.540-60", "name": "Customer 60", "email": "customer60@mail.example", "phone": "+55 11 910439860", "address": {"city": "São Paulo", "state": "SP", "number": "60", "street": "Rua 60", "postal_code": "02220-000"}, "birth_date": "1981-01-29", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 59, "password_hash": "$2a$04$CqKDUtiCIfEYEQt89TpkhuUnfBUZm/zSf4teAt3mVW78SDCFFpRfq"}	customers
213	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 65, "cpf": "735.385.085-65", "name": "Customer 65", "email": "customer65@mail.example", "phone": "+55 11 910476515", "address": {"city": "Recife", "state": "PE", "number": "65", "street": "Rua 65", "postal_code": "02405-000"}, "birth_date": "1986-08-05", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 64, "password_hash": "$2a$04$M3.zwXjYUBXzKfz.nfzBcefH8HUlcyJUS.r/jET/iVJwMmuhc8ybS"}	customers
214	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 70, "cpf": "330.030.630-70", "name": "Customer 70", "email": "customer70@mail.example", "phone": "+55 11 910513170", "address": {"city": "Curitiba", "state": "PR", "number": "70", "street": "Rua 70", "postal_code": "02590-000"}, "birth_date": "1972-05-14", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 69, "password_hash": "$2a$04$jJt6qMGOY5TcsxWMICqJ4ODJZJix/9e68X/lRLHazLz5VEVLtb1u2"}	customers
215	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 75, "cpf": "925.675.175-75", "name": "Customer 75", "email": "customer75@mail.example", "phone": "+55 11 910549825", "address": {"city": "Belém", "state": "PA", "number": "75", "street": "Rua 75", "postal_code": "02775-000"}, "birth_date": "1978-08-22", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 74, "password_hash": "$2a$04$cAqjPc6rK4sabJe99jhTFuGu1ggdfjC/csjzIXlJj53HQdeYLuxyu"}	customers
216	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 80, "cpf": "520.320.720-80", "name": "Customer 80", "email": "customer80@mail.example", "phone": "+55 11 910586480", "address": {"city": "São Paulo", "state": "SP", "number": "80", "street": "Rua 80", "postal_code": "02960-000"}, "birth_date": "1995-08-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 79, "password_hash": "$2a$04$JIXtI8R7t42O1O5YbGNf3.bnJIXu3j3ZOIvtGikmhGWm2HmMt/MPy"}	customers
217	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 85, "cpf": "115.965.265-85", "name": "Customer 85", "email": "customer85@mail.example", "phone": "+55 11 910623135", "address": {"city": "Recife", "state": "PE", "number": "85", "street": "Rua 85", "postal_code": "03145-000"}, "birth_date": "1987-08-14", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 84, "password_hash": "$2a$04$6YQuAlGdDFgId55J.l47Y.OUpfyfIqblrWuqdXcwEeuUE3Xr2LFvm"}	customers
218	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 90, "cpf": "710.610.810-90", "name": "Customer 90", "email": "customer90@mail.example", "phone": "+55 11 910659790", "address": {"city": "Curitiba", "state": "PR", "number": "90", "street": "Rua 90", "postal_code": "03330-000"}, "birth_date": "1988-10-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 89, "password_hash": "$2a$04$EMTNsHhqWi/tQZoM5HWjyeMAVdXqOa1yLLcGBzxMj749Gv/9GA17."}	customers
219	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 95, "cpf": "305.255.355-95", "name": "Customer 95", "email": "customer95@mail.example", "phone": "+55 11 910696445", "address": {"city": "Belém", "state": "PA", "number": "95", "street": "Rua 95", "postal_code": "03515-000"}, "birth_date": "1981-07-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 94, "password_hash": "$2a$04$T2mrUEq1u3ojLo.BlTS2IujJuajTElCa76iqfDY84u8soG61MqY1W"}	customers
220	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 100, "cpf": "900.900.900-00", "name": "Customer 100", "email": "customer100@mail.example", "phone": "+55 11 910733100", "address": {"city": "São Paulo", "state": "SP", "number": "100", "street": "Rua 100", "postal_code": "03700-000"}, "birth_date": "1998-04-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 99, "password_hash": "$2a$04$Xpx3SX7PLgdlgGK3C.HkTetRPVh6b455JEeS.V9Hyto9HQGHTOxH."}	customers
221	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 105, "cpf": "495.545.445-05", "name": "Customer 105", "email": "customer105@mail.example", "phone": "+55 11 910769755", "address": {"city": "Recife", "state": "PE", "number": "105", "street": "Rua 105", "postal_code": "03885-000"}, "birth_date": "1968-07-13", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 104, "password_hash": "$2a$04$7E3n13F/1oqydFChgFjUHuAwKsVWQznRDQHI6kToasnUXgZE76W1a"}	customers
222	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 110, "cpf": "090.190.990-10", "name": "Customer 110", "email": "customer110@mail.example", "phone": "+55 11 910806410", "address": {"city": "Curitiba", "state": "PR", "number": "110", "street": "Rua 110", "postal_code": "04070-000"}, "birth_date": "1971-06-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 109, "password_hash": "$2a$04$PLOTb8OOIdwKmIi9NhQOqeecyE.bdqMjD4WJw57wTZCXgFCdtEfgW"}	customers
223	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 115, "cpf": "685.835.535-15", "name": "Customer 115", "email": "customer115@mail.example", "phone": "+55 11 910843065", "address": {"city": "Belém", "state": "PA", "number": "115", "street": "Rua 115", "postal_code": "04255-000"}, "birth_date": "1999-11-08", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 114, "password_hash": "$2a$04$pk/phk5PFF.4yCIgCV5alOULyJP6yKC2qSsPh8H.CPCeZbMrEtMSi"}	customers
224	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 120, "cpf": "280.480.080-20", "name": "Customer 120", "email": "customer120@mail.example", "phone": "+55 11 910879720", "address": {"city": "São Paulo", "state": "SP", "number": "120", "street": "Rua 120", "postal_code": "04440-000"}, "birth_date": "1975-12-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 119, "password_hash": "$2a$04$Xo5xbQvJciqgX6WHHJ9uYuyPmCm73wRVNONWk7bi4.XkHuSPorBlq"}	customers
225	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 125, "cpf": "875.125.625-25", "name": "Customer 125", "email": "customer125@mail.example", "phone": "+55 11 910916375", "address": {"city": "Recife", "state": "PE", "number": "125", "street": "Rua 125", "postal_code": "04625-000"}, "birth_date": "1990-09-30", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 124, "password_hash": "$2a$04$7g9JYBBHsfTfSkPqcQnXOOvc4EuXwalPuxm0o75iXxHGjZN/IsZ1O"}	customers
226	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 130, "cpf": "470.770.170-30", "name": "Customer 130", "email": "customer130@mail.example", "phone": "+55 11 910953030", "address": {"city": "Curitiba", "state": "PR", "number": "130", "street": "Rua 130", "postal_code": "04810-000"}, "birth_date": "1993-05-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 129, "password_hash": "$2a$04$HGZiPg60NkbO6Xegy9nXTOPN.0r0HTbpZe1g57F6.0oyo8DuupWTK"}	customers
227	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 135, "cpf": "065.415.715-35", "name": "Customer 135", "email": "customer135@mail.example", "phone": "+55 11 910989685", "address": {"city": "Belém", "state": "PA", "number": "135", "street": "Rua 135", "postal_code": "04995-000"}, "birth_date": "1995-02-09", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 134, "password_hash": "$2a$04$bN/z/3OH7MdlHnBF/uxay.LA37pX3/rbmXNKeqFPrrovSq7ZPuqDi"}	customers
228	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 140, "cpf": "660.060.260-40", "name": "Customer 140", "email": "customer140@mail.example", "phone": "+55 11 911026340", "address": {"city": "São Paulo", "state": "SP", "number": "140", "street": "Rua 140", "postal_code": "05180-000"}, "birth_date": "1992-04-28", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 139, "password_hash": "$2a$04$PcQ8LZngzjOjvUWJyr/SuOXfRAqmIEVBcdRM76I2ZjFlYqckR.ZLy"}	customers
229	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 145, "cpf": "255.705.805-45", "name": "Customer 145", "email": "customer145@mail.example", "phone": "+55 11 911062995", "address": {"city": "Recife", "state": "PE", "number": "145", "street": "Rua 145", "postal_code": "05365-000"}, "birth_date": "1966-04-07", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 144, "password_hash": "$2a$04$LO2i9XcS.w5Y1LfQAAzLMu4Rixx/5.OMpTJ/bE6YJAc1bRiv/PGK."}	customers
230	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 150, "cpf": "850.350.350-50", "name": "Customer 150", "email": "customer150@mail.example", "phone": "+55 11 911099650", "address": {"city": "Curitiba", "state": "PR", "number": "150", "street": "Rua 150", "postal_code": "05550-000"}, "birth_date": "1978-08-26", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 149, "password_hash": "$2a$04$cQYyIA9o7Cv7hkGczSmkneWWjcvOhc6vMsyNK4bIgEvYxkO/xtfA."}	customers
231	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 155, "cpf": "445.995.895-55", "name": "Customer 155", "email": "customer155@mail.example", "phone": "+55 11 911136305", "address": {"city": "Belém", "state": "PA", "number": "155", "street": "Rua 155", "postal_code": "05735-000"}, "birth_date": "1967-03-31", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 154, "password_hash": "$2a$04$rE6d7ZiKrqQZcLT8XD0nMuqFEDmevw9iQZSaojI66RKObN0c6C.Qq"}	customers
232	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 160, "cpf": "040.640.440-60", "name": "Customer 160", "email": "customer160@mail.example", "phone": "+55 11 911172960", "address": {"city": "São Paulo", "state": "SP", "number": "160", "street": "Rua 160", "postal_code": "05920-000"}, "birth_date": "1972-02-27", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 159, "password_hash": "$2a$04$DcOirp3mUk0.EKTEcW1ls.YnNaGXQ2TE2IizrV2/UZKi66RRlSxKK"}	customers
233	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 165, "cpf": "635.285.985-65", "name": "Customer 165", "email": "customer165@mail.example", "phone": "+55 11 911209615", "address": {"city": "Recife", "state": "PE", "number": "165", "street": "Rua 165", "postal_code": "06105-000"}, "birth_date": "1995-01-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 164, "password_hash": "$2a$04$7jVveAWzATO6I9a10m3aXeB3iKgcaGC.Z7gasneLZlp8Lyg7TJCJW"}	customers
234	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 170, "cpf": "230.930.530-70", "name": "Customer 170", "email": "customer170@mail.example", "phone": "+55 11 911246270", "address": {"city": "Curitiba", "state": "PR", "number": "170", "street": "Rua 170", "postal_code": "06290-000"}, "birth_date": "1964-02-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 169, "password_hash": "$2a$04$T9/mXCi/01ga7WyGMS89fuD3Ii7MX/o8wJF8JmrgHb6NllLEsQByu"}	customers
235	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 175, "cpf": "825.575.075-75", "name": "Customer 175", "email": "customer175@mail.example", "phone": "+55 11 911282925", "address": {"city": "Belém", "state": "PA", "number": "175", "street": "Rua 175", "postal_code": "06475-000"}, "birth_date": "1963-03-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 174, "password_hash": "$2a$04$hg4oCV7wRiCpwZDJs7OK/uLSlRTp3tc9ShXQZtUkSfj07zKl86kKG"}	customers
236	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 180, "cpf": "420.220.620-80", "name": "Customer 180", "email": "customer180@mail.example", "phone": "+55 11 911319580", "address": {"city": "São Paulo", "state": "SP", "number": "180", "street": "Rua 180", "postal_code": "06660-000"}, "birth_date": "1988-09-01", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 179, "password_hash": "$2a$04$qpom.SKsk8kmbo4eiih69.5NLUpOiG2M1H3Xeu0XmirEdBnLhFJHy"}	customers
237	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 185, "cpf": "015.865.165-85", "name": "Customer 185", "email": "customer185@mail.example", "phone": "+55 11 911356235", "address": {"city": "Recife", "state": "PE", "number": "185", "street": "Rua 185", "postal_code": "06845-000"}, "birth_date": "1970-10-30", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 184, "password_hash": "$2a$04$Bl9idiUiCGxfT/BbUFOt/e1P5dUDu.E9e7F7nlFRCTgSVUlWYQK1O"}	customers
238	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 190, "cpf": "610.510.710-90", "name": "Customer 190", "email": "customer190@mail.example", "phone": "+55 11 911392890", "address": {"city": "Curitiba", "state": "PR", "number": "190", "street": "Rua 190", "postal_code": "07030-000"}, "birth_date": "1989-07-10", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 189, "password_hash": "$2a$04$Vm3HCHGtZihMrQ8GEGajb.00wrMLFFhZdoHOvFiQjRIk0uxo00rfO"}	customers
239	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 195, "cpf": "205.155.255-95", "name": "Customer 195", "email": "customer195@mail.example", "phone": "+55 11 911429545", "address": {"city": "Belém", "state": "PA", "number": "195", "street": "Rua 195", "postal_code": "07215-000"}, "birth_date": "1983-10-20", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 194, "password_hash": "$2a$04$cege2nPs9cuEgUfuUm0RhugCp7AFykCM0s0tVUe7L4tUIFaQJqUSW"}	customers
240	2026-10-30 14:05:26.08136+00	acme_admin	UPDATE	{"id": 200, "cpf": "800.800.800-00", "name": "Customer 200", "email": "customer200@mail.example", "phone": "+55 11 911466200", "address": {"city": "São Paulo", "state": "SP", "number": "200", "street": "Rua 200", "postal_code": "07400-000"}, "birth_date": "1990-01-24", "created_at": "2026-10-30T14:05:25.941706+00:00", "referred_by": 199, "password_hash": "$2a$04$rNOp9SCF8jCt70Jg.FN6suOEVhPFy0xK1CY4dvTvNTyGSV74Vkx3m"}	customers
\.


--
-- Data for Name: invoices; Type: TABLE DATA; Schema: billing; Owner: -
--

COPY billing.invoices (id, order_id, issued_on, amount, access_key) FROM stdin;
1	6	2026-10-30	1656.48	33333333333333333333333333333333335894709918
2	9	2026-10-30	205.47	33333333333333333333333333333333338842064877
3	18	2026-10-30	1781.76	33333333333333333333333333333333317684129754
4	21	2026-10-30	1360.08	33333333333333333333333333333333320631484713
5	30	2026-10-30	1773.60	33333333333333333333333333333333329473549590
6	33	2026-10-30	436.44	33333333333333333333333333333333332420904549
7	42	2026-10-30	1552.24	33333333333333333333333333333333341262969426
8	45	2026-10-30	858.57	33333333333333333333333333333333344210324385
9	54	2026-10-30	750.44	33333333333333333333333333333333353052389262
10	57	2026-10-30	1234.74	33333333333333333333333333333333355999744221
11	66	2026-10-30	1661.88	33333333333333333333333333333333364841809098
12	69	2026-10-30	890.52	33333333333333333333333333333333367789164057
13	78	2026-10-30	1768.24	33333333333333333333333333333333376631228934
14	81	2026-10-30	1436.85	33333333333333333333333333333333379578583893
15	90	2026-10-30	1881.76	33333333333333333333333333333333388420648770
16	93	2026-10-30	867.21	33333333333333333333333333333333391368003729
17	102	2026-10-30	425.00	33333333333333333333333333333333100210068606
18	105	2026-10-30	651.96	33333333333333333333333333333333103157423565
19	114	2026-10-30	645.24	33333333333333333333333333333333111999488442
20	117	2026-10-30	432.87	33333333333333333333333333333333114946843401
21	126	2026-10-30	1656.48	33333333333333333333333333333333123788908278
22	129	2026-10-30	205.47	33333333333333333333333333333333126736263237
23	138	2026-10-30	1781.76	33333333333333333333333333333333135578328114
24	141	2026-10-30	1360.08	33333333333333333333333333333333138525683073
25	150	2026-10-30	1773.60	33333333333333333333333333333333147367747950
26	153	2026-10-30	436.44	33333333333333333333333333333333150315102909
27	162	2026-10-30	1552.24	33333333333333333333333333333333159157167786
28	165	2026-10-30	858.57	33333333333333333333333333333333162104522745
29	174	2026-10-30	750.44	33333333333333333333333333333333170946587622
30	177	2026-10-30	1234.74	33333333333333333333333333333333173893942581
31	186	2026-10-30	1661.88	33333333333333333333333333333333182736007458
32	189	2026-10-30	890.52	33333333333333333333333333333333185683362417
33	198	2026-10-30	1768.24	33333333333333333333333333333333194525427294
34	201	2026-10-30	1436.85	33333333333333333333333333333333197472782253
35	210	2026-10-30	1881.76	33333333333333333333333333333333206314847130
36	213	2026-10-30	867.21	33333333333333333333333333333333209262202089
37	222	2026-10-30	425.00	33333333333333333333333333333333218104266966
38	225	2026-10-30	651.96	33333333333333333333333333333333221051621925
39	234	2026-10-30	645.24	33333333333333333333333333333333229893686802
40	237	2026-10-30	432.87	33333333333333333333333333333333232841041761
41	246	2026-10-30	1656.48	33333333333333333333333333333333241683106638
42	249	2026-10-30	205.47	33333333333333333333333333333333244630461597
43	258	2026-10-30	1781.76	33333333333333333333333333333333253472526474
44	261	2026-10-30	1360.08	33333333333333333333333333333333256419881433
45	270	2026-10-30	1773.60	33333333333333333333333333333333265261946310
46	273	2026-10-30	436.44	33333333333333333333333333333333268209301269
47	282	2026-10-30	1552.24	33333333333333333333333333333333277051366146
48	285	2026-10-30	858.57	33333333333333333333333333333333279998721105
49	294	2026-10-30	750.44	33333333333333333333333333333333288840785982
50	297	2026-10-30	1234.74	33333333333333333333333333333333291788140941
51	306	2026-10-30	1661.88	33333333333333333333333333333333300630205818
52	309	2026-10-30	890.52	33333333333333333333333333333333303577560777
53	318	2026-10-30	1768.24	33333333333333333333333333333333312419625654
54	321	2026-10-30	1436.85	33333333333333333333333333333333315366980613
55	330	2026-10-30	1881.76	33333333333333333333333333333333324209045490
56	333	2026-10-30	867.21	33333333333333333333333333333333327156400449
57	342	2026-10-30	425.00	33333333333333333333333333333333335998465326
58	345	2026-10-30	651.96	33333333333333333333333333333333338945820285
59	354	2026-10-30	645.24	33333333333333333333333333333333347787885162
60	357	2026-10-30	432.87	33333333333333333333333333333333350735240121
61	366	2026-10-30	1656.48	33333333333333333333333333333333359577304998
62	369	2026-10-30	205.47	33333333333333333333333333333333362524659957
63	378	2026-10-30	1781.76	33333333333333333333333333333333371366724834
64	381	2026-10-30	1360.08	33333333333333333333333333333333374314079793
65	390	2026-10-30	1773.60	33333333333333333333333333333333383156144670
66	393	2026-10-30	436.44	33333333333333333333333333333333386103499629
67	402	2026-10-30	1552.24	33333333333333333333333333333333394945564506
68	405	2026-10-30	858.57	33333333333333333333333333333333397892919465
69	414	2026-10-30	750.44	33333333333333333333333333333333406734984342
70	417	2026-10-30	1234.74	33333333333333333333333333333333409682339301
71	426	2026-10-30	1661.88	33333333333333333333333333333333418524404178
72	429	2026-10-30	890.52	33333333333333333333333333333333421471759137
73	438	2026-10-30	1768.24	33333333333333333333333333333333430313824014
74	441	2026-10-30	1436.85	33333333333333333333333333333333433261178973
75	450	2026-10-30	1881.76	33333333333333333333333333333333442103243850
76	453	2026-10-30	867.21	33333333333333333333333333333333445050598809
77	462	2026-10-30	425.00	33333333333333333333333333333333453892663686
78	465	2026-10-30	651.96	33333333333333333333333333333333456840018645
79	474	2026-10-30	645.24	33333333333333333333333333333333465682083522
80	477	2026-10-30	432.87	33333333333333333333333333333333468629438481
81	486	2026-10-30	1656.48	33333333333333333333333333333333477471503358
82	489	2026-10-30	205.47	33333333333333333333333333333333480418858317
83	498	2026-10-30	1781.76	33333333333333333333333333333333489260923194
84	501	2026-10-30	1360.08	33333333333333333333333333333333492208278153
85	510	2026-10-30	1773.60	33333333333333333333333333333333501050343030
86	513	2026-10-30	436.44	33333333333333333333333333333333503997697989
87	522	2026-10-30	1552.24	33333333333333333333333333333333512839762866
88	525	2026-10-30	858.57	33333333333333333333333333333333515787117825
89	534	2026-10-30	750.44	33333333333333333333333333333333524629182702
90	537	2026-10-30	1234.74	33333333333333333333333333333333527576537661
91	546	2026-10-30	1661.88	33333333333333333333333333333333536418602538
92	549	2026-10-30	890.52	33333333333333333333333333333333539365957497
93	558	2026-10-30	1768.24	33333333333333333333333333333333548208022374
94	561	2026-10-30	1436.85	33333333333333333333333333333333551155377333
95	570	2026-10-30	1881.76	33333333333333333333333333333333559997442210
96	573	2026-10-30	867.21	33333333333333333333333333333333562944797169
97	582	2026-10-30	425.00	33333333333333333333333333333333571786862046
98	585	2026-10-30	651.96	33333333333333333333333333333333574734217005
99	594	2026-10-30	645.24	33333333333333333333333333333333583576281882
100	597	2026-10-30	432.87	33333333333333333333333333333333586523636841
101	1	2026-10-30	1261.55	33333333333333333333333333333333333982451653
102	10	2026-10-30	480.04	33333333333333333333333333333333339824516530
103	13	2026-10-30	1333.11	33333333333333333333333333333333312771871489
104	22	2026-10-30	1290.40	33333333333333333333333333333333321613936366
105	25	2026-10-30	316.41	33333333333333333333333333333333324561291325
106	34	2026-10-30	776.39	33333333333333333333333333333333333403356202
107	37	2026-10-30	1831.88	33333333333333333333333333333333336350711161
108	46	2026-10-30	827.48	33333333333333333333333333333333345192776038
109	49	2026-10-30	2175.07	33333333333333333333333333333333348140130997
110	58	2026-10-30	879.96	33333333333333333333333333333333356982195874
111	61	2026-10-30	2675.59	33333333333333333333333333333333359929550833
112	70	2026-10-30	2245.50	33333333333333333333333333333333368771615710
113	73	2026-10-30	2604.02	33333333333333333333333333333333371718970669
114	82	2026-10-30	1719.69	33333333333333333333333333333333380561035546
115	85	2026-10-30	2924.58	33333333333333333333333333333333383508390505
116	94	2026-10-30	240.94	33333333333333333333333333333333392350455382
117	97	2026-10-30	883.86	33333333333333333333333333333333395297810341
118	106	2026-10-30	977.19	33333333333333333333333333333333104139875218
119	109	2026-10-30	2228.15	33333333333333333333333333333333107087230177
120	118	2026-10-30	1235.77	33333333333333333333333333333333115929295054
121	121	2026-10-30	1261.55	33333333333333333333333333333333118876650013
122	130	2026-10-30	480.04	33333333333333333333333333333333127718714890
123	133	2026-10-30	1333.11	33333333333333333333333333333333130666069849
124	142	2026-10-30	1290.40	33333333333333333333333333333333139508134726
125	145	2026-10-30	316.41	33333333333333333333333333333333142455489685
126	154	2026-10-30	776.39	33333333333333333333333333333333151297554562
127	157	2026-10-30	1831.88	33333333333333333333333333333333154244909521
128	166	2026-10-30	827.48	33333333333333333333333333333333163086974398
129	169	2026-10-30	2175.07	33333333333333333333333333333333166034329357
130	178	2026-10-30	879.96	33333333333333333333333333333333174876394234
131	181	2026-10-30	2675.59	33333333333333333333333333333333177823749193
132	190	2026-10-30	2245.50	33333333333333333333333333333333186665814070
133	193	2026-10-30	2604.02	33333333333333333333333333333333189613169029
134	202	2026-10-30	1719.69	33333333333333333333333333333333198455233906
135	205	2026-10-30	2924.58	33333333333333333333333333333333201402588865
136	214	2026-10-30	240.94	33333333333333333333333333333333210244653742
137	217	2026-10-30	883.86	33333333333333333333333333333333213192008701
138	226	2026-10-30	977.19	33333333333333333333333333333333222034073578
139	229	2026-10-30	2228.15	33333333333333333333333333333333224981428537
140	238	2026-10-30	1235.77	33333333333333333333333333333333233823493414
141	241	2026-10-30	1261.55	33333333333333333333333333333333236770848373
142	250	2026-10-30	480.04	33333333333333333333333333333333245612913250
143	253	2026-10-30	1333.11	33333333333333333333333333333333248560268209
144	262	2026-10-30	1290.40	33333333333333333333333333333333257402333086
145	265	2026-10-30	316.41	33333333333333333333333333333333260349688045
146	274	2026-10-30	776.39	33333333333333333333333333333333269191752922
147	277	2026-10-30	1831.88	33333333333333333333333333333333272139107881
148	286	2026-10-30	827.48	33333333333333333333333333333333280981172758
149	289	2026-10-30	2175.07	33333333333333333333333333333333283928527717
150	298	2026-10-30	879.96	33333333333333333333333333333333292770592594
151	301	2026-10-30	2675.59	33333333333333333333333333333333295717947553
152	310	2026-10-30	2245.50	33333333333333333333333333333333304560012430
153	313	2026-10-30	2604.02	33333333333333333333333333333333307507367389
154	322	2026-10-30	1719.69	33333333333333333333333333333333316349432266
155	325	2026-10-30	2924.58	33333333333333333333333333333333319296787225
156	334	2026-10-30	240.94	33333333333333333333333333333333328138852102
157	337	2026-10-30	883.86	33333333333333333333333333333333331086207061
158	346	2026-10-30	977.19	33333333333333333333333333333333339928271938
159	349	2026-10-30	2228.15	33333333333333333333333333333333342875626897
160	358	2026-10-30	1235.77	33333333333333333333333333333333351717691774
161	361	2026-10-30	1261.55	33333333333333333333333333333333354665046733
162	370	2026-10-30	480.04	33333333333333333333333333333333363507111610
163	373	2026-10-30	1333.11	33333333333333333333333333333333366454466569
164	382	2026-10-30	1290.40	33333333333333333333333333333333375296531446
165	385	2026-10-30	316.41	33333333333333333333333333333333378243886405
166	394	2026-10-30	776.39	33333333333333333333333333333333387085951282
167	397	2026-10-30	1831.88	33333333333333333333333333333333390033306241
168	406	2026-10-30	827.48	33333333333333333333333333333333398875371118
169	409	2026-10-30	2175.07	33333333333333333333333333333333401822726077
170	418	2026-10-30	879.96	33333333333333333333333333333333410664790954
171	421	2026-10-30	2675.59	33333333333333333333333333333333413612145913
172	430	2026-10-30	2245.50	33333333333333333333333333333333422454210790
173	433	2026-10-30	2604.02	33333333333333333333333333333333425401565749
174	442	2026-10-30	1719.69	33333333333333333333333333333333434243630626
175	445	2026-10-30	2924.58	33333333333333333333333333333333437190985585
176	454	2026-10-30	240.94	33333333333333333333333333333333446033050462
177	457	2026-10-30	883.86	33333333333333333333333333333333448980405421
178	466	2026-10-30	977.19	33333333333333333333333333333333457822470298
179	469	2026-10-30	2228.15	33333333333333333333333333333333460769825257
180	478	2026-10-30	1235.77	33333333333333333333333333333333469611890134
181	481	2026-10-30	1261.55	33333333333333333333333333333333472559245093
182	490	2026-10-30	480.04	33333333333333333333333333333333481401309970
183	493	2026-10-30	1333.11	33333333333333333333333333333333484348664929
184	502	2026-10-30	1290.40	33333333333333333333333333333333493190729806
185	505	2026-10-30	316.41	33333333333333333333333333333333496138084765
186	514	2026-10-30	776.39	33333333333333333333333333333333504980149642
187	517	2026-10-30	1831.88	33333333333333333333333333333333507927504601
188	526	2026-10-30	827.48	33333333333333333333333333333333516769569478
189	529	2026-10-30	2175.07	33333333333333333333333333333333519716924437
190	538	2026-10-30	879.96	33333333333333333333333333333333528558989314
191	541	2026-10-30	2675.59	33333333333333333333333333333333531506344273
192	550	2026-10-30	2245.50	33333333333333333333333333333333540348409150
193	553	2026-10-30	2604.02	33333333333333333333333333333333543295764109
194	562	2026-10-30	1719.69	33333333333333333333333333333333552137828986
195	565	2026-10-30	2924.58	33333333333333333333333333333333555085183945
196	574	2026-10-30	240.94	33333333333333333333333333333333563927248822
197	577	2026-10-30	883.86	33333333333333333333333333333333566874603781
198	586	2026-10-30	977.19	33333333333333333333333333333333575716668658
199	589	2026-10-30	2228.15	33333333333333333333333333333333578664023617
200	598	2026-10-30	1235.77	33333333333333333333333333333333587506088494
201	2	2026-10-30	1024.55	33333333333333333333333333333333331964903306
202	5	2026-10-30	823.99	33333333333333333333333333333333334912258265
203	14	2026-10-30	2153.45	33333333333333333333333333333333313754323142
204	17	2026-10-30	2101.39	33333333333333333333333333333333316701678101
205	26	2026-10-30	1822.64	33333333333333333333333333333333325543742978
206	29	2026-10-30	2507.00	33333333333333333333333333333333328491097937
207	38	2026-10-30	2279.90	33333333333333333333333333333333337333162814
208	41	2026-10-30	2315.98	33333333333333333333333333333333340280517773
209	50	2026-10-30	2164.89	33333333333333333333333333333333349122582650
210	53	2026-10-30	3335.04	33333333333333333333333333333333352069937609
211	62	2026-10-30	2156.62	33333333333333333333333333333333360912002486
212	65	2026-10-30	2456.99	33333333333333333333333333333333363859357445
213	74	2026-10-30	1050.35	33333333333333333333333333333333372701422322
214	77	2026-10-30	1665.59	33333333333333333333333333333333375648777281
215	86	2026-10-30	1355.86	33333333333333333333333333333333384490842158
216	89	2026-10-30	2624.21	33333333333333333333333333333333387438197117
217	98	2026-10-30	913.72	33333333333333333333333333333333396280261994
218	101	2026-10-30	2062.06	33333333333333333333333333333333399227616953
219	110	2026-10-30	1454.21	33333333333333333333333333333333108069681830
220	113	2026-10-30	2674.13	33333333333333333333333333333333111017036789
221	122	2026-10-30	1024.55	33333333333333333333333333333333119859101666
222	125	2026-10-30	823.99	33333333333333333333333333333333122806456625
223	134	2026-10-30	2153.45	33333333333333333333333333333333131648521502
224	137	2026-10-30	2101.39	33333333333333333333333333333333134595876461
225	146	2026-10-30	1822.64	33333333333333333333333333333333143437941338
226	149	2026-10-30	2507.00	33333333333333333333333333333333146385296297
227	158	2026-10-30	2279.90	33333333333333333333333333333333155227361174
228	161	2026-10-30	2315.98	33333333333333333333333333333333158174716133
229	170	2026-10-30	2164.89	33333333333333333333333333333333167016781010
230	173	2026-10-30	3335.04	33333333333333333333333333333333169964135969
231	182	2026-10-30	2156.62	33333333333333333333333333333333178806200846
232	185	2026-10-30	2456.99	33333333333333333333333333333333181753555805
233	194	2026-10-30	1050.35	33333333333333333333333333333333190595620682
234	197	2026-10-30	1665.59	33333333333333333333333333333333193542975641
235	206	2026-10-30	1355.86	33333333333333333333333333333333202385040518
236	209	2026-10-30	2624.21	33333333333333333333333333333333205332395477
237	218	2026-10-30	913.72	33333333333333333333333333333333214174460354
238	221	2026-10-30	2062.06	33333333333333333333333333333333217121815313
239	230	2026-10-30	1454.21	33333333333333333333333333333333225963880190
240	233	2026-10-30	2674.13	33333333333333333333333333333333228911235149
241	242	2026-10-30	1024.55	33333333333333333333333333333333237753300026
242	245	2026-10-30	823.99	33333333333333333333333333333333240700654985
243	254	2026-10-30	2153.45	33333333333333333333333333333333249542719862
244	257	2026-10-30	2101.39	33333333333333333333333333333333252490074821
245	266	2026-10-30	1822.64	33333333333333333333333333333333261332139698
246	269	2026-10-30	2507.00	33333333333333333333333333333333264279494657
247	278	2026-10-30	2279.90	33333333333333333333333333333333273121559534
248	281	2026-10-30	2315.98	33333333333333333333333333333333276068914493
249	290	2026-10-30	2164.89	33333333333333333333333333333333284910979370
250	293	2026-10-30	3335.04	33333333333333333333333333333333287858334329
251	302	2026-10-30	2156.62	33333333333333333333333333333333296700399206
252	305	2026-10-30	2456.99	33333333333333333333333333333333299647754165
253	314	2026-10-30	1050.35	33333333333333333333333333333333308489819042
254	317	2026-10-30	1665.59	33333333333333333333333333333333311437174001
255	326	2026-10-30	1355.86	33333333333333333333333333333333320279238878
256	329	2026-10-30	2624.21	33333333333333333333333333333333323226593837
257	338	2026-10-30	913.72	33333333333333333333333333333333332068658714
258	341	2026-10-30	2062.06	33333333333333333333333333333333335016013673
259	350	2026-10-30	1454.21	33333333333333333333333333333333343858078550
260	353	2026-10-30	2674.13	33333333333333333333333333333333346805433509
261	362	2026-10-30	1024.55	33333333333333333333333333333333355647498386
262	365	2026-10-30	823.99	33333333333333333333333333333333358594853345
263	374	2026-10-30	2153.45	33333333333333333333333333333333367436918222
264	377	2026-10-30	2101.39	33333333333333333333333333333333370384273181
265	386	2026-10-30	1822.64	33333333333333333333333333333333379226338058
266	389	2026-10-30	2507.00	33333333333333333333333333333333382173693017
267	398	2026-10-30	2279.90	33333333333333333333333333333333391015757894
268	401	2026-10-30	2315.98	33333333333333333333333333333333393963112853
269	410	2026-10-30	2164.89	33333333333333333333333333333333402805177730
270	413	2026-10-30	3335.04	33333333333333333333333333333333405752532689
271	422	2026-10-30	2156.62	33333333333333333333333333333333414594597566
272	425	2026-10-30	2456.99	33333333333333333333333333333333417541952525
273	434	2026-10-30	1050.35	33333333333333333333333333333333426384017402
274	437	2026-10-30	1665.59	33333333333333333333333333333333429331372361
275	446	2026-10-30	1355.86	33333333333333333333333333333333438173437238
276	449	2026-10-30	2624.21	33333333333333333333333333333333441120792197
277	458	2026-10-30	913.72	33333333333333333333333333333333449962857074
278	461	2026-10-30	2062.06	33333333333333333333333333333333452910212033
279	470	2026-10-30	1454.21	33333333333333333333333333333333461752276910
280	473	2026-10-30	2674.13	33333333333333333333333333333333464699631869
281	482	2026-10-30	1024.55	33333333333333333333333333333333473541696746
282	485	2026-10-30	823.99	33333333333333333333333333333333476489051705
283	494	2026-10-30	2153.45	33333333333333333333333333333333485331116582
284	497	2026-10-30	2101.39	33333333333333333333333333333333488278471541
285	506	2026-10-30	1822.64	33333333333333333333333333333333497120536418
286	509	2026-10-30	2507.00	33333333333333333333333333333333500067891377
287	518	2026-10-30	2279.90	33333333333333333333333333333333508909956254
288	521	2026-10-30	2315.98	33333333333333333333333333333333511857311213
289	530	2026-10-30	2164.89	33333333333333333333333333333333520699376090
290	533	2026-10-30	3335.04	33333333333333333333333333333333523646731049
291	542	2026-10-30	2156.62	33333333333333333333333333333333532488795926
292	545	2026-10-30	2456.99	33333333333333333333333333333333535436150885
293	554	2026-10-30	1050.35	33333333333333333333333333333333544278215762
294	557	2026-10-30	1665.59	33333333333333333333333333333333547225570721
295	566	2026-10-30	1355.86	33333333333333333333333333333333556067635598
296	569	2026-10-30	2624.21	33333333333333333333333333333333559014990557
297	578	2026-10-30	913.72	33333333333333333333333333333333567857055434
298	581	2026-10-30	2062.06	33333333333333333333333333333333570804410393
299	590	2026-10-30	1454.21	33333333333333333333333333333333579646475270
300	593	2026-10-30	2674.13	33333333333333333333333333333333582593830229
\.


--
-- Data for Name: payments; Type: TABLE DATA; Schema: billing; Owner: -
--

COPY billing.payments (id, invoice_id, paid_at, amount, method, card_last4, gateway_payload) FROM stdin;
1	1	2026-10-31 00:00:00+00	1656.48	card	0037	\N
2	2	2026-10-31 00:00:00+00	205.47	boleto	\N	\N
3	3	2026-10-31 00:00:00+00	1781.76	pix	\N	\N
4	4	2026-10-31 00:00:00+00	1360.08	card	0148	\N
5	5	2026-10-31 00:00:00+00	1773.60	boleto	\N	\N
6	6	2026-10-31 00:00:00+00	436.44	pix	\N	\N
7	7	2026-10-31 00:00:00+00	776.12	card	0259	\N
8	8	2026-10-31 00:00:00+00	858.57	boleto	\N	\N
9	9	2026-10-31 00:00:00+00	750.44	pix	\N	\N
10	10	2026-10-31 00:00:00+00	1234.74	card	0370	\N
11	11	2026-10-31 00:00:00+00	1661.88	boleto	\N	\N
12	12	2026-10-31 00:00:00+00	890.52	pix	\N	\N
13	13	2026-10-31 00:00:00+00	1768.24	card	0481	\N
14	14	2026-10-31 00:00:00+00	718.43	boleto	\N	\N
15	15	2026-10-31 00:00:00+00	1881.76	pix	\N	\N
16	16	2026-10-31 00:00:00+00	867.21	card	0592	\N
17	17	2026-10-31 00:00:00+00	425.00	boleto	\N	\N
18	18	2026-10-31 00:00:00+00	651.96	pix	\N	\N
19	19	2026-10-31 00:00:00+00	645.24	card	0703	\N
20	20	2026-10-31 00:00:00+00	432.87	boleto	\N	\N
21	21	2026-10-31 00:00:00+00	828.24	pix	\N	\N
22	22	2026-10-31 00:00:00+00	205.47	card	0814	\N
23	23	2026-10-31 00:00:00+00	1781.76	boleto	\N	\N
24	24	2026-10-31 00:00:00+00	1360.08	pix	\N	\N
25	25	2026-10-31 00:00:00+00	1773.60	card	0925	\N
26	26	2026-10-31 00:00:00+00	436.44	boleto	\N	\N
27	27	2026-10-31 00:00:00+00	1552.24	pix	\N	\N
28	28	2026-10-31 00:00:00+00	429.29	card	1036	\N
29	29	2026-10-31 00:00:00+00	750.44	boleto	\N	\N
30	30	2026-10-31 00:00:00+00	1234.74	pix	\N	\N
31	31	2026-10-31 00:00:00+00	1661.88	card	1147	\N
32	32	2026-10-31 00:00:00+00	890.52	boleto	\N	\N
33	33	2026-10-31 00:00:00+00	1768.24	pix	\N	\N
34	34	2026-10-31 00:00:00+00	1436.85	card	1258	\N
35	35	2026-10-31 00:00:00+00	940.88	boleto	\N	\N
36	36	2026-10-31 00:00:00+00	867.21	pix	\N	\N
37	37	2026-10-31 00:00:00+00	425.00	card	1369	\N
38	38	2026-10-31 00:00:00+00	651.96	boleto	\N	\N
39	39	2026-10-31 00:00:00+00	645.24	pix	\N	\N
40	40	2026-10-31 00:00:00+00	432.87	card	1480	\N
41	41	2026-10-31 00:00:00+00	1656.48	boleto	\N	\N
42	42	2026-10-31 00:00:00+00	102.74	pix	\N	\N
43	43	2026-10-31 00:00:00+00	1781.76	card	1591	\N
44	44	2026-10-31 00:00:00+00	1360.08	boleto	\N	\N
45	45	2026-10-31 00:00:00+00	1773.60	pix	\N	\N
46	46	2026-10-31 00:00:00+00	436.44	card	1702	\N
47	47	2026-10-31 00:00:00+00	1552.24	boleto	\N	\N
48	48	2026-10-31 00:00:00+00	858.57	pix	\N	\N
49	49	2026-10-31 00:00:00+00	375.22	card	1813	\N
50	50	2026-10-31 00:00:00+00	1234.74	boleto	\N	\N
51	51	2026-10-31 00:00:00+00	1661.88	pix	\N	\N
52	52	2026-10-31 00:00:00+00	890.52	card	1924	\N
53	53	2026-10-31 00:00:00+00	1768.24	boleto	\N	\N
54	54	2026-10-31 00:00:00+00	1436.85	pix	\N	\N
55	55	2026-10-31 00:00:00+00	1881.76	card	2035	\N
56	56	2026-10-31 00:00:00+00	433.61	boleto	\N	\N
57	57	2026-10-31 00:00:00+00	425.00	pix	\N	\N
58	58	2026-10-31 00:00:00+00	651.96	card	2146	\N
59	59	2026-10-31 00:00:00+00	645.24	boleto	\N	\N
60	60	2026-10-31 00:00:00+00	432.87	pix	\N	\N
61	61	2026-10-31 00:00:00+00	1656.48	card	2257	\N
62	62	2026-10-31 00:00:00+00	205.47	boleto	\N	\N
63	63	2026-10-31 00:00:00+00	890.88	pix	\N	\N
64	64	2026-10-31 00:00:00+00	1360.08	card	2368	\N
65	65	2026-10-31 00:00:00+00	1773.60	boleto	\N	\N
66	66	2026-10-31 00:00:00+00	436.44	pix	\N	\N
67	67	2026-10-31 00:00:00+00	1552.24	card	2479	\N
68	68	2026-10-31 00:00:00+00	858.57	boleto	\N	\N
69	69	2026-10-31 00:00:00+00	750.44	pix	\N	\N
70	70	2026-10-31 00:00:00+00	617.37	card	2590	\N
71	71	2026-10-31 00:00:00+00	1661.88	boleto	\N	\N
72	72	2026-10-31 00:00:00+00	890.52	pix	\N	\N
73	73	2026-10-31 00:00:00+00	1768.24	card	2701	\N
74	74	2026-10-31 00:00:00+00	1436.85	boleto	\N	\N
75	75	2026-10-31 00:00:00+00	1881.76	pix	\N	\N
76	76	2026-10-31 00:00:00+00	867.21	card	2812	\N
77	77	2026-10-31 00:00:00+00	212.50	boleto	\N	\N
78	78	2026-10-31 00:00:00+00	651.96	pix	\N	\N
79	79	2026-10-31 00:00:00+00	645.24	card	2923	\N
80	80	2026-10-31 00:00:00+00	432.87	boleto	\N	\N
81	81	2026-10-31 00:00:00+00	1656.48	pix	\N	\N
82	82	2026-10-31 00:00:00+00	205.47	card	3034	\N
83	83	2026-10-31 00:00:00+00	1781.76	boleto	\N	\N
84	84	2026-10-31 00:00:00+00	680.04	pix	\N	\N
85	85	2026-10-31 00:00:00+00	1773.60	card	3145	\N
86	86	2026-10-31 00:00:00+00	436.44	boleto	\N	\N
87	87	2026-10-31 00:00:00+00	1552.24	pix	\N	\N
88	88	2026-10-31 00:00:00+00	858.57	card	3256	\N
89	89	2026-10-31 00:00:00+00	750.44	boleto	\N	\N
90	90	2026-10-31 00:00:00+00	1234.74	pix	\N	\N
91	91	2026-10-31 00:00:00+00	830.94	card	3367	\N
92	92	2026-10-31 00:00:00+00	890.52	boleto	\N	\N
93	93	2026-10-31 00:00:00+00	1768.24	pix	\N	\N
94	94	2026-10-31 00:00:00+00	1436.85	card	3478	\N
95	95	2026-10-31 00:00:00+00	1881.76	boleto	\N	\N
96	96	2026-10-31 00:00:00+00	867.21	pix	\N	\N
97	97	2026-10-31 00:00:00+00	425.00	card	3589	\N
98	98	2026-10-31 00:00:00+00	325.98	boleto	\N	\N
99	99	2026-10-31 00:00:00+00	645.24	pix	\N	\N
100	100	2026-10-31 00:00:00+00	432.87	card	3700	\N
101	101	2026-10-31 00:00:00+00	1261.55	boleto	\N	\N
102	102	2026-10-31 00:00:00+00	480.04	pix	\N	\N
103	103	2026-10-31 00:00:00+00	1333.11	card	3811	\N
104	104	2026-10-31 00:00:00+00	1290.40	boleto	\N	\N
105	105	2026-10-31 00:00:00+00	158.21	pix	\N	\N
106	106	2026-10-31 00:00:00+00	776.39	card	3922	\N
107	107	2026-10-31 00:00:00+00	1831.88	boleto	\N	\N
108	108	2026-10-31 00:00:00+00	827.48	pix	\N	\N
109	109	2026-10-31 00:00:00+00	2175.07	card	4033	\N
110	110	2026-10-31 00:00:00+00	879.96	boleto	\N	\N
111	111	2026-10-31 00:00:00+00	2675.59	pix	\N	\N
112	112	2026-10-31 00:00:00+00	1122.75	card	4144	\N
113	113	2026-10-31 00:00:00+00	2604.02	boleto	\N	\N
114	114	2026-10-31 00:00:00+00	1719.69	pix	\N	\N
115	115	2026-10-31 00:00:00+00	2924.58	card	4255	\N
116	116	2026-10-31 00:00:00+00	240.94	boleto	\N	\N
117	117	2026-10-31 00:00:00+00	883.86	pix	\N	\N
118	118	2026-10-31 00:00:00+00	977.19	card	4366	\N
119	119	2026-10-31 00:00:00+00	1114.08	boleto	\N	\N
120	120	2026-10-31 00:00:00+00	1235.77	pix	\N	\N
121	121	2026-10-31 00:00:00+00	1261.55	card	4477	\N
122	122	2026-10-31 00:00:00+00	480.04	boleto	\N	\N
123	123	2026-10-31 00:00:00+00	1333.11	pix	\N	\N
124	124	2026-10-31 00:00:00+00	1290.40	card	4588	\N
125	125	2026-10-31 00:00:00+00	316.41	boleto	\N	\N
126	126	2026-10-31 00:00:00+00	388.20	pix	\N	\N
127	127	2026-10-31 00:00:00+00	1831.88	card	4699	\N
128	128	2026-10-31 00:00:00+00	827.48	boleto	\N	\N
129	129	2026-10-31 00:00:00+00	2175.07	pix	\N	\N
130	130	2026-10-31 00:00:00+00	879.96	card	4810	\N
131	131	2026-10-31 00:00:00+00	2675.59	boleto	\N	\N
132	132	2026-10-31 00:00:00+00	2245.50	pix	\N	\N
133	133	2026-10-31 00:00:00+00	1302.01	card	4921	\N
134	134	2026-10-31 00:00:00+00	1719.69	boleto	\N	\N
135	135	2026-10-31 00:00:00+00	2924.58	pix	\N	\N
136	136	2026-10-31 00:00:00+00	240.94	card	5032	\N
137	137	2026-10-31 00:00:00+00	883.86	boleto	\N	\N
138	138	2026-10-31 00:00:00+00	977.19	pix	\N	\N
139	139	2026-10-31 00:00:00+00	2228.15	card	5143	\N
140	140	2026-10-31 00:00:00+00	617.89	boleto	\N	\N
141	141	2026-10-31 00:00:00+00	1261.55	pix	\N	\N
142	142	2026-10-31 00:00:00+00	480.04	card	5254	\N
143	143	2026-10-31 00:00:00+00	1333.11	boleto	\N	\N
144	144	2026-10-31 00:00:00+00	1290.40	pix	\N	\N
145	145	2026-10-31 00:00:00+00	316.41	card	5365	\N
146	146	2026-10-31 00:00:00+00	776.39	boleto	\N	\N
147	147	2026-10-31 00:00:00+00	915.94	pix	\N	\N
148	148	2026-10-31 00:00:00+00	827.48	card	5476	\N
149	149	2026-10-31 00:00:00+00	2175.07	boleto	\N	\N
150	150	2026-10-31 00:00:00+00	879.96	pix	\N	\N
151	151	2026-10-31 00:00:00+00	2675.59	card	5587	\N
152	152	2026-10-31 00:00:00+00	2245.50	boleto	\N	\N
153	153	2026-10-31 00:00:00+00	2604.02	pix	\N	\N
154	154	2026-10-31 00:00:00+00	859.85	card	5698	\N
155	155	2026-10-31 00:00:00+00	2924.58	boleto	\N	\N
156	156	2026-10-31 00:00:00+00	240.94	pix	\N	\N
157	157	2026-10-31 00:00:00+00	883.86	card	5809	\N
158	158	2026-10-31 00:00:00+00	977.19	boleto	\N	\N
159	159	2026-10-31 00:00:00+00	2228.15	pix	\N	\N
160	160	2026-10-31 00:00:00+00	1235.77	card	5920	\N
161	161	2026-10-31 00:00:00+00	630.78	boleto	\N	\N
162	162	2026-10-31 00:00:00+00	480.04	pix	\N	\N
163	163	2026-10-31 00:00:00+00	1333.11	card	6031	\N
164	164	2026-10-31 00:00:00+00	1290.40	boleto	\N	\N
165	165	2026-10-31 00:00:00+00	316.41	pix	\N	\N
166	166	2026-10-31 00:00:00+00	776.39	card	6142	\N
167	167	2026-10-31 00:00:00+00	1831.88	boleto	\N	\N
168	168	2026-10-31 00:00:00+00	413.74	pix	\N	\N
169	169	2026-10-31 00:00:00+00	2175.07	card	6253	\N
170	170	2026-10-31 00:00:00+00	879.96	boleto	\N	\N
171	171	2026-10-31 00:00:00+00	2675.59	pix	\N	\N
172	172	2026-10-31 00:00:00+00	2245.50	card	6364	\N
173	173	2026-10-31 00:00:00+00	2604.02	boleto	\N	\N
174	174	2026-10-31 00:00:00+00	1719.69	pix	\N	\N
175	175	2026-10-31 00:00:00+00	1462.29	card	6475	\N
176	176	2026-10-31 00:00:00+00	240.94	boleto	\N	\N
177	177	2026-10-31 00:00:00+00	883.86	pix	\N	\N
178	178	2026-10-31 00:00:00+00	977.19	card	6586	\N
179	179	2026-10-31 00:00:00+00	2228.15	boleto	\N	\N
180	180	2026-10-31 00:00:00+00	1235.77	pix	\N	\N
181	181	2026-10-31 00:00:00+00	1261.55	card	6697	\N
182	182	2026-10-31 00:00:00+00	240.02	boleto	\N	\N
183	183	2026-10-31 00:00:00+00	1333.11	pix	\N	\N
184	184	2026-10-31 00:00:00+00	1290.40	card	6808	\N
185	185	2026-10-31 00:00:00+00	316.41	boleto	\N	\N
186	186	2026-10-31 00:00:00+00	776.39	pix	\N	\N
187	187	2026-10-31 00:00:00+00	1831.88	card	6919	\N
188	188	2026-10-31 00:00:00+00	827.48	boleto	\N	\N
189	189	2026-10-31 00:00:00+00	1087.54	pix	\N	\N
190	190	2026-10-31 00:00:00+00	879.96	card	7030	\N
191	191	2026-10-31 00:00:00+00	2675.59	boleto	\N	\N
192	192	2026-10-31 00:00:00+00	2245.50	pix	\N	\N
193	193	2026-10-31 00:00:00+00	2604.02	card	7141	\N
194	194	2026-10-31 00:00:00+00	1719.69	boleto	\N	\N
195	195	2026-10-31 00:00:00+00	2924.58	pix	\N	\N
196	196	2026-10-31 00:00:00+00	120.47	card	7252	\N
197	197	2026-10-31 00:00:00+00	883.86	boleto	\N	\N
198	198	2026-10-31 00:00:00+00	977.19	pix	\N	\N
199	199	2026-10-31 00:00:00+00	2228.15	card	7363	\N
200	200	2026-10-31 00:00:00+00	1235.77	boleto	\N	\N
201	201	2026-10-31 00:00:00+00	1024.55	pix	\N	\N
202	202	2026-10-31 00:00:00+00	823.99	card	7474	\N
203	203	2026-10-31 00:00:00+00	1076.73	boleto	\N	\N
204	204	2026-10-31 00:00:00+00	2101.39	pix	\N	\N
205	205	2026-10-31 00:00:00+00	1822.64	card	7585	\N
206	206	2026-10-31 00:00:00+00	2507.00	boleto	\N	\N
207	207	2026-10-31 00:00:00+00	2279.90	pix	\N	\N
208	208	2026-10-31 00:00:00+00	2315.98	card	7696	\N
209	209	2026-10-31 00:00:00+00	2164.89	boleto	\N	\N
210	210	2026-10-31 00:00:00+00	1667.52	pix	\N	\N
211	211	2026-10-31 00:00:00+00	2156.62	card	7807	\N
212	212	2026-10-31 00:00:00+00	2456.99	boleto	\N	\N
213	213	2026-10-31 00:00:00+00	1050.35	pix	\N	\N
214	214	2026-10-31 00:00:00+00	1665.59	card	7918	\N
215	215	2026-10-31 00:00:00+00	1355.86	boleto	\N	\N
216	216	2026-10-31 00:00:00+00	2624.21	pix	\N	\N
217	217	2026-10-31 00:00:00+00	456.86	card	8029	\N
218	218	2026-10-31 00:00:00+00	2062.06	boleto	\N	\N
219	219	2026-10-31 00:00:00+00	1454.21	pix	\N	\N
220	220	2026-10-31 00:00:00+00	2674.13	card	8140	\N
221	221	2026-10-31 00:00:00+00	1024.55	boleto	\N	\N
222	222	2026-10-31 00:00:00+00	823.99	pix	\N	\N
223	223	2026-10-31 00:00:00+00	2153.45	card	8251	\N
224	224	2026-10-31 00:00:00+00	1050.70	boleto	\N	\N
225	225	2026-10-31 00:00:00+00	1822.64	pix	\N	\N
226	226	2026-10-31 00:00:00+00	2507.00	card	8362	\N
227	227	2026-10-31 00:00:00+00	2279.90	boleto	\N	\N
228	228	2026-10-31 00:00:00+00	2315.98	pix	\N	\N
229	229	2026-10-31 00:00:00+00	2164.89	card	8473	\N
230	230	2026-10-31 00:00:00+00	3335.04	boleto	\N	\N
231	231	2026-10-31 00:00:00+00	1078.31	pix	\N	\N
232	232	2026-10-31 00:00:00+00	2456.99	card	8584	\N
233	233	2026-10-31 00:00:00+00	1050.35	boleto	\N	\N
234	234	2026-10-31 00:00:00+00	1665.59	pix	\N	\N
235	235	2026-10-31 00:00:00+00	1355.86	card	8695	\N
236	236	2026-10-31 00:00:00+00	2624.21	boleto	\N	\N
237	237	2026-10-31 00:00:00+00	913.72	pix	\N	\N
238	238	2026-10-31 00:00:00+00	1031.03	card	8806	\N
239	239	2026-10-31 00:00:00+00	1454.21	boleto	\N	\N
240	240	2026-10-31 00:00:00+00	2674.13	pix	\N	\N
241	241	2026-10-31 00:00:00+00	1024.55	card	8917	\N
242	242	2026-10-31 00:00:00+00	823.99	boleto	\N	\N
243	243	2026-10-31 00:00:00+00	2153.45	pix	\N	\N
244	244	2026-10-31 00:00:00+00	2101.39	card	9028	\N
245	245	2026-10-31 00:00:00+00	911.32	boleto	\N	\N
246	246	2026-10-31 00:00:00+00	2507.00	pix	\N	\N
247	247	2026-10-31 00:00:00+00	2279.90	card	9139	\N
248	248	2026-10-31 00:00:00+00	2315.98	boleto	\N	\N
249	249	2026-10-31 00:00:00+00	2164.89	pix	\N	\N
250	250	2026-10-31 00:00:00+00	3335.04	card	9250	\N
251	251	2026-10-31 00:00:00+00	2156.62	boleto	\N	\N
252	252	2026-10-31 00:00:00+00	1228.50	pix	\N	\N
253	253	2026-10-31 00:00:00+00	1050.35	card	9361	\N
254	254	2026-10-31 00:00:00+00	1665.59	boleto	\N	\N
255	255	2026-10-31 00:00:00+00	1355.86	pix	\N	\N
256	256	2026-10-31 00:00:00+00	2624.21	card	9472	\N
257	257	2026-10-31 00:00:00+00	913.72	boleto	\N	\N
258	258	2026-10-31 00:00:00+00	2062.06	pix	\N	\N
259	259	2026-10-31 00:00:00+00	727.11	card	9583	\N
260	260	2026-10-31 00:00:00+00	2674.13	boleto	\N	\N
261	261	2026-10-31 00:00:00+00	1024.55	pix	\N	\N
262	262	2026-10-31 00:00:00+00	823.99	card	9694	\N
263	263	2026-10-31 00:00:00+00	2153.45	boleto	\N	\N
264	264	2026-10-31 00:00:00+00	2101.39	pix	\N	\N
265	265	2026-10-31 00:00:00+00	1822.64	card	9805	\N
266	266	2026-10-31 00:00:00+00	1253.50	boleto	\N	\N
267	267	2026-10-31 00:00:00+00	2279.90	pix	\N	\N
268	268	2026-10-31 00:00:00+00	2315.98	card	9916	\N
269	269	2026-10-31 00:00:00+00	2164.89	boleto	\N	\N
270	270	2026-10-31 00:00:00+00	3335.04	pix	\N	\N
271	271	2026-10-31 00:00:00+00	2156.62	card	0027	\N
272	272	2026-10-31 00:00:00+00	2456.99	boleto	\N	\N
273	273	2026-10-31 00:00:00+00	525.18	pix	\N	\N
274	274	2026-10-31 00:00:00+00	1665.59	card	0138	\N
275	275	2026-10-31 00:00:00+00	1355.86	boleto	\N	\N
276	276	2026-10-31 00:00:00+00	2624.21	pix	\N	\N
277	277	2026-10-31 00:00:00+00	913.72	card	0249	\N
278	278	2026-10-31 00:00:00+00	2062.06	boleto	\N	\N
279	279	2026-10-31 00:00:00+00	1454.21	pix	\N	\N
280	280	2026-10-31 00:00:00+00	1337.07	card	0360	\N
281	281	2026-10-31 00:00:00+00	1024.55	boleto	\N	\N
282	282	2026-10-31 00:00:00+00	823.99	pix	\N	\N
283	283	2026-10-31 00:00:00+00	2153.45	card	0471	\N
284	284	2026-10-31 00:00:00+00	2101.39	boleto	\N	\N
285	285	2026-10-31 00:00:00+00	1822.64	pix	\N	\N
286	286	2026-10-31 00:00:00+00	2507.00	card	0582	\N
287	287	2026-10-31 00:00:00+00	1139.95	boleto	\N	\N
288	288	2026-10-31 00:00:00+00	2315.98	pix	\N	\N
289	289	2026-10-31 00:00:00+00	2164.89	card	0693	\N
290	290	2026-10-31 00:00:00+00	3335.04	boleto	\N	\N
291	291	2026-10-31 00:00:00+00	2156.62	pix	\N	\N
292	292	2026-10-31 00:00:00+00	2456.99	card	0804	\N
293	293	2026-10-31 00:00:00+00	1050.35	boleto	\N	\N
294	294	2026-10-31 00:00:00+00	832.80	pix	\N	\N
295	295	2026-10-31 00:00:00+00	1355.86	card	0915	\N
296	296	2026-10-31 00:00:00+00	2624.21	boleto	\N	\N
297	297	2026-10-31 00:00:00+00	913.72	pix	\N	\N
298	298	2026-10-31 00:00:00+00	2062.06	card	1026	\N
299	299	2026-10-31 00:00:00+00	1454.21	boleto	\N	\N
300	300	2026-10-31 00:00:00+00	2674.13	pix	\N	\N
\.


--
-- Data for Name: refunds; Type: TABLE DATA; Schema: billing; Owner: -
--

COPY billing.refunds (id, order_id, line, amount, reason) FROM stdin;
1	50	1	284.66	Arrived broken
2	100	1	188.43	Arrived broken
3	150	1	443.40	Arrived broken
4	200	1	326.61	Arrived broken
5	250	1	85.32	Arrived broken
6	300	1	275.81	Arrived broken
7	350	1	256.80	Arrived broken
8	400	1	64.78	Arrived broken
9	450	1	470.44	Arrived broken
10	500	1	184.00	Arrived broken
11	550	1	439.20	Arrived broken
12	600	1	200.73	Arrived broken
\.


--
-- Data for Name: categories; Type: TABLE DATA; Schema: catalog; Owner: -
--

COPY catalog.categories (id, parent_id, name, slug) FROM stdin;
1	\N	Electronics	electronics
2	\N	Home	home
3	\N	Books	books
4	1	Electronics Basics	electronics-basics
5	1	Electronics Premium	electronics-premium
6	2	Home Basics	home-basics
7	2	Home Premium	home-premium
8	3	Books Basics	books-basics
9	3	Books Premium	books-premium
\.


--
-- Data for Name: price_history; Type: TABLE DATA; Schema: catalog; Owner: -
--

COPY catalog.price_history (product_id, valid_during, price) FROM stdin;
1	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	336.64
2	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	168.85
3	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	422.05
4	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	37.37
5	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	50.57
6	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	103.31
7	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	225.48
8	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	180.66
9	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	262.79
10	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	341.50
11	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	260.16
12	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	436.53
13	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	378.72
14	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	373.92
15	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	66.69
16	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	94.59
17	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	146.54
18	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	395.28
19	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	45.19
20	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	366.53
21	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	189.67
22	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	148.85
23	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	195.59
24	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	214.22
25	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	439.83
26	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	397.85
27	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	424.99
28	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	165.60
29	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	224.76
30	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	290.50
31	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	99.88
32	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	290.05
33	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	128.87
34	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	182.59
35	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	129.86
36	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	62.58
37	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	385.71
38	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	423.40
39	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	354.32
40	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	88.86
41	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	373.30
42	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	17.29
43	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	112.43
44	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	294.48
45	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	413.49
46	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	18.11
47	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	61.64
48	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	58.30
49	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	147.69
50	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	95.63
51	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	91.77
52	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	425.95
53	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	56.65
54	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	165.72
55	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	287.78
56	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	82.78
57	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	21.81
58	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	231.12
59	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	408.02
60	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	346.64
61	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	216.60
62	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	145.18
63	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	19.32
64	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	403.73
65	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	19.07
66	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	168.61
67	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	127.11
68	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	248.23
69	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	447.18
70	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	56.70
71	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	130.93
72	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	182.62
73	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	437.77
74	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	372.71
75	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	162.25
76	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	156.57
77	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	151.10
78	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	76.79
79	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	151.28
80	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	297.73
81	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	384.15
82	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	290.48
83	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	257.57
84	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	272.10
85	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	124.88
86	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	400.90
87	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	251.61
88	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	293.95
89	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	95.63
90	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	224.64
91	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	445.03
92	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	48.52
93	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	26.96
94	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	300.68
95	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	370.42
96	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	340.27
97	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	262.80
98	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	399.06
99	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	426.83
100	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	74.29
101	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	98.48
102	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	72.87
103	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	141.53
104	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	125.53
105	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	70.20
106	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	281.89
107	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	267.16
108	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	169.59
109	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	407.26
110	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	349.25
111	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	439.61
112	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	425.78
113	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	395.48
114	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	102.02
115	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	186.95
116	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	447.96
117	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	389.70
118	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	256.19
119	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	431.06
120	["2025-01-01 00:00:00+00","2025-07-01 00:00:00+00")	264.44
1	["2025-07-01 00:00:00+00",)	374.04
2	["2025-07-01 00:00:00+00",)	187.61
3	["2025-07-01 00:00:00+00",)	468.94
4	["2025-07-01 00:00:00+00",)	41.52
5	["2025-07-01 00:00:00+00",)	56.19
6	["2025-07-01 00:00:00+00",)	114.79
7	["2025-07-01 00:00:00+00",)	250.53
8	["2025-07-01 00:00:00+00",)	200.73
9	["2025-07-01 00:00:00+00",)	291.99
10	["2025-07-01 00:00:00+00",)	379.44
11	["2025-07-01 00:00:00+00",)	289.07
12	["2025-07-01 00:00:00+00",)	485.03
13	["2025-07-01 00:00:00+00",)	420.80
14	["2025-07-01 00:00:00+00",)	415.47
15	["2025-07-01 00:00:00+00",)	74.10
16	["2025-07-01 00:00:00+00",)	105.10
17	["2025-07-01 00:00:00+00",)	162.82
18	["2025-07-01 00:00:00+00",)	439.20
19	["2025-07-01 00:00:00+00",)	50.21
20	["2025-07-01 00:00:00+00",)	407.25
21	["2025-07-01 00:00:00+00",)	210.74
22	["2025-07-01 00:00:00+00",)	165.39
23	["2025-07-01 00:00:00+00",)	217.32
24	["2025-07-01 00:00:00+00",)	238.02
25	["2025-07-01 00:00:00+00",)	488.70
26	["2025-07-01 00:00:00+00",)	442.06
27	["2025-07-01 00:00:00+00",)	472.21
28	["2025-07-01 00:00:00+00",)	184.00
29	["2025-07-01 00:00:00+00",)	249.73
30	["2025-07-01 00:00:00+00",)	322.78
31	["2025-07-01 00:00:00+00",)	110.98
32	["2025-07-01 00:00:00+00",)	322.28
33	["2025-07-01 00:00:00+00",)	143.19
34	["2025-07-01 00:00:00+00",)	202.88
35	["2025-07-01 00:00:00+00",)	144.29
36	["2025-07-01 00:00:00+00",)	69.53
37	["2025-07-01 00:00:00+00",)	428.57
38	["2025-07-01 00:00:00+00",)	470.44
39	["2025-07-01 00:00:00+00",)	393.69
40	["2025-07-01 00:00:00+00",)	98.73
41	["2025-07-01 00:00:00+00",)	414.78
42	["2025-07-01 00:00:00+00",)	19.21
43	["2025-07-01 00:00:00+00",)	124.92
44	["2025-07-01 00:00:00+00",)	327.20
45	["2025-07-01 00:00:00+00",)	459.43
46	["2025-07-01 00:00:00+00",)	20.12
47	["2025-07-01 00:00:00+00",)	68.49
48	["2025-07-01 00:00:00+00",)	64.78
49	["2025-07-01 00:00:00+00",)	164.10
50	["2025-07-01 00:00:00+00",)	106.25
51	["2025-07-01 00:00:00+00",)	101.97
52	["2025-07-01 00:00:00+00",)	473.28
53	["2025-07-01 00:00:00+00",)	62.94
54	["2025-07-01 00:00:00+00",)	184.13
55	["2025-07-01 00:00:00+00",)	319.76
56	["2025-07-01 00:00:00+00",)	91.98
57	["2025-07-01 00:00:00+00",)	24.23
58	["2025-07-01 00:00:00+00",)	256.80
59	["2025-07-01 00:00:00+00",)	453.36
60	["2025-07-01 00:00:00+00",)	385.15
61	["2025-07-01 00:00:00+00",)	240.67
62	["2025-07-01 00:00:00+00",)	161.31
63	["2025-07-01 00:00:00+00",)	21.47
64	["2025-07-01 00:00:00+00",)	448.59
65	["2025-07-01 00:00:00+00",)	21.19
66	["2025-07-01 00:00:00+00",)	187.34
67	["2025-07-01 00:00:00+00",)	141.23
68	["2025-07-01 00:00:00+00",)	275.81
69	["2025-07-01 00:00:00+00",)	496.87
70	["2025-07-01 00:00:00+00",)	63.00
71	["2025-07-01 00:00:00+00",)	145.48
72	["2025-07-01 00:00:00+00",)	202.91
73	["2025-07-01 00:00:00+00",)	486.41
74	["2025-07-01 00:00:00+00",)	414.12
75	["2025-07-01 00:00:00+00",)	180.28
76	["2025-07-01 00:00:00+00",)	173.97
77	["2025-07-01 00:00:00+00",)	167.89
78	["2025-07-01 00:00:00+00",)	85.32
79	["2025-07-01 00:00:00+00",)	168.09
80	["2025-07-01 00:00:00+00",)	330.81
81	["2025-07-01 00:00:00+00",)	426.83
82	["2025-07-01 00:00:00+00",)	322.76
83	["2025-07-01 00:00:00+00",)	286.19
84	["2025-07-01 00:00:00+00",)	302.33
85	["2025-07-01 00:00:00+00",)	138.76
86	["2025-07-01 00:00:00+00",)	445.44
87	["2025-07-01 00:00:00+00",)	279.57
88	["2025-07-01 00:00:00+00",)	326.61
89	["2025-07-01 00:00:00+00",)	106.25
90	["2025-07-01 00:00:00+00",)	249.60
91	["2025-07-01 00:00:00+00",)	494.48
92	["2025-07-01 00:00:00+00",)	53.91
93	["2025-07-01 00:00:00+00",)	29.95
94	["2025-07-01 00:00:00+00",)	334.09
95	["2025-07-01 00:00:00+00",)	411.58
96	["2025-07-01 00:00:00+00",)	378.08
97	["2025-07-01 00:00:00+00",)	292.00
98	["2025-07-01 00:00:00+00",)	443.40
99	["2025-07-01 00:00:00+00",)	474.25
100	["2025-07-01 00:00:00+00",)	82.54
101	["2025-07-01 00:00:00+00",)	109.42
102	["2025-07-01 00:00:00+00",)	80.97
103	["2025-07-01 00:00:00+00",)	157.25
104	["2025-07-01 00:00:00+00",)	139.48
105	["2025-07-01 00:00:00+00",)	78.00
106	["2025-07-01 00:00:00+00",)	313.21
107	["2025-07-01 00:00:00+00",)	296.84
108	["2025-07-01 00:00:00+00",)	188.43
109	["2025-07-01 00:00:00+00",)	452.51
110	["2025-07-01 00:00:00+00",)	388.06
111	["2025-07-01 00:00:00+00",)	488.46
112	["2025-07-01 00:00:00+00",)	473.09
113	["2025-07-01 00:00:00+00",)	439.42
114	["2025-07-01 00:00:00+00",)	113.36
115	["2025-07-01 00:00:00+00",)	207.72
116	["2025-07-01 00:00:00+00",)	497.73
117	["2025-07-01 00:00:00+00",)	433.00
118	["2025-07-01 00:00:00+00",)	284.66
119	["2025-07-01 00:00:00+00",)	478.95
120	["2025-07-01 00:00:00+00",)	293.82
\.


--
-- Data for Name: products; Type: TABLE DATA; Schema: catalog; Owner: -
--

COPY catalog.products (id, sku, name, description, category_id, price, cost, tags, attributes, active, created_at) FROM stdin;
1	SKU-00001	Kettle 1	Product number 1	2	374.04	247.78	{sale}	{"colour": "blue", "weight_g": 107}	t	2026-10-30 14:05:25.929607+00
2	SKU-00002	Novel 2	Product number 2	3	187.61	81.73	{gift}	{"colour": "black", "weight_g": 114}	t	2026-10-30 14:05:25.929607+00
3	SKU-00003	Headphones 3	Product number 3	4	468.94	341.24	{eco}	{"colour": "white", "weight_g": 121}	t	2026-10-30 14:05:25.929607+00
4	SKU-00004	Mug 4	Product number 4	5	41.52	24.43	{new}	{"colour": "red", "weight_g": 128}	t	2026-10-30 14:05:25.929607+00
5	SKU-00005	Charger 5	Product number 5	6	56.19	33.78	{sale}	{"colour": "blue", "weight_g": 135}	t	2026-10-30 14:05:25.929607+00
6	SKU-00006	Atlas 6	Product number 6	7	114.79	73.96	{gift}	{"colour": "black", "weight_g": 142}	t	2026-10-30 14:05:25.929607+00
7	SKU-00007	Blanket 7	Product number 7	8	250.53	143.91	{eco}	{"colour": "white", "weight_g": 149}	t	2026-10-30 14:05:25.929607+00
8	SKU-00008	Lamp 8	Product number 8	9	200.73	146.59	{new}	{"colour": "red", "weight_g": 156}	t	2026-10-30 14:05:25.929607+00
9	SKU-00009	Kettle 9	Product number 9	1	291.99	118.07	{sale}	{"colour": "blue", "weight_g": 163}	t	2026-10-30 14:05:25.929607+00
10	SKU-00010	Novel 10	Product number 10	2	379.44	303.14	{gift}	{"colour": "black", "weight_g": 170}	t	2026-10-30 14:05:25.929607+00
11	SKU-00011	Headphones 11	Product number 11	3	289.07	134.38	{eco}	{"colour": "white", "weight_g": 177}	t	2026-10-30 14:05:25.929607+00
12	SKU-00012	Mug 12	Product number 12	4	485.03	283.72	{new}	{"colour": "red", "weight_g": 184}	t	2026-10-30 14:05:25.929607+00
13	SKU-00013	Charger 13	Product number 13	5	420.80	262.87	{sale}	{"colour": "blue", "weight_g": 191}	t	2026-10-30 14:05:25.929607+00
14	SKU-00014	Atlas 14	Product number 14	6	415.47	272.31	{gift}	{"colour": "black", "weight_g": 198}	t	2026-10-30 14:05:25.929607+00
15	SKU-00015	Blanket 15	Product number 15	7	74.10	56.63	{eco}	{"colour": "white", "weight_g": 205}	t	2026-10-30 14:05:25.929607+00
16	SKU-00016	Lamp 16	Product number 16	8	105.10	78.81	{new}	{"colour": "red", "weight_g": 212}	t	2026-10-30 14:05:25.929607+00
17	SKU-00017	Kettle 17	Product number 17	9	162.82	100.93	{sale}	{"colour": "blue", "weight_g": 219}	t	2026-10-30 14:05:25.929607+00
18	SKU-00018	Novel 18	Product number 18	1	439.20	313.48	{gift}	{"colour": "black", "weight_g": 226}	t	2026-10-30 14:05:25.929607+00
19	SKU-00019	Headphones 19	Product number 19	2	50.21	23.83	{eco}	{"colour": "white", "weight_g": 233}	t	2026-10-30 14:05:25.929607+00
20	SKU-00020	Mug 20	Product number 20	3	407.25	170.70	{new}	{"colour": "red", "weight_g": 240}	t	2026-10-30 14:05:25.929607+00
21	SKU-00021	Charger 21	Product number 21	4	210.74	129.59	{sale}	{"colour": "blue", "weight_g": 247}	t	2026-10-30 14:05:25.929607+00
22	SKU-00022	Atlas 22	Product number 22	5	165.39	132.20	{gift}	{"colour": "black", "weight_g": 254}	t	2026-10-30 14:05:25.929607+00
23	SKU-00023	Blanket 23	Product number 23	6	217.32	156.87	{eco}	{"colour": "white", "weight_g": 261}	t	2026-10-30 14:05:25.929607+00
24	SKU-00024	Lamp 24	Product number 24	7	238.02	159.39	{new}	{"colour": "red", "weight_g": 268}	t	2026-10-30 14:05:25.929607+00
25	SKU-00025	Kettle 25	Product number 25	8	488.70	316.15	{sale}	{"colour": "blue", "weight_g": 275}	t	2026-10-30 14:05:25.929607+00
26	SKU-00026	Novel 26	Product number 26	9	442.06	297.51	{gift}	{"colour": "black", "weight_g": 282}	t	2026-10-30 14:05:25.929607+00
27	SKU-00027	Headphones 27	Product number 27	1	472.21	353.58	{eco}	{"colour": "white", "weight_g": 289}	t	2026-10-30 14:05:25.929607+00
28	SKU-00028	Mug 28	Product number 28	2	184.00	140.82	{new}	{"colour": "red", "weight_g": 296}	t	2026-10-30 14:05:25.929607+00
29	SKU-00029	Charger 29	Product number 29	3	249.73	145.04	{sale}	{"colour": "blue", "weight_g": 303}	t	2026-10-30 14:05:25.929607+00
30	SKU-00030	Atlas 30	Product number 30	4	322.78	246.04	{gift}	{"colour": "black", "weight_g": 310}	t	2026-10-30 14:05:25.929607+00
31	SKU-00031	Blanket 31	Product number 31	5	110.98	88.63	{eco}	{"colour": "white", "weight_g": 317}	t	2026-10-30 14:05:25.929607+00
32	SKU-00032	Lamp 32	Product number 32	6	322.28	197.57	{new}	{"colour": "red", "weight_g": 324}	t	2026-10-30 14:05:25.929607+00
33	SKU-00033	Kettle 33	Product number 33	7	143.19	89.55	{sale}	{"colour": "blue", "weight_g": 331}	t	2026-10-30 14:05:25.929607+00
34	SKU-00034	Novel 34	Product number 34	8	202.88	116.11	{gift}	{"colour": "black", "weight_g": 338}	t	2026-10-30 14:05:25.929607+00
35	SKU-00035	Headphones 35	Product number 35	9	144.29	110.00	{eco}	{"colour": "white", "weight_g": 345}	t	2026-10-30 14:05:25.929607+00
36	SKU-00036	Mug 36	Product number 36	1	69.53	42.03	{new}	{"colour": "red", "weight_g": 352}	t	2026-10-30 14:05:25.929607+00
37	SKU-00037	Charger 37	Product number 37	2	428.57	333.99	{sale}	{"colour": "blue", "weight_g": 359}	t	2026-10-30 14:05:25.929607+00
38	SKU-00038	Atlas 38	Product number 38	3	470.44	256.95	{gift}	{"colour": "black", "weight_g": 366}	t	2026-10-30 14:05:25.929607+00
39	SKU-00039	Blanket 39	Product number 39	4	393.69	216.75	{eco}	{"colour": "white", "weight_g": 373}	t	2026-10-30 14:05:25.929607+00
40	SKU-00040	Lamp 40	Product number 40	5	98.73	64.49	{new}	{"colour": "red", "weight_g": 380}	t	2026-10-30 14:05:25.929607+00
41	SKU-00041	Kettle 41	Product number 41	6	414.78	203.59	{sale}	{"colour": "blue", "weight_g": 387}	t	2026-10-30 14:05:25.929607+00
42	SKU-00042	Novel 42	Product number 42	7	19.21	10.88	{gift}	{"colour": "black", "weight_g": 394}	t	2026-10-30 14:05:25.929607+00
43	SKU-00043	Headphones 43	Product number 43	8	124.92	88.57	{eco}	{"colour": "white", "weight_g": 401}	t	2026-10-30 14:05:25.929607+00
44	SKU-00044	Mug 44	Product number 44	9	327.20	251.89	{new}	{"colour": "red", "weight_g": 408}	t	2026-10-30 14:05:25.929607+00
45	SKU-00045	Charger 45	Product number 45	1	459.43	228.08	{sale}	{"colour": "blue", "weight_g": 415}	t	2026-10-30 14:05:25.929607+00
46	SKU-00046	Atlas 46	Product number 46	2	20.12	11.28	{gift}	{"colour": "black", "weight_g": 422}	t	2026-10-30 14:05:25.929607+00
47	SKU-00047	Blanket 47	Product number 47	3	68.49	31.66	{eco}	{"colour": "white", "weight_g": 429}	t	2026-10-30 14:05:25.929607+00
48	SKU-00048	Lamp 48	Product number 48	4	64.78	37.07	{new}	{"colour": "red", "weight_g": 436}	t	2026-10-30 14:05:25.929607+00
49	SKU-00049	Kettle 49	Product number 49	5	164.10	92.98	{sale}	{"colour": "blue", "weight_g": 443}	t	2026-10-30 14:05:25.929607+00
50	SKU-00050	Novel 50	Product number 50	6	106.25	82.94	{gift}	{"colour": "black", "weight_g": 450}	t	2026-10-30 14:05:25.929607+00
51	SKU-00051	Headphones 51	Product number 51	7	101.97	77.44	{eco}	{"colour": "white", "weight_g": 457}	t	2026-10-30 14:05:25.929607+00
52	SKU-00052	Mug 52	Product number 52	8	473.28	211.69	{new}	{"colour": "red", "weight_g": 464}	t	2026-10-30 14:05:25.929607+00
53	SKU-00053	Charger 53	Product number 53	9	62.94	31.05	{sale}	{"colour": "blue", "weight_g": 471}	t	2026-10-30 14:05:25.929607+00
54	SKU-00054	Atlas 54	Product number 54	1	184.13	114.38	{gift}	{"colour": "black", "weight_g": 478}	t	2026-10-30 14:05:25.929607+00
55	SKU-00055	Blanket 55	Product number 55	2	319.76	241.59	{eco}	{"colour": "white", "weight_g": 485}	t	2026-10-30 14:05:25.929607+00
56	SKU-00056	Lamp 56	Product number 56	3	91.98	43.14	{new}	{"colour": "red", "weight_g": 492}	t	2026-10-30 14:05:25.929607+00
57	SKU-00057	Kettle 57	Product number 57	4	24.23	16.01	{sale}	{"colour": "blue", "weight_g": 499}	t	2026-10-30 14:05:25.929607+00
58	SKU-00058	Novel 58	Product number 58	5	256.80	187.43	{gift}	{"colour": "black", "weight_g": 506}	t	2026-10-30 14:05:25.929607+00
59	SKU-00059	Headphones 59	Product number 59	6	453.36	358.68	{eco}	{"colour": "white", "weight_g": 513}	t	2026-10-30 14:05:25.929607+00
60	SKU-00060	Mug 60	Product number 60	7	385.15	269.79	{new}	{"colour": "red", "weight_g": 520}	t	2026-10-30 14:05:25.929607+00
61	SKU-00061	Charger 61	Product number 61	8	240.67	127.72	{sale}	{"colour": "blue", "weight_g": 527}	t	2026-10-30 14:05:25.929607+00
62	SKU-00062	Atlas 62	Product number 62	9	161.31	92.12	{gift}	{"colour": "black", "weight_g": 534}	t	2026-10-30 14:05:25.929607+00
63	SKU-00063	Blanket 63	Product number 63	1	21.47	14.12	{eco}	{"colour": "white", "weight_g": 541}	t	2026-10-30 14:05:25.929607+00
64	SKU-00064	Lamp 64	Product number 64	2	448.59	320.85	{new}	{"colour": "red", "weight_g": 548}	t	2026-10-30 14:05:25.929607+00
65	SKU-00065	Kettle 65	Product number 65	3	21.19	11.92	{sale}	{"colour": "blue", "weight_g": 555}	t	2026-10-30 14:05:25.929607+00
66	SKU-00066	Novel 66	Product number 66	4	187.34	95.04	{gift}	{"colour": "black", "weight_g": 562}	t	2026-10-30 14:05:25.929607+00
67	SKU-00067	Headphones 67	Product number 67	5	141.23	83.24	{eco}	{"colour": "white", "weight_g": 569}	t	2026-10-30 14:05:25.929607+00
68	SKU-00068	Mug 68	Product number 68	6	275.81	154.50	{new}	{"colour": "red", "weight_g": 576}	t	2026-10-30 14:05:25.929607+00
69	SKU-00069	Charger 69	Product number 69	7	496.87	245.69	{sale}	{"colour": "blue", "weight_g": 583}	t	2026-10-30 14:05:25.929607+00
70	SKU-00070	Atlas 70	Product number 70	8	63.00	29.97	{gift}	{"colour": "black", "weight_g": 590}	t	2026-10-30 14:05:25.929607+00
71	SKU-00071	Blanket 71	Product number 71	9	145.48	114.56	{eco}	{"colour": "white", "weight_g": 597}	t	2026-10-30 14:05:25.929607+00
72	SKU-00072	Lamp 72	Product number 72	1	202.91	140.53	{new}	{"colour": "red", "weight_g": 604}	t	2026-10-30 14:05:25.929607+00
73	SKU-00073	Kettle 73	Product number 73	2	486.41	308.64	{sale}	{"colour": "blue", "weight_g": 611}	t	2026-10-30 14:05:25.929607+00
74	SKU-00074	Novel 74	Product number 74	3	414.12	244.64	{gift}	{"colour": "black", "weight_g": 618}	t	2026-10-30 14:05:25.929607+00
75	SKU-00075	Headphones 75	Product number 75	4	180.28	129.16	{eco}	{"colour": "white", "weight_g": 625}	t	2026-10-30 14:05:25.929607+00
76	SKU-00076	Mug 76	Product number 76	5	173.97	127.56	{new}	{"colour": "red", "weight_g": 632}	t	2026-10-30 14:05:25.929607+00
77	SKU-00077	Charger 77	Product number 77	6	167.89	128.16	{sale}	{"colour": "blue", "weight_g": 639}	t	2026-10-30 14:05:25.929607+00
78	SKU-00078	Atlas 78	Product number 78	7	85.32	36.71	{gift}	{"colour": "black", "weight_g": 646}	t	2026-10-30 14:05:25.929607+00
79	SKU-00079	Blanket 79	Product number 79	8	168.09	69.07	{eco}	{"colour": "white", "weight_g": 653}	t	2026-10-30 14:05:25.929607+00
80	SKU-00080	Lamp 80	Product number 80	9	330.81	155.30	{new}	{"colour": "red", "weight_g": 660}	t	2026-10-30 14:05:25.929607+00
81	SKU-00081	Kettle 81	Product number 81	1	426.83	210.12	{sale}	{"colour": "blue", "weight_g": 667}	t	2026-10-30 14:05:25.929607+00
82	SKU-00082	Novel 82	Product number 82	2	322.76	219.60	{gift}	{"colour": "black", "weight_g": 674}	t	2026-10-30 14:05:25.929607+00
83	SKU-00083	Headphones 83	Product number 83	3	286.19	177.77	{eco}	{"colour": "white", "weight_g": 681}	t	2026-10-30 14:05:25.929607+00
84	SKU-00084	Mug 84	Product number 84	4	302.33	139.21	{new}	{"colour": "red", "weight_g": 688}	t	2026-10-30 14:05:25.929607+00
85	SKU-00085	Charger 85	Product number 85	5	138.76	100.07	{sale}	{"colour": "blue", "weight_g": 695}	t	2026-10-30 14:05:25.929607+00
86	SKU-00086	Atlas 86	Product number 86	6	445.44	192.16	{gift}	{"colour": "black", "weight_g": 702}	t	2026-10-30 14:05:25.929607+00
87	SKU-00087	Blanket 87	Product number 87	7	279.57	149.23	{eco}	{"colour": "white", "weight_g": 709}	t	2026-10-30 14:05:25.929607+00
88	SKU-00088	Lamp 88	Product number 88	8	326.61	147.81	{new}	{"colour": "red", "weight_g": 716}	t	2026-10-30 14:05:25.929607+00
89	SKU-00089	Kettle 89	Product number 89	9	106.25	69.50	{sale}	{"colour": "blue", "weight_g": 723}	t	2026-10-30 14:05:25.929607+00
90	SKU-00090	Novel 90	Product number 90	1	249.60	109.03	{gift}	{"colour": "black", "weight_g": 730}	t	2026-10-30 14:05:25.929607+00
91	SKU-00091	Headphones 91	Product number 91	2	494.48	282.63	{eco}	{"colour": "white", "weight_g": 737}	t	2026-10-30 14:05:25.929607+00
92	SKU-00092	Mug 92	Product number 92	3	53.91	39.51	{new}	{"colour": "red", "weight_g": 744}	t	2026-10-30 14:05:25.929607+00
93	SKU-00093	Charger 93	Product number 93	4	29.95	21.95	{sale}	{"colour": "blue", "weight_g": 751}	t	2026-10-30 14:05:25.929607+00
94	SKU-00094	Atlas 94	Product number 94	5	334.09	181.21	{gift}	{"colour": "black", "weight_g": 758}	t	2026-10-30 14:05:25.929607+00
95	SKU-00095	Blanket 95	Product number 95	6	411.58	311.98	{eco}	{"colour": "white", "weight_g": 765}	t	2026-10-30 14:05:25.929607+00
96	SKU-00096	Lamp 96	Product number 96	7	378.08	156.88	{new}	{"colour": "red", "weight_g": 772}	t	2026-10-30 14:05:25.929607+00
97	SKU-00097	Kettle 97	Product number 97	8	292.00	210.46	{sale}	{"colour": "blue", "weight_g": 779}	t	2026-10-30 14:05:25.929607+00
98	SKU-00098	Novel 98	Product number 98	9	443.40	266.77	{gift}	{"colour": "black", "weight_g": 786}	t	2026-10-30 14:05:25.929607+00
99	SKU-00099	Headphones 99	Product number 99	1	474.25	245.26	{eco}	{"colour": "white", "weight_g": 793}	t	2026-10-30 14:05:25.929607+00
100	SKU-00100	Mug 100	Product number 100	2	82.54	65.95	{new}	{"colour": "red", "weight_g": 800}	t	2026-10-30 14:05:25.929607+00
101	SKU-00101	Charger 101	Product number 101	3	109.42	79.57	{sale}	{"colour": "blue", "weight_g": 807}	t	2026-10-30 14:05:25.929607+00
102	SKU-00102	Atlas 102	Product number 102	4	80.97	44.78	{gift}	{"colour": "black", "weight_g": 814}	t	2026-10-30 14:05:25.929607+00
103	SKU-00103	Blanket 103	Product number 103	5	157.25	66.93	{eco}	{"colour": "white", "weight_g": 821}	t	2026-10-30 14:05:25.929607+00
104	SKU-00104	Lamp 104	Product number 104	6	139.48	79.32	{new}	{"colour": "red", "weight_g": 828}	t	2026-10-30 14:05:25.929607+00
105	SKU-00105	Kettle 105	Product number 105	7	78.00	39.57	{sale}	{"colour": "blue", "weight_g": 835}	t	2026-10-30 14:05:25.929607+00
106	SKU-00106	Novel 106	Product number 106	8	313.21	125.87	{gift}	{"colour": "black", "weight_g": 842}	t	2026-10-30 14:05:25.929607+00
107	SKU-00107	Headphones 107	Product number 107	9	296.84	132.47	{eco}	{"colour": "white", "weight_g": 849}	t	2026-10-30 14:05:25.929607+00
108	SKU-00108	Mug 108	Product number 108	1	188.43	120.63	{new}	{"colour": "red", "weight_g": 856}	t	2026-10-30 14:05:25.929607+00
109	SKU-00109	Charger 109	Product number 109	2	452.51	204.67	{sale}	{"colour": "blue", "weight_g": 863}	t	2026-10-30 14:05:25.929607+00
110	SKU-00110	Atlas 110	Product number 110	3	388.06	284.67	{gift}	{"colour": "black", "weight_g": 870}	t	2026-10-30 14:05:25.929607+00
111	SKU-00111	Blanket 111	Product number 111	4	488.46	207.35	{eco}	{"colour": "white", "weight_g": 877}	t	2026-10-30 14:05:25.929607+00
112	SKU-00112	Lamp 112	Product number 112	5	473.09	291.97	{new}	{"colour": "red", "weight_g": 884}	t	2026-10-30 14:05:25.929607+00
113	SKU-00113	Kettle 113	Product number 113	6	439.42	208.44	{sale}	{"colour": "blue", "weight_g": 891}	t	2026-10-30 14:05:25.929607+00
114	SKU-00114	Novel 114	Product number 114	7	113.36	74.30	{gift}	{"colour": "black", "weight_g": 898}	t	2026-10-30 14:05:25.929607+00
115	SKU-00115	Headphones 115	Product number 115	8	207.72	96.15	{eco}	{"colour": "white", "weight_g": 905}	t	2026-10-30 14:05:25.929607+00
116	SKU-00116	Mug 116	Product number 116	9	497.73	303.93	{new}	{"colour": "red", "weight_g": 912}	t	2026-10-30 14:05:25.929607+00
117	SKU-00117	Charger 117	Product number 117	1	433.00	284.31	{sale}	{"colour": "blue", "weight_g": 919}	t	2026-10-30 14:05:25.929607+00
118	SKU-00118	Atlas 118	Product number 118	2	284.66	192.52	{gift}	{"colour": "black", "weight_g": 926}	t	2026-10-30 14:05:25.929607+00
119	SKU-00119	Blanket 119	Product number 119	3	478.95	296.87	{eco}	{"colour": "white", "weight_g": 933}	t	2026-10-30 14:05:25.929607+00
120	SKU-00120	Lamp 120	Product number 120	4	293.82	225.32	{new}	{"colour": "red", "weight_g": 940}	t	2026-10-30 14:05:25.929607+00
\.


--
-- Data for Name: employees; Type: TABLE DATA; Schema: hr; Owner: -
--

COPY hr.employees (id, name, email, manager_id, hired_on, salary) FROM stdin;
1	Ana Lima	ana@acme.example	\N	2019-03-01	18000.00
2	Employee 1	employee1@acme.example	1	2020-01-18	7813.52
3	Employee 2	employee2@acme.example	1	2020-02-04	4886.93
4	Employee 3	employee3@acme.example	1	2020-02-21	7368.35
5	Employee 4	employee4@acme.example	1	2020-03-09	6967.16
6	Employee 5	employee5@acme.example	1	2020-03-26	4933.92
7	Employee 6	employee6@acme.example	1	2020-04-12	11472.36
8	Employee 7	employee7@acme.example	1	2020-04-29	5715.57
9	Employee 8	employee8@acme.example	1	2020-05-16	10474.51
10	Employee 9	employee9@acme.example	1	2020-06-02	9271.68
11	Employee 10	employee10@acme.example	1	2020-06-19	10500.93
12	Employee 11	employee11@acme.example	1	2020-07-06	3949.73
13	Employee 12	employee12@acme.example	1	2020-07-23	3043.21
14	Employee 13	employee13@acme.example	1	2020-08-09	11231.19
15	Employee 14	employee14@acme.example	1	2020-08-26	8278.18
\.


--
-- Data for Name: movements_2025; Type: TABLE DATA; Schema: inventory; Owner: -
--

COPY inventory.movements_2025 (id, store_id, product_id, moved_at, quantity) FROM stdin;
1	2	2	2025-06-01 05:00:00+00	10
2	3	3	2025-06-01 10:00:00+00	10
3	4	4	2025-06-01 15:00:00+00	-2
4	5	5	2025-06-01 20:00:00+00	10
5	1	6	2025-06-02 01:00:00+00	10
6	2	7	2025-06-02 06:00:00+00	-2
7	3	8	2025-06-02 11:00:00+00	10
8	4	9	2025-06-02 16:00:00+00	10
9	5	10	2025-06-02 21:00:00+00	-2
10	1	11	2025-06-03 02:00:00+00	10
11	2	12	2025-06-03 07:00:00+00	10
12	3	13	2025-06-03 12:00:00+00	-2
13	4	14	2025-06-03 17:00:00+00	10
14	5	15	2025-06-03 22:00:00+00	10
15	1	16	2025-06-04 03:00:00+00	-2
16	2	17	2025-06-04 08:00:00+00	10
17	3	18	2025-06-04 13:00:00+00	10
18	4	19	2025-06-04 18:00:00+00	-2
19	5	20	2025-06-04 23:00:00+00	10
20	1	21	2025-06-05 04:00:00+00	10
21	2	22	2025-06-05 09:00:00+00	-2
22	3	23	2025-06-05 14:00:00+00	10
23	4	24	2025-06-05 19:00:00+00	10
24	5	25	2025-06-06 00:00:00+00	-2
25	1	26	2025-06-06 05:00:00+00	10
26	2	27	2025-06-06 10:00:00+00	10
27	3	28	2025-06-06 15:00:00+00	-2
28	4	29	2025-06-06 20:00:00+00	10
29	5	30	2025-06-07 01:00:00+00	10
30	1	31	2025-06-07 06:00:00+00	-2
31	2	32	2025-06-07 11:00:00+00	10
32	3	33	2025-06-07 16:00:00+00	10
33	4	34	2025-06-07 21:00:00+00	-2
34	5	35	2025-06-08 02:00:00+00	10
35	1	36	2025-06-08 07:00:00+00	10
36	2	37	2025-06-08 12:00:00+00	-2
37	3	38	2025-06-08 17:00:00+00	10
38	4	39	2025-06-08 22:00:00+00	10
39	5	40	2025-06-09 03:00:00+00	-2
40	1	41	2025-06-09 08:00:00+00	10
41	2	42	2025-06-09 13:00:00+00	10
42	3	43	2025-06-09 18:00:00+00	-2
43	4	44	2025-06-09 23:00:00+00	10
44	5	45	2025-06-10 04:00:00+00	10
45	1	46	2025-06-10 09:00:00+00	-2
46	2	47	2025-06-10 14:00:00+00	10
47	3	48	2025-06-10 19:00:00+00	10
48	4	49	2025-06-11 00:00:00+00	-2
49	5	50	2025-06-11 05:00:00+00	10
50	1	51	2025-06-11 10:00:00+00	10
51	2	52	2025-06-11 15:00:00+00	-2
52	3	53	2025-06-11 20:00:00+00	10
53	4	54	2025-06-12 01:00:00+00	10
54	5	55	2025-06-12 06:00:00+00	-2
55	1	56	2025-06-12 11:00:00+00	10
56	2	57	2025-06-12 16:00:00+00	10
57	3	58	2025-06-12 21:00:00+00	-2
58	4	59	2025-06-13 02:00:00+00	10
59	5	60	2025-06-13 07:00:00+00	10
60	1	61	2025-06-13 12:00:00+00	-2
61	2	62	2025-06-13 17:00:00+00	10
62	3	63	2025-06-13 22:00:00+00	10
63	4	64	2025-06-14 03:00:00+00	-2
64	5	65	2025-06-14 08:00:00+00	10
65	1	66	2025-06-14 13:00:00+00	10
66	2	67	2025-06-14 18:00:00+00	-2
67	3	68	2025-06-14 23:00:00+00	10
68	4	69	2025-06-15 04:00:00+00	10
69	5	70	2025-06-15 09:00:00+00	-2
70	1	71	2025-06-15 14:00:00+00	10
71	2	72	2025-06-15 19:00:00+00	10
72	3	73	2025-06-16 00:00:00+00	-2
73	4	74	2025-06-16 05:00:00+00	10
74	5	75	2025-06-16 10:00:00+00	10
75	1	76	2025-06-16 15:00:00+00	-2
76	2	77	2025-06-16 20:00:00+00	10
77	3	78	2025-06-17 01:00:00+00	10
78	4	79	2025-06-17 06:00:00+00	-2
79	5	80	2025-06-17 11:00:00+00	10
80	1	81	2025-06-17 16:00:00+00	10
81	2	82	2025-06-17 21:00:00+00	-2
82	3	83	2025-06-18 02:00:00+00	10
83	4	84	2025-06-18 07:00:00+00	10
84	5	85	2025-06-18 12:00:00+00	-2
85	1	86	2025-06-18 17:00:00+00	10
86	2	87	2025-06-18 22:00:00+00	10
87	3	88	2025-06-19 03:00:00+00	-2
88	4	89	2025-06-19 08:00:00+00	10
89	5	90	2025-06-19 13:00:00+00	10
90	1	91	2025-06-19 18:00:00+00	-2
91	2	92	2025-06-19 23:00:00+00	10
92	3	93	2025-06-20 04:00:00+00	10
93	4	94	2025-06-20 09:00:00+00	-2
94	5	95	2025-06-20 14:00:00+00	10
95	1	96	2025-06-20 19:00:00+00	10
96	2	97	2025-06-21 00:00:00+00	-2
97	3	98	2025-06-21 05:00:00+00	10
98	4	99	2025-06-21 10:00:00+00	10
99	5	100	2025-06-21 15:00:00+00	-2
100	1	101	2025-06-21 20:00:00+00	10
101	2	102	2025-06-22 01:00:00+00	10
102	3	103	2025-06-22 06:00:00+00	-2
103	4	104	2025-06-22 11:00:00+00	10
104	5	105	2025-06-22 16:00:00+00	10
105	1	106	2025-06-22 21:00:00+00	-2
106	2	107	2025-06-23 02:00:00+00	10
107	3	108	2025-06-23 07:00:00+00	10
108	4	109	2025-06-23 12:00:00+00	-2
109	5	110	2025-06-23 17:00:00+00	10
110	1	111	2025-06-23 22:00:00+00	10
111	2	112	2025-06-24 03:00:00+00	-2
112	3	113	2025-06-24 08:00:00+00	10
113	4	114	2025-06-24 13:00:00+00	10
114	5	115	2025-06-24 18:00:00+00	-2
115	1	116	2025-06-24 23:00:00+00	10
116	2	117	2025-06-25 04:00:00+00	10
117	3	118	2025-06-25 09:00:00+00	-2
118	4	119	2025-06-25 14:00:00+00	10
119	5	120	2025-06-25 19:00:00+00	10
120	1	1	2025-06-26 00:00:00+00	-2
121	2	2	2025-06-26 05:00:00+00	10
122	3	3	2025-06-26 10:00:00+00	10
123	4	4	2025-06-26 15:00:00+00	-2
124	5	5	2025-06-26 20:00:00+00	10
125	1	6	2025-06-27 01:00:00+00	10
126	2	7	2025-06-27 06:00:00+00	-2
127	3	8	2025-06-27 11:00:00+00	10
128	4	9	2025-06-27 16:00:00+00	10
129	5	10	2025-06-27 21:00:00+00	-2
130	1	11	2025-06-28 02:00:00+00	10
131	2	12	2025-06-28 07:00:00+00	10
132	3	13	2025-06-28 12:00:00+00	-2
133	4	14	2025-06-28 17:00:00+00	10
134	5	15	2025-06-28 22:00:00+00	10
135	1	16	2025-06-29 03:00:00+00	-2
136	2	17	2025-06-29 08:00:00+00	10
137	3	18	2025-06-29 13:00:00+00	10
138	4	19	2025-06-29 18:00:00+00	-2
139	5	20	2025-06-29 23:00:00+00	10
140	1	21	2025-06-30 04:00:00+00	10
141	2	22	2025-06-30 09:00:00+00	-2
142	3	23	2025-06-30 14:00:00+00	10
143	4	24	2025-06-30 19:00:00+00	10
144	5	25	2025-07-01 00:00:00+00	-2
145	1	26	2025-07-01 05:00:00+00	10
146	2	27	2025-07-01 10:00:00+00	10
147	3	28	2025-07-01 15:00:00+00	-2
148	4	29	2025-07-01 20:00:00+00	10
149	5	30	2025-07-02 01:00:00+00	10
150	1	31	2025-07-02 06:00:00+00	-2
151	2	32	2025-07-02 11:00:00+00	10
152	3	33	2025-07-02 16:00:00+00	10
153	4	34	2025-07-02 21:00:00+00	-2
154	5	35	2025-07-03 02:00:00+00	10
155	1	36	2025-07-03 07:00:00+00	10
156	2	37	2025-07-03 12:00:00+00	-2
157	3	38	2025-07-03 17:00:00+00	10
158	4	39	2025-07-03 22:00:00+00	10
159	5	40	2025-07-04 03:00:00+00	-2
160	1	41	2025-07-04 08:00:00+00	10
161	2	42	2025-07-04 13:00:00+00	10
162	3	43	2025-07-04 18:00:00+00	-2
163	4	44	2025-07-04 23:00:00+00	10
164	5	45	2025-07-05 04:00:00+00	10
165	1	46	2025-07-05 09:00:00+00	-2
166	2	47	2025-07-05 14:00:00+00	10
167	3	48	2025-07-05 19:00:00+00	10
168	4	49	2025-07-06 00:00:00+00	-2
169	5	50	2025-07-06 05:00:00+00	10
170	1	51	2025-07-06 10:00:00+00	10
171	2	52	2025-07-06 15:00:00+00	-2
172	3	53	2025-07-06 20:00:00+00	10
173	4	54	2025-07-07 01:00:00+00	10
174	5	55	2025-07-07 06:00:00+00	-2
175	1	56	2025-07-07 11:00:00+00	10
176	2	57	2025-07-07 16:00:00+00	10
177	3	58	2025-07-07 21:00:00+00	-2
178	4	59	2025-07-08 02:00:00+00	10
179	5	60	2025-07-08 07:00:00+00	10
180	1	61	2025-07-08 12:00:00+00	-2
181	2	62	2025-07-08 17:00:00+00	10
182	3	63	2025-07-08 22:00:00+00	10
183	4	64	2025-07-09 03:00:00+00	-2
184	5	65	2025-07-09 08:00:00+00	10
185	1	66	2025-07-09 13:00:00+00	10
186	2	67	2025-07-09 18:00:00+00	-2
187	3	68	2025-07-09 23:00:00+00	10
188	4	69	2025-07-10 04:00:00+00	10
189	5	70	2025-07-10 09:00:00+00	-2
190	1	71	2025-07-10 14:00:00+00	10
191	2	72	2025-07-10 19:00:00+00	10
192	3	73	2025-07-11 00:00:00+00	-2
193	4	74	2025-07-11 05:00:00+00	10
194	5	75	2025-07-11 10:00:00+00	10
195	1	76	2025-07-11 15:00:00+00	-2
196	2	77	2025-07-11 20:00:00+00	10
197	3	78	2025-07-12 01:00:00+00	10
198	4	79	2025-07-12 06:00:00+00	-2
199	5	80	2025-07-12 11:00:00+00	10
200	1	81	2025-07-12 16:00:00+00	10
201	2	82	2025-07-12 21:00:00+00	-2
202	3	83	2025-07-13 02:00:00+00	10
203	4	84	2025-07-13 07:00:00+00	10
204	5	85	2025-07-13 12:00:00+00	-2
205	1	86	2025-07-13 17:00:00+00	10
206	2	87	2025-07-13 22:00:00+00	10
207	3	88	2025-07-14 03:00:00+00	-2
208	4	89	2025-07-14 08:00:00+00	10
209	5	90	2025-07-14 13:00:00+00	10
210	1	91	2025-07-14 18:00:00+00	-2
211	2	92	2025-07-14 23:00:00+00	10
212	3	93	2025-07-15 04:00:00+00	10
213	4	94	2025-07-15 09:00:00+00	-2
214	5	95	2025-07-15 14:00:00+00	10
215	1	96	2025-07-15 19:00:00+00	10
216	2	97	2025-07-16 00:00:00+00	-2
217	3	98	2025-07-16 05:00:00+00	10
218	4	99	2025-07-16 10:00:00+00	10
219	5	100	2025-07-16 15:00:00+00	-2
220	1	101	2025-07-16 20:00:00+00	10
221	2	102	2025-07-17 01:00:00+00	10
222	3	103	2025-07-17 06:00:00+00	-2
223	4	104	2025-07-17 11:00:00+00	10
224	5	105	2025-07-17 16:00:00+00	10
225	1	106	2025-07-17 21:00:00+00	-2
226	2	107	2025-07-18 02:00:00+00	10
227	3	108	2025-07-18 07:00:00+00	10
228	4	109	2025-07-18 12:00:00+00	-2
229	5	110	2025-07-18 17:00:00+00	10
230	1	111	2025-07-18 22:00:00+00	10
231	2	112	2025-07-19 03:00:00+00	-2
232	3	113	2025-07-19 08:00:00+00	10
233	4	114	2025-07-19 13:00:00+00	10
234	5	115	2025-07-19 18:00:00+00	-2
235	1	116	2025-07-19 23:00:00+00	10
236	2	117	2025-07-20 04:00:00+00	10
237	3	118	2025-07-20 09:00:00+00	-2
238	4	119	2025-07-20 14:00:00+00	10
239	5	120	2025-07-20 19:00:00+00	10
240	1	1	2025-07-21 00:00:00+00	-2
241	2	2	2025-07-21 05:00:00+00	10
242	3	3	2025-07-21 10:00:00+00	10
243	4	4	2025-07-21 15:00:00+00	-2
244	5	5	2025-07-21 20:00:00+00	10
245	1	6	2025-07-22 01:00:00+00	10
246	2	7	2025-07-22 06:00:00+00	-2
247	3	8	2025-07-22 11:00:00+00	10
248	4	9	2025-07-22 16:00:00+00	10
249	5	10	2025-07-22 21:00:00+00	-2
250	1	11	2025-07-23 02:00:00+00	10
251	2	12	2025-07-23 07:00:00+00	10
252	3	13	2025-07-23 12:00:00+00	-2
253	4	14	2025-07-23 17:00:00+00	10
254	5	15	2025-07-23 22:00:00+00	10
255	1	16	2025-07-24 03:00:00+00	-2
256	2	17	2025-07-24 08:00:00+00	10
257	3	18	2025-07-24 13:00:00+00	10
258	4	19	2025-07-24 18:00:00+00	-2
259	5	20	2025-07-24 23:00:00+00	10
260	1	21	2025-07-25 04:00:00+00	10
261	2	22	2025-07-25 09:00:00+00	-2
262	3	23	2025-07-25 14:00:00+00	10
263	4	24	2025-07-25 19:00:00+00	10
264	5	25	2025-07-26 00:00:00+00	-2
265	1	26	2025-07-26 05:00:00+00	10
266	2	27	2025-07-26 10:00:00+00	10
267	3	28	2025-07-26 15:00:00+00	-2
268	4	29	2025-07-26 20:00:00+00	10
269	5	30	2025-07-27 01:00:00+00	10
270	1	31	2025-07-27 06:00:00+00	-2
271	2	32	2025-07-27 11:00:00+00	10
272	3	33	2025-07-27 16:00:00+00	10
273	4	34	2025-07-27 21:00:00+00	-2
274	5	35	2025-07-28 02:00:00+00	10
275	1	36	2025-07-28 07:00:00+00	10
276	2	37	2025-07-28 12:00:00+00	-2
277	3	38	2025-07-28 17:00:00+00	10
278	4	39	2025-07-28 22:00:00+00	10
279	5	40	2025-07-29 03:00:00+00	-2
280	1	41	2025-07-29 08:00:00+00	10
281	2	42	2025-07-29 13:00:00+00	10
282	3	43	2025-07-29 18:00:00+00	-2
283	4	44	2025-07-29 23:00:00+00	10
284	5	45	2025-07-30 04:00:00+00	10
285	1	46	2025-07-30 09:00:00+00	-2
286	2	47	2025-07-30 14:00:00+00	10
287	3	48	2025-07-30 19:00:00+00	10
288	4	49	2025-07-31 00:00:00+00	-2
289	5	50	2025-07-31 05:00:00+00	10
290	1	51	2025-07-31 10:00:00+00	10
291	2	52	2025-07-31 15:00:00+00	-2
292	3	53	2025-07-31 20:00:00+00	10
293	4	54	2025-08-01 01:00:00+00	10
294	5	55	2025-08-01 06:00:00+00	-2
295	1	56	2025-08-01 11:00:00+00	10
296	2	57	2025-08-01 16:00:00+00	10
297	3	58	2025-08-01 21:00:00+00	-2
298	4	59	2025-08-02 02:00:00+00	10
299	5	60	2025-08-02 07:00:00+00	10
300	1	61	2025-08-02 12:00:00+00	-2
301	2	62	2025-08-02 17:00:00+00	10
302	3	63	2025-08-02 22:00:00+00	10
303	4	64	2025-08-03 03:00:00+00	-2
304	5	65	2025-08-03 08:00:00+00	10
305	1	66	2025-08-03 13:00:00+00	10
306	2	67	2025-08-03 18:00:00+00	-2
307	3	68	2025-08-03 23:00:00+00	10
308	4	69	2025-08-04 04:00:00+00	10
309	5	70	2025-08-04 09:00:00+00	-2
310	1	71	2025-08-04 14:00:00+00	10
311	2	72	2025-08-04 19:00:00+00	10
312	3	73	2025-08-05 00:00:00+00	-2
313	4	74	2025-08-05 05:00:00+00	10
314	5	75	2025-08-05 10:00:00+00	10
315	1	76	2025-08-05 15:00:00+00	-2
316	2	77	2025-08-05 20:00:00+00	10
317	3	78	2025-08-06 01:00:00+00	10
318	4	79	2025-08-06 06:00:00+00	-2
319	5	80	2025-08-06 11:00:00+00	10
320	1	81	2025-08-06 16:00:00+00	10
321	2	82	2025-08-06 21:00:00+00	-2
322	3	83	2025-08-07 02:00:00+00	10
323	4	84	2025-08-07 07:00:00+00	10
324	5	85	2025-08-07 12:00:00+00	-2
325	1	86	2025-08-07 17:00:00+00	10
326	2	87	2025-08-07 22:00:00+00	10
327	3	88	2025-08-08 03:00:00+00	-2
328	4	89	2025-08-08 08:00:00+00	10
329	5	90	2025-08-08 13:00:00+00	10
330	1	91	2025-08-08 18:00:00+00	-2
331	2	92	2025-08-08 23:00:00+00	10
332	3	93	2025-08-09 04:00:00+00	10
333	4	94	2025-08-09 09:00:00+00	-2
334	5	95	2025-08-09 14:00:00+00	10
335	1	96	2025-08-09 19:00:00+00	10
336	2	97	2025-08-10 00:00:00+00	-2
337	3	98	2025-08-10 05:00:00+00	10
338	4	99	2025-08-10 10:00:00+00	10
339	5	100	2025-08-10 15:00:00+00	-2
340	1	101	2025-08-10 20:00:00+00	10
341	2	102	2025-08-11 01:00:00+00	10
342	3	103	2025-08-11 06:00:00+00	-2
343	4	104	2025-08-11 11:00:00+00	10
344	5	105	2025-08-11 16:00:00+00	10
345	1	106	2025-08-11 21:00:00+00	-2
346	2	107	2025-08-12 02:00:00+00	10
347	3	108	2025-08-12 07:00:00+00	10
348	4	109	2025-08-12 12:00:00+00	-2
349	5	110	2025-08-12 17:00:00+00	10
350	1	111	2025-08-12 22:00:00+00	10
351	2	112	2025-08-13 03:00:00+00	-2
352	3	113	2025-08-13 08:00:00+00	10
353	4	114	2025-08-13 13:00:00+00	10
354	5	115	2025-08-13 18:00:00+00	-2
355	1	116	2025-08-13 23:00:00+00	10
356	2	117	2025-08-14 04:00:00+00	10
357	3	118	2025-08-14 09:00:00+00	-2
358	4	119	2025-08-14 14:00:00+00	10
359	5	120	2025-08-14 19:00:00+00	10
360	1	1	2025-08-15 00:00:00+00	-2
361	2	2	2025-08-15 05:00:00+00	10
362	3	3	2025-08-15 10:00:00+00	10
363	4	4	2025-08-15 15:00:00+00	-2
364	5	5	2025-08-15 20:00:00+00	10
365	1	6	2025-08-16 01:00:00+00	10
366	2	7	2025-08-16 06:00:00+00	-2
367	3	8	2025-08-16 11:00:00+00	10
368	4	9	2025-08-16 16:00:00+00	10
369	5	10	2025-08-16 21:00:00+00	-2
370	1	11	2025-08-17 02:00:00+00	10
371	2	12	2025-08-17 07:00:00+00	10
372	3	13	2025-08-17 12:00:00+00	-2
373	4	14	2025-08-17 17:00:00+00	10
374	5	15	2025-08-17 22:00:00+00	10
375	1	16	2025-08-18 03:00:00+00	-2
376	2	17	2025-08-18 08:00:00+00	10
377	3	18	2025-08-18 13:00:00+00	10
378	4	19	2025-08-18 18:00:00+00	-2
379	5	20	2025-08-18 23:00:00+00	10
380	1	21	2025-08-19 04:00:00+00	10
381	2	22	2025-08-19 09:00:00+00	-2
382	3	23	2025-08-19 14:00:00+00	10
383	4	24	2025-08-19 19:00:00+00	10
384	5	25	2025-08-20 00:00:00+00	-2
385	1	26	2025-08-20 05:00:00+00	10
386	2	27	2025-08-20 10:00:00+00	10
387	3	28	2025-08-20 15:00:00+00	-2
388	4	29	2025-08-20 20:00:00+00	10
389	5	30	2025-08-21 01:00:00+00	10
390	1	31	2025-08-21 06:00:00+00	-2
391	2	32	2025-08-21 11:00:00+00	10
392	3	33	2025-08-21 16:00:00+00	10
393	4	34	2025-08-21 21:00:00+00	-2
394	5	35	2025-08-22 02:00:00+00	10
395	1	36	2025-08-22 07:00:00+00	10
396	2	37	2025-08-22 12:00:00+00	-2
397	3	38	2025-08-22 17:00:00+00	10
398	4	39	2025-08-22 22:00:00+00	10
399	5	40	2025-08-23 03:00:00+00	-2
400	1	41	2025-08-23 08:00:00+00	10
401	2	42	2025-08-23 13:00:00+00	10
402	3	43	2025-08-23 18:00:00+00	-2
403	4	44	2025-08-23 23:00:00+00	10
404	5	45	2025-08-24 04:00:00+00	10
405	1	46	2025-08-24 09:00:00+00	-2
406	2	47	2025-08-24 14:00:00+00	10
407	3	48	2025-08-24 19:00:00+00	10
408	4	49	2025-08-25 00:00:00+00	-2
409	5	50	2025-08-25 05:00:00+00	10
410	1	51	2025-08-25 10:00:00+00	10
411	2	52	2025-08-25 15:00:00+00	-2
412	3	53	2025-08-25 20:00:00+00	10
413	4	54	2025-08-26 01:00:00+00	10
414	5	55	2025-08-26 06:00:00+00	-2
415	1	56	2025-08-26 11:00:00+00	10
416	2	57	2025-08-26 16:00:00+00	10
417	3	58	2025-08-26 21:00:00+00	-2
418	4	59	2025-08-27 02:00:00+00	10
419	5	60	2025-08-27 07:00:00+00	10
420	1	61	2025-08-27 12:00:00+00	-2
421	2	62	2025-08-27 17:00:00+00	10
422	3	63	2025-08-27 22:00:00+00	10
423	4	64	2025-08-28 03:00:00+00	-2
424	5	65	2025-08-28 08:00:00+00	10
425	1	66	2025-08-28 13:00:00+00	10
426	2	67	2025-08-28 18:00:00+00	-2
427	3	68	2025-08-28 23:00:00+00	10
428	4	69	2025-08-29 04:00:00+00	10
429	5	70	2025-08-29 09:00:00+00	-2
430	1	71	2025-08-29 14:00:00+00	10
431	2	72	2025-08-29 19:00:00+00	10
432	3	73	2025-08-30 00:00:00+00	-2
433	4	74	2025-08-30 05:00:00+00	10
434	5	75	2025-08-30 10:00:00+00	10
435	1	76	2025-08-30 15:00:00+00	-2
436	2	77	2025-08-30 20:00:00+00	10
437	3	78	2025-08-31 01:00:00+00	10
438	4	79	2025-08-31 06:00:00+00	-2
439	5	80	2025-08-31 11:00:00+00	10
440	1	81	2025-08-31 16:00:00+00	10
441	2	82	2025-08-31 21:00:00+00	-2
442	3	83	2025-09-01 02:00:00+00	10
443	4	84	2025-09-01 07:00:00+00	10
444	5	85	2025-09-01 12:00:00+00	-2
445	1	86	2025-09-01 17:00:00+00	10
446	2	87	2025-09-01 22:00:00+00	10
447	3	88	2025-09-02 03:00:00+00	-2
448	4	89	2025-09-02 08:00:00+00	10
449	5	90	2025-09-02 13:00:00+00	10
450	1	91	2025-09-02 18:00:00+00	-2
451	2	92	2025-09-02 23:00:00+00	10
452	3	93	2025-09-03 04:00:00+00	10
453	4	94	2025-09-03 09:00:00+00	-2
454	5	95	2025-09-03 14:00:00+00	10
455	1	96	2025-09-03 19:00:00+00	10
456	2	97	2025-09-04 00:00:00+00	-2
457	3	98	2025-09-04 05:00:00+00	10
458	4	99	2025-09-04 10:00:00+00	10
459	5	100	2025-09-04 15:00:00+00	-2
460	1	101	2025-09-04 20:00:00+00	10
461	2	102	2025-09-05 01:00:00+00	10
462	3	103	2025-09-05 06:00:00+00	-2
463	4	104	2025-09-05 11:00:00+00	10
464	5	105	2025-09-05 16:00:00+00	10
465	1	106	2025-09-05 21:00:00+00	-2
466	2	107	2025-09-06 02:00:00+00	10
467	3	108	2025-09-06 07:00:00+00	10
468	4	109	2025-09-06 12:00:00+00	-2
469	5	110	2025-09-06 17:00:00+00	10
470	1	111	2025-09-06 22:00:00+00	10
471	2	112	2025-09-07 03:00:00+00	-2
472	3	113	2025-09-07 08:00:00+00	10
473	4	114	2025-09-07 13:00:00+00	10
474	5	115	2025-09-07 18:00:00+00	-2
475	1	116	2025-09-07 23:00:00+00	10
476	2	117	2025-09-08 04:00:00+00	10
477	3	118	2025-09-08 09:00:00+00	-2
478	4	119	2025-09-08 14:00:00+00	10
479	5	120	2025-09-08 19:00:00+00	10
480	1	1	2025-09-09 00:00:00+00	-2
481	2	2	2025-09-09 05:00:00+00	10
482	3	3	2025-09-09 10:00:00+00	10
483	4	4	2025-09-09 15:00:00+00	-2
484	5	5	2025-09-09 20:00:00+00	10
485	1	6	2025-09-10 01:00:00+00	10
486	2	7	2025-09-10 06:00:00+00	-2
487	3	8	2025-09-10 11:00:00+00	10
488	4	9	2025-09-10 16:00:00+00	10
489	5	10	2025-09-10 21:00:00+00	-2
490	1	11	2025-09-11 02:00:00+00	10
491	2	12	2025-09-11 07:00:00+00	10
492	3	13	2025-09-11 12:00:00+00	-2
493	4	14	2025-09-11 17:00:00+00	10
494	5	15	2025-09-11 22:00:00+00	10
495	1	16	2025-09-12 03:00:00+00	-2
496	2	17	2025-09-12 08:00:00+00	10
497	3	18	2025-09-12 13:00:00+00	10
498	4	19	2025-09-12 18:00:00+00	-2
499	5	20	2025-09-12 23:00:00+00	10
500	1	21	2025-09-13 04:00:00+00	10
501	2	22	2025-09-13 09:00:00+00	-2
502	3	23	2025-09-13 14:00:00+00	10
503	4	24	2025-09-13 19:00:00+00	10
504	5	25	2025-09-14 00:00:00+00	-2
505	1	26	2025-09-14 05:00:00+00	10
506	2	27	2025-09-14 10:00:00+00	10
507	3	28	2025-09-14 15:00:00+00	-2
508	4	29	2025-09-14 20:00:00+00	10
509	5	30	2025-09-15 01:00:00+00	10
510	1	31	2025-09-15 06:00:00+00	-2
511	2	32	2025-09-15 11:00:00+00	10
512	3	33	2025-09-15 16:00:00+00	10
513	4	34	2025-09-15 21:00:00+00	-2
514	5	35	2025-09-16 02:00:00+00	10
515	1	36	2025-09-16 07:00:00+00	10
516	2	37	2025-09-16 12:00:00+00	-2
517	3	38	2025-09-16 17:00:00+00	10
518	4	39	2025-09-16 22:00:00+00	10
519	5	40	2025-09-17 03:00:00+00	-2
520	1	41	2025-09-17 08:00:00+00	10
521	2	42	2025-09-17 13:00:00+00	10
522	3	43	2025-09-17 18:00:00+00	-2
523	4	44	2025-09-17 23:00:00+00	10
524	5	45	2025-09-18 04:00:00+00	10
525	1	46	2025-09-18 09:00:00+00	-2
526	2	47	2025-09-18 14:00:00+00	10
527	3	48	2025-09-18 19:00:00+00	10
528	4	49	2025-09-19 00:00:00+00	-2
529	5	50	2025-09-19 05:00:00+00	10
530	1	51	2025-09-19 10:00:00+00	10
531	2	52	2025-09-19 15:00:00+00	-2
532	3	53	2025-09-19 20:00:00+00	10
533	4	54	2025-09-20 01:00:00+00	10
534	5	55	2025-09-20 06:00:00+00	-2
535	1	56	2025-09-20 11:00:00+00	10
536	2	57	2025-09-20 16:00:00+00	10
537	3	58	2025-09-20 21:00:00+00	-2
538	4	59	2025-09-21 02:00:00+00	10
539	5	60	2025-09-21 07:00:00+00	10
540	1	61	2025-09-21 12:00:00+00	-2
541	2	62	2025-09-21 17:00:00+00	10
542	3	63	2025-09-21 22:00:00+00	10
543	4	64	2025-09-22 03:00:00+00	-2
544	5	65	2025-09-22 08:00:00+00	10
545	1	66	2025-09-22 13:00:00+00	10
546	2	67	2025-09-22 18:00:00+00	-2
547	3	68	2025-09-22 23:00:00+00	10
548	4	69	2025-09-23 04:00:00+00	10
549	5	70	2025-09-23 09:00:00+00	-2
550	1	71	2025-09-23 14:00:00+00	10
551	2	72	2025-09-23 19:00:00+00	10
552	3	73	2025-09-24 00:00:00+00	-2
553	4	74	2025-09-24 05:00:00+00	10
554	5	75	2025-09-24 10:00:00+00	10
555	1	76	2025-09-24 15:00:00+00	-2
556	2	77	2025-09-24 20:00:00+00	10
557	3	78	2025-09-25 01:00:00+00	10
558	4	79	2025-09-25 06:00:00+00	-2
559	5	80	2025-09-25 11:00:00+00	10
560	1	81	2025-09-25 16:00:00+00	10
561	2	82	2025-09-25 21:00:00+00	-2
562	3	83	2025-09-26 02:00:00+00	10
563	4	84	2025-09-26 07:00:00+00	10
564	5	85	2025-09-26 12:00:00+00	-2
565	1	86	2025-09-26 17:00:00+00	10
566	2	87	2025-09-26 22:00:00+00	10
567	3	88	2025-09-27 03:00:00+00	-2
568	4	89	2025-09-27 08:00:00+00	10
569	5	90	2025-09-27 13:00:00+00	10
570	1	91	2025-09-27 18:00:00+00	-2
571	2	92	2025-09-27 23:00:00+00	10
572	3	93	2025-09-28 04:00:00+00	10
573	4	94	2025-09-28 09:00:00+00	-2
574	5	95	2025-09-28 14:00:00+00	10
575	1	96	2025-09-28 19:00:00+00	10
576	2	97	2025-09-29 00:00:00+00	-2
577	3	98	2025-09-29 05:00:00+00	10
578	4	99	2025-09-29 10:00:00+00	10
579	5	100	2025-09-29 15:00:00+00	-2
580	1	101	2025-09-29 20:00:00+00	10
581	2	102	2025-09-30 01:00:00+00	10
582	3	103	2025-09-30 06:00:00+00	-2
583	4	104	2025-09-30 11:00:00+00	10
584	5	105	2025-09-30 16:00:00+00	10
585	1	106	2025-09-30 21:00:00+00	-2
586	2	107	2025-10-01 02:00:00+00	10
587	3	108	2025-10-01 07:00:00+00	10
588	4	109	2025-10-01 12:00:00+00	-2
589	5	110	2025-10-01 17:00:00+00	10
590	1	111	2025-10-01 22:00:00+00	10
591	2	112	2025-10-02 03:00:00+00	-2
592	3	113	2025-10-02 08:00:00+00	10
593	4	114	2025-10-02 13:00:00+00	10
594	5	115	2025-10-02 18:00:00+00	-2
595	1	116	2025-10-02 23:00:00+00	10
596	2	117	2025-10-03 04:00:00+00	10
597	3	118	2025-10-03 09:00:00+00	-2
598	4	119	2025-10-03 14:00:00+00	10
599	5	120	2025-10-03 19:00:00+00	10
600	1	1	2025-10-04 00:00:00+00	-2
601	2	2	2025-10-04 05:00:00+00	10
602	3	3	2025-10-04 10:00:00+00	10
603	4	4	2025-10-04 15:00:00+00	-2
604	5	5	2025-10-04 20:00:00+00	10
605	1	6	2025-10-05 01:00:00+00	10
606	2	7	2025-10-05 06:00:00+00	-2
607	3	8	2025-10-05 11:00:00+00	10
608	4	9	2025-10-05 16:00:00+00	10
609	5	10	2025-10-05 21:00:00+00	-2
610	1	11	2025-10-06 02:00:00+00	10
611	2	12	2025-10-06 07:00:00+00	10
612	3	13	2025-10-06 12:00:00+00	-2
613	4	14	2025-10-06 17:00:00+00	10
614	5	15	2025-10-06 22:00:00+00	10
615	1	16	2025-10-07 03:00:00+00	-2
616	2	17	2025-10-07 08:00:00+00	10
617	3	18	2025-10-07 13:00:00+00	10
618	4	19	2025-10-07 18:00:00+00	-2
619	5	20	2025-10-07 23:00:00+00	10
620	1	21	2025-10-08 04:00:00+00	10
621	2	22	2025-10-08 09:00:00+00	-2
622	3	23	2025-10-08 14:00:00+00	10
623	4	24	2025-10-08 19:00:00+00	10
624	5	25	2025-10-09 00:00:00+00	-2
625	1	26	2025-10-09 05:00:00+00	10
626	2	27	2025-10-09 10:00:00+00	10
627	3	28	2025-10-09 15:00:00+00	-2
628	4	29	2025-10-09 20:00:00+00	10
629	5	30	2025-10-10 01:00:00+00	10
630	1	31	2025-10-10 06:00:00+00	-2
631	2	32	2025-10-10 11:00:00+00	10
632	3	33	2025-10-10 16:00:00+00	10
633	4	34	2025-10-10 21:00:00+00	-2
634	5	35	2025-10-11 02:00:00+00	10
635	1	36	2025-10-11 07:00:00+00	10
636	2	37	2025-10-11 12:00:00+00	-2
637	3	38	2025-10-11 17:00:00+00	10
638	4	39	2025-10-11 22:00:00+00	10
639	5	40	2025-10-12 03:00:00+00	-2
640	1	41	2025-10-12 08:00:00+00	10
641	2	42	2025-10-12 13:00:00+00	10
642	3	43	2025-10-12 18:00:00+00	-2
643	4	44	2025-10-12 23:00:00+00	10
644	5	45	2025-10-13 04:00:00+00	10
645	1	46	2025-10-13 09:00:00+00	-2
646	2	47	2025-10-13 14:00:00+00	10
647	3	48	2025-10-13 19:00:00+00	10
648	4	49	2025-10-14 00:00:00+00	-2
649	5	50	2025-10-14 05:00:00+00	10
650	1	51	2025-10-14 10:00:00+00	10
651	2	52	2025-10-14 15:00:00+00	-2
652	3	53	2025-10-14 20:00:00+00	10
653	4	54	2025-10-15 01:00:00+00	10
654	5	55	2025-10-15 06:00:00+00	-2
655	1	56	2025-10-15 11:00:00+00	10
656	2	57	2025-10-15 16:00:00+00	10
657	3	58	2025-10-15 21:00:00+00	-2
658	4	59	2025-10-16 02:00:00+00	10
659	5	60	2025-10-16 07:00:00+00	10
660	1	61	2025-10-16 12:00:00+00	-2
661	2	62	2025-10-16 17:00:00+00	10
662	3	63	2025-10-16 22:00:00+00	10
663	4	64	2025-10-17 03:00:00+00	-2
664	5	65	2025-10-17 08:00:00+00	10
665	1	66	2025-10-17 13:00:00+00	10
666	2	67	2025-10-17 18:00:00+00	-2
667	3	68	2025-10-17 23:00:00+00	10
668	4	69	2025-10-18 04:00:00+00	10
669	5	70	2025-10-18 09:00:00+00	-2
670	1	71	2025-10-18 14:00:00+00	10
671	2	72	2025-10-18 19:00:00+00	10
672	3	73	2025-10-19 00:00:00+00	-2
673	4	74	2025-10-19 05:00:00+00	10
674	5	75	2025-10-19 10:00:00+00	10
675	1	76	2025-10-19 15:00:00+00	-2
676	2	77	2025-10-19 20:00:00+00	10
677	3	78	2025-10-20 01:00:00+00	10
678	4	79	2025-10-20 06:00:00+00	-2
679	5	80	2025-10-20 11:00:00+00	10
680	1	81	2025-10-20 16:00:00+00	10
681	2	82	2025-10-20 21:00:00+00	-2
682	3	83	2025-10-21 02:00:00+00	10
683	4	84	2025-10-21 07:00:00+00	10
684	5	85	2025-10-21 12:00:00+00	-2
685	1	86	2025-10-21 17:00:00+00	10
686	2	87	2025-10-21 22:00:00+00	10
687	3	88	2025-10-22 03:00:00+00	-2
688	4	89	2025-10-22 08:00:00+00	10
689	5	90	2025-10-22 13:00:00+00	10
690	1	91	2025-10-22 18:00:00+00	-2
691	2	92	2025-10-22 23:00:00+00	10
692	3	93	2025-10-23 04:00:00+00	10
693	4	94	2025-10-23 09:00:00+00	-2
694	5	95	2025-10-23 14:00:00+00	10
695	1	96	2025-10-23 19:00:00+00	10
696	2	97	2025-10-24 00:00:00+00	-2
697	3	98	2025-10-24 05:00:00+00	10
698	4	99	2025-10-24 10:00:00+00	10
699	5	100	2025-10-24 15:00:00+00	-2
700	1	101	2025-10-24 20:00:00+00	10
701	2	102	2025-10-25 01:00:00+00	10
702	3	103	2025-10-25 06:00:00+00	-2
703	4	104	2025-10-25 11:00:00+00	10
704	5	105	2025-10-25 16:00:00+00	10
705	1	106	2025-10-25 21:00:00+00	-2
706	2	107	2025-10-26 02:00:00+00	10
707	3	108	2025-10-26 07:00:00+00	10
708	4	109	2025-10-26 12:00:00+00	-2
709	5	110	2025-10-26 17:00:00+00	10
710	1	111	2025-10-26 22:00:00+00	10
711	2	112	2025-10-27 03:00:00+00	-2
712	3	113	2025-10-27 08:00:00+00	10
713	4	114	2025-10-27 13:00:00+00	10
714	5	115	2025-10-27 18:00:00+00	-2
715	1	116	2025-10-27 23:00:00+00	10
716	2	117	2025-10-28 04:00:00+00	10
717	3	118	2025-10-28 09:00:00+00	-2
718	4	119	2025-10-28 14:00:00+00	10
719	5	120	2025-10-28 19:00:00+00	10
720	1	1	2025-10-29 00:00:00+00	-2
721	2	2	2025-10-29 05:00:00+00	10
722	3	3	2025-10-29 10:00:00+00	10
723	4	4	2025-10-29 15:00:00+00	-2
724	5	5	2025-10-29 20:00:00+00	10
725	1	6	2025-10-30 01:00:00+00	10
726	2	7	2025-10-30 06:00:00+00	-2
727	3	8	2025-10-30 11:00:00+00	10
728	4	9	2025-10-30 16:00:00+00	10
729	5	10	2025-10-30 21:00:00+00	-2
730	1	11	2025-10-31 02:00:00+00	10
731	2	12	2025-10-31 07:00:00+00	10
732	3	13	2025-10-31 12:00:00+00	-2
733	4	14	2025-10-31 17:00:00+00	10
734	5	15	2025-10-31 22:00:00+00	10
735	1	16	2025-11-01 03:00:00+00	-2
736	2	17	2025-11-01 08:00:00+00	10
737	3	18	2025-11-01 13:00:00+00	10
738	4	19	2025-11-01 18:00:00+00	-2
739	5	20	2025-11-01 23:00:00+00	10
740	1	21	2025-11-02 04:00:00+00	10
741	2	22	2025-11-02 09:00:00+00	-2
742	3	23	2025-11-02 14:00:00+00	10
743	4	24	2025-11-02 19:00:00+00	10
744	5	25	2025-11-03 00:00:00+00	-2
745	1	26	2025-11-03 05:00:00+00	10
746	2	27	2025-11-03 10:00:00+00	10
747	3	28	2025-11-03 15:00:00+00	-2
748	4	29	2025-11-03 20:00:00+00	10
749	5	30	2025-11-04 01:00:00+00	10
750	1	31	2025-11-04 06:00:00+00	-2
751	2	32	2025-11-04 11:00:00+00	10
752	3	33	2025-11-04 16:00:00+00	10
753	4	34	2025-11-04 21:00:00+00	-2
754	5	35	2025-11-05 02:00:00+00	10
755	1	36	2025-11-05 07:00:00+00	10
756	2	37	2025-11-05 12:00:00+00	-2
757	3	38	2025-11-05 17:00:00+00	10
758	4	39	2025-11-05 22:00:00+00	10
759	5	40	2025-11-06 03:00:00+00	-2
760	1	41	2025-11-06 08:00:00+00	10
761	2	42	2025-11-06 13:00:00+00	10
762	3	43	2025-11-06 18:00:00+00	-2
763	4	44	2025-11-06 23:00:00+00	10
764	5	45	2025-11-07 04:00:00+00	10
765	1	46	2025-11-07 09:00:00+00	-2
766	2	47	2025-11-07 14:00:00+00	10
767	3	48	2025-11-07 19:00:00+00	10
768	4	49	2025-11-08 00:00:00+00	-2
769	5	50	2025-11-08 05:00:00+00	10
770	1	51	2025-11-08 10:00:00+00	10
771	2	52	2025-11-08 15:00:00+00	-2
772	3	53	2025-11-08 20:00:00+00	10
773	4	54	2025-11-09 01:00:00+00	10
774	5	55	2025-11-09 06:00:00+00	-2
775	1	56	2025-11-09 11:00:00+00	10
776	2	57	2025-11-09 16:00:00+00	10
777	3	58	2025-11-09 21:00:00+00	-2
778	4	59	2025-11-10 02:00:00+00	10
779	5	60	2025-11-10 07:00:00+00	10
780	1	61	2025-11-10 12:00:00+00	-2
781	2	62	2025-11-10 17:00:00+00	10
782	3	63	2025-11-10 22:00:00+00	10
783	4	64	2025-11-11 03:00:00+00	-2
784	5	65	2025-11-11 08:00:00+00	10
785	1	66	2025-11-11 13:00:00+00	10
786	2	67	2025-11-11 18:00:00+00	-2
787	3	68	2025-11-11 23:00:00+00	10
788	4	69	2025-11-12 04:00:00+00	10
789	5	70	2025-11-12 09:00:00+00	-2
790	1	71	2025-11-12 14:00:00+00	10
791	2	72	2025-11-12 19:00:00+00	10
792	3	73	2025-11-13 00:00:00+00	-2
793	4	74	2025-11-13 05:00:00+00	10
794	5	75	2025-11-13 10:00:00+00	10
795	1	76	2025-11-13 15:00:00+00	-2
796	2	77	2025-11-13 20:00:00+00	10
797	3	78	2025-11-14 01:00:00+00	10
798	4	79	2025-11-14 06:00:00+00	-2
799	5	80	2025-11-14 11:00:00+00	10
800	1	81	2025-11-14 16:00:00+00	10
801	2	82	2025-11-14 21:00:00+00	-2
802	3	83	2025-11-15 02:00:00+00	10
803	4	84	2025-11-15 07:00:00+00	10
804	5	85	2025-11-15 12:00:00+00	-2
805	1	86	2025-11-15 17:00:00+00	10
806	2	87	2025-11-15 22:00:00+00	10
807	3	88	2025-11-16 03:00:00+00	-2
808	4	89	2025-11-16 08:00:00+00	10
809	5	90	2025-11-16 13:00:00+00	10
810	1	91	2025-11-16 18:00:00+00	-2
811	2	92	2025-11-16 23:00:00+00	10
812	3	93	2025-11-17 04:00:00+00	10
813	4	94	2025-11-17 09:00:00+00	-2
814	5	95	2025-11-17 14:00:00+00	10
815	1	96	2025-11-17 19:00:00+00	10
816	2	97	2025-11-18 00:00:00+00	-2
817	3	98	2025-11-18 05:00:00+00	10
818	4	99	2025-11-18 10:00:00+00	10
819	5	100	2025-11-18 15:00:00+00	-2
820	1	101	2025-11-18 20:00:00+00	10
821	2	102	2025-11-19 01:00:00+00	10
822	3	103	2025-11-19 06:00:00+00	-2
823	4	104	2025-11-19 11:00:00+00	10
824	5	105	2025-11-19 16:00:00+00	10
825	1	106	2025-11-19 21:00:00+00	-2
826	2	107	2025-11-20 02:00:00+00	10
827	3	108	2025-11-20 07:00:00+00	10
828	4	109	2025-11-20 12:00:00+00	-2
829	5	110	2025-11-20 17:00:00+00	10
830	1	111	2025-11-20 22:00:00+00	10
831	2	112	2025-11-21 03:00:00+00	-2
832	3	113	2025-11-21 08:00:00+00	10
833	4	114	2025-11-21 13:00:00+00	10
834	5	115	2025-11-21 18:00:00+00	-2
835	1	116	2025-11-21 23:00:00+00	10
836	2	117	2025-11-22 04:00:00+00	10
837	3	118	2025-11-22 09:00:00+00	-2
838	4	119	2025-11-22 14:00:00+00	10
839	5	120	2025-11-22 19:00:00+00	10
840	1	1	2025-11-23 00:00:00+00	-2
841	2	2	2025-11-23 05:00:00+00	10
842	3	3	2025-11-23 10:00:00+00	10
843	4	4	2025-11-23 15:00:00+00	-2
844	5	5	2025-11-23 20:00:00+00	10
845	1	6	2025-11-24 01:00:00+00	10
846	2	7	2025-11-24 06:00:00+00	-2
847	3	8	2025-11-24 11:00:00+00	10
848	4	9	2025-11-24 16:00:00+00	10
849	5	10	2025-11-24 21:00:00+00	-2
850	1	11	2025-11-25 02:00:00+00	10
851	2	12	2025-11-25 07:00:00+00	10
852	3	13	2025-11-25 12:00:00+00	-2
853	4	14	2025-11-25 17:00:00+00	10
854	5	15	2025-11-25 22:00:00+00	10
855	1	16	2025-11-26 03:00:00+00	-2
856	2	17	2025-11-26 08:00:00+00	10
857	3	18	2025-11-26 13:00:00+00	10
858	4	19	2025-11-26 18:00:00+00	-2
859	5	20	2025-11-26 23:00:00+00	10
860	1	21	2025-11-27 04:00:00+00	10
861	2	22	2025-11-27 09:00:00+00	-2
862	3	23	2025-11-27 14:00:00+00	10
863	4	24	2025-11-27 19:00:00+00	10
864	5	25	2025-11-28 00:00:00+00	-2
865	1	26	2025-11-28 05:00:00+00	10
866	2	27	2025-11-28 10:00:00+00	10
867	3	28	2025-11-28 15:00:00+00	-2
868	4	29	2025-11-28 20:00:00+00	10
869	5	30	2025-11-29 01:00:00+00	10
870	1	31	2025-11-29 06:00:00+00	-2
871	2	32	2025-11-29 11:00:00+00	10
872	3	33	2025-11-29 16:00:00+00	10
873	4	34	2025-11-29 21:00:00+00	-2
874	5	35	2025-11-30 02:00:00+00	10
875	1	36	2025-11-30 07:00:00+00	10
876	2	37	2025-11-30 12:00:00+00	-2
877	3	38	2025-11-30 17:00:00+00	10
878	4	39	2025-11-30 22:00:00+00	10
879	5	40	2025-12-01 03:00:00+00	-2
880	1	41	2025-12-01 08:00:00+00	10
881	2	42	2025-12-01 13:00:00+00	10
882	3	43	2025-12-01 18:00:00+00	-2
883	4	44	2025-12-01 23:00:00+00	10
884	5	45	2025-12-02 04:00:00+00	10
885	1	46	2025-12-02 09:00:00+00	-2
886	2	47	2025-12-02 14:00:00+00	10
887	3	48	2025-12-02 19:00:00+00	10
888	4	49	2025-12-03 00:00:00+00	-2
889	5	50	2025-12-03 05:00:00+00	10
890	1	51	2025-12-03 10:00:00+00	10
891	2	52	2025-12-03 15:00:00+00	-2
892	3	53	2025-12-03 20:00:00+00	10
893	4	54	2025-12-04 01:00:00+00	10
894	5	55	2025-12-04 06:00:00+00	-2
895	1	56	2025-12-04 11:00:00+00	10
896	2	57	2025-12-04 16:00:00+00	10
897	3	58	2025-12-04 21:00:00+00	-2
898	4	59	2025-12-05 02:00:00+00	10
899	5	60	2025-12-05 07:00:00+00	10
900	1	61	2025-12-05 12:00:00+00	-2
901	2	62	2025-12-05 17:00:00+00	10
902	3	63	2025-12-05 22:00:00+00	10
903	4	64	2025-12-06 03:00:00+00	-2
904	5	65	2025-12-06 08:00:00+00	10
905	1	66	2025-12-06 13:00:00+00	10
906	2	67	2025-12-06 18:00:00+00	-2
907	3	68	2025-12-06 23:00:00+00	10
908	4	69	2025-12-07 04:00:00+00	10
909	5	70	2025-12-07 09:00:00+00	-2
910	1	71	2025-12-07 14:00:00+00	10
911	2	72	2025-12-07 19:00:00+00	10
912	3	73	2025-12-08 00:00:00+00	-2
913	4	74	2025-12-08 05:00:00+00	10
914	5	75	2025-12-08 10:00:00+00	10
915	1	76	2025-12-08 15:00:00+00	-2
916	2	77	2025-12-08 20:00:00+00	10
917	3	78	2025-12-09 01:00:00+00	10
918	4	79	2025-12-09 06:00:00+00	-2
919	5	80	2025-12-09 11:00:00+00	10
920	1	81	2025-12-09 16:00:00+00	10
921	2	82	2025-12-09 21:00:00+00	-2
922	3	83	2025-12-10 02:00:00+00	10
923	4	84	2025-12-10 07:00:00+00	10
924	5	85	2025-12-10 12:00:00+00	-2
925	1	86	2025-12-10 17:00:00+00	10
926	2	87	2025-12-10 22:00:00+00	10
927	3	88	2025-12-11 03:00:00+00	-2
928	4	89	2025-12-11 08:00:00+00	10
929	5	90	2025-12-11 13:00:00+00	10
930	1	91	2025-12-11 18:00:00+00	-2
931	2	92	2025-12-11 23:00:00+00	10
932	3	93	2025-12-12 04:00:00+00	10
933	4	94	2025-12-12 09:00:00+00	-2
934	5	95	2025-12-12 14:00:00+00	10
935	1	96	2025-12-12 19:00:00+00	10
936	2	97	2025-12-13 00:00:00+00	-2
937	3	98	2025-12-13 05:00:00+00	10
938	4	99	2025-12-13 10:00:00+00	10
939	5	100	2025-12-13 15:00:00+00	-2
940	1	101	2025-12-13 20:00:00+00	10
941	2	102	2025-12-14 01:00:00+00	10
942	3	103	2025-12-14 06:00:00+00	-2
943	4	104	2025-12-14 11:00:00+00	10
944	5	105	2025-12-14 16:00:00+00	10
945	1	106	2025-12-14 21:00:00+00	-2
946	2	107	2025-12-15 02:00:00+00	10
947	3	108	2025-12-15 07:00:00+00	10
948	4	109	2025-12-15 12:00:00+00	-2
949	5	110	2025-12-15 17:00:00+00	10
950	1	111	2025-12-15 22:00:00+00	10
951	2	112	2025-12-16 03:00:00+00	-2
952	3	113	2025-12-16 08:00:00+00	10
953	4	114	2025-12-16 13:00:00+00	10
954	5	115	2025-12-16 18:00:00+00	-2
955	1	116	2025-12-16 23:00:00+00	10
956	2	117	2025-12-17 04:00:00+00	10
957	3	118	2025-12-17 09:00:00+00	-2
958	4	119	2025-12-17 14:00:00+00	10
959	5	120	2025-12-17 19:00:00+00	10
960	1	1	2025-12-18 00:00:00+00	-2
961	2	2	2025-12-18 05:00:00+00	10
962	3	3	2025-12-18 10:00:00+00	10
963	4	4	2025-12-18 15:00:00+00	-2
964	5	5	2025-12-18 20:00:00+00	10
965	1	6	2025-12-19 01:00:00+00	10
966	2	7	2025-12-19 06:00:00+00	-2
967	3	8	2025-12-19 11:00:00+00	10
968	4	9	2025-12-19 16:00:00+00	10
969	5	10	2025-12-19 21:00:00+00	-2
970	1	11	2025-12-20 02:00:00+00	10
971	2	12	2025-12-20 07:00:00+00	10
972	3	13	2025-12-20 12:00:00+00	-2
973	4	14	2025-12-20 17:00:00+00	10
974	5	15	2025-12-20 22:00:00+00	10
975	1	16	2025-12-21 03:00:00+00	-2
976	2	17	2025-12-21 08:00:00+00	10
977	3	18	2025-12-21 13:00:00+00	10
978	4	19	2025-12-21 18:00:00+00	-2
979	5	20	2025-12-21 23:00:00+00	10
980	1	21	2025-12-22 04:00:00+00	10
981	2	22	2025-12-22 09:00:00+00	-2
982	3	23	2025-12-22 14:00:00+00	10
983	4	24	2025-12-22 19:00:00+00	10
984	5	25	2025-12-23 00:00:00+00	-2
985	1	26	2025-12-23 05:00:00+00	10
986	2	27	2025-12-23 10:00:00+00	10
987	3	28	2025-12-23 15:00:00+00	-2
988	4	29	2025-12-23 20:00:00+00	10
989	5	30	2025-12-24 01:00:00+00	10
990	1	31	2025-12-24 06:00:00+00	-2
991	2	32	2025-12-24 11:00:00+00	10
992	3	33	2025-12-24 16:00:00+00	10
993	4	34	2025-12-24 21:00:00+00	-2
994	5	35	2025-12-25 02:00:00+00	10
995	1	36	2025-12-25 07:00:00+00	10
996	2	37	2025-12-25 12:00:00+00	-2
997	3	38	2025-12-25 17:00:00+00	10
998	4	39	2025-12-25 22:00:00+00	10
999	5	40	2025-12-26 03:00:00+00	-2
1000	1	41	2025-12-26 08:00:00+00	10
1001	2	42	2025-12-26 13:00:00+00	10
1002	3	43	2025-12-26 18:00:00+00	-2
1003	4	44	2025-12-26 23:00:00+00	10
1004	5	45	2025-12-27 04:00:00+00	10
1005	1	46	2025-12-27 09:00:00+00	-2
1006	2	47	2025-12-27 14:00:00+00	10
1007	3	48	2025-12-27 19:00:00+00	10
1008	4	49	2025-12-28 00:00:00+00	-2
1009	5	50	2025-12-28 05:00:00+00	10
1010	1	51	2025-12-28 10:00:00+00	10
1011	2	52	2025-12-28 15:00:00+00	-2
1012	3	53	2025-12-28 20:00:00+00	10
1013	4	54	2025-12-29 01:00:00+00	10
1014	5	55	2025-12-29 06:00:00+00	-2
1015	1	56	2025-12-29 11:00:00+00	10
1016	2	57	2025-12-29 16:00:00+00	10
1017	3	58	2025-12-29 21:00:00+00	-2
1018	4	59	2025-12-30 02:00:00+00	10
1019	5	60	2025-12-30 07:00:00+00	10
1020	1	61	2025-12-30 12:00:00+00	-2
1021	2	62	2025-12-30 17:00:00+00	10
1022	3	63	2025-12-30 22:00:00+00	10
1023	4	64	2025-12-31 03:00:00+00	-2
1024	5	65	2025-12-31 08:00:00+00	10
1025	1	66	2025-12-31 13:00:00+00	10
1026	2	67	2025-12-31 18:00:00+00	-2
1027	3	68	2025-12-31 23:00:00+00	10
\.


--
-- Data for Name: movements_2026; Type: TABLE DATA; Schema: inventory; Owner: -
--

COPY inventory.movements_2026 (id, store_id, product_id, moved_at, quantity) FROM stdin;
1028	4	69	2026-01-01 04:00:00+00	10
1029	5	70	2026-01-01 09:00:00+00	-2
1030	1	71	2026-01-01 14:00:00+00	10
1031	2	72	2026-01-01 19:00:00+00	10
1032	3	73	2026-01-02 00:00:00+00	-2
1033	4	74	2026-01-02 05:00:00+00	10
1034	5	75	2026-01-02 10:00:00+00	10
1035	1	76	2026-01-02 15:00:00+00	-2
1036	2	77	2026-01-02 20:00:00+00	10
1037	3	78	2026-01-03 01:00:00+00	10
1038	4	79	2026-01-03 06:00:00+00	-2
1039	5	80	2026-01-03 11:00:00+00	10
1040	1	81	2026-01-03 16:00:00+00	10
1041	2	82	2026-01-03 21:00:00+00	-2
1042	3	83	2026-01-04 02:00:00+00	10
1043	4	84	2026-01-04 07:00:00+00	10
1044	5	85	2026-01-04 12:00:00+00	-2
1045	1	86	2026-01-04 17:00:00+00	10
1046	2	87	2026-01-04 22:00:00+00	10
1047	3	88	2026-01-05 03:00:00+00	-2
1048	4	89	2026-01-05 08:00:00+00	10
1049	5	90	2026-01-05 13:00:00+00	10
1050	1	91	2026-01-05 18:00:00+00	-2
1051	2	92	2026-01-05 23:00:00+00	10
1052	3	93	2026-01-06 04:00:00+00	10
1053	4	94	2026-01-06 09:00:00+00	-2
1054	5	95	2026-01-06 14:00:00+00	10
1055	1	96	2026-01-06 19:00:00+00	10
1056	2	97	2026-01-07 00:00:00+00	-2
1057	3	98	2026-01-07 05:00:00+00	10
1058	4	99	2026-01-07 10:00:00+00	10
1059	5	100	2026-01-07 15:00:00+00	-2
1060	1	101	2026-01-07 20:00:00+00	10
1061	2	102	2026-01-08 01:00:00+00	10
1062	3	103	2026-01-08 06:00:00+00	-2
1063	4	104	2026-01-08 11:00:00+00	10
1064	5	105	2026-01-08 16:00:00+00	10
1065	1	106	2026-01-08 21:00:00+00	-2
1066	2	107	2026-01-09 02:00:00+00	10
1067	3	108	2026-01-09 07:00:00+00	10
1068	4	109	2026-01-09 12:00:00+00	-2
1069	5	110	2026-01-09 17:00:00+00	10
1070	1	111	2026-01-09 22:00:00+00	10
1071	2	112	2026-01-10 03:00:00+00	-2
1072	3	113	2026-01-10 08:00:00+00	10
1073	4	114	2026-01-10 13:00:00+00	10
1074	5	115	2026-01-10 18:00:00+00	-2
1075	1	116	2026-01-10 23:00:00+00	10
1076	2	117	2026-01-11 04:00:00+00	10
1077	3	118	2026-01-11 09:00:00+00	-2
1078	4	119	2026-01-11 14:00:00+00	10
1079	5	120	2026-01-11 19:00:00+00	10
1080	1	1	2026-01-12 00:00:00+00	-2
1081	2	2	2026-01-12 05:00:00+00	10
1082	3	3	2026-01-12 10:00:00+00	10
1083	4	4	2026-01-12 15:00:00+00	-2
1084	5	5	2026-01-12 20:00:00+00	10
1085	1	6	2026-01-13 01:00:00+00	10
1086	2	7	2026-01-13 06:00:00+00	-2
1087	3	8	2026-01-13 11:00:00+00	10
1088	4	9	2026-01-13 16:00:00+00	10
1089	5	10	2026-01-13 21:00:00+00	-2
1090	1	11	2026-01-14 02:00:00+00	10
1091	2	12	2026-01-14 07:00:00+00	10
1092	3	13	2026-01-14 12:00:00+00	-2
1093	4	14	2026-01-14 17:00:00+00	10
1094	5	15	2026-01-14 22:00:00+00	10
1095	1	16	2026-01-15 03:00:00+00	-2
1096	2	17	2026-01-15 08:00:00+00	10
1097	3	18	2026-01-15 13:00:00+00	10
1098	4	19	2026-01-15 18:00:00+00	-2
1099	5	20	2026-01-15 23:00:00+00	10
1100	1	21	2026-01-16 04:00:00+00	10
1101	2	22	2026-01-16 09:00:00+00	-2
1102	3	23	2026-01-16 14:00:00+00	10
1103	4	24	2026-01-16 19:00:00+00	10
1104	5	25	2026-01-17 00:00:00+00	-2
1105	1	26	2026-01-17 05:00:00+00	10
1106	2	27	2026-01-17 10:00:00+00	10
1107	3	28	2026-01-17 15:00:00+00	-2
1108	4	29	2026-01-17 20:00:00+00	10
1109	5	30	2026-01-18 01:00:00+00	10
1110	1	31	2026-01-18 06:00:00+00	-2
1111	2	32	2026-01-18 11:00:00+00	10
1112	3	33	2026-01-18 16:00:00+00	10
1113	4	34	2026-01-18 21:00:00+00	-2
1114	5	35	2026-01-19 02:00:00+00	10
1115	1	36	2026-01-19 07:00:00+00	10
1116	2	37	2026-01-19 12:00:00+00	-2
1117	3	38	2026-01-19 17:00:00+00	10
1118	4	39	2026-01-19 22:00:00+00	10
1119	5	40	2026-01-20 03:00:00+00	-2
1120	1	41	2026-01-20 08:00:00+00	10
1121	2	42	2026-01-20 13:00:00+00	10
1122	3	43	2026-01-20 18:00:00+00	-2
1123	4	44	2026-01-20 23:00:00+00	10
1124	5	45	2026-01-21 04:00:00+00	10
1125	1	46	2026-01-21 09:00:00+00	-2
1126	2	47	2026-01-21 14:00:00+00	10
1127	3	48	2026-01-21 19:00:00+00	10
1128	4	49	2026-01-22 00:00:00+00	-2
1129	5	50	2026-01-22 05:00:00+00	10
1130	1	51	2026-01-22 10:00:00+00	10
1131	2	52	2026-01-22 15:00:00+00	-2
1132	3	53	2026-01-22 20:00:00+00	10
1133	4	54	2026-01-23 01:00:00+00	10
1134	5	55	2026-01-23 06:00:00+00	-2
1135	1	56	2026-01-23 11:00:00+00	10
1136	2	57	2026-01-23 16:00:00+00	10
1137	3	58	2026-01-23 21:00:00+00	-2
1138	4	59	2026-01-24 02:00:00+00	10
1139	5	60	2026-01-24 07:00:00+00	10
1140	1	61	2026-01-24 12:00:00+00	-2
1141	2	62	2026-01-24 17:00:00+00	10
1142	3	63	2026-01-24 22:00:00+00	10
1143	4	64	2026-01-25 03:00:00+00	-2
1144	5	65	2026-01-25 08:00:00+00	10
1145	1	66	2026-01-25 13:00:00+00	10
1146	2	67	2026-01-25 18:00:00+00	-2
1147	3	68	2026-01-25 23:00:00+00	10
1148	4	69	2026-01-26 04:00:00+00	10
1149	5	70	2026-01-26 09:00:00+00	-2
1150	1	71	2026-01-26 14:00:00+00	10
1151	2	72	2026-01-26 19:00:00+00	10
1152	3	73	2026-01-27 00:00:00+00	-2
1153	4	74	2026-01-27 05:00:00+00	10
1154	5	75	2026-01-27 10:00:00+00	10
1155	1	76	2026-01-27 15:00:00+00	-2
1156	2	77	2026-01-27 20:00:00+00	10
1157	3	78	2026-01-28 01:00:00+00	10
1158	4	79	2026-01-28 06:00:00+00	-2
1159	5	80	2026-01-28 11:00:00+00	10
1160	1	81	2026-01-28 16:00:00+00	10
1161	2	82	2026-01-28 21:00:00+00	-2
1162	3	83	2026-01-29 02:00:00+00	10
1163	4	84	2026-01-29 07:00:00+00	10
1164	5	85	2026-01-29 12:00:00+00	-2
1165	1	86	2026-01-29 17:00:00+00	10
1166	2	87	2026-01-29 22:00:00+00	10
1167	3	88	2026-01-30 03:00:00+00	-2
1168	4	89	2026-01-30 08:00:00+00	10
1169	5	90	2026-01-30 13:00:00+00	10
1170	1	91	2026-01-30 18:00:00+00	-2
1171	2	92	2026-01-30 23:00:00+00	10
1172	3	93	2026-01-31 04:00:00+00	10
1173	4	94	2026-01-31 09:00:00+00	-2
1174	5	95	2026-01-31 14:00:00+00	10
1175	1	96	2026-01-31 19:00:00+00	10
1176	2	97	2026-02-01 00:00:00+00	-2
1177	3	98	2026-02-01 05:00:00+00	10
1178	4	99	2026-02-01 10:00:00+00	10
1179	5	100	2026-02-01 15:00:00+00	-2
1180	1	101	2026-02-01 20:00:00+00	10
1181	2	102	2026-02-02 01:00:00+00	10
1182	3	103	2026-02-02 06:00:00+00	-2
1183	4	104	2026-02-02 11:00:00+00	10
1184	5	105	2026-02-02 16:00:00+00	10
1185	1	106	2026-02-02 21:00:00+00	-2
1186	2	107	2026-02-03 02:00:00+00	10
1187	3	108	2026-02-03 07:00:00+00	10
1188	4	109	2026-02-03 12:00:00+00	-2
1189	5	110	2026-02-03 17:00:00+00	10
1190	1	111	2026-02-03 22:00:00+00	10
1191	2	112	2026-02-04 03:00:00+00	-2
1192	3	113	2026-02-04 08:00:00+00	10
1193	4	114	2026-02-04 13:00:00+00	10
1194	5	115	2026-02-04 18:00:00+00	-2
1195	1	116	2026-02-04 23:00:00+00	10
1196	2	117	2026-02-05 04:00:00+00	10
1197	3	118	2026-02-05 09:00:00+00	-2
1198	4	119	2026-02-05 14:00:00+00	10
1199	5	120	2026-02-05 19:00:00+00	10
1200	1	1	2026-02-06 00:00:00+00	-2
1201	2	2	2026-02-06 05:00:00+00	10
1202	3	3	2026-02-06 10:00:00+00	10
1203	4	4	2026-02-06 15:00:00+00	-2
1204	5	5	2026-02-06 20:00:00+00	10
1205	1	6	2026-02-07 01:00:00+00	10
1206	2	7	2026-02-07 06:00:00+00	-2
1207	3	8	2026-02-07 11:00:00+00	10
1208	4	9	2026-02-07 16:00:00+00	10
1209	5	10	2026-02-07 21:00:00+00	-2
1210	1	11	2026-02-08 02:00:00+00	10
1211	2	12	2026-02-08 07:00:00+00	10
1212	3	13	2026-02-08 12:00:00+00	-2
1213	4	14	2026-02-08 17:00:00+00	10
1214	5	15	2026-02-08 22:00:00+00	10
1215	1	16	2026-02-09 03:00:00+00	-2
1216	2	17	2026-02-09 08:00:00+00	10
1217	3	18	2026-02-09 13:00:00+00	10
1218	4	19	2026-02-09 18:00:00+00	-2
1219	5	20	2026-02-09 23:00:00+00	10
1220	1	21	2026-02-10 04:00:00+00	10
1221	2	22	2026-02-10 09:00:00+00	-2
1222	3	23	2026-02-10 14:00:00+00	10
1223	4	24	2026-02-10 19:00:00+00	10
1224	5	25	2026-02-11 00:00:00+00	-2
1225	1	26	2026-02-11 05:00:00+00	10
1226	2	27	2026-02-11 10:00:00+00	10
1227	3	28	2026-02-11 15:00:00+00	-2
1228	4	29	2026-02-11 20:00:00+00	10
1229	5	30	2026-02-12 01:00:00+00	10
1230	1	31	2026-02-12 06:00:00+00	-2
1231	2	32	2026-02-12 11:00:00+00	10
1232	3	33	2026-02-12 16:00:00+00	10
1233	4	34	2026-02-12 21:00:00+00	-2
1234	5	35	2026-02-13 02:00:00+00	10
1235	1	36	2026-02-13 07:00:00+00	10
1236	2	37	2026-02-13 12:00:00+00	-2
1237	3	38	2026-02-13 17:00:00+00	10
1238	4	39	2026-02-13 22:00:00+00	10
1239	5	40	2026-02-14 03:00:00+00	-2
1240	1	41	2026-02-14 08:00:00+00	10
1241	2	42	2026-02-14 13:00:00+00	10
1242	3	43	2026-02-14 18:00:00+00	-2
1243	4	44	2026-02-14 23:00:00+00	10
1244	5	45	2026-02-15 04:00:00+00	10
1245	1	46	2026-02-15 09:00:00+00	-2
1246	2	47	2026-02-15 14:00:00+00	10
1247	3	48	2026-02-15 19:00:00+00	10
1248	4	49	2026-02-16 00:00:00+00	-2
1249	5	50	2026-02-16 05:00:00+00	10
1250	1	51	2026-02-16 10:00:00+00	10
1251	2	52	2026-02-16 15:00:00+00	-2
1252	3	53	2026-02-16 20:00:00+00	10
1253	4	54	2026-02-17 01:00:00+00	10
1254	5	55	2026-02-17 06:00:00+00	-2
1255	1	56	2026-02-17 11:00:00+00	10
1256	2	57	2026-02-17 16:00:00+00	10
1257	3	58	2026-02-17 21:00:00+00	-2
1258	4	59	2026-02-18 02:00:00+00	10
1259	5	60	2026-02-18 07:00:00+00	10
1260	1	61	2026-02-18 12:00:00+00	-2
1261	2	62	2026-02-18 17:00:00+00	10
1262	3	63	2026-02-18 22:00:00+00	10
1263	4	64	2026-02-19 03:00:00+00	-2
1264	5	65	2026-02-19 08:00:00+00	10
1265	1	66	2026-02-19 13:00:00+00	10
1266	2	67	2026-02-19 18:00:00+00	-2
1267	3	68	2026-02-19 23:00:00+00	10
1268	4	69	2026-02-20 04:00:00+00	10
1269	5	70	2026-02-20 09:00:00+00	-2
1270	1	71	2026-02-20 14:00:00+00	10
1271	2	72	2026-02-20 19:00:00+00	10
1272	3	73	2026-02-21 00:00:00+00	-2
1273	4	74	2026-02-21 05:00:00+00	10
1274	5	75	2026-02-21 10:00:00+00	10
1275	1	76	2026-02-21 15:00:00+00	-2
1276	2	77	2026-02-21 20:00:00+00	10
1277	3	78	2026-02-22 01:00:00+00	10
1278	4	79	2026-02-22 06:00:00+00	-2
1279	5	80	2026-02-22 11:00:00+00	10
1280	1	81	2026-02-22 16:00:00+00	10
1281	2	82	2026-02-22 21:00:00+00	-2
1282	3	83	2026-02-23 02:00:00+00	10
1283	4	84	2026-02-23 07:00:00+00	10
1284	5	85	2026-02-23 12:00:00+00	-2
1285	1	86	2026-02-23 17:00:00+00	10
1286	2	87	2026-02-23 22:00:00+00	10
1287	3	88	2026-02-24 03:00:00+00	-2
1288	4	89	2026-02-24 08:00:00+00	10
1289	5	90	2026-02-24 13:00:00+00	10
1290	1	91	2026-02-24 18:00:00+00	-2
1291	2	92	2026-02-24 23:00:00+00	10
1292	3	93	2026-02-25 04:00:00+00	10
1293	4	94	2026-02-25 09:00:00+00	-2
1294	5	95	2026-02-25 14:00:00+00	10
1295	1	96	2026-02-25 19:00:00+00	10
1296	2	97	2026-02-26 00:00:00+00	-2
1297	3	98	2026-02-26 05:00:00+00	10
1298	4	99	2026-02-26 10:00:00+00	10
1299	5	100	2026-02-26 15:00:00+00	-2
1300	1	101	2026-02-26 20:00:00+00	10
1301	2	102	2026-02-27 01:00:00+00	10
1302	3	103	2026-02-27 06:00:00+00	-2
1303	4	104	2026-02-27 11:00:00+00	10
1304	5	105	2026-02-27 16:00:00+00	10
1305	1	106	2026-02-27 21:00:00+00	-2
1306	2	107	2026-02-28 02:00:00+00	10
1307	3	108	2026-02-28 07:00:00+00	10
1308	4	109	2026-02-28 12:00:00+00	-2
1309	5	110	2026-02-28 17:00:00+00	10
1310	1	111	2026-02-28 22:00:00+00	10
1311	2	112	2026-03-01 03:00:00+00	-2
1312	3	113	2026-03-01 08:00:00+00	10
1313	4	114	2026-03-01 13:00:00+00	10
1314	5	115	2026-03-01 18:00:00+00	-2
1315	1	116	2026-03-01 23:00:00+00	10
1316	2	117	2026-03-02 04:00:00+00	10
1317	3	118	2026-03-02 09:00:00+00	-2
1318	4	119	2026-03-02 14:00:00+00	10
1319	5	120	2026-03-02 19:00:00+00	10
1320	1	1	2026-03-03 00:00:00+00	-2
1321	2	2	2026-03-03 05:00:00+00	10
1322	3	3	2026-03-03 10:00:00+00	10
1323	4	4	2026-03-03 15:00:00+00	-2
1324	5	5	2026-03-03 20:00:00+00	10
1325	1	6	2026-03-04 01:00:00+00	10
1326	2	7	2026-03-04 06:00:00+00	-2
1327	3	8	2026-03-04 11:00:00+00	10
1328	4	9	2026-03-04 16:00:00+00	10
1329	5	10	2026-03-04 21:00:00+00	-2
1330	1	11	2026-03-05 02:00:00+00	10
1331	2	12	2026-03-05 07:00:00+00	10
1332	3	13	2026-03-05 12:00:00+00	-2
1333	4	14	2026-03-05 17:00:00+00	10
1334	5	15	2026-03-05 22:00:00+00	10
1335	1	16	2026-03-06 03:00:00+00	-2
1336	2	17	2026-03-06 08:00:00+00	10
1337	3	18	2026-03-06 13:00:00+00	10
1338	4	19	2026-03-06 18:00:00+00	-2
1339	5	20	2026-03-06 23:00:00+00	10
1340	1	21	2026-03-07 04:00:00+00	10
1341	2	22	2026-03-07 09:00:00+00	-2
1342	3	23	2026-03-07 14:00:00+00	10
1343	4	24	2026-03-07 19:00:00+00	10
1344	5	25	2026-03-08 00:00:00+00	-2
1345	1	26	2026-03-08 05:00:00+00	10
1346	2	27	2026-03-08 10:00:00+00	10
1347	3	28	2026-03-08 15:00:00+00	-2
1348	4	29	2026-03-08 20:00:00+00	10
1349	5	30	2026-03-09 01:00:00+00	10
1350	1	31	2026-03-09 06:00:00+00	-2
1351	2	32	2026-03-09 11:00:00+00	10
1352	3	33	2026-03-09 16:00:00+00	10
1353	4	34	2026-03-09 21:00:00+00	-2
1354	5	35	2026-03-10 02:00:00+00	10
1355	1	36	2026-03-10 07:00:00+00	10
1356	2	37	2026-03-10 12:00:00+00	-2
1357	3	38	2026-03-10 17:00:00+00	10
1358	4	39	2026-03-10 22:00:00+00	10
1359	5	40	2026-03-11 03:00:00+00	-2
1360	1	41	2026-03-11 08:00:00+00	10
1361	2	42	2026-03-11 13:00:00+00	10
1362	3	43	2026-03-11 18:00:00+00	-2
1363	4	44	2026-03-11 23:00:00+00	10
1364	5	45	2026-03-12 04:00:00+00	10
1365	1	46	2026-03-12 09:00:00+00	-2
1366	2	47	2026-03-12 14:00:00+00	10
1367	3	48	2026-03-12 19:00:00+00	10
1368	4	49	2026-03-13 00:00:00+00	-2
1369	5	50	2026-03-13 05:00:00+00	10
1370	1	51	2026-03-13 10:00:00+00	10
1371	2	52	2026-03-13 15:00:00+00	-2
1372	3	53	2026-03-13 20:00:00+00	10
1373	4	54	2026-03-14 01:00:00+00	10
1374	5	55	2026-03-14 06:00:00+00	-2
1375	1	56	2026-03-14 11:00:00+00	10
1376	2	57	2026-03-14 16:00:00+00	10
1377	3	58	2026-03-14 21:00:00+00	-2
1378	4	59	2026-03-15 02:00:00+00	10
1379	5	60	2026-03-15 07:00:00+00	10
1380	1	61	2026-03-15 12:00:00+00	-2
1381	2	62	2026-03-15 17:00:00+00	10
1382	3	63	2026-03-15 22:00:00+00	10
1383	4	64	2026-03-16 03:00:00+00	-2
1384	5	65	2026-03-16 08:00:00+00	10
1385	1	66	2026-03-16 13:00:00+00	10
1386	2	67	2026-03-16 18:00:00+00	-2
1387	3	68	2026-03-16 23:00:00+00	10
1388	4	69	2026-03-17 04:00:00+00	10
1389	5	70	2026-03-17 09:00:00+00	-2
1390	1	71	2026-03-17 14:00:00+00	10
1391	2	72	2026-03-17 19:00:00+00	10
1392	3	73	2026-03-18 00:00:00+00	-2
1393	4	74	2026-03-18 05:00:00+00	10
1394	5	75	2026-03-18 10:00:00+00	10
1395	1	76	2026-03-18 15:00:00+00	-2
1396	2	77	2026-03-18 20:00:00+00	10
1397	3	78	2026-03-19 01:00:00+00	10
1398	4	79	2026-03-19 06:00:00+00	-2
1399	5	80	2026-03-19 11:00:00+00	10
1400	1	81	2026-03-19 16:00:00+00	10
1401	2	82	2026-03-19 21:00:00+00	-2
1402	3	83	2026-03-20 02:00:00+00	10
1403	4	84	2026-03-20 07:00:00+00	10
1404	5	85	2026-03-20 12:00:00+00	-2
1405	1	86	2026-03-20 17:00:00+00	10
1406	2	87	2026-03-20 22:00:00+00	10
1407	3	88	2026-03-21 03:00:00+00	-2
1408	4	89	2026-03-21 08:00:00+00	10
1409	5	90	2026-03-21 13:00:00+00	10
1410	1	91	2026-03-21 18:00:00+00	-2
1411	2	92	2026-03-21 23:00:00+00	10
1412	3	93	2026-03-22 04:00:00+00	10
1413	4	94	2026-03-22 09:00:00+00	-2
1414	5	95	2026-03-22 14:00:00+00	10
1415	1	96	2026-03-22 19:00:00+00	10
1416	2	97	2026-03-23 00:00:00+00	-2
1417	3	98	2026-03-23 05:00:00+00	10
1418	4	99	2026-03-23 10:00:00+00	10
1419	5	100	2026-03-23 15:00:00+00	-2
1420	1	101	2026-03-23 20:00:00+00	10
1421	2	102	2026-03-24 01:00:00+00	10
1422	3	103	2026-03-24 06:00:00+00	-2
1423	4	104	2026-03-24 11:00:00+00	10
1424	5	105	2026-03-24 16:00:00+00	10
1425	1	106	2026-03-24 21:00:00+00	-2
1426	2	107	2026-03-25 02:00:00+00	10
1427	3	108	2026-03-25 07:00:00+00	10
1428	4	109	2026-03-25 12:00:00+00	-2
1429	5	110	2026-03-25 17:00:00+00	10
1430	1	111	2026-03-25 22:00:00+00	10
1431	2	112	2026-03-26 03:00:00+00	-2
1432	3	113	2026-03-26 08:00:00+00	10
1433	4	114	2026-03-26 13:00:00+00	10
1434	5	115	2026-03-26 18:00:00+00	-2
1435	1	116	2026-03-26 23:00:00+00	10
1436	2	117	2026-03-27 04:00:00+00	10
1437	3	118	2026-03-27 09:00:00+00	-2
1438	4	119	2026-03-27 14:00:00+00	10
1439	5	120	2026-03-27 19:00:00+00	10
1440	1	1	2026-03-28 00:00:00+00	-2
1441	2	2	2026-03-28 05:00:00+00	10
1442	3	3	2026-03-28 10:00:00+00	10
1443	4	4	2026-03-28 15:00:00+00	-2
1444	5	5	2026-03-28 20:00:00+00	10
1445	1	6	2026-03-29 01:00:00+00	10
1446	2	7	2026-03-29 06:00:00+00	-2
1447	3	8	2026-03-29 11:00:00+00	10
1448	4	9	2026-03-29 16:00:00+00	10
1449	5	10	2026-03-29 21:00:00+00	-2
1450	1	11	2026-03-30 02:00:00+00	10
1451	2	12	2026-03-30 07:00:00+00	10
1452	3	13	2026-03-30 12:00:00+00	-2
1453	4	14	2026-03-30 17:00:00+00	10
1454	5	15	2026-03-30 22:00:00+00	10
1455	1	16	2026-03-31 03:00:00+00	-2
1456	2	17	2026-03-31 08:00:00+00	10
1457	3	18	2026-03-31 13:00:00+00	10
1458	4	19	2026-03-31 18:00:00+00	-2
1459	5	20	2026-03-31 23:00:00+00	10
1460	1	21	2026-04-01 04:00:00+00	10
1461	2	22	2026-04-01 09:00:00+00	-2
1462	3	23	2026-04-01 14:00:00+00	10
1463	4	24	2026-04-01 19:00:00+00	10
1464	5	25	2026-04-02 00:00:00+00	-2
1465	1	26	2026-04-02 05:00:00+00	10
1466	2	27	2026-04-02 10:00:00+00	10
1467	3	28	2026-04-02 15:00:00+00	-2
1468	4	29	2026-04-02 20:00:00+00	10
1469	5	30	2026-04-03 01:00:00+00	10
1470	1	31	2026-04-03 06:00:00+00	-2
1471	2	32	2026-04-03 11:00:00+00	10
1472	3	33	2026-04-03 16:00:00+00	10
1473	4	34	2026-04-03 21:00:00+00	-2
1474	5	35	2026-04-04 02:00:00+00	10
1475	1	36	2026-04-04 07:00:00+00	10
1476	2	37	2026-04-04 12:00:00+00	-2
1477	3	38	2026-04-04 17:00:00+00	10
1478	4	39	2026-04-04 22:00:00+00	10
1479	5	40	2026-04-05 03:00:00+00	-2
1480	1	41	2026-04-05 08:00:00+00	10
1481	2	42	2026-04-05 13:00:00+00	10
1482	3	43	2026-04-05 18:00:00+00	-2
1483	4	44	2026-04-05 23:00:00+00	10
1484	5	45	2026-04-06 04:00:00+00	10
1485	1	46	2026-04-06 09:00:00+00	-2
1486	2	47	2026-04-06 14:00:00+00	10
1487	3	48	2026-04-06 19:00:00+00	10
1488	4	49	2026-04-07 00:00:00+00	-2
1489	5	50	2026-04-07 05:00:00+00	10
1490	1	51	2026-04-07 10:00:00+00	10
1491	2	52	2026-04-07 15:00:00+00	-2
1492	3	53	2026-04-07 20:00:00+00	10
1493	4	54	2026-04-08 01:00:00+00	10
1494	5	55	2026-04-08 06:00:00+00	-2
1495	1	56	2026-04-08 11:00:00+00	10
1496	2	57	2026-04-08 16:00:00+00	10
1497	3	58	2026-04-08 21:00:00+00	-2
1498	4	59	2026-04-09 02:00:00+00	10
1499	5	60	2026-04-09 07:00:00+00	10
1500	1	61	2026-04-09 12:00:00+00	-2
1501	2	62	2026-04-09 17:00:00+00	10
1502	3	63	2026-04-09 22:00:00+00	10
1503	4	64	2026-04-10 03:00:00+00	-2
1504	5	65	2026-04-10 08:00:00+00	10
1505	1	66	2026-04-10 13:00:00+00	10
1506	2	67	2026-04-10 18:00:00+00	-2
1507	3	68	2026-04-10 23:00:00+00	10
1508	4	69	2026-04-11 04:00:00+00	10
1509	5	70	2026-04-11 09:00:00+00	-2
1510	1	71	2026-04-11 14:00:00+00	10
1511	2	72	2026-04-11 19:00:00+00	10
1512	3	73	2026-04-12 00:00:00+00	-2
1513	4	74	2026-04-12 05:00:00+00	10
1514	5	75	2026-04-12 10:00:00+00	10
1515	1	76	2026-04-12 15:00:00+00	-2
1516	2	77	2026-04-12 20:00:00+00	10
1517	3	78	2026-04-13 01:00:00+00	10
1518	4	79	2026-04-13 06:00:00+00	-2
1519	5	80	2026-04-13 11:00:00+00	10
1520	1	81	2026-04-13 16:00:00+00	10
1521	2	82	2026-04-13 21:00:00+00	-2
1522	3	83	2026-04-14 02:00:00+00	10
1523	4	84	2026-04-14 07:00:00+00	10
1524	5	85	2026-04-14 12:00:00+00	-2
1525	1	86	2026-04-14 17:00:00+00	10
1526	2	87	2026-04-14 22:00:00+00	10
1527	3	88	2026-04-15 03:00:00+00	-2
1528	4	89	2026-04-15 08:00:00+00	10
1529	5	90	2026-04-15 13:00:00+00	10
1530	1	91	2026-04-15 18:00:00+00	-2
1531	2	92	2026-04-15 23:00:00+00	10
1532	3	93	2026-04-16 04:00:00+00	10
1533	4	94	2026-04-16 09:00:00+00	-2
1534	5	95	2026-04-16 14:00:00+00	10
1535	1	96	2026-04-16 19:00:00+00	10
1536	2	97	2026-04-17 00:00:00+00	-2
1537	3	98	2026-04-17 05:00:00+00	10
1538	4	99	2026-04-17 10:00:00+00	10
1539	5	100	2026-04-17 15:00:00+00	-2
1540	1	101	2026-04-17 20:00:00+00	10
1541	2	102	2026-04-18 01:00:00+00	10
1542	3	103	2026-04-18 06:00:00+00	-2
1543	4	104	2026-04-18 11:00:00+00	10
1544	5	105	2026-04-18 16:00:00+00	10
1545	1	106	2026-04-18 21:00:00+00	-2
1546	2	107	2026-04-19 02:00:00+00	10
1547	3	108	2026-04-19 07:00:00+00	10
1548	4	109	2026-04-19 12:00:00+00	-2
1549	5	110	2026-04-19 17:00:00+00	10
1550	1	111	2026-04-19 22:00:00+00	10
1551	2	112	2026-04-20 03:00:00+00	-2
1552	3	113	2026-04-20 08:00:00+00	10
1553	4	114	2026-04-20 13:00:00+00	10
1554	5	115	2026-04-20 18:00:00+00	-2
1555	1	116	2026-04-20 23:00:00+00	10
1556	2	117	2026-04-21 04:00:00+00	10
1557	3	118	2026-04-21 09:00:00+00	-2
1558	4	119	2026-04-21 14:00:00+00	10
1559	5	120	2026-04-21 19:00:00+00	10
1560	1	1	2026-04-22 00:00:00+00	-2
1561	2	2	2026-04-22 05:00:00+00	10
1562	3	3	2026-04-22 10:00:00+00	10
1563	4	4	2026-04-22 15:00:00+00	-2
1564	5	5	2026-04-22 20:00:00+00	10
1565	1	6	2026-04-23 01:00:00+00	10
1566	2	7	2026-04-23 06:00:00+00	-2
1567	3	8	2026-04-23 11:00:00+00	10
1568	4	9	2026-04-23 16:00:00+00	10
1569	5	10	2026-04-23 21:00:00+00	-2
1570	1	11	2026-04-24 02:00:00+00	10
1571	2	12	2026-04-24 07:00:00+00	10
1572	3	13	2026-04-24 12:00:00+00	-2
1573	4	14	2026-04-24 17:00:00+00	10
1574	5	15	2026-04-24 22:00:00+00	10
1575	1	16	2026-04-25 03:00:00+00	-2
1576	2	17	2026-04-25 08:00:00+00	10
1577	3	18	2026-04-25 13:00:00+00	10
1578	4	19	2026-04-25 18:00:00+00	-2
1579	5	20	2026-04-25 23:00:00+00	10
1580	1	21	2026-04-26 04:00:00+00	10
1581	2	22	2026-04-26 09:00:00+00	-2
1582	3	23	2026-04-26 14:00:00+00	10
1583	4	24	2026-04-26 19:00:00+00	10
1584	5	25	2026-04-27 00:00:00+00	-2
1585	1	26	2026-04-27 05:00:00+00	10
1586	2	27	2026-04-27 10:00:00+00	10
1587	3	28	2026-04-27 15:00:00+00	-2
1588	4	29	2026-04-27 20:00:00+00	10
1589	5	30	2026-04-28 01:00:00+00	10
1590	1	31	2026-04-28 06:00:00+00	-2
1591	2	32	2026-04-28 11:00:00+00	10
1592	3	33	2026-04-28 16:00:00+00	10
1593	4	34	2026-04-28 21:00:00+00	-2
1594	5	35	2026-04-29 02:00:00+00	10
1595	1	36	2026-04-29 07:00:00+00	10
1596	2	37	2026-04-29 12:00:00+00	-2
1597	3	38	2026-04-29 17:00:00+00	10
1598	4	39	2026-04-29 22:00:00+00	10
1599	5	40	2026-04-30 03:00:00+00	-2
1600	1	41	2026-04-30 08:00:00+00	10
1601	2	42	2026-04-30 13:00:00+00	10
1602	3	43	2026-04-30 18:00:00+00	-2
1603	4	44	2026-04-30 23:00:00+00	10
1604	5	45	2026-05-01 04:00:00+00	10
1605	1	46	2026-05-01 09:00:00+00	-2
1606	2	47	2026-05-01 14:00:00+00	10
1607	3	48	2026-05-01 19:00:00+00	10
1608	4	49	2026-05-02 00:00:00+00	-2
1609	5	50	2026-05-02 05:00:00+00	10
1610	1	51	2026-05-02 10:00:00+00	10
1611	2	52	2026-05-02 15:00:00+00	-2
1612	3	53	2026-05-02 20:00:00+00	10
1613	4	54	2026-05-03 01:00:00+00	10
1614	5	55	2026-05-03 06:00:00+00	-2
1615	1	56	2026-05-03 11:00:00+00	10
1616	2	57	2026-05-03 16:00:00+00	10
1617	3	58	2026-05-03 21:00:00+00	-2
1618	4	59	2026-05-04 02:00:00+00	10
1619	5	60	2026-05-04 07:00:00+00	10
1620	1	61	2026-05-04 12:00:00+00	-2
1621	2	62	2026-05-04 17:00:00+00	10
1622	3	63	2026-05-04 22:00:00+00	10
1623	4	64	2026-05-05 03:00:00+00	-2
1624	5	65	2026-05-05 08:00:00+00	10
1625	1	66	2026-05-05 13:00:00+00	10
1626	2	67	2026-05-05 18:00:00+00	-2
1627	3	68	2026-05-05 23:00:00+00	10
1628	4	69	2026-05-06 04:00:00+00	10
1629	5	70	2026-05-06 09:00:00+00	-2
1630	1	71	2026-05-06 14:00:00+00	10
1631	2	72	2026-05-06 19:00:00+00	10
1632	3	73	2026-05-07 00:00:00+00	-2
1633	4	74	2026-05-07 05:00:00+00	10
1634	5	75	2026-05-07 10:00:00+00	10
1635	1	76	2026-05-07 15:00:00+00	-2
1636	2	77	2026-05-07 20:00:00+00	10
1637	3	78	2026-05-08 01:00:00+00	10
1638	4	79	2026-05-08 06:00:00+00	-2
1639	5	80	2026-05-08 11:00:00+00	10
1640	1	81	2026-05-08 16:00:00+00	10
1641	2	82	2026-05-08 21:00:00+00	-2
1642	3	83	2026-05-09 02:00:00+00	10
1643	4	84	2026-05-09 07:00:00+00	10
1644	5	85	2026-05-09 12:00:00+00	-2
1645	1	86	2026-05-09 17:00:00+00	10
1646	2	87	2026-05-09 22:00:00+00	10
1647	3	88	2026-05-10 03:00:00+00	-2
1648	4	89	2026-05-10 08:00:00+00	10
1649	5	90	2026-05-10 13:00:00+00	10
1650	1	91	2026-05-10 18:00:00+00	-2
1651	2	92	2026-05-10 23:00:00+00	10
1652	3	93	2026-05-11 04:00:00+00	10
1653	4	94	2026-05-11 09:00:00+00	-2
1654	5	95	2026-05-11 14:00:00+00	10
1655	1	96	2026-05-11 19:00:00+00	10
1656	2	97	2026-05-12 00:00:00+00	-2
1657	3	98	2026-05-12 05:00:00+00	10
1658	4	99	2026-05-12 10:00:00+00	10
1659	5	100	2026-05-12 15:00:00+00	-2
1660	1	101	2026-05-12 20:00:00+00	10
1661	2	102	2026-05-13 01:00:00+00	10
1662	3	103	2026-05-13 06:00:00+00	-2
1663	4	104	2026-05-13 11:00:00+00	10
1664	5	105	2026-05-13 16:00:00+00	10
1665	1	106	2026-05-13 21:00:00+00	-2
1666	2	107	2026-05-14 02:00:00+00	10
1667	3	108	2026-05-14 07:00:00+00	10
1668	4	109	2026-05-14 12:00:00+00	-2
1669	5	110	2026-05-14 17:00:00+00	10
1670	1	111	2026-05-14 22:00:00+00	10
1671	2	112	2026-05-15 03:00:00+00	-2
1672	3	113	2026-05-15 08:00:00+00	10
1673	4	114	2026-05-15 13:00:00+00	10
1674	5	115	2026-05-15 18:00:00+00	-2
1675	1	116	2026-05-15 23:00:00+00	10
1676	2	117	2026-05-16 04:00:00+00	10
1677	3	118	2026-05-16 09:00:00+00	-2
1678	4	119	2026-05-16 14:00:00+00	10
1679	5	120	2026-05-16 19:00:00+00	10
1680	1	1	2026-05-17 00:00:00+00	-2
1681	2	2	2026-05-17 05:00:00+00	10
1682	3	3	2026-05-17 10:00:00+00	10
1683	4	4	2026-05-17 15:00:00+00	-2
1684	5	5	2026-05-17 20:00:00+00	10
1685	1	6	2026-05-18 01:00:00+00	10
1686	2	7	2026-05-18 06:00:00+00	-2
1687	3	8	2026-05-18 11:00:00+00	10
1688	4	9	2026-05-18 16:00:00+00	10
1689	5	10	2026-05-18 21:00:00+00	-2
1690	1	11	2026-05-19 02:00:00+00	10
1691	2	12	2026-05-19 07:00:00+00	10
1692	3	13	2026-05-19 12:00:00+00	-2
1693	4	14	2026-05-19 17:00:00+00	10
1694	5	15	2026-05-19 22:00:00+00	10
1695	1	16	2026-05-20 03:00:00+00	-2
1696	2	17	2026-05-20 08:00:00+00	10
1697	3	18	2026-05-20 13:00:00+00	10
1698	4	19	2026-05-20 18:00:00+00	-2
1699	5	20	2026-05-20 23:00:00+00	10
1700	1	21	2026-05-21 04:00:00+00	10
1701	2	22	2026-05-21 09:00:00+00	-2
1702	3	23	2026-05-21 14:00:00+00	10
1703	4	24	2026-05-21 19:00:00+00	10
1704	5	25	2026-05-22 00:00:00+00	-2
1705	1	26	2026-05-22 05:00:00+00	10
1706	2	27	2026-05-22 10:00:00+00	10
1707	3	28	2026-05-22 15:00:00+00	-2
1708	4	29	2026-05-22 20:00:00+00	10
1709	5	30	2026-05-23 01:00:00+00	10
1710	1	31	2026-05-23 06:00:00+00	-2
1711	2	32	2026-05-23 11:00:00+00	10
1712	3	33	2026-05-23 16:00:00+00	10
1713	4	34	2026-05-23 21:00:00+00	-2
1714	5	35	2026-05-24 02:00:00+00	10
1715	1	36	2026-05-24 07:00:00+00	10
1716	2	37	2026-05-24 12:00:00+00	-2
1717	3	38	2026-05-24 17:00:00+00	10
1718	4	39	2026-05-24 22:00:00+00	10
1719	5	40	2026-05-25 03:00:00+00	-2
1720	1	41	2026-05-25 08:00:00+00	10
1721	2	42	2026-05-25 13:00:00+00	10
1722	3	43	2026-05-25 18:00:00+00	-2
1723	4	44	2026-05-25 23:00:00+00	10
1724	5	45	2026-05-26 04:00:00+00	10
1725	1	46	2026-05-26 09:00:00+00	-2
1726	2	47	2026-05-26 14:00:00+00	10
1727	3	48	2026-05-26 19:00:00+00	10
1728	4	49	2026-05-27 00:00:00+00	-2
1729	5	50	2026-05-27 05:00:00+00	10
1730	1	51	2026-05-27 10:00:00+00	10
1731	2	52	2026-05-27 15:00:00+00	-2
1732	3	53	2026-05-27 20:00:00+00	10
1733	4	54	2026-05-28 01:00:00+00	10
1734	5	55	2026-05-28 06:00:00+00	-2
1735	1	56	2026-05-28 11:00:00+00	10
1736	2	57	2026-05-28 16:00:00+00	10
1737	3	58	2026-05-28 21:00:00+00	-2
1738	4	59	2026-05-29 02:00:00+00	10
1739	5	60	2026-05-29 07:00:00+00	10
1740	1	61	2026-05-29 12:00:00+00	-2
1741	2	62	2026-05-29 17:00:00+00	10
1742	3	63	2026-05-29 22:00:00+00	10
1743	4	64	2026-05-30 03:00:00+00	-2
1744	5	65	2026-05-30 08:00:00+00	10
1745	1	66	2026-05-30 13:00:00+00	10
1746	2	67	2026-05-30 18:00:00+00	-2
1747	3	68	2026-05-30 23:00:00+00	10
1748	4	69	2026-05-31 04:00:00+00	10
1749	5	70	2026-05-31 09:00:00+00	-2
1750	1	71	2026-05-31 14:00:00+00	10
1751	2	72	2026-05-31 19:00:00+00	10
1752	3	73	2026-06-01 00:00:00+00	-2
1753	4	74	2026-06-01 05:00:00+00	10
1754	5	75	2026-06-01 10:00:00+00	10
1755	1	76	2026-06-01 15:00:00+00	-2
1756	2	77	2026-06-01 20:00:00+00	10
1757	3	78	2026-06-02 01:00:00+00	10
1758	4	79	2026-06-02 06:00:00+00	-2
1759	5	80	2026-06-02 11:00:00+00	10
1760	1	81	2026-06-02 16:00:00+00	10
1761	2	82	2026-06-02 21:00:00+00	-2
1762	3	83	2026-06-03 02:00:00+00	10
1763	4	84	2026-06-03 07:00:00+00	10
1764	5	85	2026-06-03 12:00:00+00	-2
1765	1	86	2026-06-03 17:00:00+00	10
1766	2	87	2026-06-03 22:00:00+00	10
1767	3	88	2026-06-04 03:00:00+00	-2
1768	4	89	2026-06-04 08:00:00+00	10
1769	5	90	2026-06-04 13:00:00+00	10
1770	1	91	2026-06-04 18:00:00+00	-2
1771	2	92	2026-06-04 23:00:00+00	10
1772	3	93	2026-06-05 04:00:00+00	10
1773	4	94	2026-06-05 09:00:00+00	-2
1774	5	95	2026-06-05 14:00:00+00	10
1775	1	96	2026-06-05 19:00:00+00	10
1776	2	97	2026-06-06 00:00:00+00	-2
1777	3	98	2026-06-06 05:00:00+00	10
1778	4	99	2026-06-06 10:00:00+00	10
1779	5	100	2026-06-06 15:00:00+00	-2
1780	1	101	2026-06-06 20:00:00+00	10
1781	2	102	2026-06-07 01:00:00+00	10
1782	3	103	2026-06-07 06:00:00+00	-2
1783	4	104	2026-06-07 11:00:00+00	10
1784	5	105	2026-06-07 16:00:00+00	10
1785	1	106	2026-06-07 21:00:00+00	-2
1786	2	107	2026-06-08 02:00:00+00	10
1787	3	108	2026-06-08 07:00:00+00	10
1788	4	109	2026-06-08 12:00:00+00	-2
1789	5	110	2026-06-08 17:00:00+00	10
1790	1	111	2026-06-08 22:00:00+00	10
1791	2	112	2026-06-09 03:00:00+00	-2
1792	3	113	2026-06-09 08:00:00+00	10
1793	4	114	2026-06-09 13:00:00+00	10
1794	5	115	2026-06-09 18:00:00+00	-2
1795	1	116	2026-06-09 23:00:00+00	10
1796	2	117	2026-06-10 04:00:00+00	10
1797	3	118	2026-06-10 09:00:00+00	-2
1798	4	119	2026-06-10 14:00:00+00	10
1799	5	120	2026-06-10 19:00:00+00	10
1800	1	1	2026-06-11 00:00:00+00	-2
1801	2	2	2026-06-11 05:00:00+00	10
1802	3	3	2026-06-11 10:00:00+00	10
1803	4	4	2026-06-11 15:00:00+00	-2
1804	5	5	2026-06-11 20:00:00+00	10
1805	1	6	2026-06-12 01:00:00+00	10
1806	2	7	2026-06-12 06:00:00+00	-2
1807	3	8	2026-06-12 11:00:00+00	10
1808	4	9	2026-06-12 16:00:00+00	10
1809	5	10	2026-06-12 21:00:00+00	-2
1810	1	11	2026-06-13 02:00:00+00	10
1811	2	12	2026-06-13 07:00:00+00	10
1812	3	13	2026-06-13 12:00:00+00	-2
1813	4	14	2026-06-13 17:00:00+00	10
1814	5	15	2026-06-13 22:00:00+00	10
1815	1	16	2026-06-14 03:00:00+00	-2
1816	2	17	2026-06-14 08:00:00+00	10
1817	3	18	2026-06-14 13:00:00+00	10
1818	4	19	2026-06-14 18:00:00+00	-2
1819	5	20	2026-06-14 23:00:00+00	10
1820	1	21	2026-06-15 04:00:00+00	10
1821	2	22	2026-06-15 09:00:00+00	-2
1822	3	23	2026-06-15 14:00:00+00	10
1823	4	24	2026-06-15 19:00:00+00	10
1824	5	25	2026-06-16 00:00:00+00	-2
1825	1	26	2026-06-16 05:00:00+00	10
1826	2	27	2026-06-16 10:00:00+00	10
1827	3	28	2026-06-16 15:00:00+00	-2
1828	4	29	2026-06-16 20:00:00+00	10
1829	5	30	2026-06-17 01:00:00+00	10
1830	1	31	2026-06-17 06:00:00+00	-2
1831	2	32	2026-06-17 11:00:00+00	10
1832	3	33	2026-06-17 16:00:00+00	10
1833	4	34	2026-06-17 21:00:00+00	-2
1834	5	35	2026-06-18 02:00:00+00	10
1835	1	36	2026-06-18 07:00:00+00	10
1836	2	37	2026-06-18 12:00:00+00	-2
1837	3	38	2026-06-18 17:00:00+00	10
1838	4	39	2026-06-18 22:00:00+00	10
1839	5	40	2026-06-19 03:00:00+00	-2
1840	1	41	2026-06-19 08:00:00+00	10
1841	2	42	2026-06-19 13:00:00+00	10
1842	3	43	2026-06-19 18:00:00+00	-2
1843	4	44	2026-06-19 23:00:00+00	10
1844	5	45	2026-06-20 04:00:00+00	10
1845	1	46	2026-06-20 09:00:00+00	-2
1846	2	47	2026-06-20 14:00:00+00	10
1847	3	48	2026-06-20 19:00:00+00	10
1848	4	49	2026-06-21 00:00:00+00	-2
1849	5	50	2026-06-21 05:00:00+00	10
1850	1	51	2026-06-21 10:00:00+00	10
1851	2	52	2026-06-21 15:00:00+00	-2
1852	3	53	2026-06-21 20:00:00+00	10
1853	4	54	2026-06-22 01:00:00+00	10
1854	5	55	2026-06-22 06:00:00+00	-2
1855	1	56	2026-06-22 11:00:00+00	10
1856	2	57	2026-06-22 16:00:00+00	10
1857	3	58	2026-06-22 21:00:00+00	-2
1858	4	59	2026-06-23 02:00:00+00	10
1859	5	60	2026-06-23 07:00:00+00	10
1860	1	61	2026-06-23 12:00:00+00	-2
1861	2	62	2026-06-23 17:00:00+00	10
1862	3	63	2026-06-23 22:00:00+00	10
1863	4	64	2026-06-24 03:00:00+00	-2
1864	5	65	2026-06-24 08:00:00+00	10
1865	1	66	2026-06-24 13:00:00+00	10
1866	2	67	2026-06-24 18:00:00+00	-2
1867	3	68	2026-06-24 23:00:00+00	10
1868	4	69	2026-06-25 04:00:00+00	10
1869	5	70	2026-06-25 09:00:00+00	-2
1870	1	71	2026-06-25 14:00:00+00	10
1871	2	72	2026-06-25 19:00:00+00	10
1872	3	73	2026-06-26 00:00:00+00	-2
1873	4	74	2026-06-26 05:00:00+00	10
1874	5	75	2026-06-26 10:00:00+00	10
1875	1	76	2026-06-26 15:00:00+00	-2
1876	2	77	2026-06-26 20:00:00+00	10
1877	3	78	2026-06-27 01:00:00+00	10
1878	4	79	2026-06-27 06:00:00+00	-2
1879	5	80	2026-06-27 11:00:00+00	10
1880	1	81	2026-06-27 16:00:00+00	10
1881	2	82	2026-06-27 21:00:00+00	-2
1882	3	83	2026-06-28 02:00:00+00	10
1883	4	84	2026-06-28 07:00:00+00	10
1884	5	85	2026-06-28 12:00:00+00	-2
1885	1	86	2026-06-28 17:00:00+00	10
1886	2	87	2026-06-28 22:00:00+00	10
1887	3	88	2026-06-29 03:00:00+00	-2
1888	4	89	2026-06-29 08:00:00+00	10
1889	5	90	2026-06-29 13:00:00+00	10
1890	1	91	2026-06-29 18:00:00+00	-2
1891	2	92	2026-06-29 23:00:00+00	10
1892	3	93	2026-06-30 04:00:00+00	10
1893	4	94	2026-06-30 09:00:00+00	-2
1894	5	95	2026-06-30 14:00:00+00	10
1895	1	96	2026-06-30 19:00:00+00	10
1896	2	97	2026-07-01 00:00:00+00	-2
1897	3	98	2026-07-01 05:00:00+00	10
1898	4	99	2026-07-01 10:00:00+00	10
1899	5	100	2026-07-01 15:00:00+00	-2
1900	1	101	2026-07-01 20:00:00+00	10
1901	2	102	2026-07-02 01:00:00+00	10
1902	3	103	2026-07-02 06:00:00+00	-2
1903	4	104	2026-07-02 11:00:00+00	10
1904	5	105	2026-07-02 16:00:00+00	10
1905	1	106	2026-07-02 21:00:00+00	-2
1906	2	107	2026-07-03 02:00:00+00	10
1907	3	108	2026-07-03 07:00:00+00	10
1908	4	109	2026-07-03 12:00:00+00	-2
1909	5	110	2026-07-03 17:00:00+00	10
1910	1	111	2026-07-03 22:00:00+00	10
1911	2	112	2026-07-04 03:00:00+00	-2
1912	3	113	2026-07-04 08:00:00+00	10
1913	4	114	2026-07-04 13:00:00+00	10
1914	5	115	2026-07-04 18:00:00+00	-2
1915	1	116	2026-07-04 23:00:00+00	10
1916	2	117	2026-07-05 04:00:00+00	10
1917	3	118	2026-07-05 09:00:00+00	-2
1918	4	119	2026-07-05 14:00:00+00	10
1919	5	120	2026-07-05 19:00:00+00	10
1920	1	1	2026-07-06 00:00:00+00	-2
1921	2	2	2026-07-06 05:00:00+00	10
1922	3	3	2026-07-06 10:00:00+00	10
1923	4	4	2026-07-06 15:00:00+00	-2
1924	5	5	2026-07-06 20:00:00+00	10
1925	1	6	2026-07-07 01:00:00+00	10
1926	2	7	2026-07-07 06:00:00+00	-2
1927	3	8	2026-07-07 11:00:00+00	10
1928	4	9	2026-07-07 16:00:00+00	10
1929	5	10	2026-07-07 21:00:00+00	-2
1930	1	11	2026-07-08 02:00:00+00	10
1931	2	12	2026-07-08 07:00:00+00	10
1932	3	13	2026-07-08 12:00:00+00	-2
1933	4	14	2026-07-08 17:00:00+00	10
1934	5	15	2026-07-08 22:00:00+00	10
1935	1	16	2026-07-09 03:00:00+00	-2
1936	2	17	2026-07-09 08:00:00+00	10
1937	3	18	2026-07-09 13:00:00+00	10
1938	4	19	2026-07-09 18:00:00+00	-2
1939	5	20	2026-07-09 23:00:00+00	10
1940	1	21	2026-07-10 04:00:00+00	10
1941	2	22	2026-07-10 09:00:00+00	-2
1942	3	23	2026-07-10 14:00:00+00	10
1943	4	24	2026-07-10 19:00:00+00	10
1944	5	25	2026-07-11 00:00:00+00	-2
1945	1	26	2026-07-11 05:00:00+00	10
1946	2	27	2026-07-11 10:00:00+00	10
1947	3	28	2026-07-11 15:00:00+00	-2
1948	4	29	2026-07-11 20:00:00+00	10
1949	5	30	2026-07-12 01:00:00+00	10
1950	1	31	2026-07-12 06:00:00+00	-2
1951	2	32	2026-07-12 11:00:00+00	10
1952	3	33	2026-07-12 16:00:00+00	10
1953	4	34	2026-07-12 21:00:00+00	-2
1954	5	35	2026-07-13 02:00:00+00	10
1955	1	36	2026-07-13 07:00:00+00	10
1956	2	37	2026-07-13 12:00:00+00	-2
1957	3	38	2026-07-13 17:00:00+00	10
1958	4	39	2026-07-13 22:00:00+00	10
1959	5	40	2026-07-14 03:00:00+00	-2
1960	1	41	2026-07-14 08:00:00+00	10
1961	2	42	2026-07-14 13:00:00+00	10
1962	3	43	2026-07-14 18:00:00+00	-2
1963	4	44	2026-07-14 23:00:00+00	10
1964	5	45	2026-07-15 04:00:00+00	10
1965	1	46	2026-07-15 09:00:00+00	-2
1966	2	47	2026-07-15 14:00:00+00	10
1967	3	48	2026-07-15 19:00:00+00	10
1968	4	49	2026-07-16 00:00:00+00	-2
1969	5	50	2026-07-16 05:00:00+00	10
1970	1	51	2026-07-16 10:00:00+00	10
1971	2	52	2026-07-16 15:00:00+00	-2
1972	3	53	2026-07-16 20:00:00+00	10
1973	4	54	2026-07-17 01:00:00+00	10
1974	5	55	2026-07-17 06:00:00+00	-2
1975	1	56	2026-07-17 11:00:00+00	10
1976	2	57	2026-07-17 16:00:00+00	10
1977	3	58	2026-07-17 21:00:00+00	-2
1978	4	59	2026-07-18 02:00:00+00	10
1979	5	60	2026-07-18 07:00:00+00	10
1980	1	61	2026-07-18 12:00:00+00	-2
1981	2	62	2026-07-18 17:00:00+00	10
1982	3	63	2026-07-18 22:00:00+00	10
1983	4	64	2026-07-19 03:00:00+00	-2
1984	5	65	2026-07-19 08:00:00+00	10
1985	1	66	2026-07-19 13:00:00+00	10
1986	2	67	2026-07-19 18:00:00+00	-2
1987	3	68	2026-07-19 23:00:00+00	10
1988	4	69	2026-07-20 04:00:00+00	10
1989	5	70	2026-07-20 09:00:00+00	-2
1990	1	71	2026-07-20 14:00:00+00	10
1991	2	72	2026-07-20 19:00:00+00	10
1992	3	73	2026-07-21 00:00:00+00	-2
1993	4	74	2026-07-21 05:00:00+00	10
1994	5	75	2026-07-21 10:00:00+00	10
1995	1	76	2026-07-21 15:00:00+00	-2
1996	2	77	2026-07-21 20:00:00+00	10
1997	3	78	2026-07-22 01:00:00+00	10
1998	4	79	2026-07-22 06:00:00+00	-2
1999	5	80	2026-07-22 11:00:00+00	10
2000	1	81	2026-07-22 16:00:00+00	10
\.


--
-- Data for Name: movements_other; Type: TABLE DATA; Schema: inventory; Owner: -
--

COPY inventory.movements_other (id, store_id, product_id, moved_at, quantity) FROM stdin;
\.


--
-- Data for Name: stock_east_west; Type: TABLE DATA; Schema: inventory; Owner: -
--

COPY inventory.stock_east_west (store_id, region, product_id, quantity) FROM stdin;
2	east	82	-32
5	west	85	-32
2	east	87	160
5	west	90	160
2	east	92	160
5	west	95	160
2	east	97	-32
5	west	100	-32
2	east	102	160
5	west	105	160
2	east	107	160
5	west	110	160
2	east	112	-32
5	west	115	-32
2	east	117	160
5	west	120	160
2	east	2	170
5	west	5	170
2	east	7	-34
5	west	10	-34
2	east	12	170
5	west	15	170
2	east	17	170
5	west	20	170
2	east	22	-34
5	west	25	-34
2	east	27	170
5	west	30	170
2	east	32	170
5	west	35	170
2	east	37	-34
5	west	40	-34
2	east	42	170
5	west	45	170
2	east	47	170
5	west	50	170
2	east	52	-34
5	west	55	-34
2	east	57	170
5	west	60	170
2	east	62	170
5	west	65	170
2	east	67	-34
5	west	70	-34
2	east	72	170
5	west	75	170
2	east	77	170
5	west	80	170
\.


--
-- Data for Name: stock_north_south; Type: TABLE DATA; Schema: inventory; Owner: -
--

COPY inventory.stock_north_south (store_id, region, product_id, quantity) FROM stdin;
3	south	83	160
4	north	84	160
1	south	86	160
3	south	88	-32
4	north	89	160
1	south	91	-32
3	south	93	160
4	north	94	-32
1	south	96	160
3	south	98	160
4	north	99	160
1	south	101	160
3	south	103	-32
4	north	104	160
1	south	106	-32
3	south	108	160
4	north	109	-32
1	south	111	160
3	south	113	160
4	north	114	160
1	south	116	160
3	south	118	-32
4	north	119	160
1	south	1	-32
3	south	3	170
4	north	4	-34
1	south	6	170
3	south	8	170
4	north	9	170
1	south	11	170
3	south	13	-34
4	north	14	170
1	south	16	-34
3	south	18	170
4	north	19	-34
1	south	21	170
3	south	23	170
4	north	24	170
1	south	26	170
3	south	28	-34
4	north	29	170
1	south	31	-34
3	south	33	170
4	north	34	-34
1	south	36	170
3	south	38	170
4	north	39	170
1	south	41	170
3	south	43	-34
4	north	44	170
1	south	46	-34
3	south	48	170
4	north	49	-34
1	south	51	170
3	south	53	170
4	north	54	170
1	south	56	170
3	south	58	-34
4	north	59	170
1	south	61	-34
3	south	63	170
4	north	64	-34
1	south	66	170
3	south	68	170
4	north	69	170
1	south	71	170
3	south	73	-34
4	north	74	170
1	south	76	-34
3	south	78	170
4	north	79	-34
1	south	81	170
\.


--
-- Data for Name: stores; Type: TABLE DATA; Schema: inventory; Owner: -
--

COPY inventory.stores (id, name, region) FROM stdin;
1	Centro	south
2	Boa Viagem	east
3	Batel	south
4	Nazaré	north
5	Online	west
\.


--
-- Data for Name: customers; Type: TABLE DATA; Schema: sales; Owner: -
--

COPY sales.customers (id, name, email, cpf, phone, password_hash, birth_date, address, referred_by, created_at) FROM stdin;
1	Customer 1	customer1@mail.example	919.729.709-01	+55 11 910007331	$2a$04$r4x7Pjpr.PJlWw0yhzYeoukDDtC7Ly/aMEUgbJniscvZvVHQLv2yu	1987-06-08	("Rua 1",1,Recife,PE,00037-000)	\N	2026-10-30 14:05:25.941706+00
2	Customer 2	customer2@mail.example	838.458.418-02	+55 11 910014662	$2a$04$ByYzQxJmhR7yhDYgrSc6r.g4eQwjOdxL7fn2tC5Tghwv/0cq.PvT.	1986-03-22	("Rua 2",2,Curitiba,PR,00074-000)	\N	2026-10-30 14:05:25.941706+00
3	Customer 3	customer3@mail.example	757.187.127-03	+55 11 910021993	$2a$04$Q/pTXlgfl7FysU2/vWmMG.ioIeD6B20QUybnfOuVaKkq1OOahtTkq	1990-06-16	("Rua 3",3,Belém,PA,00111-000)	\N	2026-10-30 14:05:25.941706+00
4	Customer 4	customer4@mail.example	676.916.836-04	+55 11 910029324	$2a$04$L5d6rt4fHxREoGU29C8dkejmKvX4LpPN53K.8Ay1nwQ.gQ2WB5Ica	1978-11-07	("Rua 4",4,"São Paulo",SP,00148-000)	\N	2026-10-30 14:05:25.941706+00
6	Customer 6	customer6@mail.example	514.374.254-06	+55 11 910043986	$2a$04$IokdaIWG6br8u62AJchWWeBur1EBRWfFVv416BvDh0edQMIrxGWxa	1967-08-15	("Rua 6",6,Curitiba,PR,00222-000)	\N	2026-10-30 14:05:25.941706+00
7	Customer 7	customer7@mail.example	433.103.963-07	+55 11 910051317	$2a$04$gLJVIMDQxakCGoyMBQ/m6u0kK5zSwTy2nHu9sZTfiz0b7cDj4r7u.	1975-04-04	("Rua 7",7,Belém,PA,00259-000)	\N	2026-10-30 14:05:25.941706+00
8	Customer 8	customer8@mail.example	352.832.672-08	+55 11 910058648	$2a$04$LVIXga05I.CZ5vq6O2n/oeHEgjQNf7o/q3D1d3tG22J5Av1adfnsi	1986-04-03	("Rua 8",8,"São Paulo",SP,00296-000)	\N	2026-10-30 14:05:25.941706+00
9	Customer 9	customer9@mail.example	271.561.381-09	+55 11 910065979	$2a$04$aT9cWkx4cd9m7J4./b9vOOsFBufm6zRRLqYWHb2klvbb.RrgNzwGS	1970-06-11	("Rua 9",9,Recife,PE,00333-000)	\N	2026-10-30 14:05:25.941706+00
11	Customer 11	customer11@mail.example	109.019.799-11	+55 11 910080641	$2a$04$GIT0I1hEDtEzyEbTaE5ahuOlgIp/dgAYe3SIHwWIarE7DyF9f.z9S	1977-11-18	("Rua 11",11,Belém,PA,00407-000)	\N	2026-10-30 14:05:25.941706+00
12	Customer 12	customer12@mail.example	028.748.508-12	+55 11 910087972	$2a$04$ZWvllJESsz2gZ/vLngCvjeWgPPVDiwg.26bjgRXlEH.fjeKLNChD2	1963-12-30	("Rua 12",12,"São Paulo",SP,00444-000)	\N	2026-10-30 14:05:25.941706+00
13	Customer 13	customer13@mail.example	947.477.217-13	+55 11 910095303	$2a$04$IJSfhB02qnFty1Ssho6NIOWr2bLiy1a3UbzX139XwgeJjrpwDi92m	1976-01-05	("Rua 13",13,Recife,PE,00481-000)	\N	2026-10-30 14:05:25.941706+00
14	Customer 14	customer14@mail.example	866.206.926-14	+55 11 910102634	$2a$04$Xr74MpyrxhX59qJspgb8ou/3zLmjUMyprnudIH6Izwlt4mg1vV9Hu	1992-10-25	("Rua 14",14,Curitiba,PR,00518-000)	\N	2026-10-30 14:05:25.941706+00
16	Customer 16	customer16@mail.example	704.664.344-16	+55 11 910117296	$2a$04$0KiVZo9M.TdebzheOE/6GuGnz7iXdM6U2a4UnoL.dy9ZbWbDwJDQy	1974-07-24	("Rua 16",16,"São Paulo",SP,00592-000)	\N	2026-10-30 14:05:25.941706+00
17	Customer 17	customer17@mail.example	623.393.053-17	+55 11 910124627	$2a$04$bO/2M.qClJnR44FKPGq2oeHpZDGsoD6o7.HE8wAF6xEJ.j2njmOEK	1989-07-31	("Rua 17",17,Recife,PE,00629-000)	\N	2026-10-30 14:05:25.941706+00
18	Customer 18	customer18@mail.example	542.122.762-18	+55 11 910131958	$2a$04$3IsiWW6WH6oNNXMVsi1pHuRMZD3FcNsJNm7.u8euhrkPfs0S6PWWW	1960-10-09	("Rua 18",18,Curitiba,PR,00666-000)	\N	2026-10-30 14:05:25.941706+00
19	Customer 19	customer19@mail.example	461.851.471-19	+55 11 910139289	$2a$04$KGfg.FjwONn6RqEVW4rIwufTj1oEaT6ZDNUImwSsbTmxqAHD37S52	1999-08-23	("Rua 19",19,Belém,PA,00703-000)	\N	2026-10-30 14:05:25.941706+00
21	Customer 21	customer21@mail.example	299.309.889-21	+55 11 910153951	$2a$04$5T8WjUhag4ESOVA288624eCO35WwgUxOl2G5gIncWJ9cxetiWi.uG	1981-02-08	("Rua 21",21,Recife,PE,00777-000)	\N	2026-10-30 14:05:25.941706+00
22	Customer 22	customer22@mail.example	218.038.598-22	+55 11 910161282	$2a$04$NjEf86WYZzVawH3b425hIeeRdK45rVY52Ty/eRInNVq2PnOLR48Ha	1980-01-04	("Rua 22",22,Curitiba,PR,00814-000)	\N	2026-10-30 14:05:25.941706+00
23	Customer 23	customer23@mail.example	137.767.307-23	+55 11 910168613	$2a$04$BhPkXumAYOPGWtGup73or..X6N4CU1y5p7r5e3MFEgf837hlAxvxq	1978-12-01	("Rua 23",23,Belém,PA,00851-000)	\N	2026-10-30 14:05:25.941706+00
24	Customer 24	customer24@mail.example	056.496.016-24	+55 11 910175944	$2a$04$YSGMgrQo6khS0UEfk5Nnu.4eoVhTBl/C1xb2ifOTYdbE9i/pvAezC	1972-10-20	("Rua 24",24,"São Paulo",SP,00888-000)	\N	2026-10-30 14:05:25.941706+00
26	Customer 26	customer26@mail.example	894.954.434-26	+55 11 910190606	$2a$04$/MDd3r/0hga7hoYGO0TBvO8cxraOFUjrJfTdNMlqOnkIHUOgDwTu.	1995-06-18	("Rua 26",26,Curitiba,PR,00962-000)	\N	2026-10-30 14:05:25.941706+00
27	Customer 27	customer27@mail.example	813.683.143-27	+55 11 910197937	$2a$04$9eMO3F4UdKX0vfFXixBWKehuNb.4p2ayx92aWD885IsXXicSFnKZq	1984-01-13	("Rua 27",27,Belém,PA,00999-000)	\N	2026-10-30 14:05:25.941706+00
28	Customer 28	customer28@mail.example	732.412.852-28	+55 11 910205268	$2a$04$skIhaxbIGW62aKkq/iMZTOCwK.lZxqoPxoAwglRPVnEPt.Iz2Hkty	1978-06-28	("Rua 28",28,"São Paulo",SP,01036-000)	\N	2026-10-30 14:05:25.941706+00
29	Customer 29	customer29@mail.example	651.141.561-29	+55 11 910212599	$2a$04$UMBnVR4Vtk8jlOQqhdHe.u0mef.hYlOzVZpU0irfUqZvKNv6ee/se	1977-05-25	("Rua 29",29,Recife,PE,01073-000)	\N	2026-10-30 14:05:25.941706+00
31	Customer 31	customer31@mail.example	489.599.979-31	+55 11 910227261	$2a$04$RL0SSfhBOJcZVU1v8n.MWetZyjbBq39HbyNcoUJj9QXyDzMB0uWim	1970-04-07	("Rua 31",31,Belém,PA,01147-000)	\N	2026-10-30 14:05:25.941706+00
32	Customer 32	customer32@mail.example	408.328.688-32	+55 11 910234592	$2a$04$aD3LweebfQ5eFLpCQMTHPukVVsydeZK8RGrPx19RvgaJUVbml.8jK	1965-06-16	("Rua 32",32,"São Paulo",SP,01184-000)	\N	2026-10-30 14:05:25.941706+00
33	Customer 33	customer33@mail.example	327.057.397-33	+55 11 910241923	$2a$04$5pbeYPfc5FWkaepANyybwORHI3zIraTpkonDrBMdqMLmX1kEVTBRO	1980-05-07	("Rua 33",33,Recife,PE,01221-000)	\N	2026-10-30 14:05:25.941706+00
34	Customer 34	customer34@mail.example	246.786.106-34	+55 11 910249254	$2a$04$s.PsTezUCCf.qSJ/PV1hOuqABCQ0WgKPpwGu51ujcGWOYDDMSYP2i	1968-09-06	("Rua 34",34,Curitiba,PR,01258-000)	\N	2026-10-30 14:05:25.941706+00
36	Customer 36	customer36@mail.example	084.244.524-36	+55 11 910263916	$2a$04$xxV2aXV5EyZsFm398jfgMOTMn3K5Ac5iS4vnPglSslpVJjKpbzV3S	1998-08-18	("Rua 36",36,"São Paulo",SP,01332-000)	\N	2026-10-30 14:05:25.941706+00
37	Customer 37	customer37@mail.example	003.973.233-37	+55 11 910271247	$2a$04$OiwPSGxDo/ejM.AfH1zae.wXhfrUXE6hfaGQjyEy9d37ahYor5vPa	1976-04-01	("Rua 37",37,Recife,PE,01369-000)	\N	2026-10-30 14:05:25.941706+00
38	Customer 38	customer38@mail.example	922.702.942-38	+55 11 910278578	$2a$04$N4N0yQd07vwQm4398BfWSONG5ket3zjwzKDqxHHOvo/U0j4DB1fE2	1982-07-03	("Rua 38",38,Curitiba,PR,01406-000)	\N	2026-10-30 14:05:25.941706+00
39	Customer 39	customer39@mail.example	841.431.651-39	+55 11 910285909	$2a$04$vw1uP2pJxAKyf6zSwF.R0eWnc8k12MhZ/NMtqiRwv2Ig4hdHlPghi	2000-10-18	("Rua 39",39,Belém,PA,01443-000)	\N	2026-10-30 14:05:25.941706+00
41	Customer 41	customer41@mail.example	679.889.069-41	+55 11 910300571	$2a$04$cYhbkAFAD1yEHu3suCgpl.C6DtIcm0EflFF7hul1HyC/V1JuWv.ae	1969-07-01	("Rua 41",41,Recife,PE,01517-000)	\N	2026-10-30 14:05:25.941706+00
42	Customer 42	customer42@mail.example	598.618.778-42	+55 11 910307902	$2a$04$B5g2plUE90K8h9kwA3hxm.ln1N19Ix2NoDsOknSf6dSpJQsyS.dI2	1962-03-03	("Rua 42",42,Curitiba,PR,01554-000)	\N	2026-10-30 14:05:25.941706+00
43	Customer 43	customer43@mail.example	517.347.487-43	+55 11 910315233	$2a$04$CtQ/Fyd7cUFTvvZJSaER2.yaMjuKM84wVbgQFuvwsaSElQcyGAyVu	2000-05-18	("Rua 43",43,Belém,PA,01591-000)	\N	2026-10-30 14:05:25.941706+00
44	Customer 44	customer44@mail.example	436.076.196-44	+55 11 910322564	$2a$04$57Azr.ud.O.SMYlkj56yw.MuLTNfKpBVGT5TaMAfxA0HPWvCgZeaG	1968-11-01	("Rua 44",44,"São Paulo",SP,01628-000)	\N	2026-10-30 14:05:25.941706+00
46	Customer 46	customer46@mail.example	274.534.614-46	+55 11 910337226	$2a$04$haoFLUdXUHKnllAaIUqtpu3LiszCyc3SBRZdoh3YRM4/lTB06S6Y.	1998-07-23	("Rua 46",46,Curitiba,PR,01702-000)	\N	2026-10-30 14:05:25.941706+00
47	Customer 47	customer47@mail.example	193.263.323-47	+55 11 910344557	$2a$04$mz8bHfM7.wNv.KXDspppC.tKZZdJX8XlMV1JYCRDbu2LxE0vl3kLu	1962-10-26	("Rua 47",47,Belém,PA,01739-000)	\N	2026-10-30 14:05:25.941706+00
48	Customer 48	customer48@mail.example	112.992.032-48	+55 11 910351888	$2a$04$DJ9b10fxwhYuv1LMTLZMWu8Msm5Zcdg6bClCkj0li2Hz96O7UCqty	1979-05-20	("Rua 48",48,"São Paulo",SP,01776-000)	\N	2026-10-30 14:05:25.941706+00
49	Customer 49	customer49@mail.example	031.721.741-49	+55 11 910359219	$2a$04$4LkylBejL8jNp3uF6t6PUOXYtrYPNHmrkQJN9xxfnUL1OqVOb2RzG	1968-02-09	("Rua 49",49,Recife,PE,01813-000)	\N	2026-10-30 14:05:25.941706+00
51	Customer 51	customer51@mail.example	869.179.159-51	+55 11 910373881	$2a$04$Pe55Q5oMdCwfypP11H0LH.JHvr8fYETfPvLtW6za6n3qc4Egtxf5e	1966-09-30	("Rua 51",51,Belém,PA,01887-000)	\N	2026-10-30 14:05:25.941706+00
52	Customer 52	customer52@mail.example	788.908.868-52	+55 11 910381212	$2a$04$ycYg1Ffm8qSRjjR8SdARducyZ4YBZFFP5kuykDL3LsJCj6r/pQ6zK	1963-01-13	("Rua 52",52,"São Paulo",SP,01924-000)	\N	2026-10-30 14:05:25.941706+00
53	Customer 53	customer53@mail.example	707.637.577-53	+55 11 910388543	$2a$04$gJw4qQCpWhB9SE2qbD.sse8NQF9Qnkx17V4RWEWZLgqCYqEoB3CSq	1960-11-22	("Rua 53",53,Recife,PE,01961-000)	\N	2026-10-30 14:05:25.941706+00
54	Customer 54	customer54@mail.example	626.366.286-54	+55 11 910395874	$2a$04$gMDa3cIYu9EVsKzPAN2RMO3NsUfepUIWajFy2ohrk90YUINwEXyiS	1995-03-05	("Rua 54",54,Curitiba,PR,01998-000)	\N	2026-10-30 14:05:25.941706+00
56	Customer 56	customer56@mail.example	464.824.704-56	+55 11 910410536	$2a$04$ADP3pZw57jdc2Hs/IBmxAOg4xzsWZEakQ3Bp3C2Leei12DI.z4Hb6	1976-03-11	("Rua 56",56,"São Paulo",SP,02072-000)	\N	2026-10-30 14:05:25.941706+00
57	Customer 57	customer57@mail.example	383.553.413-57	+55 11 910417867	$2a$04$p5H/nFTuYgXnUbadnnvAZe7nwOMXAuIuEKrLMsFSU36nEpQUuyDuK	1967-04-17	("Rua 57",57,Recife,PE,02109-000)	\N	2026-10-30 14:05:25.941706+00
58	Customer 58	customer58@mail.example	302.282.122-58	+55 11 910425198	$2a$04$cNT9iRcphaESMKxMaryG.uPIFteyRKs1kEn.k2hcE5Mmy4IZDk732	1993-05-29	("Rua 58",58,Curitiba,PR,02146-000)	\N	2026-10-30 14:05:25.941706+00
59	Customer 59	customer59@mail.example	221.011.831-59	+55 11 910432529	$2a$04$wdNS4oi/scdMZp0kdQz3Ye6kKLL77N2.3E64Wlhb8sYmfp3N4E2am	1995-06-03	("Rua 59",59,Belém,PA,02183-000)	\N	2026-10-30 14:05:25.941706+00
61	Customer 61	customer61@mail.example	059.469.249-61	+55 11 910447191	$2a$04$mCmb2bfxD.1XdRhPppTc6OArm04KgAIJqDlZmIaV31.FKMfXQjJ6O	1965-07-08	("Rua 61",61,Recife,PE,02257-000)	\N	2026-10-30 14:05:25.941706+00
62	Customer 62	customer62@mail.example	978.198.958-62	+55 11 910454522	$2a$04$3x3ufDSNWy6.Ok5gmhvVSuF.1c/UuGp3kZMS4HflVkGRvIcJ3ACp6	1971-08-22	("Rua 62",62,Curitiba,PR,02294-000)	\N	2026-10-30 14:05:25.941706+00
63	Customer 63	customer63@mail.example	897.927.667-63	+55 11 910461853	$2a$04$V5IB0NPjmsd3zS4AISh2euHPi4lf1J1cFRuwgk4XB0ZcpJOyVcaSa	2000-11-04	("Rua 63",63,Belém,PA,02331-000)	\N	2026-10-30 14:05:25.941706+00
64	Customer 64	customer64@mail.example	816.656.376-64	+55 11 910469184	$2a$04$cxBa5ZSgsTeiXWkCN96XBO/42qMk2fcfWHbYUJqYIgRuem9xpa9oe	1987-04-06	("Rua 64",64,"São Paulo",SP,02368-000)	\N	2026-10-30 14:05:25.941706+00
66	Customer 66	customer66@mail.example	654.114.794-66	+55 11 910483846	$2a$04$D5nAfWhBMFbnO9JlWTLgCu6AgDzhhorgg8GvdpzlLvVWXAJpRaJoO	1992-06-10	("Rua 66",66,Curitiba,PR,02442-000)	\N	2026-10-30 14:05:25.941706+00
67	Customer 67	customer67@mail.example	573.843.503-67	+55 11 910491177	$2a$04$1egs1fJ.n0YMGQCBN/A/quPW0RJNkO2fsQ4Q3/knnQ59VouUjvOa6	1968-05-07	("Rua 67",67,Belém,PA,02479-000)	\N	2026-10-30 14:05:25.941706+00
68	Customer 68	customer68@mail.example	492.572.212-68	+55 11 910498508	$2a$04$nCtVrht3InOwuZPc6QRG3emBUZzspDfAogDLV2qiDEZeIDgmdmzty	1989-04-05	("Rua 68",68,"São Paulo",SP,02516-000)	\N	2026-10-30 14:05:25.941706+00
69	Customer 69	customer69@mail.example	411.301.921-69	+55 11 910505839	$2a$04$PFsyYgeuxUaNevcbGwXQwOtiRy0gy54El0dDeKKVYOcJAqtgP8dCq	1981-03-24	("Rua 69",69,Recife,PE,02553-000)	\N	2026-10-30 14:05:25.941706+00
71	Customer 71	customer71@mail.example	249.759.339-71	+55 11 910520501	$2a$04$FAbUnaaql8Qqqs524Aw2UuKr3VJ2EGXTjx5AaK5Yz0FwK8NoeM.hm	1982-08-11	("Rua 71",71,Belém,PA,02627-000)	\N	2026-10-30 14:05:25.941706+00
72	Customer 72	customer72@mail.example	168.488.048-72	+55 11 910527832	$2a$04$LGVrFoSzV81zSvOxRyqhZOQHK1C2YKT0JnvEf9yjiIw1ru9u3KPfO	1966-06-28	("Rua 72",72,"São Paulo",SP,02664-000)	\N	2026-10-30 14:05:25.941706+00
73	Customer 73	customer73@mail.example	087.217.757-73	+55 11 910535163	$2a$04$Wgf1.2aB5.cXUpaMaVpukuC2vRvPW/RiME9SU81ksf2G2cM.bN.Fq	1988-12-27	("Rua 73",73,Recife,PE,02701-000)	\N	2026-10-30 14:05:25.941706+00
74	Customer 74	customer74@mail.example	006.946.466-74	+55 11 910542494	$2a$04$B1nuypHBbMh1ajPbHsqk5.tCpt1tY1uLwPEb9sPinfqHny.yIgQy6	1980-06-12	("Rua 74",74,Curitiba,PR,02738-000)	\N	2026-10-30 14:05:25.941706+00
76	Customer 76	customer76@mail.example	844.404.884-76	+55 11 910557156	$2a$04$f4nXpwAN7Yn2IhCsupuJ7eUs0FfhWnsxfPM0xf.IvQhmtXqvyVYM.	1981-08-21	("Rua 76",76,"São Paulo",SP,02812-000)	\N	2026-10-30 14:05:25.941706+00
77	Customer 77	customer77@mail.example	763.133.593-77	+55 11 910564487	$2a$04$XNXzP/NIWfHXctn1Z7AbmuMeNlLHRIADeurf0sLIILvCbRo.UMPXW	1987-09-07	("Rua 77",77,Recife,PE,02849-000)	\N	2026-10-30 14:05:25.941706+00
78	Customer 78	customer78@mail.example	682.862.302-78	+55 11 910571818	$2a$04$6fmpRd/Fq42AP/ttUz0SIeQ/pelXtEqN.fMC3wsX/x6theK42/.ay	1983-04-30	("Rua 78",78,Curitiba,PR,02886-000)	\N	2026-10-30 14:05:25.941706+00
79	Customer 79	customer79@mail.example	601.591.011-79	+55 11 910579149	$2a$04$id1Bb2WUozJvkWfRp9Vm7e5uRP9ppC/bWgsm.oFwKAJFJm6Sl7axC	1975-10-06	("Rua 79",79,Belém,PA,02923-000)	\N	2026-10-30 14:05:25.941706+00
81	Customer 81	customer81@mail.example	439.049.429-81	+55 11 910593811	$2a$04$8csHOruuNTFDLlItysL8xe8fLoti8Io48zPF5jRgoNJpP5f4yIDMO	1960-04-01	("Rua 81",81,Recife,PE,02997-000)	\N	2026-10-30 14:05:25.941706+00
82	Customer 82	customer82@mail.example	358.778.138-82	+55 11 910601142	$2a$04$NSzzyp2yUS1koHF/9UZSKOo8S0l5pxFRc8l96KOlkB/.6sORIKX8m	1977-09-23	("Rua 82",82,Curitiba,PR,03034-000)	\N	2026-10-30 14:05:25.941706+00
83	Customer 83	customer83@mail.example	277.507.847-83	+55 11 910608473	$2a$04$l94EZpweOgdJJOHyCbEq/eU3wCaCjkjgQ1nPnJRY9ZpE4JfmKM.4S	1970-10-05	("Rua 83",83,Belém,PA,03071-000)	\N	2026-10-30 14:05:25.941706+00
84	Customer 84	customer84@mail.example	196.236.556-84	+55 11 910615804	$2a$04$gfk3jTfpbdS/UOA.GatSWO.k9rbwywcpy9Tqbw7/jsCO55SrVd3OC	1970-10-16	("Rua 84",84,"São Paulo",SP,03108-000)	\N	2026-10-30 14:05:25.941706+00
86	Customer 86	customer86@mail.example	034.694.974-86	+55 11 910630466	$2a$04$kNUldsTAIJ90zcG0yA/6LuOUqCFBg9/8xMiIHgoMQDfqkBgFaqySO	1960-05-20	("Rua 86",86,Curitiba,PR,03182-000)	\N	2026-10-30 14:05:25.941706+00
87	Customer 87	customer87@mail.example	953.423.683-87	+55 11 910637797	$2a$04$WRAbQfY6TjGkzNOCO36OXOyF5SubgX5O2/QZG9nsCNasIaxL0cVHC	1985-02-02	("Rua 87",87,Belém,PA,03219-000)	\N	2026-10-30 14:05:25.941706+00
88	Customer 88	customer88@mail.example	872.152.392-88	+55 11 910645128	$2a$04$XBpsgnFWuLauwgYUPt8JrOI0fuSv.1NwHLn9Fr6l4odBBMefty4SG	1977-07-31	("Rua 88",88,"São Paulo",SP,03256-000)	\N	2026-10-30 14:05:25.941706+00
89	Customer 89	customer89@mail.example	791.881.101-89	+55 11 910652459	$2a$04$Z7j8Ym9taIQ4nvFHwtOLxOAccr6o8qXzdHcaFY2jApocgACJFqrk2	1981-02-04	("Rua 89",89,Recife,PE,03293-000)	\N	2026-10-30 14:05:25.941706+00
91	Customer 91	customer91@mail.example	629.339.519-91	+55 11 910667121	$2a$04$fTSITSNGltjNtS4vh7lMAelSps2NpRFCbnqvOEvxYDuPhazdvYjoi	1985-02-17	("Rua 91",91,Belém,PA,03367-000)	\N	2026-10-30 14:05:25.941706+00
92	Customer 92	customer92@mail.example	548.068.228-92	+55 11 910674452	$2a$04$FaSwQ6Z/lAO.xur9e3zSteyVVd6ZZEeunWfe6RsuJMRIpCQ6uOe6K	1973-10-05	("Rua 92",92,"São Paulo",SP,03404-000)	\N	2026-10-30 14:05:25.941706+00
93	Customer 93	customer93@mail.example	467.797.937-93	+55 11 910681783	$2a$04$EsxRXphBr7dPcnrpCA0x5eDHIjXHmT9mgjagbi5abrVsjuH93WiTe	1989-08-19	("Rua 93",93,Recife,PE,03441-000)	\N	2026-10-30 14:05:25.941706+00
94	Customer 94	customer94@mail.example	386.526.646-94	+55 11 910689114	$2a$04$J5eE9Eqx8RRtgCJd8DLTxO2Bd3mBccXW33t6nomZ6Wd5zkuxhaeoa	1960-05-04	("Rua 94",94,Curitiba,PR,03478-000)	\N	2026-10-30 14:05:25.941706+00
96	Customer 96	customer96@mail.example	224.984.064-96	+55 11 910703776	$2a$04$aatft2umuGgdB6c2weXLtuwiAAI1280bkNdSju5qJi2BAk.W7JmEy	1998-10-25	("Rua 96",96,"São Paulo",SP,03552-000)	\N	2026-10-30 14:05:25.941706+00
97	Customer 97	customer97@mail.example	143.713.773-97	+55 11 910711107	$2a$04$tlIrT/MGEqROFqw7fHn16e5DYwXOVAU7SZ2QFKn0Rwh47kJ5uPdQm	1969-07-24	("Rua 97",97,Recife,PE,03589-000)	\N	2026-10-30 14:05:25.941706+00
98	Customer 98	customer98@mail.example	062.442.482-98	+55 11 910718438	$2a$04$ZvEUhrTmEdB4imL9E7g4Eub474XT18aH.fehoIZKZ9YDCkWW6f1V6	1998-09-22	("Rua 98",98,Curitiba,PR,03626-000)	\N	2026-10-30 14:05:25.941706+00
99	Customer 99	customer99@mail.example	981.171.191-99	+55 11 910725769	$2a$04$38IHqITQmsa7rJaUE/3.fuoKY2AmBXqLfLlT499mTVIgH0A2qcyMK	1972-03-07	("Rua 99",99,Belém,PA,03663-000)	\N	2026-10-30 14:05:25.941706+00
101	Customer 101	customer101@mail.example	819.629.609-01	+55 11 910740431	$2a$04$P.8uleuFoWLk6PIajm3blu0u0FqgauQ.D3vLF8L1QNEkkbf0jrktK	1976-12-05	("Rua 101",101,Recife,PE,03737-000)	\N	2026-10-30 14:05:25.941706+00
102	Customer 102	customer102@mail.example	738.358.318-02	+55 11 910747762	$2a$04$33cWb7Ks48nXzl0BX51zGuIFMmMFINf5awpvRLVGICy1GzYrdCDzm	1998-08-03	("Rua 102",102,Curitiba,PR,03774-000)	\N	2026-10-30 14:05:25.941706+00
103	Customer 103	customer103@mail.example	657.087.027-03	+55 11 910755093	$2a$04$2IsxAWWmgubCgLb6o3apeO9yUD.DXv3ytmBfpi0wPnArWiYq7cYxO	1979-05-16	("Rua 103",103,Belém,PA,03811-000)	\N	2026-10-30 14:05:25.941706+00
104	Customer 104	customer104@mail.example	576.816.736-04	+55 11 910762424	$2a$04$6DR/G38u3gQ5N6jCCwAM3..O1UWI5ArG/w3RsyjxPmVP0iexD79Gu	1994-10-10	("Rua 104",104,"São Paulo",SP,03848-000)	\N	2026-10-30 14:05:25.941706+00
106	Customer 106	customer106@mail.example	414.274.154-06	+55 11 910777086	$2a$04$xIcGYd/8B5KdP.vO5zL9au.VpzpjyQJfIreDNxNj82cuUKfD2K3Um	1973-09-11	("Rua 106",106,Curitiba,PR,03922-000)	\N	2026-10-30 14:05:25.941706+00
107	Customer 107	customer107@mail.example	333.003.863-07	+55 11 910784417	$2a$04$s5Qfac15MqDvEsyOUO1iXuMmw5y2O3cQXiQ1uWsPI.2hu8gt1i8gO	1977-10-10	("Rua 107",107,Belém,PA,03959-000)	\N	2026-10-30 14:05:25.941706+00
108	Customer 108	customer108@mail.example	252.732.572-08	+55 11 910791748	$2a$04$MQZ/K7.GpnGpn3xE2lT6yePiBTTQ6GitWsxtIlQcEA6893Mq4YKni	1986-07-15	("Rua 108",108,"São Paulo",SP,03996-000)	\N	2026-10-30 14:05:25.941706+00
109	Customer 109	customer109@mail.example	171.461.281-09	+55 11 910799079	$2a$04$DwB6f/a2oKuy.JCL6WU6eu.Ua7DidxK/yywSwH3khAU5.G3F9Bu1e	1994-03-10	("Rua 109",109,Recife,PE,04033-000)	\N	2026-10-30 14:05:25.941706+00
111	Customer 111	customer111@mail.example	009.919.699-11	+55 11 910813741	$2a$04$jO0QvQ9uxKnmrbd8GXc6/.SsNW0/MqJRxk3C/./Gy3I5rK6Qd1IjW	1973-05-27	("Rua 111",111,Belém,PA,04107-000)	\N	2026-10-30 14:05:25.941706+00
112	Customer 112	customer112@mail.example	928.648.408-12	+55 11 910821072	$2a$04$KVoi7fUxdyqlciGeOTCTduXjg/M/cLJlKxhKMhttYNnfHTUhaEwYq	1981-01-27	("Rua 112",112,"São Paulo",SP,04144-000)	\N	2026-10-30 14:05:25.941706+00
113	Customer 113	customer113@mail.example	847.377.117-13	+55 11 910828403	$2a$04$xbRA0ul.p6csjDgvF4eReuLDAna6rpyLab/Cx6GWpd9Q8bpcRqoS2	1999-01-17	("Rua 113",113,Recife,PE,04181-000)	\N	2026-10-30 14:05:25.941706+00
114	Customer 114	customer114@mail.example	766.106.826-14	+55 11 910835734	$2a$04$K2bLEDyjXoaCw1gLIR.lHOrxuT07Fyk2Q7eWTqCuYQdMnjh4.2b0C	1984-08-16	("Rua 114",114,Curitiba,PR,04218-000)	\N	2026-10-30 14:05:25.941706+00
116	Customer 116	customer116@mail.example	604.564.244-16	+55 11 910850396	$2a$04$CxuQe4jWjZXZkQ0WMNQQ8OQr8gjJG3mDWBEhk/Lwm7qE44CnHINKC	1964-07-09	("Rua 116",116,"São Paulo",SP,04292-000)	\N	2026-10-30 14:05:25.941706+00
117	Customer 117	customer117@mail.example	523.293.953-17	+55 11 910857727	$2a$04$tCGbbgNKoPDQ7GYReiWRL.ddKi/yUktsxUNU29tfdEZ.cp4j8udMS	1981-01-15	("Rua 117",117,Recife,PE,04329-000)	\N	2026-10-30 14:05:25.941706+00
118	Customer 118	customer118@mail.example	442.022.662-18	+55 11 910865058	$2a$04$tuVbtUsH8dqDl6jQTsXPbOyDkfNOgeWMVOvJ8PHULHlHPrdtxd4iO	1988-03-17	("Rua 118",118,Curitiba,PR,04366-000)	\N	2026-10-30 14:05:25.941706+00
119	Customer 119	customer119@mail.example	361.751.371-19	+55 11 910872389	$2a$04$aI4HUUtn/N9yvFGostAMX.IL.11b5qxi7KDl8eC1LVEm7AispZwlW	1981-01-20	("Rua 119",119,Belém,PA,04403-000)	\N	2026-10-30 14:05:25.941706+00
121	Customer 121	customer121@mail.example	199.209.789-21	+55 11 910887051	$2a$04$VYWdNVsfgJtV5i0oPE6XD.U1kBgykPcy6t2HZW1JgKRcjfsEgGS7G	1987-03-05	("Rua 121",121,Recife,PE,04477-000)	\N	2026-10-30 14:05:25.941706+00
122	Customer 122	customer122@mail.example	118.938.498-22	+55 11 910894382	$2a$04$WfLZ9Y/ZVqZZ5gxsZa.sQuE0M.K1/CDy9HKNX/L3nNBNjiRHr/RNG	1978-02-20	("Rua 122",122,Curitiba,PR,04514-000)	\N	2026-10-30 14:05:25.941706+00
123	Customer 123	customer123@mail.example	037.667.207-23	+55 11 910901713	$2a$04$5YBvOHr5ZghumXdOaEN.pen0PYkAwPOF0M8uIKTHW/P13rr9DOstG	1966-04-12	("Rua 123",123,Belém,PA,04551-000)	\N	2026-10-30 14:05:25.941706+00
124	Customer 124	customer124@mail.example	956.396.916-24	+55 11 910909044	$2a$04$LQF.8Tv1J.79SGJmCpM74e3evRfqr13DzAuXEYcIB5tAUg1wDsise	1992-11-13	("Rua 124",124,"São Paulo",SP,04588-000)	\N	2026-10-30 14:05:25.941706+00
126	Customer 126	customer126@mail.example	794.854.334-26	+55 11 910923706	$2a$04$4E3VIdzxm8THVj6qCuuUS.9OexHn9xUtLEODYdb4em1PJ1g4WRMGG	1975-12-26	("Rua 126",126,Curitiba,PR,04662-000)	\N	2026-10-30 14:05:25.941706+00
127	Customer 127	customer127@mail.example	713.583.043-27	+55 11 910931037	$2a$04$cfkmgUjbzYZLq7sMvo2vke91AXy0C01Etrt9CpDodeKD1W8fccoyS	1971-05-06	("Rua 127",127,Belém,PA,04699-000)	\N	2026-10-30 14:05:25.941706+00
128	Customer 128	customer128@mail.example	632.312.752-28	+55 11 910938368	$2a$04$hZaUNOZYX/1LKhNDo8IGk.AlJOOfZ93zVG6.amu8865ozx3hNWTF.	1986-11-03	("Rua 128",128,"São Paulo",SP,04736-000)	\N	2026-10-30 14:05:25.941706+00
129	Customer 129	customer129@mail.example	551.041.461-29	+55 11 910945699	$2a$04$2nLr0dVuMxpGOVUzy9pai.fWpdVWcfRuPvVFVFMVrkBHI47VwPhFW	2000-11-20	("Rua 129",129,Recife,PE,04773-000)	\N	2026-10-30 14:05:25.941706+00
131	Customer 131	customer131@mail.example	389.499.879-31	+55 11 910960361	$2a$04$rJxlJPGOILiCGuNRmqyVOuPZr/n4vhomvknrNblzcc7sBkw6Y5jOO	1995-01-04	("Rua 131",131,Belém,PA,04847-000)	\N	2026-10-30 14:05:25.941706+00
132	Customer 132	customer132@mail.example	308.228.588-32	+55 11 910967692	$2a$04$JVJBf5xpc5OwaCo89RaGZ.dFm.wP6yjE4rNZmMzv57sbITGYgS5gK	1999-10-18	("Rua 132",132,"São Paulo",SP,04884-000)	\N	2026-10-30 14:05:25.941706+00
133	Customer 133	customer133@mail.example	227.957.297-33	+55 11 910975023	$2a$04$e61w9KloAyIugifwKOlhXuAVZMxwbfokClC45SWYn5ZlGBdg7FEoS	1975-11-15	("Rua 133",133,Recife,PE,04921-000)	\N	2026-10-30 14:05:25.941706+00
134	Customer 134	customer134@mail.example	146.686.006-34	+55 11 910982354	$2a$04$CFByGd1WeCD2fucWsYruEub0OiOfeWG82TKjtmOCjFDZJ4etm8cK2	1988-08-12	("Rua 134",134,Curitiba,PR,04958-000)	\N	2026-10-30 14:05:25.941706+00
136	Customer 136	customer136@mail.example	984.144.424-36	+55 11 910997016	$2a$04$GRuMNlwXgw0kXWPOamHOb.LlFfaTr1JyY.Kdy82s442XVHJkMM.QW	1982-06-11	("Rua 136",136,"São Paulo",SP,05032-000)	\N	2026-10-30 14:05:25.941706+00
137	Customer 137	customer137@mail.example	903.873.133-37	+55 11 911004347	$2a$04$oMrqpwmGzZ5HbNgWWA7DteIaCCy/.Bqz4eolbfvuKtq3Uzc0QCGGu	1996-09-12	("Rua 137",137,Recife,PE,05069-000)	\N	2026-10-30 14:05:25.941706+00
138	Customer 138	customer138@mail.example	822.602.842-38	+55 11 911011678	$2a$04$T35xJWui/Pp/qVMKB8/FR.Mux1sIK77K2tspYHQZQF6fL6/9hDgp6	1963-04-12	("Rua 138",138,Curitiba,PR,05106-000)	\N	2026-10-30 14:05:25.941706+00
139	Customer 139	customer139@mail.example	741.331.551-39	+55 11 911019009	$2a$04$ZWt/H5phZth48/0hNWUJDuHDOOBhpsY.fvPLhT8amsgQJrWQoRB/G	1999-08-22	("Rua 139",139,Belém,PA,05143-000)	\N	2026-10-30 14:05:25.941706+00
141	Customer 141	customer141@mail.example	579.789.969-41	+55 11 911033671	$2a$04$EPxCSLCX301DTSnLeDvlMekzUnyi76j.mfLSWJyQohHZmL9G1JSBK	1960-04-01	("Rua 141",141,Recife,PE,05217-000)	\N	2026-10-30 14:05:25.941706+00
142	Customer 142	customer142@mail.example	498.518.678-42	+55 11 911041002	$2a$04$1KTj1lfzfGyRg28mDWUjW.QZpv.1jbnHU4X/Kh8Sbiguiaw6/GIdy	1975-11-01	("Rua 142",142,Curitiba,PR,05254-000)	\N	2026-10-30 14:05:25.941706+00
143	Customer 143	customer143@mail.example	417.247.387-43	+55 11 911048333	$2a$04$HIB.ivTLOwIKdNnB72KHEuRX7g4O70mRMyhBNJeRGmbAjhXs0wzGK	1974-03-05	("Rua 143",143,Belém,PA,05291-000)	\N	2026-10-30 14:05:25.941706+00
144	Customer 144	customer144@mail.example	336.976.096-44	+55 11 911055664	$2a$04$dkiq2zijeryRgC4L1tldGeYfdHqnFu8nYvlXJLAfEqZK1TFhjC8Cm	1992-03-22	("Rua 144",144,"São Paulo",SP,05328-000)	\N	2026-10-30 14:05:25.941706+00
146	Customer 146	customer146@mail.example	174.434.514-46	+55 11 911070326	$2a$04$41Ljn4c7taKDp4m2iM7VnuF31ratHfxalg7DYfeWi9jAzasMlbrmu	1989-01-29	("Rua 146",146,Curitiba,PR,05402-000)	\N	2026-10-30 14:05:25.941706+00
147	Customer 147	customer147@mail.example	093.163.223-47	+55 11 911077657	$2a$04$vO6Lrzf/n73Mn0oQ5LoVOOwHjQRVPZCIfkGmndtyQzum3aiVnvIdG	1983-01-22	("Rua 147",147,Belém,PA,05439-000)	\N	2026-10-30 14:05:25.941706+00
148	Customer 148	customer148@mail.example	012.892.932-48	+55 11 911084988	$2a$04$.kMCLDsx.qVpMiH08pLO2el2c58irr3YjpU3t.E4ZeZwXQFhQnX.y	1963-07-06	("Rua 148",148,"São Paulo",SP,05476-000)	\N	2026-10-30 14:05:25.941706+00
149	Customer 149	customer149@mail.example	931.621.641-49	+55 11 911092319	$2a$04$4LcxJHWi/Nkq2Kys.x6yoeL9ip9TqaGrT89oX.GtU51Ub6vzT2jp.	1995-07-24	("Rua 149",149,Recife,PE,05513-000)	\N	2026-10-30 14:05:25.941706+00
151	Customer 151	customer151@mail.example	769.079.059-51	+55 11 911106981	$2a$04$W0zwUwZ4cICadocBUYMb7eEaLQi9sF/vl9.PYI95Yg1kNVxEJmIOC	1961-03-18	("Rua 151",151,Belém,PA,05587-000)	\N	2026-10-30 14:05:25.941706+00
152	Customer 152	customer152@mail.example	688.808.768-52	+55 11 911114312	$2a$04$nPBMY.TY9VnVw5XBQTssnehIABaf7YCxNd9sL1bLhGdaSQzAjj5mq	1983-07-23	("Rua 152",152,"São Paulo",SP,05624-000)	\N	2026-10-30 14:05:25.941706+00
153	Customer 153	customer153@mail.example	607.537.477-53	+55 11 911121643	$2a$04$DkYeCV05Xx0HVpQWzphb3.x/c9bAhRYgoL5BhS.M6N63beCvQutpG	1994-04-20	("Rua 153",153,Recife,PE,05661-000)	\N	2026-10-30 14:05:25.941706+00
154	Customer 154	customer154@mail.example	526.266.186-54	+55 11 911128974	$2a$04$WKFvRio1WMezNVup2ps.S.L/r64KrdeDGyNVUyD.5ytSVgU.yNTs2	1966-06-07	("Rua 154",154,Curitiba,PR,05698-000)	\N	2026-10-30 14:05:25.941706+00
156	Customer 156	customer156@mail.example	364.724.604-56	+55 11 911143636	$2a$04$.K4XRPQO4L8sTRCIm2/Mn.bZ.E7hCBoP.ZsFzY9GFGNp1qYfmxybG	1991-12-08	("Rua 156",156,"São Paulo",SP,05772-000)	\N	2026-10-30 14:05:25.941706+00
157	Customer 157	customer157@mail.example	283.453.313-57	+55 11 911150967	$2a$04$Scs3NAH90hK1m5AKowOF5ulVrM9CN1qB1xiP3oTKF5onRVS.gDeKG	1980-08-25	("Rua 157",157,Recife,PE,05809-000)	\N	2026-10-30 14:05:25.941706+00
158	Customer 158	customer158@mail.example	202.182.022-58	+55 11 911158298	$2a$04$YZiHdxIT0oeQJwots4YsFuOlU0ib/KmDwdcj.50zCN0iRh.FamINa	1989-07-07	("Rua 158",158,Curitiba,PR,05846-000)	\N	2026-10-30 14:05:25.941706+00
159	Customer 159	customer159@mail.example	121.911.731-59	+55 11 911165629	$2a$04$XR5rabfNwjno9uxf/hfvpOqP0YOAVJX2Nb.Ct6uYPKQ4hJ0K4dcI6	1998-10-28	("Rua 159",159,Belém,PA,05883-000)	\N	2026-10-30 14:05:25.941706+00
161	Customer 161	customer161@mail.example	959.369.149-61	+55 11 911180291	$2a$04$nzQI7y7uc2hYvVofecBN8uQV6vAHMzFuf.qjKji6n1Xt8MD8KtrNm	1961-03-13	("Rua 161",161,Recife,PE,05957-000)	\N	2026-10-30 14:05:25.941706+00
162	Customer 162	customer162@mail.example	878.098.858-62	+55 11 911187622	$2a$04$6dSkQW5Q90ForfB7ztQUde5jKQbwyR33J77ooY8nctksQTIzXNDI2	1976-01-11	("Rua 162",162,Curitiba,PR,05994-000)	\N	2026-10-30 14:05:25.941706+00
163	Customer 163	customer163@mail.example	797.827.567-63	+55 11 911194953	$2a$04$eNvhUySgtZ3FbrmJJkEIV.hFXLfQdOZZQzgyDDh4rQ1fe9/VV2VTq	1970-08-04	("Rua 163",163,Belém,PA,06031-000)	\N	2026-10-30 14:05:25.941706+00
164	Customer 164	customer164@mail.example	716.556.276-64	+55 11 911202284	$2a$04$7fFIPykmdX4Ilg3SUvRRuOEa6eUWLLNt4wC073XmRmK8yEf0NcZ36	1991-09-02	("Rua 164",164,"São Paulo",SP,06068-000)	\N	2026-10-30 14:05:25.941706+00
166	Customer 166	customer166@mail.example	554.014.694-66	+55 11 911216946	$2a$04$NO/mX4bRp5m9b14EPr/4COLRveE7OX9e/BgMynpvK66uINKDvZIEa	1966-03-28	("Rua 166",166,Curitiba,PR,06142-000)	\N	2026-10-30 14:05:25.941706+00
167	Customer 167	customer167@mail.example	473.743.403-67	+55 11 911224277	$2a$04$dGgDoTVAtZqiJRyBmcD04OBvQl5OyZPst/8HXpGABdPbROCT8vfkm	1961-09-03	("Rua 167",167,Belém,PA,06179-000)	\N	2026-10-30 14:05:25.941706+00
168	Customer 168	customer168@mail.example	392.472.112-68	+55 11 911231608	$2a$04$yEYTuCscn2.xyNAzKP9oYeFyRSIVlP4JlPECefpDWMYo4oPbtTp5a	1967-05-13	("Rua 168",168,"São Paulo",SP,06216-000)	\N	2026-10-30 14:05:25.941706+00
169	Customer 169	customer169@mail.example	311.201.821-69	+55 11 911238939	$2a$04$1zM10njQ4lAUcJo34zwsQuLCc3ZGODusLO285OwB9VLd4NZmtH4F.	1974-03-17	("Rua 169",169,Recife,PE,06253-000)	\N	2026-10-30 14:05:25.941706+00
171	Customer 171	customer171@mail.example	149.659.239-71	+55 11 911253601	$2a$04$UIO9qW0Xzo1DkFH/2tc9kuGuDxryu1c31u9DXTYmDeTR3ZBo0ffxK	1983-11-09	("Rua 171",171,Belém,PA,06327-000)	\N	2026-10-30 14:05:25.941706+00
172	Customer 172	customer172@mail.example	068.388.948-72	+55 11 911260932	$2a$04$p8CHb/TjMAliN1aGWVMFju6pSJffH8qKoYYNCdLRtvF4AbGMi56ny	1978-09-13	("Rua 172",172,"São Paulo",SP,06364-000)	\N	2026-10-30 14:05:25.941706+00
173	Customer 173	customer173@mail.example	987.117.657-73	+55 11 911268263	$2a$04$0leXPRU4T.Mq8HYinUgl7.yFXEKjJ8njnnH.x/xaYuSHBJFtVxTbe	1974-07-25	("Rua 173",173,Recife,PE,06401-000)	\N	2026-10-30 14:05:25.941706+00
174	Customer 174	customer174@mail.example	906.846.366-74	+55 11 911275594	$2a$04$ypDWQGBhePkP0/JLJplsrOhoAQf/Jvf0sNnYm6xSTNpWoajH5g336	1998-08-20	("Rua 174",174,Curitiba,PR,06438-000)	\N	2026-10-30 14:05:25.941706+00
176	Customer 176	customer176@mail.example	744.304.784-76	+55 11 911290256	$2a$04$pJKf.9Rn07YNCtllrkJcfuwh2ovzBYx.DMgPcahiZn5zRTZuQUipG	1999-10-17	("Rua 176",176,"São Paulo",SP,06512-000)	\N	2026-10-30 14:05:25.941706+00
177	Customer 177	customer177@mail.example	663.033.493-77	+55 11 911297587	$2a$04$FzB7pXMDxOxTtvNnIYbWMOYIURv155pnxfaTp9dJB5FTeRP1HN5kC	1964-04-02	("Rua 177",177,Recife,PE,06549-000)	\N	2026-10-30 14:05:25.941706+00
178	Customer 178	customer178@mail.example	582.762.202-78	+55 11 911304918	$2a$04$mP30BoXRVsmkrxDITDCtMuM6ZfDn0R/v/U5ZsBzk18/7SEIdb2dxG	1976-08-31	("Rua 178",178,Curitiba,PR,06586-000)	\N	2026-10-30 14:05:25.941706+00
179	Customer 179	customer179@mail.example	501.491.911-79	+55 11 911312249	$2a$04$RCApgw/ByKVrmusm4Qwyquf74z2E/aw8qvnBH64HIQGo0LybKtlze	2000-10-25	("Rua 179",179,Belém,PA,06623-000)	\N	2026-10-30 14:05:25.941706+00
181	Customer 181	customer181@mail.example	339.949.329-81	+55 11 911326911	$2a$04$N4y0OoeBUFxK.QauEfLXoeJe.ci0bq/f/POCqPBcJxGED30hZO.2y	1982-10-19	("Rua 181",181,Recife,PE,06697-000)	\N	2026-10-30 14:05:25.941706+00
182	Customer 182	customer182@mail.example	258.678.038-82	+55 11 911334242	$2a$04$wrjaBQtrX6uxwCLP39/le.Cm.NOLMFI0/F1Ms/lrASCYUVOpTq7o.	1984-11-19	("Rua 182",182,Curitiba,PR,06734-000)	\N	2026-10-30 14:05:25.941706+00
183	Customer 183	customer183@mail.example	177.407.747-83	+55 11 911341573	$2a$04$kqMywGn1k/QgHWpes5m74eYERG65zdZcQtetOBBWl6J.Maw7NJGsC	1992-01-11	("Rua 183",183,Belém,PA,06771-000)	\N	2026-10-30 14:05:25.941706+00
184	Customer 184	customer184@mail.example	096.136.456-84	+55 11 911348904	$2a$04$whlyLscLG/Fh3fDHXjswneuNSI/2tpE47SMFoAx24uYBlPIQ.gon6	1979-10-09	("Rua 184",184,"São Paulo",SP,06808-000)	\N	2026-10-30 14:05:25.941706+00
186	Customer 186	customer186@mail.example	934.594.874-86	+55 11 911363566	$2a$04$mJ3dtYvyf4dd2AcpL/dvgOp/U6oQla96w4I0qKprs8a6PhsU3LghS	1980-02-02	("Rua 186",186,Curitiba,PR,06882-000)	\N	2026-10-30 14:05:25.941706+00
187	Customer 187	customer187@mail.example	853.323.583-87	+55 11 911370897	$2a$04$1V9Ooov..N6PGcDbvnTtE.NgOklNUOJEfYv8yjFpYALlq/d8pleV6	1964-07-06	("Rua 187",187,Belém,PA,06919-000)	\N	2026-10-30 14:05:25.941706+00
188	Customer 188	customer188@mail.example	772.052.292-88	+55 11 911378228	$2a$04$OScCxySnx/XK4DRVdf6mgey.5hJsAihqSjpIaN8I6nmxSaBl1cd1m	1964-01-26	("Rua 188",188,"São Paulo",SP,06956-000)	\N	2026-10-30 14:05:25.941706+00
189	Customer 189	customer189@mail.example	691.781.001-89	+55 11 911385559	$2a$04$fPpeBolhZS6zvY1rCRQfiOngY9m0/gbpNWa7kB90lDNXwPtIbEr22	1978-02-06	("Rua 189",189,Recife,PE,06993-000)	\N	2026-10-30 14:05:25.941706+00
191	Customer 191	customer191@mail.example	529.239.419-91	+55 11 911400221	$2a$04$xTENDrSjGjXDxbK..xoc/eGd8qGktC2Ds8i3ijF/Mw0yJS2QauoAW	1981-05-11	("Rua 191",191,Belém,PA,07067-000)	\N	2026-10-30 14:05:25.941706+00
192	Customer 192	customer192@mail.example	448.968.128-92	+55 11 911407552	$2a$04$NCJ5g5BY.tWYr.7Kze6ujuvsHEffe1UZ6lTGg3NsnZLgX38VQKlk.	1963-06-12	("Rua 192",192,"São Paulo",SP,07104-000)	\N	2026-10-30 14:05:25.941706+00
193	Customer 193	customer193@mail.example	367.697.837-93	+55 11 911414883	$2a$04$MkluKRbV2b83QJppyGWYc.j4ZK2xSbUL3D7LtWHnyv8WNF3cetCWq	1962-03-05	("Rua 193",193,Recife,PE,07141-000)	\N	2026-10-30 14:05:25.941706+00
194	Customer 194	customer194@mail.example	286.426.546-94	+55 11 911422214	$2a$04$YIYvUycaR1iFhgYEcgNAAuUcIWKheayJWd.fIhFYVkmx2o9bk61OG	1962-06-12	("Rua 194",194,Curitiba,PR,07178-000)	\N	2026-10-30 14:05:25.941706+00
196	Customer 196	customer196@mail.example	124.884.964-96	+55 11 911436876	$2a$04$JNTEP6V.sBsCy1HhOAMg.ewOGAKiuLUDWoFVb6.PjhrbJoZmqFDe6	1977-09-16	("Rua 196",196,"São Paulo",SP,07252-000)	\N	2026-10-30 14:05:25.941706+00
197	Customer 197	customer197@mail.example	043.613.673-97	+55 11 911444207	$2a$04$gPPUmzenF2ArmqD15SzWjuV/H1k9iTM6h1.kFt/ras17Nk0prUSRi	1971-05-24	("Rua 197",197,Recife,PE,07289-000)	\N	2026-10-30 14:05:25.941706+00
198	Customer 198	customer198@mail.example	962.342.382-98	+55 11 911451538	$2a$04$Exx1MFoaX0r7DLs5qAdJpuTiEkalraJntvY3tvPY8191OfTfmae3W	1990-05-27	("Rua 198",198,Curitiba,PR,07326-000)	\N	2026-10-30 14:05:25.941706+00
199	Customer 199	customer199@mail.example	881.071.091-99	+55 11 911458869	$2a$04$SAcm48dBQDmA.spi/1oVPeIqB1uZy0genDmcOTAHkfBVv8j1mK5Ea	1964-09-16	("Rua 199",199,Belém,PA,07363-000)	\N	2026-10-30 14:05:25.941706+00
5	Customer 5	customer5@mail.example	595.645.545-05	+55 11 910036655	$2a$04$VmBTSTT2AUHarciYpEhLFu1OTVz0nCkbtp/s0Ig1JGojP4Y/h07Qi	1994-05-06	("Rua 5",5,Recife,PE,00185-000)	4	2026-10-30 14:05:25.941706+00
10	Customer 10	customer10@mail.example	190.290.090-10	+55 11 910073310	$2a$04$WWDpBXegYHHqHSnfi0.EdOpizSenS.kbHSi9gqYfmZSMYGNAGngIy	1984-12-28	("Rua 10",10,Curitiba,PR,00370-000)	9	2026-10-30 14:05:25.941706+00
15	Customer 15	customer15@mail.example	785.935.635-15	+55 11 910109965	$2a$04$IMP6cgtcmz30W3Mhtmu4FeJgk.TIwdsITqM9ssnQWEyIMjXCDsq5.	1969-04-06	("Rua 15",15,Belém,PA,00555-000)	14	2026-10-30 14:05:25.941706+00
20	Customer 20	customer20@mail.example	380.580.180-20	+55 11 910146620	$2a$04$mPxJbzVaoF2MsDvUrk.pceIuREkHLv9k5Ba0bDfczYLJCGsjXeTRO	1999-04-15	("Rua 20",20,"São Paulo",SP,00740-000)	19	2026-10-30 14:05:25.941706+00
25	Customer 25	customer25@mail.example	975.225.725-25	+55 11 910183275	$2a$04$UNr3FrlFLq46GrgYhJYJkeIafUIaJwyzkVDGBKN9bPJ7E.Xv6yG1C	1979-08-09	("Rua 25",25,Recife,PE,00925-000)	24	2026-10-30 14:05:25.941706+00
30	Customer 30	customer30@mail.example	570.870.270-30	+55 11 910219930	$2a$04$xWII0wz5cl2PeDn2Kg8qMOk4XWOffgKwvUtoaWG2NvlVn615ZFRKu	1972-04-04	("Rua 30",30,Curitiba,PR,01110-000)	29	2026-10-30 14:05:25.941706+00
35	Customer 35	customer35@mail.example	165.515.815-35	+55 11 910256585	$2a$04$5RKlaQHMadS8IEl6XjfCcO.o2k4nrMwcx8i2ZrdUsmniYmPLPNy.K	1996-08-18	("Rua 35",35,Belém,PA,01295-000)	34	2026-10-30 14:05:25.941706+00
40	Customer 40	customer40@mail.example	760.160.360-40	+55 11 910293240	$2a$04$bdaeeH0csZwXBt2fqIpkN.7eH/k0e71yMpyBb3zRIoyx3FoolDPZO	1994-07-15	("Rua 40",40,"São Paulo",SP,01480-000)	39	2026-10-30 14:05:25.941706+00
45	Customer 45	customer45@mail.example	355.805.905-45	+55 11 910329895	$2a$04$r3pu8FEJ4AziPE80TQsOE.gC97VPapMdAOinxE9v8Rf1KqpUmtQ2e	1978-10-18	("Rua 45",45,Recife,PE,01665-000)	44	2026-10-30 14:05:25.941706+00
50	Customer 50	customer50@mail.example	950.450.450-50	+55 11 910366550	$2a$04$gXe.pgCGK/Lo7XGm0lDwsOdxr4caBlhB5QmTXx98RjMG1czTqq6pm	1961-10-29	("Rua 50",50,Curitiba,PR,01850-000)	49	2026-10-30 14:05:25.941706+00
55	Customer 55	customer55@mail.example	545.095.995-55	+55 11 910403205	$2a$04$6ALe3h0rbhstucXRBQV0petrOfOdQKM8ta1TbQOLabFukVWIwMQIu	1968-03-11	("Rua 55",55,Belém,PA,02035-000)	54	2026-10-30 14:05:25.941706+00
60	Customer 60	customer60@mail.example	140.740.540-60	+55 11 910439860	$2a$04$CqKDUtiCIfEYEQt89TpkhuUnfBUZm/zSf4teAt3mVW78SDCFFpRfq	1981-01-29	("Rua 60",60,"São Paulo",SP,02220-000)	59	2026-10-30 14:05:25.941706+00
65	Customer 65	customer65@mail.example	735.385.085-65	+55 11 910476515	$2a$04$M3.zwXjYUBXzKfz.nfzBcefH8HUlcyJUS.r/jET/iVJwMmuhc8ybS	1986-08-05	("Rua 65",65,Recife,PE,02405-000)	64	2026-10-30 14:05:25.941706+00
70	Customer 70	customer70@mail.example	330.030.630-70	+55 11 910513170	$2a$04$jJt6qMGOY5TcsxWMICqJ4ODJZJix/9e68X/lRLHazLz5VEVLtb1u2	1972-05-14	("Rua 70",70,Curitiba,PR,02590-000)	69	2026-10-30 14:05:25.941706+00
75	Customer 75	customer75@mail.example	925.675.175-75	+55 11 910549825	$2a$04$cAqjPc6rK4sabJe99jhTFuGu1ggdfjC/csjzIXlJj53HQdeYLuxyu	1978-08-22	("Rua 75",75,Belém,PA,02775-000)	74	2026-10-30 14:05:25.941706+00
80	Customer 80	customer80@mail.example	520.320.720-80	+55 11 910586480	$2a$04$JIXtI8R7t42O1O5YbGNf3.bnJIXu3j3ZOIvtGikmhGWm2HmMt/MPy	1995-08-09	("Rua 80",80,"São Paulo",SP,02960-000)	79	2026-10-30 14:05:25.941706+00
85	Customer 85	customer85@mail.example	115.965.265-85	+55 11 910623135	$2a$04$6YQuAlGdDFgId55J.l47Y.OUpfyfIqblrWuqdXcwEeuUE3Xr2LFvm	1987-08-14	("Rua 85",85,Recife,PE,03145-000)	84	2026-10-30 14:05:25.941706+00
90	Customer 90	customer90@mail.example	710.610.810-90	+55 11 910659790	$2a$04$EMTNsHhqWi/tQZoM5HWjyeMAVdXqOa1yLLcGBzxMj749Gv/9GA17.	1988-10-07	("Rua 90",90,Curitiba,PR,03330-000)	89	2026-10-30 14:05:25.941706+00
95	Customer 95	customer95@mail.example	305.255.355-95	+55 11 910696445	$2a$04$T2mrUEq1u3ojLo.BlTS2IujJuajTElCa76iqfDY84u8soG61MqY1W	1981-07-27	("Rua 95",95,Belém,PA,03515-000)	94	2026-10-30 14:05:25.941706+00
100	Customer 100	customer100@mail.example	900.900.900-00	+55 11 910733100	$2a$04$Xpx3SX7PLgdlgGK3C.HkTetRPVh6b455JEeS.V9Hyto9HQGHTOxH.	1998-04-28	("Rua 100",100,"São Paulo",SP,03700-000)	99	2026-10-30 14:05:25.941706+00
105	Customer 105	customer105@mail.example	495.545.445-05	+55 11 910769755	$2a$04$7E3n13F/1oqydFChgFjUHuAwKsVWQznRDQHI6kToasnUXgZE76W1a	1968-07-13	("Rua 105",105,Recife,PE,03885-000)	104	2026-10-30 14:05:25.941706+00
110	Customer 110	customer110@mail.example	090.190.990-10	+55 11 910806410	$2a$04$PLOTb8OOIdwKmIi9NhQOqeecyE.bdqMjD4WJw57wTZCXgFCdtEfgW	1971-06-01	("Rua 110",110,Curitiba,PR,04070-000)	109	2026-10-30 14:05:25.941706+00
115	Customer 115	customer115@mail.example	685.835.535-15	+55 11 910843065	$2a$04$pk/phk5PFF.4yCIgCV5alOULyJP6yKC2qSsPh8H.CPCeZbMrEtMSi	1999-11-08	("Rua 115",115,Belém,PA,04255-000)	114	2026-10-30 14:05:25.941706+00
120	Customer 120	customer120@mail.example	280.480.080-20	+55 11 910879720	$2a$04$Xo5xbQvJciqgX6WHHJ9uYuyPmCm73wRVNONWk7bi4.XkHuSPorBlq	1975-12-01	("Rua 120",120,"São Paulo",SP,04440-000)	119	2026-10-30 14:05:25.941706+00
125	Customer 125	customer125@mail.example	875.125.625-25	+55 11 910916375	$2a$04$7g9JYBBHsfTfSkPqcQnXOOvc4EuXwalPuxm0o75iXxHGjZN/IsZ1O	1990-09-30	("Rua 125",125,Recife,PE,04625-000)	124	2026-10-30 14:05:25.941706+00
130	Customer 130	customer130@mail.example	470.770.170-30	+55 11 910953030	$2a$04$HGZiPg60NkbO6Xegy9nXTOPN.0r0HTbpZe1g57F6.0oyo8DuupWTK	1993-05-20	("Rua 130",130,Curitiba,PR,04810-000)	129	2026-10-30 14:05:25.941706+00
135	Customer 135	customer135@mail.example	065.415.715-35	+55 11 910989685	$2a$04$bN/z/3OH7MdlHnBF/uxay.LA37pX3/rbmXNKeqFPrrovSq7ZPuqDi	1995-02-09	("Rua 135",135,Belém,PA,04995-000)	134	2026-10-30 14:05:25.941706+00
140	Customer 140	customer140@mail.example	660.060.260-40	+55 11 911026340	$2a$04$PcQ8LZngzjOjvUWJyr/SuOXfRAqmIEVBcdRM76I2ZjFlYqckR.ZLy	1992-04-28	("Rua 140",140,"São Paulo",SP,05180-000)	139	2026-10-30 14:05:25.941706+00
145	Customer 145	customer145@mail.example	255.705.805-45	+55 11 911062995	$2a$04$LO2i9XcS.w5Y1LfQAAzLMu4Rixx/5.OMpTJ/bE6YJAc1bRiv/PGK.	1966-04-07	("Rua 145",145,Recife,PE,05365-000)	144	2026-10-30 14:05:25.941706+00
150	Customer 150	customer150@mail.example	850.350.350-50	+55 11 911099650	$2a$04$cQYyIA9o7Cv7hkGczSmkneWWjcvOhc6vMsyNK4bIgEvYxkO/xtfA.	1978-08-26	("Rua 150",150,Curitiba,PR,05550-000)	149	2026-10-30 14:05:25.941706+00
155	Customer 155	customer155@mail.example	445.995.895-55	+55 11 911136305	$2a$04$rE6d7ZiKrqQZcLT8XD0nMuqFEDmevw9iQZSaojI66RKObN0c6C.Qq	1967-03-31	("Rua 155",155,Belém,PA,05735-000)	154	2026-10-30 14:05:25.941706+00
160	Customer 160	customer160@mail.example	040.640.440-60	+55 11 911172960	$2a$04$DcOirp3mUk0.EKTEcW1ls.YnNaGXQ2TE2IizrV2/UZKi66RRlSxKK	1972-02-27	("Rua 160",160,"São Paulo",SP,05920-000)	159	2026-10-30 14:05:25.941706+00
165	Customer 165	customer165@mail.example	635.285.985-65	+55 11 911209615	$2a$04$7jVveAWzATO6I9a10m3aXeB3iKgcaGC.Z7gasneLZlp8Lyg7TJCJW	1995-01-01	("Rua 165",165,Recife,PE,06105-000)	164	2026-10-30 14:05:25.941706+00
170	Customer 170	customer170@mail.example	230.930.530-70	+55 11 911246270	$2a$04$T9/mXCi/01ga7WyGMS89fuD3Ii7MX/o8wJF8JmrgHb6NllLEsQByu	1964-02-01	("Rua 170",170,Curitiba,PR,06290-000)	169	2026-10-30 14:05:25.941706+00
175	Customer 175	customer175@mail.example	825.575.075-75	+55 11 911282925	$2a$04$hg4oCV7wRiCpwZDJs7OK/uLSlRTp3tc9ShXQZtUkSfj07zKl86kKG	1963-03-20	("Rua 175",175,Belém,PA,06475-000)	174	2026-10-30 14:05:25.941706+00
180	Customer 180	customer180@mail.example	420.220.620-80	+55 11 911319580	$2a$04$qpom.SKsk8kmbo4eiih69.5NLUpOiG2M1H3Xeu0XmirEdBnLhFJHy	1988-09-01	("Rua 180",180,"São Paulo",SP,06660-000)	179	2026-10-30 14:05:25.941706+00
185	Customer 185	customer185@mail.example	015.865.165-85	+55 11 911356235	$2a$04$Bl9idiUiCGxfT/BbUFOt/e1P5dUDu.E9e7F7nlFRCTgSVUlWYQK1O	1970-10-30	("Rua 185",185,Recife,PE,06845-000)	184	2026-10-30 14:05:25.941706+00
190	Customer 190	customer190@mail.example	610.510.710-90	+55 11 911392890	$2a$04$Vm3HCHGtZihMrQ8GEGajb.00wrMLFFhZdoHOvFiQjRIk0uxo00rfO	1989-07-10	("Rua 190",190,Curitiba,PR,07030-000)	189	2026-10-30 14:05:25.941706+00
195	Customer 195	customer195@mail.example	205.155.255-95	+55 11 911429545	$2a$04$cege2nPs9cuEgUfuUm0RhugCp7AFykCM0s0tVUe7L4tUIFaQJqUSW	1983-10-20	("Rua 195",195,Belém,PA,07215-000)	194	2026-10-30 14:05:25.941706+00
200	Customer 200	customer200@mail.example	800.800.800-00	+55 11 911466200	$2a$04$rNOp9SCF8jCt70Jg.FN6suOEVhPFy0xK1CY4dvTvNTyGSV74Vkx3m	1990-01-24	("Rua 200",200,"São Paulo",SP,07400-000)	199	2026-10-30 14:05:25.941706+00
\.


--
-- Data for Name: order_items; Type: TABLE DATA; Schema: sales; Owner: -
--

COPY sales.order_items (order_id, line, product_id, quantity, unit_price) FROM stdin;
1	1	39	3	393.69
2	1	70	4	63.00
3	1	101	1	109.42
4	1	12	2	485.03
5	1	43	3	124.92
6	1	74	4	414.12
7	1	105	1	78.00
8	1	16	2	105.10
9	1	47	3	68.49
10	1	78	4	85.32
11	1	109	1	452.51
12	1	20	2	407.25
13	1	51	3	101.97
14	1	82	4	322.76
15	1	113	1	439.42
16	1	24	2	238.02
17	1	55	3	319.76
18	1	86	4	445.44
19	1	117	1	433.00
20	1	28	2	184.00
21	1	59	3	453.36
22	1	90	4	249.60
23	1	1	1	374.04
24	1	32	2	322.28
25	1	63	3	21.47
26	1	94	4	334.09
27	1	5	1	56.19
28	1	36	2	69.53
29	1	67	3	141.23
30	1	98	4	443.40
31	1	9	1	291.99
32	1	40	2	98.73
33	1	71	3	145.48
34	1	102	4	80.97
35	1	13	1	420.80
36	1	44	2	327.20
37	1	75	3	180.28
38	1	106	4	313.21
39	1	17	1	162.82
40	1	48	2	64.78
41	1	79	3	168.09
42	1	110	4	388.06
43	1	21	1	210.74
44	1	52	2	473.28
45	1	83	3	286.19
46	1	114	4	113.36
47	1	25	1	488.70
48	1	56	2	91.98
49	1	87	3	279.57
50	1	118	4	284.66
51	1	29	1	249.73
52	1	60	2	385.15
53	1	91	3	494.48
54	1	2	4	187.61
55	1	33	1	143.19
56	1	64	2	448.59
57	1	95	3	411.58
58	1	6	4	114.79
59	1	37	1	428.57
60	1	68	2	275.81
61	1	99	3	474.25
62	1	10	4	379.44
63	1	41	1	414.78
64	1	72	2	202.91
65	1	103	3	157.25
66	1	14	4	415.47
67	1	45	1	459.43
68	1	76	2	173.97
69	1	107	3	296.84
70	1	18	4	439.20
71	1	49	1	164.10
72	1	80	2	330.81
73	1	111	3	488.46
74	1	22	4	165.39
75	1	53	1	62.94
76	1	84	2	302.33
77	1	115	3	207.72
78	1	26	4	442.06
79	1	57	1	24.23
80	1	88	2	326.61
81	1	119	3	478.95
82	1	30	4	322.78
83	1	61	1	240.67
84	1	92	2	53.91
85	1	3	3	468.94
86	1	34	4	202.88
87	1	65	1	21.19
88	1	96	2	378.08
89	1	7	3	250.53
90	1	38	4	470.44
91	1	69	1	496.87
92	1	100	2	82.54
93	1	11	3	289.07
94	1	42	4	19.21
95	1	73	1	486.41
96	1	104	2	139.48
97	1	15	3	74.10
98	1	46	4	20.12
99	1	77	1	167.89
100	1	108	2	188.43
101	1	19	3	50.21
102	1	50	4	106.25
103	1	81	1	426.83
104	1	112	2	473.09
105	1	23	3	217.32
106	1	54	4	184.13
107	1	85	1	138.76
108	1	116	2	497.73
109	1	27	3	472.21
110	1	58	4	256.80
111	1	89	1	106.25
112	1	120	2	293.82
113	1	31	3	110.98
114	1	62	4	161.31
115	1	93	1	29.95
116	1	4	2	41.52
117	1	35	3	144.29
118	1	66	4	187.34
119	1	97	1	292.00
120	1	8	2	200.73
121	1	39	3	393.69
122	1	70	4	63.00
123	1	101	1	109.42
124	1	12	2	485.03
125	1	43	3	124.92
126	1	74	4	414.12
127	1	105	1	78.00
128	1	16	2	105.10
129	1	47	3	68.49
130	1	78	4	85.32
131	1	109	1	452.51
132	1	20	2	407.25
133	1	51	3	101.97
134	1	82	4	322.76
135	1	113	1	439.42
136	1	24	2	238.02
137	1	55	3	319.76
138	1	86	4	445.44
139	1	117	1	433.00
140	1	28	2	184.00
141	1	59	3	453.36
142	1	90	4	249.60
143	1	1	1	374.04
144	1	32	2	322.28
145	1	63	3	21.47
146	1	94	4	334.09
147	1	5	1	56.19
148	1	36	2	69.53
149	1	67	3	141.23
150	1	98	4	443.40
151	1	9	1	291.99
152	1	40	2	98.73
153	1	71	3	145.48
154	1	102	4	80.97
155	1	13	1	420.80
156	1	44	2	327.20
157	1	75	3	180.28
158	1	106	4	313.21
159	1	17	1	162.82
160	1	48	2	64.78
161	1	79	3	168.09
162	1	110	4	388.06
163	1	21	1	210.74
164	1	52	2	473.28
165	1	83	3	286.19
166	1	114	4	113.36
167	1	25	1	488.70
168	1	56	2	91.98
169	1	87	3	279.57
170	1	118	4	284.66
171	1	29	1	249.73
172	1	60	2	385.15
173	1	91	3	494.48
174	1	2	4	187.61
175	1	33	1	143.19
176	1	64	2	448.59
177	1	95	3	411.58
178	1	6	4	114.79
179	1	37	1	428.57
180	1	68	2	275.81
181	1	99	3	474.25
182	1	10	4	379.44
183	1	41	1	414.78
184	1	72	2	202.91
185	1	103	3	157.25
186	1	14	4	415.47
187	1	45	1	459.43
188	1	76	2	173.97
189	1	107	3	296.84
190	1	18	4	439.20
191	1	49	1	164.10
192	1	80	2	330.81
193	1	111	3	488.46
194	1	22	4	165.39
195	1	53	1	62.94
196	1	84	2	302.33
197	1	115	3	207.72
198	1	26	4	442.06
199	1	57	1	24.23
200	1	88	2	326.61
201	1	119	3	478.95
202	1	30	4	322.78
203	1	61	1	240.67
204	1	92	2	53.91
205	1	3	3	468.94
206	1	34	4	202.88
207	1	65	1	21.19
208	1	96	2	378.08
209	1	7	3	250.53
210	1	38	4	470.44
211	1	69	1	496.87
212	1	100	2	82.54
213	1	11	3	289.07
214	1	42	4	19.21
215	1	73	1	486.41
216	1	104	2	139.48
217	1	15	3	74.10
218	1	46	4	20.12
219	1	77	1	167.89
220	1	108	2	188.43
221	1	19	3	50.21
222	1	50	4	106.25
223	1	81	1	426.83
224	1	112	2	473.09
225	1	23	3	217.32
226	1	54	4	184.13
227	1	85	1	138.76
228	1	116	2	497.73
229	1	27	3	472.21
230	1	58	4	256.80
231	1	89	1	106.25
232	1	120	2	293.82
233	1	31	3	110.98
234	1	62	4	161.31
235	1	93	1	29.95
236	1	4	2	41.52
237	1	35	3	144.29
238	1	66	4	187.34
239	1	97	1	292.00
240	1	8	2	200.73
241	1	39	3	393.69
242	1	70	4	63.00
243	1	101	1	109.42
244	1	12	2	485.03
245	1	43	3	124.92
246	1	74	4	414.12
247	1	105	1	78.00
248	1	16	2	105.10
249	1	47	3	68.49
250	1	78	4	85.32
251	1	109	1	452.51
252	1	20	2	407.25
253	1	51	3	101.97
254	1	82	4	322.76
255	1	113	1	439.42
256	1	24	2	238.02
257	1	55	3	319.76
258	1	86	4	445.44
259	1	117	1	433.00
260	1	28	2	184.00
261	1	59	3	453.36
262	1	90	4	249.60
263	1	1	1	374.04
264	1	32	2	322.28
265	1	63	3	21.47
266	1	94	4	334.09
267	1	5	1	56.19
268	1	36	2	69.53
269	1	67	3	141.23
270	1	98	4	443.40
271	1	9	1	291.99
272	1	40	2	98.73
273	1	71	3	145.48
274	1	102	4	80.97
275	1	13	1	420.80
276	1	44	2	327.20
277	1	75	3	180.28
278	1	106	4	313.21
279	1	17	1	162.82
280	1	48	2	64.78
281	1	79	3	168.09
282	1	110	4	388.06
283	1	21	1	210.74
284	1	52	2	473.28
285	1	83	3	286.19
286	1	114	4	113.36
287	1	25	1	488.70
288	1	56	2	91.98
289	1	87	3	279.57
290	1	118	4	284.66
291	1	29	1	249.73
292	1	60	2	385.15
293	1	91	3	494.48
294	1	2	4	187.61
295	1	33	1	143.19
296	1	64	2	448.59
297	1	95	3	411.58
298	1	6	4	114.79
299	1	37	1	428.57
300	1	68	2	275.81
301	1	99	3	474.25
302	1	10	4	379.44
303	1	41	1	414.78
304	1	72	2	202.91
305	1	103	3	157.25
306	1	14	4	415.47
307	1	45	1	459.43
308	1	76	2	173.97
309	1	107	3	296.84
310	1	18	4	439.20
311	1	49	1	164.10
312	1	80	2	330.81
313	1	111	3	488.46
314	1	22	4	165.39
315	1	53	1	62.94
316	1	84	2	302.33
317	1	115	3	207.72
318	1	26	4	442.06
319	1	57	1	24.23
320	1	88	2	326.61
321	1	119	3	478.95
322	1	30	4	322.78
323	1	61	1	240.67
324	1	92	2	53.91
325	1	3	3	468.94
326	1	34	4	202.88
327	1	65	1	21.19
328	1	96	2	378.08
329	1	7	3	250.53
330	1	38	4	470.44
331	1	69	1	496.87
332	1	100	2	82.54
333	1	11	3	289.07
334	1	42	4	19.21
335	1	73	1	486.41
336	1	104	2	139.48
337	1	15	3	74.10
338	1	46	4	20.12
339	1	77	1	167.89
340	1	108	2	188.43
341	1	19	3	50.21
342	1	50	4	106.25
343	1	81	1	426.83
344	1	112	2	473.09
345	1	23	3	217.32
346	1	54	4	184.13
347	1	85	1	138.76
348	1	116	2	497.73
349	1	27	3	472.21
350	1	58	4	256.80
351	1	89	1	106.25
352	1	120	2	293.82
353	1	31	3	110.98
354	1	62	4	161.31
355	1	93	1	29.95
356	1	4	2	41.52
357	1	35	3	144.29
358	1	66	4	187.34
359	1	97	1	292.00
360	1	8	2	200.73
361	1	39	3	393.69
362	1	70	4	63.00
363	1	101	1	109.42
364	1	12	2	485.03
365	1	43	3	124.92
366	1	74	4	414.12
367	1	105	1	78.00
368	1	16	2	105.10
369	1	47	3	68.49
370	1	78	4	85.32
371	1	109	1	452.51
372	1	20	2	407.25
373	1	51	3	101.97
374	1	82	4	322.76
375	1	113	1	439.42
376	1	24	2	238.02
377	1	55	3	319.76
378	1	86	4	445.44
379	1	117	1	433.00
380	1	28	2	184.00
381	1	59	3	453.36
382	1	90	4	249.60
383	1	1	1	374.04
384	1	32	2	322.28
385	1	63	3	21.47
386	1	94	4	334.09
387	1	5	1	56.19
388	1	36	2	69.53
389	1	67	3	141.23
390	1	98	4	443.40
391	1	9	1	291.99
392	1	40	2	98.73
393	1	71	3	145.48
394	1	102	4	80.97
395	1	13	1	420.80
396	1	44	2	327.20
397	1	75	3	180.28
398	1	106	4	313.21
399	1	17	1	162.82
400	1	48	2	64.78
401	1	79	3	168.09
402	1	110	4	388.06
403	1	21	1	210.74
404	1	52	2	473.28
405	1	83	3	286.19
406	1	114	4	113.36
407	1	25	1	488.70
408	1	56	2	91.98
409	1	87	3	279.57
410	1	118	4	284.66
411	1	29	1	249.73
412	1	60	2	385.15
413	1	91	3	494.48
414	1	2	4	187.61
415	1	33	1	143.19
416	1	64	2	448.59
417	1	95	3	411.58
418	1	6	4	114.79
419	1	37	1	428.57
420	1	68	2	275.81
421	1	99	3	474.25
422	1	10	4	379.44
423	1	41	1	414.78
424	1	72	2	202.91
425	1	103	3	157.25
426	1	14	4	415.47
427	1	45	1	459.43
428	1	76	2	173.97
429	1	107	3	296.84
430	1	18	4	439.20
431	1	49	1	164.10
432	1	80	2	330.81
433	1	111	3	488.46
434	1	22	4	165.39
435	1	53	1	62.94
436	1	84	2	302.33
437	1	115	3	207.72
438	1	26	4	442.06
439	1	57	1	24.23
440	1	88	2	326.61
441	1	119	3	478.95
442	1	30	4	322.78
443	1	61	1	240.67
444	1	92	2	53.91
445	1	3	3	468.94
446	1	34	4	202.88
447	1	65	1	21.19
448	1	96	2	378.08
449	1	7	3	250.53
450	1	38	4	470.44
451	1	69	1	496.87
452	1	100	2	82.54
453	1	11	3	289.07
454	1	42	4	19.21
455	1	73	1	486.41
456	1	104	2	139.48
457	1	15	3	74.10
458	1	46	4	20.12
459	1	77	1	167.89
460	1	108	2	188.43
461	1	19	3	50.21
462	1	50	4	106.25
463	1	81	1	426.83
464	1	112	2	473.09
465	1	23	3	217.32
466	1	54	4	184.13
467	1	85	1	138.76
468	1	116	2	497.73
469	1	27	3	472.21
470	1	58	4	256.80
471	1	89	1	106.25
472	1	120	2	293.82
473	1	31	3	110.98
474	1	62	4	161.31
475	1	93	1	29.95
476	1	4	2	41.52
477	1	35	3	144.29
478	1	66	4	187.34
479	1	97	1	292.00
480	1	8	2	200.73
481	1	39	3	393.69
482	1	70	4	63.00
483	1	101	1	109.42
484	1	12	2	485.03
485	1	43	3	124.92
486	1	74	4	414.12
487	1	105	1	78.00
488	1	16	2	105.10
489	1	47	3	68.49
490	1	78	4	85.32
491	1	109	1	452.51
492	1	20	2	407.25
493	1	51	3	101.97
494	1	82	4	322.76
495	1	113	1	439.42
496	1	24	2	238.02
497	1	55	3	319.76
498	1	86	4	445.44
499	1	117	1	433.00
500	1	28	2	184.00
501	1	59	3	453.36
502	1	90	4	249.60
503	1	1	1	374.04
504	1	32	2	322.28
505	1	63	3	21.47
506	1	94	4	334.09
507	1	5	1	56.19
508	1	36	2	69.53
509	1	67	3	141.23
510	1	98	4	443.40
511	1	9	1	291.99
512	1	40	2	98.73
513	1	71	3	145.48
514	1	102	4	80.97
515	1	13	1	420.80
516	1	44	2	327.20
517	1	75	3	180.28
518	1	106	4	313.21
519	1	17	1	162.82
520	1	48	2	64.78
521	1	79	3	168.09
522	1	110	4	388.06
523	1	21	1	210.74
524	1	52	2	473.28
525	1	83	3	286.19
526	1	114	4	113.36
527	1	25	1	488.70
528	1	56	2	91.98
529	1	87	3	279.57
530	1	118	4	284.66
531	1	29	1	249.73
532	1	60	2	385.15
533	1	91	3	494.48
534	1	2	4	187.61
535	1	33	1	143.19
536	1	64	2	448.59
537	1	95	3	411.58
538	1	6	4	114.79
539	1	37	1	428.57
540	1	68	2	275.81
541	1	99	3	474.25
542	1	10	4	379.44
543	1	41	1	414.78
544	1	72	2	202.91
545	1	103	3	157.25
546	1	14	4	415.47
547	1	45	1	459.43
548	1	76	2	173.97
549	1	107	3	296.84
550	1	18	4	439.20
551	1	49	1	164.10
552	1	80	2	330.81
553	1	111	3	488.46
554	1	22	4	165.39
555	1	53	1	62.94
556	1	84	2	302.33
557	1	115	3	207.72
558	1	26	4	442.06
559	1	57	1	24.23
560	1	88	2	326.61
561	1	119	3	478.95
562	1	30	4	322.78
563	1	61	1	240.67
564	1	92	2	53.91
565	1	3	3	468.94
566	1	34	4	202.88
567	1	65	1	21.19
568	1	96	2	378.08
569	1	7	3	250.53
570	1	38	4	470.44
571	1	69	1	496.87
572	1	100	2	82.54
573	1	11	3	289.07
574	1	42	4	19.21
575	1	73	1	486.41
576	1	104	2	139.48
577	1	15	3	74.10
578	1	46	4	20.12
579	1	77	1	167.89
580	1	108	2	188.43
581	1	19	3	50.21
582	1	50	4	106.25
583	1	81	1	426.83
584	1	112	2	473.09
585	1	23	3	217.32
586	1	54	4	184.13
587	1	85	1	138.76
588	1	116	2	497.73
589	1	27	3	472.21
590	1	58	4	256.80
591	1	89	1	106.25
592	1	120	2	293.82
593	1	31	3	110.98
594	1	62	4	161.31
595	1	93	1	29.95
596	1	4	2	41.52
597	1	35	3	144.29
598	1	66	4	187.34
599	1	97	1	292.00
600	1	8	2	200.73
601	1	39	3	393.69
602	1	70	4	63.00
603	1	101	1	109.42
604	1	12	2	485.03
605	1	43	3	124.92
606	1	74	4	414.12
607	1	105	1	78.00
608	1	16	2	105.10
609	1	47	3	68.49
610	1	78	4	85.32
611	1	109	1	452.51
612	1	20	2	407.25
613	1	51	3	101.97
614	1	82	4	322.76
615	1	113	1	439.42
616	1	24	2	238.02
617	1	55	3	319.76
618	1	86	4	445.44
619	1	117	1	433.00
620	1	28	2	184.00
1	2	46	4	20.12
2	2	77	1	167.89
4	2	19	3	50.21
5	2	50	4	106.25
7	2	112	2	473.09
8	2	23	3	217.32
10	2	85	1	138.76
11	2	116	2	497.73
13	2	58	4	256.80
14	2	89	1	106.25
16	2	31	3	110.98
17	2	62	4	161.31
19	2	4	2	41.52
20	2	35	3	144.29
22	2	97	1	292.00
23	2	8	2	200.73
25	2	70	4	63.00
26	2	101	1	109.42
28	2	43	3	124.92
29	2	74	4	414.12
31	2	16	2	105.10
32	2	47	3	68.49
34	2	109	1	452.51
35	2	20	2	407.25
37	2	82	4	322.76
38	2	113	1	439.42
40	2	55	3	319.76
41	2	86	4	445.44
43	2	28	2	184.00
44	2	59	3	453.36
46	2	1	1	374.04
47	2	32	2	322.28
49	2	94	4	334.09
50	2	5	1	56.19
52	2	67	3	141.23
53	2	98	4	443.40
55	2	40	2	98.73
56	2	71	3	145.48
58	2	13	1	420.80
59	2	44	2	327.20
61	2	106	4	313.21
62	2	17	1	162.82
64	2	79	3	168.09
65	2	110	4	388.06
67	2	52	2	473.28
68	2	83	3	286.19
70	2	25	1	488.70
71	2	56	2	91.98
73	2	118	4	284.66
74	2	29	1	249.73
76	2	91	3	494.48
77	2	2	4	187.61
79	2	64	2	448.59
80	2	95	3	411.58
82	2	37	1	428.57
83	2	68	2	275.81
85	2	10	4	379.44
86	2	41	1	414.78
88	2	103	3	157.25
89	2	14	4	415.47
91	2	76	2	173.97
92	2	107	3	296.84
94	2	49	1	164.10
95	2	80	2	330.81
97	2	22	4	165.39
98	2	53	1	62.94
100	2	115	3	207.72
101	2	26	4	442.06
103	2	88	2	326.61
104	2	119	3	478.95
106	2	61	1	240.67
107	2	92	2	53.91
109	2	34	4	202.88
110	2	65	1	21.19
112	2	7	3	250.53
113	2	38	4	470.44
115	2	100	2	82.54
116	2	11	3	289.07
118	2	73	1	486.41
119	2	104	2	139.48
121	2	46	4	20.12
122	2	77	1	167.89
124	2	19	3	50.21
125	2	50	4	106.25
127	2	112	2	473.09
128	2	23	3	217.32
130	2	85	1	138.76
131	2	116	2	497.73
133	2	58	4	256.80
134	2	89	1	106.25
136	2	31	3	110.98
137	2	62	4	161.31
139	2	4	2	41.52
140	2	35	3	144.29
142	2	97	1	292.00
143	2	8	2	200.73
145	2	70	4	63.00
146	2	101	1	109.42
148	2	43	3	124.92
149	2	74	4	414.12
151	2	16	2	105.10
152	2	47	3	68.49
154	2	109	1	452.51
155	2	20	2	407.25
157	2	82	4	322.76
158	2	113	1	439.42
160	2	55	3	319.76
161	2	86	4	445.44
163	2	28	2	184.00
164	2	59	3	453.36
166	2	1	1	374.04
167	2	32	2	322.28
169	2	94	4	334.09
170	2	5	1	56.19
172	2	67	3	141.23
173	2	98	4	443.40
175	2	40	2	98.73
176	2	71	3	145.48
178	2	13	1	420.80
179	2	44	2	327.20
181	2	106	4	313.21
182	2	17	1	162.82
184	2	79	3	168.09
185	2	110	4	388.06
187	2	52	2	473.28
188	2	83	3	286.19
190	2	25	1	488.70
191	2	56	2	91.98
193	2	118	4	284.66
194	2	29	1	249.73
196	2	91	3	494.48
197	2	2	4	187.61
199	2	64	2	448.59
200	2	95	3	411.58
202	2	37	1	428.57
203	2	68	2	275.81
205	2	10	4	379.44
206	2	41	1	414.78
208	2	103	3	157.25
209	2	14	4	415.47
211	2	76	2	173.97
212	2	107	3	296.84
214	2	49	1	164.10
215	2	80	2	330.81
217	2	22	4	165.39
218	2	53	1	62.94
220	2	115	3	207.72
221	2	26	4	442.06
223	2	88	2	326.61
224	2	119	3	478.95
226	2	61	1	240.67
227	2	92	2	53.91
229	2	34	4	202.88
230	2	65	1	21.19
232	2	7	3	250.53
233	2	38	4	470.44
235	2	100	2	82.54
236	2	11	3	289.07
238	2	73	1	486.41
239	2	104	2	139.48
241	2	46	4	20.12
242	2	77	1	167.89
244	2	19	3	50.21
245	2	50	4	106.25
247	2	112	2	473.09
248	2	23	3	217.32
250	2	85	1	138.76
251	2	116	2	497.73
253	2	58	4	256.80
254	2	89	1	106.25
256	2	31	3	110.98
257	2	62	4	161.31
259	2	4	2	41.52
260	2	35	3	144.29
262	2	97	1	292.00
263	2	8	2	200.73
265	2	70	4	63.00
266	2	101	1	109.42
268	2	43	3	124.92
269	2	74	4	414.12
271	2	16	2	105.10
272	2	47	3	68.49
274	2	109	1	452.51
275	2	20	2	407.25
277	2	82	4	322.76
278	2	113	1	439.42
280	2	55	3	319.76
281	2	86	4	445.44
283	2	28	2	184.00
284	2	59	3	453.36
286	2	1	1	374.04
287	2	32	2	322.28
289	2	94	4	334.09
290	2	5	1	56.19
292	2	67	3	141.23
293	2	98	4	443.40
295	2	40	2	98.73
296	2	71	3	145.48
298	2	13	1	420.80
299	2	44	2	327.20
301	2	106	4	313.21
302	2	17	1	162.82
304	2	79	3	168.09
305	2	110	4	388.06
307	2	52	2	473.28
308	2	83	3	286.19
310	2	25	1	488.70
311	2	56	2	91.98
313	2	118	4	284.66
314	2	29	1	249.73
316	2	91	3	494.48
317	2	2	4	187.61
319	2	64	2	448.59
320	2	95	3	411.58
322	2	37	1	428.57
323	2	68	2	275.81
325	2	10	4	379.44
326	2	41	1	414.78
328	2	103	3	157.25
329	2	14	4	415.47
331	2	76	2	173.97
332	2	107	3	296.84
334	2	49	1	164.10
335	2	80	2	330.81
337	2	22	4	165.39
338	2	53	1	62.94
340	2	115	3	207.72
341	2	26	4	442.06
343	2	88	2	326.61
344	2	119	3	478.95
346	2	61	1	240.67
347	2	92	2	53.91
349	2	34	4	202.88
350	2	65	1	21.19
352	2	7	3	250.53
353	2	38	4	470.44
355	2	100	2	82.54
356	2	11	3	289.07
358	2	73	1	486.41
359	2	104	2	139.48
361	2	46	4	20.12
362	2	77	1	167.89
364	2	19	3	50.21
365	2	50	4	106.25
367	2	112	2	473.09
368	2	23	3	217.32
370	2	85	1	138.76
371	2	116	2	497.73
373	2	58	4	256.80
374	2	89	1	106.25
376	2	31	3	110.98
377	2	62	4	161.31
379	2	4	2	41.52
380	2	35	3	144.29
382	2	97	1	292.00
383	2	8	2	200.73
385	2	70	4	63.00
386	2	101	1	109.42
388	2	43	3	124.92
389	2	74	4	414.12
391	2	16	2	105.10
392	2	47	3	68.49
394	2	109	1	452.51
395	2	20	2	407.25
397	2	82	4	322.76
398	2	113	1	439.42
400	2	55	3	319.76
401	2	86	4	445.44
403	2	28	2	184.00
404	2	59	3	453.36
406	2	1	1	374.04
407	2	32	2	322.28
409	2	94	4	334.09
410	2	5	1	56.19
412	2	67	3	141.23
413	2	98	4	443.40
415	2	40	2	98.73
416	2	71	3	145.48
418	2	13	1	420.80
419	2	44	2	327.20
421	2	106	4	313.21
422	2	17	1	162.82
424	2	79	3	168.09
425	2	110	4	388.06
427	2	52	2	473.28
428	2	83	3	286.19
430	2	25	1	488.70
431	2	56	2	91.98
433	2	118	4	284.66
434	2	29	1	249.73
436	2	91	3	494.48
437	2	2	4	187.61
439	2	64	2	448.59
440	2	95	3	411.58
442	2	37	1	428.57
443	2	68	2	275.81
445	2	10	4	379.44
446	2	41	1	414.78
448	2	103	3	157.25
449	2	14	4	415.47
451	2	76	2	173.97
452	2	107	3	296.84
454	2	49	1	164.10
455	2	80	2	330.81
457	2	22	4	165.39
458	2	53	1	62.94
460	2	115	3	207.72
461	2	26	4	442.06
463	2	88	2	326.61
464	2	119	3	478.95
466	2	61	1	240.67
467	2	92	2	53.91
469	2	34	4	202.88
470	2	65	1	21.19
472	2	7	3	250.53
473	2	38	4	470.44
475	2	100	2	82.54
476	2	11	3	289.07
478	2	73	1	486.41
479	2	104	2	139.48
481	2	46	4	20.12
482	2	77	1	167.89
484	2	19	3	50.21
485	2	50	4	106.25
487	2	112	2	473.09
488	2	23	3	217.32
490	2	85	1	138.76
491	2	116	2	497.73
493	2	58	4	256.80
494	2	89	1	106.25
496	2	31	3	110.98
497	2	62	4	161.31
499	2	4	2	41.52
500	2	35	3	144.29
502	2	97	1	292.00
503	2	8	2	200.73
505	2	70	4	63.00
506	2	101	1	109.42
508	2	43	3	124.92
509	2	74	4	414.12
511	2	16	2	105.10
512	2	47	3	68.49
514	2	109	1	452.51
515	2	20	2	407.25
517	2	82	4	322.76
518	2	113	1	439.42
520	2	55	3	319.76
521	2	86	4	445.44
523	2	28	2	184.00
524	2	59	3	453.36
526	2	1	1	374.04
527	2	32	2	322.28
529	2	94	4	334.09
530	2	5	1	56.19
532	2	67	3	141.23
533	2	98	4	443.40
535	2	40	2	98.73
536	2	71	3	145.48
538	2	13	1	420.80
539	2	44	2	327.20
541	2	106	4	313.21
542	2	17	1	162.82
544	2	79	3	168.09
545	2	110	4	388.06
547	2	52	2	473.28
548	2	83	3	286.19
550	2	25	1	488.70
551	2	56	2	91.98
553	2	118	4	284.66
554	2	29	1	249.73
556	2	91	3	494.48
557	2	2	4	187.61
559	2	64	2	448.59
560	2	95	3	411.58
562	2	37	1	428.57
563	2	68	2	275.81
565	2	10	4	379.44
566	2	41	1	414.78
568	2	103	3	157.25
569	2	14	4	415.47
571	2	76	2	173.97
572	2	107	3	296.84
574	2	49	1	164.10
575	2	80	2	330.81
577	2	22	4	165.39
578	2	53	1	62.94
580	2	115	3	207.72
581	2	26	4	442.06
583	2	88	2	326.61
584	2	119	3	478.95
586	2	61	1	240.67
587	2	92	2	53.91
589	2	34	4	202.88
590	2	65	1	21.19
592	2	7	3	250.53
593	2	38	4	470.44
595	2	100	2	82.54
596	2	11	3	289.07
598	2	73	1	486.41
599	2	104	2	139.48
601	2	46	4	20.12
602	2	77	1	167.89
604	2	19	3	50.21
605	2	50	4	106.25
607	2	112	2	473.09
608	2	23	3	217.32
610	2	85	1	138.76
611	2	116	2	497.73
613	2	58	4	256.80
614	2	89	1	106.25
616	2	31	3	110.98
617	2	62	4	161.31
619	2	4	2	41.52
620	2	35	3	144.29
2	3	84	2	302.33
5	3	57	1	24.23
8	3	30	4	322.78
11	3	3	3	468.94
14	3	96	2	378.08
17	3	69	1	496.87
20	3	42	4	19.21
23	3	15	3	74.10
26	3	108	2	188.43
29	3	81	1	426.83
32	3	54	4	184.13
35	3	27	3	472.21
38	3	120	2	293.82
41	3	93	1	29.95
44	3	66	4	187.34
47	3	39	3	393.69
50	3	12	2	485.03
53	3	105	1	78.00
56	3	78	4	85.32
59	3	51	3	101.97
62	3	24	2	238.02
65	3	117	1	433.00
68	3	90	4	249.60
71	3	63	3	21.47
74	3	36	2	69.53
77	3	9	1	291.99
80	3	102	4	80.97
83	3	75	3	180.28
86	3	48	2	64.78
89	3	21	1	210.74
92	3	114	4	113.36
95	3	87	3	279.57
98	3	60	2	385.15
101	3	33	1	143.19
104	3	6	4	114.79
107	3	99	3	474.25
110	3	72	2	202.91
113	3	45	1	459.43
116	3	18	4	439.20
119	3	111	3	488.46
122	3	84	2	302.33
125	3	57	1	24.23
128	3	30	4	322.78
131	3	3	3	468.94
134	3	96	2	378.08
137	3	69	1	496.87
140	3	42	4	19.21
143	3	15	3	74.10
146	3	108	2	188.43
149	3	81	1	426.83
152	3	54	4	184.13
155	3	27	3	472.21
158	3	120	2	293.82
161	3	93	1	29.95
164	3	66	4	187.34
167	3	39	3	393.69
170	3	12	2	485.03
173	3	105	1	78.00
176	3	78	4	85.32
179	3	51	3	101.97
182	3	24	2	238.02
185	3	117	1	433.00
188	3	90	4	249.60
191	3	63	3	21.47
194	3	36	2	69.53
197	3	9	1	291.99
200	3	102	4	80.97
203	3	75	3	180.28
206	3	48	2	64.78
209	3	21	1	210.74
212	3	114	4	113.36
215	3	87	3	279.57
218	3	60	2	385.15
221	3	33	1	143.19
224	3	6	4	114.79
227	3	99	3	474.25
230	3	72	2	202.91
233	3	45	1	459.43
236	3	18	4	439.20
239	3	111	3	488.46
242	3	84	2	302.33
245	3	57	1	24.23
248	3	30	4	322.78
251	3	3	3	468.94
254	3	96	2	378.08
257	3	69	1	496.87
260	3	42	4	19.21
263	3	15	3	74.10
266	3	108	2	188.43
269	3	81	1	426.83
272	3	54	4	184.13
275	3	27	3	472.21
278	3	120	2	293.82
281	3	93	1	29.95
284	3	66	4	187.34
287	3	39	3	393.69
290	3	12	2	485.03
293	3	105	1	78.00
296	3	78	4	85.32
299	3	51	3	101.97
302	3	24	2	238.02
305	3	117	1	433.00
308	3	90	4	249.60
311	3	63	3	21.47
314	3	36	2	69.53
317	3	9	1	291.99
320	3	102	4	80.97
323	3	75	3	180.28
326	3	48	2	64.78
329	3	21	1	210.74
332	3	114	4	113.36
335	3	87	3	279.57
338	3	60	2	385.15
341	3	33	1	143.19
344	3	6	4	114.79
347	3	99	3	474.25
350	3	72	2	202.91
353	3	45	1	459.43
356	3	18	4	439.20
359	3	111	3	488.46
362	3	84	2	302.33
365	3	57	1	24.23
368	3	30	4	322.78
371	3	3	3	468.94
374	3	96	2	378.08
377	3	69	1	496.87
380	3	42	4	19.21
383	3	15	3	74.10
386	3	108	2	188.43
389	3	81	1	426.83
392	3	54	4	184.13
395	3	27	3	472.21
398	3	120	2	293.82
401	3	93	1	29.95
404	3	66	4	187.34
407	3	39	3	393.69
410	3	12	2	485.03
413	3	105	1	78.00
416	3	78	4	85.32
419	3	51	3	101.97
422	3	24	2	238.02
425	3	117	1	433.00
428	3	90	4	249.60
431	3	63	3	21.47
434	3	36	2	69.53
437	3	9	1	291.99
440	3	102	4	80.97
443	3	75	3	180.28
446	3	48	2	64.78
449	3	21	1	210.74
452	3	114	4	113.36
455	3	87	3	279.57
458	3	60	2	385.15
461	3	33	1	143.19
464	3	6	4	114.79
467	3	99	3	474.25
470	3	72	2	202.91
473	3	45	1	459.43
476	3	18	4	439.20
479	3	111	3	488.46
482	3	84	2	302.33
485	3	57	1	24.23
488	3	30	4	322.78
491	3	3	3	468.94
494	3	96	2	378.08
497	3	69	1	496.87
500	3	42	4	19.21
503	3	15	3	74.10
506	3	108	2	188.43
509	3	81	1	426.83
512	3	54	4	184.13
515	3	27	3	472.21
518	3	120	2	293.82
521	3	93	1	29.95
524	3	66	4	187.34
527	3	39	3	393.69
530	3	12	2	485.03
533	3	105	1	78.00
536	3	78	4	85.32
539	3	51	3	101.97
542	3	24	2	238.02
545	3	117	1	433.00
548	3	90	4	249.60
551	3	63	3	21.47
554	3	36	2	69.53
557	3	9	1	291.99
560	3	102	4	80.97
563	3	75	3	180.28
566	3	48	2	64.78
569	3	21	1	210.74
572	3	114	4	113.36
575	3	87	3	279.57
578	3	60	2	385.15
581	3	33	1	143.19
584	3	6	4	114.79
587	3	99	3	474.25
590	3	72	2	202.91
593	3	45	1	459.43
596	3	18	4	439.20
599	3	111	3	488.46
602	3	84	2	302.33
605	3	57	1	24.23
608	3	30	4	322.78
611	3	3	3	468.94
614	3	96	2	378.08
617	3	69	1	496.87
620	3	42	4	19.21
\.


--
-- Data for Name: orders; Type: TABLE DATA; Schema: sales; Owner: -
--

COPY sales.orders (id, number, customer_id, sold_by, status, placed_at, shipping_address, total) FROM stdin;
3	1002	40	5	cancelled	2025-01-02 15:00:00+00	\N	109.42
6	1005	79	8	shipped	2025-01-04 06:00:00+00	\N	1656.48
9	1008	118	11	paid	2025-01-05 21:00:00+00	\N	205.47
12	1011	157	14	placed	2025-01-07 12:00:00+00	\N	814.50
15	1014	196	3	cancelled	2025-01-09 03:00:00+00	\N	439.42
18	1017	35	6	shipped	2025-01-10 18:00:00+00	\N	1781.76
21	1020	74	9	paid	2025-01-12 09:00:00+00	\N	1360.08
24	1023	113	12	placed	2025-01-14 00:00:00+00	\N	644.56
27	1026	152	15	cancelled	2025-01-15 15:00:00+00	\N	56.19
30	1029	191	4	shipped	2025-01-17 06:00:00+00	\N	1773.60
33	1032	30	7	paid	2025-01-18 21:00:00+00	\N	436.44
36	1035	69	10	placed	2025-01-20 12:00:00+00	\N	654.40
39	1038	108	13	cancelled	2025-01-22 03:00:00+00	\N	162.82
42	1041	147	2	shipped	2025-01-23 18:00:00+00	\N	1552.24
45	1044	186	5	paid	2025-01-25 09:00:00+00	\N	858.57
48	1047	25	8	placed	2025-01-27 00:00:00+00	\N	183.96
51	1050	64	11	cancelled	2025-01-28 15:00:00+00	\N	249.73
54	1053	103	14	shipped	2025-01-30 06:00:00+00	\N	750.44
57	1056	142	3	paid	2025-01-31 21:00:00+00	\N	1234.74
60	1059	181	6	placed	2025-02-02 12:00:00+00	\N	551.62
63	1062	20	9	cancelled	2025-02-04 03:00:00+00	\N	414.78
66	1065	59	12	shipped	2025-02-05 18:00:00+00	\N	1661.88
69	1068	98	15	paid	2025-02-07 09:00:00+00	\N	890.52
72	1071	137	4	placed	2025-02-09 00:00:00+00	\N	661.62
75	1074	176	7	cancelled	2025-02-10 15:00:00+00	\N	62.94
78	1077	15	10	shipped	2025-02-12 06:00:00+00	\N	1768.24
81	1080	54	13	paid	2025-02-13 21:00:00+00	\N	1436.85
84	1083	93	2	placed	2025-02-15 12:00:00+00	\N	107.82
87	1086	132	5	cancelled	2025-02-17 03:00:00+00	\N	21.19
90	1089	171	8	shipped	2025-02-18 18:00:00+00	\N	1881.76
93	1092	10	11	paid	2025-02-20 09:00:00+00	\N	867.21
96	1095	49	14	placed	2025-02-22 00:00:00+00	\N	278.96
99	1098	88	3	cancelled	2025-02-23 15:00:00+00	\N	167.89
102	1101	127	6	shipped	2025-02-25 06:00:00+00	\N	425.00
105	1104	166	9	paid	2025-02-26 21:00:00+00	\N	651.96
108	1107	5	12	placed	2025-02-28 12:00:00+00	\N	995.46
111	1110	44	15	cancelled	2025-03-02 03:00:00+00	\N	106.25
114	1113	83	4	shipped	2025-03-03 18:00:00+00	\N	645.24
117	1116	122	7	paid	2025-03-05 09:00:00+00	\N	432.87
120	1119	161	10	placed	2025-03-07 00:00:00+00	\N	401.46
123	1122	200	13	cancelled	2025-03-08 15:00:00+00	\N	109.42
126	1125	39	2	shipped	2025-03-10 06:00:00+00	\N	1656.48
129	1128	78	5	paid	2025-03-11 21:00:00+00	\N	205.47
132	1131	117	8	placed	2025-03-13 12:00:00+00	\N	814.50
135	1134	156	11	cancelled	2025-03-15 03:00:00+00	\N	439.42
138	1137	195	14	shipped	2025-03-16 18:00:00+00	\N	1781.76
141	1140	34	3	paid	2025-03-18 09:00:00+00	\N	1360.08
144	1143	73	6	placed	2025-03-20 00:00:00+00	\N	644.56
147	1146	112	9	cancelled	2025-03-21 15:00:00+00	\N	56.19
150	1149	151	12	shipped	2025-03-23 06:00:00+00	\N	1773.60
153	1152	190	15	paid	2025-03-24 21:00:00+00	\N	436.44
156	1155	29	4	placed	2025-03-26 12:00:00+00	\N	654.40
159	1158	68	7	cancelled	2025-03-28 03:00:00+00	\N	162.82
162	1161	107	10	shipped	2025-03-29 18:00:00+00	\N	1552.24
165	1164	146	13	paid	2025-03-31 09:00:00+00	\N	858.57
168	1167	185	2	placed	2025-04-02 00:00:00+00	\N	183.96
171	1170	24	5	cancelled	2025-04-03 15:00:00+00	\N	249.73
174	1173	63	8	shipped	2025-04-05 06:00:00+00	\N	750.44
177	1176	102	11	paid	2025-04-06 21:00:00+00	\N	1234.74
180	1179	141	14	placed	2025-04-08 12:00:00+00	\N	551.62
183	1182	180	3	cancelled	2025-04-10 03:00:00+00	\N	414.78
186	1185	19	6	shipped	2025-04-11 18:00:00+00	\N	1661.88
189	1188	58	9	paid	2025-04-13 09:00:00+00	\N	890.52
192	1191	97	12	placed	2025-04-15 00:00:00+00	\N	661.62
195	1194	136	15	cancelled	2025-04-16 15:00:00+00	\N	62.94
198	1197	175	4	shipped	2025-04-18 06:00:00+00	\N	1768.24
201	1200	14	7	paid	2025-04-19 21:00:00+00	\N	1436.85
204	1203	53	10	placed	2025-04-21 12:00:00+00	\N	107.82
207	1206	92	13	cancelled	2025-04-23 03:00:00+00	\N	21.19
210	1209	131	2	shipped	2025-04-24 18:00:00+00	\N	1881.76
213	1212	170	5	paid	2025-04-26 09:00:00+00	\N	867.21
216	1215	9	8	placed	2025-04-28 00:00:00+00	\N	278.96
219	1218	48	11	cancelled	2025-04-29 15:00:00+00	\N	167.89
222	1221	87	14	shipped	2025-05-01 06:00:00+00	\N	425.00
225	1224	126	3	paid	2025-05-02 21:00:00+00	\N	651.96
228	1227	165	6	placed	2025-05-04 12:00:00+00	\N	995.46
231	1230	4	9	cancelled	2025-05-06 03:00:00+00	\N	106.25
234	1233	43	12	shipped	2025-05-07 18:00:00+00	\N	645.24
237	1236	82	15	paid	2025-05-09 09:00:00+00	\N	432.87
240	1239	121	4	placed	2025-05-11 00:00:00+00	\N	401.46
243	1242	160	7	cancelled	2025-05-12 15:00:00+00	\N	109.42
246	1245	199	10	shipped	2025-05-14 06:00:00+00	\N	1656.48
249	1248	38	13	paid	2025-05-15 21:00:00+00	\N	205.47
252	1251	77	2	placed	2025-05-17 12:00:00+00	\N	814.50
255	1254	116	5	cancelled	2025-05-19 03:00:00+00	\N	439.42
258	1257	155	8	shipped	2025-05-20 18:00:00+00	\N	1781.76
261	1260	194	11	paid	2025-05-22 09:00:00+00	\N	1360.08
264	1263	33	14	placed	2025-05-24 00:00:00+00	\N	644.56
267	1266	72	3	cancelled	2025-05-25 15:00:00+00	\N	56.19
270	1269	111	6	shipped	2025-05-27 06:00:00+00	\N	1773.60
273	1272	150	9	paid	2025-05-28 21:00:00+00	\N	436.44
276	1275	189	12	placed	2025-05-30 12:00:00+00	\N	654.40
279	1278	28	15	cancelled	2025-06-01 03:00:00+00	\N	162.82
282	1281	67	4	shipped	2025-06-02 18:00:00+00	\N	1552.24
285	1284	106	7	paid	2025-06-04 09:00:00+00	\N	858.57
288	1287	145	10	placed	2025-06-06 00:00:00+00	\N	183.96
291	1290	184	13	cancelled	2025-06-07 15:00:00+00	\N	249.73
294	1293	23	2	shipped	2025-06-09 06:00:00+00	\N	750.44
297	1296	62	5	paid	2025-06-10 21:00:00+00	\N	1234.74
300	1299	101	8	placed	2025-06-12 12:00:00+00	\N	551.62
303	1302	140	11	cancelled	2025-06-14 03:00:00+00	\N	414.78
306	1305	179	14	shipped	2025-06-15 18:00:00+00	\N	1661.88
309	1308	18	3	paid	2025-06-17 09:00:00+00	\N	890.52
312	1311	57	6	placed	2025-06-19 00:00:00+00	\N	661.62
315	1314	96	9	cancelled	2025-06-20 15:00:00+00	\N	62.94
318	1317	135	12	shipped	2025-06-22 06:00:00+00	\N	1768.24
321	1320	174	15	paid	2025-06-23 21:00:00+00	\N	1436.85
324	1323	13	4	placed	2025-06-25 12:00:00+00	\N	107.82
327	1326	52	7	cancelled	2025-06-27 03:00:00+00	\N	21.19
330	1329	91	10	shipped	2025-06-28 18:00:00+00	\N	1881.76
333	1332	130	13	paid	2025-06-30 09:00:00+00	\N	867.21
336	1335	169	2	placed	2025-07-02 00:00:00+00	\N	278.96
339	1338	8	5	cancelled	2025-07-03 15:00:00+00	\N	167.89
342	1341	47	8	shipped	2025-07-05 06:00:00+00	\N	425.00
345	1344	86	11	paid	2025-07-06 21:00:00+00	\N	651.96
348	1347	125	14	placed	2025-07-08 12:00:00+00	\N	995.46
351	1350	164	3	cancelled	2025-07-10 03:00:00+00	\N	106.25
354	1353	3	6	shipped	2025-07-11 18:00:00+00	\N	645.24
357	1356	42	9	paid	2025-07-13 09:00:00+00	\N	432.87
360	1359	81	12	placed	2025-07-15 00:00:00+00	\N	401.46
363	1362	120	15	cancelled	2025-07-16 15:00:00+00	\N	109.42
366	1365	159	4	shipped	2025-07-18 06:00:00+00	\N	1656.48
369	1368	198	7	paid	2025-07-19 21:00:00+00	\N	205.47
372	1371	37	10	placed	2025-07-21 12:00:00+00	\N	814.50
375	1374	76	13	cancelled	2025-07-23 03:00:00+00	\N	439.42
378	1377	115	2	shipped	2025-07-24 18:00:00+00	\N	1781.76
381	1380	154	5	paid	2025-07-26 09:00:00+00	\N	1360.08
384	1383	193	8	placed	2025-07-28 00:00:00+00	\N	644.56
387	1386	32	11	cancelled	2025-07-29 15:00:00+00	\N	56.19
390	1389	71	14	shipped	2025-07-31 06:00:00+00	\N	1773.60
393	1392	110	3	paid	2025-08-01 21:00:00+00	\N	436.44
396	1395	149	6	placed	2025-08-03 12:00:00+00	\N	654.40
399	1398	188	9	cancelled	2025-08-05 03:00:00+00	\N	162.82
402	1401	27	12	shipped	2025-08-06 18:00:00+00	\N	1552.24
405	1404	66	15	paid	2025-08-08 09:00:00+00	\N	858.57
408	1407	105	4	placed	2025-08-10 00:00:00+00	\N	183.96
411	1410	144	7	cancelled	2025-08-11 15:00:00+00	\N	249.73
414	1413	183	10	shipped	2025-08-13 06:00:00+00	\N	750.44
417	1416	22	13	paid	2025-08-14 21:00:00+00	\N	1234.74
420	1419	61	2	placed	2025-08-16 12:00:00+00	\N	551.62
423	1422	100	5	cancelled	2025-08-18 03:00:00+00	\N	414.78
426	1425	139	8	shipped	2025-08-19 18:00:00+00	\N	1661.88
429	1428	178	11	paid	2025-08-21 09:00:00+00	\N	890.52
432	1431	17	14	placed	2025-08-23 00:00:00+00	\N	661.62
435	1434	56	3	cancelled	2025-08-24 15:00:00+00	\N	62.94
438	1437	95	6	shipped	2025-08-26 06:00:00+00	\N	1768.24
441	1440	134	9	paid	2025-08-27 21:00:00+00	\N	1436.85
444	1443	173	12	placed	2025-08-29 12:00:00+00	\N	107.82
447	1446	12	15	cancelled	2025-08-31 03:00:00+00	\N	21.19
450	1449	51	4	shipped	2025-09-01 18:00:00+00	\N	1881.76
453	1452	90	7	paid	2025-09-03 09:00:00+00	\N	867.21
456	1455	129	10	placed	2025-09-05 00:00:00+00	\N	278.96
459	1458	168	13	cancelled	2025-09-06 15:00:00+00	\N	167.89
462	1461	7	2	shipped	2025-09-08 06:00:00+00	\N	425.00
465	1464	46	5	paid	2025-09-09 21:00:00+00	\N	651.96
468	1467	85	8	placed	2025-09-11 12:00:00+00	\N	995.46
471	1470	124	11	cancelled	2025-09-13 03:00:00+00	\N	106.25
474	1473	163	14	shipped	2025-09-14 18:00:00+00	\N	645.24
477	1476	2	3	paid	2025-09-16 09:00:00+00	\N	432.87
480	1479	41	6	placed	2025-09-18 00:00:00+00	\N	401.46
483	1482	80	9	cancelled	2025-09-19 15:00:00+00	\N	109.42
486	1485	119	12	shipped	2025-09-21 06:00:00+00	\N	1656.48
489	1488	158	15	paid	2025-09-22 21:00:00+00	\N	205.47
492	1491	197	4	placed	2025-09-24 12:00:00+00	\N	814.50
495	1494	36	7	cancelled	2025-09-26 03:00:00+00	\N	439.42
498	1497	75	10	shipped	2025-09-27 18:00:00+00	\N	1781.76
501	1500	114	13	paid	2025-09-29 09:00:00+00	\N	1360.08
504	1503	153	2	placed	2025-10-01 00:00:00+00	\N	644.56
507	1506	192	5	cancelled	2025-10-02 15:00:00+00	\N	56.19
510	1509	31	8	shipped	2025-10-04 06:00:00+00	\N	1773.60
513	1512	70	11	paid	2025-10-05 21:00:00+00	\N	436.44
516	1515	109	14	placed	2025-10-07 12:00:00+00	\N	654.40
519	1518	148	3	cancelled	2025-10-09 03:00:00+00	\N	162.82
522	1521	187	6	shipped	2025-10-10 18:00:00+00	\N	1552.24
525	1524	26	9	paid	2025-10-12 09:00:00+00	\N	858.57
528	1527	65	12	placed	2025-10-14 00:00:00+00	\N	183.96
531	1530	104	15	cancelled	2025-10-15 15:00:00+00	\N	249.73
534	1533	143	4	shipped	2025-10-17 06:00:00+00	\N	750.44
537	1536	182	7	paid	2025-10-18 21:00:00+00	\N	1234.74
540	1539	21	10	placed	2025-10-20 12:00:00+00	\N	551.62
543	1542	60	13	cancelled	2025-10-22 03:00:00+00	\N	414.78
546	1545	99	2	shipped	2025-10-23 18:00:00+00	\N	1661.88
549	1548	138	5	paid	2025-10-25 09:00:00+00	\N	890.52
552	1551	177	8	placed	2025-10-27 00:00:00+00	\N	661.62
555	1554	16	11	cancelled	2025-10-28 15:00:00+00	\N	62.94
558	1557	55	14	shipped	2025-10-30 06:00:00+00	\N	1768.24
561	1560	94	3	paid	2025-10-31 21:00:00+00	\N	1436.85
564	1563	133	6	placed	2025-11-02 12:00:00+00	\N	107.82
567	1566	172	9	cancelled	2025-11-04 03:00:00+00	\N	21.19
570	1569	11	12	shipped	2025-11-05 18:00:00+00	\N	1881.76
573	1572	50	15	paid	2025-11-07 09:00:00+00	\N	867.21
576	1575	89	4	placed	2025-11-09 00:00:00+00	\N	278.96
579	1578	128	7	cancelled	2025-11-10 15:00:00+00	\N	167.89
582	1581	167	10	shipped	2025-11-12 06:00:00+00	\N	425.00
585	1584	6	13	paid	2025-11-13 21:00:00+00	\N	651.96
588	1587	45	2	placed	2025-11-15 12:00:00+00	\N	995.46
591	1590	84	5	cancelled	2025-11-17 03:00:00+00	\N	106.25
594	1593	123	8	shipped	2025-11-18 18:00:00+00	\N	645.24
597	1596	162	11	paid	2025-11-20 09:00:00+00	\N	432.87
600	1599	1	14	placed	2025-11-22 00:00:00+00	\N	401.46
603	1602	4	\N	draft	\N	\N	109.42
606	1605	7	\N	draft	\N	\N	1656.48
609	1608	10	\N	draft	\N	\N	205.47
612	1611	13	\N	draft	\N	\N	814.50
615	1614	16	\N	draft	\N	\N	439.42
618	1617	19	\N	draft	\N	\N	1781.76
1	1000	14	3	paid	2025-01-01 13:00:00+00	\N	1261.55
4	1003	53	6	placed	2025-01-03 04:00:00+00	\N	1120.69
7	1006	92	9	cancelled	2025-01-04 19:00:00+00	\N	1024.18
10	1009	131	12	shipped	2025-01-06 10:00:00+00	\N	480.04
13	1012	170	15	paid	2025-01-08 01:00:00+00	\N	1333.11
16	1015	9	4	placed	2025-01-09 16:00:00+00	\N	808.98
19	1018	48	7	cancelled	2025-01-11 07:00:00+00	\N	516.04
22	1021	87	10	shipped	2025-01-12 22:00:00+00	\N	1290.40
25	1024	126	13	paid	2025-01-14 13:00:00+00	\N	316.41
28	1027	165	2	placed	2025-01-16 04:00:00+00	\N	513.82
31	1030	4	5	cancelled	2025-01-17 19:00:00+00	\N	502.19
34	1033	43	8	shipped	2025-01-19 10:00:00+00	\N	776.39
37	1036	82	11	paid	2025-01-21 01:00:00+00	\N	1831.88
40	1039	121	14	placed	2025-01-22 16:00:00+00	\N	1088.84
43	1042	160	3	cancelled	2025-01-24 07:00:00+00	\N	578.74
46	1045	199	6	shipped	2025-01-25 22:00:00+00	\N	827.48
49	1048	38	9	paid	2025-01-27 13:00:00+00	\N	2175.07
52	1051	77	12	placed	2025-01-29 04:00:00+00	\N	1193.99
55	1054	116	15	cancelled	2025-01-30 19:00:00+00	\N	340.65
58	1057	155	4	shipped	2025-02-01 10:00:00+00	\N	879.96
61	1060	194	7	paid	2025-02-03 01:00:00+00	\N	2675.59
64	1063	33	10	placed	2025-02-04 16:00:00+00	\N	910.09
67	1066	72	13	cancelled	2025-02-06 07:00:00+00	\N	1405.99
70	1069	111	2	shipped	2025-02-07 22:00:00+00	\N	2245.50
73	1072	150	5	paid	2025-02-09 13:00:00+00	\N	2604.02
76	1075	189	8	placed	2025-02-11 04:00:00+00	\N	2088.10
79	1078	28	11	cancelled	2025-02-12 19:00:00+00	\N	921.41
82	1081	67	14	shipped	2025-02-14 10:00:00+00	\N	1719.69
85	1084	106	3	paid	2025-02-16 01:00:00+00	\N	2924.58
88	1087	145	6	placed	2025-02-17 16:00:00+00	\N	1227.91
91	1090	184	9	cancelled	2025-02-19 07:00:00+00	\N	844.81
94	1093	23	12	shipped	2025-02-20 22:00:00+00	\N	240.94
97	1096	62	15	paid	2025-02-22 13:00:00+00	\N	883.86
100	1099	101	4	placed	2025-02-24 04:00:00+00	\N	1000.02
103	1102	140	7	cancelled	2025-02-25 19:00:00+00	\N	1080.05
106	1105	179	10	shipped	2025-02-27 10:00:00+00	\N	977.19
109	1108	18	13	paid	2025-03-01 01:00:00+00	\N	2228.15
112	1111	57	2	placed	2025-03-02 16:00:00+00	\N	1339.23
115	1114	96	5	cancelled	2025-03-04 07:00:00+00	\N	195.03
118	1117	135	8	shipped	2025-03-05 22:00:00+00	\N	1235.77
121	1120	174	11	paid	2025-03-07 13:00:00+00	\N	1261.55
124	1123	13	14	placed	2025-03-09 04:00:00+00	\N	1120.69
127	1126	52	3	cancelled	2025-03-10 19:00:00+00	\N	1024.18
130	1129	91	6	shipped	2025-03-12 10:00:00+00	\N	480.04
133	1132	130	9	paid	2025-03-14 01:00:00+00	\N	1333.11
136	1135	169	12	placed	2025-03-15 16:00:00+00	\N	808.98
139	1138	8	15	cancelled	2025-03-17 07:00:00+00	\N	516.04
142	1141	47	4	shipped	2025-03-18 22:00:00+00	\N	1290.40
145	1144	86	7	paid	2025-03-20 13:00:00+00	\N	316.41
148	1147	125	10	placed	2025-03-22 04:00:00+00	\N	513.82
151	1150	164	13	cancelled	2025-03-23 19:00:00+00	\N	502.19
154	1153	3	2	shipped	2025-03-25 10:00:00+00	\N	776.39
157	1156	42	5	paid	2025-03-27 01:00:00+00	\N	1831.88
160	1159	81	8	placed	2025-03-28 16:00:00+00	\N	1088.84
163	1162	120	11	cancelled	2025-03-30 07:00:00+00	\N	578.74
166	1165	159	14	shipped	2025-03-31 22:00:00+00	\N	827.48
169	1168	198	3	paid	2025-04-02 13:00:00+00	\N	2175.07
172	1171	37	6	placed	2025-04-04 04:00:00+00	\N	1193.99
175	1174	76	9	cancelled	2025-04-05 19:00:00+00	\N	340.65
178	1177	115	12	shipped	2025-04-07 10:00:00+00	\N	879.96
181	1180	154	15	paid	2025-04-09 01:00:00+00	\N	2675.59
184	1183	193	4	placed	2025-04-10 16:00:00+00	\N	910.09
187	1186	32	7	cancelled	2025-04-12 07:00:00+00	\N	1405.99
190	1189	71	10	shipped	2025-04-13 22:00:00+00	\N	2245.50
193	1192	110	13	paid	2025-04-15 13:00:00+00	\N	2604.02
196	1195	149	2	placed	2025-04-17 04:00:00+00	\N	2088.10
199	1198	188	5	cancelled	2025-04-18 19:00:00+00	\N	921.41
202	1201	27	8	shipped	2025-04-20 10:00:00+00	\N	1719.69
205	1204	66	11	paid	2025-04-22 01:00:00+00	\N	2924.58
208	1207	105	14	placed	2025-04-23 16:00:00+00	\N	1227.91
211	1210	144	3	cancelled	2025-04-25 07:00:00+00	\N	844.81
214	1213	183	6	shipped	2025-04-26 22:00:00+00	\N	240.94
217	1216	22	9	paid	2025-04-28 13:00:00+00	\N	883.86
220	1219	61	12	placed	2025-04-30 04:00:00+00	\N	1000.02
223	1222	100	15	cancelled	2025-05-01 19:00:00+00	\N	1080.05
226	1225	139	4	shipped	2025-05-03 10:00:00+00	\N	977.19
229	1228	178	7	paid	2025-05-05 01:00:00+00	\N	2228.15
232	1231	17	10	placed	2025-05-06 16:00:00+00	\N	1339.23
235	1234	56	13	cancelled	2025-05-08 07:00:00+00	\N	195.03
238	1237	95	2	shipped	2025-05-09 22:00:00+00	\N	1235.77
241	1240	134	5	paid	2025-05-11 13:00:00+00	\N	1261.55
244	1243	173	8	placed	2025-05-13 04:00:00+00	\N	1120.69
247	1246	12	11	cancelled	2025-05-14 19:00:00+00	\N	1024.18
250	1249	51	14	shipped	2025-05-16 10:00:00+00	\N	480.04
253	1252	90	3	paid	2025-05-18 01:00:00+00	\N	1333.11
256	1255	129	6	placed	2025-05-19 16:00:00+00	\N	808.98
259	1258	168	9	cancelled	2025-05-21 07:00:00+00	\N	516.04
262	1261	7	12	shipped	2025-05-22 22:00:00+00	\N	1290.40
265	1264	46	15	paid	2025-05-24 13:00:00+00	\N	316.41
268	1267	85	4	placed	2025-05-26 04:00:00+00	\N	513.82
271	1270	124	7	cancelled	2025-05-27 19:00:00+00	\N	502.19
274	1273	163	10	shipped	2025-05-29 10:00:00+00	\N	776.39
277	1276	2	13	paid	2025-05-31 01:00:00+00	\N	1831.88
280	1279	41	2	placed	2025-06-01 16:00:00+00	\N	1088.84
283	1282	80	5	cancelled	2025-06-03 07:00:00+00	\N	578.74
286	1285	119	8	shipped	2025-06-04 22:00:00+00	\N	827.48
289	1288	158	11	paid	2025-06-06 13:00:00+00	\N	2175.07
292	1291	197	14	placed	2025-06-08 04:00:00+00	\N	1193.99
295	1294	36	3	cancelled	2025-06-09 19:00:00+00	\N	340.65
298	1297	75	6	shipped	2025-06-11 10:00:00+00	\N	879.96
301	1300	114	9	paid	2025-06-13 01:00:00+00	\N	2675.59
304	1303	153	12	placed	2025-06-14 16:00:00+00	\N	910.09
307	1306	192	15	cancelled	2025-06-16 07:00:00+00	\N	1405.99
310	1309	31	4	shipped	2025-06-17 22:00:00+00	\N	2245.50
313	1312	70	7	paid	2025-06-19 13:00:00+00	\N	2604.02
316	1315	109	10	placed	2025-06-21 04:00:00+00	\N	2088.10
319	1318	148	13	cancelled	2025-06-22 19:00:00+00	\N	921.41
322	1321	187	2	shipped	2025-06-24 10:00:00+00	\N	1719.69
325	1324	26	5	paid	2025-06-26 01:00:00+00	\N	2924.58
328	1327	65	8	placed	2025-06-27 16:00:00+00	\N	1227.91
331	1330	104	11	cancelled	2025-06-29 07:00:00+00	\N	844.81
334	1333	143	14	shipped	2025-06-30 22:00:00+00	\N	240.94
337	1336	182	3	paid	2025-07-02 13:00:00+00	\N	883.86
340	1339	21	6	placed	2025-07-04 04:00:00+00	\N	1000.02
343	1342	60	9	cancelled	2025-07-05 19:00:00+00	\N	1080.05
346	1345	99	12	shipped	2025-07-07 10:00:00+00	\N	977.19
349	1348	138	15	paid	2025-07-09 01:00:00+00	\N	2228.15
352	1351	177	4	placed	2025-07-10 16:00:00+00	\N	1339.23
355	1354	16	7	cancelled	2025-07-12 07:00:00+00	\N	195.03
358	1357	55	10	shipped	2025-07-13 22:00:00+00	\N	1235.77
361	1360	94	13	paid	2025-07-15 13:00:00+00	\N	1261.55
364	1363	133	2	placed	2025-07-17 04:00:00+00	\N	1120.69
367	1366	172	5	cancelled	2025-07-18 19:00:00+00	\N	1024.18
370	1369	11	8	shipped	2025-07-20 10:00:00+00	\N	480.04
373	1372	50	11	paid	2025-07-22 01:00:00+00	\N	1333.11
376	1375	89	14	placed	2025-07-23 16:00:00+00	\N	808.98
379	1378	128	3	cancelled	2025-07-25 07:00:00+00	\N	516.04
382	1381	167	6	shipped	2025-07-26 22:00:00+00	\N	1290.40
385	1384	6	9	paid	2025-07-28 13:00:00+00	\N	316.41
388	1387	45	12	placed	2025-07-30 04:00:00+00	\N	513.82
391	1390	84	15	cancelled	2025-07-31 19:00:00+00	\N	502.19
394	1393	123	4	shipped	2025-08-02 10:00:00+00	\N	776.39
397	1396	162	7	paid	2025-08-04 01:00:00+00	\N	1831.88
400	1399	1	10	placed	2025-08-05 16:00:00+00	\N	1088.84
403	1402	40	13	cancelled	2025-08-07 07:00:00+00	\N	578.74
406	1405	79	2	shipped	2025-08-08 22:00:00+00	\N	827.48
409	1408	118	5	paid	2025-08-10 13:00:00+00	\N	2175.07
412	1411	157	8	placed	2025-08-12 04:00:00+00	\N	1193.99
415	1414	196	11	cancelled	2025-08-13 19:00:00+00	\N	340.65
418	1417	35	14	shipped	2025-08-15 10:00:00+00	\N	879.96
421	1420	74	3	paid	2025-08-17 01:00:00+00	\N	2675.59
424	1423	113	6	placed	2025-08-18 16:00:00+00	\N	910.09
427	1426	152	9	cancelled	2025-08-20 07:00:00+00	\N	1405.99
430	1429	191	12	shipped	2025-08-21 22:00:00+00	\N	2245.50
433	1432	30	15	paid	2025-08-23 13:00:00+00	\N	2604.02
436	1435	69	4	placed	2025-08-25 04:00:00+00	\N	2088.10
439	1438	108	7	cancelled	2025-08-26 19:00:00+00	\N	921.41
442	1441	147	10	shipped	2025-08-28 10:00:00+00	\N	1719.69
445	1444	186	13	paid	2025-08-30 01:00:00+00	\N	2924.58
448	1447	25	2	placed	2025-08-31 16:00:00+00	\N	1227.91
451	1450	64	5	cancelled	2025-09-02 07:00:00+00	\N	844.81
454	1453	103	8	shipped	2025-09-03 22:00:00+00	\N	240.94
457	1456	142	11	paid	2025-09-05 13:00:00+00	\N	883.86
460	1459	181	14	placed	2025-09-07 04:00:00+00	\N	1000.02
463	1462	20	3	cancelled	2025-09-08 19:00:00+00	\N	1080.05
466	1465	59	6	shipped	2025-09-10 10:00:00+00	\N	977.19
469	1468	98	9	paid	2025-09-12 01:00:00+00	\N	2228.15
472	1471	137	12	placed	2025-09-13 16:00:00+00	\N	1339.23
475	1474	176	15	cancelled	2025-09-15 07:00:00+00	\N	195.03
478	1477	15	4	shipped	2025-09-16 22:00:00+00	\N	1235.77
481	1480	54	7	paid	2025-09-18 13:00:00+00	\N	1261.55
484	1483	93	10	placed	2025-09-20 04:00:00+00	\N	1120.69
487	1486	132	13	cancelled	2025-09-21 19:00:00+00	\N	1024.18
490	1489	171	2	shipped	2025-09-23 10:00:00+00	\N	480.04
493	1492	10	5	paid	2025-09-25 01:00:00+00	\N	1333.11
496	1495	49	8	placed	2025-09-26 16:00:00+00	\N	808.98
499	1498	88	11	cancelled	2025-09-28 07:00:00+00	\N	516.04
502	1501	127	14	shipped	2025-09-29 22:00:00+00	\N	1290.40
505	1504	166	3	paid	2025-10-01 13:00:00+00	\N	316.41
508	1507	5	6	placed	2025-10-03 04:00:00+00	\N	513.82
511	1510	44	9	cancelled	2025-10-04 19:00:00+00	\N	502.19
514	1513	83	12	shipped	2025-10-06 10:00:00+00	\N	776.39
517	1516	122	15	paid	2025-10-08 01:00:00+00	\N	1831.88
520	1519	161	4	placed	2025-10-09 16:00:00+00	\N	1088.84
523	1522	200	7	cancelled	2025-10-11 07:00:00+00	\N	578.74
526	1525	39	10	shipped	2025-10-12 22:00:00+00	\N	827.48
529	1528	78	13	paid	2025-10-14 13:00:00+00	\N	2175.07
532	1531	117	2	placed	2025-10-16 04:00:00+00	\N	1193.99
535	1534	156	5	cancelled	2025-10-17 19:00:00+00	\N	340.65
538	1537	195	8	shipped	2025-10-19 10:00:00+00	\N	879.96
541	1540	34	11	paid	2025-10-21 01:00:00+00	\N	2675.59
544	1543	73	14	placed	2025-10-22 16:00:00+00	\N	910.09
547	1546	112	3	cancelled	2025-10-24 07:00:00+00	\N	1405.99
550	1549	151	6	shipped	2025-10-25 22:00:00+00	\N	2245.50
553	1552	190	9	paid	2025-10-27 13:00:00+00	\N	2604.02
556	1555	29	12	placed	2025-10-29 04:00:00+00	\N	2088.10
559	1558	68	15	cancelled	2025-10-30 19:00:00+00	\N	921.41
562	1561	107	4	shipped	2025-11-01 10:00:00+00	\N	1719.69
565	1564	146	7	paid	2025-11-03 01:00:00+00	\N	2924.58
568	1567	185	10	placed	2025-11-04 16:00:00+00	\N	1227.91
571	1570	24	13	cancelled	2025-11-06 07:00:00+00	\N	844.81
574	1573	63	2	shipped	2025-11-07 22:00:00+00	\N	240.94
577	1576	102	5	paid	2025-11-09 13:00:00+00	\N	883.86
580	1579	141	8	placed	2025-11-11 04:00:00+00	\N	1000.02
583	1582	180	11	cancelled	2025-11-12 19:00:00+00	\N	1080.05
586	1585	19	14	shipped	2025-11-14 10:00:00+00	\N	977.19
589	1588	58	3	paid	2025-11-16 01:00:00+00	\N	2228.15
592	1591	97	6	placed	2025-11-17 16:00:00+00	\N	1339.23
595	1594	136	9	cancelled	2025-11-19 07:00:00+00	\N	195.03
598	1597	175	12	shipped	2025-11-20 22:00:00+00	\N	1235.77
601	1600	2	\N	draft	\N	\N	1261.55
604	1603	5	\N	draft	\N	\N	1120.69
607	1606	8	\N	draft	\N	\N	1024.18
610	1609	11	\N	draft	\N	\N	480.04
613	1612	14	\N	draft	\N	\N	1333.11
616	1615	17	\N	draft	\N	\N	808.98
619	1618	20	\N	draft	\N	\N	516.04
2	1001	27	4	shipped	2025-01-02 02:00:00+00	\N	1024.55
5	1004	66	7	paid	2025-01-03 17:00:00+00	\N	823.99
8	1007	105	10	placed	2025-01-05 08:00:00+00	\N	2153.28
11	1010	144	13	cancelled	2025-01-06 23:00:00+00	\N	2854.79
14	1013	183	2	shipped	2025-01-08 14:00:00+00	\N	2153.45
17	1016	22	5	paid	2025-01-10 05:00:00+00	\N	2101.39
20	1019	61	8	placed	2025-01-11 20:00:00+00	\N	877.71
23	1022	100	11	cancelled	2025-01-13 11:00:00+00	\N	997.80
26	1025	139	14	shipped	2025-01-15 02:00:00+00	\N	1822.64
29	1028	178	3	paid	2025-01-16 17:00:00+00	\N	2507.00
32	1031	17	6	placed	2025-01-18 08:00:00+00	\N	1139.45
35	1034	56	9	cancelled	2025-01-19 23:00:00+00	\N	2651.93
38	1037	95	12	shipped	2025-01-21 14:00:00+00	\N	2279.90
41	1040	134	15	paid	2025-01-23 05:00:00+00	\N	2315.98
44	1043	173	4	placed	2025-01-24 20:00:00+00	\N	3056.00
47	1046	12	7	cancelled	2025-01-26 11:00:00+00	\N	2314.33
50	1049	51	10	shipped	2025-01-28 02:00:00+00	\N	2164.89
53	1052	90	13	paid	2025-01-29 17:00:00+00	\N	3335.04
56	1055	129	2	placed	2025-01-31 08:00:00+00	\N	1674.90
59	1058	168	5	cancelled	2025-02-01 23:00:00+00	\N	1388.88
62	1061	7	8	shipped	2025-02-03 14:00:00+00	\N	2156.62
65	1064	46	11	paid	2025-02-05 05:00:00+00	\N	2456.99
68	1067	85	14	placed	2025-02-06 20:00:00+00	\N	2204.91
71	1070	124	3	cancelled	2025-02-08 11:00:00+00	\N	412.47
74	1073	163	6	shipped	2025-02-10 02:00:00+00	\N	1050.35
77	1076	2	9	paid	2025-02-11 17:00:00+00	\N	1665.59
80	1079	41	12	placed	2025-02-13 08:00:00+00	\N	2211.84
83	1082	80	15	cancelled	2025-02-14 23:00:00+00	\N	1333.13
86	1085	119	4	shipped	2025-02-16 14:00:00+00	\N	1355.86
89	1088	158	7	paid	2025-02-18 05:00:00+00	\N	2624.21
92	1091	197	10	placed	2025-02-19 20:00:00+00	\N	1509.04
95	1094	36	13	cancelled	2025-02-21 11:00:00+00	\N	1986.74
98	1097	75	2	shipped	2025-02-23 02:00:00+00	\N	913.72
101	1100	114	5	paid	2025-02-24 17:00:00+00	\N	2062.06
104	1103	153	8	placed	2025-02-26 08:00:00+00	\N	2842.19
107	1106	192	11	cancelled	2025-02-27 23:00:00+00	\N	1669.33
110	1109	31	14	shipped	2025-03-01 14:00:00+00	\N	1454.21
113	1112	70	3	paid	2025-03-03 05:00:00+00	\N	2674.13
116	1115	109	6	placed	2025-03-04 20:00:00+00	\N	2707.05
119	1118	148	9	cancelled	2025-03-06 11:00:00+00	\N	2036.34
122	1121	187	12	shipped	2025-03-08 02:00:00+00	\N	1024.55
125	1124	26	15	paid	2025-03-09 17:00:00+00	\N	823.99
128	1127	65	4	placed	2025-03-11 08:00:00+00	\N	2153.28
131	1130	104	7	cancelled	2025-03-12 23:00:00+00	\N	2854.79
134	1133	143	10	shipped	2025-03-14 14:00:00+00	\N	2153.45
137	1136	182	13	paid	2025-03-16 05:00:00+00	\N	2101.39
140	1139	21	2	placed	2025-03-17 20:00:00+00	\N	877.71
143	1142	60	5	cancelled	2025-03-19 11:00:00+00	\N	997.80
146	1145	99	8	shipped	2025-03-21 02:00:00+00	\N	1822.64
149	1148	138	11	paid	2025-03-22 17:00:00+00	\N	2507.00
152	1151	177	14	placed	2025-03-24 08:00:00+00	\N	1139.45
155	1154	16	3	cancelled	2025-03-25 23:00:00+00	\N	2651.93
158	1157	55	6	shipped	2025-03-27 14:00:00+00	\N	2279.90
161	1160	94	9	paid	2025-03-29 05:00:00+00	\N	2315.98
164	1163	133	12	placed	2025-03-30 20:00:00+00	\N	3056.00
167	1166	172	15	cancelled	2025-04-01 11:00:00+00	\N	2314.33
170	1169	11	4	shipped	2025-04-03 02:00:00+00	\N	2164.89
173	1172	50	7	paid	2025-04-04 17:00:00+00	\N	3335.04
176	1175	89	10	placed	2025-04-06 08:00:00+00	\N	1674.90
179	1178	128	13	cancelled	2025-04-07 23:00:00+00	\N	1388.88
182	1181	167	2	shipped	2025-04-09 14:00:00+00	\N	2156.62
185	1184	6	5	paid	2025-04-11 05:00:00+00	\N	2456.99
188	1187	45	8	placed	2025-04-12 20:00:00+00	\N	2204.91
191	1190	84	11	cancelled	2025-04-14 11:00:00+00	\N	412.47
194	1193	123	14	shipped	2025-04-16 02:00:00+00	\N	1050.35
602	1601	3	\N	draft	\N	\N	1024.55
197	1196	162	3	paid	2025-04-17 17:00:00+00	\N	1665.59
200	1199	1	6	placed	2025-04-19 08:00:00+00	\N	2211.84
203	1202	40	9	cancelled	2025-04-20 23:00:00+00	\N	1333.13
206	1205	79	12	shipped	2025-04-22 14:00:00+00	\N	1355.86
209	1208	118	15	paid	2025-04-24 05:00:00+00	\N	2624.21
212	1211	157	4	placed	2025-04-25 20:00:00+00	\N	1509.04
215	1214	196	7	cancelled	2025-04-27 11:00:00+00	\N	1986.74
218	1217	35	10	shipped	2025-04-29 02:00:00+00	\N	913.72
221	1220	74	13	paid	2025-04-30 17:00:00+00	\N	2062.06
224	1223	113	2	placed	2025-05-02 08:00:00+00	\N	2842.19
227	1226	152	5	cancelled	2025-05-03 23:00:00+00	\N	1669.33
230	1229	191	8	shipped	2025-05-05 14:00:00+00	\N	1454.21
233	1232	30	11	paid	2025-05-07 05:00:00+00	\N	2674.13
236	1235	69	14	placed	2025-05-08 20:00:00+00	\N	2707.05
239	1238	108	3	cancelled	2025-05-10 11:00:00+00	\N	2036.34
242	1241	147	6	shipped	2025-05-12 02:00:00+00	\N	1024.55
245	1244	186	9	paid	2025-05-13 17:00:00+00	\N	823.99
248	1247	25	12	placed	2025-05-15 08:00:00+00	\N	2153.28
251	1250	64	15	cancelled	2025-05-16 23:00:00+00	\N	2854.79
254	1253	103	4	shipped	2025-05-18 14:00:00+00	\N	2153.45
257	1256	142	7	paid	2025-05-20 05:00:00+00	\N	2101.39
260	1259	181	10	placed	2025-05-21 20:00:00+00	\N	877.71
263	1262	20	13	cancelled	2025-05-23 11:00:00+00	\N	997.80
266	1265	59	2	shipped	2025-05-25 02:00:00+00	\N	1822.64
269	1268	98	5	paid	2025-05-26 17:00:00+00	\N	2507.00
272	1271	137	8	placed	2025-05-28 08:00:00+00	\N	1139.45
275	1274	176	11	cancelled	2025-05-29 23:00:00+00	\N	2651.93
278	1277	15	14	shipped	2025-05-31 14:00:00+00	\N	2279.90
281	1280	54	3	paid	2025-06-02 05:00:00+00	\N	2315.98
284	1283	93	6	placed	2025-06-03 20:00:00+00	\N	3056.00
287	1286	132	9	cancelled	2025-06-05 11:00:00+00	\N	2314.33
290	1289	171	12	shipped	2025-06-07 02:00:00+00	\N	2164.89
293	1292	10	15	paid	2025-06-08 17:00:00+00	\N	3335.04
296	1295	49	4	placed	2025-06-10 08:00:00+00	\N	1674.90
299	1298	88	7	cancelled	2025-06-11 23:00:00+00	\N	1388.88
302	1301	127	10	shipped	2025-06-13 14:00:00+00	\N	2156.62
305	1304	166	13	paid	2025-06-15 05:00:00+00	\N	2456.99
308	1307	5	2	placed	2025-06-16 20:00:00+00	\N	2204.91
311	1310	44	5	cancelled	2025-06-18 11:00:00+00	\N	412.47
314	1313	83	8	shipped	2025-06-20 02:00:00+00	\N	1050.35
317	1316	122	11	paid	2025-06-21 17:00:00+00	\N	1665.59
320	1319	161	14	placed	2025-06-23 08:00:00+00	\N	2211.84
323	1322	200	3	cancelled	2025-06-24 23:00:00+00	\N	1333.13
326	1325	39	6	shipped	2025-06-26 14:00:00+00	\N	1355.86
329	1328	78	9	paid	2025-06-28 05:00:00+00	\N	2624.21
332	1331	117	12	placed	2025-06-29 20:00:00+00	\N	1509.04
335	1334	156	15	cancelled	2025-07-01 11:00:00+00	\N	1986.74
338	1337	195	4	shipped	2025-07-03 02:00:00+00	\N	913.72
341	1340	34	7	paid	2025-07-04 17:00:00+00	\N	2062.06
344	1343	73	10	placed	2025-07-06 08:00:00+00	\N	2842.19
347	1346	112	13	cancelled	2025-07-07 23:00:00+00	\N	1669.33
350	1349	151	2	shipped	2025-07-09 14:00:00+00	\N	1454.21
353	1352	190	5	paid	2025-07-11 05:00:00+00	\N	2674.13
356	1355	29	8	placed	2025-07-12 20:00:00+00	\N	2707.05
359	1358	68	11	cancelled	2025-07-14 11:00:00+00	\N	2036.34
362	1361	107	14	shipped	2025-07-16 02:00:00+00	\N	1024.55
365	1364	146	3	paid	2025-07-17 17:00:00+00	\N	823.99
368	1367	185	6	placed	2025-07-19 08:00:00+00	\N	2153.28
371	1370	24	9	cancelled	2025-07-20 23:00:00+00	\N	2854.79
374	1373	63	12	shipped	2025-07-22 14:00:00+00	\N	2153.45
377	1376	102	15	paid	2025-07-24 05:00:00+00	\N	2101.39
380	1379	141	4	placed	2025-07-25 20:00:00+00	\N	877.71
383	1382	180	7	cancelled	2025-07-27 11:00:00+00	\N	997.80
386	1385	19	10	shipped	2025-07-29 02:00:00+00	\N	1822.64
389	1388	58	13	paid	2025-07-30 17:00:00+00	\N	2507.00
392	1391	97	2	placed	2025-08-01 08:00:00+00	\N	1139.45
395	1394	136	5	cancelled	2025-08-02 23:00:00+00	\N	2651.93
398	1397	175	8	shipped	2025-08-04 14:00:00+00	\N	2279.90
401	1400	14	11	paid	2025-08-06 05:00:00+00	\N	2315.98
404	1403	53	14	placed	2025-08-07 20:00:00+00	\N	3056.00
407	1406	92	3	cancelled	2025-08-09 11:00:00+00	\N	2314.33
410	1409	131	6	shipped	2025-08-11 02:00:00+00	\N	2164.89
413	1412	170	9	paid	2025-08-12 17:00:00+00	\N	3335.04
416	1415	9	12	placed	2025-08-14 08:00:00+00	\N	1674.90
419	1418	48	15	cancelled	2025-08-15 23:00:00+00	\N	1388.88
422	1421	87	4	shipped	2025-08-17 14:00:00+00	\N	2156.62
425	1424	126	7	paid	2025-08-19 05:00:00+00	\N	2456.99
428	1427	165	10	placed	2025-08-20 20:00:00+00	\N	2204.91
431	1430	4	13	cancelled	2025-08-22 11:00:00+00	\N	412.47
434	1433	43	2	shipped	2025-08-24 02:00:00+00	\N	1050.35
437	1436	82	5	paid	2025-08-25 17:00:00+00	\N	1665.59
440	1439	121	8	placed	2025-08-27 08:00:00+00	\N	2211.84
443	1442	160	11	cancelled	2025-08-28 23:00:00+00	\N	1333.13
446	1445	199	14	shipped	2025-08-30 14:00:00+00	\N	1355.86
449	1448	38	3	paid	2025-09-01 05:00:00+00	\N	2624.21
452	1451	77	6	placed	2025-09-02 20:00:00+00	\N	1509.04
455	1454	116	9	cancelled	2025-09-04 11:00:00+00	\N	1986.74
458	1457	155	12	shipped	2025-09-06 02:00:00+00	\N	913.72
461	1460	194	15	paid	2025-09-07 17:00:00+00	\N	2062.06
464	1463	33	4	placed	2025-09-09 08:00:00+00	\N	2842.19
467	1466	72	7	cancelled	2025-09-10 23:00:00+00	\N	1669.33
470	1469	111	10	shipped	2025-09-12 14:00:00+00	\N	1454.21
473	1472	150	13	paid	2025-09-14 05:00:00+00	\N	2674.13
476	1475	189	2	placed	2025-09-15 20:00:00+00	\N	2707.05
479	1478	28	5	cancelled	2025-09-17 11:00:00+00	\N	2036.34
482	1481	67	8	shipped	2025-09-19 02:00:00+00	\N	1024.55
485	1484	106	11	paid	2025-09-20 17:00:00+00	\N	823.99
488	1487	145	14	placed	2025-09-22 08:00:00+00	\N	2153.28
491	1490	184	3	cancelled	2025-09-23 23:00:00+00	\N	2854.79
494	1493	23	6	shipped	2025-09-25 14:00:00+00	\N	2153.45
497	1496	62	9	paid	2025-09-27 05:00:00+00	\N	2101.39
500	1499	101	12	placed	2025-09-28 20:00:00+00	\N	877.71
503	1502	140	15	cancelled	2025-09-30 11:00:00+00	\N	997.80
506	1505	179	4	shipped	2025-10-02 02:00:00+00	\N	1822.64
509	1508	18	7	paid	2025-10-03 17:00:00+00	\N	2507.00
512	1511	57	10	placed	2025-10-05 08:00:00+00	\N	1139.45
515	1514	96	13	cancelled	2025-10-06 23:00:00+00	\N	2651.93
518	1517	135	2	shipped	2025-10-08 14:00:00+00	\N	2279.90
521	1520	174	5	paid	2025-10-10 05:00:00+00	\N	2315.98
524	1523	13	8	placed	2025-10-11 20:00:00+00	\N	3056.00
527	1526	52	11	cancelled	2025-10-13 11:00:00+00	\N	2314.33
530	1529	91	14	shipped	2025-10-15 02:00:00+00	\N	2164.89
533	1532	130	3	paid	2025-10-16 17:00:00+00	\N	3335.04
536	1535	169	6	placed	2025-10-18 08:00:00+00	\N	1674.90
539	1538	8	9	cancelled	2025-10-19 23:00:00+00	\N	1388.88
542	1541	47	12	shipped	2025-10-21 14:00:00+00	\N	2156.62
545	1544	86	15	paid	2025-10-23 05:00:00+00	\N	2456.99
548	1547	125	4	placed	2025-10-24 20:00:00+00	\N	2204.91
551	1550	164	7	cancelled	2025-10-26 11:00:00+00	\N	412.47
554	1553	3	10	shipped	2025-10-28 02:00:00+00	\N	1050.35
557	1556	42	13	paid	2025-10-29 17:00:00+00	\N	1665.59
560	1559	81	2	placed	2025-10-31 08:00:00+00	\N	2211.84
563	1562	120	5	cancelled	2025-11-01 23:00:00+00	\N	1333.13
566	1565	159	8	shipped	2025-11-03 14:00:00+00	\N	1355.86
569	1568	198	11	paid	2025-11-05 05:00:00+00	\N	2624.21
572	1571	37	14	placed	2025-11-06 20:00:00+00	\N	1509.04
575	1574	76	3	cancelled	2025-11-08 11:00:00+00	\N	1986.74
578	1577	115	6	shipped	2025-11-10 02:00:00+00	\N	913.72
581	1580	154	9	paid	2025-11-11 17:00:00+00	\N	2062.06
584	1583	193	12	placed	2025-11-13 08:00:00+00	\N	2842.19
587	1586	32	15	cancelled	2025-11-14 23:00:00+00	\N	1669.33
590	1589	71	4	shipped	2025-11-16 14:00:00+00	\N	1454.21
593	1592	110	7	paid	2025-11-18 05:00:00+00	\N	2674.13
596	1595	149	10	placed	2025-11-19 20:00:00+00	\N	2707.05
599	1598	188	13	cancelled	2025-11-21 11:00:00+00	\N	2036.34
605	1604	6	\N	draft	\N	\N	823.99
608	1607	9	\N	draft	\N	\N	2153.28
611	1610	12	\N	draft	\N	\N	2854.79
614	1613	15	\N	draft	\N	\N	2153.45
617	1616	18	\N	draft	\N	\N	2101.39
620	1619	21	\N	draft	\N	\N	877.71
\.


--
-- Data for Name: imported_orders; Type: TABLE DATA; Schema: staging; Owner: -
--

COPY staging.imported_orders (external_ref, customer_id, product_id, quantity, raw, loaded_at) FROM stdin;
MKT-1	2	2	2	{"n": 1, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-2	3	3	3	{"n": 2, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-3	4	4	1	{"n": 3, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-4	5	5	2	{"n": 4, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-5	6	6	3	{"n": 5, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-6	7	7	1	{"n": 6, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-7	8	8	2	{"n": 7, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-8	9	9	3	{"n": 8, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-9	10	10	1	{"n": 9, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-10	9010	11	2	{"n": 10, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-11	12	12	3	{"n": 11, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-12	13	13	1	{"n": 12, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-13	14	14	2	{"n": 13, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-14	15	15	3	{"n": 14, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-15	16	16	1	{"n": 15, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-16	17	17	2	{"n": 16, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-17	18	18	3	{"n": 17, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-18	19	19	1	{"n": 18, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-19	20	20	2	{"n": 19, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-20	9020	21	3	{"n": 20, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-21	22	22	1	{"n": 21, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-22	23	23	2	{"n": 22, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-23	24	24	3	{"n": 23, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-24	25	25	1	{"n": 24, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-25	26	26	2	{"n": 25, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-26	27	27	3	{"n": 26, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-27	28	28	1	{"n": 27, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-28	29	29	2	{"n": 28, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-29	30	30	3	{"n": 29, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-30	9030	31	1	{"n": 30, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-31	32	32	2	{"n": 31, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-32	33	33	3	{"n": 32, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-33	34	34	1	{"n": 33, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-34	35	35	2	{"n": 34, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-35	36	36	3	{"n": 35, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-36	37	37	1	{"n": 36, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-37	38	38	2	{"n": 37, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-38	39	39	3	{"n": 38, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-39	40	40	1	{"n": 39, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-40	9040	41	2	{"n": 40, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-41	42	42	3	{"n": 41, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-42	43	43	1	{"n": 42, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-43	44	44	2	{"n": 43, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-44	45	45	3	{"n": 44, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-45	46	46	1	{"n": 45, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-46	47	47	2	{"n": 46, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-47	48	48	3	{"n": 47, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-48	49	49	1	{"n": 48, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-49	50	50	2	{"n": 49, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-50	9050	51	3	{"n": 50, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-51	52	52	1	{"n": 51, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-52	53	53	2	{"n": 52, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-53	54	54	3	{"n": 53, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-54	55	55	1	{"n": 54, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-55	56	56	2	{"n": 55, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-56	57	57	3	{"n": 56, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-57	58	58	1	{"n": 57, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-58	59	59	2	{"n": 58, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-59	60	60	3	{"n": 59, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-60	9060	61	1	{"n": 60, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-61	62	62	2	{"n": 61, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-62	63	63	3	{"n": 62, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-63	64	64	1	{"n": 63, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-64	65	65	2	{"n": 64, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-65	66	66	3	{"n": 65, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-66	67	67	1	{"n": 66, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-67	68	68	2	{"n": 67, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-68	69	69	3	{"n": 68, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-69	70	70	1	{"n": 69, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-70	9070	71	2	{"n": 70, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-71	72	72	3	{"n": 71, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-72	73	73	1	{"n": 72, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-73	74	74	2	{"n": 73, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-74	75	75	3	{"n": 74, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-75	76	76	1	{"n": 75, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-76	77	77	2	{"n": 76, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-77	78	78	3	{"n": 77, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-78	79	79	1	{"n": 78, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-79	80	80	2	{"n": 79, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-80	9080	81	3	{"n": 80, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-81	82	82	1	{"n": 81, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-82	83	83	2	{"n": 82, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-83	84	84	3	{"n": 83, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-84	85	85	1	{"n": 84, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-85	86	86	2	{"n": 85, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-86	87	87	3	{"n": 86, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-87	88	88	1	{"n": 87, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-88	89	89	2	{"n": 88, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-89	90	90	3	{"n": 89, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-90	9090	91	1	{"n": 90, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-91	92	92	2	{"n": 91, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-92	93	93	3	{"n": 92, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-93	94	94	1	{"n": 93, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-94	95	95	2	{"n": 94, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-95	96	96	3	{"n": 95, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-96	97	97	1	{"n": 96, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-97	98	98	2	{"n": 97, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-98	99	99	3	{"n": 98, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-99	100	100	1	{"n": 99, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-100	9100	101	2	{"n": 100, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-101	102	102	3	{"n": 101, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-102	103	103	1	{"n": 102, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-103	104	104	2	{"n": 103, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-104	105	105	3	{"n": 104, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-105	106	106	1	{"n": 105, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-106	107	107	2	{"n": 106, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-107	108	108	3	{"n": 107, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-108	109	109	1	{"n": 108, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-109	110	110	2	{"n": 109, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-110	9110	111	3	{"n": 110, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-111	112	112	1	{"n": 111, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-112	113	113	2	{"n": 112, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-113	114	114	3	{"n": 113, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-114	115	115	1	{"n": 114, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-115	116	116	2	{"n": 115, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-116	117	117	3	{"n": 116, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-117	118	118	1	{"n": 117, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-118	119	119	2	{"n": 118, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-119	120	120	3	{"n": 119, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-120	9120	1	1	{"n": 120, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-121	122	2	2	{"n": 121, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-122	123	3	3	{"n": 122, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-123	124	4	1	{"n": 123, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-124	125	5	2	{"n": 124, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-125	126	6	3	{"n": 125, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-126	127	7	1	{"n": 126, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-127	128	8	2	{"n": 127, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-128	129	9	3	{"n": 128, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-129	130	10	1	{"n": 129, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-130	9130	11	2	{"n": 130, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-131	132	12	3	{"n": 131, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-132	133	13	1	{"n": 132, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-133	134	14	2	{"n": 133, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-134	135	15	3	{"n": 134, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-135	136	16	1	{"n": 135, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-136	137	17	2	{"n": 136, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-137	138	18	3	{"n": 137, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-138	139	19	1	{"n": 138, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-139	140	20	2	{"n": 139, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-140	9140	21	3	{"n": 140, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-141	142	22	1	{"n": 141, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-142	143	23	2	{"n": 142, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-143	144	24	3	{"n": 143, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-144	145	25	1	{"n": 144, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-145	146	26	2	{"n": 145, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-146	147	27	3	{"n": 146, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-147	148	28	1	{"n": 147, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-148	149	29	2	{"n": 148, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-149	150	30	3	{"n": 149, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-150	9150	31	1	{"n": 150, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-151	152	32	2	{"n": 151, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-152	153	33	3	{"n": 152, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-153	154	34	1	{"n": 153, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-154	155	35	2	{"n": 154, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-155	156	36	3	{"n": 155, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-156	157	37	1	{"n": 156, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-157	158	38	2	{"n": 157, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-158	159	39	3	{"n": 158, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-159	160	40	1	{"n": 159, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-160	9160	41	2	{"n": 160, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-161	162	42	3	{"n": 161, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-162	163	43	1	{"n": 162, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-163	164	44	2	{"n": 163, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-164	165	45	3	{"n": 164, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-165	166	46	1	{"n": 165, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-166	167	47	2	{"n": 166, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-167	168	48	3	{"n": 167, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-168	169	49	1	{"n": 168, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-169	170	50	2	{"n": 169, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-170	9170	51	3	{"n": 170, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-171	172	52	1	{"n": 171, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-172	173	53	2	{"n": 172, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-173	174	54	3	{"n": 173, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-174	175	55	1	{"n": 174, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-175	176	56	2	{"n": 175, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-176	177	57	3	{"n": 176, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-177	178	58	1	{"n": 177, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-178	179	59	2	{"n": 178, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-179	180	60	3	{"n": 179, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-180	9180	61	1	{"n": 180, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-181	182	62	2	{"n": 181, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-182	183	63	3	{"n": 182, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-183	184	64	1	{"n": 183, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-184	185	65	2	{"n": 184, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-185	186	66	3	{"n": 185, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-186	187	67	1	{"n": 186, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-187	188	68	2	{"n": 187, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-188	189	69	3	{"n": 188, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-189	190	70	1	{"n": 189, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-190	9190	71	2	{"n": 190, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-191	192	72	3	{"n": 191, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-192	193	73	1	{"n": 192, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-193	194	74	2	{"n": 193, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-194	195	75	3	{"n": 194, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-195	196	76	1	{"n": 195, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-196	197	77	2	{"n": 196, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-197	198	78	3	{"n": 197, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-198	199	79	1	{"n": 198, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-199	200	80	2	{"n": 199, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-200	9200	81	3	{"n": 200, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-201	2	82	1	{"n": 201, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-202	3	83	2	{"n": 202, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-203	4	84	3	{"n": 203, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-204	5	85	1	{"n": 204, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-205	6	86	2	{"n": 205, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-206	7	87	3	{"n": 206, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-207	8	88	1	{"n": 207, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-208	9	89	2	{"n": 208, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-209	10	90	3	{"n": 209, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-210	9210	91	1	{"n": 210, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-211	12	92	2	{"n": 211, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-212	13	93	3	{"n": 212, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-213	14	94	1	{"n": 213, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-214	15	95	2	{"n": 214, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-215	16	96	3	{"n": 215, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-216	17	97	1	{"n": 216, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-217	18	98	2	{"n": 217, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-218	19	99	3	{"n": 218, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-219	20	100	1	{"n": 219, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-220	9220	101	2	{"n": 220, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-221	22	102	3	{"n": 221, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-222	23	103	1	{"n": 222, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-223	24	104	2	{"n": 223, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-224	25	105	3	{"n": 224, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-225	26	106	1	{"n": 225, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-226	27	107	2	{"n": 226, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-227	28	108	3	{"n": 227, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-228	29	109	1	{"n": 228, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-229	30	110	2	{"n": 229, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-230	9230	111	3	{"n": 230, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-231	32	112	1	{"n": 231, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-232	33	113	2	{"n": 232, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-233	34	114	3	{"n": 233, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-234	35	115	1	{"n": 234, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-235	36	116	2	{"n": 235, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-236	37	117	3	{"n": 236, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-237	38	118	1	{"n": 237, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-238	39	119	2	{"n": 238, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-239	40	120	3	{"n": 239, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-240	9240	1	1	{"n": 240, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-241	42	2	2	{"n": 241, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-242	43	3	3	{"n": 242, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-243	44	4	1	{"n": 243, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-244	45	5	2	{"n": 244, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-245	46	6	3	{"n": 245, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-246	47	7	1	{"n": 246, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-247	48	8	2	{"n": 247, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-248	49	9	3	{"n": 248, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-249	50	10	1	{"n": 249, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-250	9250	11	2	{"n": 250, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-251	52	12	3	{"n": 251, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-252	53	13	1	{"n": 252, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-253	54	14	2	{"n": 253, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-254	55	15	3	{"n": 254, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-255	56	16	1	{"n": 255, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-256	57	17	2	{"n": 256, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-257	58	18	3	{"n": 257, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-258	59	19	1	{"n": 258, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-259	60	20	2	{"n": 259, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-260	9260	21	3	{"n": 260, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-261	62	22	1	{"n": 261, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-262	63	23	2	{"n": 262, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-263	64	24	3	{"n": 263, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-264	65	25	1	{"n": 264, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-265	66	26	2	{"n": 265, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-266	67	27	3	{"n": 266, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-267	68	28	1	{"n": 267, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-268	69	29	2	{"n": 268, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-269	70	30	3	{"n": 269, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-270	9270	31	1	{"n": 270, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-271	72	32	2	{"n": 271, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-272	73	33	3	{"n": 272, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-273	74	34	1	{"n": 273, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-274	75	35	2	{"n": 274, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-275	76	36	3	{"n": 275, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-276	77	37	1	{"n": 276, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-277	78	38	2	{"n": 277, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-278	79	39	3	{"n": 278, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-279	80	40	1	{"n": 279, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-280	9280	41	2	{"n": 280, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-281	82	42	3	{"n": 281, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-282	83	43	1	{"n": 282, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-283	84	44	2	{"n": 283, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-284	85	45	3	{"n": 284, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-285	86	46	1	{"n": 285, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-286	87	47	2	{"n": 286, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-287	88	48	3	{"n": 287, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-288	89	49	1	{"n": 288, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-289	90	50	2	{"n": 289, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-290	9290	51	3	{"n": 290, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-291	92	52	1	{"n": 291, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-292	93	53	2	{"n": 292, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-293	94	54	3	{"n": 293, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-294	95	55	1	{"n": 294, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-295	96	56	2	{"n": 295, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-296	97	57	3	{"n": 296, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-297	98	58	1	{"n": 297, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-298	99	59	2	{"n": 298, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-299	100	60	3	{"n": 299, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
MKT-300	9300	61	1	{"n": 300, "marketplace": "acme-mkt"}	2026-10-30 14:05:26.233627+00
\.


--
-- Data for Name: session_cache; Type: TABLE DATA; Schema: staging; Owner: -
--

COPY staging.session_cache (token, customer_id, expires_at) FROM stdin;
287e7f51c0b31d0573f7761dd0615130	2	2026-10-30 15:05:26.235198+00
e59c5a383528943bba3f90e3ae50741c	3	2026-10-30 15:05:26.235198+00
7b397ac51f1bf8d5ba46243fa50454a6	4	2026-10-30 15:05:26.235198+00
5be5b8d25ad274bb8db3b755f2105942	5	2026-10-30 15:05:26.235198+00
95813611df8a80f71879501fd2b5b168	6	2026-10-30 15:05:26.235198+00
3f8fca0b4df85b4ce9e310e8e85a5d00	7	2026-10-30 15:05:26.235198+00
a5149445b39cd5e6e93f5b52926ea331	8	2026-10-30 15:05:26.235198+00
18aa1052bcb73767fe35b62ed2c2debd	9	2026-10-30 15:05:26.235198+00
9b21cc1ec5a61e6a6d466e055ae76878	10	2026-10-30 15:05:26.235198+00
726af7bd0ba2aedb9640fb4ebd043e3a	11	2026-10-30 15:05:26.235198+00
b5d4eaf81b86419a6d04a7449f5eacc2	12	2026-10-30 15:05:26.235198+00
0276cca9ddcae5c8894d1ad8122abfca	13	2026-10-30 15:05:26.235198+00
1a35036bd81972106d088c7342480092	14	2026-10-30 15:05:26.235198+00
b7ff47a975e020ee8f960b6af7205dde	15	2026-10-30 15:05:26.235198+00
d159801fe6d9e758062f4be3ad2aa311	16	2026-10-30 15:05:26.235198+00
661666c3f83dfd05fe1a287dbc809263	17	2026-10-30 15:05:26.235198+00
a09c70fbf62ac2616f6db6d699cfe6aa	18	2026-10-30 15:05:26.235198+00
81856e333ced01c9f071792212bb2995	19	2026-10-30 15:05:26.235198+00
c5455c4d2d75dcf8b3bff870fa2d683a	20	2026-10-30 15:05:26.235198+00
b564d5ff3b3eb7345dad49e1d8639225	21	2026-10-30 15:05:26.235198+00
dab49398c494df68ff41615fe71682db	22	2026-10-30 15:05:26.235198+00
6056d899651dffe3142639cefb3aee24	23	2026-10-30 15:05:26.235198+00
13bbc4f3aad045a77b7e9951e918e4cb	24	2026-10-30 15:05:26.235198+00
22985fed2b6710a5a5becd031e388426	25	2026-10-30 15:05:26.235198+00
8f37bbc095e4ce842587c58619fcceea	26	2026-10-30 15:05:26.235198+00
7953c53d9939332346bc0c8c2e52b8a8	27	2026-10-30 15:05:26.235198+00
dd55384617ec01ae2d276467f29dd6a4	28	2026-10-30 15:05:26.235198+00
f9389ac0327a2e7bfae94a7738ac7b6a	29	2026-10-30 15:05:26.235198+00
2377ab71e4a56e546b633052914b1180	30	2026-10-30 15:05:26.235198+00
d7bdacd0847d6f8cb62ad3b9d297f454	31	2026-10-30 15:05:26.235198+00
18477fea64a3ad977d6b7a51396d186e	32	2026-10-30 15:05:26.235198+00
cf9f804c88565e66a5b67a94844df207	33	2026-10-30 15:05:26.235198+00
86e3d35e577385d74de07848abe32f95	34	2026-10-30 15:05:26.235198+00
5ba472fcf12d1865de2995406411a269	35	2026-10-30 15:05:26.235198+00
063a8604a2437969909e707ea323d334	36	2026-10-30 15:05:26.235198+00
c485fcf510706a492de857969e51a59d	37	2026-10-30 15:05:26.235198+00
73903442452c5903575ce9e77bb40961	38	2026-10-30 15:05:26.235198+00
0fe8742c6864da9d6ce5f93dc55b896d	39	2026-10-30 15:05:26.235198+00
c8971def65bcdf1ee863c423aae40fa3	40	2026-10-30 15:05:26.235198+00
0618a6302bdfee59f80f9d73343133f7	41	2026-10-30 15:05:26.235198+00
bb8d4564bbe156915de5dba9a6a72c47	42	2026-10-30 15:05:26.235198+00
ba4969254719434bbdc5228405293ecd	43	2026-10-30 15:05:26.235198+00
bf671a4fbcb12bd53772779a128d6359	44	2026-10-30 15:05:26.235198+00
dda8f7f4f1fed4b70ede51a2f8033f54	45	2026-10-30 15:05:26.235198+00
3516080cd84c47038e2ae44f6a915c4d	46	2026-10-30 15:05:26.235198+00
f774dcf11dc4a85361eabae6a4c457ed	47	2026-10-30 15:05:26.235198+00
9a1829bb33155ddba655acf8ff8c2569	48	2026-10-30 15:05:26.235198+00
b25b60dfa635b60695d84a480c9202c7	49	2026-10-30 15:05:26.235198+00
16e50e3472cec9d3221f712c73afb30c	50	2026-10-30 15:05:26.235198+00
78478f09d4cd6989277738a4566c2079	51	2026-10-30 15:05:26.235198+00
\.


--
-- Name: log_id_seq; Type: SEQUENCE SET; Schema: audit; Owner: -
--

SELECT pg_catalog.setval('audit.log_id_seq', 240, true);


--
-- Name: invoices_id_seq; Type: SEQUENCE SET; Schema: billing; Owner: -
--

SELECT pg_catalog.setval('billing.invoices_id_seq', 300, true);


--
-- Name: payments_id_seq; Type: SEQUENCE SET; Schema: billing; Owner: -
--

SELECT pg_catalog.setval('billing.payments_id_seq', 300, true);


--
-- Name: refunds_id_seq; Type: SEQUENCE SET; Schema: billing; Owner: -
--

SELECT pg_catalog.setval('billing.refunds_id_seq', 12, true);


--
-- Name: categories_id_seq; Type: SEQUENCE SET; Schema: catalog; Owner: -
--

SELECT pg_catalog.setval('catalog.categories_id_seq', 9, true);


--
-- Name: products_id_seq; Type: SEQUENCE SET; Schema: catalog; Owner: -
--

SELECT pg_catalog.setval('catalog.products_id_seq', 120, true);


--
-- Name: employees_id_seq; Type: SEQUENCE SET; Schema: hr; Owner: -
--

SELECT pg_catalog.setval('hr.employees_id_seq', 15, true);


--
-- Name: movements_id_seq; Type: SEQUENCE SET; Schema: inventory; Owner: -
--

SELECT pg_catalog.setval('inventory.movements_id_seq', 2000, true);


--
-- Name: stores_id_seq; Type: SEQUENCE SET; Schema: inventory; Owner: -
--

SELECT pg_catalog.setval('inventory.stores_id_seq', 5, true);


--
-- Name: customers_id_seq; Type: SEQUENCE SET; Schema: sales; Owner: -
--

SELECT pg_catalog.setval('sales.customers_id_seq', 200, true);


--
-- Name: order_number_seq; Type: SEQUENCE SET; Schema: sales; Owner: -
--

SELECT pg_catalog.setval('sales.order_number_seq', 1619, true);


--
-- Name: orders_id_seq; Type: SEQUENCE SET; Schema: sales; Owner: -
--

SELECT pg_catalog.setval('sales.orders_id_seq', 620, true);


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
-- Name: best_sellers; Type: MATERIALIZED VIEW DATA; Schema: catalog; Owner: -
--

REFRESH MATERIALIZED VIEW catalog.best_sellers;


--
-- Name: stock_by_region; Type: MATERIALIZED VIEW DATA; Schema: inventory; Owner: -
--

REFRESH MATERIALIZED VIEW inventory.stock_by_region;


--
-- PostgreSQL database dump complete
--

\unrestrict p3E6d0wMzjUEsb9juymz1hVuePOU7ZQZsuJPe1MB4ZuKXycxouMGo5fYcrji7Ms

