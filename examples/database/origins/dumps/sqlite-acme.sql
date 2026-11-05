BEGIN TRANSACTION;
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES categories (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE
);
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    cpf TEXT UNIQUE CHECK (cpf GLOB '[0-9][0-9][0-9].[0-9][0-9][0-9].[0-9][0-9][0-9]-[0-9][0-9]'),
    phone TEXT,
    password_hash TEXT NOT NULL,
    referred_by INTEGER REFERENCES customers (id) ON DELETE SET NULL
);
CREATE TABLE imported_orders (external_ref TEXT, customer_id INTEGER, product_id INTEGER, quantity INTEGER);
CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products (id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC NOT NULL,
    PRIMARY KEY (order_id, line)
) WITHOUT ROWID;
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'placed', 'paid', 'shipped', 'cancelled')),
    placed_at TEXT,
    total NUMERIC NOT NULL DEFAULT 0
);
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories (id),
    price NUMERIC NOT NULL CHECK (price >= 0),
    cost NUMERIC CHECK (cost IS NULL OR cost <= price),
    margin NUMERIC GENERATED ALWAYS AS (price - coalesce(cost, 0)) STORED,
    attributes TEXT CHECK (json_valid(attributes)),
    active INTEGER NOT NULL DEFAULT 1
);
PRAGMA writable_schema=ON;
INSERT INTO sqlite_master(type,name,tbl_name,rootpage,sql)VALUES('table','products_search','products_search',0,'CREATE VIRTUAL TABLE products_search USING fts5 (name, content = ''products'', content_rowid = ''id'')');
CREATE TABLE 'products_search_config'(k PRIMARY KEY, v) WITHOUT ROWID;
CREATE TABLE 'products_search_data'(id INTEGER PRIMARY KEY, block BLOB);
CREATE TABLE 'products_search_docsize'(id INTEGER PRIMARY KEY, sz BLOB);
CREATE TABLE 'products_search_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;
CREATE TABLE stores (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    name_upper TEXT GENERATED ALWAYS AS (upper(name)) VIRTUAL
) STRICT;
CREATE INDEX products_active_category ON products (category_id) WHERE active = 1;
CREATE INDEX products_lower_name ON products (lower(name));
CREATE INDEX orders_customer ON orders (customer_id);
CREATE TRIGGER items_total_insert AFTER INSERT ON order_items
BEGIN
    UPDATE orders SET total = total + NEW.quantity * NEW.unit_price WHERE id = NEW.order_id;
END;
CREATE TRIGGER items_total_delete AFTER DELETE ON order_items
BEGIN
    UPDATE orders SET total = total - OLD.quantity * OLD.unit_price WHERE id = OLD.order_id;
END;
CREATE VIEW order_summary AS
SELECT o.id, c.name AS customer, o.status, o.total, count(i.line) AS line_count
FROM orders o JOIN customers c ON c.id = o.customer_id LEFT JOIN order_items i ON i.order_id = o.id
GROUP BY o.id;
CREATE VIEW customers_in_debt AS
SELECT customer, sum(total) AS due FROM order_summary WHERE status = 'placed' GROUP BY customer;
PRAGMA writable_schema=OFF;
COMMIT;
