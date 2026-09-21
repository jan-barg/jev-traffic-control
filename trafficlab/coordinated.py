"""Corridor plan selection with observed history, a fluid forecast and fixed anchors."""
from collections import deque
import math
import numpy as np
from .controllers import JevWorker

CYCLE=90.0
CADENCE=90.0
FIRST_DECISION=60.0
INSTALL_DELAY=3.0
HORIZON=180
DT=2


def candidate_plans(meta):
    plans={f'g{g}':{'label':f'{g}/{82-g} s avenue/cross',
                    'greens':{k:g for k in meta['junctions']}} for g in (30,38,46,52,60)}
    for scale,name in ((1.0,'flow'),(1.5,'cross_flow')):
        greens={}
        for key,node in meta['junctions'].items():
            a=sum(node['counts'][:2])/meta['edges'][node['incoming']['avenue']]['lanes']
            c=sum(node['counts'][2:])*scale
            greens[key]=max(22,min(60,2*round(41*a/(a+c))))
        plans[name]={'label':'Local volume-weighted splits'+(' with cross-street emphasis' if scale>1 else ''),'greens':greens}
    return plans


class PlanScheduler:
    """Change green durations only at a local cycle start; keep its original anchor."""
    def __init__(self,sim,meta,plans,initial='g52',step=.2):
        self.sim=sim;self.meta=meta;self.plans=plans;self.step=step
        assert initial in plans and 'g52' in plans
        assert all(set(p['greens'])==set(meta['junctions']) and all(22<=g<=60 for g in p['greens'].values()) for p in plans.values())
        self.desired=initial;self.install_after=0.;self.decision_id=None
        self.signals={};self.events=[];self.installs=[];self.violations=[];self.actions=[]
        for key in meta['junctions']:
            durations=[p.duration for p in sim.trafficlight.getAllProgramLogics(key)[0].phases]
            assert durations==[52,3,1,30,3,1]
            phase=sim.trafficlight.getPhase(key)
            anchor=sim.trafficlight.getNextSwitch(key)-sum(durations[:phase+1])
            self.signals[key]={'anchor':anchor,'phase':phase,'since':None,'green':52,'plan':'g52','compensated':False,'decision_id':None}

    def accept(self,plan,t,observed_t,source):
        accepted=plan in self.plans and t-observed_t<=2.200001
        a={'t':round(t,3),'junction':'corridor','action':plan,'accepted':accepted,'source':source,'observed_t':observed_t,'install_after_s':observed_t+INSTALL_DELAY}
        if accepted:
            self.desired=plan;self.install_after=observed_t+INSTALL_DELAY;self.decision_id=len(self.actions)
        self.actions.append(a)
        return accepted

    def tick(self,t):
        for key,s in self.signals.items():
            phase=self.sim.trafficlight.getPhase(key)
            cycle=math.floor((t-s['anchor']+1e-7)/CYCLE)
            start=s['anchor']+cycle*CYCLE
            if phase!=s['phase']:
                if s['since'] is not None:
                    expected=[s['green'],3,1,82-s['green'],3,1][s['phase']]
                    if abs(t-s['since']-expected)>self.step+1e-6:
                        self.violations.append({'junction':key,'t':t,'phase':s['phase'],'duration':t-s['since'],'expected':expected})
                if phase==0:
                    if abs(t-start)>self.step+1e-6:self.violations.append({'junction':key,'anchor_error':t-start})
                    if t+1e-7>=self.install_after:
                        s['plan']=self.desired;s['green']=self.plans[self.desired]['greens'][key]
                        s['decision_id']=self.decision_id
                    s['compensated']=False
                    if s['green']!=52:self.sim.trafficlight.setPhaseDuration(key,start+s['green']-t)
                    self.installs.append({'t':round(t,3),'junction':key,'cycle':cycle,'cycle_start_s':start,'plan':s['plan'],'avenue_green_s':s['green'],'cross_green_s':82-s['green'],'decision_id':s['decision_id']})
                self.events.append({'t':round(t,3),'junction':key,'phase':phase,'cycle':cycle,'cycle_start_s':start,'green':s['green'],'plan':s['plan']})
                s['phase']=phase;s['since']=t
            if phase==3 and s['green']!=52 and not s['compensated']:
                self.sim.trafficlight.setPhaseDuration(key,start+86-t)
                s['compensated']=True


