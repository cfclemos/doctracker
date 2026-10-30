"""Read SQL files with tree-sitter, sqlglot and sqlparse; build the schema each one understands (applying
ALTERs in order) and compare it with what the live database holds."""
import re, sys, time, urllib.parse
from collections import Counter
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

ROOT = Path(sys.argv[1]); TB = ROOT / "examples/database"
env = dotenv_values(TB / ".env"); pw = urllib.parse.quote(env["READER_PASSWORD"], safe="")
apw = urllib.parse.quote(env["POSTGRES_ADMIN_PASSWORD"], safe="")
KINDS = ["tables", "columns", "primary keys", "foreign keys", "unique", "checks", "indexes", "views", "materialized views",
         "functions", "procedures", "triggers", "sequences", "types", "table comments", "column comments"]


def norm(name, default):
    parts = [p.strip('"`[]').lower() for p in re.split(r"\.(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", name.strip())]
    return ".".join(([default] if len(parts) == 1 else []) + parts[-2:])


def prepare(sql, engine):
    """The same clean-up for every reader: no psql meta-commands, no GO, MySQL delimiters undone."""
    sql = re.sub(r"(?m)^\\.*$", "", sql)
    sql = re.sub(r"/\*![0-9]*\s*(.*?)\*/", r"\1", sql, flags=re.S) if engine == "mysql" else sql
    if engine == "tsql":
        sql = re.sub(r"(?mi)^\s*GO\s*$", ";", sql)
    if engine == "mysql":  # DELIMITER blocks: their statements end with the delimiter; make it ';' and keep bodies whole
        out, delim = [], ";"
        for line in sql.splitlines():
            m = re.match(r"\s*DELIMITER\s+(\S+)", line, re.I)
            if m: delim = m.group(1); continue
            out.append(line.replace(delim, ";\n-- end\n") if delim != ";" and line.rstrip().endswith(delim) else line)
        sql = "\n".join(out)
    return sql


class Schema:
    def __init__(self, default):
        self.default = default; self.found = {k: set() for k in KINDS}; self.count = Counter(); self.unknown = Counter()
    def table(self, name): t = norm(name, self.default); self.found["tables"].add(t); return t
    def column(self, table, col): self.found["columns"].add(f"{table}.{col.strip(chr(34) + '`[]').lower()}")
    def drop_column(self, table, col): self.found["columns"].discard(f"{table}.{col.strip(chr(34) + '`[]').lower()}")
    def rename_column(self, table, old, new):
        self.drop_column(table, old); self.column(table, new)
    def add(self, kind, name=None): self.count[kind] += 1; name and self.found[kind].add(norm(name, self.default))


def result(s):
    return {k: (len(s.found[k]) if k in ("tables", "columns", "views", "materialized views", "functions", "procedures", "triggers",
                                          "sequences", "types") else s.count[k]) for k in KINDS}


# --- b) sqlglot ---------------------------------------------------------------------------------------
import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel
import logging
logging.getLogger("sqlglot").setLevel(logging.ERROR)


def cls(*names):
    return tuple(getattr(exp, n) for n in names if hasattr(exp, n))


