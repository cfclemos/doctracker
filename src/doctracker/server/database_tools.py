"""MCP tools over the project's database connections: thin wrappers over `ConnectionStore`, the same the wiki uses.

Agents can list the connections, test them, read what the server last read from each allowed
connection's database (it reads them by itself, read only) and ask for a database to be read again now; allowing a declared connection, entering one and removing one
are the user's decisions, made only in the wiki.
"""

from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from doctracker.databases import CatalogStore, ConnectionStore, Locked, collect_connection
from doctracker.databases.origins import comparisons, database_object as object_with_origins, describe_origins
from doctracker.graph import MAX_CALL_DEPTH, er_diagram, trim_view
from doctracker.server.state import DocState
from doctracker.databases.readonly import run_test
from doctracker.server.note_tools import refusals_reported


def register_database_tools(mcp: MCPServer, connections: ConnectionStore, catalog: CatalogStore, state: DocState,
                            project_root: Path) -> None:
    """Add the tools over the project's database connections, what was collected from them, and the
    origins of the schema (SQL files and migrations).

    Args:
        mcp: Server to register the tools on.
        connections: Store of the connections (the same one the wiki uses).
        catalog: What was last read from each database (the same store the wiki uses).
        state: The project as read, with its origins.
        project_root: Root of the documented project.
    """

    @mcp.tool()
    @refusals_reported
    def list_connections() -> list[dict]:
        """List the project's database connections: those its files declare and those the user entered.

        A declared connection is blocked until the user allows it in the wiki (DATABASE ›
        Connections); only allowed ones can be tested or read. Passwords are never given: `password`
        is the variable holding it (`${PGPASSWORD}`), `•••` when written in a file or saved, or empty.

        Returns:
            Each connection: `id`, `name`, `kind`, `host`, `port`, `database`, `user`, `password`,
            `source` (what declared it, or `entered`), `origin` (file and line), `allowed`.
        """
        return connections.connections()

    @mcp.tool()
    @refusals_reported
    async def test_connection(connection_id: str) -> dict:
        """Test an allowed connection, read only: connect, read the server's version, try a write.

        Nothing is changed: the session is read only where the database allows it, the transaction
        is rolled back, and the write tried is aborted before it reaches the database.

        Args:
            connection_id: The connection, from `list_connections`.

        Returns:
            `ok`, `version`, `read_only_session` (None where the database has no such session),
            `can_write` (SQL Server: whether the user holds write permissions), `write_refused`,
            `error` and `seconds`.
        """
        try:
            spec = connections.spec(connection_id)
        except Locked as locked:
            raise ToolError(f"{locked} The user unlocks it in the wiki (DATABASE › Connections).") from locked
        return await run_test(spec)

    @mcp.tool()
    @refusals_reported
    async def refresh_database(connection_id: str) -> dict:
        """Read an allowed connection's database again now, from its catalog, read only.

        The server already reads every allowed connection by itself (when allowed, at start and every
        minute); this is for a change just made in the database.

        Reads every schema of the connection's database: tables, views, materialized views, foreign
        tables, columns (type, null, default, comment, marks), keys, constraints, indexes, sequences,
        types, functions, procedures, triggers, comments, row estimates and sizes; and the relations
        (foreign key, implied, view reads, foreign table, partition of, inherits, trigger calls).
        Only the state last read is kept; the other tools give it.

        Args:
            connection_id: The connection, from `list_connections`.

        Returns:
            The database's state: `started` (when read), `seconds`, `version`, `server`, `database`,
            `databases` (the other databases on the server, not read), `counts` (objects and relations
            by kind), `unavailable` (what could not be read, and why) and `failure` (`started`, `error`)
            when reading it again failed (the state read before is kept).
        """
        try:
            return await collect_connection(connections, catalog, connection_id)
        except Locked as locked:
            raise ToolError(f"{locked} The user unlocks it in the wiki (DATABASE › Connections).") from locked

    @mcp.tool()
    @refusals_reported
    def database_objects(connection_id: str = "", kind: str = "", schema: str = "", within: str = "",
                         name: str = "") -> list[dict]:
        """List the objects of the databases as last read: every connection's, or one's.

        Args:
            connection_id: Only this connection's; empty for all.
            kind: Only this kind: `schema`, `table`, `view`, `materialized view`, `foreign table`, `column`,
                `sequence`, `enum`, `domain`, `function`, `procedure`, `aggregate`, `trigger`, `synonym`.
            schema: Only what is inside a schema of this name.
            within: Only what is inside this server, database or schema, by its path
                (`db:<server>`, `db:<server>/<database>`, `db:<server>/<database>/<schema>`).
            name: Only the objects whose name holds this text.

        Returns:
            Each object's `path` (`db:<server>/<database>/<schema>.<name>`), `kind`, `parent`, `name`,
            `connection` and `data` (type, comment, keys, indexes, row estimate... as it applies).
        """
        return catalog.objects(connection_id, kind, schema, within, name)

    @mcp.tool()
    @refusals_reported
    def database_level(at: str = "") -> dict:
        """Browse the databases as last read, one level of the SQL tree at a time (as the wiki's Navigate Database).

        Args:
            at: Empty for the servers; then a server's path for its databases, a database's for its
                schemas, a schema's for its tables and views, a table's or view's for its columns
                (the `path` of a row of the level above).

        Returns:
            `at`, `level` (servers, databases, schemas, tables, columns) and `rows`, each with its `path`,
            `name`, what that level counts or shows of it (databases, schemas, tables, views,
            functions, columns, rows, size, type, null, default, marks, comment...) and `down` (it
            holds a next level).
        """
        return catalog.level(at)

    @mcp.tool()
    @refusals_reported
    def er_diagram_view(project: str = "", focus: str = "", depth: int = MAX_CALL_DEPTH, kinds: list[str] | None = None,
                        hide_unconnected: bool = False) -> dict:
        """Get the entity-relationship diagram of the project's databases, as the wiki's DATABASE › Diagram (ER) draws it.

        The live databases and what the project's files declare, in the levels of the DATABASES tree;
        each table and view with its columns, and how the tables relate. Over 500 boxes, only the most
        connected.

        Args:
            project: Only what is inside this level (`databases:<project>`); empty for all.
            focus: A table or view (its path): it and those `depth` relations away; or a level (a database,
                schema or origin): only what it holds.
            depth: How many relations away from a focused table (1 to 3).
            kinds: Only these relations: `foreign-key`, `implied`, `view-reads`, `partition-of`, `inherits`,
                `foreign-table`; all by default.
            hide_unconnected: Leave out the tables with no relation.

        Returns:
            `nodes` (the levels as frames; tables and views with `columns`: name, type, marks, nullable,
            comment, path), `edges` (`source`, `target`, `kind`; a foreign key's and an implied one's
            `via` and `to` columns and the cardinality of each end: `source_end` zero-one / zero-many,
            `target_end` one / zero-one) and `left_out` (boxes over the limit).
        """
        graph = er_diagram(state, catalog, connections.connections(), "", project, focus, max(1, min(depth, MAX_CALL_DEPTH)))
        return trim_view(graph, kinds, hide_unconnected)

    @mcp.tool()
    @refusals_reported
    def database_object(path: str) -> dict:
        """Give one object of the databases as last read, or one the project's SQL files declare (the same
        shape), with what it holds and its relations.

        Args:
            path: The object's path, from `database_objects`, `database_origin` or a search
                (`db:<server>/<database>/<schema>.<name>`, or `origin:<origin>::<schema>.<name>`).

        Returns:
            The object (see `database_objects`) with `children` (path, kind, name, data), `relations`
            (`source`, `target`, `kind`; both directions, a table's with its columns' and triggers'),
            `ends` (kind, name, parent of each object they reach), `read` (when its database was read),
            `declared` (a file's: where it was created and last changed), `unavailable` (what could not be
            read of its database, and why) and, for a table, view or column, `declared_by` on a live one
            (the origins declaring it and where they differ) or `found_in` on a file's (where it is in the
            databases its file describes, and where they differ).
        """
        found = object_with_origins(path, state.origins, catalog, connections.connections(), project_root)
        if found is None:
            raise ToolError(f"No object {path} in the databases read nor in the SQL files. List them with "
                            "database_objects or database_origin.")
        return found

    @mcp.tool()
    @refusals_reported
    def database_origins() -> list[dict]:
        """List the origins of the project's database schema: migration sets (Flyway, golang-migrate,
        dbmate, Alembic, Django, Prisma), SQL files that declare tables, views, functions..., and ORM
        models (SQLAlchemy, Django, a Prisma schema), read as text, never run.

        Returns:
            Each origin's `name` (its folder or file), `kind`, `dialect`, `steps` (how many), `unread`
            (statements not understood), `objects` (how many it ends with) and `links`: the databases it
            describes, each with `how` the link was made (`chosen` by the user, the tool's `history`
            table, `declared` in its configuration) and what its history says (steps applied, pending).
            A dump also has `tool`, `dump` (what it writes of itself, each with its line), `generated`
            (`at`, and `source`: `dump` with its line, `git` with its commit, or none) and, for one
            database of a dump holding several (`<file>@<database>`: `@`, not `#`, which a URL cuts), `part_of` and `lines`.
        """
        described = describe_origins(state.origins, catalog, connections.connections(), project_root)
        return [{"name": o["name"], "kind": o["kind"], "dialect": o["dialect"], "steps": len(o["steps"]),
                 "unread": sum(step["unread"] for step in o["steps"]), "objects": len(o["objects"]),
                 "links": described[o["name"]]["links"], "suggestions": described[o["name"]]["suggestions"],
                 **{key: o[key] for key in ("tool", "dump", "generated", "part_of", "lines") if key in o}}
                for o in state.origins]

    @mcp.tool()
    @refusals_reported
    def database_origin(name: str) -> dict:
        """Give one origin of the schema: its steps (each statement's line and what it did), the schema
        it ends with (each object with the file and line that created and last changed it), the
        databases it describes and where it differs from each.

        Args:
            name: The origin's name, from `database_origins`.

        Returns:
            The origin with `steps`, `objects`, `links`, `unlinked`, `suggestions`, `warning` and
            `differences` by database (`missing`, `extra`, and per table its `differences`); an ORM's
            also by `origin:<name>`, its other origin (its models against its migrations: `related`).
        """
        origin = next((o for o in state.origins if o["name"] == name), None)
        if origin is None:
            raise ToolError(f"No origin {name}. List them with database_origins.")
        described = describe_origins(state.origins, catalog, connections.connections(), project_root)[name]
        return {**origin, **described,
                "differences": comparisons(origin, described, catalog)}
