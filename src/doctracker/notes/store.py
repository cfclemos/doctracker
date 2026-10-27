"""Plans and notes, kept in one SQLite database (`doc/sqlite/notes.db`).

This is the only code that reads or changes them: the MCP tools (source `agent`) and the wiki
(source `wiki`) both call these methods, so both ends always see and do the same thing.

The planner. A plan is made of features, a feature of tasks; a simple plan is just one feature
with one task. Only tasks have a status set by hand (`todo`, `doing`, `done`); the state of a
feature or plan is worked out from its tasks. Any item (plan, feature or task, written
`plan:1`, `feature:2`, `task:3`) may also depend on any other item, always with a reason; an
item whose dependencies are not done is blocked. Items may have a due date: one not done past
it is late, and so are its parents. While a task is worked on, it gathers annotations (what was
done, decided or found) and evidence that it is done (from the diff, the agent or the wiki).

The notes. Lasting knowledge of one of the `NOTE_TYPES`, in two groups: guidelines (how to work)
and memory (what is known), optionally about entities of the code. Notes are not rewritten
when they stop being true: a new note supersedes them.
"""

import json
import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

NOTE_TYPES = {
    "preference": "How the user wants the work done.",
    "rule": "A constraint of the project.",
    "decision": "A design decision and why it was taken.",
    "context": "How a part works, or why it is the way it is.",
    "pitfall": "Something not obvious that breaks.",
    "reference": "A pointer to something outside the project.",
}
"""The closed list of note types, with what each one is for."""

NOTE_GROUPS = {"guidelines": ("preference", "rule"), "memory": ("decision", "context", "pitfall", "reference")}
"""Guidelines say how to work; memory keeps what is known about the project."""

NOTE_GROUP_TEXTS = {
    "guidelines": ("How the work must be done.", "Agents get these by themselves: always, when planning, when "
                   "committing (its moments), and when the code of its entities is read or edited."),
    "memory": ("What is known about the project.", "Not given by itself: agents find it with recall when they "
               "need it, and the notes about some code come when that code is read or edited."),
}
"""What each group is for and how agents get it: `(title, text)`."""

NOTE_TYPE_USES = {
    "preference": ("Write it when the user corrects or confirms a way of working.",
                   "Show the commit text before committing."),
    "rule": ("It holds whoever works on the project; it is not a matter of taste.",
             "Dependencies only under permissive licenses (MIT, BSD, Apache-2.0, ISC)."),
    "decision": ("A choice taken with the user, with why, so nobody undoes it by mistake.",
                 "Commits made outside the flow are found by the git watcher, not by git hooks, which would "
                 "clash with the project's own."),
    "context": ("When the code alone does not say how a part works or why it is so.",
                "doctracker documents itself: the server runs on port 8765."),
    "pitfall": ("Something not obvious that breaks, and how it shows up.",
                "Changes to Python files need a server restart; templates do not."),
    "reference": ("Where to find something outside the project.",
                  "The second test project is ~/Documentos/Projects/Teste3."),
}
"""When to write each note type, `(when, example)`: shown in the wiki and in the create_note tool."""

NOT_A_NOTE = "Not a note: the progress of a task (annotate the task) or what the code and git already say."
"""What does not go into notes."""

TASK_STATUSES = ("todo", "doing", "done")
"""Where a task stands, set by hand."""

STATES = ("todo", "doing", "blocked", "late", "done")
"""Worked-out state of any item: `done` wins, then `late` (due date passed), then `blocked`
(a dependency is not done), then `doing` and `todo`."""

EVIDENCE_SOURCES = ("diff", "agent", "wiki")
"""Where the evidence that a task is done comes from: the changed code, the agent's word or the user in the wiki."""

SOURCES = ("agent", "wiki")
"""Who made a change: an agent through the MCP tools, or the user in the wiki."""

KINDS = {"plan": "plans", "feature": "features", "task": "tasks"}
"""Kinds of planner items, with their table."""

MOMENTS = ("always", "planning", "commit")
"""When a guideline is given to the agent: in every session, when planning, when committing.
A note about code entities is also given when that code is read or edited."""

REVIEWS = {"title": "Reviews", "goal": "Commits made outside the flow, to be checked against the planning and the memory.",
           "feature": "Commits outside the flow"}
"""The fixed plan of the reviews: created with the store, never deleted, its own fields never change."""

ADDED_COLUMNS = (("notes", "moments", "TEXT NOT NULL DEFAULT '[]'"), ("plans", "fixed", "INTEGER NOT NULL DEFAULT 0"))
"""Columns added after the first version of the tables: `ALTER TABLE` adds them to an older database."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY, title TEXT NOT NULL, goal TEXT NOT NULL DEFAULT '',
  requirements TEXT NOT NULL DEFAULT '[]', decisions TEXT NOT NULL DEFAULT '[]', branches TEXT NOT NULL DEFAULT '[]',
  due TEXT NOT NULL DEFAULT '', source TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS features (
  id INTEGER PRIMARY KEY, plan_id INTEGER NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', branch TEXT NOT NULL DEFAULT '',
  due TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY, feature_id INTEGER NOT NULL REFERENCES features(id) ON DELETE CASCADE,
  title TEXT NOT NULL, criteria TEXT NOT NULL DEFAULT '[]', branch TEXT NOT NULL DEFAULT '', due TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'todo', position INTEGER NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS annotations (
  id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  text TEXT NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence (
  id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  source TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dependencies (
  item TEXT NOT NULL, depends_on TEXT NOT NULL, reason TEXT NOT NULL, source TEXT NOT NULL, created TEXT NOT NULL,
  PRIMARY KEY (item, depends_on));
CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY, type TEXT NOT NULL, statement TEXT NOT NULL, why TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active', source TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS links (
  source TEXT NOT NULL, target TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY (source, target, kind));
CREATE TABLE IF NOT EXISTS commits (
  hash TEXT PRIMARY KEY, tasks TEXT NOT NULL DEFAULT '[]', closed INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS archive (
  id INTEGER PRIMARY KEY, item TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL, plan TEXT NOT NULL,
  feature TEXT NOT NULL DEFAULT '', content TEXT NOT NULL, commits TEXT NOT NULL DEFAULT '[]', archived TEXT NOT NULL);
"""
"""Tables. Task criteria are `[{"text", "done"}]`. `dependencies` says that `item` waits for
`depends_on` (both `kind:id`). `links` holds the relations of notes, made by the methods here:
`note:<id>` → entity path (`about`), `note:<new>` → `note:<old>` (`supersedes`). A note's `moments`
is a JSON list (guidelines only); a plan with `fixed` 1 is the Reviews plan. `commits` holds the
commits made by the commit flow, with the tasks of each (`closed` once the post-commit recorded
them); `meta` holds the sync marker (`last_commit`, `last_check`). `archive` keeps the planner items
the post-commit deleted, with what they held (JSON `content`) and the full hashes of their `commits`."""

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
"""A due date, `YYYY-MM-DD`."""


