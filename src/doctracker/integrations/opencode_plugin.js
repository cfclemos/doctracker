// doctracker's OpenCode plugin (OpenCode 2 plugin API): gives doctracker's context to the agent at the
// same moments as the Claude Code hooks. Written by `doctracker init` / `doctracker start`, which fill in
// the values below; changes made here are lost when it is written again.

const BASE_URL = __BASE_URL__;
const SERVER_DOWN = __SERVER_DOWN__;
const RECORD_THE_PLAN = __RECORD_THE_PLAN__;

const TIMEOUT_MS = 2000; // a hook never waits longer than this for the server
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

    // The doctracker MCP server, unless the user configured it already.
    await ctx.mcp.transform((editor) => {
      if (!editor.get("doctracker")) editor.set("doctracker", { type: "remote", url: `${BASE_URL}/mcp` });
    });

    // Every model call: the system prompt is rebuilt each time, so what must stay is added each time,
    // from the cache. Subagents run in their own sessions and get the same.
    await ctx.session.hook("context", async (event) => {
      try {
        const current = session(event.sessionID);
        current.context ??= await ask("session", { session: event.sessionID });
        const texts = [current.context ?? SERVER_DOWN.replace("{url}", BASE_URL)];
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
