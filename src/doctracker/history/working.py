"""The working tree for the commit flow: what changed, and committing it group by group.

Paths are relative to the top of the repository, as git prints them; the git commands of the
flow run there, so the same paths can be given back to `git add`.
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

from doctracker.history.git_log import LOG_FORMAT, RECORD, Commit, parse_log

MAX_FILE_DIFF_LINES = 300
"""Diff lines given per file in the pre-commit; longer diffs are cut (and say so)."""

STATUS_NAMES = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "copied", "?": "added", "T": "modified"}
"""`git status --porcelain` letters, as words."""


async def _run(folder: Path, *args: str) -> tuple[int, str, str]:
    """Run git in a folder; the exit code, what it printed and its errors (code 127 without git)."""
    if shutil.which("git") is None:
        return 127, "", "git is not installed."
    process = await asyncio.create_subprocess_exec(
        "git", "-C", str(folder), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    output, errors = await process.communicate()
    return process.returncode, output.decode("utf-8", errors="replace"), errors.decode("utf-8", errors="replace")


async def top_level(project_root: Path) -> Path | None:
    """The top folder of the repository holding the project; None when it is not in one."""
    code, output, _ = await _run(project_root, "rev-parse", "--show-toplevel")
    return Path(output.strip()) if code == 0 else None


async def changed_files(top: Path) -> list[dict]:
    """The files changed in the working tree, staged or not, and the new files git does not ignore.

    Args:
        top: Top folder of the repository.

    Returns:
        `path`, `status` (added, modified, deleted, renamed...) and, for a rename, `old_path`.
    """
    code, output, _ = await _run(top, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if code != 0:
        return []
    entries, files = output.split("\0"), []
    index = 0
    while index < len(entries):
        entry = entries[index]
        index += 1
        if len(entry) < 4:
            continue
        letters, path = entry[:2], entry[3:]
        letter = next((char for char in letters if char != " "), "M")
        file = {"path": path, "status": STATUS_NAMES.get(letter, "modified")}
        if "R" in letters or "C" in letters:
            file["old_path"] = entries[index]
            index += 1
        files.append(file)
    return files


async def line_counts(top: Path) -> dict[str, tuple[int, int]]:
    """Lines added and removed per tracked file against the last commit (`git diff --numstat HEAD`)."""
    code, output, _ = await _run(top, "diff", "--numstat", "HEAD")
    counts = {}
    for line in output.splitlines() if code == 0 else []:
        added, removed, path = (line.split("\t") + ["", "", ""])[:3]
        counts[path] = (int(added) if added.isdigit() else 0, int(removed) if removed.isdigit() else 0)
    return counts


async def file_diff(top: Path, file: dict) -> dict:
    """The changes of one file against the last commit, cut at `MAX_FILE_DIFF_LINES` lines.

    Args:
        top: Top folder of the repository.
        file: An entry of `changed_files`.

    Returns:
        The entry with `diff` (unified diff text; a new file shows as added lines) and `truncated`.
    """
    code, output, _ = await _run(top, "diff", "HEAD", "--", file["path"])
    text = output if code == 0 else ""
    if not text and file["status"] == "added":
        try:
            content = (top / file["path"]).read_text(encoding="utf-8")
            text = "".join(f"+{line}\n" for line in content.splitlines())
        except (OSError, UnicodeDecodeError):
            text = "(binary or unreadable file)"
    lines = text.splitlines()
    return {**file, "diff": "\n".join(lines[:MAX_FILE_DIFF_LINES]), "truncated": len(lines) > MAX_FILE_DIFF_LINES}


async def commit_files(top: Path, files: list[str], message: str) -> tuple[str | None, str]:
    """`git add` the files and `git commit` them with the message.

    When the commit fails (a hook of the project refuses it, for example), the files are taken out
    of the index again, with their changes kept on disk, so nothing is left half done.

    Args:
        top: Top folder of the repository.
        files: Paths relative to the top of the repository; deleted files are recorded as deleted.
        message: The commit message.

    Returns:
        The new commit's full hash and an empty error, or `None` and what git said.
    """
    code, _, errors = await _run(top, "add", "-A", "--", *files)
    if code != 0:
        return None, errors.strip()
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as handle:
        handle.write(message.strip() + "\n")
    try:
        code, output, errors = await _run(top, "commit", "-F", handle.name)
    finally:
        Path(handle.name).unlink(missing_ok=True)
    if code != 0:
        await _run(top, "reset", "-q", "--", *files)
        return None, (errors.strip() or output.strip())
    code, output, _ = await _run(top, "rev-parse", "HEAD")
    return output.strip(), ""


async def head(top: Path) -> str:
    """The hash of the checked-out commit; empty in a repository without commits."""
    code, output, _ = await _run(top, "rev-parse", "HEAD")
    return output.strip() if code == 0 else ""


async def commits_since(top: Path, since_commit: str, since_time: str) -> list[Commit]:
    """The commits reachable from HEAD and not from `since_commit`, made after `since_time`, oldest first.

    The time keeps a checkout of an older branch from passing its commits off as new.

    Args:
        top: Top folder of the repository.
        since_commit: The last commit already seen.
        since_time: When the commits were last checked, ISO 8601.

    Returns:
        The new commits, with their files.
    """
    code, output, _ = await _run(top, "log", f"{since_commit}..HEAD", f"--since={since_time}", "--name-status",
                                 "-M", f"--format={RECORD}{LOG_FORMAT}")
    return list(reversed(parse_log(output))) if code == 0 else []
