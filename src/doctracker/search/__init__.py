"""Text, BM25, semantic and hybrid search, shared by the MCP tools and the wiki."""

from doctracker.search.engine import (
    AGENT_WAIT_SECONDS,
    DEFAULT_LIMIT,
    MODES,
    WIKI_WAIT_SECONDS,
    SearchEngine,
    SearchOutcome,
)

__all__ = ["AGENT_WAIT_SECONDS", "DEFAULT_LIMIT", "MODES", "WIKI_WAIT_SECONDS", "SearchEngine", "SearchOutcome"]
"""Public API of the search package."""
