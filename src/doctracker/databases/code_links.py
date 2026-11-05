"""Which code uses each table and column of the databases, found by reading the code, never running it.

Four ways lead from the code to a table:

- an ORM's model declares it (`maps`): the class to its table, each attribute to its column, from the
  mapping the ORM's reader gives (`orm.read`);
- SQL written inside a Python string, read by sqlglot (`reads`, `writes`): an f-string's parts the code
  fills in make it `partial`;
- a `.sql` file that declares nothing (queries, data), each statement by its line;
- code naming a model class or one of its attributes (`through model`), resolved as the code graph
  resolves names (`extraction.graph`), the use being `likely` since the code may never reach the database.

The links name their tables as the code writes them; which live table or file's table each one reaches
is worked out when it is asked for (`code_use`, `database_use`), since the databases change while the
code stays. One function serves the object's page and the MCP tool `database_object` (`code_use`), and
its mirror the code entity's page and `get_entity` (`database_use`).
"""

import ast
import re
from pathlib import Path

import sqlglot
from sqlglot import exp

from doctracker.databases.origins.compare import found_in
from doctracker.databases.origins.sql import split_statements
from doctracker.extraction.graph import _dotted, _functions, _parse, _Resolver, _Scope

USES = ("maps", "reads", "writes", "through model")
"""What a piece of code does with a table or column: declares it as an ORM model, reads it or writes it
in SQL, or names the model holding it."""

_HOLE = "doctracker_hole"
"""What stands for each part of an f-string filled in by the code while its SQL is read."""

_LOOKS_SQL = re.compile(r"^\s*(?:--[^\n]*\n\s*)*(SELECT|INSERT|UPDATE|DELETE|WITH|MERGE)\b[\s\S]*\b(FROM|INTO|SET|USING)\b",
                        re.IGNORECASE)
"""A string that may be a query: one starting with a statement's word and holding a table's place."""

_DIALECTS = (None, "postgres", "mysql", "tsql", "sqlite")
"""The SQL dialects a string is read in, one after the other until one reads it."""

_WRITES = (exp.Insert, exp.Update, exp.Delete, exp.Merge)
"""The statements writing to the table they name first."""

_TABULAR = ("table", "view", "materialized view", "foreign table")
"""The kinds of object that hold columns."""


def extract_links(root: Path, files: list[str], entities: dict[str, dict], origins: list[dict]) -> list[dict]:
    """Find every link between the project's code and the tables and columns it uses.

    Args:
        root: The project's root.
        files: The project's files, relative to the root.
        entities: Every entity extracted, by path.
        origins: The origins read (`origins.extract_origins`), an ORM's with its `mapping`.

    Returns:
        One link per code entity, table, column and use: `entity` (its path, or the file of a query
        file or a schema with no entity), `file`, `line` (the first), `lines` (every line of that use),
        `table` (as written: `schema.name` or `name`, lower case), `column` (empty for the table),
        `origin` and `object` (an ORM's: the origin and the path of what it declares), `use` (see
        `USES`), `evidence` (the statement or the line) and `confidence` (`certain`, `partial`, `likely`).
    """
    found: dict[tuple, dict] = {}

    def add(entity: str, file: str, line: int, table: str, column: str, use: str, evidence: str, confidence: str,
            origin: str = "", path: str = "") -> None:
        key = (entity, table, column.lower(), use, origin)
        if key in found:
            if line not in found[key]["lines"]:
                found[key]["lines"].append(line)
            return
        found[key] = {"entity": entity, "file": file, "line": line, "lines": [line], "table": table, "column": column,
                      "origin": origin, "object": path, "use": use, "evidence": evidence, "confidence": confidence}

    classes = {(_relative(root, e["filepath"]), e["name"]): path for path, e in entities.items()
               if e["kind"] == "class" and e.get("language") == "python"}
    models: dict[str, tuple] = {}  # class path → (origin, its table's path, table)
    for origin in origins:
        for mapped in origin.get("mapping", []):
            key = _object_key(origin, mapped["table"])
            if key is None:
                continue
            columns = {c["name"].lower(): c["name"] for c in origin["objects"][key].get("columns", [])}
            table_path = f"origin:{origin['name']}::{key}"
            owner = classes.get((mapped["file"], mapped["class"].rsplit(".", 1)[-1]))
            entity = owner or mapped["file"]
            add(entity, mapped["file"], mapped["line"], key, "", "maps", f"{mapped['class'].rsplit('.', 1)[-1]} → {key}",
                "certain", origin["name"], table_path)
            if owner:
                models[owner] = (origin["name"], table_path, key)
            for attribute, column in mapped["columns"].items():
                name = columns.get(column.lower(), column)
                member = f"{owner}.{attribute}" if owner and f"{owner}.{attribute}" in entities else ""
                add(member or entity, mapped["file"], entities[member]["lineno"] if member else mapped["line"], key, name, "maps",
                    f"{attribute} → {key}.{name}", "certain", origin["name"], f"{table_path}.{name}")
                if member:
                    models[member] = (origin["name"], f"{table_path}.{name}", key, name)

    resolver = _Resolver(entities)
    for path, entity in entities.items():
        if entity["kind"] == "module" and entity["filepath"].endswith(".py"):
            tree = _parse(root / entity["filepath"])
            if tree is not None:
                lines = (root / entity["filepath"]).read_text(encoding="utf-8", errors="replace").splitlines()
                _python_links(path, _relative(root, entity["filepath"]), tree, lines, resolver, models, add)

    declaring = {file for origin in origins for step in origin["steps"] for file in (step["file"], step.get("down"))}
    for file in files:
        if file.lower().endswith(".sql") and file not in declaring:
            try:
                text = (root / file).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line, statement in split_statements(text, "postgres"):
                if not _LOOKS_SQL.match(statement):  # what declares (a down migration's DROP, ALTER) is no use of a table
                    continue
                for table, column, use in _sql_uses(statement):
                    add(file, file, line, table, column, use, _short(statement), "certain")
    return list(found.values())


