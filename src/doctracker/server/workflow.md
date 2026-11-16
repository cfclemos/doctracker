# How to work in a project documented by doctracker

This project keeps its plans, guidelines and memory in doctracker (MCP server "doctracker"), not in
files, code comments or the agent's own memory. Follow these steps in order; each names the tools it
uses. The user decides at every step marked **(user)**.

## 1. Find what is known

- Before planning, changing code or writing a note, call `recall(query)`: open planning first, then
  guidelines, memory and code.
- `work_context` gives the open plans in full; `list_notes` the guidelines and memory.

## 2. Plan

- Judge whether the change needs planning: new behaviour, several files, a design choice, or an open
  plan it touches. Small fixes do not; they still need a task (step 4).
- Plan in plan mode: call EnterPlanMode when you have it; otherwise stop and ask the user to switch the
  session to plan mode, and plan only once it is. Bring the choices to the user instead of deciding
  them alone **(user)**.
- Once the plan is approved, record it in the Planner: `create_plan` (features and tasks with their
  criteria, the requirements and the decisions taken with the user, with why), or `add_feature` /
  `add_task` to an open plan.

## 3. Branch

- Before the first edit, create the work's branch from main with `start_branch(item, name)`: it
  records the branch on the plan, feature or task. A short name for the work, e.g. `free-ports`.
- The branch is how the post-commit knows the work is complete and merges it into main (step 7).

## 4. Work

- Set the task you work on to `doing` (`update_task`) before editing; outside plan mode, edits of the
  project are refused while no task is in progress. A small task can be added on the spot (`add_task`).
- Before writing or changing code or docstrings, read `documentation_guide` and follow it.
- While working, write on the task what was done **and why** (`annotate_task`): the reason for each
  change, the cause of a bug, what was found and decided. These annotations become the commit messages.
- Record what shows the task is done (`add_task_evidence`): a test, a run, a check. Tick each criterion
  as it is met (`check_criterion`). Only the user approves a task as done **(user)**.
- Knowledge that outlives the task goes into notes (`create_note`): guidelines for how to work, memory
  for what is known.

## 5. Plan the commits

- Call `prepare_commit` with no arguments: the changed files, the tasks a commit may carry out (with
  their annotations), the renames and the commit guidelines.
- Split the work into **separate commits, one purpose each**: a file goes whole into one commit.
- Write each message as a short subject saying what changed, then a body saying why, built from the
  annotations of its tasks (reasons and causes). Name the renames as `old.path → new.path`.
- Check the groups with `prepare_commit(groups)` and go through them with the user, problems included
  **(user)**.

## 6. Commit

- `commit` the approved groups only. On an error it stops; fix the cause with the user, check again,
  commit the rest.
- Then call `after_commit`: it records the commits on their tasks and lists what is pending.

## 7. Clean and merge

- Show the user the pending tasks and the done items that can be cleaned; archive only those the user
  confirms with `clean_done` **(user)**.
- When the work planned for the branch is all done and committed, `after_commit` merges it into main
  (`--no-ff`) and says how it went. On a conflict nothing is merged: show git's message to the user.
  `merge_branch` merges by hand when the user asks.

## Commits made outside this flow

Commits made from the terminal or an IDE become tasks of the Reviews plan. Go through them with the
user; once approved they are done.
