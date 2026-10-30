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
    if (d.method === "Runtime.consoleAPICalled") log.push(d.params.type + " " + d.params.args.map((a) => a.value ?? a.description).join(" ").slice(0, 200));
    if (d.method === "Log.entryAdded") log.push("LOG " + d.params.entry.level + " " + d.params.entry.text.slice(0, 200) + " " + (d.params.entry.url || ""));
    if (waiting[d.id]) { waiting[d.id](d.result); delete waiting[d.id]; } };
  const send = (method, params = {}) => new Promise((r) => { waiting[++id] = r; ws.send(JSON.stringify({ id, method, params })); });
  await send("Runtime.enable"); await send("Log.enable");
  await send("Page.navigate", { url });
  await sleep(+process.env.WAIT || 15000);
  const r = await send("Runtime.evaluate", { expression: "document.getElementById('stats').textContent + ' | canvases: ' + document.querySelectorAll('canvas').length", returnByValue: true });
  console.log("STATE:", r.result?.value); console.log(log.slice(0, 12).join("\n"));
  const shot = await send("Page.captureScreenshot", { format: "png" });
  require("fs").writeFileSync(dir + ".png", Buffer.from(shot.data, "base64"));
  ws.close(); chrome.kill();
})().catch((e) => { console.log("ERR", e.message); chrome.kill(); });
