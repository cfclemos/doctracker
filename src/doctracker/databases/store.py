"""Keep the database connections: those the project declares, those the user enters, and the consent to use them.

Everything lives in `doc/connections/`, out of git (`doc/.gitignore`, and a `.gitignore` of its own).
`connections.json` holds no secret: which connections the user allowed, the ones entered by hand, the
user's changes to declared ones and those deleted from the list; passwords are either a reference to
an environment variable or kept in `secrets.bin`,
encrypted (Fernet, from `cryptography`). The key is kept in the system's vault (`keyring`); where
there is none, it is derived from a master password the user types (scrypt) and never written.
"""

import base64
import json
import os
import uuid
from pathlib import Path

import keyring
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from doctracker.config import DOC_DIR
from doctracker.databases.discovery import HIDDEN, KINDS, Connection, discover, environment, parse_url, resolve
from doctracker.databases.readonly import SIGN_INS

CONNECTIONS_DIR = Path(DOC_DIR) / "connections"
"""Folder of the connections, relative to the project root; never committed."""

VAULT_SERVICE = "doctracker"
"""Name under which the key is kept in the system's vault (one entry per project)."""

SSH_FIELDS = ("ssh_host", "ssh_port", "ssh_user", "ssh_key", "ssh_jump", "ssh_config", "sign_in", "sign_in_option")
"""How a connection is reached: its SSH tunnel and its sign-in, besides the SSH password."""

FIELDS = ("name", "kind", "host", "port", "database", "user") + SSH_FIELDS
"""What the user enters for a connection, besides its passwords."""

EDITABLE = ("host", "port", "database", "user") + SSH_FIELDS
"""What the user may change in any connection, declared or entered, besides its passwords."""


def _values(fields: dict, keys: tuple[str, ...]) -> dict:
    """The fields a form or a tool gives, cleaned: texts stripped, `ssh_config` a yes or no."""
    values = {key: (bool(fields.get(key)) if key == "ssh_config" else str(fields.get(key, "")).strip())
              for key in keys if key in fields or key == "ssh_config"}
    if values.get("sign_in", "password") not in SIGN_INS:
        raise ValueError("Choose how to sign in.")
    return values


def _check_sign_in(kind: str, user: str, sign_in: str, password: str) -> None:
    """Refuse a connection missing what it needs to sign in: a user (but SQLite), and a password unless
    an AWS RDS IAM token takes its place (`password` is the one given or the one already saved).

    Raises:
        ValueError: When the user or the password is missing.
    """
    if kind == "sqlite":
        return
    if not user:
        raise ValueError("A connection needs a user.")
    if sign_in != "aws-iam" and not password:
        raise ValueError("A connection needs a password, or ${VARIABLE} for the variable holding it.")


class Locked(Exception):
    """The passwords cannot be read yet: there is no vault and the master password was not typed."""


