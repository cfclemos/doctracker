-- Step 5: a destructive change, a rename and an index (what a migration lint must flag).
ALTER TABLE products DROP COLUMN description;
ALTER TABLE customers RENAME COLUMN name TO full_name;
CREATE INDEX orders_customer ON orders (customer_id);
