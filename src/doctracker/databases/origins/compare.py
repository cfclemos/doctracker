"""Where an origin and a live database differ, both ways: "Declared by" on a live object, "Found in"
on a file's, and the page and MCP answer that gathers them."""

import re
from pathlib import Path

import sqlglot
from sqlglot import exp

from doctracker.databases.origins.collection import ORIGIN_PREFIX, _mysql_default, _mysql_type
from doctracker.databases.origins.links import HISTORY_TOOLS, describe_origins


def _type(text: str, dialect: str) -> str:
    """A column type as it is compared: what sqlglot makes of it in the origin's dialect, in lower case,
    a type of the project's own without its schema; MySQL's as it keeps it (`BOOLEAN` is `tinyint(1)`)."""
    if dialect == "mysql":
        return _mysql_type(text)
    try:
        text = exp.DataType.build(text, dialect=dialect).sql(dialect)
    except Exception:  # a type of the database's own that sqlglot does not know
        pass
    return text.lower().replace(" ", "").replace('"', "").rsplit(".", 1)[-1]


_SAME_DEFAULTS = {"now()": "current_timestamp", "current_timestamp()": "current_timestamp", "getdate()": "current_timestamp",
                  "true": "1", "false": "0"}
"""Defaults written differently that are the same."""


def _default(text: str, dialect: str = "postgres") -> str:
    """A default as it is compared: read by sqlglot and written back without its casts, then without
    outer parentheses and case, synonyms made one."""
    try:
        tree = sqlglot.parse_one(str(text), read=dialect).transform(lambda node: node.this if isinstance(node, exp.Cast) else node)
        text = tree.sql(dialect)
    except Exception:  # not an expression sqlglot reads: compared as written
        pass
    text = re.sub(r"::[\w ]+(\[\])?", "", str(text or "")).strip().lower()
    while text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    text = text.strip("'")
    text = re.sub(r"nextval\('([^']*)'\)", lambda m: f"nextval('{m[1].replace(chr(34), '')}')", text)  # "public".x_seq is public.x_seq
    return "" if text == "null" else _SAME_DEFAULTS.get(text, text)  # DEFAULT NULL: no default


