"""Plans, tasks and notes, kept in one SQLite database (`doc/sqlite/notes.db`).

This is the only code that reads or changes them: the MCP tools (source `agent`) and the wiki
(source `wiki`) both call these methods, so both ends always see and do the same thing.

- A plan says what a piece of work is for: its goal, requirements and decisions. A small plan
  is one branch; a large one is split into tasks, each with a branch of its own if needed.
- A task belongs to a plan and lists what "done" means (its criteria). While it is worked on,
  it gathers annotations (what was done, decided or found) and evidence that it is done (from
  the diff, from the agent or from the wiki).
- A note is lasting knowledge of one of the `NOTE_TYPES`, optionally about entities of the code.
  Notes are not rewritten when they stop being true: a new note supersedes them.
"""

import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

NOTE_TYPES = {
    "preference": "How the user wants the work done.",
    "rule": "A constraint of the project.",
    "decision": "A design decision and why it was taken.",
    "pitfall": "Something not obvious that breaks.",
    "context": "How a part works, or why it is the way it is.",
    "reference": "A pointer to something outside the project.",
    "summary": "What a commit did, kept as history.",
}
"""The closed list of note types, with what each one is for."""

PLAN_STATUSES = ("active", "done")
"""A plan is worked on until it is done."""

TASK_STATUSES = ("todo", "doing", "done")
"""Where a task stands."""

EVIDENCE_SOURCES = ("diff", "agent", "wiki")
"""Where the evidence that a task is done comes from: the changed code, the agent's word or the user in the wiki."""

SOURCES = ("agent", "wiki")
"""Who made a change: an agent through the MCP tools, or the user in the wiki."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '',
  requirements TEXT NOT NULL DEFAULT '[]', decisions TEXT NOT NULL DEFAULT '[]', branches TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'active', source TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  title TEXT NOT NULL, criteria TEXT NOT NULL DEFAULT '[]', branch TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'todo', position INTEGER NOT NULL, source TEXT NOT NULL,
  created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS annotations (
  id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  text TEXT NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  source TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY, type TEXT NOT NULL, statement TEXT NOT NULL, why TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active', source TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS links (
  source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY (source, target, kind));
"""
"""Tables. `links` holds the relations, made by the methods here and never directly by an agent:
`note:<id>` → entity path (`about`), `note:<new>` → `note:<old>` (`supersedes`)."""


