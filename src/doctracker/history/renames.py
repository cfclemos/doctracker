"""Renames and moves of the project's classes and functions between two versions of the code.

Each changed Python file is read in both versions with `ast` (the older one from git, never
imported): an entity gone from the older version and one that appeared in the newer are paired when
the newer has the same body under another name (renamed), or the same name elsewhere and no other
entity took it (moved). The methods of a renamed or moved class follow it and are not listed apart;
so does the content of a module whose file git saw renamed (the module is listed as moved).
"""

import ast
import hashlib
from pathlib import Path

from doctracker.history import working


def source_roots(entities: dict[str, dict]) -> set[str]:
    """The folders the packages are found in, from the extracted modules (e.g. `src/`).

    Args:
        entities: Extracted entities, by path; modules carry their `filepath`, relative to the project root.

    Returns:
        Each folder relative to the project root, with a trailing slash (empty for the root itself).
    """
    roots = set()
    for path, entity in entities.items():
        if entity.get("kind") != "module" or not entity.get("filepath"):
            continue
        file = entity["filepath"]
        tail = path.replace(".", "/") + ("/__init__.py" if file.endswith("__init__.py") else ".py")
        if file.endswith(tail):
            roots.add(file[: -len(tail)])
    return roots


def module_path(file: str, roots: set[str]) -> str | None:
    """The dotted path of a Python file of the project (`src/pkg/mod.py` → `pkg.mod`); None outside the roots."""
    if not file.endswith(".py"):
        return None
    for root in sorted(roots, key=len, reverse=True):
        if file.startswith(root):
            parts = file[len(root): -len(".py")].split("/")
            return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)
    return None


def entities_of(source: str, module: str) -> dict[str, tuple[str, str]]:
    """The classes and functions (methods included) of a module's source, with a hash of their body.

    Args:
        source: The module's code.
        module: Its dotted path.

    Returns:
        `{path: (kind, hash)}`, `kind` being `class` or `function`; empty when the code does not parse.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    found = {}

    def visit(nodes: list[ast.stmt], prefix: str) -> None:
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(node, ast.ClassDef) else "function"
                signature = node.bases if kind == "class" else [node.args, node.returns]
                body = ast.dump(ast.Module(body=node.body, type_ignores=[])) + "".join(
                    ast.dump(part) for part in signature if part is not None)
                found[f"{prefix}.{node.name}"] = (kind, hashlib.sha1(body.encode("utf-8")).hexdigest())
                if kind == "class":
                    visit(node.body, f"{prefix}.{node.name}")

    visit(tree.body, module)
    return found


def pair_renames(older: dict[str, tuple[str, str]], newer: dict[str, tuple[str, str]]) -> list[dict]:
    """Pair the entities gone from the older version with those that appeared in the newer one.

    Args:
        older: `entities_of` the older version of the changed files, merged.
        newer: The same for the newer version.

    Returns:
        `[{"old", "new", "how"}]`, `how` being `renamed` (same body) or `moved` (same name), sorted by `old`.
    """
    gone = [path for path in older if path not in newer]
    appeared = {path for path in newer if path not in older}
    pairs = {}
    for path in gone:
        same_body = [new for new in appeared if newer[new] == older[path]]
        if len(same_body) == 1:
            pairs[path] = (same_body[0], "renamed" if same_body[0].rsplit(".", 1)[1] != path.rsplit(".", 1)[1]
                           else "moved")
            appeared.discard(same_body[0])
    for path in gone:
        if path in pairs:
            continue
        name, kind = path.rsplit(".", 1)[1], older[path][0]
        same_name = [new for new in appeared if new.rsplit(".", 1)[1] == name and newer[new][0] == kind]
        if len(same_name) == 1:
            pairs[path] = (same_name[0], "moved")
            appeared.discard(same_name[0])
    # The members of a class that was paired follow it: only the class is listed.
    followed = {old for old, (new, _) in pairs.items()
                for parent_old, (parent_new, _) in pairs.items()
                if old.startswith(f"{parent_old}.") and new.startswith(f"{parent_new}.")}
    return [{"old": old, "new": new, "how": how} for old, (new, how) in sorted(pairs.items()) if old not in followed]


async def detect_renames(top: Path, project_root: Path, roots: set[str], files: list[dict],
                         older: str = "HEAD", newer: str = "") -> list[dict]:
    """The renames and moves among changed files, between two versions of the code.

    Args:
        top: Top folder of the repository (the paths in `files` are relative to it).
        project_root: Root of the project.
        roots: `source_roots` of the project, relative to its root.
        files: Changed files, `path`, `status` and `old_path` for a renamed file, as `working.changed_files`.
        older: The older version: a commit (`HEAD` for the last one).
        newer: The newer version: a commit, or empty for the working tree.

    Returns:
        What `pair_renames` gives.
    """
    prefix = project_root.resolve().relative_to(top.resolve()).as_posix()
    prefix = "" if prefix == "." else f"{prefix}/"

    def module(path: str) -> str | None:
        return module_path(path[len(prefix):], roots) if path.startswith(prefix) else None

    before, after, modules = {}, {}, {}
    for file in files:
        if file["status"] == "renamed" and (old := module(file["old_path"])) and (new := module(file["path"])):
            modules[old] = new
        old_path = file.get("old_path", file["path"])
        if file["status"] != "added" and (name := module(old_path)):
            source = await working.file_at(top, older, old_path)
            if source is not None:
                before.update(entities_of(source, name))
        if file["status"] != "deleted" and (name := module(file["path"])):
            if newer:
                source = await working.file_at(top, newer, file["path"])
            else:
                try:
                    source = (top / file["path"]).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    source = None
            if source is not None:
                after.update(entities_of(source, name))
    # A module whose file git saw renamed moved, and what it holds follows it: only the module is listed.
    paired = [{"old": old, "new": new, "how": "moved"} for old, new in modules.items() if old != new]
    paired += [entry for entry in pair_renames(before, after)
               if not any(entry["old"].startswith(f"{old}.") and entry["new"].startswith(f"{new}.")
                          for old, new in modules.items())]
    return sorted(paired, key=lambda entry: entry["old"])
