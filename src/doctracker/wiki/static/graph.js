// Graph view pages: architecture and calls drawn with Cytoscape.js, classes as HTML boxes and SVG
// lines placed by dagre (see drawClassDiagram).
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

// CLASSES page: a UML class diagram drawn as HTML boxes over SVG lines, in the style of database
// diagrams (DBeaver): a dark header with the class name, one row per attribute with an icon for its
// type, then the methods. A composition line starts at the attribute that holds the other class.
// dagre (MIT) only computes where the boxes go inside each group of related classes (see umlLayout).
// Wheel zooms, dragging a box moves it, dragging the background pans, a click highlights a class
// and its relations, a double click opens its page.
const UML_MARKERS = `<defs>
  <marker id="uml-diamond" viewBox="0 0 16 10" refX="1" refY="5" markerWidth="16" markerHeight="10" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
    <path d="M1 5 L8 1 L15 5 L8 9 Z" class="uml-marker-hollow"/></marker>
  <marker id="uml-dot" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse">
    <circle cx="5" cy="5" r="4" class="uml-marker-filled"/></marker>
  <marker id="uml-triangle" viewBox="0 0 14 14" refX="13" refY="7" markerWidth="14" markerHeight="14" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M1 1 L13 7 L1 13 Z" class="uml-marker-hollow"/></marker>
  <marker id="uml-arrow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M1 1 L11 6 L1 11" class="uml-marker-open"/></marker>
</defs>`;

function umlBox(node) {
  const rows = node.attributes.map((attribute) => `
    <div class="uml-row" data-attribute="${escapeHtml(attribute.name)}" title="${escapeHtml(`${attribute.name}: ${attribute.type || "?"}`)}">
      <i class="uml-type uml-type-${attribute.icon}"></i><span class="uml-name">${escapeHtml(attribute.name)}</span>
      <span class="uml-kind">${escapeHtml(attribute.type)}</span></div>`).join("");
  const methods = node.methods.map((method) => `
    <div class="uml-row uml-method ${method.kind}" title="${escapeHtml(method.signature)}">
      <i class="uml-type uml-type-method"></i><span class="uml-name">${escapeHtml(method.name)}()</span>
      <span class="uml-kind">${method.kind ? escapeHtml(method.kind) : ""}</span></div>`).join("");
  return `<div class="uml-class" data-id="${escapeHtml(node.id)}">
    <div class="uml-head" title="${escapeHtml(node.summary || node.id)}"><i class="uml-type uml-type-class"></i>
      <strong>${escapeHtml(node.label)}</strong>${node.stereotype ? `<span class="uml-stereotype">«${escapeHtml(node.stereotype)}»</span>` : ""}</div>
    ${rows ? `<div class="uml-section">${rows}</div>` : ""}
    ${methods ? `<div class="uml-section">${methods}</div>` : ""}
  </div>`;
}

// SVG path of a relation. Composition: from the side of the attribute row to the side of the held
// class's header (both on the same side when the boxes are stacked). Inheritance: from the top of the
// subclass to the bottom of the base class. Use: between the headers' sides.
function umlPath(edge, boxes) {
  const from = boxes[edge.source];
  const to = boxes[edge.target];
  if (edge.kind === "inherits") {
    const x1 = from.x + from.width / 2, y1 = from.y, x2 = to.x + to.width / 2, y2 = to.y + to.height;
    const middle = (y1 + y2) / 2;
    return `M ${x1} ${y1} C ${x1} ${middle}, ${x2} ${middle}, ${x2} ${y2}`;
  }
  const row = edge.via && from.rows[edge.via];
  const y1 = from.y + (row ?? from.headCenter);
  const y2 = to.y + to.headCenter;
  const apart = from.x + from.width < to.x || to.x + to.width < from.x;
  let right = to.x + to.width / 2 > from.x + from.width / 2;  // which side of the source box the line leaves from
  if (!apart) right = true;
  const x1 = right ? from.x + from.width : from.x;
  const x2 = apart ? (right ? to.x : to.x + to.width) : to.x + to.width;
  const reach = Math.max(40, Math.abs(x2 - x1) / 2);
  const c1 = x1 + (right ? reach : -reach);
  const c2 = apart ? x2 + (right ? -reach : reach) : x2 + reach;
  return `M ${x1} ${y1} C ${c1} ${y1}, ${c2} ${y2}, ${x2} ${y2}`;
}

