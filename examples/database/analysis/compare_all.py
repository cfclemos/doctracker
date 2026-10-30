"""Compare, object by object, what each collector reads from the four test databases (read only)."""
import json, subprocess, sqlite3, sys, time, urllib.parse
from collections import defaultdict
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, event, inspect, text

ROOT = Path(sys.argv[1])
BIN = Path(__file__).parent / "bin"
env = dotenv_values(ROOT / "examples/database/.env")
pw = urllib.parse.quote(env["READER_PASSWORD"], safe="")
SQLITE = ROOT / "examples/database/sqlite/acme.sqlite"
ENGINES = {
    "postgres": dict(sa=f"postgresql+pg8000://doctracker_reader:{pw}@localhost:{env['POSTGRES_PORT']}/acme",
                     tbls=f"postgres://doctracker_reader:{pw}@localhost:{env['POSTGRES_PORT']}/acme?sslmode=disable",
                     atlas=f"postgres://doctracker_reader:{pw}@localhost:{env['POSTGRES_PORT']}/acme?sslmode=disable",
                     system={"pg_catalog", "information_schema", "pg_toast"}, default="public"),
    "mysql": dict(sa=f"mysql+pymysql://doctracker_reader:{pw}@127.0.0.1:{env['MYSQL_PORT']}/acme",
                  tbls=f"mysql://doctracker_reader:{pw}@127.0.0.1:{env['MYSQL_PORT']}/acme",
                  atlas=f"mysql://doctracker_reader:{pw}@127.0.0.1:{env['MYSQL_PORT']}/acme",
                  only={"acme"}, default="acme"),
    "sqlserver": dict(sa=f"mssql+pytds://doctracker_reader:{pw}@127.0.0.1:{env['MSSQL_PORT']}/acme",
                      tbls=f"mssql://doctracker_reader:{pw}@127.0.0.1:{env['MSSQL_PORT']}/acme",
                      atlas=None, only={"dbo", "catalog", "sales", "staging", "security"}, default="dbo"),
    "sqlite": dict(sa=f"sqlite:///{SQLITE}", tbls=f"sq://{SQLITE}", atlas=f"sqlite://{SQLITE}", only={"main"}, default="main"),
}


def keep(conf, schema):
    if "only" in conf:
        return schema in conf["only"]
    return schema not in conf["system"] and not schema.startswith("pg_")


def safe(call, *args, **kw):
    try:
        return call(*args, **kw)
    except NotImplementedError:
        return None


def sa_collect(conf):
    """a) SQLAlchemy Inspector: what it gives on every engine."""
    engine = create_engine(conf["sa"])
    insp = inspect(engine)
    out = defaultdict(set)
    for s in [s for s in insp.get_schema_names() if keep(conf, s)] or [None]:
        out["schemas"].add(s)
        for t in insp.get_table_names(schema=s):
            q = f"{s}.{t}"
            out["tables"].add(q)
            for c in insp.get_columns(t, schema=s):
                out["columns"].add(f"{q}.{c['name']}")
                if c.get("comment"): out["column comments"].add(f"{q}.{c['name']}")
                if c.get("computed"): out["generated columns"].add(f"{q}.{c['name']}")
                if c.get("identity") or c.get("autoincrement") is True: out["identity columns"].add(f"{q}.{c['name']}")
            if insp.get_pk_constraint(t, schema=s).get("constrained_columns"): out["primary keys"].add(q)
            for fk in (safe(insp.get_foreign_keys, t, schema=s) or []):
                out["foreign keys"].add(f"{q}({','.join(fk['constrained_columns'])})")
            for u in (safe(insp.get_unique_constraints, t, schema=s) or []): out["unique constraints"].add(f"{q}({','.join(u['column_names'])})")
            for c in (safe(insp.get_check_constraints, t, schema=s) or []): out["check constraints"].add(f"{q}:{c.get('name')}")
            for i in (safe(insp.get_indexes, t, schema=s) or []): out["indexes"].add(f"{q}:{i['name']}")
            try:
                if insp.get_table_comment(t, schema=s).get("text"): out["table comments"].add(q)
            except NotImplementedError:
                pass
        out["views"] |= {f"{s}.{v}" for v in insp.get_view_names(schema=s)}
        for kind, call in (("materialized views", "get_materialized_view_names"), ("sequences", "get_sequence_names"),
                           ("foreign tables", "get_foreign_table_names")):
            try:
                out[kind] |= {f"{s}.{v}" for v in getattr(insp, call)(schema=s)}
            except (NotImplementedError, AttributeError):
                pass
        for kind, call in (("enums", "get_enums"), ("domains", "get_domains")):
            try:
                out[kind] |= {f"{s}.{e['name']}" for e in getattr(insp, call)(schema=s)}
            except (NotImplementedError, AttributeError):
                pass
    return out


