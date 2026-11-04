"""Read SQLAlchemy models (declarative classes and `Table()`) into the DDL SQLAlchemy would send.

An origin is the models of one declarative base (a `DeclarativeBase` subclass or a `declarative_base()`)
with the `Table()`s on its metadata: its classes are read from the code, never imported — mixins and
`__abstract__` parents, `Mapped[...]` annotations (`Optional`, `X | None`, `Annotated` aliases, the
base's `type_annotation_map`), `mapped_column()` / `Column()` with their types (the project's own
`TypeDecorator`s through their `impl`, its enums through their members), keys, `Identity`, `Computed`,
server defaults and comments; `__tablename__` (also from a `declared_attr`), `__table_args__` (also
returned by a function), joined and single-table inheritance, and the metadata's `naming_convention`.

From what is read, the same objects are built with doctracker's own SQLAlchemy (`MetaData`, `Table`,
`Column`...) and `create_all` on a mock engine writes the DDL in the origin's dialect: what SQLAlchemy
itself decides (SERIAL or identity, the convention's names, the enums created first, the comments) comes
from it, not from rules of ours. What only the running code would tell (columns added in a loop, a type
of a library doctracker lacks) is reported as not resolved.
"""

import ast
import importlib
import re
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.sql.sqltypes import _type_map

from doctracker.databases.origins.orm.python import Project, Unresolved, keyword, name_of

KIND = "sqlalchemy"
"""The kind of the origins this reader finds."""

_BASES = {"sqlalchemy.orm.DeclarativeBase", "sqlalchemy.orm.DeclarativeBaseNoMeta", "sqlalchemy.orm.decl_api.DeclarativeBase"}
_FACTORIES = {"sqlalchemy.orm.declarative_base", "sqlalchemy.ext.declarative.declarative_base", "sqlalchemy.orm.decl_api.declarative_base"}
_PYTHON_TYPES = {t.__name__: instance for t, instance in _type_map.items()}
"""SQLAlchemy's own type for each Python type of an annotation (`int` → `Integer()`...)."""

_SCHEMES = {"postgresql": "postgres", "postgres": "postgres", "mysql": "mysql", "mariadb": "mysql", "sqlite": "sqlite",
            "mssql": "tsql", "oracle": "oracle"}
"""The dialect of a database URL's scheme (`postgresql+psycopg://` → postgres)."""

_URLS = {"postgres": "postgresql://", "mysql": "mysql://", "sqlite": "sqlite://", "tsql": "mssql://", "oracle": "oracle://"}
"""The URL of the mock engine writing each dialect's DDL."""


# ---------------------------------------------------------------- types, defaults, columns

def library_object(name: str):
    """The object of doctracker's own SQLAlchemy a dotted library name stands for (`sqlalchemy.types.Numeric`),
    or None when it is not SQLAlchemy's."""
    if not name.startswith("sqlalchemy"):
        return None
    module, _, attribute = name.rpartition(".")
    while module:
        try:
            found = importlib.import_module(module)
            for part in name[len(module) + 1:].split("."):
                found = getattr(found, part)
            return found
        except (ImportError, AttributeError):
            module = module.rpartition(".")[0]
    return None


def _arguments(project: Project, call: ast.Call | None, module: str) -> tuple[list, dict]:
    if call is None:
        return [], {}
    return ([project.value(a, module) for a in call.args],
            {k.arg: project.value(k.value, module) for k in call.keywords if k.arg})


def enum_members(project: Project, node: ast.AST, module: str) -> tuple[str, list[str]] | None:
    """A Python enum of the project a reference stands for: its class name and its members' names (what
    SQLAlchemy's `Enum` stores)."""
    found, where = project.class_of(node, module)
    if found is None or not any(name_of(b) in ("Enum", "StrEnum", "IntEnum") for b in found.bases):
        return None
    return found.name, [t.id for s in found.body if isinstance(s, ast.Assign) for t in s.targets if isinstance(t, ast.Name)]


