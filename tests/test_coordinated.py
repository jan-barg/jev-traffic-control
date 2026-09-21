import contextlib,io,json
from collections import defaultdict
from pathlib import Path
import pytest
from trafficlab.coordinated import candidate_plans,numerical_choice
from trafficlab.run_coordinated import run
from trafficlab.scenario import ROOT
from trafficlab.plan_scenario import demand_factor


def test_candidate_splits_and_numerical_selection():
    meta=json.loads((ROOT/'scenario/network.json').read_text())
    for plan in candidate_plans(meta).values():
        assert len(plan['greens'])==12
        assert all(22<=g<=60 and 22<=82-g<=60 for g in plan['greens'].values())
    assert numerical_choice({'corridor':{'candidate_plans':{'g52':{'objective':100},'flow':{'objective':80}}}})=='flow'


def test_shift_profile_has_no_future_switch_before_it_occurs():
    e={'kind':'cross','to':'6_26'}
    assert demand_factor('shift',e,379.9,180,600)==1
    assert demand_factor('shift',e,380,180,600)==2.2
    assert demand_factor('shift',e,580,180,600)==.6


@pytest.mark.parametrize('plan',['g30','g60','flow'])
def test_persistent_plans_preserve_observed_cycles_and_clearances(plan,tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        r=run(controller='development-static',static_plan=plan,seed=905,warmup=0,duration=90,drain=180,out_root=tmp_path)
    assert r['valid']
    folder=next(tmp_path.iterdir());events=defaultdict(list)
    for event in json.loads((folder/'signal_events.json').read_text()):events[event['junction']].append(event)
    for rows in events.values():
        for a,b in zip(rows,rows[1:]):
            assert b['phase']==(a['phase']+1)%6
            expected=[a['green'],3,1,82-a['green'],3,1][a['phase']]
            assert abs(b['t']-a['t']-expected)<=.200001
        starts=[r['t'] for r in rows if r['phase']==0]
        assert all(abs(b-a-90)<1e-6 for a,b in zip(starts,starts[1:]))


def test_new_runner_fixed_is_exactly_original(tmp_path):
    expected=next(r for r in json.loads((ROOT/'viewer/dist/data/runs.json').read_text()) if r['controller']=='fixed' and r['scenario']=='am' and r['seed']==11)
    with contextlib.redirect_stdout(io.StringIO()):
        r=run(controller='fixed',seed=11,drain=180,out_root=tmp_path)
    assert r['valid'] and r['demand_sha256']==expected['demand_sha256']
    assert all(r['metrics'][k]==v for k,v in expected['metrics'].items())
