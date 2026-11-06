"""Where two places of the databases differ (DATABASES › Diff: `compare`), and the same comparison on one
object: "Declared by" on a live object, "Found in" on a file's, and the page and MCP answer that gathers them."""

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


def sql_key(text: str, dialect: str = "postgres") -> str:
    """An expression (a check, a view's query, a function's body) as it is compared: what databases add
    when they keep it left out, so the same rule written two ways is one (`status IN ('a', 'b')` and
    PostgreSQL's `status = ANY (ARRAY['a'::text, 'b'::text])`): casts, parentheses and quotes dropped,
    `= ANY (ARRAY[...])` read as `IN (...)`, case and spacing ignored.

    Args:
        text: The SQL.
        dialect: sqlglot's name for its SQL.

    Returns:
        The key; the text with its spacing and case evened out when sqlglot cannot read it.
    """
    text = re.sub(r"\b_(?:latin1|utf8mb4|utf8mb3|utf8|binary|ascii)'", "'", text)  # MySQL's charset before a string
    try:
        tree = sqlglot.parse_one(text, read=dialect)
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError, ValueError):
        return re.sub(r"\s+", " ", text).strip().lower()
    for node in list(tree.find_all(exp.Cast, exp.Paren)):
        replaced = node.replace(node.this)
        tree = replaced if node is tree else tree
    tree = tree.transform(lambda node: exp.In(this=node.this, expressions=node.expression.this.expressions)
                          if isinstance(node, exp.EQ) and isinstance(node.expression, exp.Any)
                          and isinstance(node.expression.this, exp.Array) else node)
    def flat(node):  # PostgreSQL's FROM ((a JOIN b ON ...) JOIN c ON ...): the table and its joins, in order
        if isinstance(node, exp.Subquery) and not node.alias and isinstance(node.this, (exp.Subquery, exp.Table)):
            table, joins = flat(node.this)
            return table, joins + list(node.args.get("joins") or [])
        joins = list(node.args.get("joins") or [])
        node.set("joins", None)
        return node, joins

    for select in list(tree.find_all(exp.Select)):
        source = select.args.get("from_") or select.args.get("from")
        if source is not None and isinstance(source.this, exp.Subquery) and not source.this.alias:
            table, joins = flat(source.this)
            source.set("this", table)
            select.set("joins", joins + list(select.args.get("joins") or []))
    for select in tree.find_all(exp.Select):  # MySQL's `products.id` reading one table only: `id`
        source = select.args.get("from_") or select.args.get("from")
        if source is not None and isinstance(source.this, exp.Table) and not select.args.get("joins"):
            names = {source.this.name.lower(), (source.this.alias or "").lower()} - {""}
            for column in select.find_all(exp.Column):
                if column.table and column.table.lower() in names:
                    column.set("table", None)
                    column.set("db", None)
    for alias in list(tree.find_all(exp.Alias)):  # MySQL's `o.id AS id`: the column's own name
        if isinstance(alias.this, exp.Column) and alias.alias.lower() == alias.this.name.lower():
            alias.replace(alias.this)
    for identifier in tree.find_all(exp.Identifier):
        identifier.set("quoted", False)
    return tree.sql(dialect="postgres").lower()


def _short(place: str) -> str:
    """A place as the comparison's badges name it: a file's last two parts, or a database's name."""
    if place.startswith(ORIGIN_PREFIX):
        return "/".join(place.removeprefix(ORIGIN_PREFIX).partition("::")[0].split("/")[-2:])
    parts = place.removeprefix("db:").split("/")
    return parts[1] if len(parts) > 1 else parts[0]


def _find_table(catalog, base: str, key: str) -> str:
    """The path of a table or view `schema.table` inside a database or a file (any case); empty when it has none."""
    joined = f"{base}::{key}" if base.startswith(ORIGIN_PREFIX) else f"{base}/{key}"
    if catalog.object(joined) is not None:
        return joined
    held = catalog.objects(connection_id=base) if base.startswith(ORIGIN_PREFIX) else catalog.objects(within=base)
    return next((o["path"] for o in held if o["kind"] in _TABLES and _local_key(o["path"]).lower() == key.lower()), "")


