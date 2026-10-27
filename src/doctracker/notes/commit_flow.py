"""The commit flow: pre-commit (plan the commits with the user), commit, post-commit, and the
review of commits made outside it.

1. `prepare_commit` gives the material (changed files with their line counts, the open tasks,
   the guidelines for committing) and the diffs asked for; called again with the proposed groups,
   it checks them and lists what is missing. The groups are planned and approved with the user here, before committing.
2. `commit` only runs `git add` and `git commit`, group by group. It stops at the first error and
   says where; calling it again with the groups left goes on.
3. `after_commit` records the commits on their tasks and lists what is pending and what can be
   cleaned up; `clean_done` deletes, once the user confirms. When the work planned for the current
   branch is all done and committed, `merge_ready` says so and `merge` merges it into main, once the
   user confirms.
4. `review_outside_commits` turns each commit not made by the flow into a task of the Reviews plan.
"""

from datetime import datetime, timezone
from pathlib import Path

from doctracker.history import working
from doctracker.notes.context import commit_context
from doctracker.notes.store import NoteStore, parse_item

COMMITTED = "Committed as "
"""Start of the evidence the post-commit adds to a task, followed by the commit's short hash."""


async def prepare_commit(notes: NoteStore, project_root: Path, groups: list[dict] | None = None,
                         diffs: list[str] | None = None) -> dict:
    """The pre-commit: the material to plan the commits, the diffs asked for, or the check of the groups.

    The material lists the files without their diffs (a branch may change many files); the diffs of
    the files that need a closer look are asked for with `diffs`.

    Args:
        notes: The store.
        project_root: Root of the project.
        groups: The planned commits, `[{"files": [...], "message": "...", "tasks": ["task:3"]}]`.
        diffs: Paths whose changes to give (each cut at `working.MAX_FILE_DIFF_LINES` lines).

    Returns:
        With groups: `ready` (nothing missing), `problems` (to solve with the user) and `left_out`
        (changed files in no group: they stay uncommitted). With diffs: `diffs` (path, status, diff,
        truncated). Otherwise: `files` (path, status, lines `added` and `removed`), `tasks` (the open
        ones and those done but not committed yet: title, state, criteria, annotations, evidence) and
        `guidelines`.
    """
    top = await working.top_level(project_root)
    if top is None:
        return {"error": "The project is not in a git repository."}
    files = await working.changed_files(top)
    if diffs and groups is None:
        return {"diffs": [await working.file_diff(top, file) for file in files if file["path"] in diffs]}
    if groups is None:
        counts = await working.line_counts(top)
        listed = []
        for file in files:
            added, removed = counts.get(file["path"], (0, 0))
            if file["status"] == "added" and file["path"] not in counts:
                added = _line_count(top / file["path"])
            listed.append({**file, "added": added, "removed": removed})
        return {"files": listed, "tasks": _tasks_to_commit(notes), "guidelines": commit_context(notes)}
    changed = {file["path"] for file in files}
    problems, seen = [], {}
    for number, group in enumerate(groups, start=1):
        if not (group.get("message") or "").strip():
            problems.append(f"Commit {number} has no message.")
        if not group.get("files"):
            problems.append(f"Commit {number} has no files.")
        for path in group.get("files", []):
            if path not in changed:
                problems.append(f"Commit {number}: {path} has no changes.")
            elif path in seen:
                problems.append(f"{path} is in commits {seen[path]} and {number}; a file goes in one commit.")
            else:
                seen[path] = number
        for item in group.get("tasks", []):
            problems.extend(f"Commit {number}: {gap}" for gap in _task_gaps(notes, item))
    return {"ready": not problems, "problems": problems, "left_out": sorted(changed - set(seen))}


