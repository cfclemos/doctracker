"""Every kind of search, in one place, used by the MCP tools and by the wiki.

All searches return `(path, score)` pairs, best first. Semantic and hybrid searches
need the embedding backend; while it is being prepared they report its progress
instead of results.
"""

from dataclasses import dataclass, field

from doctracker.embeddings.service import EmbeddingService
from doctracker.server.state import DocState
from doctracker.wiki.pages import description_text, summary

RRF_K = 60
"""Constant of reciprocal rank fusion: each list adds `1 / (RRF_K + rank)` to an entity's hybrid score."""

MAX_MEANING_RESULTS = 100
"""Most results of semantic and hybrid searches: every entity is somewhat similar to any query,
so their list is cut here (10 pages of `DEFAULT_LIMIT`)."""

DEFAULT_LIMIT = 10
"""Results returned when the caller does not ask for a number (MCP tools and the wiki search box)."""

AGENT_WAIT_SECONDS = 60.0
"""How long MCP tools wait for the embedding backend before answering "preparing"."""

WIKI_WAIT_SECONDS = 10.0
"""How long the wiki search box waits for the embedding backend before showing its progress."""

MODES = {
    "default": {
        "label": "Default",
        "title": "Text in names, paths and descriptions",
        "placeholder": "Search modules, classes, functions…",
    },
    "bm25": {
        "label": "BM25",
        "title": "Words in any order, ranked by BM25",
        "placeholder": "Words, in any order…",
    },
    "semantic": {
        "label": "Semantic",
        "title": "Meaning, in any language (embedding model)",
        "placeholder": "Describe what you are looking for, in any language…",
    },
    "hybrid": {
        "label": "Hybrid",
        "title": "BM25 and semantic combined",
        "placeholder": "Words or a question, in any language…",
    },
}
"""Search modes accepted by `SearchEngine.run`, with the texts the wiki shows for each one."""


@dataclass
class SearchOutcome:
    """Result of a search.

    Attributes:
        results: `(path, score)` pairs of the requested page, best first.
        total: Results of the search across all pages.
        offset: Position of the first result of the page in the whole list (0 is the best).
        ready: False when the embedding backend is still being prepared (semantic and hybrid only).
        status: Embedding backend status (progress, error) when `ready` is False.
    """

    results: list[tuple[str, float]] = field(default_factory=list)
    total: int = 0
    offset: int = 0
    ready: bool = True
    status: dict | None = None


class SearchEngine:
    """Runs text, BM25, semantic and hybrid searches over the extracted entities.

    Args:
        state: Extracted entities.
        embeddings: Embedding service; its `index` holds the BM25 and vector indexes.

    Attributes:
        state: Extracted entities.
        embeddings: Embedding service and search indexes.
    """

    def __init__(self, state: DocState, embeddings: EmbeddingService) -> None:
        self.state = state
        self.embeddings = embeddings

    async def run(self, mode: str, query: str, limit: int, wait: float, offset: int = 0) -> SearchOutcome:
        """Run the search of the given mode and return one page of its results.

        Every mode ranks its whole list; the page is cut here, so paging works the
        same in all modes (and in the MCP tools and the wiki).

        Args:
            mode: A key of `MODES`; anything else runs the default search.
            query: Text to search for.
            limit: Results per page.
            wait: Seconds to wait for the embedding backend (semantic and hybrid).
            offset: Results to skip, e.g. `limit * (page - 1)`.

        Returns:
            The page and the total, or the backend progress when it is not ready yet.
        """
        if mode == "bm25":
            ranked = self.bm25(query)
        elif mode in ("semantic", "hybrid"):
            ranked = await (self.semantic(query, wait) if mode == "semantic" else self.hybrid(query, wait))
            if ranked is None:
                return SearchOutcome(ready=False, status=self.embeddings.status())
        else:
            ranked = self.text(query)
        offset = max(0, offset)
        return SearchOutcome(ranked[offset : offset + limit], total=len(ranked), offset=offset)

    def text(self, query: str) -> list[tuple[str, float]]:
        """Find the text as typed: exact name, name prefix, name, path or description containing it.

        Args:
            query: Text to find; case is ignored.

        Returns:
            `(path, score)` pairs, best first; the score only orders the groups above (4 = exact name).
        """
        query = query.strip().lower()
        if not query:
            return []
        scored = []
        for path, entity in self.state.entities.items():
            name = entity["name"].lower()
            if name == query:
                tier = 0
            elif name.startswith(query):
                tier = 1
            elif query in name:
                tier = 2
            elif query in path.lower():
                tier = 3
            elif query in description_text(entity).lower():
                tier = 4
            else:
                continue
            scored.append((tier, len(path), path))
        return [(path, float(4 - tier)) for tier, _, path in sorted(scored)]

    def bm25(self, query: str) -> list[tuple[str, float]]:
        """Rank entities by the words they share with the query (BM25), updating the index first.

        Args:
            query: Words, in any order.

        Returns:
            `(path, score)` pairs of every entity with at least one of the words, best first.
        """
        self.embeddings.index.update_texts(self.state.entities)
        return self.embeddings.index.search_bm25(query)

    async def semantic(self, query: str, wait: float) -> list[tuple[str, float]] | None:
        """Rank entities by meaning, comparing embedding vectors.

        Args:
            query: Question or description, in any language.
            wait: Seconds to wait for the embedding backend.

        Returns:
            The `MAX_MEANING_RESULTS` closest `(path, similarity)` pairs, best first;
            `None` while the embedding backend is not ready.
        """
        if not await self.embeddings.ensure_ready(wait):
            return None
        await self.embeddings.update_index()
        vector = await self.embeddings.embed_query(query)
        return self.embeddings.index.search_vectors(vector, MAX_MEANING_RESULTS)

    async def hybrid(self, query: str, wait: float) -> list[tuple[str, float]] | None:
        """Combine BM25 and semantic search with reciprocal rank fusion.

        Entities found by both rank highest; each list adds `1 / (RRF_K + rank)`.

        Args:
            query: Text to search for.
            wait: Seconds to wait for the embedding backend.

        Returns:
            The `MAX_MEANING_RESULTS` best fused `(path, score)` pairs, best first;
            `None` while the embedding backend is not ready.
        """
        semantic = await self.semantic(query, wait)
        if semantic is None:
            return None
        scores: dict[str, float] = {}
        for ranked in (self.bm25(query), semantic):
            for rank, (path, _) in enumerate(ranked, start=1):
                scores[path] = scores.get(path, 0.0) + 1.0 / (RRF_K + rank)
        return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)[:MAX_MEANING_RESULTS]

    def describe(self, outcome: SearchOutcome) -> dict:
        """Turn a search outcome into the answer of an MCP search tool.

        Args:
            outcome: Result of a search.

        Returns:
            `status` (`ready` or `preparing`) and either the page (`results`: path, kind,
            score, summary; `total`, `offset`) or the embedding backend status.
        """
        if not outcome.ready:
            return {"status": "preparing", **(outcome.status or {})}
        results = []
        for path, score in outcome.results:
            entity = self.state.entities.get(path)
            if entity is None:
                continue
            results.append({"path": path, "kind": entity["kind"], "score": round(score, 4), "summary": summary(entity)})
        return {"status": "ready", "total": outcome.total, "offset": outcome.offset, "results": results}
