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
        `search_text`; each file is also added to the `members` of its package.
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
            if parent in entities:
                entities[parent]["members"].append(file_path)
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
                names = {part.text.decode("utf-8") for part in _walk(selectors)  # not :hover, :not(...)
                         if part.type == "class_name" and part.parent is not None
                         and part.parent.type == "class_selector"}
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


_CLASS_ATTRIBUTE = re.compile(r"""\bclass\s*=\s*(["'])(.*?)\1""", re.S)
_HANDLER_ATTRIBUTE = re.compile(r"""\bon[a-z]+\s*=\s*(["'])(.*?)\1""", re.S)
_URL_ATTRIBUTE = re.compile(
    r"""\b(?:hx-(?:get|post|put|patch|delete)|href|action|src|data-url)\s*=\s*(["'])(/.*?)\1""", re.S)
_CALLED = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
_TOKEN = re.compile(r"[A-Za-z_][\w-]*")
_SELECTOR_CLASS = re.compile(r"\.([A-Za-z_][\w-]*)")
_DYNAMIC_CLASS = re.compile(r"([A-Za-z_][\w-]*-)(?:\{\{|\$\{)")
_JINJA_BLOCK = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)


def frontend_edges(entities: dict[str, dict], root: Path, registered: dict[str, str],
                   routes: list[tuple[str, str, str]]) -> list[dict]:
    """Find what the front-end files use: templates, macros, Python helpers, CSS classes, JS functions, routes.

    Templates use the Python functions registered for them (`refers`), the templates they include,
    extend or import (`uses`) and the macros they call (`calls`); templates and scripts use CSS
    classes (`uses`: class attributes, class names in JS strings and selectors) and call JS
    functions (`calls`: JS calls, inline `on…` handlers); a URL they name (`hx-get`, `href`,
    `action`, `fetch(...)`...) reaches the Python entity declaring its route (`refers`, with `via`:
    the route and its handler). Each relation starts at the macro or JS function the use is in, else
    at the file.

    Args:
        entities: Every extracted entity, Python and front-end, by path.
        root: Project root.
        registered: Names the templates use → Python function or class registered under them.
        routes: `(URL pattern, entity declaring the route, handler)` from the Python code.

    Returns:
        `{"source", "target", "kind"}` (and `via` for routes) relations, without duplicates.
    """
    index = _Index(entities, routes)
    found: dict[tuple[str, str, str], str] = {}
    for path, entity in entities.items():
        if entity["kind"] not in FRONTEND_KINDS.values() or entity["kind"] == "stylesheet":
            continue
        try:
            source = (root / entity["filepath"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if entity["kind"] == "template":
            uses = _template_uses(path, source, registered, index)
        else:
            uses = _script_uses(source, index)
        for line, target, kind, via in uses:
            source_path = index.owner(path, line)
            if target != source_path:
                found.setdefault((source_path, target, kind), via)
    return [{"source": source, "target": target, "kind": kind, **({"via": via} if via else {})}
            for (source, target, kind), via in sorted(found.items())]


class _Index:
    """The front-end entities by what names them, and the routes as patterns.

    Args:
        entities: Every extracted entity, by path.
        routes: `(URL pattern, entity declaring the route, handler)`.
    """

    def __init__(self, entities: dict[str, dict], routes: list[tuple[str, str, str]]) -> None:
        self.entities = entities
        self.classes: dict[str, list[str]] = {}
        self.functions: dict[str, list[str]] = {}
        self.templates: dict[str, str] = {}
        for path, entity in entities.items():
            if entity["kind"] == "css class":
                self.classes.setdefault(entity["name"][1:], []).append(path)
            elif entity["kind"] == "js function":
                self.functions.setdefault(entity["name"], []).append(path)
            elif entity["kind"] == "template":
                self.templates[path] = path
        self.routes = []
        for pattern, declared_by, handler in routes:
            # `{name}` matches one part of the path, `{name:path}` the rest of it.
            parts = re.split(r"(\{[^}]*\})", pattern)
            regex = "".join(("(.+)" if part.endswith(":path}") else "([^/]+)") if part.startswith("{")
                            else re.escape(part) for part in parts)
            literal = len("".join(part for part in parts if not part.startswith("{")))
            self.routes.append((re.compile(f"^{regex}$"), literal, declared_by, f"{pattern} → {handler}"))

    def owner(self, file: str, line: int) -> str:
        """The innermost member of a file (macro, JS function) holding a line; the file itself otherwise."""
        holding = [member for member in self.entities[file]["members"]
                   if self.entities[member]["lineno"] <= line <= self.entities[member]["endlineno"]]
        return min(holding, default=file,
                   key=lambda member: self.entities[member]["endlineno"] - self.entities[member]["lineno"])

    def template(self, name: str) -> str | None:
        """The template a Jinja name (`macros.html`, `sub/page.html`) points to, when only one matches."""
        matching = [path for path in self.templates if path.endswith(f"/{name}")]
        return matching[0] if len(matching) == 1 else None

    def route(self, url: str) -> tuple[str, str] | None:
        """The entity declaring the route a URL reaches, and `pattern → handler`; the most literal route wins."""
        path = url.split("?", 1)[0].split("#", 1)[0]
        matching = [(literal, declared_by, via) for regex, literal, declared_by, via in self.routes
                    if regex.match(path)]
        return max(matching)[1:] if matching else None

    def class_uses(self, text: str, line: int, selectors: bool = False) -> list[tuple[int, str, str, str]]:
        """The CSS classes a text names: `.name` in a selector, or any word that is a class name.

        A name built with a value (`state-{{ x }}`, `state-${x}`) uses every class starting with its fixed part.
        """
        names = set(_SELECTOR_CLASS.findall(text) if selectors else _TOKEN.findall(text))
        prefixes = set(_DYNAMIC_CLASS.findall(text)) | {name for name in names if name.endswith("-")}
        for prefix in prefixes:  # `"note-" ~ note.type` too
            names |= {name for name in self.classes if name.startswith(prefix)}
        return [(line, path, "uses", "") for name in sorted(names) for path in self.classes.get(name, [])]

    def url_use(self, url: str, line: int) -> list[tuple[int, str, str, str]]:
        """The route a URL reaches, as a use."""
        reached = self.route(_JINJA_BLOCK.sub("x", url))
        return [(line, reached[0], "refers", reached[1])] if reached else []


def _line(source: str, offset: int) -> int:
    """The line (from 1) of a character offset."""
    return source.count("\n", 0, offset) + 1


def _template_uses(template: str, source: str, registered: dict[str, str],
                   index: _Index) -> list[tuple[int, str, str, str]]:
    """What a template uses: `(line, target, kind, via)` for each use."""
    uses = []
    try:
        tree = Environment().parse(source)
    except TemplateSyntaxError:
        tree = None
    if tree is not None:
        aliases: dict[str, str] = {}  # name → the template it imports
        imported: dict[str, str] = {}  # name → the macro it imports
        for node in tree.find_all((nodes.Extends, nodes.Include, nodes.Import, nodes.FromImport)):
            if not (isinstance(node.template, nodes.Const) and (target := index.template(node.template.value))):
                continue
            uses.append((node.lineno, target, "uses", ""))
            if isinstance(node, nodes.Import):
                aliases[node.target] = target
            elif isinstance(node, nodes.FromImport):
                for name in node.names:
                    name, alias = name if isinstance(name, tuple) else (name, name)
                    imported[alias] = f"{target}:{name}"
        local = {macro.name for macro in tree.find_all(nodes.Macro)}
        for node in tree.find_all(nodes.Call):
            called = node.node
            target = None
            if (isinstance(called, nodes.Getattr) and isinstance(called.node, nodes.Name)
                    and called.node.name in aliases):
                target = f"{aliases[called.node.name]}:{called.attr}"
            elif isinstance(called, nodes.Name):  # a macro of this template, or one imported by name
                target = f"{template}:{called.name}" if called.name in local else imported.get(called.name)
            if target and target in index.entities:
                uses.append((node.lineno, target, "calls", ""))
        for node in tree.find_all((nodes.Name, nodes.Filter, nodes.Test)):
            if node.name in registered and node.name not in local and getattr(node, "ctx", "load") == "load":
                uses.append((node.lineno, registered[node.name], "refers", ""))
        for node in tree.find_all(nodes.Const):
            if isinstance(node.value, str) and node.value.startswith("/"):
                uses.extend(index.url_use(node.value, node.lineno))
            elif isinstance(node.value, str):  # class names given to a macro or joined with ~
                uses.extend(index.class_uses(node.value, node.lineno))
    for match in _CLASS_ATTRIBUTE.finditer(source):
        value = match.group(2)
        quoted = " ".join(re.findall(r"""["']([^"']*)["']""", value))  # names written inside {{ }} or {% %}
        dynamic = " ".join(_DYNAMIC_CLASS.findall(value))
        uses.extend(index.class_uses(f"{_JINJA_BLOCK.sub(' ', value)} {quoted} {value if dynamic else ''}",
                                     _line(source, match.start())))
    for match in _HANDLER_ATTRIBUTE.finditer(source):
        line = _line(source, match.start())
        uses.extend((line, path, "calls", "") for name in _CALLED.findall(match.group(2))
                    for path in index.functions.get(name, []))
    for match in _URL_ATTRIBUTE.finditer(source):
        uses.extend(index.url_use(match.group(2), _line(source, match.start())))
    return uses


def _script_uses(source: str, index: _Index) -> list[tuple[int, str, str, str]]:
    """What a script uses: `(line, target, kind, via)` for each use."""
    uses = []
    for node in _walk(_JS.parse(source.encode("utf-8")).root_node):
        line = node.start_point[0] + 1
        if node.type == "call_expression":
            called = node.child_by_field_name("function")
            if called is not None and called.type == "identifier":
                name = called.text.decode("utf-8")
                uses.extend((line, path, "calls", "") for path in index.functions.get(name, []))
        elif node.type == "identifier" and node.parent is not None:
            # A function named without being called: a callback, a value in an object or a list.
            parent = node.parent
            called = parent.type == "call_expression" and parent.child_by_field_name("function") == node
            declared = parent.child_by_field_name("name") == node
            if not called and not declared:
                uses.extend((line, path, "refers", "") for path in index.functions.get(node.text.decode("utf-8"), []))
        elif node.type in ("string", "template_string"):
            text = node.text.decode("utf-8")[1:-1]
            if text.startswith("/") and len(text) > 1:
                uses.extend(index.url_use(re.sub(r"\$\{[^}]*\}", "x", text), line))
            looks_like_selector = any(mark in text for mark in (".", "#", "[", ":", ">"))
            uses.extend(index.class_uses(text, line, selectors=looks_like_selector and "class=" not in text))
            for match in _CLASS_ATTRIBUTE.finditer(text):
                uses.extend(index.class_uses(match.group(2), line))
    return uses