def _relative(root: Path, filepath: str) -> str:
    """A file's path relative to the project's root, with forward slashes."""
    try:
        return Path(filepath).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return Path(filepath).as_posix()


def _object_key(origin: dict, table: str) -> str | None:
    """What an origin declares under a table's name as its ORM writes it (`customers`, `sales.customers`)."""
    table = table.lower()
    return next((key for key in origin["objects"] if key.lower() == table or key.lower().partition(".")[2] == table), None)


def _short(text: str) -> str:
    """A statement or line as evidence: on one line, at most 300 characters."""
    one = " ".join(text.split())
    return one if len(one) <= 300 else one[:299] + "…"


def _python_links(module: str, file: str, tree: ast.Module, lines: list[str], resolver: _Resolver, models: dict[str, tuple],
                  add) -> None:
    """Find the links of one Python module: SQL inside its strings and the models it names.

    Args:
        module: Path of the module.
        file: Its file, relative to the root.
        tree: Its syntax tree.
        lines: Its source, line by line.
        resolver: Name resolution for the whole project.
        models: What each model class and model attribute declares: `(origin, path, table)` and, for an
            attribute, its column too.
        add: Where each link found goes (see `extract_links`).
    """
    bodies =[(path, owner, function) for function, path, owner in _functions(tree, module, None) if path in resolver.entities]
    bodies.append((module, None, ast.Module(body=[node for node in tree.body if not isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))], type_ignores=[])))
    for path, owner, body in bodies:
        nodes = list(ast.walk(body))
        docstrings = {id(node.value) for node in nodes if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)}
        inside = {id(part) for node in nodes if isinstance(node, ast.JoinedStr) for part in node.values}
        named = {id(node.value): f"{path}.{node.targets[0].id}" for node in body.body  # a constant's string: the constant's
                 if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                 and f"{path}.{node.targets[0].id}" in resolver.entities} if path == module else {}
        for node in nodes:
            if isinstance(node, ast.JoinedStr):
                text = "".join(part.value if isinstance(part, ast.Constant) else _HOLE for part in node.values)
                confidence = "partial"
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings | inside:
                text, confidence = node.value, "certain"
            else:
                continue
            if _LOOKS_SQL.match(text):
                for table, column, use in _sql_uses(text):
                    add(named.get(id(node), path), file, node.lineno, table, column, use, _short(text.replace(_HOLE, "{…}")), confidence)
        if not models:
            continue
        scope = _Scope(resolver, module, owner, path)
        for node in nodes:
            scope._learn(node)
        for node in nodes:
            if not isinstance(node, (ast.Name, ast.Attribute)) or isinstance(getattr(node, "ctx", None), ast.Store):
                continue
            parts = _dotted(node)
            used = scope._resolve(parts) if parts else None
            if used in models and used != path:
                origin, target, table, *column = models[used]
                evidence = lines[node.lineno - 1].strip() if 0 < node.lineno <= len(lines) else ".".join(parts)
                add(path, file, node.lineno, table, column[0] if column else "", "through model", _short(evidence),
                    "likely", origin, target)


