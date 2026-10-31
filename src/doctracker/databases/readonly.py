"""Open a database so that it can only be read, and test a connection that way.

Several layers keep every operation a read: the session itself is read only where the database
allows it (Postgres and MySQL read-only sessions, SQLite opened read only and `query_only`),
every transaction is rolled back, and each statement is checked before it is sent: anything that
is not a query (insert, update, delete, DDL, `SELECT ... INTO`, a data-changing `WITH`...) is
aborted with `ReadOnlyViolation`. Connections run in a process apart from the server.

A connection may go through an SSH tunnel (paramiko; through a jump host too, and with what
`~/.ssh/config` says when asked) and sign in to an AWS RDS database with an IAM token instead of a
password (boto3, the optional extra `doctracker[aws]`). Google Cloud SQL and Azure Entra ID are not
supported: their libraries bring a package under MPL-2.0 (certifi), against the licence rule.
"""

import asyncio
import contextlib
import logging
import multiprocessing
import re
import select
import socket
import sqlite3
import ssl
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import paramiko

import sqlglot
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import URL, Engine
from sqlglot import exp

from doctracker.databases.discovery import DEFAULT_PORTS

logging.getLogger("sqlglot").setLevel(logging.ERROR)  # its notes on statements it keeps as raw commands

DRIVERS = {"postgresql": "postgresql+pg8000", "mysql": "mysql+pymysql", "mssql": "mssql+pytds",
           "oracle": "oracle+oracledb"}
"""The SQLAlchemy driver doctracker uses for each kind of database (SQLite uses Python's own)."""

DIALECTS = {"postgresql": "postgres", "mysql": "mysql", "mssql": "tsql", "sqlite": "sqlite", "oracle": "oracle"}
"""sqlglot's name for each kind's SQL, used to check the statements."""

TIMEOUT_SECONDS = 15
"""Longest wait for a server to answer, when connecting and for the whole test."""

_WRITES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter, exp.Into,
           exp.TruncateTable, exp.Grant, exp.Command)
"""What a statement may not hold anywhere inside it, even within a query (`WITH x AS (DELETE ...)`)."""

_READ_COMMANDS = ("SHOW", "EXPLAIN", "DESCRIBE", "DESC")
"""Statements sqlglot keeps as raw commands that only read."""

_READ_PRAGMAS = {"table_info", "table_xinfo", "table_list", "index_list", "index_info", "index_xinfo",
                 "foreign_key_list", "database_list", "collation_list", "function_list", "pragma_list"}
"""SQLite pragmas that take an argument and only read (a pragma given a value otherwise changes a setting)."""

_PRAGMA = re.compile(r"\bPRAGMA\s+(?:[\w\"\[\]`]+\.)?[\"`\[]?(?P<name>\w+)[\"`\]]?\s*(?P<sets>[=(])?", re.IGNORECASE)
"""A SQLite pragma: its name, and `=` or `(` when it is given a value."""

_PARAMETER = re.compile(r"%\(\w+\)s")
"""A named parameter marker (`%(name)s`, used by python-tds), which sqlglot cannot read."""

_SESSION = {"postgresql": "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY",
            "mysql": "SET SESSION TRANSACTION READ ONLY", "sqlite": "PRAGMA query_only = 1"}
"""What makes a new session read only, per kind; sent by doctracker itself, before any other statement."""

_CHECKS = {"postgresql": ("SELECT version()", "SHOW transaction_read_only"),
           "mysql": ("SELECT version()", "SELECT @@session.transaction_read_only"),
           "mssql": ("SELECT @@version", "SELECT IS_ROLEMEMBER('db_owner') + IS_ROLEMEMBER('db_datawriter') + "
                                         "ISNULL(HAS_PERMS_BY_NAME(DB_NAME(), 'DATABASE', 'CREATE TABLE'), 0)"),
           "sqlite": ("SELECT sqlite_version()", "PRAGMA query_only"),
           "oracle": ("SELECT banner FROM v$version WHERE ROWNUM = 1", None)}
"""Per kind: the query reading the server's version, and the one telling whether the session can write."""

WRITE_PROBE = "CREATE TABLE doctracker_write_check (x INT)"
"""The write the test tries: it must be aborted before reaching the database."""


class ReadOnlyViolation(Exception):
    """A statement that is not a read was about to be sent; it was aborted."""


