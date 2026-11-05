"""Samples of a table's data, the profile of each column, and the relations found through the data.

A table's sample is `SAMPLE_ROWS` rows taken at random (from a live database, or from the rows a dump
holds), turned at once into what may be kept: a column's profile (nulls, distinct values, smallest and
largest, lengths, the most frequent values, the formats found) and a few rows to show. A sensitive
column (by its name, its comment, or the format of its values) never keeps a value: each letter and
digit becomes `*`, the rest stays (`joao@google.com` → `****@******.***`), and its masks are listed
once each. The values themselves stay in the process that read them.

Relations through the data: the distinct values of each key column (a one-column primary key or unique
column, not sensitive) are kept, up to `KEY_VALUES`; a column of a compatible type whose sampled values
are, at least `CONTAINED` of them, among a key's values is `contained in` that key, the best one only (see `containment`). Live
databases are compared with each other; what a file declares, only within that file.

The same functions serve the live databases (`collect`) and the dumps (`origins.sql.read_origin`).
"""

import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, time

from sqlglot import exp

from doctracker.databases.readonly import DIALECTS, TIMEOUT_SECONDS

SAMPLE_ROWS = 1000
"""Rows taken at random from each table."""

SHOWN = 20
"""Most values (and rows) a sample shows."""

KEY_VALUES = 100_000
"""Most distinct values kept of a key column, to find the columns contained in it."""

CONTAINED = 0.8
"""Share of a column's sampled values that must be among a key's values for it to be `contained in` it."""

LEAST_DISTINCT = 10
"""Fewest distinct sampled values a column needs to be compared with the keys (fewer fit in any key)."""

QUERY_SECONDS = TIMEOUT_SECONDS
"""Longest a sample's query may run; one that takes longer leaves the table unsampled, with the reason."""

LONGEST = 200
"""Longest text kept of a value; a longer one is cut, ending with `…`."""

SAMPLED_KINDS = ("table", "materialized view")
"""The kinds of object sampled: views are not (reading one runs its query)."""

_RANDOM = {"postgresql": "random()", "sqlite": "random()", "mysql": "RAND()", "mssql": "NEWID()", "oracle": "dbms_random.value"}
"""What orders rows at random, per kind of database."""

FORMATS = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$"),
    "cpf": re.compile(r"^\d{3}\.\d{3}\.\d{3}-\d{2}$"),
    "cnpj": re.compile(r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$"),
    "phone": re.compile(r"^\+?\d{1,3}[ -]?\(?\d{2,3}\)?[ -]?\d{4,5}-?\d{4}$"),
    "card": re.compile(r"^(?:\d[ -]?){12,18}\d$"),
    "password hash": re.compile(r"^\$(2[abxy]|argon2(id|i|d)|pbkdf2[-\w]*|scrypt|[156])\$"),
    "token": re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]+$"),
    "uuid": re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE),
    "ip": re.compile(r"^\d{1,3}(\.\d{1,3}){3}$"),
    "url": re.compile(r"^https?://\S+$", re.IGNORECASE),
    "postal code": re.compile(r"^\d{5}-\d{3}$"),
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([+-]\d{2}(:?\d{2})?|Z)?)?$"),
}
"""The formats a value is recognised by, the first that matches."""

SENSITIVE_FORMATS = {"email", "cpf", "cnpj", "phone", "card", "password hash", "token"}
"""The formats that make a column sensitive."""

_SENSITIVE_NAME = re.compile(
    r"(^|_)(e_?mail|cpf|cnpj|ssn|rg|passport|passaporte|phone|telefone|celular|mobile|password|passwd|senha|pwd|hash|"
    r"token|secret|segredo|api_?key|salary|salario|wage|income|renda|birth|birthday|nascimento|dob|address|endereco|"
    r"street|card|cartao|iban|tax_?id|nif)(s?)($|_)", re.IGNORECASE)
"""Words of a column's name that make it sensitive (`email`, `customer_cpf`, `password_hash`, `birth_date`...)."""

_SENSITIVE_COMMENT = re.compile(r"\b(sensitive|sens[ií]vel|pii|lgpd|gdpr|confidential|confidencial|personal data|"
                                r"dados? pessoa(l|is)|private|privado)\b", re.IGNORECASE)
"""Words of a column's comment that make it sensitive."""


def sample_query(kind: str, schema: str, table: str) -> str:
    """The query reading `SAMPLE_ROWS` rows of a table at random, in the database's own SQL.

    Args:
        kind: The kind of database (`postgresql`, `mysql`, `mssql`, `sqlite`...).
        schema: The table's schema (ignored for SQLite).
        table: The table's name.

    Returns:
        The query; MySQL's carries its time limit as a hint (the other drivers end a query by their own timeout).
    """
    dialect = DIALECTS[kind]
    query = exp.select("*").from_(exp.table_(table, db=None if kind == "sqlite" else schema, quoted=True)) \
        .order_by(exp.maybe_parse(_RANDOM[kind], dialect=dialect)).limit(SAMPLE_ROWS).sql(dialect)
    if kind == "mysql":
        query = query.replace("SELECT", f"SELECT /*+ MAX_EXECUTION_TIME({QUERY_SECONDS * 1000}) */", 1)
    return query


