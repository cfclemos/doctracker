"""Codex integration: the hooks that give doctracker's context to the agent, and its MCP server.

Codex hooks have the same format as Claude Code's, so they follow the same pattern: `doctracker init`
and `doctracker start` write them into the project's `.codex/hooks.json` and the MCP server into
`.codex/config.toml` (both local, kept out of git through `.git/info/exclude`). Each hook runs
`doctracker hook <event>`, answered by `doctracker.integrations.claude_code.answer`. Codex edits files
with `apply_patch`, the only tool its hooks are limited to. Codex loads a project's `.codex/` only when
the project is trusted, and runs a hook only after it was trusted in `/hooks`.
"""

import json
from pathlib import Path

from doctracker.integrations import exclude_from_git
from doctracker.integrations.claude_code import MCP_NAME, set_hooks

HOOKS_PATH = Path(".codex") / "hooks.json"
"""Codex hooks of the project."""

CONFIG_PATH = Path(".codex") / "config.toml"
"""Codex settings of the project, where its MCP servers are."""

HOOKS = {
    "SessionStart": "",
    "SubagentStart": "",
    "UserPromptSubmit": "",
    "PreToolUse": "apply_patch",
    "PostToolUse": "apply_patch",
}
"""The events doctracker answers, with the tools they are limited to (empty: every one)."""

MCP_SECTION = f"[mcp_servers.{MCP_NAME}]"
"""The header of doctracker's server in `.codex/config.toml`."""


def write_hooks(project_root: Path, base_url: str) -> Path:
    """Write doctracker's hooks into `.codex/hooks.json` and keep the file out of git.

    The file's other hooks are kept; writing again only refreshes doctracker's (e.g. after a port change).

    Args:
        project_root: Root of the project.
        base_url: The doctracker server the hooks ask, e.g. `http://127.0.0.1:8765`.

    Returns:
        The hooks file.
    """
    file = project_root / HOOKS_PATH
    config = json.loads(file.read_text(encoding="utf-8")) if file.exists() else {}
    set_hooks(config.setdefault("hooks", {}), HOOKS, base_url)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    exclude_from_git(project_root, HOOKS_PATH.as_posix())
    return file


def write_mcp_config(project_root: Path, base_url: str) -> Path:
    """Write doctracker's MCP server into `.codex/config.toml` and keep the file out of git.

    Only the `[mcp_servers.doctracker]` table is replaced; the rest of the file stays as written.

    Args:
        project_root: Root of the project.
        base_url: The doctracker server, e.g. `http://127.0.0.1:8765`.

    Returns:
        The config file.
    """
    file = project_root / CONFIG_PATH
    lines = file.read_text(encoding="utf-8").splitlines() if file.exists() else []
    kept, ours = [], False
    for line in lines:
        if line.strip().startswith("["):
            ours = line.strip() == MCP_SECTION
        if not ours:
            kept.append(line)
    while kept and not kept[-1].strip():
        kept.pop()
    section = [MCP_SECTION, f"url = {json.dumps(f'{base_url}/mcp')}"]
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text("\n".join([*kept, *([""] if kept else []), *section]) + "\n", encoding="utf-8")
    exclude_from_git(project_root, CONFIG_PATH.as_posix())
    return file
