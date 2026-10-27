# DOCUMENTATION TRACKER (DOCTRACKER)

**One place for the documentation, notes and plans of a Python project developed with LLM agents.**

When agents work on a codebase, documentation ends up scattered: notes in many
Markdown files, memories, code comments and commit messages, all drifting out of
sync. Documentation Tracker (doctracker) centralizes it. It runs an [MCP](https://modelcontextprotocol.io)
server that agents (Claude Code, OpenCode, …) connect to, gives them the right
context at the right moments, and serves a live wiki of the project in your browser.

> **Status: alpha (0.3).** The technical reference, search, code graphs, git
> history, agent notes, the planner and the commit flow work. See [Roadmap](#roadmap).

## Features

- **Technical reference built from the code** — modules, classes, functions,
  methods and attributes, with signatures, type hints, decorators and parsed
  docstrings (Google, NumPy or Sphinx style).
- **Static analysis only** — the code is read with [griffe](https://mkdocstrings.github.io/griffe/),
  never imported or executed.
- **Live wiki** — edit a file or commit and the open page updates by itself.
- **Code graphs** — architecture (modules and imports, cycles marked), class
  diagram and call graph of any function.
- **Git history** — branch graph, commits with their diffs, and the commits that
  changed a file or an entity.
- **Agent notes** — guidelines (how to work) and memory (what is known), optionally
  tied to entities of the code. A new note is compared with the existing ones
  first, so the same knowledge is not written twice.
- **Planner** — plans, features and tasks with criteria, states, dependencies,
  due dates, annotations and evidence. Done work is archived, tied to its commits.
- **Commit flow** — the agent plans the commits with you, commits only what you
  approved, records them on their tasks and merges the branch into main when its
  planned work is done. Commits made outside the flow become review tasks.
- **Context for agents, by itself** — Claude Code hooks and an OpenCode plugin,
  written by doctracker, give the agent the guidelines and the open planning at
  the start of a session, when planning, when a file is read or edited and when
  committing.
- **Search** — plain text, **BM25** (words in any order), **semantic** (meaning,
  in any language) and **hybrid** (both), the same for agents and in the wiki;
  `recall` searches the open planning first, then the guidelines, memory, code
  and the archive.
- **Local embeddings** — semantic search runs on your machine with
  [llama.cpp](https://github.com/ggml-org/llama.cpp) (downloaded and managed by
  doctracker, on the GPU when there is one) or on your own [vLLM](https://github.com/vllm-project/vllm) server.
- **Everything in one folder** — doctracker keeps its data in `doc/` inside your
  project; the agents' settings it writes stay local and out of git.
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

The server prints where it wrote the agents' settings and its two addresses:

```text
Claude Code hooks: .claude/settings.local.json
OpenCode plugin: .opencode/plugins/doctracker.js
Wiki: http://127.0.0.1:8765/
MCP:  http://127.0.0.1:8765/mcp
```

Open the wiki in your browser. Keep the server running while you work on the code;
stop it with `Ctrl+C`.

## Connecting an agent

The MCP server uses the Streamable HTTP transport at `http://127.0.0.1:8765/mcp`.
Start the server before the agent.

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

`init` and `start` also write doctracker's hooks into `.claude/settings.local.json`
(your other settings are kept) and switch Claude Code's own auto memory off for
the project, so notes are kept only in doctracker.

**OpenCode** (version 2) — nothing to configure. When OpenCode is installed (or the
project has an `.opencode/` folder), `init` and `start` write the plugin
`.opencode/plugins/doctracker.js`, which registers the MCP server and gives the
context. The plugin is kept out of git through `.git/info/exclude`.

**Other agents** — any MCP client that supports Streamable HTTP can connect to the
same URL. Without hooks, the agent gets the same contexts from the `agent_context`
tool.

### When the agent gets what

| Moment | Context |
| --- | --- |
| Session start, after a summary, subagent | where notes and plans live, the guidelines given always, the open planning, the review tasks |
| Planning (plan mode, OpenCode's `plan` agent) | the planning guidelines, the requirements of the open plans, and a reminder to record the approved plan in the Planner |
| A file is read or edited | the notes about its code, once per file and session, and a reminder when no task is in progress |
| Committing | the commit guidelines, with the pre-commit material |
| Server not running | a request to ask you whether to start it |

### What the agent gets

| Group | Tools |
| --- | --- |
| Code | `list_entities`, `get_entity`, `status`, `documentation_guide` (also the `doctracker://guide` resource) |
| Search | `recall`, `hybrid_search`, `bm25_search`, `semantic_search` |
| Graphs | `architecture_view`, `class_diagram_view`, `call_graph_view` |
| Git | `git_history`, `git_branches`, `git_commit` |
| Notes | `create_note`, `update_note`, `supersede_note`, `delete_note`, `list_notes` |
| Planner | `work_context`, `create_plan`, `update_plan`, `add_feature`, `update_feature`, `add_task`, `update_task`, `check_criterion`, `annotate_task`, `add_task_evidence`, `add_dependency`, `remove_dependency`, `delete_item`, and the tools to change or delete annotations and evidence |
| Commit flow | `prepare_commit`, `commit`, `after_commit`, `clean_done`, `merge_branch` |
| Context | `agent_context` |
| Embeddings | `embedding_status`, `set_embedding_model`, `set_models_dir` |

## Notes and planning

**Notes** are short facts, in two groups:

| Group | Types | Given to the agent |
| --- | --- | --- |
| Guidelines (how to work) | `preference`, `rule` | by itself, at their moments: `always`, `planning`, `commit`; and when the code of their entities is read or edited |
| Memory (what is known) | `decision`, `context`, `pitfall`, `reference` | found with `recall` when needed |

A note that stops being true is superseded by a new one, not rewritten. Before a
note is added it is compared with the active notes of its group; when similar ones
exist it is refused and they are listed, so the agent updates one of them instead.

**The Planner** holds plans made of features, and features made of tasks. Tasks
have criteria, a state (`todo`, `doing`, `done`), annotations of what was done or
found, and evidence. Any item can depend on another; blocked and late items are
marked. Only you approve a task as done. The fixed **Reviews** plan collects the
commits made outside the commit flow, and is shown only when it has tasks.

## The commit flow

1. **Pre-commit** — `prepare_commit` gives the changed files, the open tasks and
   the commit guidelines. The agent proposes the commits (files, message and tasks)
   and goes through them with you; the server checks that every file is in one
   commit only and lists what is missing.
2. **Commit** — `commit` runs `git add` and `git commit` for each approved group,
   and stops at the first error, leaving that group's changes unstaged.
3. **Post-commit** — `after_commit` records the commits on their tasks, lists what
   is pending and what can be cleaned, and merges the branch into main (`--no-ff`)
   once its planned work is done and committed. `clean_done` archives the done
   items you confirm and deletes them; the archive keeps them tied to their commits.

Commits made from the terminal or an IDE are found by the git watcher (also those
made while the server was off) and become tasks of the Reviews plan.

## Search

| Mode | Finds | Needs the embedding model |
| --- | --- | --- |
| Default | the text as typed, in names, paths and descriptions | no |
| BM25 | entities sharing words with the query, in any order; rare words and matches in names weigh more; identifiers are split (`get_weather` → `get`, `weather`) | no |
| Semantic | entities close in meaning, in any language ("what happens when the city does not exist?") | yes |
| Hybrid | BM25 and semantic combined (reciprocal rank fusion) | yes |

`recall` (also the "All" mode in the wiki) groups its results: open planning first,
then guidelines, memory, code and the archive. It uses hybrid search when the
embedding model is ready and BM25 meanwhile.

Semantic and hybrid searches return at most 100 results. The indexes live in
`doc/sqlite/doctracker.db` and are updated incrementally, when a search needs
them: only entities and notes whose text changed are processed again.

### The embedding model

Nothing is downloaded until the first semantic or hybrid search. Then doctracker:

1. downloads the model (default: [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF), Q8, ~640 MB);
2. downloads the llama.cpp build for your machine (`device: "auto"` tries CUDA,
   then any other GPU through Vulkan, then the CPU; NVIDIA libraries are never
   downloaded, the installed CUDA runtime is used);
3. starts `llama-server` and embeds every entity and note.

On a recent GPU this takes about 25 seconds the first time, about 1 second when
the files are already there, and each search then takes a few milliseconds. The
server stops after `idle_timeout` seconds without use and starts again when needed.

To use your own **vLLM** server instead, set `embeddings.vllm_url` (and
`vllm_model`); it takes precedence and nothing is downloaded.

## The wiki

- **Tree** — AGENT NOTES, the views (architecture, classes, calls, git), and the
  packages, folders and modules (with [Tabler](https://tabler.io/icons) icons),
  classes (**C**), functions (**f**) and methods (**m**). Branches collapse; the
  tree can be resized or hidden (☰).
- **Module pages** — description, public API (`__all__`) and members grouped by kind.
- **Entity pages** — description, signature, parameters table, returns, raises,
  examples, notes, members (for classes) and the source code with syntax
  highlighting. Every section can be collapsed from its badge.
- **Graphs** — architecture, class diagram and call graph, with a focus on any entity.
- **Git** — the branch graph, the history (also of one file) and each commit with
  its message, files and diffs.
- **AGENT NOTES** — the Planner as cards and a dependency drawing, and the notes;
  everything can be created and edited here as well as by the agent.
- **Code theme** — choose among the Pygments themes in the Source section; the
  choice is saved in `config.json`.
- **Search** — pick a mode (Default, BM25, Semantic, Hybrid, All), press `/` anywhere,
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
│   ├── doctracker.db   # search indexes
│   └── notes.db        # notes, planner, commit records and archive
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
- The wiki only accepts changes (notes, planner, code theme) from its own pages.
- doctracker is a local development tool: there is no authentication, so do not
  expose the server on a network.

## Roadmap

- Dead code analysis in the wiki.

## License

[MIT](LICENSE). The bundled [htmx](https://htmx.org) is distributed under the
Zero-Clause BSD license (`src/doctracker/wiki/static/htmx-LICENSE.txt`), the bundled
[Cytoscape.js](https://js.cytoscape.org), [dagre](https://github.com/dagrejs/dagre) and
[Tabler Icons](https://tabler.io/icons) under MIT (`cytoscape-LICENSE.txt`, `dagre-LICENSE.txt`,
`icons/tabler-icons-LICENSE.txt`). The
embedding model and llama.cpp are downloaded on use and keep their own licenses
(Apache-2.0 and MIT).
