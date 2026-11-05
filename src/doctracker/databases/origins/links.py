"""Which live databases each origin describes, in layers, each link saying how it was made."""

import re
import zlib
from pathlib import Path

_CONNECTION_DIALECTS = {"postgresql": "postgres", "mysql": "mysql", "mssql": "tsql", "sqlite": "sqlite", "oracle": "oracle"}
"""The SQL dialect of each kind of connection: an origin meets only the databases of its own dialect."""

HISTORY_TOOLS = {"flyway": "flyway_schema_history", "golang-migrate": "schema_migrations", "dbmate": "schema_migrations",
                 "alembic": "alembic_version", "django migrations": "django_migrations", "prisma migrations": "_prisma_migrations"}
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
    if origin["kind"] == "alembic" and rows and "version_num" in rows[0]:
        heads = {row["version_num"] for row in rows} & set(versions)
        if not heads:
            return None
        revises = {step["version"]: step.get("revises") or [] for step in origin["steps"]}
        done, waiting = set(), list(heads)
        while waiting:  # a head and every revision before it
            revision = waiting.pop()
            if revision in revises and revision not in done:
                done.add(revision)
                waiting += revises[revision]
        return {"tool": "alembic", "applied": len(done), "steps": len(versions), "version": ", ".join(sorted(heads)),
                "pending": [Path(s["file"]).name for s in origin["steps"] if s["version"] not in done], "changed": [], "failed": []}
    if origin["kind"] == "django migrations" and rows and "app" in rows[0]:
        names = {Path(s["file"]).stem: s for s in origin["steps"]}
        done = {row["name"] for row in rows if row.get("app") == origin.get("app")} & set(names)
        if not done:
            return None
        return {"tool": "django", "applied": len(done), "steps": len(names), "version": max(done),
                "pending": [Path(s["file"]).name for s in origin["steps"] if Path(s["file"]).stem not in done], "changed": [], "failed": []}
    if origin["kind"] == "prisma migrations" and rows and "migration_name" in rows[0]:
        done = {row["migration_name"] for row in rows if row.get("finished_at") and not row.get("rolled_back_at")} & set(versions)
        if not done:
            return None
        return {"tool": "prisma", "applied": len(done), "steps": len(versions), "version": max(done),
                "pending": [s["version"] for s in origin["steps"] if s["version"] not in done], "changed": [],
                "failed": [row["migration_name"] for row in rows if not row.get("finished_at") and not row.get("rolled_back_at")]}
    if origin["kind"] == "dbmate" and rows and "dirty" not in rows[0]:
        done = {row.get("version") for row in rows} & set(versions)
        if not done:
            return None
        return {"tool": "dbmate", "applied": len(done), "steps": len(versions), "version": max(done),
                "pending": [Path(s["file"]).name for s in origin["steps"] if s["version"] not in done], "changed": [], "failed": []}
    return None


_DESCRIBED: dict = {}
"""The last answer of `describe_origins`, with what it was made from: asked again by every page that shows
"Declared by" or "Found in", it is made again only when the origins read, the databases read (the store's
file) or the connections changed."""


def describe_origins(origins: list[dict], catalog, connections: list[dict], root: Path) -> dict[str, dict]:
    """Which databases each origin describes, in layers, each link saying how it was made.

    1. Chosen by hand (the origin's page): always wins, also to take a link away.
    2. The tool's history table in a database read: the proof it migrated it (and how far).
    3. The origin's own configuration (Flyway's file), or a connection declared in the origin's folder.
    4. An ORM's models: the databases its migrations are linked to by history or declaration (`related`).
    5. The names of its tables: only a suggestion, to confirm by hand, ranked by the whole comparison
       (the tables the same in everything first).

    Args:
        origins: The origins read (`extract_origins`).
        catalog: The databases read (`CatalogStore`).
        connections: The project's connections (`ConnectionStore.connections`).
        root: The project's root.

    Returns:
        By origin name: `links` (`database`, `how`: list of `chosen`, `history`, `declared`, `related`;
        `history` what its history table says; `declared` the file or connection naming it, or the
        related origin; a dump's, the line naming its database), `unlinked` (taken away by hand),
        `suggestions` (`database`, `matched`, `total`, `same`: the tables with no difference at all),
        `warning` when the layers disagree and `related` (the other origin of the same ORM, or empty).
    """
    from doctracker.databases.origins.compare import compare_origin  # compare reads the links: imported here

    try:
        stored = catalog.path.stat().st_mtime_ns
    except OSError:
        stored = 0
    key = (id(origins), len(origins), stored, tuple(sorted((c.get("id"), c.get("kind"), c.get("folder")) for c in connections)))
    if _DESCRIBED.get("key") == key:
        return _DESCRIBED["value"]
    _DESCRIBED["value"] = found = _describe(origins, catalog, connections, root, compare_origin)
    _DESCRIBED["key"] = key
    return found


