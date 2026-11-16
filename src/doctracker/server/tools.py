"""MCP tools that let agents read the technical documentation."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from doctracker.analysis import DEAD_KINDS, VERDICTS, dead_code_kinds, filter_rows
from doctracker.config import Config, set_config_value
from doctracker.databases import ConnectionStore
from doctracker.databases.code_links import database_use
from doctracker.graph import (CALL_KINDS, MAX_CALL_DEPTH, architecture, call_graph, class_diagram, entity_history,
                              trim_view)
from doctracker.history import commit_diff, read_branch_graph
from doctracker.notes.context import CONTEXT_KINDS, context_for
from doctracker.search import AGENT_WAIT_SECONDS, DEFAULT_LIMIT, SearchEngine
from doctracker.server.guide import documentation_guide as build_guide
from doctracker.server.guide import workflow_guide as build_workflow
from doctracker.server.state import DocState
from doctracker.wiki.pages import summary

GUIDE_URI = "doctracker://guide"
"""URI of the MCP resource with the documentation guide."""

WORKFLOW_URI = "doctracker://workflow"
"""URI of the MCP resource with the workflow guide."""


def register_tools(mcp: MCPServer, state: DocState, config: Config, search: SearchEngine, connections: ConnectionStore) -> None:
    """Add the documentation tools and the documentation guide to the MCP server.

    Args:
        mcp: Server to register the tools and the guide resource on.
        state: Extracted entities the tools read.
        config: Project settings; the `set_*` tools change it and save it to config.json.
        search: Search engine behind the search tools (the same one the wiki uses).
        connections: Store of the database connections, for the tables an entity uses.
    """
    embeddings = search.embeddings
    project_root = embeddings.project_root

    @mcp.tool()
    def architecture_view(level: str = "modules", project: str = "", focus: str = "",
                          depth: int = MAX_CALL_DEPTH, kinds: list[str] | None = None,
                          hide_unconnected: bool = False) -> dict:
        """Get the architecture: packages and files of every language, and how the files relate.

        The same options as the wiki's Architecture tab; over 500 boxes, only the most connected.

        Args:
            level: `modules` (every file) or `packages` (files merged into their package, imports only).
            project: Only this project (`project:<name>`, as in the nodes); empty for all.
            focus: Only this module (or file) and those `depth` relations away from it.
            depth: How many relations away from `focus` (1 to 3).
            kinds: Only these relations: `imports`, `uses`, `calls`, `refers`, `inherits`, `has`; all by default.
            hide_unconnected: Leave out the files with no relation.

        Returns:
            `nodes` (id, `role`: project, package, subpackage or module; `frame`: drawn around what
            it holds; enclosing `parent`; `page`: entity path; summary; a package's own `__init__.py`
            is the module `<package>.__init__`), `edges` (`kind`, `weight`; imports in a cycle have
            `cycle`; at package level one undirected link per pair, `counts` by direction), `cycles`
            (the files of each import cycle) and `left_out` (boxes over the limit).
        """
        graph = architecture(state, level, "", project, focus, depth)
        return trim_view(graph, kinds, hide_unconnected)

    @mcp.tool()
    def class_diagram_view(package: str = "", project: str = "", focus: str = "",
                           depth: int = MAX_CALL_DEPTH, kinds: list[str] | None = None,
                           hide_unconnected: bool = False) -> dict:
        """Get the class diagram: classes, interfaces, structs, enums... with their members, and how they relate.

        The same options as the wiki's Classes tab; over 500 boxes, only the most connected.

        Args:
            package: Only classes under this path (e.g. `pkg.server`); empty means all.
            project: Only the classes of this project (`project:<name>`); empty for all.
            focus: Only this class and those `depth` relations away from it.
            depth: How many relations away from `focus` (1 to 3).
            kinds: Only these relations: `inherits`, `implements`, `has`, `uses`, `refers`; all by default.
            hide_unconnected: Leave out the classes with no relation.

        Returns:
            `nodes` (class path, `stereotype` such as dataclass, enum or interface, `attributes` with
            name, type, icon and the project class they hold, `methods` with name, signature and kind;
            the files and packages above as frames), `edges` (`inherits`; `implements` = the base is an
            interface, trait or protocol; `has` = an attribute holds another class, `via` naming it;
            `uses` = a method calls another class; `refers` = named without a call, e.g. a type)
            and `left_out` (boxes over the limit).
        """
        graph = class_diagram(state, package, "", project, focus, depth)
        return trim_view(graph, kinds, hide_unconnected)

    @mcp.tool()
    def call_graph_view(path: str, depth: int = MAX_CALL_DEPTH, direction: str = "both",
                        kinds: list[str] | None = None) -> dict:
        """Get what a function, method or class calls and what calls it.

        The same options as the wiki's Functions and Calls tab; over 500 boxes, only the most connected.

        Args:
            path: Entity in the center: its path (`pkg.api.get_weather`) or its name (`get_weather`).
            depth: How many calls away to go (1 to 3).
            direction: `out` (what it calls), `in` (what calls it) or `both`.
            kinds: Only these relations, followed and returned: `calls`, `refers`, `template`, `css-class`,
                `route`; all by default.

        Returns:
            `focus` (the path found), `nodes` (with `distance` from the center and `side`: focus,
            callee, caller), `edges` (`kind`) and `left_out`; `error` when nothing has that name.
        """
        chosen = tuple(kind for kind in CALL_KINDS if kinds is None or kind in kinds)
        return trim_view(call_graph(state, path, depth, direction, chosen))

    @mcp.tool()
    async def git_history(path: str, limit: int = 20) -> dict:
        """List the commits that changed the file of an entity, newest first.

        Args:
            path: Entity path; the commits of its module's file are listed.
            limit: Most recent commits to list.

        Returns:
            `commits` (short hash, author, date, subject, body: the full message after the
            subject, where the reasons for a change usually are), or `error` when the project
            is not a git repository.
        """
        commits = await entity_history(state, project_root, path, max(1, limit))
        return {"commits": commits} if commits is not None else {"error": "Unknown entity or not a git repository."}

    @mcp.tool()
    async def git_branches(limit: int = 50) -> dict:
        """List the recent commits of every branch, one lane per branch.

        The branch a commit was made on comes from the local reflog while it remembers it;
        older commits follow the topology, like `git log --graph`.

        Args:
            limit: Most recent commits to list, across all branches.

        Returns:
            `commits`, newest first: hash, short, parents, refs (branches and tags), branch
            (from the reflog; empty when unknown), lane, open (tip of a branch that goes on
            to the present), merged_into (merge where a branch merged through a later commit
            ends), next_on_branch (next commit of the same branch when it is not a child),
            author, date, subject, body (rest of the message); or `error` when the project is
            not a git repository.
        """
        commits = await read_branch_graph(project_root, max(1, limit))
        return {"commits": commits} if commits is not None else {"error": "Not a git repository."}

    @mcp.tool()
    async def git_commit(hash: str) -> dict:
        """Get what one commit changed: each file with its added (+) and removed (-) lines.

        Args:
            hash: Full or abbreviated commit hash (from `git_history`).

        Returns:
            `files`: path, status, additions, deletions and `diff` (unified diff lines of the file), and
            `planned_work`: the archived tasks the commit carried out (criteria, annotations, evidence);
            or `error` when the commit is not found.
        """
        files = await commit_diff(project_root, hash.strip())
        if files is None:
            return {"error": "Commit not found or not a git repository."}
        signs = {"add": "+", "delete": "-", "context": " ", "hunk": ""}
        return {
            "files": [
                {
                    "path": file.path,
                    "old_path": file.old_path,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "binary": file.binary,
                    "truncated": file.truncated,
                    "diff": "\n".join(signs[line.kind] + line.text for line in file.lines),
                }
                for file in files
            ],
            "planned_work": search.notes.archived(hash),
        }

    @mcp.tool()
    async def bm25_search(query: str, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Find entities by the words they share with the query, ranked by BM25.

        Words count in any order; rare words weigh more, and matches in the name more than
        in the description. Identifiers are split (`get_weather` matches "weather").

        Args:
            query: Words to look for (in the language of the docstrings).
            limit: Results per page.
            offset: Results to skip, for the next pages (e.g. `offset=10` with `limit=10` is page 2).

        Returns:
            `status`, `total`, `offset` and `results`: path, kind, BM25 score (higher is better) and summary.
        """
        return search.describe(await search.run("bm25", query, max(1, limit), AGENT_WAIT_SECONDS, offset))

    @mcp.tool()
    async def semantic_search(query: str, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Find entities by meaning, in any language (e.g. "what happens when the city does not exist?").

        The first call may download the embedding model and llama.cpp and build the index;
        while that happens the answer has `"status": "preparing"` and a progress `step`.
        Call again later (or check `embedding_status`).

        Args:
            query: Question or description of what you are looking for.
            limit: Results per page.
            offset: Results to skip, for the next pages (e.g. `offset=10` with `limit=10` is page 2).

        Returns:
            `status`, and when ready, `total`, `offset` and `results`: path, kind, similarity score (0 to 1) and summary.
        """
        return search.describe(await search.run("semantic", query, max(1, limit), AGENT_WAIT_SECONDS, offset))

    @mcp.tool()
    async def hybrid_search(query: str, limit: int = DEFAULT_LIMIT, offset: int = 0) -> dict:
        """Find entities with BM25 and semantic search combined (reciprocal rank fusion).

        Usually the best choice: words and meaning both count. Needs the embedding model,
        like `semantic_search` (answers `"status": "preparing"` while it is being prepared).

        Args:
            query: Words or a question, in any language.
            limit: Results per page.
            offset: Results to skip, for the next pages (e.g. `offset=10` with `limit=10` is page 2).

        Returns:
            `status`, and when ready, `total`, `offset` and `results`: path, kind, fused score (higher is better) and summary.
        """
        return search.describe(await search.run("hybrid", query, max(1, limit), AGENT_WAIT_SECONDS, offset))

    @mcp.tool()
    async def recall(query: str) -> dict:
        """Find what the project knows about a subject: open planning first, then guidelines, memory and code.

        Use it before planning, before changing code and before writing a note, to build on what is
        already recorded. Each group lists at most a few results; open planner items come before
        done ones. Hybrid search when the embedding model is ready, BM25 meanwhile.

        Args:
            query: Words or a question, in any language.

        Returns:
            `mode`, then `planning`, `guidelines`, `memory` and `code`: lists of `ref` (e.g. `task:3`,
            `note:7`, an entity path), `kind`, `title`, `state` (planner items) and `score`.
        """
        return await search.recall(query)

    @mcp.tool(description=f"""Get what doctracker tells agents at one moment of the work.

The same texts the hooks give by themselves: `session` (where everything is kept, the guidelines
given always, the open planning, the reviews waiting), `planning` (how to plan here, the planning
guidelines, the open requirements), `file` (the notes about the code of a file), `commit` (the
guidelines given when committing), `edit` (why editing the project is refused while no task is in
progress; empty when one is).

Args:
    kind: One of {", ".join(CONTEXT_KINDS)}.
    path: For `file`: the file, absolute or relative to the project root.

Returns:
    `context`: the text (empty when there is nothing to say).""")
    def agent_context(kind: str, path: str = "") -> dict:
        try:
            return {"context": context_for(kind, search.notes, state.entities, project_root, path)}
        except ValueError as refused:
            raise ToolError(str(refused)) from refused

    @mcp.tool()
    def embedding_status() -> dict:
        """Report the embedding backend: state, model, device, llama.cpp build, models folder and index size."""
        return embeddings.status()

    @mcp.tool()
    async def set_embedding_model(model: str) -> dict:
        """Change the embedding model and save it in config.json.

        With a vLLM server configured (`embeddings.vllm_url`), this sets the model name served by vLLM.
        Otherwise it sets the GGUF model for llama.cpp, downloaded on next use.

        Args:
            model: For llama.cpp, `owner/repo/file.gguf` on Hugging Face
                (e.g. `Qwen/Qwen3-Embedding-0.6B-GGUF/Qwen3-Embedding-0.6B-Q8_0.gguf`) or a local `.gguf` path.
                For vLLM, the served model name (e.g. `Qwen/Qwen3-Embedding-0.6B`).

        Returns:
            The new embedding status. The index is rebuilt with the new model on next use.
        """
        key = "vllm_model" if embeddings.uses_vllm else "model"
        if key == "model" and not model.endswith(".gguf"):
            raise ToolError("Use 'owner/repo/file.gguf' (Hugging Face) or the path of a local .gguf file")
        set_config_value(project_root, config, key, model, section="embeddings")
        await embeddings.reset()
        return embeddings.status()

    @mcp.tool()
    async def set_models_dir(path: str = "") -> dict:
        """Change the folder for embedding models and llama.cpp binaries, and save it in config.json.

        Args:
            path: Absolute path, or relative to the project root. Empty means the default, `doc/models`.

        Returns:
            The new embedding status. Files are downloaded to the new folder on next use.
        """
        set_config_value(project_root, config, "models_dir", path.strip() or None, section="embeddings")
        await embeddings.reset()
        return embeddings.status()

    @mcp.tool()
    async def set_vllm_url(url: str = "") -> dict:
        """Set, change or remove the vLLM server used for embeddings, and save it in config.json.

        Args:
            url: Base URL of a running vLLM server (e.g. `http://127.0.0.1:8000`). Empty removes it,
                going back to the llama.cpp server managed by doctracker. The model it serves is set
                with set_embedding_model.

        Returns:
            The new embedding status. The index is rebuilt with the new backend on next use.
        """
        url = url.strip()
        if url and not url.startswith(("http://", "https://")):
            raise ToolError("Use the server's base URL, e.g. 'http://127.0.0.1:8000'")
        set_config_value(project_root, config, "vllm_url", url.rstrip("/") or None, section="embeddings")
        await embeddings.reset()
        return embeddings.status()

    @mcp.tool()
    def workflow_guide() -> str:
        """Explain how to work in this project: recall, plan, branch, work, commit, clean and merge.

        Read it at the start of a session, before planning or changing code, and follow its steps.

        Returns:
            The guide in Markdown.
        """
        return build_workflow()

    @mcp.resource(WORKFLOW_URI, name="workflow-guide", title="How to work in a project documented by doctracker",
                  mime_type="text/markdown")
    def workflow_resource() -> str:
        """How to work in this project: recall, plan, branch, work, commit, clean and merge."""
        return build_workflow()

    @mcp.tool()
    def documentation_guide() -> str:
        """Explain how to write and document this project's code so doctracker builds complete pages.

        Read it before writing or changing code, docstrings, module docstrings, type hints or `__all__`.

        Returns:
            The guide in Markdown, adapted to this project's settings (docstring style, private members).
        """
        return build_guide(config)

    @mcp.resource(GUIDE_URI, name="documentation-guide", title="How to write and document code for doctracker",
                  mime_type="text/markdown")
    def guide_resource() -> str:
        """How to write and document this project's code so doctracker builds complete pages."""
        return build_guide(config)

    @mcp.tool()
    def list_entities(prefix: str = "", kind: str = "") -> list[dict]:
        """List documented entities.

        Args:
            prefix: Only entities whose qualified path starts with this text (e.g. `mypkg.api`).
            kind: Only entities of this kind: `module`, `class`, `function`, `attribute` or `type alias`.

        Returns:
            One item per entity with its path, kind and the first line of its docstring.
        """
        items = []
        for path, entity in sorted(state.entities.items()):
            if prefix and not path.startswith(prefix):
                continue
            if kind and entity["kind"] != kind:
                continue
            items.append({"path": path, "kind": entity["kind"], "summary": summary(entity)})
        return items

    @mcp.tool()
    def get_entity(path: str) -> dict:
        """Get the full technical reference of one entity.

        Args:
            path: Qualified path of the entity (e.g. `mypkg.api.get_weather`); an earlier name of a
                renamed or moved entity gives the entity it is now.

        Returns:
            Signature data, parameters, docstring sections, location in the code and members,
            `previous_names` (earlier paths, newest first: path, how, commit, created) and `database_use`
            (the tables and columns it and its members use: `use`, `table`, `column`, `line`, `evidence`,
            `confidence`, `how` and `objects`, the paths reached; see `databases.code_links.database_use`).
        """
        entity = state.entities.get(path) or state.entities.get(search.notes.current_name(path))
        if entity is None:
            raise ToolError(f"Unknown entity: {path}")
        return {**entity, "previous_names": search.notes.previous_names(entity["path"]),
                "database_use": database_use(entity["path"], state.code_links, state.origins, search.catalog,
                                             connections.connections(), project_root)}

    @mcp.tool(description=f"""Find dead code: what nothing in the project uses, from the code graph and vulture.

A Python function or class is `unused` when both agree, `public, unused inside` when its package offers
it (`__all__`, re-exported); the front-end (JS functions, CSS classes, templates, macros) is judged by
the graph, `maybe used by data` when the Python code writes its name as a string; `vulture only` covers
variables, attributes, properties, imports and unreachable code. Check before deleting: code used only
from outside the project, or through data, is not seen. The same list as the wiki's CODE › Dead Code page.

Args:
    prefix: Only paths (or files) starting with it, e.g. `mypkg.api` or `mypkg/static`.
    verdict: One of {", ".join(VERDICTS)}; empty for all.
    kind: One of {", ".join(DEAD_KINDS)}, or the own kind of another language (`interface`...); empty for all.
    min_confidence: Only findings at least this sure, 0 to 100.

Returns:
    `total` (every finding), `shown` and `rows`: `path` (the entity, or `file:line`), `name`, `kind`,
    `verdict`, `confidence`, `used_by`, `file`, `line` and `message` (why).""")
    def dead_code(prefix: str = "", verdict: str = "", kind: str = "", min_confidence: int = 0) -> dict:
        if verdict and verdict not in VERDICTS:
            raise ToolError(f"Unknown verdict {verdict!r}; use one of: {', '.join(VERDICTS)}")
        kinds = dead_code_kinds(state.dead_code)
        if kind and kind not in kinds:
            raise ToolError(f"Unknown kind {kind!r}; use one of: {', '.join(kinds)}")
        rows = filter_rows(state.dead_code, prefix.strip(), verdict, kind, min_confidence)
        return {"total": len(state.dead_code), "shown": len(rows), "rows": rows}

    @mcp.tool()
    def status() -> dict:
        """Report whether the documentation is built, any loading errors, and the languages left out
        because their grammar could not be fetched (e.g. without network)."""
        return {
            "ready": state.ready,
            "packages": state.roots,
            "entities": len(state.entities),
            "errors": state.errors,
            "missing_grammars": state.missing_grammars,
        }