def rows(conn, sql):
    return [tuple(r) for r in conn.execute(text(sql))]


PG = {
    "schemas": "select nspname from pg_namespace where nspname !~ '^pg_' and nspname <> 'information_schema'",
    "databases": "select datname from pg_database where not datistemplate",
    "tables": "select n.nspname||'.'||c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind in ('r','p') and n.nspname !~ '^pg_' and n.nspname<>'information_schema'",
    "partitions": "select c.relname from pg_class c where c.relispartition and c.relkind in ('r','p')",
    "inheritance": "select c.relname from pg_inherits i join pg_class c on c.oid=i.inhrelid where not c.relispartition",
    "unlogged tables": "select relname from pg_class where relpersistence='u' and relkind='r'",
    "foreign tables": "select n.nspname||'.'||c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='f'",
    "views": "select n.nspname||'.'||c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='v' and n.nspname !~ '^pg_' and n.nspname<>'information_schema'",
    "materialized views": "select n.nspname||'.'||c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='m'",
    "sequences": "select n.nspname||'.'||c.relname from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='S'",
    "columns": "select n.nspname||'.'||c.relname||'.'||a.attname from pg_attribute a join pg_class c on c.oid=a.attrelid join pg_namespace n on n.oid=c.relnamespace where a.attnum>0 and not a.attisdropped and c.relkind in ('r','p') and n.nspname !~ '^pg_' and n.nspname<>'information_schema'",
    "generated columns": "select attrelid::regclass||'.'||attname from pg_attribute where attgenerated<>'' and attnum>0",
    "identity columns": "select attrelid::regclass||'.'||attname from pg_attribute where attidentity<>'' and attnum>0 and not attisdropped",
    "primary keys": "select conrelid::regclass::text from pg_constraint where contype='p' and conparentid=0 and connamespace::regnamespace::text !~ '^(pg_|information_schema)'",
    "foreign keys": "select conrelid::regclass||':'||conname from pg_constraint where contype='f' and conparentid=0",
    "unique constraints": "select conrelid::regclass||':'||conname from pg_constraint where contype='u' and conparentid=0 and connamespace::regnamespace::text !~ '^(pg_|information_schema)'",
    "check constraints": "select conrelid::regclass||':'||conname from pg_constraint where contype='c' and conrelid<>0 and connamespace::regnamespace::text !~ '^(pg_|information_schema)'",
    "exclusion constraints": "select conname from pg_constraint where contype='x'",
    "indexes": "select indexrelid::regclass::text from pg_index i join pg_class c on c.oid=i.indrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname !~ '^pg_' and n.nspname<>'information_schema' and not c.relispartition",
    "enums": "select typnamespace::regnamespace||'.'||typname from pg_type where typtype='e'",
    "domains": "select typnamespace::regnamespace||'.'||typname from pg_type where typtype='d' and typnamespace::regnamespace::text !~ '^(pg_|information_schema)'",
    "composite types": "select t.typname from pg_type t join pg_class c on c.oid=t.typrelid where c.relkind='c' and t.typnamespace::regnamespace::text !~ '^(pg_|information_schema)'",
    "functions": "select p.oid::regprocedure::text from pg_proc p where p.prokind='f' and p.pronamespace::regnamespace::text !~ '^(pg_|information_schema)' and not exists (select 1 from pg_depend d where d.objid=p.oid and d.deptype='e')",
    "procedures": "select oid::regprocedure::text from pg_proc where prokind='p'",
    "aggregates": "select p.oid::regprocedure::text from pg_proc p where prokind='a' and pronamespace::regnamespace::text !~ '^(pg_|information_schema)' and not exists (select 1 from pg_depend d where d.objid=p.oid and d.deptype='e')",
    "triggers": "select tgname from pg_trigger where not tgisinternal",
    "event triggers": "select evtname from pg_event_trigger",
    "rules": "select rulename from pg_rewrite r join pg_class c on c.oid=r.ev_class where rulename<>'_RETURN' and c.relnamespace::regnamespace::text !~ '^pg_'",
    "row security policies": "select polname from pg_policy",
    "extended statistics": "select stxname from pg_statistic_ext",
    "collations": "select collname from pg_collation where collnamespace::regnamespace::text !~ '^pg_'",
    "text search configs": "select cfgname from pg_ts_config where cfgnamespace::regnamespace::text !~ '^pg_'",
    "operators": "select o.oprname from pg_operator o where oprnamespace::regnamespace::text !~ '^pg_' and not exists (select 1 from pg_depend d where d.objid=o.oid and d.deptype='e')",
    "casts": "select c.oid::text from pg_cast c join pg_proc p on p.oid=c.castfunc where p.pronamespace::regnamespace::text !~ '^pg_' and not exists (select 1 from pg_depend d where d.objid=c.oid and d.deptype='e')",
    "extensions": "select extname from pg_extension",
    "foreign servers": "select srvname from pg_foreign_server",
    "user mappings": "select srvname||':'||usename from pg_user_mappings",
    "publications": "select pubname from pg_publication",
    "subscriptions": "select subname from pg_subscription",
    "tablespaces": "select spcname from pg_tablespace where spcname not in ('pg_default','pg_global')",
    "roles": "select rolname from pg_roles where rolname !~ '^pg_'",
    "view dependencies": "select distinct v.oid::regclass||'->'||d.refobjid::regclass from pg_rewrite r join pg_class v on v.oid=r.ev_class join pg_depend d on d.objid=r.oid and d.refobjid<>v.oid and d.classid='pg_rewrite'::regclass and d.refclassid='pg_class'::regclass where v.relkind in ('v','m') and v.relnamespace::regnamespace::text !~ '^(pg_|information_schema)'",
    "table comments": "select objoid::regclass::text from pg_description where classoid='pg_class'::regclass and objsubid=0 and objoid in (select oid from pg_class where relkind in ('r','p') and relnamespace::regnamespace::text !~ '^(pg_|information_schema)')",
    "column comments": "select objoid::regclass||'.'||objsubid from pg_description where classoid='pg_class'::regclass and objsubid>0",
    "other comments": "select o.identity from pg_description d, pg_identify_object(d.classoid, d.objoid, d.objsubid) o where d.classoid<>'pg_class'::regclass and (o.schema is null or o.schema !~ '^(pg_|information_schema)') and not exists (select 1 from pg_depend e where e.objid=d.objoid and e.deptype='e') and o.type not in ('language','access method','extension') and o.identity<>'public'",
    "shared comments": "select classoid::regclass||':'||objoid from pg_shdescription where classoid<>'pg_database'::regclass or objoid in (select oid from pg_database where datname like 'acme%')",
    "grants": "select n.nspname||'.'||c.relname||':'||a.grantee::regrole from pg_class c join pg_namespace n on n.oid=c.relnamespace, aclexplode(c.relacl) a where c.relacl is not null and n.nspname !~ '^pg_' and n.nspname<>'information_schema' and a.grantee<>c.relowner",
}
MYSQL = {
    "schemas": "select schema_name from information_schema.schemata where schema_name='acme'",
    "tables": "select concat(table_schema,'.',table_name) from information_schema.tables where table_schema='acme' and table_type='BASE TABLE'",
    "views": "select concat(table_schema,'.',table_name) from information_schema.views where table_schema='acme'",
    "columns": "select concat(c.table_schema,'.',c.table_name,'.',c.column_name) from information_schema.columns c join information_schema.tables t using (table_schema, table_name) where c.table_schema='acme' and t.table_type='BASE TABLE'",
    "generated columns": "select column_name from information_schema.columns where table_schema='acme' and generation_expression<>''",
    "identity columns": "select column_name from information_schema.columns where table_schema='acme' and extra like '%auto_increment%'",
    "primary keys": "select table_name from information_schema.table_constraints where table_schema='acme' and constraint_type='PRIMARY KEY'",
    "foreign keys": "select constraint_name from information_schema.referential_constraints where constraint_schema='acme'",
    "unique constraints": "select concat(table_name,':',constraint_name) from information_schema.table_constraints where table_schema='acme' and constraint_type='UNIQUE'",
    "check constraints": "select constraint_name from information_schema.check_constraints where constraint_schema='acme'",
    "indexes": "select distinct concat(table_name,':',index_name) from information_schema.statistics where table_schema='acme'",
    "partitions": "select concat(table_name,':',partition_name) from information_schema.partitions where table_schema='acme' and partition_name is not null",
    "functions": "select routine_name from information_schema.routines where routine_schema='acme' and routine_type='FUNCTION'",
    "procedures": "select routine_name from information_schema.routines where routine_schema='acme' and routine_type='PROCEDURE'",
    "triggers": "select trigger_name from information_schema.triggers where trigger_schema='acme'",
    "events": "select event_name from information_schema.events where event_schema='acme'",
    "table comments": "select table_name from information_schema.tables where table_schema='acme' and table_type='BASE TABLE' and table_comment<>''",
    "column comments": "select concat(table_name,'.',column_name) from information_schema.columns where table_schema='acme' and column_comment<>''",
    "other comments": "select routine_name from information_schema.routines where routine_schema='acme' and routine_comment<>'' union all select event_name from information_schema.events where event_schema='acme' and event_comment<>''",
    "view dependencies": "select concat(view_name,'->',table_name) from information_schema.view_table_usage where view_schema='acme'",
    "roles": "select distinct grantee from information_schema.applicable_roles",
    "grants": "select concat(grantee,':',privilege_type) from information_schema.user_privileges",
}
MSSQL = {
    "schemas": "select name from sys.schemas where name in ('dbo','catalog','sales','staging','security')",
    "tables": "select s.name+'.'+t.name from sys.tables t join sys.schemas s on s.schema_id=t.schema_id where t.is_ms_shipped=0",
    "temporal tables": "select name from sys.tables where temporal_type=2",
    "views": "select s.name+'.'+v.name from sys.views v join sys.schemas s on s.schema_id=v.schema_id where v.is_ms_shipped=0",
    "columns": "select s.name+'.'+t.name+'.'+c.name from sys.columns c join sys.tables t on t.object_id=c.object_id join sys.schemas s on s.schema_id=t.schema_id where t.is_ms_shipped=0",
    "generated columns": "select name from sys.computed_columns",
    "identity columns": "select c.name from sys.identity_columns c join sys.tables t on t.object_id=c.object_id where t.is_ms_shipped=0",
    "primary keys": "select name from sys.key_constraints where type='PK'",
    "foreign keys": "select name from sys.foreign_keys",
    "unique constraints": "select name from sys.key_constraints where type='UQ'",
    "check constraints": "select name from sys.check_constraints",
    "default constraints": "select name from sys.default_constraints",
    "indexes": "select object_name(i.object_id)+':'+i.name from sys.indexes i join sys.objects o on o.object_id=i.object_id where i.name is not null and o.is_ms_shipped=0",
    "sequences": "select name from sys.sequences",
    "synonyms": "select name from sys.synonyms",
    "functions": "select name from sys.objects where type in ('FN','IF','TF')",
    "procedures": "select name from sys.procedures",
    "triggers": "select name from sys.triggers where parent_class=1",
    "user types": "select name from sys.types where is_user_defined=1",
    "row security policies": "select name from sys.security_policies",
    "partition functions": "select name from sys.partition_functions",
    "partitions": "select object_name(p.object_id)+':'+cast(p.partition_number as varchar) from sys.partitions p where p.index_id in (0,1) and p.partition_number>1",
    "view dependencies": "select distinct object_name(d.referencing_id)+'->'+d.referenced_entity_name from sys.sql_expression_dependencies d join sys.views v on v.object_id=d.referencing_id",
    "table comments": "select object_name(major_id) from sys.extended_properties where class=1 and minor_id=0 and name='MS_Description'",
    "column comments": "select object_name(major_id)+'.'+cast(minor_id as varchar) from sys.extended_properties where class=1 and minor_id>0 and name='MS_Description'",
    "roles": "select name from sys.database_principals where type='R' and is_fixed_role=0 and name<>'public'",
    "grants": "select object_name(major_id)+':'+permission_name from sys.database_permissions where class=1",
}


