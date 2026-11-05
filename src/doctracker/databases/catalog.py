"""The current state of the project's live databases, kept in `doc/sqlite/databases.db`.

Only the last successful collection of each connection is kept (its objects, relations and what
was unavailable): it is what the search, the MCP tools and the wiki show. A collection that fails
keeps the state read before, with the failure noted beside it until a collection succeeds again.
No history is kept: the evolution of a database comes from its migrations and commits.

Each table's sample (`samples`) is kept apart from the readings: a reading replaces the objects every
minute, while a table is sampled only when new, changed or asked for again. The `contained in`
relations found through the samples (`samples.containment`) are kept apart too, and given with the
others, carrying their `ratio`.
"""

import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from doctracker.databases import samples as sampling

SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
  id INTEGER PRIMARY KEY AUTOINCREMENT, connection TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
  server TEXT NOT NULL, database TEXT NOT NULL, started TEXT NOT NULL, seconds REAL NOT NULL, ok INTEGER NOT NULL,
  error TEXT NOT NULL, version TEXT NOT NULL, databases TEXT NOT NULL, fingerprint TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS objects (
  collection INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE, path TEXT NOT NULL, kind TEXT NOT NULL,
  parent TEXT NOT NULL, name TEXT NOT NULL, data TEXT NOT NULL, PRIMARY KEY (collection, path));
