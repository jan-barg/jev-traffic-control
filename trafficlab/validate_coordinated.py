"""Audit actual plan installations, signal transitions, inputs and inference timing."""
from collections import Counter,defaultdict
import hashlib,json
import numpy as np
from .scenario import ROOT


def audit():
    protocol=json.loads((ROOT/'results/coordinated_protocol.json').read_text())
    for filename,sha in {**protocol['source_hashes'],**protocol['previous_result_hashes']}.items():
        assert hashlib.sha256((ROOT/filename).read_bytes()).hexdigest()==sha,filename
    rows=[json.loads(p.read_text()) for p in (ROOT/'results/raw').glob('plan_*/result.json')]
    expected={(s,c,n) for s in protocol['scenarios'] for c in protocol['controllers'] for n in protocol['seeds']}
    assert len(rows)==60 and {(r['scenario'],r['controller'],r['seed']) for r in rows}==expected
    assert all(r['valid'] for r in rows)
    retry_path=ROOT/'results/coordinated_execution_retry.json'
    excluded=0
    if retry_path.exists():
        retry=json.loads(retry_path.read_text())
        excluded=len(retry['invalid_attempts'])
        assert excluded==15
        assert {(r['scenario'],r['controller'],r['seed']) for r in retry['invalid_attempts']}=={x for x in expected if x[1]=='plan-jev'}
        for r in retry['invalid_attempts']:
            assert not r['valid'] and r['execution']['max_clock_lag_s']>=.2
            for filename,sha in r['files_sha256'].items():
                path=ROOT/retry['local_archive']/r['id']/filename
                assert hashlib.sha256(path.read_bytes()).hexdigest()==sha,str(path)
    counts=Counter();errors=Counter();by_scenario=defaultdict(Counter);agreement=0;model_actions=0;latencies=[];install_lags=[];phase_checks=0;cycle_checks=0;install_checks=0
    for r in rows:
        ref=next(x for x in rows if x['scenario']==r['scenario'] and x['seed']==r['seed'] and x['controller']=='fixed')
        assert r['demand_sha256']==ref['demand_sha256'] and r['network_sha256']==ref['network_sha256']
        c=r['metrics']['conservation'];assert c['requested']==c['completed']+c['running']+c['pending']
        assert not any(r['metrics'][k] for k in ('plan_timing_violations','colliding_vehicle_events','teleports','conflicting_green_steps'))
        folder=ROOT/'results/raw'/r['id'];actions=json.loads((folder/'actions.json').read_text())
        forecasts={f['observed_sim_s']:f for f in json.loads((folder/'plan_forecasts.json').read_text())}
        if r['controller']=='plan-jev':
            assert r['execution']['mode']=='realtime' and r['model']=='jev-1.13.0'
            requests=json.loads((folder/'jev_requests.json').read_text());by_time={q['observed_sim_s']:q for q in requests}
            latencies.extend(q['latency_s'] for q in requests)
            errors.update(q['error'] for q in requests if q.get('error'))
        seen=set()
        for a in actions:
            assert a['accepted'] and a['action'] in r['plan_library']
            assert a['observed_t'] not in seen;seen.add(a['observed_t'])
            assert abs(a['install_after_s']-a['observed_t']-3)<1e-7
            assert a['t']<=a['install_after_s']
            if a['source']=='response':
                q=by_time[a['observed_t']]
                assert not q.get('expired') and not q.get('error')
                assert q['model']=='jev-1.13.0'
                assert a['t']+1e-7>=q['completed_sim_s']
                assert a['t']-q['completed_sim_s']<=.2+r['execution']['max_clock_lag_s']+1e-7
                assert q['answers']['corridor']['choice']==a['action']
                assert q['observations']==forecasts[a['observed_t']]['state']
                model_actions+=1;counts[a['action']]+=1;by_scenario[r['scenario']][a['action']]+=1
                agreement+=a['action']==forecasts[a['observed_t']]['numerical_choice']
            elif a['source']=='numerical':assert a['action']==forecasts[a['observed_t']]['numerical_choice']
            else:assert a['source']=='fallback'
        installed=set()
        for i in json.loads((folder/'plan_installs.json').read_text()):
            key=(i['junction'],i['cycle']);assert key not in installed;installed.add(key)
            assert i['avenue_green_s']==r['plan_library'][i['plan']]['greens'][i['junction']]
            assert i['avenue_green_s']+i['cross_green_s']==82 and 22<=i['avenue_green_s']<=60
            assert abs(i['t']-i['cycle_start_s'])<=.200001
            if i['decision_id'] is not None:
                a=actions[i['decision_id']]
                assert a['accepted'] and a['action']==i['plan'] and i['t']>=a['install_after_s']
                if r['controller']=='plan-jev':install_lags.append(i['t']-a['observed_t'])
            install_checks+=1
        events=defaultdict(list)
        for e in json.loads((folder/'signal_events.json').read_text()):events[e['junction']].append(e)
        for sequence in events.values():
            for a,b in zip(sequence,sequence[1:]):
                assert b['phase']==(a['phase']+1)%6
                duration=[a['green'],3,1,82-a['green'],3,1][a['phase']]
                assert abs(b['t']-a['t']-duration)<=.200001,(r['id'],a,b)
                phase_checks+=1
            starts=[e for e in sequence if e['phase']==0]
            for a,b in zip(starts,starts[1:]):assert abs(b['t']-a['t']-90)<1e-6;cycle_checks+=1
    old=json.loads((ROOT/'results/raw/bench_am_fixed_11/result.json').read_text())
    check=json.loads((ROOT/'tmp/plan-validation/plan_fixed_check/result.json').read_text())
    assert all(check['metrics'][k]==v for k,v in old['metrics'].items())
    live=[r for r in rows if r['controller']=='plan-jev']
    result={'valid_runs':len(rows),'previous_50_results_unchanged':True,'frozen_sources_match':True,'fresh_seeds':protocol['seeds'],
        'paired_inputs':True,'fixed_regression_exact':True,'phase_durations_checked':phase_checks,'cycles_checked':cycle_checks,
        'plan_installations_checked':install_checks,'timing_violations':0,'no_early_response_or_installation':True,
        'model_actions':model_actions,'choices':dict(counts),'choices_by_scenario':{k:dict(v) for k,v in by_scenario.items()},'error_types':dict(errors),'agrees_with_numerical_selector':agreement,
        'requests':len(latencies),'latency_s':{k:float(np.quantile(latencies,q)) for k,q in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},
        'installation_age_s':{k:float(np.quantile(install_lags,q)) for k,q in [('p50',.5),('p95',.95),('max',1)]},
        'api_errors':sum(r['execution']['api_errors'] for r in live),'deadline_misses':sum(r['execution']['deadline_misses'] for r in live),
        'fallback_actions':sum(r['execution']['fallback_actions'] for r in live),'max_clock_lag_s':max(r['execution']['max_clock_lag_s'] for r in live),
        'excluded_clock_invalid_attempts':excluded,'field_validated':False}
    (ROOT/'results/coordinated_validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
    return result

if __name__=='__main__':audit()
