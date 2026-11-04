"""The origins of the project's schema: the SQL files and migrations that declare it, read as text.

An origin is either a set of migration steps of a known tool, applied in order — Flyway
(`V<version>__<name>.sql`), golang-migrate (`<version>_<name>.up.sql`, its `.down.sql` the undo of
the step), dbmate (`-- migrate:up` / `-- migrate:down` in each file) — or any other `.sql` file that
declares schema (CREATE / ALTER / DROP / COMMENT ON): a schema file, an initdb script, a dump.
Files that only query or fill tables are not origins.

Each statement is read with sqlglot in the origin's dialect; what its grammar leaves as a raw command
(domains, types, functions and triggers written in PL code, MySQL's DEFINER objects...) is read by our
own rules from its text, and what neither understands is kept as "not read". The steps are applied in
order into one schema (tables with their columns, keys, constraints and indexes; views and what they
read; functions, procedures, triggers, sequences, types), every object remembering the file and line
that created it and the last that changed it; partitions and child tables take their parent's
columns. Nothing is run: the files are only read.
"""

import logging
import re
import zlib
from pathlib import Path

import sqlglot
from sqlglot import exp

logging.getLogger("sqlglot").setLevel(logging.ERROR)  # its notes on statements it keeps as raw commands

DEFAULT_SCHEMAS = {"postgres": "public", "tsql": "dbo", "sqlite": "main", "mysql": ""}
"""The schema of a name written without one, per dialect (MySQL: the database itself, unknown here)."""

_DDL = re.compile(r"^\s*(CREATE|ALTER|DROP|COMMENT\s+ON|RENAME\s+TABLE)\b", re.IGNORECASE | re.MULTILINE)
"""A statement that declares schema."""

_FLYWAY = re.compile(r"^V(?P<version>\d+(?:[._]\d+)*)__(?P<name>.+)\.sql$", re.IGNORECASE)
_GOLANG = re.compile(r"^(?P<version>\d+)_(?P<name>.+)\.(?P<way>up|down)\.sql$", re.IGNORECASE)
_DBMATE = re.compile(r"^--\s*migrate:(up|down)\b", re.IGNORECASE | re.MULTILINE)
_DUMP = re.compile(r"^--\s*(PostgreSQL database dump|MySQL dump|MariaDB dump)|^PRAGMA foreign_keys=OFF;", re.IGNORECASE | re.MULTILINE)
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
        Each origin's `name` (its folder for a migration set, its file otherwise), `kind` (`flyway`,
        `golang-migrate`, `dbmate`, `dump`, `sql file`), `folder`, and `steps` in order: `file`,
        `version`, `title`, and `down` (the file undoing it, golang-migrate) when there is one.
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
        if match := _FLYWAY.match(name):
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
            alone.append({"name": file, "kind": "dump" if _DUMP.search(text) else "sql file", "folder": folder,
                          "steps": [{"file": file, "version": "", "title": name}]})
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
    counts); T-SQL's `GO` lines end a statement too; dbmate's `-- migrate:down` part is left out.

    Returns:
        `(line, text)` of each statement, in order.
    """
    if (cut := re.search(r"^--\s*migrate:down\b", text, re.IGNORECASE | re.MULTILINE)):
        text = text[:cut.start()]
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


def _join_bodies(statements: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Put back together a trigger's or routine's BEGIN ... END body cut at its inner semicolons."""
    joined: list[tuple[int, str]] = []
    depth = 0
    for line, text in statements:
        code = _QUOTED.sub(" ", text)  # a word in a string, a quoted body or a comment opens nothing
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

    def __init__(self, dialect: str) -> None:
        self.dialect = dialect
        self.objects: dict[str, dict] = {}
        self.servers: dict[str, dict] = {}  # PostgreSQL's foreign servers, by name: their options (host, port, dbname)

    def key(self, schema: str, name: str) -> str:
        """An object's key: its schema (the dialect's default when not written) and name, in lower case."""
        return f"{schema or DEFAULT_SCHEMAS.get(self.dialect, '')}.{name}".lower()

    def put(self, kind: str, schema: str, name: str, place: dict, **data) -> dict:
        """Create an object, or take its place (CREATE OR REPLACE); a function, procedure, domain, type or
        sequence also gets what its definition says of it (see `_details`)."""
        schema = schema or DEFAULT_SCHEMAS.get(self.dialect, "")
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