def _now() -> str:
    """Current time, ISO 8601 in UTC, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _check(value: str, allowed, what: str) -> None:
    """Refuse a value outside its closed list.

    Raises:
        ValueError: When `value` is not one of `allowed`.
    """
    if value not in allowed:
        raise ValueError(f"Unknown {what} {value!r}; use one of: {', '.join(allowed)}.")


def _title(title: str, what: str) -> str:
    """A title without surrounding blanks; refused when empty."""
    if not title or not title.strip():
        raise ValueError(f"A {what} needs a title.")
    return title.strip()


def _due(due: str | None) -> str:
    """A due date, checked: `YYYY-MM-DD`, or empty for none."""
    due = (due or "").strip()
    if due and (not _DATE.match(due) or not _valid_date(due)):
        raise ValueError(f"Use the date format YYYY-MM-DD for the due date, not {due!r}.")
    return due


def _valid_date(text: str) -> bool:
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False


def _lines(items: list[str] | None) -> str:
    """Store a list of short texts as JSON, without blank entries."""
    return json.dumps([item.strip() for item in items or [] if item and item.strip()])


def _criteria(items: list | None) -> str:
    """Store task criteria as JSON `[{"text", "done"}]`; plain texts start not done."""
    criteria = []
    for item in items or []:
        text, done = (item.get("text", ""), bool(item.get("done"))) if isinstance(item, dict) else (item, False)
        if text and str(text).strip():
            criteria.append({"text": str(text).strip(), "done": done})
    return json.dumps(criteria)


def parse_item(item: str) -> tuple[str, int]:
    """Split a planner item reference, e.g. `task:3` → (`task`, 3).

    Raises:
        ValueError: When it is not `plan:<id>`, `feature:<id>` or `task:<id>`.
    """
    kind, _, number = (item or "").strip().partition(":")
    if kind not in KINDS or not number.isdigit():
        raise ValueError(f"Refer to a planner item as plan:<id>, feature:<id> or task:<id>, not {item!r}.")
    return kind, int(number)


class NoteStore:
    """Plans (with their features and tasks) and notes of the project.

    Args:
        path: Database file; its folder is created when the database is first opened.
        entity_exists: Tells whether an entity path exists in the code, to check the entities a note is about.
        on_change: Called after every change, so open wiki pages reload.

    Attributes:
        path: Database file.
        committing: True while the commit flow runs, so its commits are not taken for outside ones.
    """

    def __init__(self, path: Path, entity_exists: Callable[[str], bool], on_change: Callable[[], None]) -> None:
        self.path = path
        self._entity_exists = entity_exists
        self._on_change = on_change
        self.committing = False
        self._ensure_reviews()

    @contextmanager
    def _connect(self, write: bool = False) -> Iterator[sqlite3.Connection]:
        """Open the database for one operation; a write runs in one transaction and notifies the wiki."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(SCHEMA)
            _add_columns(connection)
            if write:
                with connection:
                    yield connection
            else:
                yield connection
        finally:
            connection.close()
        if write:
            self._on_change()

    def _ensure_reviews(self) -> None:
        """Create the fixed Reviews plan, with its feature, when the database has none."""
        with self._connect() as connection, connection:
            if connection.execute("SELECT 1 FROM plans WHERE fixed = 1").fetchone():
                return
            now = _now()
            plan_id = connection.execute(
                "INSERT INTO plans (title, goal, fixed, source, created, updated) VALUES (?, ?, 1, 'agent', ?, ?)",
                (REVIEWS["title"], REVIEWS["goal"], now, now)).lastrowid
            connection.execute(
                "INSERT INTO features (plan_id, title, position, source, created, updated) VALUES (?, ?, 0, 'agent', ?, ?)",
                (plan_id, REVIEWS["feature"], now, now))

    def _refuse_fixed(self, plan_id: int) -> None:
        """Refuse to change or delete the Reviews plan itself.

        Raises:
            ValueError: When `plan_id` is the Reviews plan.
        """
        with self._connect() as connection:
            if connection.execute("SELECT 1 FROM plans WHERE id = ? AND fixed = 1", (plan_id,)).fetchone():
                raise ValueError("The Reviews plan is fixed: it is never deleted and its own fields do not change. "
                                 "Change its features and tasks instead.")

    # --- Planner: creating

    def create_plan(self, title: str, goal: str = "", requirements: list[str] | None = None,
                    decisions: list[str] | None = None, branches: list[str] | None = None, due: str = "",
                    features: list[dict] | None = None, source: str = "agent") -> dict:
        """Create a plan with its features and tasks in one go.

        Without features, the plan gets one feature with one task, both with its title: a simple
        plan. A feature given without tasks gets one task with its title.

        Args:
            title: Short name of the work.
            goal: What the work is for.
            requirements: What the result must do or respect.
            decisions: Decisions already taken, with why.
            branches: Git branches of the plan, if any.
            due: Due date, `YYYY-MM-DD`.
            features: `[{"title", "description", "branch", "due", "tasks": [{"title", "criteria", "branch", "due"}]}]`.
            source: `agent` or `wiki`.

        Returns:
            The plan (see `get_plan`).
        """
        _check(source, SOURCES, "source")
        title = _title(title, "plan")
        features = features or [{"title": title}]
        now = _now()
        with self._connect(write=True) as connection:
            plan_id = connection.execute(
                "INSERT INTO plans (title, goal, requirements, decisions, branches, due, source, created, updated)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (title, (goal or "").strip(), _lines(requirements), _lines(decisions), _lines(branches), _due(due),
                 source, now, now),
            ).lastrowid
            for feature in features:
                self._insert_feature(connection, plan_id, feature, source)
        return self.get_plan(plan_id)

    def add_feature(self, plan_id: int, title: str, description: str = "", branch: str = "", due: str = "",
                    tasks: list[dict] | None = None, source: str = "agent") -> dict:
        """Add a feature, with its tasks, at the end of a plan; without tasks it gets one with its title.

        Args:
            plan_id: The plan.
            title: What the feature delivers.
            description: More about it.
            branch: Its git branch, if it has one of its own.
            due: Due date, `YYYY-MM-DD`.
            tasks: `[{"title", "criteria", "branch", "due"}]`.
            source: `agent` or `wiki`.

        Returns:
            The feature (see `get_feature`).
        """
        _check(source, SOURCES, "source")
        self._exists("plan", plan_id)
        with self._connect(write=True) as connection:
            feature_id = self._insert_feature(connection, plan_id, {"title": title, "description": description,
                                                                    "branch": branch, "due": due, "tasks": tasks}, source)
        return self.get_feature(feature_id)

    def add_task(self, feature_id: int, title: str, criteria: list[str] | None = None, branch: str = "", due: str = "",
                 source: str = "agent") -> dict:
        """Add a task at the end of a feature.

        Args:
            feature_id: The feature.
            title: What has to be done.
            criteria: What "done" means for it, one per item.
            branch: Its own git branch, if any.
            due: Due date, `YYYY-MM-DD`.
            source: `agent` or `wiki`.

        Returns:
            The task (see `get_task`).
        """
        _check(source, SOURCES, "source")
        self._exists("feature", feature_id)
        with self._connect(write=True) as connection:
            task_id = self._insert_task(connection, feature_id, {"title": title, "criteria": criteria, "branch": branch,
                                                                 "due": due}, source)
        return self.get_task(task_id)

    def _insert_feature(self, connection: sqlite3.Connection, plan_id: int, feature: dict, source: str) -> int:
        """Insert a feature and its tasks (one task with its title when none is given)."""
        title = _title(feature.get("title", ""), "feature")
        now = _now()
        position = connection.execute("SELECT coalesce(max(position), 0) + 1 FROM features WHERE plan_id = ?",
                                      (plan_id,)).fetchone()[0]
        feature_id = connection.execute(
            "INSERT INTO features (plan_id, title, description, branch, due, position, source, created, updated)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (plan_id, title, (feature.get("description") or "").strip(), (feature.get("branch") or "").strip(),
             _due(feature.get("due")), position, source, now, now),
        ).lastrowid
        for task in feature.get("tasks") or [{"title": title}]:
            self._insert_task(connection, feature_id, task, source)
        return feature_id

    def _insert_task(self, connection: sqlite3.Connection, feature_id: int, task: dict, source: str) -> int:
        """Insert a task at the end of a feature."""
        now = _now()
        position = connection.execute("SELECT coalesce(max(position), 0) + 1 FROM tasks WHERE feature_id = ?",
                                      (feature_id,)).fetchone()[0]
        return connection.execute(
            "INSERT INTO tasks (feature_id, title, criteria, branch, due, position, source, created, updated)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (feature_id, _title(task.get("title", ""), "task"), _criteria(task.get("criteria")),
             (task.get("branch") or "").strip(), _due(task.get("due")), position, source, now, now),
        ).lastrowid

    # --- Planner: changing

    def update_plan(self, plan_id: int, title: str | None = None, goal: str | None = None,
                    requirements: list[str] | None = None, decisions: list[str] | None = None,
                    branches: list[str] | None = None, due: str | None = None) -> dict:
        """Change a plan; only the fields given change (a list given replaces the stored one).

        Returns:
            The plan (see `get_plan`).

        Raises:
            ValueError: For the Reviews plan, whose fields never change.
        """
        self._refuse_fixed(plan_id)
        changes = {}
        if title is not None:
            changes["title"] = _title(title, "plan")
        if goal is not None:
            changes["goal"] = goal.strip()
        for name, items in (("requirements", requirements), ("decisions", decisions), ("branches", branches)):
            if items is not None:
                changes[name] = _lines(items)
        if due is not None:
            changes["due"] = _due(due)
        self._update("plan", plan_id, changes)
        return self.get_plan(plan_id)

    def update_feature(self, feature_id: int, title: str | None = None, description: str | None = None,
                       branch: str | None = None, due: str | None = None) -> dict:
        """Change a feature; only the fields given change.

        Returns:
            The feature (see `get_feature`).
        """
        changes = {}
        if title is not None:
            changes["title"] = _title(title, "feature")
        if description is not None:
            changes["description"] = description.strip()
        if branch is not None:
            changes["branch"] = branch.strip()
        if due is not None:
            changes["due"] = _due(due)
        self._update("feature", feature_id, changes)
        return self.get_feature(feature_id)

    def update_task(self, task_id: int, title: str | None = None, criteria: list | None = None,
                    branch: str | None = None, due: str | None = None, status: str | None = None,
                    source: str = "agent") -> dict:
        """Change a task; only the fields given change.

        Marking a task done in the wiki also records it as evidence from the user.

        Args:
            task_id: The task.
            title: New title.
            criteria: New criteria: texts (a text kept from before keeps its tick), or `{"text", "done"}`.
            branch: New branch (empty for none).
            due: New due date (empty for none).
            status: `todo`, `doing` or `done`.
            source: `agent` or `wiki`.

        Returns:
            The task (see `get_task`).
        """
        _check(source, SOURCES, "source")
        changes = {}
        if title is not None:
            changes["title"] = _title(title, "task")
        current = self.get_task(task_id)
        if criteria is not None:
            ticked = {criterion["text"] for criterion in current["criteria"] if criterion["done"]}
            changes["criteria"] = _criteria([item if isinstance(item, dict) else {"text": item, "done": item.strip() in ticked}
                                             for item in criteria if item])
        if branch is not None:
            changes["branch"] = branch.strip()
        if due is not None:
            changes["due"] = _due(due)
        if status is not None:
            _check(status, TASK_STATUSES, "task status")
            changes["status"] = status
        was_done = current["status"] == "done"
        self._update("task", task_id, changes)
        if status == "done" and not was_done and source == "wiki":
            self.add_evidence(task_id, "wiki", "Marked done in the wiki.")
        return self.get_task(task_id)

    def approve_task(self, task_id: int, detail: str = "") -> dict:
        """Close a task with the user's explicit approval, given in the wiki, recorded as evidence.

        Args:
            task_id: The task.
            detail: What the user checked or says, if anything.

        Returns:
            The task (see `get_task`).
        """
        self._exists("task", task_id)
        self.add_evidence(task_id, "wiki", "Approved as done by the user" + (f": {detail.strip()}" if detail.strip() else "."))
        self._update("task", task_id, {"status": "done"})
        return self.get_task(task_id)

    def withdraw_approval(self, task_id: int, reason: str = "") -> dict:
        """Take back the user's approval of a task: it goes back to doing.

        The evidence the approval recorded in the wiki ("Approved as done…", "Marked done in the wiki.")
        is deleted, as it no longer holds; other evidence stays. An annotation keeps that the approval
        was withdrawn, and why.

        Args:
            task_id: The task.
            reason: Why the approval is withdrawn, if said.

        Returns:
            The task (see `get_task`).
        """
        self._exists("task", task_id)
        with self._connect(write=True) as connection:
            connection.execute("DELETE FROM evidence WHERE task_id = ? AND source = 'wiki'"
                               " AND (detail LIKE 'Approved as done by the user%' OR detail = 'Marked done in the wiki.')",
                               (task_id,))
            connection.execute("UPDATE tasks SET status = 'doing', updated = ? WHERE id = ?", (_now(), task_id))
            connection.execute("INSERT INTO annotations (task_id, text, source, created) VALUES (?, ?, 'wiki', ?)",
                               (task_id, "Approval withdrawn" + (f": {reason.strip()}" if reason.strip() else "."), _now()))
        return self.get_task(task_id)

    def check_criterion(self, task_id: int, index: int, done: bool = True, source: str = "agent") -> dict:
        """Tick (or untick) one criterion of a task; ticking it in the wiki is recorded as evidence, and
        unticking it takes that evidence back.

        Args:
            task_id: The task.
            index: Position of the criterion, from 0.
            done: Whether it is met.
            source: `agent` or `wiki`.

        Returns:
            The task (see `get_task`).
        """
        _check(source, SOURCES, "source")
        criteria = self.get_task(task_id)["criteria"]
        if not 0 <= index < len(criteria):
            raise ValueError(f"Task {task_id} has no criterion {index}; it has {len(criteria)} (counted from 0).")
        criteria[index]["done"] = bool(done)
        self._update("task", task_id, {"criteria": json.dumps(criteria)})
        detail = f"Checked in the wiki: {criteria[index]['text']}"
        if done and source == "wiki":
            self.add_evidence(task_id, "wiki", detail)
        elif not done:  # unticked: the evidence its tick recorded no longer holds
            with self._connect(write=True) as connection:
                connection.execute("DELETE FROM evidence WHERE id = (SELECT max(id) FROM evidence WHERE task_id = ?"
                                   " AND source = 'wiki' AND detail = ?)", (task_id, detail))
        return self.get_task(task_id)

    def annotate_task(self, task_id: int, text: str, source: str = "agent") -> dict:
        """Write down, on a task, something done, decided or found while working on it.

        Returns:
            The task (see `get_task`).
        """
        _check(source, SOURCES, "source")
        if not text or not text.strip():
            raise ValueError("An annotation needs a text.")
        self._exists("task", task_id)
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
        if not detail or not detail.strip():
            raise ValueError("Evidence needs a detail.")
        self._exists("task", task_id)
        with self._connect(write=True) as connection:
            connection.execute("INSERT INTO evidence (task_id, source, detail, created) VALUES (?, ?, ?, ?)",
                               (task_id, source, detail.strip(), _now()))
        return self.get_task(task_id)

    def update_evidence(self, evidence_id: int, detail: str) -> dict:
        """Change what a piece of evidence says.

        Returns:
            The task it belongs to (see `get_task`).
        """
        return self._change_entry("evidence", "detail", evidence_id, detail)

    def delete_evidence(self, evidence_id: int) -> dict:
        """Delete a piece of evidence that does not hold.

        Returns:
            The task it belonged to (see `get_task`).
        """
        return self._delete_entry("evidence", evidence_id)

    def update_annotation(self, annotation_id: int, text: str) -> dict:
        """Change what an annotation of a task says.

        Returns:
            The task it belongs to (see `get_task`).
        """
        return self._change_entry("annotations", "text", annotation_id, text)

    def delete_annotation(self, annotation_id: int) -> dict:
        """Delete an annotation of a task.

        Returns:
            The task it belonged to (see `get_task`).
        """
        return self._delete_entry("annotations", annotation_id)

    def _change_entry(self, table: str, column: str, entry_id: int, value: str) -> dict:
        """Change the text of one annotation or piece of evidence.

        Args:
            table: `annotations` or `evidence`.
            column: Its text column (`text` or `detail`).
            entry_id: The entry.
            value: The new text.

        Returns:
            The task it belongs to (see `get_task`).
        """
        what = "an annotation" if table == "annotations" else "evidence"
        if not value or not value.strip():
            raise ValueError(f"{what.capitalize()} needs a text.")
        with self._connect(write=True) as connection:
            row = connection.execute(f"SELECT task_id FROM {table} WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise ValueError(f"There is no {what.removeprefix('an ')} {entry_id}.")
            connection.execute(f"UPDATE {table} SET {column} = ? WHERE id = ?", (value.strip(), entry_id))
        return self.get_task(row["task_id"])

    def _delete_entry(self, table: str, entry_id: int) -> dict:
        """Delete one annotation or piece of evidence.

        Returns:
            The task it belonged to (see `get_task`).
        """
        with self._connect(write=True) as connection:
            row = connection.execute(f"SELECT task_id FROM {table} WHERE id = ?", (entry_id,)).fetchone()
            if row is None:
                raise ValueError(f"There is no {'annotation' if table == 'annotations' else 'evidence'} {entry_id}.")
            connection.execute(f"DELETE FROM {table} WHERE id = ?", (entry_id,))
        return self.get_task(row["task_id"])

    def delete_item(self, item: str) -> None:
        """Delete a plan, feature or task made by mistake, with everything inside it and its dependencies.

        Args:
            item: `plan:<id>`, `feature:<id>` or `task:<id>`; the Reviews plan is refused.
        """
        kind, item_id = parse_item(item)
        if kind == "plan":
            self._refuse_fixed(item_id)
        inside = self._descendants(kind, item_id)
        with self._connect(write=True) as connection:
            if connection.execute(f"DELETE FROM {KINDS[kind]} WHERE id = ?", (item_id,)).rowcount == 0:
                raise ValueError(f"There is no {kind} {item_id}.")
            for gone in inside:
                connection.execute("DELETE FROM dependencies WHERE item = ? OR depends_on = ?", (gone, gone))

    # --- Planner: dependencies

    def add_dependency(self, item: str, depends_on: str | list[str], reason: str, source: str = "agent") -> dict:
        """Record that an item waits for one or more others (any kinds), and why.

        Either all of them are recorded or none: each one is checked before any is written.

        Args:
            item: The item that waits, e.g. `task:3`.
            depends_on: What it waits for, e.g. `plan:1`, or several of them.
            reason: Why it waits for them; shown on the lines in the planner.
            source: `agent` or `wiki`.

        Returns:
            The item that waits (see `get_item`).

        Raises:
            ValueError: When an item does not exist, nothing is given, the reason is empty, an item is
                inside the one that waits (it already waits for what it contains), or a dependency would
                make a cycle (counting that a plan waits for its features, a feature for its tasks).
        """
        _check(source, SOURCES, "source")
        waited = [depends_on] if isinstance(depends_on, str) else list(depends_on or [])
        if not waited:
            raise ValueError("Say what the item waits for.")
        if not reason or not reason.strip():
            raise ValueError("A dependency needs a reason.")
        item = ":".join(map(str, parse_item(item)))
        self._exists(*parse_item(item))
        references = []
        inside = set(self._descendants(*parse_item(item))) - {item}
        for other in waited:
            other = ":".join(map(str, parse_item(other)))
            self._exists(*parse_item(other))
            if other in inside:
                raise ValueError(f"{item} contains {other}: it already waits for it.")
            if item == other or item in self._waits_for(other):
                raise ValueError(f"{item} cannot depend on {other}: {other} already waits for {item}, "
                                 "directly, through other dependencies or through what it contains.")
            references.append(other)
        with self._connect(write=True) as connection:
            connection.executemany("INSERT OR REPLACE INTO dependencies (item, depends_on, reason, source, created)"
                                   " VALUES (?, ?, ?, ?, ?)", [(item, other, reason.strip(), source, _now()) for other in references])
        return self.get_item(item)

    def remove_dependency(self, item: str, depends_on: str) -> dict:
        """Remove a dependency.

        Returns:
            The item that waited (see `get_item`).
        """
        item, depends_on = ":".join(map(str, parse_item(item))), ":".join(map(str, parse_item(depends_on)))
        with self._connect(write=True) as connection:
            if connection.execute("DELETE FROM dependencies WHERE item = ? AND depends_on = ?",
                                  (item, depends_on)).rowcount == 0:
                raise ValueError(f"{item} does not depend on {depends_on}.")
        return self.get_item(item)

    def _children(self, connection: sqlite3.Connection, item: str) -> list[str]:
        """What an item contains: a plan its features, a feature its tasks."""
        kind, item_id = parse_item(item)
        if kind == "plan":
            return [f"feature:{row[0]}" for row in connection.execute("SELECT id FROM features WHERE plan_id = ?", (item_id,))]
        if kind == "feature":
            return [f"task:{row[0]}" for row in connection.execute("SELECT id FROM tasks WHERE feature_id = ?", (item_id,))]
        return []

    def _waits_for(self, item: str) -> set[str]:
        """Everything an item waits for: its dependencies and what it contains, followed all the way."""
        seen: set[str] = set()
        with self._connect() as connection:
            pending = [item]
            while pending:
                current = pending.pop()
                following = self._children(connection, current) + [row[0] for row in connection.execute(
                    "SELECT depends_on FROM dependencies WHERE item = ?", (current,))]
                for other in following:
                    if other not in seen:
                        seen.add(other)
                        pending.append(other)
        return seen

    def _descendants(self, kind: str, item_id: int) -> list[str]:
        """An item and everything it contains."""
        found, pending = [], [f"{kind}:{item_id}"]
        with self._connect() as connection:
            while pending:
                current = pending.pop()
                found.append(current)
                pending.extend(self._children(connection, current))
        return found

    # --- Planner: reading

    def planner(self, include_done: bool = True, include_empty_reviews: bool = False) -> dict:
        """Everything in the planner, with the worked-out state of every item.

        Args:
            include_done: Also the plans that are done.
            include_empty_reviews: Also the Reviews plan while it has no task (it is left out then).

        Returns:
            `plans` (newest first, see `get_plan`) and `dependencies` (`item`, `depends_on`, `reason`).
        """
        today = date.today().isoformat()
        with self._connect() as connection:
            plans = [self._plan(row) for row in connection.execute("SELECT * FROM plans ORDER BY id DESC")]
            features = [dict(row) for row in connection.execute("SELECT * FROM features ORDER BY position, id")]
            tasks = [self._task_row(connection, row) for row in connection.execute("SELECT * FROM tasks ORDER BY position, id")]
            dependencies = [dict(row) for row in connection.execute(
                "SELECT item, depends_on, reason, source, created FROM dependencies ORDER BY created")]
        _work_out_states(plans, features, tasks, dependencies, today)
        if not include_empty_reviews:
            plans = [plan for plan in plans if not plan["fixed"] or any(f["tasks"] for f in plan["features"])]
        if not include_done:
            plans = [plan for plan in plans if plan["state"] != "done"]
        kept = {item for plan in plans for item in _items_of(plan)}
        return {"plans": plans, "dependencies": [d for d in dependencies if d["item"] in kept or d["depends_on"] in kept]}

    def planner_graph(self, plan_ids: list[int] | None = None) -> dict:
        """The planner as a graph, for the wiki: plans and features are frames, tasks are boxes.

        Only the highest of levels that repeat one another is drawn: a feature whose only task has
        its title is drawn as that task's box (labeled as the feature); a plan whose only feature has
        its title takes that feature's place (a frame of its tasks, or a single box). Dependencies of
        the levels not drawn go to the one drawn.

        Args:
            plan_ids: Only these plans; `None` for all. An item of another plan that one of them
                depends on (or that depends on one of them) comes as an `external` node, so the
                dependency still shows.

        Returns:
            `nodes` (`id` = item reference, `kind` (plan, feature, task or external), `label`, `state`,
            `parent`, `frame` and the item's fields; a box of a task also has `level` (the item it
            stands for: plan, feature or task), `task_id`, `open` (the task's reference) and
            `waits_for`, its dependencies with their titles; an external node has `plan_id` and `plan`)
            and `edges` (`source` = what is waited for, `target` = what waits, `reason`); `drawn_as` gives,
            for every item shown, the node it is drawn in.
        """
        planner = self.planner()
        owner = {}  # item reference -> (its plan, the item)
        for plan in planner["plans"]:
            for entry in [plan, *plan["features"], *(task for feature in plan["features"] for task in feature["tasks"])]:
                owner[entry["item"]] = (plan, entry)

        def same(first: dict, second: dict) -> bool:
            return first["title"].strip().casefold() == second["title"].strip().casefold()

        def task_box(task: dict, stands_for: dict, level: str, parent: str, merged: list[dict]) -> dict:
            waits = [dict(waited, title=owner[waited["item"]][1]["title"]) for item in merged for waited in item["depends_on"]]
            return {"id": stands_for["item"], "kind": "task", "level": level, "label": stands_for["title"],
                    "state": stands_for["state"], "status": task["status"], "parent": parent, "frame": False,
                    "task_id": task["id"], "open": task["item"], "due": stands_for["due"] or task["due"],
                    "branch": task["branch"], "criteria_done": sum(c["done"] for c in task["criteria"]),
                    "criteria": len(task["criteria"]), "evidence": len(task["evidence"]),
                    "annotations": len(task["annotations"]), "waits_for": waits}

        def empty_box(thing: dict, level: str, parent: str) -> dict:
            """A plan or feature with nothing inside yet: a box (a frame would have nothing to wrap)."""
            return {"id": thing["item"], "kind": "task", "level": level, "label": thing["title"], "state": thing["state"],
                    "status": "", "parent": parent, "frame": False, "task_id": None, "open": thing["item"],
                    "due": thing["due"], "branch": thing.get("branch", ""), "criteria_done": 0, "criteria": 0,
                    "evidence": 0, "annotations": 0, "empty": True,
                    "waits_for": [dict(waited, title=owner[waited["item"]][1]["title"]) for waited in thing["depends_on"]]}

        nodes, drawn_as = [], {}  # drawn_as: item reference -> the node it is drawn in
        for plan in planner["plans"]:
            if plan_ids is not None and plan["id"] not in plan_ids:
                continue
            features = plan["features"]
            if not features:
                nodes.append(empty_box(plan, "plan", ""))
                drawn_as[plan["item"]] = plan["item"]
                continue
            merge_feature = len(features) == 1 and same(features[0], plan)
            for feature in features:
                if not feature["tasks"] and not merge_feature:
                    if not drawn_as.get(plan["item"]):
                        nodes.append({"id": plan["item"], "kind": "plan", "label": plan["title"], "state": plan["state"],
                                      "parent": "", "frame": True, "due": plan["due"], "goal": plan["goal"],
                                      "branches": plan["branches"]})
                        drawn_as[plan["item"]] = plan["item"]
                    nodes.append(empty_box(feature, "feature", plan["item"]))
                    drawn_as[feature["item"]] = feature["item"]
                    continue
                if not feature["tasks"]:  # the plan's only feature, of the same title, with no task yet
                    nodes.append(empty_box(plan, "plan", ""))
                    drawn_as.update({plan["item"]: plan["item"], feature["item"]: plan["item"]})
                    continue
                single_task = len(feature["tasks"]) == 1 and same(feature["tasks"][0], feature)
                if merge_feature and single_task:  # the whole plan is one task: one box
                    task = feature["tasks"][0]
                    nodes.append(task_box(task, plan, "plan", "", [task, feature, plan]))
                    drawn_as.update({plan["item"]: plan["item"], feature["item"]: plan["item"], task["item"]: plan["item"]})
                    continue
                if not drawn_as.get(plan["item"]):
                    nodes.append({"id": plan["item"], "kind": "plan", "label": plan["title"], "state": plan["state"],
                                  "parent": "", "frame": True, "due": plan["due"], "goal": plan["goal"], "branches": plan["branches"]})
                    drawn_as[plan["item"]] = plan["item"]
                frame = plan["item"] if merge_feature else feature["item"]
                drawn_as[feature["item"]] = frame
                if single_task:  # the feature is one task: its box, labeled as the feature
                    task = feature["tasks"][0]
                    nodes.append(task_box(task, feature, "feature", plan["item"], [task, feature]))
                    drawn_as[feature["item"]] = drawn_as[task["item"]] = feature["item"]
                    continue
                if not merge_feature:
                    nodes.append({"id": feature["item"], "kind": "feature", "label": feature["title"], "state": feature["state"],
                                  "parent": plan["item"], "frame": True, "due": feature["due"], "branch": feature["branch"],
                                  "description": feature["description"]})
                for task in feature["tasks"]:
                    nodes.append(task_box(task, task, "task", frame, [task]))
                    drawn_as[task["item"]] = task["item"]

        edges, seen = [], {}
        for dependency in planner["dependencies"]:
            ends = [drawn_as.get(end, end) for end in (dependency["depends_on"], dependency["item"])]
            if ends[0] == ends[1] or not any(end in drawn_as.values() for end in ends):
                continue
            for end in ends:
                if end not in drawn_as.values() and all(node["id"] != end for node in nodes):
                    plan, entry = owner[end]
                    nodes.append({"id": end, "kind": "external", "label": entry["title"], "state": entry["state"], "parent": "",
                                  "frame": False, "plan_id": plan["id"], "plan": plan["title"], "level": end.split(":")[0]})
            key = tuple(ends)
            if key in seen:  # several dependencies drawn between the same two nodes: one line, every reason
                seen[key]["reason"] += f"; {dependency['reason']}"
                continue
            seen[key] = {"id": f"{ends[0]}->{ends[1]}", "source": ends[0], "target": ends[1], "kind": "depends",
                         "reason": dependency["reason"]}
            edges.append(seen[key])
        return {"nodes": nodes, "edges": edges, "drawn_as": drawn_as}

    def get_plan(self, plan_id: int) -> dict:
        """Read a plan with its features and tasks, in order, and the worked-out states.

        Returns:
            `id`, `item` (`plan:<id>`), `title`, `goal`, `requirements`, `decisions`, `branches`, `due`,
            `state`, `depends_on` (`[{"item", "reason", "state"}]`), `source`, `created`, `updated` and
            `features`, each with its `tasks` (see `get_task`).

        Raises:
            ValueError: When there is no such plan.
        """
        self._exists("plan", plan_id)
        return next(plan for plan in self.planner(include_empty_reviews=True)["plans"] if plan["id"] == plan_id)

    def get_feature(self, feature_id: int) -> dict:
        """Read a feature with its tasks (see `get_plan`); it also has `plan_id` and `description`."""
        self._exists("feature", feature_id)
        return next(feature for plan in self.planner(include_empty_reviews=True)["plans"] for feature in plan["features"]
                    if feature["id"] == feature_id)

    def get_task(self, task_id: int) -> dict:
        """Read a task.

        Returns:
            `id`, `item`, `feature_id`, `title`, `criteria` (`[{"text", "done"}]`), `branch`, `due`,
            `status` (set by hand), `state` (worked out), `depends_on`, `annotations`, `evidence`,
            `source`, `created` and `updated`.
        """
        self._exists("task", task_id)
        return next(task for plan in self.planner(include_empty_reviews=True)["plans"] for feature in plan["features"]
                    for task in feature["tasks"] if task["id"] == task_id)

    def get_item(self, item: str) -> dict:
        """Read a plan, feature or task from its reference (`plan:1`, `feature:2`, `task:3`)."""
        kind, item_id = parse_item(item)
        return {"plan": self.get_plan, "feature": self.get_feature, "task": self.get_task}[kind](item_id)

    # --- Notes

    def create_note(self, type: str, statement: str, why: str = "", entities: list[str] | None = None,
                    source: str = "agent", moments: list[str] | None = None) -> dict:
        """Write down a piece of lasting knowledge.

        Args:
            type: One of `NOTE_TYPES`.
            statement: The knowledge itself, in one or two sentences.
            why: Why it holds (the reason behind a rule or decision, how a pitfall shows up).
            entities: Paths of the code entities it is about (classes, functions, modules...).
            source: `agent` or `wiki`.
            moments: Guidelines only: when it is given to the agent (`MOMENTS`); `always` by default.

        Returns:
            The note (see `get_note`).
        """
        _check(type, NOTE_TYPES, "note type")
        _check(source, SOURCES, "source")
        if not statement or not statement.strip():
            raise ValueError("A note needs a statement.")
        paths = self._entities(entities)
        stored_moments = _moments(type, moments)
        now = _now()
        with self._connect(write=True) as connection:
            note_id = connection.execute(
                "INSERT INTO notes (type, statement, why, moments, source, created, updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (type, statement.strip(), (why or "").strip(), stored_moments, source, now, now),
            ).lastrowid
            self._link_entities(connection, note_id, paths)
        return self.get_note(note_id)

    def update_note(self, note_id: int, statement: str | None = None, why: str | None = None,
                    entities: list[str] | None = None, moments: list[str] | None = None) -> dict:
        """Fix a note (a typo, a missing entity, when a guideline is given). To record that it no
        longer holds, use `supersede_note`.

        Returns:
            The note (see `get_note`).
        """
        changes = {}
        if moments is not None:
            changes["moments"] = _moments(self.get_note(note_id)["type"], moments)
        if statement is not None:
            if not statement.strip():
                raise ValueError("A note needs a statement.")
            changes["statement"] = statement.strip()
        if why is not None:
            changes["why"] = why.strip()
        paths = self._entities(entities) if entities is not None else None
        self._update("note", note_id, changes, force=paths is not None)
        if paths is not None:
            with self._connect(write=True) as connection:
                connection.execute("DELETE FROM links WHERE source = ? AND kind = 'about'", (f"note:{note_id}",))
                self._link_entities(connection, note_id, paths)
        return self.get_note(note_id)

    def supersede_note(self, note_id: int, statement: str, why: str = "", entities: list[str] | None = None,
                       type: str | None = None, source: str = "agent", moments: list[str] | None = None) -> dict:
        """Replace a note that no longer holds by a new one; the old one is kept, marked as superseded.

        The new note keeps the old one's entities, and its moments when both are guidelines, unless given.

        Returns:
            The new note (see `get_note`).
        """
        old = self.get_note(note_id)
        if old["status"] == "superseded":
            raise ValueError(f"Note {note_id} is already superseded by note {old['superseded_by']}.")
        new_type = type or old["type"]
        if moments is None and note_group(new_type) == old["group"] == "guidelines":
            moments = old["moments"]
        new = self.create_note(new_type, statement, why, old["entities"] if entities is None else entities, source,
                               moments)
        with self._connect(write=True) as connection:
            connection.execute("UPDATE notes SET status = 'superseded', updated = ? WHERE id = ?", (_now(), note_id))
            connection.execute("INSERT INTO links (source, target, kind) VALUES (?, ?, 'supersedes')",
                               (f"note:{new['id']}", f"note:{note_id}"))
        return self.get_note(new["id"])

    def delete_note(self, note_id: int) -> None:
        """Delete a note made by mistake (a note that stopped holding is superseded instead)."""
        with self._connect(write=True) as connection:
            if connection.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount == 0:
                raise ValueError(f"There is no note {note_id}.")
            connection.execute("DELETE FROM links WHERE source = ? OR target = ?", (f"note:{note_id}", f"note:{note_id}"))

    def get_note(self, note_id: int) -> dict:
        """Read a note.

        Returns:
            `id`, `type`, `group` (`guidelines` or `memory`), `statement`, `why`, `moments` (guidelines),
            `status` (`active` or `superseded`), `source`, `created`, `updated`, `entities`, `supersedes`
            and `superseded_by`.

        Raises:
            ValueError: When there is no such note.
        """
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
            if row is None:
                raise ValueError(f"There is no note {note_id}.")
            return self._note(connection, row)

    def list_notes(self, group: str = "", type: str = "", status: str = "active", entity: str = "",
                   moment: str = "") -> list[dict]:
        """List notes, newest first.

        Args:
            group: `guidelines` (preferences and rules) or `memory` (decisions, context, pitfalls,
                references); empty for both.
            type: Only this type; empty for every type of the group.
            status: `active`, `superseded`, or empty for both.
            entity: Only notes about this entity path; empty for every note.
            moment: Only the guidelines given at this moment (`MOMENTS`); empty for every note.

        Returns:
            The notes (see `get_note`).
        """
        if group:
            _check(group, NOTE_GROUPS, "note group")
        if type:
            _check(type, NOTE_TYPES, "note type")
        types = [type] if type else list(NOTE_GROUPS[group]) if group else list(NOTE_TYPES)
        conditions, values = [f"type IN ({', '.join('?' * len(types))})"], list(types)
        if status:
            conditions.append("status = ?")
            values.append(status)
        if entity:
            conditions.append("'note:' || id IN (SELECT source FROM links WHERE kind = 'about' AND target = ?)")
            values.append(entity)
        if moment:
            _check(moment, MOMENTS, "moment")
            conditions.append("EXISTS (SELECT 1 FROM json_each(moments) WHERE value = ?)")
            values.append(moment)
        query = f"SELECT * FROM notes WHERE {' AND '.join(conditions)} ORDER BY id DESC"
        with self._connect() as connection:
            return [self._note(connection, row) for row in connection.execute(query, values)]

    # --- Commits

    def record_commit(self, commit_hash: str, tasks: list[str]) -> None:
        """Remember a commit made by the commit flow, with the tasks it carries out.

        Args:
            commit_hash: Full hash.
            tasks: References of its tasks (`task:<id>`).
        """
        with self._connect(write=True) as connection:
            connection.execute("INSERT OR REPLACE INTO commits (hash, tasks, created) VALUES (?, ?, ?)",
                               (commit_hash, json.dumps(tasks), _now()))

    def made_by_flow(self, commit_hash: str) -> bool:
        """Whether a commit was made by the commit flow (and so needs no review)."""
        with self._connect() as connection:
            return connection.execute("SELECT 1 FROM commits WHERE hash = ?", (commit_hash,)).fetchone() is not None

    def open_commits(self) -> list[dict]:
        """The commits of the flow the post-commit has not closed yet: `hash` and `tasks`, oldest first."""
        with self._connect() as connection:
            return [{"hash": row["hash"], "tasks": json.loads(row["tasks"])} for row in connection.execute(
                "SELECT hash, tasks FROM commits WHERE closed = 0 ORDER BY created")]

    def close_commit(self, commit_hash: str) -> None:
        """Mark a commit of the flow as handled by the post-commit."""
        with self._connect(write=True) as connection:
            connection.execute("UPDATE commits SET closed = 1 WHERE hash = ?", (commit_hash,))

    def get_meta(self, key: str) -> str:
        """A value of the sync marker (`last_commit`, `last_check`); empty when not set."""
        with self._connect() as connection:
            row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else ""

    def set_meta(self, key: str, value: str) -> None:
        """Set a value of the sync marker."""
        with self._connect() as connection, connection:
            connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))

    def archive_item(self, item: str) -> None:
        """Keep a plan, feature or task, with everything inside it, in the archive before it is deleted.

        Each task keeps its criteria, annotations, evidence and the commits recorded with it; a
        feature or plan keeps its own fields.

        Args:
            item: `plan:<id>`, `feature:<id>` or `task:<id>`.
        """
        kind, _ = parse_item(item)
        found = self.get_item(item)
        if kind == "plan":
            plan, features = found, found["features"]
        elif kind == "feature":
            plan, features = self.get_plan(found["plan_id"]), [found]
        else:
            feature = self.get_feature(found["feature_id"])
            plan, features = self.get_plan(feature["plan_id"]), [{**feature, "tasks": [found]}]
        rows = []
        if kind == "plan":
            rows.append((plan["item"], "plan", plan["title"], plan["title"], "",
                         {"goal": plan["goal"], "requirements": plan["requirements"], "decisions": plan["decisions"]}, []))
        for feature in features:
            if kind != "task":
                rows.append((feature["item"], "feature", feature["title"], plan["title"], "",
                             {"description": feature["description"]}, []))
            for task in feature["tasks"]:
                rows.append((task["item"], "task", task["title"], plan["title"], feature["title"],
                             {"criteria": task["criteria"], "annotations": [a["text"] for a in task["annotations"]],
                              "evidence": [e["detail"] for e in task["evidence"]]}, self._commits_of(task["item"])))
        now = _now()
        with self._connect(write=True) as connection:
            connection.executemany(
                "INSERT INTO archive (item, kind, title, plan, feature, content, commits, archived) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(ref, row_kind, title, plan_title, feature_title, json.dumps(content), json.dumps(commits), now)
                 for ref, row_kind, title, plan_title, feature_title, content, commits in rows])

    def _commits_of(self, task: str) -> list[str]:
        """Full hashes of the flow's commits that carried out a task."""
        with self._connect() as connection:
            return [row["hash"] for row in connection.execute(
                "SELECT hash FROM commits WHERE EXISTS (SELECT 1 FROM json_each(tasks) WHERE value = ?) ORDER BY created",
                (task,))]

    def archived(self, commit_hash: str = "") -> list[dict]:
        """Archived planner items, oldest first.

        Args:
            commit_hash: Only the tasks carried out by this commit (full or abbreviated hash); empty for all.

        Returns:
            `id`, `item`, `kind`, `title`, `plan`, `feature`, `archived`, `commits` and what they held
            (`criteria`, `annotations`, `evidence` for a task; the own fields of a plan or feature).
        """
        query, values = "SELECT * FROM archive", []
        if commit_hash:
            query += " WHERE EXISTS (SELECT 1 FROM json_each(commits) WHERE value LIKE ? || '%')"
            values.append(commit_hash.strip().lower())
        with self._connect() as connection:
            return [{**{key: row[key] for key in row.keys() if key not in ("content", "commits")},
                     "commits": json.loads(row["commits"]), **json.loads(row["content"])}
                    for row in connection.execute(query + " ORDER BY id", values)]

    def add_review(self, title: str, detail: str) -> dict:
        """Add a task to the Reviews plan, with its evidence (a commit made outside the flow).

        The task goes to the Reviews feature; it is made again if it was deleted.

        Args:
            title: The task, e.g. `Review commit abc1234: Fix the parser`.
            detail: What the commit says and touches, kept as evidence (source `diff`).

        Returns:
            The task.
        """
        with self._connect() as connection, connection:
            plan_id = connection.execute("SELECT id FROM plans WHERE fixed = 1").fetchone()["id"]
            feature = connection.execute("SELECT id FROM features WHERE plan_id = ? AND title = ?",
                                         (plan_id, REVIEWS["feature"])).fetchone()
            if feature is None:
                now = _now()
                feature_id = connection.execute(
                    "INSERT INTO features (plan_id, title, position, source, created, updated) "
                    "VALUES (?, ?, 0, 'agent', ?, ?)", (plan_id, REVIEWS["feature"], now, now)).lastrowid
            else:
                feature_id = feature["id"]
        task = self.add_task(feature_id, title, ["Planning and memory checked against the commit"])
        return self.add_evidence(task["id"], "diff", detail)

    # --- Search

    def searchable(self) -> dict[str, dict]:
        """Every planner item, active note and archived item as a search document.

        Returns:
            By reference (`plan:<id>`, `note:<id>`, `archive:<id>`...): `group` (`planning`, `guidelines`,
            `memory` or `history`, the archived work),
            `kind` (plan, feature, task or the note type), `title`, `state` and `plan` (the plan's id;
            planner items only) and `text`, the words the search compares.
        """
        documents = {}
        for plan in self.planner()["plans"]:
            in_plan = {"plan": plan["id"]}
            documents[plan["item"]] = _document("planning", "plan", plan["title"], plan["state"], in_plan,
                                                plan["goal"], *plan["requirements"], *plan["decisions"])
            for feature in plan["features"]:
                documents[feature["item"]] = _document("planning", "feature", feature["title"], feature["state"],
                                                       in_plan, feature["description"])
                for task in feature["tasks"]:
                    documents[task["item"]] = _document("planning", "task", task["title"], task["state"], in_plan,
                                                        *(criterion["text"] for criterion in task["criteria"]))
        for note in self.list_notes():
            documents[f"note:{note['id']}"] = _document(note["group"], note["type"], note["statement"], "", {},
                                                        note["why"], *note["entities"])
        for entry in self.archived():
            documents[f"archive:{entry['id']}"] = _document(
                "history", entry["kind"], entry["title"], "", {"commits": entry["commits"], "plan": entry["plan"]},
                *(c["text"] for c in entry.get("criteria", [])), *entry.get("annotations", []), *entry.get("evidence", []),
                entry.get("goal", ""), entry.get("description", ""))
        return documents

    # --- Helpers

    def _exists(self, kind: str, item_id: int) -> None:
        """Refuse a plan, feature or task that does not exist."""
        with self._connect() as connection:
            if connection.execute(f"SELECT 1 FROM {KINDS[kind]} WHERE id = ?", (item_id,)).fetchone() is None:
                raise ValueError(f"There is no {kind} {item_id}.")

    def _update(self, kind: str, row_id: int, changes: dict, force: bool = False) -> None:
        """Change some columns of one plan, feature, task or note, and its `updated` time."""
        if not changes and not force:
            return
        table = {**KINDS, "note": "notes"}[kind]
        changes = {**changes, "updated": _now()}
        assignments = ", ".join(f"{column} = ?" for column in changes)
        with self._connect(write=True) as connection:
            if connection.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", (*changes.values(), row_id)).rowcount == 0:
                raise ValueError(f"There is no {kind} {row_id}.")

    def _entities(self, entities: list[str] | None) -> list[str]:
        """Check that every entity path exists in the code.

        Raises:
            ValueError: Naming the paths that do not exist.
        """
        paths = list(dict.fromkeys(path.strip() for path in entities or [] if path and path.strip()))
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
        """A plan row as a dict, with its lists decoded."""
        plan = dict(row)
        for name in ("requirements", "decisions", "branches"):
            plan[name] = json.loads(plan[name])
        plan["fixed"] = bool(plan["fixed"])
        return plan

    @staticmethod
    def _task_row(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
        """A task row as a dict, with its criteria, annotations and evidence."""
        task = dict(row)
        task["criteria"] = json.loads(task["criteria"])
        task["annotations"] = [dict(item) for item in connection.execute(
            "SELECT id, text, source, created FROM annotations WHERE task_id = ? ORDER BY id", (task["id"],))]
        task["evidence"] = [dict(item) for item in connection.execute(
            "SELECT id, source, detail, created FROM evidence WHERE task_id = ? ORDER BY id", (task["id"],))]
        return task

    @staticmethod
    def _note(connection: sqlite3.Connection, row: sqlite3.Row) -> dict:
        """A note row as a dict, with its group, entities and what it supersedes or is superseded by."""
        note = dict(row)
        note["group"] = note_group(note["type"])
        note["moments"] = json.loads(note["moments"])
        key = f"note:{note['id']}"
        note["entities"] = [target for (target,) in connection.execute(
            "SELECT target FROM links WHERE source = ? AND kind = 'about' ORDER BY target", (key,))]
        supersedes = connection.execute("SELECT target FROM links WHERE source = ? AND kind = 'supersedes'", (key,)).fetchone()
        superseded_by = connection.execute("SELECT source FROM links WHERE target = ? AND kind = 'supersedes'", (key,)).fetchone()
        note["supersedes"] = int(supersedes[0].removeprefix("note:")) if supersedes else None
        note["superseded_by"] = int(superseded_by[0].removeprefix("note:")) if superseded_by else None
        return note


def _add_columns(connection: sqlite3.Connection) -> None:
    """Bring an older database up to date: add the `ADDED_COLUMNS` it lacks.

    Guidelines written before `moments` existed are given `always`.
    """
    for table, column, definition in ADDED_COLUMNS:
        if column not in {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}:
            with connection:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
                if column == "moments":
                    guidelines = NOTE_GROUPS["guidelines"]
                    connection.execute(f"UPDATE notes SET moments = '[\"always\"]' WHERE type IN "
                                       f"({', '.join('?' * len(guidelines))})", guidelines)


def _moments(type: str, moments: list[str] | None) -> str:
    """Check when a note is given and store it as JSON: guidelines get `always` by default, memory none.

    Raises:
        ValueError: For an unknown moment, or moments given to a memory note.
    """
    if note_group(type) == "memory":
        if moments:
            raise ValueError("Only guidelines (preferences and rules) have moments; memory notes are found by search.")
        return "[]"
    chosen = ["always"] if moments is None else list(dict.fromkeys(moment.strip() for moment in moments if moment.strip()))
    for moment in chosen:
        _check(moment, MOMENTS, "moment")
    return json.dumps(chosen)


def document_text(kind: str, title: str, *details: str) -> str:
    """The words the search compares for a planner item or a note: its kind, title and details."""
    return "\n".join([f"{kind} {title}", *(detail for detail in details if detail)])


def note_group(type: str) -> str:
    """The group of a note type: `guidelines` or `memory`.

    Raises:
        ValueError: When `type` is not one of `NOTE_TYPES`.
    """
    _check(type, NOTE_TYPES, "note type")
    return next(group for group, types in NOTE_GROUPS.items() if type in types)


def _document(group: str, kind: str, title: str, state: str, extra: dict, *details: str) -> dict:
    """A search document of `NoteStore.searchable`."""
    return {"group": group, "kind": kind, "title": title, "state": state, **extra,
            "text": document_text(kind, title, *details)}


def _items_of(plan: dict) -> list[str]:
    """A plan's reference and those of its features and tasks."""
    return [plan["item"], *(feature["item"] for feature in plan["features"]),
            *(task["item"] for feature in plan["features"] for task in feature["tasks"])]


def _work_out_states(plans: list[dict], features: list[dict], tasks: list[dict], dependencies: list[dict], today: str) -> None:
    """Nest features in plans and tasks in features, and give every item its `state` and `depends_on`.

    First pass, every level: a task is done by its status; a feature or plan is done when everything
    inside is done, doing when something inside started. An item not done is late when its due date
    passed or something inside is late. Second pass, from tasks up: an item still todo or doing is
    blocked when something it or one of its parents depends on is not done (what waits, waits with
    everything inside it), or when everything left inside it is blocked.
    """
    for plan in plans:
        plan["item"], plan["features"] = f"plan:{plan['id']}", []
    by_plan = {plan["id"]: plan for plan in plans}
    by_feature = {}
    for feature in features:
        feature["item"], feature["tasks"] = f"feature:{feature['id']}", []
        feature.pop("position")
        by_plan[feature["plan_id"]]["features"].append(feature)
        by_feature[feature["id"]] = feature
    for task in tasks:
        task["item"] = f"task:{task['id']}"
        task.pop("position")
        by_feature[task["feature_id"]]["tasks"].append(task)

    def own_late(item: dict) -> bool:
        return bool(item["due"]) and item["due"] < today

    for task in tasks:
        task["state"] = "done" if task["status"] == "done" else "late" if own_late(task) else task["status"]
    for level in ([(feature, feature["tasks"]) for feature in features], [(plan, plan["features"]) for plan in plans]):
        for item, children in level:
            states = [child["state"] for child in children]
            if states and all(state == "done" for state in states):
                item["state"] = "done"
            elif own_late(item) or "late" in states:
                item["state"] = "late"
            elif any(state in ("doing", "done") for state in states):
                item["state"] = "doing"
            else:
                item["state"] = "todo"

    items = {item["item"]: item for item in [*plans, *features, *tasks]}
    for item in items.values():
        item["depends_on"] = [{"item": dependency["depends_on"], "reason": dependency["reason"],
                               "state": items[dependency["depends_on"]]["state"]}
                              for dependency in dependencies if dependency["item"] == item["item"]]
    # An item waits when one of its own dependencies, or one of its parents', is not done.
    def waits(item: dict) -> bool:
        return any(dependency["state"] != "done" for dependency in item["depends_on"])

    parent = {feature["item"]: by_plan[feature["plan_id"]] for feature in features}
    parent.update({task["item"]: by_feature[task["feature_id"]] for task in tasks})

    def waiting(item: dict) -> bool:
        while item is not None:
            if waits(item):
                return True
            item = parent.get(item["item"])
        return False

    for level in ([(task, []) for task in tasks], [(feature, feature["tasks"]) for feature in features],
                  [(plan, plan["features"]) for plan in plans]):
        for item, children in level:
            if item["state"] not in ("todo", "doing"):
                continue
            left = [child["state"] for child in children if child["state"] != "done"]
            if waiting(item) or (left and all(state == "blocked" for state in left)):
                item["state"] = "blocked"
