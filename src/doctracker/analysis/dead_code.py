"""Dead code: what nothing in the project uses, from the code graph and vulture together.

Each one errs where the other does not. The graph knows who uses what, through calls, references,
templates, CSS classes and routes, but misses what it cannot resolve (dynamic attributes, calls on
returned values). vulture (MIT) only compares names, so it sees those, but a name used anywhere
saves every entity with that name. A Python function or class is `unused` only when both agree;
one its package offers (`__all__`, re-exported) is `public, unused inside` when the graph finds no use.
vulture alone judges what the graph has no data for: variables, attributes, properties, imports
and unreachable code. The front-end is judged by the graph alone, and a CSS class or template
whose name the Python code writes as a string may be used through data.

The project's code is read, never run.
"""

import ast
import re
from pathlib import Path

from vulture import Vulture

VERDICTS = ("unused", "public, unused inside", "front-end unused", "maybe used by data", "vulture only")
"""What a row says, from the surest to the least sure."""

DEAD_KINDS = ("function", "class", "variable", "attribute", "property", "import", "unreachable code",
              "js function", "css class", "template", "macro")
"""The kinds of the rows, for the filters."""

_PYTHON_KINDS = ("function", "class")
_FRONTEND_KINDS = ("js function", "css class", "template", "macro")
_VULTURE_ONLY = {"variable": "variable", "attribute": "attribute", "property": "property", "import": "import",
                 "unreachable_code": "unreachable code"}
_WORD = re.compile(r"[A-Za-z_][\w-]*")


def scan(root: Path, entities: dict[str, dict], edges: list[dict]) -> list[dict]:
    """Find the dead code of the project.

    Runs in the extraction worker process, after the graph is built.

    Args:
        root: Project root.
        entities: Every extracted entity, Python and front-end, by path.
        edges: The relations of the graph.

    Returns:
        One row per finding, sorted by file and line: `path` (the entity, or `file:line` for what
        is not one), `name`, `kind` (see `DEAD_KINDS`), `verdict` (see `VERDICTS`), `confidence`
        (0 to 100), `used_by` (how many relations reach it), `file`, `line` and `message`.
    """
    root = root.resolve()
    used_by: dict[str, int] = {}
    for edge in edges:
        if edge["kind"] != "contains" and edge["source"] != edge["target"]:
            used_by[edge["target"]] = used_by.get(edge["target"], 0) + 1
    files = sorted({entity["filepath"] for entity in entities.values()
                    if entity["kind"] == "module" and str(entity["filepath"]).endswith(".py")})
    found = _vulture(root, files)
    exported = _exported(entities)
    strings = _python_strings(root, files)
    rows = []
    for path, entity in entities.items():
        kind = entity["kind"]
        if used_by.get(path) or kind not in _PYTHON_KINDS + _FRONTEND_KINDS:
            continue
        if kind in _PYTHON_KINDS:
            if _special(entity):
                continue
            if path in exported:  # vulture counts a name in `__all__` as used: the graph alone decides
                rows.append(_row(path, entity, kind, "public, unused inside", 60,
                                 "offered by its package, but nothing in the project uses it"))
                continue
            seen = found.get((_relative(root, entity["filepath"]), entity["name"]))
            agreeing = [item for item in seen or [] if item.typ in ("function", "method", "class")
                        and entity["lineno"] <= item.first_lineno <= (entity["endlineno"] or entity["lineno"])]
            if not agreeing:
                continue  # vulture saw the name used somewhere: maybe alive
            rows.append(_row(path, entity, kind, "unused", agreeing[0].confidence, agreeing[0].message))
        else:
            name = entity["name"].lstrip(".").removesuffix(".html")
            data = kind in ("css class", "template") and name in strings
            verdict = "maybe used by data" if data else "front-end unused"
            message = (f"'{name}' is written as a string in the Python code" if data
                       else f"no use of this {kind} in the project")
            rows.append(_row(path, entity, kind, verdict, 60 if data else 100, message))
    for (file, _), items in found.items():
        for item in items:
            if item.typ in _VULTURE_ONLY:
                rows.append({"path": f"{file}:{item.first_lineno}", "name": item.name, "kind": _VULTURE_ONLY[item.typ],
                             "verdict": "vulture only", "confidence": item.confidence, "used_by": 0, "file": file,
                             "line": item.first_lineno, "message": item.message})
    return sorted(rows, key=lambda row: (row["file"], row["line"], row["name"]))


def filter_rows(rows: list[dict], prefix: str = "", verdict: str = "", kind: str = "",
                min_confidence: int = 0) -> list[dict]:
    """Keep the rows matching the filters; empty filters keep everything.

    Args:
        rows: What `scan` gave.
        prefix: Only paths starting with it (`doctracker.wiki`, `doctracker/wiki/static`) or files starting with it.
        verdict: Only this verdict (see `VERDICTS`).
        kind: Only this kind (see `DEAD_KINDS`).
        min_confidence: Only rows at least this sure (0 to 100).

    Returns:
        The rows kept, in the same order.
    """
    return [row for row in rows
            if (not prefix or row["path"].startswith(prefix) or row["file"].startswith(prefix))
            and (not verdict or row["verdict"] == verdict) and (not kind or row["kind"] == kind)
            and row["confidence"] >= min_confidence]


def _row(path: str, entity: dict, kind: str, verdict: str, confidence: int, message: str) -> dict:
    """A finding about an entity."""
    return {"path": path, "name": entity["name"], "kind": kind, "verdict": verdict, "confidence": confidence,
            "used_by": 0, "file": entity["filepath"], "line": entity["lineno"] or 0, "message": message}


def _special(entity: dict) -> bool:
    """Whether a Python function or class is alive by its form: a dunder, or decorated (registered somewhere)."""
    name = entity["name"]
    return (name.startswith("__") and name.endswith("__")) or bool(entity.get("decorators"))


def _relative(root: Path, file: str) -> str:
    """A file path relative to the project root, with forward slashes."""
    path = (root / file).resolve()
    return path.relative_to(root).as_posix() if path.is_relative_to(root) else Path(file).as_posix()


def _vulture(root: Path, files: list[str]) -> dict[tuple[str, str], list]:
    """vulture's findings on the project's Python files, by (file relative to the root, name)."""
    scanner = Vulture()
    scanner.scavenge([str((root / file).resolve()) for file in files])
    found: dict[tuple[str, str], list] = {}
    for item in scanner.get_unused_code(min_confidence=0):
        found.setdefault((_relative(root, str(item.filename)), item.name), []).append(item)
    return found


def _exported(entities: dict[str, dict]) -> set[str]:
    """The entities a package offers: listed in their module's `__all__`, or imported by a package's `__init__`."""
    offered = set()
    for path, entity in entities.items():
        if entity["kind"] != "module":
            continue
        offered |= {f"{path}.{name}" for name in entity.get("exports", [])}
        if entity.get("is_package"):
            offered |= set(entity.get("imports", {}).values())
    return offered


def _python_strings(root: Path, files: list[str]) -> set[str]:
    """Every word written inside a string in the Python code (CSS class and template names built from data)."""
    words = set()
    for file in files:
        try:
            tree = ast.parse((root / file).read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                words |= set(_WORD.findall(node.value))
    return words
