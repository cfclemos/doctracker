-- Seed data, random but the same at every start (setseed): enough to sample values per column and
-- to find relations through the data (staging.imported_orders.customer_id matches sales.customers.id).
\set ON_ERROR_STOP on
SELECT setseed(0.42);

INSERT INTO catalog.categories (parent_id, name, slug) VALUES
    (NULL, 'Electronics', 'electronics'), (NULL, 'Home', 'home'), (NULL, 'Books', 'books');
INSERT INTO catalog.categories (parent_id, name, slug)
SELECT c.id, c.name || ' ' || sub, c.slug || '-' || lower(sub)
FROM catalog.categories c CROSS JOIN (VALUES ('Basics'), ('Premium')) AS s (sub);

INSERT INTO catalog.products (sku, name, description, category_id, price, cost, tags, attributes)
SELECT 'SKU-' || lpad(n::text, 5, '0'),
       (ARRAY['Lamp', 'Kettle', 'Novel', 'Headphones', 'Mug', 'Charger', 'Atlas', 'Blanket'])[1 + n % 8] || ' ' || n,
       'Product number ' || n,
       1 + (n % 9),
       round((10 + random() * 490)::numeric, 2) AS price,
       NULL,
       ARRAY[(ARRAY['new', 'sale', 'gift', 'eco'])[1 + n % 4]],
       jsonb_build_object('colour', (ARRAY['red', 'blue', 'black', 'white'])[1 + n % 4], 'weight_g', 100 + n * 7)
FROM generate_series(1, 120) AS n;
UPDATE catalog.products SET cost = round(price * (0.4 + random() * 0.4)::numeric, 2);

INSERT INTO catalog.price_history (product_id, valid_during, price)
SELECT id, tstzrange('2025-01-01', '2025-07-01'), round(price * 0.9, 2) FROM catalog.products
UNION ALL
SELECT id, tstzrange('2025-07-01', NULL), price FROM catalog.products;

INSERT INTO hr.employees (name, email, manager_id, hired_on, salary)
VALUES ('Ana Lima', 'ana@acme.example', NULL, '2019-03-01', 18000);
INSERT INTO hr.employees (name, email, manager_id, hired_on, salary)
SELECT 'Employee ' || n, 'employee' || n || '@acme.example', 1, date '2020-01-01' + n * 17, round((3000 + random() * 9000)::numeric, 2)
FROM generate_series(1, 14) AS n;

INSERT INTO sales.customers (name, email, cpf, phone, password_hash, birth_date, address)
SELECT 'Customer ' || n,
       'customer' || n || '@mail.example',
       lpad((n * 7919 % 1000)::text, 3, '0') || '.' || lpad((n * 104729 % 1000)::text, 3, '0') || '.'
           || lpad((n * 1299709 % 1000)::text, 3, '0') || '-' || lpad((n % 100)::text, 2, '0'),
       '+55 11 9' || lpad((10000000 + n * 7331 % 89999999)::text, 8, '0'),
       crypt('secret' || n, gen_salt('bf', 4)),
       date '1960-01-01' + (random() * 15000)::int,
       ROW('Rua ' || n, n::text, (ARRAY['São Paulo', 'Recife', 'Curitiba', 'Belém'])[1 + n % 4],
           (ARRAY['SP', 'PE', 'PR', 'PA'])[1 + n % 4], lpad((n * 37 % 100000)::text, 5, '0') || '-000')::sales.address
FROM generate_series(1, 200) AS n;
UPDATE sales.customers SET referred_by = id - 1 WHERE id % 5 = 0;

INSERT INTO sales.orders (customer_id, sold_by, status, placed_at, shipping_address)
SELECT 1 + (n * 13) % 200, 2 + n % 14,
       (ARRAY['placed', 'paid', 'shipped', 'cancelled'])[1 + n % 4]::sales.order_status,
       timestamptz '2025-01-01' + n * interval '13 hours', NULL
FROM generate_series(1, 600) AS n;
INSERT INTO sales.orders (customer_id, status) SELECT 1 + n, 'draft' FROM generate_series(1, 20) AS n;

INSERT INTO sales.order_items (order_id, line, product_id, quantity, unit_price)
SELECT o.id, l, 1 + (o.id * 31 + l * 7) % 120, 1 + (o.id + l) % 4, p.price
FROM sales.orders o
CROSS JOIN generate_series(1, 3) AS l
JOIN catalog.products p ON p.id = 1 + (o.id * 31 + l * 7) % 120
WHERE l <= 1 + o.id % 3;

INSERT INTO billing.invoices (order_id, amount, access_key)
SELECT id, total, lpad((id * 982451653)::text, 44, '3') FROM sales.orders WHERE status IN ('paid', 'shipped');
INSERT INTO billing.payments (invoice_id, paid_at, amount, method, card_last4)
SELECT id, issued_on + interval '1 day', amount * CASE WHEN id % 7 = 0 THEN 0.5 ELSE 1 END,
       (ARRAY['pix', 'card', 'boleto'])[1 + id % 3], CASE WHEN id % 3 = 1 THEN lpad((id * 37 % 10000)::text, 4, '0') END
FROM billing.invoices;
INSERT INTO billing.refunds (order_id, line, amount, reason)
SELECT order_id, line, unit_price, 'Arrived broken' FROM sales.order_items WHERE order_id % 50 = 0 AND line = 1;

INSERT INTO inventory.stores (name, region) VALUES
    ('Centro', 'south'), ('Boa Viagem', 'east'), ('Batel', 'south'), ('Nazaré', 'north'), ('Online', 'west');
INSERT INTO inventory.movements (store_id, product_id, moved_at, quantity)
SELECT 1 + n % 5, 1 + n % 120, timestamptz '2025-06-01' + n * interval '5 hours', CASE WHEN n % 3 = 0 THEN -2 ELSE 10 END
FROM generate_series(1, 2000) AS n;

INSERT INTO staging.imported_orders (external_ref, customer_id, product_id, quantity, raw)
SELECT 'MKT-' || n, CASE WHEN n % 10 = 0 THEN 9000 + n ELSE 1 + n % 200 END, 1 + n % 120, 1 + n % 3,
       jsonb_build_object('marketplace', 'acme-mkt', 'n', n)
FROM generate_series(1, 300) AS n;
INSERT INTO staging.session_cache (token, customer_id, expires_at)
SELECT encode(gen_random_bytes(16), 'hex'), 1 + n % 200, now() + interval '1 hour' FROM generate_series(1, 50) AS n;

REFRESH MATERIALIZED VIEW catalog.best_sellers;
REFRESH MATERIALIZED VIEW inventory.stock_by_region;
ANALYZE;
