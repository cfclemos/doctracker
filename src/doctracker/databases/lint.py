"""The lint of the project's databases: what in their schema and in their migrations deserves a look.

The schema rules run over every object of `CatalogStore`, the live databases' and those the project's
files declare (the same shape, the same function); the migration rules over the steps of each migration
origin, what each statement did (`read_origin`), and for the steps that change a column or create an
index, the schema before and after the step. One finding is kept per rule, object (`schema.table.column`,
or a step's `file:line`) and detail, with every place it was found in (a database read, an origin): the
same table in several databases is one finding.

A finding the user accepts (with a reason) is kept in `doc/lint/accepted.json`, versioned with the
project as the slices are; it stays listed, marked accepted. Nothing here touches a database.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from doctracker.config import DOC_DIR
from doctracker.databases.catalog import CatalogStore
from doctracker.databases.origins.evolution import MIGRATION_KINDS, _steps_up_to
from doctracker.databases.origins.links import describe_origins
from doctracker.databases.origins.sql import read_origin
from doctracker.databases.readonly import DIALECTS
from doctracker.databases.slices import SliceStore, table_key

LEVELS = ("error", "warning", "info")
"""The levels of a finding, the gravest first."""

RULES = {
    "no-primary-key": ("error", "Table without primary key",
                       "Without a primary key a row cannot be told apart from another: updates and deletes may hit "
                       "several rows, replication and ORMs need one, duplicates go unseen. Add a primary key (an "
                       "identity column if the table has no natural one)."),
    "fk-without-index": ("warning", "Foreign key without index",
                         "The database checks the key on every delete or update of the table it refers to, and joins "
                         "go through it: without an index on its columns each of those reads the whole table, and "
                         "may lock it. Create an index starting with the key's columns."),
    "relation-by-name": ("warning", "Relation only by name",
                         "A <name>_id column matching another table's primary key, with no foreign key declared: "
                         "nothing stops it from holding ids that do not exist (orphans). Declare the foreign key, "
                         "after cleaning the values that point nowhere."),
    "fk-type-mismatch": ("warning", "Foreign key type differs",
                         "The column and the column it refers to have different types: every join converts one of "
                         "them, indexes may not be used, and values that fit one may not fit the other. Give both "
                         "the same type."),
    "redundant-index": ("warning", "Redundant index",
                        "Its columns are the first columns of another index, or of the primary key or a unique "
                        "constraint, which already serves the same reads: it only costs writes and space. Drop it "
                        "(unless it is unique where the other is not)."),
    "isolated-table": ("info", "Isolated table",
                       "No foreign key, relation by name, view or partition reaches it or leaves it. It may be a log "
                       "or configuration table, or a table forgotten; check that it is still used."),
    "nullable-fk": ("info", "Nullable foreign key",
                    "The key may be left empty: the row may exist without the row it refers to. Fine when the "
                    "relation is optional; when it is not, make the column NOT NULL."),
    "money-in-float": ("error", "Money in a floating-point type",
                       "Floating-point types (real, float, double) cannot hold most decimal fractions exactly: sums of "
                       "prices and amounts drift by cents. Use numeric / decimal with a fixed scale, or whole cents in "
                       "an integer."),
    "timestamp-without-zone": ("warning", "Timestamp without time zone",
                               "The moment is kept without its time zone: values written from servers or users in other "
                               "zones, or across daylight saving changes, cannot be compared. Use timestamp with time "
                               "zone (PostgreSQL timestamptz, SQL Server datetimeoffset), or keep every value in UTC by rule."),
    "reserved-word": ("warning", "Name is a reserved word",
                      "The name is a reserved word of SQL or of the database: every query must quote it, tools and ORMs "
                      "trip on it, and moving to another database may break. Rename it."),
    "mixed-naming": ("info", "Mixed naming convention",
                     "The names of the same schema follow different conventions (snake_case beside camelCase or "
                     "PascalCase): people and queries guess wrong. Follow the convention most names follow."),
    "no-comment": ("info", "Without comment",
                   "The table or column has no comment in the database: what it holds, its unit and its rules are "
                   "only in someone's head. Write a COMMENT ON it (agents and this wiki read it)."),
    "destructive-step": ("error", "Destructive migration step",
                         "The step drops a table or a column, or empties a table: its data is lost when the step runs, "
                         "and the code still using it breaks. Make sure the data is kept elsewhere and nothing uses it."),
    "rename-step": ("warning", "Rename in a migration step",
                    "The step renames a table or a column: the code reading the old name breaks the moment it runs, "
                    "unless both are deployed together. Prefer adding the new name, copying, then dropping the old."),
    "narrowed-type": ("error", "Type narrowed",
                      "The step changes a column to a smaller type (a shorter text, fewer digits, a smaller integer): "
                      "values that do not fit fail the step or are cut. Check the longest value first."),
    "not-null-without-default": ("error", "NOT NULL without DEFAULT",
                                 "The step makes a column of a table that already exists NOT NULL with no default: "
                                 "the step fails as soon as the table holds a row without a value. Give it a default, or "
                                 "fill it before."),
    "index-without-concurrently": ("warning", "Index created without CONCURRENTLY",
                                   "PostgreSQL locks writes on the table while it builds an index: on a big table the "
                                   "application stops writing for the whole build. Use CREATE INDEX CONCURRENTLY "
                                   "(outside a transaction)."),
    "step-without-down": ("warning", "Step without down",
                          "The step has no way back: a deployment that goes wrong cannot be rolled back by the tool. "
                          "Write its down migration."),
    "step-changed-after-applied": ("error", "Step changed after applied",
                                   "The step's file differs from what the database recorded when it ran: the databases "
                                   "migrated before and after the change are not the same. Never edit an applied step: "
                                   "write a new one."),
    "no-slice": ("info", "Table in no slice",
                 "The project has slices of its schema, and this table is in none: the part of the system it belongs "
                 "to is not told. Add it to a slice."),
}
"""Each rule's id: its level, title and help (why it matters and how to fix it)."""

