"""MCP tools for the plans, tasks and notes: thin wrappers over `NoteStore`, the same methods the wiki uses."""

import functools
from collections.abc import Callable

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from doctracker.notes import NOTE_TYPES, NoteStore

TYPES_HELP = "; ".join(f"`{name}`: {text}" for name, text in NOTE_TYPES.items())
"""The note types and what each is for, shown in the tool descriptions."""



def refusals_reported(tool: Callable) -> Callable:
    """Pass the store's refusals (unknown type, missing title...) to the agent as tool errors.

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
    """Add the tools that read and change plans, tasks and notes.

    Every change made here is recorded with the source `agent`.

    Args:
        mcp: Server to register the tools on.
        notes: Store of the plans, tasks and notes (the same one the wiki uses).
    """

    @mcp.tool()
    @refusals_reported
    def work_context() -> dict:
        """Get the work in progress: the active plans, each with its tasks, their annotations and evidence.

        Call it when a session starts or after the conversation was summarized, before working.

        Returns:
            `plans`, newest first.
        """
        return {"plans": notes.list_plans("active")}

    @mcp.tool()
    @refusals_reported
    def create_plan(title: str, goal: str = "", requirements: list[str] | None = None,
                    decisions: list[str] | None = None, branches: list[str] | None = None) -> dict:
        """Start a plan for a piece of work. A small plan is one branch; a large one is split into tasks.

        Args:
            title: Short name of the work.
            goal: What the work is for.
            requirements: What the result must do or respect, one per item.
            decisions: Decisions already taken with the user, with why, one per item.
            branches: Git branches of the plan, if any.

        Returns:
            The plan.
        """
        return notes.create_plan(title, goal, requirements, decisions, branches)

    @mcp.tool()
    @refusals_reported
    def update_plan(plan_id: int, title: str | None = None, goal: str | None = None,
                    requirements: list[str] | None = None, decisions: list[str] | None = None,
                    branches: list[str] | None = None, status: str | None = None) -> dict:
        """Change a plan. Only the fields given change; a list given replaces the stored one.

        Args:
            plan_id: The plan.
            title: New title.
            goal: New goal.
            requirements: New list of requirements.
            decisions: New list of decisions.
            branches: New list of branches.
            status: `active` or `done`.

        Returns:
            The plan.
        """
        return notes.update_plan(plan_id, title, goal, requirements, decisions, branches, status)

    @mcp.tool()
    @refusals_reported
    def delete_plan(plan_id: int) -> dict:
        """Delete a plan made by mistake, with its tasks. A finished plan is set to `done` instead.

        Args:
            plan_id: The plan.

        Returns:
            `deleted`: the plan id.
        """
        notes.delete_plan(plan_id)
        return {"deleted": plan_id}

    @mcp.tool()
    @refusals_reported
    def add_task(plan_id: int, title: str, criteria: list[str] | None = None, branch: str = "") -> dict:
        """Add a task at the end of a plan.

        Args:
            plan_id: The plan.
            title: What has to be done.
            criteria: What "done" means for it, one per item.
            branch: Its own git branch, when the plan is split into branches per task.

        Returns:
            The task.
        """
        return notes.add_task(plan_id, title, criteria, branch)

    @mcp.tool()
    @refusals_reported
    def update_task(task_id: int, title: str | None = None, criteria: list[str] | None = None,
                    branch: str | None = None, status: str | None = None) -> dict:
        """Change a task. Only the fields given change.

        Args:
            task_id: The task.
            title: New title.
            criteria: New list of criteria.
            branch: New branch (empty for none).
            status: `todo`, `doing` or `done`.

        Returns:
            The task.
        """
        return notes.update_task(task_id, title, criteria, branch, status)

    @mcp.tool()
    @refusals_reported
    def delete_task(task_id: int) -> dict:
        """Delete a task made by mistake, with its annotations and evidence.

        Args:
            task_id: The task.

        Returns:
            `deleted`: the task id.
        """
        notes.delete_task(task_id)
        return {"deleted": task_id}

    @mcp.tool()
    @refusals_reported
    def annotate_task(task_id: int, text: str) -> dict:
        """Write down on a task what was done, decided or found while working on it.

        Write it here, not in files, memories or code comments: it stays with the task until the commit.

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

    @mcp.tool(description=f"""Write down a piece of lasting knowledge of the project, as one short fact.

Use it instead of writing notes in files, memories or code comments. Types: {TYPES_HELP}.
If a note on the same subject exists and no longer holds, use supersede_note; to fix it, use update_note.

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

    @mcp.tool()
    @refusals_reported
    def list_notes(type: str = "", status: str = "active", entity: str = "") -> dict:
        """List the notes, newest first.

        Args:
            type: Only this type (see create_note); empty for every type.
            status: `active`, `superseded`, or empty for both.
            entity: Only notes about this entity path; empty for every note.

        Returns:
            `notes`.
        """
        return {"notes": notes.list_notes(type, status, entity)}
