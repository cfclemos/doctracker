"""Relations between entities, for the code graph: contains, imports, inherits and calls.

Everything is static: each source file is parsed once with `ast` and every name is
resolved with what the extraction already knows — the imports of each module, `self`
and `cls`, the type hints of parameters and attributes, the value of attributes
(`self.index = SearchIndex(...)`) and simple local assignments (`client = Client()`).
Calls that cannot be resolved this way (dynamic attributes, values returned by
other calls, callbacks) are left out.
"""

import ast
import re
from pathlib import Path

EDGE_KINDS = ("contains", "imports", "inherits", "has", "calls")
"""Kinds of relations: parent → member, module → imported module, class → base class,
class → class held in one of its attributes (composition), function → function or class it calls."""

_IDENTIFIER = re.compile(r"[A-Za-z_][\w.]*")
"""A dotted name inside a type hint, e.g. `SearchIndex` in `SearchIndex | None`."""

_CALLED_NAME = re.compile(r"\s*([A-Za-z_][\w.]*)\s*\(")
"""The name called at the start of an attribute value, e.g. `SearchIndex` in `SearchIndex(path)`."""

_ALIAS_HOPS = 8
"""Most re-exports followed when resolving an imported name (`from pkg import X` where `pkg` re-exports `X`)."""


def extract_edges(entities: dict[str, dict], root: Path) -> list[dict]:
    """Find every relation between the entities of the project.

    Args:
        entities: Extracted entities, by path (modules carry their `imports`).
        root: Project root, to read the source files.

    Returns:
        One `{"source", "target", "kind"}` per relation, without duplicates; both ends
        are entity paths and `kind` is one of `EDGE_KINDS`. `has` relations also carry
        `via`: the attribute that holds the other class (one relation per attribute).
    """
    resolver = _Resolver(entities)
    edges: set[tuple[str, str, str]] = set()
    held_by: set[tuple[str, str, str]] = set()  # (class, held class, attribute)
    for path, entity in entities.items():
        if entity["parent"] in entities:
            edges.add((entity["parent"], path, "contains"))
        if entity["kind"] == "module":
            for target in entity.get("imports", {}).values():
                imported = resolver.canonical(target)
                if imported and resolver.module_of(imported) != path:
                    edges.add((path, resolver.module_of(imported), "imports"))
            if entity["filepath"].endswith(".py"):
                tree = _parse(root / entity["filepath"])
                if tree is not None:
                    edges |= _call_edges(path, tree, resolver) | _import_edges(path, tree, resolver)
        if entity["kind"] == "class":
            module = resolver.module_of(path)
            for base in entity["bases"]:
                target = resolver.type_from_text(module, base)
                if target and target != path:
                    edges.add((path, target, "inherits"))
            for member in entity["members"]:
                if entities[member]["kind"] == "attribute":
                    held = resolver.instance_type(member)
                    if held and held != path:
                        held_by.add((path, held, member))
    return ([{"source": source, "target": target, "kind": kind} for source, target, kind in sorted(edges)]
            + [{"source": source, "target": target, "kind": "has", "via": via} for source, target, via in sorted(held_by)])