def sa_type(project: Project, node: ast.AST, module: str):
    """The SQLAlchemy type a type written in the code means, built with doctracker's own SQLAlchemy.

    Raises:
        Unresolved: When it is not SQLAlchemy's nor the project's own type of one.
    """
    reference = node.func if isinstance(node, ast.Call) else node
    if (members := enum_members(project, reference, module)) is not None:  # a Python enum written as a type
        return sa.Enum(*members[1], name=members[0].lower())
    found, where = project.class_of(reference, module)
    if found is not None:  # the project's own type: a TypeDecorator by its impl, a subclass by its SQLAlchemy base
        for statement in found.body:
            if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "impl" for t in statement.targets):
                return sa_type(project, statement.value, where)
        for base in found.bases:
            try:
                return sa_type(project, ast.Call(func=base, args=node.args, keywords=node.keywords) if isinstance(node, ast.Call) else base, where)
            except Unresolved:
                continue
        raise Unresolved(f"the type {found.name}", getattr(node, "lineno", 0))
    kind = library_object(project.library(reference, module))
    if not (isinstance(kind, type) and issubclass(kind, sa.types.TypeEngine)):
        raise Unresolved(f"the type {ast.unparse(node)[:60]}", getattr(node, "lineno", 0))
    if issubclass(kind, sa.Enum) and isinstance(node, ast.Call):
        labels = []
        for argument in node.args:
            members = enum_members(project, argument, module)
            labels += members[1] if members else [project.value(argument, module)]
        first = enum_members(project, node.args[0], module) if node.args else None
        _, options = _arguments(project, ast.Call(func=node.func, args=[], keywords=node.keywords), module)
        options.setdefault("name", first[0].lower() if first else None)
        return sa.Enum(*labels, **{k: v for k, v in options.items() if k in ("name", "schema", "native_enum", "length", "create_constraint")})
    args, options = _arguments(project, node if isinstance(node, ast.Call) else None, module)
    return kind(*args, **options)


def server_default(project: Project, node: ast.AST | None, module: str):
    """A server default written in the code, as doctracker's SQLAlchemy takes it (a string, `text()`,
    `func.now()`, `true()`...)."""
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        return str(node.value)
    name = project.library(node.func if isinstance(node, ast.Call) else node, module)
    if name.endswith((".text", ".literal_column")) and isinstance(node, ast.Call):
        return sa.text(str(project.value(node.args[0], module)))
    if name.endswith((".true", ".false", ".null")):
        return library_object(name)()
    if ".func." in name or name.startswith("sqlalchemy.func"):
        function = name.rsplit(".", 1)[-1]
        return getattr(sa.func, function)(*[project.value(a, module) for a in node.args]) if isinstance(node, ast.Call) else None
    if isinstance(node, ast.Call) and name_of(node.func) == "now":
        return sa.func.now()
    raise Unresolved(f"the server default {ast.unparse(node)[:60]}", getattr(node, "lineno", 0))


