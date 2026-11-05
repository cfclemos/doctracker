"""Read what a live database holds from its catalog, read only, in a process apart from the server.

A collection reads the connection's database, every schema of it; a connection that names no
database reads every database the user can see on the server (PostgreSQL, SQL Server; MySQL's
databases are its schemas), each one through a connection of its own. What is read of each: tables, views, materialized
views, foreign tables, columns (type, null, default, comment and the marks primary key, foreign key,
unique, indexed, null allowed, computed), keys, constraints, indexes, sequences, types, functions,
procedures and triggers, the comments of each, and per table the row estimate and the size kept by
the database. SQLAlchemy's Inspector reads the part every database shares; our own catalog queries
read the rest (what views read, functions, triggers, partitions, foreign tables, statistics).

Relations between objects: foreign key (column to column), implied (a `<name>_id` column with no
declared key, matched by name to a one-column primary key), view reads, foreign table (to the table
it stands for, in another database), partition of, inherits and trigger calls (trigger to function).

Nothing is guessed: what a query cannot read (the user's permissions, a database without that
catalog, statistics never gathered) goes to `unavailable` with the reason. Every statement passes
through the read-only engine of `readonly.py`, so a write would be aborted before being sent.

Objects are named by path: `db:<server>/<database>/<schema>.<object>`, a column
`.../<schema>.<table>.<column>` and a trigger `.../<schema>.<table>:<trigger>`; the server is the
connection's `host:port` (`sqlite` for a file).
"""

import asyncio
import re
import multiprocessing
import time
import warnings
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import sqlglot
from sqlglot import exp
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Inspector, ObjectKind

from doctracker.databases.catalog import CatalogStore
from doctracker.databases.discovery import DEFAULT_PORTS
from doctracker.databases.readonly import _CHECKS, DIALECTS, _message, opened
from doctracker.databases.store import ConnectionStore

COLLECT_TIMEOUT_SECONDS = 300
"""Longest a collection may take before it is given up."""

SYSTEM_SCHEMAS = {"information_schema", "pg_catalog", "pg_toast", "sys", "guest", "INFORMATION_SCHEMA",
                  "performance_schema", "mysql"}
"""Schemas of the database itself, never collected (with `pg_*` and SQL Server's `db_*` roles)."""

SYSTEM_DATABASES = {"template0", "template1", "master", "tempdb", "model", "msdb", "mysql",
                    "information_schema", "performance_schema", "sys"}
"""Databases of the server itself, never read nor listed."""

_FIRST_DATABASE = {"postgresql": "postgres"}
"""The database to list the others from when the connection names none (PostgreSQL would otherwise
choose the one named like the user, which may not exist)."""

_CURRENT = {"postgresql": "SELECT current_database()", "mysql": "SELECT database()", "mssql": "SELECT db_name()",
            "oracle": "SELECT sys_context('USERENV', 'DB_NAME') FROM dual"}
"""The name of the database a connection is in, per kind."""

_DATABASES = {"postgresql": "SELECT datname FROM pg_database WHERE NOT datistemplate",
              "mysql": "SELECT schema_name FROM information_schema.schemata",
              "mssql": "SELECT name FROM sys.databases"}
"""The databases of the server the user can see, per kind."""

_PG_NOT_SYSTEM = "{0} !~ '^pg_' AND {0} <> 'information_schema'"