def _parse(file: Path) -> ast.Module | None:
    """Parse a source file.

    Args:
        file: The source file.

    Returns:
        Its syntax tree, or `None` when it cannot be read or parsed.
    """
    try:
        return ast.parse(file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return None


def _import_edges(module: str, tree: ast.Module, resolver: "_Resolver") -> set[tuple[str, str, str]]:
    """Find every module of the project a module imports, wherever the import is written.

    Imports inside functions (often written there to load something late or to avoid an
    import cycle) are real dependencies too; griffe only lists the module-level ones.

    Args:
        module: Path of the module.
        tree: Its syntax tree.
        resolver: Name resolution for the whole project.

    Returns:
        `(module, imported module, "imports")` relations, without the module itself.
    """
    package = module if resolver.entities[module].get("is_package") else module.rpartition(".")[0]
    edges = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:  # relative: `from . import x`, `from ..pkg import y`
                parent = package.rsplit(".", node.level - 1)[0] if node.level > 1 else package
                base = f"{parent}.{base}" if base else parent
            targets = [f"{base}.{alias.name}" for alias in node.names if alias.name != "*"] or [base]
        else:
            continue
        for target in targets:
            imported = resolver.canonical(target) or resolver.canonical(target.rpartition(".")[0] or target)
            if imported and resolver.module_of(imported) != module:
                edges.add((module, resolver.module_of(imported), "imports"))
    return edges


def _call_edges(module: str, tree: ast.Module, resolver: "_Resolver") -> set[tuple[str, str, str]]:
    """Find the calls made by the functions and methods of one module.

    Args:
        module: Path of the module.
        tree: Its syntax tree.
        resolver: Name resolution for the whole project.

    Returns:
        `(caller, callee, "calls")` relations; nested functions count as their enclosing function.
    """
    edges = set()
    for function, path, owner in _functions(tree, module, None):
        if path not in resolver.entities:
            continue
        for callee in _Scope(resolver, module, owner, path).calls(function):
            if callee != path:
                edges.add((path, callee, "calls"))
    return edges


def _functions(node: ast.AST, prefix: str, owner: str | None):
    """Walk the top-level functions and the methods of a module, with their entity paths.

    Args:
        node: Module or class node.
        prefix: Path of `node`.
        owner: Path of the class when `node` is a class body, else `None`.

    Yields:
        `(function node, entity path, class path or None)`.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield child, f"{prefix}.{child.name}", owner
        elif isinstance(child, ast.ClassDef):
            yield from _functions(child, f"{prefix}.{child.name}", f"{prefix}.{child.name}")


class _Resolver:
    """Turns names written in the code into entity paths.

    Args:
        entities: Extracted entities, by path.

    Attributes:
        entities: Extracted entities, by path.
    """

    def __init__(self, entities: dict[str, dict]) -> None:
        self.entities = entities
        self._canonical: dict[str, str | None] = {}

    def canonical(self, path: str) -> str | None:
        """Follow re-exports until an entity is found (e.g. `pkg.Engine` → `pkg.engine.Engine`).

        Args:
            path: Dotted path as written in an import.

        Returns:
            The entity path, or `None` when it is outside the project.
        """
        if path in self._canonical:
            return self._canonical[path]
        self._canonical[path] = None  # guards against import cycles
        found = None
        current = path
        for _ in range(_ALIAS_HOPS):
            if current in self.entities:
                found = current
                break
            parent, _, name = current.rpartition(".")
            if not parent:
                break
            parent = self.canonical(parent)
            if parent is None:
                break
            if f"{parent}.{name}" in self.entities:
                found = f"{parent}.{name}"
                break
            current = self.entities[parent].get("imports", {}).get(name)
            if current is None:
                break
        self._canonical[path] = found
        return found

    def module_of(self, path: str) -> str:
        """Find the module an entity is defined in (the entity itself for modules).

        Args:
            path: Entity path.

        Returns:
            Path of the module.
        """
        while self.entities[path]["kind"] != "module" and self.entities[path]["parent"] in self.entities:
            path = self.entities[path]["parent"]
        return path

    def name_in_module(self, module: str, name: str) -> str | None:
        """Resolve a bare name used at module level: a member, an imported name or a package.

        Args:
            module: Module where the name is used.
            name: The name, e.g. `load_config`.

        Returns:
            The entity path, or `None` for names from outside the project (builtins, libraries).
        """
        if f"{module}.{name}" in self.entities:
            return f"{module}.{name}"
        imported = self.entities[module].get("imports", {}).get(name)
        if imported:
            return self.canonical(imported)
        return name if name in self.entities else None

    def member(self, owner: str, name: str, seen: frozenset = frozenset()) -> str | None:
        """Find a member of a module or class, looking in base classes too.

        Args:
            owner: Module or class path.
            name: Member name.
            seen: Classes already visited (inheritance cycles).

        Returns:
            The member path, or `None` when it is not found.
        """
        direct = self.canonical(f"{owner}.{name}")
        if direct:
            return direct
        entity = self.entities.get(owner)
        if entity is None or entity["kind"] != "class" or owner in seen:
            return None
        module = self.module_of(owner)
        for base in entity["bases"]:
            base_class = self.type_from_text(module, base)
            if base_class:
                found = self.member(base_class, name, seen | {owner})
                if found:
                    return found
        return None

    def type_from_text(self, module: str, text: str) -> str | None:
        """Find the project class named in a type hint or base class (e.g. `SearchIndex | None`).

        Args:
            module: Module where the text is written.
            text: Type hint or base class, as written.

        Returns:
            The first project class found in the text, or `None`.
        """
        for name in _IDENTIFIER.findall(text or ""):
            path = self.dotted(module, name.split("."))
            if path and self.entities[path]["kind"] == "class":
                return path
        return None

    def dotted(self, module: str, parts: list[str]) -> str | None:
        """Resolve a dotted name used at module level, e.g. `engine.SearchEngine`.

        Args:
            module: Module where the name is used.
            parts: The name split at the dots.

        Returns:
            The entity path, or `None`.
        """
        path = self.name_in_module(module, parts[0])
        for part in parts[1:]:
            if path is None:
                return None
            path = self.member(path, part)
        return path

    def instance_type(self, path: str) -> str | None:
        """Find the class of the value an attribute holds or a function returns.

        Uses the type hint, or, for attributes without one, the class called in
        their value (`self.index = SearchIndex(...)`) or the type hint of the
        `__init__` parameter they are set from (`self.state = state`).

        Args:
            path: Attribute or function path.

        Returns:
            The class path, or `None` when it cannot be told.
        """
        entity = self.entities[path]
        module = self.module_of(path)
        if entity["kind"] == "attribute":
            found = self.type_from_text(module, entity.get("annotation", ""))
            if found:
                return found
            value = entity.get("value", "")
            match = _CALLED_NAME.match(value)
            if match:
                called = self.dotted(module, match.group(1).split("."))
                if called and self.entities[called]["kind"] == "class":
                    return called
            init = self.entities.get(f"{entity['parent']}.__init__")
            if init and value.isidentifier():
                for parameter in init.get("parameters", []):
                    if parameter["name"] == value:
                        return self.type_from_text(module, parameter["annotation"])
            return None
        if entity["kind"] == "function":
            return self.type_from_text(module, entity.get("returns", ""))
        return None


class _Scope:
    """Names known inside one function: `self`, parameters, local imports and assignments.

    Args:
        resolver: Name resolution for the whole project.
        module: Module of the function.
        owner: Class of the method, or `None` for a module-level function.
        function: Path of the function.

    Attributes:
        resolver: Name resolution for the whole project.
        module: Module of the function.
        owner: Class of the method, if any.
        instances: Local names holding an instance of a project class, by name.
        aliases: Local names that refer to an entity (local imports), by name.
    """

    def __init__(self, resolver: _Resolver, module: str, owner: str | None, function: str) -> None:
        self.resolver = resolver
        self.module = module
        self.owner = owner
        self.instances: dict[str, str] = {}
        self.aliases: dict[str, str] = {}
        for parameter in resolver.entities[function].get("parameters", []):
            found = resolver.type_from_text(module, parameter["annotation"])
            if found:
                self.instances[parameter["name"]] = found

    def calls(self, function: ast.AST) -> set[str]:
        """Resolve every call inside a function body.

        Local imports and assignments are read first, so their names are known anywhere in the body.

        Args:
            function: Function node.

        Returns:
            Paths of the called functions and classes.
        """
        nodes = list(ast.walk(function))
        for node in nodes:
            self._learn(node)
        found = set()
        for node in nodes:
            if isinstance(node, ast.Call):
                parts = _dotted(node.func)
                callee = self._resolve(parts) if parts else None
                if callee and self.resolver.entities[callee]["kind"] in ("function", "class"):
                    found.add(callee)
        return found

    def _learn(self, node: ast.AST) -> None:
        """Record names a statement introduces: local imports and `name = Class(...)` assignments.

        Args:
            node: Any node of the function body.
        """
        if isinstance(node, ast.Import):
            for alias in node.names:
                # `import a.b as c` binds `c` to `a.b`; `import a.b` binds `a` to `a`.
                name = alias.asname or alias.name.split(".")[0]
                path = self.resolver.canonical(alias.name if alias.asname else name)
                if path:
                    self.aliases[name] = path
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                path = self.resolver.canonical(f"{node.module}.{alias.name}")
                if path:
                    self.aliases[alias.asname or alias.name] = path
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                return
            found = None
            if isinstance(node, ast.AnnAssign):
                found = self.resolver.type_from_text(self.module, ast.unparse(node.annotation))
            if found is None and isinstance(node.value, ast.Call):
                parts = _dotted(node.value.func)
                called = self._resolve(parts) if parts else None
                if called and self.resolver.entities[called]["kind"] == "class":
                    found = called
                elif called and self.resolver.entities[called]["kind"] == "function":
                    found = self.resolver.instance_type(called)
            if found:
                self.instances[targets[0].id] = found

    def _resolve(self, parts: list[str]) -> str | None:
        """Resolve a dotted name used in the function, e.g. `self.index.search_bm25`.

        Args:
            parts: The name split at the dots.

        Returns:
            The entity path, or `None` when some part cannot be resolved.
        """
        head, rest = parts[0], parts[1:]
        if head in ("self", "cls") and self.owner:
            path = self.owner
        elif head in self.instances:
            path = self.instances[head]
        elif head in self.aliases:
            path = self.aliases[head]
        else:
            path = self.resolver.name_in_module(self.module, head)
        for index, part in enumerate(rest):
            if path is None:
                return None
            path = self.resolver.member(path, part)
            is_last = index == len(rest) - 1
            if path and not is_last and self.resolver.entities[path]["kind"] in ("attribute", "function"):
                path = self.resolver.instance_type(path)
        return path


def _dotted(node: ast.AST) -> list[str] | None:
    """Split a called expression into names, e.g. `self.index.search` → `["self", "index", "search"]`.

    Args:
        node: The `func` of a call.

    Returns:
        The names, or `None` for anything else (calls on call results, subscripts...).
    """
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return parts[::-1]
