// Live updates: the server sends a "changed" event when the code or the notes change,
// and every element listening to "docs-changed" reloads itself through htmx.
// While a modal is open (something is being filled in), the reload waits until it closes.
const events = new EventSource("/events");
let reloadWaiting = false;
let ownChangeUntil = 0;  // a change this page just sent: its own answer already shows it
events.addEventListener("changed", () => {
  if (Date.now() < ownChangeUntil) return;
  if (document.querySelector("dialog[open]")) reloadWaiting = true;
  else htmx.trigger(document.body, "docs-changed");
});
document.addEventListener("htmx:beforeRequest", (event) => {
  if (event.detail.requestConfig?.verb === "post" && event.detail.requestConfig.path?.startsWith("/notes/")) {
    ownChangeUntil = Date.now() + 3000;
  }
});
document.addEventListener("close", (event) => {
  if (event.target.matches("dialog") && reloadWaiting) {
    reloadWaiting = false;
    htmx.trigger(document.body, "docs-changed");
  }
}, true);  // "close" does not bubble: listen while it goes down

// Modals of the notes page: their content is loaded into the dialog, which then opens; × closes it.
document.addEventListener("htmx:afterSwap", (event) => {
  const dialog = event.detail.target.closest?.("dialog");
  if (dialog && !dialog.open) dialog.showModal();
});
document.addEventListener("click", (event) => {
  if (event.target.closest(".dialog-close")) event.target.closest("dialog")?.close();
});

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

// Planner page: the bar between the drawing and the panel sets how much of the width the drawing
// takes (25% to 75%, half at first), remembered in the browser.
const SPLIT_KEY = "doctracker-planner-split";

function applyPlannerSplit() {
  const layout = document.querySelector(".planner-layout");
  const share = load(localStorage, SPLIT_KEY, null);
  if (layout && share) layout.style.setProperty("--split", `${share}%`);
}
document.addEventListener("DOMContentLoaded", applyPlannerSplit);
document.addEventListener("htmx:afterSettle", applyPlannerSplit);

