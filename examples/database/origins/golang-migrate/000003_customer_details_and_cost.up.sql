-- Step 3: more about customers, and the cost of each product.
ALTER TABLE customers ADD COLUMN cpf char(14) UNIQUE;
ALTER TABLE customers ADD COLUMN phone text;
ALTER TABLE products ADD COLUMN cost numeric(12, 2);
