"""Read Alembic migrations into the DDL each revision's `upgrade()` would send.

An origin is a folder of revisions (`revision = ...`, `down_revision = ...`, `def upgrade()`), applied in
the order of their graph (branches and merges, a revision after every one it revises). Each `upgrade()`
is read from the code, never run: the `op.*` calls (tables and columns created, changed, renamed and
dropped; indexes, keys, uniques, checks and comments), `batch_alter_table` blocks, loops over constants,
an `if` on the dialect's name, columns returned by a helper of another module, and `op.execute` (its SQL
read as SQL). The columns and types are read as the SQLAlchemy reader reads them, and doctracker's own
SQLAlchemy writes them (`CreateTable`, `CreateColumn`); what depends on the live database or on running
the code (`is_offline_mode()`, an inspector, `RunPython`-like data code) is reported as not resolved.
"""

import ast
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.schema import CreateColumn, CreateIndex, CreateTable

from doctracker.databases.origins.orm import sqlalchemy as models
from doctracker.databases.origins.orm.python import Project, Unresolved, keyword, name_of

KIND = "alembic"
"""The kind of the origins this reader finds."""

_DATA = {"bulk_insert", "get_bind", "get_context", "inline_literal", "f"}
"""`op` calls about data or the connection: no schema."""


def _revision(project: Project, module: str) -> dict | None:
    """A revision module's id, the ids it revises and its `upgrade()`; None for any other module."""
    tree = project.tree(module)
    if tree is None:
        return None
    top = {t.id: s.value for s in tree.body if isinstance(s, (ast.Assign, ast.AnnAssign))
           for t in (s.targets if isinstance(s, ast.Assign) else [s.target]) if isinstance(t, ast.Name) and s.value is not None}
    upgrade = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None)
    if "revision" not in top or "down_revision" not in top or upgrade is None:
        return None
    try:
        revision, down = project.value(top["revision"], module), project.value(top["down_revision"], module)
    except Unresolved:
        return None
    return {"revision": str(revision), "down": [] if down is None else [down] if isinstance(down, str) else list(down),
            "upgrade": upgrade, "title": (ast.get_docstring(tree) or "").splitlines()[0] if ast.get_docstring(tree) else ""}


def find(root: Path, files: list[str], project: Project) -> list[dict]:
    """The project's Alembic origins: one per folder of revisions, its steps in the revisions' order."""
    folders: dict[str, dict[str, dict]] = {}
    for module, file in project.files.items():
        if file not in files or "revision" not in models._text(root, file):
            continue
        if (found := _revision(project, module)) is not None:
            folders.setdefault(str(Path(file).parent.as_posix()), {})[found["revision"]] = {**found, "file": file}
    origins = []
    for folder, revisions in sorted(folders.items()):
        order, done = [], set()

        def visit(revision: str) -> None:
            if revision in done or revision not in revisions:
                return
            done.add(revision)
            for down in revisions[revision]["down"]:
                visit(down)
            order.append(revision)
        for revision in sorted(revisions):
            visit(revision)
        origins.append({"name": folder, "kind": KIND, "folder": folder,
                        "steps": [{"file": revisions[r]["file"], "version": r, "title": revisions[r]["title"] or Path(revisions[r]["file"]).stem,
                                   "revises": revisions[r]["down"]} for r in order]})
    return origins


def models_base(project: Project, origin: dict) -> tuple[str, str] | None:
    """The declarative base of the models an Alembic origin migrates: what its `env.py` (beside the
    revisions' folder) gives `target_metadata` (`Base.metadata`), as `(module, name)`; None when it gives none."""
    env = project.module_of(str((Path(origin["folder"]).parent / "env.py").as_posix()))
    tree = project.tree(env) if env else None
    for node in ast.walk(tree) if tree else []:
        target = node.value if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "target_metadata" for t in node.targets) else None
        if target is None and isinstance(node, ast.Call) and name_of(node.func) == "configure":
            target = keyword(node, "target_metadata")
        holder = target.value if isinstance(target, ast.Attribute) and target.attr == "metadata" else None
        found = project.resolve(holder, env) if holder is not None else None
        if found and found[0] in ("class", "assign"):
            return found[2], name_of(holder)
    return None