def read_sqlglot(sql, dialect, default):
    s = Schema(default)
    for stmt in sqlglot.parse(sql, read=dialect, error_level=ErrorLevel.IGNORE):
        if stmt is None: continue
        if isinstance(stmt, exp.Command):
            s.unknown[" ".join(str(stmt.this).split()[:2]).upper() + " " + str(stmt.expression or "").split()[0:1].__str__()] += 1; continue
        if isinstance(stmt, exp.Create):
            kind = (stmt.args.get("kind") or "").upper()
            target = stmt.this
            if kind == "TABLE":
                schema = target if isinstance(target, exp.Schema) else None
                table = schema.this if schema else target
                if not isinstance(table, exp.Table): s.unknown["CREATE TABLE ?"] += 1; continue
                t = s.table(table.sql(dialect=dialect))
                for item in (schema.expressions if schema else []):
                    if isinstance(item, exp.ColumnDef):
                        s.column(t, item.name)
                        for c in item.constraints:
                            k = c.kind
                            if isinstance(k, exp.PrimaryKeyColumnConstraint): s.add("primary keys")
                            elif isinstance(k, exp.UniqueColumnConstraint): s.add("unique")
                            elif isinstance(k, exp.CheckColumnConstraint): s.add("checks")
                            elif isinstance(k, cls("Reference")) or "REFERENCES" in c.sql(dialect=dialect).upper(): s.add("foreign keys")
                            elif isinstance(k, exp.CommentColumnConstraint): s.add("column comments")
                    else:
                        node = item.args.get("this") if isinstance(item, exp.Constraint) else item
                        for sub in ([node] + (item.expressions if isinstance(item, exp.Constraint) else [])):
                            if isinstance(sub, cls("PrimaryKey", "PrimaryKeyColumnConstraint")): s.add("primary keys")
                            elif isinstance(sub, cls("ForeignKey")): s.add("foreign keys")
                            elif isinstance(sub, cls("UniqueColumnConstraint", "Unique")): s.add("unique")
                            elif isinstance(sub, cls("CheckColumnConstraint", "Check")): s.add("checks")
                            elif isinstance(sub, cls("IndexColumnConstraint")): s.add("indexes")
                props = stmt.args.get("properties")
                if props and any(isinstance(p, exp.SchemaCommentProperty) for p in props.expressions): s.add("table comments")
            elif kind == "VIEW":
                mat = stmt.args.get("properties") and any(isinstance(p, exp.MaterializedProperty) for p in stmt.args["properties"].expressions)
                s.add("materialized views" if mat else "views", target.sql(dialect=dialect))
            elif kind == "INDEX": s.add("indexes")
            elif kind == "FUNCTION": s.add("functions", (target.this if isinstance(target, exp.UserDefinedFunction) else target).sql(dialect=dialect).split("(")[0])
            elif kind == "PROCEDURE": s.add("procedures", (target.this if isinstance(target, exp.UserDefinedFunction) else target).sql(dialect=dialect).split("(")[0])
            elif kind == "SEQUENCE": s.add("sequences", target.sql(dialect=dialect))
            elif kind in ("TYPE", "DOMAIN"): s.add("types", target.sql(dialect=dialect))
            elif kind == "TRIGGER": s.add("triggers", target.sql(dialect=dialect))
            elif kind in ("SCHEMA", "DATABASE", "EXTENSION"): pass
            else: s.unknown[f"CREATE {kind}"] += 1
        elif isinstance(stmt, exp.Alter):
            t = norm(stmt.this.sql(dialect=dialect), default)
            for action in stmt.args.get("actions") or []:
                if isinstance(action, exp.ColumnDef): s.column(t, action.name)
                elif isinstance(action, exp.Drop) and (action.args.get("kind") or "").upper() == "COLUMN" and action.this is not None: s.drop_column(t, action.this.name)
                elif type(action).__name__ == "RenameColumn" and action.this is not None and action.args.get("to") is not None:
                    s.rename_column(t, action.this.name, action.args["to"].name)
                elif isinstance(action, exp.AddConstraint):
                    txt = action.sql(dialect=dialect).upper()
                    s.add("foreign keys" if "FOREIGN KEY" in txt else "primary keys" if "PRIMARY KEY" in txt else "unique" if "UNIQUE" in txt else "checks" if "CHECK" in txt else "indexes")
        elif isinstance(stmt, exp.Comment):
            s.add("column comments" if (stmt.args.get("kind") or "").upper() == "COLUMN" else "table comments" if (stmt.args.get("kind") or "").upper() == "TABLE" else "other")
        elif isinstance(stmt, cls("Insert", "Select", "Set", "Use", "Drop", "Grant", "Revoke", "Update", "Delete", "Analyze", "Transaction", "Commit")) or type(stmt).__name__ in ("Command", "Semicolon"):
            pass
        else:
            s.unknown[type(stmt).__name__] += 1
    return s


