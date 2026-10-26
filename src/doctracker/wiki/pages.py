"""Turn extracted entities into the data the wiki templates display."""

import re
from datetime import datetime
from pathlib import Path

from markdown_it import MarkdownIt
from markupsafe import Markup
from pygments import highlight as pygments_highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import PythonConsoleLexer, PythonLexer
from pygments.styles import get_all_styles, get_style_by_name
from pygments.token import Token

from doctracker.server.state import DocState

_markdown = MarkdownIt("commonmark", {"html": False})
"""Markdown renderer for docstrings; raw HTML is disabled, so it is escaped."""

_commit_markdown = MarkdownIt("commonmark", {"html": False}).disable("emphasis")
"""Markdown renderer for commit messages: no emphasis, so names like `__init__` stay as written."""

_formatter = HtmlFormatter(nowrap=True)
"""Outputs only the token spans: the template provides `<pre><code>`, the CSS provides the colors."""

_python = PythonLexer()
"""Lexer for Python source code."""

_console = PythonConsoleLexer()
"""Lexer for interactive sessions (`>>>` examples)."""

GROUPS = (
    ("module", "Modules"),
    ("class", "Classes"),
    ("function", "Functions"),
    ("attribute", "Attributes"),
    ("type alias", "Type aliases"),
)
"""Order and labels of the member groups on module and class pages, as `(kind, label)`."""


def render_markdown(text: str) -> str:
    """Render docstring text (Markdown) as HTML; raw HTML in docstrings is escaped.

    Args:
        text: Markdown text; empty or `None` gives an empty string.

    Returns:
        The HTML.
    """
    return _markdown.render(text or "")


def render_commit_message(text: str) -> str:
    """Render a commit message body as HTML: lines wrapped by git join into paragraphs, `-` items into lists.

    Args:
        text: The body; empty or `None` gives an empty string.

    Returns:
        The HTML; raw HTML in the message is escaped.
    """
    return _commit_markdown.render(text or "")


def local_time(stamp: str) -> str:
    """Show an ISO 8601 date-time in this machine's time zone, to the minute (e.g. `2026-10-26 13:35`).

    Notes are stored in UTC and commits carry their author's offset; both are shown as local time.

    Args:
        stamp: The date-time, e.g. `2026-10-26T16:35:00+00:00`.

    Returns:
        The local date and time; the text as it is when it is not a date-time.
    """
    try:
        moment = datetime.fromisoformat(stamp)
    except (TypeError, ValueError):
        return stamp or ""
    return (moment.astimezone() if moment.tzinfo else moment).strftime("%Y-%m-%d %H:%M")


CODE_THEMES = sorted(get_all_styles())
"""Names of every Pygments theme, offered in the "Code theme" select of the Source block."""


SOURCE_SELECTOR = ".block-source .code-block"
"""CSS selector the code theme applies to: only the source code, not signatures or examples."""


def code_theme_css(name: str) -> str:
    """Build the CSS of one Pygments theme, applied only to the Source block.

    Args:
        name: Theme name, one of `CODE_THEMES`.

    Returns:
        Rules for the theme's tokens plus its text and background colors, all scoped to `SOURCE_SELECTOR`.
    """
    style = get_style_by_name(name)
    text = style.style_for_token(Token.Text)["color"] or ("dddddd" if _is_dark(style.background_color) else "1f2328")
    rules = HtmlFormatter(style=name).get_style_defs(SOURCE_SELECTOR)
    # Pygments also emits unscoped rules (e.g. `pre { ... }`); keep only the Source ones.
    scoped = "\n".join(line for line in rules.splitlines() if line.startswith(SOURCE_SELECTOR))
    return f"{SOURCE_SELECTOR} {{ color: #{text}; background: {style.background_color}; }}\n{scoped}\n"


def _is_dark(color: str) -> bool:
    """Tell whether a background color is dark, to pick a readable default text color.

    Args:
        color: Hex color such as `#272822` or `#fff`; empty means white.

    Returns:
        True when the perceived brightness is below half.
    """
    color = (color or "#ffffff").lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    red, green, blue = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    return red * 0.299 + green * 0.587 + blue * 0.114 < 128


