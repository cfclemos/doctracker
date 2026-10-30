"""What the four databases offer, in common, for samples, column profiles, statistics and relations found
through the data. Read only, as doctracker_reader; values printed are masked."""
import re, sys, urllib.parse
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

ROOT = Path(sys.argv[1])
env = dotenv_values(ROOT / "examples/database/.env")
pw = urllib.parse.quote(env["READER_PASSWORD"], safe="")
URLS = {
    "postgres": f"postgresql+pg8000://doctracker_reader:{pw}@localhost:{env['POSTGRES_PORT']}/acme",
    "mysql": f"mysql+pymysql://doctracker_reader:{pw}@127.0.0.1:{env['MYSQL_PORT']}/acme",
    "sqlserver": f"mssql+pytds://doctracker_reader:{pw}@127.0.0.1:{env['MSSQL_PORT']}/acme",
    "sqlite": f"sqlite:///{ROOT / 'examples/database/sqlite/acme.sqlite'}",
}
T = {  # the same tables in each database
    "postgres": dict(customers="sales.customers", orders="sales.orders", imported="staging.imported_orders"),
    "mysql": dict(customers="customers", orders="orders", imported="imported_orders"),
    "sqlserver": dict(customers="sales.customers", orders="sales.orders", imported="staging.imported_orders"),
    "sqlite": dict(customers="customers", orders="orders", imported="imported_orders"),
}
SAMPLE = {  # n random rows: the only part that differs between engines
    "postgres": "SELECT {c} FROM {t} ORDER BY random() LIMIT 5",
    "mysql": "SELECT {c} FROM {t} ORDER BY RAND() LIMIT 5",
    "sqlserver": "SELECT TOP 5 {c} FROM {t} ORDER BY NEWID()",
    "sqlite": "SELECT {c} FROM {t} ORDER BY random() LIMIT 5",
}
ESTIMATE = {  # rows, from the catalog, without counting
    "postgres": "SELECT reltuples::bigint FROM pg_class WHERE oid = 'sales.customers'::regclass",
    "mysql": "SELECT table_rows FROM information_schema.tables WHERE table_schema = 'acme' AND table_name = 'customers'",
    "sqlserver": "SELECT SUM(row_count) FROM sys.dm_db_partition_stats WHERE object_id = OBJECT_ID('sales.customers') AND index_id IN (0, 1)",
    "sqlite": "SELECT stat FROM sqlite_stat1 WHERE tbl = 'customers' LIMIT 1",
}
COLUMN_STATS = {  # per-column statistics kept by the database (distinct values, nulls, most common, histogram)
    "postgres": "SELECT null_frac, n_distinct, most_common_vals IS NOT NULL, histogram_bounds IS NOT NULL FROM pg_stats WHERE schemaname = 'sales' AND tablename = 'orders' AND attname = 'status'",
    "mysql": "SELECT histogram->>'$.\"histogram-type\"' FROM information_schema.column_statistics WHERE schema_name = 'acme' AND table_name = 'orders' AND column_name = 'status'",
    "sqlserver": "SELECT s.name FROM sys.stats s JOIN sys.stats_columns sc ON sc.object_id = s.object_id AND sc.stats_id = s.stats_id JOIN sys.columns c ON c.object_id = sc.object_id AND c.column_id = sc.column_id WHERE s.object_id = OBJECT_ID('sales.orders') AND c.name = 'status'",
    "sqlite": "SELECT count(*) FROM sqlite_master WHERE name = 'sqlite_stat4'",
}
FORMATS = {"email": r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", "cpf": r"^\d{3}\.\d{3}\.\d{3}-\d{2}$", "phone": r"^\+\d{2} \d{2} \d{8,9}$",
           "bcrypt": r"^\$2[aby]\$\d{2}\$", "uuid": r"^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$"}


def shape(value):
    """A value as its format only: what the documentation may show for a sensitive column."""
    v = str(value)
    for name, rx in FORMATS.items():
        if re.match(rx, v, re.I): return f"<{name}>"
    return re.sub(r"[A-Za-z]", "a", re.sub(r"\d", "9", v))[:24]


for name, url in URLS.items():
    t = T[name]
    print(f"\n### {name}")
    with create_engine(url).connect() as c:
        def one(sql):
            try:
                return c.execute(text(sql)).fetchall()
            except Exception as error:
                c.rollback()
                return f"no ({str(error).splitlines()[0][:70]})"
        print("1 sample (masked to formats):", [shape(r[0]) for r in one(SAMPLE[name].format(c="email", t=t["customers"]))],
              [shape(r[0]) for r in one(SAMPLE[name].format(c="cpf", t=t["customers"]))])
        print("2 profile (generic SQL):", one(f"SELECT COUNT(*), COUNT(DISTINCT status), SUM(CASE WHEN placed_at IS NULL THEN 1 ELSE 0 END), MIN(total), MAX(total) FROM {t['orders']}"))
        print("3 row estimate from the catalog:", one(ESTIMATE[name]))
        print("4 column statistics kept by the database:", one(COLUMN_STATS[name]))
        print("5 relation through the data (imported_orders.customer_id in customers.id):",
              one(f"SELECT COUNT(DISTINCT i.customer_id), COUNT(DISTINCT c.id) FROM {t['imported']} i LEFT JOIN {t['customers']} c ON c.id = i.customer_id"))
        print("6 orders.status values (enum or check, from data):", sorted(r[0] for r in one(f"SELECT DISTINCT status FROM {t['orders']}")))
