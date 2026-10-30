// Schema and table views under each Depth, with and without other schemas; prints what is drawn.
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
  const shot = async (name) => { const s = await send("Page.captureScreenshot", { format: "png" }); require("fs").writeFileSync(`${dir}-${name}.png`, Buffer.from(s.data, "base64")); };
  const set = (sel, js) => ev(`(() => { const el = document.querySelector('${sel}'); ${js}; el.dispatchEvent(new Event('change')); })()`);
  await send("Runtime.enable"); await send("Page.navigate", { url }); await sleep(5000);
  for (const view of [["area_00"], ["area_00", "area_00.entity_0000"]]) {
    await ev(`window.universe.show(${JSON.stringify(view)})`); await sleep(500);
    for (const others of [false, true]) for (const d of [1, 2, 3]) {
      await set("#others", `el.checked = ${others}`); await set("#depth", `el.value = '${d}'`); await sleep(500);
      const st = await ev("document.getElementById('crumbs').textContent + ' | ' + document.getElementById('stats').textContent");
      console.log(`others=${others} depth=${d}  ${st}`);
      if (d === 2) await shot(`${view.length}-${others}`);
    }
  }
  console.log(log.join("\n"));
  ws.close(); chrome.kill();
})().catch((e) => { console.log("ERR", e.message); chrome.kill(); });