_QUERIES = {
    "postgresql": {
        "view reads": f"""SELECT DISTINCT vn.nspname, v.relname, tn.nspname, t.relname FROM pg_rewrite r
            JOIN pg_class v ON v.oid = r.ev_class JOIN pg_namespace vn ON vn.oid = v.relnamespace
            JOIN pg_depend d ON d.objid = r.oid AND d.classid = 'pg_rewrite'::regclass AND d.refclassid = 'pg_class'::regclass
            JOIN pg_class t ON t.oid = d.refobjid JOIN pg_namespace tn ON tn.oid = t.relnamespace
            WHERE v.relkind IN ('v', 'm') AND t.oid <> v.oid AND {_PG_NOT_SYSTEM.format('vn.nspname')}""",
        "routines": f"""SELECT n.nspname, p.proname, pg_get_function_identity_arguments(p.oid),
            CASE p.prokind WHEN 'p' THEN 'procedure' WHEN 'a' THEN 'aggregate' ELSE 'function' END,
            l.lanname, pg_get_function_result(p.oid), obj_description(p.oid, 'pg_proc')
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace JOIN pg_language l ON l.oid = p.prolang
            WHERE p.prokind IN ('f', 'p', 'a') AND {_PG_NOT_SYSTEM.format('n.nspname')}
            AND NOT EXISTS (SELECT 1 FROM pg_depend e WHERE e.objid = p.oid AND e.deptype = 'e')""",
        "triggers": """SELECT n.nspname, c.relname, t.tgname, pn.nspname, p.proname, pg_get_function_identity_arguments(p.oid),
            pg_get_triggerdef(t.oid), obj_description(t.oid, 'pg_trigger')
            FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_proc p ON p.oid = t.tgfoid JOIN pg_namespace pn ON pn.oid = p.pronamespace WHERE NOT t.tgisinternal""",
        "parents": """SELECT cn.nspname, c.relname, pn.nspname, p.relname, c.relispartition, pg_get_expr(c.relpartbound, c.oid)
            FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid JOIN pg_namespace cn ON cn.oid = c.relnamespace
            JOIN pg_class p ON p.oid = i.inhparent JOIN pg_namespace pn ON pn.oid = p.relnamespace
            WHERE c.relkind IN ('r', 'p', 'f')""",
        "foreign targets": """SELECT n.nspname, c.relname, s.srvname, s.srvoptions, f.ftoptions FROM pg_foreign_table f
            JOIN pg_class c ON c.oid = f.ftrelid JOIN pg_namespace n ON n.oid = c.relnamespace
            JOIN pg_foreign_server s ON s.oid = f.ftserver""",
        "column types": f"""SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
            FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE a.attnum > 0 AND NOT a.attisdropped AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
            AND {_PG_NOT_SYSTEM.format('n.nspname')}""",
        "statistics": f"""SELECT n.nspname, c.relname, c.reltuples::bigint,
            CASE WHEN c.relkind = 'f' THEN NULL ELSE pg_total_relation_size(c.oid) END
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind IN ('r', 'p', 'm', 'f') AND {_PG_NOT_SYSTEM.format('n.nspname')}""",
    },
    "mysql": {
        "view reads": """SELECT view_schema, view_name, table_schema, table_name FROM information_schema.view_table_usage
            WHERE view_schema = database()""",
        "routines": """SELECT routine_schema, routine_name, '', lower(routine_type), 'sql', dtd_identifier, routine_comment
            FROM information_schema.routines WHERE routine_schema = database()""",
        "triggers": """SELECT trigger_schema, event_object_table, trigger_name, NULL, NULL, NULL,
            concat(action_timing, ' ', event_manipulation, ' ', action_statement), NULL
            FROM information_schema.triggers WHERE trigger_schema = database()""",
        "partitions": """SELECT table_schema, table_name, partition_name, partition_method, partition_expression, partition_description
            FROM information_schema.partitions WHERE table_schema = database() AND partition_name IS NOT NULL""",
        "statistics": """SELECT table_schema, table_name, table_rows, data_length + index_length FROM information_schema.tables
            WHERE table_schema = database() AND table_type = 'BASE TABLE'""",
    },
    "mssql": {
        "view reads": """SELECT DISTINCT schema_name(o.schema_id), o.name, coalesce(d.referenced_schema_name, schema_name(o.schema_id)),
            d.referenced_entity_name FROM sys.sql_expression_dependencies d JOIN sys.objects o ON o.object_id = d.referencing_id
            WHERE o.type = 'V' AND d.referenced_entity_name IS NOT NULL""",
        "routines": """SELECT schema_name(o.schema_id), o.name, '', CASE WHEN o.type = 'P' THEN 'procedure' ELSE 'function' END,
            'sql', NULL, CAST(e.value AS nvarchar(4000)) FROM sys.objects o
            LEFT JOIN sys.extended_properties e ON e.major_id = o.object_id AND e.minor_id = 0 AND e.class = 1 AND e.name = 'MS_Description'
            WHERE o.type IN ('FN', 'IF', 'TF', 'P') AND o.is_ms_shipped = 0""",
        "triggers": """SELECT schema_name(o.schema_id), o.name, t.name, NULL, NULL, NULL, NULL, NULL FROM sys.triggers t
            JOIN sys.objects o ON o.object_id = t.parent_id WHERE t.parent_class = 1""",
        "synonyms": "SELECT schema_name(schema_id), name, base_object_name FROM sys.synonyms",
        "statistics": """SELECT schema_name(t.schema_id), t.name, sum(CASE WHEN p.index_id IN (0, 1) THEN p.rows ELSE 0 END),
            sum(a.total_pages) * 8192 FROM sys.tables t JOIN sys.partitions p ON p.object_id = t.object_id
            JOIN sys.allocation_units a ON a.container_id = p.partition_id WHERE t.is_ms_shipped = 0
            GROUP BY t.schema_id, t.name""",
    },
    "sqlite": {
        "triggers": "SELECT 'main', tbl_name, name, NULL, NULL, NULL, sql, NULL FROM sqlite_master WHERE type = 'trigger'",
        "view sql": "SELECT name, sql FROM sqlite_master WHERE type = 'view'",
        # what SQLAlchemy's reflection of SQLite leaves out: indexes on expressions, the actions of foreign keys
        "index sql": "SELECT tbl_name, name, sql FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL",
        "key actions": """SELECT m.name, k.id, k."from", k."table", k.on_update, k.on_delete
            FROM sqlite_master m JOIN pragma_foreign_key_list(m.name) k WHERE m.type = 'table'""",
    },
}
"""Our own catalog queries, per kind of database: what the Inspector does not read."""