def _table_lines(compared: dict, column: str = "") -> list[dict]:
    """Where a table (or one of its columns) differs, from `compare` of the table on both sides: its marked
    lines, whichever tab holds them (a column's: those that start with its name)."""
    lines = [line for tab in compared["tabs"].values() for table in tab["tables"] for line in table["lines"] if line["mark"]]
    if column:
        lines = [line for line in lines if line["text"].split(" ", 1)[0].lower() == column.lower()]
    return lines


def declared_by(path: str, origins: list[dict], catalog, connections: list[dict], root: Path) -> list[dict]:
    """The origins that declare a live table, view or column of a database they describe, with where
    they differ from it: the comparison of DATABASES › Diff (`compare`), on that table.

    Args:
        path: The live object's path (a table's, a view's or a column's).
        origins: The origins read.
        catalog: The databases read.
        connections: The project's connections.
        root: The project's root.

    Returns:
        Each origin's `origin`, `kind`, `object` (what it says of the object: `created`, `changed`,
        and a column's type, null and default), `names` (`a`: the origin's, `b`: the database's) and
        `lines` (`mark` - in the origin, + in the database, ~ the table's own change, and `text`: only
        those about this object).
    """
    found = catalog.object(path)
    if found is None:
        return []
    database = "/".join(path.split("/")[:2])
    column = found["kind"] == "column"
    table_path = found["parent"] if column else path
    key = _local_key(table_path)
    links = describe_origins(origins, catalog, connections, root)
    result = []
    for origin in origins:
        if database not in {link["database"] for link in links[origin["name"]]["links"]}:
            continue
        own = next((k for k in origin["objects"] if k.lower() == key.lower()), None)
        place = _find_table(catalog, f"{ORIGIN_PREFIX}{origin['name']}", key) if own else ""
        if not place:
            continue
        declared = origin["objects"][own]
        detail = {"created": declared["created"], "changed": declared["changed"], "kind": declared["kind"]}
        if column:
            mine = next((c for c in declared.get("columns", []) if c["name"].lower() == found["name"].lower()), None)
            if mine is None:
                continue
            detail = {"created": mine["created"], "changed": mine["changed"], "type": mine["type"], "nullable": mine["nullable"],
                      "default": mine["default"]}
        lines = _table_lines(compare(catalog, place, table_path), found["name"] if column else "")
        result.append({"origin": origin["name"], "kind": origin["kind"], "object": detail,
                       "names": {"a": _short(place), "b": _short(table_path)}, "lines": lines})
    return result


def found_in(path: str, origins: list[dict], catalog, connections: list[dict], root: Path) -> list[dict]:
    """The mirror of `declared_by`: where a table, view or column a file declares is, in the live
    databases its origin describes, with where they differ (the comparison of DATABASES › Diff).

    Args:
        path: What the file declares (`origin:<name>::<schema>.<object>`, a column's with `.<column>`).
        origins: The origins read.
        catalog: The databases read.
        connections: The project's connections.
        root: The project's root.

    Returns:
        For each linked database holding it: `database`, `how` (how the link was made, see
        `describe_origins`), `path` (the live object's), `names` (`a`: the origin's, `b`: the
        database's) and `lines` (as `declared_by` gives them, only those about this object).
    """
    found = catalog.object(path)
    name = path.removeprefix(ORIGIN_PREFIX).partition("::")[0]
    if found is None or not any(o["name"] == name for o in origins):
        return []
    column = found["kind"] == "column"
    table_path = found["parent"] if column else path
    key = _local_key(table_path)
    result = []
    for link in describe_origins(origins, catalog, connections, root)[name]["links"]:
        live = _find_table(catalog, link["database"], key)
        if not live:
            continue
        if column:
            held = next((c["path"] for c in (catalog.object(live) or {}).get("children", [])
                         if c["kind"] == "column" and c["name"].lower() == found["name"].lower()), "")
            if not held:
                continue
        lines = _table_lines(compare(catalog, table_path, live), found["name"] if column else "")
        result.append({"database": link["database"], "how": link["how"], "path": held if column else live,
                       "names": {"a": _short(table_path), "b": _short(live)}, "lines": lines})
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


