"""Frontend routes: wiki pages, source code on demand and live-update events."""

import asyncio
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from doctracker.config import Config, set_config_value
from doctracker.graph import CALL_DIRECTIONS, MAX_CALL_DEPTH, architecture, call_graph, class_diagram
from doctracker.history import commit_diff, read_branch_graph, read_history
from doctracker.notes import NOTE_TYPES, PLAN_STATUSES, TASK_STATUSES, NoteStore
from doctracker.search import DEFAULT_LIMIT, MODES, WIKI_WAIT_SECONDS, SearchEngine
from doctracker.server.state import DocState
from doctracker.wiki import pages

KEEPALIVE_SECONDS = 15
"""Seconds between keepalive messages on an idle live-update (SSE) connection."""

GIT_COMMITS = 500
"""Most recent commits listed on the git page."""


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


def _static_url(name: str) -> str:
    """Build the URL of a static file with its modification time, so browsers never use a stale copy.

    Args:
        name: File name inside `wiki/static/`, e.g. `style.css`.

    Returns:
        `/static/<name>?v=<modification time>`; without the version when the file is not found.
    """
    file = Path(str(files("doctracker.wiki").joinpath("static", name)))
    return f"/static/{name}?v={int(file.stat().st_mtime)}" if file.is_file() else f"/static/{name}"


