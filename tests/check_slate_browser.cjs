// Exercise the actual component's save/restore/switch protocol with a durable IDB stub.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync('components/slate_workspaces/index.html','utf8');
const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const disk=new Map(),local=new Map();
function boot(){
 const messages=[],listeners={};
 const elements={tabs:{children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)}},status:{textContent:''}};
 const db={transaction(){const tx={objectStore(){return {getAll(){const r={};queueMicrotask(()=>{r.result=[...disk.values()];r.onsuccess()});return r},put(record){disk.set(record.id,structuredClone(record));queueMicrotask(()=>tx.oncomplete())}}}};return tx}};
 const window={parent:{postMessage(x){messages.push(x)}},addEventListener(type,fn){listeners[type]=fn},dispatchEvent(e){listeners.message(e)}};
 const ctx={window,document:{getElementById:id=>elements[id],createElement:()=>({setAttribute(){}})},indexedDB:{open(){const r={};queueMicrotask(()=>{r.result=db;r.onsuccess()});return r}},localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v)},crypto:require('crypto').webcrypto,MessageEvent:class{constructor(type,options){this.data=options.data}},queueMicrotask,Map,Date,JSON};
 vm.runInNewContext(code,ctx);
 return {elements,messages,async render(args){await listeners.message({data:{type:'streamlit:render',args}})},selected(){return messages.filter(x=>x.type==='streamlit:setComponentValue').at(-1)?.value.selected}};
}
(async()=>{
 const first=boot();await first.render({generation:'one',active:null,current:null,incoming:{id:'nba',name:'nba.csv',title:'DK NBA',data:'csv',snapshot:''}});
 assert.equal(first.selected().id,'nba');
 await first.render({generation:'one',active:'nba',current:first.selected(),snapshot:'saved-nba'});
 await first.render({generation:'one',active:'nba',current:first.selected(),snapshot:'saved-nba',incoming:{id:'nfl',name:'nfl.csv',title:'FD NFL',data:'csv2',snapshot:''}});
 const nfl=first.selected();assert.equal(nfl.id,'nfl');
 await first.render({generation:'one',active:'nfl',current:nfl,snapshot:'saved-nfl'});
 const restarted=boot();await restarted.render({generation:'new-server',active:null,current:null});
 assert.equal(restarted.selected().id,'nfl');assert.equal(restarted.selected().snapshot,'saved-nfl');
 const nbaTab=restarted.elements.tabs.children.find(b=>b.textContent==='DK NBA');nbaTab.onclick();
 assert.equal(restarted.selected().id,'nba');assert.equal(restarted.selected().snapshot,'saved-nba');
 console.log('Browser save, server-reboot restore, and cross-sport tab switch passed.');
})().catch(error=>{console.error(error);process.exitCode=1});