# --- DATABASES › Diff: any two places compared, an origin's or a live database's, at any level.

_TABLES = ("table", "view", "materialized view", "foreign table")
_TOOL_TABLES = {"alembic_version", "django_migrations", "_prisma_migrations", "databasechangelog", "databasechangeloglock",
                "flyway_schema_history", "schema_migrations"}
_LEVELS = ("database", "schema", "table")
DIFF_TABS = (("only_a", "Only in A"), ("only_b", "Only in B"), ("different", "Differences"))
"""The tabs of DATABASES › Diff, by key: what only A holds, what only B holds, and what both hold differently."""


def place_level(place: str) -> str:
    """How deep a place of the SQL tree is: `server`, `database` (a whole origin is one), `schema` or `table`.

    Args:
        place: `origin:<name>[::<schema>[.<table>]]` or `db:<server>[/<database>[/<schema>[.<table>]]]`.
    """
    if place.startswith(ORIGIN_PREFIX):
        inner = place.partition("::")[2]
        return "table" if "." in inner else "schema" if inner else "database"
    parts = place.removeprefix("db:").split("/")
    return ("server", "database", "schema")[len(parts) - 1] if len(parts) < 3 or "." not in parts[2] else "table"


def _local_key(place: str) -> str:
    """A place's path inside its database: `schema` or `schema.table`; empty for a whole database."""
    if place.startswith(ORIGIN_PREFIX):
        return place.partition("::")[2]
    parts = place.removeprefix("db:").split("/", 2)
    return parts[2] if len(parts) == 3 else ""


def _collection(catalog, place: str) -> dict | None:
    """What a place holds, as a collection `schema_diff` reads (`objects`, `kind`: its SQL dialect); None
    when the store holds nothing there."""
    from doctracker.databases.readonly import DIALECTS

    if place.startswith(ORIGIN_PREFIX):
        held = catalog.objects(connection_id=place.partition("::")[0])
    else:
        held = catalog.objects(within="/".join(place.split("/")[:2]))
    key = _local_key(place)
    if key:
        inside = (f"{place}.", f"{place}:")
        held = [o for o in held if o["path"] == place or o["path"].startswith(inside)]
    if not held:
        return None
    kind = catalog.kinds().get(held[0]["connection"], "")
    return {"objects": held, "kind": DIALECTS.get(kind, kind)}


def _line(column: dict) -> str:
    """A column as a line of a table's schema: name, type, null and default."""
    side = column["a"] or column["b"]
    return f"{column['name']} {side['type'] or '-'}{'' if side['nullable'] else ' not null'}" + \
        (f" default {side['default']}" if side["default"] else "")


def _sided(column: dict, side: str) -> str:
    """A column as one side holds it."""
    return _line({**column, "a": column[side], "b": None})


