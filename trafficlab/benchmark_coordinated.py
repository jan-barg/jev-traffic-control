"""Freeze and run the fresh, paired corridor-plan experiment."""
import argparse,hashlib,json,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from .scenario import ROOT

SCENARIOS=('am','surge','shift')
SEEDS=tuple(range(31,36))
CONTROLLERS=('fixed','library-fixed','plan-numeric','plan-jev')
FILES=['trafficlab/coordinated.py','trafficlab/plan_scenario.py','trafficlab/run_coordinated.py',
       'trafficlab/benchmark_coordinated.py','trafficlab/tune_plans.py','trafficlab/run.py',
       'trafficlab/controllers.py','trafficlab/scenario.py','results/plan_library.json',
       'scenario/network.net.xml','data/midtown_am.json']


def freeze():
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
    target=ROOT/'results/coordinated_protocol.json'
    if target.exists():
        assert json.loads(target.read_text())['source_hashes']==hashes,'Experiment code changed after freezing'
        return
    previous={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for pattern in ('bench_*/result.json','bounded_*/result.json') for p in (ROOT/'results/raw').glob(pattern)}
    assert len(previous)==50
    protocol={'created_at':datetime.now(timezone.utc).isoformat(),'design':'Fresh paired pilot after development on seeds 901–902. No prior evaluation seeds reused.',
        'seeds':SEEDS,'scenarios':SCENARIOS,'controllers':CONTROLLERS,'expected_runs':60,
        'warmup_s':180,'measurement_s':600,'drain_s':180,'step_s':.2,'model':'jev-1.13.0',
        'control':'One corridor decision every 90 s, first at t=60 s. Each selected plan installs at local cycle starts after observation time +3 s. Preserve 90 s cycle and original offsets; greens 22–60 s, yellow 3 s, all-red 1 s.',
        'latency':'Jev runs at 1x real time. Forecast preparation, scheduling and actual inference included; 2 s deadline, no retries, retain current plan on failure. Numerical computation measured and applied after its rounded-up simulation-step delay; same installation window.',
        'predictor':'180 s fluid queue forecast at 2 s resolution. Last 60 s observed boundary arrivals, current vehicle positions and speeds, finite link storage, published turn shares, assumed 0.48 veh/s/lane discharge. Terminal penalty 30 s/queued vehicle. No future departures or scenario labels in controller inputs.',
        'shift_scenario':'Baseline until evaluation minute 3:20; then avenue arrivals x0.65 and cross arrivals x2.2 until minute 6:40; then avenue x1.4 and cross x0.6. Synthetic stress scenario.',
        'primary':'Mean accumulated SUMO timeLoss plus insertion delay per requested evaluation trip, including unfinished/uninserted trips.',
        'statistics':'Per-scenario paired Student-t 95% intervals across five seeds. Also report Jev minus numerical and Jev minus best static. Exploratory pilot; no multiplicity adjustment or field-effect claim.',
        'replay_seed':31,'source_hashes':hashes,'previous_result_hashes':previous}
    target.write_text(json.dumps(protocol,indent=2)+'\n')


def execute(spec):
    index,(scenario,controller,seed)=spec;tag=f'plan_{scenario}_{controller}_{seed}';out=ROOT/'results/raw'/tag
    if (out/'result.json').exists():raise RuntimeError(f'Refusing to overwrite {tag}')
    if controller=='plan-jev':time.sleep(index*.7)
    out.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,'-m','trafficlab.run_coordinated','--controller',controller,'--scenario',scenario,'--seed',str(seed),'--tag',tag]
    if controller=='plan-jev':cmd.append('--realtime')
    if seed==31:cmd.append('--replay')
    print('Starting '+tag,flush=True)
    with (out/'console.log').open('w') as log:r=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
    if r.returncode:raise RuntimeError(f'{tag} failed; see console.log')
    result=json.loads((out/'result.json').read_text())
    print(json.dumps({'finished':tag,'valid':result['valid'],'delay_s':result['metrics']['mean_delay_s'],'api_errors':result['execution']['api_errors'],'deadline_misses':result['execution']['deadline_misses']}),flush=True)
    return result['valid']


def main():
    p=argparse.ArgumentParser();p.add_argument('--only',choices=['conventional','jev'],required=True);p.add_argument('--parallel',type=int,default=3);a=p.parse_args()
    freeze();controllers=CONTROLLERS[:-1] if a.only=='conventional' else CONTROLLERS[-1:]
    specs=[(s,c,n) for s in SCENARIOS for c in controllers for n in SEEDS]
    with ThreadPoolExecutor(max_workers=a.parallel) as pool:results=list(pool.map(execute,enumerate(specs)))
    print(json.dumps({'completed':len(results),'valid':sum(results)}),flush=True)
    if not all(results):raise SystemExit(1)

if __name__=='__main__':main()
