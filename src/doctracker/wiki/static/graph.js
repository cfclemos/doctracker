// Diagram pages (DIAGRAMS: architecture, classes, calls; the planner): HTML boxes over SVG lines,
// drawn by drawDiagram, placed in layers by dagre (MIT) or by forces with WebCola (MIT), as the
// Layout switch of the drawing's bar says.
// Each page has a .graph-canvas with data-view (which diagram), data-url (its data, built by
// doctracker.graph) and data-focus (a node to select).
// Colors come from the page's CSS variables, so the diagrams match the tree, the badges and the theme.

function escapeHtml(text) {
  return String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
}

function wikiLink(id, label) {
  const url = `/wiki/${escapeHtml(id)}`;
  return `<a href="${url}" hx-get="${url}" hx-target="#content" hx-push-url="true">${escapeHtml(label)}</a>`;
}

// The head of the boxes floating over a drawing (the info panel, the legend): what it is if any, its
// name (HTML), its path if any, and × to close it.
function infoHead(role, title, path = "") {
  return `<header class="graph-info-head">
    <button type="button" class="graph-close" aria-label="Close" title="Close">×</button>
    ${role ? `<p class="graph-info-role">${escapeHtml(role)}</p>` : ""}
    <h2>${title}</h2>
    ${path ? `<code class="path">${escapeHtml(path)}</code>` : ""}
  </header>`;
}

// The legend of a drawing (its items in a template of the page) goes into its box once, with the info
// panel's head.
// Pressing the mouse in a drawing starts a drag of the drawing, never one of the browser's own: no text
// selection, no dragging of a link, of the text already selected or of a line (any of them takes the mouse
// away from the drawing until a click elsewhere, Shift + click, gives it back).
function holdMouse(element, signal) {
  element.addEventListener("mousedown", (event) => {
    if (event.button !== 0 || event.target.closest("button, input, select, textarea, label")) return;
    window.getSelection()?.removeAllRanges();
    event.preventDefault();
  }, { signal });
  element.addEventListener("dragstart", (event) => event.preventDefault(), { signal });
}

function fillLegend(canvas) {
  const legendBox = canvas.closest(".graph-area").querySelector(".graph-legend-box");
  const legendItems = canvas.closest(".graph-area").querySelector("template.graph-legend-items");
  if (legendBox && legendItems && !legendBox.childElementCount) {
    legendBox.innerHTML = `${infoHead("", "Legend")}<div class="graph-legend">${legendItems.innerHTML}</div>`;
  }
  return legendBox;
}

// Box diagrams (CLASSES and ARCHITECTURE): HTML boxes over SVG lines, in the style of database
// diagrams (DBeaver). Each page gives its boxes, layout and lines (DIAGRAMS); drawDiagram does the
// rest: it measures the boxes, places them, draws frames around grouped boxes and the lines, and
// handles the mouse — the wheel zooms, dragging a box moves it, dragging the background pans, a
// click highlights a box and its relations, a double click opens its wiki page. dagre (MIT)
// computes the layouts.
const DIAGRAM_MARGIN = 30;
const FRAME_PAD = 32;
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
  <marker id="er-one" viewBox="0 0 24 16" refX="24" refY="8" markerWidth="24" markerHeight="16" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
    <path d="M13 2 V14 M18 2 V14" class="er-marker"/></marker>
  <marker id="er-zero-one" viewBox="0 0 24 16" refX="24" refY="8" markerWidth="24" markerHeight="16" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
    <circle cx="9" cy="8" r="4" class="er-marker er-marker-circle"/><path d="M18 2 V14" class="er-marker"/></marker>
  <marker id="er-zero-many" viewBox="0 0 24 16" refX="24" refY="8" markerWidth="24" markerHeight="16" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
    <circle cx="6" cy="8" r="4" class="er-marker er-marker-circle"/><path d="M13 8 L24 1 M13 8 L24 15 M13 8 H24" class="er-marker"/></marker>
  ${[["one", "1"], ["zero-one", "0..1"], ["zero-many", "*"]].map(([end, text]) => `
  <marker id="er-uml-${end}-l" viewBox="-40 -16 40 20" refX="0" refY="0" markerWidth="40" markerHeight="20" orient="0" markerUnits="userSpaceOnUse">
    <text x="-5" y="-4" text-anchor="end" class="er-multiplicity">${text}</text></marker>
  <marker id="er-uml-${end}-r" viewBox="0 -16 40 20" refX="0" refY="0" markerWidth="40" markerHeight="20" orient="0" markerUnits="userSpaceOnUse">
    <text x="5" y="-4" class="er-multiplicity">${text}</text></marker>`).join("")}
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
    <div class="uml-head" title="${escapeHtml(node.summary || node.id)}">${node.role === "class" ? '<i class="uml-type uml-type-class"></i>'
      : `<i class="icon icon-${escapeHtml(node.role)}">${escapeHtml(node.symbol || "")}</i>`}
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
  if (edge.kind === "inherits" || edge.kind === "implements") {  // from the subclass up to its base
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
      if (edge.kind === "inherits" || edge.kind === "implements") graph.setEdge(edge.target, edge.source);
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
    implements: 'marker-end="url(#uml-triangle)"', uses: 'marker-end="url(#uml-arrow)"', refers: 'marker-end="url(#uml-arrow)"' }[edge.kind] || "";
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

// --- CALLS: one box per function, method or class, its border telling its side (the focus, what it
// calls, what calls it); callers on the left, the focus in the middle, what it calls on the right.

function callBox(node) {
  return `<div class="uml-box call-box call-${node.side}" data-box="${escapeHtml(node.id)}" data-page="${escapeHtml(node.id)}">
    <div class="uml-head" title="${escapeHtml(node.summary || node.id)}"><i class="icon icon-${escapeHtml(node.role)}">${escapeHtml(node.symbol || "")}</i>
      <strong>${escapeHtml(node.label)}</strong></div></div>`;
}

function callLayout(boxes, data) {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 90 });
  graph.setDefaultEdgeLabel(() => ({}));
  for (const [id, box] of Object.entries(boxes)) graph.setNode(id, { width: box.width, height: box.height });
  for (const edge of data.edges) if (boxes[edge.source] && boxes[edge.target]) graph.setEdge(edge.source, edge.target);
  dagre.layout(graph);
  for (const [id, box] of Object.entries(boxes)) {
    const placed = graph.node(id);
    box.x = placed.x - box.width / 2;
    box.y = placed.y - box.height / 2;
  }
}

const COLA_GAP = 90;  // room kept around every box and frame
const COLA_LEVEL_GAP = 160;  // between a box and what it uses, below it
const COLA_LINK = 240;  // length of a relation

function colaLayout(boxes, data, _aspect, heads = {}) {
  const parentOf = Object.fromEntries(data.nodes.map((node) => [node.id, node.parent || ""]));
  const inside = {};
  for (const node of data.nodes) if (boxes[node.id] || node.frame) (inside[node.parent || ""] ||= []).push(node.id);
  const within = (id, frame) => {
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
      if (!content) return null;
      return { id, width: Math.max(content.width + 2 * FRAME_PAD, heads[id] || 0), height: content.height + 2 * FRAME_PAD + FRAME_HEAD,
        place: (x, y) => content.place(x + FRAME_PAD, y + FRAME_PAD + FRAME_HEAD) };
    }).filter(Boolean);
    if (!items.length) return null;
    const at = Object.fromEntries(items.map((item, index) => [item.id, index]));
    const pairs = new Set(), links = [];
    for (const edge of data.edges) {
      const source = within(edge.source, frame), target = within(edge.target, frame);
      if (source in at && target in at && source !== target && !pairs.has(`${source}\u0000${target}`)) {
        pairs.add(`${source}\u0000${target}`);
        links.push({ source: at[source], target: at[target] });
      }
    }
    const columns = Math.ceil(Math.sqrt(items.length));
    const nodes = items.map((item, index) => ({ width: item.width + COLA_GAP, height: item.height + COLA_GAP,
      x: (index % columns) * 240 + Math.random(), y: Math.floor(index / columns) * 120 + Math.random() }));
    if (items.length > 1) {
      new cola.Layout().size([1200, 900]).nodes(nodes).links(links)
        .avoidOverlaps(true).flowLayout("y", COLA_LEVEL_GAP).linkDistance(COLA_LINK).handleDisconnected(true)
        .start(20, 15, 25, 0, false);
    }
    const left = Math.min(...items.map((item, index) => nodes[index].x - item.width / 2));
    const top = Math.min(...items.map((item, index) => nodes[index].y - item.height / 2));
    return {
      width: Math.max(...items.map((item, index) => nodes[index].x + item.width / 2)) - left,
      height: Math.max(...items.map((item, index) => nodes[index].y + item.height / 2)) - top,
      place: (x, y) => items.forEach((item, index) => item.place(x + nodes[index].x - item.width / 2 - left,
        y + nodes[index].y - item.height / 2 - top)),
    };
  };
  arrange("")?.place(0, 0);
}

// A line between two boxes wherever they are: side to side when one is beside the other, top to
// bottom otherwise (the calls diagram, and every diagram laid out by forces).
function linkPath(edge, boxes) {
  const from = boxes[edge.source], to = boxes[edge.target];
  if (!from || !to) return "";
  const dx = (to.x + to.width / 2) - (from.x + from.width / 2), dy = (to.y + to.height / 2) - (from.y + from.height / 2);
  if (Math.abs(dx) * 0.6 > Math.abs(dy)) {
    const x1 = dx > 0 ? from.x + from.width : from.x, x2 = dx > 0 ? to.x : to.x + to.width;
    const y1 = from.y + from.height / 2, y2 = to.y + to.height / 2, middle = (x1 + x2) / 2;
    return `M ${x1} ${y1} C ${middle} ${y1}, ${middle} ${y2}, ${x2} ${y2}`;
  }
  const y1 = dy > 0 ? from.y + from.height : from.y, y2 = dy > 0 ? to.y : to.y + to.height;
  const x1 = from.x + from.width / 2, x2 = to.x + to.width / 2, middle = (y1 + y2) / 2;
  return `M ${x1} ${y1} C ${x1} ${middle}, ${x2} ${middle}, ${x2} ${y2}`;
}

// --- Levels (architecture, classes): the diagram opens with its first level only; a click on a
// closed box opens it in place as a frame with the next level inside, a click on a frame's title
// closes it. At each level, what has no relation at all (nor anything it holds) goes to an
// UNCONNECTED group of its own. A line whose ends are inside closed boxes is drawn between those boxes, thicker
// the more lines it stands for, so no relation is lost. What is open is kept per tab.
const OPEN_KEY = "doctracker-diagram-open";

function openFrames(name) {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(`${OPEN_KEY}-${name}`) || "[]"));
  } catch {
    return new Set();
  }
}

function saveOpenFrames(name, open) {
  try { sessionStorage.setItem(`${OPEN_KEY}-${name}`, JSON.stringify([...open])); } catch {}
}

function foldLevels(data, open, hideLoose = false) {
  const nodes = Object.fromEntries(data.nodes.map((node) => [node.id, node]));
  const parentOf = Object.fromEntries(data.nodes.map((node) => [node.id, nodes[node.parent] ? node.parent : ""]));
  const ancestors = (id) => {
    const found = [];
    for (let parent = parentOf[id]; parent; parent = parentOf[parent]) found.push(parent);
    return found;
  };
  const children = {};
  for (const node of data.nodes) (children[parentOf[node.id]] ||= []).push(node.id);
  // Whether an item, or something it holds, has any relation: what has none is loose.
  const linked = new Set();
  for (const edge of data.edges) {
    for (const id of [edge.source, ...ancestors(edge.source), edge.target, ...ancestors(edge.target)]) linked.add(id);
  }
  const count = (id) => (children[id] || []).reduce((sum, child) => sum + (nodes[child].frame ? count(child) : 1), 0);
  // The groups of unconnected items, one per level that has some (and other items too).
  const groupOf = {};
  const groups = [];
  const containers = ["", ...data.nodes.filter((node) => node.frame).map((node) => node.id)];
  for (const container of containers) {
    const loose = (children[container] || []).filter((id) => !linked.has(id));
    if (hideLoose) {
      for (const item of loose) groupOf[item] = "hidden";
      continue;
    }
    if (!loose.length || loose.length === (children[container] || []).length && container) continue;
    const id = `unconnected:${container}`;
    groups.push({ id, label: "UNCONNECTED", role: "unconnected", parent: container, frame: true, page: "",
      summary: `${loose.length} item${loose.length > 1 ? "s" : ""} with no relation`, unconnected: true });
    for (const item of loose) groupOf[item] = id;
  }
  const all = { ...nodes, ...Object.fromEntries(groups.map((group) => [group.id, group])) };
  const parent = (id) => groupOf[id] || (id in parentOf ? parentOf[id] : all[id]?.parent) || "";
  const shown = (id) => {  // every frame above it is open
    if (groupOf[id] === "hidden") return false;
    for (let up = parent(id); up; up = parent(up)) if (up === "hidden" || !open.has(up)) return false;
    return true;
  };
  const total = (id) => (id.startsWith("unconnected:") ? Object.values(groupOf).filter((group) => group === id).length : count(id));
  // The items a closed level holds, to tell which languages and projects are inside it.
  const leavesOf = (id) => (id.startsWith("unconnected:") ? Object.keys(groupOf).filter((item) => groupOf[item] === id)
    : children[id] || []).flatMap((child) => (all[child]?.frame ? leavesOf(child) : [child]));
  const projectOf = (id) => {
    for (let at = id; at; at = parentOf[at]) if (nodes[at]?.role === "project") return nodes[at].label;
    return "";
  };
  const result = [];
  for (const node of Object.values(all)) {
    if (!shown(node.id)) continue;
    const item = { ...node, parent: parent(node.id) || null };
    if (node.frame && !open.has(node.id)) {
      const leaves = leavesOf(node.id);
      Object.assign(item, { frame: false, closed: true, count: total(node.id),
        languages: [...new Set(leaves.map((leaf) => nodes[leaf]?.language_label || nodes[leaf]?.language).filter(Boolean))],
        projects: [...new Set(leaves.map(projectOf).filter(Boolean))] });
    }
    result.push(item);
  }
  const visible = new Set(result.map((node) => node.id));
  const drawn = (id) => {  // the box a hidden item is drawn in: its nearest shown, closed holder
    let at = id;
    while (at && !visible.has(at)) at = parent(at);
    return at;
  };
  const lifted = {};
  for (const edge of data.edges) {
    const source = drawn(edge.source), target = drawn(edge.target);
    if (!source || !target || source === target) continue;
    const key = `${source}\u0000${target}\u0000${edge.kind}`;
    const line = (lifted[key] ||= { ...edge, id: key, source, target, weight: 0, lifted: source !== edge.source || target !== edge.target });
    line.weight += edge.weight || 1;
    line.cycle = line.cycle || edge.cycle;
  }
  return { ...data, nodes: result, edges: Object.values(lifted) };
}