def server_name(spec: dict) -> str:
    """The server a connection reaches, as named in the paths: `host:port`, or `sqlite` for a file."""
    if spec["kind"] == "sqlite":
        return "sqlite"
    return f"{spec.get('host') or 'localhost'}:{spec.get('port') or DEFAULT_PORTS.get(spec['kind'], '')}"


class _Collection:
    """What one collection has read so far: objects by path, relations, what was unavailable.

    Attributes:
        base: The path of the database being read, `db:<server>/<database>` (what a file declares:
            `origin:<name>`, see `databases.origins.as_collection`).
        separator: Between the base and a schema: `/`, or `::` in what a file declares.
        prefix: Put before what could not be read, when several databases are read (their name).
        objects: Objects by path: `path`, `kind`, `parent`, `name` and `data`.
        relations: `source`, `target` and `kind` of each relation.
        unavailable: `what` could not be read, and the `reason`.
    """

    def __init__(self, base: str, separator: str = "/") -> None:
        self.base = base
        self.separator = separator
        self.prefix = ""
        self.objects: dict[str, dict] = {}
        self.relations: list[dict] = []
        self.unavailable: list[dict] = []

    def path(self, schema: str, *names: str) -> str:
        """The path of a schema, or of an object inside it."""
        return f"{self.base}{self.separator}{schema}" + "".join(f".{name}" for name in names)

    def add(self, path: str, kind: str, parent: str, name: str, **data) -> dict:
        """Add an object (or complete it, when already there) and return it."""
        found = self.objects.setdefault(path, {"path": path, "kind": kind, "parent": parent, "name": name, "data": {}})
        found["data"].update({key: value for key, value in data.items() if value not in (None, "", [], {})})
        return found

    def relate(self, source: str, target: str, kind: str) -> None:
        """Add a relation."""
        self.relations.append({"source": source, "target": target, "kind": kind})

    def attempt(self, what: str, connection: Connection, read) -> None:
        """Run one part of the reading; when it fails, note it as unavailable and go on with the rest."""
        try:
            read()
        except NotImplementedError:  # the database has no such thing (SQLite's comments): nothing to read
            connection.rollback()
        except Exception as failed:  # a permission or a catalog the database lacks: the rest is still read
            self.unavailable.append({"what": f"{self.prefix}: {what}" if self.prefix else what, "reason": _message(failed)})
            connection.rollback()


