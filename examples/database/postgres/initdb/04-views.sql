-- Views, a view of views and materialized views.
\set ON_ERROR_STOP on

CREATE VIEW sales.order_summary AS
SELECT o.id, o.number, c.name AS customer, o.status, o.placed_at, o.total, count(i.line) AS lines
FROM sales.orders o
JOIN sales.customers c ON c.id = o.customer_id
LEFT JOIN sales.order_items i ON i.order_id = o.id
GROUP BY o.id, c.name;
COMMENT ON VIEW sales.order_summary IS 'Each order with its customer and how many lines it has.';

CREATE VIEW billing.open_invoices AS
SELECT inv.id, inv.order_id, inv.amount, inv.amount - coalesce(sum(p.amount), 0) AS due
FROM billing.invoices inv
LEFT JOIN billing.payments p ON p.invoice_id = inv.id
GROUP BY inv.id
HAVING inv.amount - coalesce(sum(p.amount), 0) > 0;
COMMENT ON VIEW billing.open_invoices IS 'Invoices not fully paid, with what is still due.';

-- A view built on other views.
CREATE VIEW sales.customers_in_debt AS
SELECT s.customer, sum(oi.due) AS due
FROM sales.order_summary s
JOIN billing.open_invoices oi ON oi.order_id = s.id
GROUP BY s.customer;
COMMENT ON VIEW sales.customers_in_debt IS 'Customers with invoices still to pay (a view of two views).';

CREATE MATERIALIZED VIEW catalog.best_sellers AS
SELECT p.id, p.name, sum(i.quantity) AS sold, sum(i.quantity * i.unit_price) AS revenue
FROM catalog.products p
JOIN sales.order_items i ON i.product_id = p.id
GROUP BY p.id, p.name
WITH NO DATA;
COMMENT ON MATERIALIZED VIEW catalog.best_sellers IS 'Products by units sold; refreshed every night.';
CREATE UNIQUE INDEX best_sellers_id ON catalog.best_sellers (id);

CREATE MATERIALIZED VIEW inventory.stock_by_region AS
SELECT region, product_id, sum(quantity) AS quantity FROM inventory.stock GROUP BY region, product_id
WITH NO DATA;
COMMENT ON MATERIALIZED VIEW inventory.stock_by_region IS 'Units of each product per region.';