def compare_origin(origin: dict, catalog, database: str) -> dict:
    """Where an origin's schema and a database it describes differ.

    Args:
        origin: The origin read.
        catalog: The databases read.
        database: The database's path; or another origin, as `origin:<name>` (an ORM's models against
            its migrations).

    Returns:
        `missing` (the origin's tables and views the database lacks), `extra` (the database's tables
        the origin does not declare, the tools' history tables left out) and `tables`: by the
        origin's object key, its live `path` and its `differences` (columns missing either side, type,
        null, default, primary key, foreign keys, indexes).
    """
    def held(kind: str) -> list[dict]:
        if database.startswith(ORIGIN_PREFIX):  # another origin: what it ends with, as the store keeps it
            return catalog.objects(connection_id=database, kind=kind)
        return catalog.objects(kind=kind, within=database)

    live = {}
    for kind in ("table", "view", "materialized view", "foreign table"):
        for obj in held(kind):  # a schema's path ends with its name, after `/` (a database) or `::` (an origin)
            live[f"{obj['parent'].rsplit('::', 1)[-1].rsplit('/', 1)[-1]}.{obj['name']}".lower()] = obj
    columns: dict[str, dict[str, dict]] = {}
    for column in held("column"):
        columns.setdefault(column["parent"], {})[column["name"].lower()] = column
    by_name: dict[str, list[str]] = {}
    for key in live:
        by_name.setdefault(key.split(".", 1)[1], []).append(key)
    result = {"missing": [], "extra": [], "tables": {}}
    seen = set()
    for key, obj in origin["objects"].items():
        if obj["kind"] not in ("table", "view", "materialized view", "foreign table"):
            continue
        match = key if key in live else (by_name.get(obj["name"].lower(), [None])[0] if not obj["schema"] or len(by_name.get(obj["name"].lower(), [])) == 1 else None)
        if match is None:
            result["missing"].append(key)
            continue
        seen.add(match)
        target, differences = live[match], []
        held = columns.get(target["path"], {})
        mine = {c["name"].lower(): c for c in obj.get("columns", [])}
        for name, column in mine.items():
            other = held.get(name)
            if other is None:
                differences.append(f"column {column['name']} is not in the database")
                continue
            data = other["data"]
            if column["type"] and _type(column["type"], origin["dialect"]) != _type(str(data.get("type", "")), origin["dialect"]):
                differences.append(f"{column['name']}: {column['type']} in the files, {data.get('type')} in the database")
            if obj["kind"] == "table" and bool(column["nullable"]) != bool(data.get("nullable", True)):
                differences.append(f"{column['name']}: {'null allowed' if column['nullable'] else 'not null'} in the files, "
                                   f"{'null allowed' if data.get('nullable', True) else 'not null'} in the database")
            if origin["dialect"] == "mysql":  # as MySQL keeps it: `0` of a decimal(12,2) is 0.00, a string without quotes
                same_default = _mysql_default(column["default"], _type(column["type"], "mysql")) == _mysql_default(data.get("default") or "", str(data.get("type", "")))
            else:
                same_default = _default(column["default"], origin["dialect"]) == _default(data.get("default", ""), origin["dialect"])
            if column["default"] and not column["identity"] and not same_default:
                differences.append(f"{column['name']}: default {column['default']} in the files, {data.get('default') or 'none'} in the database")
        for name, other in held.items():
            if name not in mine and mine:
                differences.append(f"column {other['name']} is only in the database")
        if obj["kind"] == "table":
            pk = (target["data"].get("primary_key") or {}).get("columns") or []
            if obj.get("primary_key") and [c.lower() for c in obj["primary_key"]] != [c.lower() for c in pk]:
                differences.append(f"primary key ({', '.join(obj['primary_key'])}) in the files, ({', '.join(pk) or 'none'}) in the database")
            live_keys = {tuple(c.lower() for c in k["columns"]) for k in target["data"].get("foreign_keys") or []}
            for key_ in obj.get("foreign_keys") or []:
                if tuple(c.lower() for c in key_["columns"]) not in live_keys:
                    differences.append(f"foreign key ({', '.join(key_['columns'])}) → {key_['table']} is not in the database")
            live_indexes = {i["name"].lower() for i in target["data"].get("indexes") or [] if i.get("name")}
            for index in obj.get("indexes") or []:
                if index["name"] and index["name"].lower() not in live_indexes:
                    differences.append(f"index {index['name']} is not in the database")
        result["tables"][key] = {"path": target["path"], "differences": differences}
    tools = set(HISTORY_TOOLS.values()) | {"alembic_version", "django_migrations", "_prisma_migrations", "databasechangelog"}
    result["extra"] = sorted(key for key, obj in live.items() if key not in seen and obj["name"].lower() not in tools)
    return result


def comparisons(origin: dict, described: dict, catalog) -> dict[str, dict]:
    """Where an origin differs from each database it is linked to and, for an ORM, from its other origin
    (its models from its migrations): `compare_origin` of each, by the database's path or `origin:<name>`.
    What DATABASE › Drift and the MCP tool `database_origin` show.

    Args:
        origin: The origin read.
        described: What `describe_origins` says of it.
        catalog: The databases read (and the origins' collections).
    """
    found = {link["database"]: compare_origin(origin, catalog, link["database"]) for link in described["links"]}
    if described.get("related"):
        found[f"{ORIGIN_PREFIX}{described['related']}"] = compare_origin(origin, catalog, f"{ORIGIN_PREFIX}{described['related']}")
    return found