CREATE TABLE IF NOT EXISTS relations (
  collection INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE, source TEXT NOT NULL,
  target TEXT NOT NULL, kind TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS relations_source ON relations (collection, source);
CREATE INDEX IF NOT EXISTS relations_target ON relations (collection, target);
CREATE TABLE IF NOT EXISTS origin_links (
  origin TEXT NOT NULL, database TEXT NOT NULL, linked INTEGER NOT NULL, PRIMARY KEY (origin, database));
CREATE TABLE IF NOT EXISTS unavailable (
  collection INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE, what TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS samples (
  connection TEXT NOT NULL, path TEXT NOT NULL, signature TEXT NOT NULL, read TEXT NOT NULL, data TEXT NOT NULL,
  PRIMARY KEY (connection, path));
CREATE TABLE IF NOT EXISTS data_relations (
  connection TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL, ratio REAL NOT NULL);
"""
"""Tables: `collections` (per connection, its last successful collection and a later failed one, with
the other `databases` on the server as JSON and a `fingerprint` of what was read), `objects` (what the collection read, `data` as JSON),
`relations` and `unavailable`; `origin_links`, the links between an origin (SQL files, migrations) and a
database chosen by hand (`linked` 1) or taken away by hand (0); `samples`, each table's sample (`data` as
JSON, see `samples.table_sample`) with the `signature` of the columns it was taken from; `data_relations`,
the `contained in` relations found through the samples, by the source's connection."""

SEARCHED_KINDS = ("table", "view", "materialized view", "foreign table", "column", "function", "procedure",
                  "aggregate", "trigger", "sequence", "enum", "domain", "synonym")
"""Kinds of object found by the searches."""

UNIVERSE_KINDS = {"database": "database", "schema": "schema", "table": "table", "foreign table": "table",
                  "view": "view", "materialized view": "view", "column": "column"}
"""What the Universe draws of each kind of object (the SQL tree), as the kind it is drawn as."""

UNIVERSE_RELATIONS = ("foreign key", "implied", "view reads", "foreign table", "contained in")
"""The relations the Universe draws."""

_CURRENT = "SELECT id FROM collections WHERE ok = 1"
"""The current collection of each connection: its last successful one, the only one kept."""

ORIGINS = "origin:"
"""What starts the connection of a collection made from a file (`databases.origins.as_collection`):
kept beside the live databases, read by `object`, `outline`, the search and a file's own Universe,
left out of what lists the live databases."""

_LIVE = f"{_CURRENT} AND connection NOT LIKE '{ORIGINS}%'"
"""The current collections of the live databases only."""

_RELATIONS = ("(SELECT collection, source, target, kind, NULL AS ratio FROM relations UNION ALL "
              "SELECT c.id, d.source, d.target, 'contained in', d.ratio FROM data_relations d "
              "JOIN collections c ON c.connection = d.connection AND c.ok = 1)")
"""Every relation, as a table: those read with each collection and those found through the samples."""

_TABULAR = ("table", "view", "materialized view", "foreign table")
"""The kinds of object that hold columns."""


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
            if "fingerprint" not in {row[1] for row in connection.execute("PRAGMA table_info(collections)")}:
                connection.execute("ALTER TABLE collections ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''")
            if write:
                with connection:
                    yield connection
            else:
                yield connection
        finally:
            connection.close()

    def save(self, connection_id: str, name: str, result: dict, tell: bool = True) -> dict:
        """Keep a collection in place of the one before; a failed one is noted beside the state read before.

        The wiki is told only when something read differs from the reading it replaces, so the
        readings made every minute do not reload its pages for nothing.

        Args:
            connection_id: The connection collected.
            name: The connection's name, as the user knows it.
            result: What `collect.collect` returned.
            tell: Tell the wiki when it changed; False when the caller tells it once for several.

        Returns:
            The connection's state (see `collection`), with `changed`: whether it differs from the one before.
        """
        fingerprint = hashlib.sha256(json.dumps(
            [result[key] for key in ("ok", "error", "databases", "objects", "relations", "unavailable")],
            sort_keys=True, default=str).encode("utf-8")).hexdigest()
        with self._connect(write=True) as connection:
            replaced = connection.execute("SELECT fingerprint FROM collections WHERE connection = ? AND ok = ?",
                                          (connection_id, int(result["ok"]))).fetchone()
            connection.execute(f"DELETE FROM collections WHERE connection = ?{'' if result['ok'] else ' AND ok = 0'}",
                               (connection_id,))
            cursor = connection.execute(
                "INSERT INTO collections (connection, name, kind, server, database, started, seconds, ok, error, version, databases, fingerprint) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (connection_id, name, result["kind"], result["server"], result["database"], result["started"],
                 result["seconds"], int(result["ok"]), result["error"], result["version"], json.dumps(result["databases"]),
                 fingerprint))
            collection = cursor.lastrowid
            connection.executemany("INSERT OR REPLACE INTO objects VALUES (?, ?, ?, ?, ?, ?)",
                                   [(collection, o["path"], o["kind"], o["parent"], o["name"], json.dumps(o["data"], default=str))
                                    for o in result["objects"]])
            connection.executemany("INSERT INTO relations VALUES (?, ?, ?, ?)",
                                   [(collection, r["source"], r["target"], r["kind"]) for r in result["relations"]])
            connection.executemany("INSERT INTO unavailable VALUES (?, ?, ?)",
                                   [(collection, u["what"], u["reason"]) for u in result["unavailable"]])
            sampled = self._keep_samples(connection, connection_id, result) if result["ok"] else False
        if sampled:
            self._contain()
        changed = replaced is None or replaced["fingerprint"] != fingerprint or sampled
        if changed and tell:
            self._on_change()
        return {**(self.collection(connection_id) or {}), "changed": changed}

    @staticmethod
    def _keep_samples(connection: sqlite3.Connection, connection_id: str, result: dict) -> bool:
        """Keep the samples a collection took (in place of those before), and drop those of tables gone.

        Returns:
            Whether any sample kept differs from before.
        """
        changed = False
        for taken in result.get("samples") or []:
            data = json.dumps(taken["data"], sort_keys=True, default=str)
            before = connection.execute("SELECT data FROM samples WHERE connection = ? AND path = ?",
                                        (connection_id, taken["path"])).fetchone()
            changed |= before is None or before["data"] != data
            connection.execute("INSERT OR REPLACE INTO samples VALUES (?, ?, ?, ?, ?)",
                               (connection_id, taken["path"], taken["signature"], result["started"], data))
        tables = {o["path"] for o in result["objects"] if o["kind"] in sampling.SAMPLED_KINDS}
        gone = [row["path"] for row in connection.execute("SELECT path FROM samples WHERE connection = ?", (connection_id,))
                if row["path"] not in tables]
        connection.executemany("DELETE FROM samples WHERE connection = ? AND path = ?", [(connection_id, path) for path in gone])
        return changed or bool(gone)

    def _contain(self) -> None:
        """Find again the `contained in` relations through every sample kept (`samples.containment`): the
        live databases with each other, what a file declares within that file."""
        with self._connect(write=True) as connection:
            tables = [{"path": row["path"], "connection": row["connection"], "data": json.loads(row["data"]),
                       "scope": row["connection"] if row["connection"].startswith(ORIGINS) else "live"}
                      for row in connection.execute("SELECT * FROM samples WHERE connection IN (SELECT connection FROM collections WHERE ok = 1)")]
            tables = [table for table in tables if "profiles" in table["data"]]
            owner = {table["path"]: table["connection"] for table in tables}
            connection.execute("DELETE FROM data_relations")
            connection.executemany("INSERT INTO data_relations VALUES (?, ?, ?, ?)",
                                   [(owner[found["table"]], found["source"], found["target"], found["ratio"])
                                    for found in sampling.containment(tables)])

    def signatures(self, connection_id: str, again: str = "") -> dict[str, str]:
        """The signature of each table's sample kept for a connection (see `samples.signature`): the tables
        a collection need not sample again.

        Args:
            connection_id: The connection.
            again: Leave out the tables whose path starts with this (to sample them again); empty for none.

        Returns:
            By table path, its sample's signature.
        """
        with self._connect() as connection:
            return {row["path"]: row["signature"] for row in connection.execute(
                "SELECT path, signature FROM samples WHERE connection = ?", (connection_id,))
                if not again or not row["path"].startswith(again)}

    def keep_origins(self, collections: list[dict]) -> None:
        """Keep what the project's files declare, as collections beside the live databases (connection
        `origin:<name>`), in place of the ones before; those of files gone are dropped. The wiki is told
        once, when any changed.

        Args:
            collections: What `databases.origins.as_collection` gives of each origin.
        """
        changed = False
        for collection in collections:
            changed |= self.save(f"{ORIGINS}{collection['database']}", collection["database"], collection, tell=False)["changed"]
        kept = [f"{ORIGINS}{c['database']}" for c in collections]
        others = f" AND connection NOT IN ({', '.join('?' * len(kept))})" if kept else ""
        with self._connect(write=True) as connection:
            changed |= connection.execute(f"DELETE FROM collections WHERE connection LIKE '{ORIGINS}%'" + others, kept).rowcount > 0
            gone = connection.execute(f"DELETE FROM samples WHERE connection LIKE '{ORIGINS}%'" + others, kept).rowcount > 0
        if gone:
            self._contain()
        if changed or gone:
            self._on_change()

    def forget(self, connection_id: str) -> None:
        """Drop what was read from a connection (blocked, changed or deleted).

        Args:
            connection_id: The connection.
        """
        with self._connect(write=True) as connection:
            removed = connection.execute("DELETE FROM collections WHERE connection = ?", (connection_id,)).rowcount
            sampled = connection.execute("DELETE FROM samples WHERE connection = ?", (connection_id,)).rowcount
        if sampled:
            self._contain()
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
                                   f"SELECT kind, count(*) FROM {_RELATIONS} WHERE collection = ? GROUP BY kind", (row["id"],))}},
                    "unavailable": [dict(u) for u in connection.execute(
                        "SELECT what, reason FROM unavailable WHERE collection = ?", (row["id"],))]})
        return found

    def kinds(self) -> dict[str, str]:
        """The kind of database each current collection was read from, by connection: a live one's
        (`postgresql`, `mysql`, `mssql`, `sqlite`...), a file's its dialect (`postgres`, `tsql`...)."""
        with self._connect() as connection:
            return {row["connection"]: row["kind"] for row in connection.execute(f"SELECT connection, kind FROM collections WHERE id IN ({_CURRENT})")}

    def last_try(self, connection_id: str) -> str:
        """When a connection was last read, successfully or not (ISO 8601, UTC); empty when never."""
        with self._connect() as connection:
            row = connection.execute("SELECT max(started) FROM collections WHERE connection = ?", (connection_id,)).fetchone()
        return row[0] or ""

    def objects(self, connection_id: str = "", kind: str = "", schema: str = "", within: str = "", name: str = "",
                origins: bool = False) -> list[dict]:
        """The objects of the databases as last read, every connection's or one's.

        Args:
            connection_id: Only this connection's (a file's: `origin:<name>`); empty for every live database's.
            kind: Only this kind (`table`, `view`, `column`, `function`...); empty for all.
            schema: Only the objects inside a schema of this name; empty for all.
            within: Only what is inside this server, database or schema (its path, e.g.
                `db:127.0.0.1:5432/shop`); empty for all.
            name: Only the objects whose name holds this text (any case); empty for all.
            origins: Also what the project's files declare (see `keep_origins`).

        Returns:
            Each object's `path`, `kind`, `parent`, `name`, `connection` and `data`, by path.
        """
        query = (f"SELECT o.*, c.connection FROM objects o JOIN collections c ON c.id = o.collection "
                 f"WHERE o.collection IN ({_CURRENT if origins or connection_id else _LIVE})")
        values: list = []
        for column, value in (("c.connection", connection_id), ("o.kind", kind)):
            if value:
                query += f" AND {column} = ?"
                values.append(value)
        if schema:
            query += " AND (o.parent LIKE ? OR o.parent LIKE ?)"
            values += [f"%/{schema}", f"%/{schema}.%"]
        if within:  # a server or a database holds paths under `/`, a schema under `.`
            query += " AND o.path LIKE ? ESCAPE '\\'"
            values.append(_like(within) + ("/%" if within.count("/") < 2 else ".%"))
        if name:
            query += " AND o.name LIKE ? ESCAPE '\\'"
            values.append(f"%{_like(name)}%")
        with self._connect() as connection:
            return [_object(row) for row in connection.execute(query + " ORDER BY o.path", values)]

    def relations(self, kinds: tuple[str, ...] = ()) -> list[dict]:
        """The relations of the databases as last read and of what the files declare.

        Args:
            kinds: Only these kinds (`foreign key`, `implied`, `view reads`…); empty for all.

        Returns:
            Each relation's `source`, `target` and `kind`, once; one found through the samples (`contained
            in`) also with its `ratio`.
        """
        query = f"SELECT DISTINCT source, target, kind, ratio FROM {_RELATIONS} WHERE collection IN ({_CURRENT})"
        if kinds:
            query += f" AND kind IN ({', '.join('?' * len(kinds))})"
        with self._connect() as connection:
            return [_relation(row) for row in connection.execute(query, list(kinds))]

    def outline(self) -> dict[str, list[tuple[str, str, str, str]]]:
        """What the tree shows of the databases read and of what the files declare, by connection (a
        file's: `origin:<name>`): every object but the columns, as `(path, kind, parent, name)`, in path order."""
        query = (f"SELECT o.path, o.kind, o.parent, o.name, c.connection FROM objects o JOIN collections c ON c.id = o.collection "
                 f"WHERE o.collection IN ({_CURRENT}) AND o.kind != 'column' ORDER BY o.path")
        found: dict[str, list[tuple[str, str, str, str]]] = {}
        with self._connect() as connection:
            for row in connection.execute(query):
                found.setdefault(row["connection"], []).append((row["path"], row["kind"], row["parent"], row["name"]))
        return found

    def object(self, path: str) -> dict | None:
        """One object of the databases as last read, with what it holds and its relations.

        Args:
            path: The object's path (`db:<server>/<database>/<schema>.<name>`; what a file declares:
                `origin:<name>::<schema>.<name>`).

        Returns:
            The object (see `objects`) with `children` (`path`, `kind`, `name`, `data` of what it holds),
            `relations` (`source`, `target`, `kind`, both ways; a table's or view's include its columns'
            and triggers'; `ratio` for one found through the samples), `ends` (`kind`, `name`, `parent` of
            every object those relations reach, by path), `read` (when its database was read; empty for a
            file's), `declared` (a file's: where it was created and last changed), `unavailable` (what
            could not be read of its database, and why); a table's or view's `sample` (`read`, `rows`,
            `columns`, `shown`, `profiles`, see `samples.table_sample`), a column's `profile` (`read`,
            `rows` and its profile), each `unavailable` with the reason when there is none; None when no
            database read holds it.
        """
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT o.*, c.connection, c.started FROM objects o JOIN collections c ON c.id = o.collection "
                f"WHERE o.path = ? AND o.collection IN ({_CURRENT}) ORDER BY o.collection DESC", (path,)).fetchone()
            if row is None:
                return None
            found = _object(row)
            found["read"] = row["started"]
            found["declared"] = found["data"].pop("declared", None)
            found["children"] = [{"path": r["path"], "kind": r["kind"], "name": r["name"], "data": json.loads(r["data"])}
                                 for r in connection.execute("SELECT * FROM objects WHERE collection = ? AND parent = ? ORDER BY rowid",
                                                             (row["collection"], path))]
            inside = row["kind"] in ("table", "view", "materialized view", "foreign table")
            found["relations"] = [_relation(r) for r in connection.execute(
                f"SELECT DISTINCT source, target, kind, ratio FROM {_RELATIONS} WHERE collection IN ({_CURRENT}) AND (source = ? OR target = ?"
                + (" OR source LIKE ? ESCAPE '\\' OR target LIKE ? ESCAPE '\\' OR source LIKE ? ESCAPE '\\'" if inside else "") + ")",
                (path, path, *((f"{_like(path)}.%", f"{_like(path)}.%", f"{_like(path)}:%") if inside else ())))]
            ends = {end for r in found["relations"] for end in (r["source"], r["target"])}
            found["ends"] = {r["path"]: {"kind": r["kind"], "name": r["name"], "parent": r["parent"]} for r in connection.execute(
                f"SELECT path, kind, name, parent FROM objects WHERE collection IN ({_CURRENT}) "
                f"AND path IN ({', '.join('?' * len(ends))})", list(ends))} if ends else {}
            found["unavailable"] = [dict(u) for u in connection.execute(
                "SELECT what, reason FROM unavailable WHERE collection = ?", (row["collection"],))]
            if inside or found["kind"] == "column":
                table = connection.execute("SELECT kind FROM objects WHERE collection = ? AND path = ?",
                                           (row["collection"], path if inside else found["parent"])).fetchone()
                held = connection.execute("SELECT read, data FROM samples WHERE connection = ? AND path = ?",
                                          (found["connection"], path if inside else found["parent"])).fetchone()
                sample = _sample(held, found["connection"], table["kind"] if table else "")
                if inside:
                    found["sample"] = sample
                else:
                    found["profile"] = ({"unavailable": sample["unavailable"]} if "unavailable" in sample else
                                        {"read": sample["read"], "rows": sample["rows"], **(sample["profiles"].get(found["name"])
                                         or {"unavailable": "The sample read no values of it."})})
        return found

    def level(self, at: str = "") -> dict:
        """One level of the SQL tree, as the Navigate Database tab browses it: what `at` holds, one row each.

        Args:
            at: Empty for the servers; a server's path for its databases, a database's for its schemas,
                a schema's for its tables and views, a table's or view's for its columns.

        Returns:
            `at`, `level` (`servers`, `databases`, `schemas`, `tables`, `columns`) and `rows`: each one's
            `path`, `name` and what that level shows of it — servers: `databases`, `read`; databases:
            `schemas`, `tables`, `views`, `comment`; schemas: `tables`, `views`, `functions`, `comment`;
            tables and views: `kind`, `columns`, `rows`, `size`, `comment`; columns: `type`, `null`,
            `default`, `marks` (with `sensitive` when its sample says so), `nulls` (% of the sampled rows),
            `distinct` (in the sample), `comment`. Rows that hold a next level have `down` true.
        """
        tables, views = ("table", "foreign table"), ("view", "materialized view")
        if not at:
            with self._connect() as connection:
                read = {f"db:{server}": started for server, started in connection.execute(
                    "SELECT server, max(started) FROM collections WHERE ok = 1 GROUP BY server")}
            servers: dict[str, int] = {}
            for database in self.objects(kind="database"):
                servers[database["parent"]] = servers.get(database["parent"], 0) + 1
            rows = [{"path": path, "name": path.removeprefix("db:"), "databases": count, "read": read.get(path, ""), "down": True}
                    for path, count in sorted(servers.items())]
            return {"at": at, "level": "servers", "rows": rows}
        inside = self.objects(within=at) if at.count("/") < 2 or "." not in at.split("/")[-1] else []
        found = self.object(at) if at.count("/") >= 2 else None
        if at.count("/") == 0:  # a server: its databases
            level, holders = "databases", [o for o in self.objects(kind="database") if o["parent"] == at]
        elif at.count("/") == 1:
            level, holders = "schemas", [o for o in inside if o["kind"] == "schema"]
        elif found and found["kind"] == "schema":
            level, holders = "tables", [o for o in inside if o["parent"] == at and o["kind"] in tables + views]
        elif found and found["kind"] in tables + views:
            columns = [c for c in found["children"] if c["kind"] == "column"]
            sample = found["sample"]
            profiles, sampled = sample.get("profiles") or {}, sample.get("rows") or 0
            return {"at": at, "level": "columns", "rows": [
                {"path": c["path"], "name": c["name"], "type": c["data"].get("type", ""),
                 "null": "yes" if c["data"].get("nullable", True) else "no", "default": c["data"].get("default") or c["data"].get("computed") or "",
                 "marks": [m for m in c["data"].get("marks", []) if m != "null"] + (["sensitive"] if (profiles.get(c["name"]) or {}).get("sensitive") else []),
                 "nulls": round(100 * profiles[c["name"]]["nulls"] / sampled, 1) if c["name"] in profiles and sampled else None,
                 "distinct": profiles[c["name"]]["distinct"] if c["name"] in profiles else None,
                 "comment": c["data"].get("comment", ""), "down": False}
                for c in columns]}
        else:
            return {"at": at, "level": "", "rows": []}
        if level == "databases":
            inside = self.objects(within=at)
        counts: dict[str, dict[str, int]] = {}
        for item in inside:  # how many of each kind each row holds, anywhere below it
            for holder in holders:
                if item["path"].startswith(holder["path"] + ("/" if level == "databases" else ".")):
                    counted = counts.setdefault(holder["path"], {})
                    counted[item["kind"]] = counted.get(item["kind"], 0) + 1
        rows = []
        for holder in holders:
            n, data = counts.get(holder["path"], {}), holder["data"]
            row = {"path": holder["path"], "name": holder["name"], "comment": data.get("comment", ""), "down": True}
            if level == "databases":
                row.update(schemas=n.get("schema", 0), tables=sum(n.get(k, 0) for k in tables), views=sum(n.get(k, 0) for k in views))
            elif level == "schemas":
                row.update(tables=sum(n.get(k, 0) for k in tables), views=sum(n.get(k, 0) for k in views),
                           functions=n.get("function", 0) + n.get("procedure", 0) + n.get("aggregate", 0))
            else:
                row.update(kind=holder["kind"], columns=n.get("column", 0), rows=data.get("rows"), size=data.get("bytes"))
            rows.append(row)
        return {"at": at, "level": level, "rows": rows}

    def origin_choices(self) -> dict[tuple[str, str], bool]:
        """The links between origins and databases chosen by hand: True linked, False taken away."""
        with self._connect() as connection:
            return {(origin, database): bool(linked) for origin, database, linked in connection.execute(
                "SELECT origin, database, linked FROM origin_links")}

    def choose_origin_link(self, origin: str, database: str, linked: bool | None) -> None:
        """Link an origin to a database by hand (True), take a link away (False), or leave it to the
        other layers again (None).

        Args:
            origin: The origin's name (its folder or file).
            database: The database's path (`db:<server>/<database>`).
            linked: The choice.
        """
        with self._connect(write=True) as connection:
            if linked is None:
                connection.execute("DELETE FROM origin_links WHERE origin = ? AND database = ?", (origin, database))
            else:
                connection.execute("INSERT OR REPLACE INTO origin_links VALUES (?, ?, ?)", (origin, database, int(linked)))
        self._on_change()

    def searchable(self) -> dict[str, dict]:
        """The objects of the databases as last read, as search documents.

        Returns:
            By path: `kind`, `title` (the name), `summary` (its comment, else its kind and type) and
            `text` (kind, path, type and comment), the words the search compares.
        """
        documents = {}
        for found in self.objects(origins=True):  # what the files declare, found as the live objects are
            if found["kind"] in SEARCHED_KINDS:
                data = found["data"]
                described = " ".join(str(part) for part in (found["kind"], data.get("type", "")) if part)
                documents[found["path"]] = {"kind": found["kind"], "title": found["name"],
                                            "summary": str(data.get("comment") or described), "text": " ".join(
                    str(part) for part in (found["kind"], found["path"], data.get("type", ""), data.get("comment", "")) if part)}
        return documents

    def universe(self, origin: str = "") -> dict:
        """The databases as last read, as the Universe draws them: the SQL tree and the relations.

        Args:
            origin: Draw what this file declares instead (its collection's connection, `origin:<name>`).

        Returns:
            `nodes`: `id` (the path; a server is `db:<host:port>`), `label`, `kind` (`server`, `database`,
            `schema`, `table` for tables and foreign tables, `view` for views and materialized views,
            `column`), `parent`, and for columns `type`, `flags` (pk, fk, unique, index, null, generated)
            and `comment`. `edges`: `source`, `target`, `kind` (foreign key, implied, view reads, foreign
            table, contained in, this one with its `ratio`), both ends drawn.
        """
        nodes: dict[str, dict] = {}
        for found in self.objects(connection_id=origin):
            kind = UNIVERSE_KINDS.get(found["kind"])
            if kind is None:
                continue
            node = {"id": found["path"], "label": found["name"], "kind": kind, "parent": found["parent"] or None}
            if kind == "database" and found["parent"]:
                server = found["parent"]
                nodes.setdefault(server, {"id": server, "label": server.removeprefix("db:"), "kind": "server", "parent": None})
            if kind == "column":
                node.update(type=found["data"].get("type", ""), flags=found["data"].get("marks", []))
            if found["data"].get("comment"):
                node["comment"] = found["data"]["comment"]
            if found["kind"] != kind:
                node["subkind"] = found["kind"]
            nodes.setdefault(found["path"], node)
        with self._connect() as connection:
            rows = connection.execute(f"SELECT DISTINCT source, target, kind, ratio FROM {_RELATIONS} WHERE collection IN "
                                      f"({_CURRENT + ' AND connection = ?' if origin else _LIVE}) "
                                      f"AND kind IN ({', '.join('?' * len(UNIVERSE_RELATIONS))})",
                                      ([origin] if origin else []) + list(UNIVERSE_RELATIONS)).fetchall()
        # A foreign table names its server as that server reaches it (a name inside its network, say),
        # not as doctracker does: without that exact path, the one table with its database and name.
        by_place: dict[str, list[str]] = {}
        for path in nodes:
            by_place.setdefault(path.split("/", 1)[-1], []).append(path)
        edges = []
        for source, target, kind, ratio in rows:
            if kind == "foreign table" and target not in nodes and len(by_place.get(target.split("/", 1)[-1], [])) == 1:
                target = by_place[target.split("/", 1)[-1]][0]
            if source in nodes and target in nodes:
                edges.append({"source": source, "target": target, "kind": kind, **({"ratio": ratio} if ratio is not None else {})})
        return {"nodes": list(nodes.values()), "edges": edges}


