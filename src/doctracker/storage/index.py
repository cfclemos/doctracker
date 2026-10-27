"""Search indexes kept on disk in one SQLite database: BM25 (FTS5) and embedding vectors.

Nothing stays in memory between searches: every search opens the database, brings
the indexes in line with the current documents (only new or changed texts are
processed, in one transaction) and runs the query. The documents are the code's
entities (by path) and the notes and planner items (by `note:<id>`, `task:<id>`...).

Vector similarity runs inside SQLite with the `sqlite-vec` extension when this
Python allows loading extensions; otherwise the vectors are read and compared with numpy.
"""

import hashlib
import re
import sqlite3
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from doctracker.wiki.pages import description_text, signature

MAX_TEXT_CHARS = 20000
"""Longest entity text sent to the embedding model, so it fits in the model's context."""

NAME_WEIGHT = 5.0
"""How much more a match in the entity's name counts than a match in its description (BM25)."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (path TEXT PRIMARY KEY, hash TEXT NOT NULL, text TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS bm25 USING fts5(path UNINDEXED, name, body, tokenize = 'unicode61');
CREATE TABLE IF NOT EXISTS vectors (path TEXT PRIMARY KEY, hash TEXT NOT NULL, vector BLOB NOT NULL);
"""
"""Tables: `documents` (text of each entity and its hash), `bm25` (tokenized text),
`vectors` (one float32 vector per entity) and `meta` (e.g. the model of the vectors)."""

_WORD = re.compile(r"[A-Za-z0-9]+")
"""A run of letters and digits; everything else separates words."""

_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
"""Parts of a camelCase or PascalCase word, e.g. `HTTPClient` → `HTTP`, `Client`."""


def entity_text(entity: dict) -> str:
    """Build the text that represents an entity: kind, path, signature and full description.

    Args:
        entity: Extracted entity.

    Returns:
        The text, cut at `MAX_TEXT_CHARS` characters.
    """
    text = f"{entity['kind']} {entity['path']}\n{signature(entity)}\n{description_text(entity)}"
    return text[:MAX_TEXT_CHARS]


NOT_SEARCHED = ("__all__",)
"""Entity names left out of every search: `__all__` only lists names that are entities themselves."""


def searchable(entity: dict) -> bool:
    """Whether an entity is found by the searches (see `NOT_SEARCHED`)."""
    return entity["name"] not in NOT_SEARCHED


def entity_documents(entities: dict[str, dict]) -> dict[str, tuple[str, str]]:
    """The searchable documents of the code: each entity's name and text, by path.

    Args:
        entities: Extracted entities, by path.

    Returns:
        `{path: (name, text)}`, ready for `SearchIndex.update_texts`; `NOT_SEARCHED` names left out.
    """
    return {path: (entity["name"], entity_text(entity)) for path, entity in entities.items() if searchable(entity)}


def tokenize(text: str) -> list[str]:
    """Split text into lowercase words, also splitting code identifiers.

    `get_weather` gives `get`, `weather`; `WeatherClient` gives `weather`, `client`
    and also `weatherclient`, so the whole identifier can be searched too.

    Args:
        text: Any text: code, signature or description.

    Returns:
        The words, in order, with repetitions (BM25 counts them).
    """
    words = []
    for word in _WORD.findall(text):
        parts = _CAMEL.findall(word)
        words.extend(part.lower() for part in parts)
        if len(parts) > 1:
            words.append(word.lower())
    return words


