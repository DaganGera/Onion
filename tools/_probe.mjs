const t = (await (await fetch('http://localhost:9333/json/list')).json()).find((x) => x.type === 'page');
const ws = new WebSocket(t.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0;
const p = new Map();
const logs = [];
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (p.has(m.id)) { p.get(m.id)(m); p.delete(m.id); }
  if (m.method === 'Runtime.consoleAPICalled') logs.push(m.params.type + ': ' + m.params.args.map((a) => a.value ?? a.description).join(' ').slice(0, 300));
  if (m.method === 'Runtime.exceptionThrown') logs.push('EXC: ' + JSON.stringify(m.params.exceptionDetails).slice(0, 800));
});
const call = (method, params) => new Promise((res) => { const i = ++id; p.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
await call('Runtime.enable', {});
const r = await call('Runtime.evaluate', { awaitPromise: true, returnByValue: true, expression: `(async () => {
  await new Promise((r) => setTimeout(r, 3000));
  return location.hash + ' | receipt=' + !!document.querySelector('.receipt') + ' | ' + (document.querySelector('main')?.innerText ?? document.body.innerText).slice(0, 300);
})()` });
console.log(JSON.stringify(r.result?.result?.value ?? r.result));
console.log(logs.join('\n'));
ws.close();
