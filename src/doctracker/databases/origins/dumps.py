"""Recognise schema dumps and read what they say of themselves.

A dump is known by the mark its tool writes in it, never by the file's name: pg_dump and pg_dumpall
(`-- PostgreSQL database dump`, `-- PostgreSQL database cluster dump`), mysqldump and mariadb-dump
(`-- MySQL dump`, `-- MariaDB dump`), the sqlite3 command's `.dump` (`PRAGMA foreign_keys=OFF;` then
`BEGIN TRANSACTION;`), SQL Server Management Studio's "Generate Scripts" (`/****** Object: …
Script Date: … ******/`), and Python's `sqlite3` `iterdump()` by its whole shape. What the dump writes
of itself (its tool and version, the server's version, the host and database it came from, the encoding,
when it was made) is read as written, each with its line, nothing deduced. A dump of several databases
(pg_dumpall, `mysqldump --databases`, several `USE`) is cut into the lines of each one. When the dump
does not say when it was made, the last commit of the file says when it entered the repository; the
file's date on disk is never used (a clone or a checkout changes it).

The rows a dump holds (PostgreSQL's `COPY … FROM stdin` blocks, and `INSERT … VALUES` of every tool) are
read too, without running anything: a sample of each table's rows taken at random and the values of its
key columns go through the same code as a live database's (`samples`), and only what that code keeps
leaves this module.
"""

import random
import re
from collections.abc import Iterator
from pathlib import Path

from doctracker.databases import samples
from doctracker.history.git_log import last_change

TOOLS = {"pg_dump": "pg_dump", "pg_dumpall": "pg_dumpall", "mysqldump": "mysqldump", "mariadb-dump": "mariadb-dump",
         "sqlite3": "sqlite3 .dump", "iterdump": "Python's sqlite3 iterdump()", "ssms": "SQL Server Management Studio (Generate Scripts)"}
"""Each tool a dump is recognised as, and how its name is shown."""

_MARKS = [("pg_dumpall", re.compile(r"^--\s*PostgreSQL database cluster dump\s*$", re.MULTILINE)),
          ("pg_dump", re.compile(r"^--\s*PostgreSQL database dump\s*$", re.MULTILINE)),
          ("mariadb-dump", re.compile(r"^--\s*MariaDB dump\b", re.MULTILINE)),
          ("mysqldump", re.compile(r"^--\s*MySQL dump\b", re.MULTILINE)),
          ("sqlite3", re.compile(r"\A\s*PRAGMA foreign_keys=OFF;\s*\nBEGIN TRANSACTION;", re.IGNORECASE)),
          ("ssms", re.compile(r"^/\*{6} Object:.*Script Date:.*\*{6}/", re.MULTILINE))]
"""The mark each tool writes, the cluster dump's before the database dump's (both start alike)."""

_ITERDUMP_LINE = re.compile(r"""^(CREATE\s|INSERT INTO "[^"]+" VALUES|INSERT INTO sqlite_(master|schema)\s*\(|PRAGMA writable_schema=|"""
                            r"""DELETE FROM "?sqlite_sequence"?;|ANALYZE sqlite_(master|schema);)""", re.IGNORECASE)
"""How a line of `iterdump()` starts (a statement it writes; the lines of a statement spanning several start otherwise)."""


