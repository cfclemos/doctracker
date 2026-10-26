"""In-memory documentation data shared by the MCP tools and the frontend."""

import asyncio
from dataclasses import dataclass, field


@dataclass
class DocState:
    """Latest extraction result plus the open frontend connections to notify.

    Attributes:
        roots: Paths of the documented top-level packages.
        entities: Every extracted entity, by qualified path.
        edges: Relations between entities (contains, imports, inherits, calls), for the graph.
        errors: Packages that could not be loaded, with the reason.
        ready: Whether the first extraction has finished.
        listeners: One queue per open wiki page, notified when the data changes.
    """

    roots: list[str] = field(default_factory=list)
    entities: dict[str, dict] = field(default_factory=dict)
    edges: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    ready: bool = False
    listeners: set[asyncio.Queue] = field(default_factory=set)

    def update(self, result: dict) -> None:
        """Replace the data with a new extraction result and notify the frontend.

        Args:
            result: Output of `extract_project`: `roots`, `entities`, `edges` and `errors`.
        """
        self.roots = result["roots"]
        self.entities = result["entities"]
        self.edges = result["edges"]
        self.errors = result["errors"]
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
