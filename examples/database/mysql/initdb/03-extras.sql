-- The rest of what MySQL describes: spatial and other column types, invisible and descending indexes,
-- a virtual generated column, a list partition, a view with a check option, roles and a function default.
USE acme;

CREATE TABLE stores (
    id SMALLINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    region ENUM('north', 'south', 'east', 'west') NOT NULL,
    services SET('pickup', 'returns', 'repairs') NOT NULL DEFAULT 'pickup',
    location POINT NOT NULL SRID 4326,
    opened YEAR,
    flags BIT(8) NOT NULL DEFAULT b'00000001',
    code CHAR(36) NOT NULL DEFAULT (UUID()),
    name_upper VARCHAR(100) AS (UPPER(name)) VIRTUAL,
    photo MEDIUMBLOB,
    SPATIAL INDEX stores_location (location),
    INDEX stores_opened_desc (opened DESC),
    INDEX stores_region_invisible (region) INVISIBLE
) COMMENT = 'Physical stores, where they are and what they offer.';
INSERT INTO stores (name, region, services, location, opened) VALUES
    ('Centro', 'south', 'pickup,returns', ST_GeomFromText('POINT(-23.55 -46.63)', 4326), 2015),
    ('Boa Viagem', 'east', 'pickup', ST_GeomFromText('POINT(-8.12 -34.90)', 4326), 2019);

CREATE TABLE price_history (
    product_id INT NOT NULL,
    region VARCHAR(10) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (product_id, region)
) COMMENT = 'Prices per region, split by region.'
PARTITION BY LIST COLUMNS (region) (
    PARTITION p_ns VALUES IN ('north', 'south'),
    PARTITION p_ew VALUES IN ('east', 'west')
);

CREATE VIEW active_products AS
SELECT id, sku, name, category_id, price FROM products WHERE active
WITH CASCADED CHECK OPTION;

CREATE ROLE IF NOT EXISTS acme_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON acme.* TO acme_app;
