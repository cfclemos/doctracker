"""OpenCode integration: the plugin that gives doctracker's context to the agent.

`doctracker init` and `doctracker start` write `opencode_plugin.js` into the project's
`.opencode/plugins/doctracker.js`, with the server's address and the shared texts filled in, and keep
it out of git through `.git/info/exclude` (local, never the project's `.gitignore`). The plugin asks
the running server for the context of each moment (`/hooks/context/...`), as the Claude Code hooks do.
"""

import json
import shutil
from pathlib import Path

from doctracker.integrations import RECORD_THE_PLAN, SERVER_DOWN, exclude_from_git

PLUGIN_PATH = Path(".opencode") / "plugins" / "doctracker.js"
"""Where OpenCode loads the project's plugin from."""

TEMPLATE = Path(__file__).with_name("opencode_plugin.js")
"""The plugin, with `__NAME__` placeholders for the values."""


def uses_opencode(project_root: Path) -> bool:
    """Whether the plugin is wanted: OpenCode is installed, or the project has an `.opencode/` folder."""
    return shutil.which("opencode") is not None or (project_root / ".opencode").is_dir()


def write_plugin(project_root: Path, base_url: str) -> Path:
    """Write the plugin into `.opencode/plugins/doctracker.js` and keep it out of git.

    Only that file is written; writing again only refreshes it (e.g. after a port change).

    Args:
        project_root: Root of the project.
        base_url: The doctracker server, e.g. `http://127.0.0.1:8765`.

    Returns:
        The plugin file.
    """
    values = {"__BASE_URL__": base_url, "__SERVER_DOWN__": SERVER_DOWN, "__RECORD_THE_PLAN__": RECORD_THE_PLAN}
    text = TEMPLATE.read_text(encoding="utf-8")
    for placeholder, value in values.items():
        text = text.replace(placeholder, json.dumps(value))
    file = project_root / PLUGIN_PATH
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")
    exclude_from_git(project_root, PLUGIN_PATH.as_posix())
    return file
