// doctracker's OpenCode plugin (OpenCode 2 plugin API): gives doctracker's context to the agent at the
// same moments as the Claude Code hooks. Written by `doctracker init` / `doctracker start`, which fill in
// the values below; changes made here are lost when it is written again.

import { execFile } from "node:child_process";
import { fileURLToPath } from "node:url";

const BASE_URL = __BASE_URL__;
const SERVER_DOWN = __SERVER_DOWN__;
const RECORD_THE_PLAN = __RECORD_THE_PLAN__;
const DOCTRACKER = __DOCTRACKER__; // the command that runs doctracker, as [program, ...arguments]
const START_TIMEOUT_MS = __START_TIMEOUT_MS__; // the longest wait for a server being started
const PROJECT_ROOT = fileURLToPath(new URL("../..", import.meta.url)); // this file is .opencode/plugins/

const TIMEOUT_MS = 2000; // a hook never waits longer than this for the server
const WATCH_MS = 2000; // how often the plugin checks whether the server restarted
const SERVER_HEADER = "x-doctracker-server"; // carries the server's id in the MCP config, see `ensure`
const FILE_TOOLS = ["read", "edit", "write"]; // tools that read or change one file
const PATCH_FILE = /^\*\*\* (?:Add|Update|Delete) File: (.+)$/gm; // the files of an `apply_patch`