class SearchIndex:
    """BM25 and vector indexes of the entities, in `doc/sqlite/doctracker.db`.

    Args:
        path: Database file; its folder is created when the database is first opened.

    Attributes:
        path: Database file.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[tuple[sqlite3.Connection, bool]]:
        """Open the database for one operation, with `sqlite-vec` loaded when possible.

        Yields:
            The connection and whether `sqlite-vec` is available on it.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        try:
            connection.executescript(SCHEMA)
            yield connection, _load_sqlite_vec(connection)
        finally:
            connection.close()

    def count(self) -> int:
        """Number of entities with a vector in the index."""
        if not self.path.exists():
            return 0
        with self._connect() as (connection, _):
            return connection.execute("SELECT count(*) FROM vectors").fetchone()[0]

    def update_texts(self, documents: dict[str, tuple[str, str]]) -> None:
        """Bring the stored texts and the BM25 index in line with `documents`, in one transaction.

        New or changed documents are re-indexed and lose their vector (made again on
        the next semantic search); removed documents are deleted everywhere.

        Args:
            documents: Every current document, `{key: (name, text)}`: the entities and the notes.
        """
        texts = {path: text[:MAX_TEXT_CHARS] for path, (_, text) in documents.items()}
        hashes = {path: _hash(text) for path, text in texts.items()}
        with self._connect() as (connection, _):
            stored = dict(connection.execute("SELECT path, hash FROM documents"))
            changed = [path for path in texts if stored.get(path) != hashes[path]]
            removed = [path for path in stored if path not in texts]
            if not changed and not removed:
                return
            with connection:
                for path in removed + changed:
                    connection.execute("DELETE FROM documents WHERE path = ?", (path,))
                    connection.execute("DELETE FROM bm25 WHERE path = ?", (path,))
                    connection.execute("DELETE FROM vectors WHERE path = ?", (path,))
                for path in changed:
                    connection.execute(
                        "INSERT INTO documents (path, hash, text) VALUES (?, ?, ?)", (path, hashes[path], texts[path])
                    )
                    connection.execute(
                        "INSERT INTO bm25 (path, name, body) VALUES (?, ?, ?)",
                        (path, " ".join(tokenize(documents[path][0])), " ".join(tokenize(texts[path]))),
                    )

    def search_bm25(self, query: str, limit: int = -1) -> list[tuple[str, float]]:
        """Rank entities by BM25: shared words, weighted by how rare they are.

        Matches in the name count `NAME_WEIGHT` times more than in the description.

        Args:
            query: Words to look for, in any order.
            limit: Maximum number of results; -1 (the default) returns every match.

        Returns:
            `(path, score)` pairs, best first (higher score is better); empty without searchable words.
        """
        words = sorted(set(tokenize(query)))
        if not words:
            return []
        expression = " OR ".join(f'"{word}"' for word in words)
        with self._connect() as (connection, _):
            rows = connection.execute(
                f"SELECT path, bm25(bm25, 0, {NAME_WEIGHT}, 1.0) AS rank FROM bm25 WHERE bm25 MATCH ? "
                "ORDER BY rank LIMIT ?",
                (expression, limit),
            ).fetchall()
        return [(path, -rank) for path, rank in rows]

    async def update_vectors(
        self,
        model_id: str,
        embed: Callable[[list[str]], Awaitable[np.ndarray]],
        on_progress: Callable[[int, int], None],
    ) -> None:
        """Embed the entities that have no vector yet; a different model rebuilds every vector.

        Call `update_texts` first. The new vectors are written in one transaction.

        Args:
            model_id: Model the vectors must come from.
            embed: Turns a list of texts into normalized vectors, one row per text.
            on_progress: Called with the vectors done and the total when the update finishes.
        """
        with self._connect() as (connection, _):
            stored_model = connection.execute("SELECT value FROM meta WHERE key = 'model'").fetchone()
            if stored_model is None or stored_model[0] != model_id:
                with connection:
                    connection.execute("DELETE FROM vectors")
                    connection.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('model', ?)", (model_id,))
            missing = connection.execute(
                "SELECT path, hash, text FROM documents WHERE path NOT IN (SELECT path FROM vectors)"
            ).fetchall()
        if not missing:
            return
        vectors = await embed([text for _, _, text in missing])
        with self._connect() as (connection, _):
            with connection:
                connection.executemany(
                    "INSERT OR REPLACE INTO vectors (path, hash, vector) VALUES (?, ?, ?)",
                    [(path, digest, vectors[row].astype(np.float32).tobytes()) for row, (path, digest, _) in enumerate(missing)],
                )
            total = connection.execute("SELECT count(*) FROM documents").fetchone()[0]
        on_progress(total, total)

    def search_vectors(self, query: np.ndarray, limit: int) -> list[tuple[str, float]]:
        """Rank entities by cosine similarity between their vector and `query`.

        Runs inside SQLite with `sqlite-vec`; without it, the vectors are read and compared with numpy.

        Args:
            query: Normalized vector of the query, from the same model as the stored vectors.
            limit: Maximum number of results.

        Returns:
            `(path, similarity)` pairs, best first (1 means identical direction).
        """
        blob = query.astype(np.float32).tobytes()
        with self._connect() as (connection, has_vec):
            if has_vec:
                rows = connection.execute(
                    "SELECT path, vec_distance_cosine(vector, ?) AS distance FROM vectors ORDER BY distance LIMIT ?",
                    (blob, limit),
                ).fetchall()
                return [(path, 1.0 - distance) for path, distance in rows]
            rows = connection.execute("SELECT path, vector FROM vectors").fetchall()
        if not rows:
            return []
        matrix = np.vstack([np.frombuffer(vector, dtype=np.float32) for _, vector in rows])
        scores = matrix @ query.astype(np.float32)
        limit = min(limit, len(scores))
        best = np.argpartition(-scores, limit - 1)[:limit]
        best = best[np.argsort(-scores[best])]
        return [(rows[row][0], float(scores[row])) for row in best]


def _load_sqlite_vec(connection: sqlite3.Connection) -> bool:
    """Load the `sqlite-vec` extension on a connection.

    Args:
        connection: Open connection.

    Returns:
        True when loaded; False when this Python cannot load SQLite extensions or the package is missing.
    """
    try:
        import sqlite_vec

        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        return True
    except (AttributeError, ImportError, sqlite3.Error, OSError):
        return False


def _hash(text: str) -> str:
    """Fingerprint of a text, to detect changes.

    Args:
        text: Entity text.

    Returns:
        SHA-256 in hexadecimal.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
