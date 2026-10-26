// Graph view pages (architecture, classes, calls), drawn with Cytoscape.js.
// Each page has a .graph-canvas with data-view (which style and layout to use), data-url
// (the view's data, built by doctracker.graph) and data-focus (a node to select).
// Colors come from the page's CSS variables, so the graphs match the tree, the badges and the theme.

// Zoom per mouse wheel step: 1 is Cytoscape's default, higher zooms faster.
const WHEEL_SENSITIVITY = 3;

// CSS variable of each node role.
const ROLE_COLORS = {
  package: "--accent", subpackage: "--accent", module: "--accent",
  class: "--class", function: "--function", method: "--method",
  attribute: "--attribute", "type alias": "--attribute",
};

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function wikiLink(id, label) {
  const url = `/wiki/${escapeHtml(id)}`;
  return `<a href="${url}" hx-get="${url}" hx-target="#content" hx-push-url="true">${escapeHtml(label)}</a>`;
}

// Style shared by every view: labels readable on the theme, highlight and fade classes.
function baseStyle() {
  const fg = cssVar("--fg");
  const bg = cssVar("--bg");
  return [
    { selector: "node", style: {
      "background-color": "data(color)", label: "data(label)", color: fg, "font-size": 10,
      "text-valign": "bottom", "text-margin-y": 3, "text-outline-color": bg, "text-outline-width": 2,
      "min-zoomed-font-size": 6,
    } },
    { selector: "edge", style: {
      width: 1.4, "curve-style": "bezier", opacity: 0.8, "line-color": "data(color)",
      "target-arrow-shape": "triangle", "target-arrow-color": "data(color)", "arrow-scale": 0.8,
    } },
    { selector: ".hidden", style: { display: "none" } },
    { selector: ".faded", style: { opacity: 0.12 } },
    { selector: "node.match, node:selected", style: { "border-width": 3, "border-color": fg, "z-index": 10 } },
    { selector: "edge.near", style: { width: 2.6, opacity: 1, "z-index": 9 } },
  ];
}

// Per view: how nodes and edges look, and how they are laid out.
const VIEWS = {
  architecture: {
    decorate(data) {
      for (const node of data.nodes) node.color = cssVar(ROLE_COLORS[node.role] || "--muted");
      for (const edge of data.edges) edge.color = cssVar(edge.cycle ? "--raises" : "--accent");
    },
    style: () => [
      { selector: "node", style: { shape: "round-rectangle", width: 26, height: 26 } },
      { selector: ":parent", style: {
        "background-color": "data(color)", "background-opacity": 0.06, "border-width": 1.5,
        "border-color": "data(color)", "text-valign": "top", "text-margin-y": -4, "font-weight": "bold",
        padding: 18, shape: "round-rectangle",
      } },
      { selector: "edge", style: { width: (edge) => 1.2 + Math.min(edge.data("weight") || 1, 6) * 0.4 } },
      { selector: "edge[?cycle]", style: { width: 3 } },
    ],
    layout: { name: "cose", animate: false, padding: 30, nodeRepulsion: () => 60000, idealEdgeLength: () => 110,
      gravity: 0.1, nestingFactor: 1.4, numIter: 2500, nodeDimensionsIncludeLabels: true },
  },

  classes: {
    decorate(data) {
      const line = "─".repeat(18);
      for (const node of data.nodes) {
        node.color = cssVar("--class");
        const parts = [node.label];
        parts.push(line, ...(node.attributes.length ? node.attributes : [" "]));
        parts.push(line, ...(node.methods.length ? node.methods : [" "]));
        node.uml = parts.join("\n");
      }
      const colors = { inherits: "--class", has: "--method", uses: "--muted" };
      for (const edge of data.edges) edge.color = cssVar(colors[edge.kind] || "--muted");
    },
    style: () => [
      { selector: "node", style: {
        shape: "round-rectangle", label: "data(uml)", "text-wrap": "wrap", "text-valign": "center",
        "text-halign": "center", "text-justification": "left", "font-family": "ui-monospace, monospace",
        "font-size": 9, "line-height": 1.35, width: "label", height: "label", padding: 10,
        "background-color": cssVar("--bg"), "border-width": 2, "border-color": "data(color)", "text-outline-width": 0,
      } },
      { selector: "edge[kind = 'inherits']", style: { "target-arrow-shape": "triangle", "target-arrow-fill": "hollow", "arrow-scale": 1.4 } },
      { selector: "edge[kind = 'has']", style: { "source-arrow-shape": "diamond", "source-arrow-color": "data(color)", "target-arrow-shape": "vee", "arrow-scale": 1.1 } },
      { selector: "edge[kind = 'uses']", style: { "line-style": "dashed", "target-arrow-shape": "vee" } },
    ],
    layout: { name: "cose", animate: false, padding: 40, nodeRepulsion: () => 400000, idealEdgeLength: () => 180,
      gravity: 0.05, numIter: 2500, nodeDimensionsIncludeLabels: true },
  },

  calls: {
    decorate(data) {
      const sides = { focus: "--fg", callee: "--function", caller: "--note" };
      for (const node of data.nodes) {
        node.color = cssVar(ROLE_COLORS[node.role] || "--muted");
        node.ring = cssVar(sides[node.side] || "--muted");
        node.size = node.side === "focus" ? 40 : 24;
      }
      for (const edge of data.edges) edge.color = cssVar("--function");
    },
    style: () => [
      { selector: "node", style: { width: "data(size)", height: "data(size)", "border-width": 3, "border-color": "data(ring)" } },
      { selector: "node[side = 'focus']", style: { "font-size": 13, "font-weight": "bold" } },
    ],
    layout: { name: "concentric", padding: 40, minNodeSpacing: 40, levelWidth: () => 1,
      concentric: (node) => 10 - node.data("distance") },
  },

};

