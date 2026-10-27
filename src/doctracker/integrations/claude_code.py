"""Claude Code integration: the hooks that give doctracker's context to the agent, and their settings.

`doctracker init` and `doctracker start` write the hooks into the project's
`.claude/settings.local.json` and the MCP server into `.mcp.json` (both local, never committed).
Each hook runs `doctracker hook <event>` with the server's address, which reads the event Claude
Code sends, asks the running server for the context of that moment (`/hooks/context/...`) and
answers it as `additionalContext`. When a session opens and the server does not answer, the hook
starts it and waits (`doctracker.integrations.autostart`).
"""

import json
import sqlite3
from pathlib import Path

import httpx2

from doctracker.config import DOC_DIR, NOTES_DATABASE_PATH
from doctracker.integrations import NOT_STARTED, RECORD_THE_PLAN, SERVER_DOWN, doctracker_command, exclude_from_git
from doctracker.integrations.autostart import START_TIMEOUT, ensure_server
from doctracker.notes import NoteStore
from doctracker.notes.context import session_context

SETTINGS_PATH = Path(".claude") / "settings.local.json"
"""Claude Code settings of the project that stay on this machine."""

MCP_PATH = Path(".mcp.json")
"""The project's MCP servers for Claude Code."""

MCP_NAME = "doctracker"
"""The name of doctracker's server in `.mcp.json` (its tools are `mcp__doctracker__...`)."""

HOOKS = {
    "SessionStart": "",
    "SubagentStart": "",
    "UserPromptSubmit": "",
    "PreToolUse": "EnterPlanMode|ExitPlanMode|Edit|Write|MultiEdit",
    "PostToolUse": "Read|Edit|Write|MultiEdit",
}
"""The events doctracker answers, with the tools they are limited to (empty: every one)."""

HOOK_TIMEOUT = 10
"""Seconds Claude Code waits for a doctracker hook."""

START_EVENTS = ("SessionStart", "SubagentStart")
"""Events that start the server when it does not answer."""

START_HOOK_TIMEOUT = int(START_TIMEOUT) + 15
"""Seconds Claude Code waits for a hook of `START_EVENTS`: long enough for the server to come up."""

SERVER_TIMEOUT = 5.0
"""Seconds a hook waits for the doctracker server."""

FILE_TOOLS = ("Read", "Edit", "Write", "MultiEdit")
"""Tools that read or change one file; its notes are given once per session."""

EDIT_TOOLS = ("Edit", "Write", "MultiEdit")
"""Tools that change a file; outside plan mode, editing the project needs a task in progress."""


def answer(event: dict, base_url: str, project_root: Path) -> dict | None:
    """The answer to one hook event: the context of its moment, or nothing.

    Args:
        event: What Claude Code sent: `hook_event_name`, `session_id`, `permission_mode`,
            `tool_name`, `tool_input`...
        base_url: The doctracker server, e.g. `http://127.0.0.1:8765`.
        project_root: Root of the project, where the server is started when a session opens without it.

    Returns:
        The hook output (`hookSpecificOutput` with `additionalContext`), or None when there is
        nothing to say.
    """
    name, tool = event.get("hook_event_name", ""), event.get("tool_name", "")
    session = event.get("session_id", "")
    if name in START_EVENTS:
        text = _ask(base_url, "session", session=session, once=False)
        if text is None and ensure_server(project_root, base_url):
            text = _ask(base_url, "session", session=session, once=False)
        text = _local_session_context(project_root, base_url) if text is None else text
    elif (name == "UserPromptSubmit" and event.get("permission_mode") == "plan") or (
            name == "PreToolUse" and tool == "EnterPlanMode"):
        text = _ask(base_url, "planning", session=session, once=True)
    elif name == "PreToolUse" and tool == "ExitPlanMode":
        text = RECORD_THE_PLAN
    elif name == "PreToolUse" and tool in EDIT_TOOLS:
        path = (event.get("tool_input") or {}).get("file_path", "")
        if event.get("permission_mode") == "plan" or not _gated(project_root, path):
            return None
        reason = _ask(base_url, "edit", session=session, once=False)
        if not reason:
            return None
        return {"hookSpecificOutput": {"hookEventName": name, "permissionDecision": "deny",
                                       "permissionDecisionReason": reason}}
    elif name == "PostToolUse" and tool in FILE_TOOLS and (event.get("tool_input") or {}).get("file_path"):
        text = _ask(base_url, "file", session=session, once=True, path=event["tool_input"]["file_path"])
    else:
        text = None
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}}


