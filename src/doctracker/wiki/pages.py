"""Turn extracted entities into the data the wiki templates display."""

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
# Only the token spans: the template provides <pre><code>, the CSS provides the colors.
_formatter = HtmlFormatter(nowrap=True)
_python = PythonLexer()
_console = PythonConsoleLexer()

# Order and labels of member groups on module and class pages.
GROUPS = (
    ("module", "Modules"),
    ("class", "Classes"),
    ("function", "Functions"),
    ("attribute", "Attributes"),
    ("type alias", "Type aliases"),
)


def render_markdown(text: str) -> str:
    """Render docstring text as HTML (raw HTML in docstrings is escaped)."""
    return _markdown.render(text or "")


CODE_THEMES = sorted(get_all_styles())


SOURCE_SELECTOR = ".block-source .code-block"


def code_theme_css(name: str) -> str:
    """CSS for one Pygments theme, applied only to the Source block, with its text and background colors."""
    style = get_style_by_name(name)
    text = style.style_for_token(Token.Text)["color"] or ("dddddd" if _is_dark(style.background_color) else "1f2328")
    rules = HtmlFormatter(style=name).get_style_defs(SOURCE_SELECTOR)
    # Pygments also emits unscoped rules (e.g. `pre { ... }`); keep only the Source ones.
    scoped = "\n".join(line for line in rules.splitlines() if line.startswith(SOURCE_SELECTOR))
    return f"{SOURCE_SELECTOR} {{ color: #{text}; background: {style.background_color}; }}\n{scoped}\n"


def _is_dark(color: str) -> bool:
    color = (color or "#ffffff").lstrip("#")
    if len(color) == 3:
        color = "".join(c * 2 for c in color)
    red, green, blue = (int(color[i : i + 2], 16) for i in (0, 2, 4))
    return red * 0.299 + green * 0.587 + blue * 0.114 < 128


def highlight(code: str) -> Markup:
    """Python code as HTML with syntax highlighting. `>>>` sessions use the console lexer."""
    lexer = _console if code.lstrip().startswith(">>>") else _python
    return Markup(pygments_highlight(code, lexer, _formatter).rstrip("\n"))


def signature(entity: dict) -> str:
    """One-line signature of a function, class or attribute."""
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
    """First line of the docstring."""
    return entity["docstring"].strip().split("\n", 1)[0] if entity["docstring"] else ""


# Symbol shown before each item, by role (packages and modules use folder/file icons).
SYMBOLS = {"class": "C", "function": "f", "method": "m", "attribute": "a", "type alias": "t"}


def tree(state: DocState, current: str) -> list[dict]:
    """Navigation tree: packages and modules, with their classes, functions and methods."""
    return [_tree_node(state, path, current, "package") for path in state.roots if path in state.entities]


def _tree_node(state: DocState, path: str, current: str, role: str) -> dict:
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
        "open": current == path or current.startswith(path + "."),
    }


def _role(parent: dict, member: dict) -> str:
    """Role of a member in the tree: subpackage, module, class, function or method."""
    if member["kind"] == "module" and member.get("is_package"):
        return "subpackage"
    if member["kind"] == "function" and parent["kind"] == "class":
        return "method"
    return member["kind"]


def members_by_group(state: DocState, entity: dict) -> list[dict]:
    """Members of a module or class, grouped by kind, each ready to be shown as one row.

    Attributes without a docstring of their own take the description from the
    parent's `Attributes` docstring section.
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
    """The part of the signature after the name: `(params) -> type`, `(bases)` or `: type = value`."""
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
    """Role of the entity shown on a page, used for its icon: package, subpackage, module, class..."""
    if entity["path"] in state.roots:
        return "package"
    parent = state.entities.get(entity["parent"] or "")
    return _role(parent, entity) if parent else entity["kind"]


def parameter_rows(entity: dict) -> list[dict]:
    """Parameters table: signature data merged with descriptions from the docstring."""
    described = {}
    for section in entity["sections"]:
        if section["kind"] in ("parameters", "other parameters"):
            for item in section["items"]:
                described[item["name"].lstrip("*")] = item
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
    """First line of each attribute description in the `Attributes` docstring section."""
    descriptions = {}
    for section in entity["sections"]:
        if section["kind"] == "attributes":
            for item in section["items"]:
                descriptions[item["name"]] = item["description"].strip().split("\n", 1)[0]
    return descriptions


def other_sections(entity: dict) -> list[dict]:
    """Docstring sections not shown elsewhere on the page.

    Parameters have their own table; on modules and classes, documented attributes
    are merged into the members list.
    """
    hidden = {"parameters", "other parameters"}
    if entity["kind"] in ("module", "class"):
        hidden.add("attributes")
    return [section for section in entity["sections"] if section["kind"] not in hidden]


def breadcrumbs(state: DocState, path: str) -> list[dict]:
    """Links to the parents of an entity, from the root package down."""
    crumbs = []
    parent = state.entities[path]["parent"]
    while parent and parent in state.entities:
        crumbs.insert(0, {"path": parent, "name": state.entities[parent]["name"]})
        parent = state.entities[parent]["parent"]
    return crumbs


SNIPPET_CONTEXT = 40


def search(state: DocState, query: str, limit: int = 12) -> list[dict]:
    """Entities matching `query`, best first.

    Order: exact name, name prefix, name contains, path contains, description contains.
    The description is the docstring plus the descriptions of its parameters, returns,
    raises and other sections.
    """
    query = query.strip().lower()
    if not query:
        return []
    scored = []
    for path, entity in state.entities.items():
        name = entity["name"].lower()
        if name == query:
            score = 0
        elif name.startswith(query):
            score = 1
        elif query in name:
            score = 2
        elif query in path.lower():
            score = 3
        elif query in _description_text(entity).lower():
            score = 4
        else:
            continue
        scored.append((score, len(path), path))
    results = []
    for score, _, path in sorted(scored)[:limit]:
        entity = state.entities[path]
        parent = state.entities.get(entity["parent"] or "")
        role = "package" if path in state.roots else (_role(parent, entity) if parent else entity["kind"])
        name_parts = _split_match(entity["name"], query)
        result = {
            "path": path,
            "role": role,
            "symbol": SYMBOLS.get(role, ""),
            "name": entity["name"],
            # Name split around the first match, to highlight it.
            "before": name_parts[0],
            "match": name_parts[1],
            "after": name_parts[2],
            "snippet": None,
        }
        if score == 4:
            result["snippet"] = _snippet(_description_text(entity), query)
        results.append(result)
    return results


def _description_text(entity: dict) -> str:
    """All the descriptive text of an entity, as one line (parsed sections, without their headings)."""
    parts = [] if entity["sections"] else [entity["docstring"]]
    for section in entity["sections"]:
        parts.append(section["text"])
        parts.extend(item["description"] for item in section["items"])
    return " ".join(" ".join(part.split()) for part in parts if part)


def _split_match(text: str, query: str) -> tuple[str, str, str]:
    """`text` split as (before, match, after) around the first case-insensitive match."""
    start = text.lower().find(query)
    if start < 0:
        return text, "", ""
    return text[:start], text[start : start + len(query)], text[start + len(query) :]


def _snippet(text: str, query: str) -> dict:
    """A short piece of `text` around the first match, split for highlighting."""
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
    """Source lines of an entity, read from disk when the user asks for them."""
    if not entity["filepath"] or not entity["lineno"]:
        return ""
    path = (project_root / entity["filepath"]).resolve()
    if not path.is_relative_to(project_root.resolve()):
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    end = entity["endlineno"] or entity["lineno"]
    return "\n".join(lines[entity["lineno"] - 1 : end])
