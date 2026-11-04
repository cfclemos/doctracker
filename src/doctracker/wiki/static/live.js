// Live updates: the server sends a "changed" event when the code or the notes change,
// and every element listening to "docs-changed" reloads itself through htmx.
// While a modal is open (something is being filled in), the reload waits until it closes.
// When the connection comes back after dropping (e.g. the server restarted), the page reloads too:
// changes made while it was down were never announced to it.
const events = new EventSource("/events");
let reloadWaiting = false;
let ownChangeUntil = 0;  // a change this page just sent: its own answer already shows it
let dropped = false;  // the connection dropped since it last opened
function reloadContent() {
  if (document.querySelector("dialog[open]")) reloadWaiting = true;
  else htmx.trigger(document.body, "docs-changed");
}
events.addEventListener("changed", () => {
  if (Date.now() < ownChangeUntil) return;
  reloadContent();
});
events.addEventListener("error", () => { dropped = true; });
events.addEventListener("open", () => {
  if (!dropped) return;
  dropped = false;
  reloadContent();
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

// The row of plan cards (newest first) keeps where the user scrolled to when a reload puts it back, and
// tells the New plan button beside it how tall its scrollbar is (none when the cards fit), so the button
// stays as tall as the cards and the scrollbar runs under the cards only.
let planCardsLeft = 0;  // scroll position of the row, kept across reloads of the same page
function measurePlanCards() {
  for (const row of document.querySelectorAll(".plan-cards-row")) {
    row.parentElement.style.setProperty("--plan-scrollbar", `${row.offsetHeight - row.clientHeight}px`);
  }
}
function scrollPlanCards() {
  for (const row of document.querySelectorAll(".plan-cards-row:not([data-scrolled])")) {
    row.dataset.scrolled = "1";
    row.scrollLeft = planCardsLeft;
    row.addEventListener("scroll", () => { planCardsLeft = row.scrollLeft; });
  }
  measurePlanCards();
}
document.addEventListener("DOMContentLoaded", scrollPlanCards);
document.addEventListener("htmx:afterSettle", scrollPlanCards);
window.addEventListener("resize", measurePlanCards);

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
const TREE_KEY = "doctracker-tree-v4";  // v4: branches kept by their place in the tree

document.addEventListener("toggle", (event) => {
  const branch = event.target;
  if (!branch.matches || !branch.matches("#tree details")) return;
  const state = load(sessionStorage, TREE_KEY, {});
  state[branch.dataset.path] = branch.open;
  save(sessionStorage, TREE_KEY, state);
}, true);

// Every page sends the tree again (to mark the current item): it keeps where the user scrolled to.
let treeScroll = null;
document.addEventListener("htmx:oobBeforeSwap", (event) => {
  if (event.detail.target?.id === "tree") treeScroll = event.detail.target.scrollTop;
});

function restoreTree() {
  const state = load(sessionStorage, TREE_KEY, {});
  for (const branch of document.querySelectorAll("#tree details")) {
    if (branch.dataset.path in state) branch.open = state[branch.dataset.path];
  }
  if (treeScroll !== null) {
    document.getElementById("tree").scrollTop = treeScroll;
    treeScroll = null;
  }
}

document.addEventListener("DOMContentLoaded", restoreTree);
document.addEventListener("htmx:afterSettle", restoreTree);

// View settings kept in cookies, so the server builds every page with them: the tree's format
// (button beside CODE) and the languages the whole wiki shows (select in the search bar).
function setViewSetting(name, value) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
  reloadContent();
}

document.addEventListener("click", (event) => {
  const button = event.target.closest(".tree-layout");
  if (!button) return;
  event.preventDefault();  // the buttons sit in CODE's summary: a click must not close it
  setViewSetting("tree-layout", button.dataset.layout);
});
document.addEventListener("change", (event) => {
  if (event.target.classList.contains("language-filter")) setViewSetting("languages", event.target.value);
});

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
// A field emptied, by the × or by erasing it, counts as changed at once: what it filtered is redone.
document.addEventListener("input", (event) => {
  const clear = event.target.closest(".field-clearable")?.querySelector(".field-clear");
  if (!clear) return;
  clear.hidden = !event.target.value;
  if (!event.target.value) event.target.dispatchEvent(new Event("change", { bubbles: true }));
});
document.addEventListener("click", (event) => {
  const clear = event.target.closest(".field-clear");
  if (!clear) return;
  event.preventDefault();
  const input = clear.closest(".field-clearable").querySelector("input");
  input.value = "";
  clear.hidden = true;
  input.focus();
  input.dispatchEvent(new Event("change", { bubbles: true }));
});

// The Focus fields of the diagrams: an autocomplete under the field, from the choices of its
// data-options (a datalist kept out of the browser's own list): what has the text typed in its name or
// path, names that start with it first, each with its kind's icon, its name and its path.
// ↑ ↓ move, Enter or a click chooses (the form then draws again), Escape closes.
const FOCUS_CHOICES = 50;
function focusMenu(input) {
  let menu = input.parentElement.querySelector(".focus-menu");
  if (!menu) {
    menu = document.createElement("ul");
    menu.className = "focus-menu";
    menu.setAttribute("role", "listbox");
    input.after(menu);
  }
  return menu;
}
function showFocusChoices(input) {
  const text = input.value.trim().toLowerCase();
  const options = [...(document.getElementById(input.dataset.options)?.options || [])];
  const found = options.filter((option) => !text || option.value.toLowerCase().includes(text))
    .sort((a, b) => Number(!a.dataset.name.toLowerCase().startsWith(text)) - Number(!b.dataset.name.toLowerCase().startsWith(text)))
    .slice(0, FOCUS_CHOICES);
  const menu = focusMenu(input);
  menu.innerHTML = found.map((option, index) => `<li role="option" data-value="${escapeHtml(option.value)}"${index === 0 ? ' class="active"' : ""}>
    <span class="icon icon-${escapeHtml(option.dataset.role)}">${escapeHtml(option.dataset.symbol)}</span>
    <strong>${escapeHtml(option.dataset.name)}</strong><span class="focus-menu-path">${escapeHtml(option.value)}</span></li>`).join("")
    || '<li class="focus-menu-empty">Nothing has that name</li>';
  menu.hidden = false;
}
function chooseFocus(input, value) {
  input.value = value;
  focusMenu(input).hidden = true;
  const clear = input.closest(".field-clearable")?.querySelector(".field-clear");
  if (clear) clear.hidden = !value;
  input.dispatchEvent(new Event("change", { bubbles: true }));
}
document.addEventListener("focusin", (event) => {
  if (event.target.matches("input[data-options]")) showFocusChoices(event.target);
});
document.addEventListener("input", (event) => {
  if (event.target.matches("input[data-options]")) showFocusChoices(event.target);
});
document.addEventListener("focusout", (event) => {
  if (event.target.matches("input[data-options]")) focusMenu(event.target).hidden = true;
});
document.addEventListener("mousedown", (event) => {  // before the field loses the focus
  const item = event.target.closest(".focus-menu li[data-value]");
  if (!item) return;
  event.preventDefault();
  chooseFocus(item.closest(".field-clearable").querySelector("input[data-options]"), item.dataset.value);
});
document.addEventListener("keydown", (event) => {
  const input = event.target;
  if (!input.matches?.("input[data-options]")) return;
  const menu = focusMenu(input);
  const items = [...menu.querySelectorAll("li[data-value]")];
  const at = items.findIndex((item) => item.classList.contains("active"));
  if (event.key === "ArrowDown" || event.key === "ArrowUp") {
    event.preventDefault();
    if (menu.hidden) return showFocusChoices(input);
    const next = items[(at + (event.key === "ArrowDown" ? 1 : items.length - 1)) % items.length];
    items.forEach((item) => item.classList.toggle("active", item === next));
    next?.scrollIntoView({ block: "nearest" });
  } else if (event.key === "Enter" && !menu.hidden && items[at]) {
    event.preventDefault();
    chooseFocus(input, items[at].dataset.value);
  } else if (event.key === "Escape") {
    menu.hidden = true;
  }
});

// What is open around a drawing (legend, filters, evolution, details) is kept in the browser for that
// drawing only (the planner, Architecture, Classes... each its own): the key names the drawing.
const drawingKey = (area, what) => `doctracker-${what}-${area.querySelector(".graph-canvas")?.dataset.view}`;

// The Legend button of the drawings (right of Fit) opens the legend under it, in the drawing's top right
// corner; × or the button again closes it.
function placeLegends() {
  for (const box of document.querySelectorAll(".graph-legend-box")) {
    const open = load(localStorage, drawingKey(box.closest(".graph-area"), "legend-open"), false);
    box.hidden = !open;
    box.closest(".graph-area").querySelector(".graph-legend-open")?.setAttribute("aria-expanded", String(open));
  }
}
document.addEventListener("DOMContentLoaded", placeLegends);
document.addEventListener("htmx:afterSettle", placeLegends);
document.addEventListener("click", (event) => {
  const button = event.target.closest(".graph-legend-open, .graph-legend-box .graph-close");
  if (!button) return;
  const open = button.matches(".graph-legend-open") && button.getAttribute("aria-expanded") !== "true";
  save(localStorage, drawingKey(button.closest(".graph-area"), "legend-open"), open);
  placeLegends();
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
      fold();
    }
  });

  // On a small screen the search is one button: it opens the search as a panel under the bar, and folds
  // again on ×, Esc, a result chosen, or a click outside it with nothing typed.
  const search = document.getElementById("search");
  const unfold = () => { search.classList.add("searching"); input.focus(); };
  const fold = () => search.classList.remove("searching");
  document.querySelector(".search-open").addEventListener("click", () => {
    if (search.classList.contains("searching")) fold();
    else unfold();
  });
  search.querySelector(".search-fold").addEventListener("click", () => { close(); fold(); });

  // Keep focus in the box while clicking an option, then close after navigating.
  results.addEventListener("mousedown", (event) => event.preventDefault());
  results.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      close();
      input.blur();
      fold();
    }
  });
  input.addEventListener("blur", (event) => {
    close();
    // not when going to its filter, nor to the search button, whose click folds it itself
    if (!input.value && !search.contains(event.relatedTarget) && !event.relatedTarget?.closest(".search-open")) fold();
  });
  document.addEventListener("click", (event) => {
    if (!input.value && !search.contains(event.target) && !event.target.closest(".search-open")) fold();
  });

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
      unfold();
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

