"""Slices of the schema: cuts of the whole, each a few tables kept together with a name and a text.

A slice holds a name, a text (Markdown: what the slice is for), its tables — from one or more databases
or from the project's files — and where each box stands in the ER drawing. It is kept in the project,
one file per slice in `doc/slices/<name>.json`, so it is versioned and shared with the project (in a
documented project, `doc/config/` and `doc/slices/` go to git). Each table is kept by its full path (where
it was taken from) and by `schema.table`: opened where that path is not (another machine, another port)
it is found by its name, and the slice says so. Nothing here touches a database.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from doctracker.config import DOC_DIR

SLICES_FOLDER = f"{DOC_DIR}/slices"
"""Where the slices are kept, in the documented project."""

_TABLE_KINDS = ("table", "view", "materialized view", "foreign table")


def table_key(path: str) -> str:
    """A table's `schema.table`, whatever its source (a live database's path, a file's)."""
    if "::" in path:
        return path.split("::", 1)[1]
    return path.split("/", 3)[-1] if path.startswith("db:") else path


def _file_name(name: str) -> str:
    """A slice's file: its name in lower case, letters, digits and dashes."""
    return (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "slice") + ".json"


class SliceStore:
    """The project's slices, one JSON file each.

    Args:
        project_root: Root of the documented project.
        on_change: Called after a slice is saved or deleted (the wiki reloads).
    """

    def __init__(self, project_root: Path, on_change=None) -> None:
        self.folder = project_root / SLICES_FOLDER
        self.on_change = on_change

    def slices(self) -> list[dict]:
        """Every slice, by name."""
        found = []
        for file in sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []:
            try:
                found.append({**json.loads(file.read_text(encoding="utf-8")), "file": f"{SLICES_FOLDER}/{file.name}"})
            except (OSError, ValueError):
                continue
        return sorted(found, key=lambda s: s.get("name", "").lower())

    def slice(self, name: str) -> dict | None:
        """One slice by its name (any case); None when there is none."""
        return next((s for s in self.slices() if s.get("name", "").lower() == name.lower()), None)

    def save(self, name: str, text: str, tables: list[dict], previous: str = "") -> dict:
        """Keep a slice: a new one, or one changed (`previous`: its name before, when renamed).

        Args:
            name: Its name.
            text: What it is for (Markdown).
            tables: Each table's `path` and, when placed in the drawing, `x` and `y`.
            previous: The name it had, when it is renamed or changed.

        Returns:
            The slice as kept.

        Raises:
            ValueError: Without a name or a table, or when another slice has the name.
        """
        name = " ".join(name.split())
        if not name:
            raise ValueError("A slice needs a name.")
        if not tables:
            raise ValueError("A slice needs at least one table.")
        other = self.slice(name)
        if other is not None and other["name"].lower() != (previous or "").lower():
            raise ValueError(f"There is already a slice named {other['name']}.")
        before = self.slice(previous) if previous else None
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        kept = []
        for table in tables:
            entry = {"path": table["path"], "key": table.get("key") or table_key(table["path"])}
            if table.get("x") is not None and table.get("y") is not None:
                entry.update(x=round(float(table["x"])), y=round(float(table["y"])))
            if entry["path"] not in [t["path"] for t in kept]:
                kept.append(entry)
        found = {"name": name, "text": text.strip(), "tables": kept,
                 "created": (before or {}).get("created", now), "changed": now}
        self.folder.mkdir(parents=True, exist_ok=True)
        if before is not None and _file_name(before["name"]) != _file_name(name):
            (self.folder / _file_name(before["name"])).unlink(missing_ok=True)
        (self.folder / _file_name(name)).write_text(json.dumps(found, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if self.on_change:
            self.on_change()
        return found

    def delete(self, name: str) -> None:
        """Forget a slice (its file removed)."""
        found = self.slice(name)
        if found is not None:
            (self.folder / _file_name(found["name"])).unlink(missing_ok=True)
            if self.on_change:
                self.on_change()


def resolve(found: dict, catalog) -> dict:
    """Where a slice's tables are now: each by its path, else by its `schema.table` in the databases read
    and the files (the only one of that name), else missing.

    Args:
        found: The slice.
        catalog: The databases read and what the files declare (`CatalogStore`).

    Returns:
        The slice with, for each table, `found` (its path now, or none), `found_by` (`path`, `name` or
        none) and `kind`; plus `databases` (the databases and files its tables are in) and `total` (how
        many tables and views those hold).
    """
    held = {o["path"]: o for o in catalog.objects(origins=True) if o["kind"] in _TABLE_KINDS}
    by_key: dict[str, list[str]] = {}
    for path in held:
        by_key.setdefault(table_key(path).lower(), []).append(path)
    tables = []
    for table in found.get("tables") or []:
        if table["path"] in held:
            path, how = table["path"], "path"
        else:
            named = by_key.get(table.get("key", table_key(table["path"])).lower(), [])
            path = _closest(named, table["path"])
            how = "name" if path else None
        tables.append({**table, "found": path, "found_by": how, "kind": held[path]["kind"] if path else ""})
    bases = sorted({_base(t["found"]) for t in tables if t["found"]})
    total = sum(1 for path in held if _base(path) in bases)
    return {**found, "tables": tables, "databases": bases, "total": total}


def _database_name(path: str) -> str:
    """The name of the database an object's path is in (a live one's, or a file's last part)."""
    base = _base(path)
    return base.rsplit("@", 1)[-1] if "@" in base else base.rsplit("/", 1)[-1]


def _closest(candidates: list[str], taken_from: str) -> str | None:
    """Of the tables of the same `schema.table`, the one a slice most likely meant: a live database of the
    same name, then a file of that database, then the only live one, then the only one; none when it stays
    ambiguous."""
    wanted = _database_name(taken_from).lower()
    live = [path for path in candidates if path.startswith("db:")]
    for group in ([p for p in live if _database_name(p).lower() == wanted],
                  [p for p in candidates if _database_name(p).lower() == wanted], live, candidates):
        if len(group) == 1:
            return group[0]
    return None


def _base(path: str) -> str:
    """The database (or file) an object's path is in."""
    if "::" in path:
        return path.split("::", 1)[0]
    return "/".join(path.split("/")[:2])


__all__ = ["SLICES_FOLDER", "SliceStore", "resolve", "table_key"]