def column_parts(project: Project, call: ast.Call | None, module: str) -> dict:
    """What a `Column(...)` / `mapped_column(...)` call says: name, type, foreign key, identity, computed
    and its keyword options (a type that cannot be told leaves `type` None and says why in `unresolved`)."""
    parts = {"name": None, "type": None, "foreign_key": None, "identity": None, "computed": None, "options": {}, "unresolved": []}
    if call is None:
        return parts
    for argument in call.args:
        what = name_of(argument)
        try:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                parts["name"] = argument.value
            elif what == "ForeignKey":
                args, options = _arguments(project, argument, module)
                parts["foreign_key"] = sa.ForeignKey(args[0], **{k: v for k, v in options.items() if k in ("ondelete", "onupdate", "name", "deferrable", "initially")})
            elif what == "Identity":
                args, options = _arguments(project, argument, module)
                parts["identity"] = sa.Identity(**options)
            elif what == "Computed":
                args, options = _arguments(project, argument, module)
                parts["computed"] = sa.Computed(str(args[0]), **{k: v for k, v in options.items() if k == "persisted"})
            elif what == "Sequence":
                continue
            else:
                parts["type"] = sa_type(project, argument, module)
        except (Unresolved, TypeError, IndexError) as problem:
            parts["unresolved"].append(getattr(problem, "what", str(problem)))
    for item in call.keywords:
        try:
            if item.arg == "server_default":
                parts["options"]["server_default"] = server_default(project, item.value, module)
            elif item.arg == "type_":
                parts["type"] = sa_type(project, item.value, module)
            elif item.arg in ("primary_key", "nullable", "unique", "index", "comment", "autoincrement", "name", "key"):
                parts["options"][item.arg] = project.value(item.value, module)
        except Unresolved as problem:
            parts["unresolved"].append(problem.what)
    if parts["options"].get("name"):
        parts["name"] = parts["options"].pop("name")
    parts["options"].pop("key", None)
    return parts


def build_column(name: str, parts: dict, type_=None, nullable: bool | None = None) -> sa.Column:
    """A `Column` of doctracker's SQLAlchemy from the parts read (the type given when the call wrote none)."""
    options = dict(parts["options"])
    if nullable is not None and "nullable" not in options and not options.get("primary_key"):
        options["nullable"] = nullable
    extra = [x for x in (parts["foreign_key"], parts["identity"], parts["computed"]) if x is not None]
    column_type = parts["type"] if parts["type"] is not None else type_
    return sa.Column(name, column_type, *extra, **options) if column_type is not None else sa.Column(name, *extra, **options)


# ---------------------------------------------------------------- the classes

def _is_base(project: Project, node: ast.ClassDef, module: str) -> bool:
    return any(project.library(b, module) in _BASES for b in node.bases)


def _bases(project: Project, node: ast.ClassDef, module: str) -> list[tuple[ast.ClassDef, str]]:
    return [found for b in node.bases if (found := project.class_of(b, module))[0] is not None]


def _base_of(project: Project, node: ast.ClassDef, module: str, seen=None) -> tuple[str, str] | None:
    """The declarative base a class is mapped by, as `(module, name)`; None for a class that is not mapped."""
    seen = seen or set()
    if (module, node.name) in seen:
        return None
    seen.add((module, node.name))
    if _is_base(project, node, module):
        return module, node.name
    for base in node.bases:
        found = project.resolve(base, module)
        if found and found[0] == "assign" and isinstance(found[1], ast.Call) and project.library(found[1].func, found[2]) in _FACTORIES:
            return found[2], name_of(base)
        if found and found[0] == "class" and (key := _base_of(project, found[1], found[2], seen)):
            return key
    return None


def _assigns(body: list[ast.stmt]) -> dict[str, ast.expr]:
    return {t.id: s.value for s in body if isinstance(s, ast.Assign) for t in s.targets if isinstance(t, ast.Name)}


def _mapped(project: Project, node: ast.ClassDef, module: str) -> bool:
    """Whether a class is mapped (not the base itself, not abstract)."""
    return _base_of(project, node, module) is not None and not _is_base(project, node, module) \
        and project.value(_assigns(node.body).get("__abstract__"), module) is not True


