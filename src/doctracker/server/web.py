"""Frontend routes: wiki pages, source code on demand and live-update events."""

import asyncio
from datetime import datetime
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
from doctracker.notes import NOTE_GROUPS, NOTE_TYPES, NoteStore, parse_item
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
    templates.filters["local_time"] = pages.local_time
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

    def chosen_plans(params: dict) -> list[int]:
        """The plans selected in the planner (`plans=1,2`); by default the newest in progress, else the
        newest not done, else the newest."""
        plans = notes.planner()["plans"]
        existing = [plan["id"] for plan in plans]
        chosen = [int(part) for part in params.get("plans", "").split(",") if part.isdigit() and int(part) in existing]
        if chosen or params.get("plans") == "none":
            return chosen
        for wanted in (("doing", "late", "blocked"), ("todo",)):
            found = [plan["id"] for plan in plans if plan["state"] in wanted]
            if found:
                return found[:1]
        return existing[:1]

    def notes_context(params: dict) -> dict:
        """What the notes page shows: the planner (plan cards, the chosen plans, the item shown on the
        right), or the notes of one group (guidelines or memory)."""
        tab = params.get("tab", "") if params.get("tab", "") in ("planner", *NOTE_GROUPS) else "planner"
        note_type = params.get("type", "") if params.get("type", "") in NOTE_GROUPS.get(tab, ()) else ""
        note_status = params.get("status", "active") if params.get("status", "active") in ("active", "superseded", "") else "active"
        context = {"tab": tab, "note_types": NOTE_TYPES, "note_groups": NOTE_GROUPS, "note_type": note_type,
                   "note_status": note_status}
        if tab in NOTE_GROUPS:
            selected = params.get("selected", "")
            exists = selected.startswith("note:") and selected[5:].isdigit()
            if exists:
                try:
                    notes.get_note(int(selected[5:]))
                except ValueError:
                    exists = False
            context.update(selected=selected if exists else "", plans="", notes=notes.list_notes(tab, note_type, note_status),
                           tree_types=[note_type] if note_type else list(NOTE_GROUPS[tab]))
        if tab == "planner":
            chosen = chosen_plans(params)
            cards = []
            for plan in notes.planner()["plans"]:
                tasks = [task for feature in plan["features"] for task in feature["tasks"]]
                cards.append({"id": plan["id"], "title": plan["title"], "state": plan["state"], "due": plan["due"],
                              "done": sum(task["state"] == "done" for task in tasks), "total": len(tasks),
                              "chosen": plan["id"] in chosen,
                              "toggle": ",".join(str(i) for i in (sorted(set(chosen) - {plan["id"]}) if plan["id"] in chosen
                                                                  else sorted(chosen + [plan["id"]])))})
            selected = params.get("selected", "")
            try:
                notes.get_item(selected)
            except ValueError:
                selected = f"plan:{chosen[0]}" if chosen else ""
            plans = ",".join(map(str, chosen)) or "none"
            context.update(cards=cards, plans=plans, selected=selected, data_url=f"/graph/planner?plans={plans}")
        return context

    def lines(value: str | None) -> list[str] | None:
        """A textarea with one item per line, as a list (`None` when the field was not sent)."""
        return None if value is None else [line.strip() for line in value.splitlines() if line.strip()]

    def page_query(params: dict) -> str:
        """The query string that brings the notes page back to the same tab, plans, item and filters."""
        return "&".join(f"{key}={value}" for key, value in params.items() if value)

    def dependency_choices(item: str) -> list[dict]:
        """What an item can be made to wait for, as a tree, for the autocomplete of the planner panel.

        Every plan, feature and task in order, with its `ref`, `title`, `level`, `state`, `depth` (0 for a
        plan), `parent` (the ref above it) and `allowed`: false for the item itself, the plan or feature
        holding it (waiting for them would be a cycle) and what it holds (it already waits for that);
        they stay to show the tree. As in the drawing, a level that repeats the one above is not shown again.
        """
        def same(first: dict, second: dict) -> bool:
            return first["title"].strip().casefold() == second["title"].strip().casefold()

        plans = notes.planner()["plans"]
        holders = {item}  # what holds the item, and what the item holds: neither can be waited for
        for plan in plans:
            for feature in plan["features"]:
                if feature["item"] == item or any(task["item"] == item for task in feature["tasks"]):
                    holders |= {feature["item"], plan["item"]}
                if item in (plan["item"], feature["item"]):
                    holders |= {task["item"] for task in feature["tasks"]} | ({feature["item"]} if item == plan["item"] else set())

        def entry(thing: dict, level: str, depth: int, parent: str) -> dict:
            return {"ref": thing["item"], "title": thing["title"], "level": level, "state": thing["state"], "depth": depth,
                    "parent": parent, "allowed": thing["item"] not in holders}

        choices = []
        for plan in plans:
            choices.append(entry(plan, "plan", 0, ""))
            merged = len(plan["features"]) == 1 and same(plan["features"][0], plan)
            for feature in plan["features"]:
                holder = plan["item"] if merged else feature["item"]
                if not merged:
                    choices.append(entry(feature, "feature", 1, plan["item"]))
                if not (len(feature["tasks"]) == 1 and same(feature["tasks"][0], feature)):
                    choices += [entry(task, "task", 1 if merged else 2, holder) for task in feature["tasks"]]
        return choices

    def form_context(query: dict, error: str = "") -> dict:
        """A modal of the notes page (to create something, or to open a note), or the planner's right
        panel (`panel=1`) showing one plan, feature or task to read and change.

        `kind` is plan, feature, task or note; `item` (e.g. `task:3`) or `note` (an id) opens an existing
        one; `plan_id` / `feature_id` / `type` prefill a new one.
        """
        context = {"query": query, "note_types": NOTE_TYPES, "note_groups": NOTE_GROUPS, "tab": query.get("tab", "planner"),
                   "note_type": query.get("filter_type", ""), "note_status": query.get("filter_status", "active"),
                   "plans": query.get("plans", ""), "selected": query.get("selected") or query.get("item", ""),
                   "panel": query.get("panel") == "1",
                   "item": None, "note": None, "error": error}
        try:
            if query.get("item"):
                context["item"] = notes.get_item(query["item"])
                context["kind"] = parse_item(query["item"])[0]
                context["choices"] = dependency_choices(query["item"])
                context["titles"] = {entry["item"]: entry["title"] for plan in notes.planner()["plans"]
                                     for entry in [plan, *plan["features"], *(t for f in plan["features"] for t in f["tasks"])]}
            elif query.get("note"):
                context["note"] = notes.get_note(int(query["note"])) if query["note"].isdigit() else None
                context["kind"] = "note"
            else:
                context["kind"] = query.get("kind", "plan")
        except ValueError as refused:
            context["error"] = str(refused)
        return context

    def render_form(query: dict, error: str = "") -> str:
        """Render a modal or the planner's panel (see `form_context`)."""
        return templates.get_template("notes_form.html").render(**form_context(query, error))

    async def note_form(request: Request) -> Response:
        """A modal of the notes page or the planner's right panel (see `render_form`)."""
        return HTMLResponse(render_form(dict(request.query_params)))

    async def note_action(request: Request) -> Response:
        """Change the planner or the notes from the notes page, through the same methods the MCP tools use.

        Every change made here is recorded with the source `wiki`. The page comes back redrawn; a
        refused change (missing title, a cycle, a bad date...) is shown on top.
        """
        if not _same_origin(request):
            return Response("", status_code=403)
        submitted = await request.form()
        form = {key: value for key, value in submitted.items()}

        def number(name: str) -> int:
            value = form.get(name, "")
            return int(value) if value.isdigit() else 0

        def optional(name: str) -> str | None:
            return form.get(name)

        actions = {
            "create_plan": lambda: notes.create_plan(form.get("title", ""), form.get("goal", ""), lines(form.get("requirements")),
                                                     lines(form.get("decisions")), lines(form.get("branches")), form.get("due", ""),
                                                     source="wiki"),
            "update_plan": lambda: notes.update_plan(number("plan_id"), optional("title"), optional("goal"),
                                                     lines(optional("requirements")), lines(optional("decisions")),
                                                     lines(optional("branches")), optional("due")),
            "add_feature": lambda: notes.add_feature(number("plan_id"), form.get("title", ""), form.get("description", ""),
                                                     form.get("branch", ""), form.get("due", ""), source="wiki"),
            "update_feature": lambda: notes.update_feature(number("feature_id"), optional("title"), optional("description"),
                                                           optional("branch"), optional("due")),
            "add_task": lambda: notes.add_task(number("feature_id"), form.get("title", ""), lines(form.get("criteria")),
                                               form.get("branch", ""), form.get("due", ""), source="wiki"),
            "update_task": lambda: notes.update_task(number("task_id"), optional("title"), lines(optional("criteria")),
                                                     optional("branch"), optional("due"), optional("status"), source="wiki"),
            "toggle_task": lambda: (notes.update_task(number("task_id"), status="done", source="wiki") if form.get("done")
                                    else notes.withdraw_approval(number("task_id"))),
            "check_criterion": lambda: notes.check_criterion(number("task_id"), number("index"), bool(form.get("done")), "wiki"),
            "annotate_task": lambda: notes.annotate_task(number("task_id"), form.get("text", ""), "wiki"),
            "add_evidence": lambda: notes.add_evidence(number("task_id"), "wiki", form.get("detail", "")),
            "approve_task": lambda: notes.approve_task(number("task_id"), form.get("detail", "")),
            "withdraw_approval": lambda: notes.withdraw_approval(number("task_id"), form.get("detail", "")),
            "update_evidence": lambda: notes.update_evidence(number("evidence_id"), form.get("detail", "")),
            "delete_evidence": lambda: notes.delete_evidence(number("evidence_id")),
            "update_annotation": lambda: notes.update_annotation(number("annotation_id"), form.get("text", "")),
            "delete_annotation": lambda: notes.delete_annotation(number("annotation_id")),
            "add_dependency": lambda: notes.add_dependency(form.get("item", ""), submitted.getlist("depends_on"),
                                                           form.get("reason", ""), "wiki"),
            "remove_dependency": lambda: notes.remove_dependency(form.get("item", ""), form.get("depends_on", "")),
            "delete_item": lambda: notes.delete_item(form.get("item", "")),
            "create_note": lambda: notes.create_note(form.get("type", ""), form.get("statement", ""), form.get("why", ""),
                                                     lines(form.get("entities")), "wiki"),
            "update_note": lambda: notes.update_note(number("note_id"), optional("statement"), optional("why"),
                                                     lines(optional("entities"))),
            "supersede_note": lambda: notes.supersede_note(number("note_id"), form.get("statement", ""), form.get("why", ""),
                                                           source="wiki"),
            "delete_note": lambda: notes.delete_note(number("note_id")),
        }
        action = actions.get(request.path_params["action"])
        if action is None:
            return Response("", status_code=404)
        params = {"tab": form.get("tab", "planner"), "plans": form.get("plans", ""), "selected": form.get("selected", ""),
                  "type": form.get("filter_type", ""), "status": form.get("filter_status", "active")}
        error = ""
        try:
            result = action()
        except ValueError as refused:
            error = str(refused)
        name = request.path_params["action"]
        if name == "supersede_note" and not error:  # the panel goes on with the note that holds now
            params["selected"] = f"note:{result['id']}"
        if form.get("autosave") == "1":
            # A change that saved by itself: the fields already show it; only the head (state, "Saved" or
            # why not) and the plan cards come back, and the page redraws its graph in place.
            item = form.get("selected", "") if name != "update_note" else ""
            query = ({"item": item, "panel": form.get("panel", ""), "tab": params["tab"]} if item
                     else {"note": form.get("note_id", ""), "panel": form.get("panel", ""), "tab": params["tab"]})
            context = form_context(query, error)
            reply = templates.get_template("notes_head.html").render(
                **context, oob=True, saved="" if error else datetime.now().strftime("%H:%M:%S"))
            if params["tab"] == "planner":
                reply += templates.get_template("notes_cards.html").render(oob=True, **notes_context(params))
            elif form.get("panel") == "1":
                reply += templates.get_template("notes_tree.html").render(oob=True, **notes_context(params))
            changed = "diagram-changed" if form.get("panel") == "1" or params["tab"] == "planner" else "notes-saved"
            return HTMLResponse(reply, headers={"HX-Trigger": changed})
        # From the panel, only deleting the item shown changes what is shown (the whole page comes back);
        # anything else, deleting a feature or task of its lists included, answers with the panel alone.
        deleting_shown = (name == "delete_item" and form.get("item") == params["selected"]) or name == "delete_note"
        if form.get("panel") == "1" and not deleting_shown:
            # Sent from the planner's panel: only the panel and the plan cards come back, and the page
            # redraws its graph in place (keeping zoom and position), so nothing else blinks.
            if params["selected"].startswith("note:"):
                panel = render_form({"note": params["selected"][5:], "panel": "1", "tab": params["tab"],
                                     "selected": params["selected"]}, error)
                tree = templates.get_template("notes_tree.html").render(oob=True, **notes_context(params))
                return HTMLResponse(panel + tree)
            panel = render_form({"item": params["selected"], "panel": "1", "tab": "planner", "plans": params["plans"]}, error)
            cards = templates.get_template("notes_cards.html").render(oob=True, **notes_context(params))
            return HTMLResponse(panel + cards, headers={"HX-Trigger": "diagram-changed"})
        if not error:
            # What was just created is shown: a new plan joins the chosen plans and opens on the right.
            if name == "create_note" and isinstance(result, dict):
                params["selected"] = f"note:{result['id']}"
            created = name in ("create_plan", "add_feature", "add_task") and isinstance(result, dict)
            if created:
                params["selected"] = result["item"]
                if result["item"].startswith("plan:"):
                    params["plans"] = ",".join(p for p in [*params["plans"].split(","), str(result["id"])] if p.isdigit())
        context = {"path": "", "tree": pages.tree(state, ""), "view": "notes", "params": params, "error": error,
                   **notes_context(params)}
        return render_page(request, "notes.html", f"/notes?{page_query(params)}", context)

    async def git_branches(request: Request) -> Response:
        """Commits of every branch placed on lanes, for the branch graph at the top of the git page.

        Each commit also gets `body_html` (its message body rendered as Markdown, like in the commit list)
        and `date_local` (its date in this machine's time zone).
        """
        commits = await read_branch_graph(project_root, GIT_COMMITS)
        if commits is None:
            return JSONResponse({"error": "Not a git repository."})
        for commit in commits:
            commit["body_html"] = pages.render_commit_message(commit["body"])
            commit["date_local"] = pages.local_time(commit["date"])
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
        if view == "planner":
            plans = [int(part) for part in params.get("plans", "").split(",") if part.isdigit()]
            return JSONResponse(notes.planner_graph(plans))
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
        Route("/notes/form", note_form),
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