def collect(spec: dict) -> dict:
    """Read the catalog of a connection's database, or of every database on its server when it names none.

    Runs in a process apart (see `run_collect`), on a read-only engine; the transaction is rolled back.

    Args:
        spec: The resolved connection (see `readonly.open_engine`), with `ssh` when it goes through a tunnel.

    Returns:
        `ok`, `error`, `version`, `kind`, `server`, `database` (empty when every database was read),
        `started` (ISO 8601, UTC), `seconds`, `databases` (the other databases on the server, not read),
        `objects` (path, kind, parent, name, data), `relations` (source, target, kind) and
        `unavailable` (what, reason).
    """
    began = time.monotonic()
    warnings.filterwarnings("ignore", message="Did not recognize type")  # completed by our own queries
    warnings.filterwarnings("ignore", message="Skipped unsupported reflection")  # expression indexes: kept without columns
    kind = spec["kind"]
    result = {"ok": False, "error": "", "version": "", "kind": kind, "server": server_name(spec), "database": "",
              "started": datetime.now(timezone.utc).isoformat(timespec="seconds"), "databases": [],
              "objects": [], "relations": [], "unavailable": []}
    everything = not spec.get("database") and kind in _DATABASES
    first = {**spec, "database": _FIRST_DATABASE.get(kind, "")} if everything else spec
    found = _Collection(f"db:{result['server']}")
    try:
        with opened(first) as (engine, _tunnel), engine.connect() as connection:
            result["version"] = str(connection.execute(text(_CHECKS[kind][0])).scalar() or "").splitlines()[0][:160]
            if kind == "sqlite":
                database = Path(spec["host"]).name
            else:
                database = str(connection.execute(text(_CURRENT[kind])).scalar() or spec.get("database") or "")
            names: list[str] = []
            if kind in _DATABASES:
                def listed() -> None:
                    names.extend(sorted(row[0] for row in connection.execute(text(_DATABASES[kind]))
                                        if row[0] and row[0] not in SYSTEM_DATABASES))
                found.attempt("databases on the server", connection, listed)
            if not everything:
                result["database"] = database
                result["databases"] = [name for name in names if name != database]
                _read_database(found, connection, kind, database)
            connection.rollback()
        for name in names if everything else []:
            found.prefix = name
            try:
                with opened({**spec, "database": name}) as (engine, _tunnel), engine.connect() as connection:
                    _read_database(found, connection, kind, name)
                    connection.rollback()
            except Exception as failed:  # a database the user may not connect to: the others are still read
                found.unavailable.append({"what": f"database {name}", "reason": _message(failed)})
        _implied(found)
        result.update(ok=True, objects=list(found.objects.values()), relations=found.relations,
                      unavailable=found.unavailable)
    except Exception as failed:  # any driver's or SSH error is reported to the user as it is
        result["error"] = _message(failed)
    result["seconds"] = round(time.monotonic() - began, 2)
    return result


def _read_database(found: _Collection, connection: Connection, kind: str, database: str) -> None:
    """Read one database: the database itself, its schemas and everything in them."""
    server = found.base.split("/")[0]
    found.base = f"{server}/{database}"
    found.add(found.base, "database", server, database)
    _read_structure(found, connection, kind, database)
    _read_catalog(found, connection, kind)
    _read_history(found, connection, kind)


HISTORY_TABLES = {"flyway_schema_history": "flyway", "schema_migrations": "golang-migrate or dbmate",
                  "alembic_version": "alembic", "django_migrations": "django", "_prisma_migrations": "prisma",
                  "databasechangelog": "liquibase", "atlas_schema_revisions": "atlas"}
"""The tables where migration tools record the steps they applied, and the tool of each."""

HISTORY_ROWS = 5000
"""Most rows read of a history table."""


def _read_history(found: _Collection, connection: Connection, kind: str) -> None:
    """Read the rows of the migration tools' history tables (which steps a tool applied to this
    database): kept in the table's data as `history`, each row's values as text."""
    for obj in [o for o in found.objects.values() if o["kind"] == "table" and o["path"].startswith(found.base + "/")]:
        if obj["name"].lower() not in HISTORY_TABLES:
            continue
        schema = obj["parent"].rsplit("/", 1)[-1]
        query = exp.select("*").from_(exp.table_(obj["name"], db=None if kind == "sqlite" else schema)).limit(HISTORY_ROWS).sql(DIALECTS[kind])

        def read(obj=obj, query=query) -> None:
            result = connection.execute(text(query))
            names = list(result.keys())
            obj["data"]["history"] = [{name: (None if value is None else str(value)) for name, value in zip(names, row)} for row in result]
        found.attempt(f"the history of {obj['name']}", connection, read)


def _schemas(inspector: Inspector, kind: str, database: str) -> list[str]:
    """The schemas to read: every one of the database's own (MySQL: the connection's database alone)."""
    if kind == "mysql":
        return [database]
    if kind == "sqlite":
        return ["main"]
    return [s for s in inspector.get_schema_names()
            if s not in SYSTEM_SCHEMAS and not s.startswith(("pg_", "db_"))]


