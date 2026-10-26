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

// Git page: branch graph at the top, in the style of the VS Code "Git Graph" extension, drawn as SVG:
// one lane and one bright color per branch, filled commit dots (the checked-out HEAD hollow),
// S-curved forks and merges, and every commit's short hash in a badge of its lane color below its
// dot. Above the dot, the names of the main branch (local and remote) and tags; feature branch names
// are only in the tooltip. Oldest commit on the left. A branch's lane runs on until the merge that
// brought it in, or to the present while the branch exists. Clicking a commit shows its changes below.
const LANE_COLORS = ["#0085d9", "#d9008f", "#00c40a", "#d98500", "#a300d9", "#ff3b30", "#00b8ad", "#e138e8", "#85b800", "#dc5b23"];
const COMMIT_SPACING = 70;
const LANE_SPACING = 20;
const GRAPH_PADDING = { x: 60, top: 36, bottom: 24 };
const MAIN_BRANCHES = ["main", "master"];

// Names shown above a commit: tags, and the main branch with its remote copies (e.g. origin/main, origin/HEAD).
function mainRefs(refs) {
  return refs.filter((ref) => {
    if (ref.startsWith("tag: ")) return true;
    const name = ref.split("/").pop();
    return MAIN_BRANCHES.includes(name) || (ref.includes("/") && name === "HEAD");
  }).map((ref) => ref.replace(/^tag: /, "◆ "));
}

// SVG path from an older commit to a newer one (`x`, `y`, `lane` each), drawn on `lane`.
// On one lane it is straight. Between lanes it bends with the Git Graph curve (a cubic Bézier
// leaving and arriving horizontally) one step from the commit on the other lane — right after
// the parent of a fork, right before a merge commit — and runs straight the rest of the way.
function branchPath(from, to, lane) {
  const curve = (x1, y1, x2, y2) => `C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`;
  const start = `M ${from.x} ${from.y}`;
  if (from.lane === to.lane) return `${start} L ${to.x} ${to.y}`;
  if (to.x - from.x <= COMMIT_SPACING) return `${start} ${curve(from.x, from.y, to.x, to.y)}`;
  if (from.lane !== lane) return `${start} ${curve(from.x, from.y, from.x + COMMIT_SPACING, to.y)} L ${to.x} ${to.y}`;
  return `${start} L ${to.x - COMMIT_SPACING} ${from.y} ${curve(to.x - COMMIT_SPACING, from.y, to.x, to.y)}`;
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
  const byHash = Object.fromEntries(commits.map((commit) => [commit.hash, commit]));
  const color = (lane) => LANE_COLORS[lane % LANE_COLORS.length];
  const last = commits.length - 1;
  const spots = {};  // commit hash -> where its dot is
  commits.forEach((commit, index) => {
    spots[commit.hash] = {
      x: GRAPH_PADDING.x + (last - index) * COMMIT_SPACING, y: GRAPH_PADDING.top + commit.lane * LANE_SPACING, lane: commit.lane,
    };
  });

  const lines = [];
  const line = (from, to, lane) => lines.push(`<path d="${branchPath(from, to, lane)}" style="--lane:${color(lane)}"/>`);
  for (const commit of commits) {
    const here = spots[commit.hash];
    for (const parent of commit.parents) {
      // A fork or merge takes the color of the lane that is not the main line (the higher one).
      if (spots[parent]) line(spots[parent], here, Math.max(commit.lane, spots[parent].lane));
    }
    if (commit.next_on_branch && spots[commit.next_on_branch]) line(here, spots[commit.next_on_branch], commit.lane);
    if (commit.merged_into && spots[commit.merged_into]) line(here, spots[commit.merged_into], commit.lane);
    else if (commit.open) line(here, { ...here, x: spots[commits[0].hash].x }, commit.lane);
  }
  const dots = commits.map((commit) => {
    const { x, y } = spots[commit.hash];
    const names = mainRefs(commit.refs).join("  ");
    const label = names ? `<rect class="git-ref" rx="3"/><text class="git-ref" x="${x}" y="${y - 12}">${escapeHtml(names)}</text>` : "";
    return `<g class="git-node${commit.head ? " head" : ""}" data-hash="${commit.hash}" style="--lane:${color(commit.lane)}">
      <circle cx="${x}" cy="${y}" r="5"/><rect class="git-hash" rx="3"/><text class="git-hash" x="${x}" y="${y + 16}">${escapeHtml(commit.short)}</text>${label}</g>`;
  });
  const lanes = Math.max(...commits.map((commit) => commit.lane)) + 1;
  const width = 2 * GRAPH_PADDING.x + last * COMMIT_SPACING;
  const height = GRAPH_PADDING.top + (lanes - 1) * LANE_SPACING + GRAPH_PADDING.bottom;
  canvas.innerHTML = `<svg class="git-graph" width="${width}" height="${height}">${lines.join("")}${dots.join("")}</svg>`;

  // Badges (hash below, names above) fit their text.
  for (const text of canvas.querySelectorAll(".git-node text")) {
    const box = text.getBBox();
    const badge = text.previousElementSibling;
    badge.setAttribute("x", box.x - 3);
    badge.setAttribute("y", box.y);
    badge.setAttribute("width", box.width + 6);
    badge.setAttribute("height", box.height);
  }
  canvas.scrollLeft = canvas.scrollWidth;  // long histories start at the newest commit

  const select = (hash) => {
    for (const node of canvas.querySelectorAll(".git-node")) node.classList.toggle("selected", node.dataset.hash === hash);
  };
  select(canvas.dataset.selected);
  canvas.addEventListener("click", (event) => {
    const node = event.target.closest(".git-node");
    if (!node) return;
    select(node.dataset.hash);
    selectGitCommit(node.dataset.hash);
  });
  document.addEventListener("click", (event) => {
    const item = event.target.closest(".git-commit-item");
    if (item && document.body.contains(canvas)) select(item.dataset.hash);
  });

  // Everything else about a commit (message, author, date, all its names) is in the tooltip.
  const tooltip = canvas.parentElement.querySelector(".graph-tooltip");
  canvas.addEventListener("mouseover", (event) => {
    const node = event.target.closest(".git-node");
    if (!node) return;
    const commit = byHash[node.dataset.hash];
    const names = [commit.head ? "HEAD" : "", commit.branch ? `on ${commit.branch}` : "", ...commit.refs].filter(Boolean);
    tooltip.innerHTML = `
      <span class="graph-tooltip-role" style="color:${color(commit.lane)}">${escapeHtml([commit.short, ...names].join(" · "))}</span>
      <strong>${escapeHtml(commit.subject)}</strong>
      <span class="graph-tooltip-text">${escapeHtml(commit.author)} · ${escapeHtml(commit.date.slice(0, 16).replace("T", " "))}</span>`;
    const dot = node.querySelector("circle").getBoundingClientRect();
    const area = canvas.parentElement.getBoundingClientRect();
    tooltip.style.left = `${dot.right - area.left + 8}px`;
    tooltip.style.top = `${dot.bottom - area.top + 4}px`;
    tooltip.hidden = false;
  });
  canvas.addEventListener("mouseout", (event) => {
    if (event.target.closest(".git-node")) tooltip.hidden = true;
  });
  canvas.addEventListener("scroll", () => { tooltip.hidden = true; });
}

document.addEventListener("DOMContentLoaded", initBranches);
document.addEventListener("htmx:afterSettle", initBranches);
