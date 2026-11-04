"""Read the schema an ORM's code declares, without running it, into the DDL the ORM would send.

One module per ORM, each with the same three functions:

- `find(root, files, project)`: its origins, as `find_origins` gives the SQL ones (`name`, `kind`,
  `folder`, `steps`);
- `dialect(root, origin, project)`: the SQL dialect the origin is written for, and what says so;
- `read(root, origin, dialect, project)`: the DDL statements (`file`, `line`, `text`), what could not be
  resolved without running the code, the tables it expects but does not create, and the mapping of its
  classes to tables.

From the statements on, an ORM's origin takes the SQL files' path (`sql.read_origin` applies them, then
`collection.as_collection`): one shape, one store and one page whatever the source. `python.Project`
is the static reader of the project's Python they share.
"""

from pathlib import Path

from doctracker.databases.origins.orm import alembic, django, prisma, sqlalchemy
from doctracker.databases.origins.orm.python import Project

READERS = {sqlalchemy.KIND: sqlalchemy, alembic.KIND: alembic, **{kind: django for kind in django.KINDS}, prisma.KIND: prisma}
"""The ORM readers, by the kind of the origins they find."""


def find(root: Path, files: list[str], project: Project) -> list[dict]:
    """Every ORM origin of the project, reader after reader."""
    found = []
    for reader in dict.fromkeys(READERS.values()):  # each reader once (Django's finds both its kinds)
        found += reader.find(root, files, project)
    bases = {tuple(origin["base"]): origin for origin in found if origin["kind"] == sqlalchemy.KIND}
    for origin in found:  # Alembic's env.py importing the models' base: the same schema
        if origin["kind"] == alembic.KIND and (base := alembic.models_base(project, origin)) in bases:
            origin["related"], bases[base]["related"] = bases[base]["name"], origin["name"]
    return found


def read(root: Path, origin: dict, project: Project) -> dict:
    """Read an ORM origin with its reader.

    Returns:
        What the reader's `read` gives, with `dialect` and `dialect_from` (what says the dialect).
    """
    reader = READERS[origin["kind"]]
    dialect, said_by = reader.dialect(root, origin, project)
    return {**reader.read(root, origin, dialect, project), "dialect": dialect, "dialect_from": said_by}


__all__ = ["READERS", "Project", "find", "read"]