# --- a) tree-sitter -----------------------------------------------------------------------------------
import tree_sitter_language_pack as pack
PARSER = pack.get_parser("sql")


def ts_text(src, n): return src[n.start_byte:n.end_byte].decode("utf-8", "replace")


def read_treesitter(sql, default):
    s = Schema(default); src = sql.encode(); tree = PARSER.parse(src)
    def walk(n):
        yield n
        for c in n.named_children: yield from walk(c)
    s.unknown["ERROR nodes"] = sum(1 for n in walk(tree.root_node) if n.type == "ERROR")
    for st in tree.root_node.named_children:
        for node in st.named_children if st.type == "statement" else [st]:
            ty = node.type
            ref = next((c for c in node.named_children if c.type == "object_reference"), None)
            name = ts_text(src, ref) if ref else ""
            if ty == "create_table" and ref:
                t = s.table(name)
                defs = next((c for c in node.named_children if c.type == "column_definitions"), None)
                for c in defs.named_children if defs else []:
                    body = ts_text(src, c).upper()
                    if c.type == "column_definition":
                        s.column(t, ts_text(src, c.named_children[0]))
                        if "PRIMARY KEY" in body: s.add("primary keys")
                        if "REFERENCES" in body: s.add("foreign keys")
                        if re.search(r"\bUNIQUE\b", body): s.add("unique")
                        if re.search(r"\bCHECK\b", body): s.add("checks")
                    elif c.type in ("constraints", "constraint"):
                        for part in (c.named_children if c.type == "constraints" else [c]):
                            b = ts_text(src, part).upper()
                            s.add("primary keys" if "PRIMARY KEY" in b else "foreign keys" if "FOREIGN KEY" in b else "unique" if "UNIQUE" in b else "checks" if "CHECK" in b else "indexes")
            elif ty == "create_view": s.add("views", name)
            elif ty == "create_materialized_view": s.add("materialized views", name)
            elif ty == "create_index": s.add("indexes")
            elif ty == "create_function": s.add("functions", name)
            elif ty == "create_procedure": s.add("procedures", name)
            elif ty == "create_trigger": s.add("triggers", name)
            elif ty == "create_sequence": s.add("sequences", name)
            elif ty == "create_type": s.add("types", name)
            elif ty == "alter_table" and ref:
                t = norm(name, default)
                for a in node.named_children:
                    if a.type == "add_column":
                        cd = next((c for c in a.named_children if c.type == "column_definition"), None)
                        if cd: s.column(t, ts_text(src, cd.named_children[0]))
                    elif a.type == "drop_column":
                        ident = [c for c in a.named_children if c.type == "identifier"]
                        if ident: s.drop_column(t, ts_text(src, ident[-1]))
                    elif a.type == "rename_column":
                        ident = [c for c in a.named_children if c.type == "identifier"]
                        if len(ident) >= 2: s.rename_column(t, ts_text(src, ident[0]), ts_text(src, ident[1]))
                    elif a.type in ("add_constraint", "add_constraints"):
                        b = ts_text(src, a).upper()
                        s.add("foreign keys" if "FOREIGN KEY" in b else "primary keys" if "PRIMARY KEY" in b else "unique" if "UNIQUE" in b else "checks")
            elif ty == "comment_statement":
                b = ts_text(src, node).upper()
                s.add("column comments" if " COLUMN " in b else "table comments" if " TABLE " in b else "other")
            elif ty not in ("create_schema", "create_extension", "insert", "select", "set_statement", "drop_table", "grant", "create_database", "transaction", "update", "delete"):
                s.unknown[ty] += 1
    return s


# --- c) sqlparse + our rules --------------------------------------------------------------------------
import sqlparse


def split_top(body):
    depth, cur, out = 0, "", []
    for ch in body:
        depth += ch == "("; depth -= ch == ")"
        if ch == "," and depth == 0: out.append(cur); cur = ""
        else: cur += ch
    return out + [cur]