def compare(catalog, a: str, b: str, root: Path | None = None, ignore: tuple[str, ...] | list[str] = ()) -> dict:
    """Where two places of the SQL tree differ: an origin's (its schema once every step is applied) or a
    live database's, a whole database, a schema or one table or view, on either side. Tables are matched
    by their name in the database (`schema.table`); two schemas or two tables of different names are
    compared with each other; a deeper place is compared with the same place inside the other side.
    What DATABASES › Diff and the MCP tool `database_diff` show (built on `evolution.schema_diff`).

    Args:
        catalog: The databases read and what the files declare (`CatalogStore`).
        a: Place A, e.g. `origin:examples/db/migrations` or `db:localhost:5432/shop/public.customers`.
        b: Place B.
        root: The project's root, to give each table the commits that changed it in an origin; none
            leaves them out.
        ignore: What the comparison leaves out: `checks`, `comments`, `indexes` (a profile's, see
            `diff_profiles.IGNORABLE`).

    Returns:
        `a`, `b`, their `levels`, `error` (why they cannot be compared, else empty) and `tabs`: for each key
        of `DIFF_TABS`, its `count` (objects) and `tables`, each with `key`, `kind`, `a` and `b` (its path on
        each side, or none), `whole` (the whole table is on one side only) and `lines` (`mark`: empty for a
        line the same on both sides, `-` A's, `+` B's, `~` a change of the table itself; `text`: a column or
        a key, index, check, comment) and, with `root`, `commits` (`hash`, `short`, `at`, `subject`, the
        newest first) and `origin` (the origin they changed).
    """
    from doctracker.databases.origins.evolution import schema_diff

    result = {"a": a, "b": b, "levels": [place_level(a), place_level(b)], "error": "",
              "tabs": {key: {"count": 0, "tables": []} for key, _ in DIFF_TABS}}
    if "server" in result["levels"]:
        result["error"] = "Choose a database (or a schema, a table) on both sides: a server holds several."
        return result
    first, second = _collection(catalog, a), _collection(catalog, b)
    if first is None or second is None:
        result["error"] = f"Nothing is read at {a if first is None else b}."
        return result
    depth_a, depth_b = _LEVELS.index(result["levels"][0]), _LEVELS.index(result["levels"][1])
    key_a, key_b = _local_key(a).lower(), _local_key(b).lower()
    align = None
    if depth_a == depth_b and key_a != key_b:
        align = (key_b, key_a)
    else:  # the broader side narrowed to the place the other one names
        narrow, key = (second, key_a) if depth_a > depth_b else (first, key_b)
        if key:
            narrow["objects"] = [o for o in narrow["objects"] if (_local_key(o["path"]).lower() + ".").startswith(f"{key}.")
                                 or _local_key(o["path"]).lower().startswith(f"{key}:")]
    tools = {name.lower() for name in HISTORY_TOOLS.values()} | _TOOL_TABLES  # the migration tools' own tables
    for collection in (first, second):
        dropped = {o["path"] for o in collection["objects"] if o["kind"] in _TABLES and o["name"].lower() in tools}
        collection["objects"] = [o for o in collection["objects"] if o["path"] not in dropped and o["parent"] not in dropped]
    found = schema_diff(first, second, align=align)
    left_out = tuple(prefix for key, prefix in (("checks", "check "), ("indexes", "index "), ("comments", "comment ")) if key in ignore)
    for table in found["tables"]:
        table["changes"] = [change for change in table["changes"] if not change.startswith(left_out)] if left_out else table["changes"]
        if table["status"] == "changed" and not table["changes"] and all(c["status"] == "same" for c in table["columns"]):
            table["status"] = "same"
    tabs = result["tabs"]
    files = _declared_files(first, second)
    for table in found["tables"]:
        if table["status"] == "same":
            continue
        head = {"key": table["key"], "kind": table["kind"], "a": table["a"], "b": table["b"],
                "files": files.get(table["a"], []) + files.get(table["b"], [])}
        if table["status"] in ("removed", "added"):
            tab, mark = ("only_a", "-") if table["status"] == "removed" else ("only_b", "+")
            tabs[tab]["tables"].append({**head, "whole": True, "lines": [{"mark": mark, "text": _line(c)} for c in table["columns"]]})
            tabs[tab]["count"] += 1
            continue
        both = [c for c in table["columns"] if c["status"] not in ("added", "removed")]
        for tab, status, mark, side in (("only_a", "removed", "-", "a"), ("only_b", "added", "+", "b")):
            own = [c for c in table["columns"] if c["status"] == status]
            changes = [change for change in table["changes"] if change.endswith(f" {status}")]
            if own or changes:
                lines = [{"mark": mark if c["status"] == status else "", "text": _line(c)}
                         for c in table["columns"] if c["status"] == status or c in both]
                lines += [{"mark": mark, "text": change.removesuffix(f" {status}")} for change in changes]
                tabs[tab]["tables"].append({**head, "whole": False, "lines": lines})
                tabs[tab]["count"] += len(own) + len(changes)
        changed = [c for c in both if c["status"] != "same"]
        others = [change for change in table["changes"] if not change.endswith((" added", " removed"))]
        if changed or others:
            lines = []
            for c in both:
                if c["status"] == "same":
                    lines.append({"mark": "", "text": _line(c)})
                else:
                    lines += [{"mark": "-", "text": _sided(c, "a")}, {"mark": "+", "text": _sided(c, "b")}]
            lines += [{"mark": "~", "text": change} for change in others]
            tabs["different"]["tables"].append({**head, "whole": False, "lines": lines})
            tabs["different"]["count"] += len(changed) + len(others)
    for entry in _other_objects(first, second, align, ignore):
        head = {**entry, "files": files.get(entry["a"], []) + files.get(entry["b"], [])}
        lines = head.pop("lines")
        if entry["status"] in ("removed", "added"):
            tab = "only_a" if entry["status"] == "removed" else "only_b"
            mark = "-" if tab == "only_a" else "+"
            tabs[tab]["tables"].append({**head, "whole": True, "lines": [{"mark": mark, "text": line} for line in lines]})
            tabs[tab]["count"] += 1
        else:
            tabs["different"]["tables"].append({**head, "whole": False, "lines": lines})
            tabs["different"]["count"] += 1
        head.pop("status")
    _commits(root, tabs)
    return result