def dialect(root: Path, origin: dict, project: Project) -> tuple[str, str]:
    """The dialect of the database the migrations are for: the URL written in the project (its `env.py`'s
    `create_engine`, an `alembic.ini`'s `sqlalchemy.url`); else PostgreSQL."""
    return models.url_dialect(root, project, Path(origin["folder"])) or ("postgres", "no database URL written: PostgreSQL")


class _Reader:
    """The revisions of one origin read, op after op, into statements."""

    def __init__(self, project: Project, dialect_name: str) -> None:
        self.project, self.dialect_name = project, dialect_name
        self.engine = sa.create_mock_engine(models._URLS.get(dialect_name, "postgresql://"), lambda *a, **k: None)
        if self.engine.dialect.server_version_info is None:
            self.engine.dialect.server_version_info = (16,)
        self.metadata = sa.MetaData()
        self.statements: list[dict] = []
        self.unresolved: list[dict] = []
        self.file, self.module = "", ""

    def note(self, line: int, what: str) -> None:
        self.unresolved.append({"file": self.file, "line": line, "what": what})

    def emit(self, line: int, text) -> None:
        text = text if isinstance(text, str) else str(text.compile(dialect=self.engine.dialect))
        self.statements.append({"file": self.file, "line": line, "text": text.strip()})

    def value(self, node, env):
        return self.project.value(node, self.module, env)

    def columns(self, arguments: list[ast.expr], env: dict, line: int) -> tuple[list[sa.Column], list]:
        """The columns of a `create_table` (also those a project helper returns, `*timestamps()`) and its
        other arguments (constraints)."""
        found, other = [], []
        for argument in arguments:
            if isinstance(argument, ast.Starred) and isinstance(argument.value, ast.Call):
                try:
                    node, where = self.project.inline(argument.value, self.module)
                except Unresolved as problem:
                    self.note(line, problem.what)
                    continue
                for item in node.elts if isinstance(node, (ast.List, ast.Tuple)) else []:
                    found += self._column(item, where, line)
            elif isinstance(argument, ast.Call) and name_of(argument.func) == "Column":
                found += self._column(argument, self.module, line)
            else:
                other.append(argument)
        return found, other

    def _column(self, call: ast.Call, module: str, line: int) -> list[sa.Column]:
        parts = models.column_parts(self.project, call, module)
        for what in parts["unresolved"]:
            self.note(line, f"{parts['name'] or 'a column'}: {what}")
        if not parts["name"] or (parts["type"] is None and parts["foreign_key"] is None):  # nothing to write it with
            if parts["name"] and not parts["unresolved"]:
                self.note(line, f"{parts['name']}: its type")
            return []
        return [models.build_column(parts["name"], parts)]

    def _table(self, name: str, schema: str | None) -> sa.Table:
        """The table a change is about, as created so far (a stub when created outside these revisions)."""
        key = f"{schema}.{name}" if schema else name
        found = self.metadata.tables.get(key)  # a Table has no truth value: compared with None
        return found if found is not None else sa.Table(name, self.metadata, schema=schema)

    def _stubs(self, columns: list[sa.Column]) -> None:
        """Tables a new table's foreign keys point to but no revision here created: stubs, as Alembic makes."""
        for column in columns:
            for key in column.foreign_keys:
                parts = key.target_fullname.split(".")
                table, target = (".".join(parts[:-1]), parts[-1])
                if table not in self.metadata.tables:
                    schema, _, name = table.rpartition(".")
                    sa.Table(name, self.metadata, sa.Column(target, sa.Integer), schema=schema or None)
                elif target not in self.metadata.tables[table].c:
                    self.metadata.tables[table].append_column(sa.Column(target, sa.Integer))

    def op(self, name: str, call: ast.Call, env: dict, batch: str | None = None) -> None:
        arguments = list(call.args)
        if batch is not None:  # inside batch_alter_table: the table is the batch's
            arguments.insert(1 if name in ("create_index", "create_unique_constraint", "create_check_constraint", "create_foreign_key",
                                           "drop_constraint", "drop_index") else 0, ast.Constant(batch))
        def value(node: ast.expr | None):
            return self.value(node, env)

        schema = value(keyword(call, "schema"))

        def qualified(table: str) -> str:
            return f"{schema}.{table}" if schema else table

        line = call.lineno
        if name == "create_table":
            columns, other = self.columns(arguments[1:], env, line)
            extra = []
            for item in other:
                what = name_of(item.func) if isinstance(item, ast.Call) else ""
                args = [value(a) for a in item.args] if isinstance(item, ast.Call) else []
                options = {k.arg: value(k.value) for k in item.keywords} if isinstance(item, ast.Call) else {}
                if what == "CheckConstraint":
                    extra.append(sa.CheckConstraint(str(args[0]), name=options.get("name")))
                elif what == "UniqueConstraint":
                    extra.append(sa.UniqueConstraint(*args, name=options.get("name")))
                elif what == "PrimaryKeyConstraint":
                    extra.append(sa.PrimaryKeyConstraint(*args, name=options.get("name")))
                elif what == "ForeignKeyConstraint":
                    extra.append(sa.ForeignKeyConstraint(args[0], args[1], **{k: v for k, v in options.items() if k in ("name", "ondelete", "onupdate")}))
                elif what:
                    self.note(line, f"create_table: {what}")
            self._stubs(columns)
            table_name = value(arguments[0])
            if qualified(table_name) in self.metadata.tables:  # a stub made for an earlier foreign key
                self.metadata.remove(self.metadata.tables[qualified(table_name)])
            table = sa.Table(table_name, self.metadata, *columns, *extra, schema=schema, comment=value(keyword(call, "comment")))
            if self.dialect_name == "postgres":
                for column in table.columns:
                    if isinstance(column.type, sa.Enum) and column.type.name and column.type.native_enum:
                        labels = ", ".join("'" + label.replace("'", "''") + "'" for label in column.type.enums)
                        self.emit(line, f"CREATE TYPE {column.type.name} AS ENUM ({labels})")
            self.emit(line, CreateTable(table))
            if table.comment:
                self.emit(line, sa.schema.SetTableComment(table))
            for column in table.columns:
                if column.comment:
                    self.emit(line, sa.schema.SetColumnComment(column))
            for index in table.indexes:
                self.emit(line, CreateIndex(index))
        elif name == "add_column":
            table = qualified(value(arguments[0]))
            for column in self._column(arguments[1], self.module, line):
                self._stubs([column])
                holder = self._table(value(arguments[0]), schema)
                holder.append_column(column, replace_existing=True)
                self.emit(line, f"ALTER TABLE {table} ADD COLUMN {CreateColumn(column).compile(dialect=self.engine.dialect)}")
                if column.unique:
                    self.emit(line, f"ALTER TABLE {table} ADD UNIQUE ({column.name})")
                for key in column.foreign_keys:
                    target, _, target_column = key.target_fullname.rpartition(".")
                    self.emit(line, f"ALTER TABLE {table} ADD FOREIGN KEY ({column.name}) REFERENCES {target} ({target_column})"
                                    + (f" ON DELETE {key.ondelete}" if key.ondelete else ""))
        elif name == "drop_column":
            self.emit(line, f"ALTER TABLE {qualified(value(arguments[0]))} DROP COLUMN {value(arguments[1])}")
        elif name == "alter_column":
            table, column = qualified(value(arguments[0])), value(arguments[1])
            if (type_ := keyword(call, "type_")) is not None:
                try:
                    compiled = models.sa_type(self.project, type_, self.module).compile(dialect=self.engine.dialect)
                    self.emit(line, f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {compiled}")
                except Unresolved as problem:
                    self.note(line, problem.what)
            if (nullable := keyword(call, "nullable")) is not None:
                self.emit(line, f"ALTER TABLE {table} ALTER COLUMN {column} {'DROP' if value(nullable) else 'SET'} NOT NULL")
            if (default := keyword(call, "server_default")) is not None:
                given = models.server_default(self.project, default, self.module)
                if given is None or given is False:
                    self.emit(line, f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
                else:
                    text = given if isinstance(given, str) else str(given.compile(dialect=self.engine.dialect))
                    self.emit(line, f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT "
                                    + ("'" + text.replace("'", "''") + "'" if isinstance(given, str) else text))
            if (new := keyword(call, "new_column_name")) is not None:
                self.emit(line, f"ALTER TABLE {table} RENAME COLUMN {column} TO {value(new)}")
        elif name == "rename_table":
            self.emit(line, f"ALTER TABLE {qualified(value(arguments[0]))} RENAME TO {value(arguments[1])}")
        elif name == "create_index":
            using = next((value(k.value) for k in call.keywords if k.arg and k.arg.endswith("_using")), None)
            where = next((value(k.value) for k in call.keywords if k.arg and k.arg.endswith("_where")), None)
            columns = [c if isinstance(c, str) else str(c) for c in value(arguments[2])]
            self.emit(line, f"CREATE {'UNIQUE ' if value(keyword(call, 'unique')) else ''}INDEX {value(arguments[0])} ON {qualified(value(arguments[1]))}"
                            + (f" USING {using}" if using else "") + f" ({', '.join(columns)})" + (f" WHERE {where}" if isinstance(where, str) else ""))
        elif name == "drop_index":
            self.emit(line, f"DROP INDEX {value(arguments[0])}")
        elif name == "create_foreign_key":
            options = "".join(f" ON {action} {value(keyword(call, word))}" for word, action in (("ondelete", "DELETE"), ("onupdate", "UPDATE"))
                              if keyword(call, word) is not None)
            self.emit(line, f"ALTER TABLE {qualified(value(arguments[1]))} ADD CONSTRAINT {value(arguments[0])} FOREIGN KEY "
                            f"({', '.join(value(arguments[3]))}) REFERENCES {value(arguments[2])} ({', '.join(value(arguments[4]))}){options}")
        elif name == "create_unique_constraint":
            self.emit(line, f"ALTER TABLE {qualified(value(arguments[1]))} ADD CONSTRAINT {value(arguments[0])} UNIQUE ({', '.join(value(arguments[2]))})")
        elif name == "create_check_constraint":
            condition = value(arguments[2]) if isinstance(arguments[2], ast.Constant) else ast.unparse(arguments[2])
            self.emit(line, f"ALTER TABLE {qualified(value(arguments[1]))} ADD CONSTRAINT {value(arguments[0])} CHECK ({condition})")
        elif name == "create_primary_key":
            self.emit(line, f"ALTER TABLE {qualified(value(arguments[1]))} ADD CONSTRAINT {value(arguments[0])} PRIMARY KEY ({', '.join(value(arguments[2]))})")
        elif name == "drop_constraint":
            self.emit(line, f"ALTER TABLE {qualified(value(arguments[1]))} DROP CONSTRAINT {value(arguments[0])}")
        elif name == "create_table_comment":
            self.emit(line, f"COMMENT ON TABLE {qualified(value(arguments[0]))} IS '{str(value(arguments[1])).replace(chr(39), chr(39) * 2)}'")
        elif name == "drop_table":
            self.emit(line, f"DROP TABLE {qualified(value(arguments[0]))}")
        elif name == "execute":
            sql = arguments[0]
            if isinstance(sql, ast.Call) and name_of(sql.func) == "text":
                sql = sql.args[0]
            self.emit(line, str(value(sql)))  # raw SQL: the SQL reader reads it
        elif name not in _DATA:
            self.note(line, f"op.{name}")

    def test(self, node: ast.expr, env: dict) -> bool | None:
        """An `if` the reading can decide (the dialect's name compared with a constant); None otherwise."""
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and "dialect.name" in ast.unparse(node.left):
            name = {"postgres": "postgresql", "tsql": "mssql"}.get(self.dialect_name, self.dialect_name)
            try:
                written = self.value(node.comparators[0], env)
            except Unresolved:
                return None
            if isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
                return (written == name) == isinstance(node.ops[0], ast.Eq)
            if isinstance(node.ops[0], (ast.In, ast.NotIn)):
                return (name in written) == isinstance(node.ops[0], ast.In)
        return None

    def run(self, body: list[ast.stmt], env: dict, batch: tuple[str, str] | None = None) -> None:
        for statement in body:
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
                continue  # a docstring
            if isinstance(statement, ast.Pass):
                continue
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call) and isinstance(statement.value.func, ast.Attribute):
                owner = name_of(statement.value.func.value)
                if owner == "op" or (batch and owner == batch[0]):
                    try:
                        self.op(statement.value.func.attr, statement.value, env, batch[1] if batch and owner == batch[0] else None)
                    except Unresolved as problem:
                        self.note(statement.lineno, problem.what)
                    except Exception as problem:  # what doctracker's SQLAlchemy refuses to write, or a form not foreseen
                        self.note(statement.lineno, f"op.{statement.value.func.attr}: {str(problem).splitlines()[0][:150]}")
                    continue
            if isinstance(statement, ast.With) and isinstance(statement.items[0].context_expr, ast.Call) \
                    and name_of(statement.items[0].context_expr.func) == "batch_alter_table":
                call = statement.items[0].context_expr
                alias = statement.items[0].optional_vars
                try:
                    self.run(statement.body, env, (getattr(alias, "id", ""), self.value(call.args[0], env)))
                except Unresolved as problem:
                    self.note(statement.lineno, problem.what)
                continue
            if isinstance(statement, ast.For) and isinstance(statement.target, ast.Name):
                try:
                    values = self.value(statement.iter, env)
                except Unresolved:
                    self.note(statement.lineno, f"a loop over {ast.unparse(statement.iter)[:60]}")
                    continue
                for item in values:
                    self.run(statement.body, {**env, statement.target.id: item}, batch)
                continue
            if isinstance(statement, ast.If):
                decided = self.test(statement.test, env)
                if decided is None:
                    self.note(statement.lineno, f"if {ast.unparse(statement.test)[:60]} (decided by the database or by running the code)")
                    continue
                self.run(statement.body if decided else statement.orelse, env, batch)
                continue
            self.note(statement.lineno, ast.unparse(statement).splitlines()[0][:80])


def read(root: Path, origin: dict, dialect_name: str, project: Project) -> dict:
    """Read an Alembic origin, revision after revision.

    Returns:
        `statements` (`file`, `line`, `text`), `unresolved`, `expects` (none: migrations create what they
        name) and `mapping` (none: no classes).
    """
    reader = _Reader(project, dialect_name)
    for step in origin["steps"]:
        reader.file, reader.module = step["file"], project.module_of(step["file"])
        revision = _revision(project, reader.module)
        if revision is not None:
            try:
                reader.run(revision["upgrade"].body, {})
            except (Unresolved, IndexError, TypeError) as problem:
                reader.note(getattr(problem, "line", 0), getattr(problem, "what", str(problem)))
    return {"statements": reader.statements, "unresolved": reader.unresolved, "expects": [], "mapping": []}


__all__ = ["KIND", "dialect", "find", "models_base", "read"]
