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
 const window={parent:{postMessage(x){assert(Buffer.byteLength(JSON.stringify(x),'utf8')<25000000,'WebSocket frame exceeds 25 MB');messages.push(x)}},addEventListener(type,fn){listeners[type]=fn},dispatchEvent(e){listeners.message(e)}};
 const context={window,document:{getElementById:id=>elements[id],createElement:()=>({children:[],append(x){this.children.push(x)},setAttribute(){}})},
  indexedDB:{open(){const r={};queueMicrotask(()=>{r.result=db;r.onsuccess()});return r}},
  localStorage:{getItem:k=>local.get(k),setItem:(k,v)=>local.set(k,v),removeItem:k=>local.delete(k)},
  crypto:require('crypto').webcrypto,MessageEvent:class{constructor(t,o){this.data=o.data}},queueMicrotask,Map,Date,JSON};
 vm.runInNewContext(code,context);
 return {messages,elements,async render(args){await listeners.message({data:{type:'streamlit:render',args}})},
  value(){return messages.filter(x=>x.type==='streamlit:setComponentValue').at(-1)?.value}};
}
async function finishUpload(ui){
 const parts=[];let value=ui.value();
 while(value?.upload_part){const p=value.upload_part;parts[p.index]=p.data;await ui.render({transport_only:true,upload_ack:{id:p.id,index:p.index}});value=ui.value()}
 assert(value.upload_done);return JSON.parse(parts.join(''))
}
(async()=>{
 const main={id:'main',name:'main.csv',title:'Main',data:'CSV',snapshot:'A'.repeat(32000000)};
 const afternoon={id:'afternoon',name:'afternoon.csv',title:'Afternoon',data:'CSV2',snapshot:'B'.repeat(5000000)};
 disk.set(main.id,main);disk.set(afternoon.id,afternoon);local.set('simmah-active-slate','main');
 const ui=boot();await ui.render({generation:'reboot',active:null,current:null});
 assert(ui.value().upload_part);
 const selection=await finishUpload(ui);assert.equal(selection.selected.id,'main');assert(!('records' in selection));
 assert.equal(selection.selected.snapshot,main.snapshot);
 await ui.render({generation:'reboot',active:'main',current:null,snapshot:'',
   records:[{id:'main',name:'main.csv',title:'Main'},{id:'afternoon',name:'afternoon.csv',title:'Afternoon'}],ack:selection.event});
 assert.equal(disk.get('afternoon').snapshot,afternoon.snapshot);
 const payload={current:{id:'main',name:'main.csv',title:'Main',data:'CSV'},snapshot:'C'.repeat(47810117)};
 const raw=JSON.stringify(payload),total=Math.ceil(raw.length/1000000);
 for(let index=0;index<total;index++){
  await ui.render({transport_only:true,download:{id:'download-main',index,total,data:raw.slice(index*1000000,(index+1)*1000000)}});
  assert.equal(ui.value().download_ack.index,index);
 }
 assert.equal(disk.get('main').snapshot,payload.snapshot);
 await ui.render({transport_only:true,download_done:'download-main'});assert.equal(ui.value().download_received,'download-main');
 await ui.render({generation:'reboot',active:'main',current:null,snapshot:'',records:[]});
 const afternoonGroup=ui.elements.tabs.children.find(g=>g.children[0].textContent==='Afternoon');
 afternoonGroup.children[0].onclick();const second=await finishUpload(ui);assert.equal(second.selected.id,'afternoon');
 await ui.render({generation:'reboot',active:'afternoon',current:null,snapshot:'',ack:second.event});
 const group=ui.elements.tabs.children.find(g=>g.children[0].textContent==='Afternoon');
 await group.children[1].onclick();const close=await finishUpload(ui);
 assert.equal(close.closed,'afternoon');assert.equal(close.selected.id,'main');assert(!disk.has('afternoon'));
 assert.equal(close.selected.snapshot,payload.snapshot);
 console.log('Passed: 32 MB browser restore, 47,810,117-byte server save, tab switching/closing, and EVERY browser message below the actual 25 MB server limit.');
})().catch(e=>{console.error(e);process.exitCode=1});

