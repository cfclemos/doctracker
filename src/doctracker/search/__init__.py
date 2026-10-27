"""Text, BM25, semantic and hybrid search, and recall over everything, shared by the MCP tools and the wiki."""

from doctracker.search.engine import (
    AGENT_WAIT_SECONDS,
    DEFAULT_LIMIT,
    MODES,
    RECALL_GROUPS,
    WIKI_WAIT_SECONDS,
    SearchEngine,
    SearchOutcome,
    SimilarNotesFound,
)

__all__ = ["AGENT_WAIT_SECONDS", "DEFAULT_LIMIT", "MODES", "RECALL_GROUPS", "WIKI_WAIT_SECONDS", "SearchEngine", "SearchOutcome",
           "SimilarNotesFound"]
"""Public API of the search package."""