NAME = r"((?:[\w$]+|\"[^\"]+\"|`[^`]+`|\[[^\]]+\])(?:\.(?:[\w$]+|\"[^\"]+\"|`[^`]+`|\[[^\]]+\]))?)"


def read_sqlparse(sql, default):
    s = Schema(default)
    for stmt in sqlparse.split(sql):
        st = sqlparse.format(stmt, strip_comments=True).strip()
        u = st.upper()
        if not u: continue
        m = re.match(r"CREATE\s+(?:UNLOGGED\s+|TEMPORARY\s+)?TABLE\s+(?:IF NOT EXISTS\s+)?" + NAME + r"\s*(\(.*\))?", st, re.S | re.I)
        if m:
            t = s.table(m.group(1))
            body = m.group(2)
            if body:
                depth, end = 0, 0
                for i, ch in enumerate(body):
                    depth += ch == "("; depth -= ch == ")"
                    if depth == 0: end = i; break
                for part in split_top(body[1:end]):
                    p = part.strip(); pu = p.upper()
                    if not p: continue
                    if re.match(r"(CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK|EXCLUDE|INDEX|KEY|FULLTEXT|SPATIAL|PERIOD)\b", pu):
                        s.add("primary keys" if "PRIMARY KEY" in pu else "foreign keys" if "FOREIGN KEY" in pu else "unique" if pu.startswith("UNIQUE") or " UNIQUE " in pu else "checks" if "CHECK" in pu else "indexes")
                    else:
                        s.column(t, re.split(r"\s+", p, 1)[0])
                        if "PRIMARY KEY" in pu: s.add("primary keys")
                        if "REFERENCES" in pu: s.add("foreign keys")
                        if re.search(r"\bUNIQUE\b", pu): s.add("unique")
                        if re.search(r"\bCHECK\b", pu): s.add("checks")
                        if re.search(r"\bCOMMENT\s+'", pu): s.add("column comments")
                if re.search(r"\)\s*[^;]*COMMENT\s*=?\s*'", st[m.start(2) + end:], re.I): s.add("table comments")
            continue
        for rx, kind in ((r"CREATE\s+(?:OR\s+REPLACE\s+)?MATERIALIZED\s+VIEW\s+" + NAME, "materialized views"),
                         (r"CREATE\s+(?:OR\s+REPLACE\s+|ALGORITHM=\w+\s+|DEFINER=\S+\s+|SQL SECURITY \w+\s+)*VIEW\s+" + NAME, "views"),
                         (r"CREATE\s+(?:OR\s+REPLACE\s+|DEFINER=\S+\s+)*FUNCTION\s+" + NAME, "functions"),
                         (r"CREATE\s+(?:OR\s+REPLACE\s+|DEFINER=\S+\s+)*PROC(?:EDURE)?\s+" + NAME, "procedures"),
                         (r"CREATE\s+(?:OR\s+REPLACE\s+|DEFINER=\S+\s+|CONSTRAINT\s+)*TRIGGER\s+" + NAME, "triggers"),
                         (r"CREATE\s+SEQUENCE\s+" + NAME, "sequences"), (r"CREATE\s+(?:TYPE|DOMAIN)\s+" + NAME, "types")):
            m = re.match(rx, st, re.I | re.S)
            if m: s.add(kind, m.group(1)); break
        else:
            if re.match(r"CREATE\s+(UNIQUE\s+)?(NONCLUSTERED\s+|CLUSTERED\s+)?(COLUMNSTORE\s+)?INDEX", u): s.add("indexes")
            elif (m := re.match(r"ALTER\s+TABLE\s+(?:ONLY\s+)?" + NAME + r"\s+(.*)", st, re.S | re.I)):
                t = norm(m.group(1), default); rest = m.group(2)
                for a in split_top(rest):
                    a = a.strip(); au = a.upper()
                    if (n := re.match(r"ADD\s+(?:COLUMN\s+)?(?!CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|CHECK)(\S+)", a, re.I)): s.column(t, n.group(1))
                    elif (n := re.match(r"DROP\s+COLUMN\s+(\S+)", a, re.I)): s.drop_column(t, n.group(1))
                    elif (n := re.match(r"RENAME\s+COLUMN\s+(\S+)\s+TO\s+(\S+)", a, re.I)): s.rename_column(t, n.group(1), n.group(2))
                    elif au.startswith("ADD"):
                        s.add("foreign keys" if "FOREIGN KEY" in au else "primary keys" if "PRIMARY KEY" in au else "unique" if "UNIQUE" in au else "checks" if "CHECK" in au else "indexes")
            elif (m := re.match(r"COMMENT\s+ON\s+(TABLE|COLUMN)", u)): s.add("table comments" if m.group(1) == "TABLE" else "column comments")
            elif re.match(r"EXEC\s+SP_ADDEXTENDEDPROPERTY", u): s.add("column comments" if "'COLUMN'" in u else "table comments")
    return s


