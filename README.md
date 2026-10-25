# DOCUMENTATION TRACKER (DOCTRACKER)

**One place for the documentation of a Python project developed with LLM agents.**

When agents work on a codebase, documentation ends up scattered: notes in many
Markdown files, memories, code comments and commit messages, all drifting out of
sync. Documentation Tracker (doctracker) centralizes it. It runs an [MCP](https://modelcontextprotocol.io)
server that any agent (Claude Code, OpenCode, …) can connect to, and serves a live
wiki of the project in your browser.

> **Status: alpha (0.1).** This first version builds the technical reference of the
> code. Notes, commit history and LLM summaries come in the next versions (see
> [Roadmap](#roadmap)).

## Features

- **Technical reference built from the code** — modules, classes, functions,
  methods and attributes, with signatures, type hints, decorators and parsed
  docstrings (Google, NumPy or Sphinx style).
- **Static analysis only** — the code is read with [griffe](https://mkdocstrings.github.io/griffe/),
  never imported or executed.
- **Live wiki** — edit a file and the open page updates by itself.
- **MCP server** — agents can list and read the documentation, and get a guide on
  how to document the code so the wiki stays complete.
- **Search** — by name, path and description, with keyboard navigation.
- **Everything in one folder** — doctracker keeps its files in `doc/` inside your
  project and never touches anything else.
- **Cross-platform** — Windows and Linux, Python 3.11+.

## Installation

Install it as a development dependency of the project you want to document:

```bash
uv add --dev doctracker
```

or with pip:

```bash
pip install doctracker
```

## Quick start

From the root of your project:

```bash
doctracker init     # creates doc/config/config.json (packages are detected automatically)
doctracker start    # starts the server
```

With uv, prefix the commands with `uv run` (e.g. `uv run doctracker start`).
`start` runs `init` on its own if the project has no configuration yet.

The server prints its two addresses:

```text
Wiki: http://127.0.0.1:8765/
MCP:  http://127.0.0.1:8765/mcp
```

Open the wiki in your browser. Keep the server running while you work on the code;
stop it with `Ctrl+C`.

## Connecting an agent

The MCP server uses the Streamable HTTP transport at `http://127.0.0.1:8765/mcp`.
The server must be running before the agent connects.

**Claude Code** — add a `.mcp.json` file at the root of your project:

```json
{
  "mcpServers": {
    "doctracker": { "type": "http", "url": "http://127.0.0.1:8765/mcp" }
  }
}
```

or register it from the terminal:

```bash
claude mcp add --transport http doctracker http://127.0.0.1:8765/mcp
```

**OpenCode** — in `opencode.json`:

```json
{
  "mcp": {
    "doctracker": { "type": "remote", "url": "http://127.0.0.1:8765/mcp" }
  }
}
```

**Other agents** — any MCP client that supports Streamable HTTP can connect to the
same URL.

### What the agent gets

| Name | Kind | What it does |
| --- | --- | --- |
| `list_entities` | tool | Lists documented entities, filtered by path prefix and kind. |
| `get_entity` | tool | Full technical reference of one entity. |
| `status` | tool | Whether the documentation is built, and loading errors. |
| `documentation_guide` | tool | How to document this project's code (adapted to its settings). |
| `doctracker://guide` | resource | The same guide, as a Markdown resource. |

The server's instructions tell the agent to read the guide before writing or
changing docstrings.

## The wiki

- **Tree** — packages (📦/📁), modules (📄), classes (**C**), functions (**f**) and
  methods (**m**). Branches collapse; the tree can be resized or hidden (☰).
- **Module pages** — description, public API (`__all__`) and members grouped by kind.
- **Entity pages** — description, signature, parameters table, returns, raises,
  examples, notes, members (for classes) and the source code with syntax
  highlighting. Every section can be collapsed from its badge.
- **Code theme** — choose among the Pygments themes in the Source section; the
  choice is saved in `config.json`.
- **Search** — press `/` anywhere, type, use ↑/↓ and Enter.

## Configuration

`doc/config/config.json` (created by `doctracker init`):

| Key | Default | Description |
| --- | --- | --- |
| `packages` | detected | Top-level packages to document. |
| `search_paths` | `["src", "."]` | Folders where the packages are found, relative to the project root. |
| `host` | `"127.0.0.1"` | Address the server listens on. |
| `port` | `8765` | Port of the server (also `doctracker start --port`). |
| `docstring_style` | `"google"` | `google`, `numpy` or `sphinx`. |
| `show_private` | `true` | Show `_private` members. |
| `code_theme` | `"default"` | Pygments theme of the source code. |
| `ssl_certfile` / `ssl_keyfile` | `null` | Certificate and key files; when both are set, the server uses HTTPS. |
| `watch_interval` | `1.0` | Seconds between checks for changed files. |

### The `doc/` folder

```text
doc/
├── .gitignore        # keeps local data out of git
└── config/
    └── config.json   # commit this file
```

Other folders (local data, models) are created only when a feature needs them, and
are ignored by `doc/.gitignore`.

## Documenting your code

doctracker shows what the code says, so the wiki is as good as the docstrings. In
short:

- a docstring for every module, public class, function and method;
- the first line is a one-sentence summary (it is used in lists and search);
- type hints on every parameter and return value;
- `Args`, `Returns`, `Raises`, `Attributes` and `Examples` sections as needed;
- constants documented with a string on the line after the assignment.

```python
def get_weather(city: str, units: str = "metric") -> Forecast:
    """Fetch the forecast for a city.

    Args:
        city: City name, e.g. `Lisbon`.
        units: `metric` or `imperial`.

    Returns:
        Forecast data for the city.

    Raises:
        CityNotFound: When the city is unknown.
    """
```

Agents get the complete guide from the `documentation_guide` tool.

## Security

- By default the server listens only on `127.0.0.1`, and the MCP endpoint
  validates the `Host` and `Origin` headers (protection against DNS rebinding).
- The wiki only accepts changes (such as the code theme) from its own pages.
- Exposing the server on a network is not supported yet: there is no
  authentication in this version.

## Roadmap

- Notes recorded by the agent through the MCP server, turned into atomic commits.
- Commit history linked to each function and class, with LLM summaries
  (llama.cpp or vLLM).
- Knowledge graph of the code: callers, callees, dead code.
- Semantic search.
- Editing the documentation from the wiki.

## License

[MIT](LICENSE). The bundled [htmx](https://htmx.org) is distributed under the
Zero-Clause BSD license (`src/doctracker/wiki/static/htmx-LICENSE.txt`).
