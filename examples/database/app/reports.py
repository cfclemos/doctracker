"""The shop's reports in SQL written by hand, through the DB-API: the SQL inside the strings reaches its tables."""

import sqlite3

TOP_CUSTOMERS = """
    SELECT c.id, c.full_name, SUM(o.total) AS spent
    FROM customers AS c
    JOIN orders AS o ON o.customer_id = c.id
    WHERE o.status = 'paid'
    GROUP BY c.id, c.full_name
    ORDER BY spent DESC
"""
"""The customers who spent the most."""


def top_customers(connection: sqlite3.Connection, limit: int = 10) -> list[tuple]:
    """The customers who spent the most, best first."""
    return connection.execute(TOP_CUSTOMERS + " LIMIT ?", (limit,)).fetchall()


def products_without_sales(connection: sqlite3.Connection) -> list[tuple]:
    """The products no order holds."""
    return connection.execute(
        "SELECT p.id, p.name FROM products p WHERE NOT EXISTS (SELECT 1 FROM order_items i WHERE i.product_id = p.id)").fetchall()


def cancel_drafts(connection: sqlite3.Connection, days: int) -> int:
    """Cancel the drafts older than some days; how many were cancelled."""
    cursor = connection.execute("UPDATE orders SET status = 'cancelled' WHERE status = 'draft' AND placed_at < date('now', ?)",
                                (f"-{days} days",))
    return cursor.rowcount


def count_rows(connection: sqlite3.Connection, table: str) -> int:
    """How many rows a table holds (its name given by the caller)."""
    return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def customer_emails(connection: sqlite3.Connection, schema: str) -> list[str]:
    """Every customer's email, from the customers of a schema."""
    return [row[0] for row in connection.execute(f"SELECT email FROM {schema}.customers ORDER BY email")]