// Hover tooltip, click panel (with ×), double-click to open, highlight and fit tools.
function connectTools(cy, page) {
  const tooltip = page.querySelector(".graph-tooltip");
  const info = page.querySelector(".graph-info");

  cy.on("mouseover", "node", (event) => {
    const node = event.target;
    tooltip.innerHTML = `
      <span class="graph-tooltip-role" style="color:${node.data("color")}">${escapeHtml(node.data("symbol") || "")} ${escapeHtml(node.data("role"))}</span>
      <strong>${escapeHtml(node.data("label"))}</strong>
      <span class="graph-tooltip-text${node.data("summary") ? "" : " empty"}">${escapeHtml(node.data("summary") || "No description.")}</span>`;
    const position = node.renderedPosition();
    tooltip.style.left = `${position.x + node.renderedWidth() / 2 + 10}px`;
    tooltip.style.top = `${position.y - 10}px`;
    tooltip.hidden = false;
  });
  cy.on("mouseout", "node", () => { tooltip.hidden = true; });
  cy.on("viewport", () => { tooltip.hidden = true; });

  const closeInfo = () => {
    cy.elements().removeClass("faded near");
    info.hidden = true;
  };
  const showInfo = (node) => {
    cy.batch(() => {
      cy.elements().removeClass("near").addClass("faded");
      node.closedNeighborhood().removeClass("faded");
      node.ancestors().removeClass("faded");
      node.connectedEdges().addClass("near");
    });
    const relations = {};
    for (const edge of node.connectedEdges()) {
      const outgoing = edge.source().id() === node.id();
      const key = `${edge.data("kind")} ${outgoing ? "→" : "←"}`;
      (relations[key] = relations[key] || []).push(outgoing ? edge.target() : edge.source());
    }
    info.innerHTML = `
      <button type="button" class="graph-close" aria-label="Close" title="Close">×</button>
      <p class="graph-info-role">${escapeHtml(node.data("role"))}</p>
      <h2>${wikiLink(node.id(), node.data("label"))}</h2>
      <code class="path">${escapeHtml(node.id())}</code>
      ${node.data("summary") ? `<p>${escapeHtml(node.data("summary"))}</p>` : ""}
      ${Object.entries(relations).map(([key, targets]) => `
        <h3>${escapeHtml(key)} <span class="count">${targets.length}</span></h3>
        <ul>${targets.map((target) => `<li>${wikiLink(target.id(), target.data("label"))}</li>`).join("")}</ul>`).join("")}`;
    info.hidden = false;
    htmx.process(info);
  };
  info.addEventListener("click", (event) => {
    if (event.target.closest(".graph-close")) closeInfo();
  });
  cy.on("tap", "node", (event) => showInfo(event.target));
  cy.on("tap", (event) => {
    if (event.target === cy) closeInfo();
  });
  cy.on("dbltap", "node", (event) => htmx.ajax("GET", `/wiki/${event.target.id()}`, { target: "#content" })
    .then(() => history.pushState({}, "", `/wiki/${event.target.id()}`)));

  page.querySelector(".graph-find")?.addEventListener("input", (event) => {
    const text = event.target.value.trim().toLowerCase();
    cy.batch(() => {
      cy.elements().removeClass("match faded");
      if (!text) return;
      const matches = cy.nodes().filter((node) => node.id().toLowerCase().includes(text));
      cy.elements().not(matches).not(matches.ancestors()).addClass("faded");
      matches.addClass("match");
    });
  });
  page.querySelector(".graph-fit")?.addEventListener("click", () => cy.fit(cy.elements().not(".hidden"), 30));

  return showInfo;
}