def _read_structure(found: _Collection, connection: Connection, kind: str, database: str) -> None:
    """Read with SQLAlchemy's Inspector what every database shares: schemas, tables, views, columns,
    keys, constraints, indexes and comments; sequences, enums and domains where the database has them."""
    inspector = inspect(connection)
    for schema in _schemas(inspector, kind, database):
        schema_path = found.path(schema)
        found.add(schema_path, "schema", found.base, schema)
        query_schema = None if kind == "sqlite" else schema
        kinds: dict[str, str] = {}
        for object_kind, call in (("table", "get_table_names"), ("foreign table", "get_foreign_table_names"),
                                  ("view", "get_view_names"), ("materialized view", "get_materialized_view_names")):
            def names(object_kind=object_kind, call=call) -> None:
                for name in getattr(inspector, call)(schema=query_schema):
                    kinds[name] = object_kind
            if hasattr(inspector, call):
                found.attempt(f"{object_kind}s of {schema}", connection, names)
        if not kinds:
            continue
        for name, object_kind in kinds.items():
            found.add(found.path(schema, name), object_kind, schema_path, name)

        def multi(call: str) -> dict:
            got = getattr(inspector, call)(schema=query_schema, kind=ObjectKind.ANY)
            return {table: value for (_schema, table), value in got.items() if table in kinds}

        parts: dict[str, dict] = defaultdict(dict)
        for part, call in (("columns", "get_multi_columns"), ("pk", "get_multi_pk_constraint"),
                           ("fks", "get_multi_foreign_keys"), ("unique", "get_multi_unique_constraints"),
                           ("checks", "get_multi_check_constraints"), ("indexes", "get_multi_indexes"),
                           ("comment", "get_multi_table_comment")):
            def read(part=part, call=call) -> None:
                parts[part] = multi(call)
            found.attempt(f"{part} of {schema}", connection, read)
        if kind == "sqlite":
            found.attempt(f"unique constraints and autoincrement of {schema}", connection, lambda: _sqlite_parts(connection, parts))
        for name in kinds:
            _add_table(found, schema, name, {part: values.get(name) for part, values in parts.items()})
        for name, object_kind in kinds.items():
            if object_kind in ("view", "materialized view"):
                def definition(name=name) -> None:
                    found.add(found.path(schema, name), kinds[name], schema_path, name,
                              definition=inspector.get_view_definition(name, schema=query_schema))
                found.attempt(f"definition of {schema}.{name}", connection, definition)
        for object_kind, call in (("sequence", "get_sequence_names"), ("enum", "get_enums"), ("domain", "get_domains")):
            if not hasattr(inspector, call):
                continue
            def extras(object_kind=object_kind, call=call) -> None:
                for item in getattr(inspector, call)(schema=query_schema):
                    if isinstance(item, str):
                        found.add(found.path(schema, item), object_kind, schema_path, item)
                    else:
                        found.add(found.path(schema, item["name"]), object_kind, schema_path, item["name"],
                                  labels=item.get("labels"), type=str(item.get("type") or ""),
                                  nullable=item.get("nullable"), default=item.get("default"),
                                  checks=[c.get("check") for c in item.get("constraints") or []])
            found.attempt(f"{object_kind}s of {schema}", connection, extras)


def _sqlite_parts(connection: Connection, parts: dict) -> None:
    """Complete what SQLAlchemy's reflection of SQLite misses, from SQLite's own pragmas and table SQL: the
    unique constraints it does not find in a table's text (quoted names), and the `AUTOINCREMENT` keys."""
    uniques: dict[tuple[str, str], list[str]] = {}
    for table, index, column in connection.execute(text(
            "SELECT m.name, l.name, i.name FROM sqlite_master m JOIN pragma_index_list(m.name) l JOIN pragma_index_info(l.name) i "
            "WHERE m.type = 'table' AND l.origin = 'u' ORDER BY m.name, l.name, i.seqno")):
        uniques.setdefault((table, index), []).append(column)
    for (table, _), columns in uniques.items():
        held = parts["unique"].setdefault(table, []) if "unique" in parts else None
        if held is not None and all(u["column_names"] != columns for u in held):
            held.append({"name": None, "column_names": columns})
    for table, sql in connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type = 'table' AND sql LIKE '%AUTOINCREMENT%'")):
        for match in re.finditer(r"[\"`\[]?(\w+)[\"`\]]?\s+INTEGER\s+(?:NOT\s+NULL\s+)?PRIMARY\s+KEY\s+(?:ASC\s+|DESC\s+)?AUTOINCREMENT", sql, re.IGNORECASE):
            for column in (parts.get("columns") or {}).get(table) or []:
                if column["name"] == match[1]:
                    column["autoincrement"] = True