// A closed level (package, file, UNCONNECTED group): a box naming it, with how many items it holds;
// a click opens it.
function closedBox(node) {
  return `<div class="uml-box arch-box arch-${escapeHtml(node.role)} closed-box" data-box="${escapeHtml(node.id)}" data-open-level="${escapeHtml(node.id)}"
      ${node.page ? `data-page="${escapeHtml(node.page)}"` : ""}>
    <div class="uml-head" title="${escapeHtml(node.summary || node.page || "")} — click to open"><i class="arch-icon arch-icon-${escapeHtml(node.role)}"></i>
      <strong>${escapeHtml(node.label)}</strong><span class="closed-count">${node.count}</span><span class="closed-open" aria-hidden="true">▸</span></div></div>`;
}

// Over MAX_BOXES boxes, only the most connected are drawn, and the bar says how to see the others.
const MAX_BOXES = 500;

function limitBoxes(data) {
  const leaves = data.nodes.filter((node) => !node.frame);
  if (leaves.length <= MAX_BOXES) return { data, hidden: 0 };
  const degree = {};
  for (const edge of data.edges) {
    degree[edge.source] = (degree[edge.source] || 0) + (edge.weight || 1);
    degree[edge.target] = (degree[edge.target] || 0) + (edge.weight || 1);
  }
  const kept = new Set(leaves.sort((a, b) => (degree[b.id] || 0) - (degree[a.id] || 0) || a.id.localeCompare(b.id))
    .slice(0, MAX_BOXES).map((node) => node.id));
  const nodes = data.nodes.filter((node) => node.frame || kept.has(node.id));
  return { data: { ...data, nodes, edges: data.edges.filter((edge) => kept.has(edge.source) && kept.has(edge.target)) },
    hidden: leaves.length - MAX_BOXES };
}

// A switch of the drawing's bar kept per browser (Hide unconnected).
function setting(name) {
  try { return localStorage.getItem(`doctracker-diagram-${name}`) === "1"; } catch { return false; }
}

function setSetting(name, on) {
  try { localStorage.setItem(`doctracker-diagram-${name}`, on ? "1" : "0"); } catch {}
}

// The layout chosen in the drawing's bar (Layers or Forces), kept per browser.
const LAYOUT_KEY = "doctracker-diagram-layout";
function chosenLayout() {
  try {
    return localStorage.getItem(LAYOUT_KEY) === "forces" ? "forces" : "layers";
  } catch {
    return "layers";
  }
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
    hx-get="/agent/form?${query}&tab=planner&plans=${escapeHtml(params.get("plans") || "")}">${escapeHtml(label)}</button>`;
}

function plannerDetail(item) {
  return `/agent/form?item=${encodeURIComponent(item)}&panel=1&tab=planner&plans=${encodeURIComponent(plannerParams().get("plans") || "")}`;
}

// The reference agents use for an item (plan:3, task:12): a box standing for several levels shows each.
function plannerRef(node) {
  const refs = [node.id, node.open].filter((ref, index, all) => ref && all.indexOf(ref) === index);
  return `<code class="planner-ref" title="Reference used by the agents">${refs.map(escapeHtml).join(" · ")}</code>`;
}
function plannerBox(node) {
  if (node.kind === "external") {
    const plans = new Set((plannerParams().get("plans") || "").split(",").filter((part) => /^\d+$/.test(part)));
    plans.add(String(node.plan_id));
    const url = `/agent/planner?plans=${[...plans].join(",")}&selected=${encodeURIComponent(node.id)}`;
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
      <div class="planner-facts">${plannerRef(node)}<span>no ${node.level === "plan" ? "features" : "tasks"} yet</span>${node.due ? `<span title="Due date">⏱ ${escapeHtml(node.due)}</span>` : ""}</div>${waits}
    </div>`;
  }
  return `<div class="uml-box planner-task state-${node.state}" data-box="${escapeHtml(node.id)}" data-open="${plannerDetail(node.open)}">
    <div class="uml-head">
      <form class="planner-check" hx-post="/agent/toggle_task" hx-target="#content" hx-trigger="change"
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
    <div class="planner-facts">${plannerRef(node)}${facts}</div>${waits}
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
      ${plannerRef(node)}<span class="planner-state">${STATE_LABELS[node.state]}</span>${node.due ? `<span title="Due date">⏱ ${escapeHtml(node.due)}</span>` : ""}
      ${add}</div></div>`;
}

// --- ER (DATABASE › Diagram): each table and view a box with one row per column (its name, its type as
// the database keeps it, its marks with the Universe's symbols), inside the levels of the DATABASES tree.
// A key's line goes from the column's row to the row of the column it refers to, its ends telling how
// many rows each side may have: crow's foot symbols or UML multiplicities, as chosen on the bar. Which
// columns show is chosen by kind in the filters; both choices are kept for the browser.
const ER_COLUMNS_KEY = "doctracker-er-columns";
const ER_NOTATION_KEY = "doctracker-er-notation";
const ER_KINDS = ["pk", "fk", "unique", "index", "generated", "other"];

function erColumnKinds() {
  try { return new Set(JSON.parse(localStorage.getItem(ER_COLUMNS_KEY)) || ER_KINDS); } catch { return new Set(ER_KINDS); }
}

function erNotation() {
  try { return localStorage.getItem(ER_NOTATION_KEY) === "uml" ? "uml" : "crow"; } catch { return "crow"; }
}

// A column shows when it is of any kind chosen; "other" stands for the columns of none.
function erShown(column, kinds) {
  const own = ER_KINDS.filter((kind) => kind !== "other" && (column.marks || []).includes(kind));
  return (own.length ? own : ["other"]).some((kind) => kinds.has(kind));
}

function erMarks(column) {
  return universeMarks(column.marks).map((mark) => `<svg class="er-mark er-mark-${mark}" viewBox="0 0 24 24" aria-label="${UNIVERSE_SYMBOLS[mark][1]}">
    <title>${UNIVERSE_SYMBOLS[mark][1]}</title>${UNIVERSE_SYMBOLS[mark][0].replace(/#000/g, "currentColor")}</svg>`).join("");
}

function erBox(node) {
  const kinds = erColumnKinds();
  const shown = node.columns.filter((column) => erShown(column, kinds));
  const rows = shown.map((column) => `
    <div class="uml-row er-row" data-row="${escapeHtml(column.name)}" data-column="${escapeHtml(column.name)}" data-page="${escapeHtml(column.path)}"
         title="${escapeHtml(`${column.name}: ${column.type || "?"}${column.comment ? ` — ${column.comment}` : ""}`)}">
      <span class="er-marks">${erMarks(column)}</span><span class="uml-name">${escapeHtml(column.name)}</span>
      <span class="uml-kind">${escapeHtml(column.type)}</span></div>`).join("");
  const left = node.columns.length - shown.length;
  const kind = node.role === "table" ? "" : `<span class="uml-stereotype">${escapeHtml(node.role.replace("-", " "))}</span>`;
  return `<div class="uml-box er-box er-${escapeHtml(node.role)}${node.suggested ? " er-suggested" : ""}" data-box="${escapeHtml(node.id)}" data-page="${escapeHtml(node.page)}">
    <div class="uml-head" title="${escapeHtml(node.summary || node.id)}"><i class="arch-icon arch-icon-${escapeHtml(node.role)}"></i>
      <strong>${escapeHtml(node.label)}</strong>${kind}</div>
    ${rows || left ? `<div class="uml-section">${rows}${left ? `<div class="uml-row er-more">${left} more column${left > 1 ? "s" : ""}</div>` : ""}</div>` : ""}
  </div>`;
}

// Laid out as the architecture is, level by level, the table referred to above the one referring to it. A
// slice's tables stand where they were saved; those without a place, and the suggested ones, in a column
// to the right of them. What the slice could not find is said above the drawing.
function erLayout(boxes, data, aspect, heads) {
  archLayout(boxes, { ...data, edges: data.edges.map((edge) => ({ ...edge, source: edge.target, target: edge.source })) }, aspect, heads);
  if (!data.slice) return;
  const placed = data.nodes.filter((node) => boxes[node.id] && Number.isFinite(node.x) && Number.isFinite(node.y));
  for (const node of placed) Object.assign(boxes[node.id], { x: node.x, y: node.y });
  const right = Math.max(0, ...placed.map((node) => node.x + boxes[node.id].width)) + 80;
  let y = 0;
  for (const node of data.nodes.filter((item) => boxes[item.id] && !placed.includes(item))) {
    Object.assign(boxes[node.id], { x: right, y });
    y += boxes[node.id].height + 30;
  }
  const warning = Object.values(boxes)[0]?.element.closest(".graph-area")?.querySelector(".graph-warning");
  const list = (keys) => keys.join(", ");
  const told = [data.slice.missing.length ? `Not in any database read nor file: ${list(data.slice.missing)} (left out).` : "",
    data.slice.by_name.length ? `Not where the slice took ${data.slice.by_name.length > 1 ? "them" : "it"} from, found by name in ${list(data.slice.by_name_in)}: `
      + `${list(data.slice.by_name)}.` : ""].filter(Boolean);
  if (warning && told.length) {
    warning.hidden = false;
    warning.textContent = told.join(" ");
  }
}

// The tables a slice holds, or those chosen for a new one, kept for the browser tab across redraws.
const erChosen = new Map();  // slice name ("" for a new one) → Set of table paths

// From the side of the referring column's row to the side of the referred column's row (a box's title
// when the row is not shown); a table referring to itself, a loop on its right. Remembers on the edge
// which side each end meets its box, for the UML multiplicities.
function erPath(edge, boxes) {
  const from = boxes[edge.source], to = boxes[edge.target];
  if (!from || !to) return "";
  const y1 = from.y + (from.rows?.[edge.via] ?? from.headCenter), y2 = to.y + (to.rows?.[edge.to] ?? to.headCenter);
  if (edge.source === edge.target) {
    const x = from.x + from.width, reach = 50;
    edge.sides = ["right", "right"];
    return `M ${x} ${y1} C ${x + reach} ${y1}, ${x + reach} ${y2}, ${x} ${y2}`;
  }
  const apart = from.x + from.width < to.x || to.x + to.width < from.x;
  const right = !apart || to.x + to.width / 2 > from.x + from.width / 2;
  const x1 = right ? from.x + from.width : from.x;
  const x2 = apart ? (right ? to.x : to.x + to.width) : to.x + to.width;
  edge.sides = [right ? "right" : "left", apart ? (right ? "left" : "right") : "right"];
  const reach = Math.max(40, Math.abs(x2 - x1) / 2);
  const c1 = x1 + (right ? reach : -reach);
  const c2 = apart ? x2 + (right ? -reach : reach) : x2 + reach;
  return `M ${x1} ${y1} C ${c1} ${y1}, ${c2} ${y2}, ${x2} ${y2}`;
}

// The ends of a key's line, once it is drawn: crow's foot symbols (turned with the line), or the UML
// multiplicities beside the end, on the side away from the box. Other relations end in an arrow.
function erLineEnds(element, edge) {
  if (!edge.source_end || edge.lifted) {
    element.setAttribute("marker-end", "url(#uml-arrow)");
    element.removeAttribute("marker-start");
    return;
  }
  if (erNotation() === "crow") {
    element.setAttribute("marker-start", `url(#er-${edge.source_end})`);
    element.setAttribute("marker-end", `url(#er-${edge.target_end})`);
    return;
  }
  const [start, end] = edge.sides || ["right", "left"];
  element.setAttribute("marker-start", `url(#er-uml-${edge.source_end}-${start === "right" ? "r" : "l"})`);
  element.setAttribute("marker-end", `url(#er-uml-${edge.target_end}-${end === "right" ? "r" : "l"})`);
}

// The bar's Notation and the filters' Columns: kept for the browser, the drawing made again in place.
// Ctrl + click on a table adds it to the slice open (a faded suggestion joins it) or takes it away; with
// no slice open, it chooses tables for a new one (Save as slice). Save the slice keeps its tables and
// where they stand now, in its file.
function erBar(page, redraw, signal) {
  const canvas = page.querySelector('.graph-canvas[data-view="er"]');
  const data = canvas?.drawnData;
  const name = data?.slice?.name ?? "";
  if (canvas && data) {
    if (!erChosen.has(name)) erChosen.set(name, new Set(data.slice ? data.nodes.filter((node) => !node.suggested).map((node) => node.id) : []));
    const chosen = erChosen.get(name);
    const saveAs = page.querySelector(".er-save-as"), save = page.querySelector(".er-save");
    const mark = () => {
      for (const box of canvas.querySelectorAll(".er-box[data-box]")) {
        const inside = chosen.has(box.dataset.box);
        box.classList.toggle("er-suggested", Boolean(data.slice) && !inside);
        box.classList.toggle("er-chosen", !data.slice && inside);
      }
      if (saveAs) saveAs.hidden = Boolean(data.slice) || !chosen.size;
    };
    mark();
    canvas.addEventListener("click", (event) => {
      const box = event.target.closest(".er-box[data-box]");
      if (!box || !(event.ctrlKey || event.metaKey)) return;
      event.stopImmediatePropagation();
      if (chosen.has(box.dataset.box)) chosen.delete(box.dataset.box);
      else chosen.add(box.dataset.box);
      mark();
    }, { signal, capture: true });
    const tables = () => {
      const at = canvas.boxPositions();
      return [...chosen].map((path) => ({ path, x: at[path]?.x, y: at[path]?.y }));
    };
    saveAs?.addEventListener("click", () => {
      htmx.ajax("POST", "/database/slice-new", { target: "#database-dialog-body", values: { tables: JSON.stringify(tables()) } });
    }, { signal });
    save?.addEventListener("click", async () => {
      const body = new URLSearchParams({ from: "diagram", name, previous: name, tables: JSON.stringify(tables()) });
      const answer = await (await fetch("/database/slice-save", { method: "POST", body })).json();
      save.textContent = answer.ok ? "Saved" : answer.error;
      setTimeout(() => { save.textContent = "Save the slice"; }, 1800);
    }, { signal });
  }
  for (const button of page.querySelectorAll(".graph-notation")) {
    button.setAttribute("aria-checked", String(button.dataset.notation === erNotation()));
    button.addEventListener("click", () => {
      try { localStorage.setItem(ER_NOTATION_KEY, button.dataset.notation); } catch {}
      redraw();
    }, { signal });
  }
  const kinds = erColumnKinds();
  for (const box of page.querySelectorAll(".er-columns input")) {
    box.checked = kinds.has(box.value);
    box.addEventListener("change", () => {
      const chosen = [...page.querySelectorAll(".er-columns input")].filter((input) => input.checked).map((input) => input.value);
      try { localStorage.setItem(ER_COLUMNS_KEY, JSON.stringify(chosen)); } catch {}
      redraw();
    }, { signal });
  }
}

