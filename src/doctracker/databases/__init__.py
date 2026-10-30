"""The databases of the documented project: the connections it declares or the user enters, opened read only.

`discovery` finds what the project's files declare (read as text, never run); `store` keeps the
connections, the user's consent and the passwords (encrypted, out of git); `readonly` opens a
connection that can only read and tests it.
"""

from doctracker.databases.discovery import Connection, discover
from doctracker.databases.readonly import ReadOnlyViolation, is_read_only, test_connection
from doctracker.databases.store import ConnectionStore, Locked

__all__ = ["Connection", "ConnectionStore", "Locked", "ReadOnlyViolation", "discover", "is_read_only", "test_connection"]
