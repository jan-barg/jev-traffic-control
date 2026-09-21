import contextlib
import io
import json
from pathlib import Path
import pytest
from trafficlab.bounded import BoundedPlan,CHOICES
from trafficlab.run_bounded import run
from trafficlab.scenario import ROOT


def test_shift_is_not_accumulated_across_cycles():
    p=BoundedPlan(0);assert p.ready(30,0);p.requested=True
    assert p.choose('avenue_plus_5',30.4,0,0)
    assert p.delta==5
    assert not p.choose('cross_plus_5',31,0,0)
    p.update(90)
    assert p.delta==0 and not p.decided and not p.requested
    assert not p.choose('avenue_plus_5',120.4,0,0)  # stale cycle
    assert p.choose('cross_plus_5',120.4,1,0)
    assert p.avenue_green+p.delta+p.cross_green-p.delta+8==90


def test_invalid_or_late_choice_cannot_change_split():
    p=BoundedPlan(0);p.update(30)
    assert not p.choose('anything',30.4,0,0)
    assert not p.choose('avenue_plus_5',42.2,0,0)
    assert not p.choose('avenue_plus_5',35,0,1)
    assert p.delta==0


@pytest.mark.parametrize('policy',list(CHOICES))
def test_sumo_cycle_and_clearance_invariants(policy,tmp_path):
    with contextlib.redirect_stdout(io.StringIO()):
        r=run(policy=policy,seed=901,warmup=0,duration=90,drain=90,out_root=tmp_path)
    assert r['valid']
    assert r['metrics']['bounded_timing_violations']==0
    assert r['metrics']['max_cycle_anchor_error_s']<=.200001
    assert r['metrics']['conflicting_green_steps']==0
    actions=json.loads(next(tmp_path.glob('*/actions.json')).read_text())
    assert actions and all(a['accepted'] for a in actions)
    assert all(a['avenue_green_s']+a['cross_green_s']+8==90 for a in actions)


def test_keep_reproduces_v1_fixed_controller(tmp_path):
    original=json.loads((ROOT/'viewer/dist/data/runs.json').read_text())
    expected=next(r for r in original if r['scenario']=='am' and r['controller']=='fixed' and r['seed']==11)
    with contextlib.redirect_stdout(io.StringIO()):
        actual=run(policy='keep',seed=11,drain=180,out_root=tmp_path)
    assert all(actual['metrics'][k]==v for k,v in expected['metrics'].items())
    assert actual['movement_counts']==expected['movement_counts']
    assert actual['demand_sha256']==expected['demand_sha256']
    assert actual['network_sha256']==expected['network_sha256']
