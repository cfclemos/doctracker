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
from doctracker.server.state import DocState
from doctracker.server.tools import register_tools
from doctracker.server.watcher import watch
from doctracker.server.web import web_routes

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def create_app(project_root: Path, config: Config) -> Starlette:
    """Create the ASGI app with every service the server provides."""
    state = DocState()
    mcp = MCPServer(
        name="doctracker",
        version=__version__,
        instructions=(
            "Technical documentation of this project, built from its code. "
            "Use list_entities to explore and get_entity for details. "
            "Before writing or changing docstrings, call documentation_guide (also available as the "
            "doctracker://guide resource) and follow it."
        ),
    )
    register_tools(mcp, state, config)

    app = mcp.streamable_http_app(host=config.host, transport_security=_transport_security(config))
    app.router.routes.extend(web_routes(state, project_root, config))

    mcp_lifespan = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def lifespan(starlette_app: Starlette):
        async with mcp_lifespan(starlette_app) as lifespan_state:
            watcher = asyncio.create_task(watch(project_root, config, state))
            try:
                yield lifespan_state
            finally:
                watcher.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await watcher

    app.router.lifespan_context = lifespan
    return app


def _transport_security(config: Config) -> TransportSecuritySettings | None:
    """Host/Origin validation. The SDK already protects local hosts; other hosts are allowed explicitly."""
    if config.host in LOCAL_HOSTS:
        return None
    scheme = "https" if config.ssl_certfile else "http"
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{config.host}:*"],
        allowed_origins=[f"{scheme}://{config.host}:*"],
    )


def run(project_root: Path, config: Config) -> None:
    """Start the server and block until it stops."""
    uvicorn.run(
        create_app(project_root, config),
        host=config.host,
        port=config.port,
        ssl_certfile=config.ssl_certfile,
        ssl_keyfile=config.ssl_keyfile,
        log_level="info",
    )
