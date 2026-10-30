"""Writes universe-acme.json from the four test servers (read only, catalog only): server → database →
schema → tables and views → columns, with foreign keys, implied relations, what views read and the
foreign tables pointing to another database."""
import json, sys, urllib.parse
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect, text

ROOT, OUT = Path(sys.argv[1]), Path(sys.argv[2])
env = dotenv_values(ROOT / "examples/database/.env")
pw = urllib.parse.quote(env["READER_PASSWORD"], safe="")
pg = lambda db: f"postgresql+pg8000://doctracker_reader:{pw}@localhost:{env['POSTGRES_PORT']}/{db}"
SERVERS = {  # server → database → url
    "postgres": {"acme": pg("acme"), "acme_warehouse": pg("acme_warehouse")},
    "mysql": {"acme": f"mysql+pymysql://doctracker_reader:{pw}@127.0.0.1:{env['MYSQL_PORT']}/acme"},
    "sqlserver": {"acme": f"mssql+pytds://doctracker_reader:{pw}@127.0.0.1:{env['MSSQL_PORT']}/acme"},
    "sqlite": {"acme.sqlite": f"sqlite:///{ROOT / 'examples/database/sqlite/acme.sqlite'}"},
}
if len(sys.argv) > 3 and sys.argv[3] == "large":  # the generated 600 tables alone
    SERVERS = {"postgres": {"acme_large": pg("acme_large")}}
SYSTEM = {"pg_catalog", "information_schema", "pg_toast", "sys", "guest", "INFORMATION_SCHEMA", "performance_schema", "mysql"}
READS = {
    "postgresql": """select distinct vn.nspname, v.relname, tn.nspname, t.relname from pg_rewrite r join pg_class v on v.oid = r.ev_class
                     join pg_namespace vn on vn.oid = v.relnamespace join pg_depend d on d.objid = r.oid and d.classid = 'pg_rewrite'::regclass
                     and d.refclassid = 'pg_class'::regclass join pg_class t on t.oid = d.refobjid join pg_namespace tn on tn.oid = t.relnamespace
                     where v.relkind in ('v','m') and t.oid <> v.oid""",
    "mysql": "select view_schema, view_name, table_schema, table_name from information_schema.view_table_usage where view_schema = database()",
    "mssql": """select distinct schema_name(o.schema_id), o.name, coalesce(d.referenced_schema_name, 'dbo'), d.referenced_entity_name
                from sys.sql_expression_dependencies d join sys.objects o on o.object_id = d.referencing_id where o.type = 'V'""",
}
FOREIGN = """select n.nspname, c.relname, s.srvoptions, f.ftoptions from pg_foreign_table f join pg_class c on c.oid = f.ftrelid
             join pg_namespace n on n.oid = c.relnamespace join pg_foreign_server s on s.oid = f.ftserver"""

nodes, edges, pks = {}, [], {}
def node(id, label, kind, parent=None): nodes.setdefault(id, dict(id=id, label=label, kind=kind, parent=parent))
def edge(s, t, kind): edges.append(dict(source=s, target=t, kind=kind))
def safe(call, *a, **k):
    try: return call(*a, **k)
    except Exception: return []