// A column clicked, in the Details panel: what it is and the keys it is an end of.
function erColumnInfo(node, name, edges, nodes) {
  const column = node.columns?.find((item) => item.name === name);
  if (!column) return "";
  const label = (id) => nodes.find((item) => item.id === id)?.label || id;
  const keys = edges.filter((edge) => edge.via && ((edge.source === node.id && edge.columns?.includes(name))
    || (edge.target === node.id && edge.target_columns?.includes(name))));
  const marks = universeMarks(column.marks).map((mark) => UNIVERSE_SYMBOLS[mark][1]);
  return `<p class="graph-info-role">column of ${escapeHtml(node.label)}</p>
    <h3 class="graph-details-name">${escapeHtml(column.name)}</h3>
    <code class="path">${escapeHtml(column.path)}</code>
    <p><code>${escapeHtml(column.type || "?")}</code> · ${escapeHtml(marks.join(", "))}</p>
    ${column.comment ? `<p>${escapeHtml(column.comment)}</p>` : ""}
    ${keys.length ? `<h4>Keys <span class="count">${keys.length}</span></h4><ul>${keys.map((edge) => `<li>${escapeHtml(edge.kind.replace("-", " "))}
      ${edge.source === node.id ? "→" : "←"} <button type="button" class="graph-details-show" data-show="${escapeHtml(edge.source === node.id ? edge.target : edge.source)}">${escapeHtml(label(edge.source === node.id ? edge.target : edge.source))}</button></li>`).join("")}</ul>` : ""}`;
}

const DIAGRAMS = {
  calls: { box: callBox, layout: callLayout, path: linkPath, markers: () => 'marker-end="url(#arch-arrow)"', layouts: true, fromFocus: true,
    info: true, empty: "Nothing calls it and it calls nothing." },
  classes: { box: classBox, frame: archFrame, layout: archLayout, path: classPath, markers: classMarkers, layouts: true,
    info: true, levels: "classes", empty: "No classes here." },
  architecture: { box: archBox, frame: archFrame, layout: archLayout, prepare: archPorts, path: archPath,
    markers: (edge) => (edge.directed ? `marker-end="url(#${edge.cycle ? "arch-arrow-cycle" : "arch-arrow"})"` : ""),
    layouts: true, info: true, levels: "architecture", empty: "No modules." },
  planner: { box: plannerBox, frame: plannerFrame, layout: plannerLayout, prepare: plannerLanes, path: plannerPath,
    dragOuterFrames: true, openTarget: "#planner-detail", edgeReasons: true, fitWidth: true,
    markers: () => 'marker-end="url(#dep-arrow)"', empty: "No plans yet: create one with New plan." },
  er: { box: erBox, frame: archFrame, layout: erLayout, path: erPath, markers: () => "", lineEnds: erLineEnds, bar: erBar,
    columnInfo: erColumnInfo, layouts: true, info: true, levels: "er", empty: "No table here." },
};
DIAGRAMS.local = { ...DIAGRAMS.calls, empty: "It has no relations with the rest of the project." };  // an entity's page