def highlight(code: str) -> Markup:
    """Turn Python code into HTML with syntax highlighting.

    Args:
        code: Python source, or an interactive session starting with `>>>` (console lexer).

    Returns:
        Token spans with Pygments classes, safe to insert in a template.
    """
    lexer = _console if code.lstrip().startswith(">>>") else _python
    return Markup(pygments_highlight(code, lexer, _formatter).rstrip("\n"))


def signature(entity: dict) -> str:
    """Write the one-line signature of a function, class or attribute.

    Args:
        entity: Extracted entity.

    Returns:
        `def name(params) -> type`, `class Name(bases)`, `name: type = value`, or the path for modules.
    """
    kind = entity["kind"]
    if kind == "function":
        result = f"def {entity['name']}({_parameters(entity['parameters'])})"
        if entity["returns"]:
            result += f" -> {entity['returns']}"
        return result
    if kind == "class":
        bases = f"({', '.join(entity['bases'])})" if entity["bases"] else ""
        return f"class {entity['name']}{bases}"
    if kind == "attribute":
        result = entity["name"]
        if entity["annotation"]:
            result += f": {entity['annotation']}"
        if entity["value"]:
            result += f" = {entity['value']}"
        return result
    return entity["path"]


def _parameters(parameters: list[dict]) -> str:
    """Write a parameter list as in Python source, with the `/` and `*` markers where they belong.

    Args:
        parameters: Parameters of a function, in order.

    Returns:
        The list without the parentheses, e.g. `x: int, /, *, flag: bool = False`.
    """
    parts = []
    keyword_only_marked = False
    for index, parameter in enumerate(parameters):
        kind = parameter["kind"]
        text = parameter["name"]
        if parameter["annotation"]:
            text += f": {parameter['annotation']}"
        if parameter["default"]:
            text += f" = {parameter['default']}" if parameter["annotation"] else f"={parameter['default']}"
        if kind == "variadic positional":
            text = "*" + text
            keyword_only_marked = True
        elif kind == "variadic keyword":
            text = "**" + text
        elif kind == "keyword-only" and not keyword_only_marked:
            parts.append("*")
            keyword_only_marked = True
        parts.append(text)
        next_kind = parameters[index + 1]["kind"] if index + 1 < len(parameters) else None
        if kind == "positional-only" and next_kind != "positional-only":
            parts.append("/")
    return ", ".join(parts)


def summary(entity: dict) -> str:
    """Get the summary of an entity: the first line of its docstring.

    Args:
        entity: Extracted entity.

    Returns:
        The first line, or an empty string without a docstring.
    """
    return _first_line(entity["docstring"])


def _first_line(text: str) -> str:
    """Get the first line of a text, without surrounding blanks.

    Args:
        text: Docstring or description; empty gives an empty string.

    Returns:
        The first line.
    """
    return text.strip().split("\n", 1)[0] if text else ""


def _section_items(entity: dict, kinds: tuple[str, ...]) -> list[dict]:
    """Collect the items of the docstring sections of the given kinds, in docstring order.

    Args:
        entity: Extracted entity.
        kinds: Section kinds, e.g. `("parameters", "other parameters")` or `("attributes",)`.

    Returns:
        The items (name, annotation, description) of every matching section.
    """
    return [item for section in entity["sections"] if section["kind"] in kinds for item in section["items"]]


SYMBOLS = {"class": "C", "function": "f", "method": "m", "attribute": "a", "type alias": "t"}
"""Symbol shown before each item in the tree and on pages, by role (packages and modules use folder/file icons)."""


def tree(state: DocState, current: str) -> list[dict]:
    """Build the navigation tree: packages and modules, with their classes, functions and methods.

    Args:
        state: Extracted entities.
        current: Path of the page being shown; its item is marked.

    Returns:
        One node per root package, with nested `children`.
    """
    return [_tree_node(state, path, current, "package") for path in state.roots if path in state.entities]


