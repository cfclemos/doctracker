"""MCP tools that let agents read the technical documentation."""

from mcp.server import MCPServer

from doctracker.config import Config
from doctracker.server.guide import documentation_guide as build_guide
from doctracker.server.state import DocState

GUIDE_URI = "doctracker://guide"


def register_tools(mcp: MCPServer, state: DocState, config: Config) -> None:
    """Add the documentation tools and the documentation guide to the MCP server."""

    @mcp.tool()
    def documentation_guide() -> str:
        """Explain how to document this project's code so doctracker builds complete pages.

        Read it before writing or changing docstrings, module docstrings, type hints or `__all__`.

        Returns:
            The guide in Markdown, adapted to this project's settings (docstring style, private members).
        """
        return build_guide(config)

    @mcp.resource(GUIDE_URI, name="documentation-guide", title="How to document code for doctracker",
                  mime_type="text/markdown")
    def guide_resource() -> str:
        """How to document this project's code so doctracker builds complete pages."""
        return build_guide(config)

    @mcp.tool()
    def list_entities(prefix: str = "", kind: str = "") -> list[dict]:
        """List documented entities.

        Args:
            prefix: Only entities whose qualified path starts with this text (e.g. `mypkg.api`).
            kind: Only entities of this kind: `module`, `class`, `function`, `attribute` or `type alias`.

        Returns:
            One item per entity with its path, kind and the first line of its docstring.
        """
        items = []
        for path, entity in sorted(state.entities.items()):
            if prefix and not path.startswith(prefix):
                continue
            if kind and entity["kind"] != kind:
                continue
            summary = entity["docstring"].strip().split("\n", 1)[0] if entity["docstring"] else ""
            items.append({"path": path, "kind": entity["kind"], "summary": summary})
        return items

    @mcp.tool()
    def get_entity(path: str) -> dict:
        """Get the full technical reference of one entity.

        Args:
            path: Qualified path of the entity (e.g. `mypkg.api.get_weather`).

        Returns:
            Signature data, parameters, docstring sections, location in the code and members.
        """
        entity = state.entities.get(path)
        if entity is None:
            raise ValueError(f"Unknown entity: {path}")
        return entity

    @mcp.tool()
    def status() -> dict:
        """Report whether the documentation is built and any loading errors."""
        return {
            "ready": state.ready,
            "packages": state.roots,
            "entities": len(state.entities),
            "errors": state.errors,
        }
