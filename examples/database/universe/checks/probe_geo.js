const { spawn } = require("child_process");
const [url, dir, port, view] = process.argv.slice(2);
const chrome = spawn("chromium", ["--headless=new", "--no-sandbox", `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--window-size=1400,900", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
(async () => {
  let target; for (let i = 0; i < 40 && !target; i++) { await sleep(250); try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch {} }
  const ws = new WebSocket(target.webSocketDebuggerUrl); await new Promise((r) => (ws.onopen = r));
  let id = 0; const waiting = {}; ws.onmessage = (m) => { const d = JSON.parse(m.data); if (waiting[d.id]) { waiting[d.id](d.result); delete waiting[d.id]; } };
  const send = (method, params = {}) => new Promise((r) => { waiting[++id] = r; ws.send(JSON.stringify({ id, method, params })); });
  const ev = async (e) => (await send("Runtime.evaluate", { expression: e, returnByValue: true })).result?.value;
  await send("Runtime.enable"); await send("Page.navigate", { url }); await sleep(5000);
  await ev(`(() => { const el = document.getElementById('others'); el.checked = true; el.dispatchEvent(new Event('change')); })()`); await sleep(300);
  await ev(`window.universe.show(window.universe.chain(${JSON.stringify(view)}))`); await sleep(700);
  console.log(await ev(`(() => { const u = window.universe, xs = [], ys = [], ids = []; u.graph.forEachNode((id, a) => { xs.push(a.x); ys.push(a.y); ids.push(id.split(/[./]/).pop() + '@' + a.x.toFixed(0) + ',' + a.y.toFixed(0)); });
    const a = u.renderer.graphToViewport({x:0,y:0}), b = u.renderer.graphToViewport({x:u.base,y:0});
    return JSON.stringify({ base: u.base, ext: [Math.max(...xs)-Math.min(...xs), Math.max(...ys)-Math.min(...ys)], px: b.x - a.x, nodes: ids }); })()`));
  const s = await send("Page.captureScreenshot", { format: "png" }); require("fs").writeFileSync(`${dir}.png`, Buffer.from(s.data, "base64"));
  ws.close(); chrome.kill();
})();