def _tree_node(state: DocState, path: str, current: str, role: str) -> dict:
    """Build one node of the navigation tree and, recursively, its children.

    Args:
        state: Extracted entities.
        path: Entity of this node.
        current: Path of the page being shown.
        role: Role of this node (`package`, `subpackage`, `module`, `class`, `function`, `method`).

    Returns:
        Path, name, role, symbol, children, and whether it is the current page.
    """
    entity = state.entities[path]
    children = []
    for member_path in entity["members"]:
        member = state.entities.get(member_path)
        if member and member["kind"] in ("module", "class", "function"):
            children.append(_tree_node(state, member_path, current, _role(entity, member)))
    return {
        "path": path,
        "name": entity["name"],
        "role": role,
        "symbol": SYMBOLS.get(role, ""),
        "children": children,
        "current": path == current,
    }


def _role(parent: dict, member: dict) -> str:
    """Tell the role of a member: subpackage, module, class, function or method.

    Args:
        parent: Entity that contains the member.
        member: The member.

    Returns:
        `subpackage` for packages inside packages, `method` for functions inside classes, otherwise its kind.
    """
    if member["kind"] == "module" and member.get("is_package"):
        return "subpackage"
    if member["kind"] == "function" and parent["kind"] == "class":
        return "method"
    return member["kind"]


def members_by_group(state: DocState, entity: dict) -> list[dict]:
    """Members of a module or class, grouped by kind, each ready to be shown as one row.

    Attributes without a docstring of their own take the description from the
    parent's `Attributes` docstring section.

    Args:
        state: Extracted entities.
        entity: Module or class whose members are listed.

    Returns:
        Groups in `GROUPS` order (functions of a class are labeled "Methods"), each with
        its role and its rows: path, name, role, symbol, signature details and summary.
    """
    documented = _documented_attributes(entity)
    groups = []
    for kind, label in GROUPS:
        items = []
        for member_path in entity["members"]:
            member = state.entities.get(member_path)
            if member and member["kind"] == kind:
                role = _role(entity, member)
                items.append(
                    {
                        "path": member["path"],
                        "name": member["name"],
                        "role": role,
                        "symbol": SYMBOLS.get(role, ""),
                        "details": signature_details(member),
                        "summary": summary(member) or documented.get(member["name"], ""),
                    }
                )
        if items:
            is_method = entity["kind"] == "class" and kind == "function"
            groups.append(
                {
                    "label": "Methods" if is_method else label,
                    "role": "method" if is_method else items[0]["role"],
                    "items": items,
                }
            )
    return groups


def signature_details(entity: dict) -> str:
    """Get the part of the signature after the name, shown muted next to the name in member lists.

    Args:
        entity: Extracted entity.

    Returns:
        `(params) -> type`, `(bases)`, `: type = value`, or an empty string for modules.
    """
    full = signature(entity)
    kind = entity["kind"]
    if kind == "function":
        return full.removeprefix(f"def {entity['name']}")
    if kind == "class":
        return full.removeprefix(f"class {entity['name']}")
    if kind == "attribute":
        return full.removeprefix(entity["name"])
    return ""


def page_role(state: DocState, entity: dict) -> str:
    """Tell the role of the entity shown on a page, used for its icon and badge colors.

    Args:
        state: Extracted entities.
        entity: Entity of the page.

    Returns:
        `package` for root packages, otherwise its role inside its parent (see `_role`).
    """
    if entity["path"] in state.roots:
        return "package"
    parent = state.entities.get(entity["parent"] or "")
    return _role(parent, entity) if parent else entity["kind"]


def parameter_rows(entity: dict) -> list[dict]:
    """Build the parameters table: signature data merged with descriptions from the docstring.

    For classes, parameters not described in `Args` take the description of the
    attribute with the same name, so dataclass fields documented in `Attributes`
    also appear in the table.

    Args:
        entity: Function, method or class (whose parameters are those of `__init__`).

    Returns:
        One row per parameter (without `self`/`cls`): name, annotation, default and description.
    """
    described = {item["name"].lstrip("*"): item for item in _section_items(entity, ("parameters", "other parameters"))}
    if entity["kind"] == "class":
        for item in _section_items(entity, ("attributes",)):
            described.setdefault(item["name"], item)
    rows = []
    for parameter in entity.get("parameters", []):
        if parameter["name"] in ("self", "cls"):
            continue
        doc = described.get(parameter["name"], {})
        rows.append(
            {
                "name": parameter["name"],
                "annotation": parameter["annotation"] or doc.get("annotation", ""),
                "default": parameter["default"],
                "description": doc.get("description", ""),
            }
        )
    return rows


