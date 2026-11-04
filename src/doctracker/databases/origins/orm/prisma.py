"""Read a Prisma schema (`schema.prisma`) into the DDL `prisma migrate` would write for it.

An origin is a `.prisma` file with models. Its `datasource` gives the provider (PostgreSQL, MySQL,
SQLite; CockroachDB is written as PostgreSQL); its `enum`s, `model`s and their fields are read from the
text: scalar types and the native ones (`@db.VarChar(80)`, `@db.Uuid`…), `Unsupported("…")`, optional
fields, `@id` / `@@id`, `@unique` / `@@unique`, `@@index` (with its `type`), `@default` (`autoincrement()`,
`now()`, `dbgenerated("…")`, literals, enum values; `uuid()` / `cuid()` are the client's, not the
database's), `@map` / `@@map`, `@@schema` (multiSchema), relations with their actions and `map:` names,
implicit many-to-many tables (`_AToB`), and `@ignore` / `@@ignore` (still in the database). The names
are Prisma's (`<table>_pkey`, `<table>_<columns>_key`, `_idx`, `_fkey`). The `migrations/` folder next to
it is SQL: an origin of its own, read by the SQL reader.
"""

import re
from pathlib import Path

from doctracker.databases.origins.orm.python import Project

KIND = "prisma schema"
"""The kind of the origins this reader finds."""

_PROVIDERS = {"postgresql": "postgres", "postgres": "postgres", "cockroachdb": "postgres", "mysql": "mysql", "sqlite": "sqlite"}

_SCALARS = {
    "postgres": {"String": "TEXT", "Int": "INTEGER", "BigInt": "BIGINT", "Boolean": "BOOLEAN", "Float": "DOUBLE PRECISION",
                 "Decimal": "DECIMAL(65,30)", "DateTime": "TIMESTAMP(3)", "Json": "JSONB", "Bytes": "BYTEA"},
    "mysql": {"String": "VARCHAR(191)", "Int": "INTEGER", "BigInt": "BIGINT", "Boolean": "BOOLEAN", "Float": "DOUBLE",
              "Decimal": "DECIMAL(65, 30)", "DateTime": "DATETIME(3)", "Json": "JSON", "Bytes": "LONGBLOB"},
    "sqlite": {"String": "TEXT", "Int": "INTEGER", "BigInt": "BIGINT", "Boolean": "BOOLEAN", "Float": "REAL", "Decimal": "DECIMAL",
               "DateTime": "DATETIME", "Json": "JSONB", "Bytes": "BLOB"},
}
"""The column type of each Prisma scalar, per provider."""

_NATIVE = {"Uuid": "UUID", "VarChar": "VARCHAR", "Char": "CHAR", "Text": "TEXT", "Timestamp": "TIMESTAMP", "Timestamptz": "TIMESTAMPTZ",
           "Decimal": "DECIMAL", "SmallInt": "SMALLINT", "Integer": "INTEGER", "Int": "INT", "BigInt": "BIGINT", "Date": "DATE",
           "Time": "TIME", "Timetz": "TIMETZ", "Inet": "INET", "JsonB": "JSONB", "Json": "JSON", "DoublePrecision": "DOUBLE PRECISION",
           "Real": "REAL", "Boolean": "BOOLEAN", "Money": "MONEY", "Xml": "XML", "Citext": "CITEXT", "Bit": "BIT", "VarBit": "VARBIT",
           "ByteA": "BYTEA", "TinyInt": "TINYINT", "MediumInt": "MEDIUMINT", "UnsignedInt": "INT UNSIGNED", "UnsignedBigInt": "BIGINT UNSIGNED",
           "Double": "DOUBLE", "Float": "FLOAT", "DateTime": "DATETIME", "TinyText": "TINYTEXT", "MediumText": "MEDIUMTEXT",
           "LongText": "LONGTEXT", "Blob": "BLOB", "LongBlob": "LONGBLOB", "Year": "YEAR"}
"""Prisma's native types (`@db.X`) and the type they write."""

_ACTIONS = {"Cascade": "CASCADE", "SetNull": "SET NULL", "Restrict": "RESTRICT", "NoAction": "NO ACTION", "SetDefault": "SET DEFAULT"}
_CLIENT_DEFAULTS = ("uuid(", "cuid(", "nanoid(", "ulid(")


