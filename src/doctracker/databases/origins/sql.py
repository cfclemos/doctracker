"""Read the project's SQL files into the schema each origin ends with.

Find the origins (migration sets of Flyway, golang-migrate and dbmate; any other `.sql` file declaring
schema), cut each file into statements, read each statement with sqlglot in the origin's dialect and,
where its grammar leaves a raw command, by our own rules; apply the steps in order into one schema,
every object remembering the file and line that created it and the last that changed it.
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path

import sqlglot
from sqlglot import exp

from doctracker.databases.origins import dumps, orm

logging.getLogger("sqlglot").setLevel(logging.ERROR)  # its notes on statements it keeps as raw commands


DEFAULT_SCHEMAS = {"postgres": "public", "tsql": "dbo", "sqlite": "main", "mysql": ""}
"""The schema of a name written without one, per dialect (MySQL: the database itself, unknown here)."""


_DDL = re.compile(r"^\s*(CREATE|ALTER|DROP|COMMENT\s+ON|RENAME\s+TABLE)\b", re.IGNORECASE | re.MULTILINE)
"""A statement that declares schema."""


_FLYWAY = re.compile(r"^V(?P<version>\d+(?:[._]\d+)*)__(?P<name>.+)\.sql$", re.IGNORECASE)
"""A Flyway migration: `V<version>__<name>.sql`."""

_PRISMA = re.compile(r"^(?P<version>(?P<stamp>\d{8,})_(?P<name>.+))/migration\.sql$", re.IGNORECASE)
"""A Prisma migration: `migrations/<timestamp>_<name>/migration.sql`."""

_GOLANG = re.compile(r"^(?P<version>\d+)_(?P<name>.+)\.(?P<way>up|down)\.sql$", re.IGNORECASE)
"""A golang-migrate step: `<version>_<name>.up.sql`, its undo `.down.sql`."""

_DBMATE = re.compile(r"^--\s*migrate:(up|down)\b", re.IGNORECASE | re.MULTILINE)
"""A dbmate migration's parts, in one file."""

_TOOL_DIALECTS = {"pg_dump": "postgres", "pg_dumpall": "postgres", "mysqldump": "mysql", "mariadb-dump": "mysql", "sqlite3": "sqlite",
                  "iterdump": "sqlite", "ssms": "tsql"}
"""The dialect a dump is written in, by the tool that wrote it."""

_GO = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)
"""T-SQL's batch separator, on a line of its own."""


def guess_dialect(text: str) -> str:
    """The SQL dialect a file is written in, from its marks: a dump's own header first, then T-SQL, MySQL,
    SQLite, else PostgreSQL."""
    if re.search(r"^--\s*PostgreSQL database dump", text, re.MULTILINE):
        return "postgres"
    if re.search(r"^--\s*(MySQL|MariaDB) dump", text, re.MULTILINE):
        return "mysql"
    if _GO.search(text) or re.search(r"(?<!AS )\bIDENTITY\s*\(\s*\d|\bNVARCHAR\b|\[\w+\]\.\[|\bsp_addextendedproperty\b", text, re.IGNORECASE):
        return "tsql"
    if "`" in text or re.search(r"\bAUTO_INCREMENT\b|\bENGINE\s*=|\bDELIMITER\b", text, re.IGNORECASE):
        return "mysql"
    if re.search(r"\bAUTOINCREMENT\b|\bWITHOUT ROWID\b|^PRAGMA\b", text, re.IGNORECASE | re.MULTILINE):
        return "sqlite"
    return "postgres"


def find_origins(root: Path, files: list[str]) -> list[dict]:
    """Group the project's SQL files into origins.

    Args:
        root: The project's root.
        files: The project's files, relative to the root (`config.project_files`).

    Returns:
        Each origin's `name` (its folder for a migration set, its file otherwise; one database of a dump
        holding several: `<file>@<database>`), `kind` (`flyway`, `golang-migrate`, `dbmate`, `prisma
        migrations`, `dump`, `sql file`), `folder`, and `steps` in order: `file`, `version`, `title`, and
        `down` (the file undoing it, golang-migrate) when there is one. A dump also has `tool`, `dump`
        (what it writes of itself, see `dumps.header`), `generated` (`dumps.generated`), `dialect_hint`,
        and, for one database of several, `part_of` (the file) and `lines` (its first and last).
    """
    texts: dict[str, str] = {}
    for file in files:
        if file.lower().endswith(".sql"):
            try:
                texts[file] = (root / file).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    sets: dict[tuple[str, str], list[dict]] = {}
    alone = []
    downs: dict[tuple[str, str], str] = {}
    for file, text in texts.items():
        folder, name = str(Path(file).parent.as_posix()), Path(file).name
        if Path(file).parent.parent.name == "migrations" and (match := _PRISMA.match(f"{Path(file).parent.name}/{name}")):
            sets.setdefault(("prisma migrations", str(Path(file).parent.parent.as_posix())), []).append(
                {"file": file, "version": match["version"], "title": match["name"].replace("_", " ")})
        elif match := _FLYWAY.match(name):
            sets.setdefault(("flyway", folder), []).append({"file": file, "version": match["version"].replace("_", "."),
                                                            "title": match["name"].replace("_", " ")})
        elif match := _GOLANG.match(name):
            if match["way"].lower() == "down":
                downs[(folder, match["version"])] = file
            else:
                sets.setdefault(("golang-migrate", folder), []).append(
                    {"file": file, "version": match["version"], "title": match["name"].replace("_", " ")})
        elif _DBMATE.search(text):
            stem = Path(name).stem
            version, _, title = stem.partition("_")
            sets.setdefault(("dbmate", folder), []).append({"file": file, "version": version, "title": title.replace("_", " ")})
        elif _DDL.search(text):
            tool = dumps.recognise(text)
            if tool is None:
                alone.append({"name": file, "kind": "sql file", "folder": folder, "steps": [{"file": file, "version": "", "title": name}]})
                continue
            written = dumps.header(text, tool)
            dump = {"kind": "dump", "folder": folder, "steps": [{"file": file, "version": "", "title": name}], "tool": tool,
                    "dump": written, "generated": dumps.generated(root, file, written), "dialect_hint": _TOOL_DIALECTS[tool]}
            parts = dumps.sections(text, tool)
            for part in parts:  # a dump of several databases: one origin each, its own lines
                alone.append({**dump, "name": f"{file}@{part['database']}", "part_of": file, "lines": [part["first"], part["last"]],
                              "dump": {**written, "database": {"value": part["database"], "line": part["first"]}}})
            if not parts:
                alone.append({**dump, "name": file})
    origins = []
    for (kind, folder), steps in sorted(sets.items(), key=lambda item: item[0][1]):
        steps.sort(key=lambda step: [int(part) if part.isdigit() else part for part in re.split(r"[._]", step["version"])])
        for step in steps:
            if kind == "golang-migrate" and (folder, step["version"]) in downs:
                step["down"] = downs[(folder, step["version"])]
        origins.append({"name": folder, "kind": kind, "folder": folder, "steps": steps})
    return origins + sorted(alone, key=lambda origin: origin["name"])


def split_statements(text: str, dialect: str) -> list[tuple[int, str]]:
    """Cut a file's SQL into statements, each with the line it starts on.

    The dialect's own tokenizer finds the semicolons (so none inside a string or a function body
    counts); T-SQL's `GO` lines end a statement too; dbmate's `-- migrate:down` part is left out, and so
    are the rows of a dump's `COPY … FROM stdin` (no SQL; `dumps.rows` reads them).

    Returns:
        `(line, text)` of each statement, in order.
    """
    if (cut := re.search(r"^--\s*migrate:down\b", text, re.IGNORECASE | re.MULTILINE)):
        text = text[:cut.start()]
    text = dumps.COPY_DATA.sub(lambda match: match[1] + re.sub(r"[^\n]", " ", match["data"]), text)  # rows, blanked
    # psql's own commands (\set, \connect, \restrict...) are no SQL: blanked, keeping the lines where they are.
    text = re.sub(r"^\\.*$", lambda match: " " * len(match.group(0)), text, flags=re.MULTILINE)
    if re.search(r"^\s*DELIMITER\s+\S+", text, re.IGNORECASE | re.MULTILINE):
        return _split_delimited(text)
    text = _GO.sub(lambda match: ";".ljust(len(match.group(0))), text)
    try:
        tokens = sqlglot.Dialect.get_or_raise(dialect).tokenize(text)
    except Exception:  # a text its tokenizer cannot follow: cut at the semicolons ending a line
        statements, start = [], 0
        for match in re.finditer(r";[ \t]*$", text, re.MULTILINE):
            statements.append((text.count("\n", 0, start) + 1, text[start:match.end()]))
            start = match.end()
        statements.append((text.count("\n", 0, start) + 1, text[start:]))
        return [(line, chunk.strip()) for line, chunk in statements if chunk.strip(" ;\n\t")]
    statements, first = [], None
    for token in tokens:
        if token.token_type == sqlglot.TokenType.SEMICOLON:
            if first is not None:
                statements.append((first.line, text[first.start:token.end + 1].strip()))
            first = None
        elif first is None:
            first = token
    if first is not None:
        statements.append((first.line, text[first.start:].strip()))
    return _join_bodies(statements)


