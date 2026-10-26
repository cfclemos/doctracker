# DOCUMENTATION TRACKER (DOCTRACKER)

**One place for the documentation of a Python project developed with LLM agents.**

When agents work on a codebase, documentation ends up scattered: notes in many
Markdown files, memories, code comments and commit messages, all drifting out of
sync. Documentation Tracker (doctracker) centralizes it. It runs an [MCP](https://modelcontextprotocol.io)
server that any agent (Claude Code, OpenCode, …) can connect to, and serves a live
wiki of the project in your browser.

> **Status: alpha (0.2).** doctracker builds the technical reference of the code
> and searches it by words and by meaning. Notes, commit history and LLM summaries
> come in the next versions (see [Roadmap](#roadmap)).

## Features

- **Technical reference built from the code** — modules, classes, functions,
  methods and attributes, with signatures, type hints, decorators and parsed
  docstrings (Google, NumPy or Sphinx style).
- **Static analysis only** — the code is read with [griffe](https://mkdocstrings.github.io/griffe/),
  never imported or executed.
- **Live wiki** — edit a file and the open page updates by itself.
- **Four kinds of search**, the same for agents and in the wiki:
  plain text, **BM25** (words in any order), **semantic** (meaning, in any
  language) and **hybrid** (both combined), with paging.
- **Local embeddings** — semantic search runs on your machine with
  [llama.cpp](https://github.com/ggml-org/llama.cpp) (downloaded and managed by
  doctracker, on the GPU when there is one) or on your own [vLLM](https://github.com/vllm-project/vllm) server.
- **MCP server** — agents can list, read and search the documentation, and get a
  guide on how to document the code so the wiki stays complete.
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
| `bm25_search` | tool | Finds entities by the words they share with the query. |
| `semantic_search` | tool | Finds entities by meaning, in any language. |
| `hybrid_search` | tool | BM25 and semantic search combined; usually the best choice. |
| `embedding_status` | tool | State of the embedding backend: model, device, download progress, index size. |
| `set_embedding_model` | tool | Changes the embedding model and saves it in `config.json`. |
| `set_models_dir` | tool | Changes the folder of models and llama.cpp binaries. |
| `documentation_guide` | tool | How to document this project's code (adapted to its settings). |
| `doctracker://guide` | resource | The same guide, as a Markdown resource. |

The search tools take `limit` and `offset` (paging) and return `total`. The
server's instructions tell the agent to read the guide before writing or
changing docstrings.

## Search

| Mode | Finds | Needs the embedding model |
| --- | --- | --- |
| Default | the text as typed, in names, paths and descriptions | no |
| BM25 | entities sharing words with the query, in any order; rare words and matches in names weigh more; identifiers are split (`get_weather` → `get`, `weather`) | no |
| Semantic | entities close in meaning, in any language ("what happens when the city does not exist?") | yes |
| Hybrid | BM25 and semantic combined (reciprocal rank fusion) | yes |

Semantic and hybrid searches return at most 100 results. The indexes live in
`doc/sqlite/doctracker.db` and are updated incrementally, when a search needs
them: only entities whose text changed are processed again.

### The embedding model

Nothing is downloaded until the first semantic or hybrid search. Then doctracker:

1. downloads the model (default: [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF), Q8, ~640 MB);
2. downloads the llama.cpp build for your machine (`device: "auto"` tries CUDA,
   then any other GPU through Vulkan, then the CPU; NVIDIA libraries are never
   downloaded, the installed CUDA runtime is used);
3. starts `llama-server` and embeds every entity.

On a recent GPU this takes about 25 seconds the first time, about 1 second when
the files are already there, and each search then takes a few milliseconds. The
server stops after `idle_timeout` seconds without use and starts again when needed.

To use your own **vLLM** server instead, set `embeddings.vllm_url` (and
`vllm_model`); it takes precedence and nothing is downloaded.

## The wiki

- **Tree** — packages, folders and modules (with [Tabler](https://tabler.io/icons) icons), classes (**C**), functions (**f**) and
  methods (**m**). Branches collapse; the tree can be resized or hidden (☰).
- **Module pages** — description, public API (`__all__`) and members grouped by kind.
- **Entity pages** — description, signature, parameters table, returns, raises,
  examples, notes, members (for classes) and the source code with syntax
  highlighting. Every section can be collapsed from its badge.
- **Code theme** — choose among the Pygments themes in the Source section; the
  choice is saved in `config.json`.
- **Search** — pick a mode (Default, BM25, Semantic, Hybrid), press `/` anywhere,
  type, use ↑/↓ and Enter; pages are at the bottom of the results.

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
| `embeddings` | see below | Settings of the embedding model. |

`embeddings` section:

| Key | Default | Description |
| --- | --- | --- |
| `vllm_url` | `null` | Base URL of a running vLLM server; when set, it is used instead of llama.cpp. |
| `vllm_model` | `"Qwen/Qwen3-Embedding-0.6B"` | Model name served by vLLM. |
| `model` | `"Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf"` | GGUF model for llama.cpp: `owner/repo/file.gguf` on Hugging Face, or a local file. |
| `models_dir` | `null` | Folder for models and llama.cpp binaries; `null` means `doc/models`. Point several projects to the same folder to download once. |
| `device` | `"auto"` | `auto` (CUDA, then Vulkan, then CPU), `cuda`, `vulkan` or `cpu`. |
| `llama_cpp_release` | `"b11887"` | llama.cpp release to download, or `latest`. |
| `port` | `8790` | Port of the managed `llama-server`. |
| `idle_timeout` | `600` | Seconds without use before `llama-server` is stopped. |
| `query_instruction` | (Qwen3 instruction) | Text added before every search query. |

### The `doc/` folder

```text
doc/
├── .gitignore          # keeps local data out of git
├── config/
│   └── config.json     # commit this file
├── sqlite/
│   └── doctracker.db   # search indexes (created on first search)
└── models/             # embedding model and llama.cpp (created on first semantic search)
```

`sqlite/` and `models/` are created only when a feature needs them, and are
ignored by `doc/.gitignore`.

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
- Documentation coverage report (undocumented entities and parameters).
- Editing the documentation from the wiki.

## License

[MIT](LICENSE). The bundled [htmx](https://htmx.org) is distributed under the
Zero-Clause BSD license (`src/doctracker/wiki/static/htmx-LICENSE.txt`), the bundled
[Cytoscape.js](https://js.cytoscape.org) and [Tabler Icons](https://tabler.io/icons) under MIT
(`cytoscape-LICENSE.txt`, `icons/tabler-icons-LICENSE.txt`). The
embedding model and llama.cpp are downloaded on use and keep their own licenses
(Apache-2.0 and MIT).
