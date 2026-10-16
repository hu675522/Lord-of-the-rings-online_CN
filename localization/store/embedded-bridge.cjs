/* Local CEF bridge prototype. No game files or cookies are read/written; no
 * session URLs or account/price values are logged. Only the local store page receives the
 * bundled wording script. Requires Node 22+; not installed automatically. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function allowedStore(value) {
  try { const u = new URL(value); return u.protocol === 'https:' && u.hostname === 'store.lotro.com' &&
    !u.username && !u.password && (!u.port || u.port === '443'); } catch { return false; }
}
function debuggerUrl(value, port) {
  const u = new URL(value);
  if (u.protocol !== 'ws:' || !['127.0.0.1', 'localhost', '[::1]'].includes(u.hostname) ||
      Number(u.port) !== port || u.username || u.password || u.search || u.hash ||
      !/^\/devtools\/page\/[A-Za-z0-9_-]+$/.test(u.pathname)) throw new Error('Invalid debugger endpoint');
  u.hostname = '127.0.0.1'; return u.href;
}
function validateOwners(owners, game) {
  if (!Array.isArray(owners)) owners = [owners];
  const expected = ['lotroclient.exe', 'x64/lotroclient64.exe'].map(p => path.win32.resolve(game,p).toLowerCase());
  return owners.length > 0 && owners.every(o => ['127.0.0.1', '::1'].includes(o.LocalAddress) &&
    typeof o.Executable === 'string' && expected.includes(path.win32.resolve(o.Executable).toLowerCase()));
}
function checkOwner(port, game) {
  // Only the validated integer port is interpolated into this fixed command.
  const script = `$ErrorActionPreference='Stop'; @(Get-NetTCPConnection -State Listen -LocalPort ${port} | ForEach-Object { $p=Get-Process -Id $_.OwningProcess; [pscustomobject]@{LocalAddress=$_.LocalAddress;Executable=$p.Path} }) | ConvertTo-Json -Compress`;
  const result = execFileSync('powershell.exe', ['-NoProfile','-NonInteractive','-Command',script], {encoding:'utf8',windowsHide:true,timeout:10000,stdio:['ignore','pipe','ignore']});
  if (!validateOwners(JSON.parse(result),game)) throw new Error('Endpoint does not belong to loopback-only game browser');
}
async function listPages(port) {
  const response = await fetch(`http://127.0.0.1:${port}/json/list`, {redirect:'error', signal:AbortSignal.timeout(3000)});
  if (!response.ok) throw new Error('Debugger list unavailable');
  const text = await response.text(); if (text.length > 1024*1024) throw new Error('Diagnostic response too large');
  const pages = JSON.parse(text); if (!Array.isArray(pages)) throw new Error('Invalid target list');
  return pages.filter(p => p.type === 'page' && allowedStore(p.url));
}
function inject(url, source) {
  return new Promise((resolve,reject) => {
    const ws = new WebSocket(url); const timer = setTimeout(() => finish(new Error('Debugger timeout')),5000);
    function finish(error,value) { clearTimeout(timer); ws.close(); error ? reject(error) : resolve(value); }
    ws.addEventListener('error', () => finish(new Error('Debugger connection failed')));
    ws.addEventListener('open', () => ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{
      expression:source+'\n; Boolean(globalThis.__LOTRO_ZH_STORE__?.active)',returnByValue:true}})));
    ws.addEventListener('message', event => {
      try { const reply=JSON.parse(event.data); if(reply.id!==1)return;
        if(reply.error || reply.result?.exceptionDetails) return finish(new Error('Translation script failed'));
        finish(null,reply.result?.result?.value === true);
      } catch { finish(new Error('Invalid debugger reply')); }
    });
  });
}
async function once(port,game,source) {
  if (!Number.isInteger(port) || port<1024 || port>65535) throw new Error('Invalid local port');
  checkOwner(port,game);
  const pages = await listPages(port); let active=0;
  for(const page of pages) if(await inject(debuggerUrl(page.webSocketDebuggerUrl,port),source)) active++;
  return {store_pages:pages.length,active_translation_pages:active};
}
async function main() {
  const args=process.argv.slice(2); const portAt=args.indexOf('--port');
  const port=portAt<0 ? 19222 : Number(args[portAt+1]);
  const at=args.indexOf('--game-dir'); if(at<0 || !args[at+1]) throw new Error('--game-dir is required');
  const game=args[at+1]; const source=fs.readFileSync(path.join(__dirname,'store-zh.user.js'),'utf8');
  let last='';
  do {
    let message;
    try {message=JSON.stringify(await once(port,game,source));}
    catch {message='尚未接入已核验的游戏商城页面；未执行翻译。';}
    if(message!==last){console.log(message);last=message;}
    if(args.includes('--once'))break;
    await new Promise(resolve=>setTimeout(resolve,5000));
  } while(true);
}
module.exports={allowedStore,debuggerUrl,validateOwners};
if(require.main===module) main().catch(()=>{console.error('商城桥接启动失败；没有修改游戏。');process.exitCode=1;});
