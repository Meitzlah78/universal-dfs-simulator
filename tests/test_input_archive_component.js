// Minimal asynchronous IndexedDB fixture: verifies the component's message,
// hashing, retention and recovery protocol without a Streamlit dependency.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto').webcrypto;
const databases=new Map();
function req(fn){const r={};setImmediate(()=>{try{r.result=fn();r.onsuccess?.()}catch(e){r.error=e;r.onerror?.()}});return r}
const indexedDB={open(name){const r={};setImmediate(()=>{let db=databases.get(name);if(!db){db={stores:new Map(),createObjectStore(s){this.stores.set(s,new Map())},transaction(s){const tx={objectStore(){const values=db.stores.get(s);return {get:k=>req(()=>values.get(k)),getAllKeys:()=>req(()=>[...values.keys()]),put(v,k){values.set(k===undefined?v.digest:k,v);setImmediate(()=>tx.oncomplete?.())}}}};return tx}};databases.set(name,db);r.result=db;r.onupgradeneeded?.()}r.result=db;r.onsuccess?.()});return r}};
const messages=[],listeners={},status={textContent:''};
const context={crypto,indexedDB,Uint8Array,Promise,Error,JSON,Set,Map,console,
 atob:v=>Buffer.from(v,'base64').toString('binary'),navigator:{storage:{persist:async()=>true}},
 document:{getElementById:()=>status},MessageEvent:class{constructor(_,a){Object.assign(this,a)}},
 window:{parent:{postMessage:m=>{assert(Buffer.byteLength(JSON.stringify(m),'utf8')<25000000,'Archive WebSocket frame exceeds enforced 25 MB limit');messages.push(m)}},addEventListener:(name,fn)=>listeners[name]=fn,dispatchEvent:e=>listeners.message(e)}};
const html=fs.readFileSync('components/input_archive/index.html','utf8');
vm.runInNewContext(html.split('<script>')[1].split('</script>')[0],context);
const tick=()=>new Promise(resolve=>setTimeout(resolve,30));
const render=async args=>{await listeners.message({data:{type:'streamlit:render',args}});await tick()};
const value=()=>messages.filter(x=>x.type==='streamlit:setComponentValue').at(-1).value;
(async()=>{
 await render({records:[],restore:[]});const owner=value().owner;assert.equal(owner.length,32);
 const data=Buffer.from('raw original\r\n').toString('base64');
 const digest=require('crypto').createHash('sha256').update(Buffer.from(data,'base64')).digest('hex');
 await render({records:[{digest,filename:'salary.csv',data}],restore:[]});assert.equal(value().hashes[0],digest);
 await render({records:[],restore:[digest]});assert.equal(value().restored[0].data,data);assert.equal(value().owner,owner);
 await render({records:[],restore:[]});assert.equal(value().hashes.length,1);
 await render({records:[{digest:'0'.repeat(64),filename:'bad.csv',data}],restore:[]});assert.match(value().error,/SHA-256/);
 const large=Buffer.alloc(35857500,73),largeData=large.toString('base64');
 const largeDigest=require('crypto').createHash('sha256').update(large).digest('hex');
 const payload=JSON.stringify({current:{records:[{digest:largeDigest,filename:'large-build.zip',data:largeData}],restore:[]},snapshot:''});
 const total=Math.ceil(payload.length/1000000);
 for(let index=0;index<total;index++){
  await render({transport_only:true,download:{id:'large-file',index,total,data:payload.slice(index*1000000,(index+1)*1000000)}});
  assert.equal(value().download_ack.index,index);
 }
 await render({transport_only:true,download_done:'large-file'});
 assert.equal(value().download_received,'large-file');assert(value().hashes.includes(largeDigest));
 await render({current:{records:[],restore:[largeDigest]}});
 const parts=[];let current=value();
 while(current.upload_part){
  const part=current.upload_part;parts[part.index]=part.data;
  await render({transport_only:true,upload_ack:{id:part.id,index:part.index}});current=value();
 }
 assert(current.upload_done);
 const restored=JSON.parse(parts.join('')).selected;
 assert.equal(restored.restored[0].data,largeData);assert.equal(restored.owner,owner);
 console.log('Archive browser protocol passed: identity, exact-byte hash, retention, restore, corrupt-input rejection.');
 console.log('47.8 MB archive saved and restored in chunks: EVERY browser message below the enforced 25 MB limit.');
})().catch(e=>{console.error(e);process.exitCode=1});
