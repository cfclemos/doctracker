"""Read the technical structure of a project with griffe and turn it into plain data.

The result only holds built-in types (dicts, lists, strings), so it can cross
process boundaries and be stored later without depending on griffe objects.
"""

import logging
from pathlib import Path

import griffe

MEMBER_KINDS = ("module", "class", "function", "attribute", "type alias")
"""Kinds of members kept from griffe; anything else (e.g. aliases created by imports) is skipped."""


def extract_project(
    project_root: str,
    packages: list[str],
    search_paths: list[str],
    docstring_style: str,
    show_private: bool,
) -> dict:
    """Load every package statically and turn it into plain data.

    Runs in a worker process, so it takes and returns only built-in types.
    The project's code is read, never imported or executed.

    Args:
        project_root: Root of the documented project.
        packages: Top-level packages to load.
        search_paths: Folders where the packages are found, relative to `project_root`.
        docstring_style: `google`, `numpy` or `sphinx`.
        show_private: Keep `_private` members.

    Returns:
        `roots` (paths of the loaded packages), `entities` (every entity by path) and
        `errors` (packages that could not be loaded, with the reason).
    """
    logging.getLogger("griffe").setLevel(logging.ERROR)
    root = Path(project_root)
    paths = [str(root / path) for path in search_paths]
    entities: dict[str, dict] = {}
    roots = []
    errors = []
    for package in packages:
        try:
            module = griffe.load(
                package,
                search_paths=paths,
                docstring_parser=docstring_style,
                allow_inspection=False,
            )
        except (griffe.GriffeError, ImportError, OSError) as error:
            errors.append(f"{package}: {error}")
            continue
        roots.append(module.path)
        _collect(module, root, docstring_style, show_private, entities)
    return {"roots": roots, "entities": entities, "errors": errors}


def _collect(obj: griffe.Object, root: Path, style: str, show_private: bool, entities: dict) -> None:
    """Add `obj` and its members (recursively) to `entities`.

    Aliases (names imported from elsewhere) are skipped.

    Args:
        obj: Module, class, function or attribute loaded by griffe.
        root: Project root, for relative file paths.
        style: Docstring style.
        show_private: Keep `_private` members.
        entities: Collected entities by path; filled in place.
    """
    entity = _to_entity(obj, root, style)
    members = []
    for member in obj.members.values():
        if member.is_alias:
            continue
        if member.is_private and not show_private:
            continue
        if member.kind.value not in MEMBER_KINDS:
            continue
        members.append(member.path)
        _collect(member, root, style, show_private, entities)
    entity["members"] = members
    entities[obj.path] = entity


def _to_entity(obj: griffe.Object, root: Path, style: str) -> dict:
    """Convert one griffe object to a plain dict (without its members).

    Args:
        obj: Module, class, function or attribute loaded by griffe.
        root: Project root, for the relative file path.
        style: Docstring style.

    Returns:
        Common keys (path, kind, location, docstring, sections, decorators) plus the
        ones of its kind: parameters and returns, bases, annotation and value, or exports.
    """
    entity = {
        "path": obj.path,
        "name": obj.name,
        "kind": obj.kind.value,
        "parent": obj.parent.path if obj.parent else None,
        "filepath": _relative(obj.filepath, root),
        "lineno": obj.lineno,
        "endlineno": obj.endlineno,
        "is_private": obj.is_private,
        "docstring": obj.docstring.value if obj.docstring else "",
        "sections": _sections(obj.docstring, style),
        "decorators": [str(decorator.value) for decorator in getattr(obj, "decorators", [])],
    }
    if obj.is_function:
        entity["parameters"] = [_parameter(parameter) for parameter in obj.parameters]
        entity["returns"] = str(obj.returns) if obj.returns else ""
    if obj.is_class:
        entity["bases"] = [str(base) for base in obj.bases]
        init = obj.members.get("__init__")
        params = init.parameters if init is not None and init.is_function else []
        entity["parameters"] = [_parameter(parameter) for parameter in params if parameter.name != "self"]
    if obj.is_attribute:
        entity["annotation"] = str(obj.annotation) if obj.annotation else ""
        entity["value"] = str(obj.value) if obj.value is not None else ""
    if obj.is_module:
        entity["exports"] = [str(name) for name in obj.exports] if obj.exports else []
        entity["is_package"] = entity["filepath"].endswith("__init__.py") or isinstance(obj.filepath, list)
    return entity


def _parameter(parameter: griffe.Parameter) -> dict:
    """Convert a function parameter to a plain dict.

    Args:
        parameter: Parameter loaded by griffe.

    Returns:
        Name, annotation, default (empty when there is none) and kind (e.g. `keyword-only`).
    """
    kind = parameter.kind.value
    # griffe fills `*args`/`**kwargs` with `()`/`{}`, which are not real defaults.
    variadic = kind in ("variadic positional", "variadic keyword")
    return {
        "name": parameter.name,
        "annotation": str(parameter.annotation) if parameter.annotation else "",
        "default": str(parameter.default) if parameter.default is not None and not variadic else "",
        "kind": kind,
    }


def _sections(docstring: griffe.Docstring | None, style: str) -> list[dict]:
    """Parse a docstring into a list of `{"kind", "title", "text", "items"}` sections.

    Args:
        docstring: Docstring loaded by griffe, or `None` when the object has none.
        style: Docstring style.

    Returns:
        Sections in docstring order; text sections use `text`, the others `items`
        (name, annotation, description, and `is_code` for examples).
    """
    if docstring is None:
        return []
    sections = []
    for section in docstring.parse(style):
        value = section.value
        entry = {"kind": section.kind.value, "title": section.title or "", "text": "", "items": []}
        if isinstance(value, str):
            entry["text"] = value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, tuple):  # examples: (kind, text), kind is "text" or "examples" (code)
                    entry["items"].append(
                        {"name": "", "annotation": "", "description": item[1], "is_code": item[0].value == "examples"}
                    )
                else:
                    entry["items"].append(_section_item(item))
        else:  # admonition, deprecated
            entry["text"] = getattr(value, "description", "") or ""
            entry["title"] = entry["title"] or str(getattr(value, "annotation", "") or "")
        sections.append(entry)
    return sections


def _section_item(item: griffe.DocstringElement) -> dict:
    """Convert one item of a docstring section (a parameter, a raised exception...) to a plain dict.

    Args:
        item: Item parsed by griffe; not every kind has a name or an annotation.

    Returns:
        Name, annotation and description, empty strings when missing.
    """
    annotation = getattr(item, "annotation", None)
    return {
        "name": getattr(item, "name", "") or "",
        "annotation": str(annotation) if annotation else "",
        "description": getattr(item, "description", "") or "",
    }


def _relative(filepath: Path | list[Path], root: Path) -> str:
    """Make the path of a source file relative to the project root, with forward slashes.

    Args:
        filepath: File of the object; namespace packages have a list of folders, the first is used.
        root: Project root.

    Returns:
        The relative path, or the absolute one when the file is outside the project.
    """
    if isinstance(filepath, list):  # namespace packages have several folders
        filepath = filepath[0]
    try:
        return Path(filepath).relative_to(root).as_posix()
    except ValueError:
        return Path(filepath).as_posix()