async def commit(notes: NoteStore, project_root: Path, groups: list[dict]) -> dict:
    """Run the planned commits: `git add` and `git commit` for each group, in order.

    Nothing is checked here: the groups were planned and approved in the pre-commit. At the first
    error it stops; the failed group's files are taken out of the index, with their changes kept.

    Args:
        notes: The store; every commit made is recorded with its tasks.
        project_root: Root of the project.
        groups: The approved commits, `[{"files": [...], "message": "...", "tasks": [...]}]`.

    Returns:
        `committed` (`hash`, `message` subject, `tasks`), `failed` (the group's number and git's
        `error`, or None) and `not_run` (numbers of the groups left, to commit again after the fix).
    """
    top = await working.top_level(project_root)
    if top is None:
        return {"committed": [], "failed": {"group": 1, "error": "The project is not in a git repository."},
                "not_run": list(range(2, len(groups) + 1))}
    committed = []
    notes.committing = True
    try:
        for number, group in enumerate(groups, start=1):
            commit_hash, error = await working.commit_files(top, group.get("files", []), group.get("message", ""))
            if commit_hash is None:
                return {"committed": committed, "failed": {"group": number, "error": error},
                        "not_run": list(range(number + 1, len(groups) + 1))}
            notes.record_commit(commit_hash, group.get("tasks", []))
            committed.append({"hash": commit_hash, "subject": group["message"].strip().splitlines()[0],
                              "tasks": group.get("tasks", [])})
    finally:
        notes.committing = False
    return {"committed": committed, "failed": None, "not_run": []}


def after_commit(notes: NoteStore) -> dict:
    """The post-commit: record the new commits on their tasks, and say what is left.

    Args:
        notes: The store.

    Returns:
        `recorded` (the commits just recorded on their tasks), `pending` (open tasks: ref, title,
        state), `can_clean` (done and committed items that can be deleted: tasks, and features and
        plans with everything inside done and committed; approved reviews too, but never the
        Reviews plan or its feature).
    """
    recorded = []
    for made in notes.open_commits():
        for item in made["tasks"]:
            kind, task_id = parse_item(item)
            if kind == "task":
                try:
                    notes.add_evidence(task_id, "diff", f"{COMMITTED}{made['hash'][:7]}.")
                except ValueError:
                    pass  # the task was deleted meanwhile
        notes.close_commit(made["hash"])
        recorded.append(made)
    pending, can_clean = [], []
    for plan in notes.planner()["plans"]:
        plan_clean = not plan["fixed"]
        for feature in plan["features"]:
            feature_clean = not plan["fixed"]
            for task in feature["tasks"]:
                # A review is done once approved; any other task also has to be committed.
                committed = plan["fixed"] or any(e["detail"].startswith(COMMITTED) for e in task["evidence"])
                if task["state"] == "done" and committed:
                    can_clean.append({"ref": task["item"], "title": task["title"]})
                else:
                    feature_clean = False
                    if task["state"] != "done":
                        pending.append({"ref": task["item"], "title": task["title"], "state": task["state"]})
            if feature_clean and feature["tasks"]:
                can_clean.append({"ref": feature["item"], "title": feature["title"]})
            plan_clean = plan_clean and feature_clean and bool(feature["tasks"])
        if plan_clean and plan["features"]:
            can_clean.append({"ref": plan["item"], "title": plan["title"]})
    return {"recorded": recorded, "pending": pending, "can_clean": can_clean}


async def merge_ready(notes: NoteStore, project_root: Path) -> dict | None:
    """Whether the work planned for the checked-out branch is complete, so it can be merged.

    The work of a branch is the plans, features and tasks naming it; it is complete when each of
    their tasks is done and committed.

    Args:
        notes: The store.
        project_root: Root of the project.

    Returns:
        `branch` and `into` (main) when it is complete; None otherwise, or when no plan names the
        branch, or on the main branch.
    """
    top = await working.top_level(project_root)
    if top is None:
        return None
    branch, into = await working.current_branch(top), await working.main_branch(top)
    if not branch or not into or branch == into:
        return None
    tasks = []
    for plan in notes.planner()["plans"]:
        for feature in plan["features"]:
            for task in feature["tasks"]:
                if branch in (*plan["branches"], feature["branch"], task["branch"]):
                    tasks.append(task)
    complete = all(task["state"] == "done" and any(e["detail"].startswith(COMMITTED) for e in task["evidence"])
                   for task in tasks)
    return {"branch": branch, "into": into} if tasks and complete else None