def _like(text: str) -> str:
    """Text for a LIKE pattern, its own `%`, `_` and `\\` taken literally (with ESCAPE '\\')."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _relation(row: sqlite3.Row) -> dict:
    """A relation row as the store gives it: `ratio` only for one found through the samples."""
    found = {"source": row["source"], "target": row["target"], "kind": row["kind"]}
    if row["ratio"] is not None:
        found["ratio"] = row["ratio"]
    return found


_HIDDEN = ("probe", "family", "marks")
"""What a column's profile keeps only to find containment: not shown."""


def _sample(held: sqlite3.Row | None, connection_id: str, kind: str) -> dict:
    """A table's sample as shown (`read`, `rows`, `columns`, `shown`, `profiles`), or `unavailable` and why."""
    if held is None:
        if connection_id.startswith(ORIGINS):
            return {"unavailable": "A file declares no rows: only the rows a dump holds are read."}
        if kind == "foreign table":
            return {"unavailable": "A foreign table is not sampled: reading it reads another database."}
        if kind not in sampling.SAMPLED_KINDS:
            return {"unavailable": "A view is not sampled: reading it runs its query."}
        return {"unavailable": "Not sampled yet: it is sampled at the next reading of its database."}
    data = json.loads(held["data"])
    if "unavailable" in data:
        return {"unavailable": data["unavailable"]}
    return {"read": held["read"], "rows": data["rows"], "columns": data["columns"], "shown": data["shown"],
            "profiles": {name: {k: v for k, v in found.items() if k not in _HIDDEN} for name, found in data["profiles"].items()}}


def _object(row: sqlite3.Row) -> dict:
    """An object row as the store gives it."""
    return {"path": row["path"], "kind": row["kind"], "parent": row["parent"], "name": row["name"],
            "connection": row["connection"], "data": json.loads(row["data"])}