def find(root: Path, files: list[str], project: Project) -> list[dict]:
    """The project's SQLAlchemy model origins: one per declarative base, with the files of its classes
    and of the `Table()`s on its metadata.

    Returns:
        Origins as `find_origins` gives them (`name`, `kind`, `folder`, `steps`), each step a file.
    """
    groups: dict[tuple[str, str], list[str]] = {}
    for module, file in project.files.items():
        if file not in files:
            continue
        try:
            text = (root / file).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "sqlalchemy" not in text and "Mapped" not in text and "__tablename__" not in text:
            continue
        for node in (project.tree(module) or ast.Module(body=[])).body:
            key = None
            if isinstance(node, ast.ClassDef) and ("__tablename__" in ast.unparse(node) or _mapped(project, node, module)):
                key = _base_of(project, node, module)
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and project.library(node.value.func, module).endswith(".Table"):
                key = _metadata_owner(project, node.value, module)
            if key and file not in groups.setdefault(key, []):
                groups[key].append(file)
    origins = []
    for (module, base), model_files in groups.items():
        model_files = sorted(set(model_files) | {project.files[module]})
        folder = str(Path(model_files[0]).parent.as_posix()) if len(model_files) == 1 else \
            str(Path(*Path(model_files[0]).parts[:len(_shared(model_files))]).as_posix())
        origins.append({"name": model_files[0] if len(model_files) == 1 else folder, "kind": KIND, "folder": folder,
                        "base": [module, base],
                        "steps": [{"file": f, "version": "", "title": Path(f).name} for f in model_files]})
    return origins


def _shared(files: list[str]) -> tuple[str, ...]:
    parts = [Path(f).parent.parts for f in files]
    shared = []
    for items in zip(*parts):
        if len(set(items)) != 1:
            break
        shared.append(items[0])
    return tuple(shared)


def _metadata_owner(project: Project, call: ast.Call, module: str) -> tuple[str, str] | None:
    """The declarative base whose metadata a `Table("name", Base.metadata, ...)` is on."""
    if len(call.args) < 2:
        return None
    holder = call.args[1].value if isinstance(call.args[1], ast.Attribute) else None
    found = project.resolve(holder, module) if holder is not None else None
    if found and found[0] == "class":
        return _base_of(project, found[1], found[2])
    if found and found[0] == "assign":
        return found[2], name_of(holder)
    return None


def dialect(root: Path, origin: dict, project: Project) -> tuple[str, str]:
    """The SQL dialect the models are written for, and what says so: a dialect's own types in the model
    files, a `create_engine("<url>")` of the project, an `alembic.ini`'s `sqlalchemy.url`; else PostgreSQL."""
    for step in origin["steps"]:
        text = (root / step["file"]).read_text(encoding="utf-8", errors="replace")
        if match := re.search(r"sqlalchemy\.dialects\.(\w+)", text):
            found = {"postgresql": "postgres", "mysql": "mysql", "sqlite": "sqlite", "mssql": "tsql", "oracle": "oracle"}.get(match[1])
            if found:
                return found, f"the {match[1]} types in {Path(step['file']).name}"
    found = url_dialect(root, project, Path(origin["folder"]))
    return found or ("postgres", "no database URL written: PostgreSQL")


def url_dialect(root: Path, project: Project, folder: Path) -> tuple[str, str] | None:
    """The dialect of a database URL written near an origin: `create_engine("<url>")` in the code of its
    folder's parent and below it, then the `sqlalchemy.url` of an `alembic.ini` in the folder or above it;
    None when none is written."""
    near = folder.parent.as_posix()
    for module, file in project.files.items():
        if near not in ("", ".") and not file.startswith(f"{near}/"):
            continue
        tree = project.tree(module) if "create_engine" in _text(root, file) else None
        for node in ast.walk(tree) if tree else []:
            if isinstance(node, ast.Call) and name_of(node.func) == "create_engine" and node.args:
                try:
                    url = str(project.value(node.args[0], module))
                except Unresolved:
                    continue
                if (scheme := _SCHEMES.get(url.split(":", 1)[0].split("+", 1)[0].lower())) is not None:
                    return scheme, f"create_engine in {Path(file).name}:{node.lineno}"
    for place in [folder, *folder.parents]:
        ini = root / place / "alembic.ini"
        if ini.is_file():
            match = re.search(r"^\s*sqlalchemy\.url\s*=\s*(\S+)", ini.read_text(encoding="utf-8", errors="replace"), re.MULTILINE)
            if match and (scheme := _SCHEMES.get(match[1].split(":", 1)[0].split("+", 1)[0].lower())) is not None:
                return scheme, f"sqlalchemy.url in {(place / 'alembic.ini').as_posix()}"
    return None


