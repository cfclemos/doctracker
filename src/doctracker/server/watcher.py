"""Watch the project and keep the wiki up to date.

Two things are watched by polling modification times (standard library only):

- the project's Python files: a change rebuilds the documentation (the extraction runs
  in a separate process, so the server stays responsive);
- the git state (HEAD, branches, tags): a commit, checkout or new branch tells the open wiki
  pages to reload, since the code itself did not change, and a commit made outside the commit
  flow becomes a task of the Reviews plan (also for the commits made while the server was off).
"""

import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from doctracker.config import DOC_DIR, Config
from doctracker.extraction import extract_project
from doctracker.history import git_dir
from doctracker.notes import NoteStore
from doctracker.notes.commit_flow import review_outside_commits
from doctracker.server.state import DocState

SKIPPED_DIRS = {DOC_DIR, ".git", ".venv", "venv", "__pycache__", "node_modules", ".mypy_cache", ".ruff_cache"}
"""Folders never scanned for changes (besides any folder starting with a dot)."""

GIT_FILES = ("HEAD", "packed-refs", "logs/HEAD")
"""Files of the git folder that change on commit, checkout, reset or branch creation (with `refs/`)."""


def snapshot(project_root: Path, search_paths: list[str]) -> dict[str, int]:
    """Map every watched `.py` file to its modification time.

    Runs in a worker process.

    Args:
        project_root: Root of the documented project.
        search_paths: Folders to scan, relative to `project_root`.

    Returns:
        Modification time in nanoseconds, by file path; two equal snapshots mean nothing changed.
    """
    files = {}
    for search_path in search_paths:
        base = project_root / search_path
        if base.is_dir():
            _scan(base, files)
    return files


def git_snapshot(folder: Path | None) -> dict[str, int]:
    """Map the files that hold the git state (HEAD, branches, tags) to their modification time.

    Runs in a worker process.

    Args:
        folder: The repository's git folder, or `None` outside a repository.

    Returns:
        Modification time in nanoseconds, by file path; empty outside a repository.
    """
    files: dict[str, int] = {}
    if folder is None:
        return files
    for name in GIT_FILES:
        path = folder / name
        if path.is_file():
            files[str(path)] = path.stat().st_mtime_ns
    refs = folder / "refs"
    if refs.is_dir():
        for path in refs.rglob("*"):
            if path.is_file():
                files[str(path)] = path.stat().st_mtime_ns
    return files


def _scan(folder: Path, files: dict[str, int]) -> None:
    """Add the `.py` files of `folder` and its subfolders to `files`, skipping `SKIPPED_DIRS`.

    Args:
        folder: Folder to scan; unreadable folders are skipped.
        files: Modification time by file path; filled in place.
    """
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


async def watch(project_root: Path, config: Config, state: DocState, notes: NoteStore) -> None:
    """Build the documentation once, then keep the wiki in line with the code and the git state.

    A changed Python file rebuilds the documentation; a changed git state (commit, checkout,
    branch) only notifies the open pages. Runs until cancelled; scanning and extraction
    happen in a worker process.

    Args:
        project_root: Root of the documented project.
        config: Project settings (packages, search paths, docstring style, watch interval).
        state: Shared data, replaced after every extraction.
        notes: The store, where commits made outside the commit flow become reviews.
    """
    loop = asyncio.get_running_loop()
    repository = await git_dir(project_root)
    with ProcessPoolExecutor(max_workers=1) as executor:
        previous_code = previous_git = None
        while True:
            code = await loop.run_in_executor(executor, snapshot, project_root, config.search_paths)
            git = await loop.run_in_executor(executor, git_snapshot, repository)
            if code != previous_code:
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
            elif git != previous_git and previous_git is not None:
                state.notify()
            if git != previous_git:  # also at startup: the commits made while the server was off
                await review_outside_commits(notes, project_root)
            previous_code, previous_git = code, git
            await asyncio.sleep(config.watch_interval)
