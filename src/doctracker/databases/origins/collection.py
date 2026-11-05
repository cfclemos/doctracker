"""Turn the schema an origin ends with into a live database's collection.

The objects as the database would keep them (its type names, its defaults, the names it gives to
constraints and indexes, a serial's sequence), built by the collector's own code, so that what a file
declares and what a database gives share one shape, one store and one page.
"""

import re

import sqlglot
from sqlalchemy.dialects.sqlite.base import SQLiteDialect
from sqlglot import exp

from doctracker.databases.origins.sql import DEFAULT_SCHEMAS, _check_name, _named, _reads, _split_top


_SQLITE = SQLiteDialect()
"""SQLAlchemy's SQLite dialect: what it reads of a type written in SQLite, the collector's reading too."""

_POSTGRES_TYPES = {exp.DataType.Type.INT: "integer", exp.DataType.Type.BIGINT: "bigint", exp.DataType.Type.SMALLINT: "smallint",
                   exp.DataType.Type.TEXT: "text", exp.DataType.Type.BOOLEAN: "boolean", exp.DataType.Type.DATE: "date",
                   exp.DataType.Type.DOUBLE: "double precision", exp.DataType.Type.FLOAT: "real", exp.DataType.Type.VARBINARY: "bytea",
                   exp.DataType.Type.CHAR: "character", exp.DataType.Type.VARCHAR: "character varying",
                   exp.DataType.Type.DECIMAL: "numeric", exp.DataType.Type.TIMESTAMP: "timestamp{} without time zone",
                   exp.DataType.Type.TIMESTAMPTZ: "timestamp{} with time zone", exp.DataType.Type.TIME: "time{} without time zone",
                   exp.DataType.Type.TIMETZ: "time{} with time zone"}
"""PostgreSQL's own names of the types (`format_type`), as a live reading gives them; `{}` holds a precision."""


def _database_type(text: str, dialect: str) -> str:
    """A column type as the database writes it in its catalog: PostgreSQL's `format_type` names
    (`integer`, `timestamp with time zone`, `character(14)`…); SQLite's as SQLAlchemy reads them back from
    the type written (its own affinity rules: `varchar(14)` → `NUMERIC(14)`, none → `NULL`); the others as
    sqlglot writes them in their dialect (the spelling SQLAlchemy reads back)."""
    if dialect == "sqlite":
        return text if text == "NULL" else str(_SQLITE._resolve_type_affinity((text or "").upper()))  # as its get_columns
    if not text:
        return ""
    try:
        built = exp.DataType.build(text, dialect=dialect, udt=True)
    except Exception:  # a type of the database's own that sqlglot does not know: as written
        return text
    if dialect != "postgres":
        return built.sql(dialect)
    if built.this == exp.DataType.Type.ARRAY and built.expressions:
        return _database_type(built.expressions[0].sql("postgres"), dialect) + "[]"
    if built.this == exp.DataType.Type.USERDEFINED:  # a type of the database's own; the schemas it searches unwritten
        return re.sub(r"^(public|pg_catalog)\.", "", text.lower().replace('"', ""))
    arguments = [e.sql("postgres") for e in built.expressions]
    name = _POSTGRES_TYPES.get(built.this)
    if name is None:
        return built.sql("postgres").lower().replace(", ", ",")
    if "{}" in name:
        return name.format(f"({arguments[0]})" if arguments else "")
    return f"{name}({','.join(arguments)})" if arguments else name


def _postgres_default(default: str, type_: str) -> str:
    """A default as PostgreSQL keeps it: a string cast to its column's type (`'draft'::text`), a
    sequence's name to `regclass`, `true` / `false` in lower case (also a boolean's written as a string,
    `'true'`, `'f'`, `'1'`…)."""
    if re.fullmatch(r"(?i)true|false|null", default):
        return default.lower()
    if type_ == "boolean" and (word := re.fullmatch(r"(?i)'\s*(t|true|y|yes|on|1|f|false|n|no|off|0)\s*'", default)):
        return "true" if word[1].lower() in ("t", "true", "y", "yes", "on", "1") else "false"
    if re.fullmatch(r"'(?:[^']|'')*'", default) and type_:
        base = re.sub(r"\(.*\)", "", type_).strip()
        return f"{default}::{ {'character': 'bpchar'}.get(base, base) }"
    return re.sub(r"nextval\('([^']+)'\)", r"nextval('\1'::regclass)", default)


