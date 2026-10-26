// Graph view pages: calls drawn with Cytoscape.js; architecture and classes as HTML boxes and SVG
// lines placed by dagre (see drawDiagram).
// Each page has a .graph-canvas with data-view (which style and layout to use), data-url
// (the view's data, built by doctracker.graph) and data-focus (a node to select).
// Colors come from the page's CSS variables, so the graphs match the tree, the badges and the theme.

// Zoom per mouse wheel step: 1 is Cytoscape's default, higher zooms faster.
const WHEEL_SENSITIVITY = 3;

// Largest zoom when a graph is fitted to the canvas: small graphs stay at a readable size.
const MAX_FIT_ZOOM = 3;

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

// Box diagrams (CLASSES and ARCHITECTURE): HTML boxes over SVG lines, in the style of database
// diagrams (DBeaver). Each page gives its boxes, layout and lines (DIAGRAMS); drawDiagram does the
// rest: it measures the boxes, places them, draws frames around grouped boxes and the lines, and
// handles the mouse — the wheel zooms, dragging a box moves it, dragging the background pans, a
// click highlights a box and its relations, a double click opens its wiki page. dagre (MIT)
// computes the layouts.
const DIAGRAM_MARGIN = 30;
const FRAME_PAD = 14;
const FRAME_HEAD = 24;

const DIAGRAM_MARKERS = `<defs>
  <marker id="uml-diamond" viewBox="0 0 16 10" refX="1" refY="5" markerWidth="16" markerHeight="10" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
    <path d="M1 5 L8 1 L15 5 L8 9 Z" class="uml-marker-hollow"/></marker>
  <marker id="uml-dot" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse">
    <circle cx="5" cy="5" r="4" class="uml-marker-filled"/></marker>
  <marker id="uml-triangle" viewBox="0 0 14 14" refX="13" refY="7" markerWidth="14" markerHeight="14" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M1 1 L13 7 L1 13 Z" class="uml-marker-hollow"/></marker>
  <marker id="uml-arrow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="12" markerHeight="12" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M1 1 L11 6 L1 11" class="uml-marker-open"/></marker>
  <marker id="arch-arrow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M1 1 L11 6 L1 11 Z" class="arch-marker"/></marker>
  <marker id="dep-arrow" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="14" markerHeight="14" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M1 1 L11 6 L1 11 Z" class="dep-marker"/></marker>
  <marker id="arch-arrow-cycle" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto" markerUnits="userSpaceOnUse">
    <path d="M1 1 L11 6 L1 11 Z" class="arch-marker-cycle"/></marker>
</defs>`;

// --- CLASSES: a dark header with the class name, one row per attribute with an icon for its type,
// then the methods. A composition line starts at the attribute that holds the other class.

function classBox(node) {
  const rows = node.attributes.map((attribute) => `
    <div class="uml-row" data-row="${escapeHtml(attribute.name)}" title="${escapeHtml(`${attribute.name}: ${attribute.type || "?"}`)}">
      <i class="uml-type uml-type-${attribute.icon}"></i><span class="uml-name">${escapeHtml(attribute.name)}</span>
      <span class="uml-kind">${escapeHtml(attribute.type)}</span></div>`).join("");
  const methods = node.methods.map((method) => `
    <div class="uml-row uml-method ${method.kind}" title="${escapeHtml(method.signature)}">
      <i class="uml-type uml-type-method"></i><span class="uml-name">${escapeHtml(method.name)}()</span>
      <span class="uml-kind">${method.kind ? escapeHtml(method.kind) : ""}</span></div>`).join("");
  return `<div class="uml-box uml-class" data-box="${escapeHtml(node.id)}" data-page="${escapeHtml(node.id)}">
    <div class="uml-head" title="${escapeHtml(node.summary || node.id)}"><i class="uml-type uml-type-class"></i>
      <strong>${escapeHtml(node.label)}</strong>${node.stereotype ? `<span class="uml-stereotype">«${escapeHtml(node.stereotype)}»</span>` : ""}</div>
    ${rows ? `<div class="uml-section">${rows}</div>` : ""}
    ${methods ? `<div class="uml-section">${methods}</div>` : ""}
  </div>`;
}

// Composition: from the side of the attribute row to the side of the held class's header (both on
// the same side when the boxes are stacked). Inheritance: from the top of the subclass to the bottom
// of the base class. Use: between the headers' sides.
function classPath(edge, boxes) {
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
  const right = !apart || to.x + to.width / 2 > from.x + from.width / 2;  // which side the line leaves from
  const x1 = right ? from.x + from.width : from.x;
  const x2 = apart ? (right ? to.x : to.x + to.width) : to.x + to.width;
  const reach = Math.max(40, Math.abs(x2 - x1) / 2);
  const c1 = x1 + (right ? reach : -reach);
  const c2 = apart ? x2 + (right ? -reach : reach) : x2 + reach;
  return `M ${x1} ${y1} C ${c1} ${y1}, ${c2} ${y2}, ${x2} ${y2}`;
}

// Classes linked by any relation form a group laid out by dagre (bases above subclasses, owners
// above parts); the groups and the lone classes are then packed in rows, biggest first, with the
// row width chosen so the whole diagram has about the canvas's shape (aspect = width / height).
const CLASS_GAP = 50;

