"""Read the project's Python code without running it: what a name, a call or an expression stands for.

The ORM readers ask it what a name means where it is written — a constant, a class, a function, or a
name imported from another module of the project (`from base import Base`, `from .fields import
MoneyField`, `import lab.fields` then `lab.fields.MoneyField`) — and the value of simple expressions:
literals, constants, f-strings, `+`, `.lower()` / `.upper()`, lists, tuples, dicts, and calls of a
project function whose body is one `return` (inlined with its arguments). Whatever needs the code to
run raises `Unresolved`, which the readers report with its file and line. Nothing is imported: the
files are parsed with `ast`, each once, when first needed.
"""

import ast
from pathlib import Path


class Unresolved(Exception):
    """What the static reading cannot tell without running the code.

    Attributes:
        what: What could not be told, in a few words.
        line: The line it is written on (0 when not known).
    """

    def __init__(self, what: str, line: int = 0) -> None:
        super().__init__(what)
        self.what, self.line = what, line


def name_of(node: ast.AST | None) -> str:
    """The last name of a reference: `Integer` for `sa.Integer`, `sa.Integer(...)` or `Mapped[...]`'s `Mapped`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, (ast.Call,)):
        return name_of(node.func)
    if isinstance(node, ast.Subscript):
        return name_of(node.value)
    if isinstance(node, ast.Starred):
        return name_of(node.value)
    return ""


def dotted(node: ast.AST) -> str:
    """A reference written with dots, as written (`lab.fields.MoneyField`); empty for anything else."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = dotted(node.value)
        return f"{head}.{node.attr}" if head else ""
    return ""


def keyword(call: ast.Call, name: str) -> ast.expr | None:
    """The value a call gives to a keyword argument, or None."""
    for item in call.keywords:
        if item.arg == name:
            return item.value
    return None