def _view_body(text: str) -> str:
    """The query of a CREATE VIEW statement, as written (what the database gives as its definition)."""
    match = re.search(r"\bVIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w.\"`\[\]]+\s*(?:\([^)]*\)\s*)?(?:WITH\s*\([^)]*\)\s*)?AS\s+", text,
                      re.IGNORECASE)
    body = text[match.end():] if match else text
    return re.sub(r"\s*(WITH\s+(CASCADED\s+|LOCAL\s+)?CHECK\s+OPTION|WITH\s+(NO\s+)?DATA)?\s*;?\s*$", "", body, flags=re.IGNORECASE)


def _view_columns(body: str, dialect: str, objects: dict, home: str = "") -> list[dict]:
    """A view's columns from its query: each name it gives, with the type of the column it takes when
    it takes one as it is (`o.id`, `c.name AS customer`); a view it reads must have its own columns
    already (see `as_collection`)."""
    try:
        query = sqlglot.parse_one(body, read=dialect)
    except Exception:  # a query sqlglot cannot read: its columns unknown
        return []
    if not isinstance(query, (exp.Select, exp.SetOperation)):
        return []
    select = query if isinstance(query, exp.Select) else next(query.find_all(exp.Select), None)
    tables = {}
    for table in (select.find_all(exp.Table) if select else []):
        key = f"{table.db or home}.{table.name}".lower()
        if key in objects:
            tables[(table.alias_or_name or table.name).lower()] = objects[key]
    columns = []
    for projection in select.expressions if select else []:
        name = projection.alias_or_name
        if not name or name == "*":
            continue
        inner = projection.this if isinstance(projection, exp.Alias) else projection

        def typed(node: exp.Expression) -> str:
            """The type an expression gives, as PostgreSQL types it, where it can be told from the query."""
            if isinstance(node, exp.Paren):
                return typed(node.this)
            if isinstance(node, exp.Column):
                owners = [tables[node.table.lower()]] if node.table and node.table.lower() in tables else list(tables.values())
                found = [c for t in owners for c in t.get("columns") or [] if c["name"].lower() == node.name.lower()]
                return _database_type(found[0]["type"], dialect) if len(found) == 1 and found[0]["type"] else ""
            if dialect == "sqlite":  # SQLite gives a view's column a type only when it takes a table's column as it is
                return ""
            if isinstance(node, exp.Cast):
                return _database_type(node.to.sql(dialect), dialect)
            if isinstance(node, exp.Count):
                return "bigint"
            if isinstance(node, (exp.Sum, exp.Avg)):
                inner_type = typed(node.this)
                if isinstance(node, exp.Sum) and inner_type in ("integer", "smallint"):
                    return "bigint"
                return "numeric" if inner_type.startswith(("bigint", "numeric", "integer", "smallint")) else inner_type
            if isinstance(node, (exp.Max, exp.Min)):
                return typed(node.this)
            if isinstance(node, (exp.Coalesce, exp.Greatest, exp.Least)):
                return typed(node.this)
            if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Div)):
                sides = [typed(node.left), typed(node.right)]
                if any(side.startswith("numeric") for side in sides):
                    return "numeric"
                return sides[0] if sides[0] == sides[1] else ""
            return ""
        type_ = typed(inner)
        columns.append({"name": name, "type": type_, "nullable": True, "default": "", "computed": "", "identity": False,
                        "pk": False, "unique": False, "references": None, "check": "", "comment": ""})
    return columns


def _options(options: list[str]) -> dict[str, str]:
    """A foreign key's options as written (`ON DELETE CASCADE`), as a live reading gives them (`ondelete: CASCADE`)."""
    found = {}
    for option in options:
        match = re.match(r"ON\s+(DELETE|UPDATE)\s+(.+)", option, re.IGNORECASE)
        if match:
            found[f"on{match[1].lower()}"] = match[2].upper()
    return found