def catalog_collect(name, conf):
    """c) SQLAlchemy plus our own catalog queries: the reference."""
    out = defaultdict(set)
    if name == "sqlite":
        db = sqlite3.connect(f"file:{SQLITE}?mode=ro", uri=True)
        for kind, name_, tbl, sql in db.execute("select type, name, tbl_name, sql from sqlite_master where name not like 'sqlite_%'"):
            if kind == "table" and sql and sql.startswith("CREATE VIRTUAL"): out["virtual tables"].add(name_); continue
            if kind == "table" and "_search_" in name_: continue  # the FTS5 shadow tables
            out[{"table": "tables", "index": "indexes", "view": "views", "trigger": "triggers"}[kind]].add(f"main.{name_}" if kind in ("table", "view") else name_)
            if kind == "table":
                if sql.rstrip().upper().endswith("STRICT"): out["strict tables"].add(name_)
                if "WITHOUT ROWID" in sql.upper(): out["without rowid tables"].add(name_)
                for col in db.execute(f"pragma table_xinfo('{name_}')"):
                    out["columns"].add(f"main.{name_}.{col[1]}")
                    if col[6] in (2, 3): out["generated columns"].add(f"{name_}.{col[1]}")
                    if col[5]: out.setdefault("_pk", set()).add(name_)
                for fk in db.execute(f"pragma foreign_key_list('{name_}')"): out["foreign keys"].add(f"{name_}:{fk[0]}")
                for idx in db.execute(f"pragma index_list('{name_}')"):
                    if idx[3] == "u": out["unique constraints"].add(f"{name_}:{idx[1]}")
                if "CHECK" in sql.upper(): out["check constraints"].add(name_)
        out["primary keys"] = out.pop("_pk", set()); out["schemas"] = {"main"}
        out["view dependencies"] = {"<error: SQLite keeps no dependencies: the view's SQL must be parsed>"}
        return out
    queries = {"postgres": PG, "mysql": MYSQL, "sqlserver": MSSQL}[name]
    engine = create_engine(conf["sa"])
    with engine.connect() as conn:
        for kind, sql in queries.items():
            try:
                out[kind] = {r[0] for r in rows(conn, sql)}
            except Exception as error:
                out[kind] = {f"<error: {str(error).splitlines()[0][:60]}>"}
                conn.rollback()
    return out


