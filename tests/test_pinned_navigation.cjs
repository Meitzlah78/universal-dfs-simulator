const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync('components/pinned_navigation/index.html','utf8');
const classes=()=>{const values=new Set();return {add:v=>values.add(v),remove:v=>values.delete(v),contains:v=>values.has(v)}};
const element=(width,height)=>({isConnected:true,classList:classes(),matches:()=>false,getBoundingClientRect:()=>({left:24,width,height})});
const header=element(700,80),chrome=element(700,40);
let host,tabs,sections;
function replace(width){host=element(width,45);tabs=element(width,42);tabs.parentElement=host;sections={querySelector:()=>tabs}}
replace(700);
const style=new Map(),documentElement={classList:classes(),style:{setProperty:(k,v)=>style.set(k,v),getPropertyValue:k=>style.get(k)||''}};
const doc={body:{},documentElement,querySelector:s=>s.includes('app_header')?header:s.includes('section_tabs')?sections:chrome};
let next=0,frames=new Map(),resizeObservers=[],mutations=[];
const root={document:doc,postMessage(){},addEventListener(){},removeEventListener(){},requestAnimationFrame:fn=>{frames.set(++next,fn);return next},cancelAnimationFrame:id=>frames.delete(id),
  ResizeObserver:class{constructor(fn){this.fn=fn;this.targets=[];resizeObservers.push(this)}observe(el){this.targets.push(el)}disconnect(){this.targets=[]}},
  MutationObserver:class{constructor(fn){this.fn=fn;mutations.push(this)}observe(){this.active=true}disconnect(){this.active=false}}};
let render;
vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],{window:{parent:root,addEventListener:(_event,fn)=>render=fn}});
function flush(){const pending=[...frames.values()];frames.clear();for(const fn of pending)fn()}
render({data:{type:'streamlit:render'}});flush();
assert.equal(style.get('--simmah-tabs-width'),'700px');
assert(documentElement.classList.contains('simmah-pinned-navigation-ready'));
const oldTabs=tabs,oldHost=host;
oldTabs.isConnected=false;oldHost.isConnected=false;
replace(320);mutations[0].fn();flush();
assert.equal(style.get('--simmah-tabs-width'),'320px');
assert(resizeObservers[0].targets.includes(tabs));
assert(!resizeObservers[0].targets.includes(oldTabs));
assert(!oldHost.classList.contains('simmah-navigation-spacer'));
assert(host.classList.contains('simmah-navigation-spacer'));
// During a rerun the bar can temporarily disappear. Native flow must be restored.
sections=null;mutations[0].fn();flush();
assert(!documentElement.classList.contains('simmah-pinned-navigation-ready'));
replace(500);mutations[0].fn();flush();
assert.equal(style.get('--simmah-tabs-width'),'500px');
assert(documentElement.classList.contains('simmah-pinned-navigation-ready'));
// A fresh iframe disposes old observers and reconnects even after missing nodes.
render({data:{type:'streamlit:render'}});flush();
assert.equal(mutations[0].active,false);
assert.equal(mutations[1].active,true);
root.__simmahPinnedNavigation.dispose();
assert(!documentElement.classList.contains('simmah-pinned-navigation-ready'));
assert.equal(mutations[1].active,false);
console.log('Pinned navigation: node replacement, temporary removal, and observer cleanup passed.');
