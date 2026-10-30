DROP INDEX orders_customer;
ALTER TABLE customers RENAME COLUMN full_name TO name;
ALTER TABLE products ADD COLUMN description text;