def _documented_attributes(entity: dict) -> dict[str, str]:
    """Collect the first line of each attribute description in the `Attributes` docstring section.

    Args:
        entity: Module or class.

    Returns:
        Description by attribute name.
    """
    return {item["name"]: _first_line(item["description"]) for item in _section_items(entity, ("attributes",))}


def other_sections(entity: dict) -> list[dict]:
    """Docstring sections not shown elsewhere on the page.

    Parameters have their own table; on modules and classes, documented attributes
    are merged into the members list.

    Args:
        entity: Extracted entity.

    Returns:
        The remaining sections, in docstring order.
    """
    hidden = {"parameters", "other parameters"}
    if entity["kind"] in ("module", "class"):
        hidden.add("attributes")
    return [section for section in entity["sections"] if section["kind"] not in hidden]


def breadcrumbs(state: DocState, path: str) -> list[dict]:
    """List the parents of an entity, from the root package down, for the page's breadcrumbs.

    Args:
        state: Extracted entities.
        path: Entity of the page.

    Returns:
        Path and name of each parent.
    """
    crumbs = []
    parent = state.entities[path]["parent"]
    while parent and parent in state.entities:
        crumbs.insert(0, {"path": parent, "name": state.entities[parent]["name"]})
        parent = state.entities[parent]["parent"]
    return crumbs


SNIPPET_CONTEXT = 40
"""Characters of description shown on each side of a match in search results."""


def ranked_results(state: DocState, ranked: list[tuple[str, float]], query: str) -> list[dict]:
    """Turn search results (any mode) into the rows of the search box.

    The name and a description snippet are highlighted around the typed text, or,
    when it is not found as a whole, around the first query word found. Semantic
    matches may share no word with the query; then the summary is shown instead.

    Args:
        state: Extracted entities.
        ranked: `(path, score)` pairs, best first, from `SearchEngine`.
        query: Text typed in the search box.

    Returns:
        Rows with path, role, symbol, highlighted name, snippet and score; entities that
        no longer exist are skipped.
    """
    phrase = query.strip().lower()
    terms = [phrase] + [word for word in re.findall(r"[a-z0-9]+", phrase) if len(word) > 1]
    results = []
    for path, score in ranked:
        entity = state.entities.get(path)
        if entity is None:
            continue
        role = page_role(state, entity)
        name_term = next((term for term in terms if term and term in entity["name"].lower()), "")
        before, match, after = _split_match(entity["name"], name_term) if name_term else (entity["name"], "", "")
        description = description_text(entity)
        text_term = next((term for term in terms if term and term in description.lower()), "")
        if name_term and name_term == text_term == phrase:
            snippet = None  # the name already shows the match
        elif text_term:
            snippet = _snippet(description, text_term)
        else:
            snippet = {"before": summary(entity), "match": "", "after": ""} if summary(entity) else None
        results.append(
            {
                "path": path,
                "role": role,
                "symbol": SYMBOLS.get(role, ""),
                "before": before,
                "match": match,
                "after": after,
                "snippet": snippet,
                "score": score,
            }
        )
    return results


def class_packages(state: DocState) -> list[str]:
    """List the packages and modules that contain classes, for the filter of the class diagram.

    Args:
        state: Extracted entities.

    Returns:
        Sorted paths of every package or module with at least one class below it.
    """
    found = set()
    for path, entity in state.entities.items():
        if entity["kind"] == "class":
            parent = entity["parent"]
            while parent in state.entities:
                if state.entities[parent]["kind"] == "module":
                    found.add(parent)
                parent = state.entities[parent]["parent"]
    return sorted(found)


