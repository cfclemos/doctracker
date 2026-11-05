-- Ship the orders paid this month and keep the totals up to date.
UPDATE orders SET status = 'shipped' WHERE status = 'paid' AND placed_at >= date_trunc('month', now());

UPDATE orders o SET total = (SELECT COALESCE(SUM(quantity * unit_price), 0) FROM order_items i WHERE i.order_id = o.id);

DELETE FROM payments WHERE order_id IN (SELECT id FROM orders WHERE status = 'cancelled');
