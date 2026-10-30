"""Build the acme shop as an SQLite file: tables (one STRICT), keys, checks, generated columns, views,
triggers and a full-text (FTS5) virtual table.

SQLite has no server, so it is not in compose.yaml: run `python sqlite/build.py` from this folder and
it writes `sqlite/acme.sqlite` (kept out of git), from scratch every time.
"""

import random
import sqlite3
from pathlib import Path

DATABASE = Path(__file__).with_name("acme.sqlite")
"""The file written."""

SCHEMA = """
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    parent_id INTEGER REFERENCES categories (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE
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
CREATE INDEX products_active_category ON products (category_id) WHERE active = 1;
CREATE INDEX products_lower_name ON products (lower(name));
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    cpf TEXT UNIQUE CHECK (cpf GLOB '[0-9][0-9][0-9].[0-9][0-9][0-9].[0-9][0-9][0-9]-[0-9][0-9]'),
    phone TEXT,
    password_hash TEXT NOT NULL,
    referred_by INTEGER REFERENCES customers (id) ON DELETE SET NULL
);
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'placed', 'paid', 'shipped', 'cancelled')),
    placed_at TEXT,
    total NUMERIC NOT NULL DEFAULT 0
);
CREATE INDEX orders_customer ON orders (customer_id);
CREATE TABLE order_items (
    order_id INTEGER NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    line INTEGER NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products (id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC NOT NULL,
    PRIMARY KEY (order_id, line)
) WITHOUT ROWID;
CREATE TABLE imported_orders (external_ref TEXT, customer_id INTEGER, product_id INTEGER, quantity INTEGER);
CREATE TABLE stores (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    region TEXT NOT NULL,
    name_upper TEXT GENERATED ALWAYS AS (upper(name)) VIRTUAL
) STRICT;
CREATE VIRTUAL TABLE products_search USING fts5 (name, content = 'products', content_rowid = 'id');
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
"""
"""The tables, indexes, triggers and views."""


def build(path: Path = DATABASE) -> None:
    """Write the database from scratch, with the same seed data every time.

    Args:
        path: The SQLite file to write; replaced when it exists.
    """
    path.unlink(missing_ok=True)
    rng = random.Random(42)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO categories (parent_id, name, slug) VALUES (?, ?, ?)",
                       [(None, "Electronics", "electronics"), (None, "Home", "home"), (1, "Audio", "audio")])
        db.executemany("INSERT INTO products (sku, name, category_id, price, cost, attributes) VALUES (?, ?, ?, ?, ?, ?)",
                       [(f"SKU-{n:05}", f"Product {n}", 1 + n % 3, price := round(10 + rng.random() * 490, 2),
                         round(price * 0.6, 2), f'{{"n": {n}}}') for n in range(1, 121)])
        db.executemany("INSERT INTO customers (name, email, cpf, phone, password_hash) VALUES (?, ?, ?, ?, ?)",
                       [(f"Customer {n}", f"customer{n}@mail.example",
                         f"{n * 7919 % 1000:03}.{n * 104729 % 1000:03}.{n * 1299709 % 1000:03}-{n % 100:02}",
                         f"+55 11 9{10000000 + n * 7331 % 89999999}", "$2b$04$" + "x" * 53) for n in range(1, 201)])
        db.executemany("INSERT INTO orders (customer_id, status, placed_at) VALUES (?, ?, ?)",
                       [(1 + n * 13 % 200, ("placed", "paid", "shipped", "cancelled")[n % 4], f"2025-01-{1 + n % 28:02}")
                        for n in range(1, 601)])
        db.execute("""INSERT INTO order_items (order_id, line, product_id, quantity, unit_price)
                      SELECT o.id, l.line, p.id, 1 + (o.id + l.line) % 4, p.price
                      FROM orders o JOIN (SELECT 1 AS line UNION ALL SELECT 2 UNION ALL SELECT 3) l ON l.line <= 1 + o.id % 3
                      JOIN products p ON p.id = 1 + (o.id * 31 + l.line * 7) % 120""")
        db.executemany("INSERT INTO stores (name, region) VALUES (?, ?)", [("Centro", "south"), ("Boa Viagem", "east")])
        db.execute("INSERT INTO products_search (products_search) VALUES ('rebuild')")
        db.executemany("INSERT INTO imported_orders VALUES (?, ?, ?, ?)",
                       [(f"MKT-{n}", 9000 + n if n % 10 == 0 else 1 + n % 200, 1 + n % 120, 1 + n % 3) for n in range(1, 301)])


if __name__ == "__main__":
    build()
    print(f"Written {DATABASE}")
