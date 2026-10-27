"""Build the doctracker server: MCP endpoint at `/mcp`, wiki frontend and watcher."""

import asyncio
import contextlib
from pathlib import Path

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from doctracker import __version__
from doctracker.config import NOTES_DATABASE_PATH, Config
from doctracker.embeddings.service import EmbeddingService
from doctracker.notes import NoteStore
from doctracker.search import SearchEngine
from doctracker.server.hooks import hook_routes
from doctracker.server.note_tools import register_note_tools
from doctracker.server.state import DocState
from doctracker.server.tools import register_tools
from doctracker.server.watcher import watch
from doctracker.server.web import web_routes
from doctracker.storage.index import entity_documents

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
"""Hosts the MCP SDK already protects against DNS rebinding by itself."""


def create_app(project_root: Path, config: Config) -> Starlette:
    """Create the ASGI app with every service the server provides.

    MCP endpoint at `/mcp`, the wiki routes, the hook routes (`/hooks/...`), the file watcher, the embedding
    service (prepared on demand, stopped with the server), and the search engine
    and the notes store, both shared by the MCP tools and the wiki.

    Args:
        project_root: Root of the documented project.
        config: Project settings.

    Returns:
        The Starlette app, ready to be served by uvicorn.
    """
    state = DocState()
    # Until the first extraction ends, entity paths cannot be checked, so they are accepted.
    notes = NoteStore(project_root / NOTES_DATABASE_PATH, lambda path: not state.ready or path in state.entities,
                      state.notify)

    def documents() -> dict[str, tuple[str, str]]:
        """Everything searchable: the code's entities and the planner items and notes."""
        found = entity_documents(state.entities)
        found.update({key: (document["title"], document["text"]) for key, document in notes.searchable().items()})
        return found

    embeddings = EmbeddingService(project_root, config, documents)
    search = SearchEngine(state, embeddings, notes)
    mcp = MCPServer(
        name="doctracker",
        version=__version__,
        instructions=(
            "This project keeps its plans, guidelines and memory here: record notes, decisions and progress "
            "with these tools (create_note, annotate_task, update_task), not in files or local memory, and call "
            "recall(query) before planning, changing code or writing a note. "
            "Technical documentation of this project, built from its code. "
            "Use list_entities to explore and get_entity for details. To find entities, use "
            "hybrid_search (words and meaning), bm25_search (words) or semantic_search (meaning). "
            "Before writing or changing docstrings, call documentation_guide (also available as the "
            "doctracker://guide resource) and follow it."
        ),
    )
    register_tools(mcp, state, config, search)
    register_note_tools(mcp, notes, search)

    app = mcp.streamable_http_app(host=config.host, transport_security=_transport_security(config))
    app.router.routes.extend(web_routes(state, project_root, config, search, notes))
    app.router.routes.extend(hook_routes(state, project_root, notes))

    mcp_lifespan = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(starlette_app: Starlette):
        async with mcp_lifespan(starlette_app) as lifespan_state:
            tasks = [
                asyncio.create_task(watch(project_root, config, state, notes)),
                asyncio.create_task(embeddings.stop_when_idle()),
            ]
            try:
                yield lifespan_state
            finally:
                for task in tasks:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                await embeddings.stop()

    app.router.lifespan_context = lifespan
    return app


def _transport_security(config: Config) -> TransportSecuritySettings | None:
    """Choose the Host/Origin validation of the MCP endpoint.

    Args:
        config: Project settings; `host` and `ssl_certfile` are used.

    Returns:
        `None` for local hosts (the SDK already protects them), otherwise settings
        that allow only the configured host.
    """
    if config.host in LOCAL_HOSTS:
        return None
    scheme = "https" if config.ssl_certfile else "http"
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{config.host}:*"],
        allowed_origins=[f"{scheme}://{config.host}:*"],
    )


def run(project_root: Path, config: Config) -> None:
    """Start the server and block until it stops.

    Args:
        project_root: Root of the documented project.
        config: Project settings; with `ssl_certfile` and `ssl_keyfile`, the server uses HTTPS.
    """
    uvicorn.run(
        create_app(project_root, config),
        host=config.host,
        port=config.port,
        ssl_certfile=config.ssl_certfile,
        ssl_keyfile=config.ssl_keyfile,
        log_level="info",
    )