class TrafficHistory:
    def __init__(self,sim,meta):
        self.sim=sim;self.meta=meta;self.samples=deque();self.previous={k:set() for k in meta['edges']}
        self.length={k:sim.lane.getLength(k+'_0') for k in meta['edges']}
        self.storage={k:self.length[k]*e['lanes']/7.5 for k,e in meta['edges'].items()}

    def sample(self,t):
        entries={};queues={}
        for key in self.meta['edges']:
            current=set(self.sim.edge.getLastStepVehicleIDs(key))
            entries[key]=len(current-self.previous[key]);self.previous[key]=current
            queues[key]=self.sim.edge.getLastStepHaltingNumber(key)
        self.samples.append((t,entries,queues))
        while self.samples and self.samples[0][0]<t-120:self.samples.popleft()

    def snapshot(self,t):
        recent=[s for s in self.samples if s[0]>t-60]
        prior=[s for s in self.samples if s[0]<=t-60]
        rates={e:sum(s[1][e] for s in recent)/max(1,len(recent)) for e in self.meta['edges']}
        old={e:sum(s[1][e] for s in prior)/max(1,len(prior)) for e in self.meta['edges']}
        queues={};moving={};observed=[]
        for key,e in self.meta['edges'].items():
            queues[key]=0;moving[key]=[]
            for v in self.sim.edge.getLastStepVehicleIDs(key):
                speed=self.sim.vehicle.getSpeed(v)
                if speed<.1:queues[key]+=1
                else:
                    remaining=max(0,self.length[key]-self.sim.vehicle.getLanePosition(v))
                    moving[key].append(min(90,remaining/max(2,speed)))
            if e['to'] in self.meta['junctions']:
                observed.append({'junction':e['to'],'approach':e['kind'],'queued':queues[key],
                                 'vehicles':queues[key]+len(moving[key]),'arrivals_last_minute':round(60*rates[key],1),
                                 'arrivals_previous_minute':round(60*old[key],1),'storage_fraction':round((queues[key]+len(moving[key]))/self.storage[key],2)})
        return {'t':t,'rates':rates,'queues':queues,'moving':moving,'observations':observed}