_OTHERS = ("view", "materialized view", "function", "procedure", "aggregate", "trigger", "sequence", "enum", "type", "domain", "synonym")
"""The objects compared besides the tables' columns and keys: by what each kind says of itself (`_described`)."""


def _query(text: str, dialect: str) -> str:
    """A view's query out of its text (the whole `CREATE VIEW ... AS` an origin keeps, or the query alone a
    database gives), laid out one clause a line, the way `sql_key` compares it; the text itself when
    sqlglot cannot read it."""
    try:
        tree = sqlglot.parse_one(text, read=dialect)
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError, ValueError):
        return text.strip()
    if isinstance(tree, exp.Create) and tree.expression is not None:
        tree = tree.expression
    key = sql_key(tree.sql(dialect=dialect), dialect)
    try:
        return sqlglot.parse_one(key, read="postgres").sql(dialect="postgres", pretty=True).lower()
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError, ValueError):
        return key


def _body(text: str) -> str:
    """A routine's code: what its dollar quotes (or `BEGIN ... END`) hold, whichever way it was kept (the
    whole `CREATE FUNCTION` of a file, or the body a database gives)."""
    quoted = re.search(r"\$(\w*)\$(.*?)\$\1\$", text, re.S)
    if quoted:
        return quoted.group(2).strip()
    block = re.search(r"\bBEGIN\b.*\bEND\b", text, re.S | re.I)
    return (block.group(0) if block else text).strip()


def _described(obj: dict, dialect: str) -> list[tuple[str, str, str]]:
    """What an object other than a table says of itself, as `(what, shown, compared)`: a routine's arguments,
    returns, language and code, a trigger's definition, an enum's labels, a type's attributes, a domain's
    type and checks, a view's query (`compared`: the key the two sides are compared by)."""
    data, kind = obj["data"], obj["kind"]
    found = []
    if kind in ("view", "materialized view"):
        if data.get("definition"):
            query = _query(data["definition"], dialect)
            found.append(("query", query, query))
    elif kind in ("function", "procedure", "aggregate"):
        arguments = data.get("arguments") or (obj["name"].partition("(")[2].rstrip(")") if "(" in obj["name"] else "")
        if arguments:
            found.append(("arguments", arguments, _routine_key(f"f({arguments.lower()})")))
        for what, value in (("returns", data.get("returns") or ""), ("language", data.get("language") or "")):
            if value:
                found.append((what, value, re.sub(r"\s+", " ", value).strip().lower()))
        if data.get("definition"):
            body = _body(data["definition"])
            found.append(("code", body, re.sub(r"\s+", " ", body).strip().lower()))
    elif kind == "trigger":
        if data.get("definition"):
            said = re.sub(r"\s+", " ", data["definition"].replace('"', "")).strip().rstrip(";").lower()
            found.append(("definition", data["definition"], re.sub(r"\bon \S+ ", "on _ ", said, count=1)))  # a partition's copy names its own table
    elif kind == "enum":
        found.append(("labels", ", ".join(data.get("labels") or []), "|".join(data.get("labels") or [])))
    elif kind == "type":
        attributes = data.get("attributes") or []
        found += [("attribute", a, re.sub(r"\s+", " ", a).lower()) for a in attributes]
    elif kind == "domain":
        found.append(("type", data.get("type", ""), _type(str(data.get("type", "")), dialect).partition("(")[0]))  # some catalogs give no length
        found += [("check", c, sql_key(c, dialect)) for c in data.get("checks") or []]
    elif kind == "synonym" and data.get("target"):
        found.append(("target", data["target"], data["target"].lower()))
    for what in ("start", "increment", "minimum", "maximum"):
        if kind == "sequence" and data.get(what) is not None:
            found.append((what, str(data[what]), str(data[what])))
    return found