def tbls_collect(conf):
    out = defaultdict(set)
    r = subprocess.run([BIN / "tbls", "out", "--dsn", conf["tbls"], "-t", "json"], capture_output=True, text=True)
    if r.returncode:
        out["error"] = {r.stderr.strip().splitlines()[-1][:100] if r.stderr.strip() else "failed"}
        return out
    doc = json.loads(r.stdout)
    default = conf["default"]
    for t in doc.get("tables") or []:
        q = t["name"] if "." in t["name"] else f"{default}.{t['name']}"
        kind = {"BASE TABLE": "tables", "VIEW": "views", "MATERIALIZED VIEW": "materialized views", "FOREIGN TABLE": "foreign tables",
                "table": "tables", "view": "views"}.get(t.get("type"), "tables")
        out[kind].add(q)
        if t.get("comment") and kind == "tables": out["table comments"].add(q)
        for c in t.get("columns") or []:
            if kind == "tables": out["columns"].add(f"{q}.{c['name']}")
            if c.get("comment"): out["column comments"].add(f"{q}.{c['name']}")
        for i in t.get("indexes") or []: out["indexes"].add(f"{q}:{i['name']}")
        for c in t.get("constraints") or []:
            k = {"PRIMARY KEY": "primary keys", "FOREIGN KEY": "foreign keys", "UNIQUE": "unique constraints", "CHECK": "check constraints",
                 "EXCLUDE": "exclusion constraints", "x": "exclusion constraints", "p": "primary keys", "f": "foreign keys", "u": "unique constraints", "c": "check constraints"}.get(c.get("type"), c.get("type", "?").lower())
            out[k].add(f"{q}:{c['name']}")
        for tr in t.get("triggers") or []: out["triggers"].add(tr["name"])
        for ref in t.get("referenced_tables") or []: out["view dependencies"].add(f"{q}->{ref}")
    for f in doc.get("functions") or []:
        out["procedures" if (f.get("type") or "").upper() == "PROCEDURE" else "functions"].add(f"{f['name']}({f.get('arguments', '')})")
    for e in doc.get("enums") or []: out["enums"].add(e["name"])
    out["schemas"] = {n.split(".")[0] for k in ("tables", "views") for n in out[k]}
    return out