class ConnectionStore:
    """The project's connections and their passwords, for the wiki and the MCP tools alike.

    Attributes:
        project_root: Root of the documented project.
        folder: `doc/connections/` of the project.
    """

    def __init__(self, project_root: Path) -> None:
        """Open the store of a project; nothing is read until asked.

        Args:
            project_root: Root of the documented project.
        """
        self.project_root = project_root
        self.folder = project_root / CONNECTIONS_DIR
        self._key: bytes | None = None

    # The files.

    def _data(self) -> dict:
        """What `connections.json` holds, no secrets in it: `allowed` (ids the user allowed), `entered`
        (connections entered by hand), `edited` (declared connections changed by the user: id → fields)
        and `removed` (declared connections the user deleted from the list)."""
        path = self.folder / "connections.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        return {"allowed": data.get("allowed", []), "entered": data.get("entered", []),
                "edited": data.get("edited", {}), "removed": data.get("removed", [])}

    def _write(self, data: dict) -> None:
        """Write `connections.json`, creating the folder with a `.gitignore` that keeps it all out of git."""
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / ".gitignore").write_text("*\n", encoding="utf-8")
        (self.folder / "connections.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # The key and the passwords.

    def _account(self) -> str:
        """The vault entry of this project: its absolute path."""
        return str(self.project_root.resolve())

    def has_vault(self) -> bool:
        """Whether the system offers a vault for the key (a headless server often has none)."""
        try:
            return keyring.get_keyring().priority > 0
        except Exception:  # a vault backend failing to load counts as none
            return False

    def locked(self) -> bool:
        """Whether a master password must be typed before passwords can be saved or read."""
        if self._key is not None:
            return False
        return not self.has_vault()

    def _cipher(self) -> Fernet:
        """The cipher of `secrets.bin`, its key from the vault (created there the first time).

        Raises:
            Locked: When there is no vault and the master password was not typed.
        """
        if self._key is None and self.has_vault():
            try:
                stored = keyring.get_password(VAULT_SERVICE, self._account())
                if stored is None:
                    stored = Fernet.generate_key().decode("ascii")
                    keyring.set_password(VAULT_SERVICE, self._account(), stored)
                self._key = stored.encode("ascii")
            except keyring.errors.KeyringError as failed:
                raise Locked(f"The system's vault refused the key: {failed}") from failed
        if self._key is None:
            raise Locked("Type the master password to unlock the saved passwords.")
        return Fernet(self._key)

    def unlock(self, master_password: str) -> None:
        """Derive the key from a master password, where there is no vault.

        The first time, it becomes the master password; later, a wrong one is refused.

        Args:
            master_password: The password the user typed.

        Raises:
            ValueError: When it is empty, or does not open the passwords already saved.
        """
        if not master_password:
            raise ValueError("Type the master password.")
        self.folder.mkdir(parents=True, exist_ok=True)
        salt_file = self.folder / "salt"
        if not salt_file.is_file():
            salt_file.write_bytes(os.urandom(16))
        derived = Scrypt(salt=salt_file.read_bytes(), length=32, n=2 ** 15, r=8, p=1).derive(master_password.encode("utf-8"))
        key = base64.urlsafe_b64encode(derived)
        secrets_file = self.folder / "secrets.bin"
        if secrets_file.is_file():
            try:
                Fernet(key).decrypt(secrets_file.read_bytes())
            except InvalidToken:
                raise ValueError("Wrong master password.") from None
        self._key = key

    def _secrets(self) -> dict[str, str]:
        """The saved passwords, by connection id (decrypted in memory only)."""
        path = self.folder / "secrets.bin"
        if not path.is_file():
            return {}
        try:
            return json.loads(self._cipher().decrypt(path.read_bytes()))
        except InvalidToken:
            raise Locked("The saved passwords cannot be opened with this key.") from None

    def _write_secrets(self, secrets: dict[str, str]) -> None:
        """Encrypt and write the saved passwords."""
        cipher = self._cipher()
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "secrets.bin").write_bytes(cipher.encrypt(json.dumps(secrets).encode("utf-8")))

    # The connections.

    def _declared(self, data: dict) -> list[Connection]:
        """The connections the project declares, less those the user deleted, with the user's changes."""
        declared = []
        for connection in discover(self.project_root):
            if connection.id in data["removed"]:
                continue
            changes = data["edited"].get(connection.id)
            if changes:
                connection.url_variable = ""  # changed by hand: its fields are used, not its URL variable
                for key in EDITABLE:
                    setattr(connection, key, changes.get(key, getattr(connection, key)))
                if "password" in changes:
                    connection.password, connection.secret = changes["password"], ""
                connection.ssh_password = changes.get("ssh_password", connection.ssh_password)
            declared.append(connection)
        return declared

    def connections(self) -> list[dict]:
        """List every connection: those the project declares, then those entered by hand.

        Returns:
            Each connection without secrets (see `Connection.public`), with `allowed` (declared ones
            start blocked until the user allows them; one entered by hand is allowed when entered) and
            `edited` (a declared one the user changed).
        """
        data = self._data()
        listed = [*self._declared(data), *(Connection(**entry) for entry in data["entered"])]
        return [{**c.public(), "allowed": c.id in data["allowed"], "edited": c.id in data["edited"]} for c in listed]

    def _find(self, connection_id: str, data: dict | None = None) -> Connection:
        """A connection by its id, declared or entered.

        Raises:
            ValueError: When there is none with that id.
        """
        data = data or self._data()
        for entry in data["entered"]:
            if entry["id"] == connection_id:
                return Connection(**entry)
        for connection in self._declared(data):
            if connection.id == connection_id:
                return connection
        raise ValueError(f"No connection {connection_id}.")

    def allow(self, connection_id: str, allowed: bool = True) -> None:
        """Give (or take back) the user's consent to use a connection.

        Args:
            connection_id: The connection.
            allowed: False blocks it.
        """
        self._find(connection_id)
        data = self._data()
        data["allowed"] = [i for i in data["allowed"] if i != connection_id] + ([connection_id] if allowed else [])
        self._write(data)

    def _password(self, connection_id: str, password: str) -> str | None:
        """Keep a new password (`connection_id` may end in `/ssh` for the SSH one): a `${VAR}` reference
        as it is, a value encrypted. Gives what the connection shows for it, or None when `password`
        is empty (the one saved is kept)."""
        if password.startswith("${"):
            self._forget_secret(connection_id)
            return password
        if password:
            secrets = self._secrets()
            secrets[connection_id] = password
            self._write_secrets(secrets)
            return HIDDEN
        return None

    def save(self, fields: dict, password: str = "", ssh_password: str = "") -> dict:
        """Add a connection entered by hand; it is allowed by being entered.

        Args:
            fields: `name`, `kind`, `host`, `port`, `database`, `user`, and how it is reached
                (`SSH_FIELDS`); values may be `${VAR}` references.
            password: The password, or `${VAR}` for the variable holding it; empty for none.
            ssh_password: The same for the SSH server (the key's passphrase when there is a key).

        Returns:
            The connection saved, without secrets.

        Raises:
            ValueError: When the kind is unknown, or the name or host is missing.
            Locked: When a password must be saved and the key is not available.
        """
        values = {"sign_in": "password", **_values(fields, FIELDS)}
        if values.get("kind") not in KINDS:
            raise ValueError("Choose the kind of database.")
        if not values.get("name") or not values.get("host"):
            raise ValueError("A connection needs a name and a host (a file, for SQLite).")
        _check_sign_in(values["kind"], values.get("user", ""), values["sign_in"], password)
        identifier = uuid.uuid4().hex[:12]
        entry = {"id": identifier, **values, "source": "entered", "password": self._password(identifier, password) or "",
                 "ssh_password": self._password(f"{identifier}/ssh", ssh_password) or ""}
        data = self._data()
        data["entered"].append(entry)
        data["allowed"].append(identifier)
        self._write(data)
        return Connection(**entry).public()

    def edit(self, connection_id: str, fields: dict, password: str = "", ssh_password: str = "") -> dict:
        """Change the server, database, user, password, SSH tunnel or sign-in of any connection.

        A declared connection keeps its declaration in the project's file: the changes are kept here,
        over it (and its URL variable, if any, is no longer used).

        Args:
            connection_id: The connection.
            fields: `host`, `port`, `database`, `user` and `SSH_FIELDS`; those missing are kept.
            password: A new password or `${VAR}`; empty keeps the current one.
            ssh_password: The same for the SSH server.

        Returns:
            The connection changed, without secrets.

        Raises:
            ValueError: When it is unknown, or its host would be empty.
            Locked: When a password must be saved and the key is not available.
        """
        data = self._data()
        connection = self._find(connection_id, data)
        changes = _values(fields, EDITABLE)
        if "ssh_host" not in fields:  # the tunnel was not in the form: its checkbox keeps its value
            changes.pop("ssh_config", None)
        if changes.get("host", connection.host) == "":
            raise ValueError("A connection needs a host (a file, for SQLite).")
        _check_sign_in(connection.kind, changes.get("user", connection.user), changes.get("sign_in", connection.sign_in),
                       password or connection.password or connection.url_variable)
        for key, secret_id, given in (("password", connection_id, password), ("ssh_password", f"{connection_id}/ssh", ssh_password)):
            shown = self._password(secret_id, given)
            if shown is not None:
                changes[key] = shown
        entry = next((e for e in data["entered"] if e["id"] == connection_id), None)
        if entry is not None:
            entry.update(changes)
        else:
            data["edited"][connection_id] = {**data["edited"].get(connection_id, {}), **changes}
        self._write(data)
        return self._find(connection_id).public()

    def remove(self, connection_id: str) -> None:
        """Delete a connection: one entered by hand with its saved password; a declared one from the
        list (its declaration stays in the project's file), with the user's changes to it.

        Raises:
            ValueError: When there is none with that id.
        """
        data = self._data()
        self._find(connection_id, data)
        if any(e["id"] == connection_id for e in data["entered"]):
            data["entered"] = [e for e in data["entered"] if e["id"] != connection_id]
        else:
            data["removed"].append(connection_id)
            data["edited"].pop(connection_id, None)
        data["allowed"] = [i for i in data["allowed"] if i != connection_id]
        self._write(data)
        self._forget_secret(connection_id)
        self._forget_secret(f"{connection_id}/ssh")

    def _forget_secret(self, connection_id: str) -> None:
        """Drop a saved password, when there is one."""
        if (self.folder / "secrets.bin").is_file():
            secrets = self._secrets()
            if secrets.pop(connection_id, None) is not None:
                self._write_secrets(secrets)

    def spec(self, connection_id: str) -> dict:
        """Resolve a connection for opening it: references replaced by values, the password read.

        Args:
            connection_id: The connection; it must be allowed.

        Returns:
            `kind`, `host`, `port`, `database`, `user`, `password`, `sign_in`, `sign_in_option`, and
            `ssh` (host, port, user, key, password, jump, config) when it goes through a tunnel; ready
            for `readonly.opened`.

        Raises:
            ValueError: When it is unknown or not allowed, or its URL variable is not set.
            Locked: When its password is saved and the key is not available.
        """
        data = self._data()
        connection = self._find(connection_id, data)
        if connection_id not in data["allowed"]:
            raise ValueError("This connection is blocked: allow it first.")
        values = environment(self.project_root, connection.folder)
        if connection.url_variable:
            parts = parse_url(values.get(connection.url_variable, ""))
            if not parts:
                raise ValueError(f"The variable {connection.url_variable} is not set.")
            spec = {key: resolve(parts[key], values) for key in ("kind", "host", "port", "database", "user", "password")}
        else:
            spec = {key: resolve(getattr(connection, key), values) for key in ("kind", "host", "port", "database", "user")}
            if connection.password == HIDDEN:
                spec["password"] = connection.secret or self._secrets().get(connection.id, "")
            else:
                spec["password"] = resolve(connection.password, values)
        if spec["kind"] == "sqlite" and not Path(spec["host"]).is_absolute():
            spec["host"] = str(self.project_root / spec["host"])
        spec["sign_in"], spec["sign_in_option"] = connection.sign_in or "password", resolve(connection.sign_in_option, values)
        if connection.ssh_host:
            ssh = {key: resolve(getattr(connection, f"ssh_{key}"), values) for key in ("host", "port", "user", "key", "jump")}
            ssh["password"] = (self._secrets().get(f"{connection.id}/ssh", "") if connection.ssh_password == HIDDEN
                               else resolve(connection.ssh_password, values))
            if ssh["key"] and not Path(ssh["key"]).expanduser().is_absolute():
                ssh["key"] = str(self.project_root / ssh["key"])
            spec["ssh"] = {**ssh, "config": connection.ssh_config}
        return spec
