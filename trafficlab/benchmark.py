"""Launch independent replications. Each Jev process has a real wall-clock budget."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .scenario import ROOT


def execute(spec):
    scenario,controller,seed=spec
    tag=f'bench_{scenario}_{controller}_{seed}'
    out=ROOT/'results/raw'/tag; out.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,'-m','trafficlab.run','--controller',controller,'--seed',str(seed),'--scenario',scenario,'--warmup','180','--duration','600','--drain','180','--tag',tag]
    if controller=='jev': cmd.append('--realtime')
    if seed==11: cmd.append('--replay')
    print(f'Starting {tag}',flush=True)
    with (out/'console.log').open('w') as f:
        result=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:
        print(f'FAILED {tag}; see {out / "console.log"}',flush=True)
        return False
    data=json.loads((out/'result.json').read_text())
    print(json.dumps({'finished':tag,'valid':data['valid'],'mean_delay_s':data['metrics']['mean_delay_s'],'errors':data['execution']['api_errors'],'clock_lag_max':data['execution']['max_clock_lag_s']}),flush=True)
    return data['valid']


def main():
    p=argparse.ArgumentParser(); p.add_argument('--only',choices=['conventional','jev','all'],default='all'); p.add_argument('--parallel',type=int,default=5); args=p.parse_args()
    controllers=['fixed','actuated','pressure'] if args.only=='conventional' else ['jev'] if args.only=='jev' else ['fixed','actuated','pressure','jev']
    jobs=[(s,c,n) for s in ['am','surge'] for c in controllers for n in range(11,16)]
    protocol=ROOT/'results/protocol.json'
    if not protocol.exists():
        protocol.parent.mkdir(exist_ok=True)
        protocol.write_text(json.dumps({'created_at':datetime.now(timezone.utc).isoformat(),'seeds':list(range(11,16)),'development_seeds':[901,902],'scenarios':{'am':'published AM expected arrival rates','surge':'50% increase in boundary demand during middle half of measurement window'},'warmup_s':180,'measurement_s':600,'drain_s':180,'step_s':.2,'primary_metric':'SUMO timeLoss + entry delay per requested evaluation-cohort trip, including unfinished/uninserted demand','jev':'real API calls; real-time paced; 2 s decision deadline; 5 s cadence; no retries; queue-pressure fallback','geometry':'schematic NYC-informed 12-node grid; observed turns, assumed lanes/timings/behavior','inference':'paired t intervals across independent seeds; pilot n=5, no field-effect claim','source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in list((ROOT/'trafficlab').glob('*.py'))+[ROOT/'scenario/network.net.xml',ROOT/'data/midtown_am.json']}},indent=2)+'\n')
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        outcomes=list(pool.map(execute,jobs))
    print(json.dumps({'completed':len(outcomes),'valid':sum(outcomes),'failed':len(outcomes)-sum(outcomes)}))
    if not all(outcomes): sys.exit(1)


if __name__=='__main__': main()