// The rows under a drawing's bar (the filters, the evolution) open and close from the bar's buttons;
// closed at first, kept for that drawing. A row the page needs open (nothing chosen yet) stays open.
function placeRows() {
  for (const button of document.querySelectorAll(".graph-row-toggle")) {
    const area = button.closest(".graph-area");
    const row = area.querySelector(`[data-row-of="${button.dataset.row}"]`);
    const open = load(localStorage, drawingKey(area, `${button.dataset.row}-open`), false) || row?.dataset.forced === "1";
    row?.classList.toggle("closed", !open);
    button.setAttribute("aria-pressed", String(open));
  }
}
document.addEventListener("DOMContentLoaded", placeRows);
document.addEventListener("htmx:afterSettle", placeRows);
document.addEventListener("click", (event) => {
  const button = event.target.closest(".graph-row-toggle");
  if (!button) return;
  save(localStorage, drawingKey(button.closest(".graph-area"), `${button.dataset.row}-open`), button.getAttribute("aria-pressed") !== "true");
  placeRows();
});

// Expand: the drawing's area opens in a modal over the page (the class `expanded`); the same button, now
// an ×, or Escape close it. Nothing is moved, so the drawing keeps its state and refits by itself.
function expandDrawing(area, on) {
  area.classList.toggle("expanded", on);
  document.body.classList.toggle("drawing-expanded", on);
  const button = area.querySelector(".graph-expand");
  button.setAttribute("aria-label", on ? "Close" : "Expand");
  button.dataset.tip = on ? "Close" : "Expand";
}
document.addEventListener("click", (event) => {
  if (!event.target.closest(".graph-expand")) return;
  const area = event.target.closest(".graph-area");
  expandDrawing(area, !area.classList.contains("expanded"));
});
document.addEventListener("keydown", (event) => {
  const area = document.querySelector(".graph-area.expanded");
  if (event.key === "Escape" && area && !document.querySelector("dialog[open]")) expandDrawing(area, false);
});
document.addEventListener("htmx:beforeSwap", (event) => {  // a new page: the modal goes with the old one
  if (event.detail.target?.id === "content") document.body.classList.remove("drawing-expanded");
});

