"""The origins of the project's schema: the SQL files and migrations that declare it, read as text.

An origin is either a set of migration steps of a known tool, applied in order — Flyway
(`V<version>__<name>.sql`), golang-migrate (`<version>_<name>.up.sql`, its `.down.sql` the undo of
the step), dbmate (`-- migrate:up` / `-- migrate:down` in each file) — or any other `.sql` file that
declares schema (CREATE / ALTER / DROP / COMMENT ON): a schema file, an initdb script, a dump.
Files that only query or fill tables are not origins.

Each statement is read with sqlglot in the origin's dialect; what its grammar leaves as a raw command
(domains, types, functions and triggers written in PL code, MySQL's DEFINER objects...) is read by our
own rules from its text, and what neither understands is kept as "not read". The steps are applied in
order into one schema (tables with their columns, keys, constraints and indexes; views and what they
read; functions, procedures, triggers, sequences, types), every object remembering the file and line
that created it and the last that changed it; partitions and child tables take their parent's
columns. Nothing is run: the files are only read.

An ORM's code is an origin too (`orm`): SQLAlchemy models, Alembic migrations, Django models and
migrations, a Prisma schema (its `migrations/` folder is SQL), each read without running it into the DDL
its ORM would send, then the same path as the SQL files.

The package's modules: `sql` (find the origins, cut and read their SQL), `orm` (the ORMs' readers),
`collection` (the schema an origin ends with as a live database's collection), `links` (which databases
each origin describes) and `compare` (where they differ, both ways).
"""

from doctracker.databases.origins.collection import ORIGIN_PREFIX, as_collection
from doctracker.databases.origins.compare import DIFF_TABS, compare, database_object, declared_by, default_b, found_in, place_level
from doctracker.databases.origins.links import HISTORY_TOOLS, describe_origins, flyway_checksum
from doctracker.databases.origins.sql import DEFAULT_SCHEMAS, extract_origins, find_origins, guess_dialect, read_origin, split_statements

__all__ = ["DEFAULT_SCHEMAS", "DIFF_TABS", "HISTORY_TOOLS", "ORIGIN_PREFIX", "as_collection", "compare", "database_object", "declared_by",
           "default_b", "describe_origins", "extract_origins", "find_origins", "flyway_checksum", "found_in", "guess_dialect", "place_level", "read_origin",
           "split_statements"]
