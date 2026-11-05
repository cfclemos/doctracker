"""In-memory documentation data shared by the MCP tools and the frontend."""

import asyncio
from collections.abc import MutableMapping
from dataclasses import dataclass, field


@dataclass
class DocState:
    """Latest extraction result plus the open frontend connections to notify.

    Attributes:
        roots: Paths of the documented top-level packages.
        entities: Every extracted entity, by qualified path.
        edges: Relations between entities (contains, imports, inherits, calls), for the graph.
        errors: Packages that could not be loaded, with the reason.
        dead_code: Findings of the dead code analysis (see `doctracker.analysis.scan`).
        missing_grammars: Languages left out because their grammar could not be fetched (e.g. without
            network): `language`, `grammar`, `files` and `error`.
        origins: The SQL files and migrations declaring a database schema, as read (see `databases.origins`).
        code_links: The tables and columns the code uses (see `databases.code_links.extract_links`).
        retry: Set to read the code again at once (e.g. to try the grammars again), cleared by the watcher.
        ready: Whether the first extraction has finished.
        progress: Where the extraction running is (`step`, `steps`, `title`, `done`, `total`, `unit`, see
            `extraction.griffe_loader._report`), shared with its worker process; empty before it starts.
        listeners: One queue per open wiki page, notified when the data changes.
    """

    roots: list[str] = field(default_factory=list)
    entities: dict[str, dict] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dead_code: list[dict] = field(default_factory=list)
    missing_grammars: list[dict] = field(default_factory=list)
    origins: list[dict] = field(default_factory=list)
    code_links: list[dict] = field(default_factory=list)
    retry: bool = False
    ready: bool = False
    progress: MutableMapping = field(default_factory=dict)
    listeners: set[asyncio.Queue] = field(default_factory=set)

    def update(self, result: dict) -> None:
        """Replace the data with a new extraction result and notify the frontend.

        Args:
            result: Output of `extract_project`: `roots`, `entities`, `edges`, `errors`, `dead_code`, `origins` and `code_links`.
        """
        self.roots = result["roots"]
        self.entities = result["entities"]
        self.edges = result["edges"]
        self.errors = result["errors"]
        self.dead_code = result.get("dead_code", [])
        self.missing_grammars = result.get("missing_grammars", [])
        self.origins = result.get("origins", [])
        self.code_links = result.get("code_links", [])
        self.ready = True
        self.notify()

    def notify(self) -> None:
        """Tell every open wiki page to reload its content (e.g. after a commit or a branch change)."""
        for queue in self.listeners:
            queue.put_nowait("changed")

    def subscribe(self) -> asyncio.Queue:
        """Register a wiki page to be notified of changes.

        Returns:
            Queue that receives `"changed"` every time the data is replaced.
        """
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Stop notifying a wiki page (its connection was closed).

        Args:
            queue: Queue returned by `subscribe`.
        """
        self.listeners.discard(queue)
