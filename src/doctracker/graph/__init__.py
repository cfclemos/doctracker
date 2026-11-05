"""Thematic views of the code graph (architecture, classes, calls), the databases' ER diagram and entity history, shared by the wiki and the MCP tools."""

from doctracker.graph.model import (
    CALL_DIRECTIONS,
    CALL_KINDS,
    ER_KINDS,
    LOCAL_KINDS,
    MAX_CALL_DEPTH,
    architecture,
    call_graph,
    class_diagram,
    class_paths,
    entity_history,
    er_diagram,
    file_timeline,
    find_callable,
    trim_view,
)

__all__ = [
    "CALL_DIRECTIONS",
    "CALL_KINDS",
    "ER_KINDS",
    "LOCAL_KINDS",
    "MAX_CALL_DEPTH",
    "architecture",
    "call_graph",
    "class_diagram",
    "class_paths",
    "entity_history",
    "er_diagram",
    "file_timeline",
    "find_callable",
    "trim_view",
]
"""Public API of the graph package."""
