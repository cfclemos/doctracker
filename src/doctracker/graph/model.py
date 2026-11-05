"""Thematic views of the code graph, shared by the wiki pages and the MCP tools.

- architecture: packages and modules, and which module imports which (import cycles marked);
- classes: a UML class diagram (members, inheritance, composition, use);
- calls: the call neighborhood of one function, method or class;
- entity history: the commits that changed an entity's file.
"""

import re
from pathlib import Path

from doctracker.extraction.languages import language_label
from doctracker.history import read_history
from doctracker.server.state import DocState
from doctracker.wiki.pages import CLASS_KINDS, SYMBOLS, group_of, page_role, project_groups, signature_details, summary

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
        `id` (the path), `label`, `role`, `symbol`, `summary`, `language` (and its name, `language_label`),
        `filepath` (the file it is in) and the extra fields.
    """
    entity = state.entities[path]
    role = page_role(state, entity)
    return {"id": path, "label": entity["name"], "role": role, "symbol": SYMBOLS.get(role, ""),
            "summary": summary(entity), "language": entity["language"],
            "language_label": language_label(entity["language"]), "filepath": entity["filepath"], **extra}


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


def _in_projects(state: DocState, nodes: list[dict], apart: str) -> list[dict]:
    """Put the top-level nodes of a diagram in their projects (the tree's), as frames above them.

    Args:
        state: Extracted entities.
        nodes: The diagram's nodes; those without a parent get their project as parent (in place).
        apart: A folder whose projects go in a group of their own (see `project_groups`).

    Returns:
        The project frames (and the group of `apart`) that hold something, to add to the nodes.
    """
    groups = project_groups(state, apart)
    # A namespace package spread over several members of a monorepo is split: what it holds goes into
    # the member it lies in, and the namespace itself is not drawn.
    for node in list(nodes):
        entity = state.entities.get(node.get("page") or node["id"])
        if not node.get("frame") or entity is None or len(entity.get("folders") or []) < 2:
            continue
        places = {group_of({**entity, "folders": [folder]}, groups) for folder in entity["folders"]}
        if len(places) < 2:
            continue
        nodes.remove(node)
        nodes[:] = [child for child in nodes if child["id"] != f"{node['id']}.__init__"]  # it has no file of its own
        for child in nodes:
            if child.get("parent") == node["id"]:
                child["parent"] = None
    used = set()
    for node in nodes:
        entity = state.entities.get(node.get("page") or node["id"])
        if node.get("parent") or entity is None:
            continue
        node["parent"] = group_of(entity, groups)
        used.add(node["parent"])
    by_id = {group["id"]: group for group in groups}
    for group in list(used):
        while group and by_id.get(group, {}).get("parent"):
            group = by_id[group]["parent"]
            used.add(group)
    return [{"id": group["id"], "label": group["label"], "role": group["role"], "symbol": "", "page": group["page"],
             "summary": f"{group['label']}: {', '.join(group['folders'])}", "parent": group["parent"], "frame": True}
            for group in groups if group["id"] in used]


ARCHITECTURE_KINDS = ("imports", "uses", "calls", "refers", "inherits", "has")
"""Relations drawn between files in the architecture, each its own line: what a file imports, the
templates and CSS classes it uses, what its code calls, refers to, inherits from or holds."""


def architecture(state: DocState, level: str = "modules", apart: str = "", project: str = "", focus: str = "",
                 depth: int = MAX_CALL_DEPTH, kinds: tuple[str, ...] = ARCHITECTURE_KINDS) -> dict:
    """Build the architecture view: packages, subpackages and modules, linked by imports.

    At module level, packages and subpackages are frames (`frame` is true) and every
    module is a box inside its package's frame, the package's own `__init__.py` included
    (its box id is `<package>.__init__`, so its imports start from it, not from the frame).
    Imports between modules are directed, and the ones that are part of a cycle (importing
    each other, directly or through others) are marked. At package level, each package is a
    box and each pair of packages gets one undirected link: `weight` counts the module imports
    between them both ways, `counts` splits them by direction.

    Args:
        state: Extracted entities and relations.
        level: `modules` (every module) or `packages` (modules merged into their package).
        apart: At module level, a folder whose projects go in a group of their own (`examples` in
            doctracker's own repository, as in the tree).
        project: At module level, only this project (`project:<name>`, as in the nodes); empty for all.
        focus: At module level, only this module (or file) and those `depth` relations away from it.
        depth: How many relations away from `focus`.
        kinds: The relations drawn, a part of `ARCHITECTURE_KINDS`.

    Returns:
        `nodes` (`role`: package, subpackage or module; `parent`: enclosing frame; `frame`;
        `page`: entity path of its wiki page) and `edges` (`imports`, with `directed`,
        `weight`, `cycle` and, at package level, `counts` by `"source->target"`).
    """
    modules = [path for path, entity in state.entities.items() if entity["kind"] == "module"]
    packages = [path for path in modules if state.entities[path].get("is_package")]
    nodes = []
    if level == "packages":
        owner = {path: _package_of(state, path) for path in modules}
        for path in sorted(set(owner.values())):
            node = _node(state, path, parent=None, frame=False, page=path)
            if path in state.roots:
                # Subpackages have boxes of their own: the root's box stands for its own modules only.
                files = sorted(Path(state.entities[module]["filepath"]).name for module, package in owner.items()
                               if package == path)
                node.update(label=f"{node['label']} (root modules)", summary=f"Modules: {', '.join(files)}")
            nodes.append(node)
    else:
        owner = {path: f"{path}.__init__" if path in packages else path for path in modules}
        for path in packages:
            parent = state.entities[path]["parent"]
            nodes.append(_node(state, path, parent=parent if parent in packages else None, frame=True, page=path))
        for path in modules:
            node = _node(state, path, parent=path if path in packages else state.entities[path]["parent"],
                         frame=False, page=path)
            node.update(id=owner[path], role="module", label=Path(state.entities[path]["filepath"]).name)
            nodes.append(node)
    weights: dict[tuple[str, str], int] = {}
    for edge in _edges_of(state, "imports"):
        source, target = owner.get(edge["source"]), owner.get(edge["target"])
        if source and target and source != target:
            weights[(source, target)] = weights.get((source, target), 0) + 1
    if level != "packages":
        return _file_relations(state, nodes, owner, weights, apart, project, focus, depth, kinds)
    if level == "packages":
        # One undirected link per pair of packages: how much they depend on each other, both ways.
        pairs: dict[tuple[str, str], dict[str, int]] = {}
        for (source, target), weight in weights.items():
            pairs.setdefault(tuple(sorted((source, target))), {})[f"{source}->{target}"] = weight
        edges = [
            {"id": f"imports:{a}--{b}", "source": a, "target": b, "kind": "imports", "directed": False,
             "weight": sum(counts.values()), "counts": counts, "cycle": False}
            for (a, b), counts in sorted(pairs.items())
        ]
        return {"nodes": nodes, "edges": edges}
    return {"nodes": nodes, "edges": []}  # not reached: the module level returns above


def _file_relations(state: DocState, nodes: list[dict], owner: dict[str, str], imports: dict[tuple[str, str], int],
                    apart: str, project: str, focus: str, depth: int, kinds: tuple[str, ...]) -> dict:
    """The module level of the architecture: every relation between files, the filters, the cycles.

    Args:
        state: Extracted entities and relations.
        nodes: The packages (frames) and modules (boxes); put in their projects here.
        owner: Box of each module (a package's own module is `<package>.__init__`).
        imports: Imports between boxes, with how many.
        apart, project, focus, depth, kinds: As in `architecture`.

    Returns:
        `nodes`, `edges` (one per pair of boxes and kind, with `weight`; imports also `cycle`) and
        `cycles` (the boxes of each import cycle).
    """
    nodes += _in_projects(state, nodes, apart)
    weights: dict[tuple[str, str, str], int] = {(s, t, "imports"): w for (s, t), w in imports.items()}

    def box_of(path: str) -> str | None:  # the box of the file an entity is in
        while path and path in state.entities and state.entities[path]["kind"] != "module":
            path = state.entities[path]["parent"]
        return owner.get(path)

    for kind in ARCHITECTURE_KINDS[1:]:
        for edge in _edges_of(state, kind):
            source, target = box_of(edge["source"]), box_of(edge["target"])
            if source and target and source != target:
                weights[(source, target, kind)] = weights.get((source, target, kind), 0) + 1
    in_cycle, cycles = _cycles(set(imports))
    pairs = [(s, t) for s, t, kind in weights if kind in kinds]
    nodes = _filtered(nodes, pairs, project, (owner.get(focus) or focus) if focus else "", depth)
    keep = {node["id"] for node in nodes if not node["frame"]}
    edges = [
        {"id": f"{kind}:{s}->{t}", "source": s, "target": t, "kind": kind, "directed": True, "weight": w,
         "cycle": kind == "imports" and (s, t) in in_cycle}
        for (s, t, kind), w in sorted(weights.items()) if kind in kinds and s in keep and t in keep
    ]
    return {"nodes": nodes, "edges": edges, "cycles": [members for members in cycles if set(members) <= keep]}


def _filtered(nodes: list[dict], pairs: list[tuple[str, str]], project: str, focus: str, depth: int) -> list[dict]:
    """Keep the boxes of a diagram that pass its filters, and the frames that still hold one of them.

    Args:
        nodes: The diagram's boxes and frames, already in their projects.
        pairs: The relations between boxes, to find the neighbours of `focus`.
        project: Only the boxes inside this project (`project:<name>`); empty for all.
        focus: Only this box and those `depth` relations away from it; empty for all.
        depth: How many relations away from `focus`.

    Returns:
        The nodes kept, in their order.
    """
    by_id = {node["id"]: node for node in nodes}
    ancestors = lambda node_id: [] if not by_id.get(node_id, {}).get("parent") else [by_id[node_id]["parent"], *ancestors(by_id[node_id]["parent"])]
    keep = {node["id"] for node in nodes if not node["frame"]}
    if project:
        keep = {node_id for node_id in keep if project in ancestors(node_id)}
    if focus:
        neighbours: dict[str, set[str]] = {}
        for source, target in pairs:
            neighbours.setdefault(source, set()).add(target)
            neighbours.setdefault(target, set()).add(source)
        reached = frontier = {focus} if focus in by_id else set()
        for _ in range(max(1, depth)):
            frontier = {other for node_id in frontier for other in neighbours.get(node_id, ())} - reached
            reached = reached | frontier
        keep &= reached
    holding = {ancestor for node_id in keep for ancestor in ancestors(node_id)}
    return [node for node in nodes if node["id"] in keep or node["id"] in holding]


def _cycles(edges: set[tuple[str, str]]) -> tuple[set[tuple[str, str]], list[list[str]]]:
    """Find the cycles of a directed graph (its strongly connected groups of more than one node).

    Args:
        edges: Directed `(source, target)` pairs.

    Returns:
        The pairs that belong to a cycle, and the nodes of each cycle (sorted, the biggest cycle first).
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
    members: dict[str, list[str]] = {}
    for node, (root, size) in group.items():
        if size > 1:
            members.setdefault(root, []).append(node)
    cycles = sorted((sorted(nodes) for nodes in members.values()), key=lambda nodes: (-len(nodes), nodes))
    return {(s, t) for s, t in edges if group[s][0] == group[t][0] and group[s][1] > 1}, cycles


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
    if entity.get("kind_label") in CLASS_KINDS:  # another language's interface, struct, enum, trait, impl
        return entity["kind_label"]
    if any(decorator.split("(")[0].rsplit(".", 1)[-1] == "dataclass" for decorator in entity["decorators"]):
        return "dataclass"
    for base in entity["bases"]:
        name = base.split("[")[0].rsplit(".", 1)[-1]
        if name in STEREOTYPES:
            return STEREOTYPES[name]
        if name.endswith(("Exception", "Error")):
            return "exception"
    return ""


CLASS_RELATIONS = ("inherits", "implements", "has", "uses", "refers")
"""Relations drawn between classes, each its own line."""

IMPLEMENTED = ("interface", "trait", "protocol")
"""Stereotypes of a class that others implement instead of extending: a base with one is `implements`."""


def class_paths(state: DocState) -> list[str]:
    """List what the class diagram holds: classes and what goes with them (interfaces, structs, enums,
    traits) of any language; not SQL tables nor Rust `impl` blocks, which are not types of their own.

    Args:
        state: Extracted entities.

    Returns:
        Their paths, sorted.
    """
    return sorted(path for path, entity in state.entities.items() if entity["kind"] == "class"
                  and entity["language"] != "sql" and entity.get("kind_label") != "impl")


def class_diagram(state: DocState, package: str = "", apart: str = "", project: str = "", focus: str = "",
                  depth: int = MAX_CALL_DEPTH) -> dict:
    """Build a UML class diagram.

    Each class lists its attributes (name, type and an icon for the type) and its methods
    (name and full signature). Relations: inheritance, implementation (the base is an interface,
    a trait or a protocol), composition (an attribute holds another class; `via` names the
    attribute), use (a method calls another class or one of its methods) and reference (a class
    named without being called, e.g. as a type). Only what `class_paths` lists is drawn.

    Args:
        state: Extracted entities and relations.
        package: Only classes under this path (e.g. `pkg.server`); empty means all.
        apart: A folder whose projects go in a group of their own (see `architecture`).
        project: Only the classes of this project (`project:<name>`, as in the nodes); empty for all.
        focus: Only this class and those `depth` relations away from it; empty for all.
        depth: How many relations away from `focus`.

    Returns:
        `nodes` (class path, `stereotype`, `attributes`: name, type, icon, target class;
        `methods`: name, signature, kind; `parent`: the file it is in) plus the files and packages
        above the classes as frames (`frame` true, `parent` the package above), and `edges`
        (one of `CLASS_RELATIONS`; `has` with `via`).
    """
    classes = [path for path in class_paths(state) if not package or path == package or path.startswith(package + ".")]
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
        nodes.append(_node(state, path, stereotype=stereotype, attributes=attributes, methods=methods,
                           parent=_module_of(state, path), frame=False))
    # The levels above the classes, as frames: the file of each class, then its packages up to the top.
    frames: dict[str, str | None] = {}
    for node in list(nodes):
        module = node["parent"]
        while module and module not in frames:
            parent = _module_of(state, module)
            frames[module] = parent
            module = parent
    nodes.extend(_node(state, path, parent=parent, frame=True, page=path) for path, parent in frames.items())
    nodes += _in_projects(state, nodes, apart)
    stereotypes = {node["id"]: node["stereotype"] for node in nodes if not node["frame"]}
    edges, seen = [], set()
    for edge in _edges_of(state, "inherits"):
        if edge["source"] in kept and edge["target"] in kept:
            kind = "implements" if stereotypes[edge["target"]] in IMPLEMENTED else "inherits"
            edges.append({"id": f"{kind}:{edge['source']}->{edge['target']}", **edge, "kind": kind})
            seen.add((edge["source"], edge["target"]))
    for edge in _edges_of(state, "has"):
        if edge["source"] in kept and edge["target"] in kept:
            via = state.entities[edge["via"]]["name"]
            edges.append({"id": f"has:{edge['source']}.{via}->{edge['target']}", **edge, "via": via})
            seen.add((edge["source"], edge["target"]))
    for relation, kind in (("calls", "uses"), ("refers", "refers")):
        for edge in _edges_of(state, relation):
            source = _class_of(state, edge["source"])
            target = _class_of(state, edge["target"])
            if source in kept and target in kept and source != target and (source, target) not in seen:
                seen.add((source, target))
                edges.append({"id": f"{kind}:{source}->{target}", "source": source, "target": target, "kind": kind})
    nodes = _filtered(nodes, [(edge["source"], edge["target"]) for edge in edges], project, focus, depth)
    kept = {node["id"] for node in nodes if not node["frame"]}
    return {"nodes": nodes, "edges": [edge for edge in edges if edge["source"] in kept and edge["target"] in kept]}


ER_KINDS = ("foreign-key", "implied", "view-reads", "partition-of", "inherits", "foreign-table")
"""The relations of the ER diagram: a foreign key and an implied one (from a column's row to a column's
row, with their cardinality), a view reading a table, a partition or child table and its parent, a
foreign table and the table it stands for."""

_ER_TABLES = {"table": "table", "foreign table": "foreign-table", "view": "view", "materialized view": "materialized-view"}
"""What the ER diagram draws as boxes, and the role each kind takes."""

_ER_RELATIONS = {"implied": "implied", "view reads": "view-reads", "partition of": "partition-of", "inherits": "inherits",
                 "foreign table": "foreign-table"}
"""The catalog's relations the ER diagram draws besides the foreign keys (read from each table's keys)."""


def _er_frame_role(node: dict) -> str:
    """The role of a level of the DATABASES tree as a frame of the ER diagram."""
    role, path = node["role"], node["path"]
    if role.startswith("connection-"):
        return "connection"
    if role == "folder":  # a schema of a database, or a folder of files
        return "schema" if path.startswith(("db:", "origin:")) else "folder"
    return {"module": "file", "connections": "connections"}.get(role, role)


def er_diagram(state: DocState, catalog, connections: list[dict], apart: str = "", project: str = "", focus: str = "",
               depth: int = MAX_CALL_DEPTH, slice_: dict | None = None) -> dict:
    """Build the entity-relationship diagram of the project's databases: the live ones and what its files
    declare, in the levels of the DATABASES tree (project › Connections / files › connection › database
    › schema), each table and view a box with one row per column.

    Args:
        state: Extracted entities, with the origins.
        catalog: The databases read and what the files declare (`CatalogStore`).
        connections: Every connection of the project (`ConnectionStore.connections`).
        apart: A folder whose subfolders are projects of their own (see `database_tree`).
        project: Only the boxes inside this level (a project's `databases:<name>`); empty for all.
        focus: A table or view (its path): only it and those `depth` relations away; a level (a database,
            a schema, an origin): only what it holds; empty for all.
        depth: How many relations away from a focused table.
        slice_: A slice as found now (`databases.slices.resolve`): only its tables, at their positions,
            without the levels, and the tables related to them as suggestions.

    Returns:
        `nodes`: the levels as frames (`frame` true; `role` project, connections, connection, folder, file,
        database, schema) and the tables and views as boxes (`role` table, view, materialized-view,
        foreign-table; `columns`: name, type, marks, nullable, comment, path), each with `id` (its path),
        `label`, `parent`, `page`, `summary`; `edges`: `source` and `target` (tables), `kind` (one of
        `ER_KINDS`); a foreign key and an implied one also with `via` and `to` (the columns of each end),
        `source_end` (`zero-one` when its columns are unique, else `zero-many`) and `target_end` (`one`
        when its columns are NOT NULL, else `zero-one`).
    """
    from doctracker.wiki.pages import database_tree  # the tree's own levels

    tree = database_tree(state, connections, apart=apart, read=catalog.outline())
    nodes: list[dict] = []
    placed: dict[str, str] = {}  # a table's path -> the level it is drawn in

    def walk(items: list[dict], parent: str | None) -> None:
        for item in items:
            if "#" in item["path"] and not item["link"]:  # a kind group (Tables, Views…): its tables go in the level above
                for child in item["children"]:
                    placed.setdefault(child["path"], parent or "")
                continue
            if item["path"] in placed:  # an object of a file, straight in its file
                continue
            nodes.append({"id": item["path"], "label": item["name"], "role": _er_frame_role(item), "parent": parent, "frame": True,
                          "page": item["path"] if item["path"].startswith(("db:", "origin:")) else "", "summary": item["name"]})
            walk(item["children"], item["path"])

    walk(tree, None)
    objects = {o["path"]: o for o in catalog.objects(origins=True) if o["kind"] in _ER_TABLES and o["path"] in placed}
    columns: dict[str, list[dict]] = {}
    for column in catalog.objects(kind="column", origins=True):
        if column["parent"] in objects:
            columns.setdefault(column["parent"], []).append(column)
    for path, obj in objects.items():
        held = sorted(columns.get(path, []), key=lambda c: c["data"].get("position", 0))
        nodes.append({"id": path, "label": obj["name"], "role": _ER_TABLES[obj["kind"]], "parent": placed[path] or None, "frame": False,
                      "page": path, "summary": str(obj["data"].get("comment") or obj["kind"]),
                      "columns": [{"name": c["name"], "type": c["data"].get("type", ""), "marks": c["data"].get("marks", []),
                                   "nullable": bool(c["data"].get("nullable", True)), "comment": c["data"].get("comment", ""),
                                   "path": c["path"]} for c in held]})
    def unique(table: dict, names: list[str]) -> bool:
        """Whether these columns of a table can hold each value once: its primary key, or a unique key or index on them."""
        data, wanted = table["data"], sorted(names)
        held = [(data.get("primary_key") or {}).get("columns") or []] + [u.get("columns") or [] for u in data.get("unique") or []]
        held += [i.get("columns") or [] for i in data.get("indexes") or [] if i.get("unique")]
        return any(sorted(columns_) == wanted for columns_ in held if columns_)

    def nullable(table_path: str, names: list[str]) -> bool:
        by_name = {c["name"]: c for c in columns.get(table_path, [])}
        return any(by_name.get(name, {}).get("data", {}).get("nullable", True) for name in names)

    edges = []
    for path, obj in objects.items():  # foreign keys, from each table's own keys (one line per key, not per column)
        for key in obj["data"].get("foreign_keys") or []:
            if key.get("target") not in objects:
                continue
            names, targets = key.get("columns") or [], key.get("target_columns") or []
            edges.append({"id": f"foreign-key:{path}({','.join(names)})->{key['target']}", "source": path, "target": key["target"],
                          "kind": "foreign-key", "via": names[0] if names else "", "to": targets[0] if targets else "",
                          "columns": names, "target_columns": targets, "name": key.get("name") or "",
                          "source_end": "zero-one" if unique(obj, names) else "zero-many",
                          "target_end": "zero-one" if nullable(path, names) else "one"})
    by_place: dict[str, list[str]] = {}  # a foreign table's target, as the server reaches it, by database and name
    for path in objects:
        by_place.setdefault(path.split("/", 1)[-1], []).append(path)
    column_table = {c["path"]: table for table, held in columns.items() for c in held}
    for relation in catalog.relations(tuple(_ER_RELATIONS)):
        kind, source, target = _ER_RELATIONS[relation["kind"]], relation["source"], relation["target"]
        if kind == "foreign-table" and target not in objects and len(by_place.get(target.split("/", 1)[-1], [])) == 1:
            target = by_place[target.split("/", 1)[-1]][0]
        if kind == "implied":  # column to column
            source_table, target_table = column_table.get(source), column_table.get(target)
            if not source_table or not target_table:
                continue
            via, to = source.rsplit(".", 1)[-1], target.rsplit(".", 1)[-1]
            edges.append({"id": f"implied:{source}->{target}", "source": source_table, "target": target_table, "kind": kind,
                          "via": via, "to": to, "columns": [via], "target_columns": [to],
                          "source_end": "zero-one" if unique(objects[source_table], [via]) else "zero-many",
                          "target_end": "zero-one" if nullable(source_table, [via]) else "one"})
        elif source in objects and target in objects and source != target:
            edges.append({"id": f"{kind}:{source}->{target}", "source": source, "target": target, "kind": kind})
    edges = list({edge["id"]: edge for edge in edges}.values())
    if slice_ is not None:
        return _slice_view(nodes, edges, slice_)
    frames = {node["id"] for node in nodes if node["frame"]}
    if focus in frames:  # a level: what it holds
        by_id = {node["id"]: node for node in nodes}
        keep = {node["id"] for node in nodes if not node["frame"] and focus in _ancestors(by_id, node["id"])}
        holding = {up for node_id in keep for up in _ancestors(by_id, node_id)}
        nodes = [node for node in nodes if node["id"] in keep or node["id"] in holding]
        focus = ""
    nodes = _filtered(nodes, [(edge["source"], edge["target"]) for edge in edges], project, focus, depth)
    kept = {node["id"] for node in nodes if not node["frame"]}
    return {"nodes": nodes, "edges": [edge for edge in edges if edge["source"] in kept and edge["target"] in kept]}


def _slice_view(nodes: list[dict], edges: list[dict], found: dict) -> dict:
    """A slice in the ER diagram: its tables found, at their saved positions, with no levels around them;
    the tables one relation away from them, `suggested`; and `slice` (its name, text, the tables not found
    and those found by name)."""
    by_id = {node["id"]: node for node in nodes if not node["frame"]}
    kept = {}
    for table in found["tables"]:
        if table["found"] in by_id:
            kept[table["found"]] = {**by_id[table["found"]], "parent": None, "x": table.get("x"), "y": table.get("y"),
                                    "found_by": table["found_by"]}
    def base(path: str) -> str:  # the database (or file) a table is in
        return path.split("::", 1)[0] if "::" in path else "/".join(path.split("/")[:2])

    bases = {base(path) for path in kept}  # suggestions only from the databases the slice's tables are in
    near = {end for edge in edges if edge["source"] in kept or edge["target"] in kept for end in (edge["source"], edge["target"])}
    suggested = {path: {**by_id[path], "parent": None, "suggested": True} for path in near - set(kept)
                 if path in by_id and base(path) in bases}
    drawn = {**kept, **suggested}
    return {"nodes": list(drawn.values()), "edges": [edge for edge in edges if edge["source"] in drawn and edge["target"] in drawn],
            "slice": {"name": found["name"], "text": found.get("text", ""),
                      "missing": [t["key"] for t in found["tables"] if not t["found"]],
                      "by_name": [t["key"] for t in found["tables"] if t["found_by"] == "name"],
                      "by_name_in": sorted({base(t["found"]).removeprefix("db:").removeprefix("origin:")
                                            for t in found["tables"] if t["found_by"] == "name"})}}


def _ancestors(by_id: dict[str, dict], node_id: str) -> list[str]:
    """The levels above a node of a diagram, nearest first."""
    found, at = [], by_id.get(node_id, {}).get("parent")
    while at:
        found.append(at)
        at = by_id.get(at, {}).get("parent")
    return found


def _module_of(state: DocState, path: str) -> str | None:
    """The module (file or package) holding an entity, outside any class; `None` at the top."""
    parent = state.entities[path]["parent"]
    while parent and parent in state.entities and state.entities[parent]["kind"] != "module":
        parent = state.entities[parent]["parent"]
    return parent if parent in state.entities else None


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


CALL_KINDS = ("calls", "refers", "template", "css-class", "route")
"""Relations of the call graph, each its own line: calls, names used without a call (a callback, a
type), templates included or rendered, CSS classes used and the routes a URL reaches."""

LOCAL_KINDS = ("imports", "inherits", "has", "calls", "refers", "template", "css-class", "route")
"""Relations of an entity's local graph (its page): every relation but containment."""

_DRAWN_FROM = {"template": "uses", "css-class": "uses", "route": "refers"}
"""The extracted relation each kind of the call graph is read from (the others are their own)."""


def _call_kind(state: DocState, edge: dict) -> str:
    """Tell the kind a relation is drawn as in the call graph: `uses` is a template or a CSS class, a
    `refers` with a route (`via`) is a route."""
    if edge["kind"] == "uses":
        return "css-class" if state.entities[edge["target"]]["language"] == "css" else "template"
    if edge["kind"] == "refers" and edge.get("via"):
        return "route"
    return edge["kind"]


def find_callable(state: DocState, name: str) -> str | None:
    """Find the function, method or class a call graph is centered on, by its path or by its name.

    Args:
        state: Extracted entities and relations.
        name: An entity path, or a name as written in the code (`call_graph`, `NoteStore.add_task`).

    Returns:
        The path; among several of the same name, the one with the most calls in and out. `None`
        when nothing has that path or name.
    """
    name = name.strip()
    if name in state.entities:
        return name
    found = [path for path, entity in state.entities.items() if entity["kind"] in ("function", "class")
             and (entity["name"] == name or path.endswith(("." + name, ":" + name)))]
    if not found:
        return None
    degree: dict[str, int] = {}
    for kind in CALL_KINDS:
        for edge in _edges_of(state, kind):
            for end in (edge["source"], edge["target"]):
                degree[end] = degree.get(end, 0) + 1
    return max(found, key=lambda path: (degree.get(path, 0), -len(path)))


def call_graph(state: DocState, focus: str, depth: int = MAX_CALL_DEPTH, direction: str = "both", to: str = "",
               kinds: tuple[str, ...] = CALL_KINDS) -> dict:
    """Build the call neighborhood of one function, method or class.

    Args:
        state: Extracted entities and relations.
        focus: Path or name of the entity in the center (see `find_callable`).
        depth: How many calls away to go (1 to `MAX_CALL_DEPTH`).
        direction: `out` (what it calls), `in` (what calls it) or `both`.
        to: Path or name of another entity: instead of the neighborhood, the shortest call paths
            from `focus` to it (or from it to `focus`, when there are none the other way).
        kinds: The relations followed and drawn: `CALL_KINDS`, or `LOCAL_KINDS` for the local graph
            of an entity's page.

    Returns:
        `focus` (the path found), `nodes` (with `distance` from the focus and `side`: `focus`,
        `callee`, `caller` or `path`) and `edges` (one of `kinds`); `nodes` and `edges`
        are empty, with an `error`, when `focus` or `to` is unknown or no path links them.
    """
    read = sorted({_DRAWN_FROM.get(kind, kind) for kind in kinds})
    calls = [{**edge, "kind": _call_kind(state, edge)} for base in read for edge in _edges_of(state, base)]
    calls = [edge for edge in calls if edge["kind"] in kinds]
    callees: dict[str, list[str]] = {}
    callers: dict[str, list[str]] = {}
    for edge in calls:
        callees.setdefault(edge["source"], []).append(edge["target"])
        callers.setdefault(edge["target"], []).append(edge["source"])
    start = find_callable(state, focus)
    if start is None:
        return {"focus": "", "nodes": [], "edges": [], "error": f"Nothing is called {focus}."}
    if to.strip():
        end = find_callable(state, to)
        if end is None:
            return {"focus": start, "nodes": [], "edges": [], "error": f"Nothing is called {to}."}
        found = _shortest_paths(start, end, callees) or _shortest_paths(end, start, callees)
        if not found:
            return {"focus": start, "nodes": [], "edges": [], "error": f"No calls lead from {focus} to {to}, nor back."}
        nodes = [_node(state, path, distance=distance, side="focus" if path in (start, end) else "path")
                 for path, distance in found.items()]
        edges = [{"id": f"{e['kind']}:{e['source']}->{e['target']}", **e} for e in calls
                 if e["source"] in found and e["target"] in found and found[e["target"]] == found[e["source"]] + 1]
        return {"focus": start, "nodes": nodes, "edges": edges}
    depth = max(1, min(depth, MAX_CALL_DEPTH))
    reached_at = {start: (0, "focus")}
    walks = [("callee", callees)] if direction == "out" else [("caller", callers)] if direction == "in" else [
        ("callee", callees), ("caller", callers)]
    for side, neighbors in walks:
        frontier = [start]
        for distance in range(1, depth + 1):
            reached = []
            for path in frontier:
                for neighbor in neighbors.get(path, []):
                    if neighbor not in reached_at:
                        reached_at[neighbor] = (distance, side)
                        reached.append(neighbor)
            frontier = reached
    nodes = [_node(state, path, distance=distance, side=side) for path, (distance, side) in reached_at.items()]
    edges = [
        {"id": f"{e['kind']}:{e['source']}->{e['target']}", **e}
        for e in calls
        if e["source"] in reached_at and e["target"] in reached_at
    ]
    return {"focus": start, "nodes": nodes, "edges": edges}


def _shortest_paths(start: str, end: str, callees: dict[str, list[str]]) -> dict[str, int]:
    """The entities on every shortest call path from `start` to `end`, with their distance from `start`.

    Args:
        start: Where the calls start.
        end: Where they must arrive.
        callees: What each entity calls.

    Returns:
        Path → calls from `start`; empty when no calls lead from `start` to `end`.
    """
    ahead = {start: 0}
    frontier = [start]
    while frontier and end not in ahead:
        reached = []
        for path in frontier:
            for callee in callees.get(path, []):
                if callee not in ahead:
                    ahead[callee] = ahead[path] + 1
                    reached.append(callee)
        frontier = reached
    if end not in ahead:
        return {}
    on_path = {end}
    frontier = [end]
    while frontier:  # back from the end: what is one call closer to the start and calls it
        frontier = [path for path in ahead for target in frontier
                    if ahead[path] == ahead[target] - 1 and target in callees.get(path, []) and path not in on_path]
        on_path.update(frontier)
    return {path: ahead[path] for path in on_path}


MAX_BOXES = 500
"""Most boxes a diagram given to an agent holds: over it, the most connected (as the wiki draws)."""


def trim_view(graph: dict, kinds: list[str] | None = None, hide_unconnected: bool = False,
              max_boxes: int = MAX_BOXES) -> dict:
    """Apply the options of a diagram's bar to a diagram, for the MCP tools: what the wiki's bar does.

    Args:
        graph: A diagram (`nodes`, `edges`), as `architecture`, `class_diagram` or `call_graph` build it.
        kinds: Only these relations; `None` keeps them all.
        hide_unconnected: Leave out the boxes with no relation left.
        max_boxes: Over this many boxes, only the most connected are kept.

    Returns:
        The diagram with the boxes and frames kept, plus `left_out`: how many boxes the limit left out.
    """
    edges = [edge for edge in graph["edges"] if kinds is None or edge["kind"] in kinds]
    boxes = [node for node in graph["nodes"] if not node.get("frame")]
    degree: dict[str, int] = {}
    for edge in edges:
        for end in (edge["source"], edge["target"]):
            degree[end] = degree.get(end, 0) + edge.get("weight", 1)
    if hide_unconnected:
        boxes = [node for node in boxes if node["id"] in degree]
    left_out = max(0, len(boxes) - max_boxes)
    kept = {node["id"] for node in sorted(boxes, key=lambda node: (-degree.get(node["id"], 0), node["id"]))[:max_boxes]}
    parent_of = {node["id"]: node.get("parent") for node in graph["nodes"]}
    holding = set()
    for node_id in kept:  # the frames above what is kept
        at = parent_of.get(node_id)
        while at and at not in holding:
            holding.add(at)
            at = parent_of.get(at)
    return {**graph, "nodes": [node for node in graph["nodes"] if node["id"] in kept or node["id"] in holding],
            "edges": [edge for edge in edges if edge["source"] in kept and edge["target"] in kept], "left_out": left_out}


TIMELINE_COMMITS = 5000
"""Most commits the timeline goes through, the newest."""


async def file_timeline(project_root: Path) -> dict | None:
    """Tell, for each file of the project, at which commit it appeared: the timeline of the diagrams.

    Read from the git log only (the code of old commits is never read): a file appears at the commit
    that added it, keeps that commit when it is renamed or moved, and starts again if it is deleted
    and added back. A file not committed yet has no commit: it appears only at the end, "now".

    Args:
        project_root: Root of the documented project.

    Returns:
        `commits` (oldest first: `short`, `author`, `date`, `subject`) and `added` (file path, relative to the
        project root → the index of its commit in `commits`); `None` when git or the repository is missing.
    """
    commits = await read_history(project_root, TIMELINE_COMMITS)
    if commits is None:
        return None
    commits.reverse()
    added: dict[str, int] = {}
    for index, commit in enumerate(commits):
        for path in commit.deleted:
            added.pop(path, None)
        for old, new in commit.renamed:
            added[new] = added.pop(old, index)
        for path in commit.added:
            added.setdefault(path, index)
    return {"commits": [{"short": c.short, "author": c.author, "date": c.date[:10], "subject": c.subject} for c in commits],
            "added": added}


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
