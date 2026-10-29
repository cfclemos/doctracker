-- The customers of the shop.
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL
);

-- The orders, each made by one customer.
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers (id),
    total_cents INTEGER NOT NULL
);

-- What each customer spent.
CREATE VIEW customer_totals AS
SELECT customers.name, SUM(orders.total_cents) AS spent
FROM customers JOIN orders ON orders.customer_id = customers.id
GROUP BY customers.name;