def web_routes(state: DocState, project_root: Path, config: Config, search: SearchEngine,
               notes: NoteStore) -> list[BaseRoute]:
    """Build the frontend routes served next to the MCP endpoint.

    `/wiki/<path>`, the graph views `/architecture`, `/classes`, `/calls` (and their data under
    `/graph/...`), the history `/git` (with `/git/branches` and `/git/commit/<hash>`), the plans,
    tasks and notes `/notes` (changed through `/notes/<action>`), `/source/<path>`,
    `/search` (modes `default`, `bm25`, `semantic`, `hybrid`),
    `/code-theme/<name>.css`, `/settings/code-theme`, `/events` (live updates) and `/static`.

    Args:
        state: Extracted entities shown by the wiki.
        project_root: Root of the documented project, to read source code and save settings.
        config: Project settings; the code theme chosen in the wiki is saved here.
        search: Search engine behind the search box (the same one the MCP tools use).
        notes: Store of the plans, tasks and notes (the same one the MCP tools use).

    Returns:
        The routes, to add to the server app.
    """
    templates = Environment(loader=PackageLoader("doctracker.wiki", "templates"), autoescape=select_autoescape())
    templates.filters["markdown"] = pages.render_markdown
    templates.filters["commit_message"] = pages.render_commit_message
    templates.filters["highlight"] = pages.highlight
    templates.globals.update(
        static_url=_static_url,
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

    def render_page(request: Request, content: str, url: str, context: dict, status: int = 200) -> HTMLResponse:
        """Render a page: the whole document, or only the content panel for htmx navigation."""
        is_fragment = "HX-Request" in request.headers and "HX-History-Restore-Request" not in request.headers
        template = "fragment.html" if is_fragment else "base.html"
        html = templates.get_template(template).render(content=content, page_url=url, state=state, **context)
        return HTMLResponse(html, status_code=status)

    def render(request: Request, path: str) -> HTMLResponse:
        entity = state.entities.get(path)
        context = {"path": path, "entity": entity, "tree": pages.tree(state, path)}
        if not state.ready:
            content, status = "loading.html", 200
        elif entity is None:
            content, status = "not_found.html", 404
        else:
            content, status = ("module.html" if entity["kind"] == "module" else "entity.html"), 200
            context["breadcrumbs"] = pages.breadcrumbs(state, path)
        return render_page(request, content, f"/wiki/{path}", context, status)

    async def view_page(request: Request) -> Response:
        """One of the views: architecture, classes, calls, git or notes."""
        view = request.url.path.strip("/")
        params = dict(request.query_params)
        context = {
            "path": "",
            "tree": pages.tree(state, ""),
            "view": view,
            "params": params,
            "data_url": f"/graph/{view}?{request.url.query}" if request.url.query else f"/graph/{view}",
            "class_packages": pages.class_packages(state),
            "call_targets": pages.call_targets(state),
            "call_directions": CALL_DIRECTIONS,
            "max_call_depth": MAX_CALL_DEPTH,
        }
        if view == "git":
            # Commits newest first, optionally only those that changed one file.
            commits = await read_history(project_root, GIT_COMMITS, params.get("file", ""))
            context["commits"] = commits
            context["selected"] = params.get("commit") or (commits[0].hash if commits else "")
        if view == "notes":
            context.update(notes_context(params))
        url = f"/{view}?{request.url.query}" if request.url.query else f"/{view}"
        return render_page(request, f"{view}.html" if state.ready else "loading.html", url, context)

    def notes_context(params: dict) -> dict:
        """What the notes page shows: the plans (work tab) and the notes, filtered (notes tab)."""
        note_type = params.get("type", "") if params.get("type", "") in NOTE_TYPES else ""
        note_status = params.get("status", "active") if params.get("status", "active") in ("active", "superseded", "") else "active"
        return {
            "tab": "notes" if params.get("tab") == "notes" else "work",
            "plans": notes.list_plans(""),
            "notes": notes.list_notes(note_type, note_status),
            "note_types": NOTE_TYPES,
            "note_type": note_type,
            "note_status": note_status,
            "plan_statuses": PLAN_STATUSES,
            "task_statuses": TASK_STATUSES,
        }

    def lines(value: str | None) -> list[str] | None:
        """A textarea with one item per line, as a list (`None` when the field was not sent)."""
        return None if value is None else [line.strip() for line in value.splitlines() if line.strip()]

    async def note_action(request: Request) -> Response:
        """Change plans, tasks or notes from the notes page, through the same methods the MCP tools use.

        The page comes back redrawn; a refused change (unknown type, missing title...) is shown on top.
        """
        if not _same_origin(request):
            return Response("", status_code=403)
        form = {key: value for key, value in (await request.form()).items()}

        def number(name: str) -> int:
            value = form.get(name, "")
            return int(value) if value.isdigit() else 0

        actions = {
            "create_plan": lambda: notes.create_plan(form.get("title", ""), form.get("goal", ""), lines(form.get("requirements")),
                                                     lines(form.get("decisions")), lines(form.get("branches")), "wiki"),
            "update_plan": lambda: notes.update_plan(number("plan_id"), form.get("title"), form.get("goal"),
                                                     lines(form.get("requirements")), lines(form.get("decisions")),
                                                     lines(form.get("branches")), form.get("status")),
            "delete_plan": lambda: notes.delete_plan(number("plan_id")),
            "add_task": lambda: notes.add_task(number("plan_id"), form.get("title", ""), lines(form.get("criteria")),
                                               form.get("branch", ""), "wiki"),
            "update_task": lambda: notes.update_task(number("task_id"), form.get("title"), lines(form.get("criteria")),
                                                     form.get("branch"), form.get("status")),
            "delete_task": lambda: notes.delete_task(number("task_id")),
            "annotate_task": lambda: notes.annotate_task(number("task_id"), form.get("text", ""), "wiki"),
            "add_evidence": lambda: notes.add_evidence(number("task_id"), "wiki", form.get("detail", "")),
            "create_note": lambda: notes.create_note(form.get("type", ""), form.get("statement", ""), form.get("why", ""),
                                                     lines(form.get("entities")), "wiki"),
            "update_note": lambda: notes.update_note(number("note_id"), form.get("statement"), form.get("why"),
                                                     lines(form.get("entities"))),
            "supersede_note": lambda: notes.supersede_note(number("note_id"), form.get("statement", ""), form.get("why", ""),
                                                           source="wiki"),
            "delete_note": lambda: notes.delete_note(number("note_id")),
        }
        action = actions.get(request.path_params["action"])
        if action is None:
            return Response("", status_code=404)
        params = {"tab": form.get("tab", "work"), "type": form.get("filter_type", ""), "status": form.get("filter_status", "active")}
        error = ""
        try:
            action()
        except ValueError as refused:
            error = str(refused)
        query = "&".join(f"{key}={value}" for key, value in params.items() if value)
        context = {"path": "", "tree": pages.tree(state, ""), "view": "notes", "params": params, "error": error,
                   **notes_context(params)}
        return render_page(request, "notes.html", f"/notes?{query}", context)

    async def git_branches(request: Request) -> Response:
        """Commits of every branch placed on lanes, for the branch graph at the top of the git page.

        Each commit also gets `body_html`: its message body rendered as Markdown, like in the commit list.
        """
        commits = await read_branch_graph(project_root, GIT_COMMITS)
        if commits is None:
            return JSONResponse({"error": "Not a git repository."})
        for commit in commits:
            commit["body_html"] = pages.render_commit_message(commit["body"])
        return JSONResponse({"commits": commits})

    async def git_commit(request: Request) -> Response:
        """Changed lines of one commit, file by file (right side of the git page)."""
        commit_hash = request.path_params["hash"]
        files = await commit_diff(project_root, commit_hash)
        if files is None:
            return HTMLResponse('<p class="empty">Commit not found.</p>', status_code=404)
        html =templates.get_template("git_commit.html").render(files=files, hash=commit_hash)
        return HTMLResponse(html)

    async def view_data(request: Request) -> Response:
        """Data of a graph view, as JSON, built by the same functions the MCP tools use."""
        view = request.path_params["view"]
        params = request.query_params
        if view == "architecture":
            return JSONResponse(architecture(state, params.get("level", "modules")))
        if view == "classes":
            return JSONResponse(class_diagram(state, params.get("package", "")))
        if view == "calls":
            depth = int(params.get("depth", "1")) if params.get("depth", "1").isdigit() else 1
            return JSONResponse(call_graph(state, params.get("focus", ""), depth, params.get("direction", "both")))
        return JSONResponse({"error": f"Unknown view: {view}"}, status_code=404)

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
        Route("/architecture", view_page),
        Route("/classes", view_page),
        Route("/calls", view_page),
        Route("/git", view_page),
        Route("/notes", view_page),
        Route("/notes/{action}", note_action, methods=["POST"]),
        Route("/graph/{view}", view_data),
        Route("/git/branches", git_branches),
        Route("/git/commit/{hash}", git_commit),
        Route("/source/{path:path}", source),
        Route("/search", search_box),
        Route("/code-theme/{name}.css", theme),
        Route("/settings/code-theme", set_code_theme, methods=["POST"]),
        Route("/events", events),
        Mount("/static", StaticFiles(packages=[("doctracker.wiki", "static")]), name="static"),
    ]
