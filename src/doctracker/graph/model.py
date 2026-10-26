"""Thematic views of the code graph, shared by the wiki pages and the MCP tools.

- architecture: packages and modules, and which module imports which (import cycles marked);
- classes: a UML class diagram (members, inheritance, composition, use);
- calls: the call neighborhood of one function, method or class;
- entity history: the commits that changed an entity's file.
"""

import re
from pathlib import Path

from doctracker.history import read_history
from doctracker.server.state import DocState
from doctracker.wiki.pages import SYMBOLS, page_role, signature_details, summary

CALL_DIRECTIONS = ("both", "out", "in")
"""Directions of a call graph: callees and callers, callees only (`out`), callers only (`in`)."""

MAX_CALL_DEPTH = 3
"""Deepest call neighborhood: beyond this the graph stops being readable."""


def _node(state: DocState, path: str, **extra: object) -> dict:
    """Describe one entity as a graph node.

    Args:
        state: Extracted entities.
        path: Entity path.
        **extra: More fields for the node (e.g. its parent box, its distance to the focus).

    Returns:
        `id` (the path), `label`, `role`, `symbol`, `summary` and the extra fields.
    """
    entity = state.entities[path]
    role = page_role(state, entity)
    return {"id": path, "label": entity["name"], "role": role, "symbol": SYMBOLS.get(role, ""),
            "summary": summary(entity), **extra}


def _edges_of(state: DocState, kind: str) -> list[dict]:
    """Relations of one kind whose ends both exist.

    Args:
        state: Extracted entities and relations.
        kind: Relation kind, e.g. `imports`.

    Returns:
        The relations (`source`, `target`, `kind`).
    """
    return [e for e in state.edges if e["kind"] == kind and e["source"] in state.entities and e["target"] in state.entities]


def _package_of(state: DocState, path: str) -> str:
    """Find the package a module belongs to (a package belongs to itself).

    Args:
        state: Extracted entities.
        path: Module path.

    Returns:
        Path of the package.
    """
    entity = state.entities[path]
    return path if entity.get("is_package") else (entity["parent"] or path)


def architecture(state: DocState, level: str = "modules") -> dict:
    """Build the architecture view: packages and modules, linked by imports.

    Modules are drawn inside the box of their package. Imports that are part of a
    cycle (modules importing each other, directly or through others) are marked.

    Args:
        state: Extracted entities and relations.
        level: `modules` (every module) or `packages` (modules merged into their package).

    Returns:
        `nodes` (with `parent` = enclosing package) and `edges` (`imports`, with `cycle`
        and, at package level, `weight` = number of module imports merged).
    """
    modules = [path for path, entity in state.entities.items() if entity["kind"] == "module"]
    if level == "packages":
        owner = {path: _package_of(state, path) for path in modules}
        kept = sorted(set(owner.values()))
    else:
        owner = {path: path for path in modules}
        kept = modules
    nodes = []
    for path in kept:
        parent = state.entities[path]["parent"]
        nodes.append(_node(state, path, parent=parent if parent in kept else None))
    weights: dict[tuple[str, str], int] = {}
    for edge in _edges_of(state, "imports"):
        source, target = owner.get(edge["source"]), owner.get(edge["target"])
        if source and target and source != target:
            weights[(source, target)] = weights.get((source, target), 0) + 1
    in_cycle = _cycle_edges(set(weights))
    edges = [
        {"id": f"imports:{s}->{t}", "source": s, "target": t, "kind": "imports", "weight": w, "cycle": (s, t) in in_cycle}
        for (s, t), w in sorted(weights.items())
    ]
    return {"nodes": nodes, "edges": edges}


