// Double-clicks a schema in the universe: the view must stay and the details must open.
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
  const at = async (node) => JSON.parse(await ev(`(() => { const {renderer, graph} = window.universe; const p = renderer.graphToViewport(graph.getNodeAttributes(${JSON.stringify(node)})); const r = document.getElementById('stage').getBoundingClientRect(); return JSON.stringify([p.x + r.left, p.y + r.top]); })()`));
  const press = async (x, y, n) => { await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", clickCount: n }); await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", clickCount: n }); };
  await send("Runtime.enable"); await send("Page.navigate", { url }); await sleep(5000);
  const [x, y] = await at("area_00");
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await press(x, y, 1); await sleep(380); await press(x, y, 2); await sleep(800);
  console.log("double:", await ev("document.getElementById('crumbs').textContent + ' | details hidden=' + document.getElementById('details').hidden + ' | ' + document.getElementById('details-body').innerText.slice(0, 160).replace(/\\n/g, ' / ')"));
  const s = await send("Page.captureScreenshot", { format: "png" }); require("fs").writeFileSync(`${dir}.png`, Buffer.from(s.data, "base64"));
  await ev("document.getElementById('details').hidden = true");
  const [hx, hy] = await at("area_01"); await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: hx, y: hy }); await sleep(300);
  console.log("hover box:", await ev("document.getElementById('hoverbox').hidden + ' ' + document.getElementById('hoverbox').textContent"));
  await ev("document.getElementById('hover-details').click()"); await sleep(300);
  console.log("box button:", await ev("document.getElementById('details').hidden + ' ' + document.querySelector('#details h2').textContent"));
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y }); await sleep(100);
  await press(x, y, 1); await sleep(900);
  console.log("single:", await ev("document.getElementById('crumbs').textContent"));
  console.log(log.join("\n"));
  ws.close(); chrome.kill();
})().catch((e) => { console.log("ERR", e.message); chrome.kill(); });
