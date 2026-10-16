const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {allowedStore,debuggerUrl,validateOwners}=require('../localization/store/embedded-bridge.cjs');
const {translate}=require('../localization/store/store-zh.user.js');

test('accepts only HTTPS official store targets and the same local debugger port',()=>{
  assert.equal(allowedStore('https://store.lotro.com/session?private=token'),true);
  for(const value of ['http://store.lotro.com/','https://store.lotro.com.evil.invalid/','https://pay.example/','https://user@store.lotro.com/'])assert.equal(allowedStore(value),false);
  assert.equal(debuggerUrl('ws://localhost:19222/devtools/page/ABC123',19222),'ws://127.0.0.1:19222/devtools/page/ABC123');
  for(const value of ['ws://remote.example:19222/devtools/page/ABC','ws://127.0.0.1:19223/devtools/page/ABC','ws://127.0.0.1:19222/devtools/page/ABC?token=secret'])assert.throws(()=>debuggerUrl(value,19222));
});
test('rejects wildcard listeners and another application on the local port',()=>{
  const game='D:\\Games\\LOTRO';
  assert.equal(validateOwners([{LocalAddress:'127.0.0.1',Executable:game+'\\x64\\lotroclient64.exe'}],game),true);
  assert.equal(validateOwners([{LocalAddress:'0.0.0.0',Executable:game+'\\x64\\lotroclient64.exe'}],game),false);
  assert.equal(validateOwners([{LocalAddress:'127.0.0.1',Executable:'C:\\Chrome\\chrome.exe'}],game),false);
});
test('new screenshot labels translate while prices and input text remain literal',()=>{
  assert.equal(translate('Apprentice Riding Trait (Account)'),'初级骑术特性（账号）');
  assert.equal(translate('30% off Shared Wardrobe & More!'),'共享衣橱等商品优惠 30%！');
  for(const value of ['1,397','2,097','109','hu675522','UNKNOWN_PRODUCT'])assert.equal(translate(value),value);
});
test('DOM translation preserves values, URLs and handlers across repeated injection and updates',()=>{
  const texts=[]; const elements=[];
  function element(tag,blocked=false,attrs={}) { const e={nodeType:1,tagName:tag,attrs:{...attrs},value:'PRIVATE_INPUT',onclick:()=>42,
    closest:()=>blocked ? {} : null,getAttribute(k){return this.attrs[k]??null},setAttribute(k,v){this.attrs[k]=v},
    querySelectorAll(){return elements.filter(x=>x!==this)}}; elements.push(e);return e; }
  const body=element('BODY');const link=element('A',false,{href:'https://store.lotro.com/private?token=KEEP'});
  const input=element('INPUT',true,{placeholder:'Search'});
  function text(value,parent=body){const t={nodeType:3,nodeValue:value,parentElement:parent};texts.push(t);return t;}
  const title=text('Specials');const price=text('1,397');const username=text('hu675522');const field=text('Search',input);
  let callback;let observers=0;
  const context={location:{protocol:'https:',hostname:'store.lotro.com'},window:{},Node:{TEXT_NODE:3,ELEMENT_NODE:1},NodeFilter:{SHOW_TEXT:4},
    document:{body,createTreeWalker(){let i=0;return {nextNode:()=>texts[i++]||null}}},
    MutationObserver:class{constructor(cb){callback=cb;observers++}observe(){}disconnect(){}}};
  const script=fs.readFileSync(require.resolve('../localization/store/store-zh.user.js'),'utf8');
  const click=link.onclick; vm.runInNewContext(script,context);vm.runInNewContext(script,context);
  assert.equal(title.nodeValue,'精选优惠');assert.equal(price.nodeValue,'1,397');assert.equal(username.nodeValue,'hu675522');
  assert.equal(input.value,'PRIVATE_INPUT');assert.equal(field.nodeValue,'Search');assert.equal(input.attrs.placeholder,'搜索');
  assert.equal(link.attrs.href,'https://store.lotro.com/private?token=KEEP');assert.equal(link.onclick,click);assert.equal(observers,1);
  input.attrs.placeholder='Search';callback([{type:'attributes',target:input}]);assert.equal(input.attrs.placeholder,'搜索');
  title.nodeValue='Sales';callback([{type:'characterData',target:title}]);assert.equal(title.nodeValue,'促销');
});
