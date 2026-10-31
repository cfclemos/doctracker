"""The current state of the project's live databases, kept in `doc/sqlite/databases.db`.

Only the last successful collection of each connection is kept (its objects, relations and what
was unavailable): it is what the search, the MCP tools and the wiki show. A collection that fails
keeps the state read before, with the failure noted beside it until a collection succeeds again.
No history is kept: the evolution of a database comes from its migrations and commits.
"""

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
  id INTEGER PRIMARY KEY AUTOINCREMENT, connection TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
  server TEXT NOT NULL, database TEXT NOT NULL, started TEXT NOT NULL, seconds REAL NOT NULL, ok INTEGER NOT NULL,
  error TEXT NOT NULL, version TEXT NOT NULL, databases TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS objects (
  collection INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE, path TEXT NOT NULL, kind TEXT NOT NULL,
  parent TEXT NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (collection, path));
CREATE TABLE IF NOT EXISTS relations (
  collection INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE, source TEXT NOT NULL,
  target TEXT NOT NULL, kind TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS relations_source ON relations (collection, source);
CREATE INDEX IF NOT EXISTS relations_target ON relations (collection, target);
CREATE TABLE IF NOT EXISTS unavailable (
  collection INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE, what TEXT NOT NULL, reason TEXT NOT NULL);
"""
"""Tables: `collections` (per connection, its last successful collection and a later failed one, with
the other `databases` on the server as JSON), `objects` (what the collection read, `data` as JSON),
`relations` and `unavailable`."""

SEARCHED_KINDS = ("table", "view", "materialized view", "foreign table", "column", "function", "procedure",
                  "aggregate", "trigger", "sequence", "enum", "domain", "synonym")
"""Kinds of object found by the searches."""

_CURRENT = "SELECT id FROM collections WHERE ok = 1"
"""The current collection of each connection: its last successful one, the only one kept."""


class CatalogStore:
    """The current state of the project's live databases.

    Args:
        path: Database file; its folder is created when the database is first opened.
        on_change: Called after a collection is saved (the wiki reloads).

    Attributes:
        path: Database file.
    """

    def __init__(self, path: Path, on_change: Callable[[], None]) -> None:
        self.path = path
        self._on_change = on_change

    @contextmanager
    def _connect(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        """Open the database for one operation; a write runs in one transaction."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            if write:
                with connection:
                    yield connection
            else:
                yield connection
        finally:
            connection.close()

    def save(self, connection_id: str, name: str, result: dict) -> dict:
        """Keep a collection in place of the one before; a failed one is noted beside the state read before.

        Args:
            connection_id: The connection collected.
            name: The connection's name, as the user knows it.
            result: What `collect.collect` returned.

        Returns:
            The connection's state (see `collection`).
        """
        with self._connect(write=True) as connection:
            connection.execute(f"DELETE FROM collections WHERE connection = ?{'' if result['ok'] else ' AND ok = 0'}",
                               (connection_id,))
            cursor = connection.execute(
                "INSERT INTO collections (connection, name, kind, server, database, started, seconds, ok, error, version, databases) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (connection_id, name, result["kind"], result["server"], result["database"], result["started"],
                 result["seconds"], int(result["ok"]), result["error"], result["version"], json.dumps(result["databases"])))
            collection = cursor.lastrowid
            connection.executemany("INSERT OR REPLACE INTO objects VALUES (?, ?, ?, ?, ?, ?)",
                                   [(collection, o["path"], o["kind"], o["parent"], o["name"], json.dumps(o["data"], default=str))
                                    for o in result["objects"]])
            connection.executemany("INSERT INTO relations VALUES (?, ?, ?, ?)",
                                   [(collection, r["source"], r["target"], r["kind"]) for r in result["relations"]])
            connection.executemany("INSERT INTO unavailable VALUES (?, ?, ?)",
                                   [(collection, u["what"], u["reason"]) for u in result["unavailable"]])
        self._on_change()
        return self.collection(connection_id)

    def forget(self, connection_id: str) -> None:
        """Drop what was read from a connection (blocked, changed or deleted).

        Args:
            connection_id: The connection.
        """
        with self._connect(write=True) as connection:
            removed = connection.execute("DELETE FROM collections WHERE connection = ?", (connection_id,)).rowcount
        if removed:
            self._on_change()

    def collection(self, connection_id: str) -> dict | None:
        """The state of a connection's database, as last read.

        Args:
            connection_id: The connection.

        Returns:
            None when it was never read. Otherwise `started` (when it was read), `seconds`, `version`,
            `server`, `database`, `databases` (the other databases on the server), `counts` (objects and
            relations by kind), `unavailable` (what, reason), and `failure` (`started`, `error`) when the
            last try to read it again failed; without a successful reading, only `failure`.
        """
        with self._connect() as connection:
            rows = {bool(row["ok"]): row for row in connection.execute(
                "SELECT * FROM collections WHERE connection = ?", (connection_id,))}
            if not rows:
                return None
            failed = rows.get(False)
            found: dict = {"failure": {"started": failed["started"], "error": failed["error"]} if failed else None}
            row = rows.get(True)
            if row is not None:
                found.update({
                    "started": row["started"], "seconds": row["seconds"], "version": row["version"], "server": row["server"],
                    "database": row["database"], "databases": json.loads(row["databases"]),
                    "counts": {"objects": {kind: n for kind, n in connection.execute(
                                   "SELECT kind, count(*) FROM objects WHERE collection = ? GROUP BY kind", (row["id"],))},
                               "relations": {kind: n for kind, n in connection.execute(
                                   "SELECT kind, count(*) FROM relations WHERE collection = ? GROUP BY kind", (row["id"],))}},
                    "unavailable": [dict(u) for u in connection.execute(
                        "SELECT what, reason FROM unavailable WHERE collection = ?", (row["id"],))]})
        return found

    def last_try(self, connection_id: str) -> str:
        """When a connection was last read, successfully or not (ISO 8601, UTC); empty when never."""
        with self._connect() as connection:
            row = connection.execute("SELECT max(started) FROM collections WHERE connection = ?", (connection_id,)).fetchone()
        return row[0] or ""

    def objects(self, connection_id: str = "", kind: str = "", schema: str = "") -> list[dict]:
        """The objects of the databases as last read, every connection's or one's.

        Args:
            connection_id: Only this connection's; empty for all.
            kind: Only this kind (`table`, `view`, `column`, `function`...); empty for all.
            schema: Only the objects inside this schema; empty for all.

        Returns:
            Each object's `path`, `kind`, `parent`, `name`, `connection` and `data`, by path.
        """
        query = (f"SELECT o.*, c.connection FROM objects o JOIN collections c ON c.id = o.collection "
                 f"WHERE o.collection IN ({_CURRENT})")
        values: list = []
        for column, value in (("c.connection", connection_id), ("o.kind", kind)):
            if value:
                query += f" AND {column} = ?"
                values.append(value)
        if schema:
            query += " AND (o.parent LIKE ? OR o.parent LIKE ?)"
            values += [f"%/{schema}", f"%/{schema}.%"]
        with self._connect() as connection:
            return [_object(row) for row in connection.execute(query + " ORDER BY o.path", values)]

    def object(self, path: str) -> dict | None:
        """One object of the databases as last read, with its relations.

        Args:
            path: The object's path (`db:<server>/<database>/<schema>.<name>`).

        Returns:
            The object (see `objects`) with `children` (paths and kinds of what it holds) and `relations`
            (`source`, `target`, `kind`, both ways); None when no database read holds it.
        """
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT o.*, c.connection FROM objects o JOIN collections c ON c.id = o.collection "
                f"WHERE o.path = ? AND o.collection IN ({_CURRENT}) ORDER BY o.collection DESC", (path,)).fetchone()
            if row is None:
                return None
            found = _object(row)
            found["children"] = [{"path": p, "kind": k} for p, k in connection.execute(
                "SELECT path, kind FROM objects WHERE collection = ? AND parent = ? ORDER BY path", (row["collection"], path))]
            found["relations"] = [dict(r) for r in connection.execute(
                "SELECT source, target, kind FROM relations WHERE collection = ? AND (source = ? OR target = ?)",
                (row["collection"], path, path))]
        return found

    def searchable(self) -> dict[str, dict]:
        """The objects of the databases as last read, as search documents.

        Returns:
            By path: `kind`, `title` (the name), `summary` (its comment, else its kind and type) and
            `text` (kind, path, type and comment), the words the search compares.
        """
        documents = {}
        for found in self.objects():
            if found["kind"] in SEARCHED_KINDS:
                data = found["data"]
                described = " ".join(str(part) for part in (found["kind"], data.get("type", "")) if part)
                documents[found["path"]] = {"kind": found["kind"], "title": found["name"],
                                            "summary": str(data.get("comment") or described), "text": " ".join(
                    str(part) for part in (found["kind"], found["path"], data.get("type", ""), data.get("comment", "")) if part)}
        return documents


def _object(row: sqlite3.Row) -> dict:
    """An object row as the store gives it."""
    return {"path": row["path"], "kind": row["kind"], "parent": row["parent"], "name": row["name"],
            "connection": row["connection"], "data": json.loads(row["data"])}
