"""Start, stop and restart a project's doctracker server in the background, and wait until it answers.

Used when an agent opens a session: the hook blocks while the server comes up, so the agent gets
its context and tools without the user starting anything. `doctracker start` records its process in
`doc/logs/server.json`, so `doctracker restart` can stop it and start it again.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx2

from doctracker.config import DOC_DIR

LOG_PATH = Path(DOC_DIR) / "logs" / "server.log"
"""Output of a server started by an agent's session."""

START_TIMEOUT = 60.0
"""Seconds to wait for a server just started to answer."""

POLL_INTERVAL = 0.5
"""Seconds between two checks while waiting."""

CHECK_TIMEOUT = 2.0
"""Seconds one check waits for the server."""

STOP_TIMEOUT = 15.0
"""Seconds to wait for a stopped server to stop answering."""

RECORD_PATH = Path(DOC_DIR) / "logs" / "server.json"
"""The running server: its process id and address, written by `doctracker start`."""


def ensure_server(project_root: Path, base_url: str) -> bool:
    """Start the server in the background when it does not answer, and wait for it.

    Args:
        project_root: Root of the documented project.
        base_url: The server, e.g. `http://127.0.0.1:8765`; its host and port are given to `start`.

    Returns:
        Whether the server answers.
    """
    if answers(base_url):
        return True
    process = start_detached(project_root, base_url)
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline and process.poll() is None:
        time.sleep(POLL_INTERVAL)
        if answers(base_url):
            return True
    return answers(base_url)


def answers(base_url: str) -> bool:
    """Whether the server at `base_url` answers its hook route."""
    try:
        return httpx2.get(f"{base_url}/hooks/context/commit", timeout=CHECK_TIMEOUT).is_success
    except httpx2.HTTPError:
        return False


def start_detached(project_root: Path, base_url: str) -> subprocess.Popen:
    """Run `doctracker start` for the project in a process of its own, which outlives the caller.

    Args:
        project_root: Root of the documented project; the server's output goes to `doc/logs/server.log`.
        base_url: The address the server must listen on.

    Returns:
        The started process.
    """
    address = urlsplit(base_url)
    command = [sys.executable, "-m", "doctracker", "start"]
    if address.hostname:
        command += ["--host", address.hostname]
    if address.port:
        command += ["--port", str(address.port)]
    if sys.platform == "win32":
        options = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP}
    else:
        options = {"start_new_session": True}
    _make_logs_dir(project_root)
    with (project_root / LOG_PATH).open("ab") as output:
        return subprocess.Popen(command, cwd=project_root, stdin=subprocess.DEVNULL, stdout=output,
                                stderr=subprocess.STDOUT, **options)


def record_server(project_root: Path, base_url: str) -> None:
    """Record this process as the project's server, unless another recorded server still answers.

    The record stays after the server stops (uvicorn ends the process by its own signal); a record
    whose server does not answer is overwritten here and ignored by `stop_server`.

    Args:
        project_root: Root of the documented project.
        base_url: The address this server listens on.
    """
    running = _read_record(project_root)
    if running and answers(running["url"]):
        return
    _make_logs_dir(project_root)
    (project_root / RECORD_PATH).write_text(json.dumps({"pid": os.getpid(), "url": base_url}) + "\n", encoding="utf-8")


def stop_server(project_root: Path) -> str | None:
    """Stop the recorded server and wait until it no longer answers.

    Nothing is stopped when the recorded process does not answer at its address (it already
    stopped, and its id may now belong to another program).

    Args:
        project_root: Root of the documented project.

    Returns:
        The recorded address (where the server ran, stopped now or before), or None without a record.
    """
    running = _read_record(project_root)
    if not running:
        return None
    if not answers(running["url"]):
        return running["url"]
    os.kill(running["pid"], signal.SIGTERM)
    deadline = time.monotonic() + STOP_TIMEOUT
    while time.monotonic() < deadline and answers(running["url"]):
        time.sleep(POLL_INTERVAL)
    return running["url"]


def recorded_url(project_root: Path) -> str | None:
    """The address of the project's recorded server, running or not.

    Args:
        project_root: Root of the documented project.

    Returns:
        The address written by `doctracker start`, or None without a record.
    """
    running = _read_record(project_root)
    return running["url"] if running else None


def _make_logs_dir(project_root: Path) -> None:
    """Create `doc/logs/` with a `.gitignore` of its own, so it stays out of git in every project."""
    logs = (project_root / LOG_PATH).parent
    logs.mkdir(parents=True, exist_ok=True)
    ignore = logs / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")


def _read_record(project_root: Path) -> dict | None:
    """The recorded server (`pid`, `url`), or None when there is no readable record."""
    try:
        return json.loads((project_root / RECORD_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
