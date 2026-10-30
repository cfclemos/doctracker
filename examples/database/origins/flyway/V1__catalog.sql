-- Step 1: what the shop sells.
CREATE TABLE categories (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    parent_id integer REFERENCES categories (id) ON DELETE CASCADE,
    name text NOT NULL,
    slug text NOT NULL UNIQUE
);
COMMENT ON TABLE categories IS 'Categories of products, as a tree.';
CREATE TABLE products (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    name text NOT NULL,
    description text,
    category_id integer NOT NULL REFERENCES categories (id),
    price numeric(12, 2) NOT NULL CHECK (price >= 0),
    active boolean NOT NULL DEFAULT true
);
COMMENT ON TABLE products IS 'What the shop sells.';
