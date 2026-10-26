"""Read the project's git history with the `git` command (no library needed).

Each commit lists the files it added, modified, deleted or renamed; `commit_diff`
gives the changed lines of each file of one commit.
"""

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

COMMIT_HASH = re.compile(r"^[0-9a-f]{4,40}$")
"""A full or abbreviated commit hash; anything else is refused before calling git."""

MAX_DIFF_LINES = 3000
"""Most diff lines kept per file; longer diffs are cut (and marked as truncated)."""

_HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)$")
"""Hunk header of a unified diff: old start line, new start line, and the context after it."""

RECORD = "\x1e"
"""Separates commits in the `git log` output."""

FIELD = "\x1f"
"""Separates the fields of a commit header in the `git log` output."""

LOG_FORMAT = FIELD.join(["%H", "%h", "%an", "%aI", "%s"])
"""Commit header: full hash, short hash, author, author date (ISO 8601) and subject."""


@dataclass
class Commit:
    """One commit and the files it touched.

    Attributes:
        hash: Full commit hash.
        short: Abbreviated hash.
        author: Author name.
        date: Author date, ISO 8601.
        subject: First line of the message.
        added: Files created by the commit, relative to the project root.
        modified: Files changed by the commit.
        deleted: Files removed by the commit.
        renamed: `(old, new)` pairs of renamed files.
    """

    hash: str
    short: str
    author: str
    date: str
    subject: str
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    renamed: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class DiffLine:
    """One line of a file diff.

    Attributes:
        kind: `hunk` (a `@@` header), `context` (unchanged), `add` (+) or `delete` (−).
        old: Line number in the old file (`None` for added lines and hunk headers).
        new: Line number in the new file (`None` for deleted lines and hunk headers).
        text: The line, without the leading `+`, `-` or space.
    """

    kind: str
    old: int | None
    new: int | None
    text: str


@dataclass
class FileDiff:
    """The changes of one file in a commit.

    Attributes:
        path: File path after the commit (before it, for deleted files).
        old_path: Path before the commit, when the file was renamed.
        status: `added`, `modified`, `deleted` or `renamed`.
        additions: Lines added.
        deletions: Lines deleted.
        binary: True for binary files (no lines shown).
        truncated: True when the diff was cut at `MAX_DIFF_LINES`.
        lines: The diff lines.
    """

    path: str
    old_path: str = ""
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    binary: bool = False
    truncated: bool = False
    lines: list[DiffLine] = field(default_factory=list)


