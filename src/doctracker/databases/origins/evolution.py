"""How the project's schema evolved: the moments of each origin and the schema at any of them.

A moment is a migration step (Flyway's V3, an Alembic revision, a Django migration…) or a commit that
changed an origin's files, each marked by its source. A step is placed at the commit that brought its
file (a step not committed yet: now); a commit that edited a step already there is a moment of its own,
flagged; an origin without migrations (a schema file, ORM models, a dump) evolves by its commits, each
version of its files in git a moment, and now when its files have changes not committed. Git is only
read (`git log`, `git archive`), never written.

The schema at a moment goes through the same path as every origin (`read_origin` → `as_collection`): a
step's, the steps up to it applied (an Alembic revision with its ancestors); a commit's, the origin as its
files were then. `schema_diff` tells where two moments' schemas differ, whatever their origins.
"""

import io
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from doctracker.databases.origins.collection import ORIGIN_PREFIX, as_collection
from doctracker.databases.origins.compare import _default, _type
from doctracker.databases.origins.sql import extract_origins, read_origin

MIGRATION_KINDS = ("flyway", "golang-migrate", "dbmate", "prisma", "alembic", "django migrations")
"""The kinds of origin made of migration steps applied in order: their steps are moments of their own."""

NOW = "now"
"""The moment of what is not committed yet."""

_FIELD, _RECORD = "\x1f", "\x1e"


def _files(origin: dict) -> list[str]:
    """The files an origin is read from: its steps' (and their undo steps')."""
    found = []
    for step in origin["steps"]:
        found += [step["file"]] + ([step["down"]] if step.get("down") else [])
    return found


def _git_log(root: Path, files: list[str]) -> list[dict]:
    """The commits that changed these files, oldest first: `hash`, `short`, `at`, `subject` and `files`
    (each file's status: A added, M modified, D deleted, R renamed); empty without git or a repository."""
    if not files or shutil.which("git") is None:
        return []
    try:
        output = subprocess.run(["git", "-C", str(root), "log", "--reverse", "--name-status", "--no-renames",
                                 f"--format={_RECORD}%H{_FIELD}%h{_FIELD}%aI{_FIELD}%s", "--", *files],
                                capture_output=True, text=True, timeout=60, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    commits = []
    for record in output.split(_RECORD)[1:]:
        head, _, body = record.partition("\n")
        full, short, at, subject = (head.split(_FIELD) + ["", "", "", ""])[:4]
        changed = {}
        for line in body.splitlines():
            status, _, path = line.partition("\t")
            if path:
                changed[path] = status[:1]
        commits.append({"hash": full, "short": short, "at": at, "subject": subject, "files": changed})
    return commits


def _uncommitted(root: Path, files: list[str]) -> set[str]:
    """Which of these files have changes not committed (or were never committed)."""
    if not files or shutil.which("git") is None:
        return set()
    try:
        output = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all", "--", *files],
                                capture_output=True, text=True, timeout=30, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line[3:].strip() for line in output.splitlines() if len(line) > 3}


def head(commit: dict | None) -> dict | None:
    """A commit as a moment tells it: `hash`, `short`, `at`, `subject`."""
    return {key: commit[key] for key in ("hash", "short", "at", "subject")} if commit else None


def _when(moment: dict) -> tuple[str, int]:
    """Where a moment is in time: its commit's date (not committed: after every commit), then its step's place."""
    return (moment["commit"]["at"] if moment["commit"] else "9999", moment.get("position", 0))