async function initViews() {
  for (const canvas of document.querySelectorAll(".graph-canvas")) {
    if (canvas.dataset.ready) continue;
    canvas.dataset.ready = "1";
    const view = VIEWS[canvas.dataset.view];
    const data = await (await fetch(canvas.dataset.url)).json();
    if (data.error || !data.nodes.length) {
      canvas.innerHTML = `<p class="empty">${escapeHtml(data.error || "Nothing to show.")}</p>`;
      continue;
    }
    view.decorate(data);
    canvas.innerHTML = "";
    const cy = cytoscape({
      container: canvas,
      elements: [...data.nodes.map((node) => ({ data: node })), ...data.edges.map((edge) => ({ data: edge }))],
      style: [...baseStyle(), ...view.style()],
      layout: view.layout,
      minZoom: 0.05,
      maxZoom: 4,
      wheelSensitivity: WHEEL_SENSITIVITY,
      textureOnViewport: true,
      hideEdgesOnViewport: true,
      pixelRatio: 1,
    });
    const page = canvas.closest(".graph-page");
    const showInfo = connectTools(cy, page);
    const focus = canvas.dataset.focus && cy.getElementById(canvas.dataset.focus);
    if (focus && focus.length) {
      showInfo(focus);
      cy.animate({ center: { eles: focus }, zoom: Math.max(cy.zoom(), 1) }, { duration: 300 });
    }
  }
}

document.addEventListener("DOMContentLoaded", initViews);
document.addEventListener("htmx:afterSettle", initViews);

// Git page: branch graph at the top, in the style of the VS Code "Git Graph" extension:
// one bright color per branch lane, filled commit dots (the checked-out HEAD hollow), S-curved
// forks and merges, and branch/tag names as pills. Oldest commit on the left.
// Clicking a commit shows its changes below.
const LANE_COLORS = ["#0085d9", "#d9008f", "#00c40a", "#d98500", "#a300d9", "#ff3b30", "#00b8ad", "#e138e8", "#85b800", "#dc5b23"];
const COMMIT_SPACING = 70;
const LANE_SPACING = 30;
const MAX_LABEL_CHARS = 26;

// Text and kind of the pill shown on a commit: local branches first, then tags, then remotes.
function refLabel(refs) {
  if (!refs.length) return { text: "", kind: "" };
  const tags = refs.filter((ref) => ref.startsWith("tag: ")).map((ref) => ref.slice(5));
  const remotes = refs.filter((ref) => !ref.startsWith("tag: ") && ref.includes("/"));
  const locals = refs.filter((ref) => !ref.startsWith("tag: ") && !ref.includes("/"));
  const names = [...locals, ...tags.map((tag) => `◆ ${tag}`), ...remotes];
  let text = names.join("  ");
  if (text.length > MAX_LABEL_CHARS) text = `${text.slice(0, MAX_LABEL_CHARS - 1)}…`;
  const kind = locals.length ? "local" : tags.length ? "tag" : "remote";
  return { text, kind };
}

// Invisible node where a line bends or ends; `spot` has `id`, `x` and `lane`.
function waypoint(spot) {
  return { data: { id: spot.id }, position: { x: spot.x, y: spot.lane * LANE_SPACING }, classes: "waypoint" };
}