function classLayout(boxes, data, aspect) {
  const group = Object.fromEntries(Object.keys(boxes).map((id) => [id, id]));  // union-find
  const find = (id) => (group[id] === id ? id : (group[id] = find(group[id])));
  for (const edge of data.edges) group[find(edge.source)] = find(edge.target);
  const members = {};
  for (const id of Object.keys(boxes)) (members[find(id)] ||= []).push(id);

  const parts = Object.values(members).map((ids) => {
    const graph = new dagre.graphlib.Graph();
    graph.setGraph({ rankdir: "TB", nodesep: CLASS_GAP, ranksep: 80 });
    graph.setDefaultEdgeLabel(() => ({}));
    for (const id of ids) graph.setNode(id, { width: boxes[id].width, height: boxes[id].height });
    for (const edge of data.edges) {
      if (!ids.includes(edge.source)) continue;
      if (edge.kind === "inherits") graph.setEdge(edge.target, edge.source);
      else if (edge.kind === "has") graph.setEdge(edge.source, edge.target);
      // uses: no rank between them; being in the same group already keeps them close
    }
    dagre.layout(graph);
    return { ids, graph, width: graph.graph().width, height: graph.graph().height };
  });

  const area = parts.reduce((sum, part) => sum + (part.width + CLASS_GAP) * (part.height + CLASS_GAP), 0);
  const rowWidth = Math.max(...parts.map((part) => part.width), Math.sqrt(area * aspect));
  parts.sort((a, b) => b.height - a.height || b.width - a.width);
  let x = 0, y = 0, rowHeight = 0;
  for (const part of parts) {
    if (x > 0 && x + part.width > rowWidth) {
      x = 0;
      y += rowHeight + CLASS_GAP;
      rowHeight = 0;
    }
    for (const id of part.ids) {
      const placed = part.graph.node(id);
      boxes[id].x = x + placed.x - boxes[id].width / 2;
      boxes[id].y = y + placed.y - boxes[id].height / 2;
    }
    x += part.width + CLASS_GAP;
    rowHeight = Math.max(rowHeight, part.height);
  }
}

function classMarkers(edge) {
  return { has: 'marker-start="url(#uml-diamond)" marker-end="url(#uml-dot)"', inherits: 'marker-end="url(#uml-triangle)"',
    uses: 'marker-end="url(#uml-arrow)"' }[edge.kind] || "";
}

// --- ARCHITECTURE: packages and subpackages are frames (or boxes, at package level), modules are
// boxes inside them, each kind in its own shade of blue with the icon of the tree; an arrow goes
// from the module that imports to the module imported, importers above.

function archBox(node) {
  const role = node.role !== "module" ? `<span class="uml-stereotype">${escapeHtml(node.role)}</span>` : "";
  return `<div class="uml-box arch-box arch-${node.role}" data-box="${escapeHtml(node.id)}" data-page="${escapeHtml(node.page)}">
    <div class="uml-head" title="${escapeHtml(node.summary || node.page)}"><i class="arch-icon arch-icon-${node.role}"></i>
      <strong>${escapeHtml(node.label)}</strong>${role}</div></div>`;
}

function archFrame(node) {
  return `<div class="arch-frame arch-${node.role}${node.parent ? " inner" : ""}" data-frame="${escapeHtml(node.id)}">
    <div class="arch-frame-head" data-page="${escapeHtml(node.page)}" title="${escapeHtml(node.summary || node.page)}">
      <i class="arch-icon arch-icon-${node.role}"></i><span class="arch-frame-role">${escapeHtml(node.role)}</span>
      <strong>${escapeHtml(node.label)}</strong></div></div>`;
}

// Laid out from the inside out: each frame arranges what is directly inside it (its modules, and
// its subpackages as blocks of their own size) with dagre, importers above, an import between two
// modules counting for the blocks that contain them. Frames stay compact, unlike dagre's own
// compound layout, which adds many empty rows.
function archLayout(boxes, data, _aspect, heads = {}) {
  const parentOf = Object.fromEntries(data.nodes.map((node) => [node.id, node.parent || ""]));
  const inside = {};  // frame id ("" for the top) -> ids directly inside it
  for (const node of data.nodes) (inside[node.parent || ""] ||= []).push(node.id);
  const within = (id, frame) => {  // the item directly inside `frame` that contains `id`, if any
    while (id && parentOf[id] !== frame) id = parentOf[id];
    return id;
  };

  const arrange = (frame) => {
    const items = (inside[frame] || []).map((id) => {
      if (boxes[id]) {
        const box = boxes[id];
        return { id, width: box.width, height: box.height, place: (x, y) => { box.x = x; box.y = y; } };
      }
      const content = arrange(id);
      return { id, width: Math.max(content.width + 2 * FRAME_PAD, heads[id] || 0), height: content.height + 2 * FRAME_PAD + FRAME_HEAD,
        place: (x, y) => content.place(x + FRAME_PAD, y + FRAME_PAD + FRAME_HEAD) };
    });
    const graph = new dagre.graphlib.Graph();
    graph.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 60 });
    graph.setDefaultEdgeLabel(() => ({}));
    for (const item of items) graph.setNode(item.id, { width: item.width, height: item.height });
    for (const edge of data.edges) {
      const source = within(edge.source, frame), target = within(edge.target, frame);
      if (source && target && source !== target) graph.setEdge(source, target);
    }
    dagre.layout(graph);
    return {
      width: graph.graph().width,
      height: graph.graph().height,
      place: (x, y) => {
        for (const item of items) {
          const placed = graph.node(item.id);
          item.place(x + placed.x - item.width / 2, y + placed.y - item.height / 2);
        }
      },
    };
  };
  arrange("").place(0, 0);
}