def moments(root: Path, origins: list[dict]) -> dict:
    """The moments of every origin, for the Evolution tab and the MCP tools.

    Args:
        root: The project's root.
        origins: The origins as read (`extract_origins`).

    Returns:
        `lanes`: one per origin (`origin`, `kind`, `folder`, `migrations`: whether its steps are moments);
        `moments`: each one's `id` (`<origin>@step:<version>`, `<origin>@commit:<hash>`, `<origin>@now`),
        `origin`, `source` (`migration` or `commit`), `version` and `title` (a step's), `revises` (the steps
        it follows: the migration graph), `commit` (`hash`, `short`, `at`, `subject`; none for now), `files`
        (a commit's files and their status), `changed` (the steps a commit edited after they came) and
        `order` (its place in time over every lane).
    """
    lanes, found = [], []
    for origin in sorted(origins, key=lambda o: (o.get("folder", ""), o["name"])):
        files = _files(origin)
        log = _git_log(root, files)
        pending = _uncommitted(root, files)
        migrations = origin["kind"] in MIGRATION_KINDS
        lanes.append({"origin": origin["name"], "kind": origin["kind"], "folder": origin.get("folder", ""), "migrations": migrations})
        brought = {}  # a file → the commit that added it
        for commit in log:
            for path, status in commit["files"].items():
                if status == "A" and path not in brought:
                    brought[path] = commit
        if migrations:
            for position, step in enumerate(origin["steps"]):
                came = brought.get(step["file"])
                found.append({"id": f"{origin['name']}@step:{step['version']}", "origin": origin["name"], "source": "migration",
                              "version": step["version"], "title": step.get("title", ""), "position": position,
                              "revises": step.get("revises") if "revises" in step else ([origin["steps"][position - 1]["version"]] if position else []),
                              "commit": head(came) if came and step["file"] not in pending else None,
                              "files": {step["file"]: "A"}, "changed": []})
        steps_of = {step["file"]: step["version"] for step in origin["steps"]}
        for commit in log:
            changed = [steps_of[path] for path, status in commit["files"].items() if status == "M" and path in steps_of]
            if migrations and not changed and not any(status == "D" for status in commit["files"].values()):
                continue  # it only brought steps: they are its moments
            found.append({"id": f"{origin['name']}@commit:{commit['hash']}", "origin": origin["name"], "source": "commit",
                          "version": "", "title": commit["subject"], "revises": [], "commit": head(commit),
                          "files": commit["files"], "changed": changed if migrations else []})
        if pending and not migrations:
            found.append({"id": f"{origin['name']}@{NOW}", "origin": origin["name"], "source": "commit", "version": "",
                          "title": "Changes not committed", "revises": [], "commit": None,
                          "files": {path: "M" for path in pending}, "changed": []})
    for order, moment in enumerate(sorted(found, key=_when)):
        moment["order"] = order
    return {"lanes": lanes, "moments": sorted(found, key=lambda m: m["order"])}


def _steps_up_to(origin: dict, version: str) -> list[dict]:
    """The steps applied to reach a step: those before it (an Alembic revision: it and its ancestors)."""
    steps = origin["steps"]
    if not any("revises" in step for step in steps):
        index = next(i for i, step in enumerate(steps) if step["version"] == version)
        return steps[:index + 1]
    by_version = {step["version"]: step for step in steps}
    wanted, stack = set(), [version]
    while stack:
        current = stack.pop()
        if current in wanted or current not in by_version:
            continue
        wanted.add(current)
        stack += by_version[current].get("revises") or []
    return [step for step in steps if step["version"] in wanted]