def atlas_collect(conf):
    out = defaultdict(set)
    if not conf["atlas"]:
        out["error"] = {"SQL Server needs Atlas Pro"}
        return out
    r = subprocess.run([BIN / "atlas", "schema", "inspect", "-u", conf["atlas"], "--format", "{{ json . }}"], capture_output=True, text=True)
    if r.returncode:
        out["error"] = {r.stderr.strip().splitlines()[-1][:100] if r.stderr.strip() else "failed"}
        return out
    for s in json.loads(r.stdout).get("schemas") or []:
        out["schemas"].add(s["name"])
        for t in s.get("tables") or []:
            q = f"{s['name']}.{t['name']}"
            out["tables"].add(q)
            for c in t.get("columns") or []: out["columns"].add(f"{q}.{c['name']}")
            if t.get("primary_key"): out["primary keys"].add(q)
            for fk in t.get("foreign_keys") or []: out["foreign keys"].add(f"{q}:{fk.get('name')}")
            for i in t.get("indexes") or []: out["indexes"].add(f"{q}:{i.get('name')}")
        for key, kind in (("views", "views"), ("funcs", "functions"), ("procs", "procedures"), ("triggers", "triggers")):
            for o in s.get(key) or []: out[kind].add(f"{s['name']}.{o.get('name')}")
    return out