def find(root: Path, files: list[str], project: Project) -> list[dict]:
    """The project's Prisma schemas: each `.prisma` file declaring a model is an origin."""
    origins = []
    for file in sorted(files):
        if file.endswith(".prisma"):
            try:
                text = (root / file).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"^\s*model\s+\w+\s*\{", text, re.MULTILINE):
                folder = str(Path(file).parent.as_posix())
                origins.append({"name": file, "kind": KIND, "folder": folder,
                                "related": f"{folder}/migrations" if (root / folder / "migrations").is_dir() else "",
                                "steps": [{"file": file, "version": "", "title": Path(file).name}]})
    return origins


def dialect(root: Path, origin: dict, project: Project) -> tuple[str, str]:
    """The provider of the schema's `datasource`."""
    text = (root / origin["steps"][0]["file"]).read_text(encoding="utf-8", errors="replace")
    match = re.search(r"datasource\s+\w+\s*\{[^}]*?provider\s*=\s*\"(\w+)\"", text, re.DOTALL)
    if match and match[1] in _PROVIDERS:
        return _PROVIDERS[match[1]], f"provider in {Path(origin['steps'][0]['file']).name}"
    return "postgres", "no provider written: PostgreSQL"


def _blocks(text: str, word: str):
    """Each `<word> Name { ... }` block: its name, its line, its field lines `(line, text)` and its `@@` lines."""
    for match in re.finditer(rf"^{word}\s+(\w+)\s*\{{(.*?)^\}}", text, re.DOTALL | re.MULTILINE):
        first = text.count("\n", 0, match.start()) + 1
        fields, attributes = [], []
        for offset, raw in enumerate(match.group(2).splitlines()):
            line = raw.split("//")[0].strip()
            if line.startswith("@@"):
                attributes.append(line)
            elif line:
                fields.append((first + offset, line))
        yield match.group(1), first, fields, attributes


def _attribute(rest: str, name: str) -> str | None:
    """What `@name(...)` holds (balanced parentheses); "" when written without; None when absent."""
    match = re.search(rf"@{re.escape(name)}\b(\()?", rest)
    if not match:
        return None
    if not match.group(1):
        return ""
    depth, at = 1, match.end()
    while depth and at < len(rest):
        depth += {"(": 1, ")": -1}.get(rest[at], 0)
        at += 1
    return rest[match.end():at - 1]


def _listed(text: str) -> list[str]:
    match = re.search(r"\[([^\]]*)\]", text or "")
    return [item.strip() for item in match.group(1).split(",") if item.strip()] if match else []


def _named(text: str | None, key: str) -> str | None:
    match = re.search(rf'{key}:\s*"([^"]+)"', text or "")
    return match.group(1) if match else None