async def merge(notes: NoteStore, project_root: Path) -> dict:
    """Merge the checked-out branch into main, with a merge commit, once the user confirmed.

    The merge commit is recorded as made by the flow, so it is not taken for an outside commit.
    On a conflict the merge is aborted and the branch stays checked out.

    Args:
        notes: The store.
        project_root: Root of the project.

    Returns:
        `merged` (branch, into, hash), or `error`.
    """
    top = await working.top_level(project_root)
    if top is None:
        return {"error": "The project is not in a git repository."}
    branch, into = await working.current_branch(top), await working.main_branch(top)
    if not branch or not into or branch == into:
        return {"error": f"Nothing to merge: the checked-out branch is {branch or 'none'}."}
    notes.committing = True
    try:
        merge_hash, error = await working.merge_branch(top, branch, into)
        if merge_hash:
            notes.record_commit(merge_hash, [])
            notes.close_commit(merge_hash)
    finally:
        notes.committing = False
    if merge_hash is None:
        return {"error": error}
    return {"merged": {"branch": branch, "into": into, "hash": merge_hash}}


def clean_done(notes: NoteStore, items: list[str]) -> dict:
    """Archive and delete done and committed items the user confirmed; anything else given is refused.

    What they held stays in the archive, tied to their commits (shown with the git history).

    Args:
        notes: The store.
        items: References from `after_commit`'s `can_clean`.

    Returns:
        `deleted`, `refused` (not cleanable) and `pending`, the open tasks left (the next steps).
    """
    report = after_commit(notes)
    cleanable = {entry["ref"] for entry in report["can_clean"]}
    deleted, refused = [], []
    for item in items:
        if item not in cleanable:
            refused.append(item)
            continue
        try:
            notes.archive_item(item)
            notes.delete_item(item)
            deleted.append(item)
        except ValueError:
            pass  # already gone with the plan or feature holding it
    return {"deleted": deleted, "refused": refused, "pending": report["pending"]}


async def review_outside_commits(notes: NoteStore, project_root: Path) -> list[dict]:
    """Turn every new commit not made by the flow into a task of the Reviews plan.

    The first time, only the current commit is remembered: the history before is not reviewed.
    While the flow is committing, nothing is done (its commits are recorded right after).

    Args:
        notes: The store, holding the sync marker (`last_commit`, `last_check`).
        project_root: Root of the project.

    Returns:
        The review tasks added.
    """
    if notes.committing:
        return []
    top = await working.top_level(project_root)
    if top is None:
        return []
    current = await working.head(top)
    last, checked = notes.get_meta("last_commit"), notes.get_meta("last_check")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    added = []
    if current and last and current != last:
        for found in await working.commits_since(top, last, checked or now):
            if notes.committing or notes.made_by_flow(found.hash):
                continue
            files = [*found.added, *found.modified, *found.deleted, *(new for _, new in found.renamed)]
            detail = (f"Commit {found.short} by {found.author}, {found.date}: {found.subject}\n"
                      f"{found.body}\n\nFiles: {', '.join(files)}").replace("\n\n\n", "\n\n")
            added.append(notes.add_review(f"Review commit {found.short}: {found.subject}", detail))
    if current and not notes.committing:
        notes.set_meta("last_commit", current)
        notes.set_meta("last_check", now)
    return added


def _line_count(file: Path) -> int:
    """Lines of a new file; 0 when it cannot be read as text."""
    try:
        return len(file.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return 0


def _tasks_to_commit(notes: NoteStore) -> list[dict]:
    """The tasks a commit may carry out: those not done, and those done but not committed yet."""
    tasks = []
    for plan in notes.planner()["plans"]:
        for feature in plan["features"]:
            for task in feature["tasks"]:
                committed = any(e["detail"].startswith(COMMITTED) for e in task["evidence"])
                if task["state"] != "done" or not committed:
                    tasks.append({"ref": task["item"], "title": task["title"], "plan": plan["title"],
                                  "state": task["state"], "criteria": task["criteria"],
                                  "annotations": [a["text"] for a in task["annotations"]],
                                  "evidence": [e["detail"] for e in task["evidence"]]})
    return tasks


def _task_gaps(notes: NoteStore, item: str) -> list[str]:
    """What keeps a task from being committed as done: not found, not approved, criteria not met."""
    try:
        kind, task_id = parse_item(item)
        if kind != "task":
            return [f"{item} is not a task; give the tasks the commit carries out."]
        task = notes.get_task(task_id)
    except ValueError as missing:
        return [str(missing)]
    gaps = []
    if task["status"] != "done":
        gaps.append(f"{item} “{task['title']}” is {task['state']}, not approved as done by the user.")
    unmet = [criterion["text"] for criterion in task["criteria"] if not criterion["done"]]
    if unmet:
        gaps.append(f"{item} “{task['title']}” has criteria not met: {'; '.join(unmet)}.")
    return gaps