def _gated(project_root: Path, path: str) -> bool:
    """Whether editing a file needs a task in progress: a file of the project, outside `doc/`."""
    if not path:
        return False
    try:
        relative = (project_root / path).resolve().relative_to(project_root.resolve())
    except ValueError:
        return False
    return relative.parts[:1] != (DOC_DIR,)


def _ask(base_url: str, kind: str, session: str, once: bool, path: str = "") -> str | None:
    """Ask the server for a context; None when it does not answer."""
    params = {"session": session, **({"once": "1"} if once else {}), **({"path": path} if path else {})}
    try:
        response = httpx2.get(f"{base_url}/hooks/context/{kind}", params=params, timeout=SERVER_TIMEOUT)
        response.raise_for_status()
        return response.json().get("context", "")
    except (httpx2.HTTPError, ValueError):
        return None


def _local_session_context(project_root: Path, base_url: str) -> str:
    """The session context read straight from `notes.db`, after a warning, when the server could not start."""
    path = project_root / NOTES_DATABASE_PATH
    if not path.exists():
        return SERVER_DOWN.format(url=base_url)
    try:
        notes = NoteStore(path, lambda entity: True, lambda: None)
        return f"{NOT_STARTED.format(url=base_url)}\n\n{session_context(notes)}"
    except sqlite3.Error:
        return SERVER_DOWN.format(url=base_url)


def hook_command(event: str, base_url: str) -> str:
    """The command a hook runs: this environment's doctracker, by its absolute path, with the server's address.

    Args:
        event: The Claude Code event.
        base_url: The doctracker server, e.g. `http://127.0.0.1:8765`.

    Returns:
        The command line, with the program quoted (paths may have spaces).
    """
    program, *options = doctracker_command()
    return " ".join([f'"{program}"', *options, "hook", event, "--url", f'"{base_url}"'])


def write_settings(project_root: Path, base_url: str) -> Path:
    """Write doctracker's hooks into `.claude/settings.local.json`, approve its MCP server, turn auto memory off.

    The file's other settings and hooks are kept; doctracker's own hooks (those running
    `doctracker hook`) are replaced, so writing again only refreshes them (e.g. after a port change).
    The server of `.mcp.json` is listed in `enabledMcpjsonServers`, so Claude Code does not ask for it.

    Args:
        project_root: Root of the project.
        base_url: The doctracker server the hooks ask, e.g. `http://127.0.0.1:8765`.

    Returns:
        The settings file.
    """
    file = project_root / SETTINGS_PATH
    settings = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    hooks = settings.setdefault("hooks", {})
    for event, matcher in HOOKS.items():
        groups = [group for group in hooks.get(event, []) if not _is_ours(group)]
        timeout = START_HOOK_TIMEOUT if event in START_EVENTS else HOOK_TIMEOUT
        ours = {"hooks": [{"type": "command", "command": hook_command(event, base_url), "timeout": timeout}]}
        groups.append({"matcher": matcher, **ours} if matcher else ours)
        hooks[event] = groups
    enabled = settings.setdefault("enabledMcpjsonServers", [])
    if MCP_NAME not in enabled:
        enabled.append(MCP_NAME)
    settings["autoMemoryEnabled"] = False
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return file


def write_mcp_config(project_root: Path, base_url: str) -> Path:
    """Write doctracker's MCP server into `.mcp.json` and keep the file out of git.

    The file's other servers are kept; writing again only refreshes the address. The file is added
    to `.git/info/exclude`, which does not apply when the project already tracks it.

    Args:
        project_root: Root of the project.
        base_url: The doctracker server, e.g. `http://127.0.0.1:8765`.

    Returns:
        The MCP config file.
    """
    file = project_root / MCP_PATH
    config = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    config.setdefault("mcpServers", {})[MCP_NAME] = {"type": "http", "url": f"{base_url}/mcp"}
    file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    exclude_from_git(project_root, MCP_PATH.as_posix())
    return file


def _is_ours(group: dict) -> bool:
    """Whether a group of hooks in the settings is doctracker's."""
    return any("doctracker" in hook.get("command", "") and " hook " in hook.get("command", "")
               for hook in group.get("hooks", []))
