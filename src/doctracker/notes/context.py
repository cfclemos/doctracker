"""What doctracker tells an agent at each moment of its work, as short texts.

The hooks of the agent (session start, plan mode, reading or editing a file, commit) put these
texts in the agent's context; the MCP tool `agent_context` gives the same texts on request.
Everything is generated from the store, so the texts follow what is recorded.
"""

from pathlib import Path

from doctracker.notes.store import NoteStore

CONTEXT_LIMIT = 8000
"""Longest context text, in characters: Claude Code saves longer hook texts to a file (10,000)."""

CONTEXT_KINDS = ("session", "planning", "file", "commit")
"""The moments a context is made for."""

RULE = (
    "This project keeps its plans, guidelines and memory in doctracker (MCP server \"doctracker\"). "
    "Record notes, decisions and progress there (create_note, annotate_task, update_task), not in files "
    "or local memory. Before planning, changing code or writing a note, call recall(query)."
)
"""The first lines of every session: where everything is kept and how to find it."""

NO_TASK_IN_PROGRESS = "No task is in progress: set one to doing (update_task) before changing planned code."
"""Said with the notes of a file while no task is being worked on."""

MORE = "(more in work_context)"
"""Ends the open planning when it was cut to fit `CONTEXT_LIMIT`."""


def context_for(kind: str, notes: NoteStore, entities: dict[str, dict], project_root: Path, path: str = "") -> str:
    """The context of one moment: the single entry used by the MCP tool and the hook routes.

    Args:
        kind: One of `CONTEXT_KINDS`.
        notes: The store.
        entities: The extracted entities, by path.
        project_root: Root of the project, to make a file path relative.
        path: For `file`: the file, absolute or relative to the project root.

    Returns:
        The text (possibly empty).

    Raises:
        ValueError: For an unknown kind, or `file` without a path.
    """
    if kind == "session":
        return session_context(notes)
    if kind == "planning":
        return planning_context(notes)
    if kind == "commit":
        return commit_context(notes)
    if kind == "file":
        if not path:
            raise ValueError("The file context needs the path of the file.")
        return file_context(notes, entities, project_path(project_root, path))
    raise ValueError(f"Unknown context {kind!r}; use one of: {', '.join(CONTEXT_KINDS)}.")


def project_path(project_root: Path, path: str) -> str:
    """A file path relative to the project root with forward slashes, as the entities' `filepath`.

    Args:
        project_root: Root of the project.
        path: Absolute or relative path of a file.

    Returns:
        The relative path; the path as given (with forward slashes) when it is outside the project.
    """
    file = Path(path)
    if file.is_absolute():
        try:
            file = file.resolve().relative_to(project_root.resolve())
        except ValueError:
            pass
    return file.as_posix()


def session_context(notes: NoteStore) -> str:
    """The context of a new session (also after a summary, and for a subagent).

    The rule, the guidelines given always, the open planning (titles, states and references) and the
    reviews waiting. When it does not fit `CONTEXT_LIMIT`, the planning is cut, not the guidelines.

    Args:
        notes: The store.

    Returns:
        The text.
    """
    head = [RULE, *_guidelines(notes, "always", "Guidelines:")]
    plans = notes.planner(include_done=False)["plans"]
    reviews = [task for plan in plans if plan["fixed"] for feature in plan["features"] for task in feature["tasks"]
               if task["state"] != "done"]
    tail = ([f"Reviews: {len(reviews)} commit(s) made outside the flow wait for review "
             f"({', '.join(task['item'] for task in reviews)})."] if reviews else [])
    planning = []
    for plan in plans:
        if plan["fixed"]:
            continue
        planning.append(f"- {plan['item']} {plan['title']} — {plan['state']}")
        for feature in plan["features"]:
            if feature["state"] == "done":
                continue
            planning.append(f"  - {feature['item']} {feature['title']} — {feature['state']}")
            planning.extend(f"    - {task['item']} {task['title']} — {task['state']}"
                            for task in feature["tasks"] if task["state"] != "done")
    if planning:
        planning.insert(0, "\nOpen planning:")
    return _fit(head, planning, tail)


