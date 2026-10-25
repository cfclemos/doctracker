"""Frontend routes: wiki pages, source code on demand and live-update events."""

import asyncio
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from doctracker.config import Config, set_config_value
from doctracker.search import DEFAULT_LIMIT, MODES, WIKI_WAIT_SECONDS, SearchEngine
from doctracker.server.state import DocState
from doctracker.wiki import pages

KEEPALIVE_SECONDS = 15
"""Seconds between keepalive messages on an idle live-update (SSE) connection."""


def _same_origin(request: Request) -> bool:
    """Check that a write request comes from a page served by this server.

    Blocks other sites open in the browser from changing settings.

    Args:
        request: Incoming request.

    Returns:
        True when the `Origin` header matches this server's address.
    """
    origin = request.headers.get("origin")
    return origin is not None and origin == f"{request.url.scheme}://{request.headers.get('host', '')}"


def web_routes(state: DocState, project_root: Path, config: Config, search: SearchEngine) -> list[BaseRoute]:
    """Build the frontend routes served next to the MCP endpoint.

    `/wiki/<path>`, `/source/<path>`, `/search` (modes `default`, `bm25`, `semantic`, `hybrid`),
    `/code-theme/<name>.css`, `/settings/code-theme`, `/events` (live updates) and `/static`.

    Args:
        state: Extracted entities shown by the wiki.
        project_root: Root of the documented project, to read source code and save settings.
        config: Project settings; the code theme chosen in the wiki is saved here.
        search: Search engine behind the search box (the same one the MCP tools use).

    Returns:
        The routes, to add to the server app.
    """
    templates = Environment(loader=PackageLoader("doctracker.wiki", "templates"), autoescape=select_autoescape())
    templates.filters["markdown"] = pages.render_markdown
    templates.filters["highlight"] = pages.highlight
    templates.globals.update(
        code_theme=config.code_theme if config.code_theme in pages.CODE_THEMES else "default",
        code_themes=pages.CODE_THEMES,
        search_modes=MODES,
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

    async def search_box(request: Request) -> Response:
        query = request.query_params.get("q", "")
        mode = request.query_params.get("mode", "default")
        page = int(request.query_params.get("page", "1")) if request.query_params.get("page", "1").isdigit() else 1
        context = {"query": query, "mode": mode, "show_score": mode != "default", "results": [], "preparing": None}
        if query.strip():
            offset = DEFAULT_LIMIT * (max(1, page) - 1)
            outcome = await search.run(mode, query, DEFAULT_LIMIT, WIKI_WAIT_SECONDS, offset)
            if outcome.ready:
                context["results"] = pages.ranked_results(state, outcome.results, query)
                context["pagination"] = pages.pagination(outcome.total, outcome.offset, DEFAULT_LIMIT)
            else:
                context["preparing"] = outcome.status
        return HTMLResponse(templates.get_template("search.html").render(**context))

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
        set_config_value(project_root, config, "code_theme", name)
        templates.globals["code_theme"] = name
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
        Route("/search", search_box),
        Route("/code-theme/{name}.css", theme),
        Route("/settings/code-theme", set_code_theme, methods=["POST"]),
        Route("/events", events),
        Mount("/static", StaticFiles(packages=[("doctracker.wiki", "static")]), name="static"),
    ]