report = {}
for name, conf in ENGINES.items():
    report[name] = {}
    for label, fn in (("ours (c)", lambda: catalog_collect(name, conf)), ("SQLAlchemy (a)", lambda: sa_collect(conf)),
                      ("tbls", lambda: tbls_collect(conf)), ("Atlas", lambda: atlas_collect(conf))):
        t0 = time.time()
        try:
            report[name][label] = (fn(), time.time() - t0)
        except Exception as error:
            report[name][label] = ({"error": {(str(error).splitlines() or [type(error).__name__])[0][:100]}}, time.time() - t0)

for name, cols in report.items():
    labels = list(cols)
    kinds = sorted({k for out, _ in cols.values() for k in out})
    print(f"\n### {name}\n")
    print("| object | " + " | ".join(labels) + " |\n|---|" + "---|" * len(labels))
    for k in kinds:
        cells = []
        for l in labels:
            v = cols[l][0].get(k)
            if v is None: cells.append("–")
            elif any(str(x).startswith("<error") for x in v): cells.append("no access")
            else: cells.append(str(len(v)))
        print(f"| {k} | " + " | ".join(cells) + " |")
    print("| seconds | " + " | ".join(f"{cols[l][1]:.1f}" for l in labels) + " |")
    ref = cols["ours (c)"][0]
    for l in labels[1:]:
        missing = [k for k, v in ref.items() if v and not any(str(x).startswith("<error") for x in v) and not cols[l][0].get(k)]
        if missing: print(f"\n- {l} misses entirely: {', '.join(sorted(missing))}")
    errs = {l: next(iter(cols[l][0]["error"])) for l in labels if cols[l][0].get("error")}
    for l, e in errs.items(): print(f"- {l}: {e}")