def is_read_only(sql: str, kind: str) -> bool:
    """Tell whether a statement only reads.

    Args:
        sql: One or more SQL statements.
        kind: One of the kinds of `DIALECTS`, for the SQL to be read in its dialect.

    Returns:
        True when every statement is a query (`SELECT`, `WITH ... SELECT`, set operations) or a
        `SHOW` / `EXPLAIN` / `DESCRIBE` / reading `PRAGMA`, and none holds a write anywhere inside;
        False for anything else, and for SQL that cannot be read.
    """
    for pragma in _PRAGMA.finditer(sql):  # read from the text: sqlglot writes `name(value)` as `name = value`
        if pragma["sets"] == "=" or (pragma["sets"] == "(" and pragma["name"].lower() not in _READ_PRAGMAS):
            return False
    try:
        statements = [s for s in sqlglot.parse(_PARAMETER.sub("NULL", sql), read=DIALECTS.get(kind)) if s is not None]
    except sqlglot.errors.SqlglotError:
        return False
    if not statements:
        return False
    for statement in statements:
        if isinstance(statement, exp.Command):
            if str(statement.this).upper() not in _READ_COMMANDS:
                return False
        elif not isinstance(statement, (exp.Query, exp.Show, exp.Describe, exp.Pragma)) or statement.find(*_WRITES):
            return False
    return True


SIGN_INS = {"password": "Password", "aws-iam": "AWS RDS IAM"}
"""How doctracker signs in: a password (or none), or an AWS RDS IAM token."""


