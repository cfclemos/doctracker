"""Frontend routes: wiki pages, source code on demand and live-update events."""

import asyncio
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from doctracker.config import Config, update_config_value
from doctracker.server.state import DocState
from doctracker.wiki import pages

KEEPALIVE_SECONDS = 15


def _same_origin(request: Request) -> bool:
    """Writes are accepted only from pages served by this server (blocks other sites in the browser)."""
    origin = request.headers.get("origin")
    return origin is not None and origin == f"{request.url.scheme}://{request.headers.get('host', '')}"


def web_routes(state: DocState, project_root: Path, config: Config) -> list[BaseRoute]:
    """Build the frontend routes served next to the MCP endpoint."""
    templates = Environment(loader=PackageLoader("doctracker.wiki", "templates"), autoescape=select_autoescape())
    templates.filters["markdown"] = pages.render_markdown
    templates.filters["highlight"] = pages.highlight
    templates.globals.update(
        code_theme=config.code_theme if config.code_theme in pages.CODE_THEMES else "default",
        code_themes=pages.CODE_THEMES,
        signature=pages.signature,
        summary=pages.summary,
        page_role=pages.page_role,
        symbols=pages.SYMBOLS,
        members_by_group=pages.members_by_group,
        parameter_rows=pages.parameter_rows,
        other_sections=pages.other_sections,
    )

    def render(request: Request, path: str) -> HTMLResponse:
        entity = state.entities.get(path)
        context = {"path": path, "state": state, "entity": entity, "tree": pages.tree(state, path)}
        if not state.ready:
            content, status = "loading.html", 200
        elif entity is None:
            content, status = "not_found.html", 404
        else:
            content, status = ("module.html" if entity["kind"] == "module" else "entity.html"), 200
            context["breadcrumbs"] = pages.breadcrumbs(state, path)
        is_fragment = "HX-Request" in request.headers and "HX-History-Restore-Request" not in request.headers
        template = "fragment.html" if is_fragment else "base.html"
        html = templates.get_template(template).render(content=content, **context)
        return HTMLResponse(html, status_code=status)

    async def index(request: Request) -> Response:
        if state.ready and state.roots:
            return RedirectResponse(f"/wiki/{state.roots[0]}")
        return render(request, "")

    async def wiki(request: Request) -> Response:
        return render(request, request.path_params["path"])

    async def source(request: Request) -> Response:
        entity = state.entities.get(request.path_params["path"])
        if entity is None:
            return HTMLResponse("", status_code=404)
        code = pages.source_code(project_root, entity)
        return HTMLResponse(templates.get_template("source.html").render(code=code))

    async def search(request: Request) -> Response:
        query = request.query_params.get("q", "")
        results = pages.search(state, query)
        return HTMLResponse(templates.get_template("search.html").render(results=results, query=query))

    async def theme(request: Request) -> Response:
        name = request.path_params["name"]
        if name not in pages.CODE_THEMES:
            return Response("", status_code=404)
        return Response(pages.code_theme_css(name), media_type="text/css")

    async def set_code_theme(request: Request) -> Response:
        """Save the code theme chosen in the frontend into `config.json`."""
        if not _same_origin(request):
            return Response("", status_code=403)
        name = (await request.form()).get("code_theme", "")
        if name not in pages.CODE_THEMES:
            return Response("", status_code=400)
        config.code_theme = name
        templates.globals["code_theme"] = name
        update_config_value(project_root, "code_theme", name)
        return Response("", status_code=204)

    async def events(request: Request) -> Response:
        queue = state.subscribe()

        async def stream():
            try:
                while True:
                    try:
                        await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
                        yield "event: changed\ndata: 1\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                state.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return [
        Route("/", index),
        Route("/wiki/{path:path}", wiki),
        Route("/source/{path:path}", source),
        Route("/search", search),
        Route("/code-theme/{name}.css", theme),
        Route("/settings/code-theme", set_code_theme, methods=["POST"]),
        Route("/events", events),
        Mount("/static", StaticFiles(packages=[("doctracker.wiki", "static")]), name="static"),
    ]