foreign = []
for server, databases in SERVERS.items():
    node(server, server, "server")
    for database, url in databases.items():
        db = f"{server}/{database}"; node(db, database, "database", server)
        engine = create_engine(url)
        with engine.connect() as conn:
            insp = inspect(conn)
            schemas = [s for s in insp.get_schema_names() if s not in SYSTEM and not s.startswith(("pg_", "db_"))]
            for schema in schemas:
                sid = f"{db}/{schema}"; tables = safe(insp.get_table_names, schema=schema) + safe(getattr(insp, "get_foreign_table_names", lambda **k: []), schema=schema)
                views = safe(insp.get_view_names, schema=schema) + safe(getattr(insp, "get_materialized_view_names", lambda **k: []), schema=schema)
                if not tables and not views: continue
                node(sid, schema, "schema", db)
                for name in tables + views:
                    tid = f"{sid}.{name}"; node(tid, name, "view" if name in views else "table", sid)
                    # What marks each column: key, foreign key, unique, index, null allowed, computed by the database.
                    pk = (safe(insp.get_pk_constraint, name, schema=schema) or {}).get("constrained_columns") or []
                    if len(pk) == 1: pks.setdefault(name, []).append(f"{tid}.{pk[0]}")
                    fks = safe(insp.get_foreign_keys, name, schema=schema)
                    unique = {c for u in safe(insp.get_unique_constraints, name, schema=schema) if len(u["column_names"]) == 1 for c in u["column_names"]}
                    indexed = {c for i in safe(insp.get_indexes, name, schema=schema) for c in i.get("column_names") or [] if c}
                    unique |= {i["column_names"][0] for i in safe(insp.get_indexes, name, schema=schema) if i.get("unique") and len(i.get("column_names") or []) == 1}
                    referring = {c for fk in fks for c in fk["constrained_columns"]}
                    for c in safe(insp.get_columns, name, schema=schema):
                        node(f"{tid}.{c['name']}", c["name"], "column", tid)
                        nodes[f"{tid}.{c['name']}"].update(type=str(c.get("type")), flags=[f for f, on in (
                            ("pk", c["name"] in pk), ("fk", c["name"] in referring), ("unique", c["name"] in unique and c["name"] not in pk),
                            ("index", c["name"] in indexed), ("null", c.get("nullable", True) and c["name"] not in pk),
                            ("generated", bool(c.get("computed") or c.get("identity") or c.get("autoincrement") is True))) if on])
                    for fk in fks:
                        ref = f"{db}/{fk.get('referred_schema') or schema}.{fk['referred_table']}"
                        for a, b in zip(fk["constrained_columns"], fk["referred_columns"]): edge(f"{tid}.{a}", f"{ref}.{b}", "foreign key")
            query = READS.get(engine.dialect.name)
            if query:
                for vs, v, ts, t in safe(lambda: conn.execute(text(query)).all()):
                    if f"{db}/{vs}.{v}" in nodes and f"{db}/{ts}.{t}" in nodes: edge(f"{db}/{vs}.{v}", f"{db}/{ts}.{t}", "view reads")
            if engine.dialect.name == "postgresql":
                for schema, name, server_options, table_options in safe(lambda: conn.execute(text(FOREIGN)).all()):
                    opts = dict(o.split("=", 1) for o in (server_options or []) + (table_options or []))
                    foreign.append((f"{db}/{schema}.{name}", f"{server}/{opts.get('dbname')}/{opts.get('schema_name', schema)}.{opts.get('table_name', name)}"))
        engine.dispose()
for source, target in foreign:
    if target in nodes: edge(source, target, "foreign table")
# Implied: a column named <name>_id without a foreign key, when a table <name>(s) of the same database has a one-column key.
declared = {e["source"] for e in edges if e["kind"] == "foreign key"}
for cid, n in list(nodes.items()):
    if n["kind"] != "column" or not n["label"].endswith("_id") or cid in declared: continue
    base, db = n["label"][:-3], cid.split("/")[0] + "/" + cid.split("/")[1]
    for target in pks.get(base, []) + pks.get(base + "s", []) + pks.get(base + "es", []):
        if target.startswith(db + "/") and not target.startswith(n["parent"] + "."): edge(cid, target, "implied")
OUT.write_text(json.dumps(dict(nodes=list(nodes.values()), edges=edges)), encoding="utf-8")
flags = {}
for n in nodes.values():
    for f in n.get("flags", []): flags[f] = flags.get(f, 0) + 1
print("column marks:", flags)
kinds = lambda key, items: {k: sum(1 for x in items if x[key] == k) for k in sorted({x[key] for x in items})}
print(kinds("kind", nodes.values()), kinds("kind", edges))
