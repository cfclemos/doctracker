"""Thematic views of the code graph (architecture, classes, calls) and entity history, shared by the wiki and the MCP tools."""

from doctracker.graph.model import (
    CALL_DIRECTIONS,
    MAX_CALL_DEPTH,
    architecture,
    call_graph,
    class_diagram,
    entity_history,
)

__all__ = [
    "CALL_DIRECTIONS",
    "MAX_CALL_DEPTH",
    "architecture",
    "call_graph",
    "class_diagram",
    "entity_history",
]
"""Public API of the graph package."""
