"""The front-end files inside the packages, as entities: JS files and functions, CSS files with their
classes and their other rules, templates and their macros.

They are read statically, like the Python code: JS and CSS with tree-sitter, templates with Jinja2's
own parser. Each file is an entity under the nearest Python package, and what it defines is an
entity under the file, at `file:name` (e.g. `doctracker/wiki/static/live.js:reloadContent`; a CSS
class keeps its dot, `style.css:.plan-card`; a rule naming no class is known by its selectors,
`style.css:main`). Minified files (`*.min.*`) are vendored code and skipped. Their summary is the
comment written right above them; their text (the JS body, the CSS rules, the template) is kept for
the search.
"""

import re
from pathlib import Path

import tree_sitter_css
import tree_sitter_javascript
from jinja2 import Environment, nodes
from jinja2.exceptions import TemplateSyntaxError
from tree_sitter import Language, Node, Parser

FRONTEND_KINDS = {".js": "script", ".css": "stylesheet", ".html": "template"}
"""The front-end files read, by suffix, with the kind of their entity."""

FRONTEND_MEMBER_KINDS = ("js function", "css class", "css rule", "macro")
"""The kinds of what the files define: JS functions; CSS classes, and CSS rules naming no class; macros."""

MAX_SEARCH_CHARS = 4000
"""Longest text kept for the search of one front-end entity."""

_JS = Parser(Language(tree_sitter_javascript.language()))
_CSS = Parser(Language(tree_sitter_css.language()))
_JINJA_COMMENT = re.compile(r"\{#(.*?)#\}", re.S)
_MACRO_TAG = re.compile(r"\{%-?\s*(macro|endmacro)\b")


def extract_frontend(root: Path, entities: dict[str, dict]) -> dict[str, dict]:
    """Read the front-end files of the loaded packages.

    Args:
        root: Project root.
        entities: The Python entities already extracted (their packages give the folders to read).

    Returns:
        The front-end entities, by path, with the same keys as the Python ones plus `language` and
        `search_text`.
    """
    root = root.resolve()
    packages = {(root / entity["filepath"]).resolve().parent.relative_to(root).as_posix(): path
                for path, entity in entities.items()
                if entity["kind"] == "module" and entity.get("is_package") and isinstance(entity["filepath"], str)}
    found: dict[str, dict] = {}
    for folder, package in sorted(packages.items()):
        if Path(folder).parent.as_posix() in packages:
            continue  # read from its top package
        for file in sorted((root / folder).rglob("*")):
            kind = FRONTEND_KINDS.get(file.suffix)
            if kind is None or ".min." in file.name or not file.is_file():
                continue
            try:
                source = file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            relative = file.relative_to(root).as_posix()
            parent = _package_of(relative, packages)
            file_path = f"{package.replace('.', '/')}/{file.relative_to(root / folder).as_posix()}"
            if kind == "script":
                members = _js_functions(source)
            elif kind == "stylesheet":
                members = _css_rules(source)
            else:
                members = _macros(source)
            children = []
            for name, member_kind, lineno, endlineno, comment, text in members:
                path = f"{file_path}:{name}"
                children.append(path)
                found[path] = _entity(path, name, member_kind, file_path, relative, lineno, endlineno, comment, text)
            found[file_path] = _entity(file_path, file.name, kind, parent, relative, 1, source.count("\n") + 1,
                                       _file_comment(kind, source), source, children)
    return found


def _package_of(file: str, packages: dict[str, str]) -> str:
    """The nearest Python package holding a file (the deepest folder that is a package)."""
    folders = [folder for folder in packages if file.startswith(f"{folder}/")]
    return packages[max(folders, key=len)] if folders else ""


def _entity(path: str, name: str, kind: str, parent: str, filepath: str, lineno: int, endlineno: int,
            comment: str, text: str, members: list[str] | None = None) -> dict:
    """A front-end entity, with the keys of the Python ones."""
    return {"path": path, "name": name, "kind": kind, "parent": parent, "filepath": filepath, "lineno": lineno,
            "endlineno": endlineno, "is_private": False, "docstring": comment, "sections": [], "decorators": [],
            "members": members or [], "language": {"script": "js", "js function": "js", "stylesheet": "css",
                                                   "css class": "css", "css rule": "css"}.get(kind, "jinja"),
            "search_text": text[:MAX_SEARCH_CHARS]}


def _comment_text(comments: list[str]) -> str:
    """The text of `//`, `/* */` or `{# #}` comments, without their markers."""
    lines = []
    for comment in comments:
        body = re.sub(r"^(//|/\*+|\{#)|(\*+/|#\})$", "", comment.strip())
        lines.extend(line.strip().lstrip("*").strip() for line in body.splitlines())
    return " ".join(line for line in lines if line)


def _comments_above(node: Node) -> str:
    """The comments written on their own lines right above a node (no blank line between), as text.

    A comment at the end of the line of the code before belongs to that code, not to this node.
    """
    comments, line = [], node.start_point[0]
    sibling = node.prev_named_sibling
    while sibling is not None and sibling.type == "comment" and sibling.end_point[0] >= line - 1:
        before = sibling.prev_sibling
        if before is not None and before.end_point[0] == sibling.start_point[0]:
            break
        comments.insert(0, sibling.text.decode("utf-8"))
        line = sibling.start_point[0]
        sibling = sibling.prev_named_sibling
    return _comment_text(comments)


