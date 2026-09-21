// Exercise both experiment data paths and the public replay tool without a browser.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';

const root=path.resolve('viewer/dist');
const elements=new Map();const registered=new Map();
class Element{
  constructor(){this.value='';this.options=[];this.hidden=false;this.textContent='';this.innerHTML='';this.events={};}
  addEventListener(name,fn){this.events[name]=fn;}
  replaceChildren(...options){this.options=options;this.value=options[0]?.value||'';}
  setAttribute(){}
  scrollIntoView(){}
}
const sandbox={
  document:{getElementById:id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},modelContext:{registerTool:tool=>registered.set(tool.name,tool)}},
  window:{addEventListener(){}},
  Option:class{constructor(text,value){this.text=text;this.value=value;}},
  fetch:async url=>new Response(await fs.readFile(path.join(root,url))),
  Response,Blob,DecompressionStream,TextDecoder,Uint8Array,AbortController,performance,
  requestAnimationFrame:fn=>{if(fn.name!=='animate')queueMicrotask(()=>fn(performance.now()));}
};
vm.createContext(sandbox);vm.runInContext(await fs.readFile(path.join(root,'app.js'),'utf8'),sandbox);
for(let i=0;i<200&&!sandbox.window.trafficLab.getState().loaded;i++)await new Promise(r=>setTimeout(r,10));
assert(sandbox.window.trafficLab.getState().loaded,elements.get('status').textContent);
const configure=registered.get('configure_traffic_replay').execute;
const summary=JSON.parse(await fs.readFile(path.join(root,'data/coordinated-summary.json')));
let tested=0;
for(const [scenario,controllers] of Object.entries(summary.replays)){
  for(const controller of Object.keys(controllers).filter(c=>c!=='fixed')){
    const state=await configure({study:'coordinated',scenario,controller,time_seconds:500});
    assert.equal(state.controller,controller);assert.equal(state.scenario,scenario);assert.equal(state.study,'coordinated');assert.equal(state.playing,false);assert(state.loaded);
    assert(elements.get('benchmark-body').innerHTML.includes(summary.names[controller]));
    assert(elements.get('plan-status').textContent.includes('/12 intersections'));tested++;
    vm.runInContext("state.selected='6_26';decision();",sandbox);
    assert(elements.get('decision').innerHTML.includes('Active split'));
    if(controller!=='library-fixed')assert(elements.get('decision').innerHTML.includes('numerical minimum'));
  }
}
for(const controller of ['jev','bounded-jev','pressure','actuated']){
  const state=await configure({study:'original',scenario:'am',controller,time_seconds:400});
  assert.equal(state.controller,controller);assert.equal(state.study,'original');assert(state.loaded);tested++;
}
await assert.rejects(configure({study:'original',scenario:'shift',controller:'jev',time_seconds:400}));
console.log(`${tested} recorded comparison paths and cross-study rejection passed.`);