def _add_table(found: _Collection, schema: str, name: str, parts: dict) -> None:
    """Add a table's (or view's) columns with their marks, its keys, constraints, indexes and comment,
    and a foreign key relation from each referring column to the column it refers to."""
    path = found.path(schema, name)
    pk = (parts.get("pk") or {}).get("constrained_columns") or []
    fks = parts.get("fks") or []
    uniques = parts.get("unique") or []
    indexes = parts.get("indexes") or []
    unique = {u["column_names"][0] for u in uniques if len(u["column_names"]) == 1}
    unique |= {i["column_names"][0] for i in indexes if i.get("unique") and len(i.get("column_names") or []) == 1}
    indexed = {c for i in indexes for c in i.get("column_names") or [] if c}
    referring = {c for fk in fks for c in fk["constrained_columns"]}
    for position, column in enumerate(parts.get("columns") or [], 1):
        cname = column["name"]
        computed = column.get("computed") or {}
        identity = column.get("identity") or {}
        marks = [mark for mark, on in (
            ("pk", cname in pk), ("fk", cname in referring), ("unique", cname in unique and cname not in pk),
            ("index", cname in indexed), ("null", column.get("nullable", True) and cname not in pk),
            ("generated", bool(computed or identity or column.get("autoincrement") is True))) if on]
        found.add(f"{path}.{cname}", "column", path, cname, position=position, type=str(column.get("type")),
                  nullable=bool(column.get("nullable", True)), default=column.get("default"), comment=column.get("comment"),
                  computed=computed.get("sqltext") and str(computed["sqltext"]), identity=bool(identity), marks=marks)
    keys = []
    for fk in fks:
        target = found.path(fk.get("referred_schema") or schema, fk["referred_table"])
        keys.append({"name": fk.get("name"), "columns": fk["constrained_columns"], "target": target,
                     "target_columns": fk["referred_columns"], "options": fk.get("options") or {}})
        for source, referred in zip(fk["constrained_columns"], fk["referred_columns"]):
            found.relate(f"{path}.{source}", f"{target}.{referred}", "foreign key")
    found.add(path, found.objects[path]["kind"], found.objects[path]["parent"], name,
              comment=(parts.get("comment") or {}).get("text"),
              primary_key={"name": (parts.get("pk") or {}).get("name"), "columns": pk} if pk else None,
              foreign_keys=keys, unique=[{"name": u.get("name"), "columns": u["column_names"]} for u in uniques],
              checks=[{"name": c.get("name"), "check": str(c.get("sqltext"))} for c in parts.get("checks") or []],
              indexes=[{"name": i.get("name"), "columns": [c for c in i.get("column_names") or [] if c],
                        "expressions": [e for e in i.get("expressions") or [] if e] if None in (i.get("column_names") or []) else [],
                        "unique": bool(i.get("unique"))} for i in indexes])