// Style of an S-curve over (dx, dy): it leaves the source and reaches the target horizontally.
// Control points (dx/2, 0) and (dx/2, dy), given as Cytoscape weights along the source→target
// line and distances along its normal (-dy, dx) / length.
function sCurve(dx, dy) {
  const length2 = dx * dx + dy * dy;
  const length = Math.sqrt(length2);
  return {
    "curve-style": "unbundled-bezier", "edge-distances": "endpoints", "source-endpoint": "0 0", "target-endpoint": "0 0",
    "control-point-weights": `${(dx * dx) / 2 / length2} ${(dx * dx / 2 + dy * dy) / length2}`,
    "control-point-distances": `${(-dx * dy) / 2 / length} ${(dx * dy) / 2 / length}`,
  };
}

// Line from an older `from` to a newer `to` (each with `id`, `x`, `lane`), drawn on `lane`.
// Between lanes it bends with an S-curve one step from the commit on the other lane (right after
// the parent of a fork, right before a merge commit), and runs straight the rest of the way.
function linkCommits(elements, from, to, lane, color) {
  const edge = (source, target, style) => elements.push({
    data: { id: `${source.id}-${target.id}`, source: source.id, target: target.id, color },
    ...(style ? { style } : {}),
  });
  const curve = (source, target) => edge(source, target, sCurve(target.x - source.x, (target.lane - source.lane) * LANE_SPACING));
  if (from.lane === to.lane) return edge(from, to);
  if (to.x - from.x <= COMMIT_SPACING) return curve(from, to);
  if (from.lane !== lane) {
    const bend = { id: `${from.id}-${to.id}-bend`, x: from.x + COMMIT_SPACING, lane: to.lane };
    elements.push(waypoint(bend));
    curve(from, bend);
    edge(bend, to);
  } else {
    const bend = { id: `${from.id}-${to.id}-bend`, x: to.x - COMMIT_SPACING, lane: from.lane };
    elements.push(waypoint(bend));
    edge(from, bend);
    curve(bend, to);
  }
}

function selectGitCommit(hash) {
  for (const item of document.querySelectorAll(".git-commit-item")) {
    item.classList.toggle("current", item.dataset.hash === hash);
  }
  htmx.ajax("GET", `/git/commit/${hash}`, { target: "#git-diff" });
}

