const fs=require('fs'),vm=require('vm'),assert=require('assert');
const day='2026-10-25', stores=new Map([
 ['simmah-loaded-slates-v1',new Map([['slates',new Map([
 ['new',{id:'new',name:'DKEntries-2026-10-25.csv'}],['old',{id:'old',name:'FanDuel-2026-10-24.csv'}],['other',{id:'other',name:'Other-2026-10-25.csv'}]])]])],
 ['simmah-original-inputs-v1',new Map([['identity',new Map([['owner','a'.repeat(32)]])],['files',new Map([
 ['new',{digest:'new',filename:'FanDuel-2026-10-25.csv'}],['old',{digest:'old',filename:'DKEntries-2026-10-24.csv'}]])]])]
]);
function request(fn){const r={};queueMicrotask(()=>{r.result=fn();r.onsuccess()});return r}
const indexedDB={open(name){return request(()=>({objectStoreNames:{contains:s=>stores.get(name).has(s)},close(){},transaction(s){const values=stores.get(name).get(s),tx={objectStore(){return {get:key=>request(()=>values.get(key)),getAll:()=>request(()=>[...values.values()]),delete(key){values.delete(key)}}}};setImmediate(()=>tx.oncomplete?.());return tx}}))}};
const messages=[],listeners={},elements={clear:{},status:{}},storage=new Map([['simmah-active-slate','new']]);
const parent={postMessage:m=>messages.push(m),__simmahSlateTransfersV1:{upload:{},download:{},records:new Map([['new',{}],['old',{}]]),closedIds:new Set()},__simmahArchiveTransfersV1:{upload:{},download:{}}};
const context={indexedDB,Intl,Date,Promise,Error,crypto:require('crypto').webcrypto,localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},document:{getElementById:k=>elements[k]},window:{parent,addEventListener:(name,fn)=>listeners[name]=fn}};
vm.runInNewContext(fs.readFileSync('components/saved_cleanup/index.html','utf8').split('<script>')[1].split('</script>')[0],context);
(async()=>{listeners.message({data:{type:'streamlit:render',args:{day}}});assert.equal(stores.get('simmah-loaded-slates-v1').get('slates').size,3);await elements.clear.onclick();
assert.deepEqual([...stores.get('simmah-loaded-slates-v1').get('slates').keys()],['old','other']);
assert.deepEqual([...stores.get('simmah-original-inputs-v1').get('files').keys()],['old']);
assert.equal(stores.get('simmah-original-inputs-v1').get('identity').get('owner'),'a'.repeat(32));
const event=messages.filter(m=>m.type==='streamlit:setComponentValue').at(-1).value;
assert.equal(event.clear,true);assert.equal(event.owner,'a'.repeat(32));assert.deepEqual(Array.from(event.slates),['new']);assert.equal(parent.__simmahSlateTransfersV1.upload,null);assert.equal(storage.get('simmah-clean-start-date'),day);
console.log('Cleanup passed: explicit click only, both stores pruned, older data/identity preserved, stale transfers stopped.');})().catch(e=>{console.error(e);process.exitCode=1});