def _read_catalog(found: _Collection, connection: Connection, kind: str) -> None:
    """Read with our own catalog queries what the Inspector leaves out: what views read, functions and
    procedures, triggers, partitions and inheritance, foreign tables' targets, synonyms, statistics."""
    queries = _QUERIES.get(kind, {})

    def rows(name: str) -> list[tuple]:
        return [tuple(row) for row in connection.execute(text(queries[name]))]

    def known(schema: str, name: str) -> str | None:
        path = found.path(schema, name)
        return path if path in found.objects else None

    def view_reads() -> None:
        for view_schema, view, schema, table in rows("view reads"):
            source, target = known(view_schema, view), known(schema, table)
            if source and target:
                found.relate(source, target, "view reads")

    def view_reads_sqlite() -> None:  # SQLite keeps no dependencies: the view's own SQL tells what it reads
        for view, sql in rows("view sql"):
            for table in sqlglot.parse_one(sql, read=DIALECTS["sqlite"]).find_all(exp.Table):
                target = known("main", table.name)
                if target and known("main", view) and target != known("main", view):
                    found.relate(known("main", view), target, "view reads")

    def routines() -> None:
        for schema, name, arguments, routine_kind, language, returns, comment in rows("routines"):
            if found.path(schema) not in found.objects:
                continue
            found.add(found.path(schema, f"{name}({arguments})"), routine_kind, found.path(schema), f"{name}({arguments})",
                      language=language, returns=returns, comment=comment)

    def triggers() -> None:
        for schema, table, name, function_schema, function, arguments, definition, comment in rows("triggers"):
            table_path = known(schema, table)
            if not table_path:
                continue
            path = f"{table_path}:{name}"
            found.add(path, "trigger", table_path, name, definition=definition, comment=comment)
            if function:
                target = found.path(function_schema, f"{function}({arguments or ''})")
                found.objects[path]["data"]["function"] = target
                found.relate(path, target, "trigger calls")

    def parents() -> None:
        for schema, table, parent_schema, parent, is_partition, bound in rows("parents"):
            child, base = known(schema, table), known(parent_schema, parent)
            if child and base:
                found.objects[child]["data"].update({"partition_of" if is_partition else "inherits": base,
                                                     **({"partition_bound": bound} if bound else {})})
                found.relate(child, base, "partition of" if is_partition else "inherits")

    def partitions() -> None:
        for schema, table, partition, method, expression, description in rows("partitions"):
            path = known(schema, table)
            if path:
                data = found.objects[path]["data"]
                data["partitioning"] = f"{method} ({expression})"
                data.setdefault("partitions", []).append({"name": partition, "bound": description})

    def foreign_targets() -> None:
        for schema, table, server, server_options, table_options in rows("foreign targets"):
            path = known(schema, table)
            if not path:
                continue
            options = dict(o.split("=", 1) for o in (server_options or []) + (table_options or []))
            host = options.get("host", "")
            remote_server = f"{host}:{options.get('port', '5432')}" if host and host not in ("localhost", "127.0.0.1") \
                else found.base.split("/")[0].removeprefix("db:")
            target = (f"db:{remote_server}/{options.get('dbname', '')}/"
                      f"{options.get('schema_name', schema)}.{options.get('table_name', table)}")
            found.objects[path]["data"].update(foreign_server=server, foreign_target=target)
            found.relate(path, target, "foreign table")

    def synonyms() -> None:
        for schema, name, target in rows("synonyms"):
            if found.path(schema) in found.objects:
                found.add(found.path(schema, name), "synonym", found.path(schema), name, target=target)

    def index_sql() -> None:  # SQLite: an index on an expression, which the Inspector skips, from its own SQL
        for table, name, sql in rows("index sql"):
            path = known("main", table)
            data = found.objects[path]["data"] if path else None
            if data is None or any(i.get("name") == name for i in data.get("indexes") or []):
                continue
            inner = re.search(r"\bON\s+[\w\"`\[\]]+\s*\((.*)\)", sql, re.IGNORECASE | re.DOTALL)
            parts = [p.strip() for p in re.split(r",(?![^()]*\))", re.sub(r"\)\s*WHERE\b.*$", ")", inner[1], flags=re.IGNORECASE | re.DOTALL))] if inner else []
            data.setdefault("indexes", []).append({"name": name, "columns": [p.strip('"`[]') for p in parts if "(" not in p],
                                                   "expressions": [p for p in parts if "(" in p],
                                                   "unique": bool(re.match(r"\s*CREATE\s+UNIQUE\b", sql, re.IGNORECASE))})

    def key_actions() -> None:  # SQLite: ON DELETE / ON UPDATE of each foreign key, which the Inspector leaves empty
        actions: dict[tuple[str, int], dict] = {}
        for table, key, column, target, on_update, on_delete in rows("key actions"):
            entry = actions.setdefault((table, key), {"columns": [], "target": target, "options": {}})
            entry["columns"].append(column)
            for word, action in (("onupdate", on_update), ("ondelete", on_delete)):
                if action and action.upper() != "NO ACTION":
                    entry["options"][word] = action.upper()
        for (table, _), entry in actions.items():
            path = known("main", table)
            for key in (found.objects[path]["data"].get("foreign_keys") or []) if path else []:
                if key["columns"] == entry["columns"] and entry["options"]:
                    key["options"] = {**(key.get("options") or {}), **entry["options"]}

    def column_types() -> None:  # the type as the database writes it (the Inspector loses "with time zone", composite types)
        for schema, table, column, type_ in rows("column types"):
            path = known(schema, table)
            if path and f"{path}.{column}" in found.objects:
                found.objects[f"{path}.{column}"]["data"]["type"] = type_

    def statistics() -> None:
        for schema, table, estimate, size in rows("statistics"):
            path = known(schema, table)
            if path:
                data = found.objects[path]["data"]
                if estimate is not None and int(estimate) >= 0:  # Postgres: -1 until the table is analysed
                    data["rows"] = int(estimate)
                if size is not None:
                    data["bytes"] = int(size)

    readers = {"view reads": view_reads, "view sql": view_reads_sqlite, "routines": routines, "triggers": triggers,
               "parents": parents, "partitions": partitions, "foreign targets": foreign_targets,
               "synonyms": synonyms, "column types": column_types, "statistics": statistics, "index sql": index_sql,
               "key actions": key_actions}
    for name in queries:
        found.attempt(name, connection, readers[name])
    tables = [o for o in found.objects.values() if o["kind"] in ("table", "materialized view") and o["path"].startswith(found.base + "/")]
    if "statistics" not in queries:
        found.unavailable.append({"what": f"{found.prefix}: row estimates and sizes" if found.prefix else "row estimates and sizes",
                                  "reason": "This database keeps no statistics of its tables."})
    elif missing := [o["path"] for o in tables if "rows" not in o["data"]]:
        found.unavailable.append({"what": f"{found.prefix + ': ' if found.prefix else ''}row estimates of {len(missing)} tables",
                                  "reason": "The database has not gathered statistics of them yet (it needs ANALYZE)."})