def _is_iterdump(text: str) -> bool:
    """Whether a file has the whole shape of Python's `iterdump()`: `BEGIN TRANSACTION;` first, `COMMIT;`
    last, and between only what it writes (tables, indexes, triggers, views, their rows, virtual tables
    as `INSERT INTO sqlite_schema`, `PRAGMA writable_schema`)."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or lines[0].strip() != "BEGIN TRANSACTION;" or lines[-1].strip() != "COMMIT;":
        return False
    starts, depth = 0, 0
    for line in lines[1:-1]:
        if depth == 0 and not line.startswith((" ", "\t", ")")):  # a statement's first line
            if not _ITERDUMP_LINE.match(line) and line.strip() != "END;" \
                    and not re.match(r"^(BEGIN|SELECT|FROM|WHERE|GROUP|ORDER|UNION|JOIN|LEFT|ON)\b", line):  # a trigger's or view's body
                return False
            starts += 1
    return starts > 0


def recognise(text: str) -> str | None:
    """The tool a file was dumped with (a key of `TOOLS`), or None when it is not a dump."""
    for tool, mark in _MARKS:
        if mark.search(text):
            return tool
    return "iterdump" if _is_iterdump(text) else None


_HEADER = {
    "pg_dump": [("server", r"^--\s*Dumped from database version (.+)$"), ("version", r"^--\s*Dumped by pg_dump version (.+)$"),
                ("encoding", r"^SET client_encoding = '([^']+)';"), ("database", r"^CREATE DATABASE (\S+)"),
                ("made", r"^--\s*(?:Started|Completed) on (.+)$")],
    "pg_dumpall": [("server", r"^--\s*Dumped from database version (.+)$"), ("version", r"^--\s*Dumped by pg_dump version (.+)$"),
                   ("encoding", r"^SET client_encoding = '([^']+)';"), ("made", r"^--\s*(?:Started|Completed) on (.+)$")],
    "mysqldump": [("version", r"^--\s*MySQL dump (.+)$"), ("host", r"^--\s*Host:\s*(\S+)"), ("database", r"^--\s*Host:.*?Database:\s*(\S+)"),
                  ("server", r"^--\s*Server version\s+(.+)$"), ("encoding", r"SET NAMES (\w+)"), ("made", r"^--\s*Dump completed on (.+)$")],
    "mariadb-dump": [("version", r"^--\s*MariaDB dump (.+)$"), ("host", r"^--\s*Host:\s*(\S+)"),
                     ("database", r"^--\s*Host:.*?Database:\s*(\S+)"), ("server", r"^--\s*Server version\s+(.+)$"),
                     ("encoding", r"SET NAMES (\w+)"), ("made", r"^--\s*Dump completed on (.+)$")],
    "ssms": [("database", r"^USE \[([^\]]+)\]"), ("made", r"Script Date:\s*(.+?)\s*\*{6}/")],
    "sqlite3": [], "iterdump": [],
}
"""What each tool writes of itself: the key, and the pattern whose group is its value (the first found)."""

_DATE_FORMATS = [r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)\s*(\S*)",  # 2026-10-30 14:17:04 [UTC|-03]
                 r"(\d{1,2})/(\d{1,2})/(\d{4}) (\d{1,2}):(\d{2}):(\d{2}) ?([AP]M)"]  # SSMS: 11/4/2026 10:00:00 AM


def _date(written: str) -> tuple[str, bool] | None:
    """A date as a dump writes it, in ISO 8601, and whether it has a time zone."""
    match = re.match(_DATE_FORMATS[0], written)
    if match:
        zone = match[3] if match[3] and re.match(r"^(UTC|GMT|Z|[+-]\d{2}(:?\d{2})?|[A-Z]{3,4})$", match[3]) else ""
        return f"{match[1]}T{match[2]}" + (f" {zone}" if zone else ""), bool(zone)
    match = re.match(_DATE_FORMATS[1], written)
    if match:
        month, day, year, hour, minute, second, half = match.groups()
        hour = int(hour) % 12 + (12 if half == "PM" else 0)
        return f"{year}-{int(month):02d}-{int(day):02d}T{hour:02d}:{minute}:{second}", False
    return None


def header(text: str, tool: str) -> dict[str, dict]:
    """What a dump writes of itself, as written: by key (`tool`, `version`, `server`, `host`, `database`,
    `encoding`, `made`), its `value` and `line`."""
    found = {"tool": {"value": TOOLS[tool], "line": 0}}
    for key, pattern in _HEADER.get(tool, []):
        if key == "made":  # the last one written: pg_dump --verbose writes Started on, then Completed on
            matches = list(re.finditer(pattern, text, re.MULTILINE))
            match = matches[-1] if matches else None
        else:
            match = re.search(pattern, text, re.MULTILINE)
        if match:
            found[key] = {"value": match[1].strip().strip("`\"'"), "line": text.count("\n", 0, match.start()) + 1}
    return found


def generated(root: Path, file: str, written: dict[str, dict]) -> dict:
    """When a dump was made, and where that comes from: the date it writes (`source` `dump`, its `line`,
    and whether it has a `zone`), else the last commit of the file (`source` `git`, its `commit`: when it
    entered the repository, not when it was made), else unknown (`source` None)."""
    made = written.get("made")
    if made and (parsed := _date(made["value"])):
        return {"at": parsed[0], "source": "dump", "line": made["line"], "zone": parsed[1], "written": made["value"]}
    change = last_change(root, file)
    if change:
        return {"at": change[1], "source": "git", "commit": change[0]}
    return {"at": "", "source": None}


_SECTIONS = {
    "pg_dumpall": re.compile(r"^\\connect\s+(?:-reuse-previous=\S+\s+)?\"?([^\s\"]+)\"?", re.MULTILINE),
    "mysqldump": re.compile(r"^USE `([^`]+)`;", re.MULTILINE),
    "mariadb-dump": re.compile(r"^USE `([^`]+)`;", re.MULTILINE),
    "ssms": re.compile(r"^USE \[([^\]]+)\]", re.MULTILINE),
}
"""Where the part of each database starts in a dump of several."""

_SKIPPED = {"template1", "template0"}
"""Databases a cluster dump connects to only to set them up."""


def sections(text: str, tool: str) -> list[dict]:
    """The databases of a dump holding several, each with its `first` and `last` line; empty for a dump
    of one database (a `USE` of the only one changes nothing)."""
    pattern = _SECTIONS.get(tool)
    if pattern is None:
        return []
    starts = [(match[1], text.count("\n", 0, match.start()) + 1) for match in pattern.finditer(text)]
    if tool == "pg_dumpall":  # each database's part starts at its CREATE DATABASE, a few lines before its \connect
        for index, (name, line) in enumerate(starts):
            create = list(re.finditer(rf"^CREATE DATABASE \"?{re.escape(name)}\"?\b", text, re.MULTILINE))
            if create:
                starts[index] = (name, text.count("\n", 0, create[-1].start()) + 1)
    total = text.count("\n") + 1
    found = [{"database": name, "first": line, "last": (starts[i + 1][1] - 1 if i + 1 < len(starts) else total)}
             for i, (name, line) in enumerate(starts)]
    found = [s for s in found if s["database"] not in _SKIPPED]
    return found if len({s["database"] for s in found}) > 1 else []


COPY_DATA = re.compile(r"^(COPY\s+(?P<table>[^\s(]+)\s*(?:\((?P<columns>[^)]*)\))?\s+FROM\s+stdin[^\n]*;[ \t]*\n)(?P<data>.*?)^\\\.[ \t]*$",
                       re.IGNORECASE | re.MULTILINE | re.DOTALL)
"""A `COPY … FROM stdin;` statement of a PostgreSQL dump and its rows, up to the `\\.` line ending them."""

_INSERT = re.compile(r"^\s*INSERT\s+(?:IGNORE\s+)?INTO\s+(?P<table>(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+)(?:\s*\.\s*(?:\"[^\"]+\"|`[^`]+`|\[[^\]]+\]|[\w$]+))?)"
                     r"\s*(?:\((?P<columns>[^)]*)\))?\s*(?:OVERRIDING\s+\w+\s+VALUE\s+)?VALUES\s*", re.IGNORECASE)
"""The head of an `INSERT … VALUES`: its table and the columns it names."""

_COPY_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "\\": "\\"}
"""What a backslash and the letter after it stand for in a `COPY` row (and in a MySQL string)."""


def _names(written: str) -> list[str]:
    """The parts of a name as written (`"sales"."orders"`, `` `acme`.`orders` ``, `[dbo].[t]`), unquoted."""
    return [part.strip().strip('"`[]') for part in re.findall(r'"[^"]+"|`[^`]+`|\[[^\]]+\]|[^.\s]+', written)]


def _copy_value(value: str) -> str | None:
    """A value of a `COPY` row: `\\N` is NULL, a backslash escape stands for its character."""
    if value == "\\N":
        return None
    return re.sub(r"\\(.)", lambda m: _COPY_ESCAPES.get(m[1], m[1]), value)


def _literal(written: str, backslash: bool) -> str | None:
    """A value of an `INSERT` as text: NULL, a string (its quotes and escapes undone; binary data as its
    size), or what is written (a number, `true`...)."""
    if written.upper() == "NULL":
        return None
    match = re.fullmatch(r"(?P<prefix>_\w+\s*|[NnEeXxBb])?'(?P<body>.*)'(?:::[\w\s\[\]\".]+)?", written, re.DOTALL)
    if match is None:
        return written
    body = match["body"].replace("''", "'")
    if backslash or (match["prefix"] or "").upper() == "E":
        body = re.sub(r"\\(.)", lambda m: _COPY_ESCAPES.get(m[1], "\0" if m[1] == "0" else m[1]), body)
    if (match["prefix"] or "").strip().lower() in ("_binary", "x", "b"):
        return f"<{len(body.encode('utf-8', errors='replace'))} bytes>"
    return body


def _tuples(text: str, start: int, backslash: bool) -> Iterator[list[str | None]]:
    """The rows of an `INSERT … VALUES (…), (…)` from `start`: each a list of its values (see `_literal`)."""
    i, n, depth, row, value_start = start, len(text), 0, [], start
    while i < n:
        char = text[i]
        if char == "'":
            i += 1
            while i < n:
                if backslash and text[i] == "\\":
                    i += 2
                    continue
                if text[i] == "'":
                    if i + 1 < n and text[i + 1] == "'":
                        i += 2
                        continue
                    break
                i += 1
        elif char == "(":
            depth += 1
            if depth == 1:
                row, value_start = [], i + 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                row.append(_literal(text[value_start:i].strip(), backslash))
                yield row
        elif char == "," and depth == 1:
            row.append(_literal(text[value_start:i].strip(), backslash))
            value_start = i + 1
        elif char == ";" and depth == 0:
            return
        i += 1


def rows(text: str, statements: list[tuple[int, str]], dialect: str, lines: list[int] | None = None) -> Iterator[tuple[list[str], list[str] | None, list[str | None]]]:
    """The rows a dump holds, one at a time, without running anything.

    Args:
        text: The dump's text (for its `COPY` blocks).
        statements: Its statements, as cut (`sql.split_statements`), for its `INSERT`s.
        dialect: Its SQL dialect (MySQL's strings take backslash escapes).
        lines: Only what lies between these lines (one database of a dump holding several).

    Yields:
        The table's name as written in parts (`["sales", "orders"]`), the columns the statement names
        (None when it names none: every column, in order) and the row's values as text (None for NULL).
    """
    first, last = lines or (1, None)
    for match in COPY_DATA.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        if line < first or (last is not None and line > last):
            continue
        columns = [name.strip().strip('"') for name in match["columns"].split(",")] if match["columns"] else None
        for row in match["data"].split("\n"):
            if row:
                yield _names(match["table"]), columns, [_copy_value(value) for value in row.split("\t")]
    for _line, statement in statements:
        head = _INSERT.match(statement)
        if head is None:
            continue
        columns = [name.strip().strip('"`[]') for name in head["columns"].split(",")] if head["columns"] else None
        for row in _tuples(statement, head.end(), dialect == "mysql"):
            yield _names(head["table"]), columns, row


def table_samples(found: Iterator[tuple[list[str], list[str] | None, list[str | None]]], table_of) -> dict[str, dict]:
    """What is kept of a dump's rows, by table: the same as of a live table (`samples.table_sample`, with `keys`).

    Each table's rows are sampled at random (the same rows every time the dump is read), its key
    columns' values all read; a table the dump holds no rows of says so.

    Args:
        found: The dump's rows (`rows`).
        table_of: The table a name names in the schema the dump builds (`schema`, `name` → its object,
            or None).

    Returns:
        By table (its object's `schema.name`): its sample, or `unavailable` and the reason.
    """
    chosen = random.Random(0)
    taken: dict[str, dict] = {}
    for parts, columns, values in found:
        table = table_of(parts[-2] if len(parts) > 1 else "", parts[-1])
        if table is None or table["kind"] != "table":
            continue
        held = taken.setdefault(f"{table['schema']}.{table['name']}", {"table": table, "names": columns or [c["name"] for c in table["columns"]],
                                                                       "rows": [], "seen": 0, "keys": {}})
        if len(values) != len(held["names"]):
            continue
        held["seen"] += 1
        if len(held["rows"]) < samples.SAMPLE_ROWS:
            held["rows"].append(values)
        elif (spot := chosen.randrange(held["seen"])) < samples.SAMPLE_ROWS:
            held["rows"][spot] = values
        for index, name in enumerate(held["names"]):
            if values[index] is not None and len(held["keys"].setdefault(name, set())) <= samples.KEY_VALUES:
                held["keys"][name].add(values[index])
    found_samples = {}
    for key, held in taken.items():
        table = held["table"]
        unique = {u[0] for u in table.get("unique") or [] if len(u) == 1}
        referring = {c for k in table.get("foreign_keys") or [] for c in k["columns"]}
        columns = [{"name": c["name"], "data": {"type": c.get("type", ""), "comment": c.get("comment", ""), "marks": [
            mark for mark, on in (("pk", c["name"] in table.get("primary_key", []) or c.get("pk")), ("fk", c["name"] in referring or c.get("references")),
                                  ("unique", c["name"] in unique or c.get("unique"))) if on]}} for c in table["columns"]]
        data = samples.table_sample(columns, held["names"], held["rows"])
        pk = list(table.get("primary_key") or []) or [c["name"] for c in table["columns"] if c.get("pk")]
        data["keys"] = {name: sorted(held["keys"].get(name, set()))[:samples.KEY_VALUES] for name in samples.key_columns(data, pk)}
        found_samples[key.lower()] = data
    return found_samples


__all__ = ["COPY_DATA", "TOOLS", "generated", "header", "recognise", "rows", "sections", "table_samples"]