async function initBranches() {
  const canvas = document.querySelector(".git-branches");
  if (!canvas || canvas.dataset.ready) return;
  canvas.dataset.ready = "1";
  const data = await (await fetch(canvas.dataset.url)).json();
  if (data.error || !data.commits.length) {
    canvas.innerHTML = `<p class="empty">${escapeHtml(data.error || "No commits.")}</p>`;
    return;
  }
  const commits = data.commits;
  const known = new Set(commits.map((commit) => commit.hash));
  const laneOf = Object.fromEntries(commits.map((commit) => [commit.hash, commit.lane]));
  const color = (lane) => LANE_COLORS[lane % LANE_COLORS.length];
  const last = commits.length - 1;
  const point = (hash) => ({ id: hash, x: (last - commits.findIndex((commit) => commit.hash === hash)) * COMMIT_SPACING, lane: laneOf[hash] });
  const elements = [];
  let previousLabelAbove = false;
  // Oldest to newest, so neighbouring labels can alternate above and below their commits.
  for (let index = last; index >= 0; index -= 1) {
    const commit = commits[index];
    const label = refLabel(commit.refs);
    const above = label.text ? !previousLabelAbove : true;
    if (label.text) previousLabelAbove = above;
    else previousLabelAbove = false;
    elements.push({
      data: { id: commit.hash, label: label.text, labelKind: label.kind, color: color(commit.lane), commit },
      position: { x: (last - index) * COMMIT_SPACING, y: commit.lane * LANE_SPACING },
      classes: [commit.head ? "head" : "", label.text ? (above ? "label-above" : "label-below") : ""].join(" "),
    });
    for (const parent of commit.parents) {
      if (!known.has(parent)) continue;
      // A fork or merge takes the color of the lane that is not the main line (the higher one).
      const lane = Math.max(commit.lane, laneOf[parent]);
      linkCommits(elements, point(parent), point(commit.hash), lane, color(lane));
    }
    // A branch that still exists and was not merged goes on to the present: its lane runs to the right end.
    if (commit.open && index > 0) {
      const end = { id: `${commit.hash}-end`, x: last * COMMIT_SPACING, lane: commit.lane };
      elements.push(waypoint(end));
      linkCommits(elements, point(commit.hash), end, commit.lane, color(commit.lane));
    }
  }

  canvas.innerHTML = "";
  const bg = cssVar("--bg");
  const fg = cssVar("--fg");
  const cy = cytoscape({
    container: canvas,
    elements,
    layout: { name: "preset" },
    style: [
      { selector: "node", style: {
        width: 12, height: 12, "background-color": "data(color)", "border-width": 2, "border-color": bg,
      } },
      // The checked-out commit (HEAD): a hollow circle, as in Git Graph.
      { selector: "node.head", style: { "background-color": bg, "border-color": "data(color)", "border-width": 3, width: 14, height: 14 } },
      { selector: "node:selected", style: { width: 18, height: 18, "border-color": fg, "border-width": 3 } },
      { selector: "node.waypoint", style: { width: 1, height: 1, "background-opacity": 0, "border-width": 0, events: "no" } },
      // Branch and tag names: small pills in the lane color, alternating above and below.
      { selector: "node[label != '']", style: {
        label: "data(label)", "font-size": 9, "font-weight": "bold", color: "#ffffff",
        "text-background-color": "data(color)", "text-background-opacity": 1, "text-background-shape": "round-rectangle",
        "text-background-padding": 3, "text-border-color": "data(color)", "text-border-width": 1, "text-border-opacity": 1,
        "text-halign": "center",
      } },
      { selector: "node.label-above", style: { "text-valign": "top", "text-margin-y": -7 } },
      { selector: "node.label-below", style: { "text-valign": "bottom", "text-margin-y": 7 } },
      { selector: "node[labelKind = 'remote']", style: { "text-background-opacity": 0.12, color: "data(color)" } },
      { selector: "node[labelKind = 'tag']", style: { "text-background-color": bg, color: "data(color)" } },
      { selector: "edge", style: { width: 2.5, "line-color": "data(color)", "curve-style": "straight" } },
    ],
    minZoom: 0.2,
    maxZoom: 3,
    wheelSensitivity: WHEEL_SENSITIVITY,
    autoungrabify: true,
    boxSelectionEnabled: false,
  });

  // Small histories fit the strip; long ones start at the newest commit (right end).
  if (cy.elements().boundingBox().w < canvas.clientWidth - 80) {
    cy.fit(undefined, 40);
    cy.zoom(Math.min(cy.zoom(), 1.4));
    cy.center();
  } else {
    cy.zoom(1);
    const newest = cy.getElementById(commits[0].hash);
    cy.pan({ x: canvas.clientWidth - newest.position("x") - 80, y: canvas.clientHeight / 2 - newest.position("y") });
  }

  const selected = canvas.dataset.selected && cy.getElementById(canvas.dataset.selected);
  if (selected && selected.length) selected.select();

  cy.on("tap", "node", (event) => {
    cy.$(":selected").unselect();
    event.target.select();
    selectGitCommit(event.target.id());
  });
  document.addEventListener("click", (event) => {
    const item = event.target.closest(".git-commit-item");
    if (!item || !document.body.contains(canvas)) return;
    cy.$(":selected").unselect();
    cy.getElementById(item.dataset.hash).select();
  });

  // Everything else about a commit (message, author, date, all its names) is in the tooltip.
  const tooltip = canvas.parentElement.querySelector(".graph-tooltip");
  cy.on("mouseover", "node", (event) => {
    const commit = event.target.data("commit");
    tooltip.innerHTML = `
      <span class="graph-tooltip-role" style="color:${event.target.data("color")}">${escapeHtml(commit.short)}${commit.head ? " · HEAD" : ""}${commit.refs.length ? " · " + escapeHtml(commit.refs.join(", ")) : ""}</span>
      <strong>${escapeHtml(commit.subject)}</strong>
      <span class="graph-tooltip-text">${escapeHtml(commit.author)} · ${escapeHtml(commit.date.slice(0, 16).replace("T", " "))}</span>`;
    const position = event.target.renderedPosition();
    tooltip.style.left = `${position.x + 14}px`;
    tooltip.style.top = `${position.y + 10}px`;
    tooltip.hidden = false;
  });
  cy.on("mouseout", "node", () => { tooltip.hidden = true; });
  cy.on("viewport", () => { tooltip.hidden = true; });
}

document.addEventListener("DOMContentLoaded", initBranches);
document.addEventListener("htmx:afterSettle", initBranches);
