"""Integrations with the agents that use doctracker (Claude Code, Codex, OpenCode), and what they share."""

import shutil
import sys
from pathlib import Path

SERVER_DOWN = ("doctracker is not running at {url}, so its plans, guidelines and memory are not available. "
               "Ask the user whether to start it (`doctracker start` in the project) or to work with local "
               "memory in this session.")
"""Given at the start of a session when the server does not answer: the user decides."""

NOT_STARTED = ("doctracker is not running at {url} and could not be started (its output is in doc/logs/server.log), "
               "so its MCP tools and wiki are not available. The guidelines and planning below were read straight "
               "from its notes. Tell the user, who can start it with `doctracker start` in the project.")
"""Given at the start of a session when the hook could not start the server, before the context read from notes.db."""

RECORD_THE_PLAN = ("Plans are kept in doctracker's Planner: once the user approves this plan, record it there "
                   "(create_plan, or add_feature / add_task to an open plan) with its requirements, the decisions "
                   "taken with the user and the criteria of each task.")
"""Given when plan mode ends."""


def exclude_from_git(project_root: Path, path: str) -> None:
    """Add a path to `.git/info/exclude` when the project is the top of a git repository and it is not there yet.

    Args:
        project_root: Root of the project.
        path: The file, relative to the root, e.g. `.mcp.json`.
    """
    git = project_root / ".git"
    if not git.is_dir():
        return
    exclude = git / "info" / "exclude"
    lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    if f"/{path}" in lines:
        return
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_text("\n".join([*lines, f"/{path}"]) + "\n", encoding="utf-8")


def doctracker_command() -> list[str]:
    """The command that runs this environment's doctracker, by absolute paths.

    Returns:
        `[program]`, or `[python, "-m", "doctracker"]` when there is no `doctracker` script.
    """
    program = shutil.which("doctracker", path=str(Path(sys.executable).parent))
    return [Path(program).as_posix()] if program else [Path(sys.executable).as_posix(), "-m", "doctracker"]
