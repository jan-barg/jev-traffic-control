"""Jev chooses one bounded green split per coordinated cycle.

The native Jev controller is imported unchanged. SUMO retains control of signal
sequence and clearances. A nonzero shift changes this cycle's avenue duration,
then compensates on the cross-street green to restore the original cycle anchor.
"""
from dataclasses import dataclass
import math

from .controllers import JevWorker

CHOICES={'avenue_plus_5':5.0,'keep':0.0,'cross_plus_5':-5.0}
CYCLE=90.0
DECISION_FROM=30.0
DECISION_UNTIL=40.0
APPLY_UNTIL=42.0


@dataclass
class BoundedPlan:
    anchor: float
    avenue_green: float=52.0
    cross_green: float=30.0
    cycle: int=-999
    delta: float=0.0
    requested: bool=False
    decided: bool=False
    compensated: bool=False

    def update(self,t):
        cycle=math.floor((t-self.anchor+1e-7)/CYCLE)
        if cycle!=self.cycle:
            self.cycle=cycle;self.delta=0.0;self.requested=False;self.decided=False;self.compensated=False
        return self.anchor+self.cycle*CYCLE

    def ready(self,t,phase):
        start=self.update(t)
        return phase==0 and not self.requested and DECISION_FROM-1e-7<=t-start<DECISION_UNTIL-1e-7

    def choose(self,action,t,epoch,phase):
        start=self.update(t)
        if action not in CHOICES or epoch!=self.cycle or self.decided or phase!=0 or t-start>APPLY_UNTIL+1e-7:
            return False
        delta=CHOICES[action]
        if not (22<=self.avenue_green+delta<=60 and 22<=self.cross_green-delta<=60):return False
        self.delta=delta;self.decided=True
        return True


class BoundedJevWorker(JevWorker):
    def dispatch(self,observations,t,wall_started):
        if self.future is not None or not observations:return False
        from typesafe_sdk import Choice
        questions={key:Choice(instructions=(
            f'At intersection `{key}`, choose the green split for this cycle using `intersections.{key}`. '
            'A coordinated 90-second plan normally gives the avenue 52 seconds and the cross street 30 seconds. '
            'Only a five-second transfer in either direction is allowed; changes expire at the end of this cycle. '
            'Minimize total vehicle delay while preserving coordinated avenue flow. Consider queued vehicles, '
            'vehicles approaching the stop line, approach lanes and downstream storage. Do not release extra '
            'traffic into a blocked downstream link. A queue on the currently red cross street alone does not '
            'prove the baseline split is wrong: that queue will receive its scheduled green. Keep the baseline '
            'unless current observations support a useful transfer. Do not calculate timings; code supplies '
            'each candidate and enforces all durations and the next cycle start.'), criteria={
                'keep':'Retain the coordinated baseline: 52 s avenue green and 30 s cross-street green.',
                'avenue_plus_5':'Transfer 5 s to the avenue: 57 s avenue, 25 s cross street; avenue need outweighs the cross-street cost.',
                'cross_plus_5':'Transfer 5 s to the cross street: 47 s avenue, 35 s cross street; cross-street need outweighs the avenue cost.'
            }) for key in observations}
        self.pending={'observed_sim_s':t,'wall_started':wall_started,'observations':observations}
        self.expired=False
        self.future=self.pool.submit(self._call,{'intersections':observations},questions)
        return True