def _identity_arguments(arguments: str) -> str:
    """A routine's arguments as its name carries them in a live reading: each one without its default."""
    parts = [re.split(r"\s+DEFAULT\s+|\s*=\s*", part, maxsplit=1, flags=re.IGNORECASE)[0].strip() for part in _split_top(arguments)]
    return ", ".join(part for part in parts if part)


def _parts(obj: dict, columns: list[dict], dialect: str, objects: dict, home: str = "") -> dict:
    """A table or view the file declares in the shape SQLAlchemy's Inspector gives one (what
    `collect._add_table` takes): its columns typed as the database writes them, its keys, uniques,
    indexes and checks, each named as the file names it or as the database names it by itself; a
    PostgreSQL partition also with its parent's foreign keys."""
    name, names = obj["name"], obj.get("names") or {}
    pk = obj.get("primary_key") or []
    keys = list(obj.get("foreign_keys") or [])
    if dialect == "postgres" and obj.get("partition_of"):
        parent = objects.get(f"{obj['partition_of'][0] or 'public'}.{obj['partition_of'][1]}".lower()) or {}
        keys += [{**k, "name": k.get("name") or _named(dialect, parent.get("name", ""), "fk", k["columns"])}
                 for k in parent.get("foreign_keys") or []]
    uniques = sorted(({"name": names.get(f"unique:{','.join(u)}") or _named(dialect, name, "unique", u), "column_names": u}
                      for u in obj.get("unique") or []), key=lambda u: u["name"] or "")
    indexes = [{"name": u["name"], "column_names": u["column_names"], "unique": True} for u in uniques
               if dialect in ("postgres", "mysql")]  # the index backing a unique constraint
    for index in obj.get("indexes") or []:
        expressions = [c for c in index["columns"] if "(" in c]
        indexes.append({"name": index["name"], "unique": index["unique"], "expressions": expressions,
                        "column_names": [None if "(" in c else c for c in index["columns"]]})
    indexes.sort(key=lambda i: i["name"] or "")
    checks = []
    for check in obj.get("checks") or []:
        checks.append({"name": names.get(f"check:{check}") or _check_name(dialect, name, check), "sqltext": check})

    def column(c: dict) -> dict:
        type_ = _database_type(c["type"], dialect)
        if not type_ and dialect == "sqlite":  # a column without a type: what SQLAlchemy reads of it from the database
            type_ = "NULL"
        default = c["default"]
        if dialect == "postgres" and c.get("serial"):
            sequence = c.get("sequence") or f"{name}_{c['name']}_seq"  # its name kept from before a rename
            sequence = sequence if obj["schema"] in ("", "public") else f"{obj['schema']}.{sequence}"
            default = f"nextval('{sequence}')"
        if dialect == "postgres" and default:
            default = _postgres_default(default, type_)
        if dialect in ("mysql", "sqlite") and str(default).upper() == "NULL":  # the database keeps no default for DEFAULT NULL
            default = ""
        return {"name": c["name"], "type": type_, "nullable": c["nullable"], "default": default or None,
                "comment": c["comment"] or None, "computed": {"sqltext": c["computed"]} if c["computed"] else None,
                "identity": {"declared": True} if c["identity"] and not c.get("serial") and dialect != "sqlite" else None,
                "autoincrement": True if c.get("serial") or str(default).startswith("nextval(") or (dialect == "sqlite" and c["identity"]) else None}

    return {"columns": [column(c) for c in columns],
            "pk": {"constrained_columns": pk, "name": names.get("pk") or _named(dialect, name, "pk", pk)} if pk else None,
            "fks": [{"name": k.get("name") or _named(dialect, name, "fk", k["columns"], n), "constrained_columns": k["columns"],
                     "referred_schema": (objects.get(f"{k['schema'] or home}.{k['table']}".lower()) or {}).get("schema", k["schema"] or home),
                     "referred_table": k["table"],
                     "referred_columns": k["target_columns"] or (objects.get(f"{k['schema'] or home}.{k['table']}".lower()) or {}).get("primary_key") or [],
                     "options": _options(k["options"])} for n, k in enumerate(keys, 1)],
            "unique": uniques, "indexes": indexes, "checks": checks,
            "comment": {"text": obj.get("comment")} if obj.get("comment") else None}


