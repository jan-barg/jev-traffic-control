const $=id=>document.getElementById(id);
const state={summary:null,left:null,right:null,t:180,playing:true,speed:8,selected:null,study:'coordinated',scenario:'am',controller:'plan-jev',loading:false};
const cache=new Map();
const vehicleColors=['#276aaf','#c69216','#537c3f','#ab4444','#7852a0','#277e79','#343434','#ab653e'];
const fmt=(n,d=1)=>n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:d,minimumFractionDigits:d});
const clock=t=>`${String(Math.floor(t/60)).padStart(2,'0')}:${String(Math.floor(t%60)).padStart(2,'0')}`;
async function replay(url){
  if(cache.has(url))return cache.get(url);
  const response=await fetch(url);if(!response.ok)throw new Error(`Replay unavailable (${response.status})`);
  const bytes=await response.arrayBuffer();const view=new Uint8Array(bytes);
  const text=view[0]===31&&view[1]===139?await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text():new TextDecoder().decode(bytes);
  const data=JSON.parse(text);cache.set(url,data);return data;
}
function frame(data,t){
  if(!data?.frames.length)return null;
  const index=Math.min(data.frames.length-1,Math.max(0,Math.floor(t-data.frames[0].t)));
  const a=data.frames[index],b=data.frames[Math.min(index+1,data.frames.length-1)];
  return{a,b,mix:Math.min(1,Math.max(0,(t-a.t)/(b.t-a.t||1)))};
}
function transform(canvas,network){
  const w=canvas.clientWidth,h=canvas.clientHeight,dpr=window.devicePixelRatio||1;
  if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);}
  const ns=network.nodes,xs=ns.map(n=>n.x),ys=ns.map(n=>n.y);
  const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
  const scale=Math.min((w-55)/(maxX-minX),(h-82)/(maxY-minY));
  const ox=(w-(maxX-minX)*scale)/2,oy=56+(h-82-(maxY-minY)*scale)/2;
  return{w,h,dpr,scale,point:(x,y)=>[ox+(x-minX)*scale,oy+(maxY-y)*scale]};
}
function draw(canvas,data){
  if(!data)return;
  const tr=transform(canvas,data.network),ctx=canvas.getContext('2d');ctx.setTransform(tr.dpr,0,0,tr.dpr,0,0);ctx.clearRect(0,0,tr.w,tr.h);
  ctx.fillStyle='#fff';ctx.fillRect(0,0,tr.w,tr.h);
  const nodes=Object.fromEntries(data.network.nodes.map(n=>[n.id,n]));
  // City blocks are derived from the simulation junctions, not background imagery.
  for(let st=25;st<30;st++){
    const a=tr.point(nodes[`7_${st}`].x,nodes[`7_${st}`].y),b=tr.point(nodes[`6_${st+1}`].x,nodes[`6_${st+1}`].y);
    ctx.strokeStyle='#ddd';ctx.lineWidth=.5;ctx.strokeRect(a[0]+14,b[1]+10,b[0]-a[0]-28,a[1]-b[1]-20);
  }
  for(const e of data.network.edges){
    const points=e.shape.map(p=>tr.point(...p));ctx.strokeStyle='#e6e6e6';ctx.lineWidth=e.lanes===3?15:8;ctx.lineCap='butt';ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();
    ctx.strokeStyle='#000';ctx.lineWidth=.5;ctx.setLineDash([3,6]);ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke();ctx.setLineDash([]);
  }
  ctx.textAlign='center';ctx.font='14px "Computer Modern",serif';ctx.fillStyle='#000';
  for(let st=25;st<=30;st++){
    const p=tr.point(nodes[`7_${st}`].x,nodes[`7_${st}`].y),q=tr.point(nodes[`6_${st}`].x,nodes[`6_${st}`].y);
    ctx.fillText(`W ${st} St ${st%2?'←':'→'}`,(p[0]+q[0])/2,p[1]-9);
  }
  for(const ave of [7,6]){
    const p=tr.point(nodes[`${ave}_30`].x,nodes[`${ave}_30`].y);
    ctx.save();ctx.font='700 14px "Computer Modern",serif';ctx.fillText(`${ave}th Ave ${ave===7?'↓':'↑'}`,p[0],p[1]-31);ctx.restore();
  }
  const f=frame(data,state.t);if(!f)return;
  const next=new Map(f.b.vehicles.map(v=>[v[0],v]));
  for(const v of f.a.vehicles){
    const n=next.get(v[0])||v,m=f.mix,x=v[1]+(n[1]-v[1])*m,y=v[2]+(n[2]-v[2])*m;
    const p=tr.point(x,y);let da=((n[3]-v[3]+540)%360)-180;const angle=v[3]+da*m;
    const speed=v[4]+(n[4]-v[4])*m;ctx.save();ctx.translate(...p);ctx.rotate((angle-90)*Math.PI/180);
    ctx.fillStyle=vehicleColors[(Math.imul(v[0],2654435761)>>>0)%vehicleColors.length];
    const length=Math.max(5,(v[5]?9:5)*tr.scale);
    ctx.fillRect(-length/2,-1.35,length,2.7);
    if(speed<.1){ctx.strokeStyle='#000';ctx.lineWidth=.7;ctx.strokeRect(-length/2-.6,-1.95,length+1.2,3.9);}
    ctx.restore();
  }
  for(const [id,j] of Object.entries(data.junctions)){
    const n=nodes[id],p=tr.point(n.x,n.y),s=f.a.signals[id];
    const color=kind=>{const indices=[...j.states[kind]].flatMap((v,i)=>v==='G'?[i]:[]);return indices.some(i=>s[i]==='G'||s[i]==='g')?'#176b37':indices.some(i=>s[i]==='y')?'#a85900':'#a21c1c';};
    ctx.fillStyle='#fff';ctx.beginPath();ctx.arc(...p,7,0,Math.PI*2);ctx.fill();
    ctx.strokeStyle='#000';ctx.lineWidth=.6;ctx.stroke();
    ctx.fillStyle=color('avenue');ctx.fillRect(p[0]-4,p[1]-5,3,10);ctx.fillStyle=color('cross');ctx.fillRect(p[0]+1,p[1]-5,3,10);
    if(state.selected===id){ctx.strokeStyle='#000';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc(...p,10,0,Math.PI*2);ctx.stroke();}
  }
}
function updateMetrics(which,data){
  const f=frame(data,state.t);if(!f)return;const m=f.a.metrics;
  $(which+'-metrics').innerHTML=`<div class="metric"><strong>${fmt(m.queued,0)}</strong><span>vehicles queued</span></div><div class="metric"><strong>${fmt(m.mean_delay_s)}<small> s</small></strong><span>delay / requested trip</span></div><div class="metric"><strong>${fmt(m.completed,0)}</strong><span>evaluation trips finished</span></div>`;
}
function decision(){
  const corridor=state.study==='coordinated'&&state.right?.plan_installs;
  const planStatus=$('plan-status');planStatus.hidden=!corridor;
  let installations={},lastCorridor=null;
  if(corridor){
    for(const x of state.right.plan_installs){if(x.t>state.t)break;installations[x.junction]=x;}
    for(const x of state.right.actions||[]){if(x.t<=state.t&&x.accepted)lastCorridor=x;}
    const target=lastCorridor?.action||state.right.result.initial_plan;
    const adopted=Object.keys(state.right.junctions).filter(id=>(installations[id]?.plan||'g52')===target).length;
    const label=state.right.result.plan_library[target]?.label||target;
    planStatus.textContent=`Selected plan: ${label}. ${adopted}/12 intersections have adopted it.${lastCorridor?` Selected at ${clock(lastCorridor.t)}${lastCorridor.source==='fallback'?' (retained after an unavailable response)':''}.`:''} Splits change at local cycle starts.`;
  }
  const el=$('decision');if(!state.selected||!state.right){el.hidden=true;return;}
  el.hidden=false;const id=state.selected,items=state.right.actions||[];
  if(corridor){
    const current=installations[id],green=current?.avenue_green_s||52;
    const [ave,st]=id.split('_');
    const forecast=lastCorridor&&(state.right.plan_decisions||[]).find(q=>q.observed_sim_s===lastCorridor.observed_t);
    const forecastNote=forecast?` At that observation, the selected plan’s forecast objective was ${fmt(forecast.candidates[lastCorridor.action].objective,0)} vehicle-seconds; the numerical minimum was ${fmt(forecast.candidates[forecast.numerical_choice].objective,0)} (${forecast.candidates[forecast.numerical_choice].label}). This is predicted queue delay plus a terminal queue penalty, not measured travel time.`:'';
    el.innerHTML=`<strong>${ave}th Avenue & West ${st}th Street</strong> · Active split: <span>${green} s avenue / ${82-green} s cross street</span>. ${current?`Installed at ${clock(current.t)}; next cycle ${clock(current.cycle_start_s+90)}.`:'Initial reference cycle.'}${lastCorridor?` Last corridor decision arrived ${fmt(lastCorridor.t-lastCorridor.observed_t,2)} s after observation.`:''}${forecastNote}`;
    return;
  }
  let last=null;for(let i=items.length-1;i>=0;i--){if(items[i].junction===id&&items[i].t<=state.t){last=items[i];break;}}
  const [ave,st]=id.split('_');
  const bounded=last&&['keep','avenue_plus_5','cross_plus_5'].includes(last.action);
  const text=bounded?`At ${clock(last.t)}, <span>${last.accepted?`${last.avenue_green_s} s avenue / ${last.cross_green_s} s cross-street green`:'split change rejected'}</span> for this cycle. ${last.accepted?`Next coordinated cycle: ${clock(last.next_cycle_start_s)}.`:''} ${last.source==='fallback'?'Baseline retained after an unavailable or late response.':`Observation age at application: ${fmt(last.t-last.observed_t,2)} s.`}`:last?`At ${clock(last.t)}, <span>${last.action==='hold'?'keep the current green':'start a phase transition'}</span>. ${last.accepted?'Applied':'Rejected by the signal guard'}. ${last.source==='response'?`Observation age at application: ${fmt(last.t-last.observed_t,2)} s.`:last.source==='fallback'?'Fallback rule used.':'Conventional controller decision.'}`:'No eligible controller decision yet at this replay time.';
  el.innerHTML=`<strong>${ave}th Avenue & West ${st}th Street</strong> · ${text}`;
}
function table(){
  const summary=state.summary,groups=summary.groups[state.scenario]||{};
  $('benchmark-body').innerHTML=Object.entries(summary.names).map(([c,name])=>{
    const g=groups[c],m=g?.metrics;
    if(!g)return `<tr><td>${name}<small>Benchmark running</small></td><td colspan="6">Results pending</td></tr>`;
    return `<tr class="${c===state.controller?'highlight':''}"><td>${name}</td><td data-primary>${fmt(m.mean_delay_s)}</td><td>${fmt(m.mean_completed_travel_s)}</td><td>${fmt(m.p95_completed_travel_s)}</td><td>${fmt(m.mean_queue_vehicles)}</td><td>${fmt(m.completed_trips,0)}</td><td>${fmt(m.unfinished_trips,1)}</td></tr>`;
  }).join('');
  const p=summary.paired[state.scenario]?.[state.controller]?.metrics?.mean_delay_s;
  if(p&&groups.fixed){
    const diff=p.mean_difference,percent=Math.abs(diff)/groups.fixed.metrics.mean_delay_s*100,ci=p.ci95;
    const equal=Math.abs(diff)<1e-9;
    const outcome=equal?'matched the tuned fixed plan’s mean delay':`produced <strong class="${ci&&ci[0]<=0&&ci[1]>=0?'caution':diff<0?'beneficial':'adverse'}">${fmt(percent)}% ${diff<0?'less':'more'} delay</strong> than the tuned fixed plan`;
    const precision=state.controller==='bounded-jev'?2:1;
    const bounded=state.controller==='bounded-jev'&&summary.bounded_validation;
    const replayKept=state.right?.actions?.every(a=>!a.accepted||a.action==='keep');
    const policyNote=bounded?` Jev retained the baseline in ${fmt(bounded.choices.keep||0,0)} of ${fmt(bounded.model_actions_applied,0)} applied choices across both scenarios.${replayKept?' The seed-11 replay retained the baseline throughout.':''}`:'';
    $('result-callout').innerHTML=`${summary.names[state.controller]} ${outcome}. Paired difference: ${diff>0?'+':''}${fmt(diff,precision)} s per requested trip${ci?` (95% interval: ${fmt(ci[0],precision)} to ${fmt(ci[1],precision)} s)`:''}; ${p.n} paired seeds. ${equal?'These seeds produced identical delay; other conditions may differ. ':ci&&ci[0]<=0&&ci[1]>=0?'The interval includes no difference. ':''}This comparison applies to the modeled conditions.${policyNote}`;
  }else $('result-callout').textContent='The benchmark is running. This viewer shows actual recorded trajectories; aggregate Jev results will appear after the real-time runs finish.';
  const comparison=state.controller==='plan-jev'&&summary.jev_comparisons?.[state.scenario];
  $('selector-comparison').hidden=!comparison;
  if(comparison){
    $('selector-comparison').textContent=['plan-numeric','library-fixed'].map(c=>{
      const p=comparison[c];return p?`Versus ${summary.names[c].toLowerCase()}: ${p.mean_difference>0?'+':''}${fmt(p.mean_difference,2)} s/trip (95% interval ${fmt(p.ci95[0],2)} to ${fmt(p.ci95[1],2)}).`:'';
    }).join(' ');
  }
  const v=summary.validation,a=v?.primary_audit,b=summary.bounded_validation;
  const boundedNote=b?` Bounded Jev: ${fmt(b.requests,0)} API batches, median ${fmt(b.latency_s.p50*1000,0)} ms, P95 ${fmt(b.latency_s.p95*1000,0)} ms; ${b.timing_violations} timing violations.`:'';
  $('verification-note').innerHTML=a?`A conventional rerun reproduced exactly; 42 sensitivity runs completed. Turning-flow error against the input counts was ${fmt(v.input_flow_check.weighted_absolute_relative_error*100,2)}% (in-sample). For native Jev, across ${fmt(a.jev_requests,0)} real API batches, latency was ${fmt(a.latency_s.p50*1000,0)} ms at the median and ${fmt(a.latency_s.p95*1000,0)} ms at P95. No model action preceded its response.${boundedNote} <strong class="caution">Field validation remains outstanding.</strong>`:'';
  const audit=summary.coordinated_validation;
  if(audit)$('verification-note').innerHTML=`${fmt(audit.phase_durations_checked,0)} phase durations and ${fmt(audit.cycles_checked,0)} cycles checked; ${audit.timing_violations} timing violations. Jev agreed with the numerical choice on ${audit.agrees_with_numerical_selector}/${audit.model_actions} decisions. Request latency: median ${fmt(audit.latency_s.p50*1000,0)} ms, P95 ${fmt(audit.latency_s.p95*1000,0)} ms. ${audit.api_errors} API errors; ${audit.deadline_misses} missed deadlines; ${audit.fallback_actions} retained-plan fallbacks. No action preceded its response or eligible cycle.${summary.execution_retry?` A laptop sleep invalidated the first 15 live attempts; the full batch was repeated unchanged. Details are in the report.`:''} <strong class="caution">Field validation remains outstanding.</strong>`;
  const d=summary.diagnostics;
  const checks=[{text:`${summary.valid_runs}/${summary.completed_runs} valid runs`,pass:summary.valid_runs===summary.completed_runs},...['collisions','teleports','conflicting_green_steps'].map((k,i)=>{const n=d.reduce((a,r)=>a+r[k],0);return{text:`${n} ${['simulated collisions','teleports','conflicting greens'][i]}`,pass:n===0}})];
  $('validation').innerHTML=checks.map(x=>`<span class="check"><span class="${x.pass?'pass':'fail'}">${x.pass?'✓':'×'}</span>${x.text}</span>`).join('');
}
let comparisonRequest=0;
async function loadComparison(){
  const request=++comparisonRequest;
  state.loading=true;$('status').textContent='Loading synchronized replay…';
  const available=state.summary.replays[state.scenario];
  for(const option of $('controller').options)option.disabled=!available[option.value];
  if(!available[state.controller])state.controller=Object.keys(available).find(c=>c!=='fixed');
  $('controller').value=state.controller;
  try{
    if(!available.fixed||!available[state.controller])throw new Error('Paired replay is still being prepared.');
    const [left,right]=await Promise.all([replay(available.fixed),replay(available[state.controller])]);
    if(request!==comparisonRequest)return;
    [state.left,state.right]=[left,right];
    if(state.left.result.demand_sha256!==state.right.result.demand_sha256)throw new Error('The replay schedules do not match.');
    $('timeline').max=state.left.result.horizon_s;state.t=Math.min(state.t,state.left.result.horizon_s-.3);
    const e=state.right.result.execution;
    $('latency').textContent=['jev','bounded-jev','plan-jev'].includes(state.controller)?`Request p95 ${fmt(e.latency_p95_s*1000,0)} ms`:state.controller==='library-fixed'?'One tuned plan':'Observed road state';
    $('status').textContent=state.summary.status!=='complete'?`${state.summary.completed_runs}/${state.summary.expected_runs} runs available`:state.summary.scenario_notes?.[state.scenario]||(state.scenario==='surge'?'Demand increases by 50% during minutes 5:30–10:30.':'');
    table();decision();
  }catch(error){if(request===comparisonRequest)$('status').textContent=error.message;}finally{if(request===comparisonRequest)state.loading=false;}
}
$('study').addEventListener('change',()=>loadStudy($('study').value));
$('scenario').addEventListener('change',()=>{state.scenario=$('scenario').value;state.selected=null;loadComparison();});
$('controller').addEventListener('change',()=>{state.controller=$('controller').value;loadComparison();});
$('play').addEventListener('click',()=>{state.playing=!state.playing;$('play').textContent=state.playing?'Pause':'Play';$('play').setAttribute('aria-label',state.playing?'Pause replay':'Play replay');});
$('timeline').addEventListener('input',()=>{state.t=+$('timeline').value;decision();});
$('speed').addEventListener('change',()=>state.speed=+$('speed').value);
$('details-button').addEventListener('click',()=>{$('details').hidden=!$('details').hidden;$('details-button').setAttribute('aria-expanded',String(!$('details').hidden));if(!$('details').hidden)$('details').scrollIntoView({behavior:'smooth',block:'start'});});
$('right-canvas').addEventListener('click',event=>{
  if(!state.right)return;const canvas=$('right-canvas'),rect=canvas.getBoundingClientRect(),tr=transform(canvas,state.right.network),x=event.clientX-rect.left,y=event.clientY-rect.top;
  const nodes=state.right.network.nodes.filter(n=>n.controlled).map(n=>{const p=tr.point(n.x,n.y);return{id:n.id,d:Math.hypot(p[0]-x,p[1]-y)}}).sort((a,b)=>a.d-b.d);
  if(nodes[0]?.d<25){state.selected=nodes[0].id;decision();}
});
let last=performance.now(),metricTime=0;
function animate(now){
  const elapsed=Math.min(.1,(now-last)/1000);last=now;
  if(state.playing&&!state.loading&&state.left){state.t+=elapsed*state.speed;if(state.t>state.left.result.horizon_s-1)state.t=0;}
  draw($('left-canvas'),state.left);draw($('right-canvas'),state.right);
  if(now-metricTime>150){metricTime=now;updateMetrics('left',state.left);updateMetrics('right',state.right);$('time').textContent=clock(state.t);$('phase').textContent=state.t<180?'Warm-up':state.t<780?'Evaluation':'Drain';$('timeline').value=state.t;decision();}
  requestAnimationFrame(animate);
}
let studyRequest=0;
async function loadStudy(study){
  const request=++studyRequest;++comparisonRequest;state.loading=true;
  try{
    const response=await fetch(study==='coordinated'?'data/coordinated-summary.json':'data/summary.json',{cache:'no-store'});
    if(!response.ok)throw new Error('Benchmark data is not available.');
    const summary=await response.json();if(request!==studyRequest)return;
    state.summary=summary;state.study=study;state.scenario='am';state.selected=null;state.left=null;state.right=null;
    state.controller=study==='coordinated'?'plan-jev':'bounded-jev';
    const scenarios=summary.scenario_names||{am:'Weekday morning',surge:'Morning + 50% surge'};
    $('study').value=study;$('scenario').replaceChildren(...Object.entries(scenarios).map(([id,name])=>new Option(name,id)));
    $('controller').replaceChildren(...Object.entries(summary.names).filter(([c])=>c!=='fixed').reverse().map(([id,name])=>new Option(name,id)));
    const seed=summary.replay_seed||11;$('run-label').textContent=`Recorded run · seed ${seed}`;$('caption-seed').textContent=`seed ${seed}`;
    $('report-download').href=summary.downloads?.report||'data/benchmark-report.md';$('runs-download').href=summary.downloads?.runs||'data/runs.json';
    $('original-method').hidden=study!=='original';$('coordinated-method').hidden=study!=='coordinated';
    await loadComparison();
  }catch(error){if(request===studyRequest){state.loading=false;$('status').textContent=error.message;}}
}
async function initialize(){
  await loadStudy(state.study);
  requestAnimationFrame(animate);
}
initialize();
// Public, read-only state is useful to verify the viewer without inspecting private API data.
window.trafficLab={getState:()=>({study:state.study,scenario:state.scenario,controller:state.controller,time:state.t,playing:state.playing,loaded:!!state.left&&!!state.right,selected:state.selected,completedRuns:state.summary?.completed_runs}),seek:t=>{state.t=Math.max(0,Math.min(+t,state.left?.result.horizon_s||960));state.playing=false;$('play').textContent='Play';}};
if(document.modelContext?.registerTool){
  const lifecycle=new AbortController();
  const tools=[{
    name:'inspect_traffic_benchmark',title:'Inspect traffic benchmark',description:'Read the displayed benchmark results and current replay selection. Does not run simulations or call Jev.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true,untrustedContentHint:false},
    execute:input=>{if(!input||Object.keys(input).length)throw new Error('No arguments expected.');return{view:window.trafficLab.getState(),results:state.summary?.groups[state.scenario],paired:state.summary?.paired[state.scenario]};}
  },{
    name:'configure_traffic_replay',title:'Configure traffic replay',description:'Choose a recorded traffic scenario and controller, then pause both synchronized views at the requested elapsed time. No new inference is performed.',inputSchema:{type:'object',properties:{study:{type:'string',enum:['coordinated','original']},scenario:{type:'string',enum:['am','surge','shift']},controller:{type:'string',enum:['plan-jev','plan-numeric','library-fixed','bounded-jev','jev','pressure','actuated']},time_seconds:{type:'number',minimum:0,maximum:959}},required:['study','scenario','controller','time_seconds'],additionalProperties:false},annotations:{readOnlyHint:false,untrustedContentHint:false},
    async execute(input){
      if(!input||!['coordinated','original'].includes(input.study)||!['am','surge','shift'].includes(input.scenario)||!['plan-jev','plan-numeric','library-fixed','bounded-jev','jev','pressure','actuated'].includes(input.controller)||typeof input.time_seconds!=='number'||!Number.isFinite(input.time_seconds)||input.time_seconds<0||input.time_seconds>959||Object.keys(input).some(k=>!['study','scenario','controller','time_seconds'].includes(k)))throw new Error('Invalid replay configuration.');
      if(state.study!==input.study)await loadStudy(input.study);
      if(!state.summary?.replays[input.scenario]?.[input.controller])throw new Error('That recorded controller is not available yet.');
      state.scenario=input.scenario;state.controller=input.controller;$('scenario').value=state.scenario;state.selected=null;
      await loadComparison();window.trafficLab.seek(input.time_seconds);$('play').setAttribute('aria-label','Play replay');
      await new Promise(resolve=>requestAnimationFrame(resolve));return window.trafficLab.getState();
    }
  }];
  for(const tool of tools){try{Promise.resolve(document.modelContext.registerTool(tool,{signal:lifecycle.signal})).catch(()=>{});}catch{}}
  window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
}