def _now() -> str:
    """Current time, ISO 8601 in UTC, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check(value: str, allowed: tuple | dict, what: str) -> None:
    """Refuse a value outside its closed list.

    Args:
        value: The value given.
        allowed: The accepted values.
        what: What the value is, for the error message.

    Raises:
        ValueError: When `value` is not accepted.
    """
    if value not in allowed:
        raise ValueError(f"Unknown {what} {value!r}; use one of: {', '.join(allowed)}.")


def _lines(items: list[str] | None) -> str:
    """Store a list of short texts as JSON, without blank entries."""
    return json.dumps([item.strip() for item in items or [] if item and item.strip()])


class NoteStore:
    """Plans, tasks and notes of the project.

    Args:
        path: Database file; its folder is created when the database is first opened.
        entity_exists: Tells whether an entity path exists in the code, to check the entities a note is about.
        on_change: Called after every change, so open wiki pages reload.

    Attributes:
        path: Database file.
    """

    def __init__(self, path: Path, entity_exists: Callable[[str], bool], on_change: Callable[[], None]) -> None:
        self.path = path
        self._entity_exists = entity_exists
        self._on_change = on_change

    @contextmanager
    def _connect(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        """Open the database for one operation; a write runs in one transaction and notifies the wiki.

        Args:
            write: Whether the operation changes something.

        Yields:
            The connection, with rows readable by column name.
        """
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
        if write:
            self._on_change()

    # --- Plans

    def create_plan(self, title: str, goal: str = "", requirements: list[str] | None = None,
                    decisions: list[str] | None = None, branches: list[str] | None = None, source: str = "agent") -> dict:
        """Start a plan.

        Args:
            title: Short name of the work.
            goal: What the work is for.
            requirements: What the result must do or respect.
            decisions: Decisions already taken, with why.
            branches: Git branches of the plan (none, one, or one per task as the work grows).
            source: `agent` or `wiki`.

        Returns:
            The plan (see `get_plan`).
        """
        _check(source, SOURCES, "source")
        if not title.strip():
            raise ValueError("A plan needs a title.")
        now = _now()
        with self._connect(write=True) as connection:
            plan_id = connection.execute(
                "INSERT INTO plans (title, goal, requirements, decisions, branches, source, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (title.strip(), goal.strip(), _lines(requirements), _lines(decisions), _lines(branches), source, now, now),
            ).lastrowid
        return self.get_plan(plan_id)

    def update_plan(self, plan_id: int, title: str | None = None, goal: str | None = None,
                    requirements: list[str] | None = None, decisions: list[str] | None = None,
                    branches: list[str] | None = None, status: str | None = None) -> dict:
        """Change a plan; only the fields given are changed (a list given replaces the stored one).

        Args:
            plan_id: The plan.
            title: New title.
            goal: New goal.
            requirements: New list of requirements.
            decisions: New list of decisions.
            branches: New list of branches.
            status: `active` or `done`.

        Returns:
            The plan (see `get_plan`).
        """
        changes = {}
        if title is not None:
            if not title.strip():
                raise ValueError("A plan needs a title.")
            changes["title"] = title.strip()
        if goal is not None:
            changes["goal"] = goal.strip()
        for name, items in (("requirements", requirements), ("decisions", decisions), ("branches", branches)):
            if items is not None:
                changes[name] = _lines(items)
        if status is not None:
            _check(status, PLAN_STATUSES, "plan status")
            changes["status"] = status
        self._update("plans", plan_id, changes)
        return self.get_plan(plan_id)

    def delete_plan(self, plan_id: int) -> None:
        """Delete a plan made by mistake, with its tasks.

        Args:
            plan_id: The plan.
        """
        self._delete("plans", plan_id)

    def get_plan(self, plan_id: int) -> dict:
        """Read a plan with its tasks, in order.

        Args:
            plan_id: The plan.

        Returns:
            `id`, `title`, `goal`, `requirements`, `decisions`, `branches`, `status`, `source`,
            `created`, `updated` and `tasks` (see `get_task`).

        Raises:
            ValueError: When there is no such plan.
        """
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
            if row is None:
                raise ValueError(f"There is no plan {plan_id}.")
            plan = self._plan(row)
            task_ids = [task_id for (task_id,) in connection.execute(
                "SELECT id FROM tasks WHERE plan_id = ? ORDER BY position, id", (plan_id,))]
        plan["tasks"] = [self.get_task(task_id) for task_id in task_ids]
        return plan

    def list_plans(self, status: str = "active") -> list[dict]:
        """List the plans, newest first, each with its tasks.

        Args:
            status: `active`, `done`, or empty for every plan.

        Returns:
            The plans (see `get_plan`).
        """
        if status:
            _check(status, PLAN_STATUSES, "plan status")
        with self._connect() as connection:
            query = "SELECT id FROM plans" + (" WHERE status = ?" if status else "") + " ORDER BY id DESC"
            plan_ids = [plan_id for (plan_id,) in connection.execute(query, (status,) if status else ())]
        return [self.get_plan(plan_id) for plan_id in plan_ids]

    # --- Tasks

    def add_task(self, plan_id: int, title: str, criteria: list[str] | None = None, branch: str = "",
                 source: str = "agent") -> dict:
        """Add a task at the end of a plan.

        Args:
            plan_id: The plan it belongs to.
            title: What has to be done.
            criteria: What "done" means for it.
            branch: Its own git branch, when the plan is split into branches per task.
            source: `agent` or `wiki`.

        Returns:
            The task (see `get_task`).
        """
        _check(source, SOURCES, "source")
        if not title.strip():
            raise ValueError("A task needs a title.")
        self.get_plan(plan_id)  # the plan must exist
        now = _now()
        with self._connect(write=True) as connection:
            position = connection.execute("SELECT coalesce(max(position), 0) + 1 FROM tasks WHERE plan_id = ?",
                                          (plan_id,)).fetchone()[0]
            task_id = connection.execute(
                "INSERT INTO tasks (plan_id, title, criteria, branch, position, source, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (plan_id, title.strip(), _lines(criteria), branch.strip(), position, source, now, now),
            ).lastrowid
        return self.get_task(task_id)

    def update_task(self, task_id: int, title: str | None = None, criteria: list[str] | None = None,
                    branch: str | None = None, status: str | None = None) -> dict:
        """Change a task; only the fields given are changed.

        Args:
            task_id: The task.
            title: New title.
            criteria: New list of criteria.
            branch: New branch (empty for none).
            status: `todo`, `doing` or `done`.

        Returns:
            The task (see `get_task`).
        """
        changes = {}
        if title is not None:
            if not title.strip():
                raise ValueError("A task needs a title.")
            changes["title"] = title.strip()
        if criteria is not None:
            changes["criteria"] = _lines(criteria)
        if branch is not None:
            changes["branch"] = branch.strip()
        if status is not None:
            _check(status, TASK_STATUSES, "task status")
            changes["status"] = status
        self._update("tasks", task_id, changes)
        return self.get_task(task_id)

    def delete_task(self, task_id: int) -> None:
        """Delete a task made by mistake, with its annotations and evidence.

        Args:
            task_id: The task.
        """
        self._delete("tasks", task_id)

    def annotate_task(self, task_id: int, text: str, source: str = "agent") -> dict:
        """Write down, on a task, something done, decided or found while working on it.

        Args:
            task_id: The task.
            text: The annotation.
            source: `agent` or `wiki`.

        Returns:
            The task (see `get_task`).
        """
        _check(source, SOURCES, "source")
        if not text.strip():
            raise ValueError("An annotation needs a text.")
        self.get_task(task_id)
        with self._connect(write=True) as connection:
            connection.execute("INSERT INTO annotations (task_id, text, source, created) VALUES (?, ?, ?, ?)",
                               (task_id, text.strip(), source, _now()))
        return self.get_task(task_id)

    def add_evidence(self, task_id: int, source: str, detail: str) -> dict:
        """Record evidence that a task is done.

        Args:
            task_id: The task.
            source: `diff` (the changed code shows it), `agent` (the agent says so) or `wiki` (the user says so).
            detail: What shows it.

        Returns:
            The task (see `get_task`).
        """
        _check(source, EVIDENCE_SOURCES, "evidence source")
        if not detail.strip():
            raise ValueError("Evidence needs a detail.")
        self.get_task(task_id)
        with self._connect(write=True) as connection:
            connection.execute("INSERT INTO evidence (task_id, source, detail, created) VALUES (?, ?, ?, ?)",
                               (task_id, source, detail.strip(), _now()))
        return self.get_task(task_id)

    def get_task(self, task_id: int) -> dict:
        """Read a task with its annotations and evidence, oldest first.

        Args:
            task_id: The task.

        Returns:
            `id`, `plan_id`, `title`, `criteria`, `branch`, `status`, `source`, `created`,
            `updated`, `annotations` and `evidence`.

        Raises:
            ValueError: When there is no such task.
        """
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise ValueError(f"There is no task {task_id}.")
            task = dict(row)
            task["criteria"] = json.loads(task["criteria"])
            task.pop("position")
            task["annotations"] = [dict(item) for item in connection.execute(
                "SELECT id, text, source, created FROM annotations WHERE task_id = ? ORDER BY id", (task_id,))]
            task["evidence"] = [dict(item) for item in connection.execute(
                "SELECT id, source, detail, created FROM evidence WHERE task_id = ? ORDER BY id", (task_id,))]
        return task

    # --- Notes

    def create_note(self, type: str, statement: str, why: str = "", entities: list[str] | None = None,
                    source: str = "agent") -> dict:
        """Write down a piece of lasting knowledge.

        Args:
            type: One of `NOTE_TYPES`.
            statement: The knowledge itself, in one or two sentences.
            why: Why it holds (the reason behind a rule or decision, how a pitfall shows up).
            entities: Paths of the code entities it is about (classes, functions, modules...).
            source: `agent` or `wiki`.

        Returns:
            The note (see `get_note`).
        """
        _check(type, NOTE_TYPES, "note type")
        _check(source, SOURCES, "source")
        if not statement.strip():
            raise ValueError("A note needs a statement.")
        paths = self._entities(entities)
        now = _now()
        with self._connect(write=True) as connection:
            note_id = connection.execute(
                "INSERT INTO notes (type, statement, why, source, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
                (type, statement.strip(), why.strip(), source, now, now),
            ).lastrowid
            self._link_entities(connection, note_id, paths)
        return self.get_note(note_id)

    def update_note(self, note_id: int, statement: str | None = None, why: str | None = None,
                    entities: list[str] | None = None) -> dict:
        """Fix a note (a typo, a missing entity). To record that it no longer holds, use `supersede_note`.

        Args:
            note_id: The note.
            statement: New statement.
            why: New reason.
            entities: New list of entity paths (replaces the stored one).

        Returns:
            The note (see `get_note`).
        """
        changes = {}
        if statement is not None:
            if not statement.strip():
                raise ValueError("A note needs a statement.")
            changes["statement"] = statement.strip()
        if why is not None:
            changes["why"] = why.strip()
        paths = self._entities(entities) if entities is not None else None
        self._update("notes", note_id, changes, force=paths is not None)
        if paths is not None:
            with self._connect(write=True) as connection:
                connection.execute("DELETE FROM links WHERE source = ? AND kind = 'about'", (f"note:{note_id}",))
                self._link_entities(connection, note_id, paths)
        return self.get_note(note_id)

    def supersede_note(self, note_id: int, statement: str, why: str = "", entities: list[str] | None = None,
                       type: str | None = None, source: str = "agent") -> dict:
        """Replace a note that no longer holds by a new one; the old one is kept, marked as superseded.

        Args:
            note_id: The note that no longer holds.
            statement: What holds now.
            why: Why it changed.
            entities: Entities the new note is about; by default, the same as the old one.
            type: Type of the new note; by default, the same as the old one.
            source: `agent` or `wiki`.

        Returns:
            The new note (see `get_note`).
        """
        old = self.get_note(note_id)
        if old["status"] == "superseded":
            raise ValueError(f"Note {note_id} is already superseded by note {old['superseded_by']}.")
        new = self.create_note(type or old["type"], statement, why, old["entities"] if entities is None else entities, source)
        with self._connect(write=True) as connection:
            connection.execute("UPDATE notes SET status = 'superseded', updated = ? WHERE id = ?", (_now(), note_id))
            connection.execute("INSERT INTO links (source, target, kind) VALUES (?, ?, 'supersedes')",
                               (f"note:{new['id']}", f"note:{note_id}"))
        return self.get_note(new["id"])

    def delete_note(self, note_id: int) -> None:
        """Delete a note made by mistake (a note that stopped holding is superseded instead).

        Args:
            note_id: The note.
        """
        self._delete("notes", note_id)
        with self._connect(write=True) as connection:
            connection.execute("DELETE FROM links WHERE source = ? OR target = ?", (f"note:{note_id}", f"note:{note_id}"))

    def get_note(self, note_id: int) -> dict:
        """Read a note.

        Args:
            note_id: The note.

        Returns:
            `id`, `type`, `statement`, `why`, `status` (`active` or `superseded`), `source`,
            `created`, `updated`, `entities`, `supersedes` and `superseded_by` (note ids or `None`).

        Raises:
            ValueError: When there is no such note.
        """
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if row is None:
                raise ValueError(f"There is no note {note_id}.")
            return self._note(connection, row)

    def list_notes(self, type: str = "", status: str = "active", entity: str = "") -> list[dict]:
        """List notes, newest first.

        Args:
            type: Only this type; empty for every type.
            status: `active`, `superseded`, or empty for both.
            entity: Only notes about this entity path; empty for every note.

        Returns:
            The notes (see `get_note`).
        """
        if type:
            _check(type, NOTE_TYPES, "note type")
        conditions, values = [], []
        if type:
            conditions.append("type = ?")
            values.append(type)
        if status:
            conditions.append("status = ?")
            values.append(status)
        if entity:
            conditions.append("'note:' || id IN (SELECT source FROM links WHERE kind = 'about' AND target = ?)")
            values.append(entity)
        query = "SELECT * FROM notes" + (" WHERE " + " AND ".join(conditions) if conditions else "") + " ORDER BY id DESC"
        with self._connect() as connection:
            return [self._note(connection, row) for row in connection.execute(query, values)]

    # --- Helpers

    def _update(self, table: str, row_id: int, changes: dict, force: bool = False) -> None:
        """Change some columns of one row and its `updated` time.

        Args:
            table: `plans`, `tasks` or `notes`.
            row_id: The row.
            changes: New value by column.
            force: Touch `updated` even without column changes (e.g. only its links changed).

        Raises:
            ValueError: When the row does not exist.
        """
        if not changes and not force:
            return
        changes = {**changes, "updated": _now()}
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with self._connect(write=True) as connection:
            cursor = connection.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*changes.values(), row_id))
            if cursor.rowcount == 0:
                raise ValueError(f"There is no {table[:-1]} {row_id}.")

    def _delete(self, table: str, row_id: int) -> None:
        """Delete one row (and, through the foreign keys, what belongs to it).

        Raises:
            ValueError: When the row does not exist.
        """
        with self._connect(write=True) as connection:
            if connection.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,)).rowcount == 0:
                raise ValueError(f"There is no {table[:-1]} {row_id}.")

    def _entities(self, entities: list[str] | None) -> list[str]:
        """Check that every entity path exists in the code.

        Raises:
            ValueError: Naming the paths that do not exist.
        """
        paths = list(dict.fromkeys(path.strip() for path in entities or [] if path.strip()))
        unknown = [path for path in paths if not self._entity_exists(path)]
        if unknown:
            raise ValueError(f"Unknown entities: {', '.join(unknown)}. Use the full path, e.g. pkg.module.Class.")
        return paths

    @staticmethod
    def _link_entities(connection: sqlite3.Connection, note_id: int, paths: list[str]) -> None:
        """Record which entities a note is about."""
        connection.executemany("INSERT OR IGNORE INTO links (source, target, kind) VALUES (?, ?, 'about')",
                               [(f"note:{note_id}", path) for path in paths])

    @staticmethod
    def _plan(row: sqlite3.Row) -> dict:
        """Turn a plan row into a dict, with its lists decoded."""
        plan = dict(row)
        for name in ("requirements", "decisions", "branches"):
            plan[name] = json.loads(plan[name])
        return plan

    @staticmethod
    def _note(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
        """Turn a note row into a dict, with its entities and what it supersedes or is superseded by."""
        note = dict(row)
        key = f"note:{note['id']}"
        note["entities"] = [target for (target,) in connection.execute(
            "SELECT target FROM links WHERE source = ? AND kind = 'about' ORDER BY target", (key,))]
        supersedes = connection.execute("SELECT target FROM links WHERE source = ? AND kind = 'supersedes'", (key,)).fetchone()
        superseded_by = connection.execute("SELECT source FROM links WHERE target = ? AND kind = 'supersedes'", (key,)).fetchone()
        note["supersedes"] = int(supersedes[0].removeprefix("note:")) if supersedes else None
        note["superseded_by"] = int(superseded_by[0].removeprefix("note:")) if superseded_by else None
        return note