def keys_query(kind: str, schema: str, table: str, column: str) -> str:
    """The query reading the distinct values of a key column, at most `KEY_VALUES` and one more (to tell
    when there were more)."""
    dialect = DIALECTS[kind]
    name = exp.column(column, quoted=True)
    query = exp.select(name).distinct().from_(exp.table_(table, db=None if kind == "sqlite" else schema, quoted=True)) \
        .where(name.is_(exp.null()).not_()).limit(KEY_VALUES + 1).sql(dialect)
    if kind == "mysql":
        query = query.replace("SELECT", f"SELECT /*+ MAX_EXECUTION_TIME({QUERY_SECONDS * 1000}) */", 1)
    return query


def as_text(value: object) -> str | None:
    """A value as the driver gives it, as text: None for NULL, `<n bytes>` for binary data, JSON for a
    document, ISO 8601 for dates and times."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray, memoryview)):
        return f"<{len(bytes(value))} bytes>"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    return str(value)


def mask(value: str) -> str:
    """A sensitive value with every letter and digit as `*`, the rest kept: `joao@google.com` → `****@******.***`."""
    return re.sub(r"[^\W_]", "*", value)


def value_format(value: str) -> str:
    """The format a value is recognised by (a key of `FORMATS`), or empty."""
    for name, pattern in FORMATS.items():
        if pattern.match(value) and (name != "card" or _luhn(value)):
            return name
    return ""


def _luhn(value: str) -> bool:
    """Whether a card number's digits pass the Luhn check."""
    digits = [int(d) for d in re.sub(r"\D", "", value)][::-1]
    return sum(d if i % 2 == 0 else (d * 2 - 9 if d > 4 else d * 2) for i, d in enumerate(digits)) % 10 == 0


def sensitive(name: str, comment: str, values: list[str]) -> str:
    """Why a column is sensitive, or empty when it is not: by its name, its comment, or the format of
    any of its values.

    Args:
        name: The column's name.
        comment: Its comment.
        values: Its values (not NULL), as text.

    Returns:
        `name`, `comment`, or `format: <format>` (e.g. `format: email`); empty when none says so.
    """
    if _SENSITIVE_NAME.search(name):
        return "name"
    if comment and _SENSITIVE_COMMENT.search(comment):
        return "comment"
    for value in set(values):
        if (found := value_format(value)) in SENSITIVE_FORMATS:
            return f"format: {found}"
    return ""


def family(type_: str) -> str:
    """The family of a column's type for comparing values: `integer`, `text`, `uuid`; empty for any other."""
    written = type_.lower()
    if "uuid" in written or "uniqueidentifier" in written:
        return "uuid"
    if re.search(r"int|serial|^number\(\d+(,\s*0)?\)$", written) and not re.search(r"interval|point", written):
        return "integer"
    if re.search(r"char|text|string|clob", written):
        return "text"
    return ""


def _cut(value: str) -> str:
    """A value cut to `LONGEST` characters."""
    return value if len(value) <= LONGEST else value[:LONGEST - 1] + "…"


def _order(values: list[str]) -> list[str]:
    """Values in order: as numbers when they all are, else as text."""
    try:
        return sorted(values, key=float)
    except ValueError:
        return sorted(values)


def profile(name: str, type_: str, comment: str, values: list[str | None], marks: list[str]) -> dict:
    """The profile of a column from its sampled values.

    Args:
        name: The column's name.
        type_: Its type, as written.
        comment: Its comment.
        values: Its sampled values, as text (None for NULL).
        marks: Its marks (`pk`, `fk`, `unique`...): a one-column key's values are compared with the others.

    Returns:
        `sensitive` (why, or empty), `nulls`, `distinct`, `min`, `max`, `min_length`, `max_length`,
        `frequent` (the 5 most frequent values and how many times each), `formats` (each format found
        and how many values have it) and `values` (at most `SHOWN` distinct values, in sample order);
        a sensitive column's values masked. For finding containment: `family`, `marks` and, when not
        sensitive, `probe` (its distinct sampled values).
    """
    present = [v for v in values if v is not None]
    why = sensitive(name, comment, present)
    shown = mask if why else (lambda value: value)
    counts = Counter(shown(v) for v in present)
    formats = Counter(found for v in present if (found := value_format(v)))
    ordered = _order(list(set(present)))
    found = {"sensitive": why, "nulls": len(values) - len(present), "distinct": len(set(present)),
             "min": _cut(shown(ordered[0])) if ordered else None, "max": _cut(shown(ordered[-1])) if ordered else None,
             "min_length": min(map(len, present)) if present else None, "max_length": max(map(len, present)) if present else None,
             "frequent": [[_cut(v), n] for v, n in counts.most_common(5) if n > 1],
             "formats": dict(formats.most_common()), "values": [_cut(v) for v in list(dict.fromkeys(shown(v) for v in present))[:SHOWN]],
             "family": family(type_), "marks": marks}
    if not why and found["family"]:
        found["probe"] = sorted(set(present))
    return found


