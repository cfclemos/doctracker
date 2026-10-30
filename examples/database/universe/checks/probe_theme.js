// Toggles the themes by clicking their checkboxes and prints what is drawn after each.
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
  const st = () => ev("document.getElementById('crumbs').textContent + ' | ' + document.getElementById('stats').textContent + ' | kinds: ' + JSON.stringify([...new Set(window.universe.graph.edges().map((e) => window.universe.graph.getEdgeAttribute(e, 'kind')))])");
  await send("Runtime.enable"); await send("Page.navigate", { url }); await sleep(5000);
  console.log("start      ", await st());
  for (const k of ["implied", "view reads", "foreign key"]) { await ev(`document.querySelector('[data-kind="${k}"]').click()`); await sleep(800); console.log("toggle " + k.padEnd(11), await st()); if (k === "implied") { const s = await send("Page.captureScreenshot", { format: "png" }); require("fs").writeFileSync(dir + "-both.png", Buffer.from(s.data, "base64")); } }
  await ev("window.universe.show(['area_00'])"); await sleep(800); console.log("schema     ", await st());
  await ev(`document.querySelector('[data-kind="implied"]').click()`); await sleep(800); console.log("-implied   ", await st());
  console.log(log.join("\n"));
  ws.close(); chrome.kill();
})().catch((e) => { console.log("ERR", e.message); chrome.kill(); });