ACCEPTED_FILE = f"{DOC_DIR}/lint/accepted.json"
"""Where the findings accepted by the user are kept, in the documented project."""

_TABLES = ("table", "view", "materialized view", "foreign table")
_LINKS = ("foreign key", "implied", "view reads", "foreign table", "partition of", "inherits")
"""The relations that tie a table to another (an isolated table has none)."""

_RESERVED = set("""all and any as asc between by case cast check column constraint create cross current_date current_time
current_timestamp current_user default delete desc distinct drop else end except exists false fetch for foreign from full
grant group having in inner insert intersect into is join left like not null of on or order outer primary references right
select session_user some table then to true union unique update user using values when where with""".split())
_RESERVED_BY = {
    "postgres": set("analyse analyze array asymmetric both collate do leading limit localtime localtimestamp offset only placing "
                    "returning symmetric trailing variadic window".split()),
    "mysql": set("change condition database databases div dual index interval key keys kill limit lock match mod option range "
                 "read rename schema separator show signal usage write".split()),
    "tsql": set("backup browse close database file function identity index key kill open option percent plan proc procedure "
                "public read rule schema top tran transaction trigger view".split()),
}
"""Reserved words: SQL's, then each dialect's own (a name among them must be quoted)."""

_MONEY = re.compile(r"(^|_)(price|prices|amount|amounts|total|totals|subtotal|cost|costs|salary|salaries|wage|wages|balance|"
                    r"fee|fees|tax|taxes|discount|money|valor|preco|saldo)($|_)")