def call_targets(state: DocState) -> list[str]:
    """List the entities a call graph can be centered on: functions, methods and classes.

    Args:
        state: Extracted entities.

    Returns:
        Their paths, sorted.
    """
    return sorted(path for path, entity in state.entities.items() if entity["kind"] in ("function", "class"))


PAGINATION_SIBLINGS = 1
"""Page numbers shown on each side of the current page in the search pagination."""


def pagination(total: int, offset: int, limit: int) -> dict | None:
    """Build the page buttons of the search box (MUI `Pagination` style: `‹ 1 … 4 5 6 … 9 ›`).

    The first and last pages are always shown, plus `PAGINATION_SIBLINGS` pages on
    each side of the current one; gaps become an ellipsis.

    Args:
        total: Results across all pages.
        offset: Position of the first result of the current page.
        limit: Results per page.

    Returns:
        `current`, `count`, `previous` and `next` page numbers (`None` at the ends), `pages`
        (numbers, with `None` for an ellipsis), and `first`, `last`, `total` for the
        "11–20 of 87" label; `None` when everything fits in one page.
    """
    count = -(-total // limit) if limit else 0
    if count <= 1:
        return None
    current = offset // limit + 1
    shown = {1, count} | set(range(current - PAGINATION_SIBLINGS, current + PAGINATION_SIBLINGS + 1))
    pages: list[int | None] = []
    for number in sorted(n for n in shown if 1 <= n <= count):
        if pages and number - pages[-1] > 1:
            pages.append(None)
        pages.append(number)
    return {
        "current": current,
        "count": count,
        "previous": current - 1 if current > 1 else None,
        "next": current + 1 if current < count else None,
        "pages": pages,
        "first": offset + 1,
        "last": min(offset + limit, total),
        "total": total,
    }


def description_text(entity: dict) -> str:
    """Join all the descriptive text of an entity in one line, without section headings.

    Used by the search box and by the semantic search index.

    Args:
        entity: Extracted entity.

    Returns:
        Text of the parsed docstring sections (or the raw docstring when nothing was parsed).
    """
    parts = [] if entity["sections"] else [entity["docstring"]]
    for section in entity["sections"]:
        parts.append(section["text"])
        parts.extend(item["description"] for item in section["items"])
    return " ".join(" ".join(part.split()) for part in parts if part)


def _split_match(text: str, query: str) -> tuple[str, str, str]:
    """Split `text` around the first case-insensitive match of `query`, to highlight it.

    Args:
        text: Text to split.
        query: Lowercase text to find.

    Returns:
        `(before, match, after)`; `(text, "", "")` when there is no match.
    """
    start = text.lower().find(query)
    if start < 0:
        return text, "", ""
    return text[:start], text[start : start + len(query)], text[start + len(query) :]


def _snippet(text: str, query: str) -> dict:
    """Cut a short piece of `text` around the first match, for a search result.

    Args:
        text: Description that contains `query`.
        query: Lowercase text that was found.

    Returns:
        `before`, `match` and `after`, with "…" where the text was cut.
    """
    start = text.lower().find(query)
    left = max(0, start - SNIPPET_CONTEXT)
    right = min(len(text), start + len(query) + SNIPPET_CONTEXT)
    before, match, after = _split_match(text[left:right], query)
    return {
        "before": ("…" if left > 0 else "") + before,
        "match": match,
        "after": after + ("…" if right < len(text) else ""),
    }


def source_code(project_root: Path, entity: dict) -> str:
    """Read the source lines of an entity from disk, when the Source block asks for them.

    Args:
        project_root: Root of the documented project; files outside it are never read.
        entity: Extracted entity, with its file and line numbers.

    Returns:
        The lines of the entity, or an empty string when the location is unknown or outside the project.
    """
    if not entity["filepath"] or not entity["lineno"]:
        return ""
    path = (project_root / entity["filepath"]).resolve()
    if not path.is_relative_to(project_root.resolve()):
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    end = entity["endlineno"] or entity["lineno"]
    return "\n".join(lines[entity["lineno"] - 1 : end])