// Place the boxes (sets each box's x and y) so the diagram fills a canvas of the given aspect
// (width / height). Classes linked by any relation form a group laid out by dagre (bases above
// subclasses, owners above parts); the groups and the lone classes are then packed in rows,
// biggest first, with the row width chosen so the whole diagram has about the canvas's shape.
const UML_GAP = 50;

function umlLayout(boxes, edges, aspect) {
  const group = Object.fromEntries(Object.keys(boxes).map((id) => [id, id]));  // union-find
  const find = (id) => (group[id] === id ? id : (group[id] = find(group[id])));
  for (const edge of edges) group[find(edge.source)] = find(edge.target);
  const members = {};
  for (const id of Object.keys(boxes)) (members[find(id)] ||= []).push(id);

  const parts = Object.values(members).map((ids) => {
    const graph = new dagre.graphlib.Graph();
    graph.setGraph({ rankdir: "TB", nodesep: UML_GAP, ranksep: 80 });
    graph.setDefaultEdgeLabel(() => ({}));
    for (const id of ids) graph.setNode(id, { width: boxes[id].width, height: boxes[id].height });
    for (const edge of edges) {
      if (!ids.includes(edge.source)) continue;
      if (edge.kind === "inherits") graph.setEdge(edge.target, edge.source);
      else if (edge.kind === "has") graph.setEdge(edge.source, edge.target);
      // uses: no rank between them; being in the same group already keeps them close
    }
    dagre.layout(graph);
    return { ids, graph, width: graph.graph().width, height: graph.graph().height };
  });

  const area = parts.reduce((sum, part) => sum + (part.width + UML_GAP) * (part.height + UML_GAP), 0);
  const rowWidth = Math.max(...parts.map((part) => part.width), Math.sqrt(area * aspect));
  parts.sort((a, b) => b.height - a.height || b.width - a.width);
  let x = UML_GAP / 2, y = UML_GAP / 2, rowHeight = 0, width = 0;
  for (const part of parts) {
    if (x > UML_GAP / 2 && x + part.width > rowWidth) {
      x = UML_GAP / 2;
      y += rowHeight + UML_GAP;
      rowHeight = 0;
    }
    for (const id of part.ids) {
      const placed = part.graph.node(id);
      boxes[id].x = x + placed.x - boxes[id].width / 2;
      boxes[id].y = y + placed.y - boxes[id].height / 2;
    }
    x += part.width + UML_GAP;
    rowHeight = Math.max(rowHeight, part.height);
    width = Math.max(width, x);
  }
  return { width: width + UML_GAP / 2, height: y + rowHeight + UML_GAP };
}