_FLOATS = {"real", "double", "float", "binary_float", "binary_double"}
_TYPE_NAMES = {"character varying": "varchar", "varchar2": "varchar", "character": "char", "int": "integer", "int4": "integer",
               "serial": "integer", "serial4": "integer", "int8": "bigint", "bigserial": "bigint", "serial8": "bigint",
               "int2": "smallint", "smallserial": "smallint", "serial2": "smallint", "decimal": "numeric", "float8": "double",
               "double precision": "double", "float4": "real", "bool": "boolean", "timestamptz": "timestamp with time zone",
               "timestamp without time zone": "timestamp", "time without time zone": "time", "timetz": "time with time zone"}
_INTEGERS = {"tinyint": 1, "smallint": 2, "mediumint": 3, "integer": 4, "bigint": 5}
_LENGTHS = ("varchar", "char", "nvarchar", "nchar", "varbinary", "binary")
_TEXTS = ("text", "clob", "longtext", "mediumtext", "ntext")

_EFFECT = re.compile(r"^(?P<what>dropped (?:column|table)|renamed (?:column|table)|changed column|added column|created index) "
                     r"(?P<rest>.*)$")


def _type(text: str) -> tuple[str, tuple[str, ...]]:
    """A column's type as compared: its name in one spelling (`varchar`, `integer`, `double`...) and its arguments
    (an integer's display width dropped)."""
    text = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    found = re.search(r"\(([^)]*)\)", text)
    args = tuple(part.strip() for part in found[1].split(",")) if found else ()
    base = re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", text.split(" collate ")[0])).strip()
    unsigned = base.endswith(" unsigned")
    base = _TYPE_NAMES.get(base.removesuffix(" unsigned"), base.removesuffix(" unsigned"))
    if base in _INTEGERS:
        args = ()
    return base + (" unsigned" if unsigned else ""), args


def _narrower(before: str, after: str) -> bool:
    """Whether a column's new type holds less than its old one: a smaller integer, a shorter text, fewer digits."""
    (a, a_args), (b, b_args) = _type(before), _type(after)
    number = lambda value: int(value) if value.isdigit() else None
    if a in _INTEGERS and b in _INTEGERS:
        return _INTEGERS[b] < _INTEGERS[a]
    if a == b and a in _LENGTHS and a_args and b_args and None not in (number(a_args[0]), number(b_args[0])):
        return number(b_args[0]) < number(a_args[0])
    if a in _TEXTS and b in _LENGTHS and b_args:
        return True
    if a == b == "numeric" and a_args and b_args and all(value.isdigit() for value in a_args + b_args):
        return int(b_args[0]) < int(a_args[0]) or (len(a_args) > 1 and len(b_args) > 1 and int(b_args[1]) < int(a_args[1]))
    return False


def _style(name: str) -> str:
    """A name's convention: `snake_case` (all lower case, a single word too), `UPPER_CASE`, `PascalCase` or `camelCase`."""
    if name == name.lower():
        return "snake_case"
    if name == name.upper():
        return "UPPER_CASE"
    return "PascalCase" if name[0].isupper() else "camelCase"


def _place(path: str) -> str:
    """Where an object was found: its database read (`db:<server>/<database>`) or its origin (`origin:<name>`)."""
    return path.split("::", 1)[0] if "::" in path else "/".join(path.split("/")[:2])


