"""Watch the project's Python files and rebuild the documentation when they change.

Change detection polls file modification times (standard library only). The
extraction itself runs in a separate process so the server stays responsive.
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from doctracker.config import DOC_DIR, Config
from doctracker.extraction import extract_project
from doctracker.server.state import DocState

SKIPPED_DIRS = {DOC_DIR, ".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}


def snapshot(project_root: Path, search_paths: list[str]) -> dict[str, int]:
    """Map every watched `.py` file to its modification time."""
    files = {}
    for search_path in search_paths:
        base = project_root / search_path
        if base.is_dir():
            _scan(base, files)
    return files


def _scan(folder: Path, files: dict[str, int]) -> None:
    try:
        entries = list(folder.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir():
            if entry.name not in SKIPPED_DIRS and not entry.name.startswith("."):
                _scan(entry, files)
        elif entry.suffix == ".py":
            try:
                files[str(entry)] = entry.stat().st_mtime_ns
            except OSError:
                pass


async def watch(project_root: Path, config: Config, state: DocState) -> None:
    """Build the documentation once, then rebuild it whenever a watched file changes."""
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=1) as executor:
        previous = None
        while True:
            current = await loop.run_in_executor(executor, snapshot, project_root, config.search_paths)
            if current != previous:
                result = await loop.run_in_executor(
                    executor,
                    extract_project,
                    str(project_root),
                    config.packages,
                    config.search_paths,
                    config.docstring_style,
                    config.show_private,
                )
                state.update(result)
                previous = current
            await asyncio.sleep(config.watch_interval)
