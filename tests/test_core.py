import json
from pathlib import Path
import pytest
from trafficlab.controllers import SignalGuard,MIN_GREEN,MAX_GREEN,YELLOW,ALL_RED,JevWorker
from trafficlab.scenario import validate_flow_balance,build_network,build_demand
from trafficlab.run import summarise_trips


def test_published_internal_counts_conserve_vehicles():
    assert validate_flow_balance()=={'internal_edges_checked':16,'errors':[]}


def test_guard_never_skips_yellow_or_all_red():
    g=SignalGuard({'avenue':'GGr','cross':'rrG'})
    assert not g.switch(MIN_GREEN-.01)
    assert g.switch(MIN_GREEN)
    assert g.state()=='yyr'
    assert g.update(MIN_GREEN+YELLOW-.01)=='yyr'
    assert g.update(MIN_GREEN+YELLOW)=='rrr'
    assert g.update(MIN_GREEN+YELLOW+ALL_RED-.01)=='rrr'
    assert g.update(MIN_GREEN+YELLOW+ALL_RED)=='rrG'


def test_stale_and_invalid_choices_do_not_change_signal():
    g=SignalGuard({'avenue':'Gr','cross':'rG'})
    assert not g.apply('switch',30,9)
    assert not g.apply('arbitrary_state',30,0)
    assert g.apply('switch',30,0)
    assert not g.apply('hold',31,0)
    assert g.update(33)=='rr'
    assert g.update(34)=='rG'


def test_maximum_green_guarantees_service_without_model():
    g=SignalGuard({'avenue':'Gr','cross':'rG'})
    assert g.update(MAX_GREEN)=='yr'
    assert g.forced==1


def test_identical_seed_produces_identical_departures_routes_and_drivers(tmp_path):
    build_network(tmp_path)
    a=build_demand(7,duration=60,directory=tmp_path)
    original=a.with_suffix('.json').read_bytes()
    b=build_demand(7,duration=60,directory=tmp_path)
    assert b.with_suffix('.json').read_bytes()==original
    vehicles=json.loads(original)['vehicles']
    assert all(len(v['route'])>=2 for v in vehicles)


def test_pending_and_unfinished_trips_stay_in_delay_denominator(tmp_path):
    trip=tmp_path/'trips.xml'
    trip.write_text('<tripinfos><tripinfo id="v0" depart="1" arrival="10" departDelay="1" duration="9" timeLoss="3" waitingTime="2" waitingCount="1"/><tripinfo id="v1" depart="2" arrival="-1" departDelay="1" duration="18" timeLoss="8" waitingTime="7" waitingCount="1"/></tripinfos>')
    demand={'requested':3,'vehicles':[{'id':f'v{i}','depart':i,'cohort':True} for i in range(3)]}
    m=summarise_trips(trip,demand,20,15)
    assert m['mean_delay_s']==pytest.approx((4+9+18)/3)
    assert m['completed_trips']==1 and m['unfinished_trips']==2 and m['uninserted_trips']==1
    assert m['conservation']=={'requested':3,'admitted':2,'completed':1,'running':1,'pending':1}


class CompletedFuture:
    def __init__(self,result): self.value=result
    def done(self): return True
    def result(self): return self.value


class InFlightFuture:
    def done(self): return False


def fake_worker(future):
    worker=JevWorker.__new__(JevWorker)
    worker.future=future; worker.pending={'observed_sim_s':10,'wall_started':100,'observations':{}}
    worker.expired=False; worker.records=[]
    return worker


def test_response_cannot_affect_simulation_before_measured_arrival():
    w=fake_worker(CompletedFuture({'wall_completed':100.65,'answers':{}}))
    assert w.poll(10.6)==[]
    assert w.future is not None
    assert w.poll(10.8)[0][0]=='response'
    assert w.records[0]['completed_sim_s']==pytest.approx(10.65)


def test_deadline_fallback_fires_once_and_late_response_is_discarded():
    w=fake_worker(InFlightFuture())
    assert w.poll(11.9)==[]
    assert w.poll(12)[0][0]=='fallback'
    assert w.poll(12.2)==[]
    w.future=CompletedFuture({'wall_completed':102.5,'answers':{}})
    assert w.poll(12.6)==[]
    assert w.records[0]['expired']
