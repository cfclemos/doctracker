# DOCUMENTATION TRACKER (DOCTRACKER)

**One place for the documentation, notes and plans of a Python project developed with LLM agents.**

When agents work on a codebase, documentation ends up scattered: notes in many
Markdown files, memories, code comments and commit messages, all drifting out of
sync. Documentation Tracker (doctracker) centralizes it. It runs an [MCP](https://modelcontextprotocol.io)
server that agents (Claude Code, OpenCode, …) connect to, gives them the right
context at the right moments, and serves a live wiki of the project in your browser.

> **Status: alpha (0.4).** The technical reference, search, code graphs, the
> project's databases, git history, agent notes, the planner and the git workflow work.

## Features

- **Technical reference built from the code** — modules, classes, functions,
  methods and attributes, with signatures, type hints, decorators and parsed
  docstrings (Google, NumPy or Sphinx style).
- **Static analysis only** — the code is read with [griffe](https://mkdocstrings.github.io/griffe/),
  never imported or executed.
- **Live wiki** — edit a file or commit and the open page updates by itself.
- **Every language like Python** — JavaScript, TypeScript, CSS, HTML, PHP, Java, C#, C,
  C++, Go, Rust and SQL are read with [tree-sitter-language-pack](https://github.com/xberg-io/tree-sitter-language-pack)
  (MIT) into the same entities as Python: files, classes, interfaces, structs, functions,
  methods, CSS classes, template macros, SQL tables, with their description (the comment
  above), signature, source, the same pages and the same relations (calls, references,
  inheritance, imports, CSS classes used, rendered templates, routes). Any other file the
  pack recognises (YAML, JSON, TOML, Markdown...) has a page with its source.
- **Diagrams** — architecture (projects, packages and files of every language, with every
  relation between files and the import cycles), classes (classes, interfaces, structs and
  enums, with inheritance, implementation, composition and use) and calls
  (around any function, or the path between two), drawn in layers or by forces, with a
  timeline through the git history and a local graph on every page.
- **Dead code** — what nothing uses, from the code graph and
  [vulture](https://github.com/jendrikseipp/vulture) together (each errs where
  the other does not) for Python, and from the code graph alone for the other
  languages; with filters, in the wiki's DEAD CODE section and the `dead_code` tool.
- **Renames followed** — renames and moves found at commit are kept, so notes,
  searches and the entity page still find an entity by its earlier names.
- **Databases, read only** — the live databases of the project (PostgreSQL, MySQL, SQL Server,
  SQLite, Oracle) and what its files declare (SQL files, migrations, ORM models, dumps) in one
  catalog: objects and relations, ER diagrams and slices, a sample of the data (sensitive values
  masked), the schema's evolution, a lint, the differences between files and databases, and the
  code that uses each table and column.
- **Git history** — branch graph, commits with their diffs and the planned work each one carried
  out, and the commits that changed a file or an entity.
- **Agent notes** — guidelines (how to work) and memory (what is known), optionally
  tied to entities of the code. A new note is compared with the existing ones
  first, so the same knowledge is not written twice.
- **Planner** — plans, features and tasks with criteria, states, dependencies,
  due dates, annotations and evidence. Done work is archived, tied to its commits.
- **Git workflow** — one script for every piece of work: plan, create the branch, work with
  the reasons written on the tasks, plan separate commits with you, commit only what you
  approved, clean up and merge into main. Commits made outside it become review tasks.
- **Context for agents, by itself** — Claude Code hooks and an OpenCode plugin,
  written by doctracker, give the agent a short pointer to the workflow guide, the
  guidelines and the open planning at the start of a session, and what matters when
  planning and when a file is read or edited.
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
doctracker init     # creates doc/config/config.json, on free ports
doctracker start    # starts the server
doctracker stop     # stops it
doctracker restart  # stops it and starts it again in the background (output in doc/logs/server.log)
```

With uv, prefix the commands with `uv run` (e.g. `uv run doctracker start`).
`start` runs `init` on its own if the project has no configuration yet. `init` picks the first
free ports from 8765 (server) and 8790 (embeddings), so several projects run side by side; the
ports stay fixed afterwards, and `start` refuses a busy port saying where to change it. After that,
opening a Claude Code session starts the server by itself when it is not running.
doctracker can be installed in the project's environment or in any other one: it reads
the code without importing it, so it never needs the project's dependencies.

### Where the code is read from

Run doctracker at the root of the project. It reads **every file of a language it knows**
(Python, JavaScript, TypeScript, CSS, HTML, PHP, Java, C#, C, C++, Go, Rust, SQL, and as
whole files YAML, JSON, TOML, Markdown...), wherever it is in the repository. Left out are the
files `.gitignore` excludes (inside git), hidden folders (`.venv`, `.git`, ...), `doc/`
and folders like `venv`, `node_modules`, `build`, `dist` and `__pycache__`.

Nothing is configured, and a new file appears in the wiki while the server runs. Python is
imported from the project root and from every `src/` folder, so a single project, a
`src/` layout and a monorepo all work; namespace packages (a folder without `__init__.py`,
like `acme` below, even when spread over several members) are one package.
`pyproject.toml` is not read, so the same layouts work with pip, uv or any build backend.

The grammars of the other languages are fetched the first time a file of theirs is read
(from the pack's GitHub releases) into `doc/grammars/`, kept out of git; without network
those files are listed without what they define, and the wiki says why. Templates are
the one exception to reading through the pack: their Jinja syntax is read with Jinja2's
own parser.

```text
my-project/                     my-monorepo/
├── pyproject.toml              ├── pyproject.toml        # e.g. [tool.uv.workspace]
├── src/                        └── packages/
│   └── myapp/__init__.py           ├── billing/
├── tests/                          │   └── src/acme/billing/__init__.py
└── static/site.css                 └── web/
                                        └── src/acme/web/__init__.py
```

The server prints where it wrote the agents' settings and its two addresses:

```text
Claude Code hooks: .claude/settings.local.json
OpenCode plugin: .opencode/plugins/doctracker.js
Wiki: http://127.0.0.1:8765/
MCP:  http://127.0.0.1:8765/mcp
```

Open the wiki in your browser. Keep the server running while you work on the code;
stop it with `Ctrl+C`, or `doctracker stop` for one started in the background. When the
server stops, the open wiki pages say so and stop updating.

## Connecting an agent

The MCP server uses the Streamable HTTP transport at `http://127.0.0.1:8765/mcp`.

**Claude Code** — nothing to configure. `init` and `start` add the server to the
project's `.mcp.json` (other servers are kept; the file is added to
`.git/info/exclude` unless the project already tracks it) and write doctracker's
hooks into `.claude/settings.local.json` (your other settings are kept). There the
server is pre-approved, and Claude Code's own auto memory is switched off for the
project, so notes are kept only in doctracker. When a session opens and the server
is not running, the session hook starts it.

**OpenCode** (version 2) — nothing to configure. When OpenCode is installed (or the
project has an `.opencode/` folder), `init` and `start` write the plugin
`.opencode/plugins/doctracker.js`, which registers the MCP server and gives the
context. The plugin is kept out of git through `.git/info/exclude`. When a session
needs the server and it is not running, the plugin starts it, as the Claude Code
hook does; when the server restarts, the plugin reconnects OpenCode's MCP
connection (OpenCode runs as a long-lived service, whose connection would not
survive the restart).

**Other agents** — any MCP client that supports Streamable HTTP can connect to the
same URL. Without hooks, the agent gets the same contexts from the `agent_context`
tool.

### When the agent gets what

| Moment | Context |
| --- | --- |
| Session start, after a summary, subagent | two sentences (plans, guidelines and memory live in doctracker; read `workflow_guide` before planning or changing code), the guidelines given always, the open planning and the review tasks |
| Planning (plan mode, OpenCode's `plan` agent) | the planning guidelines, the requirements of the open plans, and a reminder to record the approved plan in the Planner |
| A file is read or edited | the notes about its code, once per file and session, and a reminder when no task is in progress |
| A file of the project is about to be edited, outside plan mode | with no task in progress, the edit is refused: plan first, or set the task to doing (`doc/` and files outside the project are not gated) |
| Pre-commit (`prepare_commit`) | the default commit rules (no AI attribution, doctracker's local files stay out, subject and why) and the commit guidelines, with the pre-commit material |
| Server not running | the session hook starts it and waits up to a minute; if it still does not answer, the guidelines and planning read straight from `notes.db`, with a warning |

### What the agent gets

| Group | Tools |
| --- | --- |
| Guides | `workflow_guide` (also the `doctracker://workflow` resource), `documentation_guide` (also `doctracker://guide`) |
| Code | `list_entities`, `get_entity`, `status` |
| Dead code | `dead_code` (the same findings and filters as the wiki's DEAD CODE section) |
| Search | `recall`, `hybrid_search`, `bm25_search`, `semantic_search` |
| Diagrams | `architecture_view`, `class_diagram_view`, `call_graph_view` (the options of the wiki's tabs: project, focus, depth, path to, relation kinds, hide unconnected; at most 500 boxes) |
| Databases | `list_connections`, `test_connection`, `refresh_database`, `database_objects`, `database_object`, `database_level`, `er_diagram_view`, `list_slices`, `get_slice`, `database_origins`, `database_origin`, `schema_moments`, `schema_diff`, `database_diff`, `list_diff_profiles`, `save_diff_profile`, `delete_diff_profile`, `database_lint` |
| Git | `git_history`, `git_branches`, `git_commit` |
| Notes | `create_note`, `update_note`, `supersede_note`, `delete_note`, `list_notes` |
| Planner | `work_context`, `create_plan`, `update_plan`, `add_feature`, `update_feature`, `add_task`, `update_task`, `check_criterion`, `annotate_task`, `add_task_evidence`, `add_dependency`, `remove_dependency`, `delete_item`, and the tools to change or delete annotations and evidence |
| Git workflow | `start_branch`, `prepare_commit`, `commit`, `after_commit`, `clean_done`, `merge_branch` |
| Context | `agent_context` |
| Embeddings | `embedding_status`, `set_embedding_model`, `set_models_dir`, `set_vllm_url` |

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

## The git workflow

Every piece of work follows the same script, written for the agents in the workflow guide
(`workflow_guide`). You decide at the steps marked *(you)*.

1. **Recall** — `recall` first: what is planned, the guidelines, the memory and the code.
2. **Plan** — in plan mode, with the choices brought to you *(you)*. The approved plan is
   recorded in the Planner, with its requirements, the decisions and why, and the criteria of
   each task.
3. **Branch** — before the first edit, `start_branch` creates the work's branch from main and
   records it on the plan, feature or task. That is how the post-commit knows which work the
   branch carries.
4. **Work** — the task is set to `doing` (edits are refused while no task is in progress). On
   the task the agent writes what was done **and why**: the reason for each change, the cause of
   a bug, what was found and decided (`annotate_task`), and what shows it works
   (`add_task_evidence`). Only you approve a task as done *(you)*.
5. **Plan the commits** — `prepare_commit` gives the changed files, the open tasks with their
   annotations, the renames and the commit guidelines. The agent proposes **separate commits, one
   purpose each** (a file goes whole into one commit), each message a subject saying what changed
   and a body saying why, built from the tasks' annotations. The server checks the groups (every
   file in one commit only, the tasks approved, their criteria met) and the agent goes through
   them with you *(you)*.
6. **Commit** — `commit` runs `git add` and `git commit` for each approved group and stops at the
   first error, leaving that group's changes unstaged. Then `after_commit` records the commits on
   their tasks and lists what is pending.
7. **Clean** — the done items you confirm are archived and deleted with `clean_done` *(you)*;
   the archive keeps them tied to their commits, and the GIT page shows them on each commit.
8. **Merge** — once the work planned for the branch is all done and committed, `after_commit`
   merges it into main (`--no-ff`). On a conflict nothing is merged and git's message comes back;
   `merge_branch` merges by hand when you ask.

Commits made from the terminal or an IDE are found by the git watcher (also those made while
the server was off) and become tasks of the Reviews plan, which you approve in the Planner or
from the wiki's notification bell.

## Search

| Mode | Finds | Needs the embedding model |
| --- | --- | --- |
| BM25 | entities sharing words with the query, in any order; rare words and matches in names weigh more; identifiers are split (`get_weather` → `get`, `weather`) | no |
| Semantic | entities close in meaning, in any language ("what happens when the city does not exist?") | yes |
| Hybrid | BM25 and semantic combined (reciprocal rank fusion) | yes |

`recall` (also the "All" mode, the wiki's default) groups its results: open planning first,
then guidelines, memory, code, databases and the archive. It uses hybrid search when the
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
`vllm_model`), or ask the agent (`set_vllm_url`, then `set_embedding_model`);
it takes precedence and nothing is downloaded. An empty `set_vllm_url` goes back
to llama.cpp.

## Databases

The DATABASES section reads the project's databases, **only ever reading**, and what its files
declare, into one catalog with the same objects, pages and tools:

- **Connections** — found in the project's files (`.env`, `alembic.ini`, Django settings, Compose
  files, Prisma's `datasource`, `create_engine(...)`, SQLite files) or entered by hand; only those
  you allow are opened. PostgreSQL, MySQL/MariaDB, SQL Server, SQLite and Oracle, optionally
  through an SSH tunnel or with an AWS RDS IAM token (`doctracker[aws]`). Passwords stay a
  reference to an environment variable or are kept encrypted, out of git.
- **What the files declare** — SQL files and migrations (Flyway, golang-migrate, dbmate), ORM
  models and migrations (SQLAlchemy, Alembic, Django, Prisma) and schema dumps (pg_dump, mysqldump,
  sqlite3, SQL Server scripts), read as text, never run.
- **Navigate** — every object by level (servers, databases, schemas, tables and views, columns)
  or as a graph of their relations; each table with a sample of its data, sensitive values masked.
- **Diagrams** — the ER diagram of the whole schema, and slices: a few tables kept together with a
  name and a purpose, saved in `doc/slices/` (versioned with the project).
- **Diff** — any two places compared (a database, a file's schema, a schema, a table), with saved
  profiles in `doc/diff/`.
- **Evolution** — the schema at each migration step or commit, and any two moments compared.
- **Lint** — what in the schema and the migrations deserves a look, each rule with why and how to
  fix it; accepted findings are kept in `doc/lint/accepted.json`.
- **Use in the code** — each table and column links to the code that uses it (ORM models, SQL in
  Python strings, `.sql` query files), and each code page shows the tables it uses.

## The wiki

- **Dashboard** — the home page sums up each section, every number a link: open plans and reviews,
  modules, classes, functions and dead code, connections and lint findings, the branch, the files not
  committed and the last commits.
- **Tree** — the sections AGENT (Planner, Guidelines, Memory), CODE (Diagrams, Dead Code, then the
  code itself), DATABASES (Connections, Navigate, Diagrams, Diff, Evolution, Lint, then the
  connections and files) and GIT, with [Tabler](https://tabler.io/icons) icons. The buttons beside
  CODE show the code **by language** (Python by packages and modules, the others by folder) or **by
  folder**. Branches collapse; the tree can be resized or hidden (☰).
- **Notifications** — the bell in the top bar counts what needs attention (missing grammars,
  commits waiting for review) and opens each item; a review can be approved from its details.
- **Language filter** — the select in the search bar shows one language or all of them in
  the whole wiki: tree, search, graphs and dead code. The MCP tools always see everything.
- **Module pages** — description, public API (`__all__`) and members grouped by kind.
- **Entity pages** — description, signature, parameters table, returns, raises,
  examples, notes, members (for classes), the tables it uses and the source code with syntax
  highlighting. Every section can be collapsed from its badge.
- **CODE › Diagrams** — three tabs, each at its own URL; the menu opens the tab used last.
  Above every drawing, the filters say what is drawn; the legend's relations turn each kind on
  and off (with none, nothing is drawn).
  - **Architecture** — projects, packages and files, closed at first: a click opens a level.
    Filters: project, focus with depth (3 by default). Relations: imports, uses,
    calls, refers, inherits, has. The import cycles are listed; a timeline goes through the
    commits, each file appearing at the commit that added it.
  - **Classes** — classes of any language with their attributes and methods, in their files and
    packages (SQL tables are not classes: they are left out). Filters: project, focus with depth.
    Relations: inherits, implements, has, uses, refers.
  - **Functions and Calls** — a function by its name or path: what it calls and what calls it (depth and
    direction), or, with Path to, the shortest calls from it to another. Relations: calls,
    refers, templates, CSS classes, routes. It opens on the last
    choice; with no focus, nothing is drawn.
  - **Every drawing** — layers or forces, colour by kind, language or project (a chip per
    group hides it), hide unconnected, rearrange, highlight, zoom and fit, export as SVG or
    PNG; over 500 boxes, the most connected ones, with a warning.
- **Local graph** — on every entity and module page: what it uses and what uses it, up to
  three steps away, drawn like the diagrams.
- **GIT** — the branch graph on top; below, the commits, newest first. A click on a commit opens
  its full message (the why) and shows on the right the **planned work** it carried out (the
  archived tasks with their criteria, annotations and evidence) and its files, one at a time
  (select, or ‹ › to step), with the removed (−) and added (+) lines. From a file's page, the
  history shows only the commits that changed it.
- **AGENT** — the Planner as cards and a dependency drawing, the guidelines and the memory;
  everything can be created and edited here as well as by the agent.
- **Code theme** — choose among the Pygments themes in the Source section; the
  choice is saved in `config.json`.
- **Search** — pick a mode (BM25, Semantic, Hybrid, All, the default), press `/` anywhere,
  type, use ↑/↓ and Enter; pages are at the bottom of the results.

## Configuration

`doc/config/config.json` (created by `doctracker init`):

| Key | Default | Description |
| --- | --- | --- |
| `host` | `"127.0.0.1"` | Address the server listens on. |
| `port` | `8765` | Port of the server (also `doctracker start --port`); `init` takes the first free one from 8765. |
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
| `port` | `8790` | Port of the managed `llama-server`; `init` takes the first free one from 8790. |
| `idle_timeout` | `600` | Seconds without use before `llama-server` is stopped. |
| `query_instruction` | (Qwen3 instruction) | Text added before every search query. |

### The `doc/` folder

```text
doc/
├── .gitignore          # keeps local data out of git
├── config/
│   └── config.json     # commit this file
├── slices/             # schema slices (commit them)
├── diff/               # saved diff profiles (commit them)
├── lint/
│   └── accepted.json   # lint findings accepted, with their reason (commit it)
├── sqlite/
│   ├── doctracker.db   # search indexes
│   ├── notes.db        # notes, planner, commit records and archive
│   └── databases.db    # what was last read of the live databases, and the samples
├── connections/        # database connections and encrypted passwords
├── grammars/           # tree-sitter grammars of the languages read
├── models/             # embedding model and llama.cpp (created on first semantic search)
└── logs/
    ├── server.log      # output of a server started by a session hook or `restart`
    └── server.json     # the running server's process and address, for `restart`
```

Every folder is created only when a feature needs it. `sqlite/`, `connections/`, `grammars/`,
`models/` and `logs/` are kept out of git (`doc/.gitignore`; `logs/` and `connections/` have a
`.gitignore` of their own).

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

Agents get the complete guide from the `documentation_guide` tool (and how to work, from
branch to merge, from `workflow_guide`). It also gives
them default rules on how to write code: think before coding, keep it simple,
change only what the task needs, and work toward a result that can be checked.

## Security

- By default the server listens only on `127.0.0.1`, and the MCP endpoint
  validates the `Host` and `Origin` headers (protection against DNS rebinding).
- The wiki only accepts changes (notes, planner, code theme, connections) from its own pages.
- Databases are only ever read: read-only sessions where the database allows it, every
  transaction rolled back, and every statement checked before it is sent.
- doctracker is a local development tool: there is no authentication, so do not
  expose the server on a network.

## License

[MIT](LICENSE). The bundled [htmx](https://htmx.org) is distributed under the
Zero-Clause BSD license (`src/doctracker/wiki/static/htmx-LICENSE.txt`), the bundled
[dagre](https://github.com/dagrejs/dagre), [WebCola](https://github.com/tgdwyer/WebCola) and
[Tabler Icons](https://tabler.io/icons) under MIT (`dagre-LICENSE.txt`, `cola-LICENSE.txt`,
`icons/tabler-icons-LICENSE.txt`). The
embedding model and llama.cpp are downloaded on use and keep their own licenses
(Apache-2.0 and MIT).
