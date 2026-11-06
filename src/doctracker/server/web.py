"""Frontend routes: wiki pages, source code on demand and live-update events."""

import asyncio
import inspect
import json
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit

from jinja2 import Environment, PackageLoader, select_autoescape
from starlette.datastructures import QueryParams
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import BaseRoute, Mount, Route
from starlette.staticfiles import StaticFiles

from doctracker.config import GRAMMARS_DIR, Config, set_config_value
from doctracker.databases import CatalogStore, ConnectionStore, Locked, collect_connection
from doctracker.databases.code_links import code_use, database_use
from doctracker.databases.discovery import KINDS
from doctracker.databases.lint import LEVELS as LINT_LEVELS, Lint
from doctracker.databases.origins import DIFF_TABS, ORIGIN_PREFIX, compare, database_object as object_with_origins, default_b, describe_origins
from doctracker.databases.origins.evolution import MIGRATION_KINDS, describe_moment, moments, renames_between, schema_at, schema_diff
from doctracker.databases.diff_profiles import IGNORABLE, ProfileStore
from doctracker.databases.slices import SliceStore, resolve as resolve_slice, table_key
from doctracker.databases.readonly import SIGN_INS, run_test
from doctracker.extraction.languages import LANGUAGES, NO_SOURCES
from doctracker.graph import (CALL_DIRECTIONS, LOCAL_KINDS, MAX_CALL_DEPTH, architecture, call_graph, class_diagram,
                              class_paths, er_diagram, file_timeline, find_callable)
from doctracker.history import commit_diff, read_branch_graph, read_commit, read_history
from doctracker.history.working import changed_files, current_branch, top_level
from doctracker.notes import (MOMENTS, NOT_A_NOTE, NOTE_GROUP_TEXTS, NOTE_GROUPS, NOTE_TYPE_USES, NOTE_TYPES,
                              NoteStore, parse_item)
from doctracker.search import DEFAULT_LIMIT, DEFAULT_MODE, MODES, RECALL_GROUPS, WIKI_WAIT_SECONDS, SearchEngine, SimilarNotesFound
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


DIAGRAM_TABS = ("architecture", "classes", "calls")
"""The tabs of CODE › Diagrams, each a view at its own URL (`/code/diagrams/architecture`...)."""

EXAMPLES_FOLDER = "examples"
"""Folder of doctracker's own repository with the example projects, shown in the EXAMPLES section."""


def _develops_doctracker(project_root: Path) -> bool:
    """Whether the documented project is doctracker's own repository (the code running is its `src/`)."""
    try:
        return (project_root / "src" / "doctracker").resolve() == Path(__file__).resolve().parents[1]
    except OSError:
        return False