def _text(root: Path, file: str) -> str:
    try:
        return (root / file).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


class _Reader:
    """The classes of one declarative base read into doctracker's own SQLAlchemy objects."""

    def __init__(self, project: Project, origin: dict) -> None:
        self.project, self.origin = project, origin
        self.base_module, self.base_name = origin["base"]
        self.unresolved: list[dict] = []
        self.expects: list[dict] = []
        self.mapping: list[dict] = []
        self.places: dict[str, dict] = {}  # by table key / enum name: where it is written
        convention, self.annotations = {}, {}
        base = self.project.names(self.base_module).get(self.base_name)
        if base and base[0] == "class":
            for statement in base[1].body:
                if isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    target = statement.targets[0] if isinstance(statement, ast.Assign) else statement.target
                    name = getattr(target, "id", "")
                    if name == "metadata" and isinstance(statement.value, ast.Call):
                        convention = self._value(keyword(statement.value, "naming_convention"), self.base_module) or {}
                    elif name == "type_annotation_map" and isinstance(statement.value, ast.Dict):
                        for key, value in zip(statement.value.keys, statement.value.values):
                            try:
                                self.annotations[name_of(key)] = sa_type(self.project, value, self.base_module)
                            except Unresolved as problem:
                                self.note(self.base_module, value.lineno, problem.what)
        elif base and base[0] == "assign" and isinstance(base[1], ast.Call):
            metadata = keyword(base[1], "metadata")
            if isinstance(metadata, ast.Call):
                convention = self._value(keyword(metadata, "naming_convention"), self.base_module) or {}
        convention = {k: v for k, v in convention.items() if isinstance(v, str)}
        self.metadata = sa.MetaData(naming_convention=convention) if convention else sa.MetaData()

    def _value(self, node, module, env=None):
        try:
            return self.project.value(node, module, env)
        except Unresolved as problem:
            self.note(module, problem.line or getattr(node, "lineno", 0), problem.what)
            return None

    def note(self, module: str, line: int, what: str) -> None:
        self.unresolved.append({"file": self.project.files.get(module, ""), "line": line, "what": what})

    # ---- a class's columns
    def _annotation(self, node: ast.AST, module: str) -> tuple[object, bool, tuple[ast.Call, str] | None]:
        """The type, nullability and `Annotated` extras (the `mapped_column()` of the alias, with the module
        it is written in) an annotation `Mapped[...]` says."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node = ast.parse(node.value, mode="eval").body
        if isinstance(node, ast.Subscript) and name_of(node.value) == "Mapped":
            node = node.slice
        optional = False
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            optional = "None" in (ast.unparse(node.left), ast.unparse(node.right))
            node = node.left if ast.unparse(node.right) == "None" else node.right
        elif isinstance(node, ast.Subscript) and name_of(node.value) == "Optional":
            optional, node = True, node.slice
        extra = None
        found = self.project.resolve(node, module) if isinstance(node, (ast.Name, ast.Attribute)) else None
        if found and found[0] == "assign" and isinstance(found[1], ast.Subscript) and name_of(found[1].value) == "Annotated":
            items = found[1].slice.elts
            node, module = items[0], found[2]
            call = next((x for x in items[1:] if isinstance(x, ast.Call) and name_of(x.func) in ("mapped_column", "Column")), None)
            extra = (call, module) if call is not None else None
        if name_of(node) in self.annotations:
            return self.annotations[name_of(node)], optional, extra
        if (members := enum_members(self.project, node, module)) is not None:
            return sa.Enum(*members[1], name=members[0].lower()), optional, extra
        if name_of(node) in _PYTHON_TYPES:
            return _PYTHON_TYPES[name_of(node)], optional, extra
        return None, optional, extra

    def _columns(self, node: ast.ClassDef, module: str) -> list[tuple[str, sa.Column, int, str]]:
        """The columns a class body declares: `(attribute, column, line, module)`."""
        found = []
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                attribute, value, annotation = statement.target.id, statement.value, statement.annotation
            elif isinstance(statement, ast.Assign) and isinstance(statement.targets[0], ast.Name) and isinstance(statement.value, ast.Call):
                attribute, value, annotation = statement.targets[0].id, statement.value, None
            elif isinstance(statement, ast.FunctionDef) and any(name_of(d) in ("declared_attr", "directive") for d in statement.decorator_list) \
                    and statement.name != "__tablename__":
                returns = [s.value for s in statement.body if isinstance(s, ast.Return)]
                if len(returns) != 1 or not isinstance(returns[0], ast.Call) or name_of(returns[0].func) not in ("mapped_column", "Column"):
                    continue
                attribute, value, annotation = statement.name, returns[0], statement.returns
            else:
                continue
            if attribute.startswith("__") or (value is not None and not (isinstance(value, ast.Call) and name_of(value.func) in ("mapped_column", "Column"))):
                continue  # relationships, properties, other attributes
            if annotation is None and value is None:
                continue
            annotated, optional, extra = self._annotation(annotation, module) if annotation is not None else (None, False, None)
            parts = column_parts(self.project, value if isinstance(value, ast.Call) else None, module)
            if extra is not None:  # the alias's mapped_column(), read where it is written, under the column's own
                aliased = column_parts(self.project, *extra)
                for key in ("name", "type", "foreign_key", "identity", "computed"):
                    parts[key] = parts[key] if parts[key] is not None else aliased[key]
                parts["options"] = {**aliased["options"], **parts["options"]}
                parts["unresolved"] = aliased["unresolved"] + parts["unresolved"]
            for what in parts["unresolved"]:
                self.note(module, statement.lineno, f"{node.name}.{attribute}: {what}")
            if parts["type"] is None and annotated is None and parts["foreign_key"] is None:
                if not parts["unresolved"]:
                    self.note(module, statement.lineno, f"{node.name}.{attribute}: its type")
                continue
            if parts["foreign_key"] is not None and parts["type"] is None:
                annotated = None  # SQLAlchemy gives a foreign key without a written type its target's, not the annotation's
            nullable = optional if annotation is not None else None
            found.append((attribute, build_column(parts["name"] or attribute, parts, annotated, nullable), statement.lineno, module))
        return found

    def _table_args(self, node: ast.AST | None, module: str, line: int) -> tuple[list, dict]:
        """The constraints, indexes and options `__table_args__` gives (also returned by a function)."""
        if node is None:
            return [], {}
        if isinstance(node, ast.Call):
            try:
                node, module = self.project.inline(node, module)
            except Unresolved as problem:
                self.note(module, line, problem.what)
                return [], {}
        items = node.elts if isinstance(node, ast.Tuple) else [node]
        extra, options = [], {}
        for item in items:
            try:
                if isinstance(item, ast.Dict):
                    options.update({k: v for k, v in self.project.value(item, module).items() if k in ("schema", "comment")})
                    continue
                what = self.project.library(item.func, module).rsplit(".", 1)[-1] if isinstance(item, ast.Call) else ""
                args, kwargs = _arguments(self.project, item, module)
                if what == "CheckConstraint":
                    extra.append(sa.CheckConstraint(str(args[0]), name=kwargs.get("name")))
                elif what == "UniqueConstraint":
                    extra.append(sa.UniqueConstraint(*args, name=kwargs.get("name")))
                elif what == "PrimaryKeyConstraint":
                    extra.append(sa.PrimaryKeyConstraint(*args, name=kwargs.get("name")))
                elif what == "ForeignKeyConstraint":
                    extra.append(sa.ForeignKeyConstraint(args[0], args[1], **{k: v for k, v in kwargs.items() if k in ("name", "ondelete", "onupdate")}))
                elif what == "Index":
                    where = {k: sa.text(v) for k, v in kwargs.items() if k.endswith("_where") and isinstance(v, str)}
                    extra.append(sa.Index(args[0], *[sa.text(a) if "(" in a else a for a in args[1:]], unique=bool(kwargs.get("unique")),
                                          **where, **{k: v for k, v in kwargs.items() if k.endswith("_using")}))
                elif what:
                    self.note(module, item.lineno, f"__table_args__: {what}")
            except (Unresolved, TypeError, IndexError) as problem:
                self.note(module, getattr(item, "lineno", line), getattr(problem, "what", str(problem)))
        return extra, options

    def read(self) -> list[tuple[sa.Table, dict]]:
        """Every table of the base, in the order written."""
        tables: dict[str, sa.Table] = {}
        by_class: dict[str, sa.Table] = {}
        pending_columns: list[tuple[sa.Table, sa.Column]] = []
        for step in self.origin["steps"]:
            module = self.project.module_of(step["file"])
            tree = self.project.tree(module)
            for node in tree.body if tree else []:
                if isinstance(node, (ast.For, ast.While)) or (isinstance(node, ast.If) and "TYPE_CHECKING" not in ast.unparse(node.test)
                                                              and "__main__" not in ast.unparse(node.test)):
                    self.note(module, node.lineno, f"code run at import ({ast.unparse(node).splitlines()[0][:60]})")
                elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and self.project.library(node.value.func, module).endswith(".Table") \
                        and _metadata_owner(self.project, node.value, module) == (self.base_module, self.base_name):
                    table = self._imperative(node.value, module)
                    if table is not None:
                        tables[table.key] = table
                elif isinstance(node, ast.ClassDef) and _mapped(self.project, node, module) \
                        and _base_of(self.project, node, module) == (self.base_module, self.base_name):
                    self._class(node, module, tables, by_class, pending_columns)
        for table, column in pending_columns:  # single-table inheritance: into the parent's table
            if column.name not in table.c:
                table.append_column(column)
        return [(table, self.places.get(table.key, {})) for table in tables.values()]

    def _imperative(self, call: ast.Call, module: str) -> sa.Table | None:
        name = self._value(call.args[0], module)
        columns = []
        for argument in call.args[2:]:
            if isinstance(argument, ast.Call) and name_of(argument.func) == "Column":
                parts = column_parts(self.project, argument, module)
                for what in parts["unresolved"]:
                    self.note(module, argument.lineno, f"{name}: {what}")
                if parts["name"]:
                    columns.append(build_column(parts["name"], parts))
        extra, _ = self._table_args(ast.Tuple(elts=[a for a in call.args[2:] if not (isinstance(a, ast.Call) and name_of(a.func) == "Column")]),
                                    module, call.lineno)
        options = {k.arg: self._value(k.value, module) for k in call.keywords if k.arg in ("schema", "comment")}
        table = sa.Table(name, self.metadata, *columns, *extra, **options)
        self.places[table.key] = {"file": self.project.files[module], "line": call.lineno}
        return table

    def _class(self, node: ast.ClassDef, module: str, tables: dict, by_class: dict, pending: list) -> None:
        own = _assigns(node.body)
        mixins, parents = [], []
        for base, where in _bases(self.project, node, module):
            if _mapped(self.project, base, where):
                parents.append((base, where))
            elif not _is_base(self.project, base, where):
                mixins.append((base, where))
                mixins += [m for m in _bases(self.project, base, where) if not _is_base(self.project, *m)]
        tablename = self._value(own["__tablename__"], module) if "__tablename__" in own else None
        if tablename is None:
            for holder, where in [(node, module)] + mixins + [m for p in parents for m in self._mixins_of(*p)]:
                for statement in holder.body:
                    if isinstance(statement, ast.FunctionDef) and statement.name == "__tablename__":
                        returns = [s.value for s in statement.body if isinstance(s, ast.Return)]
                        tablename = self._value(returns[0], where, {"__class__": node.name}) if returns else None
        columns = [c for holder, where in [(node, module)] + mixins for c in self._columns(holder, where)]
        place = {"file": self.project.files[module], "line": node.lineno}
        has_key = any(c.primary_key for _, c, _, _ in columns)
        parent_table = by_class.get(f"{parents[0][1]}.{parents[0][0].name}") if parents else None
        if parents and parent_table is not None and (tablename is None or (not has_key and "__tablename__" not in own)):
            for _, column, _, _ in columns:  # single-table inheritance
                if column.name not in parent_table.c:
                    pending.append((parent_table, column))
            by_class[f"{module}.{node.name}"] = parent_table
            self.mapping.append({"class": f"{module}.{node.name}", "table": parent_table.fullname, **place,
                                 "columns": {a: c.name for a, c, _, _ in columns}})
            return
        if tablename is None:
            self.note(module, node.lineno, f"the table name of {node.name}")
            return
        extra, options = self._table_args(own.get("__table_args__"), module, node.lineno)
        table = sa.Table(tablename, self.metadata, *[c for _, c, _, _ in columns], *extra, **options)
        tables[table.key] = table
        by_class[f"{module}.{node.name}"] = table
        self.places[table.key] = place
        self.mapping.append({"class": f"{module}.{node.name}", "table": table.fullname, **place,
                             "columns": {a: c.name for a, c, _, _ in columns}})

    def _mixins_of(self, node: ast.ClassDef, module: str) -> list[tuple[ast.ClassDef, str]]:
        found = []
        for base, where in _bases(self.project, node, module):
            if not _mapped(self.project, base, where) and not _is_base(self.project, base, where):
                found.append((base, where))
            elif _mapped(self.project, base, where):
                found += self._mixins_of(base, where)
        return found


def ddl(metadata: sa.MetaData, dialect: str, places: dict[str, dict], default: dict) -> list[dict]:
    """The DDL `create_all` writes for a metadata in a dialect, each statement with the file and line of
    the table (or the enum, the index) it comes from."""
    statements = []

    def keep(element, *args, **kwargs) -> None:
        target = getattr(element, "element", None)
        table = getattr(target, "table", target)
        place = places.get(getattr(table, "key", ""), places.get(getattr(target, "name", ""), default))
        statements.append({**place, "text": str(element.compile(dialect=engine.dialect)).strip()})

    engine = sa.create_mock_engine(_URLS.get(dialect, "postgresql://"), keep)
    if engine.dialect.server_version_info is None:  # SQL Server's compiler asks for it
        engine.dialect.server_version_info = (16,)
    metadata.create_all(engine, checkfirst=False)
    return statements


def read(root: Path, origin: dict, dialect_name: str, project: Project) -> dict:
    """Read an origin of SQLAlchemy models.

    Returns:
        `statements` (`file`, `line`, `text`: the DDL in the dialect), `unresolved` (`file`, `line`,
        `what`), `expects` (tables it does not create) and `mapping` (class ↔ table, attribute ↔ column).
    """
    reader = _Reader(project, origin)
    tables = reader.read()
    places = {table.key: place for table, place in tables}
    for table, place in tables:
        for column in table.columns:
            if isinstance(column.type, sa.Enum) and column.type.name:
                places.setdefault(column.type.name, place)
    default = {"file": origin["steps"][0]["file"], "line": 1}
    try:
        statements = ddl(reader.metadata, dialect_name, places, default)
    except Exception as problem:  # what doctracker's SQLAlchemy refuses to write: told, nothing kept
        reader.note(project.module_of(default["file"]), 0, f"the DDL: {problem}"[:200])
        statements = []
    return {"statements": statements, "unresolved": reader.unresolved, "expects": reader.expects, "mapping": reader.mapping}


__all__ = ["KIND", "build_column", "column_parts", "dialect", "find", "read", "sa_type", "server_default", "url_dialect"]