ORIGIN_PREFIX = "origin:"
"""What starts the connection of a collection made from a file (`as_collection`), and the paths in it."""


def as_collection(origin: dict) -> dict:
    """The schema an origin ends with, as a collection of a live database (what `collect.collect`
    returns), built by the collector's own code: each table goes through `collect._add_table` in the
    Inspector's shape, then the implied relations; what the database adds by itself (the names of its
    constraints and indexes, a serial's sequence and default) is added as it would. One store, one page,
    one Universe and one search for both (`CatalogStore`).

    Paths: `origin:<name>` (the origin, as a database), `origin:<name>::<schema>` and
    `origin:<name>::<schema>.<object>`; each object's `data` also holds `declared` (`created`,
    `changed`: file and line).

    Args:
        origin: The origin read (`read_origin`).

    Returns:
        The collection, as `collect.collect` returns it.
    """
    from doctracker.databases.collect import _add_table, _Collection, _implied

    dialect, base = origin["dialect"], f"{ORIGIN_PREFIX}{origin['name']}"
    home = origin.get("default_schema", DEFAULT_SCHEMAS.get(dialect, ""))  # a name without schema is in it (a MySQL dump's: its database)
    found = _Collection(base, "::")
    found.add(base, "database", "", origin["name"].rsplit("/", 1)[-1])
    objects = {key: dict(obj) for key, obj in origin["objects"].items()}
    for _ in range(3):  # a view's columns from its query, a view reading a view after it
        for obj in objects.values():
            if "view" in obj["kind"] and obj.get("definition"):
                inferred = _view_columns(_view_body(obj["definition"]), dialect, objects, home)
                if inferred:
                    obj["columns"] = inferred
                if not obj.get("reads"):  # a view our rules read: what it reads, from its query
                    try:
                        obj["reads"] = _reads(sqlglot.parse_one(_view_body(obj["definition"]), read=dialect))
                    except Exception:
                        pass
    routines = {key: found.path(obj["schema"], f"{obj['name']}({_identity_arguments(obj.get('arguments', ''))})")
                for key, obj in objects.items() if obj["kind"] in ("function", "procedure", "aggregate")}

    def place(obj: dict) -> dict:
        return {"created": obj["created"], "changed": obj["changed"]}

    def path_of(schema: str, name: str) -> str | None:
        """The path of an object of the origin by its schema (the default one when not written) and name
        (a routine's carries its arguments, as a live reading's)."""
        key = f"{schema or home}.{name}".lower()
        if key not in objects and not schema:
            key = next((k for k, o in objects.items() if o["name"].lower() == name.lower()), key)
        if key in routines:
            return routines[key]
        return found.path(objects[key]["schema"], objects[key]["name"]) if key in objects else None

    for key, obj in objects.items():
        found.add(found.path(obj["schema"]), "schema", base, obj["schema"])
    for key, obj in objects.items():
        schema, name, kind = obj["schema"], obj["name"], obj["kind"]
        schema_path = found.path(schema)
        if kind in ("table", "foreign table", "view", "materialized view"):
            path = found.path(schema, name)
            view = "view" in kind
            body = _view_body(obj.get("definition") or "") if view else ""
            if view and dialect == "sqlite":  # SQLite keeps a view's whole statement, without its semicolon
                body = re.sub(r"\s*;\s*$", "", obj.get("definition") or "")
            found.add(path, kind, schema_path, name, declared=place(obj), definition=body or None)
            columns = obj.get("columns") or []
            _add_table(found, schema, name, _parts(obj, columns, dialect, objects, home))
            for column in columns:
                if f"{path}.{column['name']}" in found.objects and column.get("created"):
                    found.objects[f"{path}.{column['name']}"]["data"]["declared"] = place(column)
            for column in columns:  # a serial or identity column's sequence, named by the database
                if dialect == "postgres" and column["identity"] and kind == "table":
                    sequence = column.get("sequence") or f"{name}_{column['name']}_seq"  # kept from before a rename
                    found.add(found.path(schema, sequence), "sequence", schema_path, sequence, declared=place(column))
            if obj.get("foreign_server"):
                options, server = obj.get("foreign_options") or {}, origin.get("servers", {}).get(obj["foreign_server"], {})
                host = server.get("host", "")
                target = (f"db:{host}:{server.get('port', '5432')}/{server.get('dbname', '')}/"
                          f"{options.get('schema_name', schema)}.{options.get('table_name', name)}") if host else ""
                found.objects[path]["data"].update(foreign_server=obj["foreign_server"], foreign_target=target or None)
                if target:
                    found.relate(path, target, "foreign table")
        elif kind == "trigger":
            table = path_of(schema, obj.get("table", ""))
            if table is None:
                continue
            path = f"{table}:{name.split(':')[-1]}"
            function = obj.get("function") or ""
            target = path_of(*(function.split(".", 1) if "." in function else ("", function))) if function else None
            definition = obj.get("definition")
            if definition and dialect == "sqlite":  # as SQLite keeps it: without its semicolon
                definition = re.sub(r"\s*;\s*$", "", definition)
            found.add(path, "trigger", table, name.split(":")[-1], declared=place(obj), definition=definition,
                      comment=obj.get("comment"), function=target, timing=obj.get("timing"), events=obj.get("events"),
                      for_each=obj.get("for_each"))
            if target:
                found.relate(path, target, "trigger calls")
        else:  # a function, procedure, sequence, type, domain, synonym...
            data = {k: v for k, v in obj.items() if k not in ("kind", "schema", "name", "created", "changed", "arguments")}
            path = routines.get(key) or found.path(schema, name)
            shown = f"{name}({_identity_arguments(obj.get('arguments', ''))})" if key in routines else name
            found.add(path, "enum" if kind == "type" and obj.get("labels") else kind, schema_path, shown, declared=place(obj), **data)
    for schema in {home} - {None, ""}:  # the schema every database of the dialect has
        found.add(found.path(schema), "schema", base, schema)
    if dialect == "postgres":  # a partition takes its parent's foreign keys and row triggers, as PostgreSQL clones them
        for key, obj in objects.items():
            parent = objects.get(f"{obj['partition_of'][0] or 'public'}.{obj['partition_of'][1]}".lower()) if obj.get("partition_of") else None
            if parent is None:
                continue
            path, parent_path = found.path(obj["schema"], obj["name"]), found.path(parent["schema"], parent["name"])
            for trigger in [o for o in list(found.objects.values()) if o["kind"] == "trigger" and o["parent"] == parent_path]:
                clone = f"{path}:{trigger['name']}"
                found.add(clone, "trigger", path, trigger["name"], **trigger["data"])
                if trigger["data"].get("function"):
                    found.relate(clone, trigger["data"]["function"], "trigger calls")
    for key, obj in objects.items():  # what joins objects: views reading, partitions and child tables
        path = found.path(obj["schema"], obj["name"])
        if path not in found.objects:
            continue
        for read in obj.get("reads") or []:
            target = path_of(*(read.split(".", 1) if "." in read else ("", read)))
            if target and target != path:
                found.relate(path, target, "view reads")
        if obj.get("partition_of"):
            parent = path_of(*obj["partition_of"])
            if parent:
                found.objects[path]["data"].update(partition_of=parent, partition_bound=obj.get("partition_bound"))
                found.relate(path, parent, "partition of")
        for parent_schema, parent_name in obj.get("inherits") or []:
            parent = path_of(parent_schema, parent_name)
            if parent:
                found.objects[path]["data"]["inherits"] = parent
                found.relate(path, parent, "inherits")
    _implied(found)
    return {"ok": True, "error": "", "version": "", "kind": dialect, "server": "", "database": origin["name"], "started": "",
            "seconds": 0, "databases": [], "objects": list(found.objects.values()), "relations": found.relations,
            "unavailable": [{"what": "row estimates and sizes", "reason": "A file declares no rows."}]}
