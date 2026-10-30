// The universe's colours, link kinds and forces.
import forceAtlas2 from "https://esm.sh/graphology-layout-forceatlas2@0.10.1";

export const COLORS = { server: "#24292f", database: "#bc4c00", schema: "#8250df", table: "#0969da", view: "#1a7f37", column: "#6e7781" };
export const LINKS = { contains: "#d8dee4", "foreign key": "#cf222e", implied: "#bf8700", "view reads": "#1a7f37", "foreign table": "#1b7c83" };

// The same forces for the first layout and for the live movement (slower, so it moves gently); strong
// gravity keeps nodes without links near the others instead of drifting away.
export const forces = (graph, slowDown = 1) => ({ ...forceAtlas2.inferSettings(graph), barnesHutOptimize: true, strongGravityMode: true, gravity: 0.3, scalingRatio: 40, edgeWeightInfluence: 1, linLogMode: true, outboundAttractionDistribution: true, slowDown });
export { forceAtlas2 };

// ForceAtlas2 pushes two nodes apart by the product of their masses (1 + the weight of their links); a
// link from a node to itself adds mass without pulling anything, so schemas and tables push harder.
export const MASS = { server: 40, database: 40, schema: 40, table: 5, view: 2 };
