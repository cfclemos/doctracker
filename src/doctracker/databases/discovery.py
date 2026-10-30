"""Find the database connections the project declares, reading its files as text and never running them.

Sources: `.env` files (a URL in a variable, or `POSTGRES_*`, `PG*`, `MYSQL_*`, `MSSQL_*` variables),
`alembic.ini`, Django's `DATABASES` (read with `ast`), Compose files (database images and their
environment), Prisma's `datasource`, `create_engine("...")` in Python code, and SQLite files. A
password is never shown: what the user sees is the variable holding it (`${PGPASSWORD}`) or `•••`
when it is written in the file; its value is read only when the connection is opened.
"""

import ast
import hashlib
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from doctracker.config import _skipped, _walk

KINDS = {"postgresql": "PostgreSQL", "mysql": "MySQL / MariaDB", "mssql": "SQL Server", "sqlite": "SQLite",
         "oracle": "Oracle"}
"""The kinds of database doctracker connects to, with the name shown for each."""

DEFAULT_PORTS = {"postgresql": "5432", "mysql": "3306", "mssql": "1433", "oracle": "1521"}
"""Port each kind listens on when none is given."""

HIDDEN = "•••"
"""What is shown for a password written in a file."""

_SCHEMES = {"postgres": "postgresql", "postgresql": "postgresql", "pgsql": "postgresql", "mysql": "mysql",
            "mariadb": "mysql", "mssql": "mssql", "sqlserver": "mssql", "sqlite": "sqlite", "oracle": "oracle"}
"""URL schemes (before any `+driver`) and the kind each means."""

_URL = re.compile(r"^(?P<scheme>[A-Za-z][\w.+-]*)://(?:(?P<user>[^:@/]*)(?::(?P<password>[^@]*))?@)?"
                  r"(?P<host>\[[^\]]*\]|[^:/?]*)(?::(?P<port>[^/?]*))?(?:/(?P<database>[^?]*))?")
"""A database URL, `scheme[+driver]://user:password@host:port/database`; parts may be `${VAR}`."""

_REFERENCE = re.compile(r"\$\{(\w+)(?::?-([^}]*))?\}|\$(\w+)")
"""A reference to an environment variable: `${VAR}`, `${VAR:-default}` or `$VAR`."""

_ENV_PREFIXES = {"POSTGRES_": "postgresql", "PG": "postgresql", "MYSQL_": "mysql", "MARIADB_": "mysql",
                 "MSSQL_": "mssql", "ORACLE_": "oracle"}
"""Prefixes of the variables that describe one database in a `.env` file, and its kind."""

_ENV_FIELDS = (("PASSWORD", "password"), ("USER", "user"), ("HOST", "host"), ("PORT", "port"),
               ("DATABASE", "database"), ("DB", "database"), ("NAME", "database"))
"""Endings of those variables and the field each gives (`POSTGRES_ADMIN_USER` gives the user)."""

_IMAGES = (("postgis", "postgresql"), ("postgres", "postgresql"), ("mariadb", "mysql"), ("mysql", "mysql"),
           ("mssql", "mssql"), ("sqlserver", "mssql"), ("oracle", "oracle"))
"""Parts of a container image's name and the kind of database it runs."""

_TEMPLATES = (".example", ".sample", ".template", ".dist")
"""Endings of files that only show how to write the real one (`.env.example`); not read."""

_ENGINE_CALL = re.compile(r"create_(?:async_)?engine\(\s*[rRbBuU]?[\"']([^\"']+://[^\"']*)[\"']")
"""`create_engine("url")` (or `create_async_engine`) with the URL written in the code."""


