-- Step 2: customers and their orders.
CREATE TABLE customers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    email text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE customers IS 'People who buy at the shop.';
CREATE TABLE orders (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers (id),
    status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'placed', 'paid', 'shipped', 'cancelled')),
    placed_at timestamptz,
    total numeric(12, 2) NOT NULL DEFAULT 0
);
COMMENT ON TABLE orders IS 'An order of a customer.';
CREATE TABLE order_items (
    order_id bigint NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    line smallint NOT NULL,
    product_id integer NOT NULL REFERENCES products (id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line)
);
COMMENT ON TABLE order_items IS 'The lines of an order.';
