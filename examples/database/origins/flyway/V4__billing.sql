-- Step 4: payments of the orders.
CREATE TABLE payments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    paid_at timestamptz NOT NULL,
    amount numeric(12, 2) NOT NULL CHECK (amount > 0),
    method text NOT NULL CHECK (method IN ('pix', 'card', 'boleto'))
);
COMMENT ON TABLE payments IS 'Money received for an order.';