async def _git(project_root: Path, *args: str) -> str | None:
    """Run a git command in the project without blocking the server.

    Args:
        project_root: Root of the documented project.
        *args: git arguments, e.g. `"log", "-n10"`.

    Returns:
        What git printed, or `None` when git is not installed or the command failed
        (for example, the project is not a repository).
    """
    if shutil.which("git") is None:
        return None
    process = await asyncio.create_subprocess_exec(
        "git", "-C", str(project_root), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    output, _ = await process.communicate()
    return output.decode("utf-8", errors="replace") if process.returncode == 0 else None


async def commit_diff(project_root: Path, commit_hash: str) -> list[FileDiff] | None:
    """Read the changed lines of every file of one commit.

    Args:
        project_root: Root of the documented project.
        commit_hash: Full or abbreviated hash.

    Returns:
        One entry per changed file, in git's order; `None` when the hash is invalid or unknown,
        or the project is not a repository.
    """
    if not COMMIT_HASH.match(commit_hash):
        return None
    output = await _git(project_root, "show", "--format=", "--patch", "-M", "--relative", "--no-color",
                        "--no-ext-diff", commit_hash)
    return None if output is None else parse_diff(output)


def parse_diff(output: str) -> list[FileDiff]:
    """Parse a unified diff (as printed by `git show --patch`) into files and lines.

    Args:
        output: Text printed by git.

    Returns:
        One entry per file.
    """
    files: list[FileDiff] = []
    current: FileDiff | None = None
    old = new = 0
    for line in output.splitlines():
        if line.startswith("diff --git "):
            match = re.match(r"diff --git a/(.*) b/(.*)$", line)
            current = FileDiff(path=match.group(2) if match else line[11:])
            files.append(current)
        elif current is None:
            continue
        elif line.startswith("new file mode"):
            current.status = "added"
        elif line.startswith("deleted file mode"):
            current.status = "deleted"
        elif line.startswith("rename from "):
            current.status = "renamed"
            current.old_path = line[len("rename from "):]
        elif line.startswith("rename to "):
            current.path = line[len("rename to "):]
        elif line.startswith("Binary files "):
            current.binary = True
        elif line.startswith(("--- ", "+++ ", "index ", "similarity index", "old mode", "new mode")):
            continue
        elif line.startswith("@@"):
            match = _HUNK.match(line)
            if match:
                old, new = int(match.group(1)), int(match.group(2))
                _keep(current, DiffLine("hunk", None, None, line))
        elif line.startswith("+"):
            current.additions += 1
            _keep(current, DiffLine("add", None, new, line[1:]))
            new += 1
        elif line.startswith("-"):
            current.deletions += 1
            _keep(current, DiffLine("delete", old, None, line[1:]))
            old += 1
        elif line.startswith(" "):
            _keep(current, DiffLine("context", old, new, line[1:]))
            old += 1
            new += 1
    return files


def _keep(file: FileDiff, line: DiffLine) -> None:
    """Add a line to a file diff, unless it already has `MAX_DIFF_LINES` lines.

    Args:
        file: The file diff.
        line: The line to add.
    """
    if len(file.lines) < MAX_DIFF_LINES:
        file.lines.append(line)
    else:
        file.truncated = True


GRAPH_FORMAT = FIELD.join(["%H", "%h", "%P", "%D", "%an", "%aI", "%s"])
"""Commit line of the branch graph: hash, short hash, parents, references, author, date, subject."""


async def read_branch_graph(project_root: Path, limit: int) -> list[dict] | None:
    """Read the commits of every branch and place them on lanes, like `git log --graph`.

    Commits are read newest first in topological order. Each one takes the lane that was
    waiting for it (the lane of a child that named it as parent), or a new lane; its first
    parent continues on the same lane, other parents (merges) get lanes of their own.

    Args:
        project_root: Root of the documented project.
        limit: Most recent commits to read (across all branches).

    Returns:
        Newest first: `hash`, `short`, `parents`, `refs` (branch and tag names), `head`
        (the checked-out commit), `lane`, `author`, `date`, `subject`; `None` when git or
        the repository is missing.
    """
    output = await _git(project_root, "log", "--all", "--topo-order", f"-n{limit}", f"--format={GRAPH_FORMAT}")
    if output is None:
        return None
    commits = []
    for line in output.splitlines():
        parts = line.split(FIELD)
        if len(parts) != 7:
            continue
        full, short, parents, refs, author, date, subject = parts
        names = [ref.strip() for ref in refs.split(",") if ref.strip()]
        commits.append({
            "hash": full, "short": short, "parents": parents.split(), "author": author, "date": date,
            "subject": subject,
            "head": any(name == "HEAD" or name.startswith("HEAD -> ") for name in names),
            "refs": [name.removeprefix("HEAD -> ") for name in names if name != "HEAD"],
        })
    lanes: list[str | None] = []  # lanes[i] = hash of the commit lane i is waiting for
    for commit in commits:
        waiting = [index for index, expected in enumerate(lanes) if expected == commit["hash"]]
        if waiting:
            lane = waiting[0]
            for other in waiting[1:]:  # branches that end here (merged into this commit)
                lanes[other] = None
        else:
            lane = lanes.index(None) if None in lanes else len(lanes)
            if lane == len(lanes):
                lanes.append(None)
        commit["lane"] = lane
        parents = commit["parents"]
        lanes[lane] = parents[0] if parents else None
        for parent in parents[1:]:
            if parent not in lanes:
                free = lanes.index(None) if None in lanes else len(lanes)
                if free == len(lanes):
                    lanes.append(None)
                lanes[free] = parent
    return commits


async def read_history(project_root: Path, limit: int, path: str = "") -> list[Commit] | None:
    """Read the commits of the project, newest first.

    Args:
        project_root: Root of the documented project.
        limit: Most recent commits to read.
        path: Only commits that touched this file or folder (relative to the root); empty means all.

    Returns:
        The commits, newest first; `None` when git is not installed or the project is not a repository.
    """
    # --relative: file paths relative to the project root, even when it is a subfolder of the repository.
    args = ["log", f"-n{limit}", "--name-status", "-M", "--relative", f"--format={RECORD}{LOG_FORMAT}"]
    if path:
        args += ["--", path]
    output = await _git(project_root, *args)
    return None if output is None else parse_log(output)


def parse_log(output: str) -> list[Commit]:
    """Parse `git log --name-status` output made with `LOG_FORMAT`.

    Args:
        output: Text printed by git.

    Returns:
        The commits, in the order git printed them (newest first).
    """
    commits = []
    for record in output.split(RECORD):
        lines = [line for line in record.splitlines() if line.strip()]
        if not lines:
            continue
        parts = lines[0].split(FIELD)
        if len(parts) != 5:
            continue
        commit = Commit(*parts)
        for line in lines[1:]:
            status, *files = line.split("\t")
            if status.startswith("R") and len(files) == 2:
                commit.renamed.append((files[0], files[1]))
            elif status == "A" and files:
                commit.added.append(files[0])
            elif status == "D" and files:
                commit.deleted.append(files[0])
            elif files:
                commit.modified.append(files[-1])
        commits.append(commit)
    return commits
