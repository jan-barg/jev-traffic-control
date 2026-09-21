"""Input fidelity, deterministic reruns and conventional sensitivity checks.

These validate the implementation and assumptions, not field effectiveness.
"""
import contextlib
import hashlib
import json
from pathlib import Path
import numpy as np
from .scenario import ROOT,build_network,COUNTS
from .run import run


def audit_primary():
    runs=[json.loads(p.read_text()) for p in (ROOT/'results/raw').glob('bench_*/result.json')]
    assert len(runs)==40 and all(r['valid'] for r in runs), 'Incomplete or invalid primary matrix'
    expected={(s,c,n) for s in ('am','surge') for c in ('fixed','actuated','pressure','jev') for n in range(11,16)}
    assert {(r['scenario'],r['controller'],r['seed']) for r in runs}==expected
    protocol=json.loads((ROOT/'results/protocol.json').read_text())
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in protocol['source_hashes'].items()}
    assert all(hashes.values()), 'Primary source or network changed after protocol was recorded'
    for scenario in ('am','surge'):
        for seed in range(11,16):
            rows=[r for r in runs if r['scenario']==scenario and r['seed']==seed]
            assert len({r['demand_sha256'] for r in rows})==1
            assert len({r['network_sha256'] for r in rows})==1
    latency=[]; applications=[]; polling_delays=[]; choices={'hold':0,'switch':0}; forced=0
    for r in runs:
        c=r['metrics']['conservation']
        assert c['requested']==c['completed']+c['running']+c['pending']
        if r['controller']!='jev': continue
        directory=ROOT/'results/raw'/r['id']
        requests=json.loads((directory/'jev_requests.json').read_text())
        by_time={q['observed_sim_s']:q for q in requests}
        latency.extend(q['latency_s'] for q in requests)
        forced+=r['execution']['forced_max_green_transitions']
        for a in json.loads((directory/'actions.json').read_text()):
            if a['source']!='response' or not a['accepted']: continue
            q=by_time[a['observed_t']]
            assert not q.get('error') and not q['expired']
            assert a['t']+1e-7>=q['completed_sim_s'], 'Response applied before measured arrival'
            # The dispatch tick can start slightly late relative to wall time.
            # Allow its independently measured clock lag in addition to polling.
            polling_delay=a['t']-q['completed_sim_s']
            assert polling_delay<=r['execution']['step_s']+r['execution']['max_clock_lag_s']+1e-7, 'Excess application delay'
            polling_delays.append(polling_delay)
            assert a['action']==q['answers'][a['junction']]['choice']
            choices[a['action']]+=1
            applications.append(a['t']-a['observed_t'])
    return {'matrix_runs':len(runs),'protocol_hashes_match':hashes,'paired_demand_and_network':True,
            'vehicle_conservation':True,'jev_requests':len(latency),'jev_applied_actions':len(applications),
            'no_early_application':True,'application_within_step_plus_clock_lag':True,
            'max_polling_delay_s':max(polling_delays),
            'latency_s':{k:float(np.quantile(latency,q)) for k,q in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},
            'application_age_s':{k:float(np.quantile(applications,q)) for k,q in [('p50',.5),('p95',.95),('max',1)]},
            'jev_choices':choices,'jev_forced_max_green_transitions':forced,
            'max_clock_lag_s':max(r['execution']['max_clock_lag_s'] for r in runs)}


def main():
    primary=audit_primary()
    tuning=json.loads((ROOT/'results/fixed_plan_tuning.json').read_text())['selected']
    fixed=[json.loads(p.read_text()) for p in (ROOT/'results/raw').glob('bench_am_fixed_*/result.json')]
    detail=[]
    for junction,observed in COUNTS['counts'].items():
        for i,label in enumerate(COUNTS['columns']):
            rates=[r['movement_counts'][junction][i]*3600/r['measurement_s'] for r in fixed]
            detail.append({'junction':junction,'movement':label,'published_vph':observed[i],'simulated_mean_vph':float(np.mean(rates))})
    weighted_error=sum(abs(r['simulated_mean_vph']-r['published_vph']) for r in detail)/sum(r['published_vph'] for r in detail)
    cases=[('base',180,3,1,.2),('short_buffer',120,3,1,.2),('long_buffer',240,3,1,.2),('two_avenue_lanes',180,2,1,.2),('demand_minus_15pct',180,3,.85,.2),('demand_plus_15pct',180,3,1.15,.2),('step_100ms',180,3,1,.1)]
    sensitivity=[]
    for name,buffer,lanes,multiplier,step in cases:
        directory=ROOT/'tmp/validation'/name
        build_network(directory,buffer=buffer,avenue_lanes=lanes,avenue_green=tuning['avenue_green_s'],progression_speed=tuning['progression_speed_mps'])
        outputs=[]
        for controller in ('fixed','pressure'):
            for seed in (301,302,303):
                with (directory/f'{controller}_{seed}.log').open('w') as f,contextlib.redirect_stdout(f):
                    result=run(controller,seed=seed,directory=directory,out_root=directory/'runs',multiplier=multiplier,step=step,warmup=180,duration=600,drain=180)
                outputs.append(result)
        item={'case':name,'buffer_m':buffer,'avenue_lanes':lanes,'demand_multiplier':multiplier,'step_s':step,'all_valid':all(r['valid'] for r in outputs),'mean_delay_s':{c:float(np.mean([r['metrics']['mean_delay_s'] for r in outputs if r['controller']==c])) for c in ('fixed','pressure')}}
        sensitivity.append(item);print(json.dumps(item),flush=True)
    # Independent re-execution of an existing conventional replication.
    repeat_dir=ROOT/'tmp/validation/repeat';repeat_dir.mkdir(parents=True,exist_ok=True)
    with (repeat_dir/'console.log').open('w') as f,contextlib.redirect_stdout(f):
        # The CLI's default is the integer 1. Match it exactly because the stored
        # provenance hashes include JSON metadata (1 and 1.0 serialize differently).
        repeat=run('fixed',seed=11,warmup=180,duration=600,drain=180,out_root=repeat_dir,multiplier=1)
    original=next(r for r in fixed if r['seed']==11)
    deterministic=repeat['metrics']==original['metrics'] and repeat['movement_counts']==original['movement_counts'] and repeat['demand_sha256']==original['demand_sha256']
    result={'field_validated':False,'technical_reproducibility':deterministic,'primary_audit':primary,'input_flow_check':{'kind':'in-sample consistency, not independent validation','movements':48,'replications':len(fixed),'weighted_absolute_relative_error':weighted_error,'detail':detail},'sensitivity':sensitivity,'limits':'Sensitivity checks use conventional controllers only. Jev robustness to different geometry, sensor noise and response-time distributions remains untested.'}
    (ROOT/'results/validation.json').write_text(json.dumps(result,indent=2)+'\n')
    if not deterministic or not all(r['all_valid'] for r in sensitivity):raise RuntimeError('Validation failure; inspect results/validation.json')
    print(json.dumps({'deterministic_rerun':deterministic,'flow_weighted_error':weighted_error,'sensitivity_runs':len(cases)*6}))


if __name__=='__main__':main()