def web_routes(state: DocState, project_root: Path, config: Config, search: SearchEngine,
               notes: NoteStore, connections: ConnectionStore, catalog: CatalogStore) -> list[BaseRoute]:
    """Build the frontend routes served next to the MCP endpoint.

    `/wiki/<path>`, CODE's diagrams `/code/diagrams/<tab>` (architecture, classes, calls; their data under
    `/graph/...`), the history `/git` (with `/git/branches` and `/git/commit/<hash>`), the sections'
    explanation pages `/agent`, `/code` and `/databases`, AGENT's pages `/agent/<page>` (changed through
    `/agent/<action>`), DATABASES' pages `/databases/<page>[/<tab>]` (changed through
    `/databases/<action>`), `/source/<path>`,
    `/search` (modes `all`, `bm25`, `semantic`, `hybrid`),
    `/code-theme/<name>.css`, `/settings/code-theme`, `/events` (live updates) and `/static`.

    Args:
        state: Extracted entities shown by the wiki.
        project_root: Root of the documented project, to read source code and save settings.
        config: Project settings; the code theme chosen in the wiki is saved here.
        search: Search engine behind the search box (the same one the MCP tools use).
        notes: Store of the plans, tasks and notes (the same one the MCP tools use).
        connections: Store of the database connections (the same one the MCP tools use).
        catalog: Store of the collections of the databases (the same one the MCP tools use).

    Returns:
        The routes, to add to the server app.
    """
    developing = _develops_doctracker(project_root)
    templates = Environment(loader=PackageLoader("doctracker.wiki", "templates"), autoescape=select_autoescape())
    templates.filters["markdown"] = pages.render_markdown
    templates.filters["commit_message"] = pages.render_commit_message
    templates.filters["local_time"] = pages.local_time
    templates.filters["age"] = pages.age
    templates.filters["highlight"] = pages.highlight
    templates.globals.update(
        static_url=_static_url,
        no_sources=NO_SOURCES,
        grammars_dir=GRAMMARS_DIR.as_posix(),
        languages=LANGUAGES,
        max_call_depth=MAX_CALL_DEPTH,  # the Depth of every diagram: 1 to it, it by default
        code_theme=config.code_theme if config.code_theme in pages.CODE_THEMES else "default",
        code_themes=pages.CODE_THEMES,
        search_modes=MODES,
        default_mode=DEFAULT_MODE,
        signature=pages.signature,
        summary=pages.summary,
        page_role=pages.page_role,
        symbols=pages.SYMBOLS,
        members_by_group=pages.members_by_group,
        parameter_rows=pages.parameter_rows,
        other_sections=pages.other_sections,
        relations=pages.relations,
        dead_code_of=pages.dead_code_of,
        db_place=pages.db_place,
        db_marks=pages.DB_MARKS,
        db_urls=pages.DATABASE_URLS,
        db_groups=[(title, [kind for kind, same in pages.DB_GROUPS if same == title])
                   for title in dict.fromkeys(title for _, title in pages.DB_GROUPS)],
        browse_counts=pages.BROWSE_COUNTS,
        sections=pages.SECTIONS,
    )
    templates.filters["size"] = pages.size_text

    def view_settings(request: Request) -> tuple[str, set[str]]:
        """The tree layout and the shown languages chosen in this browser (cookies set by `static/live.js`)."""
        layout = request.cookies.get("tree-layout", "")
        return (layout if layout in pages.TREE_LAYOUTS else "languages",
                pages.shown_languages(state, request.cookies.get("languages", "")))

    def render_page(request: Request, content: str, url: str, context: dict, status: int = 200) -> HTMLResponse:
        """Render a page: the whole document, or only the content panel for htmx navigation."""
        is_fragment = "HX-Request" in request.headers and "HX-History-Restore-Request" not in request.headers
        if is_fragment and request.query_params.get("modal"):
            # The page alone, for the consultation modal opened from a drawing (no tree, no local graph).
            html = templates.get_template(content).render(page_url=url, state=state, modal=True, **context)
            return HTMLResponse(html, status_code=status)
        if is_fragment and request.headers.get("X-Part") == "drawing":  # a drawing's filters: its area alone, the tree as it is
            html = templates.get_template("fragment_content.html").render(content=content, page_url=url, state=state, **context)
            return HTMLResponse(html, status_code=status)
        template = "fragment.html" if is_fragment else "base.html"
        layout, shown = view_settings(request)
        current = context.get("path", "")
        html = templates.get_template(template).render(
            content=content, page_url=url, state=state,
            tree=pages.tree(state, current, layout, shown, EXAMPLES_FOLDER if developing else ""),
            examples_tree=pages.tree(state, current, layout, shown, within=EXAMPLES_FOLDER) if developing else [],
            database_tree=pages.database_tree(state, connections.connections(), current, EXAMPLES_FOLDER if developing else "",
                                              availability(), catalog.outline()),
            tree_layout=layout, tree_layouts=pages.TREE_LAYOUTS, shown_languages=shown,
            diagram_tab=request.cookies.get("diagram-tab") if request.cookies.get("diagram-tab") in DIAGRAM_TABS else "architecture",
            languages_found=pages.languages_found(state), **context)
        return HTMLResponse(html, status_code=status)

    async def earlier_names(path: str) -> list[dict]:
        """The earlier names of an entity, newest first, each with the commit that changed it.

        Each has `path`, `how`, `commit`, `short`, `date_local` and, when git still has the commit, its
        `subject`, `author` and `body_html` (for the same tooltip as the git page).
        """
        earlier = []
        for entry in notes.previous_names(path):
            commit = await read_commit(project_root, entry["commit"])
            earlier.append({**entry, "short": entry["commit"][:7],
                            "date_local": pages.local_time(commit.date if commit else entry["created"]),
                            "subject": commit.subject if commit else "", "author": commit.author if commit else "",
                            "body_html": pages.render_commit_message(commit.body) if commit else ""})
        return earlier

    def database_object(path: str) -> dict | None:
        """A database object's page data, a live one's or one a file declares (the same, from the same
        store): what the catalog holds of it; a server, which is no object of its own, as what holds its
        databases. A live table, view or column lists the files declaring it (`declared_by`); one a file
        declares, where it is in the databases its file describes (`found_in`)."""
        found = object_with_origins(path, state.origins, catalog, connections.connections(), project_root)
        if found is None and path.count("/") == 0:
            databases = [o for o in catalog.objects(kind="database") if o["parent"] == path]
            if databases:
                found = {"path": path, "kind": "server", "name": path.removeprefix("db:"), "parent": "", "data": {},
                         "children": databases, "relations": [], "ends": {}, "read": "", "unavailable": []}
        if found is not None:
            found["groups"] = pages.db_relation_groups(found)
            found["crumbs"] = pages.db_crumbs(path)
            found["lint"] = lint.for_object(path, state.origins, connections.connections())
            found["lint_listing"] = list_page(lint_rows(found["lint"]), pages.LIST_COLUMNS["lint object"], {}, "lint-object")
            found["code_use"] = code_use(path, found, state.code_links, state.origins, catalog, connections.connections(), project_root)
            found["code_listing"] = list_page(code_rows(found["code_use"]), pages.LIST_COLUMNS["code use"], {}, "code-use")
        return found

    def code_rows(found: list[dict]) -> list[dict]:
        """The links between the code and the databases as rows of a list (see `list_page`): where each
        one is written (`file:line`, and how many more lines), and whether its code has a page."""
        return [{**link, "code": link["entity"], "page": link["entity"] in state.entities,
                 "where": f"{link['file']}:{link['line']}" + (f" (+{len(link['lines']) - 1} lines)" if len(link["lines"]) > 1 else ""),
                 "how": link["how"] + (f" in {link['databases']} databases" if link.get("databases", 0) > 1 else "")}
                for link in found]

    def database_origin(name: str) -> dict | None:
        """An origin's page data: the origin as read, the databases it describes (its links, told in one
        line; the rest of it is DATABASES › Diff) and what it ends with (`declared`), from the same store
        as the live databases."""
        origin = next((o for o in state.origins if o["name"] == name), None)
        if origin is None:
            return None
        return {**origin, **describe_origins(state.origins, catalog, connections.connections(), project_root)[name],
                "declared": catalog.objects(connection_id=f"origin:{name}")}  # what it ends with, as the store keeps it

    async def render(request: Request, path: str) -> HTMLResponse:
        if path.startswith("connection:"):  # a connection in the tree: its screen, DATABASES › Connections with its details open
            context = {"path": path, "view": "database", "params": {"tab": "connections"},
                       **database_context({"tab": "connections"}), "open_connection": path.removeprefix("connection:")}
            return render_page(request, "database.html", f"/wiki/{path}", context)
        if path.startswith("origin:") and "::" in path or path.startswith("db:"):  # an object, a live database's or a file's
            found = database_object(path)
            content, status = ("database_object.html", 200) if found else ("not_found.html", 404)
            return render_page(request, content, f"/wiki/{path}", {"path": path, "item": found}, status)
        if path.startswith("origin:"):  # an origin of the schema: SQL files, migrations
            found = database_origin(path.removeprefix("origin:"))
            content, status = ("database_origin.html", 200) if found else ("not_found.html", 404)
            return render_page(request, content, f"/wiki/{path}", {"path": path, "origin": found}, status)
        entity = state.entities.get(path)
        context = {"path": path, "entity": entity}
        if not state.ready:
            content, status = "loading.html", 200
        elif entity is None:
            content, status = "not_found.html", 404
        else:
            content = "module.html" if entity["kind"] == "module" else "entity.html"  # for every language
            context["relations"] = pages.relations(state, path)
            used = code_rows(database_use(path, state.code_links, state.origins, catalog, connections.connections(), project_root))
            context["database_use"] = list_page([{**row, "of": path, "row": index} for index, row in enumerate(used)],
                                                pages.LIST_COLUMNS["database use"], {}, "database-use")
            status = 200
            context["breadcrumbs"] = pages.breadcrumbs(state, path)
            context["previous_names"] = await earlier_names(path)
        return render_page(request, content, f"/wiki/{path}", context, status)

    async def view_page(request: Request) -> Response:
        """One of the views: CODE's diagrams (architecture, classes, calls) and dead code, git."""
        view = request.url.path.rsplit("/", 1)[-1]
        params = dict(request.query_params)
        query = request.url.query
        if view == "calls":
            # Calls opens on what was chosen last (focus, depth, direction), and its fields
            # show what is drawn: the path found for a name typed, the depth (all of it by default).
            if not params and request.cookies.get("calls-view"):
                params = dict(parse_qsl(request.cookies["calls-view"]))
            params.setdefault("depth", str(MAX_CALL_DEPTH))
            params.pop("to", None)  # Path to was taken away (Filipe, 2026-11-06): an old address's is dropped
            if params.get("focus", "").strip():
                params["focus"] = find_callable(state, params["focus"]) or params["focus"]
            query = urlencode(params)
        classes = set(class_paths(state))  # what the class diagram (and its Focus) holds
        context = {
            "path": "",
            "view": view,
            "params": params,
            "data_url": f"/graph/{view}?{query}" if query else f"/graph/{view}",
            "class_targets": [row for row in pages.focus_targets(state, ("class",)) if row["path"] in classes],
            "project_groups": [group for group in pages.project_groups(state, EXAMPLES_FOLDER if developing else "")
                               if group["role"] == "project"],
            "module_targets": pages.focus_targets(state, ("module",)),
            "call_targets": pages.focus_targets(state, ("function", "class")),
            "call_directions": CALL_DIRECTIONS,
        }
        if view == "git":
            # Commits newest first, optionally only those that changed one file.
            commits = await read_history(project_root, GIT_COMMITS, params.get("file", ""))
            context["commits"] = commits
            context["selected"] = params.get("commit") or (commits[0].hash if commits else "")
        if view == "dead-code":
            context.update(pages.dead_code_view(state, params, view_settings(request)[1]))
        url = f"{request.url.path}?{request.url.query}" if request.url.query else request.url.path
        template = "diagrams.html" if view in DIAGRAM_TABS else f"{view}.html"
        response = render_page(request, template if state.ready else "loading.html", url, context)
        if view in DIAGRAM_TABS:  # Diagrams in the tree opens the tab used last
            response.set_cookie("diagram-tab", view, max_age=31536000, samesite="lax")
        if view == "calls" and request.query_params:
            response.set_cookie("calls-view", query, max_age=31536000, samesite="lax")
        return response

    async def databases_page(request: Request) -> Response:
        """A page of DATABASES (Connections, Navigate, Diagrams, Diff, Evolution, Lint), each tab of Navigate
        and Diagrams at its own address: `/databases/<page>[/<tab>]` (pages.DATABASE_URLS)."""
        tab = pages.DATABASE_VIEWS.get(request.path_params["page"])
        if tab is None:
            return render_page(request, "not_found.html", request.url.path, {"path": ""}, 404)
        params = {**database_params(request.query_params), "tab": tab}
        context = {"path": "", "view": "database", **database_context(params)}
        url = f"{request.url.path}?{request.url.query}" if request.url.query else request.url.path
        return render_page(request, "database.html" if state.ready else "loading.html", url, context)

    async def agent_page(request: Request) -> Response:
        """A page of AGENT: the planner, the guidelines or the memory, each at `/agent/<page>`."""
        page = request.path_params["page"]
        if page not in ("planner", *NOTE_GROUPS):
            return render_page(request, "not_found.html", request.url.path, {"path": ""}, 404)
        params = {**request.query_params, "tab": page}
        context = {"path": "", "view": "notes", "params": params, **notes_context(params)}
        return render_page(request, "notes.html" if state.ready else "loading.html", agent_url(params), context)

    async def section_page(request: Request) -> Response:
        """A section's explanation page (AGENT, CODE, DATABASES): what it is for and its pages."""
        name = request.url.path.strip("/")
        return render_page(request, "section.html", f"/{name}", {"path": "", "view": name, "section": pages.SECTIONS[name]})

    connection_tests: dict[str, dict] = {}  # the last test of each connection, shown on its card
    slices = SliceStore(project_root, state.notify)  # the slices of the schema, doc/slices/ (the MCP tools read the same files)
    profiles = ProfileStore(project_root, state.notify)  # the Diff's comparison profiles, doc/diff/ (the MCP tools read the same files)
    lint = Lint(project_root, catalog, slices, state.notify)  # the lint, its accepted findings in doc/lint/ (the MCP tools read the same)

    def availability() -> dict[str, str]:
        """Whether each connection answers: `failed` when its last reading or its last test failed, `ok`
        when it was read; a connection never read is left out."""
        found = {}
        for connection in connections.connections():
            read, test = catalog.collection(connection["id"]), connection_tests.get(connection["id"])
            if (read and read.get("failure")) or (test and not test["ok"]):
                found[connection["id"]] = "failed"
            elif read and read.get("started"):
                found[connection["id"]] = "ok"
        return found

    def database_params(query: QueryParams) -> dict:
        """What an address of DATABASES asks for: its fields, each list's column filters (`f_<column>`, several
        values each) and Browse's ticks (the servers, databases, schemas and tables ticked in its path)."""
        params: dict = dict(query)
        params["filters"] = {key[2:]: query.getlist(key) for key in query if key.startswith("f_")}
        params["picked"] = {level: query.getlist(field) for level, field in pages.BROWSE_FIELDS.items()}
        return params

    def database_context(params: dict, error: str = "") -> dict:
        """What a page of DATABASES shows: its view (`tab`, see pages.DATABASE_URLS), the connections, their
        last tests, whether the saved passwords wait for the master password, whether any database was
        read, the list of objects with its filters, and a refusal to show on top."""
        tab = params.get("tab", "connections")
        context = {"tab": tab, "connections": connections.connections(), "params": params,
                   "tests": connection_tests, "kinds": KINDS, "locked": connections.locked(),
                   "has_secrets": (connections.folder / "secrets.bin").is_file(), "error": error,
                   "has_collections": bool(catalog.objects(kind="database"))}
        if tab == "objects":
            context.update(objects_list(params))
        if tab == "diff":
            context.update(diff_context(params))
        if tab == "diagram":
            context.update(er_context(params))
        if tab == "evolution":
            context.update(evolution=evolution_moments(), evolution_labels=evolution_labels())
        if tab == "slices":
            context.update(slices=[resolve_slice(found, catalog) for found in slices.slices()])
        if tab == "lint":
            context.update(lint_list(params))
        return context

    def table_choices() -> list[dict]:
        """Every table and view of the databases read and of the files, for the slices' forms."""
        return [{"path": o["path"], "name": table_key(o["path"]), "kind": o["kind"],
                 "place": o["path"].split("::", 1)[0] if "::" in o["path"] else "/".join(o["path"].split("/")[:2])}
                for o in catalog.objects(origins=True) if o["kind"] in ("table", "view", "materialized view", "foreign table")]

    def neighbours(start: str, steps: int) -> list[str]:
        """A table and the tables its keys and views reach, `steps` relations away (either way)."""
        tables = {choice["path"] for choice in table_choices()}
        def table_of(path: str) -> str | None:
            return path if path in tables else (path.rsplit(".", 1)[0] if path.rsplit(".", 1)[0] in tables else None)
        links: dict[str, set[str]] = {}
        for relation in catalog.relations(("foreign key", "implied", "view reads", "partition of", "inherits", "foreign table")):
            a, b = table_of(relation["source"]), table_of(relation["target"])
            if a and b and a != b:
                links.setdefault(a, set()).add(b)
                links.setdefault(b, set()).add(a)
        reached = frontier = {start} if start in tables else set()
        for _ in range(max(0, steps)):
            frontier = {other for path in frontier for other in links.get(path, ())} - reached
            reached = reached | frontier
        return sorted(reached)

    def slice_modal(details: str = "", editing: bool = False, chosen: list[dict] | None = None, form: dict | None = None,
                    error: str = "") -> str:
        """The slices' modals: one slice's details (`details`), its form (`editing`), or a new one's form
        with the tables `chosen` (from the Diagram, with their positions)."""
        found = slices.slice(details) if details else None
        return templates.get_template("database_form.html").render(
            slice_mode=True, slice=resolve_slice(found, catalog) if found else None, editing=editing or not found,
            chosen=chosen if chosen is not None else (found or {}).get("tables", []), form=form or {}, error=error,
            choices=table_choices())

    async def slice_form(request: Request) -> Response:
        """A slice's modal: `?details=<name>`, `&edit=1`; a new one; `start` and `steps` tick a table and
        its neighbours in the form being filled (its fields kept)."""
        query = request.query_params
        chosen = None
        if query.get("start"):
            ticked = query.getlist("table")
            chosen = [{"path": path} for path in dict.fromkeys(ticked + neighbours(query["start"], int(query.get("steps") or 1)))]
        return HTMLResponse(slice_modal(query.get("details", ""), bool(query.get("edit")), chosen,
                                        {"name": query.get("name", ""), "text": query.get("text", ""), "previous": query.get("previous", "")}))

    def lint_modal(key: str, reason: str = "", error: str = "") -> str:
        """The form accepting a finding of the lint: what it is, and the reason asked."""
        finding = next((f for f in lint.findings(state.origins, connections.connections()) if f["key"] == key), None)
        return templates.get_template("database_form.html").render(lint_mode=True, finding=finding, reason=reason, error=error)

    async def lint_form(request: Request) -> Response:
        """The form accepting a finding of the lint: `?key=<the finding's key>`."""
        return HTMLResponse(lint_modal(request.query_params.get("key", "")))

    async def code_reaches(request: Request) -> Response:
        """What one use of a code entity reaches, in the consultation modal: `?entity=<the page's entity>&row=<its
        row in that page's Database use>` (a module's lists its members' too); the places split into the live
        databases and the files."""
        entity, row = request.query_params.get("entity", ""), request.query_params.get("row", "")
        rows = code_rows(database_use(entity, state.code_links, state.origins, catalog, connections.connections(), project_root))
        found = rows[int(row)] if row.isdigit() and int(row) < len(rows) else None
        places = {"live": [], "files": []}
        for path in (found or {}).get("objects", []):
            places["files" if path.startswith("origin:") else "live"].append(
                {"path": path, "where": path.partition("::")[0].removeprefix("origin:") if path.startswith("origin:")
                 else "/".join(path.removeprefix("db:").split("/")[:2]),
                 "object": pages.db_place(path) if path.startswith("origin:") else path.split("/", 2)[-1]})
        return HTMLResponse(templates.get_template("database_form.html").render(reaches_mode=True, link=found, places=places))

    evolution_cache: dict = {}  # the moments, kept until the origins are read again or git changes

    def evolution_moments() -> dict:
        """The Evolution tab's moments (see `moments`), read once per reading of the origins and state of git."""
        index = project_root / ".git" / "index"
        key = (id(state.origins), index.stat().st_mtime if index.exists() else 0)
        if evolution_cache.get("key") != key:
            evolution_cache.update(key=key, value=moments(project_root, state.origins))
        return evolution_cache["value"]

    def evolution_labels() -> dict[str, str]:
        """Each moment as the fields A and B name it: its step or commit, and its date."""
        labels = {}
        for moment in evolution_moments()["moments"]:
            commit = moment["commit"]
            what = f"{moment['version']} {moment['title']}".strip() if moment["source"] == "migration" else \
                (f"commit {commit['short']}" if commit else "not committed")
            labels[moment["id"]] = f"{what} · {commit['at'][:10] if commit else 'now'}"
        return labels

    async def evolution_part(request: Request) -> Response:
        """The Evolution tab's parts: a moment in the Details panel (`?moment=<id>`), or the diff of two
        moments (`?a=&b=&view=side|only`)."""
        query = request.query_params
        parts = templates.get_template("macros.html").module
        if query.get("moment"):
            moment = next((m for m in evolution_moments()["moments"] if m["id"] == query["moment"]), None)
            return HTMLResponse(str(parts.evolution_moment(moment, describe_moment(state.origins, query["moment"]) if moment else None)))
        a, b, view = query.get("a", ""), query.get("b", ""), query.get("view", "only")
        if not a or not b:
            return HTMLResponse(str(parts.evolution_diff(None, a, b, view, evolution_labels())))
        first, second = await asyncio.gather(asyncio.to_thread(schema_at, project_root, state.origins, a),
                                             asyncio.to_thread(schema_at, project_root, state.origins, b))
        diff = schema_diff(first, second, renames_between(state.origins, a, b)) if first and second else None
        return HTMLResponse(str(parts.evolution_diff(diff, a, b, view, evolution_labels())))

    def er_context(params: dict) -> dict:
        """Diagrams › ER Diagrams: its data's URL (with the filters chosen), the projects of the DATABASES
        tree, and what Focus offers: what the drawing can show with the Project chosen (its databases,
        schemas, files, tables and views), taken from the drawing itself."""
        outline = catalog.outline()
        drawn = er_diagram(state, catalog, connections.connections(), EXAMPLES_FOLDER if developing else "", params.get("project", ""))
        icons = {"database": "database", "schema": "schema", "file": "file"}
        targets = [{"path": node["id"], "name": node["label"], "role": icons.get(node["role"], "kind-table"), "symbol": ""}
                   for node in drawn["nodes"] if node["role"] in ("database", "schema", "file") or not node["frame"]]
        tree = pages.database_tree(state, connections.connections(), apart=EXAMPLES_FOLDER if developing else "", read=outline)
        # The filters cascade: the Project limits the Focus and the Slices offered; a Focus or Slice it does not
        # hold is let go; Depth counts only from a table or view.
        offered = {target["path"] for target in targets}
        if params.get("focus") and params["focus"] not in offered:
            params["focus"] = ""
        slice_names = [found["name"] for found in slices.slices()
                       if any(t["found"] in offered for t in resolve_slice(found, catalog)["tables"] if t["found"])]
        if params.get("slice") and params["slice"] not in slice_names:
            params["slice"] = ""
        focused_table = params.get("focus", "") in {target["path"] for target in targets if target["role"] == "kind-table"}
        query = urlencode([(key, params[key]) for key in ("project", "focus", "depth", "slice") if params.get(key)])
        return {"er_url": f"/graph/er{'?' + query if query else ''}" if targets else "",
                "er_projects": [{"path": node["path"], "name": node["name"]} for node in tree if node["role"] == "project"],
                "er_slices": slice_names, "er_targets": targets, "er_depth": focused_table}

    DIFF_GROUPS = (("migrations", "Migrations"), ("sql", "SQL files"), ("orm", "ORM models"), ("dumps", "Dumps"),
                   ("databases", "Databases"))  # the buttons over each trail of the Diff page: the kind of place

    def diff_group(place: str) -> str:
        """Which button of the Diff page a place is under: `databases` for a live one, else its origin's kind."""
        if not place.startswith(ORIGIN_PREFIX):
            return "databases"
        name = place.removeprefix(ORIGIN_PREFIX).partition("::")[0]
        kind = next((o["kind"] for o in state.origins if o["name"] == name), "")
        if kind == "dump":
            return "dumps"
        if kind == "sql file":
            return "sql"
        return "migrations" if kind in MIGRATION_KINDS or kind.endswith("migrations") else "orm"

    def diff_context(params: dict) -> dict:
        """The Diff page: places A and B (`?a=&b=`; B left out: the database A's origin created, see
        `default_b`), the kind of place each trail lists (`?ga=&gb=`, see `DIFF_GROUPS`), the boxes of each
        trail, where they differ (`compare`) and the tab shown (`?show=`)."""
        def chosen(side: str) -> str:  # the deepest field filled, each under the one before it (a changed one empties those under it)
            place = params.get(side, "")
            for depth in range(4):
                value = params.get(f"{side}{depth}", "")
                if depth == 0:
                    place = value if f"{side}0" in params else place
                elif value and place and value.startswith(place) and value != place:
                    place = value
                else:
                    break
            return place

        profile = profiles.profile(params["profile"]) if params.get("profile") else None  # opened from Saved profiles
        a = chosen("a") or (profile or {}).get("a", "")
        if params.get("ga") and a and diff_group(a) != params["ga"]:
            a = ""
        start = default_b(a, state.origins, catalog, connections.connections(), project_root)
        b = chosen("b") or (profile or {}).get("b", "") or start["b"]
        if params.get("gb") and b and diff_group(b) != params["gb"]:
            b = ""
        profile = next((p for p in profiles.profiles() if p["a"] == a and p["b"] == b), None) if a and b else None  # this comparison, saved
        ignore = (profile or {}).get("ignore", [])
        compared = compare(catalog, a, b, project_root, ignore) if a and b else None
        keys = [key for key, _ in DIFF_TABS]
        show = params.get("show") if params.get("show") in keys else \
            next((key for key in keys if compared and compared["tabs"][key]["count"]), keys[0])
        held = [o for o in catalog.objects(origins=True) if o["kind"] in ("database", "schema", "table", "view", "materialized view", "foreign table")]
        present = {diff_group(f"{ORIGIN_PREFIX}{o['name']}") for o in state.origins} | ({"databases"} if catalog.objects(kind="database") else set())
        groups = [(key, label) for key, label in DIFF_GROUPS if key in present]
        group_a = params.get("ga") or (diff_group(a) if a else next((key for key, _ in groups), ""))
        group_b = params.get("gb") if params.get("gb") and (params.get("b0") is not None or not start["b"]) else (diff_group(b) if b else "databases")
        closest = [] if start["b"] else start["suggestions"]
        def named(place: str) -> str:  # a place as the tabs name it: its database (or file), then schema.table
            if place.startswith(ORIGIN_PREFIX):
                name, _, key = place.removeprefix(ORIGIN_PREFIX).partition("::")
                base = "/".join(name.split("/")[-2:])
            else:
                parts = place.removeprefix("db:").split("/", 2)
                base, key = parts[1] if len(parts) > 1 else parts[0], parts[2] if len(parts) > 2 else ""
            return f"{base}.{key}" if key else base

        view = "profiles" if params.get("view") == "profiles" else "trails"
        saved = [{**found, "names": {"a": named(found["a"]), "b": named(found["b"])}}
                 for found in (profiles.profiles() if view == "profiles" else [])]
        return {"diff_view": view, "diff_profile": profile, "diff_ignore": ignore, "diff_profiles": saved, "ignorable": IGNORABLE,
                "diff_names": {"a": named(a) if a else "A", "b": named(b) if b else "B"},
                "diff_a": a, "diff_b": b, "diff_start": start, "diff": compared, "diff_show": show, "diff_tabs": DIFF_TABS,
                "diff_groups": groups, "diff_group": {"a": group_a, "b": group_b},
                "diff_trails": {"a": diff_trail(held, a, group_a), "b": diff_trail(held, b, group_b, closest)}}

    def diff_trail(held: list[dict], place: str, group: str, closest: list[str] = ()) -> list[dict]:
        """The fields of a side of the Diff page, down to a place: each its `title`, `help`, `placeholder`,
        `options` (`path`, `name`, `kind`, `role`: its icon, `closest`) and the one `picked`, then a field for
        the level under it, empty. The first lists the places of the kind chosen (`group`): those origins,
        or the servers read (`closest`: the databases suggested, first)."""
        by_path = {o["path"]: o for o in held}
        children: dict[str, list[dict]] = {}
        for o in held:
            children.setdefault(o["parent"], []).append({"path": o["path"], "name": o["name"], "kind": o["kind"],
                                                         "role": {"database": "kind-databases", "schema": "schema"}.get(o["kind"], "kind-table")})
        if group == "databases":
            servers = sorted({o["parent"] for o in held if o["kind"] == "database" and o["parent"]})
            roots = [{"path": by_path[path]["path"], "name": f"{by_path[path]['parent'].removeprefix('db:')} › {by_path[path]['name']}",
                      "kind": "database", "role": "kind-databases", "closest": True} for path in closest if path in by_path]
            roots += [{"path": server, "name": server.removeprefix("db:"), "kind": "server", "role": "kind-databases"} for server in servers]
        else:
            roots = sorted(({"path": f"{ORIGIN_PREFIX}{o['name']}", "name": "/".join(o["name"].split("/")[-2:]), "kind": o["kind"],
                             "role": f"kind-{group}"} for o in state.origins
                            if diff_group(f"{ORIGIN_PREFIX}{o['name']}") == group), key=lambda o: o["name"].lower())
        chain, at = [], place if diff_group(place) == group else ""
        while at in by_path:
            chain.insert(0, at)
            at = by_path[at]["parent"]
        if at.startswith("db:"):
            chain.insert(0, at)
        firsts = {"migrations": "Migrations", "sql": "SQL file", "orm": "ORM models", "dumps": "Dump", "databases": "Server"}
        titles = {"database": "Database", "schema": "Schema"}
        boxes = []
        for depth in range(len(chain) + 1):
            options = roots if depth == 0 else sorted(children.get(chain[depth - 1], []), key=lambda o: o["name"].lower())
            if not options:
                break
            title = firsts.get(group, "Place") if depth == 0 else titles.get(options[0]["kind"], "Table or view")
            help_text = (f"The {title.lower()} compared; type a part of its name or path." if depth == 0 else
                         f"Only this {title.lower()} of what the field before holds; empty: all of it.")
            boxes.append({"title": title, "help": help_text, "placeholder": f"{title}…" if depth == 0 else "All",
                          "options": options, "picked": chain[depth] if depth < len(chain) else ""})
        return boxes

    OBJECTS_PER_PAGE = 50

    def browse(params: dict) -> tuple[str, list[dict], list[dict]]:
        """Browse's level: what the ticks of the path (or `at`, a page's link) choose, and the path's parts.

        Each part of the path is a level (servers, databases, schemas, tables) with every option it has
        under what is ticked above it, and what is ticked in it; the list shows the level under the
        last part ticked (the columns, once tables are), each row knowing which ticked item holds it.
        """
        picked = {level: list(params.get("picked", {}).get(level, [])) for level in pages.BROWSE_FIELDS}
        at = params.get("at", "")
        if at and not any(picked.values()):  # a page's link, or a row's name: that one thing, down to it
            chain = [path for path, _ in pages.db_crumbs(at)] + [at]
            for level, path in zip(pages.BROWSE_FIELDS, chain):
                picked[level] = [path]
        crumbs, parents = [], [""]
        for level in pages.BROWSE_FIELDS:
            options = [{**row, "parent": parent} for parent in parents for row in catalog.level(parent)["rows"]]
            known = {row["path"] for row in options}
            ticked = [path for path in picked[level] if path in known]
            crumbs.append({"level": level, "field": pages.BROWSE_FIELDS[level], "options": options, "picked": ticked,
                           "several_parents": len(parents) > 1})
            if not ticked:
                return level, options, crumbs
            parents = ticked
        rows = [{**row, "parent": parent} for parent in parents for row in catalog.level(parent)["rows"]]
        crumbs.append({"level": "columns", "field": "", "options": [], "picked": [], "several_parents": len(parents) > 1})
        return "columns", rows, crumbs

    def objects_list(params: dict) -> dict:
        """Navigate › By Level. Browse (the default): one level of the SQL tree (`at`), its own
        columns. Search: every object read, filtered by database (or a server, from a page), schema, kind
        and name. In both, each column's own filter (the values chosen in it, `params["filters"]`) and the
        order chosen by its title; one page of the rows, the values each filter lists and the filters in use."""
        mode = "search" if params.get("mode") == "search" else "browse"
        context: dict = {"mode": mode}
        top: list[tuple[str, str, str]] = []  # the filters above the table in use: (field, label, shown)
        if mode == "browse":
            level, rows, crumbs = browse(params)
            # ← takes away the ticks of the deepest part ticked: one level up.
            up = pages.browse_url({c["level"]: c["picked"] for c in crumbs[:-2]}) if len(crumbs) > 1 else ""
            context.update(level=level, crumbs=crumbs, up=up)
        else:
            level = "search"
            within = params.get("within", "")  # a server, database or schema, from a page's link
            database = params.get("database") or ("/".join(within.split("/")[:2]) if within.count("/") >= 1 else "")
            schema = params.get("schema") or (within if within.count("/") == 2 else "")
            if database and not schema.startswith(f"{database}/"):
                schema = ""
            if params.get("database") is not None or params.get("schema") is not None:
                within = schema or database
            rows = [{"path": o["path"], "name": o["name"], "kind": o["kind"], "where": pages.db_place(o["parent"]),
                     "rows": o["data"].get("rows"), "comment": o["data"].get("comment", ""), "down": False}
                    for o in catalog.objects(kind=params.get("kind", ""), within=within, name=params.get("name", "").strip())]
            context.update(databases=catalog.objects(kind="database"), schemas=catalog.objects(kind="schema", within=database),
                           object_kinds=sorted({o["kind"] for o in catalog.objects()} - {"database", "schema"}),
                           chosen={"database": database, "schema": schema, "kind": params.get("kind", ""),
                                   "name": params.get("name", ""), "within": within})
            top = [("within", "In", pages.db_place(within) if within and not database else ""),
                   ("database", "Database", pages.db_place(database)), ("schema", "Schema", pages.db_place(schema)),
                   ("kind", "Kind", params.get("kind", "")), ("name", "Name", params.get("name", "").strip())]
        columns = pages.LIST_COLUMNS[level]
        if mode == "browse" and context["crumbs"][-1]["several_parents"]:  # rows from several ticked above: where each is
            columns = [columns[0], {"key": "in", "title": "In", "filter": "list"}, *columns[1:]]
            for row in rows:
                row["in"] = pages.db_place(row["parent"])
        context["listing"] = list_page(rows, columns, params, level if mode == "browse" else "search",
                                       [entry for entry in top if entry[2]])
        return context

    def list_page(rows: list[dict], columns: list[dict], params: dict, level: str, top: list | None = None,
                  chosen: dict[str, list[str]] | None = None) -> dict:
        """One page of a list of DATABASES (Navigate › By Level, Lint), as `macros.list_table` draws it: the rows
        its columns' filters let through (`params["filters"]`, or `chosen`), in the order chosen by a title
        (`sort`, `dir`), `page`; with the values each filter lists and the filters in use (`top`: those above
        the list, `(field, label, shown)`)."""
        chosen = params.get("filters", {}) if chosen is None else chosen  # by column, the values chosen in its filter
        values = pages.filter_values(rows, columns, chosen)
        rows, in_use = pages.filter_rows(rows, columns, chosen)
        sort = params.get("sort", "") if any(c["key"] == params.get("sort") for c in columns) else ""
        descending = params.get("dir") == "desc"
        if sort:
            rows.sort(key=lambda row: pages.sort_key(row.get(sort)), reverse=descending)
        page = int(params.get("page", "1")) if str(params.get("page", "1")).isdigit() else 1
        offset = OBJECTS_PER_PAGE * (max(1, page) - 1)
        return {"rows": rows[offset:offset + OBJECTS_PER_PAGE], "total": len(rows), "level": level,
                "pages": pages.pagination(len(rows), offset, OBJECTS_PER_PAGE), "columns": columns, "values": values,
                "sort": sort, "direction": "desc" if descending else "asc", "empty": pages.EMPTY,
                "column_filters": {c["key"]: [v for v in chosen.get(c["key"], []) if v] for c in columns},
                "in_use": (top or []) + in_use}

    def lint_rows(found: list[dict]) -> list[dict]:
        """The findings of the lint as rows of a list (see `list_page`)."""
        return [{**f, "rule": f["title"], "rule_id": f["rule"],
                 "found_in": [place.removeprefix("db:").removeprefix("origin:") for place in f["found_in"]]} for f in found]

    def lint_list(params: dict) -> dict:
        """The Lint tab: the counters of the open findings (by level, by rule) and one page of the findings.
        Opened without a State filter (a link, the tab), only the open ones are listed; the list sends its
        State filter always, so clearing it lists the accepted ones too."""
        found = lint.findings(state.origins, connections.connections())
        chosen = dict(params.get("filters", {}))
        if "state" not in chosen:
            chosen["state"] = ["open"]
        opened = [f for f in found if f["state"] == "open"]
        rules: dict[str, dict] = {}
        for f in opened:
            rules.setdefault(f["title"], {"title": f["title"], "level": f["level"], "help": f["help"], "count": 0})["count"] += 1
        return {"lint_levels": [(level, sum(1 for f in opened if f["level"] == level)) for level in LINT_LEVELS],
                "lint_rules": sorted(rules.values(), key=lambda r: (LINT_LEVELS.index(r["level"]), r["title"])),
                "lint_accepted": len(found) - len(opened),
                "listing": {**list_page(lint_rows(found), pages.LIST_COLUMNS["lint"], params, "lint", chosen=chosen), "kept": ("state",)}}

    def database_modal(details: str = "", editing: bool = False, oob: bool = False, error: str = "") -> str:
        """The modals of DATABASES: everything about a connection (`details`, changed in place with
        `editing`), or, without `details`, the form of a new one; `oob` sends its card again with it."""
        listed = {c["id"]: c for c in connections.connections()}
        return templates.get_template("database_form.html").render(
            details=listed.get(details), test=connection_tests.get(details), editing=editing, kinds=KINDS, sign_ins=SIGN_INS,
            collection=catalog.collection(details) if details else None, oob=oob, error=error)

    async def database_form(request: Request) -> Response:
        """A modal of DATABASES (see `database_modal`): `?details=<id>`, `&edit=1` to change it, or a new one."""
        query = request.query_params
        return HTMLResponse(database_modal(query.get("details", ""), bool(query.get("edit"))))

    async def refresh_quietly(connection_id: str) -> None:
        """Read a connection again; one that cannot be opened now (locked passwords, a variable not set)
        keeps what it had, its failure shown by its reading."""
        try:
            await collect_connection(connections, catalog, connection_id)
        except (ValueError, Locked):
            pass

    def diff_profile_modal(a: str, b: str, name: str = "", error: str = "", form: dict | None = None, details: bool = False) -> str:
        """The form saving a comparison of the Diff as a profile: a new one for A and B, or a saved one (`name`)
        to change, its fields kept when a refusal is shown; with `details`, the saved one's details (what it
        keeps and what its comparison finds now), in the consultation modal."""
        found = profiles.profile(name) if name else None
        counts = {}
        if details and found:
            counted = compare(catalog, found["a"], found["b"], ignore=found.get("ignore", []))
            counts = {"error": counted["error"], **{key: counted["tabs"][key]["count"] for key, _ in DIFF_TABS}}
        return templates.get_template("database_form.html").render(
            diff_profile_mode=True, profile=found, a=a or (found or {}).get("a", ""), b=b or (found or {}).get("b", ""),
            ignorable=IGNORABLE, form=form or {}, error=error, details=details and found is not None, counts=counts)

    async def diff_profile_form(request: Request) -> Response:
        """The profile form: `?a=&b=` (the comparison shown) and `&profile=<name>` (the one opened); or a
        profile's details, `?details=<name>`."""
        query = request.query_params
        if query.get("details"):
            return HTMLResponse(diff_profile_modal("", "", query["details"], details=True))
        return HTMLResponse(diff_profile_modal(query.get("a", ""), query.get("b", ""), query.get("profile", "")))

    def diff_profile_action(request: Request, name: str, form: dict, ignore: list[str]) -> Response:
        """A profile saved (`diff-profile-save`: a new one, or over the one it was, `previous`), its comparison
        then shown in Trails; or deleted (`diff-profile-delete`), Saved profiles shown again."""
        if name == "diff-profile-delete":
            profiles.delete(form.get("name", ""))
            params = {"tab": "diff", "view": "profiles"}
            return render_page(request, "database.html", "/databases/diff?view=profiles",
                               {"path": "", "view": "database", **database_context(params)})
        try:
            kept = profiles.save(form.get("name", ""), form.get("a", ""), form.get("b", ""), form.get("description", ""), ignore,
                                 form.get("previous", ""))
        except ValueError as problem:
            return HTMLResponse(diff_profile_modal(form.get("a", ""), form.get("b", ""), form.get("previous", ""), str(problem),
                                                   {**form, "ignore": ignore}), headers={"HX-Retarget": "#database-dialog-body"})
        params = {"tab": "diff", "view": "trails", "profile": kept["name"]}
        return render_page(request, "database.html", f"/databases/diff?view=trails&profile={quote(kept['name'], safe='')}",
                           {"path": "", "view": "database", **database_context(params)})

    async def slice_action(request: Request, name: str, form: dict) -> Response:
        """A slice saved (`slice-save`: from its form, the tables ticked; from the Diagram, the tables and
        positions as JSON in `tables`, answered in JSON), deleted (`slice-delete`), or the form of a new one
        holding the Diagram's selection (`slice-new`)."""
        if name == "slice-new":
            chosen = json.loads(form.get("tables") or "[]")
            return HTMLResponse(slice_modal(chosen=chosen))
        if name == "slice-delete":
            slices.delete(form.get("name", ""))
            context = {"path": "", "view": "database", "params": {"tab": "slices"}, **database_context({"tab": "slices"})}
            return render_page(request, "database.html", pages.DATABASE_URLS["slices"], context)
        from_diagram = form.get("from") == "diagram"
        if from_diagram or form.get("tables", "").startswith("["):
            tables = json.loads(form.get("tables") or "[]")
        else:
            sent = await request.form()
            placed = {}
            for value in sent.getlist("placed"):  # a new slice from the Diagram: where its boxes were
                path, _, at = value.rpartition("|")
                path, _, x = path.rpartition("|")
                placed[path] = {"x": float(x), "y": float(at)}
            tables = [{"path": path, **placed.get(path, {})} for path in sent.getlist("table")]
        previous = slices.slice(form.get("previous", "")) if form.get("previous") else None
        if not from_diagram and previous is not None:  # positions kept for the tables still in it
            placed = {t["path"]: t for t in previous.get("tables", [])}
            tables = [{**placed.get(t["path"], {}), **{k: v for k, v in t.items() if v is not None}} for t in tables]
        try:
            kept = slices.save(form.get("name", ""), form.get("text", previous.get("text", "") if previous and from_diagram else ""),
                               tables, form.get("previous", ""))
        except ValueError as problem:
            if from_diagram:
                return JSONResponse({"ok": False, "error": str(problem)})
            body = "#page-dialog-body" if form.get("edit") else "#database-dialog-body"  # the refusal shown in the form
            return HTMLResponse(slice_modal(form.get("previous", ""), True, tables, form, str(problem)), headers={"HX-Retarget": body})
        if from_diagram:
            return JSONResponse({"ok": True, "name": kept["name"]})
        context = {"path": "", "view": "database", "params": {"tab": "slices"}, **database_context({"tab": "slices"})}
        return render_page(request, "database.html", pages.DATABASE_URLS["slices"], context)

    async def database_action(request: Request) -> Response:
        """Allow, block, test, refresh (read its database again now), add, change or delete a connection,
        unlock the saved passwords, or sample a table again (`sample-again`: the connection's `id` and the table's `path`).

        The same store the MCP tools use. Sent from a connection's details (`modal`), the details come
        back (a refusal shown in them) and its card follows; otherwise the page comes back redrawn,
        with a refusal (a field missing, a wrong master password...) shown on top.
        """
        if not _same_origin(request):
            return Response("", status_code=403)
        form = {key: value for key, value in (await request.form()).items()}
        name, identifier = request.path_params["action"], form.get("id", "")
        if name == "refresh-all":  # the tree's refresh: every allowed connection read again now, in the background
            for connection in connections.connections():
                if connection["allowed"]:
                    asyncio.create_task(refresh_quietly(connection["id"]))
            return Response("", status_code=204)
        if name.startswith("diff-profile-"):
            return diff_profile_action(request, name, form, (await request.form()).getlist("ignore"))
        if name.startswith("slice-"):
            return await slice_action(request, name, form)
        if name in ("lint-accept", "lint-reopen"):  # a finding of the lint accepted (with its reason), or open again
            if name == "lint-reopen":
                lint.reopen(form.get("key", ""))
            else:
                finding = next((f for f in lint.findings(state.origins, connections.connections()) if f["key"] == form.get("key")), None)
                try:
                    if finding is None:
                        raise ValueError("This finding is no longer found: the lint was read again.")
                    lint.accept(finding, form.get("reason", ""))
                except ValueError as problem:
                    return HTMLResponse(lint_modal(form.get("key", ""), form.get("reason", ""), str(problem)),
                                        headers={"HX-Retarget": "#database-dialog-body"})
            # The list comes back as it was (its filters, order and page): the address the page is at.
            at = urlsplit(request.headers.get("HX-Current-URL", ""))
            query = at.query if at.path == pages.DATABASE_URLS["lint"] else ""
            params = {**database_params(QueryParams(query)), "tab": "lint"}
            context = {"path": "", "view": "database", **database_context(params)}
            return render_page(request, "database.html", pages.DATABASE_URLS["lint"] + (f"?{query}" if query else ""), context)
        if name == "sample-again":  # an object's page: its table sampled again now; the page follows by itself
            try:
                await collect_connection(connections, catalog, identifier, sample_again=form.get("path", ""))
            except (ValueError, Locked):
                pass
            return Response("", status_code=204)
        actions = {
            "allow": lambda: connections.allow(identifier),
            "block": lambda: connections.allow(identifier, False),
            "remove": lambda: connections.remove(identifier),
            "save": lambda: connections.save(form, form.get("password", ""), form.get("ssh_password", "")),
            "edit": lambda: connections.edit(identifier, form, form.get("password", ""), form.get("ssh_password", "")),
            "unlock": lambda: connections.unlock(form.get("master_password", "")),
        }
        if name not in actions and name not in ("test", "refresh"):
            return Response("", status_code=404)
        error = ""
        try:
            if name == "test":
                connection_tests[identifier] = await run_test(connections.spec(identifier))
            elif name == "refresh":
                await collect_connection(connections, catalog, identifier)
            else:
                actions[name]()
                if name in ("block", "remove", "edit"):  # what was read from it no longer holds
                    connection_tests.pop(identifier, None)
                    catalog.forget(identifier)
        except (ValueError, Locked) as refused:
            error = str(refused)
        if form.get("modal") and not (name == "remove" and not error):
            # From the details: they stay open, with the refusal if any, and the card follows.
            return HTMLResponse(database_modal(identifier, editing=name == "edit" and bool(error), oob=True, error=error))
        context = {"path": "", "view": "database", **database_context({"tab": "connections"}, error)}
        response = render_page(request, "database.html", pages.DATABASE_URLS["connections"], context)
        if form.get("modal"):  # deleted from its details: the page comes back in place of them, which close
            response.headers.update({"HX-Retarget": "#content", "HX-Reswap": "innerHTML", "HX-Trigger": "page-dialog-done"})
        return response

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
        context = {"tab": tab, "note_types": NOTE_TYPES, "note_groups": NOTE_GROUPS, "note_group_texts": NOTE_GROUP_TEXTS,
                   "note_type_uses": NOTE_TYPE_USES, "not_a_note": NOT_A_NOTE, "note_type": note_type,
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

    def agent_url(params: dict) -> str:
        """The address of an AGENT page with the same plans, item and filters: `/agent/<page>?...`."""
        query = "&".join(f"{key}={value}" for key, value in params.items() if value and key != "tab")
        return f"/agent/{params.get('tab') or 'planner'}" + (f"?{query}" if query else "")

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
        context = {"query": query, "note_types": NOTE_TYPES, "note_groups": NOTE_GROUPS, "moments": MOMENTS,
                   "tab": query.get("tab", "planner"),
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

        def moments() -> list[str] | None:
            # The moment checkboxes of a guideline; unticked boxes are not sent, so a marker says they were shown.
            return submitted.getlist("moments") if form.get("moments_shown") else None

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
            "create_note": lambda: search.create_reviewed_note(form.get("type", ""), form.get("statement", ""),
                                                               form.get("why", ""), lines(form.get("entities")),
                                                               form.get("different_because", ""), "wiki", moments()),
            "update_note": lambda: notes.update_note(number("note_id"), optional("statement"), optional("why"),
                                                     lines(optional("entities")), moments()),
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
        name = request.path_params["action"]
        try:
            result = action()
            if inspect.isawaitable(result):
                result = await result
        except SimilarNotesFound as found:
            # The review before adding: the modal stays open, filled in, with the similar notes listed.
            context = form_context({**form, "kind": "note"})
            reply = templates.get_template("notes_form.html").render(**context, similar=found.similar, filled=form,
                                                                       filled_moments=submitted.getlist("moments"))
            return HTMLResponse(reply, headers={"HX-Retarget": "#notes-dialog-body", "HX-Reswap": "innerHTML"})
        except ValueError as refused:
            error = str(refused)
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
        context = {"path": "", "view": "notes", "params": params, "error": error,
                   **notes_context(params)}
        return render_page(request, "notes.html", agent_url({**params, "tab": context["tab"]}), context)

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
        html = templates.get_template("git_commit.html").render(files=files, hash=commit_hash,
                                                                planned=notes.archived(commit_hash))
        return HTMLResponse(html)

    def depth_of(params) -> int:
        """The Depth chosen in a diagram's bar: 1 to `MAX_CALL_DEPTH`, all of it by default."""
        depth = params.get("depth", "")
        return min(int(depth), MAX_CALL_DEPTH) or 1 if depth.isdigit() else MAX_CALL_DEPTH

    async def view_data(request: Request) -> Response:
        """Data of a graph view, as JSON, built by the same functions the MCP tools use."""
        view = request.path_params["view"]
        params = request.query_params
        _, shown = view_settings(request)  # the wiki's language filter; the MCP tools see everything
        if view == "architecture":
            graph = architecture(state, params.get("level", "modules"), EXAMPLES_FOLDER if developing else "",
                                 params.get("project", ""), params.get("focus", ""), depth_of(params))
            return JSONResponse(pages.visible_graph(state, graph, shown))
        if view == "classes":
            graph = class_diagram(state, params.get("package", ""), EXAMPLES_FOLDER if developing else "",
                                  params.get("project", ""), params.get("focus", ""), depth_of(params))
            return JSONResponse(pages.visible_graph(state, graph, shown))
        if view == "planner":
            plans = [int(part) for part in params.get("plans", "").split(",") if part.isdigit()]
            return JSONResponse(notes.planner_graph(plans))
        if view == "calls":
            graph = call_graph(state, params.get("focus", ""), depth_of(params), params.get("direction", "both"))
            return JSONResponse(pages.visible_graph(state, graph, shown))
        if view == "timeline":  # when each file appeared, for the timeline of the architecture
            return JSONResponse(await file_timeline(project_root) or {"commits": [], "added": {}})
        if view == "universe":  # DATABASES › Navigate › By Graph: the databases as the server last read them; or what a file declares
            return JSONResponse(catalog.universe(params.get("origin", "")))
        if view == "evolution":  # DATABASES › Evolution: every origin's moments, its lane
            return JSONResponse(evolution_moments())
        if view == "er":  # DATABASES › Diagrams › ER Diagrams: the live databases and what the files declare, in the tree's levels
            found = slices.slice(params["slice"]) if params.get("slice") else None
            return JSONResponse(er_diagram(state, catalog, connections.connections(), EXAMPLES_FOLDER if developing else "",
                                           params.get("project", ""), params.get("focus", ""), depth_of(params),
                                           resolve_slice(found, catalog) if found else None))
        if view == "local":  # an entity's page: the entity and its neighbours, a few steps away
            graph = call_graph(state, params.get("focus", ""), depth_of(params), "both", kinds=LOCAL_KINDS)
            return JSONResponse(pages.visible_graph(state, graph, shown))
        return JSONResponse({"error": f"Unknown view: {view}"}, status_code=404)

    async def dashboard() -> dict:
        """What the dashboard at `/` sums up of each section, from the same functions as their pages.

        `agent`: the open plans (each with its tasks to do, doing and done) and the commits made outside the
        flow waiting for review; `code`: how many modules, classes and functions, and the dead code found;
        `databases`: the connections allowed, blocked and failing, the open lint findings by level and the
        origins differing from a database they describe; `git`: the branch, the files changed and the last
        commits.
        """
        plans, reviews = [], {"id": 0, "waiting": 0}
        for plan in notes.planner(include_done=False)["plans"]:
            tasks = [task for feature in plan["features"] for task in feature["tasks"]]
            if plan["fixed"]:
                reviews = {"id": plan["id"], "waiting": sum(task["state"] != "done" for task in tasks)}
                continue
            plans.append({"id": plan["id"], "title": plan["title"], "state": plan["state"],
                          **{status: sum(task["status"] == status for task in tasks) for status in ("todo", "doing", "done")}})
        kinds = [entity["kind"] for entity in state.entities.values()]
        listed = connections.connections()
        answers = availability()
        opened = [f for f in lint.findings(state.origins, listed) if f["state"] == "open"]
        differing = []
        for origin in state.origins:  # compared with the database it created, as Diff opens it
            place = f"{ORIGIN_PREFIX}{origin['name']}"
            if (b := default_b(place, state.origins, catalog, listed, project_root)["b"]) and \
                    any(tab["count"] for tab in compare(catalog, place, b)["tabs"].values()):
                differing.append(origin["name"])
        top = await top_level(project_root)
        commits = await read_history(project_root, 5) or []
        return {
            "agent": {"plans": plans, "reviews": reviews},
            "code": {"modules": kinds.count("module"), "classes": kinds.count("class"), "functions": kinds.count("function"),
                     "dead": len(state.dead_code)},
            "databases": {"allowed": sum(bool(c["allowed"]) for c in listed), "blocked": sum(not c["allowed"] for c in listed),
                          "failing": sum(answer == "failed" for answer in answers.values()),
                          "lint": [(level, sum(f["level"] == level for f in opened)) for level in LINT_LEVELS],
                          "differing": len(differing), "origins": len(state.origins)},
            "git": {"branch": await current_branch(top) if top else "", "changed": len(await changed_files(top)) if top else 0,
                    "commits": commits},
        }

    async def index(request: Request) -> Response:
        """The dashboard: a block per section (AGENT, CODE, DATABASES, GIT) summing it up."""
        if not state.ready:
            return render_page(request, "loading.html", "/", {"path": ""})
        return render_page(request, "dashboard.html", "/", {"path": "", "view": "dashboard", "board": await dashboard()})

    async def wiki(request: Request) -> Response:
        return await render(request, request.path_params["path"])

    async def source(request: Request) -> Response:
        path = request.path_params["path"]
        if path.startswith("file:"):  # a file of an origin (DATABASES): SQL in the origin's dialect, an ORM's code; no other file
            file = path.removeprefix("file:")
            origin = next((o for o in state.origins for step in o["steps"] if file in (step["file"], step.get("down"))), None)
            if origin is None:
                return HTMLResponse("", status_code=404)
            code = (project_root / file).read_text(encoding="utf-8", errors="replace")
            language = "python" if file.endswith(".py") else "text" if not file.lower().endswith(".sql") else origin["dialect"]
            return HTMLResponse(templates.get_template("source.html").render(code=code, language=language))
        entity = state.entities.get(path)
        if entity is None:
            return HTMLResponse("", status_code=404)
        code = pages.source_code(project_root, entity)
        language = entity["language"]
        return HTMLResponse(templates.get_template("source.html").render(code=code, language=language))

    def recall_groups(found: dict, query: str) -> list[dict]:
        """Rows of the search box for the `all` mode: each `recall` group with results, in its order.

        Planner items and notes link to their AGENT page with the item shown; code rows are
        the same as in the other modes.
        """
        groups = []
        for group in RECALL_GROUPS:
            if not found[group]:
                continue
            if group == "code":
                rows = pages.ranked_results(state, [(row["ref"], row["score"]) for row in found[group]], query)
            elif group == "databases":
                rows = [{**row, "url": f"/wiki/{row['ref']}"} for row in found[group]]
            elif group == "history":
                rows = [{**row, "url": f"/git?commit={row['commits'][0]}" if row.get("commits") else "/git"}
                        for row in found[group]]
            else:
                rows = [{**row, "url": (f"/agent/planner?plans={row['plan']}&selected={row['ref']}"
                                        if group == "planning" else f"/agent/{group}?selected={row['ref']}")}
                        for row in found[group]]
            groups.append({"name": group, "rows": rows})
        return groups

    def object_row(path: str, document: dict, score: float) -> dict:
        """A database object in the search box's results, shaped as a code entity's row."""
        return {"path": path, "role": document["kind"], "icon": "database", "symbol": "", "before": document["title"],
                "match": "", "after": "", "snippet": {"before": document["summary"], "match": "", "after": ""}, "score": score}

    async def search_box(request: Request) -> Response:
        query = request.query_params.get("q", "")
        mode = request.query_params.get("mode", DEFAULT_MODE)
        page = int(request.query_params.get("page", "1")) if request.query_params.get("page", "1").isdigit() else 1
        context = {"query": query, "mode": mode, "results": [], "preparing": None}
        _, shown = view_settings(request)
        if query.strip() and mode == "all":
            found = await search.recall(query, WIKI_WAIT_SECONDS)
            found["code"] = [row for row in found["code"] if pages.visible(state.entities.get(row["ref"]), shown)]
            context["groups"], context["renamed"] = recall_groups(found, query), found.get("renamed", [])
        elif query.strip():
            offset = DEFAULT_LIMIT * (max(1, page) - 1)
            outcome = await search.run(mode, query, DEFAULT_LIMIT, WIKI_WAIT_SECONDS, offset, shown)
            context["renamed"] = outcome.renamed
            if outcome.ready:
                objects, rows = search.database_documents(), []
                for path, score in outcome.results:
                    if path in objects:
                        rows.append(object_row(path, objects[path], score))
                    else:
                        rows.extend(pages.ranked_results(state, [(path, score)], query))
                context["results"] = rows
                context["pagination"] = pages.pagination(outcome.total, outcome.offset, DEFAULT_LIMIT)
            else:
                context["preparing"] = outcome.status
        return HTMLResponse(templates.get_template("search.html").render(**context))

    async def theme(request: Request) -> Response:
        name = request.path_params["name"]
        if name not in pages.CODE_THEMES:
            return Response("", status_code=404)
        return Response(pages.code_theme_css(name), media_type="text/css")

    async def retry_grammars(request: Request) -> Response:
        """Read the code again at once, trying the grammars that could not be fetched again."""
        if not _same_origin(request):
            return Response("", status_code=403)
        state.retry = True
        return Response("", status_code=204)

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

    async def progress(request: Request) -> Response:
        """How far the first reading of the code is: the loading screen's bar, which asks every half second.
        Once the reading is done, the page is told to load again (as the `changed` event does)."""
        if state.ready:
            return HTMLResponse("", headers={"HX-Refresh": "true"})
        return HTMLResponse(templates.get_template("macros.html").module.reading_progress(dict(state.progress)))

    async def events(request: Request) -> Response:
        queue = state.subscribe()

        async def stream():
            try:
                while True:
                    try:
                        if await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS) == "closed":
                            return
                        yield "event: changed\ndata: 1\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                state.unsubscribe(queue)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    return [
        Route("/", index),
        Route("/wiki/{path:path}", wiki),
        Route("/agent", section_page),
        Route("/agent/form", note_form),
        Route("/agent/{action}", note_action, methods=["POST"]),
        Route("/agent/{page}", agent_page),
        Route("/code", section_page),
        Route("/databases", section_page),
        Route("/databases/form", database_form),
        Route("/databases/evolution/part", evolution_part),
        Route("/databases/slice-form", slice_form),
        Route("/databases/diff-profile-form", diff_profile_form),
        Route("/databases/lint-form", lint_form),
        Route("/databases/code-reaches", code_reaches),
        Route("/databases/{action}", database_action, methods=["POST"]),
        Route("/databases/{page:path}", databases_page),
        Route("/code/diagrams/architecture", view_page),
        Route("/code/diagrams/classes", view_page),
        Route("/code/diagrams/calls", view_page),
        Route("/git", view_page),
        Route("/code/dead-code", view_page),
        Route("/graph/{view}", view_data),
        Route("/git/branches", git_branches),
        Route("/git/commit/{hash}", git_commit),
        Route("/source/{path:path}", source),
        Route("/search", search_box),
        Route("/code-theme/{name}.css", theme),
        Route("/settings/code-theme", set_code_theme, methods=["POST"]),
        Route("/grammars/retry", retry_grammars, methods=["POST"]),
        Route("/events", events),
        Route("/progress", progress),
        Mount("/static", StaticFiles(packages=[("doctracker.wiki", "static")]), name="static"),
    ]