@dataclass
class Connection:
    """A database connection: declared by a project file or entered by the user.

    Text fields may hold references to environment variables (`${PGPORT:-5432}`), resolved only when
    the connection is opened.

    Attributes:
        id: Stable identifier: the same declaration always gets the same one.
        name: What the user sees as its title.
        kind: One of `KINDS`.
        host: Server name or address (a file path for SQLite).
        port: Port, as written.
        database: Database name.
        user: User name.
        password: `${VAR}` when a variable holds it, `HIDDEN` when written in the file, `""` when none;
            never the value itself.
        url_variable: Variable holding the whole URL (`DATABASE_URL`), when that is how it is declared.
        source: What declared it (`.env`, `alembic.ini`, `Django`, `Compose`, `Prisma`, `create_engine`,
            `SQLite file`) or `entered`.
        origin: `file:line` where it is declared; empty when entered.
        folder: Folder of the declaring file, relative to the project, where its `.env` is looked for.
        ssh_host: SSH server the connection goes through; empty for none.
        ssh_port: Its port (22 when empty).
        ssh_user: User on the SSH server.
        ssh_key: Private key file for the SSH server.
        ssh_password: Like `password`: the SSH password, or the key's passphrase when there is a key.
        ssh_jump: Jump host, `user@host:port`, reached first.
        ssh_config: Whether what is missing comes from `~/.ssh/config`.
        sign_in: How to sign in: `password`, or `aws-iam` (an AWS RDS IAM token).
        sign_in_option: What that sign-in needs: the AWS region.
    """

    id: str
    name: str
    kind: str
    host: str = ""
    port: str = ""
    database: str = ""
    user: str = ""
    password: str = ""
    url_variable: str = ""
    source: str = "entered"
    origin: str = ""
    folder: str = ""
    ssh_host: str = ""
    ssh_port: str = ""
    ssh_user: str = ""
    ssh_key: str = ""
    ssh_password: str = ""
    ssh_jump: str = ""
    ssh_config: bool = False
    sign_in: str = "password"
    sign_in_option: str = ""
    secret: str = field(default="", repr=False)
    """The password itself when written in the file: kept in memory only, never shown or stored."""

    def public(self) -> dict:
        """Give the connection as a plain dict without its secret, for the wiki and the MCP tools."""
        data = asdict(self)
        data.pop("secret")
        data["kind_name"] = KINDS.get(self.kind, self.kind)
        return data


def discover(project_root: Path) -> list[Connection]:
    """Find every connection the project's files declare.

    Args:
        project_root: Root of the documented project.

    Returns:
        The connections found, each once, in the order of their files.
    """
    found: dict[str, Connection] = {}
    for folder, _, names in _walk(project_root):
        for name in sorted(names):
            path = Path(folder, name)
            file = path.relative_to(project_root).as_posix()
            if _skipped(file) or name.endswith(_TEMPLATES):
                continue
            for connection in _read(path, file):
                found.setdefault(connection.id, connection)
    return list(found.values())


