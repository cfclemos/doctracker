"""Build the doctracker server: MCP endpoint at `/mcp`, wiki frontend and watcher."""

import asyncio
import contextlib
from pathlib import Path

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette

from doctracker import __version__
from doctracker.config import Config
from doctracker.embeddings.service import EmbeddingService
from doctracker.search import SearchEngine
from doctracker.server.state import DocState
from doctracker.server.tools import register_tools
from doctracker.server.watcher import watch
from doctracker.server.web import web_routes

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
"""Hosts the MCP SDK already protects against DNS rebinding by itself."""


def create_app(project_root: Path, config: Config) -> Starlette:
    """Create the ASGI app with every service the server provides.

    MCP endpoint at `/mcp`, the wiki routes, the file watcher, the embedding
    service (prepared on demand, stopped with the server) and the search engine
    shared by the MCP tools and the wiki.

    Args:
        project_root: Root of the documented project.
        config: Project settings.

    Returns:
        The Starlette app, ready to be served by uvicorn.
    """
    state = DocState()
    embeddings = EmbeddingService(project_root, config, state)
    search = SearchEngine(state, embeddings)
    mcp = MCPServer(
        name="doctracker",
        version=__version__,
        instructions=(
            "Technical documentation of this project, built from its code. "
            "Use list_entities to explore and get_entity for details. To find entities, use "
            "hybrid_search (words and meaning), bm25_search (words) or semantic_search (meaning). "
            "Before writing or changing docstrings, call documentation_guide (also available as the "
            "doctracker://guide resource) and follow it."
        ),
    )
    register_tools(mcp, state, config, search)

    app = mcp.streamable_http_app(host=config.host, transport_security=_transport_security(config))
    app.router.routes.extend(web_routes(state, project_root, config, search))

    mcp_lifespan = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(starlette_app: Starlette):
        async with mcp_lifespan(starlette_app) as lifespan_state:
            tasks = [
                asyncio.create_task(watch(project_root, config, state)),
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
