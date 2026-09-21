"""Independently audit bounded schedules, measured latency and paired inputs."""
import hashlib,json
from collections import Counter,defaultdict
import numpy as np
from .scenario import ROOT
from .bounded import CHOICES


def audit():
    protocol=json.loads((ROOT/'results/bounded_protocol.json').read_text())
    for path,sha in {**protocol['source_hashes'],**protocol['v1_result_hashes']}.items():
        assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha,path
    rows=[json.loads(p.read_text()) for p in (ROOT/'results/raw').glob('bounded_*/result.json')]
    assert len(rows)==10 and all(r['valid'] for r in rows)
    assert {(r['scenario'],r['seed']) for r in rows}=={(s,n) for s in ('am','surge') for n in range(11,16)}
    latencies=[];ages=[];choices=Counter();applied=0;fallback=0;events_checked=0;cycles_checked=0
    for r in rows:
        assert r['controller']=='bounded-jev' and r['execution']['mode']=='realtime'
        assert r['model']=='jev-1.13.0'
        base=json.loads((ROOT/'results/raw'/f"bench_{r['scenario']}_fixed_{r['seed']}"/'result.json').read_text())
        assert r['demand_sha256']==base['demand_sha256'] and r['network_sha256']==base['network_sha256']
        c=r['metrics']['conservation'];assert c['requested']==c['completed']+c['running']+c['pending']
        directory=ROOT/'results/raw'/r['id'];requests=json.loads((directory/'jev_requests.json').read_text());by_time={q['observed_sim_s']:q for q in requests}
        latencies.extend(q['latency_s'] for q in requests)
        actions=json.loads((directory/'actions.json').read_text());splits={}
        for a in actions:
            if not a['accepted']:continue
            key=(a['junction'],a['cycle']);assert key not in splits,'Multiple choices for one cycle'
            delta=CHOICES[a['action']];splits[key]=delta
            assert a['avenue_green_s']==52+delta and a['cross_green_s']==30-delta
            assert a['avenue_green_s']+a['cross_green_s']+8==90
            if a['source']=='response':
                q=by_time[a['observed_t']]
                assert not q.get('error') and not q.get('expired')
                assert a['t']+1e-7>=q['completed_sim_s']
                assert a['t']-q['completed_sim_s']<=.2+r['execution']['max_clock_lag_s']+1e-7
                assert q['answers'][a['junction']]['choice']==a['action']
                assert q['observations'][a['junction']]['epoch']==a['cycle']
                ages.append(a['t']-a['observed_t']);choices[a['action']]+=1;applied+=1
            else:
                assert a['source']=='fallback' and a['action']=='keep';fallback+=1
        by_junction=defaultdict(list)
        for e in json.loads((directory/'signal_events.json').read_text()):by_junction[e['junction']].append(e)
        for key,events in by_junction.items():
            for before,after in zip(events,events[1:]):
                assert after['phase']==(before['phase']+1)%6
                phase=before['phase'];delta=splits.get((key,before['cycle']),0)
                expected=[52+delta,3,1,30-delta,3,1][phase]
                assert abs(after['t']-before['t']-expected)<=.200001,(r['id'],key,before,after,expected)
                events_checked+=1
            starts=[e for e in events if e['phase']==0]
            for e in starts:assert abs(e['t']-e['cycle_start_s'])<=.200001
            for before,after in zip(starts,starts[1:]):
                assert abs(after['t']-before['t']-90)<1e-6
                cycles_checked+=1
    keep=json.loads((ROOT/'tmp/bounded-validation/bounded_keep_check/result.json').read_text())
    original=json.loads((ROOT/'results/raw/bench_am_fixed_11/result.json').read_text())
    assert all(keep['metrics'][k]==v for k,v in original['metrics'].items())
    result={'valid_runs':len(rows),'protocol_hashes_match':True,'native_results_unchanged':True,'paired_inputs':True,'keep_matches_fixed_exactly':True,'phase_durations_checked':events_checked,'consecutive_cycles_checked':cycles_checked,'cycle_length_s':90,'allowed_shifts_s':[-5,0,5],'timing_violations':0,'no_early_application':True,'requests':len(latencies),'model_actions_applied':applied,'choices':dict(choices),'fallback_actions':fallback,'api_errors':sum(r['execution']['api_errors'] for r in rows),'deadline_misses':sum(r['execution']['deadline_misses'] for r in rows),'latency_s':{k:float(np.quantile(latencies,q)) for k,q in [('p50',.5),('p95',.95),('p99',.99),('max',1)]},'application_age_s':{k:float(np.quantile(ages,q)) for k,q in [('p50',.5),('p95',.95),('max',1)]},'max_clock_lag_s':max(r['execution']['max_clock_lag_s'] for r in rows),'field_validated':False}
    (ROOT/'results/bounded_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
    return result

if __name__=='__main__':audit()
