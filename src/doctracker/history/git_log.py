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


async def git_dir(project_root: Path) -> Path | None:
    """Find the repository's `.git` folder (it may be above the project, or elsewhere for worktrees).

    Args:
        project_root: Root of the documented project.

    Returns:
        Absolute path of the git folder, or `None` when the project is not in a repository.
    """
    output = await _git(project_root, "rev-parse", "--absolute-git-dir")
    return Path(output.strip()) if output else None


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


REFLOG_FORMAT = FIELD.join(["%gD", "%H", "%gs"])
"""Reflog entry: reference with its index (e.g. `refs/heads/main@{0}`), commit hash, action."""

MADE_ON_BRANCH = ("commit", "cherry-pick", "revert", "merge")
"""Reflog actions that create a commit on the checked-out branch (a fast-forward merge does not)."""


async def read_commit_branches(project_root: Path) -> dict[str, str]:
    """Find the branch each commit was made on, as far as the local reflog remembers.

    git itself does not record it; the reflog does, but only for this clone and only for a
    while (entries expire, deleted branches lose theirs).

    Args:
        project_root: Root of the documented project.

    Returns:
        Branch name by full commit hash; commits the reflog does not cover are left out.
    """
    output = await _git(project_root, "log", "--walk-reflogs", "--all", f"--format={REFLOG_FORMAT}")
    branches: dict[str, str] = {}
    for line in (output or "").splitlines():
        parts = line.split(FIELD)
        if len(parts) != 3:
            continue
        selector, full, action = parts
        made_here = action.startswith(MADE_ON_BRANCH) and not action.endswith("Fast-forward")
        if selector.startswith("refs/heads/") and made_here:
            branches.setdefault(full, selector.removeprefix("refs/heads/").rsplit("@{", 1)[0])
    return branches


async def read_branch_graph(project_root: Path, limit: int) -> list[dict] | None:
    """Read the commits of every branch and place them on lanes, one lane per branch.

    The branch of a commit comes from the reflog while it remembers it (`read_commit_branches`);
    older commits follow the topology, like `git log --graph`: a commit continues the branch
    of the child that has it as first parent. See `place_on_lanes`.

    Args:
        project_root: Root of the documented project.
        limit: Most recent commits to read (across all branches).

    Returns:
        Newest first: `hash`, `short`, `parents`, `refs` (branch and tag names), `head`
        (the checked-out commit), `branch` (from the reflog; empty when unknown), `lane`,
        `open` (tip of a branch that goes on to the present), `author`, `date`, `subject`;
        `None` when git or the repository is missing.
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
    place_on_lanes(commits, await read_commit_branches(project_root))
    return commits


def place_on_lanes(commits: list[dict], branches: dict[str, str]) -> None:
    """Give every commit a `branch` and a `lane`, one lane per branch.

    1. Branch: the reflog's when known; otherwise the branch of the child that has the
       commit as first parent (the newest such child); a commit with no such child starts
       an unnamed branch.
    2. Extent: the rows a branch takes, from its commits and the edges to their parents
       and children. A branch still open (its tip has a branch name and was not merged,
       directly or through a later commit) goes on to the newest row; its tip gets `open`.
    3. Lanes: branches from the oldest to the newest, each on the lowest lane free over its
       extent above the lane of the branch it was made from, so the main line stays at the
       bottom and branches made from it step up.

    Args:
        commits: Newest first, with `hash` and `parents`; changed in place.
        branches: Branch by commit hash, from `read_commit_branches`.
    """
    row = {commit["hash"]: index for index, commit in enumerate(commits)}
    track: dict[str, str] = {}
    oldest: dict[str, dict] = {}  # branch -> its oldest commit
    newest: dict[str, dict] = {}  # branch -> its newest commit (its tip)
    continued: dict[str, str] = {}  # commit hash -> branch of the child that has it as first parent
    for commit in commits:  # newest first: children come before their parents
        name = branches.get(commit["hash"]) or continued.get(commit["hash"]) or f"#{len(track)}"
        track[commit["hash"]] = name
        oldest[name] = commit
        newest.setdefault(name, commit)
        commit["open"] = False
        commit["branch"] = branches.get(commit["hash"], "")
        if commit["parents"]:
            continued.setdefault(commit["parents"][0], name)

    extent: dict[str, tuple[int, int]] = {}

    def stretch(name: str, index: int) -> None:
        low, high = extent.get(name, (index, index))
        extent[name] = (min(low, index), max(high, index))

    for commit in commits:
        here = row[commit["hash"]]
        stretch(track[commit["hash"]], here)
        for parent in commit["parents"]:
            if parent in row:
                stretch(track[commit["hash"]], row[parent])
                stretch(track[parent], here)

    # A branch that still exists and was not merged goes on to the present (row 0). Merged:
    # brought in by a merge, directly or as an ancestor of the merged commit.
    parents_of = {commit["hash"]: commit["parents"] for commit in commits}
    merged: set[str] = set()
    pending = [parent for commit in commits for parent in commit["parents"][1:]]
    while pending:
        current = pending.pop()
        if current in parents_of and current not in merged:
            merged.add(current)
            pending.extend(parents_of[current])
    for name, tip in newest.items():
        named = any(not ref.startswith("tag: ") for ref in tip.get("refs", []))
        tip["open"] = named and tip["hash"] not in merged
        if tip["open"]:
            stretch(name, 0)

    lanes: list[list[tuple[int, int]]] = []  # lanes[i] = row ranges already taken on lane i
    lane_of: dict[str, int] = {}
    for name in sorted(extent, key=lambda name: -row[oldest[name]["hash"]]):
        low, high = extent[name]
        parents = oldest[name]["parents"]
        base = lane_of.get(track.get(parents[0], ""), -1) if parents else -1  # lane of the branch it was made from
        free = (index for index in range(base + 1, len(lanes))
                if all(high < start or low > end for start, end in lanes[index]))
        lane = next(free, len(lanes))
        if lane == len(lanes):
            lanes.append([])
        lanes[lane].append((low, high))
        lane_of[name] = lane
    for commit in commits:
        commit["lane"] = lane_of[track[commit["hash"]]]


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