// `keep` (scale and position from a previous drawing) and `data` (already fetched) are given when the
// drawing is redone in place after a change, so it does not jump nor blink.
async function drawDiagram(canvas, view, keep = null, data = null) {
  data ||= await (await fetch(canvas.dataset.url)).json();
  if (data.error || !data.nodes.length) {
    canvas.innerHTML = `<p class="empty">${escapeHtml(data.error || view.empty)}</p>`;
    return;
  }
  const whole = data;  // drawn again from it when a level opens or closes
  // Every listener of a drawing, on the area and around it, belongs to it only: a new drawing (a level
  // opened, the layout changed, a change in the planner) removes them, so nothing is handled twice.
  const page = canvas.closest(".graph-page, .notes-page");
  page.diagramListeners?.abort();
  page.diagramListeners = new AbortController();
  const signal = page.diagramListeners.signal;
  fillLegend(canvas);
  // The legend's relation kinds filter the drawing: a kind turned off leaves out its lines and, in
  // a drawing reached from a focus (calls, local graph), what only that kind led to. With every
  // kind off, nothing is drawn. Kept per diagram and browser tab.
  const kindsKey = `doctracker-diagram-kinds-off-${canvas.dataset.view}`;
  let kindsOff = new Set();
  const kindButtons = [...page.querySelectorAll(".graph-kind")];
  // Kinds marked data-off in the legend start off, until the reader turns them on.
  kindsOff = new Set(kindButtons.filter((button) => button.dataset.off).map((button) => button.dataset.kind));
  try { kindsOff = new Set(JSON.parse(sessionStorage.getItem(kindsKey) ?? JSON.stringify([...kindsOff]))); } catch {}
  for (const button of kindButtons) {
    button.setAttribute("aria-pressed", String(!kindsOff.has(button.dataset.kind)));
    button.addEventListener("click", () => {
      if (kindsOff.has(button.dataset.kind)) kindsOff.delete(button.dataset.kind);
      else kindsOff.add(button.dataset.kind);
      try { sessionStorage.setItem(kindsKey, JSON.stringify([...kindsOff])); } catch {}
      drawDiagram(canvas, view, canvas.viewState?.(), whole);
    }, { signal });
  }
  if (kindButtons.length && kindButtons.every((button) => kindsOff.has(button.dataset.kind))) {
    canvas.innerHTML = '<p class="empty">No relation is chosen in the legend: choose one to see the drawing.</p>';
    return;
  }
  if (kindsOff.size) {
    data = { ...data, edges: data.edges.filter((edge) => !kindsOff.has(edge.kind)) };
    if (view.fromFocus && whole.focus) {
      const reached = new Set([whole.focus]);
      for (let grew = true; grew;) {
        grew = false;
        for (const edge of data.edges) {
          for (const [from, to] of [[edge.source, edge.target], [edge.target, edge.source]]) {
            if (reached.has(from) && !reached.has(to)) { reached.add(to); grew = true; }
          }
        }
      }
      data = { ...data, nodes: data.nodes.filter((node) => reached.has(node.id)),
        edges: data.edges.filter((edge) => reached.has(edge.source) && reached.has(edge.target)) };
    }
  }
  // A focus (e.g. "See in Architecture" from a page) opens, the first time, every level holding what is
  // drawn: the server sent only the focus and its neighbours, so they show at once instead of closed boxes.
  const focusId = whole.focus || canvas.dataset.focus;
  if (view.levels && focusId && !canvas.dataset.focusOpened) {
    canvas.dataset.focusOpened = "1";
    const byId = Object.fromEntries(whole.nodes.map((node) => [node.id, node]));
    if (byId[focusId] || byId[`${focusId}.__init__`]) {
      const open = openFrames(view.levels);
      for (const node of whole.nodes) {
        if (!node.frame) for (let up = node.parent; up; up = byId[up]?.parent) open.add(up);
      }
      saveOpenFrames(view.levels, open);
    }
  }
  if (view.levels && !whole.slice) data = foldLevels(data, openFrames(view.levels), setting("hide-loose"));  // a slice has no levels
  // Colour by language or project (the bar's Colour): the groups of each box — its language or project,
  // or, for a closed level, those of everything inside it. A group turned off by its chip is left out of
  // the drawing: a box whose groups are all off, a frame left with nothing, their lines.
  let colourBy = "kind";
  try { if (view.layouts) colourBy = localStorage.getItem("doctracker-diagram-colour") || "kind"; } catch {}
  const nodeOf = Object.fromEntries(data.nodes.map((node) => [node.id, node]));
  const groupKeys = (id) => {
    const node = nodeOf[id];
    if (colourBy === "language") return node?.closed ? node.languages || [] : [node?.language_label || node?.language].filter(Boolean);
    if (node?.closed && node.projects?.length) return node.projects;
    for (let at = id; at; at = nodeOf[at]?.parent) if (nodeOf[at]?.role === "project") return [nodeOf[at].label];
    return [];
  };
  const groupKeysAll = colourBy === "kind" ? [] : [...new Set(data.nodes.filter((node) => !node.frame).flatMap((node) => groupKeys(node.id)))].sort();
  const colours = Object.fromEntries(groupKeysAll.map((key, index) => [key, LANE_COLORS[index % LANE_COLORS.length]]));
  const offKey = `doctracker-diagram-off-${canvas.dataset.view}-${colourBy}`;
  let off = new Set();
  try { off = new Set(JSON.parse(sessionStorage.getItem(offKey) || "[]")); } catch {}
  if (colourBy !== "kind" && off.size) {
    const out = new Set(data.nodes.filter((node) => !node.frame && groupKeys(node.id).length
      && groupKeys(node.id).every((group) => off.has(group))).map((node) => node.id));
    data = { ...data, nodes: data.nodes.filter((node) => !out.has(node.id)),
      edges: data.edges.filter((edge) => !out.has(edge.source) && !out.has(edge.target)) };
  }
  const limited = view.layouts ? limitBoxes(data) : { data, hidden: 0 };
  data = limited.data;
  const warning = canvas.closest(".graph-area").querySelector(".graph-warning");
  if (warning) {
    warning.hidden = !limited.hidden;
    warning.textContent = limited.hidden ? `Showing the ${MAX_BOXES} most connected boxes; ${limited.hidden} more are left out. `
      + "Close some levels, or choose a language or a focus in the filters, to see them." : "";
  }
  // Frames are added outermost first, so inner frames sit on top and get the mouse.
  const parentOf = Object.fromEntries(data.nodes.map((node) => [node.id, node.parent || ""]));
  const depth = (id) => (parentOf[id] ? 1 + depth(parentOf[id]) : 0);
  const framed = data.nodes.filter((node) => node.frame).sort((a, b) => depth(a.id) - depth(b.id));
  canvas.classList.add("uml-canvas");
  canvas.innerHTML = `<div class="uml-stage">${framed.map((node) => view.frame(node)).join("")}<svg class="uml-lines">${DIAGRAM_MARKERS}</svg>
    ${data.nodes.filter((node) => !node.frame).map((node) => (node.closed ? closedBox(node) : view.box(node))).join("")}</div>`;
  const stage = canvas.querySelector(".uml-stage");
  const svg = stage.querySelector("svg");
  htmx.process(stage);  // boxes and frames may hold buttons and forms

  // The more relations a box has, the bigger its name (not the UML classes, whose rows stay readable).
  const degree = {};
  for (const edge of data.edges) {
    degree[edge.source] = (degree[edge.source] || 0) + (edge.weight || 1);
    degree[edge.target] = (degree[edge.target] || 0) + (edge.weight || 1);
  }
  const most = Math.max(1, ...Object.values(degree));
  if (view.layouts) {
    for (const element of stage.querySelectorAll(".arch-box, .call-box")) {
      const weight = Math.sqrt((degree[element.dataset.box] || 0) / most);
      element.style.fontSize = `${(1 + weight * 0.6).toFixed(2)}em`;
    }
  }
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
  // With the Forces layout (diagrams that offer it), WebCola places the boxes and the lines go straight
  // between them wherever they end up.
  const forces = view.layouts && chosenLayout() === "forces";
  if (forces) colaLayout(boxes, data, canvas.clientWidth / canvas.clientHeight, heads);
  else view.layout(boxes, data, canvas.clientWidth / canvas.clientHeight, heads);
  const path = (edge, ends) => (forces || edge.lifted || ends[edge.source]?.element?.classList.contains("closed-box")
    || ends[edge.target]?.element?.classList.contains("closed-box") ? linkPath : view.path)(edge, ends);

  // Frames wrap what is inside them (innermost first), with room for their title on top.
  const frames = {};
  for (const element of stage.querySelectorAll("[data-frame]")) frames[element.dataset.frame] = { element };
  const frameOrder = Object.keys(frames).sort((a, b) => depth(b) - depth(a));
  // What is directly inside each frame, listed once: refitting is then as fast as there are items.
  const childrenOf = {};
  for (const id of [...Object.keys(boxes), ...Object.keys(frames)]) (childrenOf[parentOf[id] || ""] ||= []).push(id);
  const fitFrames = () => {
    for (const id of frameOrder) {
      if (!frames[id]) continue;  // left out: nothing inside
      const inside = (childrenOf[id] || []).map((child) => boxes[child] || frames[child])
        .filter((item) => item && Number.isFinite(item.x));
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
    if (edge.ratio != null) return `${label(edge.source)}.${edge.via} contained in ${label(edge.target)}.${edge.to}: ${Math.round(edge.ratio * 1000) / 10}% of its sampled values`;
    if (edge.directed !== false) return `${label(edge.source)} → ${label(edge.target)}${edge.weight > 1 ? ` (${edge.weight} imports)` : ""}`;
    const ways = Object.entries(edge.counts || {}).map(([pair, count]) => {
      const [from, to] = pair.split("->");
      return `${label(from)} → ${label(to)}: ${count}`;
    });
    return `${label(edge.source)} — ${label(edge.target)}: ${edge.weight} import${edge.weight > 1 ? "s" : ""}\n${ways.join("\n")}`;
  };
  svg.insertAdjacentHTML("beforeend", data.edges.map((edge) => `<path class="uml-line ${edge.kind}${edge.cycle ? " cycle" : ""}${edge.lifted ? " lifted" : ""}"
    data-source="${escapeHtml(edge.source)}" data-target="${escapeHtml(edge.target)}" ${view.markers(edge)}
    ${edge.weight > 1 ? `style="stroke-width: ${1.4 + Math.min(edge.weight, 8) * 0.5}px"` : ""}><title>${escapeHtml(title(edge))}</title></path>`).join(""));
  const lines = [...svg.querySelectorAll(".uml-line")].map((element, index) => ({ element, edge: data.edges[index] }));
  // With `edgeReasons`, hovering a line opens a box with what waits, for what and why. Each line gets
  // a wider invisible twin, so it is easy to point at.
  if (view.edgeReasons) {
    const tooltip = canvas.closest(".graph-area").querySelector(".graph-tooltip");
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
        const bounds = canvas.closest(".graph-area").getBoundingClientRect();
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
    if (!forces) view.prepare?.(data.edges, ends);
    for (const line of lines) {
      line.element.setAttribute("d", path(line.edge, ends));
      line.hit?.setAttribute("d", line.element.getAttribute("d"));
      view.lineEnds?.(line.element, line.edge);  // ends that depend on where the line went (the ER diagram's)
    }
  };
  drawLines();

  // Zoom with the wheel (around the pointer), pan by dragging the background, fit to the canvas.
  let scale = 1, panX = 0, panY = 0;
  const zoomLevel = canvas.closest(".graph-page, .notes-page")?.querySelector(".graph-zoom-level");
  const apply = () => {
    stage.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
    canvas.classList.toggle("far", scale < 0.55);  // zoomed out: the details fade, the names stay
    if (zoomLevel) zoomLevel.textContent = `${Math.round(scale * 100)}%`;
  };
  // With `fitWidth`, only the width is fitted, so a tall column stays readable (dragging moves through
  // it): it starts at its top, or in the middle when it is shorter than the area. Fit always centres.
  const fit = () => {
    if (view.fitWidth) {
      scale = Math.min(1, (canvas.clientWidth - 20) / (size.width + 160));
      panX = Math.max(10, (canvas.clientWidth - size.width * scale) / 2);
      panY = Math.max(10, (canvas.clientHeight - size.height * scale) / 2);
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
  canvas.boxPositions = () => Object.fromEntries(Object.entries(boxes).map(([id, box]) => [id, { x: box.x, y: box.y }]));
  canvas.drawnData = data;  // what is drawn, for the view's own controls (the ER diagram's slices)
  // When the drawing area changes size (window resized, panel moved under it), fit again.
  const areaSize = () => `${canvas.clientWidth}x${canvas.clientHeight}`;
  let lastSize = areaSize();
  const resizing = new ResizeObserver(() => {
    const now = areaSize();
    if (now !== lastSize && document.body.contains(canvas)) {
      lastSize = now;
      fit();
    }
  });
  resizing.observe(canvas);
  signal.addEventListener("abort", () => resizing.disconnect());
  // The wheel zooms around the pointer.
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    const bounds = canvas.getBoundingClientRect();
    const x = event.clientX - bounds.left, y = event.clientY - bounds.top;
    const next = Math.min(3, Math.max(0.15, scale * (event.deltaY < 0 ? 1.15 : 1 / 1.15)));
    panX = x - (x - panX) * (next / scale);
    panY = y - (y - panY) * (next / scale);
    scale = next;
    apply();
  }, { passive: false, signal });

  // Dragging a box moves it; dragging a frame (by its title, or by its body for inner frames) moves
  // everything inside it. Frames refit and lines are redrawn as it moves. Dragging the background,
  // or the body of an outermost frame, pans; with `dragOuterFrames` (several outermost frames, like
  // the plans of the planner) every frame moves by its body and only the background pans.
  // A block being dragged pushes aside the blocks of its level it runs into (a frame with all it holds),
  // and, as its frame grows, that frame pushes its own neighbours: level by level up to the top.
  const rectOf = (id) => boxes[id] || frames[id];
  const holdings = (id) => (boxes[id] ? [boxes[id]] : (childrenOf[id] || []).flatMap(holdings));
  const pushAside = (item) => {
    for (let current = item; current; current = parentOf[current]) {
      if (!Number.isFinite(rectOf(current)?.x)) break;
      const level = [...Object.keys(boxes), ...Object.keys(frames)]
        .filter((id) => (parentOf[id] || "") === (parentOf[current] || "") && Number.isFinite(rectOf(id)?.x));
      // Whoever is pushed pushes in turn what it runs into, in a chain; the dragged block itself stays.
      const queue = [current];
      for (let steps = 0; queue.length && steps < 200; steps += 1) {
        const pusher = queue.shift(), here = rectOf(pusher);
        for (const id of level) {
          if (id === pusher || id === current) continue;
          const other = rectOf(id);
          const overlapX = Math.min(here.x + here.width, other.x + other.width) - Math.max(here.x, other.x) + FRAME_PAD;
          const overlapY = Math.min(here.y + here.height, other.y + other.height) - Math.max(here.y, other.y) + FRAME_PAD;
          if (overlapX <= FRAME_PAD || overlapY <= FRAME_PAD) continue;
          const [moveX, moveY] = overlapX < overlapY
            ? [(other.x + other.width / 2 < here.x + here.width / 2 ? -1 : 1) * overlapX, 0]
            : [0, (other.y + other.height / 2 < here.y + here.height / 2 ? -1 : 1) * overlapY];
          for (const box of holdings(id)) { box.x += moveX; box.y += moveY; }
          if (frames[id]) { frames[id].x += moveX; frames[id].y += moveY; }  // moved with what it holds
          queue.push(id);
        }
      }
      fitFrames();  // the level settled: its frame grows around it, then pushes its own neighbours
    }
  };
  let drag = null;  // what is being dragged: some boxes, or the background (moving is empty)
  holdMouse(canvas, signal);
  canvas.addEventListener("pointercancel", () => { drag = null; }, { signal });  // the browser took the mouse: nothing held
  canvas.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button, input, select, textarea, label, a")) return;  // a control, not a drag
    const boxElement = event.target.closest("[data-box]");
    const frameElement = !boxElement && event.target.closest("[data-frame]");
    // A frame moves by its title; by its body too for inner frames, except in the diagrams by levels,
    // where nearly everything is inside a frame and dragging the body pans.
    const frame = frameElement && (view.dragOuterFrames || event.target.closest(".arch-frame-head")
      || (!view.levels && parentOf[frameElement.dataset.frame])) ? frameElement.dataset.frame : "";
    const moving = boxElement ? [boxes[boxElement.dataset.box]]
      : frame ? holdings(frame) : [];
    drag = { moving, starts: moving.map((box) => ({ x: box.x, y: box.y })), clientX: event.clientX, clientY: event.clientY,
      startX: panX, startY: panY, moved: false, item: boxElement ? boxElement.dataset.box : frame, frame: 0 };
  }, { signal });
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
      if (!drag.frame) {  // at most once per screen frame: refit, push the neighbours, redraw
        const dragging = drag;
        drag.frame = requestAnimationFrame(() => {  // runs even when the drag ended meanwhile: the last move counts
          dragging.frame = 0;
          fitFrames();
          pushAside(dragging.item);
          place();
          drawLines();
        });
      }
    } else {
      panX = drag.startX + dx;
      panY = drag.startY + dy;
      apply();
    }
  }, { signal });
  canvas.addEventListener("pointerup", () => { setTimeout(() => { drag = null; }); }, { signal });

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
  // Colour: each box in the colour of its group, and a chip per group below the bar (see `colourBy`).
  const groupsBar = canvas.closest(".graph-area").querySelector(".graph-groups");
  const colourButtons = page.querySelectorAll(".graph-colour-by");
  for (const button of colourButtons) button.setAttribute("aria-checked", String(button.dataset.colour === colourBy));
  if (groupsBar) {
    groupsBar.hidden = colourBy === "kind";
    groupsBar.innerHTML = colourBy === "kind" ? "" : groupKeysAll.map((key) => `<button type="button" class="graph-group"
      data-group="${escapeHtml(key)}" style="--group: ${colours[key]}" aria-pressed="${!off.has(key)}">${escapeHtml(key)}</button>`).join("");
    for (const [id, box] of Object.entries(boxes)) {
      const groups = colourBy === "kind" ? [] : groupKeys(id);
      box.element.classList.toggle("grouped", groups.length === 1);  // a level holding several groups keeps its own colour
      if (groups.length === 1) box.element.style.setProperty("--group", colours[groups[0]]);
    }
    // A chip turns its group off or on; the drawing is made again without what is off, fitted to the screen.
    groupsBar.addEventListener("click", (event) => {
      const chip = event.target.closest(".graph-group");
      if (!chip) return;
      if (off.has(chip.dataset.group)) off.delete(chip.dataset.group);
      else off.add(chip.dataset.group);
      try { sessionStorage.setItem(offKey, JSON.stringify([...off])); } catch {}
      drawDiagram(canvas, view, null, whole);
    }, { signal });
  }
  for (const button of colourButtons) {
    button.addEventListener("click", () => {
      try { localStorage.setItem("doctracker-diagram-colour", button.dataset.colour); } catch {}
      drawDiagram(canvas, view, null, whole);
    }, { signal });
  }
  // The export button opens its menu of formats; a click anywhere else closes it.
  const exportToggle = page.querySelector(".graph-export-toggle"), exportItems = page.querySelector(".graph-export-items");
  if (exportToggle) {
    exportToggle.addEventListener("click", () => {
      exportItems.hidden = !exportItems.hidden;
      exportToggle.setAttribute("aria-expanded", String(!exportItems.hidden));
    }, { signal });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".graph-export-menu")) exportItems.hidden = true;
    }, { signal });
    exportItems.addEventListener("click", () => { exportItems.hidden = true; }, { signal });
  }
  // Save the drawing: an SVG holding the boxes and lines as they are drawn (with the wiki's styles),
  // or a PNG made from it.
  for (const button of page.querySelectorAll(".graph-export")) {
    button.addEventListener("click", async () => {
      const css = await (await fetch(document.querySelector('link[href*="style.css"]').href)).text();
      const copy = stage.cloneNode(true);
      copy.style.transform = "";
      const svgText = `<svg xmlns="http://www.w3.org/2000/svg" width="${size.width}" height="${size.height}">
        <foreignObject width="100%" height="100%"><div xmlns="http://www.w3.org/1999/xhtml" class="graph-canvas uml-canvas"
          style="width:${size.width}px;height:${size.height}px;background:${getComputedStyle(canvas).backgroundColor}">
          <style><![CDATA[${css.replace(/url\("icons\//g, 'url("' + new URL("icons/", location.origin + "/static/").href).replaceAll("]]>", "")}]]></style>
          ${new XMLSerializer().serializeToString(copy)}</div></foreignObject></svg>`;
      const name = `${canvas.dataset.view}-diagram`;
      const save = (blob, suffix) => {
        const link = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${name}.${suffix}` });
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      };
      if (button.dataset.format === "svg") return save(new Blob([svgText], { type: "image/svg+xml" }), "svg");
      const image = new Image();
      image.onload = () => {
        const picture = Object.assign(document.createElement("canvas"), { width: size.width * 2, height: size.height * 2 });
        const context = picture.getContext("2d");
        context.scale(2, 2);
        context.drawImage(image, 0, 0);
        picture.toBlob((blob) => save(blob, "png"));
      };
      image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgText)}`;
    }, { signal });
  }
  // Hovering a box lights it, its neighbours and their lines for a moment; leaving it brings back what
  // the last click chose.
  let chosen = "";
  canvas.addEventListener("mouseover", (event) => {
    const box = event.target.closest("[data-box]");
    if (box && !drag) highlight(box.dataset.box);
  }, { signal });
  canvas.addEventListener("mouseout", (event) => {
    const box = event.target.closest("[data-box]");
    if (box && !box.contains(event.relatedTarget) && !drag) highlight(chosen);
  }, { signal });
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
  // With `info`, a click also opens the panel of the box: what it is and its relations, each a link.
  // The box clicked, in the drawing's Details side panel: what it is, its page, what it relates to; a
  // name there shows that item in the panel too (and lights it in the drawing).
  const info = view.info && canvas.closest(".graph-area").querySelector(".graph-details");
  const pageButton = canvas.closest(".graph-area").querySelector(".graph-panel-page");  // in the panel's head
  const showInfo = (id, column = "") => {
    if (!info) return;
    const node = data.nodes.find((item) => item.id === id);
    if (pageButton) {
      pageButton.hidden = !node || node.page === "";
      pageButton.dataset.pageModal = node ? node.page || node.id : "";
    }
    if (!node) {
      info.innerHTML = '<p class="empty">Click a box to see what it is and what it relates to.</p>';
      return;
    }
    const columnText = column && view.columnInfo?.(node, column, data.edges, data.nodes);  // a row of the box (an ER column)
    if (columnText) {
      if (pageButton) pageButton.dataset.pageModal = node.columns.find((item) => item.name === column).path;
      info.innerHTML = columnText;
      htmx.process(info);
      openSidePanel(canvas.closest(".graph-area"));
      return;
    }
    const relations = {};
    for (const edge of data.edges) {
      if (edge.source !== id && edge.target !== id) continue;
      const outgoing = edge.source === id;
      const other = data.nodes.find((item) => item.id === (outgoing ? edge.target : edge.source));
      if (other) (relations[`${edge.kind || "relation"} ${outgoing ? "→" : "←"}`] ||= []).push(other);
    }
    const page = node.page || node.id;
    info.innerHTML = `
      <p class="graph-info-role">${escapeHtml(node.role || "")}</p>
      <h3 class="graph-details-name">${escapeHtml(node.label)}</h3>
      <code class="path">${escapeHtml(page)}</code>
      ${node.summary ? `<p>${escapeHtml(node.summary)}</p>` : ""}
      ${Object.entries(relations).map(([key, others]) => `
        <h4>${escapeHtml(key)} <span class="count">${others.length}</span></h4>
        <ul>${others.map((other) => `<li><button type="button" class="graph-details-show" data-show="${escapeHtml(other.id)}">${escapeHtml(other.label)}</button></li>`).join("")}</ul>`).join("")}`;
    htmx.process(info);
    openSidePanel(canvas.closest(".graph-area"));
  };
  info?.addEventListener("click", (event) => {
    const other = event.target.closest("[data-show]")?.dataset.show;
    if (!other) return;
    chosen = other;
    highlight(other);
    showInfo(other);
  }, { signal });
  canvas.addEventListener("click", (event) => {
    if (drag && drag.moved) return;  // the end of a drag, not a click
    if (event.target.closest("button, input, select, textarea, label, a")) return;
    const level = event.target.closest("[data-open-level]")?.dataset.openLevel
      || (view.levels && event.target.closest(".arch-frame-head") ? event.target.closest("[data-frame]").dataset.frame : "");
    if (level && view.levels) {
      const open = openFrames(view.levels);
      if (open.has(level)) open.delete(level);
      else open.add(level);
      saveOpenFrames(view.levels, open);
      drawDiagram(canvas, view, canvas.viewState?.(), whole);
      return;
    }
    const box = event.target.closest("[data-box]");
    chosen = box ? box.dataset.box : "";
    highlight(chosen);
    showInfo(chosen, event.target.closest("[data-column]")?.dataset.column || "");
    const open = event.target.closest("[data-open]")?.dataset.open;  // e.g. the planner's details panel
    if (open && view.openTarget) {
      htmx.ajax("GET", open, { target: view.openTarget });
      openSidePanel(canvas.closest(".graph-area"));
    }
  }, { signal });
  canvas.addEventListener("dblclick", (event) => {  // the page, in the consultation modal: the drawing stays
    const page = event.target.closest("[data-page]")?.dataset.page;
    if (page) openPageModal(page);
  }, { signal });

  page.querySelector(".graph-fit")?.addEventListener("click", fit, { signal });
  // Zoom buttons: around the middle of the drawing area.
  const zoomBy = (factor) => {
    const next = Math.min(3, Math.max(0.15, scale * factor));
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
  const focus = whole.focus || canvas.dataset.focus;  // the path the server found for the name typed
  const focused = focus && (boxes[focus] ? focus : boxes[`${focus}.__init__`] ? `${focus}.__init__` : "");
  if (focused) highlight(focused);
  // Hide unconnected: leave out the UNCONNECTED groups, and draw again.
  const hideLoose = page.querySelector(".graph-hide-loose");
  if (hideLoose) {
    hideLoose.setAttribute("aria-pressed", String(setting("hide-loose")));
    hideLoose.addEventListener("click", () => {
      setSetting("hide-loose", !setting("hide-loose"));
      drawDiagram(canvas, view, null, whole);
    }, { signal });
  }
  // The import cycles found (architecture), each with links to its files.
  const cyclesPanel = page.querySelector(".graph-cycles");
  if (cyclesPanel) {
    const cycles = whole.cycles || [];
    cyclesPanel.hidden = !cycles.length;
    cyclesPanel.querySelector(".count").textContent = cycles.length;
    const label = Object.fromEntries(whole.nodes.map((node) => [node.id, node]));
    cyclesPanel.querySelector("ul").innerHTML = cycles.map((members) => `<li>${members.map((id) =>
      wikiLink(label[id]?.page || id, label[id]?.label || id)).join(" ⇄ ")}</li>`).join("");
    htmx.process(cyclesPanel);
  }
  // The steps of a local graph (an entity's page): fetched and drawn again.
  const steps = page.querySelector(".graph-local-depth");
  steps?.addEventListener("change", () => {
    const url = new URL(canvas.dataset.url, location.href);
    url.searchParams.set("depth", steps.value);
    canvas.dataset.url = `${url.pathname}${url.search}`;
    drawDiagram(canvas, view, null);
  }, { signal });
  // Architecture evolution: the drawing of now, showing only what was there at the commit chosen (the
  // files the commit had added, the frames holding them, the lines between them); it follows the slider
  // as it moves, without moving anything. The end is now, everything. While the handle is held, the
  // commit shows under it, as the GIT page shows one. The commits are read once per page.
  const evolution = page.querySelector(".graph-evolution");
  if (evolution) {
    page.timeline ||= fetch("/graph/timeline").then((response) => response.json());
    const { commits, added } = await page.timeline;
    // A folder (a namespace package) appears with its first file; what is not committed, only at the end.
    const appeared = (path) => added[path] ?? Math.min(Infinity, ...Object.entries(added)
      .filter(([file]) => file.startsWith(`${path}/`)).map(([, index]) => index));
    const wholeParent = Object.fromEntries(whole.nodes.map((node) => [node.id, node.parent]));
    const appearAt = {};  // every file, and every level above it: the first commit something in it was there
    for (const node of whole.nodes) {
      if (node.frame) continue;
      const when = appeared(node.filepath);
      for (let id = node.id; id; id = wholeParent[id]) appearAt[id] = Math.min(appearAt[id] ?? Infinity, when);
    }
    const drawnParent = Object.fromEntries(data.nodes.map((node) => [node.id, node.parent]));
    const showAt = (at) => {
      const there = new Set();
      for (const [id, box] of Object.entries(boxes)) {
        const on = at >= commits.length || (appearAt[id] ?? 0) <= at;
        box.element.classList.toggle("evolution-later", !on);
        if (on) for (let up = id; up && !there.has(up); up = drawnParent[up]) there.add(up);
      }
      for (const [id, frame] of Object.entries(frames)) frame.element.classList.toggle("evolution-later", !there.has(id));
      for (const line of lines) {
        line.element.classList.toggle("evolution-later", !(there.has(line.edge.source) && there.has(line.edge.target)));
      }
    };
    const range = evolution.querySelector(".graph-evolution-range");
    const shown = evolution.querySelector(".graph-evolution-commit");
    const said = () => {
      const index = Number(range.value);
      const commit = commits[index];
      const dot = '<b class="graph-evolution-dot">•</b>';
      shown.innerHTML = commit
        ? `<header class="graph-evolution-head">Git commit ${dot} <code>${escapeHtml(commit.short)}</code> ${dot} ${index + 1} of ${commits.length}</header>
        <strong>${escapeHtml(commit.subject)}</strong>
        <span class="graph-tooltip-text">${escapeHtml(commit.author)} · ${escapeHtml(commit.date)}</span>`
        : `<header class="graph-evolution-head">Now ${dot} after the ${commits.length} commits</header>
        <strong>Everything, with what is not committed yet</strong>`;
      shown.style.setProperty("--at", commits.length ? index / commits.length : 1);
    };
    Object.assign(range, { max: commits.length, value: page.timelineAt ?? commits.length });
    evolution.hidden = !commits.length;
    showAt(Number(range.value));
    const follow = () => {
      said();
      shown.hidden = false;
      showAt(Number(range.value));
    };
    const release = () => {
      shown.hidden = true;
      page.timelineAt = Number(range.value);
    };
    // Closing the row shows everything again (now); opening it starts there too.
    page.querySelector('.graph-row-toggle[data-row="evolution"]')?.addEventListener("click", () => {
      range.value = commits.length;
      page.timelineAt = commits.length;
      showAt(commits.length);
    }, { signal });
    range.addEventListener("pointerdown", follow, { signal });
    range.addEventListener("input", follow, { signal });
    for (const name of ["pointerup", "pointercancel", "change", "blur"]) range.addEventListener(name, release, { signal });
  }
  // The view's own controls on the bar and in its filters (the ER diagram's Notation and Columns).
  view.bar?.(page, () => drawDiagram(canvas, view, canvas.viewState?.(), whole), signal);
  // Rearrange: arrange again what is on screen (the same open levels and layout), undoing what was moved.
  page.querySelector(".graph-rearrange")?.addEventListener("click", () => drawDiagram(canvas, view, null, whole), { signal });
  // The Layout switch (Layers / Forces) draws the diagram again in place.
  for (const button of page.querySelectorAll(".graph-layout")) {
    button.setAttribute("aria-checked", String(button.dataset.layout === chosenLayout()));
    button.addEventListener("click", () => {
      try { localStorage.setItem(LAYOUT_KEY, button.dataset.layout); } catch {}
      drawDiagram(canvas, view, null, whole);
    }, { signal });
  }
}

// DATABASE › Universe: the databases the server read, as SQL organises them (server → database → schema →
// tables and views → columns), drawn with sigma.js on WebGL (sigma.min.js: sigma, graphology, ForceAtlas2,
// noverlap, edge-curve; MIT). One click goes into a node, the path at the top goes back; the legend's
// relation kinds choose what is linked (none at first), Depth and Outside how far; every node is a badge
// in its kind's colour, a column's with its symbols. The view opened, the relations and the filters are
// kept for the browser tab, so a redraw (a database read again and changed) comes back where it was.
const UNIVERSE_COLORS = { server: "#24292f", database: "#bc4c00", schema: "#8250df", table: "#0969da", view: "#1a7f37", column: "#6e7781" };
const UNIVERSE_LINKS = { contains: "#8c959f", "foreign key": "#cf222e", implied: "#bf8700", "view reads": "#1a7f37", "foreign table": "#1b7c83",
                         "contained in": "#8250df" };
const UNIVERSE_OUTSIDE = "#9cc3f5";  // a node outside the one opened, drawn only because a link reaches it
// ForceAtlas2 pushes two nodes apart by the product of their masses (1 + the weight of their links); a
// link from a node to itself adds mass without pulling anything, so schemas and tables push harder.
const UNIVERSE_MASS = { server: 40, database: 40, schema: 40, table: 5, view: 2 };
const UNIVERSE_LEVEL = { server: 0, database: 1, schema: 2, table: 3, view: 3, column: 4 };
const UNIVERSE_NAMES = ["servers", "databases", "schemas", "tables", "columns"];
const UNIVERSE_KEY = "doctracker-universe";
// A column's characteristics, in the shapes database tools use: key primary key, link foreign key (it
// points elsewhere), diamond unique, lines indexed, bolt computed by the database, asterisk not null,
// crossed circle null allowed. Key, link and lines are Tabler's (MIT).
const UNIVERSE_SYMBOLS = {
  pk: [`<path d="M16.555 3.843l3.602 3.602a2.877 2.877 0 0 1 0 4.069l-2.643 2.643a2.877 2.877 0 0 1 -4.069 0l-.301 -.301l-6.558 6.558a2 2 0 0 1 -1.239 .578l-.175 .008h-1.172a1 1 0 0 1 -.993 -.883l-.007 -.117v-1.172a2 2 0 0 1 .467 -1.284l.119 -.13l.414 -.414h2v-2h2v-2l2.144 -2.144l-.301 -.301a2.877 2.877 0 0 1 0 -4.069l2.643 -2.643a2.877 2.877 0 0 1 4.069 0z"/><path d="M15 9h.01"/>`, "primary key"],
  fk: [`<path d="M9 15l6 -6"/><path d="M11 6l.463 -.536a5 5 0 0 1 7.071 7.072l-.534 .464"/><path d="M13 18l-.397 .534a5.068 5.068 0 0 1 -7.127 0a4.972 4.972 0 0 1 0 -7.071l.524 -.463"/>`, "foreign key"],
  unique: [`<path d="M12 3l9 9l-9 9l-9 -9z" fill="#000"/>`, "unique"],
  index: [`<path d="M9 6h11M9 12h11M9 18h11M5 6v.01M5 12v.01M5 18v.01"/>`, "indexed"],
  generated: [`<path d="M13 3v7h6l-8 11v-7h-6l8 -11" fill="#000"/>`, "computed by the database"],
  notnull: [`<path d="M12 4v16M5 8l14 8M19 8l-14 8"/>`, "not null"],
  null: [`<circle cx="12" cy="12" r="7"/><path d="M5 19l14 -14"/>`, "null allowed"],
};
const UNIVERSE_FONT = { server: 15, database: 14, schema: 13, table: 12, view: 12, column: 11 };
const UNIVERSE_FAMILY = "system-ui, sans-serif";
const UNIVERSE_PAD = 5;
// A colour mixed towards white: on a badge, the symbols take a light tint of the badge's own colour.
const universeTint = (hex, k) => "#" + [1, 3, 5].map((i) => Math.round(parseInt(hex.slice(i, i + 2), 16) * (1 - k) + 255 * k).toString(16).padStart(2, "0")).join("");
const universeIcons = new Map();
function universeIcon(mark, colour, loaded = () => {}) {
  const key = mark + colour;
  if (!universeIcons.has(key)) {
    const img = new Image();
    img.onload = loaded;
    img.src = `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="${colour}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">${UNIVERSE_SYMBOLS[mark][0].replace(/#000/g, colour)}</svg>`)}`;
    universeIcons.set(key, img);
  }
  return universeIcons.get(key);
}
const universeMarks = (flags = []) => [...["pk", "fk", "unique", "index", "generated"].filter((f) => flags.includes(f)), flags.includes("null") ? "null" : "notnull"];
// The forces, the same for the first layout and for the live movement (slower, so it moves gently); strong
// gravity keeps nodes without links near the others instead of drifting away.
const universeForces = (graph, slowDown = 1) => ({ ...SigmaBundle.forceAtlas2.inferSettings(graph), barnesHutOptimize: true, strongGravityMode: true,
  gravity: 0.3, scalingRatio: 40, edgeWeightInfluence: 1, linLogMode: true, outboundAttractionDistribution: true, slowDown });

// The Universe's drawing engine without WebGL: the part of sigma the Universe uses, drawn in Canvas 2D, so
// the same Universe (graph, layout, badges, legend, path, hover box, details, clicks, drag, zoom, pan)
// runs where WebGL is off. Coordinates as sigma's: the graph's box (the custom one when set) normalised
// to a square, y upwards, then the camera (x, y, ratio) on the viewport's smaller side. Nodes are drawn
// by the Universe's own badge (the settings' defaultDrawNodeLabel / defaultDrawNodeHover), edges as lines,
// a curved one as a quadratic curve bowing by its curvature.
class UniverseCanvas {
  constructor(graph, container, settings) {
    this.graph = graph; this.container = container; this.settings = settings;
    this.camera = { x: 0.5, y: 0.5, ratio: 1, angle: 0 };
    this.bbox = null; this.handlers = new Map(); this.captorHandlers = new Map(); this.hoveredEdge = null;
    this.element = document.createElement("canvas");
    this.element.style.cssText = "position:absolute;inset:0;width:100%;height:100%";
    container.style.position ||= "relative";
    container.appendChild(this.element);
    this.context = this.element.getContext("2d");
    this.listeners = new AbortController();
    const signal = this.listeners.signal, at = (e) => { const r = this.element.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    const captured = (name, e, extra = {}) => {
      let prevented = false;
      const event = { ...at(e), ...extra, original: e, preventSigmaDefault: () => { prevented = true; } };
      for (const fn of this.captorHandlers.get(name) ?? []) fn(event);
      return prevented;
    };
    let panning = null, downAt = null;
    holdMouse(this.element, signal);
    this.element.addEventListener("mousedown", (e) => {
      downAt = at(e);
      if (!captured("mousedown", e)) panning = { ...downAt, camera: { ...this.camera } };
    }, { signal });
    window.addEventListener("mousemove", (e) => {
      const inside = e.target === this.element;
      if (inside || panning) captured("mousemovebody", e);
      if (panning) {
        const p = at(e), side = Math.min(this.width, this.height) || 1;
        this.camera.x = panning.camera.x - ((p.x - panning.x) / side) * this.camera.ratio;
        this.camera.y = panning.camera.y + ((p.y - panning.y) / side) * this.camera.ratio;
        this.schedule();
      } else if (inside) this.edgeUnder(at(e));
    }, { signal });
    window.addEventListener("mouseup", (e) => {
      if (!downAt) return;
      const p = at(e), still = Math.hypot(p.x - downAt.x, p.y - downAt.y) < 4;
      captured("mouseup", e);
      if (still && e.target === this.element) captured("click", e);
      panning = null; downAt = null;
    }, { signal });
    this.element.addEventListener("wheel", (e) => {
      e.preventDefault();
      const p = at(e), before = this.viewportToGraph(p);
      this.camera.ratio = Math.min(Math.max(this.camera.ratio * (e.deltaY > 0 ? 1.15 : 1 / 1.15), 0.02), 20);
      const after = this.viewportToGraph(p), side = this.side();
      this.camera.x += (before.x - after.x) / side.span; this.camera.y += (before.y - after.y) / side.span;
      this.schedule();
    }, { signal, passive: false });
    this.element.addEventListener("mouseleave", () => { if (this.hoveredEdge) { this.emit("leaveEdge", { edge: this.hoveredEdge }); this.hoveredEdge = null; } }, { signal });
    this.resize();
  }
  on(name, fn) { if (!this.handlers.has(name)) this.handlers.set(name, []); this.handlers.get(name).push(fn); return this; }
  emit(name, payload) { for (const fn of this.handlers.get(name) ?? []) fn(payload); }
  getMouseCaptor() { const self = this; return { on(name, fn) { if (!self.captorHandlers.has(name)) self.captorHandlers.set(name, []); self.captorHandlers.get(name).push(fn); return this; } }; }
  getCamera() { return { setState: (state) => { Object.assign(this.camera, state); this.schedule(); }, getState: () => ({ ...this.camera }) }; }
  setCustomBBox(bbox) { this.bbox = bbox; }
  kill() { this.listeners.abort(); this.element.remove(); }
  resize() {
    const ratio = window.devicePixelRatio || 1;
    this.width = this.container.clientWidth; this.height = this.container.clientHeight;
    this.element.width = Math.max(1, Math.round(this.width * ratio)); this.element.height = Math.max(1, Math.round(this.height * ratio));
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }
  // The graph's box made a square (its larger side), as sigma normalises it.
  side() {
    let x = this.bbox?.x, y = this.bbox?.y;
    if (!x || !y) {
      const xs = [], ys = []; this.graph.forEachNode((_, a) => { xs.push(a.x); ys.push(a.y); });
      x = [Math.min(...xs, 0), Math.max(...xs, 1)]; y = [Math.min(...ys, 0), Math.max(...ys, 1)];
    }
    return { cx: (x[0] + x[1]) / 2, cy: (y[0] + y[1]) / 2, span: Math.max(x[1] - x[0], y[1] - y[0]) || 1 };
  }
  graphToViewport(p) {
    const b = this.side(), side = Math.min(this.width, this.height) || 1;
    const nx = (p.x - b.cx) / b.span + 0.5, ny = (p.y - b.cy) / b.span + 0.5;
    return { x: ((nx - this.camera.x) / this.camera.ratio) * side + this.width / 2, y: (-(ny - this.camera.y) / this.camera.ratio) * side + this.height / 2 };
  }
  viewportToGraph(p) {
    const b = this.side(), side = Math.min(this.width, this.height) || 1;
    const nx = ((p.x - this.width / 2) / side) * this.camera.ratio + this.camera.x, ny = -((p.y - this.height / 2) / side) * this.camera.ratio + this.camera.y;
    return { x: (nx - 0.5) * b.span + b.cx, y: (ny - 0.5) * b.span + b.cy };
  }
  schedule() { if (this.frame) return; this.frame = requestAnimationFrame(() => { this.frame = null; this.refresh(); }); }
  // The ends of an edge on the screen, and its control point when curved.
  edgeGeometry(edge, a, s, t) {
    const p = this.graphToViewport(this.graph.getNodeAttributes(s)), q = this.graphToViewport(this.graph.getNodeAttributes(t));
    if (a.type !== "curved" || !a.curvature) return { p, q };
    const mx = (p.x + q.x) / 2, my = (p.y + q.y) / 2, dx = q.x - p.x, dy = q.y - p.y;
    return { p, q, c: { x: mx - dy * a.curvature, y: my + dx * a.curvature } };
  }
  edgeUnder(at) {
    if (!this.settings.enableEdgeEvents) return;
    let found = null;
    this.graph.forEachEdge((edge, attributes, s, t) => {
      if (found || s === t) return;
      const a = this.settings.edgeReducer ? this.settings.edgeReducer(edge, attributes) : attributes;
      if (a.hidden) return;
      const { p, q, c } = this.edgeGeometry(edge, a, s, t), m = c ?? { x: (p.x + q.x) / 2, y: (p.y + q.y) / 2 };
      // Distance to the line, the curve taken as its two halves.
      const near = (u, v) => { const dx = v.x - u.x, dy = v.y - u.y, l = dx * dx + dy * dy || 1, k = Math.max(0, Math.min(1, ((at.x - u.x) * dx + (at.y - u.y) * dy) / l));
        return Math.hypot(at.x - (u.x + k * dx), at.y - (u.y + k * dy)); };
      if (Math.min(near(p, m), near(m, q)) <= Math.max(3, (a.size ?? 1) / 2 + 2)) found = edge;
    });
    if (found === this.hoveredEdge) return;
    if (this.hoveredEdge) this.emit("leaveEdge", { edge: this.hoveredEdge });
    this.hoveredEdge = found;
    if (found) this.emit("enterEdge", { edge: found });
  }
  refresh() {
    const context = this.context, settings = this.settings;
    this.emit("beforeRender");
    context.clearRect(0, 0, this.width, this.height);
    this.graph.forEachEdge((edge, attributes, s, t) => {
      if (s === t) return;
      const a = settings.edgeReducer ? settings.edgeReducer(edge, attributes) : attributes;
      if (a.hidden) return;
      const { p, q, c } = this.edgeGeometry(edge, a, s, t);
      context.beginPath(); context.moveTo(p.x, p.y);
      c ? context.quadraticCurveTo(c.x, c.y, q.x, q.y) : context.lineTo(q.x, q.y);
      context.strokeStyle = a.color || "#999"; context.lineWidth = Math.max(1.2, a.size ?? 1); context.stroke();  // never thinner than a pixel and a bit
    });
    const nodes = [];
    this.graph.forEachNode((node, attributes) => {
      const a = settings.nodeReducer ? settings.nodeReducer(node, attributes) : attributes;
      if (a.hidden) return;
      nodes.push({ ...a, ...this.graphToViewport(attributes) });
    });
    for (const d of nodes) if (!d.highlighted) settings.defaultDrawNodeLabel?.(context, d, settings);
    for (const d of nodes) if (d.highlighted) (settings.defaultDrawNodeHover ?? settings.defaultDrawNodeLabel)?.(context, d, settings);
  }
}

async function drawUniverse(canvas) {
  const area = canvas.closest(".graph-area"), page = canvas.closest(".graph-page");
  page.diagramListeners?.abort();
  page.diagramListeners = new AbortController();
  const signal = page.diagramListeners.signal;
  if (typeof SigmaBundle === "undefined") {
    canvas.innerHTML = '<p class="empty">The Universe could not load its drawing library.</p>';
    return;
  }
  // The engine: sigma on WebGL (it takes WebGL 2, else WebGL 1), else our own in Canvas 2D (UniverseCanvas).
  const probe = document.createElement("canvas");
  const webgl = Boolean(probe.getContext("webgl2") || probe.getContext("webgl") || probe.getContext("experimental-webgl"));
  const { Graph, Sigma, EdgeCurveProgram, indexParallelEdgesIndex, forceAtlas2, noverlap } = SigmaBundle;
  const data = await (await fetch(canvas.dataset.url)).json();
  if (!data.nodes.length) {
    canvas.innerHTML = '<p class="empty">No database read yet: allow a connection in Connections.</p>';
    return;
  }
  canvas.innerHTML = "";
  const box = canvas.closest(".graph-canvas-box");
  box.querySelectorAll(".universe-path, .universe-hover, .universe-engine").forEach((element) => element.remove());
  box.insertAdjacentHTML("beforeend", `<div class="universe-path"><button type="button" class="graph-icon universe-back" aria-label="Back" data-tip="Back one level">←</button>
    <span class="universe-crumbs"></span><span class="universe-stats"></span></div>
    ${webgl ? "" : '<div class="universe-engine" title="WebGL is off in this browser (its hardware acceleration), so the Universe is drawn in Canvas 2D, which slows down with thousands of nodes and lines. Turn hardware acceleration on to draw large databases smoothly.">drawn without WebGL · turn on WebGL (hardware acceleration) to scale to large databases</div>'}
    <div class="universe-hover" hidden><div class="universe-hover-body"></div><button type="button" class="see-in-link universe-hover-details">Details ›</button></div>`);
  const crumbsBox = box.querySelector(".universe-crumbs"), backButton = box.querySelector(".universe-back"), hoverBox = box.querySelector(".universe-hover");
  const tooltip = area.querySelector(".graph-tooltip"), info = area.querySelector(".graph-details");
  const pageButton = area.querySelector(".graph-panel-page");  // the page of the node shown in Details
  if (pageButton) pageButton.hidden = true;

  // The SQL tree: every node knows its parent.
  const byId = new Map(data.nodes.map((n) => [n.id, n]));
  const children = new Map();
  for (const n of data.nodes) if (n.parent && byId.has(n.parent)) { if (!children.has(n.parent)) children.set(n.parent, []); children.get(n.parent).push(n.id); }
  const level = (id) => UNIVERSE_LEVEL[byId.get(id).kind];
  const up = (id, at) => { let x = id; while (x && level(x) > at) x = byId.get(x).parent; return x; };  // the ancestor at a level
  const chain = (id) => { const c = []; for (let x = id; x && byId.has(x); x = byId.get(x).parent) c.unshift(x); return c; };
  const relations = data.edges;
  // A column drawn with a foreign key line always carries the foreign key mark.
  for (const e of relations) if (e.kind === "foreign key") { const c = byId.get(e.source); if (c?.kind === "column" && !(c.flags ??= []).includes("fk")) c.flags.push("fk"); }
  const esc = escapeHtml;

  // What the user chose, kept for the browser tab.
  // An object's page keeps its own (it opens on that object), so it does not move the Universe tab.
  const savedKey = canvas.closest(".universe-embed") ? `${UNIVERSE_KEY}-page` : UNIVERSE_KEY;
  let saved = {};
  try { saved = JSON.parse(sessionStorage.getItem(savedKey) || "{}"); } catch {}
  const themes = new Set(saved.themes || []);
  let depth = saved.depth || 1, others = Boolean(saved.others);
  let path = (saved.path || []).filter((id) => byId.has(id));
  // Opened from an object's page ("See in Universe"): the view of that object, or of what holds it
  // (a column's table; a function or trigger is not drawn: its schema or table).
  let opened = canvas.dataset.focus;
  while (opened && !byId.has(opened)) { const holder = opened.replace(/[.:/][^.:/]*$/, ""); opened = holder === opened ? "" : holder; }
  if (opened) path = chain(byId.get(opened).kind === "column" ? byId.get(opened).parent : opened);
  const remember = () => { try { sessionStorage.setItem(savedKey, JSON.stringify({ themes: [...themes], depth, others, path })); } catch {} };

  // The legend: colours, the relation kinds (each turns its relations on or off), the column symbols.
  const legend = fillLegend(canvas);
  for (const swatch of legend?.querySelectorAll(".universe-swatch") ?? []) swatch.style.background = swatch.dataset.node === "outside" ? UNIVERSE_OUTSIDE : UNIVERSE_COLORS[swatch.dataset.node];
  for (const line of legend?.querySelectorAll(".universe-line") ?? []) line.style.borderColor = UNIVERSE_LINKS[line.dataset.relation];
  for (const img of legend?.querySelectorAll(".universe-mark") ?? []) img.src = universeIcon(img.dataset.mark, UNIVERSE_COLORS.column).src;
  for (const button of legend?.querySelectorAll(".universe-kind") ?? []) {
    button.setAttribute("aria-pressed", String(themes.has(button.dataset.kind)));
    button.addEventListener("click", () => {
      themes.has(button.dataset.kind) ? themes.delete(button.dataset.kind) : themes.add(button.dataset.kind);
      button.setAttribute("aria-pressed", String(themes.has(button.dataset.kind)));
      show(path, true);
    }, { signal });
  }
  const depthField = area.querySelector('.universe-filters select[name="depth"]'), othersField = area.querySelector('.universe-filters input[name="others"]');
  if (depthField) { depthField.value = String(depth); depthField.addEventListener("change", () => { depth = +depthField.value; show(path, true); }, { signal }); }
  if (othersField) { othersField.checked = others; othersField.addEventListener("change", () => { others = othersField.checked; show(path, true); }, { signal }); }

  // What one view holds. [] = the servers. A server, database or schema opened = that node in the middle
  // and its children; relations are drawn between children (each end lifted to the child holding it), and
  // nodes outside it reached by them, up to Depth steps, only with Outside. A table opened = its columns
  // around it, each linked to the tables at the other end. "+n" = links to nodes not drawn.
  function build(path) {
    const nodes = new Map(), links = new Map();
    const node = (id, extra = {}) => { if (!nodes.has(id)) nodes.set(id, { id, kind: byId.get(id).kind, ...extra }); };
    // One line per pair of nodes and kind of relation, both directions summed.
    // A relation found through the samples (contained in) brings its share of values, shown on hover.
    const link = (a, b, kind, ratio) => { if (a === b) return; const key = (a < b ? `${a}|${b}` : `${b}|${a}`) + `|${kind}`;
      if (!links.has(key)) links.set(key, { a, b, kinds: {}, ratios: [] }); const l = links.get(key); l.kinds[kind] = (l.kinds[kind] ?? 0) + 1;
      if (ratio != null) l.ratios.push(ratio); };
    const chosen = relations.filter((e) => themes.has(e.kind));
    const focus = path.at(-1), at = focus ? Math.min(level(focus) + 1, 3) : 0;  // the level drawn
    const home = focus ? up(focus, Math.min(level(focus), 2)) : null;        // what counts as inside
    const inside = (id) => !home || up(id, level(home)) === home;
    const near = new Map();
    for (const e of chosen) { const a = up(e.source, at), b = up(e.target, at); if (!a || !b || a === b) continue;
      for (const [x, y] of [[a, b], [b, a]]) { if (!near.has(x)) near.set(x, new Set()); near.get(x).add(y); } }
    let ring = !focus ? data.nodes.filter((n) => n.kind === "server").map((n) => n.id) : level(focus) === 3 ? [focus] : (children.get(focus) ?? []);
    const reached = new Set(ring), via = new Map();  // via: the node each one was reached from
    for (let step = 0; focus && step < depth; step++) {
      const next = [];
      for (const t of ring) for (const n of near.get(t) ?? []) if (!reached.has(n) && (others || inside(n))) { reached.add(n); via.set(n, t); next.push(n); }
      ring = next;
    }
    if (focus) node(focus);  // first, so it starts in the middle
    for (const t of reached) node(t, inside(t) ? {} : { outside: true });
    const table = focus && level(focus) === 3 ? focus : null;
    for (const e of chosen) {
      const a = up(e.source, at), b = up(e.target, at);
      if (!reached.has(a) || !reached.has(b)) { for (const t of [a, b]) if (reached.has(t)) nodes.get(t).away = (nodes.get(t).away ?? 0) + 1; continue; }
      // The table opened links through its columns; everything else node to node.
      const from = a === table ? up(e.source, 4) : a, to = b === table ? up(e.target, 4) : b;
      if (from !== a) node(from); if (to !== b) node(to);
      link(from, to, e.kind, e.ratio);
    }
    if (table) for (const c of children.get(table) ?? []) { node(c); link(table, c, "contains"); }
    else if (focus) for (const t of reached) if (byId.get(t).parent === focus) link(focus, t, "contains");
    return { nodes, links, via };
  }

  // A name short enough to read: inside the one opened its own name; outside it, the path from where it differs.
  let outsideNodes = new Set();
  function name(id) {
    const n = byId.get(id), focus = path.at(-1);
    if (!focus || !outsideNodes.has(id)) return n.label;
    const mine = chain(focus), its = chain(id); let i = 0; while (i < mine.length && mine[i] === its[i]) i++;
    return its.slice(i).map((x) => byId.get(x).label).join(" › ");
  }
  const measure = document.createElement("canvas").getContext("2d");
  function badgeSize(label, kind, marks) {
    const f = UNIVERSE_FONT[kind]; measure.font = `600 ${f}px ${UNIVERSE_FAMILY}`;
    const symbols = marks ? marks.length * (f + 3) + 10 : 0;  // with the divider before them
    return [Math.ceil(symbols + measure.measureText(label).width + 2 * UNIVERSE_PAD), f + 2 * UNIVERSE_PAD];
  }

  const graph = new Graph({ multi: true });
  const positions = new Map();  // view → positions, so going back finds the drawing where it was
  let renderer = null;
  function show(next, keepPositions = false) {
    if (graph.order) { const p = {}; graph.forEachNode((id, a) => (p[id] = [a.x, a.y])); positions.set(path.join("|"), p); }
    const before = keepPositions ? positions.get(path.join("|")) : null;
    path = next;
    remember();
    const { nodes, links, via } = build(path), memory = before ?? positions.get(path.join("|")) ?? {};
    outsideNodes = new Set([...nodes.values()].filter((n) => n.outside).map((n) => n.id));
    graph.clear();
    // Nodes new to this view start in a spiral as wide as the drawing already there.
    const known = Object.values(memory), wide = known.length ? Math.max(...known.map(([x, y]) => Math.hypot(x, y))) / Math.sqrt(nodes.size) : 10;
    let i = 0, fresh = 0;
    for (const n of nodes.values()) {
      if (!memory[n.id]) fresh++;
      const [x, y] = memory[n.id] ?? [Math.cos(i * 2.4) * wide * Math.sqrt(i + 1), Math.sin(i * 2.4) * wide * Math.sqrt(i + 1)]; i++;
      const marks = n.kind === "column" ? universeMarks(byId.get(n.id).flags) : null, label = name(n.id) + (n.away ? ` (+${n.away})` : "");
      const [bw, bh] = badgeSize(label, n.kind, marks);
      // The badge is the node: sigma's own dot stays transparent underneath.
      graph.addNode(n.id, { x, y, kind: n.kind, outside: !!n.outside, marks, label, bw, bh, size: 3, color: "rgba(0,0,0,0)",
        fill: n.outside ? (UNIVERSE_LEVEL[n.kind] >= 3 ? UNIVERSE_OUTSIDE : universeTint(UNIVERSE_COLORS[n.kind], 0.45)) : UNIVERSE_COLORS[n.kind] });
      if (UNIVERSE_MASS[n.kind]) graph.addEdge(n.id, n.id, { kind: "mass", weight: UNIVERSE_MASS[n.kind] });
    }
    for (const l of links.values()) {
      const [kind, total] = Object.entries(l.kinds)[0];
      graph.addEdge(l.a, l.b, { kind, kinds: l.kinds, ratios: l.ratios, weight: kind === "contains" ? 3 : 1, color: UNIVERSE_LINKS[kind],
        size: kind === "contains" ? 0.5 : Math.min(1 + Math.log2(total) * 1.2, 9) });
    }
    // Two kinds between the same pair: the lines bend apart instead of covering each other.
    indexParallelEdgesIndex(graph, { edgeIndexAttribute: "parallelIndex", edgeMaxIndexAttribute: "parallelMaxIndex" });
    graph.forEachEdge((edge, a) => { if (a.kind !== "mass" && a.parallelIndex > 0) graph.mergeEdgeAttributes(edge, { type: "curved", curvature: 0.12 * a.parallelIndex }); });
    // A new view opens already settled; a view seen before comes back as it was.
    if (fresh) path.length && level(path.at(-1)) === 3 ? radial(path.at(-1), via) : forceAtlas2.assign(graph, { iterations: 300, settings: universeForces(graph) });
    crumbs();
    apart();
    const lines = [...links.values()].filter((l) => !l.kinds.contains).length;
    box.querySelector(".universe-stats").textContent = `${graph.order} nodes · ${lines} lines`;
  }
  // Layout units per screen pixel, chosen so that neighbours sit a gap apart that grows with the badges
  // (servers further apart than columns), whatever scale the layout produced. A table's rings are laid
  // out in pixels already.
  function unitOf() {
    if (path.length && level(path.at(-1)) === 3) return 1;
    const pts = []; graph.forEachNode((_, a) => pts.push([a.x, a.y, a.bw]));
    const gaps = pts.map((p) => Math.min(...pts.filter((q) => q !== p).map((q) => Math.hypot(p[0] - q[0], p[1] - q[1])))).filter((g) => Number.isFinite(g) && g > 0).sort((a, b) => a - b);
    const widths = pts.map((p) => p[2]).sort((a, b) => a - b);
    return gaps.length ? gaps[gaps.length >> 1] / (widths[widths.length >> 1] + 40) : 1;
  }
  // No badge covers another: each node pushed out of its neighbours' way, by the size of its badge.
  let baseUnit = 1;
  function apart() {
    const unit = unitOf();
    noverlap.assign(graph, { maxIterations: 600, settings: { margin: 8 * unit, ratio: 1, expansion: 1.05, gridSize: 4 },
      inputReducer: (_, a) => ({ x: a.x, y: a.y, size: (a.bw / 2) * unit }), outputReducer: (_, p) => ({ x: p.x, y: p.y }) });
    baseUnit = unit; fit();
  }
  // The camera at one pixel per unit: only a drawing larger than the screen is zoomed out.
  function fit() {
    if (!renderer || !graph.order) return;
    const unit = baseUnit, xs = [], ys = []; graph.forEachNode((_, a) => { xs.push(a.x); ys.push(a.y); });
    const w = canvas.clientWidth, h = canvas.clientHeight, cx = (Math.min(...xs) + Math.max(...xs)) / 2, cy = (Math.min(...ys) + Math.max(...ys)) / 2;
    const side = Math.max(Math.max(...xs) - Math.min(...xs) + 260 * unit, Math.max(...ys) - Math.min(...ys) + 120 * unit, Math.min(w, h) * unit);
    renderer.setCustomBBox({ x: [cx - side / 2, cx + side / 2], y: [cy - side / 2, cy + side / 2] });
    renderer.getCamera().setState({ x: 0.5, y: 0.5, ratio: 1, angle: 0 });
    renderer.refresh();
  }
  function crumbs() {
    const parts = [["Universe", []], ...path.map((p, i) => [byId.get(p).label, path.slice(0, i + 1)])];
    crumbsBox.innerHTML = parts.map(([label], i) => (i === parts.length - 1 ? `<b>${esc(label)}</b>` : `<a data-i="${i}">${esc(label)}</a>`)).join(" › ");
    backButton.disabled = !path.length;
    const label = area.querySelector(".universe-others");
    if (label) label.textContent = `other ${UNIVERSE_NAMES[Math.min(path.length ? level(path.at(-1)) : 2, 2)]}`;
  }
  crumbsBox.addEventListener("click", (e) => { if (e.target.dataset.i) show(path.slice(0, +e.target.dataset.i)); }, { signal });
  backButton.addEventListener("click", () => show(path.slice(0, -1)), { signal });

  // A table's view is drawn in rings, so lines do not cross: the table in the middle, its columns around
  // it, each table reached through a column straight out from that column, the next steps further out
  // from the table they were reached from. Each slice of the circle is as wide as what hangs on it.
  function radial(table, via) {
    const columns = (children.get(table) ?? []).filter((c) => graph.hasNode(c)), place = new Map([[table, [0, 0]]]);
    const hang = new Map();
    for (const t of via.keys()) {
      let parent = via.get(t);
      if (parent === table) parent = graph.neighbors(t).find((n) => columns.includes(n)) ?? columns[0];
      if (!hang.has(parent)) hang.set(parent, []); hang.get(parent).push(t);
    }
    const weight = new Map(), count = (n) => { const w = Math.max(1, (hang.get(n) ?? []).reduce((s, k) => s + count(k), 0)); weight.set(n, w); return w; };
    // Columns with nothing hanging still get room enough to read their names.
    const below = columns.reduce((s, c) => s + count(c), 0), room = Math.max(1, below / Math.max(columns.length, 1));
    for (const c of columns) if (!hang.has(c)) weight.set(c, room);
    const total = columns.reduce((s, c) => s + weight.get(c), 0);
    // Distances in pixels: the columns' ring just wide enough for their names, the tables well beyond.
    const inner = Math.max(80, columns.length * 16);
    const out = (n, start, w, ring) => {
      place.set(n, [start + w / 2, ring]);
      let at = start;
      for (const k of hang.get(n) ?? []) { const kw = (w * weight.get(k)) / weight.get(n); out(k, at, kw, ring === inner ? inner + 150 : ring + 140); at += kw; }
    };
    let at = 0;
    for (const c of columns) { const w = (2 * Math.PI * weight.get(c)) / total; out(c, at, w, inner); at += w; }
    graph.forEachNode((id) => { const p = place.get(id); if (!p) return; const [a, r] = p; graph.mergeNodeAttributes(id, { x: Math.cos(a) * r, y: Math.sin(a) * r }); });
    // Links that are not the way a table was reached cross the rings: drawn faint, so the tree reads.
    graph.forEachEdge((e, a, s, t) => { if (a.kind === "mass" || a.kind === "contains") return;
      const tree = via.get(s) === t || via.get(t) === s || columns.includes(s) || columns.includes(t);
      if (!tree) graph.mergeEdgeAttributes(e, { color: a.color + "40", size: 0.6 }); });
  }

  // Live movement after a drag: a few steps of the forces per frame, then it rests (not in a table's rings).
  let steps = 0;
  function move(frames) { if (path.length && level(path.at(-1)) === 3) return; const idle = steps === 0; steps = Math.max(steps, frames); if (idle) requestAnimationFrame(step); }
  function step() {
    if (steps <= 0 || signal.aborted) return;
    forceAtlas2.assign(graph, { iterations: 1, settings: universeForces(graph, 8) });
    if (--steps === 0) { const unit = unitOf(); noverlap.assign(graph, { maxIterations: 100, settings: { margin: 6 * unit }, inputReducer: (_, a) => ({ x: a.x, y: a.y, size: (a.bw / 2) * unit }), outputReducer: (_, p) => ({ x: p.x, y: p.y }) }); }
    requestAnimationFrame(step);
  }

  // The badge: opaque, in the colour of its kind, the name in white, then a column's symbols after a thin
  // divider, in a light tint of the same colour. Faded when another node is hovered, or when it does not
  // hold the text of Highlight; outlined when it is the one hovered or holds that text. Where each badge
  // was drawn is kept, so the mouse finds nodes by their badge. Badges follow the zoom: at the opening
  // zoom they have their own size; zoomed out they shrink with the distances; too small to read, only
  // the coloured shape stays.
  const rects = new Map();
  let scale = 1, hovered = null, near = new Set(), dragged = null, moved = false, find = "";
  function drawBadge(context, d, hover = false) {
    if (scale === null) { const a = renderer.graphToViewport({ x: 0, y: 0 }), b = renderer.graphToViewport({ x: baseUnit, y: 0 }); scale = Math.hypot(b.x - a.x, b.y - a.y) || 1; }
    const k = Math.min(scale, 1), f = UNIVERSE_FONT[d.kind] * k, w = d.bw * k, h = d.bh * k, left = d.x - w / 2, top = d.y - h / 2;
    rects.set(d.key, [left, top, w, h]);
    context.globalAlpha = d.dim ? 0.18 : 1;
    context.beginPath(); context.roundRect(left, top, w, h, 5 * k);
    context.fillStyle = d.fill; context.fill();
    if (hover || d.found) { context.strokeStyle = d.found ? "#d4a72c" : "#1f2328"; context.lineWidth = d.found ? 3 : 2; context.stroke(); }
    if (f >= 6) {
      const marks = d.marks ?? [], y0 = d.y - f / 2;
      context.font = `600 ${f}px ${UNIVERSE_FAMILY}`;
      const text = context.measureText(d.label).width, symbols = marks.length ? marks.length * (f + 3 * k) + 10 * k : 0;
      const start = d.x - (text + symbols) / 2;
      context.fillStyle = "#ffffff"; context.textBaseline = "top";
      context.fillText(d.label, start, y0);
      context.textBaseline = "alphabetic";
      if (marks.length) { context.strokeStyle = universeTint(d.fill, 0.55); context.lineWidth = 1; context.beginPath();
        context.moveTo(start + text + 5 * k, top + 3 * k); context.lineTo(start + text + 5 * k, top + h - 3 * k); context.stroke(); }
      let x = start + text + 10 * k;
      for (const m of marks) { const img = universeIcon(m, universeTint(d.fill, 0.8), () => renderer?.refresh()); if (img.complete) context.drawImage(img, x, y0, f, f); x += f + 3 * k; }
    }
    context.globalAlpha = 1;
  }
  const hit = (x, y) => { let found = null; for (const [id, [l, t, w, h]] of rects) if (x >= l && x <= l + w && y >= t && y <= t + h && graph.hasNode(id)) found = id; return found; };

  show(path);
  renderer = new (webgl ? Sigma : UniverseCanvas)(graph, canvas, {
    labelRenderedSizeThreshold: 0, enableEdgeEvents: true, edgeProgramClasses: { curved: EdgeCurveProgram },
    defaultDrawNodeLabel: (context, d) => drawBadge(context, d), defaultDrawNodeHover: (context, d) => drawBadge(context, d, true),
    nodeReducer: (id, a) => {
      const found = Boolean(find) && a.label.toLowerCase().includes(find);
      return { ...a, key: id, forceLabel: true, highlighted: id === hovered, found,
               dim: (!!hovered && id !== hovered && !near.has(id)) || (Boolean(find) && !found) };
    },
    edgeReducer: (id, a) => {
      if (a.kind === "mass") return { ...a, hidden: true };
      const s = graph.source(id), t = graph.target(id);
      if (hovered && s !== hovered && t !== hovered) return { ...a, hidden: true };
      return a;
    },
  });
  renderer.on("beforeRender", () => { rects.clear(); scale = null; });
  apart();
  signal.addEventListener("abort", () => renderer.kill());
  const resized = new ResizeObserver(() => { renderer.resize(); renderer.refresh(); });
  resized.observe(canvas);
  signal.addEventListener("abort", () => resized.disconnect());
  area.querySelector(".graph-fit")?.addEventListener("click", fit, { signal });
  area.querySelector(".graph-find")?.addEventListener("input", (event) => { find = event.target.value.trim().toLowerCase(); renderer.refresh(); }, { signal });

  // A line under the mouse: its two ends and how many relations of each kind it stands for.
  let mouse = [0, 0];
  document.addEventListener("mousemove", (e) => { mouse = [e.clientX, e.clientY]; }, { signal });
  renderer.on("enterEdge", ({ edge }) => {
    const k = graph.getEdgeAttribute(edge, "kinds"); if (!k || k.contains || !tooltip) return;
    const bounds = area.getBoundingClientRect();
    const ratios = graph.getEdgeAttribute(edge, "ratios") ?? [], pct = (r) => `${Math.round(r * 1000) / 10}%`;
    const share = !ratios.length ? "" : ratios.length === 1 ? ` (${pct(ratios[0])} of the values)` : ` (${pct(Math.min(...ratios))} to ${pct(Math.max(...ratios))} of the values)`;
    tooltip.innerHTML = `<span>${esc(byId.get(graph.source(edge)).label)} — ${esc(byId.get(graph.target(edge)).label)}</span><span>${Object.entries(k).map(([kind, n]) => `${n} ${esc(kind)}`).join(" · ")}${share}</span>`;
    tooltip.style.left = `${mouse[0] - bounds.left + 12}px`; tooltip.style.top = `${mouse[1] - bounds.top + 12}px`; tooltip.hidden = false;
  });
  renderer.on("leaveEdge", () => { if (tooltip) tooltip.hidden = true; });

  // Hovering a node: its neighbours stand out, and a tall box by its badge lists what it is, with Details.
  let boxNode = null, boxTimer = null;
  const hideBox = () => { boxTimer = setTimeout(() => { hoverBox.hidden = true; boxNode = null; }, 300); };
  hoverBox.addEventListener("mouseenter", () => clearTimeout(boxTimer), { signal });
  hoverBox.addEventListener("mouseleave", hideBox, { signal });
  hoverBox.querySelector(".universe-hover-details").addEventListener("click", () => { if (boxNode) details(boxNode); hoverBox.hidden = true; }, { signal });
  function enter(node) {
    hovered = node; near = new Set(graph.neighbors(node)); renderer.refresh();
    clearTimeout(boxTimer); boxNode = node;
    const [l, t, w] = rects.get(node) ?? [0, 0, 0], at = canvas.getBoundingClientRect(), outer = box.getBoundingClientRect();
    hoverBox.querySelector(".universe-hover-body").innerHTML = characteristics(node);
    hoverBox.style.left = `${at.left - outer.left + l + w + 6}px`; hoverBox.style.top = `${at.top - outer.top + t}px`; hoverBox.hidden = false;
  }
  function leave() { hovered = null; near = new Set(); renderer.refresh(); hideBox(); }
  const symbol = (m) => `<img src="${universeIcon(m, UNIVERSE_COLORS.column).src}" alt="">`;
  const row = (icon, text) => `<div class="universe-row">${icon}<span>${esc(text)}</span></div>`;
  // A node's characteristics, one under the other: name, kind and place; a column's type and symbols (a
  // foreign key with the column it points to); others what they hold and their relations by kind.
  function characteristics(id) {
    const n = byId.get(id);
    let rows = `<b>${esc(n.label)}</b><div class="universe-where">${esc(n.subkind || n.kind)} · ${esc(chain(id).slice(0, -1).map((x) => byId.get(x).label).join(" › "))}</div>`;
    if (n.kind === "column") {
      if (n.type) rows += row("", n.type);
      for (const m of universeMarks(n.flags)) {
        const to = m === "fk" ? relations.filter((e) => e.kind === "foreign key" && e.source === id).map((e) => chain(e.target).slice(2).map((x) => byId.get(x).label).join(".")) : [];
        rows += row(symbol(m), UNIVERSE_SYMBOLS[m][1] + (to.length ? ` → ${to.join(", ")}` : ""));
      }
    } else {
      const counts = {};
      for (const k of children.get(id) ?? []) counts[byId.get(k).kind] = (counts[byId.get(k).kind] ?? 0) + 1;
      for (const [k, c] of Object.entries(counts)) rows += row("", `${c} ${k}${c > 1 ? "s" : ""}`);
      const mine = (end) => up(end, UNIVERSE_LEVEL[n.kind]) === id, rel = {};
      for (const e of relations) if (mine(e.source) !== mine(e.target)) rel[e.kind] = (rel[e.kind] ?? 0) + 1;
      for (const [k, c] of Object.entries(rel)) rows += row(`<i style="border-color:${UNIVERSE_LINKS[k]}"></i>`, `${c} ${k}`);
    }
    if (n.comment) rows += `<div class="universe-comment">${esc(n.comment)}</div>`;
    return rows;
  }
  const captor = renderer.getMouseCaptor();
  captor.on("mousemovebody", (e) => {
    if (!dragged) { const node = hit(e.x, e.y); if (node !== hovered) { if (hovered) leave(); if (node) enter(node); } canvas.style.cursor = node ? "pointer" : ""; return; }
    const p = renderer.viewportToGraph(e);
    graph.mergeNodeAttributes(dragged, { x: p.x, y: p.y }); moved = true; move(30);
    e.preventSigmaDefault(); e.original.preventDefault(); e.original.stopPropagation();
  });
  captor.on("mousedown", (e) => { const node = hit(e.x, e.y); if (!node) return; dragged = node; moved = false; graph.setNodeAttribute(node, "fixed", true); e.preventSigmaDefault(); });
  captor.on("mouseup", () => { if (!dragged) return; graph.removeNodeAttribute(dragged, "fixed"); dragged = null; move(60); });

  // One click goes into the node (its place in the tree becomes the path); a second click on it within
  // half a second opens its details instead (counted here: sigma's own double click window is shorter
  // than a person's double click).
  let pending = null, pendingNode = null;
  captor.on("click", (e) => {
    const node = hit(e.x, e.y);
    if (!node || moved) return;
    clearTimeout(pending);
    if (pendingNode === node) { pendingNode = null; details(node); return; }
    pendingNode = node;
    pending = setTimeout(() => {
      pendingNode = null; hovered = null; near = new Set(); hoverBox.hidden = true;
      const target = level(node) === 4 ? byId.get(node).parent : node;
      if (target !== path.at(-1)) show(chain(target));
    }, 500);
  });
  for (const event of ["doubleClickNode", "doubleClickStage", "doubleClickEdge"]) renderer.on(event, (e) => e.preventSigmaDefault());

  // The node's details, in the drawing's Details panel: where it sits, what it holds, its relations by kind.
  function details(id) {
    if (!info) return;
    const n = byId.get(id);
    const mine = (end) => up(end, UNIVERSE_LEVEL[n.kind]) === id, short = (x) => chain(x).slice(1).map((y) => byId.get(y).label).join(".");
    const out = {}, inn = {};
    for (const e of relations) {
      if (mine(e.source) && !mine(e.target)) (out[e.kind] ??= []).push(e);
      if (mine(e.target) && !mine(e.source)) (inn[e.kind] ??= []).push(e);
    }
    const group = (list, arrow) => Object.entries(list).map(([kind, items]) => `<h4><i class="universe-line" style="border-color:${UNIVERSE_LINKS[kind]}"></i>${esc(kind)} ${arrow} <span class="count">${items.length}</span></h4>
      <ul>${items.slice(0, 50).map((e) => `<li>${esc(`${short(e.source)} → ${short(e.target)}`)}</li>`).join("")}${items.length > 50 ? `<li>… ${items.length - 50} more</li>` : ""}</ul>`).join("");
    const kids = children.get(id) ?? [], counts = {};
    for (const k of kids) counts[byId.get(k).kind] = (counts[byId.get(k).kind] ?? 0) + 1;
    const holds = n.kind === "table" || n.kind === "view"
      ? `<h4>Columns <span class="count">${kids.length}</span></h4><ul>${kids.map((c) => `<li>${esc(byId.get(c).label)} <span class="universe-type">${esc(byId.get(c).type ?? "")}</span> ${universeMarks(byId.get(c).flags).map(symbol).join("")}</li>`).join("")}</ul>`
      : kids.length ? `<p>${Object.entries(counts).map(([k, c]) => `${c} ${k}${c > 1 ? "s" : ""}`).join(" · ")}</p>` : "";
    info.innerHTML = `<p class="graph-info-role">${esc(n.subkind || n.kind)}</p><h3 class="graph-details-name">${esc(n.label)}</h3>
      <code class="path">${esc(chain(id).map((x) => byId.get(x).label).join(" › "))}</code>
      ${n.comment ? `<p>${esc(n.comment)}</p>` : ""}
      ${n.kind === "column" ? `<p>${esc(n.type ?? "")} ${universeMarks(n.flags).map((m) => `${symbol(m)} ${esc(UNIVERSE_SYMBOLS[m][1])}`).join(" · ")}</p>` : ""}
      ${holds}${group(out, "→")}${group(inn, "←")}`;
    if (pageButton) { pageButton.hidden = false; pageButton.dataset.pageModal = id; }
    openSidePanel(area);
  }
}

// DATABASE › Evolution: one lane per origin, its moments from left (oldest) to right, each in its own
// column of time over every lane. A migration step is a filled dot, joined to the step it revises (two
// steps revising the same one open a branch, a row of its own; a step revising two is the merge); a commit
// is a hollow dot, a red ring a step changed after it was created, a dashed one what is not committed. A
// click shows the moment in Details; with the Diff row open, the first click chooses A and the second B.
const EVO = { left: 290, step: 34, row: 22, pad: 18, top: 16 };

async function drawEvolution(canvas) {
  const data = await (await fetch(canvas.dataset.url)).json();
  const area = canvas.closest(".graph-area"), page = canvas.closest(".graph-page");
  page.evolutionListeners?.abort();
  page.evolutionListeners = new AbortController();
  const signal = page.evolutionListeners.signal;
  fillLegend(canvas);
  const originBox = page.querySelector(".evo-origins");
  const form = page.querySelector(".evo-diff-form");
  const pick = { a: form?.querySelector(".evo-a"), b: form?.querySelector(".evo-b") };
  let next = "a";  // which of A and B a click on a moment chooses
  const draw = () => {
    const chosen = new Set([...(originBox?.querySelectorAll("input:checked") || [])].map((input) => input.value));
    const label = originBox?.querySelector(".evo-origins-text");
    if (label) label.textContent = !chosen.size ? "All origins" : chosen.size === 1 ? [...chosen][0] : `${chosen.size} origins`;
    const lanes = data.lanes.filter((lane) => !chosen.size || chosen.has(lane.origin));
    const shown = new Set(lanes.map((lane) => lane.origin));
    const moments = data.moments.filter((moment) => shown.has(moment.origin));
    if (!moments.length) {
      canvas.innerHTML = '<p class="empty">No moment here.</p>';
      return;
    }
    const column = Object.fromEntries(moments.map((moment, index) => [moment.id, index]));
    const spots = {}, parts = [], labels = [];
    let y = EVO.top;
    lanes.forEach((lane, laneIndex) => {
      const colour = LANE_COLORS[laneIndex % LANE_COLORS.length];
      const own = moments.filter((moment) => moment.origin === lane.origin);
      // Rows of a migration lane: a step stays on its parent's row unless a sibling took it (a branch).
      const rowOf = {}, taken = {};
      let rows = 1;
      for (const moment of own) {
        if (moment.source !== "migration") { rowOf[moment.id] = 0; continue; }
        const parents = (moment.revises || []).map((version) => `${lane.origin}@step:${version}`).filter((id) => id in rowOf);
        let row = parents.length ? Math.min(...parents.map((id) => rowOf[id])) : 0;
        if (parents.length === 1 && taken[parents[0]]) row = rows++;
        if (parents.length === 1) taken[parents[0]] = true;
        rowOf[moment.id] = row;
      }
      const height = EVO.pad + rows * EVO.row;
      labels.push(`<g class="evo-lane" style="--lane:${colour}"><rect x="0" y="${y - EVO.pad / 2}" width="100%" height="${height}" class="evo-lane-band"/>
        <text x="10" y="${y + 12}" class="evo-lane-name"><title>${escapeHtml(lane.origin)}</title>${escapeHtml(lane.origin.split("/").slice(-2).join("/"))}</text>
        <text x="10" y="${y + 26}" class="evo-lane-kind">${escapeHtml(lane.kind)}</text></g>`);
      for (const moment of own) {
        spots[moment.id] = { x: EVO.left + column[moment.id] * EVO.step, y: y + 8 + rowOf[moment.id] * EVO.row, colour };
      }
      // The lines: a step to the steps it revises; a lane of commits, each to the one before.
      let before = null;
      for (const moment of own) {
        const here = spots[moment.id];
        const from = moment.source === "migration" ? (moment.revises || []).map((version) => spots[`${lane.origin}@step:${version}`]).filter(Boolean)
          : (before ? [spots[before.id]] : []);
        for (const there of from) {
          const middle = (there.x + here.x) / 2;
          parts.push(`<path class="evo-link" style="--lane:${colour}" d="M ${there.x} ${there.y} C ${middle} ${there.y}, ${middle} ${here.y}, ${here.x} ${here.y}"/>`);
        }
        if (moment.source !== "migration") before = moment;
      }
      y += height;
    });
    const dots = moments.map((moment) => {
      const { x, y: top, colour } = spots[moment.id];
      const kind = moment.commit ? (moment.changed?.length ? "changed" : moment.source === "migration" ? "migration" : "commit") : "now";
      const tip = `${moment.origin}\n${moment.source === "migration" ? `step ${moment.version} ${moment.title}` : moment.title}`
        + `\n${moment.commit ? `${moment.commit.short} · ${moment.commit.at.slice(0, 10)}` : "not committed"}`;
      return `<g class="evo-moment evo-${kind}" data-moment="${escapeHtml(moment.id)}" style="--lane:${colour}">
        <circle cx="${x}" cy="${top}" r="6"/><text class="evo-pick" x="${x}" y="${top - 10}"></text><title>${escapeHtml(tip)}</title></g>`;
    });
    const width = EVO.left + moments.length * EVO.step + EVO.pad;
    canvas.innerHTML = `<svg class="evo-svg" width="${width}" height="${y + EVO.pad}">${labels.join("")}${parts.join("")}${dots.join("")}</svg>`;
    marks();
  };
  // A and B, shown on their moments.
  const marks = () => {
    for (const element of canvas.querySelectorAll(".evo-moment")) {
      const id = element.dataset.moment;
      const letter = pick.a?.value === id ? "A" : pick.b?.value === id ? "B" : "";
      element.classList.toggle("evo-picked", Boolean(letter));
      element.querySelector(".evo-pick").textContent = letter;
    }
  };
  draw();
  originBox?.addEventListener("change", (event) => { if (event.target === originBox) draw(); }, { signal });
  for (const select of Object.values(pick)) select?.addEventListener("change", marks, { signal });
  canvas.addEventListener("click", (event) => {
    const id = event.target.closest("[data-moment]")?.dataset.moment;
    if (!id) return;
    const diffOpen = form && !form.closest("[data-row-of]").classList.contains("closed");
    if (diffOpen) {
      pick[next].value = id;
      pick[next].dispatchEvent(new Event("change", { bubbles: true }));
      next = next === "a" ? "b" : "a";
      return;
    }
    const details = area.querySelector(".graph-details");
    if (!details) return;
    htmx.ajax("GET", `/database/evolution?moment=${encodeURIComponent(id)}`, { target: details });
    openSidePanel(area);
  }, { signal });
}

function initViews() {
  for (const canvas of document.querySelectorAll(".graph-canvas")) {
    if (canvas.dataset.ready || !canvas.dataset.url) continue;  // no url: nothing chosen yet
    if (canvas.dataset.view === "universe") { canvas.dataset.ready = "1"; drawUniverse(canvas); continue; }
    if (canvas.dataset.view === "evolution") { canvas.dataset.ready = "1"; drawEvolution(canvas); continue; }
    if (!DIAGRAMS[canvas.dataset.view]) continue;
    canvas.dataset.ready = "1";
    drawDiagram(canvas, DIAGRAMS[canvas.dataset.view]);
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
  const tooltip = canvas.closest(".graph-area").querySelector(".graph-tooltip");
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
    const area = canvas.closest(".graph-area").getBoundingClientRect();
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
