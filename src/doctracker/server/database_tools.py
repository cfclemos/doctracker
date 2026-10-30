"""MCP tools over the project's database connections: thin wrappers over `ConnectionStore`, the same the wiki uses.

Agents can list the connections and test them; allowing a declared connection, entering one and
removing one are the user's decisions, made only in the wiki.
"""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from doctracker.databases import ConnectionStore, Locked
from doctracker.databases.readonly import run_test
from doctracker.server.note_tools import refusals_reported


def register_database_tools(mcp: MCPServer, connections: ConnectionStore) -> None:
    """Add the tools that list and test the project's database connections.

    Args:
        mcp: Server to register the tools on.
        connections: Store of the connections (the same one the wiki uses).
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
