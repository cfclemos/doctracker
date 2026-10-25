// Live updates: the server sends a "changed" event when the code changes,
// and every element listening to "docs-changed" reloads itself through htmx.
const events = new EventSource("/events");
events.addEventListener("changed", () => htmx.trigger(document.body, "docs-changed"));

// Tree: remember which branches the user opened or closed, so they stay that way
// when the tree is re-rendered (navigation or live update).
const TREE_KEY = "doctracker-tree";

function loadTree() {
  try {
    return JSON.parse(sessionStorage.getItem(TREE_KEY)) || {};
  } catch {
    return {};
  }
}

function saveTree(state) {
  try {
    sessionStorage.setItem(TREE_KEY, JSON.stringify(state));
  } catch {}
}

document.addEventListener("toggle", (event) => {
  const branch = event.target;
  if (!branch.matches || !branch.matches("#tree details")) return;
  const state = loadTree();
  state[branch.dataset.path] = branch.open;
  saveTree(state);
}, true);

function restoreTree() {
  const state = loadTree();
  for (const branch of document.querySelectorAll("#tree details")) {
    const containsCurrent = branch.querySelector("a.current") !== null;
    if (branch.dataset.path in state && !containsCurrent) branch.open = state[branch.dataset.path];
  }
}

document.addEventListener("DOMContentLoaded", restoreTree);
document.addEventListener("htmx:afterSettle", restoreTree);

// Tree width (drag the resizer) and visibility (toggle button), kept per browser.
const WIDTH_KEY = "doctracker-tree-width";
const HIDDEN_KEY = "doctracker-tree-hidden";
const MIN_WIDTH = 160;
const MAX_WIDTH = 640;

function setTreeWidth(pixels) {
  const width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, pixels));
  document.documentElement.style.setProperty("--tree-width", `${width}px`);
  return width;
}

function readSetting(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

// Code theme: the select in the Source block swaps the stylesheet of the source code right away;
// htmx posts the choice to the server, which saves it in config.json.
document.addEventListener("change", (event) => {
  if (!event.target.matches(".code-theme-select")) return;
  document.getElementById("code-theme").href = `/code-theme/${event.target.value}.css`;
});

// Search box: the server returns the options; this handles opening, closing and the keyboard
// (↑/↓ move, Enter opens, Esc closes, "/" focuses the box from anywhere).
document.addEventListener("DOMContentLoaded", () => {
  const box = document.getElementById("search");
  const input = document.getElementById("search-input");
  const results = document.getElementById("search-results");
  const clear = document.getElementById("search-clear");
  const options = () => [...results.querySelectorAll('[role="option"]')];

  const open = () => {
    box.classList.add("open");
    input.setAttribute("aria-expanded", "true");
  };
  const close = () => {
    box.classList.remove("open");
    input.setAttribute("aria-expanded", "false");
  };
  const select = (index) => {
    options().forEach((option, i) => option.setAttribute("aria-selected", String(i === index)));
    const chosen = options()[index];
    if (chosen) chosen.scrollIntoView({ block: "nearest" });
  };
  const selected = () => options().findIndex((option) => option.getAttribute("aria-selected") === "true");

  input.addEventListener("input", () => { clear.hidden = !input.value; });
  results.addEventListener("htmx:afterSwap", () => {
    if (document.activeElement === input) open();
    select(0);
  });
  input.addEventListener("focus", () => { if (input.value) open(); });

  input.addEventListener("keydown", (event) => {
    const count = options().length;
    if (event.key === "ArrowDown" && count) {
      event.preventDefault();
      open();
      select((selected() + 1) % count);
    } else if (event.key === "ArrowUp" && count) {
      event.preventDefault();
      select((selected() - 1 + count) % count);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const chosen = options()[Math.max(selected(), 0)];
      if (chosen) chosen.querySelector("a").click();
    } else if (event.key === "Escape") {
      close();
      input.blur();
    }
  });

  // Keep focus in the box while clicking an option, then close after navigating.
  results.addEventListener("mousedown", (event) => event.preventDefault());
  results.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      close();
      input.blur();
    }
  });
  input.addEventListener("blur", close);

  clear.addEventListener("click", () => {
    input.value = "";
    clear.hidden = true;
    results.innerHTML = "";
    close();
    input.focus();
  });

  document.addEventListener("keydown", (event) => {
    const typing = ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
    if (event.key === "/" && !typing) {
      event.preventDefault();
      input.focus();
      input.select();
    }
  });
});

document.addEventListener("DOMContentLoaded", () => {
  const savedWidth = Number(readSetting(WIDTH_KEY));
  if (savedWidth) setTreeWidth(savedWidth);
  if (readSetting(HIDDEN_KEY) === "true") document.body.classList.add("tree-hidden");

  document.getElementById("tree-toggle").addEventListener("click", () => {
    const hidden = document.body.classList.toggle("tree-hidden");
    writeSetting(HIDDEN_KEY, String(hidden));
  });

  document.getElementById("tree-resizer").addEventListener("pointerdown", (event) => {
    event.preventDefault();
    document.body.classList.add("resizing");
    let width = null;
    const move = (moveEvent) => { width = setTreeWidth(moveEvent.clientX); };
    const stop = () => {
      document.body.classList.remove("resizing");
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
      if (width) writeSetting(WIDTH_KEY, String(width));
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
  });
});
