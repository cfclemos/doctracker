// Walks server → database → schema → table (the first step by a real click) and prints each view.
const { spawn } = require("child_process");
const [url, dir, port] = process.argv.slice(2);
const chrome = spawn("chromium", ["--headless=new", "--no-sandbox", `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`,
  "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1400,900", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  let target;
  for (let i = 0; i < 40 && !target; i++) { await sleep(250); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {} }
  const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
  let id = 0; const waiting = {}; const log = [];
  ws.onmessage = (m) => { const d = JSON.parse(m.data);
    if (d.method === "Runtime.exceptionThrown") log.push("EXCEPTION " + (d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text).split("\n").slice(0, 3).join(" | "));
    if (waiting[d.id]) { waiting[d.id](d.result); delete waiting[d.id]; } };
  const send = (method, params = {}) => new Promise((r) => { waiting[++id] = r; ws.send(JSON.stringify({ id, method, params })); });
  const ev = async (e) => (await send("Runtime.evaluate", { expression: e, returnByValue: true })).result?.value;
  const state = async (name) => { console.log(name.padEnd(12), await ev("document.getElementById('crumbs').textContent + ' | ' + document.getElementById('stats').textContent + ' | ' + window.universe.graph.nodes().map((n) => window.universe.graph.getNodeAttribute(n, 'label')).slice(0, 12).join(', ')"));
    const s = await send("Page.captureScreenshot", { format: "png" }); require("fs").writeFileSync(`${dir}-${name}.png`, Buffer.from(s.data, "base64")); };
  const go = (node) => ev(`window.universe.show(window.universe.chain(${JSON.stringify(node)}))`);
  const tick = (sel, on) => ev(`(() => { const el = document.querySelector('${sel}'); el.checked = ${on}; el.dispatchEvent(new Event('change')); })()`);
  await send("Runtime.enable"); await send("Page.navigate", { url }); await sleep(5000);
  await state("1-universe");
  const [x, y] = JSON.parse(await ev(`(() => { const {renderer, graph} = window.universe; const p = renderer.graphToViewport(graph.getNodeAttributes('postgres')); const r = document.getElementById('stage').getBoundingClientRect(); return JSON.stringify([p.x + r.left, p.y + r.top]); })()`));
  for (const type of ["mouseMoved", "mousePressed", "mouseReleased"]) await send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
  await sleep(1200); await state("2-server");
  await go("postgres/acme"); await sleep(800); await state("3-database");
  await tick('[data-kind="foreign table"]', true); await sleep(800); await state("3b-ftable");
  await go("postgres/acme/sales"); await sleep(800); await state("4-schema");
  await tick("#others", true); await sleep(800); await state("4b-others");
  await go("postgres/acme/sales.orders"); await sleep(800); await state("5-table");
  const [hx, hy] = JSON.parse(await ev(`(() => { const {renderer, graph} = window.universe; const p = renderer.graphToViewport(graph.getNodeAttributes('postgres/acme/sales.orders.customer_id')); const r = document.getElementById('stage').getBoundingClientRect(); return JSON.stringify([p.x + r.left, p.y + r.top]); })()`));
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: hx, y: hy }); await sleep(500); await state("6-hover");
  console.log(log.join("\n"));
  ws.close(); chrome.kill();
})().catch((e) => { console.log("ERR", e.message); chrome.kill(); });