_QUOTED = re.compile(r"(\$\w*\$).*?\1|'(?:[^']|'')*'|\"[^\"]*\"|--[^\n]*|/\*.*?\*/", re.DOTALL)
"""Strings, quoted identifiers, PostgreSQL's dollar-quoted bodies and comments."""

_TRANSACTION = re.compile(r"\s*(BEGIN|START)(\s+(WORK|TRAN|TRANSACTION))?(\s+ISOLATION\s+LEVEL\s+[\w ]+)?\s*;?\s*", re.IGNORECASE)
"""A statement only starting a transaction (`BEGIN;`, `START TRANSACTION;`): it opens no BEGIN … END body."""


def _join_bodies(statements: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Put back together a trigger's or routine's BEGIN ... END body cut at its inner semicolons."""
    joined: list[tuple[int, str]] = []
    depth = 0
    for line, text in statements:
        code = _QUOTED.sub(" ", text)  # a word in a string, a quoted body or a comment opens nothing
        if depth == 0 and _TRANSACTION.fullmatch(code):  # BEGIN; alone starts a transaction (an Alembic offline script…)
            joined.append((line, text))
            continue
        opens = len(re.findall(r"\bBEGIN\b(?!\s+TRANSACTION)", code, re.IGNORECASE)) + len(re.findall(r"\bCASE\b", code, re.IGNORECASE))
        closes = len(re.findall(r"\bEND\b", code, re.IGNORECASE))
        if depth > 0:
            joined[-1] = (joined[-1][0], f"{joined[-1][1]}\n{text}")
        else:
            joined.append((line, text))
        depth = max(0, depth + opens - closes)
    return joined


def _split_delimited(text: str) -> list[tuple[int, str]]:
    """Cut MySQL SQL that changes its delimiter (`DELIMITER ;;`, a dump's routines and triggers)."""
    statements, delimiter, current, start = [], ";", [], 1
    for number, line in enumerate(text.splitlines(), 1):
        if match := re.match(r"^\s*DELIMITER\s+(\S+)\s*$", line, re.IGNORECASE):
            delimiter = match[1]
            continue
        if not current:
            start = number
        current.append(line)
        if line.rstrip().endswith(delimiter):
            chunk = "\n".join(current).rstrip()[: -len(delimiter)].strip()
            if chunk:
                statements.append((start, chunk))
            current = []
    if "".join(current).strip():
        statements.append((start, "\n".join(current).strip()))
    return statements


def _name(table: exp.Expression | None) -> tuple[str, str]:
    """The schema and name a table expression gives (schema empty when not written)."""
    if table is None:
        return "", ""
    if isinstance(table, exp.Schema):
        table = table.this
    return (table.args.get("db").name if table.args.get("db") else ""), (table.name if hasattr(table, "name") else str(table))


def _plain(name: str) -> str:
    """A name written in a rule's match, without its quotes or brackets."""
    return name.strip().strip('"`[]')


class _Schema:
    """The schema an origin builds, statement after statement.

    Attributes:
        dialect: The SQL dialect the origin is read in.
        objects: By `schema.name` (lower case), each object: `kind`, `schema`, `name`, `created` and
            `changed` (`file` and `line`), and what its kind holds (a table's columns, keys,
            constraints, indexes; a view's definition and what it reads...).
    """

    def __init__(self, dialect: str, default: str | None = None) -> None:
        self.dialect = dialect
        self.default = DEFAULT_SCHEMAS.get(dialect, "") if default is None else default  # a name written without schema is in it
        self.objects: dict[str, dict] = {}
        self.servers: dict[str, dict] = {}  # PostgreSQL's foreign servers, by name: their options (host, port, dbname)

    def key(self, schema: str, name: str) -> str:
        """An object's key: its schema (the dialect's default when not written) and name, in lower case."""
        return f"{schema or self.default}.{name}".lower()

    def put(self, kind: str, schema: str, name: str, place: dict, **data) -> dict:
        """Create an object, or take its place (CREATE OR REPLACE); a function, procedure, domain, type or
        sequence also gets what its definition says of it (see `_details`)."""
        schema = schema or self.default
        if kind in _DETAILED and data.get("definition"):
            data = {**_details(kind, data["definition"], self.dialect), **data}
        before = self.objects.get(self.key(schema, name))
        found = {"kind": kind, "schema": schema, "name": name, "created": place, "changed": place, **data}
        if before is not None and before["kind"] == kind:  # CREATE OR REPLACE: the same object, changed
            found["created"] = before["created"]
            if before.get("comment") and not found.get("comment"):
                found["comment"] = before["comment"]
        self.objects[self.key(schema, name)] = found
        return found

    def get(self, schema: str, name: str) -> dict | None:
        """An object by its schema and name; a name without schema found in any schema when only one has it."""
        found = self.objects.get(self.key(schema, name))
        if found is None and not schema:
            matches = [o for o in self.objects.values() if o["name"].lower() == name.lower()]
            found = matches[0] if len(matches) == 1 else None
        return found

    def table(self, schema: str, name: str, place: dict) -> dict:
        """A table to change: the one known, or one made from the change alone (its CREATE not read)."""
        found = self.get(schema, name)
        if found is None:
            found = self.put("table", schema, name, place, columns=[], primary_key=[], foreign_keys=[],
                             unique=[], checks=[], indexes=[], comment="", partial=True)
        for part, empty in (("columns", []), ("primary_key", []), ("foreign_keys", []), ("unique", []), ("checks", []),
                            ("indexes", []), ("comment", "")):
            found.setdefault(part, list(empty) if isinstance(empty, list) else empty)
        found["changed"] = place
        return found


_SERIALS = {"serial": "integer", "serial4": "integer", "bigserial": "bigint", "serial8": "bigint", "smallserial": "smallint",
            "serial2": "smallint"}
"""PostgreSQL's serial types: an integer, not null, numbered by a sequence (as the database then shows it)."""


def _serial(column: dict) -> dict:
    """A serial column as the database keeps it: its integer type, not null, numbered by the database."""
    if (base := _SERIALS.get(column["type"].lower())) is not None:
        column.update(type=base, nullable=False, identity=True, serial=True)
    return column


_DEFAULT_END = re.compile(r"\s+(NOT\s+NULL|NULL|PRIMARY\s+KEY|UNIQUE|REFERENCES|CHECK|CONSTRAINT|GENERATED|COLLATE|COMMENT|"
                          r"ON\s+UPDATE|AUTO_INCREMENT|AUTOINCREMENT)\b", re.IGNORECASE)
"""Where a default written in a column's definition ends: the next of its constraints."""


def _as_written(node: exp.Expression, source: str, dialect: str, clause: bool = True, bare: bool = True) -> str:
    """An expression as the file writes it (`now()`, not sqlglot's `CURRENT_TIMESTAMP`), from where its
    first token starts to the end of the clause (a default ends at the next constraint; with `clause`
    False, only at the parenthesis closing it, as a check's, without the parentheses around it all
    unless `bare` is False); written back by sqlglot when its place is not known."""
    starts = [n.meta["start"] for n in node.walk() if isinstance(n, exp.Expression) and "start" in n.meta]
    if not source or not starts:
        return node.sql(dialect)
    if not clause:  # what the parentheses opening before it hold: from the last keyword (CHECK, AS) on
        keyword = max(m.end() for m in re.finditer(r"\b(CHECK|AS)\s*", source[:min(starts)], re.IGNORECASE)) \
            if re.search(r"\b(CHECK|AS)\s*\(", source[:min(starts)], re.IGNORECASE) else -1
        if keyword >= 0:
            inner, _ = _parenthesised(source[keyword:])
            inner = inner.strip()
            while bare and inner.startswith("(") and _parenthesised(inner)[1].strip() == "":
                inner = _parenthesised(inner)[0].strip()
            return " ".join(inner.split()) or node.sql(dialect)
    at, depth, quote = min(starts), 0, ""
    if at > 0 and source[at - 1] in "'\"":  # a string's token starts after its quote
        at -= 1
    for end in range(at, len(source)):
        char = source[end]
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and (char in ",;" or (clause and _DEFAULT_END.match(source, end))):
            break
    else:
        end = len(source)
    return source[at:end].strip() or node.sql(dialect)


_TYPE_END = re.compile(r"\s*(,|\)|$|\b(NOT|NULL|PRIMARY|UNIQUE|REFERENCES|CHECK|CONSTRAINT|GENERATED|COLLATE|DEFAULT|AS|ON|"
                       r"AUTO_INCREMENT|AUTOINCREMENT|COMMENT|CHARACTER\s+SET|CHARSET|SRID|VISIBLE|INVISIBLE|VIRTUAL|STORED|"
                       r"COLUMN_FORMAT|STORAGE)\b)", re.IGNORECASE)
"""Where a type written after a column's name ends: a comma, the table's parenthesis, or a constraint."""


def _written_type(definition: exp.ColumnDef, source: str) -> str:
    """A column's type as the statement writes it (`numeric`, `varchar(14)`), from just after its name to
    its first constraint; empty when its place in the statement is not known."""
    end = definition.this.meta.get("end") if isinstance(definition.this, exp.Identifier) else None
    if not source or end is None:
        return ""
    text, at, depth = source[end + 1:].lstrip(" \t\"`]"), 0, 0
    while at < len(text):
        if text[at] == "(":
            depth += 1
        elif text[at] == ")":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and _TYPE_END.match(text, at) and (at == 0 or not text[at - 1].isalnum() or text[at] in ",)"):
            break
        at += 1
    return " ".join(text[:at].split())

def _column(definition: exp.ColumnDef, dialect: str, place: dict, source: str = "") -> dict:
    """A column as a ColumnDef declares it, with what its own constraints say (its default as the file
    writes it, `source` being the statement read)."""
    kind = definition.args.get("kind")
    written = _written_type(definition, source) if kind is not None and dialect in ("sqlite", "mysql") else ""
    column = {"name": definition.name, "type": (written or kind.sql(dialect)) if kind is not None else "",  # as written: the database's own spelling from it
              "nullable": True, "default": "", "computed": "", "identity": False, "pk": False, "unique": False,
              "references": None, "check": "", "comment": "", "created": place, "changed": place}
    for constraint in definition.args.get("constraints") or []:
        kind = constraint.args.get("kind")
        if isinstance(kind, exp.NotNullColumnConstraint):
            column["nullable"] = bool(kind.args.get("allow_null"))
            column["not_null"] = not column["nullable"]  # written so (SQLite: a key alone does not forbid null)
        elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
            column.update(pk=True, nullable=False)
        elif isinstance(kind, exp.UniqueColumnConstraint):
            column["unique"] = True
        elif isinstance(kind, exp.DefaultColumnConstraint):
            column["default"] = _as_written(kind.this, source, dialect)
        elif isinstance(kind, exp.GeneratedAsIdentityColumnConstraint) and kind.args.get("expression") is not None:
            # GENERATED ALWAYS AS (expr) without STORED: a computed column (PostgreSQL 18's virtual one), no identity
            column["computed"] = _as_written(kind.args["expression"], source, dialect, clause=False, bare=False)
        elif isinstance(kind, (exp.GeneratedAsIdentityColumnConstraint, exp.AutoIncrementColumnConstraint)):
            column["identity"] = True
        elif isinstance(kind, exp.ComputedColumnConstraint):
            column["computed"] = _as_written(kind.this, source, dialect, clause=False, bare=False)
        elif isinstance(kind, exp.CheckColumnConstraint):
            column["check"] = _as_written(kind.this, source, dialect, clause=False)
            column["check_name"] = constraint.name
        elif isinstance(kind, exp.CommentColumnConstraint):
            column["comment"] = kind.this.name if isinstance(kind.this, exp.Literal) else kind.this.sql(dialect)
        elif isinstance(kind, exp.Reference):
            schema, table = _name(kind.this)
            column["references"] = {"schema": schema, "table": table,
                                    "columns": [c.name for c in kind.this.expressions] if isinstance(kind.this, exp.Schema) else [],
                                    "options": [str(o) for o in kind.args.get("options") or []]}
    return _serial(column)


def _constraint(table: dict, item: exp.Expression, dialect: str, source: str = "", name: str = "") -> str:
    """Add a table-level constraint (primary key, unique, foreign key, check) to a table; say what it was.
    The name the file gives it (`CONSTRAINT <name>`) goes in the table's `names` (`pk`, `unique:<columns>`,
    `check:<text>`; a foreign key keeps its own)."""
    names = table.setdefault("names", {})
    if isinstance(item, exp.Constraint):
        return "; ".join(_constraint(table, inner, dialect, source, item.name) for inner in item.expressions)
    if isinstance(item, exp.PrimaryKey):
        table["primary_key"] = [c.name for c in item.expressions]
        if name:
            names["pk"] = name
        for column in table["columns"]:
            if column["name"] in table["primary_key"]:
                column.update(pk=True, nullable=False)
        return f"primary key ({', '.join(table['primary_key'])})"
    if isinstance(item, exp.UniqueColumnConstraint):
        columns = [c.name for c in (item.this.expressions if isinstance(item.this, exp.Schema) else [])]
        table["unique"].append(columns)
        name = name or (item.this.this.name if isinstance(item.this, exp.Schema) and isinstance(item.this.this, exp.Identifier) else "")
        if name:  # CONSTRAINT x UNIQUE (...), MySQL's UNIQUE KEY x (...)
            names[f"unique:{','.join(columns)}"] = name
        return f"unique ({', '.join(columns)})"
    if isinstance(item, exp.ForeignKey):
        reference = item.args["reference"]
        schema, target = _name(reference.this)
        key = {"columns": [c.name for c in item.expressions], "schema": schema, "table": target,
               "target_columns": [c.name for c in reference.this.expressions] if isinstance(reference.this, exp.Schema) else [],
               "options": [str(o) for o in reference.args.get("options") or []], "name": name}
        table["foreign_keys"].append(key)
        return f"foreign key ({', '.join(key['columns'])}) → {target}"
    if isinstance(item, exp.IndexColumnConstraint):  # MySQL's KEY / INDEX / FULLTEXT / SPATIAL x (...) inside the table
        columns = []
        for part in item.expressions:
            inner = part.this if isinstance(part, exp.Ordered) else part
            columns.append(inner.name if isinstance(inner, exp.Column) else inner.sql(dialect))
        table["indexes"].append({"name": item.name, "columns": columns, "unique": False})
        return f"index {item.name} ({', '.join(columns)})"
    if isinstance(item, exp.ExcludeColumnConstraint):  # PostgreSQL's exclusion constraint: kept by an index of its name
        parameters = item.this
        columns = [c.name for c in (parameters.find_all(exp.Column) if parameters else [])]
        table["indexes"].append({"name": name, "columns": columns, "unique": False})
        return f"exclusion ({', '.join(columns)})"
    if isinstance(item, exp.CheckColumnConstraint):
        check = _as_written(item.this, source, dialect, clause=False)
        table["checks"].append(check)
        if name:
            names[f"check:{check}"] = name
        return "check"
    return ""


def _add_column(table: dict, column: dict) -> None:
    """Put a column in its table, with the keys and constraints its own definition declares."""
    table["columns"].append(column)
    if column["pk"]:
        table["primary_key"] = table["primary_key"] + [column["name"]]
    if column["unique"]:
        table["unique"].append([column["name"]])
    if column["references"]:
        reference = column["references"]
        table["foreign_keys"].append({"columns": [column["name"]], "schema": reference["schema"], "table": reference["table"],
                                      "target_columns": reference["columns"], "options": reference["options"]})
    if column["check"]:
        table["checks"].append(column["check"])
        if column.get("check_name"):
            table.setdefault("names", {})[f"check:{column['check']}"] = column["check_name"]


def _create_table(schema: _Schema, statement: exp.Create, place: dict, source: str = "", without_rowid: bool = False) -> list[str]:
    """CREATE TABLE: its columns and constraints; a partition or a child table names its parent (and a
    partition its bounds), a partitioned table how it is partitioned."""
    owner, name = _name(statement.this)
    table = schema.put("table", owner, name, place, columns=[], primary_key=[], foreign_keys=[], unique=[], checks=[],
                       indexes=[], comment="")
    for item in statement.this.expressions if isinstance(statement.this, exp.Schema) else []:
        if isinstance(item, exp.Identifier):  # a column written with its name alone (SQLite: no type)
            item = exp.ColumnDef(this=item)
        if isinstance(item, exp.ColumnDef):
            _add_column(table, _column(item, schema.dialect, place, source))
        else:
            _constraint(table, item, schema.dialect, source)
    for prop in (statement.args.get("properties") or exp.Properties(expressions=[])).expressions:
        if isinstance(prop, exp.PartitionedByProperty):
            table["partitioning"] = prop.this.sql(schema.dialect)
        if isinstance(prop, exp.PartitionedOfProperty):
            table["partition_of"] = list(_name(prop.this))
            if bound := re.search(r"\bPARTITION\s+OF\s+[\w.\"]+\s+(FOR\s+VALUES\b.*?|DEFAULT)\s*(?:PARTITION\s+BY\b.*)?;?\s*$", source,
                                  re.IGNORECASE | re.DOTALL):
                table["partition_bound"] = " ".join(bound[1].split())
        elif isinstance(prop, exp.InheritsProperty):
            table["inherits"] = [list(_name(parent)) for parent in prop.expressions]
        elif isinstance(prop, exp.SchemaCommentProperty):
            table["comment"] = prop.this.name
    if schema.dialect == "sqlite" and not without_rowid:  # SQLite: a key's column may hold null unless NOT NULL is written
        for column in table["columns"]:
            if column["pk"] and not column.get("not_null"):
                column["nullable"] = True
    return [f"created table {table['schema']}.{name}" if table["schema"] else f"created table {name}"]


def _named(dialect: str, table: str, what: str, columns: list[str], position: int = 0) -> str | None:
    """The name the database gives by itself to a constraint the file does not name: PostgreSQL's
    `<table>_pkey`, `<table>_<columns>_key`, `<table>_<columns>_fkey`; MySQL's `PRIMARY`, a unique
    key's first column, `<table>_ibfk_<n>`; none for the others."""
    if dialect == "postgres":
        return {"pk": f"{table}_pkey", "unique": f"{table}_{'_'.join(columns)}_key", "fk": f"{table}_{'_'.join(columns)}_fkey"}[what]
    if dialect == "mysql":
        return {"pk": "PRIMARY", "unique": columns[0] if columns else None, "fk": f"{table}_ibfk_{position}"}[what]
    return None


def _check_name(dialect: str, table: str, check: str) -> str | None:
    """The name PostgreSQL gives by itself to a check the file does not name: `<table>_<column>_check`
    when it tests one column, else `<table>_check`; none for the others."""
    if dialect != "postgres":
        return None
    try:
        tested = sorted({c.name for c in sqlglot.parse_one(check, read=dialect).find_all(exp.Column)})
    except Exception:
        tested = []
    return f"{table}_{tested[0]}_check" if len(tested) == 1 else f"{table}_check"


def _freeze_names(schema: _Schema, table: dict) -> None:
    """Before a table or one of its columns is renamed, write down the names the database gave by itself
    to its constraints and serial sequences: it keeps them after the rename (`customers_code_key` stays
    so when `code` becomes `sku`)."""
    names, dialect, name = table.setdefault("names", {}), schema.dialect, table["name"]
    if table["primary_key"] and not names.get("pk"):
        names["pk"] = _named(dialect, name, "pk", table["primary_key"])
    for columns in table["unique"]:
        if not names.get(f"unique:{','.join(columns)}"):
            names[f"unique:{','.join(columns)}"] = _named(dialect, name, "unique", columns)
    for position, key in enumerate(table["foreign_keys"], 1):
        key["name"] = key.get("name") or _named(dialect, name, "fk", key["columns"], position)
    for check in table["checks"]:
        if not names.get(f"check:{check}"):
            names[f"check:{check}"] = _check_name(dialect, name, check)
    for column in table["columns"]:
        if column.get("identity") and not column.get("sequence"):  # a serial's or an identity's
            column["sequence"] = f"{name}_{column['name']}_seq"


def _rename_column(schema: _Schema, table: dict, old: str, new: str, place: dict) -> None:
    """Rename a column where the database follows it: the column, its table's keys, uniques, checks and
    indexes, and the foreign keys of every table pointing to it; the names the database had given keep."""
    def same(columns: list[str]) -> list[str]:
        return [new if c.lower() == old.lower() else c for c in columns]

    _freeze_names(schema, table)
    word = re.compile(rf"(?<![\w.])[\"`\[]?{re.escape(old)}[\"`\]]?(?!\w)", re.IGNORECASE)
    names = table["names"]
    for columns in table["unique"]:
        if (given := names.pop(f"unique:{','.join(columns)}", None)) is not None:
            names[f"unique:{','.join(same(columns))}"] = given
    checks = []
    for check in table["checks"]:
        renamed = word.sub(new, check)  # the database rewrites the check with the column's new name
        if (given := names.pop(f"check:{check}", None)) is not None:
            names[f"check:{renamed}"] = given
        checks.append(renamed)
    table["checks"] = checks
    for column in table["columns"]:
        if column["name"].lower() == old.lower():
            column.update(name=new, changed=place)
    table["primary_key"] = same(table["primary_key"])
    table["unique"] = [same(columns) for columns in table["unique"]]
    for index in table["indexes"]:
        index["columns"] = same(index["columns"])
    for key in table["foreign_keys"]:
        key["columns"] = same(key["columns"])
    for other in schema.objects.values():
        for key in other.get("foreign_keys") or []:
            if schema.get(key["schema"], key["table"]) is table:
                key["target_columns"] = same(key["target_columns"])


def _alter_table(schema: _Schema, statement: exp.Alter, place: dict, source: str = "") -> list[str]:
    """ALTER TABLE: columns added, changed, renamed or dropped; constraints added; the table renamed."""
    owner, name = _name(statement.this)
    table = schema.table(owner, name, place)
    effects = []
    for action in statement.args.get("actions") or []:
        if isinstance(action, exp.ColumnDef):
            table["columns"] = [c for c in table["columns"] if c["name"].lower() != action.name.lower()]
            _add_column(table, _column(action, schema.dialect, place, source))
            effects.append(f"added column {action.name} to {name}")
        elif isinstance(action, exp.Drop) and str(action.args.get("kind", "")).upper() == "COLUMN":
            gone = {c.name.lower() for c in action.args.get("tables") or []}
            table["columns"] = [c for c in table["columns"] if c["name"].lower() not in gone]
            effects.append(f"dropped column {', '.join(sorted(gone))} from {name}")
        elif isinstance(action, exp.RenameColumn):
            _rename_column(schema, table, action.this.name, action.args["to"].name, place)
            effects.append(f"renamed column {action.this.name} to {action.args['to'].name} in {name}")
        elif isinstance(action, exp.AlterColumn):
            for column in table["columns"]:
                if column["name"].lower() == action.name.lower():
                    if action.args.get("dtype"):
                        column["type"] = action.args["dtype"].sql(schema.dialect)
                    if action.args.get("allow_null") is not None:
                        column["nullable"] = bool(action.args["allow_null"])
                    if action.args.get("default"):
                        column["default"] = _as_written(action.args["default"], source, schema.dialect)
                    if action.args.get("drop"):
                        column["default"] = ""
                    column["changed"] = place
            effects.append(f"changed column {action.name} of {name}")
        elif isinstance(action, exp.AddConstraint):
            effects += [f"added {what} to {name}" for item in action.expressions if (what := _constraint(table, item, schema.dialect, source))]
        elif isinstance(action, exp.AlterRename) and (column := re.search(
                r"\bRENAME\s+(?!TO\b|COLUMN\b|CONSTRAINT\b)([\w\"`\[\]]+)\s+TO\s+([\w\"`\[\]]+)", source, re.IGNORECASE)):
            # RENAME a TO b (COLUMN left out, as PostgreSQL allows and Alembic writes): sqlglot reads a table rename
            old, new = _plain(column[1]), _plain(column[2])
            _rename_column(schema, table, old, new, place)
            effects.append(f"renamed column {old} to {new} in {name}")
        elif isinstance(action, exp.AlterRename):
            new_schema, new_name = _name(action.this)
            _freeze_names(schema, table)  # its constraints and sequences keep the names they were given
            for other in schema.objects.values():  # the foreign keys pointing to it follow it
                for key in other.get("foreign_keys") or []:
                    if schema.get(key["schema"], key["table"]) is table:
                        key.update(table=new_name, schema=new_schema or table["schema"])
            schema.objects.pop(schema.key(table["schema"], table["name"]), None)
            table.update(name=new_name, schema=new_schema or table["schema"])
            schema.objects[schema.key(table["schema"], new_name)] = table
            effects.append(f"renamed table {name} to {new_name}")
        else:
            effects.append(f"changed {name}")
    return effects


_SQLITE_SCHEMA_ROW = re.compile(r"^\s*INSERT\s+INTO\s+\"?sqlite_(?:master|schema)\"?\s*\(type,\s*name,\s*tbl_name,\s*rootpage,\s*sql\)\s*"
                                r"VALUES\s*\('\w+',\s*'(?:[^']|'')*',\s*'(?:[^']|'')*',\s*\d+,\s*'(?P<sql>(?:[^']|'')*)'\)\s*;?\s*$",
                                re.IGNORECASE | re.DOTALL)
"""A row Python's `iterdump()` writes into SQLite's own schema table: how it dumps a virtual table."""


def _apply(schema: _Schema, text: str, place: dict) -> tuple[list[str], bool]:
    """Apply one statement to the schema.

    Returns:
        What it did (`created table sales.orders`...), and whether it was read (by sqlglot or by our
        rules); a statement neither reads is left out of the schema and kept as "not read".
    """
    if (row := _SQLITE_SCHEMA_ROW.match(text)) is not None:  # the statement the row holds
        return _apply(schema, row["sql"].replace("''", "'"), place)
    text = re.sub(r"(/\*!\d+\s+|\*/)", " ", text)  # MySQL's versioned comments hold real SQL: kept, unwrapped
    text = re.sub(r"^(\s*(--[^\n]*(\n|$)|/\*.*?\*/))+", "", text, flags=re.DOTALL).strip()  # the comments before it
    if not text:
        return [], True
    if schema.dialect == "mysql" and (use := re.fullmatch(r"(?i)\s*USE\s+`?([\w$]+)`?\s*;?\s*", text)):
        schema.default = use[1]  # MySQL: a name written without its database is in the one in use
        return [f"used database {use[1]}"], True
    if schema.dialect == "mysql" and (created := re.match(r"\s*CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w.`]+)", text, re.IGNORECASE)):
        table_text, partitioning = _mysql_partitioning(text)
        table_text = re.sub(r"\s+SRID\s+\d+\b", "", table_text, flags=re.IGNORECASE)  # a spatial column's: outside sqlglot's grammar
        if table_text != text:  # what sqlglot does not read taken out, read apart
            done, read = _apply(schema, table_text, place)
            parts = [_plain(part) for part in created[1].split(".")]
            if read and partitioning and (table := schema.get(parts[0] if len(parts) > 1 else "", parts[-1])) is not None:
                table.update(partitioning)
            return done, read
    parsed = re.sub(r"\)\s*(WITHOUT\s+ROWID|STRICT)(\s*,\s*(WITHOUT\s+ROWID|STRICT))*\s*;?\s*$", ")", text, flags=re.IGNORECASE)
    try:
        statement = sqlglot.parse_one(parsed, read=schema.dialect)
    except Exception:  # outside sqlglot's grammar altogether: our rules only
        statement = None
    if isinstance(statement, exp.Create):
        kind = str(statement.args.get("kind") or "").upper()
        if kind == "TABLE" and not isinstance(statement.this, exp.Schema) and not statement.args.get("properties") \
                and not statement.expression:
            return _rules(schema, text, place)
        if kind == "TABLE":
            return _create_table(schema, statement, place, parsed, bool(re.search(r"\)\s*(?:STRICT\s*,\s*)?WITHOUT\s+ROWID", text, re.IGNORECASE))), True
        if kind == "VIEW":
            owner, name = _name(statement.this)
            query = statement.expression
            reads = _reads(query)
            materialized = any(isinstance(p, exp.MaterializedProperty) for p in (statement.args.get("properties") or exp.Properties(expressions=[])).expressions) \
                or re.match(r"\s*CREATE\s+(OR\s+REPLACE\s+)?MATERIALIZED", text, re.IGNORECASE)
            names = [n for n in (query.named_selects if isinstance(query, (exp.Select, exp.SetOperation)) else []) if n and n != "*"]
            schema.put("materialized view" if materialized else "view", owner, name, place, definition=text, reads=reads,
                       columns=[{"name": n, "type": "", "nullable": True, "default": "", "computed": "", "identity": False,
                                 "pk": False, "unique": False, "references": None, "check": "", "comment": "",
                                 "created": place, "changed": place} for n in names])
            return [f"created view {name}"], True
        if kind == "INDEX":
            index = statement.this
            owner, table_name = _name(index.args.get("table"))
            table = schema.table(owner, table_name, place)
            params = index.args.get("params")
            columns = [_as_written(c, parsed, schema.dialect) for c in (params.args.get("columns") or [])] if params else []
            table["indexes"].append({"name": index.name, "columns": [_plain(c.split(" ")[0]) for c in columns],
                                     "unique": bool(statement.args.get("unique"))})
            return [f"created index {index.name} on {table_name}"], True
        if kind in ("FUNCTION", "PROCEDURE"):
            owner, name = _name(statement.this.this if isinstance(statement.this, (exp.UserDefinedFunction, exp.StoredProcedure))
                                else statement.this)
            if not name:  # a form sqlglot reads without its name: our rules find it in the text
                return _rules(schema, text, place)
            schema.put(kind.lower(), owner, name, place, definition=text)
            return [f"created {kind.lower()} {name}"], True
        if kind in ("SEQUENCE", "SCHEMA", "TYPE", "TRIGGER"):
            owner, name = _name(statement.this)
            if kind == "SCHEMA":
                return [f"created schema {name or owner}"], True
            if kind == "TRIGGER":
                return _trigger(schema, text, place)
            schema.put(kind.lower(), owner, name, place, definition=text)
            return [f"created {kind.lower()} {name}"], True
    if isinstance(statement, exp.Alter) and str(statement.args.get("kind", "")).upper() == "TABLE":
        return _alter_table(schema, statement, place, parsed), True
    if isinstance(statement, exp.Drop):
        kind = str(statement.args.get("kind") or "").upper()
        gone = []
        for table in statement.args.get("tables") or [statement.this]:
            owner, name = _name(table)
            if schema.objects.pop(schema.key(owner, name), None) is not None or name:
                gone.append(name)
        return [f"dropped {kind.lower()} {', '.join(gone)}"], True
    if isinstance(statement, exp.Comment):
        kind = str(statement.args.get("kind") or "").upper()
        text_ = statement.expression.name if isinstance(statement.expression, exp.Literal) else ""
        target = statement.this
        if kind == "COLUMN":
            table_name = target.table if hasattr(target, "table") else ""
            owner = target.args.get("db").name if target.args.get("db") else ""
            found = schema.get(owner, table_name)
            for column in (found or {}).get("columns", []):
                if column["name"].lower() == target.name.lower():
                    column["comment"] = text_
            return [f"commented column {table_name}.{target.name}"], True
        owner, name = _name(target)
        if not name and (routine := re.match(r"^\s*COMMENT\s+ON\s+(?:FUNCTION|PROCEDURE|AGGREGATE)\s+([\w.\"]+)\s*\(", text, re.IGNORECASE)):
            parts = [_plain(part) for part in routine[1].split(".")]  # sqlglot reads a routine's signature without its name
            owner, name = (parts[0] if len(parts) > 1 else ""), parts[-1]
        found = schema.get(owner, name)
        if found is not None:
            found["comment"] = text_
        return [f"commented {kind.lower()} {name}"], True
    return _rules(schema, text, place)


_RULES = [
    ("domain", re.compile(r"^\s*CREATE\s+DOMAIN\s+(?P<name>[\w.\"]+)", re.IGNORECASE)),
    ("type", re.compile(r"^\s*CREATE\s+TYPE\s+(?P<name>[\w.\"]+)", re.IGNORECASE)),
    ("function", re.compile(r"^\s*CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?(?:DEFINER\s*=\s*\S+\s+)?FUNCTION\s+(?P<name>[\w.\"`\[\]]+)", re.IGNORECASE)),
    ("procedure", re.compile(r"^\s*CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?(?:DEFINER\s*=\s*\S+\s+)?PROC(?:EDURE)?\s+(?P<name>[\w.\"`\[\]]+)", re.IGNORECASE)),
    ("aggregate", re.compile(r"^\s*CREATE\s+(?:OR\s+REPLACE\s+)?AGGREGATE\s+(?P<name>[\w.\"]+)", re.IGNORECASE)),
    ("view", re.compile(r"^\s*CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?(?:ALGORITHM\s*=\s*\w+\s+)?(?:DEFINER\s*=\s*\S+\s+)?(?:SQL\s+SECURITY\s+\w+\s+)?(?P<materialized>MATERIALIZED\s+)?VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[\w.\"`\[\]]+)", re.IGNORECASE)),
    ("sequence", re.compile(r"^\s*CREATE\s+SEQUENCE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[\w.\"]+)", re.IGNORECASE)),
    ("synonym", re.compile(r"^\s*CREATE\s+SYNONYM\s+(?P<name>[\w.\[\]]+)", re.IGNORECASE)),
]
"""Our rules for what sqlglot leaves as a raw command: the kind of object and where its name is."""


_IGNORED = re.compile(r"^\s*(ANALYZE|VACUUM|REFRESH\s+MATERIALIZED\s+VIEW|ALTER\s+FOREIGN\s+TABLE|ALTER\s+TABLE\s+(ONLY\s+)?[\w.\"`]+\s+(ENABLE|DISABLE|FORCE|NO\s+FORCE|OWNER|REPLICA|CLUSTER)\b|CREATE\s+(DEFINER\s*=\s*\S+\s+)?EVENT|COMMENT\s+ON\s+(OPERATOR|EXTENSION|COLLATION|SERVER|PUBLICATION|SUBSCRIPTION|POLICY|RULE|TEXT\s+SEARCH|CAST|SCHEMA|DATABASE|ROLE|EVENT)|ALTER\s+TEXT\s+SEARCH|CREATE\s+(PARTITION\s+(FUNCTION|SCHEME)|SECURITY\s+POLICY|EXTENSION|ROLE|USER|DATABASE|PUBLICATION|SUBSCRIPTION|SERVER|USER\s+MAPPING|POLICY|RULE|STATISTICS|EVENT\s+TRIGGER|OPERATOR|CAST|COLLATION|TEXT\s+SEARCH|TABLESPACE|EVENT|LOGIN|FOREIGN\s+DATA)|GRANT|REVOKE|SET|USE|SELECT|INSERT|UPDATE|DELETE|COPY|BEGIN|COMMIT|START|LOCK|UNLOCK|DELIMITER|PRAGMA|EXEC|EXECUTE|IF\s|PRINT|DECLARE|\\\\|ALTER\s+(DEFAULT\s+PRIVILEGES|ROLE|USER|DATABASE|SEQUENCE|SCHEMA|EXTENSION|FUNCTION|PROCEDURE|TYPE|DOMAIN|VIEW|MATERIALIZED|INDEX|PUBLICATION|SUBSCRIPTION|SERVER|POLICY)|SELECT\s+pg_catalog|DROP\s+(EXTENSION|ROLE|USER|DATABASE|POLICY|RULE|EVENT|PUBLICATION|SUBSCRIPTION))\b", re.IGNORECASE)
"""Statements that hold no schema object of the drawing (roles, grants, settings, data, sessions...): read, nothing to record."""


_DETAILED = ("function", "procedure", "aggregate", "domain", "type", "sequence")
"""The kinds whose properties are read from their definition's text."""


_ROUTINE_HEAD = re.compile(r"^\s*CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?(?:DEFINER\s*=\s*\S+\s+)?(?:FUNCTION|PROC(?:EDURE)?|AGGREGATE)\s+[\w.\"`\[\]]+\s*",
                           re.IGNORECASE)


_RETURNS_END = re.compile(r"\s+(?:AS\b|LANGUAGE\b|BEGIN\b|(?:NOT\s+)?DETERMINISTIC\b|READS\b|MODIFIES\b|NO\s+SQL\b|CONTAINS\b|COMMENT\b|"
                          r"IMMUTABLE\b|STABLE\b|VOLATILE\b|STRICT\b|SECURITY\b|RETURN\b|WITH\b|PARALLEL\b|COST\b|SET\b|CALLED\b|\$)",
                          re.IGNORECASE)


def _parenthesised(text: str) -> tuple[str, str]:
    """What the parentheses opening `text` hold, and what follows them ("" and `text` when it opens none)."""
    if not text.startswith("("):
        return "", text
    depth = 0
    for at, char in enumerate(text):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0:
            return text[1:at], text[at + 1:]
    return text[1:], ""


def _details(kind: str, text: str, dialect: str) -> dict:
    """What a definition says of a function, procedure, domain, type or sequence, under the names a live
    database's reading gives (`arguments`, `returns`, `language`, `comment`; a domain's `type`,
    `nullable`, `default`, `checks`; an enum's `labels`; a sequence's `start`, `increment`); what it
    does not say is left out."""
    found: dict = {}
    one = lambda pattern, where=text: (m[1].strip() if (m := re.search(pattern, where, re.IGNORECASE | re.DOTALL)) else "")
    if kind == "aggregate":
        head = _ROUTINE_HEAD.match(text)
        found["arguments"] = " ".join(_parenthesised(text[head.end():] if head else "")[0].split())
        found["returns"] = one(r"\bSTYPE\s*=\s*([\w.\"]+)")
        found["language"] = "internal" if dialect == "postgres" else ""  # as PostgreSQL gives an aggregate's
        return {key: value for key, value in found.items() if value}
    if kind in ("function", "procedure"):
        head = _ROUTINE_HEAD.match(text)
        rest = text[head.end():] if head else text
        arguments, rest = _parenthesised(rest)
        if not arguments and dialect == "tsql":  # CREATE PROC name @a int, @b int AS ...
            arguments = one(r"^(.*?)\s+(?:WITH\s+\w+\s+)?AS\b", rest)
        found["arguments"] = " ".join(arguments.split())
        body = re.split(r"\bAS\s+\$|\bBEGIN\b|\bAS\b", rest, maxsplit=1, flags=re.IGNORECASE)[0] if dialect != "postgres" else rest
        if match := re.search(r"\bRETURNS\s+", body, re.IGNORECASE):
            after = body[match.end():]
            if re.match(r"TABLE\s*\(", after, re.IGNORECASE):
                inner, _ = _parenthesised(after[after.index("("):])
                found["returns"] = f"TABLE({' '.join(inner.split())})"
            else:
                end = _RETURNS_END.search(" " + after)
                found["returns"] = " ".join((after[:end.start() - 1] if end else after).split())
        found["language"] = (one(r"\bLANGUAGE\s+'?(\w+)", body if dialect != "postgres" else text)
                             or ("sql" if dialect in ("mysql", "tsql") else "")).lower()
        found["comment"] = one(r"\bCOMMENT\s+'((?:[^']|'')*)'", body).replace("''", "'")
    elif kind == "domain":
        found["type"] = one(r"\bDOMAIN\s+[\w.\"]+\s+(?:AS\s+)?(.+?)(?=\s+(?:NOT\s+NULL|NULL|DEFAULT|CHECK|CONSTRAINT|COLLATE)\b|\s*;?\s*$)")
        found["nullable"] = not re.search(r"\bNOT\s+NULL\b", text, re.IGNORECASE)
        found["default"] = one(r"\bDEFAULT\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL|CHECK|CONSTRAINT)\b|\s*;?\s*$)")
        checks = []
        for match in re.finditer(r"\bCHECK\s*", text, re.IGNORECASE):
            inner, _ = _parenthesised(text[match.end():])
            inner = inner.strip()
            while inner.startswith("(") and _parenthesised(inner)[1].strip() == "":
                inner = _parenthesised(inner)[0].strip()
            if inner:
                checks.append(" ".join(inner.split()))
        found["checks"] = checks
    elif kind == "type":
        if match := re.search(r"\bAS\s+ENUM\s*", text, re.IGNORECASE):
            inner, _ = _parenthesised(text[match.end():])
            found["labels"] = [label.replace("''", "'") for label in re.findall(r"'((?:[^']|'')*)'", inner)]
        elif match := re.search(r"\bAS\s+(?:TABLE\s*)?(?=\()", text, re.IGNORECASE):  # a composite type; T-SQL's table type
            inner, _ = _parenthesised(text[match.end():].lstrip())
            found["attributes"] = [" ".join(part.split()) for part in _split_top(inner)]
        elif match := re.search(r"\bFROM\s+(.+?)(?=\s+(?:NOT\s+NULL|NULL)\b|\s*;?\s*$)", text, re.IGNORECASE | re.DOTALL):  # T-SQL's alias type
            found["type"] = match[1].strip()
            found["nullable"] = not re.search(r"\bNOT\s+NULL\b", text, re.IGNORECASE)
    elif kind == "sequence":
        found["start"] = one(r"\bSTART\s+(?:WITH\s+)?(-?\d+)")
        found["increment"] = one(r"\bINCREMENT\s+(?:BY\s+)?(-?\d+)")
    return {key: value for key, value in found.items() if value not in ("", [], None)}


def _trigger(schema: _Schema, text: str, place: dict) -> tuple[list[str], bool]:
    """CREATE TRIGGER: its name, the table it is on and the function it runs (PostgreSQL's EXECUTE FUNCTION)."""
    match = re.search(r"TRIGGER\s+(?P<name>[\w\"`\[\].]+).*?\bON\s+(?P<table>[\w\"`\[\].]+)", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return [], False
    name, table = _plain(match["name"]).split(".")[-1], [_plain(part) for part in match["table"].split(".")]
    calls = re.search(r"EXECUTE\s+(?:FUNCTION|PROCEDURE)\s+(?P<function>[\w\".]+)", text, re.IGNORECASE)
    when = re.search(r"\b(BEFORE|AFTER|INSTEAD\s+OF|FOR)\s+((?:INSERT|UPDATE|DELETE|TRUNCATE)(?:\s+OF\s+[\w\",\s]+?)?"
                     r"(?:\s*(?:,|\bOR\b)\s*(?:INSERT|UPDATE|DELETE|TRUNCATE)(?:\s+OF\s+[\w\",\s]+?)?)*)\s+(?:ON|AS|WITH|NOT)\b",
                     text, re.IGNORECASE)  # PostgreSQL / MySQL / SQLite: ... AFTER INSERT ON t; T-SQL: ON t AFTER INSERT AS
    each = re.search(r"\bFOR\s+EACH\s+(ROW|STATEMENT)\b", text, re.IGNORECASE)
    schema.put("trigger", table[0] if len(table) > 1 else "", f"{table[-1]}:{name}", place, table=table[-1],
               function=_plain(calls["function"]) if calls else "", definition=text,
               **({"timing": " ".join(when[1].upper().split()), "events": re.sub(r"\b(INSERT|UPDATE|DELETE|TRUNCATE|OR|OF)\b",
                                                                              lambda m: m[1].upper(), " ".join(when[2].split()), flags=re.IGNORECASE)}
                  if when else {}),
               **({"for_each": each[1].lower()} if each else {}))
    return [f"created trigger {name} on {table[-1]}"], True


def _split_top(text: str) -> list[str]:
    """The parts of a list separated by commas outside parentheses and quotes."""
    parts, depth, quote, current = [], 0, "", []
    for char in text:
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        parts.append("".join(current).strip())
    return parts


_COLUMN_END = re.compile(r"\s+(NOT\s+NULL|NULL|DEFAULT|PRIMARY\s+KEY|UNIQUE|REFERENCES|CHECK|AUTO_INCREMENT|AUTOINCREMENT|GENERATED|AS\s*\(|"
                         r"COMMENT|SRID|COLLATE|CHARACTER\s+SET|CONSTRAINT|IDENTITY|ON\s+UPDATE|VIRTUAL|STORED|INVISIBLE)\b", re.IGNORECASE)
"""Where a column's type ends in its definition: the first of its constraints."""


def _rule_default(definition: str) -> str:
    """The default a column's definition writes, read by our rules: a string, an expression between
    parentheses (its own ones inside it kept), or a word."""
    found = re.search(r"\bDEFAULT\s+", definition, re.IGNORECASE)
    if not found:
        return ""
    after = definition[found.end():]
    if after.startswith("("):
        inner, _ = _parenthesised(after)
        return f"({inner})"
    word = re.match(r"'(?:[^']|'')*'|\S+", after)
    return word[0].rstrip(",") if word else ""


_PARTITION_BY = re.compile(r"\bPARTITION\s+BY\s+(?P<linear>LINEAR\s+)?(?P<method>RANGE|LIST|HASH|KEY)(?:\s+(?P<columns>COLUMNS))?\s*"
                           r"(?:ALGORITHM\s*=\s*\d+\s*)?", re.IGNORECASE)
"""Where a MySQL table's partitioning starts, and its method."""


def _mysql_partitioning(text: str) -> tuple[str, dict]:
    """A MySQL CREATE TABLE without its `PARTITION BY …` (outside sqlglot's grammar), and that partitioning
    as written: `partition_method` (`RANGE`, `LIST COLUMNS`, `LINEAR HASH`…), `partition_expression` and
    `partitions` (each `name` and `bound`, the values between the parentheses of `VALUES LESS THAN` /
    `VALUES IN`, or `MAXVALUE`); none when the table is not partitioned."""
    code = _QUOTED.sub(lambda m: " " * len(m[0]), text)  # the same length, its strings blank
    depth, start = 0, -1
    for at, char in enumerate(code):
        depth += {"(": 1, ")": -1}.get(char, 0)
        if depth == 0 and char in "Pp" and (match := _PARTITION_BY.match(code, at)) and (at == 0 or not code[at - 1].isalnum()):
            start = at
            break
    if start < 0:
        return text, {}
    method = " ".join(filter(None, [(match["linear"] or "").strip().upper(), match["method"].upper(), (match["columns"] or "").upper()]))
    expression, rest = _parenthesised(text[match.end():].lstrip())
    partitions = []
    if count := re.match(r"\s*PARTITIONS\s+(\d+)", rest, re.IGNORECASE):
        rest = rest[count.end():]
    rest = re.sub(r"^\s*SUBPARTITION\s+BY\b.*?(?=\()", "", rest, flags=re.IGNORECASE | re.DOTALL)
    definitions, _ = _parenthesised(rest.lstrip())
    for definition in _split_top(definitions):
        if found := re.match(r"\s*PARTITION\s+([\w`]+)", definition, re.IGNORECASE):
            bound = re.search(r"\bVALUES\s+(?:LESS\s+THAN|IN)\s*", definition, re.IGNORECASE)
            after = definition[bound.end():] if bound else ""
            value = _parenthesised(after)[0] if after.startswith("(") else (after.split()[0] if after.split() else "")
            partitions.append({"name": _plain(found[1]), "bound": " ".join(value.split()) or None})
    if not partitions and count:  # PARTITIONS n, none written: MySQL names them p0, p1…
        partitions = [{"name": f"p{n}", "bound": None} for n in range(int(count[1]))]
    return text[:start].rstrip(), {"partition_method": method, "partition_expression": " ".join(expression.split()), "partitions": partitions}


def _rule_table(schema: _Schema, text: str, place: dict) -> tuple[list[str], bool]:
    """CREATE TABLE that sqlglot cannot read (types of its own, options it does not know): its columns,
    primary key, uniques and foreign keys, read by our rules from the list between its parentheses."""
    match = re.match(r"^\s*CREATE\s+(?:TEMPORARY\s+|TEMP\s+|VIRTUAL\s+|(?P<foreign>FOREIGN\s+))?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[\w.\"`'\[\]]+)\s*\(", text, re.IGNORECASE)
    if not match:
        return [], False
    body, depth = [], 1
    for char in text[match.end():]:
        depth += char == "("
        depth -= char == ")"
        if depth == 0:
            break
        body.append(char)
    parts = [_plain(part.strip("'")) for part in match["name"].split(".")]
    table = schema.put("foreign table" if match["foreign"] else "table", parts[0] if len(parts) > 1 else "", parts[-1], place,
                       columns=[], primary_key=[], foreign_keys=[], unique=[], checks=[], indexes=[], comment="")
    if found := re.search(r"\bSERVER\s+(\w+)(?:\s+OPTIONS\s*\((?P<options>.*)\))?", text[match.end() + len(body):], re.IGNORECASE | re.DOTALL):
        table["foreign_server"] = found[1]
        table["foreign_options"] = dict(re.findall(r"(\w+)\s+'((?:[^']|'')*)'", found["options"] or ""))
    for item in _split_top("".join(body)):
        head = item.split(None, 1)[0].upper() if item.split() else ""
        names = lambda text_: [_plain(n) for n in _split_top(text_)]  # noqa: E731
        if head in ("PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT", "INDEX", "KEY", "SPATIAL", "FULLTEXT"):
            if found := re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", item, re.IGNORECASE):
                table["primary_key"] = names(found[1])
            elif found := re.search(r"FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+([\w.\"`\[\]]+)\s*\(([^)]*)\)", item, re.IGNORECASE):
                target = [_plain(p) for p in found[2].split(".")]
                table["foreign_keys"].append({"columns": names(found[1]), "schema": target[0] if len(target) > 1 else "",
                                              "table": target[-1], "target_columns": names(found[3]), "options": []})
            elif found := re.search(r"UNIQUE\s*(?:KEY|INDEX)?\s*[\w`\"]*\s*\(([^)]*)\)", item, re.IGNORECASE):
                table["unique"].append(names(found[1]))
            elif found := re.search(r"(?:INDEX|KEY)\s+([\w`\"]+)\s*\(([^)]*)\)", item, re.IGNORECASE):
                table["indexes"].append({"name": _plain(found[1]), "columns": [_plain(n.split()[0]) for n in _split_top(found[2]) if n.split()],
                                         "unique": False})
            continue
        name = _plain(item.split(None, 1)[0])
        rest = item[len(item.split(None, 1)[0]):]
        end = _COLUMN_END.search(rest)
        column = {"name": name, "type": (rest[:end.start()] if end else rest).strip(), "nullable": not re.search(r"\bNOT\s+NULL\b|PRIMARY\s+KEY", rest, re.IGNORECASE),
                  "default": _rule_default(rest),
                  "computed": (found[1] if (found := re.search(r"\bAS\s*(\(.*\))\s*(VIRTUAL|STORED)?", rest, re.IGNORECASE)) else ""),
                  "identity": bool(re.search(r"AUTO_?INCREMENT|IDENTITY|GENERATED\s+\w+\s+AS\s+IDENTITY", rest, re.IGNORECASE)),
                  "pk": bool(re.search(r"PRIMARY\s+KEY", rest, re.IGNORECASE)), "unique": bool(re.search(r"\bUNIQUE\b", rest, re.IGNORECASE)),
                  "references": None, "check": "",
                  "comment": (found[1] if (found := re.search(r"\bCOMMENT\s+'((?:[^']|'')*)'", rest, re.IGNORECASE)) else ""),
                  "created": place, "changed": place}
        if found := re.search(r"REFERENCES\s+([\w.\"`\[\]]+)\s*\(([^)]*)\)", rest, re.IGNORECASE):
            target = [_plain(p) for p in found[1].split(".")]
            table["foreign_keys"].append({"columns": [name], "schema": target[0] if len(target) > 1 else "", "table": target[-1],
                                          "target_columns": names(found[2]), "options": []})
        if column["pk"]:
            table["primary_key"].append(name)
        if column["unique"]:
            table["unique"].append([name])
        table["columns"].append(_serial(column))
    for column in table["columns"]:
        if column["name"] in table["primary_key"]:
            column.update(pk=True, nullable=False)
    if found := re.search(r"\)\s*[^()]*\bCOMMENT\s*=?\s*'((?:[^']|'')*)'\s*;?\s*$", text, re.IGNORECASE):
        table["comment"] = found[1]
    return [f"created {table['kind']} {parts[-1]}"], True


def _rules(schema: _Schema, text: str, place: dict) -> tuple[list[str], bool]:
    """Read by our own rules a statement sqlglot left raw: the object it creates, or nothing to record."""
    if re.match(r"^\s*CREATE\s+(?:TEMPORARY\s+|TEMP\s+|VIRTUAL\s+|FOREIGN\s+)?TABLE\b", text, re.IGNORECASE):
        if re.match(r"^\s*CREATE\s+VIRTUAL\s+TABLE", text, re.IGNORECASE):  # SQLite's full-text search and the like
            match = re.match(r"^\s*CREATE\s+VIRTUAL\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([\w\"'`]+)", text, re.IGNORECASE)
            arguments = re.search(r"\bUSING\s+\w+\s*\((.*)\)\s*;?\s*$", text, re.IGNORECASE | re.DOTALL)
            columns = []  # the module's arguments that are names (fts5's columns, rtree's); `option = value` are not
            for argument in _split_top(arguments[1]) if arguments else []:
                if (name := re.fullmatch(r"\s*([\w\"`]+)(?:\s+UNINDEXED)?\s*", argument, re.IGNORECASE)):
                    columns.append({"name": _plain(name[1]), "type": "", "nullable": True, "default": "", "computed": "", "identity": False,
                                    "pk": False, "unique": False, "references": None, "check": "", "comment": "", "created": place, "changed": place})
            schema.put("table", "", _plain(match[1].strip("'")) if match else "?", place, columns=columns, primary_key=[], foreign_keys=[],
                       unique=[], checks=[], indexes=[], comment="", virtual=True)
            return [f"created virtual table {_plain(match[1]) if match else ''}"], True
        return _rule_table(schema, text, place)
    if match := re.match(r"^\s*COMMENT\s+ON\s+(?P<kind>[A-Z ]+?)\s+(?P<name>[\w.\"]+)(?:\s*\([^)]*\))?(?:\s+ON\s+(?P<on>[\w.\"]+))?\s+IS\s+'(?P<text>(?:[^']|'')*)'", text, re.IGNORECASE):
        parts = [_plain(p) for p in match["name"].split(".")]
        name = f"{_plain(match['on'].split('.')[-1])}:{parts[-1]}" if match["on"] else parts[-1]
        found = schema.get(parts[0] if len(parts) > 1 and not match["on"] else "", name)
        if found is not None:
            found["comment"] = match["text"].replace("''", "'")
        return [f"commented {match['kind'].strip().lower()} {parts[-1]}"], True
    if match := re.match(r"^\s*CREATE\s+(?P<unique>UNIQUE\s+)?(?:CLUSTERED\s+|NONCLUSTERED\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?(?P<name>[\w\"`\[\]]+)\s+ON\s+(?P<table>[\w.\"`\[\]]+)\s*(?:USING\s+\w+\s*)?\((?P<columns>[^)]*)\)", text, re.IGNORECASE):
        parts = [_plain(p) for p in match["table"].split(".")]
        table = schema.table(parts[0] if len(parts) > 1 else "", parts[-1], place)
        table["indexes"].append({"name": _plain(match["name"]), "unique": bool(match["unique"]),
                                 "columns": [_plain(c.split()[0]) for c in _split_top(match["columns"]) if c.split()]})
        return [f"created index {_plain(match['name'])} on {parts[-1]}"], True
    if match := re.match(r"^\s*ALTER\s+TABLE\s+(?:ONLY\s+)?(?P<table>[\w.\"]+)\s+ALTER\s+COLUMN\s+(?P<column>[\w\"]+)\s+ADD\s+GENERATED", text, re.IGNORECASE):
        parts = [_plain(p) for p in match["table"].split(".")]
        table = schema.table(parts[0] if len(parts) > 1 else "", parts[-1], place)
        for column in table["columns"]:
            if column["name"].lower() == _plain(match["column"]).lower():
                column["identity"] = True
        return [f"made {_plain(match['column'])} an identity column of {parts[-1]}"], True
    if re.match(r"^\s*CREATE\s+(OR\s+REPLACE\s+)?(CONSTRAINT\s+)?(DEFINER\s*=\s*\S+\s+)?TRIGGER\b", text, re.IGNORECASE):
        return _trigger(schema, text, place)
    if match := re.match(r"^\s*CREATE\s+SERVER\s+(?P<name>[\w\"]+).*?\bOPTIONS\s*\((?P<options>.*)\)", text, re.IGNORECASE | re.DOTALL):
        schema.servers[_plain(match["name"])] = dict(re.findall(r"(\w+)\s+'((?:[^']|'')*)'", match["options"]))
        return [f"created server {_plain(match['name'])}"], True
    if match := re.match(r"^\s*ALTER\s+TABLE\s+(?:ONLY\s+)?(?P<parent>[\w.\"]+)\s+ATTACH\s+PARTITION\s+(?P<child>[\w.\"]+)", text, re.IGNORECASE):
        parent, child = [_plain(p) for p in match["parent"].split(".")], [_plain(p) for p in match["child"].split(".")]
        table = schema.table(child[0] if len(child) > 1 else "", child[-1], place)
        table["partition_of"] = [parent[0] if len(parent) > 1 else "", parent[-1]]
        if bound := re.search(r"(FOR\s+VALUES\b.*?|DEFAULT)\s*;?\s*$", text[match.end():], re.IGNORECASE | re.DOTALL):
            table["partition_bound"] = " ".join(bound[1].split())
        return [f"attached partition {child[-1]} to {parent[-1]}"], True
    for kind, rule in _RULES:
        if match := rule.match(text):
            parts = [_plain(part) for part in match["name"].split(".")]
            if kind == "view" and match["materialized"]:
                kind = "materialized view"
            schema.put(kind, parts[0] if len(parts) > 1 else "", parts[-1], place, definition=text,
                       **({"columns": [], "reads": []} if "view" in kind else {}))
            return [f"created {kind} {parts[-1]}"], True
    if _IGNORED.match(text):
        return [], True
    return [], False


def read_origin(root: Path, origin: dict, dialect: str = "", project: orm.Project | None = None) -> dict:
    """Read an origin's steps in order into the schema it builds.

    Args:
        root: The project's root.
        origin: What `find_origins` (or an ORM reader's `find`) gives of it.
        dialect: The SQL dialect to read it in; empty: guessed from its files (an ORM's: from what its
            reader finds).
        project: The project's Python, read once for all the ORM origins (`orm.Project`).

    Returns:
        The origin with `dialect`, `objects` (see `_Schema`), and in each step its `statements`
        (`line`, `text`, `effects`, `read`) and how many were `unread`. A dump's also with `samples`: by
        table (`schema.name`, lower case), what is kept of the rows it holds (`dumps.table_samples`). An ORM's also with
        `dialect_from`, `unresolved`, `expects` and `mapping` (see `orm.read`); its statements' text
        is the DDL its ORM would send, their line the line of the code declaring it.
    """
    extra: dict = {}
    if origin["kind"] in orm.READERS:
        try:
            reading = orm.read(root, origin, project or orm.Project(root, [s["file"] for s in origin["steps"]]))
        except Exception as problem:  # a form of the ORM's code the reader does not foresee: told, the rest read on
            reading = {"dialect": dialect or "postgres", "dialect_from": "", "statements": [], "expects": [], "mapping": [],
                       "unresolved": [{"file": origin["steps"][0]["file"], "line": 0, "what": f"the reading: {str(problem).splitlines()[0][:150]}"}]}
        dialect = reading["dialect"]
        given: dict[str, list[tuple[int, str]]] = {}
        for statement in reading["statements"]:
            given.setdefault(statement["file"], []).append((statement["line"], statement["text"]))
        extra = {key: reading[key] for key in ("dialect_from", "unresolved", "expects", "mapping")}
    else:
        texts = {step["file"]: (root / step["file"]).read_text(encoding="utf-8", errors="replace") for step in origin["steps"]}
        dialect = dialect or origin.get("dialect_hint") or guess_dialect("\n".join(texts.values()))
        given = {file: split_statements(text, dialect) for file, text in texts.items()}
        if origin.get("lines"):  # one database of a dump holding several: its own lines only
            first, last = origin["lines"]
            given = {file: [(line, text) for line, text in statements if first <= line <= last] for file, statements in given.items()}
    named = ((origin.get("dump") or {}).get("database") or {}).get("value", "")
    schema = _Schema(dialect, named if dialect == "mysql" and named else None)  # MySQL: a dump's database is its schema
    steps = []
    for step in origin["steps"]:
        statements = []
        for line, text in given.get(step["file"], []):
            place = {"file": step["file"], "line": line}
            try:
                effects, read = _apply(schema, text, place)
            except Exception:  # a statement whose tree holds what our reading does not expect: kept as not read
                effects, read = [], False
            statements.append({"line": line, "text": text[:4000], "effects": effects, "read": read})
        steps.append({**step, "statements": statements, "unread": sum(1 for s in statements if not s["read"])})
    for table in schema.objects.values():  # partitions and child tables take their parent's columns
        parents = ([table["partition_of"]] if table.get("partition_of") else []) + (table.get("inherits") or [])
        for parent_schema, parent_name in parents:
            parent = schema.get(parent_schema, parent_name)
            if parent:
                own = {c["name"].lower() for c in table["columns"]}
                table["columns"] = [c for c in parent["columns"] if c["name"].lower() not in own] + table["columns"]
    if origin["kind"] == "dump":  # the rows it holds, as a live table's are sampled
        extra["samples"] = dumps.table_samples(
            (row for file, text in texts.items() for row in dumps.rows(text, given.get(file, []), dialect, origin.get("lines"))),
            schema.get)
    return {**origin, "dialect": dialect, "steps": steps, "objects": schema.objects, "servers": schema.servers,
            "default_schema": schema.default, **extra}


def extract_origins(root: Path, files: list[str], on_file: Callable[[int, int], None] | None = None) -> list[dict]:
    """Find and read every origin of the project: its SQL files (see `find_origins`) and its ORM code
    (see `orm.find`); a file whose statements, once read, declare nothing (data, grants, settings) is
    left out. `on_file`, when given, is told before each origin how many are read and how many there are."""
    project = orm.Project(root, files)
    found = find_origins(root, files) + orm.find(root, files, project)
    names = {origin["name"]: origin for origin in found}
    for origin in found:  # an ORM's two origins point to each other (a Prisma schema and its SQL migrations)
        if origin.get("related") in names and not names[origin["related"]].get("related"):
            names[origin["related"]]["related"] = origin["name"]
    origins = []
    for index, origin in enumerate(found):
        if on_file is not None:
            on_file(index, len(found))
        origins.append(read_origin(root, origin, project=project))
    return [o for o in origins if o["objects"] or any(s["effects"] for step in o["steps"] for s in step["statements"])]


def _reads(query: exp.Expression | None) -> list[str]:
    """The tables and views a query reads (`schema.name`, or the name alone), its own CTEs left out."""
    if query is None:
        return []
    ctes = {cte.alias_or_name.lower() for cte in query.find_all(exp.CTE)}
    return sorted({f"{t.db}.{t.name}" if t.db else t.name for t in query.find_all(exp.Table) if t.name.lower() not in ctes})