def read(root: Path, origin: dict, dialect_name: str, project: Project) -> dict:
    """Read a Prisma schema.

    Returns:
        `statements` (`file`, `line`, `text`), `unresolved`, `expects` (none) and `mapping` (model ↔
        table, field ↔ column).
    """
    file = origin["steps"][0]["file"]
    text = (root / file).read_text(encoding="utf-8", errors="replace")
    provider = dialect_name if dialect_name in _SCALARS else "postgres"

    def quote(name: str) -> str:
        return f"`{name}`" if provider == "mysql" else f'"{name}"'

    def qualified(schema: str, table: str) -> str:
        return f'"{schema}"."{table}"' if schema and provider == "postgres" else quote(table)

    enums: dict[str, tuple[str, str, dict[str, str], int]] = {}
    for name, line, fields, attributes in _blocks(text, "enum"):
        joined = " ".join(attributes)
        values = {}
        for _, field in fields:
            value = field.split()[0]
            mapped = re.search(r'@map\("([^"]+)"\)', field)
            values[value] = mapped.group(1) if mapped else value
        enums[name] = ((re.search(r'@@schema\("([^"]+)"\)', joined) or [None, "public"])[1],
                       (re.search(r'@@map\("([^"]+)"\)', joined) or [None, name])[1], values, line)
    models = {}
    for name, line, fields, attributes in _blocks(text, "model"):
        joined = " ".join(attributes)
        parsed = []
        for field_line, field in fields:
            match = re.match(r"(\w+)\s+(Unsupported\(\"[^\"]+\"\)|\w+)(\[\])?(\?)?\s*(.*)", field)
            if match:
                parsed.append((field_line, *match.groups()))
        models[name] = {"table": (re.search(r'@@map\("([^"]+)"\)', joined) or [None, name])[1],
                        "schema": (re.search(r'@@schema\("([^"]+)"\)', joined) or [None, "public" if provider == "postgres" else ""])[1],
                        "fields": parsed, "attributes": attributes, "line": line}

    def column(model: str, field: str) -> str:
        for _, name, _, _, _, rest in models[model]["fields"]:
            if name == field:
                mapped = re.search(r'@map\("([^"]+)"\)', rest)
                return mapped.group(1) if mapped else name
        return field

    def column_type(kind: str, rest: str) -> str:
        native = re.search(r"@db\.(\w+)(?:\(([^)]*)\))?", rest)
        if native:
            written = _NATIVE.get(native.group(1), native.group(1).upper())
            arguments = native.group(2)
            if arguments:
                arguments = arguments.replace(" ", "") if provider == "postgres" else ", ".join(a.strip() for a in arguments.split(","))
                return f"{written}({arguments})"
            return written
        if kind.startswith("Unsupported"):
            return re.search(r'"([^"]+)"', kind).group(1)
        if kind in enums:
            schema, enum_name, values, _ = enums[kind]
            if provider == "mysql":
                return "ENUM(" + ", ".join("'" + v + "'" for v in values.values()) + ")"
            return qualified(schema, enum_name) if provider == "postgres" else "TEXT"
        return _SCALARS[provider][kind]

    def key_type(model: str) -> str:
        for _, name, kind, _, _, rest in models[model]["fields"]:
            if _attribute(rest, "id") is not None:
                return column_type(kind, rest)
        return "INTEGER"

    statements, indexes, keys, unresolved, mapping = [], [], [], [], []
    for name, (schema, enum_name, values, line) in enums.items():
        if provider == "postgres":
            statements.append({"file": file, "line": line, "text": f"CREATE TYPE {qualified(schema, enum_name)} AS ENUM ("
                                                                    + ", ".join("'" + v + "'" for v in values.values()) + ")"})
    many: dict[tuple[str, str], int] = {}
    for name, model in models.items():
        table, schema, place = model["table"], model["schema"], {"file": file, "line": model["line"]}
        target = qualified(schema, table)
        parts, inline, primary = [], [], []
        joined = " ".join(model["attributes"])
        identifier = re.search(r"@@id\(([^)]*)\)", joined)
        for line, field, kind, listed, optional, rest in model["fields"]:
            if kind in models:  # a relation
                relation = _attribute(rest, "relation") or ""
                if "fields:" in relation:
                    columns = [column(name, f) for f in _listed(relation.split("fields:", 1)[1])]
                    targets = [column(kind, f) for f in _listed(relation.split("references:", 1)[1])]
                    delete = re.search(r"onDelete:\s*(\w+)", relation)
                    update = re.search(r"onUpdate:\s*(\w+)", relation)
                    optional_side = all(f[4] for f in model["fields"] if f[1] in _listed(relation.split("fields:", 1)[1]))
                    actions = (f" ON DELETE {_ACTIONS[delete.group(1)] if delete else ('SET NULL' if optional_side else 'RESTRICT')}"
                               f" ON UPDATE {_ACTIONS[update.group(1)] if update else 'CASCADE'}")
                    constraint = _named(relation, "map") or f"{table}_{'_'.join(columns)}_fkey"
                    clause = (f"CONSTRAINT {quote(constraint)} FOREIGN KEY ({', '.join(quote(c) for c in columns)}) REFERENCES "
                              f"{qualified(models[kind]['schema'], models[kind]['table'])} ({', '.join(quote(c) for c in targets)}){actions}")
                    if provider == "sqlite":
                        inline.append(clause)
                    else:
                        keys.append({"file": file, "line": line, "text": f"ALTER TABLE {target} ADD {clause}"})
                elif listed:  # a list on both sides, no fields on either: an implicit many-to-many
                    back = [f for f in models[kind]["fields"] if f[2] == name and f[3] and (kind != name or f[1] != field)]
                    paired = any(f[2] == name and "fields:" in (_attribute(f[5], "relation") or "") for f in models[kind]["fields"])
                    if back and not paired:
                        many.setdefault(tuple(sorted((name, kind))), line)
                continue
            if listed and provider != "postgres":
                unresolved.append({"file": file, "line": line, "what": f"{name}.{field}: a list of scalars ({provider} has no arrays)"})
                continue
            name_in_db = column(name, field)
            typ = column_type(kind, rest) + ("[]" if listed else "")
            default = _attribute(rest, "default")
            value = None
            if default == "autoincrement()":
                if provider == "postgres":
                    typ = {"INTEGER": "SERIAL", "BIGINT": "BIGSERIAL", "SMALLINT": "SMALLSERIAL"}.get(typ, typ)
                elif provider == "mysql":
                    typ += " NOT NULL AUTO_INCREMENT"
            elif default == "now()":
                value = "CURRENT_TIMESTAMP(3)" if provider == "mysql" else "CURRENT_TIMESTAMP"
            elif default and default.startswith("dbgenerated("):
                found = re.search(r'"(.*)"', default)
                value = found.group(1) if found else None
            elif default and default.startswith(_CLIENT_DEFAULTS):
                value = None
            elif default and default.startswith('"'):
                value = "'" + default.strip('"').replace("'", "''") + "'"
            elif default and kind in enums:
                value = "'" + enums[kind][2].get(default, default) + "'"
            elif default:
                value = default
            is_key = _attribute(rest, "id") is not None
            not_null = "" if optional else " NOT NULL"
            if provider == "mysql" and "AUTO_INCREMENT" in typ:
                written = f"{quote(name_in_db)} {typ}"
            else:
                written = f"{quote(name_in_db)} {typ}{not_null}" + (" NULL" if optional and provider == "mysql" else "")
            if provider == "sqlite" and is_key and not identifier:
                written += " PRIMARY KEY" + (" AUTOINCREMENT" if default == "autoincrement()" and typ == "INTEGER" else "")
            if value is not None:
                written += f" DEFAULT {value}"
            parts.append(written)
            if is_key:
                primary = [name_in_db]
            unique = _attribute(rest, "unique")
            if unique is not None:
                indexes.append((line, True, _named(unique, "map") or f"{table}_{name_in_db}_key", [name_in_db], None))
            mapping_columns = mapping[-1]["columns"] if mapping and mapping[-1]["class"] == name else None
            if mapping_columns is None:
                mapping.append({"class": name, "table": table, **place, "columns": {}})
                mapping_columns = mapping[-1]["columns"]
            mapping_columns[field] = name_in_db
        if identifier:
            primary = [column(name, f) for f in _listed(identifier.group(1))]
        if primary and not (provider == "sqlite" and not identifier):
            pk_name = _named(identifier.group(1), "map") if identifier else None
            parts.append((f"CONSTRAINT {quote(pk_name or table + '_pkey')} " if provider == "postgres" else "")  # MySQL and SQLite name none
                         + f"PRIMARY KEY ({', '.join(quote(c) for c in primary)})")
        for attribute in model["attributes"]:
            match = re.match(r"@@(unique|index)\((.*)\)$", attribute)
            if match:
                columns = [column(name, f.split("(")[0]) for f in _listed(match.group(2))]
                given = _named(match.group(2), "map") or f"{table}_{'_'.join(columns)}_{'key' if match.group(1) == 'unique' else 'idx'}"
                using = re.search(r"type:\s*(\w+)", match.group(2))
                indexes.append((model["line"], match.group(1) == "unique", given, columns, using.group(1).upper() if using else None))
        if provider == "mysql":  # MySQL writes them inside the table
            for _, unique, given, columns, _ in indexes:
                parts.insert(len(parts) - (1 if primary else 0), f"{'UNIQUE ' if unique else ''}INDEX {quote(given)}({', '.join(quote(c) for c in columns)})")
            indexes = []
        statements.append({**place, "text": f"CREATE TABLE {target} (" + ", ".join(parts + inline) + ")"
                                            + (" DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" if provider == "mysql" else "")})
        for line, unique, given, columns, using in indexes:
            statements.append({"file": file, "line": line, "text": f"CREATE {'UNIQUE ' if unique else ''}INDEX {quote(given)} ON {target}"
                                                                    + (f" USING {using}" if using else "") + f" ({', '.join(quote(c) for c in columns)})"})
        indexes = []
    for (first, second), line in many.items():  # _<A>To<B>: the two models in alphabetical order, columns A and B
        table = f"_{first}To{second}"
        target = qualified(models[first]["schema"], table)
        a, b = key_type(first), key_type(second)
        statements.append({"file": file, "line": line, "text": f"CREATE TABLE {target} ({quote('A')} {a} NOT NULL, {quote('B')} {b} NOT NULL, "
                                                                f"CONSTRAINT {quote(table + '_AB_pkey')} PRIMARY KEY ({quote('A')}, {quote('B')}))"})
        statements.append({"file": file, "line": line, "text": f"CREATE INDEX {quote(table + '_B_index')} ON {target} ({quote('B')})"})
        for side, model in (("A", first), ("B", second)):
            keys.append({"file": file, "line": line, "text": f"ALTER TABLE {target} ADD CONSTRAINT {quote(f'{table}_{side}_fkey')} FOREIGN KEY "
                                                          f"({quote(side)}) REFERENCES {qualified(models[model]['schema'], models[model]['table'])} "
                                                          f"({quote('id')}) ON DELETE CASCADE ON UPDATE CASCADE"})
    return {"statements": statements + keys, "unresolved": unresolved, "expects": [], "mapping": mapping}


__all__ = ["KIND", "dialect", "find", "read"]