def _read(path: Path, file: str) -> list[Connection]:
    """The connections one file declares, by the kind of file it is."""
    name = path.name
    try:
        if name.startswith(".env"):
            return _from_env(path.read_text(encoding="utf-8", errors="replace"), file)
        if name == "alembic.ini":
            return _from_alembic(path.read_text(encoding="utf-8", errors="replace"), file)
        if re.fullmatch(r"(docker-)?compose[\w.-]*\.ya?ml", name):
            return _from_compose(path.read_text(encoding="utf-8", errors="replace"), file)
        if name.endswith(".prisma"):
            return _from_prisma(path.read_text(encoding="utf-8", errors="replace"), file)
        if name.endswith(".py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            return _from_django(text, file) + _from_engine_calls(text, file)
        if name.endswith((".sqlite", ".sqlite3", ".db")) and _is_sqlite(path):
            return [_connection("SQLite file", file, 1, "sqlite", host=file)]
    except OSError:
        pass
    return []


def _connection(source: str, file: str, line: int, kind: str, name: str = "", **fields: str) -> Connection:
    """Build a declared connection, its id taken from where and what it declares."""
    if fields.get("password") and not fields["password"].startswith("${"):
        fields["secret"], fields["password"] = fields["password"], HIDDEN
    key = "|".join([file, kind] + [fields.get(part, "") for part in ("host", "port", "database", "user", "url_variable")])
    identifier = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    title = name or fields.get("database") or Path(fields.get("host", "")).name or KINDS.get(kind, kind)
    return Connection(id=identifier, name=title, kind=kind, source=source, origin=f"{file}:{line}",
                      folder=Path(file).parent.as_posix(), **fields)


def _as_reference(value: str) -> str:
    """A value that is one variable reference (`${X:-a}`, `$X`) becomes `${X}`; any other is kept."""
    match = _REFERENCE.fullmatch(value.strip())
    return f"${{{match.group(1) or match.group(3)}}}" if match else value


def parse_url(url: str) -> dict[str, str] | None:
    """Split a database URL into kind, host, port, database, user and password.

    Args:
        url: `scheme[+driver]://user:password@host:port/database`; parts may be variable references.

    Returns:
        The parts (empty strings for those missing), or None when it is not a database URL.
    """
    match = _URL.match(url.strip())
    if not match:
        return None
    kind = _SCHEMES.get(match["scheme"].split("+")[0].lower())
    if not kind:
        return None
    parts = {key: match[key] or "" for key in ("host", "port", "database", "user", "password")}
    if kind == "sqlite":  # sqlite:///relative/path or sqlite:////absolute/path
        parts = {"host": url.split("://", 1)[1].lstrip("/") if "://" in url else "", "port": "", "database": "",
                 "user": "", "password": ""}
        if url.split("://", 1)[1].startswith("//"):
            parts["host"] = "/" + parts["host"]
    return {"kind": kind, **parts}


def _from_url(url: str, source: str, file: str, line: int, name: str = "", url_variable: str = "") -> list[Connection]:
    """One connection from a URL; with `url_variable`, its password lives in that variable."""
    parts = parse_url(url)
    if not parts or "driver://" in url or (parts["kind"] == "sqlite" and not parts["host"]):
        return []  # not a URL, a placeholder (alembic's template), or an SQLite database in memory
    kind = parts.pop("kind")
    if url_variable:
        parts["password"] = f"${{{url_variable}}}" if parts["password"] else ""
    else:
        parts["password"] = _as_reference(parts["password"])
    return [_connection(source, file, line, kind, name, url_variable=url_variable, **parts)]


def _env_values(text: str) -> list[tuple[int, str, str]]:
    """The `KEY=value` lines of a `.env` file, with their line numbers, quotes taken off."""
    values = []
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values.append((number, key.strip(), value))
    return values


def _from_env(text: str, file: str) -> list[Connection]:
    """Connections in a `.env` file: a URL in a variable, or a group of variables sharing a prefix."""
    found, groups = [], {}
    for number, key, value in _env_values(text):
        if "://" in value:
            found += _from_url(value, ".env", file, number, key, url_variable=key)
            continue
        prefix = next((p for p in sorted(_ENV_PREFIXES, key=len, reverse=True) if key.startswith(p)), None)
        ending = next((f for end, f in _ENV_FIELDS if key.endswith(end)), None)
        if prefix and ending:
            group = groups.setdefault(prefix, {"line": number})
            group.setdefault(ending, f"${{{key}}}" if ending == "password" else value)
            if ending == "password" and ("ROOT" in key or "_SA_" in key):  # MYSQL_ROOT_PASSWORD, MSSQL_SA_PASSWORD
                group.setdefault("user", "root" if "ROOT" in key else "sa")
    for prefix, group in groups.items():
        if "host" in group or "user" in group:  # a password alone (PGPASSWORD) does not say where to connect
            line = group.pop("line")
            group.setdefault("host", "localhost")
            found.append(_connection(".env", file, line, _ENV_PREFIXES[prefix], prefix.rstrip("_"), **group))
    return found


def _from_alembic(text: str, file: str) -> list[Connection]:
    """The `sqlalchemy.url` of an `alembic.ini` (interpolated values, `%(...)s`, are left out)."""
    for number, line in enumerate(text.splitlines(), 1):
        key, _, value = line.partition("=")
        if key.strip() == "sqlalchemy.url" and value.strip() and "%(" not in value:
            return _from_url(value.strip(), "alembic.ini", file, number, "alembic")
    return []


def _from_engine_calls(text: str, file: str) -> list[Connection]:
    """`create_engine("url")` calls with the URL written in the code."""
    found = []
    for match in _ENGINE_CALL.finditer(text):
        found += _from_url(match[1], "create_engine", file, text.count("\n", 0, match.start()) + 1)
    return found


def _django_value(node: ast.AST) -> str:
    """A value of a Django `DATABASES` entry: a literal, or `${VAR}` for `os.environ[...]`, `os.getenv(...)`,
    `os.environ.get(...)` and `env(...)`; anything else (an expression) gives an empty string."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int)):
        return str(node.value)
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return f"${{{node.slice.value}}}"
    if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
        return f"${{{node.args[0].value}}}"
    return ""


def _from_django(text: str, file: str) -> list[Connection]:
    """The entries of a Django `DATABASES = {...}`, read from the code without importing it."""
    if "DATABASES" not in text:
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DATABASES" for t in node.targets)
                and isinstance(node.value, ast.Dict)):
            continue
        for alias, entry in zip(node.value.keys, node.value.values):
            if not isinstance(entry, ast.Dict):
                continue
            values = {k.value: _django_value(v) for k, v in zip(entry.keys, entry.values) if isinstance(k, ast.Constant)}
            kind = next((k for part, k in (("postgis", "postgresql"), ("postgresql", "postgresql"), ("mysql", "mysql"),
                                            ("sqlite3", "sqlite"), ("oracle", "oracle"), ("mssql", "mssql"))
                         if part in values.get("ENGINE", "")), None)
            if not kind or (kind == "sqlite" and not values.get("NAME")):
                continue
            fields = ({"host": values["NAME"]} if kind == "sqlite" else
                      {"host": values.get("HOST") or "localhost", "port": values.get("PORT", ""),
                       "database": values.get("NAME", ""), "user": values.get("USER", ""),
                       "password": values.get("PASSWORD", "")})
            name = alias.value if isinstance(alias, ast.Constant) else "Django"
            found.append(_connection("Django", file, node.lineno, kind, f"Django {name}", **fields))
    return found


def _from_prisma(text: str, file: str) -> list[Connection]:
    """Prisma's `datasource`: its provider, and its `url` written or taken from a variable."""
    provider = re.search(r'provider\s*=\s*"(\w+)"', text)
    url = re.search(r'\burl\s*=\s*(?:env\("(\w+)"\)|"([^"]+)")', text)
    if not provider or not url or "datasource" not in text:
        return []
    line = text.count("\n", 0, url.start()) + 1
    if url[2]:
        return _from_url(url[2], "Prisma", file, line, "Prisma")
    kind = {"postgresql": "postgresql", "mysql": "mysql", "sqlserver": "mssql", "sqlite": "sqlite"}.get(provider[1])
    return [_connection("Prisma", file, line, kind, f"Prisma ({url[1]})", url_variable=url[1], password=f"${{{url[1]}}}")] if kind else []


def _from_compose(text: str, file: str) -> list[Connection]:
    """Database services of a Compose file: their image, published port and environment.

    The file is read line by line (no YAML parser): a service starts at the first indentation under
    `services:`; `image:`, `environment:` (map or list) and `ports:` are read inside it.
    """
    services, current, block, indent = [], None, "", None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #")[0].rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        depth = len(line) - len(line.lstrip())
        if depth == 0:
            current, block, indent = None, "", None if line.startswith("services:") else -1
            continue
        if indent == -1:
            continue
        if indent is None:
            indent = depth
        stripped = line.strip()
        if depth == indent and stripped.endswith(":"):
            current = {"name": stripped[:-1], "line": number, "env": {}, "ports": [], "image": ""}
            services.append(current)
            block = ""
            continue
        if current is None:
            continue
        if depth == indent * 2:
            key, _, value = stripped.partition(":")
            block = key if not value.strip() else ""
            if key == "image":
                current["image"] = value.strip().strip("\"'")
            continue
        item = stripped.removeprefix("- ").strip().strip("\"'")
        if block == "environment":
            key, sep, value = item.partition("=") if "=" in item and ":" not in item.split("=")[0] else item.partition(":")
            current["env"][key.strip()] = value.strip().strip("\"'")
        elif block == "ports":
            current["ports"].append(item)
    found = []
    for service in services:
        kind = next((k for part, k in _IMAGES if part in service["image"].lower()), None)
        if not kind:
            continue
        env = service["env"]
        host, port = "localhost", ""  # a service publishing no port of its database is not reachable from here
        for mapping in service["ports"]:
            pieces = re.split(r":(?![^{]*\})", mapping)
            if len(pieces) >= 2 and pieces[-1].split("/")[0] == DEFAULT_PORTS[kind]:
                port = pieces[-2]
                host = pieces[0] if len(pieces) == 3 else "localhost"
        if not port:
            continue
        if kind == "postgresql":
            user = env.get("POSTGRES_USER", "postgres")
            fields = {"user": user, "password": env.get("POSTGRES_PASSWORD", ""), "database": env.get("POSTGRES_DB", user)}
        elif kind == "mysql":
            user = env.get("MYSQL_USER") or env.get("MARIADB_USER") or "root"
            password = (env.get("MYSQL_PASSWORD") or env.get("MARIADB_PASSWORD")) if user != "root" else (
                env.get("MYSQL_ROOT_PASSWORD") or env.get("MARIADB_ROOT_PASSWORD"))
            fields = {"user": user, "password": password or "", "database": env.get("MYSQL_DATABASE") or env.get("MARIADB_DATABASE", "")}
        elif kind == "mssql":
            fields = {"user": "sa", "password": env.get("MSSQL_SA_PASSWORD") or env.get("SA_PASSWORD", ""), "database": ""}
        else:
            fields = {"user": env.get("APP_USER", "system"), "password": env.get("ORACLE_PASSWORD", ""), "database": ""}
        fields["password"] = _as_reference(fields["password"])
        found.append(_connection("Compose", file, service["line"], kind, f"{service['name']} (Compose)",
                                 host=host, port=port, **fields))
    return found


def _is_sqlite(path: Path) -> bool:
    """Whether a file is an SQLite database (by its first bytes)."""
    with path.open("rb") as handle:
        return handle.read(16) == b"SQLite format 3\x00"


def environment(project_root: Path, folder: str) -> dict[str, str]:
    """The variables a connection declared in `folder` sees: the process's, then the `.env` files of the
    project root and of that folder (the closest wins), as Docker Compose and most tools read them.

    Args:
        project_root: Root of the documented project.
        folder: Folder of the declaring file, relative to the project root.

    Returns:
        Variable names and their values.
    """
    values = dict(os.environ)
    for place in dict.fromkeys([project_root, project_root / folder]):
        env_file = place / ".env"
        if env_file.is_file():
            values.update({key: value for _, key, value in _env_values(env_file.read_text(encoding="utf-8", errors="replace"))})
    return values


def resolve(text: str, values: dict[str, str]) -> str:
    """Replace the variable references in a text by their values (`${X:-default}` falls back to `default`).

    Args:
        text: Text with references, e.g. `${POSTGRES_PORT:-55432}`.
        values: Variables available (see `environment`).

    Returns:
        The text with each reference replaced; unknown variables without a default become empty.
    """
    return _REFERENCE.sub(lambda m: values.get(m[1] or m[3]) or (m[2] or ""), text)