def declared_by(path: str, origins: list[dict], catalog, connections: list[dict], root: Path) -> list[dict]:
    """The origins that declare a live table, view or column of a database they describe, with where
    they differ from it.

    Args:
        path: The live object's path (a table's, a view's or a column's).
        origins: The origins read.
        catalog: The databases read.
        connections: The project's connections.
        root: The project's root.

    Returns:
        Each origin's `origin`, `kind`, `object` (what it says of the object: `created`, `changed`,
        and a column's type, null and default) and `differences` (only those about this object).
    """
    found = catalog.object(path)
    if found is None:
        return []
    database = "/".join(path.split("/")[:2])
    column = found["kind"] == "column"
    table_path = found["parent"] if column else path
    links = describe_origins(origins, catalog, connections, root)
    result = []
    for origin in origins:
        if database not in {link["database"] for link in links[origin["name"]]["links"]}:
            continue
        comparison = compare_origin(origin, catalog, database)
        for key, table in comparison["tables"].items():
            if table["path"] != table_path:
                continue
            declared = origin["objects"][key]
            if column:
                own = next((c for c in declared.get("columns", []) if c["name"].lower() == found["name"].lower()), None)
                if own is None:
                    continue
                differences = [d for d in table["differences"] if d.startswith((f"{own['name']}:", f"column {own['name']} "))]
                result.append({"origin": origin["name"], "kind": origin["kind"], "differences": differences,
                               "object": {"created": own["created"], "changed": own["changed"], "type": own["type"],
                                          "nullable": own["nullable"], "default": own["default"]}})
            else:
                result.append({"origin": origin["name"], "kind": origin["kind"], "differences": table["differences"],
                               "object": {"created": declared["created"], "changed": declared["changed"], "kind": declared["kind"]}})
    return result


def found_in(path: str, origins: list[dict], catalog, connections: list[dict], root: Path) -> list[dict]:
    """The mirror of `declared_by`: where a table, view or column a file declares is, in the live
    databases its origin describes, with where they differ.

    Args:
        path: What the file declares (`origin:<name>::<schema>.<object>`, a column's with `.<column>`).
        origins: The origins read.
        catalog: The databases read.
        connections: The project's connections.
        root: The project's root.

    Returns:
        For each linked database holding it: `database`, `how` (how the link was made, see
        `describe_origins`), `path` (the live object's) and `differences` (only those about this object).
    """
    found = catalog.object(path)
    name, _, key = path.removeprefix(ORIGIN_PREFIX).partition("::")
    origin = next((o for o in origins if o["name"] == name), None)
    if found is None or origin is None:
        return []
    column = found["kind"] == "column"
    table_key = (found["parent"].partition("::")[2] if column else key).lower()
    result = []
    for link in describe_origins(origins, catalog, connections, root)[name]["links"]:
        table = compare_origin(origin, catalog, link["database"])["tables"].get(table_key)
        if table is None:
            continue
        if column:
            live = next((c for c in (catalog.object(table["path"]) or {}).get("children", [])
                         if c["kind"] == "column" and c["name"].lower() == found["name"].lower()), None)
            if live is None:
                continue
            differences = [d for d in table["differences"] if d.startswith((f"{found['name']}:", f"column {found['name']} "))]
            result.append({"database": link["database"], "how": link["how"], "path": live["path"], "differences": differences})
        else:
            result.append({"database": link["database"], "how": link["how"], "path": table["path"], "differences": table["differences"]})
    return result


def database_object(path: str, origins: list[dict], catalog, connections: list[dict], root: Path) -> dict | None:
    """One object, a live database's or one a file declares, as the wiki's page and the MCP tool give it:
    what the store holds of it (`CatalogStore.object`, the same for both), and for a table, view or
    column the files declaring it (`declared_by`, on a live one) or where it is in the live databases
    (`found_in`, on a file's).

    Args:
        path: The object's path (`db:...` or `origin:...::...`).
        origins: The origins read.
        catalog: The databases read, and what the files declare.
        connections: The project's connections.
        root: The project's root.

    Returns:
        The object, or None when the store holds no such object.
    """
    found = catalog.object(path)
    if found is not None and found["kind"] in ("table", "view", "materialized view", "foreign table", "column"):
        if path.startswith(ORIGIN_PREFIX):
            found["found_in"] = found_in(path, origins, catalog, connections, root)
        else:
            found["declared_by"] = declared_by(path, origins, catalog, connections, root)
    return found
