"""In-memory documentation data shared by the MCP tools and the frontend."""

import asyncio
from dataclasses import dataclass, field


@dataclass
class DocState:
    """Latest extraction result plus the open frontend connections to notify."""

    roots: list[str] = field(default_factory=list)
    entities: dict[str, dict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    ready: bool = False
    listeners: set[asyncio.Queue] = field(default_factory=set)

    def update(self, result: dict) -> None:
        """Replace the data with a new extraction result and notify the frontend."""
        self.roots = result["roots"]
        self.entities = result["entities"]
        self.errors = result["errors"]
        self.ready = True
        for queue in self.listeners:
            queue.put_nowait("changed")

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self.listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)
