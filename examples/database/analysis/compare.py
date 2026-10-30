"""Compare what SQLAlchemy, SQLAlchemy + own pg_catalog queries, tbls and Atlas read from a live Postgres (read only)."""
import json, os, subprocess, sys, time
from collections import Counter
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, event, inspect, text

ROOT = Path(sys.argv[1])
BIN = Path(__file__).parent / "bin"
url = dotenv_values(ROOT / ".env")["DATABASE_URL"].rsplit("/", 1)[0] + "/" + sys.argv[2]
SYSTEM = {"pg_catalog", "information_schema", "pg_toast"}
results = {}

engine = create_engine(url.replace("postgresql://", "postgresql+pg8000://"))
@event.listens_for(engine, "connect")
def read_only(dbapi_conn, _):
    cur = dbapi_conn.cursor(); cur.execute("SET default_transaction_read_only = on"); cur.close()
    dbapi_conn.commit()

# a) SQLAlchemy Inspector
t0 = time.time()
insp = inspect(engine)
a = Counter()
schemas = [s for s in insp.get_schema_names() if s not in SYSTEM and not s.startswith("pg_")]
a["schemas"] = len(schemas)
for s in schemas:
    tables = insp.get_table_names(schema=s)
    a["tables"] += len(tables)
    for t in tables:
        cols = insp.get_columns(t, schema=s)
        a["columns"] += len(cols)
        a["column comments"] += sum(1 for c in cols if c.get("comment"))
        a["primary keys"] += 1 if insp.get_pk_constraint(t, schema=s).get("constrained_columns") else 0
        a["foreign keys"] += len(insp.get_foreign_keys(t, schema=s))
        a["indexes"] += len(insp.get_indexes(t, schema=s))
        a["unique constraints"] += len(insp.get_unique_constraints(t, schema=s))
        a["check constraints"] += len(insp.get_check_constraints(t, schema=s))
        a["table comments"] += 1 if insp.get_table_comment(t, schema=s).get("text") else 0
    a["views"] += len(insp.get_view_names(schema=s))
    a["materialized views"] += len(insp.get_materialized_view_names(schema=s))
    a["sequences"] += len(insp.get_sequence_names(schema=s))
    a["foreign tables"] += len(insp.get_foreign_table_names(schema=s))
    try:
        a["enums"] += len(insp.get_enums(schema=s))
        a["domains"] += len(insp.get_domains(schema=s))
    except Exception as error:
        a["enums/domains error"] = str(error)[:60]
results["a) SQLAlchemy"] = (a, time.time() - t0)

# c) + own pg_catalog queries for what the Inspector does not give
t0 = time.time()
extra = Counter()
queries = {
    "triggers": "select count(*) from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace where not t.tgisinternal and n.nspname not in ('pg_catalog','information_schema')",
    "functions": "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where p.prokind='f' and n.nspname not in ('pg_catalog','information_schema') and not exists (select 1 from pg_depend d where d.objid=p.oid and d.deptype='e')",
    "procedures": "select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where p.prokind='p' and n.nspname not in ('pg_catalog','information_schema')",
    "view dependencies": "select count(distinct (v.oid, d.refobjid)) from pg_rewrite r join pg_class v on v.oid=r.ev_class join pg_depend d on d.objid=r.oid and d.refobjid<>v.oid join pg_namespace n on n.oid=v.relnamespace where v.relkind in ('v','m') and n.nspname not in ('pg_catalog','information_schema')",
    "partitions": "select count(*) from pg_inherits i join pg_class c on c.oid=i.inhrelid where c.relispartition",
    "extensions": "select count(*) from pg_extension",
    "foreign servers": "select count(*) from pg_foreign_server",
    "user mappings": "select count(*) from pg_user_mappings",
    "row estimates": "select count(*) from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind in ('r','p','m') and n.nspname not in ('pg_catalog','information_schema','pg_toast')",
    "roles": "select count(*) from pg_roles where rolname not like 'pg\\_%'",
}
with engine.connect() as conn:
    for name, sql in queries.items():
        extra[name] = conn.execute(text(sql)).scalar()
    assert conn.execute(text("show default_transaction_read_only")).scalar() == "on"
c = Counter(a)
c.update(extra)
results["c) SQLAlchemy + pg_catalog"] = (c, results["a) SQLAlchemy"][1] + time.time() - t0)

# d1) tbls
t0 = time.time()
dsn = url.replace("postgresql://", "postgres://") + "?sslmode=disable"
out = subprocess.run([BIN / "tbls", "out", "--dsn", dsn, "-t", "json"], capture_output=True, text=True)
t = Counter()
if out.returncode == 0:
    doc = json.loads(out.stdout)
    for table in (doc.get("tables") or []):
        kind = table.get("type", "")
        key = {"BASE TABLE": "tables", "VIEW": "views", "MATERIALIZED VIEW": "materialized views", "FOREIGN TABLE": "foreign tables"}.get(kind, kind.lower() or "tables")
        t[key] += 1
        if key == "tables":
            t["columns"] += len((table.get("columns") or []))
            t["column comments"] += sum(1 for col in (table.get("columns") or []) if col.get("comment"))
            t["table comments"] += 1 if table.get("comment") else 0
            t["indexes"] += len(table.get("indexes", []) or [])
            cons = table.get("constraints", []) or []
            t["primary keys"] += sum(1 for x in cons if x.get("type") == "PRIMARY KEY")
            t["foreign keys"] += sum(1 for x in cons if x.get("type") == "FOREIGN KEY")
            t["unique constraints"] += sum(1 for x in cons if x.get("type") == "UNIQUE")
            t["check constraints"] += sum(1 for x in cons if x.get("type") == "CHECK")
            t["triggers"] += len(table.get("triggers", []) or [])
    t["schemas"] = len({x["name"].split(".")[0] for x in (doc.get("tables") or []) if "." in x["name"]}) or 1
    t["functions"] = len(doc.get("functions", []) or [])
    t["enums"] = len(doc.get("enums", []) or [])
    t["relations (incl. view deps)"] = len(doc.get("relations", []) or [])
else:
    t["error"] = out.stderr.strip()[:120]
results["d1) tbls"] = (t, time.time() - t0)

# d2) Atlas community
t0 = time.time()
out = subprocess.run([BIN / "atlas", "schema", "inspect", "-u", dsn, "--format", "{{ json . }}"], capture_output=True, text=True)
at = Counter()
if out.returncode == 0:
    doc = json.loads(out.stdout)
    for schema in (doc.get("schemas") or []):
        at["schemas"] += 1
        for table in schema.get("tables", []) or []:
            at["tables"] += 1
            at["columns"] += len((table.get("columns") or []) or [])
            at["primary keys"] += 1 if table.get("primary_key") else 0
            at["foreign keys"] += len(table.get("foreign_keys", []) or [])
            at["indexes"] += len(table.get("indexes", []) or [])
        for key in ("views", "materialized", "functions", "funcs", "procs", "triggers", "sequences", "enums"):
            if schema.get(key): at[key] += len(schema[key])
else:
    at["error"] = out.stderr.strip()[:200]
results["d2) Atlas community"] = (at, time.time() - t0)

kinds = sorted({k for counter, _ in results.values() for k in counter})
names = list(results)
print("| what | " + " | ".join(names) + " |")
print("|---|" + "---|" * len(names))
for k in kinds:
    print(f"| {k} | " + " | ".join(str(results[n][0].get(k, "–")) for n in names) + " |")
print("| seconds | " + " | ".join(f"{results[n][1]:.1f}" for n in names) + " |")