// The consultation modal: an entity's page over everything, without leaving the drawing. Its names open
// in it too; the footer's actions (the page, the views) leave for them. ×, Escape or a click outside close it.
function openPageModal(path) {
  const dialog = document.getElementById("page-dialog");
  htmx.ajax("GET", `/wiki/${path}?modal=1`, { target: "#page-dialog-body" });
  if (!dialog.open) dialog.showModal();
}
// An action done from the modal that ends what it showed (a connection deleted) closes it.
document.body.addEventListener("page-dialog-done", () => document.getElementById("page-dialog")?.close());
document.addEventListener("htmx:afterSwap", (event) => {  // the names of the page shown open in the modal
  if (event.detail.target.id !== "page-dialog-body") return;
  event.detail.target.scrollTop = 0;
  for (const link of event.detail.target.querySelectorAll('[hx-get^="/wiki/"]')) {
    const plain = link.cloneNode(true);  // without the htmx handling it got: it would leave the drawing
    plain.removeAttribute("hx-get");
    plain.removeAttribute("hx-push-url");
    plain.dataset.pageModal = link.getAttribute("href").replace(/^\/wiki\//, "");
    link.replaceWith(plain);
  }
});
document.addEventListener("click", (event) => {
  const dialog = document.getElementById("page-dialog");
  const shown = event.target.closest("[data-page-modal]");
  if (shown) {
    event.preventDefault();
    openPageModal(shown.dataset.pageModal);
  } else if (event.target === dialog || event.target.closest(".page-dialog-close")) {
    dialog.close();
  } else if (event.target.closest('#page-dialog [hx-target="#content"]')) {  // leaving for a page or a view
    dialog.close();
    document.querySelector(".graph-area.expanded")?.classList.remove("expanded");
  }
});

// The side panel of a drawing (the details): closed whenever a screen opens; a click on an item of the
// drawing, or the bar's button, opens it, and it stays open while the screen is shown (a filter changed
// keeps it); leaving the screen closes it. ⇄ moves it to the other side, kept in the browser per drawing.
const panelKey = (area, what) => drawingKey(area, `details-${what}`);
const detailsOpen = new Set();  // the drawings (their view) whose details are open on this screen
const viewOf = (area) => area.querySelector(".graph-canvas")?.dataset.view;
function placePanels() {
  for (const stage of document.querySelectorAll(".graph-stage:has(.graph-side-panel)")) {
    const area = stage.closest(".graph-area");
    const open = detailsOpen.has(viewOf(area));
    stage.classList.toggle("panel-closed", !open);
    stage.classList.toggle("panel-left", load(localStorage, panelKey(area, "side"), "right") === "left");
    area.querySelector(".graph-panel-toggle")?.setAttribute("aria-expanded", String(open));
  }
}
let shownScreen = location.pathname;  // the screen whose open panels detailsOpen holds
document.addEventListener("DOMContentLoaded", placePanels);
function screenChanged() {  // another screen (its address changed): every panel closes
  if (location.pathname === shownScreen) return;
  shownScreen = location.pathname;
  detailsOpen.clear();
}
for (const name of ["htmx:afterSettle", "htmx:pushedIntoHistory"]) {  // the address may change after the settle
  document.addEventListener(name, () => {
    screenChanged();
    placePanels();
  });
}
window.addEventListener("popstate", () => {
  shownScreen = location.pathname;
  detailsOpen.clear();
});
document.addEventListener("click", (event) => {
  const area = event.target.closest(".graph-area");
  if (!area) return;
  const side = panelKey(area, "side");
  if (event.target.closest(".graph-panel-toggle")) {
    if (detailsOpen.has(viewOf(area))) detailsOpen.delete(viewOf(area));
    else detailsOpen.add(viewOf(area));
  } else if (event.target.closest(".graph-panel-close")) detailsOpen.delete(viewOf(area));
  else if (event.target.closest(".graph-panel-side")) save(localStorage, side, load(localStorage, side, "right") === "left" ? "right" : "left");
  else return;
  placePanels();
});
function openSidePanel(area) {  // something clicked in the drawing: its details show (graph.js)
  if (!area || detailsOpen.has(viewOf(area))) return;
  detailsOpen.add(viewOf(area));
  placePanels();
}

// Guidelines and Memory: the bar between the tree and the note sets how much of the width the tree
// takes (25% to 75%, half at first), remembered in the browser.
const SPLIT_KEY = "doctracker-planner-split";

function applyNotesSplit() {
  const layout = document.querySelector(".notes-layout");
  const share = load(localStorage, SPLIT_KEY, null);
  if (layout && share) layout.style.setProperty("--split", `${share}%`);
}
document.addEventListener("DOMContentLoaded", applyNotesSplit);
document.addEventListener("htmx:afterSettle", applyNotesSplit);

document.addEventListener("pointerdown", (event) => {
  const splitter = event.target.closest(".notes-splitter");
  if (!splitter) return;
  event.preventDefault();
  const layout = splitter.closest(".notes-layout");
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

// Grammars that could not be fetched: the modal opens once for each list of them (its data-key), so a
// page reloading itself does not open it again; Close remembers the list, Try again does not.
const GRAMMARS_KEY = "doctracker-grammars-closed";
function showMissingGrammars(always = false) {
  const dialog = document.getElementById("grammars-dialog");
  if (!dialog || dialog.open || (!always && load(localStorage, GRAMMARS_KEY, "") === dialog.dataset.key)) return;
  dialog.addEventListener("close", () => {
    if (dialog.returnValue === "close") save(localStorage, GRAMMARS_KEY, dialog.dataset.key);
  }, { once: true });
  dialog.showModal();
}
document.addEventListener("DOMContentLoaded", () => showMissingGrammars());
document.addEventListener("htmx:afterSettle", () => showMissingGrammars());
// The warning in the topbar opens it again, even after Close.
document.addEventListener("click", (event) => {
  if (event.target.closest(".grammars-warning")) showMissingGrammars(true);
});

// Search options on a narrow screen: the filter button opens the modes and the language filter as a
// menu; picking a mode or clicking elsewhere closes it.
document.addEventListener("click", (event) => {
  const options = document.getElementById("search-filters");
  if (!options) return;
  const toggle = event.target.closest(".search-options-toggle");
  const open = toggle ? !options.classList.contains("open") : options.contains(event.target) && !event.target.closest(".search-modes button");
  options.classList.toggle("open", open);
  options.querySelector(".search-options-toggle").setAttribute("aria-expanded", String(open));
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

// A commit named on a page (e.g. the earlier names of an entity) shows its message on hover, in the same
// tooltip as the git page; it stays open while the mouse is on it, so a long message can be read.
const commitTip = document.createElement("div");
commitTip.className = "graph-tooltip commit-tooltip";
commitTip.hidden = true;
document.body.append(commitTip);
let commitTipHiding = 0;
const hideCommitTip = () => { commitTipHiding = setTimeout(() => { commitTip.hidden = true; }, 250); };
document.addEventListener("mouseover", (event) => {
  const chip = event.target.closest(".commit-chip");
  if (!chip) return;
  clearTimeout(commitTipHiding);
  const text = (value) => { const span = document.createElement("span"); span.textContent = value; return span.innerHTML; };
  const body = chip.nextElementSibling?.matches("template.commit-chip-body") ? chip.nextElementSibling.innerHTML.trim() : "";
  commitTip.innerHTML = `
    <span class="graph-tooltip-role">${text(chip.textContent)}</span>
    <strong>${text(chip.dataset.subject || "Commit no longer in git")}</strong>
    ${chip.dataset.author ? `<span class="graph-tooltip-text">${text(chip.dataset.author)} · ${text(chip.dataset.date)}</span>` : ""}
    ${body ? `<div class="graph-tooltip-body">${body}</div>` : ""}`;
  const box = chip.getBoundingClientRect();
  commitTip.style.left = `${box.left}px`;
  commitTip.style.top = `${box.bottom + 4}px`;
  commitTip.scrollTop = 0;
  commitTip.hidden = false;
});
document.addEventListener("mouseout", (event) => {
  if (event.target.closest(".commit-chip")) hideCommitTip();
});
commitTip.addEventListener("mouseenter", () => clearTimeout(commitTipHiding));
commitTip.addEventListener("mouseleave", hideCommitTip);


// The explanation of a ? opens beside it, inside the modal holding the ? (within its sides), or inside
// the window elsewhere; under it, or above when there is no room below. Being fixed to the screen, it
// never scrolls or widens the modal or panel holding the ?.
function placeHelp(event) {
  const hover = event.target.closest?.(".help-hover");
  const box = hover?.querySelector(".help-box");
  if (!box) return;
  const gap = 8, area = hover.closest("dialog")?.getBoundingClientRect()
    ?? { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
  box.style.maxWidth = `${area.right - area.left - 2 * gap}px`;
  box.style.visibility = "hidden";
  box.style.display = "block";
  const icon = hover.getBoundingClientRect(), width = box.offsetWidth, height = box.offsetHeight;
  const left = Math.max(area.left + gap, Math.min(icon.left - gap, area.right - width - gap));
  const below = icon.bottom + gap + height <= Math.min(area.bottom, window.innerHeight) - gap;
  box.style.left = `${left}px`;
  box.style.top = `${below ? icon.bottom + gap : Math.max(gap, icon.top - gap - height)}px`;
  box.style.display = "";
  box.style.visibility = "";
}
document.addEventListener("mouseover", placeHelp);
document.addEventListener("focusin", placeHelp);

// The filter boxes of a list's columns and of Browse's path (DATABASE › Navigate Database) work as
// menus: one open at a time (opening one closes the others); it opens right under its icon, inside the
// window (fixed, so the list's scrolling does not cut it), follows it when the page scrolls, and a
// column's fetches its values again (their counts follow the other filters). Its search box narrows the
// values shown. Ticks, and Clear (untick all), wait for Apply, which applies them and closes the box; a
// box closed otherwise (a click outside it, Escape) puts its ticks back as they were.
const filterTicks = new WeakMap();  // the values ticked in each box as it opened
function applyFilterBox(box) {
  if (!box) return;
  filterTicks.delete(box);  // what it holds now is what applies
  if (box.matches(".objects-crumb")) {  // a part of the path: the parts below it were chosen under it
    const parts = [...box.closest(".objects-path").querySelectorAll(".objects-crumb")];
    for (const below of parts.slice(parts.indexOf(box) + 1)) below.querySelectorAll("input[type=checkbox]").forEach((input) => { input.checked = false; });
    box.open = false;
    htmx.trigger(box.closest("form"), "path-changed");
  } else {
    box.open = false;
    htmx.trigger(box.closest("thead"), "filters-changed");
  }
}
function placeFilterBox(box) {
  const panel = box.querySelector(".objects-filter-box");
  if (!panel) return;
  const icon = box.querySelector("summary").getBoundingClientRect();
  const width = Math.min(panel.offsetWidth || 288, window.innerWidth - 16);
  panel.style.left = `${Math.max(8, Math.min(icon.left, window.innerWidth - width - 8))}px`;
  panel.style.top = `${icon.bottom + 4}px`;
  panel.style.maxHeight = `${Math.max(160, window.innerHeight - icon.bottom - 12)}px`;
}
document.addEventListener("toggle", (event) => {
  const box = event.target;
  if (box.matches?.(".objects-column-filter") && !box.open && filterTicks.has(box)) {  // closed without Apply
    const ticked = filterTicks.get(box);  // by value: its list may have been fetched again since
    box.querySelectorAll("input[type=checkbox]").forEach((input) => { input.checked = ticked.has(input.value); });
    filterTicks.delete(box);
  }
  if (!box.matches?.(".objects-column-filter") || !box.open) return;
  for (const other of document.querySelectorAll(".objects-column-filter[open]")) if (other !== box) other.open = false;
  filterTicks.set(box, new Set([...box.querySelectorAll("input[type=checkbox]:checked")].map((input) => input.value)));
  placeFilterBox(box);
  box.querySelector(".objects-values-find")?.focus();
  box.dataset.refreshing = "1";
  htmx.trigger(box.querySelector(".objects-filter-box"), "refresh-values");
}, true);  // "toggle" does not bubble: listen while it goes down
document.addEventListener("htmx:afterSwap", () => {  // its values fetched again: in place, its search focused
  const box = document.querySelector(".objects-column-filter[open]");
  if (!box) return;
  placeFilterBox(box);
  if (box.dataset.refreshing) {
    delete box.dataset.refreshing;
    box.querySelector(".objects-values-find")?.focus();
  }
});
document.addEventListener("click", (event) => {
  for (const box of document.querySelectorAll(".objects-column-filter[open]")) if (!box.contains(event.target)) box.open = false;
  const clear = event.target.closest(".objects-values-clear");
  if (clear) for (const input of clear.closest(".objects-filter-box").querySelectorAll("input[type=checkbox]")) input.checked = false;
  const apply = event.target.closest(".objects-values-apply");
  if (apply) applyFilterBox(apply.closest(".objects-column-filter"));
});
document.addEventListener("input", (event) => {  // the box's search: only narrows what it shows
  if (!event.target.matches(".objects-values-find")) return;
  event.stopPropagation();
  const text = event.target.value.trim().toLowerCase();
  for (const item of event.target.closest(".objects-filter-box").querySelectorAll(".objects-values li")) {
    item.hidden = Boolean(text) && !item.textContent.toLowerCase().includes(text);
  }
}, true);
document.addEventListener("change", (event) => {  // a tick, or the box's search: nothing applies before Apply
  if (event.target.closest?.(".objects-filter-box")) event.stopPropagation();
}, true);
document.addEventListener("scroll", () => {
  for (const box of document.querySelectorAll(".objects-column-filter[open]")) placeFilterBox(box);
}, true);
window.addEventListener("resize", () => document.querySelectorAll(".objects-column-filter[open]").forEach(placeFilterBox));
document.addEventListener("keydown", (event) => {
  const box = event.target.closest?.(".objects-column-filter[open]");
  if (!box || event.key !== "Escape") return;
  event.preventDefault();
  box.open = false;
  box.querySelector("summary").focus();
});

// Its columns' widths: the right edge of a title, dragged, makes the column wider or narrower (the list
// grows sideways and scrolls); the widths are kept per level, in this browser.
const WIDTHS_KEY = "doctracker-objects-widths";
function applyWidths(table) {
  const widths = load(localStorage, WIDTHS_KEY, {})[table.dataset.level];
  if (!widths) return;
  const cols = [...table.querySelectorAll("col")];
  cols.forEach((col, i) => { if (widths[i]) col.style.width = `${widths[i]}px`; });
  table.style.width = `${cols.reduce((sum, col) => sum + (parseFloat(col.style.width) || 0), 0)}px`;
}
document.addEventListener("htmx:afterSettle", () => document.querySelectorAll(".objects-table").forEach(applyWidths));
document.addEventListener("DOMContentLoaded", () => document.querySelectorAll(".objects-table").forEach(applyWidths));
document.addEventListener("pointerdown", (event) => {
  const handle = event.target.closest(".objects-resize");
  if (!handle) return;
  event.preventDefault();
  const table = handle.closest("table"), heads = [...handle.closest("tr").children], index = heads.indexOf(handle.closest("th"));
  const cols = [...table.querySelectorAll("col")];
  const start = heads.map((th) => th.getBoundingClientRect().width), x = event.clientX;
  cols.forEach((col, i) => { col.style.width = `${start[i]}px`; });  // every width fixed in pixels from now on
  const move = (moved) => {
    cols[index].style.width = `${Math.max(48, start[index] + moved.clientX - x)}px`;
    table.style.width = `${cols.reduce((sum, col) => sum + parseFloat(col.style.width), 0)}px`;
  };
  const stop = () => {
    document.removeEventListener("pointermove", move);
    document.removeEventListener("pointerup", stop);
    const all = load(localStorage, WIDTHS_KEY, {});
    all[table.dataset.level] = cols.map((col) => Math.round(parseFloat(col.style.width)));
    try { localStorage.setItem(WIDTHS_KEY, JSON.stringify(all)); } catch {}
  };
  document.addEventListener("pointermove", move);
  document.addEventListener("pointerup", stop);
});

// An object's page of DATABASE (in the consultation modal too): Universe, in its header or the modal's
// footer, opens the page's own Universe section and goes to it; the drawing is made when that section
// first opens (its address set then), so a page that never shows it never draws it.
document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-open-universe]")) return;
  const page = document.getElementById("page-dialog")?.open ? document.getElementById("page-dialog-body") : document.getElementById("content");
  const section = page?.querySelector('[data-section="universe"]');
  if (!section) return;
  section.open = true;
  section.scrollIntoView({ behavior: "smooth", block: "start" });
});
document.addEventListener("toggle", (event) => {
  if (!event.target.matches?.('[data-section="universe"]') || !event.target.open) return;
  const canvas = event.target.querySelector('.graph-canvas[data-view="universe"]');
  if (!canvas || canvas.dataset.url) return;
  canvas.dataset.url = canvas.closest("[data-universe-source]")?.dataset.universeSource || "/graph/universe";  // a file's own, or the live databases
  initViews();
}, true);

// The refresh beside Connections in the tree: every allowed connection read again now (the server
// does it in the background; the tree follows when a reading changes). The branch does not toggle.
document.addEventListener("click", (event) => {
  const button = event.target.closest(".tree-refresh");
  if (!button) return;
  event.preventDefault();
  button.classList.add("busy");
  fetch("/database/refresh-all", { method: "POST" }).finally(() => setTimeout(() => button.classList.remove("busy"), 1500));
});
