"""The languages doctracker reads: their names, the suffixes of their files and what is told when none is found.

Every entity carries the `language` of its file; the wiki filters and groups by it.
"""

from pathlib import PurePosixPath

LANGUAGES = {
    "python": {"label": "Python", "suffixes": (".py",)},
    "js": {"label": "JavaScript", "suffixes": (".js",)},
    "css": {"label": "CSS", "suffixes": (".css",)},
    "html": {"label": "HTML", "suffixes": (".html",)},
    "typescript": {"label": "TypeScript", "suffixes": (".ts", ".tsx")},
    "php": {"label": "PHP", "suffixes": (".php",)},
    "java": {"label": "Java", "suffixes": (".java",)},
    "csharp": {"label": "C#", "suffixes": (".cs",)},
    "c": {"label": "C", "suffixes": (".c", ".h")},
    "cpp": {"label": "C++", "suffixes": (".cpp", ".cc", ".hpp")},
    "go": {"label": "Go", "suffixes": (".go",)},
    "rust": {"label": "Rust", "suffixes": (".rs",)},
    "sql": {"label": "SQL", "suffixes": (".sql",)},
}
"""The languages read, by the `language` of their entities: the name shown and the file suffixes.
Python, JavaScript, CSS and HTML are read into what they define; the others, for now, as whole files."""

NO_SOURCES = ("No file of a known language was found in the repository.",
              "doctracker reads every file of these languages, wherever it is in the repository:",
              "Files that .gitignore excludes, hidden folders and folders like venv, node_modules, build "
              "and dist are not read.",
              "Start doctracker at the project root.")
"""Told by `start` and the wiki when nothing is found: the line before the list of `LANGUAGES`, its
title, the line after it and the advice, shown in bold."""


def language_of(file: str) -> str | None:
    """The language of a project file by its suffix, or `None` when doctracker does not read it."""
    suffix = PurePosixPath(file).suffix
    return next((name for name, language in LANGUAGES.items() if suffix in language["suffixes"]), None)