def forecast(snapshot,meta,scheduler,history,plan):
    """Conservation-based network queue model. No access to scheduled future vehicles."""
    edges=list(meta['edges']);idx={e:i for i,e in enumerate(edges)};n=len(edges);steps=HORIZON//DT
    q=np.array([snapshot['queues'][e] for e in edges],dtype=float)
    pipe=np.zeros((steps+50,n));storage=np.array([history.storage[e] for e in edges])
    exit_edges=np.array([meta['edges'][e]['to'] not in meta['junctions'] for e in edges])
    boundary=np.array([snapshot['rates'][e] if meta['edges'][e]['from'] not in meta['junctions'] else 0 for e in edges])*DT
    delays=np.array([max(1,round(history.length[e]/9/DT)) for e in edges])
    pending=np.zeros(n)
    for e in edges:
        for eta in snapshot['moving'][e]:pipe[min(len(pipe)-1,int(eta/DT)),idx[e]]+=1;pending[idx[e]]+=1
    routes=[];anchors=np.zeros(n);greens=np.zeros(n);next_start=np.zeros(n);candidate=np.zeros(n);capacities=np.zeros(n)
    for e in edges:
        i=idx[e];info=meta['edges'][e]
        if exit_edges[i]:routes.append([]);continue
        key=info['to'];node=meta['junctions'][key];s=scheduler.signals[key]
        anchors[i]=s['anchor'];greens[i]=s['green'];candidate[i]=plan['greens'][key]
        next_start[i]=s['anchor']+(math.floor((snapshot['t']+INSTALL_DELAY-s['anchor'])/90)+1)*90
        counts=node['counts'][:2] if info['kind']=='avenue' else node['counts'][2:]
        kinds=(info['kind'],'cross' if info['kind']=='avenue' else 'avenue')
        routes.append([(idx[node['outgoing'][kind]],count/sum(counts)) for kind,count in zip(kinds,counts)])
        capacities[i]=.48*info['lanes']*DT
    total=0.;peak=float(q.sum());blocked=0.
    for k in range(steps):
        pending-=pipe[k];q+=pipe[k];q[exit_edges]=0
        for i,mass in enumerate(boundary):
            if mass:pipe[k+delays[i],i]+=mass;pending[i]+=mass
        when=snapshot['t']+k*DT;age=(when-anchors)%90;g=np.where(when>=next_start,candidate,greens)
        active=np.array([(age[i]<g[i]) if meta['edges'][e]['kind']=='avenue' else (g[i]+4<=age[i]<86) for i,e in enumerate(edges)])
        flow=np.minimum(q,capacities*active);available=np.maximum(0,storage-q-pending)
        # Allocate downstream space deterministically; no mass is removed when blocked.
        for i,turns in enumerate(routes):
            if not turns:continue
            amount=flow[i]
            for j,fraction in turns:
                if fraction and not exit_edges[j]:amount=min(amount,available[j]/fraction)
            blocked+=max(0,flow[i]-amount)*DT
            q[i]-=amount
            for j,fraction in turns:
                if exit_edges[j]:continue
                mass=amount*fraction;available[j]-=mass;pending[j]+=mass;pipe[k+delays[j],j]+=mass
        total+=q.sum()*DT;peak=max(peak,float(q.sum()))
    # Terminal queue discourages hiding delay beyond the forecast horizon.
    objective=total+30*float(q.sum())
    return {'predicted_queue_delay_vehicle_s':round(float(total),1),'terminal_queue_vehicles':round(float(q.sum()),1),
            'peak_queue_vehicles':round(peak,1),'blocked_discharge_vehicle_s':round(float(blocked),1),'objective':round(float(objective),1)}


def decision_state(t,history,scheduler,plans):
    snapshot=history.snapshot(t)
    predictions={key:{'label':p['label'],'avenue_green_s':p['greens'],**forecast(snapshot,history.meta,scheduler,history,p)} for key,p in plans.items()}
    return {'corridor':{'epoch':int(t//CADENCE),'current_plan':scheduler.desired,'observed_sim_s':t,
            'forecast_horizon_s':HORIZON,'objective_definition':'Predicted total queue delay over 180 s plus 30 s per vehicle still queued; smaller is better.',
            'forecast_limitations':'Fluid approximation with recent observed boundary arrival rates, published turn shares, assumed discharge rates and finite storage. No future demand schedule.',
            'observed_approaches':snapshot['observations'],'candidate_plans':predictions}}


def numerical_choice(state):
    plans=state['corridor']['candidate_plans']
    return min(plans,key=lambda key:(plans[key]['objective'],key!='g52',key))


class CoordinatedJevWorker(JevWorker):
    def dispatch(self,state,t,wall_started):
        if self.future is not None:return False
        from typesafe_sdk import Choice
        plans=state['corridor']['candidate_plans']
        question=Choice(instructions=(
            'Select the coordinated plan for all 12 intersections using `corridor`. '
            'Minimize total vehicle delay across the entire network while avoiding persistent queues and blocked downstream links. '
            'Compare every candidate on equal terms. The current plan has no automatic preference. '
            'Use the supplied numerical forecasts, current queues and arrival trends. Lower forecast objective is better; '
            'the forecasts are approximations, so consider contrary observed evidence when relevant. '
            'Do not invent future traffic or calculate signal timings. Code preserves the 90-second cycle and original offsets, '
            'enforces green and clearance limits, and rolls the selected plan into each intersection at its next eligible cycle. '
            'These transition effects are included in the forecasts.'),
            criteria={key:f"{value['label']}; evaluate the corresponding entry in `corridor.candidate_plans.{key}`." for key,value in plans.items()})
        self.pending={'observed_sim_s':t,'wall_started':wall_started,'observations':state}
        self.expired=False;self.future=self.pool.submit(self._call,state,{'corridor':question})
        return True
