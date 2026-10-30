--
-- PostgreSQL database dump
--

\restrict I2LGEix8F3H0oGcHqrzje8KB1s8ulocCT4RMdb4TvmmTaPS1EF2X5i0Pu47YW8G

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
-- Name: logistics; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA logistics;


--
-- Name: SCHEMA logistics; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA logistics IS 'Shipments leaving the warehouse.';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: carriers; Type: TABLE; Schema: logistics; Owner: -
--

CREATE TABLE logistics.carriers (
    id smallint NOT NULL,
    name text NOT NULL
);


--
-- Name: TABLE carriers; Type: COMMENT; Schema: logistics; Owner: -
--

COMMENT ON TABLE logistics.carriers IS 'Companies that carry the parcels.';


--
-- Name: carriers_id_seq; Type: SEQUENCE; Schema: logistics; Owner: -
--

ALTER TABLE logistics.carriers ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME logistics.carriers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: shipments; Type: TABLE; Schema: logistics; Owner: -
--

CREATE TABLE logistics.shipments (
    id bigint NOT NULL,
    order_id bigint NOT NULL,
    carrier_id smallint NOT NULL,
    tracking_code text,
    shipped_at timestamp with time zone NOT NULL
);


--
-- Name: TABLE shipments; Type: COMMENT; Schema: logistics; Owner: -
--

COMMENT ON TABLE logistics.shipments IS 'A parcel sent for an order of the shop (order_id refers to acme.sales.orders, another database).';


--
-- Name: shipments_id_seq; Type: SEQUENCE; Schema: logistics; Owner: -
--

ALTER TABLE logistics.shipments ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME logistics.shipments_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: carriers carriers_name_key; Type: CONSTRAINT; Schema: logistics; Owner: -
--

ALTER TABLE ONLY logistics.carriers
    ADD CONSTRAINT carriers_name_key UNIQUE (name);


--
-- Name: carriers carriers_pkey; Type: CONSTRAINT; Schema: logistics; Owner: -
--

ALTER TABLE ONLY logistics.carriers
    ADD CONSTRAINT carriers_pkey PRIMARY KEY (id);


--
-- Name: shipments shipments_pkey; Type: CONSTRAINT; Schema: logistics; Owner: -
--

ALTER TABLE ONLY logistics.shipments
    ADD CONSTRAINT shipments_pkey PRIMARY KEY (id);


--
-- Name: shipments shipments_tracking_code_key; Type: CONSTRAINT; Schema: logistics; Owner: -
--

ALTER TABLE ONLY logistics.shipments
    ADD CONSTRAINT shipments_tracking_code_key UNIQUE (tracking_code);


--
-- Name: shipments shipments_carrier_id_fkey; Type: FK CONSTRAINT; Schema: logistics; Owner: -
--

ALTER TABLE ONLY logistics.shipments
    ADD CONSTRAINT shipments_carrier_id_fkey FOREIGN KEY (carrier_id) REFERENCES logistics.carriers(id);


--
-- PostgreSQL database dump complete
--

\unrestrict I2LGEix8F3H0oGcHqrzje8KB1s8ulocCT4RMdb4TvmmTaPS1EF2X5i0Pu47YW8G

