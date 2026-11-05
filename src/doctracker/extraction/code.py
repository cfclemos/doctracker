"""The code of every language but Python, as entities in the same shape as the Python ones.

Every file is read through tree-sitter-language-pack's grammars, all the same way: the file is a
module (`kind_label` tells what it is: `script`, `stylesheet`, `template`, `file`), and what the
pack's structure finds in it (classes, interfaces, structs, enums, functions, methods...) are its
members, each with the category the wiki and the graphs know (`kind`: `class`, `function`,
`attribute`) and its own kind (`kind_label`: `interface`, `struct`, `method`...). The same fallbacks
serve every language: the description is the doc comment, else the comments written on their own
lines right above; the signature is the first line when the pack gives none; what has no name is
left out. Stylesheets add their CSS classes and rules (from the same grammar) and templates their
macros; the Jinja syntax of templates is the one thing read with another parser, Jinja2's own,
because the pack's Jinja grammars break on real templates.

Paths are the file's path in the repository and, for what it defines, `file:Name.Child` (e.g.
`src/doctracker/wiki/static/live.js:reloadContent`, `Stock.java:Stock.unitsOf`; a CSS class keeps
its dot, `style.css:.plan-card`; a rule naming no class is known by its selectors, `style.css:main`).
Minified files (`*.min.*`) are vendored code and skipped. Files of a language the pack recognises
but doctracker does not read in full (YAML, JSON, TOML, Markdown...) are a module with no members.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path

import tree_sitter_language_pack as pack
from jinja2 import Environment, nodes
from jinja2.exceptions import TemplateSyntaxError
from tree_sitter import Node, Parser

from doctracker.config import GRAMMARS_DIR
from doctracker.extraction.languages import PACK_NAMES, language_label, language_of

FILE_LABELS = {"js": "script", "typescript": "script", "css": "stylesheet", "html": "template"}
"""What a file is (`kind_label` of its module), by language; any other language's file is a `file`."""

CATEGORIES = {"class": "class", "struct": "class", "interface": "class", "enum": "class", "trait": "class",
              "impl": "class", "function": "function", "method": "function"}
"""The category (`kind`) of each kind the pack's structure gives; any other named item is an `attribute`."""

GROUPINGS = ("module", "namespace")
"""Kinds of the pack's structure that only group what they hold (a Java package, a C# namespace)."""

MAX_SEARCH_CHARS = 4000
"""Longest text kept for the search of one entity."""

_JINJA_COMMENT = re.compile(r"\{#(.*?)#\}", re.S)
_MACRO_TAG = re.compile(r"\{%-?\s*(macro|endmacro)\b")
_DOC_TAGS = re.compile(r"</?(?:summary|remarks|returns|param|typeparam|value|example|para)\b[^>]*>")


