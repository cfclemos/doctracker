-- The acme shop on MySQL: tables, keys, checks, generated columns, enums, JSON, full-text and partial
-- indexes, partitions, views, functions, procedures, triggers and an event. Runs in database `acme`.
USE acme;

CREATE TABLE categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    parent_id INT NULL COMMENT 'The category above; none at the top.',
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    CONSTRAINT categories_parent FOREIGN KEY (parent_id) REFERENCES categories (id) ON DELETE CASCADE
) COMMENT = 'Categories of products, as a tree.';

CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    category_id INT NOT NULL,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    cost DECIMAL(12, 2) NULL,
    margin DECIMAL(12, 2) AS (price - COALESCE(cost, 0)) STORED COMMENT 'Price minus cost, worked out by the database.',
    attributes JSON NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT products_category FOREIGN KEY (category_id) REFERENCES categories (id) ON DELETE RESTRICT,
    CONSTRAINT products_cost_below_price CHECK (cost IS NULL OR cost <= price),
    FULLTEXT INDEX products_text (name, description)
) COMMENT = 'What the shop sells.';
CREATE INDEX products_lower_name ON products ((LOWER(name)));

CREATE TABLE customers (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(200) NOT NULL UNIQUE,
    cpf CHAR(14) UNIQUE COMMENT 'Brazilian taxpayer number, 000.000.000-00.',
    phone VARCHAR(30),
    password_hash CHAR(60) NOT NULL COMMENT 'bcrypt hash of the password.',
    birth_date DATE,
    referred_by BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT customers_referrer FOREIGN KEY (referred_by) REFERENCES customers (id) ON DELETE SET NULL,
    CONSTRAINT customers_cpf_format CHECK (cpf REGEXP '^[0-9]{3}\\.[0-9]{3}\\.[0-9]{3}-[0-9]{2}$')
) COMMENT = 'People who buy at the shop.';

CREATE TABLE orders (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status ENUM('draft', 'placed', 'paid', 'shipped', 'cancelled') NOT NULL DEFAULT 'draft',
    placed_at DATETIME NULL,
    total DECIMAL(12, 2) NOT NULL DEFAULT 0 COMMENT 'Sum of the items, kept by triggers.',
    CONSTRAINT orders_customer FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE RESTRICT
) COMMENT = 'An order of a customer.';

CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line SMALLINT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line),
    CONSTRAINT items_order FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE,
    CONSTRAINT items_product FOREIGN KEY (product_id) REFERENCES products (id)
) COMMENT = 'The lines of an order.';

CREATE TABLE payments (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    paid_at DATETIME NOT NULL,
    amount DECIMAL(12, 2) NOT NULL CHECK (amount > 0),
    method ENUM('pix', 'card', 'boleto') NOT NULL,
    CONSTRAINT payments_order FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE
) COMMENT = 'Money received for an order.';

-- Partitioned by range of years (partitioned tables cannot hold foreign keys in MySQL).
CREATE TABLE stock_movements (
    id BIGINT NOT NULL AUTO_INCREMENT,
    product_id INT NOT NULL,
    moved_at DATE NOT NULL,
    quantity INT NOT NULL,
    PRIMARY KEY (id, moved_at)
) COMMENT = 'Every change of stock, split by year.'
PARTITION BY RANGE (YEAR(moved_at)) (
    PARTITION p2025 VALUES LESS THAN (2026),
    PARTITION p2026 VALUES LESS THAN (2027),
    PARTITION pmax VALUES LESS THAN MAXVALUE
);

-- Loose on purpose: no primary key, ids not enforced.
CREATE TABLE imported_orders (
    external_ref VARCHAR(40),
    customer_id BIGINT,
    product_id INT,
    quantity INT,
    raw JSON
) COMMENT = 'Orders from the marketplace, before they are checked.';

CREATE TABLE audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    happened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    table_name VARCHAR(64) NOT NULL,
    action VARCHAR(10) NOT NULL,
    row_id BIGINT
) COMMENT = 'Every change written by the audit triggers.';

CREATE VIEW order_summary AS
SELECT o.id, c.name AS customer, o.status, o.placed_at, o.total, COUNT(i.line) AS line_count
FROM orders o JOIN customers c ON c.id = o.customer_id LEFT JOIN order_items i ON i.order_id = o.id
GROUP BY o.id, c.name, o.status, o.placed_at, o.total;

CREATE VIEW customers_in_debt AS
SELECT s.customer, SUM(s.total) AS due FROM order_summary s WHERE s.status = 'placed' GROUP BY s.customer;

DELIMITER //
CREATE FUNCTION final_price(base DECIMAL(12, 2), discount DECIMAL(5, 4)) RETURNS DECIMAL(12, 2)
    DETERMINISTIC COMMENT 'A price after a discount (0.1 = 10 %).'
BEGIN
    RETURN ROUND(base * (1 - discount), 2);
END//

CREATE PROCEDURE cancel_stale_drafts(IN older_than_days INT)
    COMMENT 'Cancels the drafts nobody touched for a while.'
BEGIN
    UPDATE orders SET status = 'cancelled'
    WHERE status = 'draft' AND COALESCE(placed_at, NOW() - INTERVAL (older_than_days + 1) DAY) < NOW() - INTERVAL older_than_days DAY;
END//

CREATE TRIGGER items_total_insert AFTER INSERT ON order_items FOR EACH ROW
BEGIN
    UPDATE orders SET total = total + NEW.quantity * NEW.unit_price WHERE id = NEW.order_id;
END//

CREATE TRIGGER items_total_delete AFTER DELETE ON order_items FOR EACH ROW
BEGIN
    UPDATE orders SET total = total - OLD.quantity * OLD.unit_price WHERE id = OLD.order_id;
END//

CREATE TRIGGER customers_audit AFTER UPDATE ON customers FOR EACH ROW
BEGIN
    INSERT INTO audit_log (table_name, action, row_id) VALUES ('customers', 'UPDATE', NEW.id);
END//
DELIMITER ;

CREATE EVENT purge_imported_orders ON SCHEDULE EVERY 1 DAY DISABLE
    COMMENT 'Clears the imports every night (disabled in the test bed).'
    DO DELETE FROM imported_orders;