# --- the reference: what the live database holds ------------------------------------------------------
TRUTH = {
    "postgres": {
        "tables": "select lower(n.nspname||'.'||c.relname) from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind in ('r','p') and n.nspname !~ '^pg_' and n.nspname<>'information_schema'",
        "columns": "select lower(n.nspname||'.'||c.relname||'.'||a.attname) from pg_attribute a join pg_class c on c.oid=a.attrelid join pg_namespace n on n.oid=c.relnamespace where a.attnum>0 and not a.attisdropped and c.relkind in ('r','p') and n.nspname !~ '^pg_' and n.nspname<>'information_schema'",
        "primary keys": "select oid from pg_constraint where contype='p' and connamespace::regnamespace::text !~ '^pg_'",
        "foreign keys": "select conname from pg_constraint where contype='f' and conparentid=0",
        "unique": "select conname from pg_constraint where contype='u' and conparentid=0 and connamespace::regnamespace::text !~ '^pg_'",
        "checks": "select conname from pg_constraint where contype='c' and conrelid<>0 and connamespace::regnamespace::text !~ '^pg_'",
        "indexes": "select i.indexrelid from pg_index i join pg_class c on c.oid=i.indrelid where c.relnamespace::regnamespace::text !~ '^(pg_|information_schema)' and not exists (select 1 from pg_constraint k where k.conindid=i.indexrelid) and not exists (select 1 from pg_inherits h where h.inhrelid=i.indexrelid)",
        "views": "select lower(n.nspname||'.'||c.relname) from pg_class c join pg_namespace n on n.oid=c.relnamespace where c.relkind='v' and n.nspname !~ '^pg_' and n.nspname<>'information_schema'",
        "materialized views": "select relname from pg_class where relkind='m'",
        "functions": "select p.oid from pg_proc p where p.prokind='f' and p.pronamespace::regnamespace::text !~ '^(pg_|information_schema)' and not exists (select 1 from pg_depend d where d.objid=p.oid and d.deptype='e')",
        "procedures": "select oid from pg_proc where prokind='p'",
        "triggers": "select oid from pg_trigger where not tgisinternal and tgparentid=0",
        "sequences": "select relname from pg_class c where relkind='S' and not exists (select 1 from pg_depend d where d.objid=c.oid and d.deptype='i')",
        "types": "select oid from pg_type where typtype in ('e','d') and typnamespace::regnamespace::text !~ '^(pg_|information_schema)' union all select t.oid from pg_type t join pg_class c on c.oid=t.typrelid where c.relkind='c' and t.typnamespace::regnamespace::text !~ '^(pg_|information_schema)'",
        "table comments": "select objoid from pg_description where classoid='pg_class'::regclass and objsubid=0 and objoid in (select oid from pg_class where relkind in ('r','p') and relnamespace::regnamespace::text !~ '^(pg_|information_schema)')",
        "column comments": "select objoid from pg_description where classoid='pg_class'::regclass and objsubid>0",
    },
    "mysql": {
        "tables": "select lower(concat(table_schema,'.',table_name)) from information_schema.tables where table_schema='acme' and table_type='BASE TABLE'",
        "columns": "select lower(concat(c.table_schema,'.',c.table_name,'.',c.column_name)) from information_schema.columns c join information_schema.tables t using (table_schema, table_name) where c.table_schema='acme' and t.table_type='BASE TABLE'",
        "primary keys": "select table_name from information_schema.table_constraints where table_schema='acme' and constraint_type='PRIMARY KEY'",
        "foreign keys": "select constraint_name from information_schema.referential_constraints where constraint_schema='acme'",
        "unique": "select constraint_name from information_schema.table_constraints where table_schema='acme' and constraint_type='UNIQUE'",
        "checks": "select constraint_name from information_schema.check_constraints where constraint_schema='acme'",
        "indexes": "select distinct concat(table_name,index_name) from information_schema.statistics s where table_schema='acme' and index_name<>'PRIMARY' and not exists (select 1 from information_schema.table_constraints k where k.table_schema='acme' and k.table_name=s.table_name and k.constraint_name=s.index_name)",
        "views": "select lower(concat(table_schema,'.',table_name)) from information_schema.views where table_schema='acme'",
        "materialized views": "select 1 from dual where false",
        "functions": "select routine_name from information_schema.routines where routine_schema='acme' and routine_type='FUNCTION'",
        "procedures": "select routine_name from information_schema.routines where routine_schema='acme' and routine_type='PROCEDURE'",
        "triggers": "select trigger_name from information_schema.triggers where trigger_schema='acme'",
        "sequences": "select 1 from dual where false", "types": "select 1 from dual where false",
        "table comments": "select table_name from information_schema.tables where table_schema='acme' and table_type='BASE TABLE' and table_comment<>''",
        "column comments": "select concat(table_name,column_name) from information_schema.columns where table_schema='acme' and column_comment<>''",
    },
    "tsql": {
        "tables": "select lower(s.name+'.'+t.name) from sys.tables t join sys.schemas s on s.schema_id=t.schema_id where t.is_ms_shipped=0",
        "columns": "select lower(s.name+'.'+t.name+'.'+c.name) from sys.columns c join sys.tables t on t.object_id=c.object_id join sys.schemas s on s.schema_id=t.schema_id where t.is_ms_shipped=0 and t.temporal_type<>1",
        "primary keys": "select name from sys.key_constraints where type='PK' and object_name(parent_object_id) not like '%_log'",
        "foreign keys": "select name from sys.foreign_keys", "unique": "select name from sys.key_constraints where type='UQ'",
        "checks": "select name from sys.check_constraints",
        "indexes": "select name from sys.indexes i where name is not null and is_primary_key=0 and is_unique_constraint=0 and objectproperty(object_id,'IsMsShipped')=0",
        "views": "select lower(s.name+'.'+v.name) from sys.views v join sys.schemas s on s.schema_id=v.schema_id where v.is_ms_shipped=0",
        "materialized views": "select 1 where 1=0",
        "functions": "select name from sys.objects where type in ('FN','IF','TF')", "procedures": "select name from sys.procedures",
        "triggers": "select name from sys.triggers where parent_class=1", "sequences": "select name from sys.sequences",
        "types": "select name from sys.types where is_user_defined=1",
        "table comments": "select major_id from sys.extended_properties where class=1 and minor_id=0",
        "column comments": "select major_id from sys.extended_properties where class=1 and minor_id>0",
    },
}