def _describe(origins: list[dict], catalog, connections: list[dict], root: Path, compare_origin) -> dict[str, dict]:
    """What `describe_origins` gives, made from the origins and databases read."""
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
    kinds = {c["id"]: _CONNECTION_DIALECTS.get(c.get("kind", ""), "") for c in connections}
    dialect_of = {database["path"]: kinds.get(database["connection"], "") for database in databases}
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
        written = origin.get("dump") or {}
        if "database" in written:  # the database a dump says it came from (and its host, when written)
            host = (written.get("host") or {}).get("value", "")
            for database in databases:
                server, _, database_name = database["path"].removeprefix("db:").partition("/")
                if database_name == written["database"]["value"] and (not host or _same_host(server.rpartition(":")[0]) == _same_host(host)) \
                        and dialect_of.get(database["path"]) in ("", origin["dialect"]):  # a MySQL dump is no PostgreSQL database's
                    link(database["path"], "declared", declared=f"{origin.get('part_of') or origin['name']}:{written['database']['line']}")
        for file, host, port, name in _declared_urls(root, origin):
            for database in databases:
                server, _, database_name = database["path"].removeprefix("db:").partition("/")
                server_host, _, server_port = server.rpartition(":")
                if database_name == name and _same_host(server_host) == _same_host(host) and (not port or port == server_port):
                    link(database["path"], "declared", declared=file)
        for connection in connections:  # declared in the origin's folder (an ORM's: also in the folder holding it)
            if connection.get("folder") and connection["folder"] in (origin["folder"], str(Path(origin["folder"]).parent.as_posix())):
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
                if database in links or database in unlinked or dialect_of.get(database, "") not in ("", origin["dialect"]):
                    continue
                matched = sum(1 for key in own if key in held or key.split(".", 1)[-1] in held)
                if matched / len(own) >= 0.5:
                    suggestions.append({"database": database, "matched": matched, "total": len(own)})
        for suggestion in suggestions:  # ranked by the whole comparison: tables the same in everything first
            compared = compare_origin(origin, catalog, suggestion["database"])
            suggestion["same"] = sum(1 for table in compared["tables"].values() if not table["differences"])
        suggestions.sort(key=lambda s: (-s["same"], -s["matched"]))
        history = {d for d, e in links.items() if "history" in e["how"]}
        declared = {d for d, e in links.items() if "declared" in e["how"]}
        warning = ("Its configuration names one database, but its history is in another."
                   if history and declared and not history & declared else "")
        found[origin["name"]] = {"links": sorted(links.values(), key=lambda e: e["database"]), "unlinked": unlinked,
                                 "suggestions": suggestions[:3], "warning": warning,
                                 "related": origin.get("related") if origin.get("related") in {o["name"] for o in origins} else ""}
    for origin in origins:  # an ORM's models describe the database its migrations migrated
        entry = found[origin["name"]]
        if entry["related"] and not any("history" in link["how"] or "declared" in link["how"] for link in entry["links"]):
            for link in found[entry["related"]]["links"]:
                if ("history" in link["how"] or "declared" in link["how"]) and link["database"] not in entry["unlinked"] \
                        and all(own["database"] != link["database"] for own in entry["links"]):
                    entry["links"].append({"database": link["database"], "how": ["related"], "history": None, "declared": entry["related"]})
            entry["suggestions"] = [s for s in entry["suggestions"] if all(own["database"] != s["database"] for own in entry["links"])]
    return found
