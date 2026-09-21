"""Run one real SUMO replication. Jev is forbidden in accelerated mode."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET

import libsumo as sim
import numpy as np
from dotenv import load_dotenv

from .controllers import SignalGuard,JevWorker,pressure_choice,actuated_choice,CADENCE
from .scenario import ROOT,SCENARIO,build_demand


def quantile(values,q): return float(np.quantile(values,q)) if values else None


def observations(meta,guards,t):
    output={}
    for ident,g in guards.items():
        if not g.eligible(t): continue
        node=meta['junctions'][ident]; approaches={}
        for kind in ('avenue','cross'):
            edge=node['incoming'][kind]; queue=sim.edge.getLastStepHaltingNumber(edge)
            n=sim.edge.getLastStepVehicleNumber(edge)
            counts=node['counts'][0:2] if kind=='avenue' else node['counts'][2:4]
            pressure=queue; down=[]
            for outkind,f in zip((kind,'cross' if kind=='avenue' else 'avenue'),counts):
                out=node['outgoing'][outkind]
                downstream=sim.edge.getLastStepHaltingNumber(out)
                occupancy=sim.edge.getLastStepVehicleNumber(out)/max(1,sim.lane.getLength(out+'_0')*meta['edges'][out]['lanes']/7.5)
                pressure-=f/sum(counts)*downstream
                down.append({'direction':outkind,'queued':downstream,'storage_fraction':round(occupancy,3)})
            approaches[kind]={'queued':queue,'vehicles':n,'pressure':round(pressure,3),'downstream':down}
        output[ident]={'current_green':g.group,'green_age_s':round(g.age(t),2),'epoch':g.epoch,'approaches':approaches}
    return output


def summarise_trips(path,demand,horizon,measurement_end):
    by_id={v['id']:v for v in demand['vehicles']}
    trips={x.get('id'):x.attrib for x in ET.parse(path).findall('tripinfo')}
    counts={'requested':demand['requested'],'admitted':0,'completed':0,'running':0,'pending':0}
    rows=[]
    for ident,v in by_id.items():
        tr=trips.get(ident,{})
        admitted=float(tr.get('depart',-1))>=0
        complete=float(tr.get('arrival',-1))>=0
        counts['admitted']+=admitted; counts['completed']+=complete
        counts['running']+=admitted and not complete; counts['pending']+=not admitted
        if not v['cohort']: continue
        entry=float(tr['departDelay']) if admitted else horizon-v['depart']
        loss=max(0,float(tr.get('timeLoss',0))) if admitted else 0.0
        duration=float(tr['duration'])+entry if complete else None
        rows.append({'id':ident,'admitted':admitted,'completed':complete,'completed_by_demand_end':complete and float(tr['arrival'])<=measurement_end,'delay':entry+loss,'entry_delay':entry,'onroad_loss':loss,'travel_time':duration,'waiting':max(0,float(tr.get('waitingTime',0))),'stops':max(0,float(tr.get('waitingCount',0)))})
    n=len(rows); completed=[r for r in rows if r['completed']]
    assert counts['requested']==counts['completed']+counts['running']+counts['pending']
    return {
        'conservation':counts,'requested_trips':n,'admitted_trips':sum(r['admitted'] for r in rows),
        'completed_trips':len(completed),'completed_by_demand_end':sum(r['completed_by_demand_end'] for r in rows),
        'unfinished_trips':n-len(completed),'uninserted_trips':sum(not r['admitted'] for r in rows),
        'mean_delay_s':sum(r['delay'] for r in rows)/max(n,1),
        'total_delay_vehicle_h':sum(r['delay'] for r in rows)/3600,
        'total_entry_delay_vehicle_h':sum(r['entry_delay'] for r in rows)/3600,
        'mean_completed_travel_s':float(np.mean([r['travel_time'] for r in completed])) if completed else None,
        'p95_completed_travel_s':quantile([r['travel_time'] for r in completed],.95),
        'mean_waiting_s':sum(r['waiting'] for r in rows)/max(n,1),
        'mean_stops':sum(r['stops'] for r in rows)/max(n,1),
        'completion_fraction':len(completed)/max(n,1),
    }


def run(controller='fixed',seed=1,scenario='am',warmup=180,duration=600,drain=120,step=.2,
        realtime=False,replay=False,directory=SCENARIO,out_root=None,multiplier=1.0,tag=None):
    load_dotenv(ROOT/'.env')
    if controller=='jev' and not realtime: raise ValueError('Live Jev must run at 1 simulated second per wall second.')
    if controller not in ('fixed','actuated','pressure','jev'): raise ValueError(controller)
    directory=Path(directory); meta=json.loads((directory/'network.json').read_text())
    stem=build_demand(seed,scenario,warmup,duration,directory,multiplier)
    demand=json.loads(stem.with_suffix('.json').read_text())
    identity=tag or f'{scenario}_{controller}_seed{seed}_{warmup}_{duration}_{drain}'
    out=Path(out_root or ROOT/'results/raw')/identity; out.mkdir(parents=True,exist_ok=True)
    worker=JevWorker() if controller=='jev' else None
    args=['sumo','-n',str(directory/'network.net.xml'),'-r',str(stem.with_suffix('.rou.xml')),
          '--step-length',str(step),'--seed',str(seed),'--time-to-teleport','-1','--collision.action','warn',
          '--tripinfo-output',str(out/'trips.xml'),'--tripinfo-output.write-unfinished','true',
          '--tripinfo-output.write-undeparted','true','--no-step-log','true','--duration-log.disable','true',
          '--log',str(out/'sumo.log'),'--error-log',str(out/'sumo-errors.log')]
    sim.start(args)
    guards={k:SignalGuard(v['states']) for k,v in meta['junctions'].items()} if controller!='fixed' else {}
    for k,g in guards.items(): sim.trafficlight.setRedYellowGreenState(k,g.state())
    horizon=warmup+duration+drain; steps=round(horizon/step); cadence_ticks=round(CADENCE/step)
    frame_ticks=max(1,round(1/step)); series_ticks=max(1,round(5/step))
    frames=[]; series=[]; actions=[]; latest={}; arrived=set(); requested={v['id']:v for v in demand['vehicles']}
    queue_sum=0.0; samples=0; max_queue=0; spill_seconds=0.0; collision_count=0; teleports=0
    fallback=0; rejected=0; safety_violations=0; latencies=[]; clock_lags=[]; conventional_pending=[]
    movement_counts={k:[0,0,0,0] for k in meta['junctions']}; route_indices={}
    run_start=time.perf_counter(); t=0
    try:
        for tick in range(steps):
            t=tick*step
            if realtime:
                target=run_start+t; remaining=target-time.perf_counter()
                if remaining>0: time.sleep(remaining)
                clock_lags.append(max(0,time.perf_counter()-target))
            # Timed transitions continue even while the inference worker is occupied.
            for ident,g in guards.items(): sim.trafficlight.setRedYellowGreenState(ident,g.update(t))
            if worker:
                for kind,p,record in worker.poll(t):
                    for ident,old in p['observations'].items():
                        if kind=='fallback':
                            fresh=observations(meta,guards,t).get(ident)
                            action=pressure_choice(fresh) if fresh else 'hold'; fallback+=1
                        else:
                            action=record['answers'].get(ident,{}).get('choice','invalid')
                        accepted=guards[ident].apply(action,t,old['epoch'])
                        rejected+=not accepted
                        actions.append({'t':round(t,3),'junction':ident,'action':action,'accepted':accepted,'source':kind,'observed_t':p['observed_sim_s']})
            for due,ident,action,epoch in conventional_pending[:]:
                if t+1e-8>=due:
                    accepted=guards[ident].apply(action,t,epoch)
                    actions.append({'t':round(t,3),'junction':ident,'action':action,'accepted':accepted,'source':controller,'observed_t':due-step})
                    conventional_pending.remove((due,ident,action,epoch))
            if guards and tick%cadence_ticks==0:
                observation_started=time.perf_counter(); obs=observations(meta,guards,t)
                if worker: worker.dispatch(obs,t,observation_started)
                else:
                    choose=pressure_choice if controller=='pressure' else actuated_choice
                    proposed=[(k,choose(o),o['epoch']) for k,o in obs.items()]
                    elapsed=time.perf_counter()-observation_started; latencies.append(elapsed)
                    delay=max(step,math.ceil(elapsed/step)*step)
                    conventional_pending.extend((t+delay,k,a,e) for k,a,e in proposed)
            for ident,g in guards.items(): sim.trafficlight.setRedYellowGreenState(ident,g.state())
            for ident,node in meta['junctions'].items():
                s=sim.trafficlight.getRedYellowGreenState(ident)
                a=node['states']['avenue']; c=node['states']['cross']
                if any(x in 'Gg' and y=='G' for x,y in zip(s,a)) and any(x in 'Gg' and y=='G' for x,y in zip(s,c)):
                    safety_violations+=1
            sim.simulationStep()
            t=(tick+1)*step
            collision_count+=sim.simulation.getCollidingVehiclesNumber()
            teleports+=sim.simulation.getStartingTeleportNumber()
            arrived.update(sim.simulation.getArrivedIDList())
            for v in sim.vehicle.getIDList():
                index=sim.vehicle.getRouteIndex(v); previous=route_indices.get(v,index)
                if warmup<=t<warmup+duration and index>previous:
                    route=requested[v]['route']
                    for r in range(previous,index):
                        before,after=route[r:r+2]; junction=meta['edges'][before]['to']
                        if junction in movement_counts:
                            kind=meta['edges'][before]['kind']; is_turn=kind!=meta['edges'][after]['kind']
                            movement_counts[junction][(0 if kind=='avenue' else 2)+int(is_turn)]+=1
                route_indices[v]=index
            queue=sum(sim.edge.getLastStepHaltingNumber(e) for e in meta['edges'])
            if warmup<=t<warmup+duration:
                samples+=1; queue_sum+=queue; max_queue=max(max_queue,queue)
                for e,info in meta['edges'].items():
                    storage=sim.lane.getLength(e+'_0')*info['lanes']/7.5
                    if sim.edge.getLastStepVehicleNumber(e)>=.8*storage and sim.edge.getLastStepHaltingNumber(e)>0: spill_seconds+=step
            if tick%frame_ticks==0 or tick%series_ticks==0:
                vehicles=[]
                for v in sim.vehicle.getIDList():
                    latest[v]={'loss':sim.vehicle.getTimeLoss(v),'entry':sim.vehicle.getDepartDelay(v)}
                    if replay:
                        x,y=sim.vehicle.getPosition(v)
                        vehicles.append([int(v[1:]),round(x,1),round(y,1),round(sim.vehicle.getAngle(v),1),round(sim.vehicle.getSpeed(v),2),1 if sim.vehicle.getTypeID(v).startswith('truck') else 0])
                cohort=[v for v in demand['vehicles'] if v['cohort'] and v['depart']<=t]
                loss=sum(latest[v['id']]['loss']+latest[v['id']]['entry'] if v['id'] in latest else t-v['depart'] for v in cohort)
                live={'queued':queue,'active':sim.vehicle.getIDCount(),'completed':sum(v['id'] in arrived for v in cohort),'requested':len(cohort),'mean_delay_s':round(loss/max(len(cohort),1),2)}
                if replay and tick%frame_ticks==0:
                    frames.append({'t':round(t,2),'vehicles':vehicles,'signals':{k:sim.trafficlight.getRedYellowGreenState(k) for k in meta['junctions']},'metrics':live})
                if tick%series_ticks==0: series.append({'t':round(t,2),**live})
            if tick and tick%round(60/step)==0:
                print(json.dumps({'run':identity,'sim_s':round(t),'queued':queue,'active':sim.vehicle.getIDCount(),'api_requests':len(worker.records) if worker else 0,'api_errors':sum(bool(r.get('error')) for r in worker.records) if worker else 0}),flush=True)
    finally:
        sim.close()
        if worker: worker.close()
    elapsed=time.perf_counter()-run_start
    metrics=summarise_trips(out/'trips.xml',demand,horizon,warmup+duration)
    metrics.update(mean_queue_vehicles=queue_sum/max(samples,1),peak_queue_vehicles=max_queue,
                   congested_link_seconds=spill_seconds,colliding_vehicle_events=collision_count,teleports=teleports,
                   conflicting_green_steps=safety_violations)
    logs=worker.records if worker else []
    if worker: latencies=[r['latency_s'] for r in logs]
    errors=sum(bool(r.get('error')) for r in logs)
    applied=sum(a['source']=='response' and a['accepted'] for a in actions)
    execution={'mode':'realtime' if realtime else 'accelerated_conventional','wall_s':elapsed,'step_s':step,
               'latency_p50_s':quantile(latencies,.5),'latency_p95_s':quantile(latencies,.95),'latency_p99_s':quantile(latencies,.99),
               'clock_lag_p99_s':quantile(clock_lags,.99),'max_clock_lag_s':max(clock_lags,default=0),
               'requests':len(logs),'api_errors':errors,'fallback_actions':fallback,'rejected_actions':rejected,
               'model_actions_applied':applied,'forced_max_green_transitions':sum(g.forced for g in guards.values()),
               'deadline_misses':sum(r.get('expired',False) for r in logs),'input_tokens':sum(r.get('usage',{}).get('input_tokens',0) for r in logs)}
    valid=collision_count==0 and teleports==0 and safety_violations==0 and (not realtime or max(clock_lags,default=0)<step)
    if worker and (applied==0 or errors>max(2,len(logs)*.1)): valid=False
    result={'id':identity,'controller':controller,'seed':seed,'scenario':scenario,'warmup_s':warmup,'measurement_s':duration,'drain_s':drain,'horizon_s':horizon,'demand_sha256':demand['sha256'],'network_sha256':hashlib.sha256((directory/'network.net.xml').read_bytes()).hexdigest(),'sumo_version':sim.getVersion()[1],'model':os.getenv('JEV_MODEL','jev-1.13.0') if worker else None,'valid':valid,'metrics':metrics,'execution':execution,'movement_counts':movement_counts,'series':series}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'actions.json').write_text(json.dumps(actions)+'\n')
    if worker: (out/'jev_requests.json').write_text(json.dumps(logs)+'\n')
    if replay:
        with gzip.open(out/'replay.json.gz','wt') as f: json.dump({'result':result,'network':meta['visual'],'junctions':meta['junctions'],'frames':frames,'actions':actions},f,separators=(',',':'))
    print(json.dumps({'finished':identity,'valid':valid,'metrics':metrics,'execution':execution}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--controller',choices=['fixed','actuated','pressure','jev'],default='fixed'); p.add_argument('--seed',type=int,default=1); p.add_argument('--scenario',choices=['am','surge'],default='am'); p.add_argument('--warmup',type=int,default=180); p.add_argument('--duration',type=int,default=600); p.add_argument('--drain',type=int,default=120); p.add_argument('--step',type=float,default=.2); p.add_argument('--realtime',action='store_true'); p.add_argument('--replay',action='store_true'); p.add_argument('--directory',type=Path,default=SCENARIO); p.add_argument('--out-root',type=Path); p.add_argument('--multiplier',type=float,default=1); p.add_argument('--tag'); args=p.parse_args(); run(**vars(args))
