"""Claude Code integration: the hooks that give doctracker's context to the agent, and their settings.

`doctracker init` and `doctracker start` write the hooks into the project's
`.claude/settings.local.json` (local, never committed). Each hook runs `doctracker hook <event>`,
which reads the event Claude Code sends, asks the running server for the context of that moment
(`/hooks/context/...`) and answers it as `additionalContext`.
"""

import json
import shutil
import sys
from pathlib import Path

import httpx2

from doctracker.integrations import RECORD_THE_PLAN, SERVER_DOWN

SETTINGS_PATH = Path(".claude") / "settings.local.json"
"""Claude Code settings of the project that stay on this machine."""

HOOKS = {
    "SessionStart": "",
    "SubagentStart": "",
    "UserPromptSubmit": "",
    "PreToolUse": "EnterPlanMode|ExitPlanMode",
    "PostToolUse": "Read|Edit|Write|MultiEdit",
}
"""The events doctracker answers, with the tools they are limited to (empty: every one)."""

HOOK_TIMEOUT = 10
"""Seconds Claude Code waits for a doctracker hook."""

SERVER_TIMEOUT = 5.0
"""Seconds a hook waits for the doctracker server."""

FILE_TOOLS = ("Read", "Edit", "Write", "MultiEdit")
"""Tools that read or change one file; its notes are given once per session."""


def answer(event: dict, base_url: str) -> dict | None:
    """The answer to one hook event: the context of its moment, or nothing.

    Args:
        event: What Claude Code sent: `hook_event_name`, `session_id`, `permission_mode`,
            `tool_name`, `tool_input`...
        base_url: The doctracker server, e.g. `http://127.0.0.1:8765`.

    Returns:
        The hook output (`hookSpecificOutput` with `additionalContext`), or None when there is
        nothing to say.
    """
    name, tool = event.get("hook_event_name", ""), event.get("tool_name", "")
    session = event.get("session_id", "")
    if name in ("SessionStart", "SubagentStart"):
        text = _ask(base_url, "session", session=session, once=False)
        text = SERVER_DOWN.format(url=base_url) if text is None else text
    elif (name == "UserPromptSubmit" and event.get("permission_mode") == "plan") or (
            name == "PreToolUse" and tool == "EnterPlanMode"):
        text = _ask(base_url, "planning", session=session, once=True)
    elif name == "PreToolUse" and tool == "ExitPlanMode":
        text = RECORD_THE_PLAN
    elif name == "PostToolUse" and tool in FILE_TOOLS and (event.get("tool_input") or {}).get("file_path"):
        text = _ask(base_url, "file", session=session, once=True, path=event["tool_input"]["file_path"])
    else:
        text = None
    if not text:
        return None
    return {"hookSpecificOutput": {"hookEventName": name, "additionalContext": text}}


def _ask(base_url: str, kind: str, session: str, once: bool, path: str = "") -> str | None:
    """Ask the server for a context; None when it does not answer."""
    params = {"session": session, **({"once": "1"} if once else {}), **({"path": path} if path else {})}
    try:
        response = httpx2.get(f"{base_url}/hooks/context/{kind}", params=params, timeout=SERVER_TIMEOUT)
        response.raise_for_status()
        return response.json().get("context", "")
    except (httpx2.HTTPError, ValueError):
        return None


def hook_command(event: str) -> str:
    """The command a hook runs: this environment's doctracker, by its absolute path.

    Args:
        event: The Claude Code event.

    Returns:
        The command line, with the program quoted (paths may have spaces).
    """
    program = shutil.which("doctracker", path=str(Path(sys.executable).parent))
    command = f'"{Path(program).as_posix()}"' if program else f'"{Path(sys.executable).as_posix()}" -m doctracker'
    return f"{command} hook {event}"


def write_settings(project_root: Path) -> Path:
    """Write doctracker's hooks into `.claude/settings.local.json` and switch Claude Code's own memory off.

    The file's other settings and hooks are kept; doctracker's own hooks (those running
    `doctracker hook`) are replaced, so writing again only refreshes them.

    Args:
        project_root: Root of the project.

    Returns:
        The settings file.
    """
    file = project_root / SETTINGS_PATH
    settings = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    hooks = settings.setdefault("hooks", {})
    for event, matcher in HOOKS.items():
        groups = [group for group in hooks.get(event, []) if not _is_ours(group)]
        ours = {"hooks": [{"type": "command", "command": hook_command(event), "timeout": HOOK_TIMEOUT}]}
        groups.append({"matcher": matcher, **ours} if matcher else ours)
        hooks[event] = groups
    settings["autoMemoryEnabled"] = False
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return file


def _is_ours(group: dict) -> bool:
    """Whether a group of hooks in the settings is doctracker's."""
    return any("doctracker" in hook.get("command", "") and " hook " in hook.get("command", "")
               for hook in group.get("hooks", []))