def planning_context(notes: NoteStore) -> str:
    """The context of plan mode: how to plan here, the planning guidelines and the open requirements.

    Args:
        notes: The store.

    Returns:
        The text.
    """
    lines = ["Plans are kept in doctracker's Planner. Build on the open plans and their requirements below. "
             "Before leaving plan mode, record the plan there: create_plan (features and tasks with their "
             "criteria, the requirements and the decisions taken with the user), or add_feature / add_task "
             "to an open plan.",
             *_guidelines(notes, "planning", "Guidelines for planning:")]
    for plan in notes.planner(include_done=False)["plans"]:
        if plan["fixed"] or not plan["requirements"]:
            continue
        lines.append(f"\nRequirements of {plan['item']} {plan['title']}:")
        lines.extend(f"- {requirement}" for requirement in plan["requirements"])
    return _fit(lines, [], [])


def file_context(notes: NoteStore, entities: dict[str, dict], path: str) -> str:
    """The context of a file being read or edited: the notes about its code.

    Args:
        notes: The store.
        entities: The extracted entities, by path; their `filepath` is relative to the project root.
        path: The file, relative to the project root, with forward slashes.

    Returns:
        The notes about the entities of the file and, with them, whether a task is in progress;
        empty when no note is about that code.
    """
    in_file = [entity_path for entity_path, entity in entities.items() if entity.get("filepath") == path]
    found = {}
    for entity_path in in_file:
        for note in notes.list_notes(entity=entity_path):
            found.setdefault(note["id"], note)
    if not found:
        return ""
    lines = [f"Notes about the code of {path}:"]
    for note in found.values():
        about = ", ".join(entity for entity in note["entities"] if entity in in_file)
        lines.append(f"- note:{note['id']} ({note['type']}) {note['statement']} [{about}]")
    doing = [task for plan in notes.planner(include_done=False)["plans"] for feature in plan["features"]
             for task in feature["tasks"] if task["status"] == "doing"]
    if not doing:
        lines.append(NO_TASK_IN_PROGRESS)
    return _fit(lines, [], [])


def commit_context(notes: NoteStore) -> str:
    """The context of a commit: the guidelines given when committing.

    Args:
        notes: The store.

    Returns:
        The text; empty when no guideline is given at commit.
    """
    return _fit(_guidelines(notes, "commit", "Guidelines for committing:"), [], [])


def _guidelines(notes: NoteStore, moment: str, title: str) -> list[str]:
    """The guidelines given at a moment, one line each with its reason; nothing when there are none."""
    lines = []
    for note in notes.list_notes(group="guidelines", moment=moment):
        why = f" Why: {note['why']}" if note["why"] else ""
        lines.append(f"- ({note['type']}) {note['statement']}{why}")
    return [f"\n{title}", *lines] if lines else []


MORE_GUIDELINES = "(more guidelines in list_notes)"
"""Ends the guidelines when even they do not fit `CONTEXT_LIMIT`."""


def _fit(head: list[str], cut: list[str], tail: list[str]) -> str:
    """Join the lines within `CONTEXT_LIMIT`: lines of `cut` go first, from the end, then lines of
    `head`; `tail` always stays."""
    text = "\n".join([*head, *cut, *tail]).strip()
    planning_cut = [MORE] if cut else []
    while len(text) > CONTEXT_LIMIT and cut:
        cut = cut[:-1]
        text = "\n".join([*head, *cut, MORE, *tail]).strip()
    while len(text) > CONTEXT_LIMIT and len(head) > 1:
        head = head[:-1]
        text = "\n".join([*head, MORE_GUIDELINES, *planning_cut, *tail]).strip()
    return text[:CONTEXT_LIMIT]
