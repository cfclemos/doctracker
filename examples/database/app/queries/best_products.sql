-- The products that sold the most, with how much they brought in.
SELECT p.id, p.name, SUM(i.quantity) AS sold, SUM(i.quantity * i.unit_price) AS revenue
FROM products p
JOIN order_items i ON i.product_id = p.id
JOIN orders o ON o.id = i.order_id
WHERE o.status IN ('paid', 'shipped')
GROUP BY p.id, p.name
ORDER BY revenue DESC;

-- The customers who never ordered.
SELECT c.full_name, c.email
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.id IS NULL;
