from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
import time

MIN_GREEN=22.0
MAX_GREEN=60.0
YELLOW=3.0
ALL_RED=1.0
CADENCE=5.0
DEADLINE=2.0


@dataclass
class SignalGuard:
    states: dict
    group: str='avenue'
    stage: str='green'
    since: float=0.0
    epoch: int=0
    forced: int=0

    def age(self,t): return t-self.since

    def eligible(self,t): return self.stage=='green' and self.age(t)>=MIN_GREEN-1e-7

    def switch(self,t):
        if not self.eligible(t): return False
        self.stage='yellow'; self.since=t; self.epoch+=1
        return True

    def update(self,t):
        if self.stage=='green' and self.age(t)>=MAX_GREEN-1e-7:
            self.forced+=1; self.switch(t)
        elif self.stage=='yellow' and self.age(t)>=YELLOW-1e-7:
            self.stage='red'; self.since=t
        elif self.stage=='red' and self.age(t)>=ALL_RED-1e-7:
            self.stage='green'; self.group='cross' if self.group=='avenue' else 'avenue'; self.since=t
        return self.state()

    def state(self):
        s=self.states[self.group]
        return s if self.stage=='green' else s.replace('G','y') if self.stage=='yellow' else 'r'*len(s)

    def apply(self,action,t,epoch):
        if epoch!=self.epoch or not self.eligible(t): return False
        if action not in ('hold','switch'): return False
        return self.switch(t) if action=='switch' else True


def pressure_choice(observation):
    current=observation['current_green']; other='cross' if current=='avenue' else 'avenue'
    scores=observation['approaches']
    # Hysteresis avoids spending clearance time on near-equal short queues.
    return 'switch' if scores[other]['pressure']>scores[current]['pressure']+1.0 else 'hold'


def actuated_choice(observation):
    current=observation['current_green']; other='cross' if current=='avenue' else 'avenue'
    a=observation['approaches']
    return 'switch' if a[other]['queued']>0 and (a[current]['vehicles']==0 or observation['green_age_s']>=40) else 'hold'


class JevWorker:
    """One bounded batch in flight; only the simulation thread can apply signals."""
    def __init__(self):
        from typesafe_sdk import TypeSafeClient, RetryPolicy
        if not os.getenv('TYPESAFE_API_KEY'): raise RuntimeError('TYPESAFE_API_KEY is required for Jev; no substitute controller is allowed.')
        self.client=TypeSafeClient(model=os.getenv('JEV_MODEL','jev-1.13.0'),timeout=4.0,retry=RetryPolicy(max_retries=0))
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.future=None; self.pending=None; self.expired=False
        self.records=[]

    def dispatch(self,observations,t,wall_started):
        if self.future is not None or not observations: return False
        from typesafe_sdk import Choice
        questions={k:Choice(instructions=(f'Control intersection `{k}` using only `intersections.{k}`. '
            'Choose whether to retain its current green for the next five seconds or start a safe transition to the other approach. '
            'Minimize total vehicle delay, preserve flow between neighboring junctions, avoid releasing vehicles into blocked downstream links, '
            'and avoid unnecessary switches because changing direction costs four seconds of clearance. '
            'Pressure and queue values are already computed. Both choices are presently admissible; maximum green is enforced by code.'),
            criteria={'hold':'Keep the current avenue or cross-street green for now.','switch':'Start yellow and all-red, then serve the other approach.'}) for k in observations}
        self.pending={'observed_sim_s':t,'wall_started':wall_started,'observations':observations}
        self.expired=False
        self.future=self.pool.submit(self._call,{'intersections':observations},questions)
        return True

    def _call(self,state,questions):
        try:
            response=self.client.system_one(state=state,questions=questions)
            result={'answers':{k:{'choice':v.choice,'probabilities':v.probabilities,'confidence':v.confidence} for k,v in response.choices.items()},'model':response.model,'usage':response.usage.model_dump()}
        except Exception as error:
            # Exception strings can include request metadata; log only the type.
            result={'error':type(error).__name__,'answers':{}}
        result['wall_completed']=time.perf_counter()
        return result

    def poll(self,t):
        if self.future is None: return []
        p=self.pending; events=[]
        if self.future.done():
            result=self.future.result(); latency=result['wall_completed']-p['wall_started']
            # Never let a response affect simulated time before its real elapsed latency.
            if t+1e-7<p['observed_sim_s']+latency: return []
            record={'observed_sim_s':p['observed_sim_s'],'completed_sim_s':p['observed_sim_s']+latency,'handled_sim_s':t,'latency_s':latency,'expired':self.expired or latency>DEADLINE,**{k:v for k,v in result.items() if k!='wall_completed'},'observations':p['observations']}
            if not self.expired:
                kind='fallback' if latency>DEADLINE or result.get('error') else 'response'
                events.append((kind,p,record))
            self.records.append(record); self.future=None; self.pending=None
        elif not self.expired and t-p['observed_sim_s']>=DEADLINE-1e-7:
            self.expired=True
            events.append(('fallback',p,{'deadline_miss':True}))
        return events

    def close(self):
        # A final pending response is recorded but never applied after the horizon.
        if self.future is not None:
            result=self.future.result(timeout=10)
            p=self.pending
            self.records.append({'observed_sim_s':p['observed_sim_s'],'latency_s':result['wall_completed']-p['wall_started'],'not_applied':'simulation ended',**{k:v for k,v in result.items() if k!='wall_completed'}})
        self.pool.shutdown(); self.client.close()
