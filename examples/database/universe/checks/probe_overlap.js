// Counts badges overlapping each other (screen rectangles) in a few views.
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
  const count = `(() => { const r = [...window.universe.rects].map(([id, [x, y, w, h]]) => [id.split(/[./]/).pop(), x, y, w, h]);
    const bad = []; for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) { const [n1, x1, y1, w1, h1] = r[i], [n2, x2, y2, w2, h2] = r[j]; if (x1 < x2 + w2 && x2 < x1 + w1 && y1 < y2 + h2 && y2 < y1 + h1) bad.push(n1 + '/' + n2); }
    return r.length + ' badges, ' + bad.length + ' overlapping ' + bad.slice(0, 6).join(' ') + ' | smallest font scale ' + (r.length ? Math.min(...r.map((q) => q[4])).toFixed(0) + 'px tall' : ''); })()`;
  await send("Runtime.enable"); await send("Page.navigate", { url }); await sleep(5000);
  if (process.argv[6]) { await ev(`(() => { const el = document.getElementById('others'); el.checked = true; el.dispatchEvent(new Event('change')); })()`); await sleep(500); }
  for (const view of JSON.parse(process.argv[5] || "[]")) {
    await ev(`window.universe.show(window.universe.chain(${JSON.stringify(view)}))`); await sleep(700);
    console.log(view.padEnd(40), await ev(count));
  }
  console.log(log.join("\n"));
  ws.close(); chrome.kill();
})().catch((e) => { console.log("ERR", e.message); chrome.kill(); });
