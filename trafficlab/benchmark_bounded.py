"""Frozen, exploratory add-on benchmark; never overwrites the v1 benchmark."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from .scenario import ROOT

FILES=['trafficlab/bounded.py','trafficlab/run_bounded.py','trafficlab/run.py','trafficlab/controllers.py','trafficlab/scenario.py','trafficlab/benchmark_bounded.py','scenario/network.net.xml','data/midtown_am.json']


def freeze_protocol():
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in FILES}
    target=ROOT/'results/bounded_protocol.json'
    if target.exists():
        old=json.loads(target.read_text())
        if hashes!=old['source_hashes']:raise RuntimeError('Bounded experiment code changed after its protocol was frozen')
        return
    baseline={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'results/raw').glob('bench_*/result.json'))}
    assert len(baseline)==40
    target.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'design':'Exploratory extension of v1.0.0, paired with its existing traffic schedules. Native Jev is unchanged.','seeds':list(range(11,16)),'scenarios':['am','surge'],'warmup_s':180,'measurement_s':600,'drain_s':180,'step_s':.2,'model':'jev-1.13.0','policy':'Once per local cycle, at avenue age 30–40 s, choose 47/35, 52/30, or 57/25 s avenue/cross greens. Preserve 90 s cycle, original offsets, 3 s yellow and 1 s all-red. Restore baseline next cycle.','timing':'Actual API response latency included at 1x wall clock. Poll every 0.2 s. 2 s deadline; keep baseline on timeout/error. No retries.','observation':'Current queues, vehicles, lane counts, downstream occupancy, and 15 s approach estimate from currently visible positions/speeds only. No future departures.','primary':'Mean accumulated SUMO timeLoss + insertion delay per requested evaluation trip, including unfinished/uninserted trips.','inference':'Five paired seeds per scenario; paired Student-t 95% intervals; exploratory, no field-effect claim.','source_hashes':hashes,'v1_result_hashes':baseline},indent=2)+'\n')


def execute(spec):
    scenario,seed=spec;tag=f'bounded_{scenario}_{seed}';out=ROOT/'results/raw'/tag
    if (out/'result.json').exists():raise RuntimeError(f'Refusing to overwrite {tag}')
    out.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,'-m','trafficlab.run_bounded','--scenario',scenario,'--seed',str(seed),'--realtime','--tag',tag]
    if seed==11:cmd.append('--replay')
    print(f'Starting {tag}',flush=True)
    with (out/'console.log').open('w') as f:run=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    if run.returncode:print(f'FAILED {tag}',flush=True);return False
    r=json.loads((out/'result.json').read_text())
    print(json.dumps({'finished':tag,'valid':r['valid'],'mean_delay_s':r['metrics']['mean_delay_s'],'api_errors':r['execution']['api_errors'],'timing_violations':r['metrics']['bounded_timing_violations']}),flush=True)
    return r['valid']


def main():
    p=argparse.ArgumentParser();p.add_argument('--parallel',type=int,default=10);args=p.parse_args()
    freeze_protocol()
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:outcomes=list(pool.map(execute,[(s,n) for s in ('am','surge') for n in range(11,16)]))
    print(json.dumps({'completed':len(outcomes),'valid':sum(outcomes)}),flush=True)
    if not all(outcomes):raise SystemExit(1)

if __name__=='__main__':main()