_TWO_WORD_TYPES = ("double", "character", "timestamp", "time", "bit", "national")


def _routine_key(key: str) -> str:
    """A routine as it is matched: its name and its arguments' types (`sales.f(customer bigint)` and
    `sales.f(IN customer bigint)` are one), the arguments' names and modes left out."""
    name, _, arguments = key.partition("(")
    if not arguments:
        return key
    types = []
    for argument in arguments.rstrip(")").split(","):
        words = argument.split()
        if words and words[0] in ("in", "out", "inout", "variadic"):
            words = words[1:]
        if len(words) > 1 and words[0] not in _TWO_WORD_TYPES:
            words = words[1:]
        types.append(" ".join(words))
    return f"{name}({', '.join(t for t in types if t)})"


def _other_objects(first: dict, second: dict, align: tuple[str, str] | None, ignore=()) -> list[dict]:
    """The objects other than tables of two places, matched by their path inside the database (B's
    renamed by `align`), each that differs as an entry of the tabs: `key`, `kind`, `a`, `b`, `status`
    (`removed`: only in A, `added`: only in B, `changed`) and its `lines` (a whole one's: `what value`;
    a changed one's: `{mark, text}`, a code or query line by line)."""
    import difflib

    def held(collection: dict, aligned: bool) -> dict[str, dict]:
        found = {}
        for obj in collection["objects"]:
            if obj["kind"] not in _OTHERS or obj["kind"] in _TABLES and obj["data"].get("definition") is None:
                continue
            key = _routine_key(_local_key(obj["path"]).lower()) if obj["kind"] in ("function", "procedure", "aggregate") \
                else _local_key(obj["path"]).lower()
            if aligned and align and (key == align[0] or key.startswith((f"{align[0]}.", f"{align[0]}:"))):
                key = align[1] + key[len(align[0]):]
            found[key] = obj
        return found

    in_a, in_b = held(first, False), held(second, True)
    kinds_a, kinds_b = {o["kind"] for o in in_a.values()}, {o["kind"] for o in in_b.values()}
    entries = []
    for key in sorted(set(in_a) | set(in_b)):
        one, other = in_a.get(key), in_b.get(key)
        entry = {"key": key, "kind": (one or other)["kind"], "a": one and one["path"], "b": other and other["path"]}
        if one is None or other is None:
            if entry["kind"] in _TABLES:  # a view on one side only is told with the tables
                continue
            if entry["kind"] not in (kinds_a if one is None else kinds_b):  # a side that reads no object of this kind says nothing of it
                continue
            obj, dialect = (other, second["kind"]) if one is None else (one, first["kind"])
            lines = []
            for what, shown, _ in _described(obj, dialect):
                lines += [f"{what}: {line}" if i == 0 else f"  {line}" for i, line in enumerate(shown.splitlines() or [""])]
            entries.append({**entry, "status": "added" if one is None else "removed", "lines": lines or [entry["kind"]]})
            continue
        said_a, said_b = _described(one, first["kind"]), _described(other, second["kind"])
        if "checks" in ignore:  # a domain's checks left out
            said_a, said_b = [s for s in said_a if s[0] != "check"], [s for s in said_b if s[0] != "check"]
        lines = []
        for what in dict.fromkeys([w for w, _, _ in said_a] + [w for w, _, _ in said_b]):
            here = [(s, c) for w, s, c in said_a if w == what]
            there = [(s, c) for w, s, c in said_b if w == what]
            if not here or not there or [c for _, c in here] == [c for _, c in there]:
                continue  # the same, or said by one side only (a database that gives no code): not compared
            if what in ("code", "query"):
                old, new = here[0][0].splitlines(), there[0][0].splitlines()
                for line in difflib.ndiff(old, new):
                    if line[:1] in ("-", "+", " "):
                        lines.append({"mark": line[:1].strip(), "text": f"{what}: {line[2:]}"})
            else:
                lines += [{"mark": "-", "text": f"{what}: {s}"} for s, _ in here]
                lines += [{"mark": "+", "text": f"{what}: {s}"} for s, _ in there]
        if lines:
            entries.append({**entry, "status": "changed", "lines": lines})
    return entries


