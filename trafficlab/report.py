"""Aggregate paired replications and export only public benchmark/replay artifacts."""
import json
import math
from pathlib import Path
import shutil
import numpy as np
from scipy.stats import t as student_t
from .scenario import ROOT

METRICS=['mean_delay_s','mean_completed_travel_s','p95_completed_travel_s','mean_queue_vehicles','peak_queue_vehicles','completed_by_demand_end','completed_trips','unfinished_trips','uninserted_trips','mean_stops','congested_link_seconds']
NAMES={'fixed':'Tuned fixed-time','actuated':'Actuated','pressure':'Queue pressure','jev':'Jev'}


def aggregate():
    runs=[json.loads(p.read_text()) for p in sorted((ROOT/'results/raw').glob('bench_*/result.json'))]
    groups={}; paired={}; diagnostics=[]
    for scenario in ('am','surge'):
        groups[scenario]={}; paired[scenario]={}
        for controller in NAMES:
            rows=[r for r in runs if r['scenario']==scenario and r['controller']==controller and r['valid']]
            if not rows: continue
            groups[scenario][controller]={'n':len(rows),'metrics':{m:float(np.mean([r['metrics'][m] for r in rows if r['metrics'][m] is not None])) for m in METRICS},'execution':{'requests':sum(r['execution']['requests'] for r in rows),'api_errors':sum(r['execution']['api_errors'] for r in rows),'deadline_misses':sum(r['execution']['deadline_misses'] for r in rows),'fallback_actions':sum(r['execution']['fallback_actions'] for r in rows),'latency_p50_s':float(np.mean([r['execution']['latency_p50_s'] for r in rows if r['execution']['latency_p50_s'] is not None])) if any(r['execution']['latency_p50_s'] is not None for r in rows) else None,'latency_p95_s':max((r['execution']['latency_p95_s'] or 0) for r in rows),'max_clock_lag_s':max(r['execution']['max_clock_lag_s'] for r in rows),'model_actions_applied':sum(r['execution']['model_actions_applied'] for r in rows),'input_tokens':sum(r['execution']['input_tokens'] for r in rows)}}
            if controller=='jev':
                pooled=[q['latency_s'] for r in rows for q in json.loads((ROOT/'results/raw'/r['id']/'jev_requests.json').read_text())]
                groups[scenario][controller]['execution'].update({f'latency_{p}_s':float(np.quantile(pooled,q)) for p,q in [('p50',.5),('p95',.95),('p99',.99)]})
                groups[scenario][controller]['execution']['latency_aggregation']='pooled requests within scenario'
            if controller=='fixed': continue
            deltas={m:[] for m in METRICS}; used=[]
            for r in rows:
                ref=next((b for b in runs if b['scenario']==scenario and b['controller']=='fixed' and b['seed']==r['seed'] and b['valid']),None)
                if ref is None: continue
                assert r['demand_sha256']==ref['demand_sha256'], 'Unpaired demand schedules'
                assert r['network_sha256']==ref['network_sha256'], 'Mismatched networks'
                used.append(r['seed'])
                for m in METRICS:
                    if r['metrics'][m] is not None and ref['metrics'][m] is not None: deltas[m].append(r['metrics'][m]-ref['metrics'][m])
            stats={}
            for m,v in deltas.items():
                if not v: continue
                mean=float(np.mean(v)); half=float(student_t.ppf(.975,len(v)-1)*np.std(v,ddof=1)/math.sqrt(len(v))) if len(v)>1 else None
                stats[m]={'mean_difference':mean,'ci95':[mean-half,mean+half] if half is not None else None,'n':len(v)}
            paired[scenario][controller]={'seeds':used,'vs':'fixed','metrics':stats}
    for r in runs:
        diagnostics.append({'id':r['id'],'valid':r['valid'],'collisions':r['metrics']['colliding_vehicle_events'],'teleports':r['metrics']['teleports'],'conflicting_green_steps':r['metrics']['conflicting_green_steps'],'conservation':r['metrics']['conservation']})
    sources={'nyc_counts':'https://zap.planning.nyc.gov/projects/2024M0142','sumo':'https://sumo.dlr.de/docs/','typesafe':'https://docs.typesafe.ai/models'}
    summary={'title':'Midtown Traffic Lab','expected_runs':40,'completed_runs':len(runs),'valid_runs':sum(r['valid'] for r in runs),'status':'complete' if len(runs)==40 and all(r['valid'] for r in runs) else 'in_progress','groups':groups,'paired':paired,'diagnostics':diagnostics,'sources':sources,'names':NAMES,'scope':'12 intersections: Sixth and Seventh Avenues, West 25th–30th. June 2024 published AM turning counts. Schematic roads and assumed timings.','limitations':['NYC-informed simulation; not independently validated against real travel times or queues.','Vehicle-only model: no pedestrians, bicycles, transit stops or curbside double parking.','Geometry, lane allocation, vehicle behavior and 5% truck share are assumptions.','Five paired seeds per demand pattern: a pilot, not a definitive effectiveness study.','Completed-trip travel times exclude unfinished trips; primary delay includes all requested evaluation trips.'],'methods':{'replications':5,'seeds':list(range(11,16)),'warmup_s':180,'measurement_s':600,'drain_s':180,'primary':'Mean SUMO timeLoss + entry delay per requested evaluation trip, with unfinished/uninserted vehicles retained.','confidence':'95% paired Student-t intervals across five independent seeds; multiple secondary metrics are descriptive.','clock':'Jev runs at 1× wall time. Conventional algorithms run accelerated with measured computation time rounded up to a simulation step; their travel dynamics use the same 0.2 s step.','api_concurrency':'10 independent Jev replications run concurrently; reported network/provider latency includes that load.'}}
    if (ROOT/'results/fixed_plan_tuning.json').exists(): summary['fixed_plan_tuning']=json.loads((ROOT/'results/fixed_plan_tuning.json').read_text())
    if (ROOT/'results/validation.json').exists(): summary['validation']=json.loads((ROOT/'results/validation.json').read_text())
    destination=ROOT/'viewer/dist/data'; destination.mkdir(parents=True,exist_ok=True)
    manifest={s:{} for s in ('am','surge')}
    for s in manifest:
        for c in NAMES:
            path=ROOT/'results/raw'/f'bench_{s}_{c}_11/replay.json.gz'
            if path.exists():
                filename=f'{s}_{c}.json.gz'; shutil.copy2(path,destination/filename); manifest[s][c]=f'data/{filename}'
    summary['replays']=manifest
    (ROOT/'results/summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    (destination/'summary.json').write_text(json.dumps(summary,separators=(',',':'))+'\n')
    # Small downloadable per-run dataset, with no model prompts or credentials.
    public=[{k:v for k,v in r.items() if k not in ('series',)} for r in runs]
    (destination/'runs.json').write_text(json.dumps(public,separators=(',',':'))+'\n')
    write_report(summary)
    print(json.dumps({'completed_runs':len(runs),'valid_runs':summary['valid_runs'],'replays':manifest}))
    return summary


def write_report(s):
    if s['status']!='complete' or not s.get('validation',{}).get('technical_reproducibility'): return
    v=s['validation'];a=v['primary_audit']
    lines=['# Midtown Traffic Lab — pilot results','',
           'Run on 21 September 2026 with SUMO 1.27.1 and TypeSafe Jev 1.13.0. **The first Jev controller did not improve traffic in this model.** The tuned coordinated fixed plan had lower delay in both demand scenarios. This is a result about this implementation and these assumptions, not a general limit on Jev or AI signal control.','',
           '## Primary result','',
           'All values below are means across five matched traffic seeds. Primary delay is cumulative SUMO time loss plus insertion delay, divided by every requested evaluation trip, including unfinished trips.','',
           '| Demand | Tuned fixed | Actuated | Queue pressure | Jev | Jev minus fixed (95% paired interval) |',
           '|---|---:|---:|---:|---:|---:|']
    for scenario,title in [('am','Published AM'),('surge','Synthetic surge')]:
        g=s['groups'][scenario];p=s['paired'][scenario]['jev']['metrics']['mean_delay_s'];lo,hi=p['ci95']
        lines.append('| '+title+' | '+' | '.join(f"{g[c]['metrics']['mean_delay_s']:.1f} s" for c in NAMES)+f" | +{p['mean_difference']:.1f} s ({lo:.1f} to {hi:.1f}) |")
    lines+=['','Five replications per arm is a pilot. Intervals use the paired Student-t method across seeds, not individual vehicles. They cover seed-to-seed variation within this model, not uncertainty in geometry, behavior or actual NYC operation. No secondary-metric multiple-comparison adjustment is made.','',
            '## Supporting traffic measures','',
            'Travel times include completed trips only and therefore need to be read alongside unfinished demand. Mean/peak queues cover all vehicles in the network during the ten-minute measurement window; peak is the mean of per-run maxima.','']
    for scenario,title in [('am','Published AM demand'),('surge','Synthetic surge demand')]:
        lines += [f'### {title}','','| Controller | Mean trip (s) | P95 trip (s) | Mean / peak queue | Finished by 13:00 | Finished after drain | Unfinished | Stops/trip | Congested link-s |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for c,name in NAMES.items():
            m=s['groups'][scenario][c]['metrics']
            lines.append(f"| {name} | {m['mean_completed_travel_s']:.1f} | {m['p95_completed_travel_s']:.1f} | {m['mean_queue_vehicles']:.1f} / {m['peak_queue_vehicles']:.1f} | {m['completed_by_demand_end']:.1f} | {m['completed_trips']:.1f} | {m['unfinished_trips']:.1f} | {m['mean_stops']:.2f} | {m['congested_link_seconds']:.1f} |")
        lines+=['']
    lines+=['The mean requested evaluation cohort is 693.0 vehicles in AM and 875.8 in surge; counts match across controllers. Every requested vehicle entered the network in every primary run. Stops are SUMO waiting episodes. Congested link-seconds are a spillback proxy: halted vehicles present and occupancy above 80% of assumed storage, not a measured queue-tail position. Delay is accumulated through minute 16; unfinished vehicles would incur additional delay afterward.','',
            '## Real-time inference','',
            f"Across {a['jev_requests']:,} real API batches, latency was {a['latency_s']['p50']*1000:.0f} ms at the median, {a['latency_s']['p95']*1000:.0f} ms at P95, {a['latency_s']['p99']*1000:.0f} ms at P99 and {a['latency_s']['max']*1000:.0f} ms maximum. There were zero API errors, deadline misses or fallback actions. {a['jev_applied_actions']:,} model actions were applied.",'',
            f"Every Jev run advanced at one simulated second per wall second while a separate thread made API calls. Observations and client scheduling are included in measured latency. Actions waited for the actual response and the next simulation poll; maximum extra polling delay was {a['max_polling_delay_s']*1000:.1f} ms with a 200 ms timestep. Maximum host clock lag was {a['max_clock_lag_s']*1000:.1f} ms. All accepted actions were verified against the recorded model answer and arrived before application. Roadside sensor and physical actuation latency remain unmodeled.",'',
            'Ten independent replications ran concurrently, so measured service times include that provider/client load. Replay speed affects presentation only; it never rescales the original API latency. Conventional algorithms ran accelerated, with measured computation delay rounded up to a simulation step.','',
            f"Jev chose hold {a['jev_choices']['hold']:,} times and switch {a['jev_choices']['switch']:,} times. The guard forced {a['jev_forced_max_green_transitions']:,} transitions at maximum green. The controller receives local aggregate state and downstream occupancy, but no explicit arrival forecast or corridor offset target. Poor coordination or the choice policy could explain the worse results; the present experiment does not isolate the cause. Fast inference alone did not produce good control.",'',
            '## What was validated','',
            '- 40/40 primary runs passed technical runtime checks: vehicle conservation, no simulated collisions, no teleports, no conflicting avenue/cross-street greens and acceptable real-time clock lag.',
            '- Eight automated tests passed, covering clearances, minimum/maximum green, stale/invalid actions, delayed responses, deadlines, reproducible demand and unfinished-trip accounting.',
            '- One independent fixed-controller rerun exactly reproduced metrics, movement counts and demand hash.',
            '- All primary simulator/controller/network/data hashes still match the protocol recorded before evaluation. All four arms share identical demand/network hashes for each scenario and seed.',
            f"- The 48 simulated AM turning flows have {v['input_flow_check']['weighted_absolute_relative_error']*100:.2f}% volume-weighted absolute error against the published inputs, averaged across five fixed-plan runs. This is an in-sample consistency check, not independent calibration or field validation.",
            '- 42 additional conventional sensitivity runs passed. Fixed-plan delay stayed below the simple pressure heuristic in every tested variant. These do not validate Jev under changed assumptions.','',
            '| Sensitivity case | Fixed delay (s) | Pressure delay (s) |','|---|---:|---:|']
    for case in v['sensitivity']:lines.append(f"| {case['case'].replace('_',' ')} | {case['mean_delay_s']['fixed']:.1f} | {case['mean_delay_s']['pressure']:.1f} |")
    warnings=sum(p.read_text().count('emergency braking') for p in (ROOT/'results/raw').glob('bench_*/sumo-errors.log'))
    lines+=['',f'SUMO recorded {warnings} emergency-braking warnings in the primary runs. Zero simulated collisions is an implementation check, not evidence of real-world crash safety.','',
            '## Scope and next experiment','',
            'This is a 2D replay of a microscopic SUMO simulation at 12 intersections: Sixth and Seventh Avenues, West 25th–30th Streets. Its 48 AM turning volumes come from Midtown South FEIS Figure 13-6a (June 2024 collection campaign). All 16 internal links balance. Poisson arrivals and sampled turn routes create stochastic traffic realizations. Roads are schematic; lanes, block lengths, speeds, fleet mix and signal settings are assumptions.','',
            'The reference plan was selected from 16 candidates on separate development seeds 901–902: a 90-second cycle, 52/30-second avenue/cross greens and nominal 9 m/s avenue progression. It is not verified NYC DOT timing. All adaptive arms share 22–60-second green limits, three-second yellow and one-second all-red. Their initially synchronized greens differ from the coordinated fixed offsets. The comparison concerns complete controller designs, not an isolated replacement of one timing decision.','',
            'Measurement uses three minutes of warm-up, ten minutes of demand and three minutes of drain. Surge means 50% higher boundary demand during the middle five minutes. It is a synthetic stress case. Pedestrians, bicycles, bus stops, parking interference and observed origin/destination routes are absent. Published FEIS delay estimates are modeled outputs, not independent ground truth.','',
            'A useful next controller would retain the coordinated plan and let Jev make bounded adjustments using predicted arrivals and downstream capacity. Develop it on separate seeds; freeze the policy before testing new seeds. Then obtain actual lane/turn restrictions, signal plans, held-out travel times and queue observations, add pedestrians/transit, and recalibrate before expanding to a neighborhood. The existing runner and viewer support that iteration; this pilot does not justify a borough-scale or real-street benefit claim.','',
            '## Reproduction and sources','',
            'See [README](../README.md) for commands, assumptions and metric definitions; [validation evidence](../results/validation.json), [paired results](../results/summary.json) and [protocol](../results/protocol.json) for machine-readable details. Raw requests, signal actions, SUMO trip logs and replays are retained locally under `results/raw/`.','',
            '[NYC Midtown South study record](https://zap.planning.nyc.gov/projects/2024M0142) · [SUMO trip metrics](https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html) · [TypeSafe documentation](https://docs.typesafe.ai/) · [NYC data audit](NYC_BENCHMARK_AUDIT.md)','']
    report='\n'.join(lines)
    (ROOT/'docs/BENCHMARK_RESULTS.md').write_text(report)
    public_report=report.replace('[README](../README.md)','the project README').replace('[validation evidence](../results/validation.json)','[validation evidence](validation.json)').replace('[paired results](../results/summary.json)','[paired results](summary.json)').replace('[protocol](../results/protocol.json)','[protocol](protocol.json)').replace(' · [NYC data audit](NYC_BENCHMARK_AUDIT.md)','')
    (ROOT/'viewer/dist/data/benchmark-report.md').write_text(public_report)
    shutil.copy2(ROOT/'results/validation.json',ROOT/'viewer/dist/data/validation.json')
    shutil.copy2(ROOT/'results/protocol.json',ROOT/'viewer/dist/data/protocol.json')


if __name__=='__main__': aggregate()
