// Live updates: the server sends a "changed" event when the code changes,
// and every element listening to "docs-changed" reloads itself through htmx.
const events = new EventSource("/events");
events.addEventListener("changed", () => htmx.trigger(document.body, "docs-changed"));

// Browser storage for small preferences, as JSON. Storage can be unavailable
// (private mode, blocked site data): reads then return the fallback, writes do nothing.
function load(storage, key, fallback) {
  try {
    const value = JSON.parse(storage.getItem(key));
    return value === null ? fallback : value;
  } catch {
    return fallback;
  }
}

function save(storage, key, value) {
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {}
}

// Tree: remember which branches the user opened or closed (per tab), so they stay that way
// when the tree is re-rendered (navigation or live update).
const TREE_KEY = "doctracker-tree-v2";  // v2: first level folded by default

document.addEventListener("toggle", (event) => {
  const branch = event.target;
  if (!branch.matches || !branch.matches("#tree details")) return;
  const state = load(sessionStorage, TREE_KEY, {});
  state[branch.dataset.path] = branch.open;
  save(sessionStorage, TREE_KEY, state);
}, true);

function restoreTree() {
  const state = load(sessionStorage, TREE_KEY, {});
  for (const branch of document.querySelectorAll("#tree details")) {
    if (branch.dataset.path in state) branch.open = state[branch.dataset.path];
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

// Git page: mark the clicked commit (its changes load on the right through htmx), and
// show one file of the commit at a time: chosen in the select, or stepped with ‹ ›.
function showGitFile(panel, index) {
  const select = panel.querySelector(".git-file-select");
  const count = select.options.length;
  index = (index + count) % count;
  select.selectedIndex = index;
  for (const diff of panel.querySelectorAll(".git-file-diff")) diff.hidden = Number(diff.dataset.file) !== index;
  const option = select.options[index];
  const stats = panel.querySelector(".git-file-stats");
  stats.innerHTML = `<span class="git-file-status ${option.dataset.status}">${option.dataset.status}</span>
    <span class="plus">+${option.dataset.additions}</span> <span class="minus">−${option.dataset.deletions}</span>`;
  panel.querySelector(".git-file-position").textContent = `${index + 1} / ${count}`;
  panel.querySelector(`.git-file-diff[data-file="${index}"]`)?.scrollTo(0, 0);
}

// A × inside a text field (.field-clearable) empties it; it shows only while the field has text.
document.addEventListener("input", (event) => {
  const clear = event.target.closest(".field-clearable")?.querySelector(".field-clear");
  if (clear) clear.hidden = !event.target.value;
});
document.addEventListener("click", (event) => {
  const clear = event.target.closest(".field-clear");
  if (!clear) return;
  event.preventDefault();
  const input = clear.closest(".field-clearable").querySelector("input");
  input.value = "";
  clear.hidden = true;
  input.focus();
});

// Mark a commit of the git page's list as selected (which opens its full message) and scroll
// the list so it is at the top. Used by clicks on the list and on the branch graph.
function markGitCommit(hash) {
  for (const item of document.querySelectorAll(".git-commit-item")) {
    item.classList.toggle("current", item.dataset.hash === hash);
    if (item.dataset.hash !== hash) continue;
    const list = item.closest(".git-commits");
    list.scrollTop += item.closest(".git-commit").getBoundingClientRect().top - list.getBoundingClientRect().top;
  }
}

document.addEventListener("click", (event) => {
  const commit = event.target.closest(".git-commit-item");
  if (commit) {
    markGitCommit(commit.dataset.hash);
    return;
  }
  const step = event.target.closest(".git-step");
  if (step) {
    const panel = step.closest(".git-diff");
    showGitFile(panel, panel.querySelector(".git-file-select").selectedIndex + Number(step.dataset.step));
  }
});

document.addEventListener("change", (event) => {
  if (event.target.matches(".git-file-select")) showGitFile(event.target.closest(".git-diff"), event.target.selectedIndex);
});

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

  // Search mode buttons: pick the mode, then search again with the text already typed.
  const mode = document.getElementById("search-mode");
  for (const button of document.querySelectorAll(".search-modes button")) {
    button.addEventListener("click", () => {
      for (const other of document.querySelectorAll(".search-modes button")) {
        other.setAttribute("aria-checked", String(other === button));
      }
      mode.value = button.dataset.mode;
      input.placeholder = button.dataset.placeholder;
      input.focus();
      if (input.value) htmx.trigger(input, "search-mode-changed");
    });
  }

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
  const savedWidth = load(localStorage, WIDTH_KEY, null);
  if (savedWidth) setTreeWidth(savedWidth);
  if (load(localStorage, HIDDEN_KEY, false)) document.body.classList.add("tree-hidden");

  document.getElementById("tree-toggle").addEventListener("click", () => {
    const hidden = document.body.classList.toggle("tree-hidden");
    save(localStorage, HIDDEN_KEY, hidden);
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
      if (width) save(localStorage, WIDTH_KEY, width);
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
  });
});
