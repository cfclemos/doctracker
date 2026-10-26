"""MCP tools for the planner and the notes: thin wrappers over `NoteStore`, the same methods the wiki uses."""

import functools
from collections.abc import Callable

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from doctracker.notes import NOTE_GROUPS, NOTE_TYPES, NoteStore

TYPES_HELP = "; ".join(f"`{name}`: {text}" for name, text in NOTE_TYPES.items())
"""The note types and what each is for, shown in the tool descriptions."""

GROUPS_HELP = "; ".join(f"`{group}`: {', '.join(types)}" for group, types in NOTE_GROUPS.items())
"""The note groups and their types, shown in the tool descriptions."""


def refusals_reported(tool: Callable) -> Callable:
    """Pass the store's refusals (unknown type, missing title, a cycle...) to the agent as tool errors.

    Without it, the MCP SDK hides an exception's text and the agent only sees that the tool failed.
    """

    @functools.wraps(tool)
    def run(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except ValueError as refused:
            raise ToolError(str(refused)) from refused

    return run


def register_note_tools(mcp: MCPServer, notes: NoteStore) -> None:
    """Add the tools that read and change the planner (plans, features, tasks) and the notes.

    Every change made here is recorded with the source `agent`.

    Args:
        mcp: Server to register the tools on.
        notes: Store of the plans and notes (the same one the wiki uses).
    """

    @mcp.tool()
    @refusals_reported
    def work_context() -> dict:
        """Get the work in progress: the plans not done yet, with their features, tasks and dependencies.

        Call it when a session starts or after the conversation was summarized, before working.
        Every item has a worked-out `state`: todo, doing, blocked (waits for something not done),
        late (past its due date) or done.

        Returns:
            `plans` and `dependencies`.
        """
        return notes.planner(include_done=False)

    @mcp.tool()
    @refusals_reported
    def create_plan(title: str, goal: str = "", requirements: list[str] | None = None,
                    decisions: list[str] | None = None, branches: list[str] | None = None, due: str = "",
                    features: list[dict] | None = None) -> dict:
        """Create a plan with its features and tasks in one call.

        A plan is made of features, a feature of tasks. For a simple piece of work give only the title:
        the plan gets one feature with one task of the same title. A feature given without tasks gets
        one task with its title.

        Args:
            title: Short name of the work.
            goal: What the work is for.
            requirements: What the result must do or respect, one per item.
            decisions: Decisions already taken with the user, with why, one per item.
            branches: Git branches of the plan, if any.
            due: Due date, YYYY-MM-DD.
            features: `[{"title", "description", "branch", "due", "tasks": [{"title", "criteria": [...], "branch", "due"}]}]`.

        Returns:
            The plan, with its features and tasks.
        """
        return notes.create_plan(title, goal, requirements, decisions, branches, due, features)

    @mcp.tool()
    @refusals_reported
    def add_feature(plan_id: int, title: str, description: str = "", branch: str = "", due: str = "",
                    tasks: list[dict] | None = None) -> dict:
        """Add a feature, with its tasks, to a plan. Without tasks it gets one task with its title.

        Args:
            plan_id: The plan.
            title: What the feature delivers.
            description: More about it.
            branch: Its git branch, if it has one of its own.
            due: Due date, YYYY-MM-DD.
            tasks: `[{"title", "criteria": [...], "branch", "due"}]`.

        Returns:
            The feature, with its tasks.
        """
        return notes.add_feature(plan_id, title, description, branch, due, tasks)

    @mcp.tool()
    @refusals_reported
    def add_task(feature_id: int, title: str, criteria: list[str] | None = None, branch: str = "", due: str = "") -> dict:
        """Add a task to a feature.

        Args:
            feature_id: The feature.
            title: What has to be done.
            criteria: What "done" means for it, one per item.
            branch: Its own git branch, if any.
            due: Due date, YYYY-MM-DD.

        Returns:
            The task.
        """
        return notes.add_task(feature_id, title, criteria, branch, due)

    @mcp.tool()
    @refusals_reported
    def update_plan(plan_id: int, title: str | None = None, goal: str | None = None,
                    requirements: list[str] | None = None, decisions: list[str] | None = None,
                    branches: list[str] | None = None, due: str | None = None) -> dict:
        """Change a plan. Only the fields given change; a list given replaces the stored one.

        A plan is done when all its features are; there is no status to set.

        Args:
            plan_id: The plan.
            title: New title.
            goal: New goal.
            requirements: New list of requirements.
            decisions: New list of decisions.
            branches: New list of branches.
            due: New due date, YYYY-MM-DD (empty for none).

        Returns:
            The plan.
        """
        return notes.update_plan(plan_id, title, goal, requirements, decisions, branches, due)

    @mcp.tool()
    @refusals_reported
    def update_feature(feature_id: int, title: str | None = None, description: str | None = None,
                       branch: str | None = None, due: str | None = None) -> dict:
        """Change a feature. Only the fields given change. A feature is done when all its tasks are.

        Args:
            feature_id: The feature.
            title: New title.
            description: New description.
            branch: New branch (empty for none).
            due: New due date, YYYY-MM-DD (empty for none).

        Returns:
            The feature.
        """
        return notes.update_feature(feature_id, title, description, branch, due)

    @mcp.tool()
    @refusals_reported
    def update_task(task_id: int, title: str | None = None, criteria: list[str] | None = None,
                    branch: str | None = None, due: str | None = None, status: str | None = None) -> dict:
        """Change a task. Only the fields given change.

        Args:
            task_id: The task.
            title: New title.
            criteria: New list of criteria (all start unchecked).
            branch: New branch (empty for none).
            due: New due date, YYYY-MM-DD (empty for none).
            status: `todo`, `doing` or `done`.

        Returns:
            The task.
        """
        return notes.update_task(task_id, title, criteria, branch, due, status)

    @mcp.tool()
    @refusals_reported
    def check_criterion(task_id: int, index: int, done: bool = True) -> dict:
        """Tick (or untick) one criterion of a task once it is met.

        Args:
            task_id: The task.
            index: Position of the criterion, from 0.
            done: Whether it is met.

        Returns:
            The task.
        """
        return notes.check_criterion(task_id, index, done)

    @mcp.tool()
    @refusals_reported
    def annotate_task(task_id: int, text: str) -> dict:
        """Write down on a task what was done, decided or found while working on it.

        Write it here, not in files, memories or code comments: it stays with the task.

        Args:
            task_id: The task.
            text: The annotation.

        Returns:
            The task.
        """
        return notes.annotate_task(task_id, text)

    @mcp.tool()
    @refusals_reported
    def add_task_evidence(task_id: int, detail: str, source: str = "agent") -> dict:
        """Record evidence that a task is done.

        Args:
            task_id: The task.
            detail: What shows it is done.
            source: `agent` (your own account of it) or `diff` (the changed code shows it).

        Returns:
            The task.
        """
        if source not in ("agent", "diff"):
            raise ToolError("Use the source `agent` or `diff`; `wiki` evidence comes from the user in the wiki.")
        return notes.add_evidence(task_id, source, detail)

    @mcp.tool()
    @refusals_reported
    def update_task_evidence(evidence_id: int, detail: str) -> dict:
        """Change what a piece of evidence of a task says.

        Args:
            evidence_id: The evidence (its `id` in the task's `evidence`).
            detail: What shows the task is done.

        Returns:
            The task.
        """
        return notes.update_evidence(evidence_id, detail)

    @mcp.tool()
    @refusals_reported
    def delete_task_evidence(evidence_id: int) -> dict:
        """Delete a piece of evidence of a task that does not hold.

        Args:
            evidence_id: The evidence (its `id` in the task's `evidence`).

        Returns:
            The task.
        """
        return notes.delete_evidence(evidence_id)

    @mcp.tool()
    @refusals_reported
    def update_task_annotation(annotation_id: int, text: str) -> dict:
        """Change what an annotation of a task says.

        Args:
            annotation_id: The annotation (its `id` in the task's `annotations`).
            text: The new text.

        Returns:
            The task.
        """
        return notes.update_annotation(annotation_id, text)

    @mcp.tool()
    @refusals_reported
    def delete_task_annotation(annotation_id: int) -> dict:
        """Delete an annotation of a task.

        Args:
            annotation_id: The annotation (its `id` in the task's `annotations`).

        Returns:
            The task.
        """
        return notes.delete_annotation(annotation_id)

    @mcp.tool()
    @refusals_reported
    def add_dependency(item: str, depends_on: list[str], reason: str) -> dict:
        """Record that a planner item waits for one or more others, and why. Any kinds: plans, features, tasks.

        Refused, with nothing recorded, when any of them would make a cycle, counting that a plan waits
        for its features and a feature for its tasks.

        Args:
            item: The item that waits: `plan:<id>`, `feature:<id>` or `task:<id>`.
            depends_on: What it waits for, written the same way, one or more.
            reason: Why it waits for them; shown on the lines in the planner.

        Returns:
            The item that waits.
        """
        return notes.add_dependency(item, depends_on, reason)

    @mcp.tool()
    @refusals_reported
    def remove_dependency(item: str, depends_on: str) -> dict:
        """Remove a dependency between two planner items.

        Args:
            item: The item that waits.
            depends_on: What it waited for.

        Returns:
            The item.
        """
        return notes.remove_dependency(item, depends_on)

    @mcp.tool()
    @refusals_reported
    def delete_item(item: str) -> dict:
        """Delete a plan, feature or task made by mistake, with everything inside it and its dependencies.

        Args:
            item: `plan:<id>`, `feature:<id>` or `task:<id>`.

        Returns:
            `deleted`: the item.
        """
        notes.delete_item(item)
        return {"deleted": item}

    @mcp.tool(description=f"""Write down a piece of lasting knowledge of the project, as one short fact.

Use it instead of writing notes in files, memories or code comments. Types: {TYPES_HELP}.
Groups: {GROUPS_HELP}. If a note on the same subject exists and no longer holds, use
supersede_note; to fix it, use update_note.

Args:
    type: One of the types above.
    statement: The knowledge itself, in one or two sentences.
    why: Why it holds (the reason behind a rule or decision, how a pitfall shows up).
    entities: Full paths of the code entities it is about (e.g. `pkg.module.Class`).

Returns:
    The note.""")
    @refusals_reported
    def create_note(type: str, statement: str, why: str = "", entities: list[str] | None = None) -> dict:
        return notes.create_note(type, statement, why, entities)

    @mcp.tool()
    @refusals_reported
    def update_note(note_id: int, statement: str | None = None, why: str | None = None,
                    entities: list[str] | None = None) -> dict:
        """Fix a note (wording, a missing entity). When it no longer holds, use supersede_note instead.

        Args:
            note_id: The note.
            statement: New statement.
            why: New reason.
            entities: New list of entity paths.

        Returns:
            The note.
        """
        return notes.update_note(note_id, statement, why, entities)

    @mcp.tool()
    @refusals_reported
    def supersede_note(note_id: int, statement: str, why: str = "", entities: list[str] | None = None,
                       type: str | None = None) -> dict:
        """Replace a note that no longer holds by a new one; the old one is kept as superseded.

        Args:
            note_id: The note that no longer holds.
            statement: What holds now.
            why: Why it changed.
            entities: Entities of the new note; by default, those of the old one.
            type: Type of the new note; by default, that of the old one.

        Returns:
            The new note.
        """
        return notes.supersede_note(note_id, statement, why, entities, type)

    @mcp.tool()
    @refusals_reported
    def delete_note(note_id: int) -> dict:
        """Delete a note made by mistake. A note that stopped holding is superseded, not deleted.

        Args:
            note_id: The note.

        Returns:
            `deleted`: the note id.
        """
        notes.delete_note(note_id)
        return {"deleted": note_id}

    @mcp.tool(description=f"""List the notes, newest first.

Groups: {GROUPS_HELP}.

Args:
    group: `guidelines` or `memory`; empty for both.
    type: Only this type; empty for every type of the group.
    status: `active`, `superseded`, or empty for both.
    entity: Only notes about this entity path; empty for every note.

Returns:
    `notes`.""")
    @refusals_reported
    def list_notes(group: str = "", type: str = "", status: str = "active", entity: str = "") -> dict:
        return {"notes": notes.list_notes(group, type, status, entity)}