document.addEventListener("pointerdown", (event) => {
  const splitter = event.target.closest(".planner-splitter");
  if (!splitter) return;
  event.preventDefault();
  const layout = splitter.closest(".planner-layout");
  document.body.classList.add("splitting");
  let share = null;
  const move = (moveEvent) => {
    const bounds = layout.getBoundingClientRect();
    share = Math.round(Math.min(75, Math.max(25, ((moveEvent.clientX - bounds.left) / bounds.width) * 100)) * 10) / 10;
    layout.style.setProperty("--split", `${share}%`);
  };
  const stop = () => {
    document.body.classList.remove("splitting");
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", stop);
    if (share) save(localStorage, SPLIT_KEY, share);
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", stop);
});

// Text boxes of the notes forms (planner panel, modals) grow to show all their text.
function growTextBox(box) {
  box.style.height = "auto";
  box.style.height = `${box.scrollHeight + 2}px`;
}
function growTextBoxes(root) {
  for (const box of root.querySelectorAll(".notes-form textarea, textarea.grow-line")) growTextBox(box);
}
document.addEventListener("input", (event) => {
  if (event.target.matches(".notes-form textarea, textarea.grow-line")) growTextBox(event.target);
});
// One-line texts (titles, evidence, annotations) wrap and grow when long, but Enter does not start a new
// line: in an edited row it saves; elsewhere it leaves the field (which saves) or sends a new item's form.
document.addEventListener("keydown", (event) => {
  const field = event.target;
  if (event.key !== "Enter" || event.shiftKey || !field.matches?.("textarea.grow-line")) return;
  event.preventDefault();
  if (field.closest(".row-edit") || field.closest("[hx-post*='/create_'], [hx-post*='/add_']")) htmx.trigger(field.form, "submit");
  else field.blur();
});
document.addEventListener("htmx:afterSwap", (event) => growTextBoxes(event.detail.elt || document));  // before it shows
document.addEventListener("toggle", (event) => growTextBoxes(event.target), true);  // folded sections opened

// Dependency autocomplete (planner panel): the suggestions are the tree of plans, features and tasks,
// each labeled with its level; typing keeps the items whose name contains the text and the items above
// them, so it is always clear where an item belongs. A click (or Enter) ticks an item, and again unticks
// it; the list stays open to tick several. Each ticked item is a tag in the field (a hidden depends_on
// field); × removes it, Backspace on an empty field removes the last one, the arrows move through the
// items that can be chosen.
function waitsParts(search) {
  const box = search.closest(".waits-input");
  const form = search.closest(".waits-form");
  return { box, form, list: form.querySelector(".waits-suggestions"), chips: box.querySelector(".waits-chips"),
    choices: JSON.parse(box.dataset.choices || "[]") };
}

function waitsShow(search) {
  const { list, chips, choices } = waitsParts(search);
  const taken = new Set([...chips.querySelectorAll("input")].map((input) => input.value));
  const text = search.value.trim().toLowerCase();
  const byRef = Object.fromEntries(choices.map((choice) => [choice.ref, choice]));
  const shown = new Set();
  for (const choice of choices) {
    if (text && !choice.title.toLowerCase().includes(text)) continue;
    for (let current = choice; current && !shown.has(current.ref); current = byRef[current.parent]) shown.add(current.ref);
  }
  const self = waitsParts(search).form.querySelector("input[name=item]")?.value;
  const rows = choices.filter((choice) => shown.has(choice.ref) && choice.ref !== self);
  const previous = list.querySelector(".waits-suggestion.active")?.dataset.ref;
  let first = true;
  list.innerHTML = rows.length ? rows.map((choice) => {
    const chosen = taken.has(choice.ref);
    const active = choice.allowed && (previous ? previous === choice.ref : first);
    if (choice.allowed) first = false;
    return `<li class="waits-suggestion depth-${choice.depth}${choice.allowed ? "" : " context"}${chosen ? " chosen" : ""}${active ? " active" : ""}"
        role="option" aria-selected="${chosen}" aria-disabled="${!choice.allowed}" data-ref="${escapeHtml(choice.ref)}">
      <span class="waits-check">${chosen ? "✓" : ""}</span>
      <i class="level-icon level-${choice.level}" title="${escapeHtml(choice.level)}"></i>
      <span class="waits-title">${escapeHtml(choice.title)}</span>
      <span class="waits-state state-${choice.state}" title="${escapeHtml(choice.state)}"></span></li>`;
  }).join("") : '<li class="waits-empty">Nothing found.</li>';
  list.hidden = false;
  search.setAttribute("aria-expanded", "true");
}

function waitsHide(search) {
  waitsParts(search).list.hidden = true;
  search.setAttribute("aria-expanded", "false");
}

function waitsPick(search, ref) {
  const { chips, choices } = waitsParts(search);
  const choice = choices.find((entry) => entry.ref === ref);
  if (!choice) return;
  const tag = [...chips.querySelectorAll("input")].find((input) => input.value === ref);
  if (tag) {  // ticked already: untick
    tag.closest(".waits-chip").remove();
    waitsShow(search);
    search.focus();
    return;
  }
  chips.insertAdjacentHTML("beforeend", `<span class="waits-chip" title="${escapeHtml(choice.level)}: ${escapeHtml(choice.title)}">
    <span>${escapeHtml(choice.title)}</span><button type="button" class="waits-remove" aria-label="Remove">×</button>
    <input type="hidden" name="depends_on" value="${escapeHtml(ref)}"></span>`);
  waitsShow(search);
  search.focus();
}

document.addEventListener("focusin", (event) => {
  if (event.target.matches(".waits-search")) waitsShow(event.target);
});
document.addEventListener("focusout", (event) => {
  if (event.target.matches(".waits-search")) setTimeout(() => waitsHide(event.target), 150);
});
document.addEventListener("input", (event) => {
  if (event.target.matches(".waits-search")) waitsShow(event.target);
});
document.addEventListener("keydown", (event) => {
  const search = event.target;
  if (!search.matches?.(".waits-search")) return;
  const { list, chips } = waitsParts(search);
  const items = [...list.querySelectorAll(".waits-suggestion:not(.context)")];
  const active = list.querySelector(".waits-suggestion.active");
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    const next = items[(items.indexOf(active) + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length];
    active?.classList.remove("active");
    next?.classList.add("active");
    next?.scrollIntoView({ block: "nearest" });
  } else if (event.key === "Enter") {
    if (!list.hidden && active) {
      event.preventDefault();  // pick, do not submit
      waitsPick(search, active.dataset.ref);
    }
  } else if (event.key === "Escape") {
    waitsHide(search);
  } else if (event.key === "Backspace" && !search.value && chips.lastElementChild) {
    chips.lastElementChild.remove();
    waitsShow(search);
  }
});
document.addEventListener("mousedown", (event) => {
  const suggestion = event.target.closest(".waits-suggestion");
  if (!suggestion) return;
  if (suggestion.classList.contains("context")) return event.preventDefault();  // shown for the tree only
  event.preventDefault();  // keep the focus in the field
  waitsPick(suggestion.closest(".waits-form").querySelector(".waits-search"), suggestion.dataset.ref);
});
document.addEventListener("click", (event) => {
  if (event.target.closest(".waits-remove")) {
    const form = event.target.closest(".waits-form");
    event.target.closest(".waits-chip").remove();
    const search = form.querySelector(".waits-search");
    if (!form.querySelector(".waits-suggestions").hidden) waitsShow(search);
  }
  else if (event.target.matches(".waits-input")) event.target.querySelector(".waits-search").focus();
});

// Confirmations: every hx-confirm of the wiki asks in the one confirmation modal of the page, instead of
// the browser's box. Confirm sends the request; Cancel does not (and puts back a checkbox just ticked).
document.addEventListener("htmx:confirm", (event) => {
  const question = event.detail.question;
  const dialog = document.getElementById("confirm-dialog");
  if (!question || !dialog) return;
  event.preventDefault();
  const title = event.detail.elt.closest("[data-confirm-title]")?.dataset.confirmTitle || "Confirm";
  const deleting = /^delete/i.test(title) || /^delete/i.test(question);
  dialog.querySelector(".confirm-title").textContent = title;
  dialog.querySelector(".confirm-text").textContent = question;
  dialog.classList.toggle("deleting", deleting);
  dialog.querySelector(".confirm-ok").classList.toggle("danger-fill", deleting);
  dialog.returnValue = "";
  dialog.addEventListener("close", () => {
    if (dialog.returnValue === "ok") return event.detail.issueRequest(true);
    const box = event.detail.triggeringEvent?.type === "change" && event.detail.triggeringEvent.target;
    if (box?.type === "checkbox") box.checked = !box.checked;
  }, { once: true });
  dialog.showModal();
});

// Planner panel sections fold and unfold; the folded ones stay folded from one item to the next.
const SECTIONS_KEY = "doctracker-panel-sections";
document.addEventListener("toggle", (event) => {
  const section = event.target;
  if (!section.matches?.(".panel-section")) return;
  const folded = load(localStorage, SECTIONS_KEY, {});
  folded[section.dataset.section] = !section.open;
  save(localStorage, SECTIONS_KEY, folded);
}, true);
// Folded before the new content shows (afterSwap), so it never opens and then jumps shut.
document.addEventListener("htmx:afterSwap", (event) => {
  const folded = load(localStorage, SECTIONS_KEY, {});
  for (const section of (event.detail.elt || document).querySelectorAll(".panel-section")) {
    if (folded[section.dataset.section]) section.open = false;
  }
});

// The planner's panel keeps its scroll position when it is redrawn after a change.
let panelScroll = null;
document.addEventListener("htmx:beforeSwap", (event) => {
  if (event.detail.target?.id === "planner-detail") panelScroll = event.detail.target.scrollTop;
});
document.addEventListener("htmx:afterSwap", (event) => {
  if (event.detail.target?.id !== "planner-detail" || panelScroll === null) return;
  event.detail.target.scrollTop = panelScroll;
  panelScroll = null;
});

// Rows edited in place (evidence and annotations of a task): the pencil shows the field; Enter or leaving
// it saves (the form sends itself); Esc puts the text back and closes it.
document.addEventListener("click", (event) => {
  const row = event.target.closest(".editable-row");
  if (row && event.target.closest(".row-edit-open")) {
    row.classList.add("editing");
    const field = row.querySelector(".row-edit textarea, .row-edit input:not([type=hidden])");
    if (field?.matches("textarea")) growTextBox(field);  // it was hidden: measure it now
    field?.focus();
  }
});
document.addEventListener("keydown", (event) => {
  const field = event.target.closest?.(".row-edit input, .row-edit textarea");
  if (!field || event.key !== "Escape") return;
  event.preventDefault();  // not the modal's own Escape
  field.value = field.defaultValue;
  field.closest(".editable-row").classList.remove("editing");
});

// A note saved by itself in its modal: the page's list catches up when the modal closes.
document.addEventListener("notes-saved", () => { reloadWaiting = true; });

// Notes tree: the note clicked is marked as the one shown in the panel.
document.addEventListener("click", (event) => {
  const note = event.target.closest(".tree-note");
  if (!note) return;
  for (const other of note.closest(".notes-tree").querySelectorAll(".tree-note.current")) other.classList.remove("current");
  note.classList.add("current");
});

// Notes tree: types start closed; the ones the user opens stay open while working (also when the tree
// comes back after a change), remembered for this tab of the browser.
const OPEN_TYPES_KEY = "doctracker-notes-open-types";
document.addEventListener("toggle", (event) => {
  const type = event.target;
  if (!type.matches?.(".tree-type")) return;
  const open = new Set(load(sessionStorage, OPEN_TYPES_KEY, []));
  if (type.open) open.add(type.dataset.type);
  else open.delete(type.dataset.type);
  save(sessionStorage, OPEN_TYPES_KEY, [...open]);
}, true);
function reopenTypes(root) {
  const open = new Set(load(sessionStorage, OPEN_TYPES_KEY, []));
  for (const type of root.querySelectorAll(".tree-type")) if (open.has(type.dataset.type)) type.open = true;
}
document.addEventListener("DOMContentLoaded", () => reopenTypes(document));
document.addEventListener("htmx:afterSwap", () => reopenTypes(document));
document.addEventListener("htmx:oobAfterSwap", () => reopenTypes(document));
