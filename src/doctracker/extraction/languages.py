"""The languages doctracker reads: their names, the suffixes of their files and what is told when none is found.

Every entity carries the `language` of its file; the wiki filters and groups by it.
"""

from pathlib import PurePosixPath

import tree_sitter_language_pack as pack

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
}
"""The languages read in full, by the `language` of their entities: the name shown and the file suffixes.
Python is read with griffe, the others through tree-sitter-language-pack (`PACK_NAMES`). Any other
language the pack recognises by a file's name is read as a whole file (see `language_of`)."""

PACK_NAMES = {"js": "javascript", "css": "css", "html": "html", "typescript": "typescript", "php": "php",
              "java": "java", "csharp": "csharp", "c": "c", "cpp": "cpp", "go": "go", "rust": "rust"}
"""The grammar of tree-sitter-language-pack for each language of `LANGUAGES` but Python."""

NOT_CODE = {"vimdoc"}
"""Languages the pack guesses for files that are not code (any `.txt` is taken for Vim help)."""

SCHEMA_SUFFIXES = (".sql", ".prisma")
"""Files that declare databases, read by DATABASES (`databases.origins`: SQL, a Prisma schema) and not as code."""

LABELS = {"yaml": "YAML", "json": "JSON", "toml": "TOML", "xml": "XML", "markdown": "Markdown", "bash": "Shell",
          "ini": "INI", "dockerfile": "Dockerfile", "make": "Make", "cmake": "CMake", "scss": "SCSS"}
"""The name shown for languages read as whole files, when it is not just the pack's name capitalised."""

NO_SOURCES = ("No file of a known language was found in the repository.",
              "doctracker reads every file of these languages, wherever it is in the repository:",
              "Files that .gitignore excludes, hidden folders and folders like venv, node_modules, build "
              "and dist are not read.",
              "Start doctracker at the project root.")
"""Told by `start` and the wiki when nothing is found: the line before the list of `LANGUAGES`, its
title, the line after it and the advice, shown in bold."""


def language_of(file: str) -> str | None:
    """The language of a project file: one of `LANGUAGES` by its suffix, else the one the language pack
    recognises by its name (e.g. `yaml`, read as a whole file); `None` when doctracker does not read it."""
    suffix = PurePosixPath(file).suffix
    if suffix.lower() in SCHEMA_SUFFIXES:
        return None
    known = next((name for name, language in LANGUAGES.items() if suffix in language["suffixes"]), None)
    detected = known or pack.detect_language_from_path(file)
    return None if detected in NOT_CODE else detected


def language_label(language: str) -> str:
    """The name shown for a language, e.g. `JavaScript`, `YAML`."""
    if language in LANGUAGES:
        return LANGUAGES[language]["label"]
    return LABELS.get(language, language.capitalize())

