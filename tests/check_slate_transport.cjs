const fs=require('fs'),vm=require('vm'),assert=require('assert');
const code=fs.readFileSync('components/slate_workspaces/index.html','utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const disk=new Map(),local=new Map();
function boot(){
 const messages=[],listeners={};
 const elements={tabs:{children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)}},status:{textContent:''}};
 const db={transaction(){const tx={objectStore(){return {
  getAll(){const r={};queueMicrotask(()=>{r.result=[...disk.values()];r.onsuccess()});return r},
  put(record){disk.set(record.id,structuredClone(record));queueMicrotask(()=>tx.oncomplete())},
  delete(id){disk.delete(id);queueMicrotask(()=>tx.oncomplete())}
 }}};return tx}};
 const window={parent:{postMessage(x){messages.push(x)}},addEventListener(type,fn){listeners[type]=fn},dispatchEvent(e){listeners.message(e)}};
 const context={window,document:{getElementById:id=>elements[id],createElement:()=>({children:[],append(x){this.children.push(x)},setAttribute(){}})},
  indexedDB:{open(){const r={};queueMicrotask(()=>{r.result=db;r.onsuccess()});return r}},
  localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v),removeItem:k=>local.delete(k)},
  crypto:require('crypto').webcrypto,MessageEvent:class{constructor(t,o){this.data=o.data}},queueMicrotask,Map,Date,JSON};
 vm.runInNewContext(code,context);
 return {messages,elements,async render(args){await listeners.message({data:{type:'streamlit:render',args}})},
  value(){return messages.filter(x=>x.type==='streamlit:setComponentValue').at(-1)?.value}};
}
(async()=>{
 const main={id:'main',name:'main.csv',title:'Main',data:'CSV',snapshot:'A'.repeat(32000000)};
 const afternoon={id:'afternoon',name:'afternoon.csv',title:'Afternoon',data:'CSV2',snapshot:'B'.repeat(5000000)};
 disk.set(main.id,main);disk.set(afternoon.id,afternoon);local.set('simmah-active-slate','main');
 const ui=boot();await ui.render({generation:'reboot',active:null,current:null});
 const selected=ui.value();assert.equal(selected.selected.id,'main');assert(!('records' in selected));
 assert.equal(selected.selected.snapshot.length,32000000);
 await ui.render({generation:'reboot',active:'main',current:{id:'main',name:'main.csv',title:'Main',data:'CSV'},snapshot:main.snapshot,
  records:[{id:'main',name:'main.csv',title:'Main'},{id:'afternoon',name:'afternoon.csv',title:'Afternoon'}],ack:selected.event});
 assert(ui.value().acknowledged);assert(JSON.stringify(ui.value()).length<200);
 assert.equal(disk.get('afternoon').snapshot,afternoon.snapshot);
 assert.equal(disk.get('main').snapshot,main.snapshot);
 const afternoonGroup=ui.elements.tabs.children.find(g=>g.children[0].textContent==='Afternoon');
 afternoonGroup.children[0].onclick();assert.equal(ui.value().selected.id,'afternoon');assert(!('records' in ui.value()));
 await ui.render({generation:'reboot',active:'afternoon',current:{...afternoon,snapshot:undefined},snapshot:afternoon.snapshot,ack:ui.value().event});
 const group=ui.elements.tabs.children.find(g=>g.children[0].textContent==='Afternoon');
 await group.children[1].onclick();assert.equal(ui.value().closed,'afternoon');assert.equal(ui.value().selected.id,'main');
 assert(!disk.has('afternoon'));assert.equal(ui.value().selected.snapshot,main.snapshot);
 console.log('Passed: legacy 32 MB restore, selected-only messages, tiny acknowledgements, metadata preservation, and closing an active browser-only tab.');
})().catch(e=>{console.error(e);process.exitCode=1});