async function drawClassDiagram(canvas) {
  const data = await (await fetch(canvas.dataset.url)).json();
  if (data.error || !data.nodes.length) {
    canvas.innerHTML = `<p class="empty">${escapeHtml(data.error || "No classes here.")}</p>`;
    return;
  }
  canvas.classList.add("uml-canvas");
  canvas.innerHTML = `<div class="uml-stage"><svg class="uml-lines">${UML_MARKERS}</svg>${data.nodes.map(umlBox).join("")}</div>`;
  const stage = canvas.querySelector(".uml-stage");
  const svg = stage.querySelector("svg");

  // Measure every box, then place them to fill the canvas (see umlLayout).
  const boxes = {};
  for (const element of stage.querySelectorAll(".uml-class")) {
    const head = element.querySelector(".uml-head");
    const rows = {};
    for (const row of element.querySelectorAll(".uml-row[data-attribute]")) rows[row.dataset.attribute] = row.offsetTop + row.offsetHeight / 2;
    boxes[element.dataset.id] = { element, width: element.offsetWidth, height: element.offsetHeight, rows,
      headCenter: head.offsetTop + head.offsetHeight / 2 };
  }
  const size = umlLayout(boxes, data.edges, canvas.clientWidth / canvas.clientHeight);
  for (const box of Object.values(boxes)) box.element.style.transform = `translate(${box.x}px, ${box.y}px)`;
  stage.style.width = `${size.width}px`;
  stage.style.height = `${size.height}px`;
  svg.setAttribute("width", size.width);
  svg.setAttribute("height", size.height);
  const markers = { has: 'marker-start="url(#uml-diamond)" marker-end="url(#uml-dot)"',
    inherits: 'marker-end="url(#uml-triangle)"', uses: 'marker-end="url(#uml-arrow)"' };
  svg.insertAdjacentHTML("beforeend", data.edges.map((edge) => `<path class="uml-line ${edge.kind}"
    data-source="${escapeHtml(edge.source)}" data-target="${escapeHtml(edge.target)}" d="${umlPath(edge, boxes)}" ${markers[edge.kind]}/>`).join(""));
  const lines = [...svg.querySelectorAll(".uml-line")].map((element, index) => ({ element, edge: data.edges[index] }));

  // Zoom with the wheel (around the pointer), pan by dragging the background, fit to the canvas.
  let scale = 1, panX = 0, panY = 0;
  const apply = () => { stage.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`; };
  const fit = () => {
    scale = Math.min(1, (canvas.clientWidth - 20) / size.width, (canvas.clientHeight - 20) / size.height);
    panX = (canvas.clientWidth - size.width * scale) / 2;
    panY = Math.max(10, (canvas.clientHeight - size.height * scale) / 2);
    apply();
  };
  fit();
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const bounds = canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
    const next = Math.min(3, Math.max(0.15, scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
    panX = x - (x - panX) * (next / scale);
    panY = y - (y - panY) * (next / scale);
    scale = next;
    apply();
  }, { passive: false });
  // Dragging a box moves it (and redraws its lines); dragging the background pans.
  let drag = null;  // what is being dragged: a box, or the background (box is null)
  canvas.addEventListener("pointerdown", (event) => {
    const element = event.target.closest(".uml-class");
    const box = element ? boxes[element.dataset.id] : null;
    drag = { box, clientX: event.clientX, clientY: event.clientY,
      startX: box ? box.x : panX, startY: box ? box.y : panY, moved: false };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag) return;
    const dx = event.clientX - drag.clientX, dy = event.clientY - drag.clientY;
    drag.moved ||= Math.hypot(dx, dy) > 3;
    if (!drag.moved) return;
    if (drag.box) {
      const box = drag.box;
      box.x = drag.startX + dx / scale;
      box.y = drag.startY + dy / scale;
      box.element.style.transform = `translate(${box.x}px, ${box.y}px)`;
      const id = box.element.dataset.id;
      for (const line of lines) {
        if (line.edge.source === id || line.edge.target === id) line.element.setAttribute("d", umlPath(line.edge, boxes));
      }
    } else {
      panX = drag.startX + dx;
      panY = drag.startY + dy;
      apply();
    }
  });
  canvas.addEventListener("pointerup", () => { setTimeout(() => { drag = null; }); });

  // A click highlights a class, the classes it is related to and the lines between them.
  const highlight = (id) => {
    const related = new Set([id]);
    for (const line of svg.querySelectorAll(".uml-line")) {
      const near = id && (line.dataset.source === id || line.dataset.target === id);
      line.classList.toggle("near", Boolean(near));
      line.classList.toggle("faded", Boolean(id) && !near);
      if (near) related.add(line.dataset.source).add(line.dataset.target);
    }
    for (const box of Object.values(boxes)) {
      box.element.classList.toggle("selected", box.element.dataset.id === id);
      box.element.classList.toggle("faded", Boolean(id) && !related.has(box.element.dataset.id));
    }
  };
  canvas.addEventListener("click", (event) => {
    if (drag && drag.moved) return;  // the end of a drag, not a click
    const box = event.target.closest(".uml-class");
    highlight(box ? box.dataset.id : "");
  });
  canvas.addEventListener("dblclick", (event) => {
    const box = event.target.closest(".uml-class");
    if (!box) return;
    htmx.ajax("GET", `/wiki/${box.dataset.id}`, { target: "#content" }).then(() => history.pushState({}, "", `/wiki/${box.dataset.id}`));
  });

  const page = canvas.closest(".graph-page");
  page.querySelector(".graph-fit")?.addEventListener("click", fit);
  page.querySelector(".graph-find")?.addEventListener("input", (event) => {
    const text = event.target.value.trim().toLowerCase();
    for (const box of Object.values(boxes)) {
      const match = text && box.element.dataset.id.toLowerCase().includes(text);
      box.element.classList.toggle("match", Boolean(match));
      box.element.classList.toggle("faded", Boolean(text) && !match);
    }
  });
  const focus = canvas.dataset.focus;
  if (focus && boxes[focus]) {
    highlight(focus);
    const box = boxes[focus];
    panX = canvas.clientWidth / 2 - (box.x + box.width / 2) * scale;
    panY = canvas.clientHeight / 2 - (box.y + box.height / 2) * scale;
    apply();
  }
}

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
    if (canvas.dataset.view === "classes") {
      drawClassDiagram(canvas);
      continue;
    }
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
  markGitCommit(hash);
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

  // Everything else about a commit (full message, author, date, all its names) is in the tooltip.
  // It stays open while the mouse moves into it, so a long message can be scrolled and selected.
  const tooltip = canvas.parentElement.querySelector(".graph-tooltip");
  let hiding = 0;
  const hide = () => { hiding = setTimeout(() => { tooltip.hidden = true; }, 250); };
  canvas.addEventListener("mouseover", (event) => {
    const node = event.target.closest(".git-node");
    if (!node) return;
    clearTimeout(hiding);
    const commit = byHash[node.dataset.hash];
    const names = [commit.head ? "HEAD" : "", commit.branch ? `on ${commit.branch}` : "", ...commit.refs].filter(Boolean);
    tooltip.innerHTML = `
      <span class="graph-tooltip-role" style="color:${color(commit.lane)}">${escapeHtml([commit.short, ...names].join(" · "))}</span>
      <strong>${escapeHtml(commit.subject)}</strong>
      <span class="graph-tooltip-text">${escapeHtml(commit.author)} · ${escapeHtml(commit.date.slice(0, 16).replace("T", " "))}</span>
      ${commit.body_html ? `<div class="graph-tooltip-body">${commit.body_html}</div>` : ""}`;
    const dot = node.querySelector("circle").getBoundingClientRect();
    const area = canvas.parentElement.getBoundingClientRect();
    tooltip.style.left = `${dot.right - area.left + 8}px`;
    tooltip.style.top = `${dot.bottom - area.top + 4}px`;
    tooltip.scrollTop = 0;
    tooltip.hidden = false;
  });
  canvas.addEventListener("mouseout", (event) => {
    if (event.target.closest(".git-node")) hide();
  });
  tooltip.addEventListener("mouseenter", () => clearTimeout(hiding));
  tooltip.addEventListener("mouseleave", hide);
  canvas.addEventListener("scroll", () => { tooltip.hidden = true; });
}

document.addEventListener("DOMContentLoaded", initBranches);
document.addEventListener("htmx:afterSettle", initBranches);