class Project:
    """The project's Python modules, by dotted name, read when first asked for.

    Args:
        root: The project's root.
        files: The project's files, relative to the root (only `.py` files are taken).

    Attributes:
        files: By dotted module name (`shop.models`, a package by its `__init__`), its file.
    """

    def __init__(self, root: Path, files: list[str]) -> None:
        self.root = root
        self.files: dict[str, str] = {}
        for file in files:
            if file.endswith(".py"):
                parts = Path(file).with_suffix("").parts
                self.files[".".join(parts[:-1] if parts[-1] == "__init__" else parts)] = file
        self._trees: dict[str, ast.Module | None] = {}
        self._names: dict[str, dict[str, tuple[str, object]]] = {}

    def module_of(self, file: str) -> str:
        """The dotted name of a file of the project."""
        return next((module for module, path in self.files.items() if path == file), "")

    def tree(self, module: str) -> ast.Module | None:
        """A module's syntax tree (None when it cannot be read or parsed)."""
        if module not in self._trees:
            try:
                self._trees[module] = ast.parse((self.root / self.files[module]).read_text(encoding="utf-8", errors="replace"))
            except (OSError, SyntaxError, KeyError, ValueError):
                self._trees[module] = None
        return self._trees[module]

    def names(self, module: str) -> dict[str, tuple[str, object]]:
        """What each top-level name of a module is: `assign` (its value), `class`, `function` or `import`
        (the module and name it comes from; a module itself with name None)."""
        if module not in self._names:
            found: dict[str, tuple[str, object]] = {}
            for node in (self.tree(module) or ast.Module(body=[])).body:
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            found[target.id] = ("assign", node.value)
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                    found[node.target.id] = ("assign", node.value)
                elif isinstance(node, ast.ClassDef):
                    found[node.name] = ("class", node)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found[node.name] = ("function", node)
                elif isinstance(node, ast.ImportFrom):
                    source = self._absolute(module, node.module or "", node.level)
                    for alias in node.names:
                        found[alias.asname or alias.name] = ("import", (source, alias.name))
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        found[alias.asname or alias.name.split(".")[0]] = ("import", (alias.name if alias.asname else alias.name.split(".")[0], None))
            self._names[module] = found
        return self._names[module]

    def _absolute(self, module: str, name: str, level: int) -> str:
        """The dotted name an import means: a relative one from the importing module's package."""
        if not level:
            return name
        package = module.split(".")
        if not self.files.get(module, "").endswith("__init__.py"):
            package = package[:-1]
        package = package[:len(package) - (level - 1)] if level > 1 else package
        return ".".join(package + ([name] if name else []))

    def find_module(self, name: str, near: str = "") -> str | None:
        """The project's module an import names: the same dotted name, else one in a package around the
        importing module (a script's sibling, `from base import Base`, run from its folder), the nearest
        first; None when it is not the project's (a library: a module of the project merely ending with
        the same name, elsewhere, does not hide it)."""
        if name in self.files:
            return name
        around = [module for module in self.files if module.endswith(f".{name}") and near.startswith(module[:-len(name)])]
        if not around:
            return None
        return max(around, key=lambda module: len(_common(module, near)))

    def lookup(self, module: str, name: str) -> tuple[str, object, str] | None:
        """What a name means in a module, following imports into the project's other modules.

        Returns:
            `(kind, node, module)`: `assign` / `class` / `function` and where it is defined, `module` for
            a module of the project, or `external` with the dotted name of a library's (`sqlalchemy.orm.
            Mapped`); None when the module does not know it.
        """
        seen = set()
        while (module, name) not in seen:
            seen.add((module, name))
            found = self.names(module).get(name)
            if found is None:
                return None
            kind, value = found
            if kind != "import":
                return kind, value, module
            source, imported = value
            target = self.find_module(source, module)
            if imported is None:  # import a.b: the module itself
                return ("module", None, target) if target else ("external", source, "")
            if target is None:
                inner = self.find_module(f"{source}.{imported}", module)  # from package import module
                return ("module", None, inner) if inner else ("external", f"{source}.{imported}", "")
            if imported not in self.names(target) and (inner := self.find_module(f"{target}.{imported}", module)):
                return "module", None, inner
            module, name = target, imported
        return None

    def resolve(self, node: ast.AST, module: str) -> tuple[str, object, str] | None:
        """What a reference written in a module means: a name (`MoneyField`) or a dotted one (`lab.fields.
        MoneyField`, `sa.Integer`), as `lookup` gives it."""
        path = dotted(node)
        if not path:
            return None
        head, *rest = path.split(".")
        found = self.lookup(module, head)
        for part in rest:
            if found is None:
                return None
            kind, _, where = found
            if kind == "module" and where:  # a name of the module, else one of its submodules (import lab.fields)
                inner = self.find_module(f"{where}.{part}", module) if part not in self.names(where) else None
                found = ("module", None, inner) if inner else self.lookup(where, part)
            elif kind == "external":
                found = ("external", f"{found[1]}.{part}", "")
            else:
                return None
        return found

    def library(self, node: ast.AST, module: str) -> str:
        """The dotted name of the library thing a reference stands for (`sqlalchemy.Integer`), or empty."""
        found = self.resolve(node, module)
        return str(found[1]) if found and found[0] == "external" else ""

    def class_of(self, node: ast.AST, module: str) -> tuple[ast.ClassDef | None, str]:
        """The project's class a reference stands for, and its module."""
        found = self.resolve(node, module)
        return (found[1], found[2]) if found and found[0] == "class" else (None, "")

    def value(self, node: ast.AST | None, module: str, env: dict | None = None):
        """The value of a simple expression written in a module (see the module's docstring).

        Raises:
            Unresolved: When it needs the code to run.
        """
        env = env or {}
        if node is None:
            return None
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            found = self.lookup(module, node.id)
            if found and found[0] == "assign":
                return self.value(found[1], found[2])
            raise Unresolved(f"the value of {node.id}", getattr(node, "lineno", 0))
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "cls" and node.attr == "__name__":
            if "__class__" in env:
                return env["__class__"]
        if isinstance(node, ast.Attribute):
            found = self.resolve(node, module)
            if found and found[0] == "assign":
                return self.value(found[1], found[2])
        if isinstance(node, ast.JoinedStr):
            return "".join(str(self.value(part.value, module, env)) if isinstance(part, ast.FormattedValue) else str(part.value)
                           for part in node.values)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.value(node.left, module, env) + self.value(node.right, module, env)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("lower", "upper") and not node.args:
            return getattr(str(self.value(node.func.value, module, env)), node.func.attr)()
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return [self.value(item, module, env) for item in node.elts]
        if isinstance(node, ast.Dict):
            return {self.value(k, module, env): self.value(v, module, env) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self.value(node.operand, module, env)
        raise Unresolved(ast.unparse(node)[:80], getattr(node, "lineno", 0))

    def inline(self, call: ast.Call, module: str) -> tuple[ast.expr, str]:
        """A call of a project function whose body returns one expression: that expression with the
        arguments put in its parameters' places, and the function's module.

        Raises:
            Unresolved: When the function is not the project's or does more than return a value.
        """
        found = self.resolve(call.func, module)
        if not found or found[0] != "function":
            raise Unresolved(f"the call {ast.unparse(call)[:60]}", call.lineno)
        function, where = found[1], found[2]
        returns = [s for s in function.body if isinstance(s, ast.Return)]
        if len(returns) != 1 or returns[0].value is None:
            raise Unresolved(f"what {function.name}() returns", call.lineno)
        bound = {p.arg: a for p, a in zip(function.args.args, call.args)}
        bound.update({k.arg: k.value for k in call.keywords if k.arg})
        defaults = function.args.defaults
        for parameter, default in zip(function.args.args[len(function.args.args) - len(defaults):], defaults):
            bound.setdefault(parameter.arg, default)

        class Put(ast.NodeTransformer):
            def visit_Name(self, node: ast.Name) -> ast.AST:
                return bound.get(node.id, node)

        expression = Put().visit(ast.parse(ast.unparse(returns[0].value), mode="eval").body)
        return ast.fix_missing_locations(ast.copy_location(expression, call)), where


def _common(a: str, b: str) -> str:
    """The dotted prefix two module names share."""
    shared = []
    for x, y in zip(a.split("."), b.split(".")):
        if x != y:
            break
        shared.append(x)
    return ".".join(shared)