class _Remembered(paramiko.MissingHostKeyPolicy):
    """Accept an SSH server's key not in `known_hosts` for this connection only, and note it, so the
    test can tell the user which key was accepted (nothing is written to `known_hosts`)."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    def missing_host_key(self, client, hostname, key) -> None:
        self.seen.append(f"{hostname} {key.get_name()} SHA256:{key.fingerprint.split(':', 1)[-1]}"
                         if hasattr(key, "fingerprint") else f"{hostname} {key.get_name()}")


class Tunnel:
    """An SSH tunnel to a database: a port on 127.0.0.1 forwarded, through the SSH server (and a jump
    host, if any), to the database's host and port as the SSH server sees them.

    Attributes:
        local_port: The port on 127.0.0.1 to connect to, once opened.
        host_keys: Keys of SSH servers that were not in `known_hosts`, accepted for this tunnel only.
    """

    def __init__(self, ssh: dict, target_host: str, target_port: int) -> None:
        """Prepare a tunnel; nothing connects until `open`.

        Args:
            ssh: `host`, `port`, `user`, `key` (a private key file), `password` (the password, or the
                key's passphrase when there is a key), `jump` (`user@host:port`) and `config` (True to
                fill what is missing from `~/.ssh/config`), every value resolved.
            target_host: The database's host, as the SSH server reaches it.
            target_port: The database's port.
        """
        self.ssh, self.target = ssh, (target_host, target_port)
        self.local_port = 0
        self.host_keys: list[str] = []
        self._clients: list[paramiko.SSHClient] = []
        self._server: socket.socket | None = None
        self._stop = threading.Event()

    def _settings(self, host: str, port: str | int, user: str) -> dict:
        """Host, port and user to reach `host`, completed by `~/.ssh/config` when asked."""
        found = {"hostname": host, "port": int(port or 22), "user": user, "identityfile": [], "proxyjump": ""}
        config_file = Path.home() / ".ssh" / "config"
        if self.ssh.get("config") and config_file.is_file():
            entry = paramiko.SSHConfig.from_path(str(config_file)).lookup(host)
            found.update(hostname=entry.get("hostname", host), port=int(port or entry.get("port", 22)),
                         user=user or entry.get("user", ""), identityfile=entry.get("identityfile", []),
                         proxyjump=entry.get("proxyjump", ""))
        return found

    def _connect(self, host: str, port: str | int, user: str, key: str, password: str, sock=None) -> paramiko.SSHClient:
        """Log in to one SSH server (through `sock`, a channel of the jump host, when given)."""
        policy = _Remembered()
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(policy)
        found = self._settings(host, port, user)
        key = key or (found["identityfile"][0] if found["identityfile"] else "")
        client.connect(found["hostname"], found["port"], username=found["user"] or None,
                       key_filename=str(Path(key).expanduser()) if key else None,
                       password=None if key else (password or None), passphrase=(password or None) if key else None,
                       sock=sock, timeout=TIMEOUT_SECONDS, banner_timeout=TIMEOUT_SECONDS, auth_timeout=TIMEOUT_SECONDS,
                       allow_agent=not key, look_for_keys=not key)
        self.host_keys += policy.seen
        self._clients.append(client)
        return client

    def open(self) -> int:
        """Log in (through the jump host first, if any) and start forwarding.

        Returns:
            The local port to connect to.
        """
        ssh = self.ssh
        jump = ssh.get("jump") or self._settings(ssh["host"], ssh.get("port"), ssh.get("user", ""))["proxyjump"]
        sock = None
        if jump:
            jump_user, _, jump_place = jump.rpartition("@")
            jump_host, _, jump_port = jump_place.partition(":")
            first = self._connect(jump_host, jump_port or 22, jump_user, ssh.get("key", ""), ssh.get("password", ""))
            found = self._settings(ssh["host"], ssh.get("port"), ssh.get("user", ""))
            sock = first.get_transport().open_channel("direct-tcpip", (found["hostname"], found["port"]), ("127.0.0.1", 0))
        client = self._connect(ssh["host"], ssh.get("port"), ssh.get("user", ""), ssh.get("key", ""), ssh.get("password", ""), sock)
        self._transport = client.get_transport()
        self._server = socket.create_server(("127.0.0.1", 0))
        self.local_port = self._server.getsockname()[1]
        threading.Thread(target=self._forward, daemon=True).start()
        return self.local_port

    def _forward(self) -> None:
        """Carry the bytes between each local connection and its channel through the SSH server
        (one loop, waiting on every socket at once)."""
        pairs: dict = {}
        while not self._stop.is_set():
            ready, _, _ = select.select([self._server, *pairs], [], [], 0.2)
            for end in ready:
                if end is self._server:
                    local, address = self._server.accept()
                    channel = self._transport.open_channel("direct-tcpip", self.target, address)
                    pairs[local], pairs[channel] = channel, local
                    continue
                data = end.recv(65536)
                other = pairs.get(end)
                if not data or other is None:
                    for side in (end, other):
                        pairs.pop(side, None)
                        if side is not None:
                            side.close()
                    continue
                other.sendall(data)

    def close(self) -> None:
        """Stop forwarding and log out."""
        self._stop.set()
        if self._server is not None:
            self._server.close()
        for client in reversed(self._clients):
            client.close()


def _cloud(spec: dict) -> str | None:
    """The password a cloud sign-in gives: an AWS RDS IAM token, made for this host, port and user.

    Returns:
        The token, or None for a plain password.

    Raises:
        ValueError: When boto3, the extra `doctracker[aws]`, is not installed.
    """
    if spec.get("sign_in") != "aws-iam":
        return None
    try:
        import boto3
    except ImportError as missing:
        raise ValueError("AWS RDS IAM needs doctracker's extra: pip install doctracker[aws]") from missing
    client = boto3.client("rds", region_name=spec.get("sign_in_option") or None)
    return client.generate_db_auth_token(spec["host"], int(spec.get("port") or 0), spec.get("user", ""))


def open_engine(spec: dict) -> Engine:
    """Create an engine that can only read.

    Args:
        spec: `kind`, `host`, `port`, `database`, `user` and `password`, every value resolved (no
            variable references); `sign_in` and `sign_in_option` (the AWS region) for an IAM token. For SQLite,
            `host` is the file's path.

    Returns:
        The engine; every statement it sends is checked first (`ReadOnlyViolation` when not a read).
    """
    kind = spec["kind"]
    if kind == "sqlite":
        path = spec["host"]
        engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(f"file:{path}?mode=ro", uri=True,
                                                                             timeout=TIMEOUT_SECONDS))
    else:
        connect_args = {"postgresql": {"timeout": TIMEOUT_SECONDS}, "mysql": {"connect_timeout": TIMEOUT_SECONDS},
                        "mssql": {"login_timeout": TIMEOUT_SECONDS, "timeout": TIMEOUT_SECONDS}}.get(kind, {})
        token = _cloud(spec)
        if token:  # an IAM token travels only over TLS
            connect_args[{"postgresql": "ssl_context", "mysql": "ssl"}.get(kind, "ssl")] = ssl.create_default_context()
        url = URL.create(DRIVERS[kind], username=spec.get("user") or None, password=token or spec.get("password") or None,
                         host=spec.get("host") or None, port=int(spec["port"]) if str(spec.get("port", "")).isdigit() else None,
                         database=spec.get("database") or None)
        engine = create_engine(url, connect_args=connect_args, pool_pre_ping=False)
    session = _SESSION.get(kind)

    @event.listens_for(engine, "connect")
    def read_only_session(dbapi_connection, _record):
        # doctracker's own statement, sent straight to the driver before any other.
        # Committed at once: a setting made inside a transaction is undone when that transaction is rolled back.
        if session:
            cursor = dbapi_connection.cursor()
            cursor.execute(session)
            cursor.close()
            dbapi_connection.commit()

    @event.listens_for(engine, "before_cursor_execute")
    def only_reads(_connection, _cursor, statement, _parameters, _context, _many):
        if not is_read_only(statement, kind):
            raise ReadOnlyViolation(f"Aborted, not a read: {statement.strip()[:120]}")

    return engine


@contextlib.contextmanager
def opened(spec: dict) -> Iterator[tuple[Engine, Tunnel | None]]:
    """Open a read-only engine, through its SSH tunnel when the connection has one; close both after.

    Args:
        spec: The resolved connection (see `open_engine`), with `ssh` when it goes through a tunnel.

    Yields:
        The engine, and the tunnel (None without one).
    """
    tunnel = None
    if spec.get("ssh"):
        tunnel = Tunnel(spec["ssh"], spec.get("host") or "localhost", int(spec.get("port") or DEFAULT_PORTS[spec["kind"]]))
        try:
            spec = {**spec, "host": "127.0.0.1", "port": str(tunnel.open())}
        except BaseException:
            tunnel.close()
            raise
    engine = open_engine(spec)
    try:
        yield engine, tunnel
    finally:
        engine.dispose()
        if tunnel is not None:
            tunnel.close()


def test_connection(spec: dict) -> dict:
    """Connect, read the server's version, see whether the session can write, and try a write.

    Runs in a process apart (see `run_test`). Nothing is changed: the write is aborted before it is
    sent, and the transaction is rolled back.

    Args:
        spec: The resolved connection (see `open_engine`).

    Returns:
        `ok`; `version`; `read_only_session` (True, False, or None when the database has no such
        session, as SQL Server); `can_write` (SQL Server: whether the user has write permissions);
        `write_refused` (the probe write aborted); `host_keys` (SSH servers' keys not in
        `known_hosts`, accepted for this test only); `error` when it failed; `seconds` taken;
        `tested_at`, when it ran (ISO 8601, UTC).
    """
    started = time.monotonic()
    result = {"ok": False, "version": "", "read_only_session": None, "can_write": None, "write_refused": False,
              "host_keys": [], "error": "", "tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        version_query, write_query = _CHECKS[spec["kind"]]
        with opened(spec) as (engine, tunnel), engine.connect() as connection:
            result["host_keys"] = tunnel.host_keys if tunnel else []
            with connection.begin() as transaction:
                result["version"] = str(connection.execute(text(version_query)).scalar() or "").splitlines()[0][:160]
                if write_query:
                    value = connection.execute(text(write_query)).scalar()
                    if spec["kind"] == "mssql":
                        result["can_write"] = bool(value)
                    else:
                        result["read_only_session"] = str(value).lower() in ("on", "1", "true")
                try:
                    connection.execute(text(WRITE_PROBE))
                except ReadOnlyViolation:
                    result["write_refused"] = True
                transaction.rollback()
        result["ok"] = result["write_refused"] and result["read_only_session"] is not False
        if not result["ok"] and not result["error"]:
            result["error"] = "The session is not read only." if result["read_only_session"] is False else "The write was not aborted."
    except Exception as failed:  # any driver's or SSH error is reported to the user as it is
        result["error"] = _message(failed)
    result["seconds"] = round(time.monotonic() - started, 2)
    return result


def _message(failed: Exception) -> str:
    """The driver's own words for an error (pg8000 gives a dict whose `M` is the message)."""
    original = getattr(failed, "orig", None) or failed
    detail = original.args[0] if original.args else original
    text_ = detail.get("M", str(detail)) if isinstance(detail, dict) else str(detail if isinstance(detail, str) else original)
    return f"{type(original).__name__}: {text_}".splitlines()[0][:300]


async def run_test(spec: dict) -> dict:
    """Run `test_connection` in a process of its own, giving up after `TIMEOUT_SECONDS` and a margin.

    Args:
        spec: The resolved connection (see `open_engine`).

    Returns:
        What `test_connection` returns, or a failure saying the server did not answer in time.
    """
    loop = asyncio.get_running_loop()
    with ProcessPoolExecutor(max_workers=1, mp_context=multiprocessing.get_context("spawn")) as pool:
        try:
            return await asyncio.wait_for(loop.run_in_executor(pool, test_connection, spec), TIMEOUT_SECONDS * 2)
        except TimeoutError:
            return {"ok": False, "version": "", "read_only_session": None, "can_write": None, "write_refused": False,
                    "host_keys": [], "error": f"No answer in {TIMEOUT_SECONDS * 2} seconds.", "seconds": TIMEOUT_SECONDS * 2,
                    "tested_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
