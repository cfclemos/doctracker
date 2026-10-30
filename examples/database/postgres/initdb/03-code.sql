-- Code kept in the database: SQL and PL/pgSQL functions, a procedure, triggers.
\set ON_ERROR_STOP on

CREATE FUNCTION catalog.final_price(base catalog.price, discount numeric DEFAULT 0)
RETURNS numeric LANGUAGE sql IMMUTABLE AS $$
    SELECT round(base * (1 - discount), 2)
$$;
COMMENT ON FUNCTION catalog.final_price(catalog.price, numeric) IS 'A price after a discount (0.1 = 10 %).';

CREATE FUNCTION sales.customer_lifetime_value(customer bigint)
RETURNS numeric LANGUAGE sql STABLE AS $$
    SELECT coalesce(sum(o.total), 0) FROM sales.orders o
    WHERE o.customer_id = customer AND o.status IN ('paid', 'shipped')
$$;
COMMENT ON FUNCTION sales.customer_lifetime_value(bigint) IS 'All a customer has paid, over every order.';

CREATE FUNCTION sales.recompute_total() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    UPDATE sales.orders o
    SET total = (SELECT coalesce(sum(i.quantity * i.unit_price), 0) FROM sales.order_items i WHERE i.order_id = o.id)
    WHERE o.id = coalesce(NEW.order_id, OLD.order_id);
    RETURN NULL;
END
$$;
COMMENT ON FUNCTION sales.recompute_total() IS 'Keeps sales.orders.total equal to the sum of its items.';

CREATE TRIGGER order_items_total AFTER INSERT OR UPDATE OR DELETE ON sales.order_items
    FOR EACH ROW EXECUTE FUNCTION sales.recompute_total();
COMMENT ON TRIGGER order_items_total ON sales.order_items IS 'Recomputes the order total when its items change.';

CREATE FUNCTION audit.write_log() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_SCHEMA = 'sales' THEN
        INSERT INTO audit.sales_log (action, row_data, table_name) VALUES (TG_OP, to_jsonb(coalesce(NEW, OLD)), TG_TABLE_NAME);
    ELSE
        INSERT INTO audit.catalog_log (action, row_data, table_name) VALUES (TG_OP, to_jsonb(coalesce(NEW, OLD)), TG_TABLE_NAME);
    END IF;
    RETURN coalesce(NEW, OLD);
END
$$;
COMMENT ON FUNCTION audit.write_log() IS 'Writes a row of the audit log for every change.';

CREATE TRIGGER customers_audit AFTER INSERT OR UPDATE OR DELETE ON sales.customers
    FOR EACH ROW EXECUTE FUNCTION audit.write_log();
CREATE TRIGGER products_audit AFTER UPDATE OF price ON catalog.products
    FOR EACH ROW WHEN (OLD.price IS DISTINCT FROM NEW.price) EXECUTE FUNCTION audit.write_log();
COMMENT ON TRIGGER products_audit ON catalog.products IS 'Logs every change of price.';

CREATE FUNCTION inventory.apply_movement() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO inventory.stock (store_id, region, product_id, quantity)
    SELECT NEW.store_id, s.region, NEW.product_id, NEW.quantity FROM inventory.stores s WHERE s.id = NEW.store_id
    ON CONFLICT (store_id, region, product_id) DO UPDATE SET quantity = inventory.stock.quantity + EXCLUDED.quantity;
    RETURN NEW;
END
$$;
COMMENT ON FUNCTION inventory.apply_movement() IS 'Adds a movement to the stock of its store.';
CREATE TRIGGER movements_stock AFTER INSERT ON inventory.movements
    FOR EACH ROW EXECUTE FUNCTION inventory.apply_movement();

CREATE PROCEDURE sales.cancel_stale_drafts(older_than interval DEFAULT '30 days')
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE sales.orders SET status = 'cancelled'
    WHERE status = 'draft' AND id IN (SELECT id FROM sales.orders WHERE status = 'draft')
      AND coalesce(placed_at, now() - older_than - interval '1 day') < now() - older_than;
END
$$;
COMMENT ON PROCEDURE sales.cancel_stale_drafts(interval) IS 'Cancels the drafts nobody touched for a while.';