def _sql_uses(text: str) -> list[tuple[str, str, str]]:
    """The tables and columns a piece of SQL uses, and how.

    Args:
        text: One or more statements; an f-string's parts the code fills in stand as `_HOLE`.

    Returns:
        `(table, column, use)` each once: `table` as written (`schema.name` or `name`, lower case), `column`
        empty for the table itself, `use` `writes` for the table a statement writes to and the columns it
        sets, `reads` for the rest. Nothing when no dialect reads the text.
    """
    statements = None
    for dialect in _DIALECTS:
        try:
            statements = sqlglot.parse(text, read=dialect)
            break
        except Exception:  # sqlglot's errors, and what it raises on text it does not foresee
            continue
    found: dict[tuple[str, str, str], None] = {}
    for statement in statements or []:
        if statement is None:
            continue
        ctes = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
        tables = [t for t in statement.find_all(exp.Table) if t.name and t.name.lower() not in ctes and _HOLE not in t.name]
        if not tables:
            continue
        written = None
        if isinstance(statement, _WRITES):
            target = statement.this if isinstance(statement.this, exp.Table) else statement.this.find(exp.Table) \
                if statement.this is not None else None
            written = id(target) if target is not None else None
        names = {}
        for table in tables:
            name = (f"{table.db}.{table.name}" if table.db and _HOLE not in table.db else table.name).lower()
            names[table.alias_or_name.lower()] = name
            names.setdefault(table.name.lower(), name)
            found[(name, "", "writes" if id(table) == written else "reads")] = None
        target_name = next((names[t.alias_or_name.lower()] for t in tables if id(t) == written), "")
        set_columns = set()
        if target_name and isinstance(statement, exp.Insert) and isinstance(statement.this, exp.Schema):
            set_columns = {e.name.lower() for e in statement.this.expressions if e.name}
        elif target_name and isinstance(statement, exp.Update):
            set_columns = {e.this.name.lower() for e in statement.expressions if isinstance(e, exp.EQ) and isinstance(e.this, exp.Column)}
        for column in set_columns:
            found[(target_name, column, "writes")] = None
        read = {names[t.alias_or_name.lower()] for t in tables if id(t) != written}  # what a column without its table comes from
        if not isinstance(statement, exp.Insert):
            read |= {target_name} - {""}
        other_sources = any(isinstance(alias.parent, (exp.Subquery, exp.Func, exp.Unnest, exp.Values))
                            for alias in statement.find_all(exp.TableAlias))
        single = next(iter(read)) if len(read) == 1 and not other_sources else ""
        for column in statement.find_all(exp.Column):
            if not column.name or column.name == "*" or _HOLE in column.name:
                continue
            table = names.get(column.table.lower(), "") if column.table else single
            if table and not (table == target_name and column.name.lower() in set_columns):
                found[(table, column.name.lower(), "reads")] = None
    return list(found)


def _table_of(path: str) -> tuple[str, str]:
    """A table's schema and name from its path (`db:<server>/<database>/<schema>.<name>`, `origin:<name>::<schema>.<name>`)."""
    key = path.rpartition("::")[2] if path.startswith("origin:") else path.rpartition("/")[2]
    schema, _, name = key.rpartition(".")
    return schema.lower(), name.lower()


def _database_of(path: str) -> str:
    """The database (or file) an object's path lies in."""
    return path.partition("::")[0] if path.startswith("origin:") else "/".join(path.split("/")[:2])