def _cycle_edges(edges: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Find the edges that are part of a cycle (both ends in the same strongly connected group).

    Args:
        edges: Directed `(source, target)` pairs.

    Returns:
        The pairs that belong to a cycle.
    """
    graph: dict[str, list[str]] = {}
    for source, target in edges:
        graph.setdefault(source, []).append(target)
        graph.setdefault(target, [])
    index, low, group = {}, {}, {}
    stack, on_stack, counter = [], set(), [0]

    def visit(start: str) -> None:
        # Iterative Tarjan: each frame is (node, iterator over its successors).
        frames = [(start, iter(graph[start]))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        while frames:
            node, successors = frames[-1]
            for target in successors:
                if target not in index:
                    index[target] = low[target] = counter[0]
                    counter[0] += 1
                    stack.append(target)
                    on_stack.add(target)
                    frames.append((target, iter(graph[target])))
                    break
                if target in on_stack:
                    low[node] = min(low[node], index[target])
            else:
                frames.pop()
                if frames:
                    low[frames[-1][0]] = min(low[frames[-1][0]], low[node])
                if low[node] == index[node]:
                    members = []
                    while True:
                        member = stack.pop()
                        on_stack.discard(member)
                        members.append(member)
                        if member == node:
                            break
                    for member in members:
                        group[member] = (node, len(members))

    for node in graph:
        if node not in index:
            visit(node)
    return {(s, t) for s, t in edges if group[s][0] == group[t][0] and group[s][1] > 1}


TYPE_ICONS = {
    "bool": "bool",
    **dict.fromkeys(("int", "float", "complex", "Decimal", "Fraction"), "number"),
    **dict.fromkeys(("str", "bytes"), "text"),
    **dict.fromkeys(("datetime", "date", "time", "timedelta"), "time"),
    **dict.fromkeys(("Path", "PurePath"), "path"),
    **dict.fromkeys(("list", "dict", "set", "tuple", "frozenset", "deque", "defaultdict", "OrderedDict", "Counter",
                     "Sequence", "Mapping", "MutableMapping", "Iterable", "Collection"), "collection"),
}
"""Icon of an attribute by the first type named in its hint (`str | None` → `text`); others are `other`."""

STEREOTYPES = {
    **dict.fromkeys(("Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"), "enum"),
    "Protocol": "protocol",
    "ABC": "abstract",
    "NamedTuple": "namedtuple",
    "TypedDict": "typeddict",
}
"""UML stereotype of a class by one of its bases (exceptions and dataclasses are found apart)."""

METHOD_KINDS = ("staticmethod", "classmethod", "property", "abstractmethod")
"""Decorators that tell the kind of a method."""


def _type_icon(annotation: str, holds_class: bool) -> str:
    """Tell the icon of an attribute from its type hint.

    Args:
        annotation: Type hint as written, e.g. `list[str] | None`.
        holds_class: Whether it holds a class of the project.

    Returns:
        `class`, one of the `TYPE_ICONS` values, or `other`.
    """
    if holds_class:
        return "class"
    for name in re.findall(r"[A-Za-z_]\w*", annotation):
        if name not in ("None", "Optional", "typing", "collections", "abc", "datetime", "pathlib", "decimal"):
            return TYPE_ICONS.get(name, "other")
    return TYPE_ICONS.get(annotation.rsplit(".", 1)[-1], "other")


def _stereotype(entity: dict) -> str:
    """Tell the UML stereotype of a class: dataclass, enum, protocol, abstract, exception...

    Args:
        entity: Extracted class.

    Returns:
        The stereotype name, or an empty string.
    """
    if any(decorator.split("(")[0].rsplit(".", 1)[-1] == "dataclass" for decorator in entity["decorators"]):
        return "dataclass"
    for base in entity["bases"]:
        name = base.split("[")[0].rsplit(".", 1)[-1]
        if name in STEREOTYPES:
            return STEREOTYPES[name]
        if name.endswith(("Exception", "Error")):
            return "exception"
    return ""


def class_diagram(state: DocState, package: str = "") -> dict:
    """Build a UML class diagram.

    Each class lists its attributes (name, type and an icon for the type) and its methods
    (name and full signature). Relations: inheritance, composition (an attribute holds
    another class; `via` names the attribute) and use (a method calls another class or one
    of its methods).

    Args:
        state: Extracted entities and relations.
        package: Only classes under this path (e.g. `pkg.server`); empty means all.

    Returns:
        `nodes` (class path, `stereotype`, `attributes`: name, type, icon, target class;
        `methods`: name, signature, kind) and `edges` (`inherits`, `has` with `via`, `uses`).
    """
    classes = [
        path for path, entity in state.entities.items()
        if entity["kind"] == "class" and (not package or path == package or path.startswith(package + "."))
    ]
    kept = set(classes)
    held = {edge["via"]: edge["target"] for edge in _edges_of(state, "has")}  # attribute path -> class it holds
    nodes = []
    for path in classes:
        attributes, methods = [], []
        stereotype = _stereotype(state.entities[path])
        for member in state.entities[path]["members"]:
            entity = state.entities[member]
            if stereotype == "dataclass" and entity["name"] == "__init__":
                continue  # generated from the fields, which are listed already
            if entity["kind"] == "attribute":
                target = held.get(member, "")
                annotation = entity.get("annotation", "")
                attributes.append({
                    "name": entity["name"],
                    "type": annotation or (state.entities[target]["name"] if target else ""),
                    "icon": _type_icon(annotation, bool(target)),
                    "target": target if target in kept else "",
                })
            elif entity["kind"] == "function":
                decorators = [decorator.rsplit(".", 1)[-1] for decorator in entity["decorators"]]
                methods.append({
                    "name": entity["name"],
                    "signature": f"{entity['name']}{signature_details(entity)}",
                    "kind": next((kind for kind in METHOD_KINDS if kind in decorators), ""),
                })
        nodes.append(_node(state, path, stereotype=stereotype, attributes=attributes, methods=methods))
    edges, seen = [], set()
    for edge in _edges_of(state, "inherits"):
        if edge["source"] in kept and edge["target"] in kept:
            edges.append({"id": f"inherits:{edge['source']}->{edge['target']}", **edge})
            seen.add((edge["source"], edge["target"]))
    for edge in _edges_of(state, "has"):
        if edge["source"] in kept and edge["target"] in kept:
            via = state.entities[edge["via"]]["name"]
            edges.append({"id": f"has:{edge['source']}.{via}->{edge['target']}", **edge, "via": via})
            seen.add((edge["source"], edge["target"]))
    for edge in _edges_of(state, "calls"):
        source = _class_of(state, edge["source"])
        target = _class_of(state, edge["target"])
        if source in kept and target in kept and source != target and (source, target) not in seen:
            seen.add((source, target))
            edges.append({"id": f"uses:{source}->{target}", "source": source, "target": target, "kind": "uses"})
    return {"nodes": nodes, "edges": edges}


def _class_of(state: DocState, path: str) -> str | None:
    """Find the class an entity is or belongs to (a method belongs to its class).

    Args:
        state: Extracted entities.
        path: Entity path.

    Returns:
        The class path, or `None` for module-level functions and other entities.
    """
    entity = state.entities[path]
    if entity["kind"] == "class":
        return path
    parent = state.entities.get(entity["parent"] or "")
    return entity["parent"] if parent and parent["kind"] == "class" else None


def call_graph(state: DocState, focus: str, depth: int = 1, direction: str = "both") -> dict:
    """Build the call neighborhood of one function, method or class.

    Args:
        state: Extracted entities and relations.
        focus: Path of the entity in the center.
        depth: How many calls away to go (1 to `MAX_CALL_DEPTH`).
        direction: `out` (what it calls), `in` (what calls it) or `both`.

    Returns:
        `nodes` (with `distance` from the focus and `side`: `focus`, `callee` or `caller`)
        and `edges` (`calls`); both empty when `focus` is unknown.
    """
    if focus not in state.entities:
        return {"nodes": [], "edges": []}
    depth = max(1, min(depth, MAX_CALL_DEPTH))
    calls = _edges_of(state, "calls")
    callees: dict[str, list[str]] = {}
    callers: dict[str, list[str]] = {}
    for edge in calls:
        callees.setdefault(edge["source"], []).append(edge["target"])
        callers.setdefault(edge["target"], []).append(edge["source"])
    found = {focus: (0, "focus")}
    walks = [("callee", callees)] if direction == "out" else [("caller", callers)] if direction == "in" else [
        ("callee", callees), ("caller", callers)]
    for side, neighbors in walks:
        frontier = [focus]
        for distance in range(1, depth + 1):
            reached = []
            for path in frontier:
                for neighbor in neighbors.get(path, []):
                    if neighbor not in found:
                        found[neighbor] = (distance, side)
                        reached.append(neighbor)
            frontier = reached
    nodes = [_node(state, path, distance=distance, side=side) for path, (distance, side) in found.items()]
    edges = [
        {"id": f"calls:{e['source']}->{e['target']}", **e}
        for e in calls
        if e["source"] in found and e["target"] in found
    ]
    return {"nodes": nodes, "edges": edges}


async def entity_history(state: DocState, project_root: Path, path: str, limit: int = 20) -> list[dict] | None:
    """List the commits that touched the file of an entity, newest first.

    Args:
        state: Extracted entities.
        project_root: Root of the documented project.
        path: Entity path; its module's file is used.
        limit: Most recent commits to list.

    Returns:
        Commits (short hash, author, date, subject, body); `None` when git or the repository
        is missing, or the entity is unknown.
    """
    entity = state.entities.get(path)
    if entity is None or not entity["filepath"]:
        return None
    commits = await read_history(project_root, limit, entity["filepath"])
    if commits is None:
        return None
    return [{"hash": c.hash, "short": c.short, "author": c.author, "date": c.date, "subject": c.subject, "body": c.body}
            for c in commits]
