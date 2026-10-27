"""HTTP routes the agents' hooks call to get the context of a moment (see `doctracker.notes.context`)."""

from pathlib import Path

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import BaseRoute, Route

from doctracker.notes import NoteStore
from doctracker.notes.context import context_for
from doctracker.server.state import DocState


def hook_routes(state: DocState, project_root: Path, notes: NoteStore) -> list[BaseRoute]:
    """Build `/hooks/context/<kind>`: the context of `session`, `planning`, `file` (`?path=`) or `commit`.

    With `?session=<id>&once=1`, a context already given in that agent session (the same kind and
    file) is given empty; what was given is kept in memory, so after a restart it is given again.

    Args:
        state: Extracted entities, to find the code of a file.
        project_root: Root of the documented project.
        notes: The store the contexts are made from.

    Returns:
        The routes; each answers `{"context": text}`, or 400 with `{"error": ...}`.
    """
    given: set[tuple[str, str, str]] = set()

    async def context(request: Request) -> Response:
        kind, params = request.path_params["kind"], request.query_params
        path = params.get("path", "")
        key = (params.get("session", ""), kind, path)
        if params.get("once") and key[0] and key in given:
            return JSONResponse({"context": ""})
        try:
            text = context_for(kind, notes, state.entities, project_root, path)
        except ValueError as refused:
            return JSONResponse({"error": str(refused)}, status_code=400)
        if params.get("once") and key[0] and text:
            given.add(key)
        return JSONResponse({"context": text})

    return [Route("/hooks/context/{kind}", context)]