def _at_commit(root: Path, origin: dict, commit: str) -> dict | None:
    """The origin as its files were at a commit: the project's folder holding it, taken out of git into a
    folder of its own (`git archive`, read only), its origins found there again."""
    folder = origin.get("folder") or str(Path(origin["name"]).parent)
    top = Path(folder).parts[0] if Path(folder).parts else "."
    try:
        archive = subprocess.run(["git", "-C", str(root), "archive", "--format=tar", commit, "--", top],
                                 capture_output=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    with tempfile.TemporaryDirectory(prefix="doctracker-moment-") as place:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(place, filter="data")
        files = [str(path.relative_to(place)) for path in Path(place).rglob("*") if path.is_file()]
        then = next((o for o in extract_origins(Path(place), files) if o["name"] == origin["name"]), None)
    return then


def schema_at(root: Path, origins: list[dict], moment_id: str) -> dict | None:
    """The schema at a moment, as a live database's collection (`as_collection`).

    Args:
        root: The project's root.
        origins: The origins as read now.
        moment_id: A moment's id (see `moments`).

    Returns:
        The collection, with `moment` (the id); None when the moment or its origin is unknown.
    """
    name, _, at = moment_id.rpartition("@")
    origin = next((o for o in origins if o["name"] == name), None)
    if origin is None:
        return None
    if at == NOW:
        read = origin
    elif at.startswith("step:"):
        version = at.removeprefix("step:")
        if not any(step["version"] == version for step in origin["steps"]):
            return None
        read = read_origin(root, {**origin, "steps": _steps_up_to(origin, version)}, origin["dialect"])
    elif at.startswith("commit:"):
        read = _at_commit(root, origin, at.removeprefix("commit:"))
        if read is None:
            return None
    else:
        return None
    return {**as_collection(read), "moment": moment_id}


def _local(path: str) -> str:
    """An object's path inside its collection (`schema.table`, `schema.table.column`), whatever its source."""
    if "::" in path:
        return path.split("::", 1)[1]
    return path.split("/", 3)[-1] if path.startswith("db:") else path


_RENAMED = re.compile(r"^renamed column (\S+) to (\S+) in (\S+)$")


def schema_diff(a: dict, b: dict, renames: list[tuple[str, str, str]] | None = None) -> dict:
    """Where two schemas differ: the tables and views of each, aligned by name.

    Args:
        a: The schema at the first moment (a collection, see `schema_at`).
        b: The schema at the second.
        renames: Columns renamed between them (`table`, `old`, `new`), told by the steps.

    Returns:
        `tables`: every table and view of either, in name order, each with `key`, `kind`, `status`
        (`added`, `removed`, `changed`, `same`), `a` and `b` (its path on each side, or none), `columns`
        (each `name`, `status` — added, removed, renamed, changed, same —, `a` and `b`: its type, null and
        default on each side, and `changes`) and `changes` (keys, indexes, checks, comment); `counts` by status.
    """
    def tables(collection: dict) -> dict[str, dict]:
        held = {}
        for obj in collection["objects"]:
            if obj["kind"] in ("table", "view", "materialized view", "foreign table"):
                held[_local(obj["path"]).lower()] = obj
        return held

    def columns(collection: dict) -> dict[str, list[dict]]:
        held: dict[str, list[dict]] = {}
        for obj in collection["objects"]:
            if obj["kind"] == "column":
                held.setdefault(_local(obj["parent"]).lower(), []).append(obj)
        return {key: sorted(found, key=lambda c: c["data"].get("position", 0)) for key, found in held.items()}

    def described(column: dict | None, dialect: str) -> dict | None:
        if column is None:
            return None
        data = column["data"]
        return {"type": data.get("type", ""), "nullable": bool(data.get("nullable", True)), "default": data.get("default") or "",
                "path": column["path"], "compared": (_type(str(data.get("type", "")), dialect), bool(data.get("nullable", True)),
                                                    _default(data.get("default") or "", dialect))}

    dialect_a, dialect_b = a.get("kind") or "postgres", b.get("kind") or "postgres"
    in_a, in_b, columns_a, columns_b = tables(a), tables(b), columns(a), columns(b)
    renamed = {(table.lower(), old.lower()): new.lower() for table, old, new in renames or []}
    found, counts = [], {"added": 0, "removed": 0, "changed": 0, "same": 0}
    for key in sorted(set(in_a) | set(in_b)):
        first, second = in_a.get(key), in_b.get(key)
        entry = {"key": key, "kind": (second or first)["kind"], "a": first and first["path"], "b": second and second["path"],
                 "columns": [], "changes": []}
        if first is None or second is None:
            entry["status"] = "added" if first is None else "removed"
            shown = columns_b.get(key, []) if first is None else columns_a.get(key, [])
            entry["columns"] = [{"name": c["name"], "status": entry["status"], "a": described(c, dialect_a) if second is None else None,
                                 "b": described(c, dialect_b) if first is None else None, "changes": []} for c in shown]
            counts[entry["status"]] += 1
            found.append(entry)
            continue
        old = {c["name"].lower(): c for c in columns_a.get(key, [])}
        new = {c["name"].lower(): c for c in columns_b.get(key, [])}
        table_name = key.rsplit(".", 1)[-1]
        moved = {o: n for (t, o), n in renamed.items() if t in (key, table_name) and o in old and n in new}
        for name in list(new) + [n for n in old if n not in new]:
            before_name = next((o for o, n in moved.items() if n == name), name)
            if name in moved:  # its old name: shown with the new one
                continue
            before, after = described(old.get(before_name), dialect_a), described(new.get(name), dialect_b)
            changes = []
            if before and after:
                if before_name != name:
                    changes.append(f"renamed from {old[before_name]['name']}")
                for index, what in enumerate(("type", "null", "default")):
                    if before["compared"][index] != after["compared"][index]:
                        shown = {"type": (before["type"], after["type"]), "null": ("null allowed" if before["nullable"] else "not null",
                                 "null allowed" if after["nullable"] else "not null"), "default": (before["default"] or "none", after["default"] or "none")}[what]
                        changes.append(f"{what}: {shown[0]} → {shown[1]}")
            status = "added" if before is None else "removed" if after is None else \
                ("renamed" if before_name != name and len(changes) == 1 else "changed" if changes else "same")
            entry["columns"].append({"name": (new.get(name) or old.get(before_name))["name"], "status": status, "a": before, "b": after,
                                     "changes": changes})
        data_a, data_b = first["data"], second["data"]
        pk_a, pk_b = (data_a.get("primary_key") or {}).get("columns") or [], (data_b.get("primary_key") or {}).get("columns") or []
        if [c.lower() for c in pk_a] != [c.lower() for c in pk_b]:
            entry["changes"].append(f"primary key: ({', '.join(pk_a) or 'none'}) → ({', '.join(pk_b) or 'none'})")
        for what, items, name_of in (("foreign key", "foreign_keys", lambda k: f"({', '.join(k['columns'])}) → {_local(k['target'])}"),
                                     ("index", "indexes", lambda i: i.get("name") or ", ".join(i.get("columns") or [])),
                                     ("check", "checks", lambda c: c.get("check") or ""),
                                     ("unique", "unique", lambda u: f"({', '.join(u.get('columns') or [])})")):
            held_a = {name_of(item).lower(): name_of(item) for item in data_a.get(items) or []}
            held_b = {name_of(item).lower(): name_of(item) for item in data_b.get(items) or []}
            entry["changes"] += [f"{what} {held_b[k]} added" for k in sorted(set(held_b) - set(held_a))]
            entry["changes"] += [f"{what} {held_a[k]} removed" for k in sorted(set(held_a) - set(held_b))]
        if (data_a.get("comment") or "") != (data_b.get("comment") or ""):
            entry["changes"].append("comment changed")
        changed = entry["changes"] or any(c["status"] != "same" for c in entry["columns"])
        entry["status"] = "changed" if changed else "same"
        counts[entry["status"]] += 1
        found.append(entry)
    for entry in found:
        for column in entry["columns"]:
            for side in ("a", "b"):
                if column[side]:
                    column[side].pop("compared", None)
    return {"tables": found, "counts": counts}


def renames_between(origins: list[dict], a: str, b: str) -> list[tuple[str, str, str]]:
    """The columns renamed by the steps between two moments of the same migration origin (`table`, `old`,
    `new`, from what each statement did); none across origins."""
    name_a, _, at_a = a.rpartition("@")
    name_b, _, at_b = b.rpartition("@")
    origin = next((o for o in origins if o["name"] == name_a), None)
    if origin is None or name_a != name_b or not at_a.startswith("step:") or not at_b.startswith("step:"):
        return []
    versions = [step["version"] for step in origin["steps"]]
    first, last = sorted((versions.index(at_a[5:]), versions.index(at_b[5:])))
    found = []
    for step in origin["steps"][first + 1:last + 1]:
        for statement in step.get("statements") or []:
            for effect in statement.get("effects") or []:
                if match := _RENAMED.match(effect):
                    found.append((match[3], match[1], match[2]))
    return found


def describe_moment(origins: list[dict], moment_id: str) -> dict | None:
    """What a moment did: a step's statements and their effects; a commit's files (see `moments`)."""
    name, _, at = moment_id.rpartition("@")
    origin = next((o for o in origins if o["name"] == name), None)
    if origin is None:
        return None
    if at.startswith("step:"):
        step = next((s for s in origin["steps"] if s["version"] == at[5:]), None)
        if step is None:
            return None
        return {"origin": name, "file": step["file"], "title": step.get("title", ""), "version": step["version"],
                "statements": [{"line": s["line"], "effects": s["effects"], "read": s["read"]} for s in step.get("statements") or []]}
    return {"origin": name, "path": f"{ORIGIN_PREFIX}{name}"}


__all__ = ["MIGRATION_KINDS", "NOW", "describe_moment", "moments", "renames_between", "schema_at", "schema_diff"]