def _implied(found: _Collection) -> None:
    """Relate each `<name>_id` column with no declared foreign key to the one-column primary key of a
    table named `<name>`, `<name>s` or `<name>es` in the same database."""
    keys: dict[str, list[str]] = defaultdict(list)
    for obj in found.objects.values():
        pk = (obj["data"].get("primary_key") or {}).get("columns") or []
        if obj["kind"] == "table" and len(pk) == 1:
            keys[obj["name"].lower()].append(f"{obj['path']}.{pk[0]}")
    declared = {r["source"] for r in found.relations if r["kind"] == "foreign key"}
    for obj in list(found.objects.values()):
        name = obj["name"].lower()
        if obj["kind"] != "column" or not name.endswith("_id") or obj["path"] in declared:
            continue
        base, database = name[:-3], "/".join(obj["path"].split("/")[:2]) + "/"
        for target in keys[base] + keys[base + "s"] + keys[base + "es"]:
            if target.startswith(database) and not target.startswith(obj["parent"] + "."):
                found.relate(obj["path"], target, "implied")


async def run_collect(spec: dict) -> dict:
    """Run `collect` in a process of its own, giving up after `COLLECT_TIMEOUT_SECONDS`.

    Args:
        spec: The resolved connection (see `readonly.open_engine`).

    Returns:
        What `collect` returns, or a failure saying the collection did not end in time.
    """
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        try:
            return await asyncio.wait_for(loop.run_in_executor(pool, collect, spec), COLLECT_TIMEOUT_SECONDS)
        except TimeoutError:
            return {"ok": False, "error": f"Not finished in {COLLECT_TIMEOUT_SECONDS} seconds.", "version": "",
                    "kind": spec["kind"], "server": server_name(spec), "database": spec.get("database", ""),
                    "started": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "seconds": COLLECT_TIMEOUT_SECONDS, "databases": [], "objects": [], "relations": [], "unavailable": []}


REFRESH_SECONDS = 60
"""How often the server reads each allowed connection's database again by itself."""

_CHECK_SECONDS = 30
"""How often the server looks for a connection to read: newly allowed, changed, or due again."""

_reading: dict[str, asyncio.Lock] = {}
"""One lock per connection, so a database is never read twice at the same time."""


async def collect_connection(connections: ConnectionStore, catalog: CatalogStore, connection_id: str) -> dict | None:
    """Read an allowed connection's database now and keep it as its current state (the wiki's Refresh,
    the MCP tool, and the server's own readings).

    When the database is already being read, waits for that reading instead of starting another.

    Args:
        connections: The connections.
        catalog: Where the state of each database is kept.
        connection_id: The connection; it must be allowed.

    Returns:
        The connection's state (see `CatalogStore.collection`).

    Raises:
        ValueError: When the connection is unknown or blocked.
        Locked: When its password is saved and the key is not available.
    """
    lock = _reading.setdefault(connection_id, asyncio.Lock())
    if lock.locked():
        async with lock:
            return catalog.collection(connection_id)
    async with lock:
        spec = connections.spec(connection_id)
        name = next(c["name"] for c in connections.connections() if c["id"] == connection_id)
        return catalog.save(connection_id, name, await run_collect(spec))


async def keep_collected(connections: ConnectionStore, catalog: CatalogStore) -> None:
    """Keep the allowed connections' databases read, for as long as the server runs: each one is read
    when it is allowed (or changed), when the server starts, and again every `REFRESH_SECONDS`.

    Connections that cannot be opened yet (saved passwords waiting for the master password, a
    variable not set) are tried again later.

    Args:
        connections: The connections.
        catalog: Where the state of each database is kept.
    """
    started = datetime.now(timezone.utc)
    while True:
        now = datetime.now(timezone.utc)
        for connection in connections.connections():
            last = catalog.last_try(connection["id"])
            due = not last or datetime.fromisoformat(last) < started \
                or (now - datetime.fromisoformat(last)).total_seconds() >= REFRESH_SECONDS
            if connection["allowed"] and due:
                try:
                    await collect_connection(connections, catalog, connection["id"])
                except Exception:  # not openable yet (locked passwords, a variable not set): tried again later
                    continue
        await asyncio.sleep(_CHECK_SECONDS)
