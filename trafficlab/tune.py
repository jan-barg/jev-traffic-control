"""Choose a credible fixed plan on development seeds, before held-out evaluation."""
import contextlib
import json
from .scenario import ROOT,SCENARIO,build_network
from .run import run


def main():
    candidates=[]
    for green in (40,46,52,58):
        for speed in (0,6,9,-9):
            directory=ROOT/'tmp/tuning'/f'g{green}_v{speed}'
            build_network(directory,avenue_green=green,progression_speed=speed)
            values=[]
            for seed in (901,902):
                with open(directory/f'run{seed}.log','w') as f,contextlib.redirect_stdout(f):
                    result=run('fixed',seed=seed,warmup=180,duration=600,drain=180,directory=directory,out_root=directory/'runs')
                if not result['valid']: raise RuntimeError('Invalid development run')
                values.append(result['metrics']['mean_delay_s'])
            row={'avenue_green_s':green,'cross_green_s':82-green,'progression_speed_mps':speed,'mean_delay_s':sum(values)/len(values),'seed_delays':values}
            candidates.append(row); print(json.dumps(row),flush=True)
    selected=min(candidates,key=lambda r:r['mean_delay_s'])
    build_network(SCENARIO,avenue_green=selected['avenue_green_s'],progression_speed=selected['progression_speed_mps'])
    result={'development_seeds':[901,902],'objective':'mean cohort time loss + entry delay per requested trip','selected':selected,'candidates':candidates}
    (ROOT/'results').mkdir(exist_ok=True)
    (ROOT/'results/fixed_plan_tuning.json').write_text(json.dumps(result,indent=2)+'\n')
    print('SELECTED',json.dumps(selected))


if __name__=='__main__': main()