def _declared_files(*collections: dict) -> dict[str, list[str]]:
    """The files declaring each table of an origin, by the table's path: those that created or changed it
    or one of its columns."""
    found: dict[str, set[str]] = {}
    for collection in collections:
        for obj in collection["objects"]:
            if not obj["path"].startswith(ORIGIN_PREFIX) or obj["kind"] not in (*_TABLES, *_OTHERS, "column"):
                continue
            table = obj["parent"] if obj["kind"] == "column" else obj["path"]
            for when in ("created", "changed"):
                if file := ((obj["data"].get("declared") or {}).get(when) or {}).get("file"):
                    found.setdefault(table, set()).add(file)
    return {table: sorted(names) for table, names in found.items()}


def _commits(root: Path | None, tabs: dict) -> None:
    """Give each table of the tabs the commits of its files (`git log`, read only), in one reading."""
    from doctracker.databases.origins.evolution import _git_log

    tables = [table for tab in tabs.values() for table in tab["tables"]]
    for table in tables:
        files = table.pop("files")
        table["origin"] = next((p.removeprefix(ORIGIN_PREFIX).partition("::")[0] for p in (table["a"], table["b"])
                                if p and p.startswith(ORIGIN_PREFIX)), "")
        table["commits"], table["_files"] = [], set(files)
    wanted = sorted({file for table in tables for file in table["_files"]})
    log = _git_log(root, wanted) if root and wanted else []
    for table in tables:
        own = table.pop("_files")
        table["commits"] = [{k: c[k] for k in ("hash", "short", "at", "subject")} for c in reversed(log) if own & set(c["files"])]


def default_b(a: str, origins: list[dict], catalog, connections: list[dict], root: Path) -> dict:
    """What place A is compared with at first: for an origin's place, the same place in the database the
    origin created (by its history table, its configuration, or an ORM's models through its migrations).

    Args:
        a: Place A.
        origins: The origins read.
        catalog: The databases read.
        connections: The project's connections.
        root: The project's root.

    Returns:
        `b` (empty when none is known), `how` (how the database was found, see `describe_origins`),
        `history` (what the tool's history table in it says, or none) and `suggestions` (the databases its
        tables' names suggest, the closest first).
    """
    if not a.startswith(ORIGIN_PREFIX):
        return {"b": "", "how": [], "history": None, "suggestions": []}
    name = a.removeprefix(ORIGIN_PREFIX).partition("::")[0]
    described = describe_origins(origins, catalog, connections, root).get(name) or {"links": [], "suggestions": []}
    ranked = sorted(described["links"], key=lambda link: (not link["history"], "declared" not in link["how"]))
    suggestions = [s["database"] for s in described["suggestions"]]
    if not ranked:
        return {"b": "", "how": [], "history": None, "suggestions": suggestions}
    link, key = ranked[0], _local_key(a)
    return {"b": link["database"] + (f"/{key}" if key else ""), "how": link["how"], "history": link["history"],
            "suggestions": suggestions}
