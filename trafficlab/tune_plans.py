"""Select a small corridor-plan library on development traffic only."""
from concurrent.futures import ThreadPoolExecutor
import json,subprocess,sys
from .scenario import ROOT
from .coordinated import candidate_plans

PROFILES=('am','surge','shift','dev_cross','dev_avenue','dev_local')
SEEDS=(901,902)


def execute(spec):
    profile,seed,plan=spec;tag=f'{profile}_{seed}_{plan}';out=ROOT/'tmp/plan-tuning'/tag
    out.mkdir(parents=True,exist_ok=True)
    with (out/'console.log').open('w') as log:
        subprocess.run([sys.executable,'-m','trafficlab.run_coordinated','--controller','development-static','--static-plan',plan,
                        '--scenario',profile,'--seed',str(seed),'--tag',tag,'--out-root',str(out.parent)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    result=json.loads((out/'result.json').read_text());assert result['valid'],tag
    return {'profile':profile,'seed':seed,'plan':plan,'delay_s':result['metrics']['mean_delay_s'],'valid':result['valid']}


def main():
    target=ROOT/'results/plan_library.json'
    if target.exists():raise RuntimeError('Retain existing tuning evidence; do not overwrite a selected library.')
    meta=json.loads((ROOT/'scenario/network.json').read_text());plans=candidate_plans(meta)
    with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(execute,[(p,s,k) for p in PROFILES for s in SEEDS for k in plans]))
    means={p:{k:sum(r['delay_s'] for r in rows if r['profile']==p and r['plan']==k)/len(SEEDS) for k in plans} for p in PROFILES}
    best={p:min(values,key=values.get) for p,values in means.items()}
    overall={k:sum(means[p][k] for p in ('am','surge','shift'))/3 for k in plans};best_static=min(overall,key=overall.get)
    selected={'g52',best_static,*best.values()}
    output={'development_seeds':SEEDS,'training_profiles':PROFILES,'objective':'Mean requested-cohort delay; best static minimizes equal-weight mean across AM, surge and shifting demand.',
            'plans':{k:plans[k] for k in plans if k in selected},'best_static':best_static,'best_by_training_profile':best,'profile_mean_delay_s':means,'runs':rows}
    target.write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k not in ('runs','plans')},indent=2))

if __name__=='__main__':main()