def _js_functions(source: str) -> list[tuple[str, str, int, int, str, str]]:
    """The top-level functions of a script: declared ones and named function or arrow constants.

    Returns:
        `(name, "js function", first line, last line, comment above, code)` for each.
    """
    tree = _JS.parse(source.encode("utf-8"))
    found = []
    for node in tree.root_node.named_children:
        declaration = node.child_by_field_name("declaration") if node.type == "export_statement" else node
        if declaration is None:
            continue
        if declaration.type in ("function_declaration", "generator_function_declaration"):
            named = [(declaration.child_by_field_name("name"), declaration)]
        elif declaration.type in ("lexical_declaration", "variable_declaration"):
            named = [(child.child_by_field_name("name"), child) for child in declaration.named_children
                     if child.type == "variable_declarator" and (value := child.child_by_field_name("value"))
                     and value.type in ("arrow_function", "function_expression", "function")]
        else:
            continue
        for name, _ in named:
            if name is not None and name.type == "identifier":
                found.append((name.text.decode("utf-8"), "js function", node.start_point[0] + 1,
                              node.end_point[0] + 1, _comments_above(node), node.text.decode("utf-8")))
    return found


def _css_rules(source: str) -> list[tuple[str, str, int, int, str, str]]:
    """The classes a stylesheet styles, each with every rule naming it, and the rules naming no class.

    A rule naming no class (`main`, `#topbar`, `h2`) is known by its selectors; rules with the same
    selectors are one entity.

    Returns:
        `(".name" or selectors, "css class" or "css rule", first line, last line, the first comment
        above one of its rules, its rules with their comments)` for each, in order.
    """
    tree = _CSS.parse(source.encode("utf-8"))
    found: dict[str, list] = {}

    def add(name: str, kind: str, rule: Node) -> None:
        comment = _comments_above(rule)
        entry = found.setdefault(name, [kind, rule.start_point[0] + 1, rule.end_point[0] + 1, comment, []])
        entry[2] = rule.end_point[0] + 1
        entry[3] = entry[3] or comment  # the first rule with a comment says what the class or rule is for
        entry[4].append(f"/* {comment} */\n{rule.text.decode('utf-8')}" if comment else rule.text.decode("utf-8"))

    def visit(node: Node) -> None:
        for child in node.named_children:
            if child.type == "rule_set":
                selectors = child.child_by_field_name("selectors") or child.named_children[0]
                names = {part.text.decode("utf-8") for part in _walk(selectors) if part.type == "class_name"}
                for name in sorted(names):
                    add(f".{name}", "css class", child)
                if not names:
                    add(" ".join(selectors.text.decode("utf-8").split()), "css rule", child)
            elif child.type in ("media_statement", "supports_statement", "block"):
                visit(child)

    visit(tree.root_node)
    return [(name, kind, first, last, comment, "\n".join(rules))
            for name, (kind, first, last, comment, rules) in found.items()]


def _walk(node: Node):
    """Every node under a node, the node first."""
    yield node
    for child in node.children:
        yield from _walk(child)


def _macros(source: str) -> list[tuple[str, str, int, int, str, str]]:
    """The macros a template defines (nested ones too).

    Returns:
        `(name, "macro", first line, last line, the {# comment #} right above it, its code)` for each.
    """
    try:
        tree = Environment().parse(source)
    except TemplateSyntaxError:
        return []
    lines = source.splitlines()
    found = []
    for macro in tree.find_all(nodes.Macro):
        first = macro.lineno
        last = _macro_end(lines, first)
        found.append((macro.name, "macro", first, last, _jinja_comment_above(lines, first),
                      "\n".join(lines[first - 1: last])))
    return found


def _macro_end(lines: list[str], first: int) -> int:
    """The line of the `endmacro` closing the macro opened on line `first`."""
    depth = 0
    for number, line in enumerate(lines[first - 1:], start=first):
        for tag in _MACRO_TAG.findall(line):
            depth += 1 if tag == "macro" else -1
            if depth == 0:
                return number
    return len(lines)


def _jinja_comment_above(lines: list[str], first: int) -> str:
    """The `{# comment #}` ending on the line right above line `first`."""
    end = first - 2
    if end < 0 or not lines[end].rstrip().endswith("#}"):
        return ""
    start = end
    while start > 0 and "{#" not in lines[start]:
        start -= 1
    if all(not line.strip() or line.lstrip().startswith(("{% import", "{% from", "{% extends"))
           for line in lines[:start]):
        return ""  # the comment the template starts with is the template's own
    block = "\n".join(lines[start: end + 1])
    return _comment_text([match.group(0) for match in _JINJA_COMMENT.finditer(block)][-1:])


def _file_comment(kind: str, source: str) -> str:
    """The comment a file starts with: `//` or `/* */` lines for JS and CSS, a `{# #}` for templates."""
    if kind == "template":
        head = source.lstrip()
        if head.startswith("{%") and "import" in head.split("\n", 1)[0]:
            head = head.split("\n", 1)[1].lstrip() if "\n" in head else ""
        match = _JINJA_COMMENT.match(head)
        return _comment_text([match.group(0)]) if match else ""
    comments = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            comments.append(stripped)
        elif stripped.startswith("/*") and not comments:
            end = source.find("*/")
            return _comment_text([source[source.find("/*"): end + 2]]) if end != -1 else ""
        else:
            break
    return _comment_text(comments)