def truth(engine, url):
    if engine == "sqlite":
        import sqlite3
        db = sqlite3.connect(f"file:{TB / 'sqlite/acme.sqlite'}?mode=ro", uri=True)
        out = {k: set() for k in KINDS}
        for kind, name, sql in db.execute("select type, name, sql from sqlite_master where name not like 'sqlite_%' and name not like 'products_search_%'"):
            if kind == "table":
                out["tables"].add(f"main.{name}".lower())
                for col in db.execute(f"pragma table_xinfo('{name}')"):
                    if not sql.startswith("CREATE VIRTUAL"): out["columns"].add(f"main.{name}.{col[1]}".lower())
                if "PRIMARY KEY" in sql.upper(): out["primary keys"].add(name)
                for fk in db.execute(f"pragma foreign_key_list('{name}')"): out["foreign keys"].add(f"{name}{fk[0]}")
                for m in re.finditer(r"\bCHECK\s*\(", sql, re.I): out["checks"].add(f"{name}{m.start()}")
                for m in re.finditer(r"\bUNIQUE\b", sql, re.I): out["unique"].add(f"{name}{m.start()}")
            elif kind == "index" and sql: out["indexes"].add(name)
            elif kind in ("view", "trigger"): out[kind + "s"].add(f"main.{name}" if kind == "view" else name)
        return {k: len(v) for k, v in out.items()}
    with create_engine(url).connect() as c:
        return {k: len(c.execute(text(q)).fetchall()) for k, q in TRUTH[engine].items()}