def _named(link: dict, schema: str, name: str) -> bool:
    """Whether a table as the code writes it names a table of this schema and name (a name without schema: any schema)."""
    written_schema, _, written = link["table"].rpartition(".")
    return written == name and (not written_schema or written_schema == schema)


def _same_name(catalog, link: dict) -> list[str]:
    """The tables, views and the files' tables holding the name a link writes, by path."""
    written_schema, _, written = link["table"].rpartition(".")
    return [o["path"] for o in catalog.objects(name=written, origins=True)
            if o["kind"] in _TABULAR and o["name"].lower() == written
            and (not written_schema or _table_of(o["path"])[0] == written_schema)]


def code_use(path: str, found: dict, links: list[dict], origins: list[dict], catalog, connections: list[dict], root: Path) -> list[dict]:
    """The code that uses a table, view or column: what the object's page shows in "Use in the code".

    Args:
        path: The object's path (a live one's or a file's).
        found: The object, as `CatalogStore.object` gives it.
        links: The links found in the code (`extract_links`).
        origins: The origins read.
        catalog: The databases read, and what the files declare.
        connections: The project's connections.
        root: The project's root.

    Returns:
        One row per link reaching it (a table's also those of its columns): the link (see
        `extract_links`) with `how` (`declared by <origin>` and `through <origin>` for an ORM's, `by
        name` for SQL) and `databases` (how many databases or files hold a table of that name, for SQL).
    """
    column = found["kind"] == "column"
    if not column and found["kind"] not in _TABULAR:
        return []
    table_path = found["parent"] if column else path
    schema, name = _table_of(table_path)
    reaches: dict[str, bool] = {}

    def reached(link: dict) -> bool:  # an ORM's table: this one, or where it is in the databases its origin describes
        table = link["object"].removesuffix(f".{link['column']}") if link["column"] else link["object"]
        if table not in reaches:
            reaches[table] = table == table_path or any(d["path"] == table_path for d in found_in(table, origins, catalog, connections, root))
        return reaches[table]

    rows = []
    for link in links:
        if column and link["column"].lower() != found["name"].lower():
            continue
        if link["origin"]:
            if link["table"].rpartition(".")[2] == name and reached(link):
                rows.append({**link, "how": f"{'declared by' if link['use'] == 'maps' else 'through'} {link['origin']}", "databases": 0})
        elif _named(link, schema, name):
            rows.append({**link, "how": "by name", "databases": len({_database_of(p) for p in _same_name(catalog, link)})})
    return sorted(rows, key=lambda row: (row["column"], row["file"], row["line"]))


def database_use(entity: str, links: list[dict], origins: list[dict], catalog, connections: list[dict], root: Path) -> list[dict]:
    """The tables and columns a code entity uses, its members' too: the mirror of `code_use`.

    Args:
        entity: The entity's path (or a query file's).
        links: The links found in the code (`extract_links`).
        origins: The origins read.
        catalog: The databases read, and what the files declare.
        connections: The project's connections.
        root: The project's root.

    Returns:
        One row per link of it that reaches some table: the link (see `extract_links`) with `how` (as
        in `code_use`) and `objects`, the paths it reaches (a column's when it names one): for an ORM's,
        what its origin declares and where that is in the databases it describes; for SQL, every table of
        that name.
    """
    rows = []
    for link in links:
        if link["entity"] != entity and not link["entity"].startswith(f"{entity}."):
            continue
        if link["origin"]:
            table = link["object"].removesuffix(f".{link['column']}") if link["column"] else link["object"]
            tables = [table] + [d["path"] for d in found_in(table, origins, catalog, connections, root)]
            how = f"{'declared by' if link['use'] == 'maps' else 'through'} {link['origin']}"
        else:
            tables, how = _same_name(catalog, link), "by name"
        if not tables:
            continue
        if link["column"]:
            columns = {o["parent"]: o["path"] for o in catalog.objects(kind="column", name=link["column"], origins=True)
                       if o["name"].lower() == link["column"].lower()}
            objects = [columns[t] for t in tables if t in columns]
        else:
            objects = tables
        if objects:
            rows.append({**link, "how": how, "objects": sorted(dict.fromkeys(objects))})
    return sorted(rows, key=lambda row: (row["line"], row["table"], row["column"]))


__all__ = ["USES", "code_use", "database_use", "extract_links"]
