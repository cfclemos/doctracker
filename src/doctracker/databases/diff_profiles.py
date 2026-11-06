"""Comparison profiles of DATABASES › Diff: two places compared, kept with a name.

A profile holds a name, a description, the places A and B (an origin's or a live database's, a whole
one, a schema or a table, see `origins.compare`) and what the comparison leaves out (`IGNORABLE`). It is
kept in the project, one file per profile in `doc/diff/<name>.json`, as the slices are, so it is
versioned and shared; the wiki and the MCP tools read and write the same files. Nothing here touches a
database: the comparison is made again each time a profile is opened.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from doctracker.config import DOC_DIR

PROFILES_FOLDER = f"{DOC_DIR}/diff"
"""Where the profiles are kept, in the documented project."""

IGNORABLE = {"checks": "Checks", "comments": "Comments", "indexes": "Indexes"}
"""What a profile may leave out of its comparison, by key, with its name in the wiki."""


def _file_name(name: str) -> str:
    """A profile's file: its name in lower case, letters, digits and dashes."""
    return (re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "profile") + ".json"


class ProfileStore:
    """The project's comparison profiles, one JSON file each.

    Args:
        project_root: Root of the documented project.
        on_change: Called after a profile is saved or deleted (the wiki reloads).
    """

    def __init__(self, project_root: Path, on_change=None) -> None:
        self.folder = project_root / PROFILES_FOLDER
        self.on_change = on_change

    def profiles(self) -> list[dict]:
        """Every profile, by name: `name`, `description`, `a`, `b`, `ignore`, `created`, `changed`, `file`."""
        found = []
        for file in sorted(self.folder.glob("*.json")) if self.folder.is_dir() else []:
            try:
                found.append({**json.loads(file.read_text(encoding="utf-8")), "file": f"{PROFILES_FOLDER}/{file.name}"})
            except (OSError, ValueError):
                continue
        return sorted(found, key=lambda p: p.get("name", "").lower())

    def profile(self, name: str) -> dict | None:
        """One profile by its name (any case); None when there is none."""
        return next((p for p in self.profiles() if p.get("name", "").lower() == name.lower()), None)

    def save(self, name: str, a: str, b: str, description: str = "", ignore: list[str] | None = None, previous: str = "") -> dict:
        """Keep a profile: a new one, or one changed (`previous`: its name before, when renamed).

        Args:
            name: Its name.
            a: Place A.
            b: Place B.
            description: What the comparison is for.
            ignore: What it leaves out, keys of `IGNORABLE`.
            previous: The name it had, when it is changed or renamed.

        Returns:
            The profile as kept.

        Raises:
            ValueError: Without a name, A or B, or when another profile has the name.
        """
        name = " ".join(name.split())
        if not name:
            raise ValueError("A profile needs a name.")
        if not a or not b:
            raise ValueError("A profile needs both places, A and B.")
        other = self.profile(name)
        if other is not None and other["name"].lower() != (previous or "").lower():
            raise ValueError(f"There is already a profile named {other['name']}.")
        before = self.profile(previous) if previous else None
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        found = {"name": name, "description": description.strip(), "a": a, "b": b,
                 "ignore": [key for key in IGNORABLE if key in (ignore or [])],
                 "created": (before or {}).get("created", now), "changed": now}
        self.folder.mkdir(parents=True, exist_ok=True)
        if before is not None and _file_name(before["name"]) != _file_name(name):
            (self.folder / _file_name(before["name"])).unlink(missing_ok=True)
        (self.folder / _file_name(name)).write_text(json.dumps(found, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if self.on_change:
            self.on_change()
        return found

    def delete(self, name: str) -> None:
        """Forget a profile (its file removed)."""
        found = self.profile(name)
        if found is not None:
            (self.folder / _file_name(found["name"])).unlink(missing_ok=True)
            if self.on_change:
                self.on_change()
