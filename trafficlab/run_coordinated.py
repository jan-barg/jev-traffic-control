"""Paired coordinated-plan experiment; original runners and evidence stay unchanged."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,os,time
from pathlib import Path
import libsumo as sim
from dotenv import load_dotenv
from .run import quantile,summarise_trips
from .scenario import ROOT,SCENARIO
from .plan_scenario import build_profile_demand
from .coordinated import PlanScheduler,TrafficHistory,CoordinatedJevWorker,decision_state,numerical_choice,candidate_plans,CADENCE,FIRST_DECISION

def run(controller='plan-jev',seed=1,scenario='am',warmup=180,duration=600,drain=120,step=.2,
        realtime=False,replay=False,directory=SCENARIO,out_root=None,multiplier=1,tag=None,static_plan=None):
    load_dotenv(ROOT/'.env')
    if controller=='plan-jev' and not realtime: raise ValueError('Live Jev requires real time.')
    if controller not in ('fixed','library-fixed','plan-numeric','plan-jev','development-static'):raise ValueError(controller)
    directory=Path(directory); meta=json.loads((directory/'network.json').read_text())
    stem=build_profile_demand(seed,scenario,warmup,duration,directory,multiplier)
    demand=json.loads(stem.with_suffix('.json').read_text())
    identity=tag or f'{scenario}_{controller}_seed{seed}_{warmup}_{duration}_{drain}'
    out=Path(out_root or ROOT/'results/raw')/identity; out.mkdir(parents=True,exist_ok=True)
    library_path=ROOT/'results/plan_library.json'
    library=json.loads(library_path.read_text()) if library_path.exists() else None
    plans=library['plans'] if library and controller!='development-static' else candidate_plans(meta)
    initial=static_plan or (library['best_static'] if controller=='library-fixed' else 'g52')
    worker=CoordinatedJevWorker() if controller=='plan-jev' else None
    dynamic=controller in ('plan-jev','plan-numeric')
    args=['sumo','-n',str(directory/'network.net.xml'),'-r',str(stem.with_suffix('.rou.xml')),
          '--step-length',str(step),'--seed',str(seed),'--time-to-teleport','-1','--collision.action','warn',
          '--tripinfo-output',str(out/'trips.xml'),'--tripinfo-output.write-unfinished','true',
          '--tripinfo-output.write-undeparted','true','--no-step-log','true','--duration-log.disable','true',
          '--log',str(out/'sumo.log'),'--error-log',str(out/'sumo-errors.log')]
    sim.start(args)
    coordinator=PlanScheduler(sim,meta,plans,initial,step)
    history=TrafficHistory(sim,meta) if dynamic else None
    decision_logs=[]
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
            coordinator.tick(t)
            if history and tick%round(1/step)==0:history.sample(t)
            if worker:
                for kind,p,record in worker.poll(t):
                    if kind=='fallback':action=coordinator.desired;fallback+=1
                    else:action=record['answers'].get('corridor',{}).get('choice','invalid')
                    accepted=coordinator.accept(action,t,p['observed_sim_s'],kind)
                    rejected+=not accepted
            for due,action,observed in conventional_pending[:]:
                if t+1e-8>=due:
                    accepted=coordinator.accept(action,t,observed,'numerical')
                    rejected+=not accepted;conventional_pending.remove((due,action,observed))
            if dynamic and t>=FIRST_DECISION and (tick-round(FIRST_DECISION/step))%cadence_ticks==0:
                observation_started=time.perf_counter();obs=decision_state(t,history,coordinator,plans)
                numerical=numerical_choice(obs)
                decision_logs.append({'observed_sim_s':t,'numerical_choice':numerical,'state':obs})
                if worker:worker.dispatch(obs,t,observation_started)
                else:
                    elapsed=time.perf_counter()-observation_started;latencies.append(elapsed)
                    conventional_pending.append((t+max(step,math.ceil(elapsed/step)*step),numerical,t))
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
    actions=coordinator.actions
    logs=worker.records if worker else []
    if worker: latencies=[r['latency_s'] for r in logs]
    errors=sum(bool(r.get('error')) for r in logs)
    applied=sum(a['source']=='response' and a['accepted'] for a in actions)
    execution={'mode':'realtime' if realtime else 'accelerated_conventional','wall_s':elapsed,'step_s':step,
               'latency_p50_s':quantile(latencies,.5),'latency_p95_s':quantile(latencies,.95),'latency_p99_s':quantile(latencies,.99),
               'clock_lag_p99_s':quantile(clock_lags,.99),'max_clock_lag_s':max(clock_lags,default=0),
               'requests':len(logs),'api_errors':errors,'fallback_actions':fallback,'rejected_actions':rejected,
               'model_actions_applied':applied,'forced_max_green_transitions':0,
               'deadline_misses':sum(r.get('expired',False) for r in logs),'input_tokens':sum(r.get('usage',{}).get('input_tokens',0) for r in logs)}
    metrics.update(plan_timing_violations=len(coordinator.violations))
    valid=not coordinator.violations and collision_count==0 and teleports==0 and safety_violations==0 and (not realtime or max(clock_lags,default=0)<step)
    if worker and (applied==0 or errors>max(2,len(logs)*.1)): valid=False
    result={'id':identity,'controller':controller,'seed':seed,'scenario':scenario,'warmup_s':warmup,'measurement_s':duration,'drain_s':drain,'horizon_s':horizon,'demand_sha256':demand['sha256'],'network_sha256':hashlib.sha256((directory/'network.net.xml').read_bytes()).hexdigest(),'sumo_version':sim.getVersion()[1],'model':os.getenv('JEV_MODEL','jev-1.13.0') if worker else None,'valid':valid,'metrics':metrics,'execution':execution,'movement_counts':movement_counts,'series':series,'initial_plan':initial,'plan_library':plans}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'plan_installs.json').write_text(json.dumps(coordinator.installs)+'\n')
    (out/'plan_forecasts.json').write_text(json.dumps(decision_logs)+'\n')
    (out/'signal_events.json').write_text(json.dumps(coordinator.events)+'\n')
    (out/'timing_violations.json').write_text(json.dumps(coordinator.violations)+'\n')
    (out/'actions.json').write_text(json.dumps(actions)+'\n')
    if worker: (out/'jev_requests.json').write_text(json.dumps(logs)+'\n')
    if replay:
        with gzip.open(out/'replay.json.gz','wt') as f: json.dump({'result':result,'network':meta['visual'],'junctions':meta['junctions'],'frames':frames,'actions':actions,'plan_installs':coordinator.installs},f,separators=(',',':'))
    print(json.dumps({'finished':identity,'valid':valid,'metrics':metrics,'execution':execution}),flush=True)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--seed',type=int,default=11);p.add_argument('--scenario',choices=['am','surge','shift','dev_cross','dev_avenue','dev_local'],default='am')
    p.add_argument('--warmup',type=int,default=180);p.add_argument('--duration',type=int,default=600);p.add_argument('--drain',type=int,default=180)
    p.add_argument('--step',type=float,default=.2);p.add_argument('--realtime',action='store_true');p.add_argument('--replay',action='store_true')
    p.add_argument('--tag');p.add_argument('--out-root',type=Path);p.add_argument('--static-plan');p.add_argument('--controller',choices=['fixed','library-fixed','plan-numeric','plan-jev','development-static'],default='plan-jev')
    run(**vars(p.parse_args()))