// Where each line meets its boxes: the lines of a box are spread along its edge, ordered by where
// the other end is, so they do not all meet at one point. Sets `out` and `in` (0 to 1) on each edge.
function archPorts(edges, boxes) {
  const center = (box) => box.x + box.width / 2;
  const ends = {};
  for (const edge of edges) {
    (ends[edge.source] ||= []).push({ edge, end: "out", toward: center(boxes[edge.target]) });
    (ends[edge.target] ||= []).push({ edge, end: "in", toward: center(boxes[edge.source]) });
  }
  for (const list of Object.values(ends)) {
    list.sort((a, b) => a.toward - b.toward);
    list.forEach((item, index) => { item.edge[item.end] = (index + 1) / (list.length + 1); });
  }
}

// From the bottom of the importer to the top of the imported module (or the other way round when
// the imported one is above, in a cycle); side to side when they are on the same row.
function archPath(edge, boxes) {
  const from = boxes[edge.source];
  const to = boxes[edge.target];
  let x1 = from.x + from.width * (edge.out ?? 0.5), x2 = to.x + to.width * (edge.in ?? 0.5), y1, y2;
  if (to.y >= from.y + from.height) {
    y1 = from.y + from.height;
    y2 = to.y;
  } else if (to.y + to.height <= from.y) {
    y1 = from.y;
    y2 = to.y + to.height;
  } else {
    const right = to.x > from.x;
    x1 = right ? from.x + from.width : from.x;
    x2 = right ? to.x : to.x + to.width;
    y1 = from.y + from.height / 2;
    y2 = to.y + to.height / 2;
    const middle = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${middle} ${y1}, ${middle} ${y2}, ${x2} ${y2}`;
  }
  const middle = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${middle}, ${x2} ${middle}, ${x2} ${y2}`;
}

// --- PLANNER: the chosen plans and their features are frames, tasks are boxes, each colored by its
// state (to do, in progress, blocked, late, done) and naming it. An arrow goes from what is waited for
// to what waits; its reason shows on hover. A click on a box or frame shows it in the right panel; a
// task box has a checkbox to mark it done. An item of a plan not chosen, linked by a dependency, is a
// small gray box: a click adds its plan to the chosen ones.
const STATE_LABELS = { todo: "to do", doing: "in progress", blocked: "blocked", late: "late", done: "done" };

function plannerParams() {
  return new URLSearchParams(window.location.search);
}

function plannerAdd(query, label, title) {
  const params = plannerParams();
  return `<button type="button" class="planner-button" title="${escapeHtml(title)}" hx-target="#notes-dialog-body"
    hx-get="/notes/form?${query}&tab=planner&plans=${escapeHtml(params.get("plans") || "")}">${escapeHtml(label)}</button>`;
}

function plannerDetail(item) {
  return `/notes/form?item=${encodeURIComponent(item)}&panel=1&tab=planner&plans=${encodeURIComponent(plannerParams().get("plans") || "")}`;
}

function plannerBox(node) {
  if (node.kind === "external") {
    const plans = new Set((plannerParams().get("plans") || "").split(",").filter((part) => /^\d+$/.test(part)));
    plans.add(String(node.plan_id));
    const url = `/notes?tab=planner&plans=${[...plans].join(",")}&selected=${encodeURIComponent(node.id)}`;
    return `<a class="uml-box planner-external state-${node.state}" data-box="${escapeHtml(node.id)}" href="${url}"
        hx-get="${url}" hx-target="#content" hx-push-url="true" title="Not shown: click to show the plan “${escapeHtml(node.plan)}”">
      <span class="planner-external-plan">↗ in plan: <strong>${escapeHtml(node.plan)}</strong></span>
      <span class="planner-external-item"><i class="level-icon level-${escapeHtml(node.level || "task")}"></i>
        <strong>${escapeHtml(node.label)}</strong><span class="waits-state state-${node.state}" title="${STATE_LABELS[node.state]}"></span></span></a>`;
  }
  const facts = [
    node.due ? `<span title="Due date">⏱ ${escapeHtml(node.due)}</span>` : "",
    node.branch ? `<span title="Branch"><code>${escapeHtml(node.branch)}</code></span>` : "",
    node.criteria ? `<span title="Criteria met">☑ ${node.criteria_done}/${node.criteria}</span>` : "",
    `<span title="Evidence that it is done">✔ ${node.evidence}</span>`,
    node.annotations ? `<span title="Annotations">✎ ${node.annotations}</span>` : "",
  ].join("");
  const waits = (node.waits_for || []).map((waited) => `<div class="planner-waits state-${waited.state}" title="${escapeHtml(waited.reason)}">
    ⛓ waits for <strong>${escapeHtml(waited.title)}</strong> <span class="planner-state">${STATE_LABELS[waited.state]}</span></div>`).join("");
  // A box may stand for a feature or a whole plan that is just this task: it says so.
  const level = node.level !== "task" ? `<i class="level-icon level-${node.level}" title="${escapeHtml(node.level)}"></i>` : "";
  if (node.empty) {
    return `<div class="uml-box planner-task planner-empty state-${node.state}" data-box="${escapeHtml(node.id)}" data-open="${plannerDetail(node.open)}">
      <div class="uml-head">${level}<strong>${escapeHtml(node.label)}</strong><span class="planner-state">${STATE_LABELS[node.state]}</span></div>
      <div class="planner-facts"><span>no ${node.level === "plan" ? "features" : "tasks"} yet</span>${node.due ? `<span title="Due date">⏱ ${escapeHtml(node.due)}</span>` : ""}</div>${waits}
    </div>`;
  }
  return `<div class="uml-box planner-task state-${node.state}" data-box="${escapeHtml(node.id)}" data-open="${plannerDetail(node.open)}">
    <div class="uml-head">
      <form class="planner-check" hx-post="/notes/toggle_task" hx-target="#content" hx-trigger="change"
            hx-confirm="${node.status === "done" ? `Withdraw the approval of “${escapeHtml(node.label)}”? It goes back to in progress and the approval evidence is deleted.`
              : `Mark “${escapeHtml(node.label)}” as done? It is recorded as your approval.`}"
            data-confirm-title="${node.status === "done" ? "Withdraw approval" : "Mark task as done"}">
        <input type="hidden" name="task_id" value="${node.task_id}"><input type="hidden" name="tab" value="planner">
        <input type="hidden" name="plans" value="${escapeHtml(plannerParams().get("plans") || "")}">
        <input type="hidden" name="selected" value="${escapeHtml(node.open)}">
        <input type="checkbox" name="done" value="1" aria-label="Done"${node.status === "done" ? " checked" : ""}>
      </form>
      ${level}<strong>${escapeHtml(node.label)}</strong>
      <span class="planner-state">${STATE_LABELS[node.state]}</span>
    </div>
    <div class="planner-facts">${facts}</div>${waits}
  </div>`;
}

// The planner is a column: in each frame, what is inside is stacked, what is waited for above what
// waits (in the order of the plan otherwise). Each frame is as wide as its widest item.
const STACK_GAP = 14;

function plannerLayout(boxes, data, _aspect, heads = {}) {
  const parentOf = Object.fromEntries(data.nodes.map((node) => [node.id, node.parent || ""]));
  const inside = {};
  for (const node of data.nodes) (inside[node.parent || ""] ||= []).push(node.id);
  const within = (id, frame) => {
    while (id && parentOf[id] !== frame) id = parentOf[id];
    return id;
  };
  const arrange = (frame) => {
    const ids = inside[frame] || [];
    // Waited-for first: repeatedly take, in plan order, the first item whose waits are all placed.
    const waits = Object.fromEntries(ids.map((id) => [id, new Set()]));
    for (const edge of data.edges) {
      const before = within(edge.source, frame), after = within(edge.target, frame);
      if (before && after && before !== after) waits[after].add(before);
    }
    const order = [];
    while (order.length < ids.length) {
      const next = ids.find((id) => !order.includes(id) && [...waits[id]].every((other) => order.includes(other)))
        || ids.find((id) => !order.includes(id));  // a cycle cannot happen, but never loop forever
      order.push(next);
    }
    const items = order.map((id) => {
      if (boxes[id]) return { width: boxes[id].width, height: boxes[id].height, place: (x, y) => { boxes[id].x = x; boxes[id].y = y; } };
      const content = arrange(id);
      return { width: Math.max(content.width + 2 * FRAME_PAD, heads[id] || 0), height: content.height + 2 * FRAME_PAD + FRAME_HEAD,
        place: (x, y) => content.place(x + FRAME_PAD, y + FRAME_PAD + FRAME_HEAD) };
    });
    const width = Math.max(0, ...items.map((item) => item.width));
    const height = items.reduce((sum, item) => sum + item.height, 0) + STACK_GAP * Math.max(0, items.length - 1);
    return {
      width, height,
      place: (x, y) => {
        for (const item of items) {
          item.place(x, y);
          y += item.height + STACK_GAP;
        }
      },
    };
  };
  arrange("").place(0, 0);
}

// Each dependency gets its own lane on the right of the column, the shortest nearest, so arrows do
// not cross the boxes between their ends nor run on top of each other.
function plannerLanes(edges, ends) {
  const span = (edge) => Math.abs(ends[edge.source].y - ends[edge.target].y);
  [...edges].sort((a, b) => span(a) - span(b)).forEach((edge, index) => { edge.lane = index; });
}

// From the right side of what is waited for, out to the edge's lane, along it, and back into the
// right side of what waits.
function plannerPath(edge, ends) {
  const from = ends[edge.source];
  const to = ends[edge.target];
  const right = Math.max(...Object.values(ends).map((end) => end.x + end.width));
  const lane = right + 24 + 18 * (edge.lane || 0);
  const x1 = from.x + from.width, y1 = from.y + Math.min(from.height / 2, 14);
  const x2 = to.x + to.width, y2 = to.y + Math.min(to.height / 2, 14);
  const turn = 12 * Math.sign(y2 - y1 || 1);
  return `M ${x1} ${y1} H ${lane - 12} Q ${lane} ${y1}, ${lane} ${y1 + turn} V ${y2 - turn} Q ${lane} ${y2}, ${lane - 12} ${y2} H ${x2}`;
}

function plannerFrame(node) {
  const [kind, id] = node.id.split(":");
  const add = kind === "plan" ? plannerAdd(`kind=feature&plan_id=${id}`, "+ feature", "Add a feature to this plan")
    : plannerAdd(`kind=task&feature_id=${id}`, "+ task", "Add a task to this feature");
  return `<div class="arch-frame planner-frame planner-${kind} state-${node.state}${node.parent ? " inner" : ""}"
      data-frame="${escapeHtml(node.id)}" data-open="${plannerDetail(node.id)}">
    <div class="arch-frame-head"><i class="level-icon level-${kind}" title="${kind}"></i><strong>${escapeHtml(node.label)}</strong>
      <span class="planner-state">${STATE_LABELS[node.state]}</span>${node.due ? `<span title="Due date">⏱ ${escapeHtml(node.due)}</span>` : ""}
      ${add}</div></div>`;
}

const DIAGRAMS = {
  classes: { box: classBox, layout: classLayout, path: classPath, markers: classMarkers, empty: "No classes here." },
  architecture: { box: archBox, frame: archFrame, layout: archLayout, prepare: archPorts, path: archPath,
    markers: (edge) => (edge.directed ? `marker-end="url(#${edge.cycle ? "arch-arrow-cycle" : "arch-arrow"})"` : ""),
    empty: "No modules." },
  planner: { box: plannerBox, frame: plannerFrame, layout: plannerLayout, prepare: plannerLanes, path: plannerPath,
    dragOuterFrames: true, openTarget: "#planner-detail", edgeReasons: true, fitWidth: true,
    markers: () => 'marker-end="url(#dep-arrow)"', empty: "No plans yet: create one with New plan." },
};

// `keep` (scale and position from a previous drawing) and `data` (already fetched) are given when the
// drawing is redone in place after a change, so it does not jump nor blink.
async function drawDiagram(canvas, view, keep = null, data = null) {
  data ||= await (await fetch(canvas.dataset.url)).json();
  if (data.error || !data.nodes.length) {
    canvas.innerHTML = `<p class="empty">${escapeHtml(data.error || view.empty)}</p>`;
    return;
  }
  // Frames are added outermost first, so inner frames sit on top and get the mouse.
  const parentOf = Object.fromEntries(data.nodes.map((node) => [node.id, node.parent || ""]));
  const depth = (id) => (parentOf[id] ? 1 + depth(parentOf[id]) : 0);
  const framed = data.nodes.filter((node) => node.frame).sort((a, b) => depth(a.id) - depth(b.id));
  canvas.classList.add("uml-canvas");
  canvas.innerHTML = `<div class="uml-stage">${framed.map((node) => view.frame(node)).join("")}<svg class="uml-lines">${DIAGRAM_MARKERS}</svg>
    ${data.nodes.filter((node) => !node.frame).map(view.box).join("")}</div>`;
  const stage = canvas.querySelector(".uml-stage");
  const svg = stage.querySelector("svg");
  htmx.process(stage);  // boxes and frames may hold buttons and forms

  // Measure every box (and where its rows are), then let the page place them.
  const boxes = {};
  for (const element of stage.querySelectorAll("[data-box]")) {
    const head = element.querySelector(".uml-head");
    const rows = {};
    for (const row of element.querySelectorAll("[data-row]")) rows[row.dataset.row] = row.offsetTop + row.offsetHeight / 2;
    boxes[element.dataset.box] = { element, width: element.offsetWidth, height: element.offsetHeight, rows,
      headCenter: head ? head.offsetTop + head.offsetHeight / 2 : element.offsetHeight / 2 };  // a box may have no title bar
  }
  // A frame is at least as wide as its title.
  const heads = Object.fromEntries([...stage.querySelectorAll("[data-frame]")]
    .map((element) => [element.dataset.frame, element.firstElementChild.offsetWidth]));
  view.layout(boxes, data, canvas.clientWidth / canvas.clientHeight, heads);

  // Frames wrap what is inside them (innermost first), with room for their title on top.
  const frames = {};
  for (const element of stage.querySelectorAll("[data-frame]")) frames[element.dataset.frame] = { element };
  const frameOrder = Object.keys(frames).sort((a, b) => depth(b) - depth(a));
  const fitFrames = () => {
    for (const id of frameOrder) {
      if (!frames[id]) continue;  // left out: nothing inside
      const inside = [...Object.entries(boxes), ...Object.entries(frames)].filter(([child]) => parentOf[child] === id)
        .map(([, item]) => item).filter((item) => Number.isFinite(item.x));
      if (!inside.length) {  // nothing inside: hidden, and out of every size
        frames[id].element.hidden = true;
        delete frames[id];
        continue;
      }
      const left = Math.min(...inside.map((item) => item.x)), top = Math.min(...inside.map((item) => item.y));
      const right = Math.max(...inside.map((item) => item.x + item.width)), bottom = Math.max(...inside.map((item) => item.y + item.height));
      Object.assign(frames[id], { x: left - FRAME_PAD, y: top - FRAME_PAD - FRAME_HEAD,
        width: Math.max(right - left + 2 * FRAME_PAD, heads[id] || 0), height: bottom - top + 2 * FRAME_PAD + FRAME_HEAD });
    }
  };
  const place = () => {
    for (const item of [...Object.values(boxes), ...Object.values(frames)]) {
      item.element.style.transform = `translate(${item.x}px, ${item.y}px)`;
      if (!item.element.dataset.box) {
        item.element.style.width = `${item.width}px`;
        item.element.style.height = `${item.height}px`;
      }
    }
  };

  // Start the diagram at the margin, then size the stage around everything.
  fitFrames();
  const everything = () => [...Object.values(boxes), ...Object.values(frames)];
  const minX = Math.min(...everything().map((item) => item.x)), minY = Math.min(...everything().map((item) => item.y));
  for (const box of Object.values(boxes)) {
    box.x += DIAGRAM_MARGIN - minX;
    box.y += DIAGRAM_MARGIN - minY;
  }
  fitFrames();
  place();
  const size = {
    width: Math.max(...everything().map((item) => item.x + item.width)) + DIAGRAM_MARGIN,
    height: Math.max(...everything().map((item) => item.y + item.height)) + DIAGRAM_MARGIN,
  };
  stage.style.width = `${size.width}px`;
  stage.style.height = `${size.height}px`;
  svg.setAttribute("width", size.width);
  svg.setAttribute("height", size.height);

  // Hover text: what the line links; an undirected link also tells how many imports go each way.
  const label = (id) => data.nodes.find((node) => node.id === id)?.label || id;
  const title = (edge) => {
    if (edge.reason) return `${label(edge.target)} waits for ${label(edge.source)}: ${edge.reason}`;
    if (edge.directed !== false) return `${label(edge.source)} → ${label(edge.target)}${edge.weight > 1 ? ` (${edge.weight} imports)` : ""}`;
    const ways = Object.entries(edge.counts || {}).map(([pair, count]) => {
      const [from, to] = pair.split("->");
      return `${label(from)} → ${label(to)}: ${count}`;
    });
    return `${label(edge.source)} — ${label(edge.target)}: ${edge.weight} import${edge.weight > 1 ? "s" : ""}\n${ways.join("\n")}`;
  };
  svg.insertAdjacentHTML("beforeend", data.edges.map((edge) => `<path class="uml-line ${edge.kind}${edge.cycle ? " cycle" : ""}"
    data-source="${escapeHtml(edge.source)}" data-target="${escapeHtml(edge.target)}" ${view.markers(edge)}
    ${edge.weight > 1 ? `style="stroke-width: ${1.4 + Math.min(edge.weight, 8) * 0.5}px"` : ""}><title>${escapeHtml(title(edge))}</title></path>`).join(""));
  const lines = [...svg.querySelectorAll(".uml-line")].map((element, index) => ({ element, edge: data.edges[index] }));
  // With `edgeReasons`, hovering a line opens a box with what waits, for what and why. Each line gets
  // a wider invisible twin, so it is easy to point at.
  if (view.edgeReasons) {
    const tooltip = canvas.parentElement.querySelector(".graph-tooltip");
    for (const line of lines) {
      line.element.querySelector("title")?.remove();
      line.element.insertAdjacentHTML("beforebegin", '<path class="uml-line-hit"/>');
      line.hit = line.element.previousElementSibling;
      line.hit.addEventListener("mouseenter", (event) => {
        const waited = data.nodes.find((node) => node.id === line.edge.source);
        tooltip.innerHTML = `<span class="graph-tooltip-role dependency-role">Dependency</span>
          <span class="graph-tooltip-text"><strong>${escapeHtml(label(line.edge.target))}</strong> can only be done after
            <strong>${escapeHtml(label(line.edge.source))}</strong>${waited ? ` (${escapeHtml(STATE_LABELS[waited.state] || waited.state)})` : ""}.</span>
          ${line.edge.reason ? `<span class="graph-tooltip-text"><em>Why:</em> ${escapeHtml(line.edge.reason)}</span>` : ""}`;
        const bounds = canvas.parentElement.getBoundingClientRect();
        tooltip.style.left = `${event.clientX - bounds.left + 12}px`;
        tooltip.style.top = `${event.clientY - bounds.top + 12}px`;
        tooltip.hidden = false;
        line.element.classList.add("near");
      });
      line.hit.addEventListener("mouseleave", () => {
        tooltip.hidden = true;
        line.element.classList.remove("near");
      });
    }
  }
  const drawLines = () => {
    const ends = { ...frames, ...boxes };  // a line may start or end on a frame (a plan, a package...)
    view.prepare?.(data.edges, ends);
    for (const line of lines) {
      line.element.setAttribute("d", view.path(line.edge, ends));
      line.hit?.setAttribute("d", line.element.getAttribute("d"));
    }
  };
  drawLines();

  // Zoom with the wheel (around the pointer), pan by dragging the background, fit to the canvas.
  let scale = 1, panX = 0, panY = 0;
  const zoomLevel = canvas.closest(".graph-page, .notes-page")?.querySelector(".graph-zoom-level");
  const apply = () => {
    stage.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    if (zoomLevel) zoomLevel.textContent = `${Math.round(scale * 100)}%`;
  };
  // With `fitWidth`, only the width is fitted and the drawing starts at its top, so a tall column stays
  // readable; dragging moves through it.
  const fit = () => {
    if (view.fitWidth) {
      scale = Math.min(1, (canvas.clientWidth - 20) / (size.width + 160));
      panX = Math.max(10, (canvas.clientWidth - (size.width + 160) * scale) / 2);
      panY = 10;
    } else {
      scale = Math.min(1, (canvas.clientWidth - 20) / size.width, (canvas.clientHeight - 20) / size.height);
      panX = (canvas.clientWidth - size.width * scale) / 2;
      panY = Math.max(10, (canvas.clientHeight - size.height * scale) / 2);
    }
    apply();
  };
  fit();
  if (keep) {
    ({ scale, panX, panY } = keep);
    apply();
  }
  canvas.viewState = () => ({ scale, panX, panY });
  // When the drawing area changes size (window resized, panel moved under it), fit again.
  const areaSize = () => `${canvas.clientWidth}x${canvas.clientHeight}`;
  let lastSize = areaSize();
  new ResizeObserver(() => {
    const now = areaSize();
    if (now !== lastSize && document.body.contains(canvas)) {
      lastSize = now;
      fit();
    }
  }).observe(canvas);
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

  // Dragging a box moves it; dragging a frame (by its title, or by its body for inner frames) moves
  // everything inside it. Frames refit and lines are redrawn as it moves. Dragging the background,
  // or the body of an outermost frame, pans; with `dragOuterFrames` (several outermost frames, like
  // the plans of the planner) every frame moves by its body and only the background pans.
  const contains = (frame, id) => {
    for (let parent = parentOf[id]; parent; parent = parentOf[parent]) if (parent === frame) return true;
    return false;
  };
  let drag = null;  // what is being dragged: some boxes, or the background (moving is empty)
  canvas.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button, input, select, textarea, label, a")) return;  // a control, not a drag
    const boxElement = event.target.closest("[data-box]");
    const frameElement = !boxElement && event.target.closest("[data-frame]");
    const frame = frameElement && (view.dragOuterFrames || event.target.closest(".arch-frame-head")
      || parentOf[frameElement.dataset.frame]) ? frameElement.dataset.frame : "";
    const moving = boxElement ? [boxes[boxElement.dataset.box]]
      : frame ? Object.entries(boxes).filter(([id]) => contains(frame, id)).map(([, box]) => box) : [];
    drag = { moving, starts: moving.map((box) => ({ x: box.x, y: box.y })), clientX: event.clientX, clientY: event.clientY,
      startX: panX, startY: panY, moved: false };
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag || !(event.buttons & 1)) return;
    const dx = event.clientX - drag.clientX, dy = event.clientY - drag.clientY;
    if (!drag.moved && Math.hypot(dx, dy) > 3) {
      // Only now the pointer is captured, so the drag goes on outside the area; capturing it on press
      // would hand the click to the area instead of the box clicked.
      drag.moved = true;
      canvas.setPointerCapture(event.pointerId);
    }
    if (!drag.moved) return;
    if (drag.moving.length) {
      drag.moving.forEach((box, index) => {
        box.x = drag.starts[index].x + dx / scale;
        box.y = drag.starts[index].y + dy / scale;
      });
      fitFrames();
      place();
      drawLines();
    } else {
      panX = drag.startX + dx;
      panY = drag.startY + dy;
      apply();
    }
  });
  canvas.addEventListener("pointerup", () => { setTimeout(() => { drag = null; }); });

  // A click highlights a box, the boxes it is related to and the lines between them.
  const highlight = (id) => {
    const related = new Set([id]);
    for (const { element } of lines) {
      const near = id && (element.dataset.source === id || element.dataset.target === id);
      element.classList.toggle("near", Boolean(near));
      element.classList.toggle("faded", Boolean(id) && !near);
      if (near) related.add(element.dataset.source).add(element.dataset.target);
    }
    for (const [boxId, box] of Object.entries(boxes)) {
      box.element.classList.toggle("selected", boxId === id);
      box.element.classList.toggle("faded", Boolean(id) && !related.has(boxId));
    }
    for (const [frameId, frame] of Object.entries(frames)) frame.element.classList.toggle("selected", frameId === id);
  };
  // Show an item from outside the drawing (e.g. a name clicked in the planner's panel): highlight it
  // and bring it to the middle of the area. `data.drawn_as` maps an item to the node it is drawn in.
  canvas.showItem = (item) => {
    const id = data.drawn_as?.[item] || item;
    const target = boxes[id] || frames[id];
    if (!target) return false;
    highlight(id);
    panX = canvas.clientWidth / 2 - (target.x + target.width / 2) * scale;
    panY = canvas.clientHeight / 2 - (target.y + Math.min(target.height, canvas.clientHeight / scale) / 2) * scale;
    apply();
    return true;
  };
  canvas.addEventListener("click", (event) => {
    if (drag && drag.moved) return;  // the end of a drag, not a click
    if (event.target.closest("button, input, select, textarea, label, a")) return;
    const box = event.target.closest("[data-box]");
    highlight(box ? box.dataset.box : "");
    const open = event.target.closest("[data-open]")?.dataset.open;  // e.g. the planner's right panel
    if (open && view.openTarget) htmx.ajax("GET", open, { target: view.openTarget });
  });
  canvas.addEventListener("dblclick", (event) => {
    const page = event.target.closest("[data-page]")?.dataset.page;
    if (page) htmx.ajax("GET", `/wiki/${page}`, { target: "#content" }).then(() => history.pushState({}, "", `/wiki/${page}`));
  });

  const page = canvas.closest(".graph-page, .notes-page");
  // Listeners outside the drawing area belong to this drawing only: a new drawing removes them.
  page.diagramListeners?.abort();
  page.diagramListeners = new AbortController();
  const signal = page.diagramListeners.signal;
  page.querySelector(".graph-fit")?.addEventListener("click", fit, { signal });
  // Zoom buttons: around the middle of the drawing area.
  const zoomBy = (factor) => {
    const next = factor ? Math.min(3, Math.max(0.15, scale * factor)) : 1;
    const x = canvas.clientWidth / 2, y = canvas.clientHeight / 2;
    panX = x - (x - panX) * (next / scale);
    panY = y - (y - panY) * (next / scale);
    scale = next;
    apply();
  };
  const zoom = page.querySelector(".graph-zoom");
  if (zoom) {
    zoom.hidden = false;
    zoom.querySelector(".graph-zoom-in").addEventListener("click", () => zoomBy(1.2), { signal });
    zoom.querySelector(".graph-zoom-out").addEventListener("click", () => zoomBy(1 / 1.2), { signal });
    zoom.querySelector(".graph-zoom-reset").addEventListener("click", () => zoomBy(0), { signal });
  }
  page.querySelector(".graph-find")?.addEventListener("input", (event) => {
    const text = event.target.value.trim().toLowerCase();
    for (const [boxId, box] of Object.entries(boxes)) {
      const match = text && `${boxId} ${box.element.textContent}`.toLowerCase().includes(text);
      box.element.classList.toggle("match", Boolean(match));
      box.element.classList.toggle("faded", Boolean(text) && !match);
    }
  }, { signal });
  // The focus is highlighted; the view stays fitted and centered on the whole diagram.
  const focus = canvas.dataset.focus;
  const focused = focus && (boxes[focus] ? focus : boxes[`${focus}.__init__`] ? `${focus}.__init__` : "");
  if (focused) highlight(focused);
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
  page.querySelector(".graph-fit")?.addEventListener("click", () => {
    cy.fit(cy.elements().not(".hidden"), 30);
    cy.zoom(Math.min(cy.zoom(), MAX_FIT_ZOOM));
    cy.center(cy.elements().not(".hidden"));
  });

  return showInfo;
}