CASES = [  # file(s), engine for the reference, sqlglot dialect, default schema, reference URL
    ("dump postgres acme", ["origins/dumps/postgres-acme.sql"], "postgres", "postgres", "public",
     f"postgresql+pg8000://doctracker_reader:{pw}@localhost:{env['POSTGRES_PORT']}/acme"),
    ("dump mysql acme", ["origins/dumps/mysql-acme.sql"], "mysql", "mysql", "acme",
     f"mysql+pymysql://root:{urllib.parse.quote(env['MYSQL_ROOT_PASSWORD'], safe='')}@127.0.0.1:{env['MYSQL_PORT']}/acme"),
    ("dump sqlite", ["origins/dumps/sqlite-acme.sql"], "sqlite", "sqlite", "main", None),
    ("sql server script", ["mssql/acme.sql"], "tsql", "tsql", "dbo",
     f"mssql+pytds://doctracker_reader:{pw}@127.0.0.1:{env['MSSQL_PORT']}/acme"),
    ("flyway V1..V5 (in order)", sorted((TB / "origins/flyway").glob("V*.sql")), "postgres", "postgres", "public",
     f"postgresql+pg8000://{env['POSTGRES_ADMIN_USER']}:{apw}@localhost:{env['POSTGRES_PORT']}/origin_flyway"),
]

for title, files, engine, dialect, default, url in CASES:
    sql = prepare("\n".join((TB / f if not isinstance(f, Path) else f).read_text(encoding="utf-8") for f in files), engine if engine != "tsql" else "tsql")
    ref = truth(engine, url)
    cols = {}
    for label, fn in (("tree-sitter", lambda: read_treesitter(sql, default)), ("sqlglot", lambda: read_sqlglot(sql, dialect, default)),
                      ("sqlparse + rules", lambda: read_sqlparse(sql, default))):
        t0 = time.time(); s = fn(); cols[label] = (result(s), s.unknown, time.time() - t0)
    print(f"\n### {title}\n\n| object | live database | " + " | ".join(cols) + " |\n|---|---|" + "---|" * len(cols))
    for k in KINDS:
        if ref.get(k, 0) or any(c[0][k] for c in cols.values()):
            print(f"| {k} | {ref.get(k, 0)} | " + " | ".join(("**" if c[0][k] != ref.get(k, 0) else "") + str(c[0][k]) + ("**" if c[0][k] != ref.get(k, 0) else "") for c in cols.values()) + " |")
    print("| not understood | – | " + " | ".join(str(sum(c[1].values())) for c in cols.values()) + " |")
    print("| seconds | – | " + " | ".join(f"{c[2]:.2f}" for c in cols.values()) + " |")
    for label, c in cols.items():
        if c[1]: print(f"- {label} did not understand: " + ", ".join(f"{k} ×{v}" for k, v in c[1].most_common(6)))
