"""The databases of the documented project: the connections it declares or the user enters, opened read only.

`discovery` finds what the project's files declare (read as text, never run); `store` keeps the
connections, the user's consent and the passwords (encrypted, out of git); `readonly` opens a
connection that can only read and tests it; `collect` reads a database's catalog through it (by
itself, while the server runs, and when asked), and `catalog` keeps what was last read.
"""

from doctracker.databases.catalog import CatalogStore
from doctracker.databases.collect import collect, collect_connection, keep_collected
from doctracker.databases.discovery import Connection, discover
from doctracker.databases.readonly import ReadOnlyViolation, is_read_only, test_connection
from doctracker.databases.store import ConnectionStore, Locked

__all__ = ["CatalogStore", "Connection", "ConnectionStore", "collect", "collect_connection", "keep_collected", "Locked", "ReadOnlyViolation", "discover", "is_read_only", "test_connection"]
