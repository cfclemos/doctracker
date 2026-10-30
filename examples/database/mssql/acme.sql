-- The acme shop on SQL Server: schemas, keys, checks, computed columns, sequences, filtered indexes,
-- views, functions, procedures, triggers, a synonym and descriptions (MS_Description). Run by the
-- mssql-init service with sqlcmd, only while the database acme does not exist yet; the reader's
-- password comes from the environment as an sqlcmd variable.
CREATE DATABASE acme;
GO
USE acme;
GO
CREATE SCHEMA catalog;
GO
CREATE SCHEMA sales;
GO
CREATE SCHEMA staging;
GO
CREATE SEQUENCE sales.order_number_seq AS int START WITH 1000;
GO
CREATE TABLE catalog.categories (
    id int IDENTITY PRIMARY KEY,
    parent_id int NULL REFERENCES catalog.categories (id),
    name nvarchar(100) NOT NULL,
    slug varchar(100) NOT NULL UNIQUE
);
CREATE TABLE catalog.products (
    id int IDENTITY PRIMARY KEY,
    sku varchar(20) NOT NULL CONSTRAINT products_sku_key UNIQUE,
    name nvarchar(200) NOT NULL,
    category_id int NOT NULL REFERENCES catalog.categories (id),
    price decimal(12, 2) NOT NULL CHECK (price >= 0),
    cost decimal(12, 2) NULL,
    margin AS (price - ISNULL(cost, 0)) PERSISTED,
    attributes nvarchar(max) NULL CHECK (ISJSON(attributes) = 1),
    active bit NOT NULL DEFAULT 1,
    CONSTRAINT products_cost_below_price CHECK (cost IS NULL OR cost <= price)
);
CREATE INDEX products_active_category ON catalog.products (category_id) WHERE active = 1;
CREATE TABLE sales.customers (
    id bigint IDENTITY PRIMARY KEY,
    name nvarchar(200) NOT NULL,
    email varchar(200) NOT NULL UNIQUE,
    cpf char(14) NULL UNIQUE,
    phone varchar(30) NULL,
    password_hash char(60) NOT NULL,
    referred_by bigint NULL REFERENCES sales.customers (id)
);
CREATE TABLE sales.orders (
    id bigint IDENTITY PRIMARY KEY,
    number int NOT NULL DEFAULT (NEXT VALUE FOR sales.order_number_seq) UNIQUE,
    customer_id bigint NOT NULL REFERENCES sales.customers (id),
    status varchar(10) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'placed', 'paid', 'shipped', 'cancelled')),
    placed_at datetime2 NULL,
    total decimal(12, 2) NOT NULL DEFAULT 0
);
CREATE TABLE sales.order_items (
    order_id bigint NOT NULL REFERENCES sales.orders (id) ON DELETE CASCADE,
    line smallint NOT NULL,
    product_id int NOT NULL REFERENCES catalog.products (id),
    quantity int NOT NULL CHECK (quantity > 0),
    unit_price decimal(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line)
);
CREATE TABLE staging.imported_orders (
    external_ref varchar(40) NULL,
    customer_id bigint NULL,
    product_id int NULL,
    quantity int NULL
);
GO
CREATE SYNONYM sales.items FOR sales.order_items;
GO
CREATE VIEW sales.order_summary AS
SELECT o.id, o.number, c.name AS customer, o.status, o.total, COUNT(i.line) AS line_count
FROM sales.orders o JOIN sales.customers c ON c.id = o.customer_id LEFT JOIN sales.order_items i ON i.order_id = o.id
GROUP BY o.id, o.number, c.name, o.status, o.total;
GO
CREATE FUNCTION catalog.final_price (@base decimal(12, 2), @discount decimal(5, 4)) RETURNS decimal(12, 2)
AS BEGIN RETURN ROUND(@base * (1 - @discount), 2) END;
GO
CREATE FUNCTION sales.orders_of (@customer bigint) RETURNS TABLE
AS RETURN SELECT id, number, status, total FROM sales.orders WHERE customer_id = @customer;
GO
CREATE PROCEDURE sales.cancel_stale_drafts @older_than_days int = 30
AS UPDATE sales.orders SET status = 'cancelled'
   WHERE status = 'draft' AND ISNULL(placed_at, DATEADD(day, -(@older_than_days + 1), SYSDATETIME())) < DATEADD(day, -@older_than_days, SYSDATETIME());
GO
CREATE TRIGGER sales.order_items_total ON sales.order_items AFTER INSERT, UPDATE, DELETE
AS UPDATE o SET total = (SELECT ISNULL(SUM(i.quantity * i.unit_price), 0) FROM sales.order_items i WHERE i.order_id = o.id)
   FROM sales.orders o WHERE o.id IN (SELECT order_id FROM inserted UNION SELECT order_id FROM deleted);
