-- Seed data, the same at every start.
USE acme;
SET @@cte_max_recursion_depth = 5000;

INSERT INTO categories (parent_id, name, slug) VALUES (NULL, 'Electronics', 'electronics'), (NULL, 'Home', 'home'), (NULL, 'Books', 'books');
INSERT INTO categories (parent_id, name, slug) VALUES (1, 'Audio', 'audio'), (2, 'Kitchen', 'kitchen'), (3, 'Novels', 'novels');

INSERT INTO products (sku, name, description, category_id, price, cost, attributes)
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 120)
SELECT CONCAT('SKU-', LPAD(i, 5, '0')), CONCAT(ELT(1 + i % 4, 'Lamp', 'Kettle', 'Novel', 'Headphones'), ' ', i),
       CONCAT('Product number ', i), 1 + i % 6, 10 + (i * 37) % 490, ROUND((10 + (i * 37) % 490) * 0.6, 2),
       JSON_OBJECT('colour', ELT(1 + i % 3, 'red', 'blue', 'black'), 'weight_g', 100 + i * 7)
FROM n;

INSERT INTO customers (name, email, cpf, phone, password_hash, birth_date)
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 200)
SELECT CONCAT('Customer ', i), CONCAT('customer', i, '@mail.example'),
       CONCAT(LPAD(i * 7919 % 1000, 3, '0'), '.', LPAD(i * 104729 % 1000, 3, '0'), '.', LPAD(i * 1299709 % 1000, 3, '0'), '-', LPAD(i % 100, 2, '0')),
       CONCAT('+55 11 9', LPAD(10000000 + i * 7331 % 89999999, 8, '0')),
       CONCAT('$2b$04$', LPAD(SHA2(CONCAT('secret', i), 256), 53, 'x')),
       DATE_ADD('1960-01-01', INTERVAL (i * 97) % 15000 DAY)
FROM n;
UPDATE customers SET referred_by = id - 1 WHERE id % 5 = 0;

INSERT INTO orders (customer_id, status, placed_at)
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 600)
SELECT 1 + (i * 13) % 200, ELT(1 + i % 4, 'placed', 'paid', 'shipped', 'cancelled'), TIMESTAMP('2025-01-01') + INTERVAL (i * 13) HOUR
FROM n;

-- Built apart first: the items' trigger updates orders, which a statement inserting the items cannot read.
CREATE TEMPORARY TABLE new_items AS
SELECT o.id AS order_id, l.line, p.id AS product_id, 1 + (o.id + l.line) % 4 AS quantity, p.price AS unit_price
FROM orders o
JOIN (SELECT 1 AS line UNION ALL SELECT 2 UNION ALL SELECT 3) l ON l.line <= 1 + o.id % 3
JOIN products p ON p.id = 1 + (o.id * 31 + l.line * 7) % 120;
INSERT INTO order_items (order_id, line, product_id, quantity, unit_price) SELECT * FROM new_items;
DROP TEMPORARY TABLE new_items;

INSERT INTO payments (order_id, paid_at, amount, method)
SELECT id, placed_at + INTERVAL 1 DAY, total, ELT(1 + id % 3, 'pix', 'card', 'boleto') FROM orders WHERE status IN ('paid', 'shipped') AND total > 0;

INSERT INTO stock_movements (product_id, moved_at, quantity)
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 2000)
SELECT 1 + i % 120, DATE_ADD('2025-06-01', INTERVAL (i DIV 5) DAY), IF(i % 3 = 0, -2, 10) FROM n;

INSERT INTO imported_orders (external_ref, customer_id, product_id, quantity, raw)
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 300)
SELECT CONCAT('MKT-', i), IF(i % 10 = 0, 9000 + i, 1 + i % 200), 1 + i % 120, 1 + i % 3, JSON_OBJECT('n', i) FROM n;
ANALYZE TABLE categories, products, customers, orders, order_items, payments, stock_movements, imported_orders;