async function initViews() {
  for (const canvas of document.querySelectorAll(".graph-canvas")) {
    if (canvas.dataset.ready) continue;
    canvas.dataset.ready = "1";
    if (DIAGRAMS[canvas.dataset.view]) {
      drawDiagram(canvas, DIAGRAMS[canvas.dataset.view]);
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
    // The whole graph fits and is centered, without blowing small graphs up; the focus only gets its panel.
    cy.fit(undefined, 40);
    cy.zoom(Math.min(cy.zoom(), MAX_FIT_ZOOM));
    cy.center();
    const page = canvas.closest(".graph-page");
    const showInfo = connectTools(cy, page);
    const focus = canvas.dataset.focus && cy.getElementById(canvas.dataset.focus);
    if (focus && focus.length) showInfo(focus);
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
      <span class="graph-tooltip-text">${escapeHtml(commit.author)} · ${escapeHtml(commit.date_local)}</span>
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

// After a change made in a panel (planner, notes), the server says "diagram-changed": the drawing of the
// page is redrawn in place, with the new data fetched first and the same zoom and position, so nothing blinks.
document.addEventListener("diagram-changed", async () => {
  const canvas = [...document.querySelectorAll(".graph-canvas[data-view]")].find((each) => DIAGRAMS[each.dataset.view]);
  if (!canvas) return;
  const data = await (await fetch(canvas.dataset.url)).json();
  const keep = canvas.viewState?.();
  const fresh = canvas.cloneNode(false);  // without the old drawing's listeners
  canvas.replaceWith(fresh);
  drawDiagram(fresh, DIAGRAMS[fresh.dataset.view], keep, data);
});

// A name with data-show (in the planner's panel) shows that item in the drawing.
document.addEventListener("click", (event) => {
  const name = event.target.closest("[data-show]");
  if (!name) return;
  document.querySelector('.graph-canvas[data-view="planner"]')?.showItem?.(name.dataset.show);
});
