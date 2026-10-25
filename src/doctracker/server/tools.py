"""MCP tools that let agents read the technical documentation."""

from mcp.server import MCPServer

from doctracker.config import Config, set_config_value
from doctracker.search import AGENT_WAIT_SECONDS, DEFAULT_LIMIT, SearchEngine
from doctracker.server.guide import documentation_guide as build_guide
from doctracker.server.state import DocState
from doctracker.wiki.pages import summary

GUIDE_URI = "doctracker://guide"
"""URI of the MCP resource with the documentation guide."""


def register_tools(mcp: MCPServer, state: DocState, config: Config, search: SearchEngine) -> None:
    """Add the documentation tools and the documentation guide to the MCP server.

    Args:
        mcp: Server to register the tools and the guide resource on.
        state: Extracted entities the tools read.
        config: Project settings; the `set_*` tools change it and save it to config.json.
        search: Search engine behind the search tools (the same one the wiki uses).
    """
    embeddings = search.embeddings
    project_root = embeddings.project_root

    @mcp.tool()
    async def bm25_search(query: str, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Find entities by the words they share with the query, ranked by BM25.

        Words count in any order; rare words weigh more, and matches in the name more than
        in the description. Identifiers are split (`get_weather` matches "weather").

        Args:
            query: Words to look for (in the language of the docstrings).
            limit: Results per page.
            offset: Results to skip, for the next pages (e.g. `offset=10` with `limit=10` is page 2).

        Returns:
            `status`, `total`, `offset` and `results`: path, kind, BM25 score (higher is better) and summary.
        """
        return search.describe(await search.run("bm25", query, max(1, limit), AGENT_WAIT_SECONDS, offset))

    @mcp.tool()
    async def semantic_search(query: str, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Find entities by meaning, in any language (e.g. "what happens when the city does not exist?").

        The first call may download the embedding model and llama.cpp and build the index;
        while that happens the answer has `"status": "preparing"` and a progress `step`.
        Call again later (or check `embedding_status`).

        Args:
            query: Question or description of what you are looking for.
            limit: Results per page.
            offset: Results to skip, for the next pages (e.g. `offset=10` with `limit=10` is page 2).

        Returns:
            `status`, and when ready, `total`, `offset` and `results`: path, kind, similarity score (0 to 1) and summary.
        """
        return search.describe(await search.run("semantic", query, max(1, limit), AGENT_WAIT_SECONDS, offset))

    @mcp.tool()
    async def hybrid_search(query: str, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Find entities with BM25 and semantic search combined (reciprocal rank fusion).

        Usually the best choice: words and meaning both count. Needs the embedding model,
        like `semantic_search` (answers `"status": "preparing"` while it is being prepared).

        Args:
            query: Words or a question, in any language.
            limit: Results per page.
            offset: Results to skip, for the next pages (e.g. `offset=10` with `limit=10` is page 2).

        Returns:
            `status`, and when ready, `total`, `offset` and `results`: path, kind, fused score (higher is better) and summary.
        """
        return search.describe(await search.run("hybrid", query, max(1, limit), AGENT_WAIT_SECONDS, offset))

    @mcp.tool()
    def embedding_status() -> dict:
        """Report the embedding backend: state, model, device, llama.cpp build, models folder and index size."""
        return embeddings.status()

    @mcp.tool()
    async def set_embedding_model(model: str) -> dict:
        """Change the embedding model and save it in config.json.

        With a vLLM server configured (`embeddings.vllm_url`), this sets the model name served by vLLM.
        Otherwise it sets the GGUF model for llama.cpp, downloaded on next use.

        Args:
            model: For llama.cpp, `owner/repo/file.gguf` on Hugging Face
                (e.g. `Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf`) or a local `.gguf` path.
                For vLLM, the served model name (e.g. `Qwen/Qwen3-Embedding-0.6B`).

        Returns:
            The new embedding status. The index is rebuilt with the new model on next use.
        """
        key = "vllm_model" if embeddings.uses_vllm else "model"
        if key == "model" and not model.endswith(".gguf"):
            raise ValueError("Use 'owner/repo/file.gguf' (Hugging Face) or the path of a local .gguf file")
        set_config_value(project_root, config, key, model, section="embeddings")
        await embeddings.reset()
        return embeddings.status()

    @mcp.tool()
    async def set_models_dir(path: str = "") -> dict:
        """Change the folder for embedding models and llama.cpp binaries, and save it in config.json.

        Args:
            path: Absolute path, or relative to the project root. Empty means the default, `doc/models`.

        Returns:
            The new embedding status. Files are downloaded to the new folder on next use.
        """
        set_config_value(project_root, config, "models_dir", path.strip() or None, section="embeddings")
        await embeddings.reset()
        return embeddings.status()

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
            items.append({"path": path, "kind": entity["kind"], "summary": summary(entity)})
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