class Lint:
    """The lint of the project's databases, and the findings the user accepted.

    Args:
        project_root: Root of the documented project.
        catalog: The databases read and what the files declare (`CatalogStore`).
        slices: The project's slices (`SliceStore`), for the tables in none.
        on_change: Called after a finding is accepted or its acceptance undone (the wiki reloads).
    """

    def __init__(self, project_root: Path, catalog: CatalogStore, slices: SliceStore, on_change=None) -> None:
        self.root = project_root
        self.catalog = catalog
        self.slices = slices
        self.on_change = on_change
        self.file = project_root / ACCEPTED_FILE
        self._cache: dict = {}  # the findings of the schema and of the migrations, kept until what they read changes

    def findings(self, origins: list[dict], connections: list[dict]) -> list[dict]:
        """Every finding, gravest first.

        Args:
            origins: The origins as read (`extract_origins`).
            connections: The project's connections (`ConnectionStore.connections`), for the history tables.

        Returns:
            Each finding: `key` (what identifies it), `rule`, `level`, `title` (the rule's), `help`,
            `object` (`schema.table.column`, or a step's `file:line`), `detail`, `found_in` (the databases
            read and origins holding it), `paths` (the object in each), `path` (the first), `origin` (a
            migration step's), `state` (`open` or `accepted`), and an accepted one's `reason` and `accepted`
            (when).
        """
        try:
            stamp = self.catalog.path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        if self._cache.get("schema_key") != stamp:
            self._cache.update(schema_key=stamp, schema=self._schema())
        key = (id(origins), len(origins), stamp)
        if self._cache.get("steps_key") != key:
            self._cache.update(steps_key=key, steps=self._steps(origins, connections))
        groups = {k: {**g, "found_in": list(g["found_in"]), "paths": list(g["paths"])}
                  for k, g in {**self._cache["schema"], **self._cache["steps"]}.items()}
        self._slices(groups)
        accepted = self.accepted()
        found = []
        for group in groups.values():
            level, title, help_text = RULES[group["rule"]]
            done = accepted.get(group["key"])
            found.append({**group, "level": level, "title": title, "help": help_text, "path": group["paths"][0],
                          "state": "accepted" if done else "open", "reason": (done or {}).get("reason", ""),
                          "accepted": (done or {}).get("accepted", "")})
        return sorted(found, key=lambda f: (LEVELS.index(f["level"]), f["title"], f["object"].lower(), f["detail"]))

    def for_object(self, path: str, origins: list[dict], connections: list[dict]) -> list[dict]:
        """The findings of one object of the databases (or of a file), and of what it holds (a table's columns).

        Args:
            path: The object's path.
            origins: The origins as read.
            connections: The project's connections.

        Returns:
            The findings (see `findings`) found in that object or inside it.
        """
        inside = (f"{path}.", f"{path}:")
        return [f for f in self.findings(origins, connections) if any(p == path or p.startswith(inside) for p in f["paths"])]

    # --- what is kept

    def accepted(self) -> dict[str, dict]:
        """The findings accepted, by key: `rule`, `object`, `detail`, `reason`, `accepted` (when, ISO 8601 UTC)."""
        try:
            return {item["key"]: item for item in json.loads(self.file.read_text(encoding="utf-8")).get("accepted", [])}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def accept(self, finding: dict, reason: str) -> None:
        """Accept a finding: it stays listed, marked accepted with the reason.

        Args:
            finding: The finding (see `findings`).
            reason: Why it is accepted.

        Raises:
            ValueError: When the reason is empty.
        """
        if not reason.strip():
            raise ValueError("Say why the finding is accepted.")
        kept = self.accepted()
        kept[finding["key"]] = {"key": finding["key"], "rule": finding["rule"], "object": finding["object"], "detail": finding["detail"],
                                "reason": reason.strip(), "accepted": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self._write(kept)

    def reopen(self, key: str) -> None:
        """Undo the acceptance of a finding.

        Args:
            key: The finding's key.
        """
        kept = self.accepted()
        if kept.pop(key, None) is not None:
            self._write(kept)

    def _write(self, kept: dict[str, dict]) -> None:
        """Keep the accepted findings, by rule and object, and tell the wiki."""
        self.file.parent.mkdir(parents=True, exist_ok=True)
        items = sorted(kept.values(), key=lambda item: (item["rule"], item["object"], item["detail"]))
        self.file.write_text(json.dumps({"accepted": items}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if self.on_change:
            self.on_change()

    # --- the rules

    @staticmethod
    def _add(groups: dict, rule: str, path: str, detail: str, object_: str = "", origin: str = "", place: str = "") -> None:
        """Count a finding of a rule in an object, beside the same one found elsewhere."""
        object_ = object_ or table_key(path)
        key = f"{rule}|{object_}|{detail}".lower()
        group = groups.setdefault(key, {"key": key, "rule": rule, "object": object_, "detail": detail, "origin": origin,
                                        "found_in": [], "paths": []})
        place = place or _place(path)
        if place not in group["found_in"]:
            group["found_in"].append(place)
        if path not in group["paths"]:
            group["paths"].append(path)

    def _schema(self) -> dict[str, dict]:
        """The findings of the schema rules over every object of the store, live and declared."""
        groups: dict[str, dict] = {}
        dialects = {connection: DIALECTS.get(kind, kind) for connection, kind in self.catalog.kinds().items()}
        objects = self.catalog.objects(origins=True)
        by_path = {o["path"]: o for o in objects}
        columns: dict[str, list[dict]] = {}
        for o in objects:
            if o["kind"] == "column":
                columns.setdefault(o["parent"], []).append(o)
        tied = set()  # the tables a relation reaches or leaves
        for relation in self.catalog.relations(_LINKS):
            for end in (relation["source"], relation["target"]):
                while end and end not in by_path or (end in by_path and by_path[end]["kind"] not in _TABLES):
                    end = by_path[end]["parent"] if end in by_path else ""
                if end:
                    tied.add(end)
            if relation["kind"] == "implied":
                self._add(groups, "relation-by-name", relation["source"], f"→ {table_key(relation['target'])}")
        styles: dict[tuple[str, str], list[tuple[str, str]]] = {}  # by schema and kind of name: (path, style)
        for table in objects:
            if table["kind"] not in _TABLES:
                continue
            data, path, dialect = table["data"], table["path"], dialects.get(table["connection"], "")
            own = columns.get(path, [])
            styles.setdefault((table["parent"], "table"), []).append((path, _style(table["name"])))
            if not data.get("comment"):
                self._add(groups, "no-comment", path, f"{table['kind']} without comment")
            if table["name"].lower() in _RESERVED | _RESERVED_BY.get(dialect, set()):
                self._add(groups, "reserved-word", path, f"{table['kind']} named {table['name']}")
            for column in own:
                cdata, name = column["data"], column["name"]
                styles.setdefault((table["parent"], "column"), []).append((column["path"], _style(name)))
                base = _type(cdata.get("type", ""))[0].removesuffix(" unsigned")
                if not cdata.get("comment"):
                    self._add(groups, "no-comment", column["path"], "column without comment")
                if name.lower() in _RESERVED | _RESERVED_BY.get(dialect, set()):
                    self._add(groups, "reserved-word", column["path"], f"column named {name}")
                if base in _FLOATS and _MONEY.search(re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()):
                    self._add(groups, "money-in-float", column["path"], f"{name} is {cdata.get('type')}")
                if (dialect == "postgres" and base == "timestamp") or (dialect == "tsql" and base in ("datetime", "datetime2", "smalldatetime")):
                    self._add(groups, "timestamp-without-zone", column["path"], f"{name} is {cdata.get('type')}")
            if table["kind"] != "table":
                continue
            pk = [c.lower() for c in (data.get("primary_key") or {}).get("columns") or []]
            if not pk:
                self._add(groups, "no-primary-key", path, "no primary key")
            if path not in tied:
                self._add(groups, "isolated-table", path, "no relation to another table")
            indexes = [{"name": i.get("name") or "", "columns": [c.lower() for c in i.get("columns") or []], "unique": bool(i.get("unique"))}
                       for i in data.get("indexes") or [] if i.get("columns") and not i.get("expressions")]
            uniques = [{"name": u.get("name") or "", "columns": [c.lower() for c in u.get("columns") or []]} for u in data.get("unique") or []]
            leading = [pk] + [u["columns"] for u in uniques] + [i["columns"] for i in indexes]
            for key in data.get("foreign_keys") or []:
                cols = [c.lower() for c in key["columns"]]
                shown = f"({', '.join(key['columns'])}) → {table_key(key['target'])}"
                if not any(set(found[:len(cols)]) == set(cols) for found in leading if len(found) >= len(cols)):
                    self._add(groups, "fk-without-index", path, shown)
                for source, target in zip(key["columns"], key.get("target_columns") or []):
                    column, referred = by_path.get(f"{path}.{source}"), by_path.get(f"{key['target']}.{target}")
                    if column and column["data"].get("nullable", True):
                        self._add(groups, "nullable-fk", column["path"], f"{source} → {table_key(key['target'])}.{target}")
                    if column and referred and _type(column["data"].get("type", "")) != _type(referred["data"].get("type", "")):
                        self._add(groups, "fk-type-mismatch", column["path"],
                                  f"{column['data'].get('type')} → {table_key(key['target'])}.{target} {referred['data'].get('type')}")
            pk_name = ((data.get("primary_key") or {}).get("name") or "").lower()
            constraint_names = {u["name"].lower() for u in uniques if u["name"]}
            for index in indexes:
                name, cols = index["name"], index["columns"]
                if name.lower() in constraint_names or (pk_name and name.lower() == pk_name):
                    continue  # the index the database made for the key or the constraint
                covered = ""
                if pk and (cols == pk or (not index["unique"] and pk[:len(cols)] == cols)):
                    covered = "the primary key"
                for u in uniques if not covered else []:
                    if cols == u["columns"] or (not index["unique"] and u["columns"][:len(cols)] == cols):
                        covered = f"the unique constraint {u['name']}".strip()
                        break
                for other in indexes if not covered else []:
                    if other is index or other["columns"][:len(cols)] != cols or (index["unique"] and not other["unique"]):
                        continue
                    longer = len(other["columns"]) > len(cols) and not index["unique"]
                    same = len(other["columns"]) == len(cols) and (
                        (other["unique"] and not index["unique"]) or (other["unique"] == index["unique"] and other["name"] < name))
                    if longer or same:  # of two alike, the one kept is the unique one, else the first by name
                        covered = f"the index {other['name']}"
                        break
                if covered:
                    self._add(groups, "redundant-index", path, f"index {name} ({', '.join(cols)}) covered by {covered}")
        for (_, what), named in styles.items():  # each schema's names, its tables' and its columns' apart
            counts: dict[str, int] = {}
            for _, style in named:
                counts[style] = counts.get(style, 0) + 1
            if len(counts) < 2:
                continue
            usual = max(counts, key=lambda style: (counts[style], style == "snake_case"))
            for path, style in named:
                if style != usual:
                    self._add(groups, "mixed-naming", path, f"{what} name in {style} among {usual} names")
        return groups

    def _steps(self, origins: list[dict], connections: list[dict]) -> dict[str, dict]:
        """The findings of the migration rules over each migration origin's steps."""
        groups: dict[str, dict] = {}
        migrations = [o for o in origins if o["kind"] in MIGRATION_KINDS]
        described = describe_origins(origins, self.catalog, connections, self.root) if migrations else {}
        for origin in migrations:
            name, dialect = origin["name"], origin.get("dialect", "")
            base = f"origin:{name}"
            changed: dict[str, list[str]] = {}  # a step's file name → the databases recording it otherwise
            for link in described.get(name, {}).get("links", []):
                for script in (link.get("history") or {}).get("changed", []):
                    changed.setdefault(script, []).append(link["database"])
            for step in origin["steps"]:
                file = step["file"]
                where = lambda line: f"{file}:{line}"
                if Path(file).name in changed:
                    for database in changed[Path(file).name]:
                        self._add(groups, "step-changed-after-applied", base, "changed since it was applied", file, name, database)
                if origin["kind"] == "golang-migrate" and not step.get("down"):
                    self._add(groups, "step-without-down", base, "no .down.sql", file, name)
                if origin["kind"] == "dbmate":
                    text = (self.root / file).read_text(encoding="utf-8", errors="replace")
                    down = re.split(r"--\s*migrate:down", text, maxsplit=1, flags=re.IGNORECASE)
                    body = re.sub(r"--[^\n]*", "", down[1]).strip() if len(down) > 1 else ""
                    if not body:
                        self._add(groups, "step-without-down", base, "no migrate:down section", file, name)
                before = after = None
                for statement in step.get("statements") or []:
                    for effect in statement.get("effects") or []:
                        match = _EFFECT.match(effect)
                        if not match:
                            continue
                        what = match["what"]
                        if what.startswith("dropped"):
                            self._add(groups, "destructive-step", base, effect, where(statement["line"]), name)
                        elif what.startswith("renamed"):
                            self._add(groups, "rename-step", base, effect, where(statement["line"]), name)
                        else:
                            if before is None:
                                before, after = self._around(origin, step)
                            self._change(groups, base, name, dialect, where(statement["line"]), what, match["rest"], statement, before, after)
                    if re.match(r"\s*TRUNCATE\b", statement.get("text", ""), re.IGNORECASE):
                        self._add(groups, "destructive-step", base, "truncated a table", where(statement["line"]), name)
        return groups

    def _around(self, origin: dict, step: dict) -> tuple[dict, dict]:
        """The schema of an origin just before a step and just after it (`read_origin`'s objects)."""
        steps = _steps_up_to(origin, step["version"])
        earlier = [s for s in steps if s is not step and s["file"] != step["file"]]
        try:
            before = read_origin(self.root, {**origin, "steps": earlier}, origin["dialect"])["objects"] if earlier else {}
            after = read_origin(self.root, {**origin, "steps": steps}, origin["dialect"])["objects"]
        except Exception:  # a form the reader does not foresee: the step's other rules still run
            return {}, {}
        return before, after

    def _change(self, groups: dict, base: str, name: str, dialect: str, where: str, what: str, rest: str, statement: dict,
                before: dict, after: dict) -> None:
        """The rules of a step that adds or changes a column, or creates an index: on the table as it was before."""
        def table(objects: dict, table_name: str) -> dict | None:
            wanted = table_name.split(".")[-1].strip('"`[]').lower()
            return next((o for o in objects.values() if o.get("kind") == "table" and o["name"].lower() == wanted), None)

        def column(found: dict | None, column_name: str) -> dict | None:
            return next((c for c in (found or {}).get("columns") or [] if c["name"].lower() == column_name.lower()), None)

        if what == "created index":
            on = rest.rsplit(" on ", 1)[-1]
            if dialect == "postgres" and table(before, on) and "CONCURRENTLY" not in statement.get("text", "").upper():
                self._add(groups, "index-without-concurrently", base, f"index {rest.split(' on ')[0]} on {on}", where, name)
            return
        column_name, _, table_name = rest.partition(" to " if what == "added column" else " of ")
        old_table, new_table = table(before, table_name), table(after, table_name)
        old, new = column(old_table, column_name), column(new_table, column_name)
        if old_table is None or new is None:
            return  # a table created in the same step: nothing in it to break
        no_default = not new.get("default") and not new.get("identity") and not new.get("computed")
        if not new.get("nullable", True) and no_default and (old is None or old.get("nullable", True)):
            self._add(groups, "not-null-without-default", base, f"{column_name} of {table_name}", where, name)
        if old and new and _narrower(old.get("type", ""), new.get("type", "")):
            self._add(groups, "narrowed-type", base, f"{column_name} of {table_name}: {old.get('type')} → {new.get('type')}", where, name)

    def _slices(self, groups: dict) -> None:
        """The tables in no slice, when the project has slices."""
        kept = self.slices.slices()
        if not kept:
            return
        sliced = {table_key(t["path"]).lower() for s in kept for t in s.get("tables", [])}
        for table in self.catalog.objects(origins=True):
            if table["kind"] in _TABLES and table_key(table["path"]).lower() not in sliced:
                self._add(groups, "no-slice", table["path"], f"{table['kind']} in no slice")


__all__ = ["ACCEPTED_FILE", "LEVELS", "RULES", "Lint"]