def extract_code(root: Path, files: list[str], entities: dict[str, dict],
                 on_file: Callable[[int, int], None] | None = None) -> tuple[dict[str, dict], list[dict]]:
    """Read every file that is not Python into entities, through the language pack.

    Args:
        root: Project root.
        files: The project's files (`config.project_files`); those of a language the pack reads are read.
        entities: The Python entities already extracted; a file inside a Python package is also
            added to the `members` of that package.
        on_file: Told, before each file, how many files are read and how many there are to read.

    Returns:
        The entities, by path, with the keys of the Python ones plus `kind_label`, `signature` and
        `search_text`; and the grammars that could not be fetched (e.g. without network), whose files
        are not read: `language` (its name), `grammar`, `files` (how many were left out) and `error`.
    """
    root = root.resolve()
    pack.configure(pack.PackConfig(cache_dir=str(root / GRAMMARS_DIR)))
    packages = {}
    for path, entity in entities.items():
        if entity["kind"] == "module" and entity.get("is_package"):
            # a namespace package has no __init__.py: its folders are given, one per monorepo member
            folders = entity.get("folders") or [(root / entity["filepath"]).resolve().parent.relative_to(root).as_posix()]
            packages.update(dict.fromkeys(folders, path))
    wanted = [(file, language) for file in files if ".min." not in Path(file).name
              and (language := language_of(file)) not in (None, "python")]
    # only the languages read in full need a grammar; the others are shown as whole files
    parsers, errors = _parsers({grammar_of(file, language) for file, language in wanted if language in PACK_NAMES})
    missing = [{"language": language_label(language), "grammar": grammar, "error": errors[grammar],
                "files": sum(grammar_of(file, other) == grammar for file, other in wanted)}
               for grammar, language in sorted({(grammar_of(file, language), language) for file, language in wanted})
               if grammar in errors]
    wanted = [(file, language) for file, language in wanted if grammar_of(file, language) not in errors]
    found: dict[str, dict] = {}
    for index, (file_path, language) in enumerate(wanted):
        if on_file is not None:
            on_file(index, len(wanted))
        try:
            source = (root / file_path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        parent = _package_of(file_path, packages)
        label = FILE_LABELS.get(language, "file")
        grammar = grammar_of(file_path, language)
        members: list[dict] = []
        if language in PACK_NAMES:
            members = _members(file_path, language, grammar, source, parsers[grammar])
        found[file_path] = _entity(file_path, Path(file_path).name, "module", label, parent, file_path, language,
                                   1, source.count("\n") + 1, _file_comment(label, source), source,
                                   [member["path"] for member in members if member["parent"] == file_path])
        found.update((member["path"], member) for member in members)
        if parent in entities:
            entities[parent]["members"].append(file_path)
    return found, missing


def grammar_of(file: str, language: str) -> str:
    """The pack's grammar for a file of a language (`tsx` for TypeScript files with JSX)."""
    return "tsx" if file.endswith(".tsx") else PACK_NAMES.get(language, language)


def parser_for(root: Path, file: str, language: str) -> Parser | None:
    """A parser for a file, its grammar taken from `doc/grammars/`; `None` when it is not there."""
    pack.configure(pack.PackConfig(cache_dir=str(root.resolve() / GRAMMARS_DIR)))
    return _parsers({grammar_of(file, language)})[0].get(grammar_of(file, language))


def _parsers(grammars: set[str]) -> tuple[dict[str, Parser], dict[str, str]]:
    """A parser for each grammar, fetched into `doc/grammars/` when missing; the error of each that cannot be."""
    parsers, errors = {}, {}
    for grammar in sorted(grammars):
        try:
            parsers[grammar] = Parser(pack.get_language(grammar))
        except Exception as error:  # the pack raises its own errors (download, missing language)
            errors[grammar] = str(error)
    return parsers, errors


def _members(file: str, language: str, grammar: str, source: str, parser: Parser) -> list[dict]:
    """What a file defines, as entities, parents before their members."""
    tree = parser.parse(source.encode("utf-8"))
    comments = _comments(tree.root_node, source)
    if language == "css":
        return [_entity(f"{file}:{name}", name, "attribute", kind, file, file, language, first, last, comment, text)
                for name, kind, first, last, comment, text in _css_rules(tree.root_node)]
    if language == "html":
        return [_entity(f"{file}:{name}", name, "function", "macro", file, file, language, first, last, comment, text)
                for name, first, last, comment, text in _macros(source)]
    try:
        structure = pack.process(source, pack.ProcessConfig(language=grammar, structure=True, imports=False,
                                                            exports=False)).structure
    except Exception:  # a file the pack cannot process keeps no members
        return []
    found: list[dict] = []
    lines = source.splitlines()
    data = source.encode("utf-8")

    def add(item, parent: str) -> None:
        kind = str(item.kind)
        label = (json.loads(kind).popitem()[1] if kind.startswith("{") else kind).lower()
        if label in GROUPINGS:
            for child in item.children:
                add(child, parent)
            return
        if not item.name:
            return
        path = f"{parent}.{item.name}" if parent != file else f"{file}:{item.name}"
        if any(entity["path"] == path for entity in found):
            return  # an overload: the first one stands for the name
        first, last = item.span.start_line + 1, item.span.end_line + 1
        doc = _clean_comment(item.doc_comment or "") or _comment_above(comments, first)
        entity = _entity(path, item.name, CATEGORIES.get(label, "attribute"), label, parent, file, language,
                         first, last, doc, data[item.span.start_byte:item.span.end_byte].decode("utf-8", "replace"))
        entity["signature"] = " ".join((item.signature or lines[first - 1].strip().rstrip("{")).split())
        entity["is_private"] = (item.visibility or "") == "private"
        found.append(entity)
        for child in item.children:
            add(child, path)
        entity["members"] = [member["path"] for member in found if member["parent"] == path]

    for item in structure:
        add(item, file)
    return found


def _package_of(file: str, packages: dict[str, str]) -> str:
    """The nearest Python package holding a file (the deepest folder that is a package)."""
    folders = [folder for folder in packages if file.startswith(f"{folder}/")]
    return packages[max(folders, key=len)] if folders else ""


def _entity(path: str, name: str, kind: str, label: str, parent: str, filepath: str, language: str, lineno: int,
            endlineno: int, comment: str, text: str, members: list[str] | None = None) -> dict:
    """An entity of any language but Python, with every key of the Python ones (empty where the language
    gives nothing: bases, parameters, returns, annotation, value, exports, imports), so every page and
    graph serves it as it is."""
    return {"path": path, "name": name, "kind": kind, "kind_label": label, "parent": parent, "filepath": filepath,
            "lineno": lineno, "endlineno": endlineno, "is_private": False, "docstring": comment, "sections": [],
            "decorators": [], "members": members or [], "language": language, "search_text": text[:MAX_SEARCH_CHARS],
            "bases": [], "parameters": [], "returns": "", "annotation": "", "value": "", "exports": [], "imports": {}}


def _clean_comment(text: str) -> str:
    """The text of a comment in any language, without its markers (`//`, `///`, `/* */`, `#`, `--`,
    `{# #}`, `<!-- -->`) or the XML tags of C# doc comments."""
    lines = []
    for line in _DOC_TAGS.sub("", text).strip().splitlines():
        line = re.sub(r"^\s*(///?|/\*+|\*+/|\*|#+|--|\{#|<!--)", "", line)
        line = re.sub(r"(\*+/|#\}|-->)\s*$", "", line)
        lines.append(line.strip())
    return " ".join(line for line in lines if line)


def _comments(root: Node, source: str) -> dict[int, tuple[int, str]]:
    """The comments written on their own lines, by the line (from 1) they end on: `(first line, text)`."""
    lines = source.splitlines()
    found = {}
    for node in _walk(root):
        if "comment" not in node.type:
            continue
        row, column = node.start_point
        if row < len(lines) and lines[row][:column].strip():
            continue  # at the end of a line of code: it belongs to that code
        found[node.end_point[0] + 1] = (row + 1, node.text.decode("utf-8", "replace"))
    return found


def _comment_above(comments: dict[int, tuple[int, str]], line: int) -> str:
    """The comments right above line `line` (no blank line between), as text."""
    texts = []
    while line - 1 in comments:
        first, text = comments[line - 1]
        texts.insert(0, text)
        line = first
    return _clean_comment("\n".join(texts))


def _walk(node: Node):
    """Every node under a node, the node first."""
    yield node
    for child in node.children:
        yield from _walk(child)


def _css_rules(root: Node) -> list[tuple[str, str, int, int, str, str]]:
    """The classes a stylesheet styles, each with every rule naming it, and the rules naming no class.

    A rule naming no class (`main`, `#topbar`, `h2`) is known by its selectors; rules with the same
    selectors are one entity.

    Returns:
        `(".name" or selectors, "css class" or "css rule", first line, last line, the first comment
        above one of its rules, its rules with their comments)` for each, in order.
    """
    found: dict[str, list] = {}

    def add(name: str, kind: str, rule: Node) -> None:
        comment = _comments_before(rule)
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

    visit(root)
    return [(name, kind, first, last, comment, "\n".join(rules))
            for name, (kind, first, last, comment, rules) in found.items()]


def _comments_before(node: Node) -> str:
    """The comments written on their own lines right above a node among its siblings, as text."""
    comments, line = [], node.start_point[0]
    sibling = node.prev_named_sibling
    while sibling is not None and sibling.type == "comment" and sibling.end_point[0] >= line - 1:
        before = sibling.prev_sibling
        if before is not None and before.end_point[0] == sibling.start_point[0]:
            break
        comments.insert(0, sibling.text.decode("utf-8"))
        line = sibling.start_point[0]
        sibling = sibling.prev_named_sibling
    return _clean_comment("\n".join(comments))


def _macros(source: str) -> list[tuple[str, int, int, str, str]]:
    """The macros a template defines (nested ones too), read with Jinja2's parser.

    Returns:
        `(name, first line, last line, the {# comment #} right above it, its code)` for each.
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
        found.append((macro.name, first, last, _jinja_comment_above(lines, first), "\n".join(lines[first - 1: last])))
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
    return _clean_comment([match.group(0) for match in _JINJA_COMMENT.finditer(block)][-1] if "{#" in block else "")


def _file_comment(label: str, source: str) -> str:
    """The comment a file starts with: `{# #}` for templates, else the first comment lines of any language."""
    head = source.lstrip()
    if label == "template":
        if head.startswith("{%") and "import" in head.split("\n", 1)[0]:
            head = head.split("\n", 1)[1].lstrip() if "\n" in head else ""
        match = _JINJA_COMMENT.match(head)
        return _clean_comment(match.group(0)) if match else ""
    if head.startswith("/*"):
        end = head.find("*/")
        return _clean_comment(head[: end + 2]) if end != -1 else ""
    comments = []
    for line in head.splitlines():
        if not line.strip().startswith(("//", "#", "--")) or line.startswith("#!") or line.startswith("#include"):
            break
        comments.append(line)
    return _clean_comment("\n".join(comments))


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
        if entity.get("kind_label") not in ("template", "script"):
            continue
        try:
            source = (root / entity["filepath"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if entity["kind_label"] == "template":
            uses = _template_uses(path, source, registered, index)
        else:
            parser = parser_for(root, entity["filepath"], entity["language"])
            uses = _script_uses(path, parser.parse(source.encode("utf-8")).root_node, index) if parser else []
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
            label = entity.get("kind_label")
            if label == "css class":
                self.classes.setdefault(entity["name"][1:], []).append(path)
            elif entity["kind"] == "function" and entity["language"] in ("js", "typescript"):
                self.functions.setdefault(entity["name"], []).append(path)
            elif label == "template":
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
        """The innermost member of a file (macro, function, method) holding a line; the file itself otherwise."""
        inside, holding = list(self.entities[file]["members"]), []
        while inside:
            member = self.entities[inside.pop()]
            if member["lineno"] <= line <= member["endlineno"]:
                holding.append(member["path"])
                inside.extend(member["members"])
        return min(holding, default=file,
                   key=lambda member: self.entities[member]["endlineno"] - self.entities[member]["lineno"])

    def reachable(self, name: str, file: str, line: int) -> list[str]:
        """The JS functions a name at a line of a file can mean: the innermost one in scope there (one defined
        inside a function is reached only from within it), else the top-level ones of every script."""
        scoped = []
        for path in self.functions.get(name, []):
            entity = self.entities[path]
            holder = self.entities.get(entity["parent"], {})
            if entity["filepath"] == file and holder.get("kind") == "function":
                if holder["lineno"] <= line <= holder["endlineno"]:
                    scoped.append(path)
            elif entity["filepath"] == file and entity["parent"] == file:
                scoped.append(path)
        if scoped:
            return [max(scoped, key=lambda path: self.entities[self.entities[path]["parent"]]["lineno"]
                        if self.entities[path]["parent"] != file else 0)]
        return [path for path in self.functions.get(name, []) if self.entities[path]["parent"] == self.entities[path]["filepath"]]

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
                    for path in index.reachable(name, template, line))
    for match in _URL_ATTRIBUTE.finditer(source):
        uses.extend(index.url_use(match.group(2), _line(source, match.start())))
    return uses


def _script_uses(file: str, root: Node, index: _Index) -> list[tuple[int, str, str, str]]:
    """What a script (JavaScript or TypeScript, from its syntax tree) uses: `(line, target, kind, via)` for each use."""
    uses = []
    for node in _walk(root):
        line = node.start_point[0] + 1
        if node.type == "call_expression":
            called = node.child_by_field_name("function")
            if called is not None and called.type == "identifier":
                name = called.text.decode("utf-8")
                uses.extend((line, path, "calls", "") for path in index.reachable(name, file, line))
        elif node.type == "identifier" and node.parent is not None:
            # A function named without being called: a callback, a value in an object or a list.
            parent = node.parent
            called = parent.type == "call_expression" and parent.child_by_field_name("function") == node
            declared = parent.child_by_field_name("name") == node
            if not called and not declared:
                uses.extend((line, path, "refers", "") for path in index.reachable(node.text.decode("utf-8"), file, line))
        elif node.type in ("string", "template_string"):
            text = node.text.decode("utf-8")[1:-1]
            if text.startswith("/") and len(text) > 1:
                uses.extend(index.url_use(re.sub(r"\$\{[^}]*\}", "x", text), line))
            looks_like_selector = any(mark in text for mark in (".", "#", "[", ":", ">"))
            uses.extend(index.class_uses(text, line, selectors=looks_like_selector and "class=" not in text))
            for match in _CLASS_ATTRIBUTE.finditer(text):
                uses.extend(index.class_uses(match.group(2), line))
    return uses


NAME_NODES = {"identifier", "type_identifier", "field_identifier", "property_identifier", "name"}
"""Syntax nodes that name something, in the grammars of the pack; a name that is a definition is a use of it."""

BASE_NODES = {"superclass", "super_interfaces", "base_list", "extends_clause", "implements_clause",
              "class_heritage", "base_class_clause", "extends_type_clause", "class_interface_clause"}
"""Syntax nodes holding what a class extends or implements: a name in one is an `inherits` relation."""

FAMILIES = {"cpp": "c"}
"""Languages whose names reach each other's definitions (C++ calls C)."""


def code_edges(entities: dict[str, dict], root: Path) -> list[dict]:
    """Find what the code of every other language uses: the same relations as Python's, one pass for all.

    A name in the code that names a class or function of the same language is a use of it: `calls`
    when it is what a call or a `new` calls, `inherits` when it sits in what a class extends or
    implements, `refers` otherwise (e.g. a type, a table a foreign key points to). The definition
    meant is the one in scope in the same file, else one in a file it imports (`#include`,
    `require`, `import ... from`), else the only one with that name in the project. A file importing
    another `imports` it. JavaScript and TypeScript also get `frontend_edges`; CSS and HTML have
    their own.

    Args:
        entities: Every extracted entity, by path.
        root: Project root.

    Returns:
        `{"source", "target", "kind"}` relations, without duplicates.
    """
    index = _Index(entities, [])
    definitions: dict[tuple[str, str], list[str]] = {}
    files = {}
    for path, entity in entities.items():
        language = FAMILIES.get(entity["language"], entity["language"])
        if entity["language"] in PACK_NAMES and entity["language"] not in ("css", "html"):
            if entity["kind"] in ("class", "function"):
                definitions.setdefault((language, entity["name"]), []).append(path)
            elif entity["kind"] == "module":
                files[path] = entity
    found: set[tuple[str, str, str]] = set()
    imported: dict[str, set[str]] = {}
    trees = {}
    for path, entity in files.items():
        parser = parser_for(root, path, entity["language"])
        try:
            source = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if parser is not None:
            trees[path] = parser.parse(source.encode("utf-8")).root_node
            imported[path] = {target for target in _imported_files(path, trees[path], files)}
            found |= {(path, target, "imports") for target in imported[path] if target != path}
    for path, tree in trees.items():
        language = FAMILIES.get(files[path]["language"], files[path]["language"])
        if language in ("js", "typescript"):
            continue  # their names are read by `frontend_edges`, with the CSS classes and routes they use
        for node in _walk(tree):
            if node.type not in NAME_NODES:
                continue
            name = node.text.decode("utf-8", "replace")
            candidates = definitions.get((language, name))
            if not candidates:
                continue
            line = node.start_point[0] + 1
            target = _meant(candidates, path, line, imported.get(path, set()), entities)
            source_path = index.owner(path, line)
            if not target or target == source_path or target.startswith(f"{source_path}."):
                continue
            kind = _use_kind(node, entities[source_path])
            found.add((source_path, target, kind))
            header = entities[target]["filepath"]
            if language == "c" and header.endswith((".h", ".hpp")):  # the code of what a header declares
                found |= {(source_path, other, kind) for other in candidates
                          if other != target and header in imported.get(entities[other]["filepath"], set())}
    return [{"source": source, "target": target, "kind": kind} for source, target, kind in sorted(found)]


def _meant(candidates: list[str], file: str, line: int, imported: set[str], entities: dict[str, dict]) -> str | None:
    """The definition a name means at a line of a file: in scope in the file, else in an imported file,
    else the only one there is; `None` when it cannot be told."""
    here = [path for path in candidates if entities[path]["filepath"] == file]
    scoped = [path for path in here if entities[path]["parent"] == file
              or entities.get(entities[path]["parent"], {}).get("kind") == "class"
              or entities[entities[path]["parent"]]["lineno"] <= line <= entities[entities[path]["parent"]]["endlineno"]]
    if scoped:
        return max(scoped, key=lambda path: entities[path]["lineno"] if entities[path]["lineno"] <= line else -1)
    from_imports = [path for path in candidates if entities[path]["filepath"] in imported]
    if len(from_imports) == 1:
        return from_imports[0]
    return candidates[0] if len(candidates) == 1 else None


def _use_kind(node: Node, owner: dict) -> str:
    """How a name is used: `inherits` in what a class extends, `calls` as what is called, else `refers`."""
    parent = node.parent
    for _ in range(3):
        if parent is None:
            break
        if parent.type in BASE_NODES and owner["kind"] == "class":
            return "inherits"
        if any(word in parent.type for word in ("call", "invocation", "creation", "new_expression")):
            arguments = parent.child_by_field_name("arguments")
            if arguments is None or not (arguments.start_byte <= node.start_byte < arguments.end_byte):
                return "calls"
            break
        parent = parent.parent
    return "refers"


def _imported_files(file: str, tree: Node, files: dict[str, dict]) -> list[str]:
    """The project files a file imports by path: `#include "x.h"`, `require '../x.php'`, `import ... from './x'`."""
    found = []
    folder = Path(file).parent
    for node in _walk(tree):
        if not any(word in node.type for word in ("include", "require", "import")):
            continue
        for part in _walk(node):
            if part.type not in ("string_literal", "string", "string_fragment", "system_lib_string", "string_content"):
                continue
            text = part.text.decode("utf-8", "replace").strip("\"'<>")
            if not text or "/" not in text and "." not in text:
                continue
            target = _project_file(folder, text, files)
            if target:
                found.append(target)
    return found


def _project_file(folder: Path, text: str, files: dict[str, dict]) -> str | None:
    """The project file an import's path names: relative to the importing file, else the only file ending so."""
    for suffix in ("", ".js", ".ts", ".tsx", "/index.js", "/index.ts"):
        candidate = (folder / (text + suffix)).as_posix()
        parts: list[str] = []
        for part in candidate.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part not in (".", ""):
                parts.append(part)
        if "/".join(parts) in files:
            return "/".join(parts)
    tail = text.lstrip("./")
    ending = [path for path in files if path == tail or path.endswith(f"/{tail}")]
    return ending[0] if len(ending) == 1 else None
