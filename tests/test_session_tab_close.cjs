const fs=require('fs'),vm=require('vm'),assert=require('assert');
const listeners={},messages=[],elements={tabs:{children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)}},note:{}};
const context={crypto:require('crypto').webcrypto,document:{getElementById:id=>elements[id],createElement:()=>({children:[],append(x){this.children.push(x)},setAttribute(k,v){this[k]=v}})},window:{parent:{postMessage:m=>messages.push(m)},addEventListener:(name,fn)=>listeners[name]=fn}};
vm.runInNewContext(fs.readFileSync('components/session_tabs/index.html','utf8').split('<script>')[1].split('</script>')[0],context);
listeners.message({data:{type:'streamlit:render',args:{active:'dk',records:[{id:'dk',name:'DK.csv'},{id:'fd',name:'FD.csv'}]}}});
assert.equal(elements.tabs.children.length,2);
for(const [i,id] of ['dk','fd'].entries()){const close=elements.tabs.children[i].children[1];assert.equal(close.textContent,'×');close.onclick();const event=messages.at(-1).value;assert.equal(event.closed_id,id);assert(!event.selected_id);assert(JSON.stringify(event).length<200)}
console.log('Active and inactive slate close buttons send small close events.');