def _column(definition: exp.ColumnDef, dialect: str, place: dict, source: str = "") -> dict:
    """A column as a ColumnDef declares it, with what its own constraints say (its default as the file
    writes it, `source` being the statement read)."""
    column = {"name": definition.name, "type": definition.args["kind"].sql(dialect) if definition.args.get("kind") else "",
              "nullable": True, "default": "", "computed": "", "identity": False, "pk": False, "unique": False,
              "references": None, "check": "", "comment": "", "created": place, "changed": place}
    for constraint in definition.args.get("constraints") or []:
        kind = constraint.args.get("kind")
        if isinstance(kind, exp.NotNullColumnConstraint):
            column["nullable"] = bool(kind.args.get("allow_null"))
        elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
            column.update(pk=True, nullable=False)
        elif isinstance(kind, exp.UniqueColumnConstraint):
            column["unique"] = True
        elif isinstance(kind, exp.DefaultColumnConstraint):
            column["default"] = _as_written(kind.this, source, dialect)
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
        if name:
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


def _create_table(schema: _Schema, statement: exp.Create, place: dict, source: str = "") -> list[str]:
    """CREATE TABLE: its columns and constraints; a partition or a child table names its parent (and a
    partition its bounds), a partitioned table how it is partitioned."""
    owner, name = _name(statement.this)
    table = schema.put("table", owner, name, place, columns=[], primary_key=[], foreign_keys=[], unique=[], checks=[],
                       indexes=[], comment="")
    for item in statement.this.expressions if isinstance(statement.this, exp.Schema) else []:
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
    return [f"created table {table['schema']}.{name}" if table["schema"] else f"created table {name}"]


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
            old, new = action.this.name, action.args["to"].name
            for column in table["columns"]:
                if column["name"].lower() == old.lower():
                    column.update(name=new, changed=place)
            effects.append(f"renamed column {old} to {new} in {name}")
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
        elif isinstance(action, exp.AlterRename):
            new_schema, new_name = _name(action.this)
            schema.objects.pop(schema.key(table["schema"], table["name"]), None)
            table.update(name=new_name, schema=new_schema or table["schema"])
            schema.objects[schema.key(table["schema"], new_name)] = table
            effects.append(f"renamed table {name} to {new_name}")
        else:
            effects.append(f"changed {name}")
    return effects