class BoundedCoordinator:
    def __init__(self,sim,meta,step):
        self.sim=sim;self.meta=meta;self.step=step
        self.plans={};self.phases={};self.phase_since={};self.events=[]
        self.violations=[];self.return_errors=[];self.decisions=[]
        for key in meta['junctions']:
            logic=sim.trafficlight.getAllProgramLogics(key)[0]
            durations=[p.duration for p in logic.phases]
            if durations!=[52.0,3.0,1.0,30.0,3.0,1.0]:raise ValueError('Bounded Jev requires the frozen 52/30/90 baseline')
            phase=sim.trafficlight.getPhase(key)
            # Read the running SUMO program; do not guess its offset convention.
            anchor=sim.trafficlight.getNextSwitch(key)-sum(durations[:phase+1])
            self.plans[key]=BoundedPlan(anchor)
            self.plans[key].update(0)
            self.phases[key]=phase;self.phase_since[key]=None

    def tick(self,t):
        s=self.sim
        for key,p in self.plans.items():
            start=p.update(t);phase=s.trafficlight.getPhase(key)
            previous=self.phases[key]
            if phase!=previous:
                since=self.phase_since[key]
                if since is not None:
                    elapsed=t-since;low,high=(47,57) if previous==0 else (25,35) if previous==3 else (3,3) if previous in (1,4) else (1,1)
                    if elapsed<low-self.step-1e-6 or elapsed>high+self.step+1e-6:
                        self.violations.append({'junction':key,'phase':previous,'duration_s':elapsed})
                if phase==0:
                    # SUMO exposes a transition on the next discrete simulation step.
                    error=t-start;self.return_errors.append(error)
                    if abs(error)>self.step+1e-6:self.violations.append({'junction':key,'cycle_anchor_error_s':error})
                self.events.append({'junction':key,'t':round(t,3),'phase':phase,'cycle':p.cycle,'cycle_start_s':start})
                self.phase_since[key]=t;self.phases[key]=phase
            if phase==3 and p.delta and not p.compensated:
                # Target the original cross-yellow boundary, restoring coordination.
                remaining=start+p.avenue_green+4+p.cross_green-t
                if remaining<=0:raise RuntimeError('Missed cross-street compensation')
                s.trafficlight.setPhaseDuration(key,remaining)
                p.compensated=True

    def observations(self,t):
        s=self.sim;result={}
        for key,p in self.plans.items():
            phase=s.trafficlight.getPhase(key)
            if not p.ready(t,phase):continue
            start=p.anchor+p.cycle*CYCLE;node=self.meta['junctions'][key];approaches={}
            for kind in ('avenue','cross'):
                edge=node['incoming'][kind];lanes=self.meta['edges'][edge]['lanes']
                queue=s.edge.getLastStepHaltingNumber(edge);vehicles=s.edge.getLastStepVehicleNumber(edge)
                arriving=0
                for v in s.edge.getLastStepVehicleIDs(edge):
                    speed=s.vehicle.getSpeed(v)
                    distance=max(0,s.lane.getLength(s.vehicle.getLaneID(v))-s.vehicle.getLanePosition(v))
                    if speed>.1 and distance/speed<=15:arriving+=1
                downstream=[]
                for outkind in (kind,'cross' if kind=='avenue' else 'avenue'):
                    out=node['outgoing'][outkind];storage=s.lane.getLength(out+'_0')*self.meta['edges'][out]['lanes']/7.5
                    downstream.append({'direction':outkind,'queued':s.edge.getLastStepHaltingNumber(out),'storage_fraction':round(s.edge.getLastStepVehicleNumber(out)/max(storage,1),3)})
                approaches[kind]={'queued':queue,'queued_per_lane':round(queue/lanes,2),'vehicles':vehicles,'lanes':lanes,'approaching_within_15s_at_current_speed':arriving,'downstream':downstream}
            result[key]={'epoch':p.cycle,'current_green':'avenue','cycle_age_s':round(t-start,3),'cycle_end_s':round(start+CYCLE,3),
                         'baseline_green_s':{'avenue':52,'cross':30},'approaches':approaches}
        return result

    def mark_requested(self,obs):
        for key in obs:self.plans[key].requested=True

    def apply(self,key,action,t,epoch,source,observed_t):
        p=self.plans[key];phase=self.sim.trafficlight.getPhase(key)
        accepted=p.choose(action,t,epoch,phase);start=p.anchor+p.cycle*CYCLE
        if accepted and p.delta:
            self.sim.trafficlight.setPhaseDuration(key,start+p.avenue_green+p.delta-t)
        record={'t':round(t,3),'junction':key,'action':action,'accepted':accepted,'source':source,'observed_t':observed_t,'cycle':epoch}
        if accepted:record.update(avenue_green_s=p.avenue_green+p.delta,cross_green_s=p.cross_green-p.delta,shift_s=p.delta,next_cycle_start_s=start+CYCLE)
        self.decisions.append(record)
        return accepted