def table_sample(columns: list[dict], names: list[str], rows: list[list[str | None]]) -> dict:
    """What is kept of a table's sampled rows: each column's profile, and a few rows, masked where sensitive.

    Args:
        columns: The table's columns as read (`name`, `data` with `type`, `comment`, `marks`); a column
            of the rows that is not among them is profiled by its values alone.
        names: The names of the rows' columns, in order.
        rows: The rows, each value as text (None for NULL).

    Returns:
        `rows` (how many were sampled), `columns` (the names), `shown` (at most `SHOWN` rows) and
        `profiles` (by column name, see `profile`).
    """
    by_name = {c["name"]: c.get("data") or {} for c in columns}
    profiles = {}
    for index, name in enumerate(names):
        data = by_name.get(name, {})
        profiles[name] = profile(name, str(data.get("type") or ""), str(data.get("comment") or ""),
                                 [row[index] for row in rows], list(data.get("marks") or []))
    shown = [[None if value is None else _cut(mask(value) if profiles[name]["sensitive"] else value)
              for name, value in zip(names, row)] for row in rows[:SHOWN]]
    return {"rows": len(rows), "columns": names, "shown": shown, "profiles": profiles}


def key_columns(sample: dict, primary_key: list[str]) -> list[str]:
    """The columns of a sampled table whose distinct values are kept: a one-column primary key or unique
    column, of a compared family, not sensitive."""
    return [name for name, found in sample["profiles"].items() if found["family"] and not found["sensitive"]
            and (primary_key == [name] or "unique" in found["marks"])]


def signature(columns: list[dict]) -> str:
    """What a table's sample depends on: each column's name, type, null, default, computation and marks.
    A table is sampled again when it changes."""
    held = [[c["name"], c["data"].get("type"), c["data"].get("nullable"), c["data"].get("default"),
             c["data"].get("computed"), c["data"].get("marks")] for c in columns]
    return hashlib.sha256(json.dumps(held, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def containment(tables: list[dict]) -> list[dict]:
    """Find, for each column, the key column its values are contained in.

    Each column is compared with every key column of its family in the same scope; of those holding at
    least `CONTAINED` of its sampled values, only the best is kept: the highest share, then a key in the
    same database, then a key whose name matches the column's (`product_id` → `products`, `sku` →
    `sku`), then the key with the fewest values.

    Args:
        tables: Each sampled table's `path`, `scope` (tables are compared only within the same scope)
            and `data` (see `table_sample`, with `keys`: by column, its distinct values).

    Returns:
        `table` (the source's), `source` (the column), `target` (the key column) and `ratio` (the share of
        the source's sampled values found among the key's); a column already declared as a foreign key,
        and a table's one-column primary key, are not sources.
    """
    targets: dict[tuple[str, str], list[tuple[str, str, str, set[str]]]] = {}
    for table in tables:
        for column, values in (table["data"].get("keys") or {}).items():
            found = table["data"]["profiles"].get(column) or {}
            targets.setdefault((table["scope"], found.get("family", "")), []).append(
                (f"{table['path']}.{column}", _database(table["path"]), _table_name(table["path"]), set(values)))
    relations = []
    for table in tables:
        for column, found in table["data"].get("profiles", {}).items():
            probe = found.get("probe") or []
            if len(probe) < LEAST_DISTINCT or "fk" in found["marks"] or ("pk" in found["marks"] and column in (table["data"].get("keys") or {})):
                continue
            source, wanted, home = f"{table['path']}.{column}", set(probe), _database(table["path"])
            base = column.lower().removesuffix("_id")
            best = None
            for target, database, name, values in targets.get((table["scope"], found["family"]), []):
                ratio = len(wanted & values) / len(wanted)
                if target == source or ratio < CONTAINED:
                    continue
                named = name.lower() in (base, base + "s", base + "es") or target.rsplit(".", 1)[-1].lower() == column.lower()
                rank = (round(ratio, 4), database == home, named, -len(values))
                if best is None or rank > best[0]:
                    best = (rank, target, ratio)
            if best is not None:
                relations.append({"table": table["path"], "source": source, "target": best[1], "ratio": round(best[2], 4)})
    return relations


def _database(path: str) -> str:
    """The database a table's path is in (`db:<server>/<database>`, or a file's `origin:<name>`)."""
    return path.split("::", 1)[0] if "::" in path else "/".join(path.split("/")[:2])


def _table_name(path: str) -> str:
    """A table's own name, from its path."""
    return path.split("::", 1)[-1].split("/")[-1].split(".", 1)[-1]


__all__ = ["CONTAINED", "FORMATS", "KEY_VALUES", "LEAST_DISTINCT", "SAMPLED_KINDS", "SAMPLE_ROWS", "SENSITIVE_FORMATS", "SHOWN",
           "as_text", "containment", "family", "key_columns", "keys_query", "mask", "profile", "sample_query", "sensitive",
           "signature", "table_sample", "value_format"]