def _apply(schema: _Schema, text: str, place: dict) -> tuple[list[str], bool]:
    """Apply one statement to the schema.

    Returns:
        What it did (`created table sales.orders`...), and whether it was read (by sqlglot or by our
        rules); a statement neither reads is left out of the schema and kept as "not read".
    """
    text = re.sub(r"(/\*!\d+\s+|\*/)", " ", text)  # MySQL's versioned comments hold real SQL: kept, unwrapped
    text = re.sub(r"^(\s*(--[^\n]*(\n|$)|/\*.*?\*/))+", "", text, flags=re.DOTALL).strip()  # the comments before it
    if not text:
        return [], True
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
            return _create_table(schema, statement, place, parsed), True
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
            table["indexes"].append({"name": index.name, "columns": [c.split(" ")[0] for c in columns],
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

_IGNORED = re.compile(r"^\s*(ANALYZE|VACUUM|ALTER\s+FOREIGN\s+TABLE|ALTER\s+TABLE\s+(ONLY\s+)?[\w.\"]+\s+(ENABLE|DISABLE|FORCE|NO\s+FORCE|OWNER|REPLICA|CLUSTER)\b|CREATE\s+(DEFINER\s*=\s*\S+\s+)?EVENT|COMMENT\s+ON\s+(OPERATOR|EXTENSION|COLLATION|SERVER|PUBLICATION|SUBSCRIPTION|POLICY|RULE|TEXT\s+SEARCH|CAST|SCHEMA|DATABASE|ROLE|EVENT)|ALTER\s+TEXT\s+SEARCH|CREATE\s+(PARTITION\s+(FUNCTION|SCHEME)|SECURITY\s+POLICY|EXTENSION|ROLE|USER|DATABASE|PUBLICATION|SUBSCRIPTION|SERVER|USER\s+MAPPING|POLICY|RULE|STATISTICS|EVENT\s+TRIGGER|OPERATOR|CAST|COLLATION|TEXT\s+SEARCH|TABLESPACE|EVENT|LOGIN|FOREIGN\s+DATA)|GRANT|REVOKE|SET|USE|SELECT|INSERT|UPDATE|DELETE|COPY|BEGIN|COMMIT|START|LOCK|UNLOCK|DELIMITER|PRAGMA|EXEC|EXECUTE|IF\s|PRINT|DECLARE|\\\\|ALTER\s+(DEFAULT\s+PRIVILEGES|ROLE|USER|DATABASE|SEQUENCE|SCHEMA|EXTENSION|FUNCTION|PROCEDURE|TYPE|DOMAIN|VIEW|MATERIALIZED|INDEX|PUBLICATION|SUBSCRIPTION|SERVER|POLICY)|SELECT\s+pg_catalog|DROP\s+(EXTENSION|ROLE|USER|DATABASE|POLICY|RULE|EVENT|PUBLICATION|SUBSCRIPTION))\b", re.IGNORECASE)
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
                table["indexes"].append({"name": _plain(found[1]), "columns": [n.split()[0] for n in names(found[2])], "unique": False})
            continue
        name = _plain(item.split(None, 1)[0])
        rest = item[len(item.split(None, 1)[0]):]
        end = _COLUMN_END.search(rest)
        column = {"name": name, "type": (rest[:end.start()] if end else rest).strip(), "nullable": not re.search(r"\bNOT\s+NULL\b|PRIMARY\s+KEY", rest, re.IGNORECASE),
                  "default": (found[1].strip() if (found := re.search(r"\bDEFAULT\s+(\([^)]*\)|'[^']*'|\S+)", rest, re.IGNORECASE)) else ""),
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
            schema.put("table", "", _plain(match[1].strip("'")) if match else "?", place, columns=[], primary_key=[], foreign_keys=[],
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


def read_origin(root: Path, origin: dict, dialect: str = "") -> dict:
    """Read an origin's steps in order into the schema it builds.

    Args:
        root: The project's root.
        origin: What `find_origins` gives of it.
        dialect: The SQL dialect to read it in; empty: guessed from its files.

    Returns:
        The origin with `dialect`, `objects` (see `_Schema`), and in each step its `statements`
        (`line`, `text`, `effects`, `read`) and how many were `unread`.
    """
    texts = {step["file"]: (root / step["file"]).read_text(encoding="utf-8", errors="replace") for step in origin["steps"]}
    dialect = dialect or guess_dialect("\n".join(texts.values()))
    schema = _Schema(dialect)
    steps = []
    for step in origin["steps"]:
        statements = []
        for line, text in split_statements(texts[step["file"]], dialect):
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
    return {**origin, "dialect": dialect, "steps": steps, "objects": schema.objects, "servers": schema.servers}


def extract_origins(root: Path, files: list[str]) -> list[dict]:
    """Find and read every origin of the project (see `find_origins` and `read_origin`); a file whose
    statements, once read, declare nothing (data, grants, settings) is left out."""
    origins = [read_origin(root, origin) for origin in find_origins(root, files)]
    return [o for o in origins if o["objects"] or any(s["effects"] for step in o["steps"] for s in step["statements"])]


# --- Which databases an origin describes, and where they differ (in the server, over what it read).

HISTORY_TOOLS = {"flyway": "flyway_schema_history", "golang-migrate": "schema_migrations", "dbmate": "schema_migrations"}
"""The history table each migration tool keeps in the database it migrates."""

_LOCAL = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


def _same_host(host: str) -> str:
    """A host as it is compared: every name of this machine is one."""
    return "localhost" if host.lower() in _LOCAL else host.lower()


def flyway_checksum(text: str) -> int:
    """The checksum Flyway records for a migration: CRC32 over its lines, without their line ends."""
    crc = 0
    for line in text.lstrip("﻿").splitlines():
        crc = zlib.crc32(line.encode("utf-8"), crc)
    return crc - 2**32 if crc >= 2**31 else crc


def _declared_urls(root: Path, origin: dict) -> list[tuple[str, str, str, str]]:
    """The databases an origin's own configuration names: Flyway's `flyway.conf` / `flyway.toml` in its
    folder. Each as `(file, host, port, database)`."""
    found = []
    for name in ("flyway.conf", "flyway.toml"):
        path = root / origin["folder"] / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"""(?:flyway\.url\s*=|\burl\s*=\s*["'])\s*jdbc:\w+://(?P<host>[^:/?"']+)(?::(?P<port>\d+))?/(?P<database>[^?"'\s;]+)""", text):
            found.append((f"{origin['folder']}/{name}", match["host"], match["port"] or "", match["database"]))
    return found


def _history_link(origin: dict, rows: list[dict], root: Path) -> dict | None:
    """What a tool's history table says of an origin, when it is that origin's history: the steps applied,
    those pending, those changed since they were applied (Flyway's checksum), and a failed step."""
    names = {Path(step["file"]).name: step for step in origin["steps"]}
    if origin["kind"] == "flyway":
        applied = [row for row in rows if row.get("script") in names and str(row.get("success")).lower() in ("true", "1", "t")]
        if not applied:
            return None
        changed = [row["script"] for row in applied if row.get("checksum") not in (None, "")
                   and str(flyway_checksum((root / names[row["script"]]["file"]).read_text(encoding="utf-8", errors="replace"))) != row["checksum"]]
        done = {row["script"] for row in applied}
        return {"tool": "flyway", "applied": len(done), "steps": len(origin["steps"]),
                "version": max((row["version"] for row in applied), key=lambda v: [int(p) if p.isdigit() else p for p in re.split(r"[._]", v)]),
                "pending": [Path(s["file"]).name for s in origin["steps"] if Path(s["file"]).name not in done], "changed": changed,
                "failed": [row["script"] for row in rows if str(row.get("success")).lower() in ("false", "0", "f")]}
    versions = [step["version"] for step in origin["steps"]]
    if origin["kind"] == "golang-migrate" and rows and "dirty" in rows[0]:
        version = rows[0].get("version") or ""
        if not version.isdigit() or int(version) not in {int(v) for v in versions if v.isdigit()}:
            return None
        done = [v for v in versions if v.isdigit() and int(v) <= int(version)]
        return {"tool": "golang-migrate", "applied": len(done), "steps": len(versions), "version": version,
                "pending": [Path(s["file"]).name for s in origin["steps"] if s["version"] not in done], "changed": [],
                "failed": [f"version {version} is dirty: it failed half way"] if str(rows[0].get("dirty")).lower() in ("true", "1", "t") else []}
    if origin["kind"] == "dbmate" and rows and "dirty" not in rows[0]:
        done = {row.get("version") for row in rows} & set(versions)
        if not done:
            return None
        return {"tool": "dbmate", "applied": len(done), "steps": len(versions), "version": max(done),
                "pending": [Path(s["file"]).name for s in origin["steps"] if s["version"] not in done], "changed": [], "failed": []}
    return None


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
    (`integer`, `timestamp with time zone`, `character(14)`…), the others as sqlglot writes them in
    their dialect (the spelling SQLAlchemy reads back)."""
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
    sequence's name to `regclass`, `true` / `false` in lower case."""
    if re.fullmatch(r"(?i)true|false|null", default):
        return default.lower()
    if re.fullmatch(r"'(?:[^']|'')*'", default) and type_:
        base = re.sub(r"\(.*\)", "", type_).strip()
        return f"{default}::{ {'character': 'bpchar'}.get(base, base) }"
    return re.sub(r"nextval\('([^']+)'\)", r"nextval('\1'::regclass)", default)


def _reads(query: exp.Expression | None) -> list[str]:
    """The tables and views a query reads (`schema.name`, or the name alone), its own CTEs left out."""
    if query is None:
        return []
    ctes = {cte.alias_or_name.lower() for cte in query.find_all(exp.CTE)}
    return sorted({f"{t.db}.{t.name}" if t.db else t.name for t in query.find_all(exp.Table) if t.name.lower() not in ctes})


def _view_body(text: str) -> str:
    """The query of a CREATE VIEW statement, as written (what the database gives as its definition)."""
    match = re.search(r"\bVIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?[\w.\"`\[\]]+\s*(?:\([^)]*\)\s*)?(?:WITH\s*\([^)]*\)\s*)?AS\s+", text,
                      re.IGNORECASE)
    body = text[match.end():] if match else text
    return re.sub(r"\s*(WITH\s+(CASCADED\s+|LOCAL\s+)?CHECK\s+OPTION|WITH\s+(NO\s+)?DATA)?\s*;?\s*$", "", body, flags=re.IGNORECASE)


def _view_columns(body: str, dialect: str, objects: dict) -> list[dict]:
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
        key = f"{table.db or DEFAULT_SCHEMAS.get(dialect, '')}.{table.name}".lower()
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


def _named(dialect: str, table: str, what: str, columns: list[str], position: int = 0) -> str | None:
    """The name the database gives by itself to a constraint the file does not name: PostgreSQL's
    `<table>_pkey`, `<table>_<columns>_key`, `<table>_<columns>_fkey`; MySQL's `PRIMARY`, a unique
    key's first column, `<table>_ibfk_<n>`; none for the others."""
    if dialect == "postgres":
        return {"pk": f"{table}_pkey", "unique": f"{table}_{'_'.join(columns)}_key", "fk": f"{table}_{'_'.join(columns)}_fkey"}[what]
    if dialect == "mysql":
        return {"pk": "PRIMARY", "unique": columns[0] if columns else None, "fk": f"{table}_ibfk_{position}"}[what]
    return None


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


def _parts(obj: dict, columns: list[dict], dialect: str, objects: dict) -> dict:
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
        given = names.get(f"check:{check}")
        if not given and dialect == "postgres":  # <table>_<column>_check when it tests one column, else <table>_check
            try:
                tested = sorted({c.name for c in sqlglot.parse_one(check, read=dialect).find_all(exp.Column)})
            except Exception:
                tested = []
            given = f"{name}_{tested[0]}_check" if len(tested) == 1 else f"{name}_check"
        checks.append({"name": given, "sqltext": check})

    def column(c: dict) -> dict:
        type_ = _database_type(c["type"], dialect)
        default = c["default"]
        if dialect == "postgres" and c.get("serial"):
            sequence = f"{name}_{c['name']}_seq" if obj["schema"] in ("", "public") else f"{obj['schema']}.{name}_{c['name']}_seq"
            default = f"nextval('{sequence}')"
        if dialect == "postgres" and default:
            default = _postgres_default(default, type_)
        return {"name": c["name"], "type": type_, "nullable": c["nullable"], "default": default or None,
                "comment": c["comment"] or None, "computed": {"sqltext": c["computed"]} if c["computed"] else None,
                "identity": {"declared": True} if c["identity"] and not c.get("serial") else None,
                "autoincrement": True if c.get("serial") or str(default).startswith("nextval(") else None}

    return {"columns": [column(c) for c in columns],
            "pk": {"constrained_columns": pk, "name": names.get("pk") or _named(dialect, name, "pk", pk)} if pk else None,
            "fks": [{"name": k.get("name") or _named(dialect, name, "fk", k["columns"], n), "constrained_columns": k["columns"],
                     "referred_schema": (objects.get(f"{k['schema'] or DEFAULT_SCHEMAS.get(dialect, '')}.{k['table']}".lower()) or {}).get("schema", k["schema"]),
                     "referred_table": k["table"],
                     "referred_columns": k["target_columns"] or (objects.get(f"{k['schema'] or DEFAULT_SCHEMAS.get(dialect, '')}.{k['table']}".lower()) or {}).get("primary_key") or [],
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
    found = _Collection(base, "::")
    found.add(base, "database", "", origin["name"].rsplit("/", 1)[-1])
    objects = {key: dict(obj) for key, obj in origin["objects"].items()}
    for _ in range(3):  # a view's columns from its query, a view reading a view after it
        for obj in objects.values():
            if "view" in obj["kind"] and obj.get("definition"):
                inferred = _view_columns(_view_body(obj["definition"]), dialect, objects)
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
        key = f"{schema or DEFAULT_SCHEMAS.get(dialect, '')}.{name}".lower()
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
            found.add(path, kind, schema_path, name, declared=place(obj), definition=body or None)
            columns = obj.get("columns") or []
            _add_table(found, schema, name, _parts(obj, columns, dialect, objects))
            for column in columns:
                if f"{path}.{column['name']}" in found.objects and column.get("created"):
                    found.objects[f"{path}.{column['name']}"]["data"]["declared"] = place(column)
            for column in columns:  # a serial or identity column's sequence, named by the database
                if dialect == "postgres" and column["identity"] and kind == "table":
                    sequence = f"{name}_{column['name']}_seq"
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
            found.add(path, "trigger", table, name.split(":")[-1], declared=place(obj), definition=obj.get("definition"),
                      comment=obj.get("comment"), function=target, timing=obj.get("timing"), events=obj.get("events"),
                      for_each=obj.get("for_each"))
            if target:
                found.relate(path, target, "trigger calls")
        else:  # a function, procedure, sequence, type, domain, synonym...
            data = {k: v for k, v in obj.items() if k not in ("kind", "schema", "name", "created", "changed", "arguments")}
            path = routines.get(key) or found.path(schema, name)
            shown = f"{name}({_identity_arguments(obj.get('arguments', ''))})" if key in routines else name
            found.add(path, "enum" if kind == "type" and obj.get("labels") else kind, schema_path, shown, declared=place(obj), **data)
    for schema in {DEFAULT_SCHEMAS.get(dialect)} - {None, ""}:  # the schema every database of the dialect has
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


def describe_origins(origins: list[dict], catalog, connections: list[dict], root: Path) -> dict[str, dict]:
    """Which databases each origin describes, in layers, each link saying how it was made.

    1. Chosen by hand (the origin's page): always wins, also to take a link away.
    2. The tool's history table in a database read: the proof it migrated it (and how far).
    3. The origin's own configuration (Flyway's file), or a connection declared in the origin's folder.
    4. The names of its tables: only a suggestion, to confirm by hand.

    Args:
        origins: The origins read (`extract_origins`).
        catalog: The databases read (`CatalogStore`).
        connections: The project's connections (`ConnectionStore.connections`).
        root: The project's root.

    Returns:
        By origin name: `links` (`database`, `how`: list of `chosen`, `history`, `declared`; `history`
        what its history table says; `declared` the file or connection naming it), `unlinked` (taken
        away by hand), `suggestions` (`database`, `matched`, `total`) and `warning` when the layers disagree.
    """
    databases = catalog.objects(kind="database")
    tables = catalog.objects(kind="table") + catalog.objects(kind="view") + catalog.objects(kind="materialized view") \
        + catalog.objects(kind="foreign table")
    names: dict[str, set[str]] = {}
    for table in tables:
        database = "/".join(table["path"].split("/")[:2])
        schema = table["parent"].rsplit("/", 1)[-1]
        names.setdefault(database, set()).update({f"{schema}.{table['name']}".lower(), table["name"].lower()})
    choices = catalog.origin_choices()
    by_connection: dict[str, list[str]] = {}
    for database in databases:
        by_connection.setdefault(database["connection"], []).append(database["path"])
    found = {}
    for origin in origins:
        links: dict[str, dict] = {}

        def link(database: str, how: str, **detail) -> None:
            entry = links.setdefault(database, {"database": database, "how": [], "history": None, "declared": ""})
            if how not in entry["how"]:
                entry["how"].append(how)
            entry.update(detail)

        for table in tables:
            if table["name"].lower() != HISTORY_TOOLS.get(origin["kind"]) or "history" not in table["data"]:
                continue
            if (history := _history_link(origin, table["data"]["history"], root)) is not None:
                link("/".join(table["path"].split("/")[:2]), "history", history=history)
        for file, host, port, name in _declared_urls(root, origin):
            for database in databases:
                server, _, database_name = database["path"].removeprefix("db:").partition("/")
                server_host, _, server_port = server.rpartition(":")
                if database_name == name and _same_host(server_host) == _same_host(host) and (not port or port == server_port):
                    link(database["path"], "declared", declared=file)
        for connection in connections:
            if connection.get("folder") == origin["folder"]:
                for database in by_connection.get(connection["id"], []):
                    link(database, "declared", declared=f"{connection['name']} ({connection['origin']})")
        unlinked = []
        for (name, database), linked in choices.items():
            if name != origin["name"]:
                continue
            if linked:
                link(database, "chosen")
            else:
                links.pop(database, None)
                unlinked.append(database)
        own = {key for key, obj in origin["objects"].items() if obj["kind"] in ("table", "view", "materialized view", "foreign table")}
        suggestions = []
        if own:
            for database, held in names.items():
                if database in links or database in unlinked:
                    continue
                matched = sum(1 for key in own if key in held or key.split(".", 1)[-1] in held)
                if matched / len(own) >= 0.5:
                    suggestions.append({"database": database, "matched": matched, "total": len(own)})
        suggestions.sort(key=lambda s: -s["matched"])
        history = {d for d, e in links.items() if "history" in e["how"]}
        declared = {d for d, e in links.items() if "declared" in e["how"]}
        warning = ("Its configuration names one database, but its history is in another."
                   if history and declared and not history & declared else "")
        found[origin["name"]] = {"links": sorted(links.values(), key=lambda e: e["database"]), "unlinked": unlinked,
                                 "suggestions": suggestions[:3], "warning": warning}
    return found


def _type(text: str, dialect: str) -> str:
    """A column type as it is compared: what sqlglot makes of it in the origin's dialect, in lower case,
    a type of the project's own without its schema."""
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
    return _SAME_DEFAULTS.get(text, text)


def compare_origin(origin: dict, catalog, database: str) -> dict:
    """Where an origin's schema and a database it describes differ.

    Args:
        origin: The origin read.
        catalog: The databases read.
        database: The database's path.

    Returns:
        `missing` (the origin's tables and views the database lacks), `extra` (the database's tables
        the origin does not declare, the tools' history tables left out) and `tables`: by the
        origin's object key, its live `path` and its `differences` (columns missing either side, type,
        null, default, primary key, foreign keys, indexes).
    """
    live = {}
    for kind in ("table", "view", "materialized view", "foreign table"):
        for obj in catalog.objects(kind=kind, within=database):
            live[f"{obj['parent'].rsplit('/', 1)[-1]}.{obj['name']}".lower()] = obj
    columns: dict[str, dict[str, dict]] = {}
    for column in catalog.objects(kind="column", within=database):
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
            if column["default"] and not column["identity"] \
                    and _default(column["default"], origin["dialect"]) != _default(data.get("default", ""), origin["dialect"]):
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