// The context of a moment from the server (`/hooks/context/<kind>`); null when it does not answer.
async function ask(kind, params) {
  try {
    const url = new URL(`${BASE_URL}/hooks/context/${kind}`);
    for (const [key, value] of Object.entries(params)) if (value) url.searchParams.set(key, value);
    const response = await fetch(url, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    return response.ok ? ((await response.json()).context ?? "") : null;
  } catch {
    return null;
  }
}

// When the server does not answer: start it and wait, with the same command as the Claude Code session
// hook. Its answer is the session context, read straight from notes.db when the server could not start.
function startServer() {
  return new Promise((resolve) => {
    const [program, ...options] = DOCTRACKER;
    const child = execFile(program, [...options, "hook", "SessionStart", "--url", BASE_URL],
      { cwd: PROJECT_ROOT, timeout: START_TIMEOUT_MS }, (error, stdout) => {
        try {
          resolve(JSON.parse(stdout).hookSpecificOutput.additionalContext ?? null);
        } catch {
          resolve(null);
        }
      });
    child.stdin.end(JSON.stringify({ hook_event_name: "SessionStart", cwd: PROJECT_ROOT }));
  });
}

// The id of the running server process (each answer of the hook routes names it); null when it does not answer.
async function serverID() {
  try {
    const response = await fetch(`${BASE_URL}/hooks/context/commit`, { signal: AbortSignal.timeout(TIMEOUT_MS) });
    return response.ok ? ((await response.json()).server ?? null) : null;
  } catch {
    return null;
  }
}

// Make sure the server answers and OpenCode's MCP connection reaches it: start the server when it does not
// answer (unless `start` is false), and reconnect the MCP server when the server is not the one it connected
// to. OpenCode's connection does not survive a server restart, its status still says "connected" and a
// plain reload keeps it, so the MCP config carries the server's id (`SERVER_HEADER`): a new id changes the
// config, and the reload connects again. Returns the session context of a server it had to start, or null.
// Calls made while one runs share it.
let ensuring = null;
let connectedTo = null; // the server id OpenCode's MCP connection was made to
function ensure(ctx, { loading = false, start = true } = {}) {
  ensuring ??= (async () => {
    try {
      let id = await serverID();
      const started = id === null && start ? await startServer() : null;
      id ??= await serverID();
      if (id !== null && id !== connectedTo) {
        // While the plugin loads, an MCP connection that already exists was made before (the plugin reloaded).
        const servers = loading ? ((await ctx.mcp.list()).data ?? []) : [];
        const reconnect = !loading || servers.some((server) => server.name === "doctracker");
        connectedTo = id;
        if (reconnect) await ctx.mcp.reload();
      }
      return started;
    } catch {
      return null;
    } finally {
      ensuring = null;
    }
  })();
  return ensuring;
}

// The files a tool call read or changed (paths as the tool got them; the server resolves relative ones).
function toolFiles(tool, input) {
  if (FILE_TOOLS.includes(tool)) {
    const path = input.filePath ?? input.path ?? input.file_path;
    return path ? [path] : [];
  }
  if (tool === "apply_patch" && input.patchText) {
    return [...input.patchText.matchAll(PATCH_FILE)].map((match) => match[1].trim());
  }
  return [];
}

export default {
  id: "doctracker",
  setup: async (ctx) => {
    // Per agent session: its context, its planning context, its last agent and whether it just left `plan`.
    // A context the server did not give (null) is asked again on the next call.
    const sessions = new Map();
    const session = (id) => {
      if (!sessions.has(id)) sessions.set(id, {});
      return sessions.get(id);
    };

    // Before anything else, the server must be up: OpenCode waits for the plugin, then connects the MCP server.
    let started = await ensure(ctx, { loading: true });

    // The doctracker MCP server, unless the user configured it already, with the id of the server it connects to.
    await ctx.mcp.transform((editor) => {
      if (!editor.get("doctracker")) {
        const headers = { [SERVER_HEADER]: connectedTo ?? "" };
        editor.set("doctracker", { type: "remote", url: `${BASE_URL}/mcp`, headers });
      }
    });

    // OpenCode runs as a long-lived service: a server restart between sessions is caught here, before the
    // next session lists the MCP tools. A server that was stopped is started again by the next session.
    setInterval(() => ensure(ctx, { start: false }), WATCH_MS).unref?.();

    // Every model call: the system prompt is rebuilt each time, so what must stay is added each time,
    // from the cache. Subagents run in their own sessions and get the same.
    await ctx.session.hook("context", async (event) => {
      try {
        started = (await ensure(ctx)) ?? started;
        const current = session(event.sessionID);
        current.context ??= await ask("session", { session: event.sessionID });
        const texts = [current.context ?? started ?? SERVER_DOWN.replace("{url}", BASE_URL)];
        if (current.agent === "plan" && event.agent !== "plan") current.leftPlan = true;
        current.agent = event.agent;
        if (event.agent === "plan") {
          current.planning ??= await ask("planning", { session: event.sessionID });
          texts.push(current.planning);
        }
        if (current.leftPlan) texts.push(RECORD_THE_PLAN);
        for (const text of texts) if (text) event.system.push({ type: "text", text });
      } catch {
        // A failed hook must not stop the agent.
      }
    });

    // A new prompt ends the turn in which the plan had to be recorded.
    await ctx.session.hook("prompt", (event) => {
      if (sessions.has(event.sessionID)) session(event.sessionID).leftPlan = false;
    });

    // Before a summary: the contexts are asked again afterwards, as SessionStart does after a compact.
    await ctx.session.hook("compaction", (event) => {
      sessions.delete(event.sessionID);
    });

    // Before a call of doctracker's tools (MCP tools are called by name, or from code run by `execute`):
    // the server may have restarted since the model was called.
    await ctx.tool.hook("execute.before", async (event) => {
      if (`${event.tool} ${JSON.stringify(event.input ?? {})}`.includes("doctracker")) await ensure(ctx);
    });

    // The notes of a file read or edited, once per file per session, added to the tool's result.
    await ctx.tool.hook("execute.after", async (event) => {
      try {
        if (event.status !== "completed") return;
        for (const path of toolFiles(event.tool, event.input ?? {})) {
          const text = await ask("file", { session: event.sessionID, once: "1", path });
          if (!text) continue;
          const content = event.result.content ?? "";
          event.result = {
            ...event.result,
            content: typeof content === "string" ? `${content}\n\n${text}` : [...content, { type: "text", text }],
          };
        }
      } catch {
        // A failed hook must not stop the agent.
      }
    });
  },
};