GO
EXEC sp_addextendedproperty 'MS_Description', 'People who buy at the shop.', 'SCHEMA', 'sales', 'TABLE', 'customers';
EXEC sp_addextendedproperty 'MS_Description', 'bcrypt hash of the password.', 'SCHEMA', 'sales', 'TABLE', 'customers', 'COLUMN', 'password_hash';
EXEC sp_addextendedproperty 'MS_Description', 'What the shop sells.', 'SCHEMA', 'catalog', 'TABLE', 'products';
EXEC sp_addextendedproperty 'MS_Description', 'An order of a customer.', 'SCHEMA', 'sales', 'TABLE', 'orders';
GO
-- Seed data.
INSERT INTO catalog.categories (parent_id, name, slug) VALUES (NULL, N'Electronics', 'electronics'), (NULL, N'Home', 'home'), (1, N'Audio', 'audio');
INSERT INTO catalog.products (sku, name, category_id, price, cost, attributes)
SELECT CONCAT('SKU-', RIGHT(CONCAT('00000', n), 5)), CONCAT(N'Product ', n), 1 + n % 3, 10 + (n * 37) % 490, ROUND((10 + (n * 37) % 490) * 0.6, 2), CONCAT('{"n":', n, '}')
FROM (SELECT TOP 120 ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n FROM sys.all_objects) AS s;
INSERT INTO sales.customers (name, email, cpf, phone, password_hash)
SELECT CONCAT(N'Customer ', n), CONCAT('customer', n, '@mail.example'),
       CONCAT(RIGHT(CONCAT('000', n * 7919 % 1000), 3), '.', RIGHT(CONCAT('000', n * 104729 % 1000), 3), '.', RIGHT(CONCAT('000', n * 1299709 % 1000), 3), '-', RIGHT(CONCAT('00', n % 100), 2)),
       CONCAT('+55 11 9', 10000000 + n * 7331 % 89999999), CONCAT('$2b$04$', REPLICATE('x', 53))
FROM (SELECT TOP 200 ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n FROM sys.all_objects) AS s;
INSERT INTO sales.orders (customer_id, status, placed_at)
SELECT 1 + (n * 13) % 200, CHOOSE(1 + n % 4, 'placed', 'paid', 'shipped', 'cancelled'), DATEADD(hour, n * 13, '2025-01-01')
FROM (SELECT TOP 600 ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n FROM sys.all_objects a CROSS JOIN sys.all_objects b) AS s;
INSERT INTO sales.order_items (order_id, line, product_id, quantity, unit_price)
SELECT o.id, l.line, p.id, 1 + (o.id + l.line) % 4, p.price
FROM sales.orders o
JOIN (VALUES (1), (2), (3)) AS l (line) ON l.line <= 1 + o.id % 3
JOIN catalog.products p ON p.id = 1 + (o.id * 31 + l.line * 7) % 120;
INSERT INTO staging.imported_orders (external_ref, customer_id, product_id, quantity)
SELECT CONCAT('MKT-', n), IIF(n % 10 = 0, 9000 + n, 1 + n % 200), 1 + n % 120, 1 + n % 3
FROM (SELECT TOP 300 ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS n FROM sys.all_objects) AS s;
GO
-- The rest of what SQL Server describes: types of our own, a system-versioned (temporal) table, an
-- indexed view, a columnstore index, partitioning, row-level security, a view with a check option.
CREATE TYPE sales.cpf FROM char(14) NOT NULL;
GO
CREATE TYPE sales.order_lines AS TABLE (product_id int NOT NULL, quantity int NOT NULL);
GO
CREATE TABLE catalog.price_history (
    product_id int NOT NULL PRIMARY KEY REFERENCES catalog.products (id),
    price decimal(12, 2) NOT NULL,
    valid_from datetime2 GENERATED ALWAYS AS ROW START NOT NULL,
    valid_to datetime2 GENERATED ALWAYS AS ROW END NOT NULL,
    PERIOD FOR SYSTEM_TIME (valid_from, valid_to)
) WITH (SYSTEM_VERSIONING = ON (HISTORY_TABLE = catalog.price_history_log));
GO
CREATE VIEW sales.revenue_by_product WITH SCHEMABINDING AS
SELECT i.product_id, SUM(i.quantity * i.unit_price) AS revenue, COUNT_BIG(*) AS lines
FROM sales.order_items i GROUP BY i.product_id;
GO
CREATE UNIQUE CLUSTERED INDEX revenue_by_product_key ON sales.revenue_by_product (product_id);
CREATE NONCLUSTERED COLUMNSTORE INDEX order_items_columnstore ON sales.order_items (product_id, quantity, unit_price);
GO
CREATE PARTITION FUNCTION by_year (date) AS RANGE RIGHT FOR VALUES ('2025-01-01', '2026-01-01');
CREATE PARTITION SCHEME by_year_scheme AS PARTITION by_year ALL TO ([PRIMARY]);
GO
CREATE TABLE sales.stock_movements (
    id bigint IDENTITY NOT NULL,
    product_id int NOT NULL,
    moved_on date NOT NULL,
    quantity int NOT NULL,
    CONSTRAINT stock_movements_key PRIMARY KEY (id, moved_on)
) ON by_year_scheme (moved_on);
GO
CREATE SCHEMA security;
GO
CREATE FUNCTION security.own_orders (@customer_id bigint) RETURNS TABLE WITH SCHEMABINDING
AS RETURN SELECT 1 AS allowed WHERE @customer_id = TRY_CAST(SESSION_CONTEXT(N'customer_id') AS bigint) OR SESSION_CONTEXT(N'customer_id') IS NULL;
GO
CREATE SECURITY POLICY security.orders_filter ADD FILTER PREDICATE security.own_orders(customer_id) ON sales.orders WITH (STATE = ON);
GO
CREATE VIEW catalog.active_products AS
SELECT id, sku, name, category_id, price FROM catalog.products WHERE active = 1
WITH CHECK OPTION;
GO
-- doctracker_reader: reads data and definitions, changes nothing.
CREATE LOGIN doctracker_reader WITH PASSWORD = '$(READER_PASSWORD)', CHECK_POLICY = OFF;
GO
CREATE USER doctracker_reader FOR LOGIN doctracker_reader;
ALTER ROLE db_datareader ADD MEMBER doctracker_reader;
GRANT VIEW DEFINITION TO doctracker_reader;
GO
